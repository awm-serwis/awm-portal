import os, json, secrets, hashlib, hmac, zipfile, tempfile, shutil, mimetypes
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from io import BytesIO
from flask import request, jsonify, session, send_file, Response
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
def _vehicle(pid):
    # Desktop AWM can address a vehicle by database id (e.g. /vehicles/1/...)
    # while publish endpoints use portal_id. Accept both for full compatibility.
    v=_one(sb.table("vehicles").select("*").eq("portal_id",str(pid)).limit(1).execute())
    if v: return v
    try:
        return _one(sb.table("vehicles").select("*").eq("id",int(pid)).limit(1).execute())
    except (TypeError,ValueError):
        return None
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
def _pick(m,*keys):
    for k in keys:
        v=m.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""

def _upsert_vehicle(m):
    pid=_pick(m,"id","portal_id","vin","VIN")
    if not pid: raise ValueError("Brak id pojazdu")
    vals={
        "marka":_pick(m,"marka","brand","make"),
        "model":_pick(m,"model"),
        "rej":_pick(m,"rej","rejestracja","nr_rejestracyjny","nr_rej","registration","registration_number","plate"),
        "vin":_pick(m,"vin","VIN"),
        "przebieg":_pick(m,"przebieg","mileage"),
        "rok":_pick(m,"rok","year"),
        "updated":datetime.now().isoformat(timespec="seconds"),
        "active":True
    }
    v=_vehicle(pid)
    if v:
        # Nie kasuj starszych poprawnych danych pustymi polami z częściowej publikacji.
        vals={k:val for k,val in vals.items() if k in ("updated","active") or val!=" "}
        vals={k:val for k,val in vals.items() if k in ("updated","active") or bool(val)}
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
    if not u or not okp(d.get("password",d.get("pass","")),u["pass"]): return jsonify(error="Bledny login lub haslo"),401
    session["user"]={"id":u["id"],"login":u["login"],"role":u.get("role","admin")}; session["role"]=u.get("role","admin"); return jsonify(ok=True)
def vehicles():
    if "user" not in session: return jsonify(error="auth"),401
    vs=_rows(sb.table("vehicles").select("*").eq("active",True).order("updated",desc=True).execute())
    out=[]
    for v in vs:
        ds=_rows(sb.table("docs").select("id,kind,name").eq("vehicle_id",v["id"]).order("id",desc=True).execute())
        allowed={"photo":True,"thumb":True,"opis":v.get("show_opis",True),"opis_pdf":v.get("show_opis",True),"wycena":v.get("show_wycena",True),"raport":v.get("show_raport",True),"wycena_ai":v.get("show_wycena_ai",True)}
        ds=[d for d in ds if allowed.get(d["kind"],False)]
        x=dict(v); x["docs"]=ds; x["photos"]=[d["id"] for d in ds if d["kind"]=="photo"]; x["photo"]=next((d["id"] for d in ds if d["kind"]=="thumb"),None) or next(iter(x["photos"]),None); out.append(x)
    return jsonify(out)
def preview(i):
    if "user" not in session: return __import__("flask").redirect("/")
    d=_one(sb.table("docs").select("*").eq("id",i).limit(1).execute())
    if not d: return Response("Brak dokumentu",status=404,mimetype="text/plain")
    try:
        data=sb.storage.from_(BUCKET).download(d["path"])
    except Exception:
        return Response("Nie znaleziono pliku dokumentu w magazynie.",status=404,mimetype="text/plain")
    name=d.get("name") or "dokument"; ext=Path(name).suffix.lower()
    if ext in (".pdf",".png",".jpg",".jpeg",".webp",".gif"):
        return send_file(BytesIO(data),download_name=name,mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",as_attachment=False)
    if ext==".docx":
        try:
            import re, html as _html
            from markupsafe import escape
            with zipfile.ZipFile(BytesIO(data)) as z:
                xml=z.read("word/document.xml").decode("utf-8","ignore")
            # Preserve paragraphs, table cells and line breaks for a readable browser preview.
            xml=xml.replace("</w:tc>","\t").replace("</w:tr>","\n").replace("</w:p>","\n").replace("<w:br/>","\n")
            txt=re.sub(r"<[^>]+>","",xml); txt=_html.unescape(txt)
            lines=[str(escape(x.strip())) for x in txt.splitlines() if x.strip()]
            body="<br>".join(lines)
            return Response(f'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><style>body{{margin:0;background:#e9eeeb;font:15px Segoe UI,Arial;color:#17231e;padding:28px}}.page{{box-sizing:border-box;background:#fff;max-width:900px;min-height:1100px;margin:auto;padding:60px 70px;box-shadow:0 4px 22px #0002;line-height:1.55}}@media(max-width:700px){{body{{padding:8px}}.page{{padding:25px}}}}</style></head><body><div class="page">{body}</div></body></html>''',mimetype="text/html")
        except Exception as ex:
            return Response("Nie udało się odczytać dokumentu DOCX: "+str(ex),status=422,mimetype="text/plain")
    return Response("Ten format nie ma podglądu w przeglądarce.",mimetype="text/plain")

def file_route(i):
    if "user" not in session: return __import__("flask").redirect("/")
    d=_one(sb.table("docs").select("*").eq("id",i).limit(1).execute())
    if not d: return ("Brak pliku",404)
    data=sb.storage.from_(BUCKET).download(d["path"])
    return send_file(BytesIO(data),download_name=d["name"],mimetype=mimetypes.guess_type(d["name"])[0] or "application/octet-stream",as_attachment=request.args.get("download")=="1")
def admin_access():
    if not api_ok(): return jsonify(error="bad key"),403
    users=_rows(sb.table("users").select("*").order("id").execute())
    if request.method=="GET": return jsonify(login=(users[0]["login"] if users else ADMIN_USER))
    d=request.get_json(silent=True) or {}; login=str(d.get("login","")).strip(); pw=str(d.get("password",""))
    if not login or not pw: return jsonify(error="Brak loginu lub hasla"),400
    if users:
        sb.table("users").update({"login":login,"pass":ph(pw),"role":"admin"}).eq("id",users[0]["id"]).execute()
        for u in users[1:]: sb.table("users").delete().eq("id",u["id"]).execute()
    else: sb.table("users").insert({"login":login,"pass":ph(pw),"role":"admin"}).execute()
    session["user"]=login; return jsonify(ok=True)
def admin_vehicles():
    if not api_ok(): return jsonify(error="bad key"),403
    vs=_rows(sb.table("vehicles").select("*").order("updated",desc=True).execute())
    for v in vs:
        v["docs"]=_rows(sb.table("docs").select("id,kind,name").eq("vehicle_id",v["id"]).order("id",desc=True).execute())
    out=[]
    for v in vs:
        kinds={d["kind"] for d in v["docs"]}
        x=dict(v); x.update(has_opis="opis" in kinds,has_wycena="wycena" in kinds,has_raport="raport" in kinds,has_wycena_ai="wycena_ai" in kinds)
        out.append(x)
    return jsonify(vehicles=out)
def save_ai_valuation(pid):
    if not api_ok(): return jsonify(error="bad key"),403
    v=_vehicle(pid)
    if not v: return jsonify(error="not found"),404
    x=request.get_json(silent=True) or {}
    base=float(x.get("base_value",0) or 0)
    pct=float(x.get("correction_pct",0) or 0)
    final=round(base*(1-pct/100),2)
    data=json.dumps({"base_value":base,"correction_pct":pct,"final_value":final,"reason":str(x.get("reason","") or ""),"currency":"PLN","price_type":"NETTO"},ensure_ascii=False).encode()
    _delete_docs(v["id"],["wycena_ai"])
    name="Wycena_AI_AWM.json"
    key=_key(pid,"wycena_ai",name)
    sb.storage.from_(BUCKET).upload(key,data,{"content-type":"application/json","upsert":"true"})
    row={"vehicle_id":v["id"],"kind":"wycena_ai","name":name,"storage_path":key}
    sb.table("docs").insert(row).execute()
    sb.table("vehicles").update({"show_wycena_ai":True}).eq("id",v["id"]).execute()
    return jsonify(ok=True,base_value=base,correction_pct=pct,final_value=final)

def visibility(pid):
    if not api_ok(): return jsonify(error="bad key"),403
    v=_vehicle(pid)
    if not v:return jsonify(error="not found"),404
    d=request.get_json(silent=True) or {}; allowed={"opis":"show_opis","wycena":"show_wycena","raport":"show_raport","wycena_ai":"show_wycena_ai"}
    vals={col:bool(d[k]) for k,col in allowed.items() if k in d}
    if vals: sb.table("vehicles").update(vals).eq("id",v["id"]).execute()
    return jsonify(ok=True)
def add_document(pid,kind):
    if not api_ok():return jsonify(error="bad key"),403
    if kind not in ("opis","opis_pdf","wycena","raport","wycena_ai"):return jsonify(error="kind"),400
    v=_vehicle(pid)
    if not v:return jsonify(error="not found"),404
    name=Path(request.args.get("name") or request.headers.get("X-Filename",kind+".pdf")).name
    td=Path(tempfile.mkdtemp()); f=td/name
    try:
        data=request.get_data()
        if not data or len(data)<32: return jsonify(error="empty document"),400
        f.write_bytes(data)
        # OPIS DOCX: serwer tworzy wierny PDF z TEGO SAMEGO pliku przez LibreOffice.
        # Desktop nie musi mieć Worda ani LibreOffice.
        preview_file=None
        if kind=="opis" and f.suffix.lower()==".docx":
            out=td/"pdf"; out.mkdir(exist_ok=True)
            try:
                office=shutil.which("libreoffice") or shutil.which("soffice") or "/usr/bin/libreoffice"
                profile=td/"lo_profile"; profile.mkdir(exist_ok=True)
                env=os.environ.copy(); env["HOME"]=str(td)
                r=subprocess.run([office,"-env:UserInstallation=file://"+str(profile),"--headless","--convert-to","pdf","--outdir",str(out),str(f)],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,env=env)
                made=out/(f.stem+".pdf")
                if r.returncode!=0 or not made.is_file() or made.stat().st_size<1000:
                    msg=(r.stderr or r.stdout or b"").decode(errors="ignore")[-600:]
                    return jsonify(error="server pdf conversion failed",detail=msg),500
                preview_file=made
            except Exception as ex:
                return jsonify(error="server pdf conversion unavailable",detail=str(ex)),500
        _delete_docs(v["id"],[kind])
        stored=_store(v["id"],pid,kind,f)
        if not stored: return jsonify(error="document metadata not stored"),500
        preview_stored=None
        if preview_file is not None:
            _delete_docs(v["id"],["opis_pdf"])
            preview_stored=_store(v["id"],pid,"opis_pdf",preview_file)
            if not preview_stored: return jsonify(error="preview metadata not stored"),500
        show_key="show_opis" if kind=="opis_pdf" else "show_"+kind
        sb.table("vehicles").update({show_key:True,"updated":datetime.now().isoformat(timespec="seconds")}).eq("id",v["id"]).execute()
        return jsonify(ok=True,size=len(data),doc_id=stored.get("id") if isinstance(stored,dict) else None,preview_id=preview_stored.get("id") if isinstance(preview_stored,dict) else None,preview_generated=bool(preview_stored))
    finally: shutil.rmtree(td,ignore_errors=True)
def expire(pid):
    if not api_ok():return jsonify(error="bad key"),403
    v=_vehicle(pid)
    if not v:return jsonify(ok=True)
    _delete_docs(v["id"]); sb.table("vehicles").delete().eq("id",v["id"]).execute(); return jsonify(ok=True)
def publish_auto():
    if not api_ok():return jsonify(error="unauthorized"),401
    td=None
    try:
        td,root=_extract(); m=_meta(root); m["id"]=(request.args.get("id") or m.get("id") or m.get("portal_id") or m.get("vin") or "").strip(); pid,v=_upsert_vehicle(m)
        photo_sources=[]
        for folder,kind in (("ZDJECIA","photo"),("MINIATURY","thumb")):
            p=root/folder
            if p.exists():
                fs=[f for f in p.rglob("*") if f.is_file()]
                if fs: photo_sources.append((kind,fs))
        # Podmieniaj zdjęcia tylko wtedy, gdy nowa paczka faktycznie je zawiera.
        if photo_sources:
            _delete_docs(v["id"],["photo","thumb"])
            for kind,fs in photo_sources:
                for f in fs: _store(v["id"],pid,kind,f)
        return jsonify(ok=True,id=pid)
    except Exception as ex:return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)
def publish_docs():
    if not api_ok():return jsonify(error="unauthorized"),401
    td=None
    try:
        td,root=_extract(); m=_meta(root); pid=(request.args.get("id") or str(m.get("id") or m.get("portal_id") or m.get("vin") or "")).strip(); v=_vehicle(pid)
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
        td,root=_extract(); m=_meta(root); m["id"]=(request.args.get("id") or m.get("id") or m.get("portal_id") or m.get("vin") or "").strip(); pid,v=_upsert_vehicle(m); _delete_docs(v["id"])
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
    repl={"login":login,"vehicles":vehicles,"file":file_route,"preview":preview,"admin_access":admin_access,"admin_vehicles":admin_vehicles,"save_ai_valuation":save_ai_valuation,"visibility":visibility,"add_document":add_document,"expire":expire,"publish_auto":publish_auto,"publish_docs":publish_docs,"publish":publish}
    for endpoint,fn in repl.items():
        if endpoint in app.view_functions: app.view_functions[endpoint]=fn
