"""R238 — durable workshop intake stored in Supabase. No automatic desktop import."""
import os, secrets, hmac, re
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, session
from awm_photo_payload import decode_photos

bp = Blueprint("r238_workshop", __name__)
READ_ACTIONS = ("history", "attachment")
ATTACHMENT_LIMIT = 5 * 1024 * 1024

def store():
    from supabase_backend import sb
    return sb.table("awm_intake_requests")

def authorized():
    user = session.get("user") or {}
    token = request.headers.get("X-AWM-Intake-Token", "")
    expected = os.environ.get("AWM_INTAKE_ADMIN_TOKEN", "")
    return user.get("role") == "admin" or bool(expected and hmac.compare_digest(token, expected))

@bp.post("/api/warsztat/r238/requests")
def create_request():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="Nieprawidłowe dane"), 400
    customer = str(data.get("customer") or "").strip()[:180]
    registration = str(data.get("registration") or "").strip().upper()[:80]
    description = str(data.get("description") or "").strip()[:5000]
    email = str(data.get("email") or "").strip()[:254]
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Nieprawidłowy adres e-mail"), 400
    if not registration or not description:
        return jsonify(error="Wymagane: rej / marka i model oraz opis usterki"), 400
    now = datetime.now(timezone.utc).isoformat()
    if authorized():
        marker = re.search(r"\[AWM-MOBILE:[0-9a-f]{32}\]$", description)
        if marker:
            try:
                existing = store().select("public_ref,status").like("description","%"+marker.group()).limit(1).execute().data or []
                if existing:
                    return jsonify(ok=True,reference=existing[0]["public_ref"],status=existing[0]["status"],already_exists=True),200
            except Exception:
                return jsonify(error="Nie udało się zweryfikować duplikatu"),503
    ref = "AWM-" + secrets.token_hex(8).upper()
    try:
        store().insert({"public_ref":ref, "created_utc":now, "customer":customer,
          "email":email, "phone":str(data.get("phone") or "")[:50],
          "registration":registration, "vehicle":str(data.get("vehicle") or "")[:200],
          "description":description, "status":"new", "updated_utc":now}).execute()
    except Exception:
        bp.logger.exception("R238 intake write failed") if hasattr(bp,"logger") else None
        return jsonify(error="Nie udało się zapisać zgłoszenia"), 503
    return jsonify(ok=True, reference=ref, status="new"), 201


@bp.post("/api/warsztat/r238/requests/<int:item_id>/mail-detail")
def update_mail_detail(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    if request.content_length is None or request.content_length > 250000:
        return jsonify(error="Przekroczono limit danych"),413
    data=request.get_json(silent=True)
    if not isinstance(data,dict): return jsonify(error="Nieprawidłowe dane"),400
    marker=data.get("marker")
    body=data.get("body")
    subject=data.get("subject","")
    if not isinstance(marker,str) or not re.fullmatch(r"\[AWM-MOBILE:[0-9a-f]{32}\]",marker):
        return jsonify(error="Nieprawidłowy identyfikator"),400
    if not isinstance(body,str) or not body.strip() or len(body)>32000 or not isinstance(subject,str) or len(subject)>300:
        return jsonify(error="Nieprawidłowa treść wiadomości"),400
    try:
        rows=store().select("id,description,mail_detail").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Brak zgłoszenia"),404
        current=rows[0]["description"] or ""
        if not current.endswith(marker): return jsonify(error="Niezgodny identyfikator zgłoszenia"),409
        if rows[0].get("mail_detail"): return jsonify(ok=True,already_exists=True)
        detail=(subject.strip()+"\n\n" if subject.strip() else "")+body.strip()
        changed=store().update({"mail_detail":detail}).eq("id",item_id).eq("description",current).is_("mail_detail","null").execute().data or []
        if not changed: return jsonify(error="Zgłoszenie zmienione; odśwież"),409
        return jsonify(ok=True)
    except Exception:
        return jsonify(error="Nie udało się zapisać pełnej treści"),503


@bp.get("/api/warsztat/r238/requests")
def list_requests():
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    try:
        rows = store().select("*").order("id", desc=True).limit(500).execute().data or []
    except Exception:
        return jsonify(error="Nie udało się pobrać zgłoszeń"), 503
    try:
        rows = mobile_overlay(rows)
    except Exception:
        return jsonify(error="Nie udało się odczytać statusów mobile"),503
    return jsonify(ok=True, requests=rows, mail_reply_all=True, mail_history_r419=True)

@bp.post("/api/warsztat/r238/requests/<int:item_id>/start-repair")
def start_repair(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    try:
        rows = store().select("id,status").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Nie znaleziono zgłoszenia"), 404
        if rows[0]["status"] == "repair": return jsonify(ok=True, already_moved=True)
        if rows[0]["status"] not in ("new", "order"): return jsonify(error="Nieprawidłowy status"), 409
        now = datetime.now(timezone.utc).isoformat()
        changed = store().update({"status":"repair","repair_started_utc":now,"updated_utc":now}).eq("id",item_id).in_("status",["new","order"]).execute().data or []
        if not changed: return jsonify(error="Zgłoszenie zostało już zmienione"), 409
    except Exception:
        return jsonify(error="Nie udało się zmienić statusu"), 503
    return jsonify(ok=True, status="repair")

@bp.post("/api/warsztat/r238/requests/<int:item_id>/to-order")
def move_to_order(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    try:
        rows=store().select("id,status").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Nie znaleziono zgłoszenia"),404
        if rows[0]["status"]=="order": return jsonify(ok=True,already_moved=True,status="order")
        if rows[0]["status"]!="new": return jsonify(error="Zgłoszenie nie jest nowe"),409
        changed=store().update({"status":"order","updated_utc":datetime.now(timezone.utc).isoformat()}).eq("id",item_id).eq("status","new").execute().data or []
        if not changed: return jsonify(error="Zgłoszenie zostało już zmienione"),409
    except Exception:
        return jsonify(error="Nie udało się przenieść do zleceń"),503
    return jsonify(ok=True,status="order")

@bp.delete("/api/warsztat/r238/requests/<int:item_id>")
def delete_request(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    try:
        rows=store().select("id").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Nie znaleziono zgłoszenia"),404
        store().delete().eq("id",item_id).execute()
    except Exception:
        return jsonify(error="Nie udało się usunąć zgłoszenia"),503
    return jsonify(ok=True,deleted=item_id)


# R399: authenticated mobile actions; Gmail delivery remains on the desktop.
def mobile_jobs():
    from supabase_backend import sb
    return sb.table("awm_mobile_actions")

def mobile_overlay(rows):
    if not rows:
        return rows
    ids = [r["id"] for r in rows]
    actions = []
    for i in range(0, len(ids), 50):
        actions.extend(mobile_jobs().select("request_id,kind,state").in_("request_id", ids[i:i+50]).eq("state","done").in_("kind",["check","complete","delete"]).execute().data or [])
    deleted = {a["request_id"] for a in actions if a["kind"] == "delete"}
    completed = {a["request_id"] for a in actions if a["kind"] in ("check","complete")}
    return [dict(r,status="completed") if r["id"] in completed else r for r in rows if r["id"] not in deleted]

@bp.post("/api/warsztat/r238/requests/<int:item_id>/mobile-action")
def enqueue_mobile(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    if request.content_length is None or request.content_length > 3500000:
        return jsonify(error="Przekroczono limit danych lub brak rozmiaru"),413
    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict): return jsonify(error="Nieprawidłowe dane"),400
    kind = data.get("kind")
    if kind not in ("check","complete","reply","delete","reply_photos","reply_edited","reply_edited_photos",*READ_ACTIONS): return jsonify(error="Nieprawidłowa akcja"),400
    if kind in ("reply_photos","reply_edited_photos"):
        try: decode_photos(data.get("photos"))
        except ValueError as exc: return jsonify(error=str(exc)),400
    elif "photos" in data:
        return jsonify(error="Zdjęcia wymagają akcji reply_photos"),400
    try:
        rows = store().select("*").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Brak zgłoszenia"),404
        current = mobile_overlay(rows)
        if not current: return jsonify(error="Zgłoszenie usunięte"),409
        row = current[0]
        if kind in ("check","complete") and row["status"] != "new": return jsonify(error="Zgłoszenie nie jest nowe"),409
        if kind not in READ_ACTIONS:
            active = mobile_jobs().select("id,kind,state").eq("request_id",item_id).in_("state",["queued","processing"]).in_("kind",["check","complete","reply","delete","reply_photos","reply_edited","reply_edited_photos"]).limit(1).execute().data or []
            if active: return jsonify(error="Operacja jest już w kolejce",job=active[0]),409
        payload = {"row":row}
        if kind in (*READ_ACTIONS,"reply_edited","reply_edited_photos"):
            if not re.search(r"\[AWM-MOBILE:[0-9a-f]{32}\]$",str(row.get("description",""))): return jsonify(error="Brak zgłoszenia Gmail"),400
        if kind == "attachment":
            message, part = data.get("message"), data.get("part")
            if not isinstance(message,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",message):
                return jsonify(error="Nieprawidłowy identyfikator wiadomości"),400
            if not isinstance(part,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{0,128}",part):
                return jsonify(error="Nieprawidłowy identyfikator załącznika"),400
            payload.update(message=message,part=part)
        if kind in READ_ACTIONS:
            now = datetime.now(timezone.utc)
            mobile_jobs().update({"payload":{},"read_expires_at":None}).lt("read_expires_at",now.isoformat()).eq("state","done").in_("kind",list(READ_ACTIONS)).execute()
            mobile_jobs().update({"payload":{},"read_expires_at":None,"state":"failed","error":"Upłynął czas oczekiwania na komputer"}).lt("read_expires_at",now.isoformat()).in_("state",["queued","processing"]).in_("kind",list(READ_ACTIONS)).execute()
            pending = mobile_jobs().select("id,payload").eq("request_id",item_id).eq("kind",kind).in_("state",["queued","processing"]).execute().data or []
            for job in pending:
                if all(job["payload"].get(key) == payload.get(key) for key in ("message","part")):
                    return jsonify(ok=True,job=job["id"]),202
        if kind in ("reply_edited","reply_edited_photos"):
            recipients=data.get("recipients")
            if not isinstance(recipients,dict): return jsonify(error="Brak odbiorców"),400
            for group in ("to","cc"):
                values=recipients.get(group)
                if not isinstance(values,list) or len(values)>30 or any(not isinstance(v,str) or not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+",v) for v in values): return jsonify(error="Nieprawidłowi odbiorcy"),400
            if not recipients["to"]: return jsonify(error="Brak Do"),400
            payload["recipients"]={k:recipients[k] for k in ("to","cc")}
            thread=data.get("thread")
            if not isinstance(thread,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",thread): return jsonify(error="Brak wątku"),400
            payload["thread"]=thread
        if kind in ("complete","reply","reply_photos","reply_edited","reply_edited_photos"):
            email = str(row.get("email") or "").strip()
            if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+",email): return jsonify(error="Brak poprawnego adresu nadawcy zgłoszenia"),400
            body = "Dzień dobry,\n\nZlecenie zostało zrealizowane.\n\nPozdrawiamy AWM Warsztat" if kind == "complete" else str(data.get("body") or "").strip()
            if not body or len(body)>5000: return jsonify(error="Treść odpowiedzi: 1–5000 znaków"),400
            payload.update(email=email,body=body)
            if kind in ("reply_photos","reply_edited_photos"): payload["photos"] = data["photos"]
        reply_all = kind in ("complete","reply","reply_photos") and data.get("reply_all") is True and bool(re.search(r"\[AWM-MOBILE:[0-9a-f]{32}\]$",str(row.get("description",""))))
        values = dict(request_id=item_id,kind=kind,payload=payload,reply_all=reply_all)
        if kind in READ_ACTIONS:
            values["read_expires_at"] = (now + timedelta(minutes=2)).isoformat()
        inserted = mobile_jobs().insert(values).execute().data or []
        if not inserted: raise RuntimeError("no job")
        return jsonify(ok=True,job=inserted[0]["id"]),202
    except Exception:
        return jsonify(error="Nie zapisano lub nie potwierdzono kolejki; odśwież przed ponowieniem"),503

@bp.get("/api/warsztat/r238/mobile-actions/<int:job_id>")
def mobile_state(job_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    try:
        result=mobile_jobs().select("id,state,error,kind,payload,read_expires_at").eq("id",job_id).limit(1).execute().data or []
        if result:
            job=result[0]; payload=job.pop("payload",{}) or {}; kind=job.pop("kind",None)
            expires = job.pop("read_expires_at",None)
            if kind in READ_ACTIONS:
                if not expires or datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
                    return jsonify(error="Wynik wygasł. Odśwież korespondencję."),410
                if job["state"]=="done": job[kind]=payload.get(kind)
        return (jsonify(ok=True,job=result[0]),200) if result else (jsonify(error="Brak operacji"),404)
    except Exception:
        return jsonify(error="Nie udało się pobrać stanu operacji"),503

@bp.post("/api/warsztat/r238/mobile-actions/claim")
def claim_mobile():
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    try:
        data = request.get_json(silent=True) or {}
        kinds = ["check","complete","reply","delete"]
        if isinstance(data,dict) and data.get("photo_worker") == 407: kinds.append("reply_photos")
        if isinstance(data,dict) and data.get("history_worker")==419 and data.get("mail_worker")==409:
            kinds.extend(["history","reply_edited","reply_edited_photos"])
            if data.get("attachment_worker")==419: kinds.append("attachment")
        query=mobile_jobs().select("id").eq("state","queued").in_("kind",kinds)
        if not (isinstance(data,dict) and data.get("mail_worker") == 409):
            query=query.eq("reply_all",False)
        candidates=query.order("id").limit(5).execute().data or []
        for candidate in candidates:
            changed=mobile_jobs().update({"state":"processing"}).eq("id",candidate["id"]).eq("state","queued").execute().data or []
            if changed: return jsonify(ok=True,job=changed[0])
        return jsonify(ok=True,job=None)
    except Exception:
        return jsonify(error="Nie udało się pobrać kolejki"),503

@bp.post("/api/warsztat/r238/mobile-actions/<int:job_id>/finish")
def finish_mobile(job_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"),403
    if request.content_length is None or request.content_length > 7100000:
        return jsonify(error="Przekroczono limit danych"),413
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict): return jsonify(error="Nieprawidłowe dane"),400
    state=data.get("state")
    if state not in ("done","failed"): return jsonify(error="Nieprawidłowy stan"),400
    try:
        update={"state":state,"error":str(data.get("error") or "")[:500]}
        rows=mobile_jobs().select("kind,payload").eq("id",job_id).eq("state","processing").limit(1).execute().data or []
        if rows and rows[0]["kind"] in READ_ACTIONS:
            update["read_expires_at"]=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()
            if state=="failed":
                update["payload"]={}
        if rows and rows[0]["kind"] == "attachment" and state=="done":
            attachment=data.get("attachment")
            if not isinstance(attachment,dict) or not isinstance(attachment.get("data"),str) or len(attachment["data"]) > ((ATTACHMENT_LIMIT+2)//3)*4:
                return jsonify(error="Nieprawidłowy lub za duży załącznik"),400
            update["payload"]={"attachment":attachment}
        if rows and rows[0]["kind"] == "history" and state=="done":
            history=data.get("history")
            if not isinstance(history,dict) or not isinstance(history.get("messages"),list): return jsonify(error="Brak historii"),400
            import json
            if len(json.dumps(history,ensure_ascii=False).encode())>2000000: return jsonify(error="Historia za duża"),413
            thread=history.get("thread")
            if not isinstance(thread,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",thread):
                return jsonify(error="Brak identyfikatora Gmail"),400
            request_id=rows[0]["payload"]["row"]["id"]
            store().update({"gmail_thread_id":thread}).eq("id",request_id).execute()
            update["payload"]={"history":history}
        if rows and rows[0]["kind"] in ("reply_photos","reply_edited_photos"):
            payload=dict(rows[0]["payload"])
            payload.pop("photos",None)
            update["payload"]=payload
        changed=mobile_jobs().update(update).eq("id",job_id).eq("state","processing").execute().data or []
        return (jsonify(ok=True),200) if changed else (jsonify(error="Operacja nie jest przetwarzana"),409)
    except Exception:
        return jsonify(error="Nie udało się zapisać stanu operacji"),503
