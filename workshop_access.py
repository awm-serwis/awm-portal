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
        return [u for u in all_users() if u.get("role") in ("workshop","workshop_disabled")]
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
    def create(login,password):
        row={"login":login,"pass":ph(password),"role":"workshop"}
        if has_sb():
            from supabase_backend import sb
            sb.table("users").insert(row).execute()
        else:
            c=db()
            try:c.execute("INSERT INTO users(login,pass,role) VALUES(?,?,?)",(login,row["pass"],"workshop"));c.commit()
            finally:c.close()
    def workshop_home():
        if request.host.split(":")[0].lower()=="awm-warsztat.onrender.com" or os.getenv("AWM_WORKSHOP_HOME")=="1":
            return redirect("/warsztat",302)
        return original_home()
    def workshop_login():
        result=original_login()
        if (session.get("user") or {}).get("role") not in ("admin","workshop"):
            session.clear()
            return jsonify(error="Brak uprawnień do Warsztatu"),401
        return result
    def workshop_page():
        if (session.get("user") or {}).get("role") not in ("admin","workshop"):
            return Response(LOGIN_HTML,mimetype="text/html",headers={"Cache-Control":"no-store"})
        page=g["WORKSHOP_PAGE"].replace('href="/">← PRZEJDŹ DO PRZEGLĄDÓW', 'href="https://awm-portal-1.onrender.com/">← PRZEJDŹ DO PRZEGLĄDÓW').replace("</body>",'<script src="/static/workshop_live.js?v=r51-single-vehicle-card"></script><script src="/static/workshop_access.js?v=1"></script></body>')
        return Response(page,mimetype="text/html",headers={"Cache-Control":"no-store"})
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
        # Staff may use only the Warsztat interface, not inspection/admin APIs.
        if isinstance(user,dict) and user.get("role")=="workshop":
            path=request.path
            allowed=(path=="/" or path=="/warsztat" or path.startswith("/static/")
                     or path in ("/health","/api/me","/api/logout","/api/login")
                     or path.startswith("/api/warsztat/"))
            if not allowed:
                if path.startswith("/api/"):return jsonify(error="Brak uprawnień do tego modułu"),403
                return redirect("/warsztat",302)
        if not isinstance(user,dict) or user.get("role") not in ("admin","workshop"):return None
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
        if (session.get("user") or {}).get("role")!="admin":
            return jsonify(error="Wymagane uprawnienia administratora"),403
        if request.method!="GET":
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
                create(login,password)
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
                if target["role"]!="workshop":return jsonify(error="Już zablokowane"),409
                modify(uid,{"role":"workshop_disabled"})
            elif action=="enable":
                if target["role"]!="workshop_disabled":return jsonify(error="Już aktywne"),409
                modify(uid,{"role":"workshop"})
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
