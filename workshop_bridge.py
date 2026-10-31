"""AWM Warsztat: account-assigned repairs without vehicle PINs."""
import base64, binascii, hashlib, hmac, io, os, secrets, time, uuid
from datetime import datetime, timezone
from flask import jsonify, request, session, send_file, Response
from werkzeug.utils import secure_filename

def install(app):
    from supabase_backend import sb
    BUCKET = os.getenv('SUPABASE_BUCKET', 'awm-files')
    def admin():
        return (session.get('user') or {}).get('role') in ('admin', 'workshop')
    def api():
        key=os.getenv('AWM_API_KEY','AWM-CHANGE-ME')
        return key!='AWM-CHANGE-ME' and hmac.compare_digest(request.headers.get('X-AWM-Key',''), key)
    def err(message,code): return jsonify(ok=False,error=message),code
    def clean_text(value,n=4000): return str(value or '')[:n]
    def public(row):
        return {'id':row['id'],'repair_no':row.get('repair_no'),'label':row.get('label'),
                'repair_title':row.get('repair_title'),'vehicle':row.get('vehicle') or {},
                'stages':row.get('stages') or [], 'updated_at':row.get('updated_at'),
                'has_photo':bool(row.get('photo_path'))}
    _ACCESS_KEY='_awm_allowed_user_ids'
    def access_ids(logins):
        if not isinstance(logins,list) or not logins or len(logins)>100 or any(not isinstance(x,str) or not x.strip() for x in logins):
            raise ValueError('Przypisz co najmniej jednego klienta do pojazdu')
        names=[x.strip().casefold() for x in logins]
        if len(set(names))!=len(names):raise ValueError('Powtórzony login klienta')
        users=sb.table('users').select('id,login,role').execute().data or []
        matches={u['login'].casefold():str(u['id']) for u in users if u.get('role')=='workshop_guest' and u.get('login')}
        missing=set(names)-set(matches)
        if missing:raise ValueError('Brak aktywnego konta: '+', '.join(sorted(missing)))
        return [matches[n] for n in names]
    def permitted(cid,record=None):
        u=session.get('user')
        if not isinstance(u,dict):return False
        if u.get('role') in ('admin','workshop'):return True
        if u.get('role')!='workshop_guest' or u.get('id') is None:return False
        if record is None:
            records=sb.table('awm_workshop_cases').select('sections').eq('id',str(cid)).limit(1).execute().data or []
            record=records[0] if records else None
        sec=(record or {}).get('sections') or {}
        return isinstance(sec,dict) and str(u['id']) in [str(x) for x in sec.get(_ACCESS_KEY,[])]
    def approval_public(row):
        record=(row.get('sections') or {}).get('_awm_approval') or {}
        if not isinstance(record,dict):record={}
        return {k:str(record.get(k) or '') for k in ('status','person','decided_at','request_id')}
    @app.post('/api/admin/workshop/cases')
    def awm_workshop_publish_r42():
        if not api():return err('Brak autoryzacji programu AWM',403)
        x=request.get_json(silent=True)
        if not isinstance(x,dict):return err('Nieprawidłowy format JSON',400)
        cid=clean_text(x.get('case_id'),100).strip()
        if not cid:return err('Brak identyfikatora zlecenia',400)
        vehicle=x.get('vehicle') if isinstance(x.get('vehicle'),dict) else {}
        vehicle={k:clean_text(vehicle.get(k),150) for k in ('marka','model','rok','rejestracja','vin','przebieg','typ')}
        stages=x.get('stages') if isinstance(x.get('stages'),list) else []
        stages=[{'name':clean_text(y.get('name'),90),'since':clean_text(y.get('since'),60)} for y in stages[:20] if isinstance(y,dict)]
        incoming_status=stages[-1]['name'] if stages else 'Przyjęty'
        sec=x.get('sections') if isinstance(x.get('sections'),dict) else {}
        allowed=('usterka','diagnoza','zakres','czesci','koszty','terminy','zgody','notatki')
        sections={k:sec[k] for k in allowed if k in sec}
        try: recipients=access_ids(x.get('allowed_logins'))
        except ValueError as e:return err(str(e),400)
        except Exception:
            app.logger.exception('Cannot check workshop access accounts')
            return err('Nie udało się sprawdzić kont klientów',503)
        try:
            existing=sb.table('awm_workshop_cases').select('id,photo_path,pin_hash,sections,stages').eq('source','AWM WARSZTAT').eq('desktop_case_id',cid).limit(1).execute().data or []
            old=existing[0] if existing else None
            previous_sections=(old or {}).get('sections') or {}
            if not isinstance(previous_sections,dict):previous_sections={}
            old_stage=(old or {}).get('stages') or []
            old_status=old_stage[-1].get('name','') if old_stage else ''
            approval=previous_sections.get('_awm_approval')
            requested_id=str(x.get('approval_request_id') or '').strip()
            if requested_id:
                try: requested_id=str(uuid.UUID(requested_id))
                except (ValueError,TypeError):return err('Niepoprawny identyfikator prośby o zgodę',400)
            is_new=(not isinstance(approval,dict) or not approval.get('request_id')
                    or (requested_id and requested_id!=approval.get('request_id')))
            if incoming_status=='Oczekiwanie na zgodę klienta' and (old_status!='Oczekiwanie na zgodę klienta' or is_new):
                approval={'status':'pending','person':'','decided_at':'','request_id':requested_id or str(uuid.uuid4())}
            elif not isinstance(approval,dict):
                approval={'status':'none','person':'','decided_at':'','request_id':''}
            data={'source':'AWM WARSZTAT','desktop_case_id':cid,
                  'repair_no':clean_text(x.get('repair_no'),80),'label':clean_text(x.get('label'),220),
                  'repair_title':clean_text(x.get('repair_title'),200),
                  'vehicle':vehicle,'stages':stages,'sections':dict(sections, **{_ACCESS_KEY:recipients, '_awm_approval':approval}), 'updated_at':datetime.utcnow().isoformat()+'Z'}
            photo=x.get('photo')
            if isinstance(photo,dict) and photo.get('data_b64'):
                try: raw=base64.b64decode(photo['data_b64'],validate=True)
                except (binascii.Error,ValueError):return err('Nieprawidłowy obraz',400)
                if len(raw)>3*1024*1024 or raw[:3]!=bytes((255,216,255)):return err('Nieprawidłowe zdjęcie JPEG (maksymalnie 3 MB)',400)
                path='workshop/'+secrets.token_hex(16)+'.jpg'
                sb.storage.from_(BUCKET).upload(path,raw,file_options={'content-type':'image/jpeg'})
                data['photo_path']=path
            if old:
                data['sections']['_awm_attachments']=previous_sections.get('_awm_attachments') or []
                result=sb.table('awm_workshop_cases').update(data).eq('id',old['id']).execute().data
                saved=old['id']
            else:
                result=sb.table('awm_workshop_cases').insert(data).execute().data
                saved=result[0]['id']
            if not result:return err('Brak potwierdzenia zapisu',503)
            return jsonify(ok=True,id=str(saved))
        except Exception:
            return err('Nie udało się zapisać zlecenia na platformie',503)
    @app.post('/api/admin/workshop/cases/<uuid:cid>/attachments')
    def awm_workshop_upload_attachment_r150(cid):
        if not api():return err('Brak autoryzacji programu AWM',403)
        x=request.get_json(silent=True)
        if not isinstance(x,dict):return err('Nieprawidłowy JSON',400)
        kind=x.get('kind')
        if kind not in ('report','vehicle_photo','fault_photo'):return err('Nieznany rodzaj załącznika',400)
        name=str(x.get('name') or '').strip()[:180]
        if not name or '/' in name or '\\' in name:return err('Nieprawidłowa nazwa pliku',400)
        data64=x.get('data_b64')
        if not isinstance(data64,str) or len(data64)>17*1024*1024:return err('Załącznik jest zbyt duży',413)
        try: raw=base64.b64decode(data64,validate=True)
        except (ValueError,binascii.Error):return err('Nieprawidłowy plik',400)
        if not raw or len(raw)>12*1024*1024:return err('Plik musi mieć od 1 B do 12 MB',413)
        ext=os.path.splitext(name)[1].lower()
        if kind=='report':
            if ext!='.pdf' or not raw.startswith(b'%PDF-'):return err('Wymagany raport PDF',400)
            mime='application/pdf'
        else:
            if ext in ('.jpg','.jpeg') and raw[:3]==bytes((255,216,255)):mime='image/jpeg'
            elif ext=='.png' and raw.startswith(bytes((137,80,78,71,13,10,26,10))):mime='image/png'
            else:return err('Wymagane zdjęcie JPG lub PNG',400)
        digest=hashlib.sha256(raw).hexdigest()
        try:
            rows=sb.table('awm_workshop_cases').select('id,sections').eq('id',str(cid)).eq('source','AWM WARSZTAT').limit(1).execute().data or []
            if not rows:return err('Nie znaleziono opublikowanego pojazdu',404)
            sec=rows[0].get('sections') or {}
            if not isinstance(sec,dict):return err('Nieprawidłowe sekcje zlecenia',503)
            old=sec.get('_awm_attachments') or []
            if not isinstance(old,list):old=[]
            for item in old:
                if isinstance(item,dict) and item.get('sha256')==digest and item.get('kind')==kind and item.get('name')==name:
                    return jsonify(ok=True,id=item['id'],duplicate=True)
            if len(old)>=100:return err('Przekroczono limit 100 załączników',409)
            attachment_id=str(uuid.uuid4())
            safe=secure_filename(name)[:100] or ('attachment'+ext)
            storage_path='workshop/'+str(cid)+'/attachments/'+attachment_id+'_'+safe
            sb.storage.from_(BUCKET).upload(storage_path,raw,file_options={'content-type':mime})
            entry={'id':attachment_id,'kind':kind,'name':name,'path':storage_path,'mime':mime,'sha256':digest}
            sec['_awm_attachments']=old+[entry]
            try:
                result=sb.table('awm_workshop_cases').update({'sections':sec}).eq('id',str(cid)).execute().data
                if not result:raise RuntimeError('No confirmation')
            except Exception:
                try:sb.storage.from_(BUCKET).remove([storage_path])
                except Exception:pass
                raise
            return jsonify(ok=True,id=attachment_id),201
        except Exception:
            app.logger.exception('Warsztat attachment upload failed')
            return err('Nie udało się zapisać załącznika',503)

    @app.delete('/api/admin/workshop/cases/<uuid:cid>')
    def awm_workshop_unpublish_r45(cid):
        if not api():return err('Brak autoryzacji programu AWM',403)
        try:
            rows=sb.table('awm_workshop_cases').select('id,photo_path').eq('id',str(cid)).eq('source','AWM WARSZTAT').limit(1).execute().data or []
            if not rows:return err('Nie znaleziono publikacji',404)
            sb.table('awm_workshop_cases').delete().eq('id',str(cid)).eq('source','AWM WARSZTAT').execute()
            # Retain storage image if deletion fails; do not re-expose vehicle on partial failure.
            photo=rows[0].get('photo_path')
            if photo:
                try:sb.storage.from_(BUCKET).remove([photo])
                except Exception:pass
            return jsonify(ok=True,deleted=True)
        except Exception:return err('Nie udało się usunąć publikacji',503)
    @app.get('/api/warsztat/cases')
    def awm_workshop_list_r42():
        user=session.get('user')
        role=user.get('role') if isinstance(user,dict) else None
        if role not in ('admin','workshop','workshop_guest'):return err('Zaloguj się do Warsztatu',403)
        try:
            rows=sb.table('awm_workshop_cases').select('id,repair_no,label,repair_title,vehicle,stages,sections,updated_at,photo_path').order('updated_at',desc=True).limit(500).execute().data or []
            if role=='workshop_guest':rows=[r for r in rows if permitted(r['id'],r)]
            result=[]
            for r in rows[:150]:
                vehicle=r.get('vehicle') or {}
                if role=='workshop_guest':
                    vehicle={k:vehicle.get(k,'') for k in ('marka','model','rejestracja')}
                result.append({'id':r['id'],'repair_no':r.get('repair_no'),'label':r.get('label'),
                               'repair_title':r.get('repair_title'),'vehicle':vehicle,
                               'stages':r.get('stages') or [],'has_photo':bool(r.get('photo_path')),
                               'updated_at':r.get('updated_at'), 'approval':approval_public(r)})
            return jsonify(ok=True,cases=result)
        except Exception:
            app.logger.exception('Cannot verify workshop vehicle assignments')
            return err('Nie można bezpiecznie odczytać listy pojazdów',503)

    @app.post('/api/warsztat/cases/<uuid:cid>/unlock')
    def awm_workshop_unlock_r42(cid):
        return err('PIN został wyłączony. Otwórz przypisany pojazd po zalogowaniu.',410)

    @app.route('/api/warsztat/access-cases',methods=['GET','POST'])
    def workshop_case_accounts_r143():
        key=os.getenv('AWM_API_KEY','AWM-CHANGE-ME')
        supplied=request.headers.get('X-AWM-Key','')
        desktop=bool(supplied) and key!='AWM-CHANGE-ME' and hmac.compare_digest(supplied,key)
        user=session.get('user')
        if not desktop and (not isinstance(user,dict) or user.get('role')!='admin'):
            return err('Brak uprawnień administratora',403)
        if request.method=='GET':
            try:
                sb.table('awm_workshop_cases').select('id,sections').limit(1).execute()
                return jsonify(ok=True,feature='assigned_accounts_v1')
            except Exception:return err('Baza Warsztatu niedostępna',503)
        x=request.get_json(silent=True) or {}
        cid=str(x.get('case_id') or '')
        if not __import__('re').fullmatch(r'[0-9a-fA-F-]{36}',cid):return err('Nieprawidłowy ID',400)
        try: ids=access_ids(x.get('logins'))
        except ValueError as e:return err(str(e),400)
        try:
            rows=sb.table('awm_workshop_cases').select('id,sections').eq('id',cid).limit(1).execute().data or []
            if not rows:return err('Nie znaleziono pojazdu',404)
            sec=rows[0].get('sections') or {}
            if not isinstance(sec,dict):sec={}
            sec[_ACCESS_KEY]=ids
            saved=sb.table('awm_workshop_cases').update({'sections':sec}).eq('id',cid).execute().data
            if not saved:return err('Nie potwierdzono zapisania',503)
            return jsonify(ok=True,feature='assigned_accounts_v1',case_id=cid,users=len(ids))
        except Exception:
            app.logger.exception('Assigning accounts failed')
            return err('Nie udało się zapisać przypisania',503)

    @app.get('/api/admin/workshop/cases/<uuid:cid>/approval')
    def awm_workshop_approval_read_r155(cid):
        if not api():return err('Brak autoryzacji programu AWM',403)
        try:
            rows=sb.table('awm_workshop_cases').select('sections,stages').eq('id',str(cid)).limit(1).execute().data or []
            if not rows:return err('Nie znaleziono pojazdu',404)
            return jsonify(ok=True,approval=approval_public(rows[0]))
        except Exception:
            app.logger.exception('Approval read failed')
            return err('Nie można odczytać odpowiedzi klienta',503)

    @app.post('/api/warsztat/cases/<uuid:cid>/approval')
    def awm_workshop_client_consent_r155(cid):
        user=session.get('user')
        if not isinstance(user,dict) or user.get('role')!='workshop_guest':
            return err('Zgody może udzielić wyłącznie zalogowany klient',403)
        origin=request.headers.get('Origin','').rstrip('/')
        if origin and origin!=request.host_url.rstrip('/'):return err('Niedozwolone pochodzenie',403)
        if request.headers.get('Sec-Fetch-Site','same-origin') not in ('same-origin','none'):
            return err('Niedozwolone żądanie',403)
        x=request.get_json(silent=True)
        if not isinstance(x,dict):return err('Wymagany JSON',400)
        person=str(x.get('person') or '').strip()
        if len(person)<2 or len(person)>100 or any(ord(c)<32 for c in person):
            return err('Wpisz imię i nazwisko osoby udzielającej zgody',400)
        if x.get('confirm') is not True:return err('Potwierdź świadome udzielenie zgody',400)
        try:
            rows=sb.table('awm_workshop_cases').select('id,sections,stages').eq('id',str(cid)).limit(1).execute().data or []
            if not rows:return err('Nie znaleziono pojazdu',404)
            row=rows[0]
            if not permitted(cid,row):return err('Nie masz dostępu do tego pojazdu',403)
            status=(row.get('stages') or [])
            if not status or status[-1].get('name')!='Oczekiwanie na zgodę klienta':
                return err('Ten pojazd nie oczekuje na zgodę klienta',409)
            sec=row.get('sections') or {}
            approval=sec.get('_awm_approval') or {}
            if not isinstance(approval,dict) or approval.get('status') not in ('pending','approved'):
                return err('Brak aktywnej prośby o akceptację',409)
            if approval.get('status')=='approved':
                return jsonify(ok=True,approval=approval_public(row),already_confirmed=True)
            request_id=str(x.get('request_id') or '')
            if not request_id or request_id!=approval.get('request_id'):
                return err('Prośba została odnowiona. Odśwież kartę pojazdu.',409)
            approval={'status':'approved','person':person,'decided_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'request_id':request_id,'user_id':str(user.get('id')),'login':str(user.get('login') or '')}
            sec['_awm_approval']=approval
            res=sb.table('awm_workshop_cases').update({'sections':sec}).eq('id',str(cid)).execute().data
            if not res:return err('Brak potwierdzenia zapisu zgody',503)
            return jsonify(ok=True,approval=approval_public({'sections':sec}))
        except Exception:
            app.logger.exception('Approval write failed')
            return err('Nie udało się zapisać zgody klienta',503)

    @app.get('/api/warsztat/cases/<uuid:cid>')
    def awm_workshop_details_r42(cid):
        cid=str(cid)
        try:
            if not permitted(cid):return err('Brak dostępu do tego pojazdu',403)
        except Exception:
            app.logger.exception('Case permission check failed')
            return err('Nie można zweryfikować uprawnień',503)
        rows=sb.table('awm_workshop_cases').select('id,repair_no,label,repair_title,vehicle,stages,sections,updated_at,photo_path').eq('id',cid).limit(1).execute().data or []
        if not rows:return err('Nie znaleziono pojazdu',404)
        r=rows[0]
        data=public(r)
        data['sections']={k:v for k,v in (r.get('sections') or {}).items() if not k.startswith('_awm_') and (admin() or k!='notatki')}
        items=(r.get('sections') or {}).get('_awm_attachments') or []
        data['attachments']=[{'id':v.get('id'),'kind':v.get('kind'),'name':v.get('name')} for v in items if isinstance(v,dict)]
        data['approval']=approval_public(r)
        return jsonify(ok=True,case=data)
    @app.get('/api/warsztat/cases/<uuid:cid>/photo')
    def awm_workshop_photo_r42(cid):
        cid=str(cid)
        try:
            if not permitted(cid):return err('Brak dostępu do tego pojazdu',403)
        except Exception:
            app.logger.exception('Case permission check failed')
            return err('Nie można zweryfikować uprawnień',503)
        rows=sb.table('awm_workshop_cases').select('photo_path').eq('id',cid).limit(1).execute().data or []
        if not rows or not rows[0].get('photo_path'):return err('Brak zdjęcia',404)
        try:
            raw=sb.storage.from_(BUCKET).download(rows[0]['photo_path'])
            return send_file(io.BytesIO(raw),mimetype='image/jpeg',max_age=60)
        except Exception:return err('Zdjęcie niedostępne',503)


    @app.get('/api/warsztat/cases/<uuid:cid>/attachments/<uuid:aid>')
    def awm_workshop_download_attachment_r150(cid,aid):
        try:
            if not permitted(str(cid)):return err('Brak dostępu do pojazdu',403)
            rows=sb.table('awm_workshop_cases').select('sections').eq('id',str(cid)).limit(1).execute().data or []
            if not rows:return err('Nie znaleziono pojazdu',404)
            sec=rows[0].get('sections') or {}
            attach=next((x for x in (sec.get('_awm_attachments') or []) if isinstance(x,dict) and x.get('id')==str(aid)),None)
            if not attach:return err('Nie znaleziono załącznika',404)
            raw=sb.storage.from_(BUCKET).download(attach['path'])
            mime=attach.get('mime') or 'application/octet-stream'
            # Render in browser or download; never expose storage bucket path.
            response=send_file(io.BytesIO(raw),mimetype=mime,
                as_attachment=mime not in ('application/pdf','image/jpeg','image/png'),
                download_name=attach.get('name') or 'zalacznik',max_age=0)
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Cache-Control']='private, no-store'
            return response
        except Exception:
            app.logger.exception('Warsztat attachment read failed')
            return err('Nie można pobrać załącznika',503)
