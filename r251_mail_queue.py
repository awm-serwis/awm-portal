"""R251: Customer-requested report emails, delivered only by AWM PRO's configured Gmail.
The portal never stores Gmail credentials or sends the message.
"""
import hmac
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from flask import request, session, jsonify

def install(app):
    from supabase_backend import sb
    bucket=os.getenv("SUPABASE_BUCKET","awm-files")

    def error(msg,code): return jsonify(ok=False,error=msg),code
    def api_authorized():
        key=os.getenv("AWM_API_KEY","AWM-CHANGE-ME")
        supplied=request.headers.get("X-AWM-Key","")
        return key!="AWM-CHANGE-ME" and bool(key) and hmac.compare_digest(supplied,key)
    def same_origin():
        origin=request.headers.get("Origin","").rstrip("/")
        return (not origin or origin==request.host_url.rstrip("/")) and request.headers.get("Sec-Fetch-Site","same-origin") in ("same-origin","none")
    def table(): return sb.table("awm_report_mail_queue")
    def case_record(cid):
        return (sb.table("awm_workshop_cases")
                .select("id,sections,vehicle,repair_no,desktop_case_id")
                .eq("id",str(cid)).limit(1).execute().data or [])
    def is_guest_permitted(record):
        user=session.get("user")
        if not isinstance(user,dict) or user.get("role")!="workshop_guest" or user.get("id") is None:return False
        sections=record.get("sections") or {}
        return isinstance(sections,dict) and str(user["id"]) in [str(v) for v in sections.get("_awm_allowed_user_ids",[])]

    @app.post("/api/warsztat/cases/<uuid:cid>/request-email-report")
    def request_email_report_r251(cid):
        if not same_origin():return error("Niedozwolone pochodzenie",403)
        try:
            rows=case_record(cid)
            if not rows:return error("Nie znaleziono pojazdu",404)
            row=rows[0]
            if not is_guest_permitted(row):return error("Brak dostępu do pojazdu",403)
            payload=request.get_json(silent=True) or {}
            if not isinstance(payload,dict):return error("Nieprawidłowy formularz",400)
            recipient=str(payload.get("email") or "").strip()
            if len(recipient)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",recipient):
                return error("Podaj poprawny adres e-mail",400)
            attachments=(row.get("sections") or {}).get("_awm_attachments") or []
            reports=[x for x in attachments if isinstance(x,dict) and x.get("kind")=="report" and x.get("mime")=="application/pdf" and x.get("path") and x.get("id")]
            if not reports:return error("Brak gotowego raportu PDF",409)
            chosen=reports[-1]
            aid=str(uuid.UUID(str(chosen["id"])))
            recent=(table().select("id,recipient_email,status,requested_at")
                 .eq("case_id",str(cid))
                 .gte("requested_at",(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat())
                 .order("requested_at",desc=True).limit(15).execute().data or [])
            waiting=next((x for x in recent if x["status"] in ("pending","claimed") and x["recipient_email"].casefold()==recipient.casefold()),None)
            if waiting:return jsonify(ok=True,queued=True,already_queued=True,request_id=waiting["id"],message="Żądanie jest już w kolejce AWM PRO")
            if len(recent)>=5:return error("Limit 5 próśb na pojazd na dobę; skontaktuj się z warsztatem",429)
            saved=table().insert({"case_id":str(cid),"recipient_email":recipient,
                       "report_attachment_id":aid,"status":"pending"}).execute().data or []
            if not saved:return error("Nie zapisano prośby",503)
            return jsonify(ok=True,queued=True,request_id=saved[0]["id"],message="Prośbę przekazano do AWM PRO. Wysyłka nastąpi po obsłużeniu przez warsztat"),202
        except Exception:
            app.logger.exception("R251 cannot enqueue email request")
            return error("Nie można zapisać prośby o raport",503)

    @app.get("/api/admin/workshop/report-mail-queue")
    def report_queue_list_r251():
        if not api_authorized():return error("Brak autoryzacji AWM",403)
        try:
            rows=table().select("id,case_id,recipient_email,report_attachment_id,status,requested_at,error").in_("status",["pending","failed"]).order("requested_at").limit(200).execute().data or []
            return jsonify(ok=True,requests=rows)
        except Exception:
            app.logger.exception("R251 cannot list email queue")
            return error("Kolejka niedostępna",503)

    @app.post("/api/admin/workshop/report-mail-queue/<uuid:qid>/claim")
    def report_queue_claim_r251(qid):
        if not api_authorized():return error("Brak autoryzacji AWM",403)
        data=request.get_json(silent=True) or {}
        worker=str(data.get("worker") or "").strip()[:100]
        if not worker:return error("Brak identyfikatora stanowiska",400)
        try:
            result=table().update({"status":"claimed","claimed_at":datetime.now(timezone.utc).isoformat(),"claimed_by":worker,"error":None}).eq("id",str(qid)).in_("status",["pending","failed"]).execute().data or []
            if not result:return error("Zadanie jest już obsługiwane lub wysłane",409)
            return jsonify(ok=True,request=result[0])
        except Exception:
            app.logger.exception("R251 cannot claim email")
            return error("Nie można zarezerwować wiadomości",503)

    @app.get("/api/admin/workshop/report-mail-queue/<uuid:qid>/pdf")
    def report_queue_pdf_r251(qid):
        if not api_authorized():return error("Brak autoryzacji AWM",403)
        from flask import Response
        try:
            jobs=table().select("id,case_id,report_attachment_id,status").eq("id",str(qid)).limit(1).execute().data or []
            if not jobs:return error("Brak zadania",404)
            job=jobs[0]
            if job["status"]!="claimed":return error("Najpierw zarezerwuj zadanie",409)
            cases=case_record(job["case_id"])
            if not cases:return error("Brak pojazdu",404)
            records=(cases[0].get("sections") or {}).get("_awm_attachments") or []
            matching=next((a for a in records if isinstance(a,dict) and str(a.get("id"))==str(job["report_attachment_id"]) and a.get("kind")=="report" and a.get("mime")=="application/pdf"),None)
            if not matching:return error("Raport został usunięty",404)
            raw=sb.storage.from_(bucket).download(matching["path"])
            if not raw.startswith(b"%PDF-") or len(raw)>12*1024*1024:return error("Nieprawidłowy raport",503)
            response=Response(raw,mimetype="application/pdf")
            response.headers["Content-Disposition"]="attachment; filename=raport_AWM.pdf"
            response.headers["Cache-Control"]="private, no-store"
            response.headers["X-Content-Type-Options"]="nosniff"
            return response
        except Exception:
            app.logger.exception("R251 pdf download failure")
            return error("Pobranie raportu nie powiodło się",503)

    @app.post("/api/admin/workshop/report-mail-queue/<uuid:qid>/complete")
    def report_queue_complete_r251(qid):
        if not api_authorized():return error("Brak autoryzacji AWM",403)
        data=request.get_json(silent=True) or {}
        state=data.get("status")
        if state not in ("sent","failed"):return error("Nieprawidłowy status",400)
        worker=str(data.get("worker") or "").strip()[:100]
        if not worker:return error("Brak identyfikatora stanowiska",400)
        message_id=str(data.get("message_id") or "")[:250]
        if state=="sent" and not message_id:return error("Brak potwierdzenia wysyłki Gmail",400)
        try:
            saved=table().update({"status":state,"completed_at":datetime.now(timezone.utc).isoformat(),
                "sent_message_id":message_id if state=="sent" else None,
                "error":str(data.get("error") or "")[:500] if state=="failed" else None}).eq("id",str(qid)).eq("status","claimed").eq("claimed_by",worker).execute().data or []
            if not saved:return error("Zadanie nie zostało zarezerwowane przez to stanowisko",409)
            return jsonify(ok=True,status=state)
        except Exception:
            app.logger.exception("R251 cannot complete email")
            return error("Nie zapisano rezultatu wysyłki",503)

    @app.get("/api/admin/workshop/report-mail-queue/<uuid:qid>/case")
    def report_queue_case_r251(qid):
        if not api_authorized():return error("Brak autoryzacji AWM",403)
        try:
            jobs=table().select("case_id").eq("id",str(qid)).limit(1).execute().data or []
            if not jobs:return error("Brak zadania",404)
            rows=case_record(jobs[0]["case_id"])
            if not rows:return error("Brak pojazdu",404)
            row=rows[0]
            sec=row.get("sections") or {}
            return jsonify(ok=True,repair_no=row.get("repair_no"),vehicle=row.get("vehicle"),costs=sec.get("koszty") or {})
        except Exception:return error("Nie można pobrać danych raportu",503)
