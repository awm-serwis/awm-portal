"""AWM: zarzadzanie kontami rzeczoznawcow i rejestr dostepu (dysk Render)."""
import os, sqlite3, re, hmac
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import request, session, jsonify, Response

def install_access_control(app):
    from portal_app import DATA, db, ph, API_KEY
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
    def delete_account(uid, login):
        if supa():
            from supabase_backend import sb
            sb.table("users").delete().eq("id",uid).eq("login",login).execute()
        else:
            c=db()
            try:
                c.execute("DELETE FROM users WHERE id=? AND login=?",(uid,login))
                c.commit()
            finally: c.close()
        c=audit_db()
        try:
            c.execute("DELETE FROM reviewer_labels WHERE login=?",(login,))
            c.commit()
        finally: c.close()
    def insert_account(login, password, role="reviewer"):
        if role not in ("reviewer","admin"): raise ValueError("Unsupported role")
        if supa():
            from supabase_backend import sb
            sb.table("users").insert({"login":login,"pass":ph(password),"role":role}).execute()
        else:
            c=db()
            try: c.execute("INSERT INTO users(login,pass,role) VALUES(?,?,?)",(login,ph(password),role));c.commit()
            finally: c.close()
    def desktop_key_ok():
        key=request.headers.get("X-AWM-Key","")
        return API_KEY!="AWM-CHANGE-ME" and bool(key) and hmac.compare_digest(key,API_KEY)
    def guard(write=False):
        u=session.get("user")
        desktop_key_valid=desktop_key_ok()
        if not desktop_key_valid and (not isinstance(u,dict) or u.get("role")!="admin"):
            return (jsonify(error="Dostep tylko dla administratora"),403)
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
            role=str(data.get("role") or "reviewer").strip()
            if role not in ("reviewer","admin"): return jsonify(error="Nieprawidlowa rola"),400
            if role=="admin":
                if not desktop_key_ok(): return jsonify(error="Administratora dodaje tylko program AWM"),403
                if str(data.get("confirm_admin") or "")!="UTWORZ ADMINISTRATORA":
                    return jsonify(error="Wymagane potwierdzenie utworzenia administratora"),400
                if len(password)<12: return jsonify(error="Haslo administratora: minimum 12 znakow"),400
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}",name): return jsonify(error="Login: 3–60 znakow, litery/cyfry/._-"),400
            if not 6<=len(password)<=128: return jsonify(error="Haslo musi miec co najmniej 6 znakow"),400
            if name.lower() in {str(u["login"]).lower() for u in list_accounts()}:
                return jsonify(error="Login jest juz zajety"),409
            try:
                insert_account(name,password,role=role)
                c=audit_db()
                try:
                    c.execute("INSERT OR REPLACE INTO reviewer_labels(login,label) VALUES(?,?)",(name,label))
                    c.commit()
                finally: c.close()
            except Exception:
                app.logger.exception("AWM create reviewer error")
                return jsonify(error="Nie udalo sie utworzyc konta"),503
            audit("account_created",resource=name+" ("+role+")")
            return jsonify(ok=True),201
        try: uid=int(data.get("id"))
        except (ValueError,TypeError): return jsonify(error="Niepoprawne ID"),400
        found=[x for x in list_accounts() if int(x["id"])==uid]
        if not found:return jsonify(error="Nie znaleziono konta"),404
        target=found[0]
        operation=data.get("action")
        role=target.get("role")
        if role in ("admin","admin_disabled") and not desktop_key_ok():
            return jsonify(error="Konta administratorow mozna edytowac tylko w programie AWM"),403
        if operation=="delete" and role in ("admin","admin_disabled"):
            if str(data.get("confirm_admin") or "")!="USUN ADMINISTRATORA":
                return jsonify(error="Potwierdz trwale usuniecie administratora"),400
        if operation in ("delete","disable","role") and role=="admin":
            remaining=sum(1 for a in list_accounts() if a.get("role")=="admin" and int(a["id"])!=uid)
            newrole=str(data.get("role") or "") if operation=="role" else ""
            if remaining<1 and (operation!="role" or newrole!="admin"):
                return jsonify(error="To ostatni aktywny administrator. Dodaj drugiego, potem wykonaj operacje."),409
        try:
            if operation=="delete":
                if str(data.get("confirm_login") or "")!=str(target["login"]):
                    return jsonify(error="Potwierdz dokladny login usuwanego konta"),400
                delete_account(uid,target["login"])
            elif operation=="disable":
                if role in ("disabled","admin_disabled"):return jsonify(error="Konto juz jest zablokowane"),409
                change_account(uid,role=("admin_disabled" if role=="admin" else "disabled"))
            elif operation=="enable":
                if role not in ("disabled","admin_disabled"):return jsonify(error="Konto nie jest zablokowane"),409
                change_account(uid,role=("admin" if role=="admin_disabled" else "reviewer"))
            elif operation=="role":
                if not desktop_key_ok():return jsonify(error="Zmiana roli tylko w programie AWM"),403
                newrole=str(data.get("role") or "")
                if newrole not in ("admin","reviewer"):return jsonify(error="Nieprawidlowa rola"),400
                change_account(uid,role=newrole)
            elif operation=="label":
                label=str(data.get("label") or "").strip()[:100]
                c=audit_db()
                try:
                    c.execute("INSERT OR REPLACE INTO reviewer_labels(login,label) VALUES(?,?)",(target["login"],label))
                    c.commit()
                finally: c.close()
            elif operation=="password":
                password=str(data.get("password") or "")
                minlen=12 if role in ("admin","admin_disabled") else 6
                if not minlen<=len(password)<=128:return jsonify(error="Haslo musi miec co najmniej "+str(minlen)+" znakow"),400
                change_account(uid,**{"pass":ph(password)})
            else:return jsonify(error="Nieznana operacja"),400
        except Exception:
            app.logger.exception("AWM account edit error")
            return jsonify(error="Nie udalo sie zmienic konta"),503
        audit("account_"+str(operation),resource=target["login"])
        return jsonify(ok=True)
    @app.get("/api/admin/access-events")
    def admin_access_events():
        key=request.headers.get("X-AWM-Key","")
        if API_KEY=="AWM-CHANGE-ME" or not key or not hmac.compare_digest(key,API_KEY):
            return jsonify(error="Historia dostepna tylko w programie AWM"),403
        c=audit_db()
        try: rows=[dict(r) for r in c.execute("SELECT id,created,login,event,resource,ip,success FROM events ORDER BY id DESC LIMIT 300")]
        finally:c.close()
        return jsonify(events=rows)
    @app.delete("/api/admin/access-events")
    def delete_access_events():
        key=request.headers.get("X-AWM-Key","")
        if API_KEY=="AWM-CHANGE-ME" or not key or not hmac.compare_digest(key,API_KEY):
            return jsonify(error="Usuwanie historii dostępne tylko w programie AWM"),403
        payload=request.get_json(silent=True) or {}
        ids=payload.get("ids")
        if not isinstance(ids,list) or not ids or len(ids)>300:
            return jsonify(error="Wybierz od 1 do 300 wpisów"),400
        if any(type(i) is not int or i<=0 for i in ids):
            return jsonify(error="Nieprawidłowe ID wpisu"),400
        ids=list(set(ids))
        c=audit_db()
        try:
            marks=",".join("?" for _ in ids)
            cur=c.execute("DELETE FROM events WHERE id IN ("+marks+")",ids)
            deleted=cur.rowcount
            c.execute("INSERT INTO events(created,login,event,resource,ip,success) VALUES(?,?,?,?,?,?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "AWM","audit_delete",str(deleted)+" deleted",request.remote_addr or "",1))
            c.commit()
        finally:c.close()
        return jsonify(ok=True,deleted=deleted)

    @app.before_request
    def check_disabled_reviewer():
        u=session.get("user")
        if not isinstance(u,dict) or u.get("role") not in ("reviewer","disabled","admin","admin_disabled"): return None
        if request.path.startswith("/static/") or request.path=="/health": return None
        try:
            uid=u.get("id")
            current=next((r for r in list_accounts() if str(r["id"])==str(uid)),None)
            if not current or current.get("role")!=u.get("role") or str(current.get("login"))!=str(u.get("login")) or current.get("role") in ("disabled","admin_disabled"):
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
