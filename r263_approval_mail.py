"""R263: explicit customer-requested copy of repair approval, via AWM PRO Gmail.

Independent of diagnostic PDF and of the existing report queue.
"""
import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from flask import request, session, jsonify

def install(app):
    from supabase_backend import sb
    def response_error(msg, code):
        return jsonify(ok=False,error=msg), code
    def authorized():
        secret=os.getenv('AWM_API_KEY','AWM-CHANGE-ME')
        value=request.headers.get('X-AWM-Key','')
        return secret not in ('','AWM-CHANGE-ME') and bool(value) and hmac.compare_digest(secret,value)
    def same_origin():
        origin=request.headers.get('Origin','').rstrip('/')
        return (not origin or origin==request.host_url.rstrip('/')) and request.headers.get('Sec-Fetch-Site','same-origin') in ('same-origin','none')
    def jobs():
        return sb.table('awm_approval_mail_queue')
    def get_case(cid):
        return (sb.table('awm_workshop_cases')
                .select('id,vehicle,repair_no,sections')
                .eq('id',str(cid)).limit(1).execute().data or [])
    def permitted(case):
        u=session.get('user')
        if not isinstance(u,dict) or u.get('role')!='workshop_guest' or u.get('id') is None:
            return False
        allowed=(case.get('sections') or {}).get('_awm_allowed_user_ids') or []
        return str(u['id']) in [str(x) for x in allowed]
    def approval(case):
        value=(case.get('sections') or {}).get('_awm_approval') or {}
        return value if isinstance(value,dict) else {}

    @app.post('/api/warsztat/cases/<uuid:cid>/request-approval-copy')
    def r263_client_approval_copy(cid):
        if not same_origin():return response_error('Niedozwolone pochodzenie',403)
        try:
            cases=get_case(cid)
            if not cases:return response_error('Nie znaleziono pojazdu',404)
            case=cases[0]
            if not permitted(case):return response_error('Brak dostępu do pojazdu',403)
            consent=approval(case)
            if consent.get('status')!='approved' or not consent.get('decided_at') or not consent.get('request_id'):
                return response_error('Brak zapisanej zgody na naprawę',409)
            data=request.get_json(silent=True) or {}
            if not isinstance(data,dict):return response_error('Nieprawidłowe dane',400)
            address=str(data.get('email') or '').strip()
            if len(address)>254 or not re.fullmatch(r'[^\\s@]+@[^\\s@]+\\.[^\\s@]+',address):
                return response_error('Podaj prawidłowy adres e-mail',400)
            if str(data.get('approval_request_id') or '')!=str(consent['request_id']):
                return response_error('Zgoda została zmieniona. Odśwież stronę.',409)
            earlier=(jobs().select('id,recipient_email,status')
                     .eq('case_id',str(cid)).eq('approval_request_id',str(consent['request_id']))
                     .limit(10).execute().data or [])
            existing=next((x for x in earlier if x['recipient_email'].casefold()==address.casefold()),None)
            if existing:
                return jsonify(ok=True,already_queued=True,status=existing['status'],message='Kopia zgody została już zamówiona na ten adres')
            if len(earlier)>=3:return response_error('Limit trzech adresów dla jednej zgody',429)
            result=jobs().insert({'case_id':str(cid),
                'approval_request_id':str(consent['request_id']),
                'recipient_email':address,'status':'pending'}).execute().data or []
            if not result:return response_error('Nie zapisano zamówienia',503)
            return jsonify(ok=True,queued=True,message='Zamówienie kopii zgody przekazano do AWM PRO'),202
        except Exception:
            app.logger.exception('R263 cannot queue approval email')
            return response_error('Nie można zamówić kopii zgody',503)

    @app.get('/api/admin/workshop/approval-mail-queue')
    def r263_approval_mail_list():
        if not authorized():return response_error('Brak autoryzacji AWM',403)
        try:
            result=(jobs().select('id,case_id,approval_request_id,recipient_email,status,requested_at,error')
                 .in_('status',['pending','failed']).order('requested_at')
                 .limit(200).execute().data or [])
            return jsonify(ok=True,requests=result)
        except Exception:
            app.logger.exception('R263 cannot list approval mail')
            return response_error('Kolejka niedostępna',503)

    @app.post('/api/admin/workshop/approval-mail-queue/<uuid:qid>/claim')
    def r263_approval_mail_claim(qid):
        if not authorized():return response_error('Brak autoryzacji AWM',403)
        data=request.get_json(silent=True) or {}
        worker=str(data.get('worker') or '').strip()[:100]
        if not worker:return response_error('Brak stanowiska',400)
        try:
            result=jobs().update({'status':'claimed','claimed_by':worker,
               'claimed_at':datetime.now(timezone.utc).isoformat(),'error':None}
               ).eq('id',str(qid)).in_('status',['pending','failed']).execute().data or []
            if not result:return response_error('Zadanie już wysyłane lub zakończone',409)
            return jsonify(ok=True,request=result[0])
        except Exception:
            app.logger.exception('R263 claim failed')
            return response_error('Nie można zarezerwować wysyłki',503)

    @app.get('/api/admin/workshop/approval-mail-queue/<uuid:qid>/case')
    def r263_approval_mail_case(qid):
        if not authorized():return response_error('Brak autoryzacji AWM',403)
        try:
            found=jobs().select('case_id,approval_request_id,status').eq('id',str(qid)).limit(1).execute().data or []
            if not found:return response_error('Brak zamówienia',404)
            job=found[0]
            if job['status']!='claimed':return response_error('Najpierw zarezerwuj zadanie',409)
            cases=get_case(job['case_id'])
            if not cases:return response_error('Brak pojazdu',404)
            case=cases[0];consent=approval(case)
            if consent.get('status')!='approved' or consent.get('request_id')!=job['approval_request_id']:
                return response_error('Zgoda została zmieniona; nie wysyłaj starej kopii',409)
            sec=case.get('sections') or {}
            return jsonify(ok=True,vehicle=case.get('vehicle') or {},repair_no=case.get('repair_no'),
               approval={k:consent.get(k) for k in ['person','decided_at','authorization_number','request_id']},
               fault=sec.get('usterka'),diagnosis=sec.get('diagnoza'),costs=sec.get('koszty'))
        except Exception:
            app.logger.exception('R263 case failed')
            return response_error('Nie można odczytać zgody',503)

    @app.post('/api/admin/workshop/approval-mail-queue/<uuid:qid>/complete')
    def r263_approval_mail_complete(qid):
        if not authorized():return response_error('Brak autoryzacji AWM',403)
        data=request.get_json(silent=True) or {}
        state=data.get('status')
        worker=str(data.get('worker') or '').strip()[:100]
        mid=str(data.get('message_id') or '').strip()[:250]
        if state not in ('sent','failed') or not worker or (state=='sent' and not mid):
            return response_error('Brak potwierdzenia wysyłki',400)
        try:
            result=jobs().update({'status':state,
                'completed_at':datetime.now(timezone.utc).isoformat(),
                'sent_message_id':mid if state=='sent' else None,
                'error':str(data.get('error') or '')[:400] if state=='failed' else None}
                ).eq('id',str(qid)).eq('status','claimed').eq('claimed_by',worker).execute().data or []
            if not result:return response_error('Zadanie nie należy do tego stanowiska',409)
            return jsonify(ok=True,status=state)
        except Exception:
            app.logger.exception('R263 complete failed')
            return response_error('Nie zapisano wyniku wysyłki',503)
