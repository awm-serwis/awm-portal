"""Standalone AWM Warsztat login and staff access controls."""
import os, re, hmac, sqlite3
from flask import Response, jsonify, redirect, request, session

LOGIN_HTML = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AWM Warsztat — logowanie</title>
<style>*{box-sizing:border-box}body{margin:0;background:#eef5f2;color:#153b2b;font:15px 'Segoe UI',Arial,sans-serif}header{background:linear-gradient(95deg,#003d2e,#006345);color:#fff;padding:35px 5vw;box-shadow:0 6px 23px #003c281e}.logo{font-size:35px;font-weight:900}.logo b{color:#43d994}small{letter-spacing:1px}main{max-width:430px;margin:55px auto;padding:0 15px}.card{background:#fff;padding:30px;border:1px solid #d9e9df;border-radius:14px;box-shadow:0 8px 32px #00452c20}h1{font-size:24px;margin:0 0 12px}p{color:#647c71}label{display:block;margin:17px 0 5px;font-weight:700;font-size:13px}input{height:46px;width:100%;padding:10px;border:1px solid #acc7b7;border-radius:7px;font:inherit}button{width:100%;margin-top:22px;border:0;border-radius:8px;background:#07855b;color:#fff;padding:14px;font-weight:800;cursor:pointer}button:disabled{opacity:.6}#err{min-height:20px;color:#ae1e30;font-weight:650}</style></head>
<body><header><div class="logo">AWM <b>WARSZTAT</b></div><small>DIAGNOSTYKA · NAPRAWA · SERWIS</small></header>
<main><section class="card"><h1>Logowanie do Warsztatu</h1><p>Wprowadź login i hasło nadane przez administratora.</p>
<form id="f"><label for="login">Login</label><input id="login" autocomplete="username" required autofocus><label for="pass">Hasło</label><input id="pass" type="password" autocomplete="current-password" required>
<button id="submit" type="submit">ZALOGUJ</button><p id="err" role="alert" aria-live="polite"></p></form></section></main>
<script>document.getElementById('f').addEventListener('submit',async function(ev){ev.preventDefault();let b=document.getElementById('submit'),e=document.getElementById('err');b.disabled=true;e.textContent='';try{let r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:document.getElementById('login').value.trim(),password:document.getElementById('pass').value})});let x=await r.json();if(!r.ok)throw Error(x.error||'Błędne dane');location.replace('/warsztat')}catch(x){e.textContent=x.message||'Brak połączenia';b.disabled=false}});</script></body></html>"""


RODO_NOTICE = """<div style="background:#ecf7f1;border-top:1px solid #b9d6c8;padding:13px 18px;color:#285042;font:13px Segoe UI,Arial,sans-serif;text-align:center">
<strong>RODO — ochrona danych osobowych.</strong> Administratorem danych jest Automechanika Wojciech Maniowski.
Dostęp do dokumentacji warsztatowej jest ograniczony do osób upoważnionych.
<a href="/warsztat/rodo" style="color:#046f49;text-decoration:underline;font-weight:700">Informacja o przetwarzaniu danych</a></div>"""
RODO_HTML = """<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWM Warsztat — informacja RODO</title><body style="font:15px/1.65 Segoe UI,Arial,sans-serif;max-width:850px;margin:30px auto;padding:20px;color:#153a2b;background:#f4f9f6">
<h1>Informacja o przetwarzaniu danych osobowych — RODO</h1>
<p><strong>Administrator:</strong> Automechanika Wojciech Maniowski. W sprawach dotyczących danych osobowych można kontaktować się bezpośrednio z administratorem warsztatu.</p>
<p><strong>Cel przetwarzania:</strong> realizacja zleceń diagnostycznych i serwisowych, prowadzenie dokumentacji pojazdów, obsługa kont uprawnionych użytkowników i ochrona dostępu do dokumentacji.</p>
<p><strong>Podstawy prawne:</strong> zależnie od sytuacji — wykonanie umowy (art. 6 ust. 1 lit. b RODO), obowiązek prawny (lit. c) lub prawnie uzasadniony interes administratora polegający na dokumentowaniu obsługi i zabezpieczeniu systemu (lit. f).</p>
<p><strong>Zakres i odbiorcy:</strong> dane kont użytkowników oraz dane związane ze zleceniami mogą być dostępne upoważnionym pracownikom, współpracownikom i dostawcom infrastruktury niezbędnej do utrzymania systemu, w zakresie koniecznym do wykonywania ich zadań.</p>
<p><strong>Czas przechowywania:</strong> przez okres wymagany realizacją zlecenia, dochodzeniem roszczeń i obowiązującymi przepisami. Administrator udziela szczegółowych informacji na żądanie.</p>
<p><strong>Prawa:</strong> osoba, której dane dotyczą, może żądać dostępu do danych, ich sprostowania, usunięcia lub ograniczenia przetwarzania oraz — jeśli przepisy to przewidują — wnieść sprzeciw. Przysługuje jej także prawo skargi do Prezesa Urzędu Ochrony Danych Osobowych.</p>
<p>Nie udostępniaj danych logowania ani PIN-ów osobom nieuprawnionym.</p>
<p><a href="/warsztat" style="color:#006a4b">Powrót do Warsztatu</a></p></body></html>"""

GUEST_HTML = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWM Warsztat — dostęp do zlecenia</title>
<style>body{margin:0;background:#f1f7f4;color:#153b2b;font:15px Segoe UI,Arial,sans-serif}header{background:#004c37;color:white;padding:24px 5vw}main{max-width:820px;margin:30px auto;padding:0 18px}.panel{background:white;border:1px solid #d4e5da;border-radius:13px;padding:24px;margin-bottom:15px}h1{font-size:24px}label{display:block;font-weight:700;margin:12px 0 5px}input{width:100%;padding:12px;box-sizing:border-box;border:1px solid #acccbb;border-radius:7px}button{background:#087d53;color:white;border:0;padding:12px 19px;border-radius:7px;font-weight:700;cursor:pointer;margin-top:15px}.error{color:#b02c3c}.item{padding:10px 0;border-bottom:1px solid #d8e4de;white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:#6e8379;font-size:13px}img{max-width:100%;border-radius:9px;margin:12px 0}</style></head><body>
<header><strong style="font-size:25px">AWM WARSZTAT</strong> <span style="float:right"><button id="exit" style="margin:0;background:#a52e39">WYLOGUJ</button></span><div>Dostęp zewnętrzny — wyłącznie wybrane zlecenie i PIN</div></header>
<main><section class="panel"><h1>Sprawdź zlecenie</h1><p class="muted">Identyfikator zlecenia i PIN otrzymasz od warsztatu. Nie możesz przeglądać pozostałych pojazdów.</p>
<form id="lookup"><label for="case">Identyfikator zlecenia</label><input id="case" autocomplete="off" required placeholder="UUID zlecenia">
<label for="pin">PIN zlecenia</label><input id="pin" type="password" inputmode="numeric" required autocomplete="off">
<button type="submit">POKAŻ ZLECENIE</button></form><p id="msg" class="error" role="alert"></p></section>
<section id="result" class="panel" hidden><h2 id="title">Szczegóły</h2><div id="details"></div><img id="photo" alt="Zdjęcie pojazdu" hidden></section></main>
__RODO_NOTICE__
<script>
document.getElementById('exit').addEventListener('click',async()=>{await fetch('/api/logout',{method:'POST'});location.replace('/warsztat')});
const qs=new URLSearchParams(location.search);if(qs.get('case'))document.getElementById('case').value=qs.get('case');
function put(parent,key,val){const d=document.createElement('div');d.className='item';const b=document.createElement('strong');b.textContent=key+': ';d.appendChild(b);const t=document.createElement('span');t.textContent=typeof val==='object'?JSON.stringify(val,null,2):String(val??'');d.appendChild(t);parent.appendChild(d)}
document.getElementById('lookup').addEventListener('submit',async e=>{e.preventDefault();const id=document.getElementById('case').value.trim();const pin=document.getElementById('pin').value;const msg=document.getElementById('msg');const box=document.getElementById('result');box.hidden=true;msg.textContent='';if(!/^[0-9a-fA-F-]{36}$/.test(id)){msg.textContent='Podaj poprawny identyfikator zlecenia';return}
try{const path='/api/warsztat/cases/'+encodeURIComponent(id);let r=await fetch(path+'/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});let x=await r.json();if(!r.ok)throw Error(x.error||'Nieprawidłowy PIN');r=await fetch(path);x=await r.json();if(!r.ok)throw Error(x.error||'Nie można otworzyć zlecenia');const c=x.case;const target=document.getElementById('details');target.replaceChildren();document.getElementById('title').textContent=c.label||c.repair_title||'Zlecenie';put(target,'Zlecenie',c.repair_no||id);put(target,'Pojazd',c.vehicle||{});put(target,'Etapy',c.stages||[]);for(const [k,v] of Object.entries(c.sections||{})){if(k!=='notatki')put(target,k,v)}const photo=document.getElementById('photo');photo.hidden=!c.has_photo;if(c.has_photo)photo.src=path+'/photo';document.getElementById('pin').value='';box.hidden=false}catch(ex){msg.textContent=ex.message||'Błąd odczytu'}})
</script></body></html>""".replace("__RODO_NOTICE__",RODO_NOTICE)

def install_workshop_access(app):
    original_home=app.view_functions["home"]
    original_login=app.view_functions["login"]
    original_workshop=app.view_functions["awm_workshop_landing"]
    g=original_workshop.__globals__
    db,ph,api_key=g["db"],g["ph"],g["API_KEY"]
    def has_sb(): return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"))
    def all_users():
        if has_sb():
            from supabase_backend import sb
            return sb.table("users").select("id,login,role").order("id").execute().data or []
        c=db()
        try: return [dict(r) for r in c.execute("SELECT id,login,role FROM users ORDER BY id")]
        finally: c.close()
    def staff():
        return [u for u in all_users() if u.get("role") in ("workshop","workshop_disabled","workshop_guest","workshop_guest_disabled")]
    def modify(uid, data=None, delete=False):
        if has_sb():
            from supabase_backend import sb
            q=sb.table("users")
            if delete:q.delete().eq("id",uid).execute()
            else:q.update(data).eq("id",uid).execute()
        else:
            c=db()
            try:
                if delete:c.execute("DELETE FROM users WHERE id=?",(uid,))
                else:
                    for key,value in data.items():
                        if key not in ("pass","role"):raise ValueError("Bad field")
                        c.execute("UPDATE users SET "+key+"=? WHERE id=?",(value,uid))
                c.commit()
            finally:c.close()
    def create(login,password,role="workshop"):
        if role not in ("workshop","workshop_guest"):raise ValueError("Invalid access role")
        row={"login":login,"pass":ph(password),"role":role}
        if has_sb():
            from supabase_backend import sb
            sb.table("users").insert(row).execute()
        else:
            c=db()
            try:c.execute("INSERT INTO users(login,pass,role) VALUES(?,?,?)",(login,row["pass"],role));c.commit()
            finally:c.close()
    def workshop_home():
        if request.host.split(":")[0].lower()=="awm-warsztat.onrender.com" or os.getenv("AWM_WORKSHOP_HOME")=="1":
            return redirect("/warsztat",302)
        return original_home()
    def logged_role():
        current=session.get("user")
        return current.get("role") if isinstance(current,dict) else None
    def workshop_login():
        result=original_login()
        if logged_role() not in ("admin","workshop","workshop_guest"):
            session.clear()
            return jsonify(error="Brak uprawnień do Warsztatu"),401
        return result
    def workshop_page():
        role=logged_role()
        if role=="workshop_guest":
            return Response(GUEST_HTML,mimetype="text/html",headers={"Cache-Control":"no-store"})
        if role not in ("admin","workshop"):
            return Response(LOGIN_HTML.replace("</body>",RODO_NOTICE+"</body>"),mimetype="text/html",headers={"Cache-Control":"no-store"})
        page=g["WORKSHOP_PAGE"].replace('href="/">← PRZEJDŹ DO PRZEGLĄDÓW', 'href="https://awm-portal-1.onrender.com/">← PRZEJDŹ DO PRZEGLĄDÓW').replace("</body>",RODO_NOTICE+'<script src="/static/workshop_live.js?v=r51-single-vehicle-card"></script><script src="/static/workshop_access.js?v=2"></script></body>')
        return Response(page,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.get("/warsztat/rodo")
    def workshop_rodo():
        return Response(RODO_HTML,mimetype="text/html",headers={"Cache-Control":"no-store"})
    app.view_functions["home"]=workshop_home
    app.view_functions["login"]=workshop_login
    app.view_functions["awm_workshop_landing"]=workshop_page
    # Keep employee accounts when the desktop changes the administrator password.
    def preserve_admin_accounts():
        key=request.headers.get("X-AWM-Key","")
        if not key or api_key=="AWM-CHANGE-ME" or not hmac.compare_digest(key,api_key):
            return jsonify(error="bad key"),403
        admins=[u for u in all_users() if u.get("role")=="admin"]
        if request.method=="GET":return jsonify(login=admins[0]["login"] if admins else "")
        x=request.get_json(silent=True) or {}
        login=str(x.get("login") or "").strip(); password=str(x.get("password") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}",login) or not 6<=len(password)<=128:
            return jsonify(error="Nieprawidłowy login lub hasło"),400
        if admins:
            uid=admins[0]["id"]
            if has_sb():
                from supabase_backend import sb
                sb.table("users").update({"login":login,"pass":ph(password)}).eq("id",uid).execute()
            else:
                c=db()
                try:c.execute("UPDATE users SET login=?,pass=? WHERE id=?",(login,ph(password),uid));c.commit()
                finally:c.close()
        else:
            if has_sb():
                from supabase_backend import sb
                sb.table("users").insert({"login":login,"pass":ph(password),"role":"admin"}).execute()
            else:
                c=db()
                try:c.execute("INSERT INTO users(login,pass,role) VALUES(?,?,?)",(login,ph(password),"admin"));c.commit()
                finally:c.close()
        return jsonify(ok=True,login=login)
    app.view_functions["admin_access"]=preserve_admin_accounts

    @app.before_request
    def validate_workshop_session():
        user=session.get("user")
        # Prevent workshop-only accounts from opening inspection and admin APIs.
        if isinstance(user,dict) and user.get("role") in ("workshop","workshop_guest"):
            path=request.path
            allowed=(path in ("/","/warsztat","/warsztat/rodo","/health","/api/me","/api/logout","/api/login")
                     or path.startswith("/static/"))
            if user.get("role")=="workshop":
                allowed=allowed or path.startswith("/api/warsztat/")
            else:
                # An external account may only open one case after its PIN is verified.
                allowed=allowed or bool(re.fullmatch(r"/api/warsztat/cases/[0-9a-fA-F-]{36}(?:/unlock|/photo)?",path))
            if not allowed:
                if path.startswith("/api/"):return jsonify(error="To konto nie ma dostępu do tego modułu"),403
                return redirect("/warsztat",302)
        if not isinstance(user,dict) or user.get("role") not in ("admin","workshop","workshop_guest"):return None
        if request.path.startswith("/static/") or request.path=="/health":return None
        try:
            entry=next((x for x in all_users() if str(x["id"])==str(user.get("id"))),None)
            if not entry or entry.get("role")!=user["role"] or entry.get("login")!=user.get("login"):
                session.clear()
                if request.path.startswith("/api/"):return jsonify(error="Dostęp został wycofany"),401
                return redirect("/warsztat",302)
        except Exception:
            app.logger.exception("Warsztat: access validation unavailable")
            return jsonify(error="Weryfikacja dostępu niedostępna"),503
        return None

    @app.route("/api/warsztat/access-users",methods=["GET","POST","PATCH"])
    def workshop_staff_access():
        # Desktop AWM uses the same protected API key as workshop publication.
        supplied=request.headers.get("X-AWM-Key","")
        desktop_ok=bool(supplied) and api_key!="AWM-CHANGE-ME" and hmac.compare_digest(supplied,api_key)
        if logged_role()!="admin" and not desktop_ok:
            return jsonify(error="Wymagane uprawnienia administratora lub ważny klucz AWM"),403
        if request.method!="GET" and not desktop_ok:
            origin=request.headers.get("Origin")
            site=request.headers.get("Sec-Fetch-Site","same-origin")
            if (origin and origin.rstrip("/")!=request.host_url.rstrip("/")) or site not in ("same-origin","none"):
                return jsonify(error="Niedozwolone pochodzenie"),403
        try:
            if request.method=="GET":return jsonify(users=staff())
            x=request.get_json(silent=True)
            if not isinstance(x,dict):return jsonify(error="Wymagany JSON"),400
            if request.method=="POST":
                login=str(x.get("login") or "").strip()
                password=str(x.get("password") or "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}",login):return jsonify(error="Login: 3–60 znaków, litery/cyfry/._-"),400
                if not 10<=len(password)<=128:return jsonify(error="Hasło: 10–128 znaków"),400
                if login.casefold() in {u["login"].casefold() for u in all_users()}:
                    return jsonify(error="Login już istnieje"),409
                role=str(x.get("role") or "workshop")
                if role not in ("workshop","workshop_guest"):return jsonify(error="Nieprawidłowe uprawnienia"),400
                create(login,password,role)
                return jsonify(ok=True),201
            try:uid=int(x.get("id"))
            except (TypeError,ValueError):return jsonify(error="Niepoprawne ID"),400
            target=next((u for u in staff() if str(u["id"])==str(uid)),None)
            if not target:return jsonify(error="Nie znaleziono pracownika"),404
            action=x.get("action")
            if action=="password":
                pw=str(x.get("password") or "")
                if not 10<=len(pw)<=128:return jsonify(error="Hasło: 10–128 znaków"),400
                modify(uid,{"pass":ph(pw)})
            elif action=="disable":
                if target["role"] not in ("workshop","workshop_guest"):return jsonify(error="Już zablokowane"),409
                modify(uid,{"role":target["role"]+"_disabled"})
            elif action=="enable":
                if target["role"] not in ("workshop_disabled","workshop_guest_disabled"):return jsonify(error="Już aktywne"),409
                modify(uid,{"role":target["role"].removesuffix("_disabled")})
            elif action=="delete":
                if str(x.get("confirm_login") or "")!=str(target["login"]):
                    return jsonify(error="Potwierdź login usuwanego konta"),400
                modify(uid,delete=True)
            else:return jsonify(error="Nieznana operacja"),400
            return jsonify(ok=True)
        except sqlite3.IntegrityError:return jsonify(error="Login już istnieje"),409
        except Exception:
            app.logger.exception("Warsztat account operation failed")
            return jsonify(error="Błąd zapisu kont"),503
