"""AWM: zarzadzanie kontami rzeczoznawcow i rejestr dostepu (dysk Render)."""
import os, sqlite3, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import request, session, jsonify, Response

def install_access_control(app):
    from portal_app import DATA, db, ph
    def audit_db():
        c=sqlite3.connect(Path(DATA)/"access_log.db",timeout=10)
        c.row_factory=sqlite3.Row
        c.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,created TEXT,login TEXT,event TEXT,resource TEXT,ip TEXT,success INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS reviewer_labels(login TEXT PRIMARY KEY, label TEXT)")
        return c
    def audit(event, login=None, resource="", success=True):
        try:
            c=audit_db()
            current=session.get("user") or {}
            who=login if login is not None else (current.get("login","") if isinstance(current,dict) else "")
            ip=(request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr or "")
            c.execute("INSERT INTO events(created,login,event,resource,ip,success) VALUES(?,?,?,?,?,?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),str(who)[:80],event[:48],str(resource)[:160],ip[:64],int(success)))
            threshold=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
            c.execute("DELETE FROM events WHERE created < ?",(threshold,))
            c.commit();c.close()
        except Exception: app.logger.exception("AWM audit log error")
    def supa(): return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"))
    def list_accounts():
        if supa():
            from supabase_backend import sb
            return sb.table("users").select("id,login,role").order("id").execute().data or []
        c=db()
        try: return [dict(r) for r in c.execute("SELECT id,login,role FROM users ORDER BY id")]
        finally: c.close()
    def change_account(uid, **values):
        if supa():
            from supabase_backend import sb
            sb.table("users").update(values).eq("id",uid).execute()
        else:
            c=db()
            try:
                for key,value in values.items():
                    if key not in ("role","pass"): raise ValueError("unsupported field")
                    c.execute("UPDATE users SET "+key+"=? WHERE id=?",(value,uid))
                c.commit()
            finally: c.close()
    def insert_account(login, password):
        if supa():
            from supabase_backend import sb
            sb.table("users").insert({"login":login,"pass":ph(password),"role":"reviewer"}).execute()
        else:
            c=db()
            try: c.execute("INSERT INTO users(login,pass,role) VALUES(?,?,?)",(login,ph(password),"reviewer"));c.commit()
            finally: c.close()
    def guard(write=False):
        u=session.get("user")
        if not isinstance(u,dict) or u.get("role")!="admin": return (jsonify(error="Dostep tylko dla administratora"),403)
        if write:
            origin=request.headers.get("Origin")
            if origin and origin.rstrip("/")!=request.host_url.rstrip("/"): return (jsonify(error="Niedozwolone pochodzenie"),403)
        return None
    @app.route("/api/admin/access-users",methods=["GET","POST","PATCH"])
    def manage_access_users():
        denied=guard(write=request.method!="GET")
        if denied: return denied
        if request.method=="GET":
            accounts=list_accounts()
            c=audit_db()
            try: labels={r["login"]:r["label"] for r in c.execute("SELECT login,label FROM reviewer_labels")}
            finally: c.close()
            for account in accounts: account["label"]=labels.get(account["login"],"")
            return jsonify(users=accounts)
        data=request.get_json(silent=True) or {}
        if request.method=="POST":
            name=str(data.get("login") or "").strip()
            password=str(data.get("password") or "")
            label=str(data.get("label") or "").strip()[:100]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}",name): return jsonify(error="Login: 3–60 znakow, litery/cyfry/._-"),400
            if not 6<=len(password)<=128: return jsonify(error="Haslo musi miec co najmniej 6 znakow"),400
            if name.lower() in {str(u["login"]).lower() for u in list_accounts()}:
                return jsonify(error="Login jest juz zajety"),409
            try:
                insert_account(name,password)
                c=audit_db()
                try:
                    c.execute("INSERT OR REPLACE INTO reviewer_labels(login,label) VALUES(?,?)",(name,label))
                    c.commit()
                finally: c.close()
            except Exception:
                app.logger.exception("AWM create reviewer error")
                return jsonify(error="Nie udalo sie utworzyc konta"),503
            audit("account_created",resource=name)
            return jsonify(ok=True),201
        try: uid=int(data.get("id"))
        except (ValueError,TypeError): return jsonify(error="Niepoprawne ID"),400
        found=[x for x in list_accounts() if int(x["id"])==uid]
        if not found:return jsonify(error="Nie znaleziono konta"),404
        target=found[0]
        if target.get("role")=="admin" or uid==int(session["user"]["id"]):
            return jsonify(error="Konto administratora jest chronione"),403
        operation=data.get("action")
        try:
            if operation in ("disable","enable"): change_account(uid,role=("disabled" if operation=="disable" else "reviewer"))
            elif operation=="label":
                label=str(data.get("label") or "").strip()[:100]
                c=audit_db()
                try:
                    c.execute("INSERT OR REPLACE INTO reviewer_labels(login,label) VALUES(?,?)",(target["login"],label))
                    c.commit()
                finally: c.close()
            elif operation=="password":
                password=str(data.get("password") or "")
                if not 6<=len(password)<=128:return jsonify(error="Haslo musi miec co najmniej 6 znakow"),400
                change_account(uid,**{"pass":ph(password)})
            else:return jsonify(error="Nieznana operacja"),400
        except Exception:
            app.logger.exception("AWM account edit error")
            return jsonify(error="Nie udalo sie zmienic konta"),503
        audit("account_"+str(operation),resource=target["login"])
        return jsonify(ok=True)
    @app.get("/admin/dostep")
    def access_panel():
        denied=guard()
        if denied: return Response("Brak uprawnien administratora", status=403)
        return Response((Path(__file__).resolve().parent/"access_admin.html").read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/api/admin/access-events")
    def admin_access_events():
        denied=guard()
        if denied:return denied
        c=audit_db()
        try: rows=[dict(r) for r in c.execute("SELECT created,login,event,resource,ip,success FROM events ORDER BY id DESC LIMIT 300")]
        finally:c.close()
        return jsonify(events=rows)
    @app.before_request
    def check_disabled_reviewer():
        u=session.get("user")
        if not isinstance(u,dict) or u.get("role") not in ("reviewer","disabled"): return None
        if request.path.startswith("/static/") or request.path=="/health": return None
        try:
            uid=u.get("id")
            current=next((r for r in list_accounts() if str(r["id"])==str(uid)),None)
            if not current or current.get("role")!="reviewer":
                audit("session_revoked")
                session.clear()
                if request.path.startswith("/api/"): return jsonify(error="Dostep zostal wycofany"),401
                return Response("Dostep do portalu zostal wycofany. Zaloguj sie ponownie.",status=403)
        except Exception:
            app.logger.exception("AWM session role check failed")
            return jsonify(error="Weryfikacja dostepu niedostepna"),503
        return None

    @app.after_request
    def access_events_logger(response):
        try:
            path=request.path
            if path=="/api/login" and request.method=="POST":
                payload=request.get_json(silent=True) or {}
                audit("login",login=payload.get("login",""),success=response.status_code<400)
            elif path=="/api/logout" and request.method=="POST": audit("logout")
            elif response.status_code<400 and request.method=="GET" and (
              path.startswith("/file/") or path.startswith("/preview/") or
              path.startswith("/api/file/") or path.startswith("/api/preview/") or
              path.startswith("/api/files/") or path.startswith("/api/docs/") or path.startswith("/api/doc/")):
                audit("document_open",resource=path)
        except Exception:app.logger.exception("AWM log response error")
        return response
