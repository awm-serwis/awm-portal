"""AWM R42 workshop bridge. Authenticated desktop publish; customer PIN verification."""
import base64, binascii, hashlib, hmac, io, os, secrets
from datetime import datetime
from flask import jsonify, request, session, send_file, Response

def install(app):
    from supabase_backend import sb
    BUCKET = os.getenv('SUPABASE_BUCKET', 'awm-files')
    def admin():
        return (session.get('user') or {}).get('role') == 'admin'
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
    def verified(id):
        return admin() or str(id) in session.get('awm_workshop_verified',[])
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
        sec=x.get('sections') if isinstance(x.get('sections'),dict) else {}
        allowed=('usterka','diagnoza','zakres','czesci','koszty','terminy','zgody','notatki')
        sections={k:sec[k] for k in allowed if k in sec}
        pin=x.get('pin_hash')
        if pin is not None and (not isinstance(pin,str) or len(pin)>200 or ':' not in pin):return err('Nieprawidłowy skrót PIN',400)
        try:
            existing=sb.table('awm_workshop_cases').select('id,photo_path,pin_hash').eq('source','AWM WARSZTAT').eq('desktop_case_id',cid).limit(1).execute().data or []
            old=existing[0] if existing else None
            data={'source':'AWM WARSZTAT','desktop_case_id':cid,
                  'repair_no':clean_text(x.get('repair_no'),80),'label':clean_text(x.get('label'),220),
                  'repair_title':clean_text(x.get('repair_title'),200),
                  'vehicle':vehicle,'stages':stages,'sections':sections,'updated_at':datetime.utcnow().isoformat()+'Z'}
            if pin: data['pin_hash']=pin
            photo=x.get('photo')
            if isinstance(photo,dict) and photo.get('data_b64'):
                try: raw=base64.b64decode(photo['data_b64'],validate=True)
                except (binascii.Error,ValueError):return err('Nieprawidłowy obraz',400)
                if len(raw)>3*1024*1024 or raw[:3]!=bytes((255,216,255)):return err('Nieprawidłowe zdjęcie JPEG (maksymalnie 3 MB)',400)
                path='workshop/'+secrets.token_hex(16)+'.jpg'
                sb.storage.from_(BUCKET).upload(path,raw,file_options={'content-type':'image/jpeg'})
                data['photo_path']=path
            if old:
                result=sb.table('awm_workshop_cases').update(data).eq('id',old['id']).execute().data
                saved=old['id']
            else:
                result=sb.table('awm_workshop_cases').insert(data).execute().data
                saved=result[0]['id']
            if not result:return err('Brak potwierdzenia zapisu',503)
            return jsonify(ok=True,id=str(saved))
        except Exception:
            return err('Nie udało się zapisać zlecenia na platformie',503)
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
        if not admin():return err('Wymagane uprawnienia warsztatu',403)
        try:
            rows=sb.table('awm_workshop_cases').select('id,repair_no,label,repair_title,vehicle,stages,updated_at,photo_path').order('updated_at',desc=True).limit(150).execute().data or []
            return jsonify(ok=True,cases=[public(r) for r in rows])
        except Exception:return err('Błąd odczytu zleceń',503)
    @app.post('/api/warsztat/cases/<uuid:cid>/unlock')
    def awm_workshop_unlock_r42(cid):
        cid=str(cid)
        if admin():
            ids=session.get('awm_workshop_verified',[])
            if cid not in ids:session['awm_workshop_verified']=(ids+[cid])[-30:]
            return jsonify(ok=True)
        pin=str((request.get_json(silent=True) or {}).get('pin') or '')
        attempts=session.get('awm_workshop_pin_tries',0)
        if attempts>=5:return err('Zbyt wiele prób. Spróbuj ponownie później.',429)
        if not pin.isascii() or not pin.isdigit() or len(pin)>12:return err('Nieprawidłowy PIN',403)
        rows=sb.table('awm_workshop_cases').select('pin_hash').eq('id',cid).limit(1).execute().data or []
        if not rows:return err('Nie znaleziono pojazdu',404)
        stored=rows[0].get('pin_hash') or ''
        try:
            salt,digest=stored.split(':',1)
            test=hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(salt),200000).hex()
            match=hmac.compare_digest(test,digest)
        except Exception:match=False
        if not match:
            session['awm_workshop_pin_tries']=attempts+1
            return err('Nieprawidłowy PIN',403)
        session['awm_workshop_pin_tries']=0
        ids=session.get('awm_workshop_verified',[])
        session['awm_workshop_verified']=(ids+[cid])[-30:]
        return jsonify(ok=True)
    @app.get('/api/warsztat/cases/<uuid:cid>')
    def awm_workshop_details_r42(cid):
        cid=str(cid)
        if not verified(cid):return err('Wprowadź PIN pojazdu',403)
        rows=sb.table('awm_workshop_cases').select('id,repair_no,label,repair_title,vehicle,stages,sections,updated_at,photo_path').eq('id',cid).limit(1).execute().data or []
        if not rows:return err('Nie znaleziono pojazdu',404)
        r=rows[0]
        data=public(r);data['sections']=r.get('sections') or {}
        if not admin():data['sections'].pop('notatki',None)
        return jsonify(ok=True,case=data)
    @app.get('/api/warsztat/cases/<uuid:cid>/photo')
    def awm_workshop_photo_r42(cid):
        cid=str(cid)
        if not verified(cid):return err('Wprowadź PIN pojazdu',403)
        rows=sb.table('awm_workshop_cases').select('photo_path').eq('id',cid).limit(1).execute().data or []
        if not rows or not rows[0].get('photo_path'):return err('Brak zdjęcia',404)
        try:
            raw=sb.storage.from_(BUCKET).download(rows[0]['photo_path'])
            return send_file(io.BytesIO(raw),mimetype='image/jpeg',max_age=60)
        except Exception:return err('Zdjęcie niedostępne',503)
