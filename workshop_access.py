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
<title>AWM Warsztat — statusy pojazdów</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f1f7f4;color:#153b2b;font:15px/1.5 Segoe UI,Arial,sans-serif}
header{background:#004c37;color:#fff;padding:20px 5vw;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
header strong{font-size:26px}header small{display:block;color:#d4ece0;font-size:13px}
main{max-width:1130px;margin:24px auto;padding:0 18px 30px}
.panel{background:#fff;border:1px solid #d4e5da;border-radius:13px;padding:22px;margin-bottom:16px;box-shadow:0 4px 17px #0639230b}
h1{font-size:24px;margin:0 0 8px}h2{font-size:19px;margin:0 0 14px}
.muted{color:#667e72;font-size:13px}.error{color:#b02c3c;min-height:20px}
input{width:100%;padding:11px 14px;border:1px solid #afcbbc;border-radius:8px;font:inherit}
button{background:#087d53;color:#fff;border:0;padding:11px 17px;border-radius:8px;font:700 14px Segoe UI,Arial,sans-serif;cursor:pointer}
button:focus-visible{outline:3px solid #e4b34a}button:hover{background:#066d48}
button:disabled{opacity:.6;cursor:wait}
label{display:block;margin:9px 0 5px;font-weight:700}
#vehicles{display:grid;grid-template-columns:repeat(auto-fit,minmax(275px,1fr));gap:13px;margin-top:15px}
.vehicle{background:#f9fcfa;border:1px solid #d7e6dc;padding:16px;border-radius:13px;display:flex;flex-direction:column;gap:10px}
.vehicle h3{font-size:19px;margin:0;overflow-wrap:anywhere}.vehicle .meta{font-size:13px;color:#60776b}
.status{display:inline-flex;align-items:center;align-self:flex-start;background:#e6f4ec;color:#086940;border-radius:7px;padding:6px 10px;font-size:13px;font-weight:800}
.vehicle button{margin-top:auto;align-self:flex-start}.vehicle.selected{border-color:#168656;box-shadow:0 0 0 2px #18895625}
#pinPanel[hidden],#result[hidden]{display:none}#pinPanel{border:2px solid #158653;background:#fbfffc}
.pin-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end;max-width:470px}
#pin{letter-spacing:5px;font-size:22px;max-width:230px}#result .item{padding:10px 0;border-bottom:1px solid #d8e4de;white-space:pre-wrap;overflow-wrap:anywhere}
#photo{max-width:min(100%,520px);max-height:340px;object-fit:contain;border-radius:9px}
@media(max-width:540px){.pin-grid{grid-template-columns:1fr}#pin{max-width:100%}main{padding:0 12px}}
</style></head><body>
<header><div><strong>AWM WARSZTAT</strong><small>Lista pojazdów i aktualne etapy naprawy</small></div><button id="exit" type="button" style="background:#a52e39">WYLOGUJ</button></header>
<main><section class="panel"><h1>Lista pojazdów</h1><p class="muted">Widzisz wyłącznie pojazdy przypisane do Twojego loginu. Kliknij kartę, aby zobaczyć szczegóły bez PIN-u.</p>
<label for="filter">Wyszukaj pojazd</label><input id="filter" type="search" placeholder="Marka, model, rejestracja, numer zlecenia lub status">
<div id="vehicles" aria-live="polite"><p class="muted">Ładowanie listy pojazdów…</p></div>
<p id="listError" class="error" role="alert"></p></section>
<section id="result" class="panel" hidden><h2 id="title">Szczegóły zlecenia</h2><div id="details"></div><img id="photo" alt="Zdjęcie pojazdu" hidden></section></main>
__RODO_NOTICE__
<script>
const $=id=>document.getElementById(id);
$('exit').addEventListener('click',async()=>{const r=await fetch('/api/logout',{method:'POST',credentials:'same-origin'});if(!r.ok)throw Error('Błąd wylogowania');location.replace('/warsztat')});
function put(parent,key,val){const d=document.createElement('div');d.className='item';const b=document.createElement('strong');b.textContent=key+': ';d.appendChild(b);const t=document.createElement('span');t.textContent=typeof val==='object'?JSON.stringify(val,null,2):String(val??'');d.appendChild(t);parent.appendChild(d)}
let cases=[];
function render(){
 const needle=$('filter').value.toLocaleLowerCase('pl').trim(),list=$('vehicles');list.replaceChildren();
 const filtered=cases.filter(c=>{const car=c.vehicle||{};const status=Array.isArray(c.stages)?c.stages.at(-1)?.name||'':'';
 return [car.marka,car.model,car.rejestracja,c.repair_no,status].join(' ').toLocaleLowerCase('pl').includes(needle)});
 if(!filtered.length){const p=document.createElement('p');p.className='muted';p.textContent=cases.length?'Nie znaleziono pojazdów.':'Brak opublikowanych pojazdów.';list.appendChild(p);return}
 for(const c of filtered){
  const car=c.vehicle||{},status=(Array.isArray(c.stages)?c.stages.at(-1)?.name:'')||'Przyjęty do warsztatu';
  const item=document.createElement('article');item.className='vehicle';item.dataset.id=String(c.id);
  const h=document.createElement('h3');h.textContent=[car.marka,car.model].filter(Boolean).join(' ')||'Pojazd';item.appendChild(h);
  const meta=document.createElement('span');meta.className='meta';meta.textContent='Rejestracja: '+(car.rejestracja||'—')+(c.repair_no?'  •  Zlecenie: '+c.repair_no:'');item.appendChild(meta);
  const st=document.createElement('span');st.className='status';st.textContent='● '+status;item.appendChild(st);
  item.tabIndex=0;item.setAttribute('role','button');item.setAttribute('aria-label','Szczegóły pojazdu');item.style.cursor='pointer';
  item.addEventListener('click',event=>{if(event.target.closest('button,input,label,a'))return;openCase(c,item)});
  item.addEventListener('keydown',event=>{if(event.target!==item)return;if(event.key==='Enter'||event.key===' '){event.preventDefault();openCase(c,item)}});
  const consent=c.approval||{};
  if(status==='Oczekiwanie na zgodę klienta'&&consent.status==='pending'){
   const consentBox=document.createElement('div');
   consentBox.style.cssText='background:#eaf7ef;border:1px solid #add7be;border-radius:9px;padding:11px;margin-top:5px';
   const heading=document.createElement('strong');heading.textContent='Zgoda na naprawę';consentBox.appendChild(heading);
   const person=document.createElement('input');person.placeholder='Imię i nazwisko osoby udzielającej zgody';person.autocomplete='name';person.maxLength=100;person.style.marginTop='8px';consentBox.appendChild(person);
   const checkRow=document.createElement('label');checkRow.style.cssText='display:flex;align-items:flex-start;gap:8px;font-weight:500';
   const cb=document.createElement('input');cb.type='checkbox';cb.style.cssText='width:auto;margin-top:4px';checkRow.appendChild(cb);
   const checkText=document.createElement('span');checkText.textContent='Potwierdzam, że udzielam zgody na naprawę wskazanego pojazdu.';checkRow.appendChild(checkText);consentBox.appendChild(checkRow);
   const accept=document.createElement('button');accept.type='button';accept.textContent='✓ UDZIELAM ZGODY';consentBox.appendChild(accept);
   const message=document.createElement('p');message.setAttribute('role','alert');message.className='error';consentBox.appendChild(message);
   accept.onclick=async()=>{
    const name=person.value.trim();
    if(name.length<2||!cb.checked){message.textContent='Wpisz dane osoby i zaznacz potwierdzenie zgody.';return}
    accept.disabled=true;message.textContent='';
    try{
     const r=await fetch('/api/warsztat/cases/'+encodeURIComponent(c.id)+'/approval',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({person:name,confirm:true,request_id:consent.request_id})});
     const response=await r.json();
     if(!r.ok||!response.ok)throw Error(response.error||'Nie zapisano zgody');
     c.approval=response.approval;render();
    }catch(e){message.textContent=e.message||'Błąd zapisu zgody'}
    finally{accept.disabled=false}
   };
   item.appendChild(consentBox);
  }else if(consent.status==='approved'){
   const approved=document.createElement('div');approved.style.cssText='color:#08713d;font-weight:700;font-size:13px';
   approved.textContent='✓ Zgoda udzielona: '+(consent.person||'—')+' • '+(consent.decided_at?new Date(consent.decided_at).toLocaleString('pl-PL'):'—');
   item.appendChild(approved);
  }
  list.appendChild(item);
 }
}
async function load(){
 try{const r=await fetch('/api/warsztat/cases',{credentials:'same-origin',cache:'no-store'});const x=await r.json();
 if(!r.ok||!x.ok||!Array.isArray(x.cases))throw Error(x.error||'Nie udało się pobrać listy');
 cases=x.cases;render();const requested=new URLSearchParams(location.search).get('case');const found=cases.find(c=>c.id===requested);if(found){const card=[...document.querySelectorAll(".vehicle")].find(n=>n.dataset.id===requested);if(card)openCase(found,card)}
 }catch(e){$('vehicles').replaceChildren();$('listError').textContent=e.message||'Brak połączenia'}
}
$('filter').addEventListener('input',render);load();
async function openCase(c,button){
 const id=c.id,box=$('result');box.hidden=true;$('listError').textContent='';
 button.disabled=true;
 try{
  const path='/api/warsztat/cases/'+encodeURIComponent(id);
  const r=await fetch(path,{credentials:'same-origin',cache:'no-store'}),x=await r.json();
  if(!r.ok||!x.ok||!x.case)throw Error(x.error||'Nie masz dostępu do tego pojazdu');
  const vehicle=x.case,target=$('details');target.replaceChildren();
  $('title').textContent=vehicle.label||vehicle.repair_title||'Zlecenie';
  put(target,'Zlecenie',vehicle.repair_no||id);
  put(target,'Pojazd',vehicle.vehicle||{});put(target,'Etapy',vehicle.stages||[]);
  for(const [k,v] of Object.entries(vehicle.sections||{})){if(k!=='notatki'&&!k.startsWith('_awm_'))put(target,k,v)}
  const photo=$('photo');photo.hidden=!vehicle.has_photo;
  if(vehicle.has_photo)photo.src=path+'/photo';
  for(const a of (vehicle.attachments||[])){const d=document.createElement('div');const l=document.createElement('a');l.textContent='Załącznik: '+String(a.name||'plik');l.href=path+'/attachments/'+encodeURIComponent(a.id);l.target='_blank';l.rel='noopener noreferrer';d.appendChild(l);target.appendChild(d)}
  box.hidden=false;box.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(ex){$('listError').textContent=ex.message||'Błąd odczytu pojazdu'}
 finally{button.disabled=false}
}
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
                allowed=allowed or path=="/api/warsztat/cases" or bool(re.fullmatch(r"/api/warsztat/cases/[0-9a-fA-F-]{36}(?:/unlock|/photo|/approval|/attachments/[0-9a-fA-F-]{36})?",path))
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
                if not 4<=len(password)<=128:return jsonify(error="Hasło: 4–128 znaków"),400
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
                if not 4<=len(pw)<=128:return jsonify(error="Hasło: 4–128 znaków"),400
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
