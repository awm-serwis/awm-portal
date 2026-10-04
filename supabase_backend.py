import os, json, secrets, hashlib, hmac, zipfile, tempfile, shutil, mimetypes
from pathlib import Path
from datetime import datetime
from io import BytesIO
from flask import request, jsonify, session, send_file
from supabase import create_client
from werkzeug.utils import secure_filename

URL=os.environ["SUPABASE_URL"]; KEY=os.environ["SUPABASE_SECRET_KEY"]
BUCKET=os.getenv("SUPABASE_BUCKET","awm-files")
API_KEY=os.getenv("AWM_API_KEY","AWM-CHANGE-ME")
ADMIN_USER=os.getenv("AWM_ADMIN_USER","AWM")
ADMIN_PASS=os.getenv("AWM_ADMIN_PASS","AWM-START-2026")
sb=create_client(URL,KEY)

def ph(p,s=None):
    s=s or secrets.token_hex(16)
    h=hashlib.pbkdf2_hmac("sha256",p.encode(),s.encode(),120000).hex()
    return s+"$"+h
def okp(p,stored):
    try:
        s,h=stored.split("$",1)
        return hmac.compare_digest(ph(p,s).split("$",1)[1],h)
    except: return False
def api_ok():
    return hmac.compare_digest(request.headers.get("X-AWM-Key",""),API_KEY)
def _rows(resp): return resp.data or []
def _one(resp):
    x=_rows(resp); return x[0] if x else None
def _vehicle(pid): return _one(sb.table("vehicles").select("*").eq("portal_id",pid).limit(1).execute())
def _safe(x): return secure_filename(str(x or "")) or "file"
def _init_admin():
    if not _one(sb.table("users").select("id").eq("login",ADMIN_USER).limit(1).execute()):
        sb.table("users").insert({"login":ADMIN_USER,"pass":ph(ADMIN_PASS),"role":"admin"}).execute()
def _delete_docs(vid,kinds=None):
    q=sb.table("docs").select("id,path,kind").eq("vehicle_id",vid).execute()
    rows=_rows(q)
    if kinds: rows=[r for r in rows if r["kind"] in kinds]
    paths=[r["path"] for r in rows if r.get("path")]
    if paths:
        try: sb.storage.from_(BUCKET).remove(paths)
        except Exception: pass
    if kinds:
        for k in kinds: sb.table("docs").delete().eq("vehicle_id",vid).eq("kind",k).execute()
    else: sb.table("docs").delete().eq("vehicle_id",vid).execute()
def _store(vid,pid,kind,f):
    name=Path(f).name; data=Path(f).read_bytes()
    obj=f"vehicles/{_safe(pid)}/{kind}/{secrets.token_hex(10)}_{_safe(name)}"
    mime=mimetypes.guess_type(name)[0] or "application/octet-stream"
    sb.storage.from_(BUCKET).upload(obj,data,file_options={"content-type":mime})
    try:
        return _one(sb.table("docs").insert({"vehicle_id":vid,"kind":kind,"name":name,"path":obj}).execute())
    except:
        try: sb.storage.from_(BUCKET).remove([obj])
        except: pass
        raise
def _meta(root):
    return json.loads((Path(root)/"vehicle.json").read_text(encoding="utf-8"))
def _extract():
    td=Path(tempfile.mkdtemp(prefix="awm_")); zf=td/"p.zip"; zf.write_bytes(request.get_data())
    root=td/"x"; root.mkdir()
    with zipfile.ZipFile(zf) as z:
        base=root.resolve()
        for m in z.infolist():
            target=(root/m.filename).resolve()
            if target!=base and base not in target.parents: raise ValueError("Nieprawidlowy ZIP")
            z.extract(m,root)
    return td,root
def _upsert_vehicle(m):
    pid=str(m.get("id") or m.get("portal_id") or m.get("vin") or "").strip()
    if not pid: raise ValueError("Brak id pojazdu")
    vals={k:str(m.get(k,"") or "") for k in ("marka","model","rej","vin","przebieg","rok")}
    vals.update({"updated":datetime.now().isoformat(timespec="seconds"),"active":True})
    v=_vehicle(pid)
    if v:
        sb.table("vehicles").update(vals).eq("id",v["id"]).execute(); v=_vehicle(pid)
    else:
        vals["portal_id"]=pid; v=_one(sb.table("vehicles").insert(vals).execute())
    return pid,v
def _latest(folder):
    fs=[p for p in Path(folder).rglob("*") if p.is_file()]
    return max(fs,key=lambda p:p.stat().st_mtime) if fs else None

def login():
    if request.method=="GET": return __import__("flask").redirect("/")
    d=request.get_json(silent=True) or {}
    u=_one(sb.table("users").select("*").eq("login",d.get("login","")).limit(1).execute())
    if not u or not okp(d.get("pass",""),u["pass"]): return jsonify(error="Bledny login lub haslo"),401
    session["user"]=u["login"]; session["role"]=u.get("role","admin"); return jsonify(ok=True)
def vehicles():
    if "user" not in session: return jsonify(error="auth"),401
    vs=_rows(sb.table("vehicles").select("*").eq("active",True).order("updated",desc=True).execute())
    out=[]
    for v in vs:
        ds=_rows(sb.table("docs").select("id,kind,name").eq("vehicle_id",v["id"]).order("id",desc=True).execute())
        allowed={"photo":True,"thumb":True,"opis":v.get("show_opis",True),"wycena":v.get("show_wycena",True),"raport":v.get("show_raport",True),"wycena_ai":v.get("show_wycena_ai",True)}
        ds=[d for d in ds if allowed.get(d["kind"],False)]
        x=dict(v); x["docs"]=ds; x["photos"]=[d for d in ds if d["kind"]=="photo"]; x["photo"]=next((d for d in ds if d["kind"] in ("thumb","photo")),None); out.append(x)
    return jsonify(out)
def file_route(i):
    if "user" not in session: return __import__("flask").redirect("/")
    d=_one(sb.table("docs").select("*").eq("id",i).limit(1).execute())
    if not d: return ("Brak pliku",404)
    data=sb.storage.from_(BUCKET).download(d["path"])
    return send_file(BytesIO(data),download_name=d["name"],mimetype=mimetypes.guess_type(d["name"])[0] or "application/octet-stream")
def admin_access():
    if "user" not in session: return jsonify(error="auth"),401
    users=_rows(sb.table("users").select("*").order("id").execute())
    if request.method=="GET": return jsonify(login=(users[0]["login"] if users else ADMIN_USER))
    d=request.get_json(silent=True) or {}; login=str(d.get("login","")).strip(); pw=str(d.get("pass",""))
    if not login or not pw: return jsonify(error="Brak loginu lub hasla"),400
    if users:
        sb.table("users").update({"login":login,"pass":ph(pw),"role":"admin"}).eq("id",users[0]["id"]).execute()
        for u in users[1:]: sb.table("users").delete().eq("id",u["id"]).execute()
    else: sb.table("users").insert({"login":login,"pass":ph(pw),"role":"admin"}).execute()
    session["user"]=login; return jsonify(ok=True)
def admin_vehicles():
    if "user" not in session: return jsonify(error="auth"),401
    vs=_rows(sb.table("vehicles").select("*").order("updated",desc=True).execute())
    for v in vs:
        v["docs"]=_rows(sb.table("docs").select("id,kind,name").eq("vehicle_id",v["id"]).order("id",desc=True).execute())
    return jsonify(vs)
def visibility(pid):
    if "user" not in session: return jsonify(error="auth"),401
    v=_vehicle(pid)
    if not v:return jsonify(error="not found"),404
    d=request.get_json(silent=True) or {}; allowed={"opis":"show_opis","wycena":"show_wycena","raport":"show_raport","wycena_ai":"show_wycena_ai"}
    vals={col:bool(d[k]) for k,col in allowed.items() if k in d}
    if vals: sb.table("vehicles").update(vals).eq("id",v["id"]).execute()
    return jsonify(ok=True)
def add_document(pid,kind):
    if "user" not in session:return jsonify(error="auth"),401
    if kind not in ("opis","wycena","raport","wycena_ai"):return jsonify(error="kind"),400
    v=_vehicle(pid)
    if not v:return jsonify(error="not found"),404
    name=Path(request.headers.get("X-Filename",kind+".pdf")).name
    td=Path(tempfile.mkdtemp()); f=td/name
    try:
        f.write_bytes(request.get_data()); _delete_docs(v["id"],[kind]); _store(v["id"],pid,kind,f)
        sb.table("vehicles").update({"show_"+kind:True,"updated":datetime.now().isoformat(timespec="seconds")}).eq("id",v["id"]).execute()
        return jsonify(ok=True)
    finally: shutil.rmtree(td,ignore_errors=True)
def expire(pid):
    if "user" not in session:return jsonify(error="auth"),401
    v=_vehicle(pid)
    if not v:return jsonify(ok=True)
    _delete_docs(v["id"]); sb.table("vehicles").delete().eq("id",v["id"]).execute(); return jsonify(ok=True)
def publish_auto():
    if not api_ok():return jsonify(error="unauthorized"),401
    td=None
    try:
        td,root=_extract(); pid,v=_upsert_vehicle(_meta(root)); _delete_docs(v["id"],["photo","thumb"])
        for folder,kind in (("ZDJECIA","photo"),("MINIATURY","thumb")):
            p=root/folder
            if p.exists():
                for f in p.rglob("*"):
                    if f.is_file(): _store(v["id"],pid,kind,f)
        return jsonify(ok=True,id=pid)
    except Exception as ex:return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)
def publish_docs():
    if not api_ok():return jsonify(error="unauthorized"),401
    td=None
    try:
        td,root=_extract(); m=_meta(root); pid=str(m.get("id") or m.get("portal_id") or m.get("vin") or "").strip(); v=_vehicle(pid)
        if not v: return jsonify(error="vehicle not found"),404
        for folder,kind in (("OPIS","opis"),("WYCENA","wycena"),("DIAG","raport")):
            p=root/folder
            if p.exists():
                f=_latest(p)
                if f: _delete_docs(v["id"],[kind]); _store(v["id"],pid,kind,f)
        sb.table("vehicles").update({"updated":datetime.now().isoformat(timespec="seconds")}).eq("id",v["id"]).execute()
        return jsonify(ok=True,id=pid)
    except Exception as ex:return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)
def publish():
    if not api_ok():return jsonify(error="unauthorized"),401
    td=None
    try:
        td,root=_extract(); pid,v=_upsert_vehicle(_meta(root)); _delete_docs(v["id"])
        for folder,kind in (("ZDJECIA","photo"),("MINIATURY","thumb"),("OPIS","opis"),("WYCENA","wycena"),("DIAG","raport")):
            p=root/folder
            if not p.exists(): continue
            fs=[f for f in p.rglob("*") if f.is_file()]
            if kind in ("opis","wycena","raport"): fs=[max(fs,key=lambda x:x.stat().st_mtime)] if fs else []
            for f in fs:_store(v["id"],pid,kind,f)
        return jsonify(ok=True,id=pid)
    except Exception as ex:return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)

def install_supabase(app):
    _init_admin()
    repl={"login":login,"vehicles":vehicles,"file":file_route,"admin_access":admin_access,"admin_vehicles":admin_vehicles,"visibility":visibility,"add_document":add_document,"expire":expire,"publish_auto":publish_auto,"publish_docs":publish_docs,"publish":publish}
    for endpoint,fn in repl.items():
        if endpoint in app.view_functions: app.view_functions[endpoint]=fn
