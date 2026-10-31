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
header{background-color:#00291f;background-image:url('/static/awm_header_z_projektu.svg?v=r174-garage');background-position:left center;background-repeat:no-repeat;background-size:min(1600px,94vw) auto;color:#fff;min-height:150px;padding:18px 5vw;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;border-bottom:3px solid #13ab77}header>div:first-child{visibility:hidden}header>.awm-account{background:linear-gradient(90deg,transparent,#002b23 12%);padding:12px 4px 12px 30px;border-radius:10px}@media(max-width:700px){header{background-image:none;min-height:100px}header>div:first-child{visibility:visible}header>.awm-account{background:transparent;padding:0}}
header strong{font-size:26px}header small{display:block;color:#d4ece0;font-size:13px}.awm-account{display:flex;align-items:center;gap:18px;flex-wrap:wrap}.awm-account-info{text-align:right}.awm-account-info span{font-size:15px;font-weight:500}.awm-account-info strong{font-size:16px;color:#fff}.awm-account-info small{font-size:12px}@media(max-width:580px){.awm-account{width:100%;justify-content:space-between}.awm-account-info{text-align:left}}
main{max-width:1130px;margin:24px auto;padding:0 18px 30px}
.panel{background:#fff;border:1px solid #d4e5da;border-radius:13px;padding:22px;margin-bottom:16px;box-shadow:0 4px 17px #0639230b}
h1{font-size:24px;margin:0 0 8px}h2{font-size:19px;margin:0 0 14px}
.muted{color:#667e72;font-size:13px}.error{color:#b02c3c;min-height:20px}
input{width:100%;padding:11px 14px;border:1px solid #afcbbc;border-radius:8px;font:inherit}
button{background:#087d53;color:#fff;border:0;padding:11px 17px;border-radius:8px;font:700 14px Segoe UI,Arial,sans-serif;cursor:pointer}
button:focus-visible{outline:3px solid #e4b34a}button:hover{background:#066d48}
button:disabled{opacity:.6;cursor:wait}
label{display:block;margin:9px 0 5px;font-weight:700}
#vehicles{display:grid;grid-template-columns:1fr;gap:13px;margin-top:0}
.vehicle{background:#f9fcfa;border:1px solid #d7e6dc;padding:16px;border-radius:13px;display:flex;flex-direction:column;gap:10px}
.vehicle h3{font-size:19px;margin:0;overflow-wrap:anywhere}.vehicle .meta{font-size:13px;color:#60776b}
.status{display:inline-flex;align-items:center;align-self:flex-start;background:#e6f4ec;color:#086940;border-radius:7px;padding:6px 10px;font-size:13px;font-weight:800}
.vehicle button{align-self:flex-start}.vehicle-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:4px}.vehicle-detail{padding:10px 12px;background:#fff;border:1px solid #e0ebe4;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}.vehicle-detail strong{display:block;color:#3c6654;font-size:12px}.vehicle-detail span{display:block;font-size:14px}.vehicle-media{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.vehicle-media img{height:95px;max-width:145px;object-fit:contain;border-radius:8px}.vehicle-media a{color:#086b48;font-weight:650;font-size:13px}@media(max-width:650px){.vehicle-details{grid-template-columns:1fr}}/* AWM: miniaturka pojazdu po lewej stronie karty zgody. */
.vehicle-head{display:grid;grid-template-columns:148px minmax(0,1fr);gap:14px;align-items:center}
.vehicle-head-info{min-width:0;display:flex;flex-direction:column;gap:8px;align-items:flex-start}
.vehicle-thumb{width:148px;height:112px;padding:0;border:1px solid #d7e5dc;border-radius:10px;background:linear-gradient(135deg,#e7f3eb,#d5e7df);overflow:hidden;display:flex;align-items:center;justify-content:center;color:#577769;font-size:39px}
button.vehicle-thumb{cursor:zoom-in}
.vehicle-thumb img{display:block;width:100%;height:100%;object-fit:cover}
.vehicle-thumb:focus-visible{outline:3px solid #0a8558;outline-offset:2px}
.awm-gallery[hidden]{display:none!important}
.awm-gallery{position:fixed;inset:0;z-index:5000;background:rgba(4,20,13,.92);display:flex;align-items:center;justify-content:center;padding:60px 58px}
.awm-gallery img{max-width:100%;max-height:calc(100dvh - 120px);object-fit:contain;border-radius:8px}
.awm-gallery button{position:absolute;margin:0;width:42px;height:42px;display:grid;place-items:center;padding:0;border:1px solid #ffffff77;border-radius:50%;background:#133b2e;color:#fff;font-size:25px;cursor:pointer}
.awm-gallery .awm-gallery-close{right:16px;top:14px}
.awm-gallery .awm-gallery-prev{left:12px;top:50%;transform:translateY(-50%)}
.awm-gallery .awm-gallery-next{right:12px;top:50%;transform:translateY(-50%)}
.awm-gallery .awm-gallery-count{position:absolute;bottom:15px;color:#fff;font-weight:700}
@media(max-width:540px){.vehicle-head{grid-template-columns:110px minmax(0,1fr);gap:10px;align-items:start}.vehicle-thumb{width:110px;height:90px}.vehicle-head-info{gap:5px}.awm-gallery{padding:60px 45px}}
.vehicle.selected{border-color:#168656;box-shadow:0 0 0 2px #18895625}
#pinPanel[hidden],#result[hidden]{display:none}#pinPanel{border:2px solid #158653;background:#fbfffc}
.pin-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:end;max-width:470px}
#pin{letter-spacing:5px;font-size:22px;max-width:230px}#result .item{padding:10px 0;border-bottom:1px solid #d8e4de;white-space:pre-wrap;overflow-wrap:anywhere}
#photo{max-width:min(100%,520px);max-height:340px;object-fit:contain;border-radius:9px}
@media(max-width:540px){.pin-grid{grid-template-columns:1fr}#pin{max-width:100%}main{padding:0 12px}}
</style></head><body>
<header><div><strong>AWM WARSZTAT</strong><small>Lista pojazdów i aktualne etapy naprawy</small></div><div class="awm-account"><div class="awm-account-info"><span>Witaj, <strong id="awmWelcomeName">Użytkowniku</strong></span><small>Panel klienta Warsztatu</small></div><button id="exit" type="button" style="background:#a52e39">WYLOGUJ</button></div></header>
<main><section class="panel" aria-label="Twoje pojazdy">
<div id="vehicles" aria-live="polite"><p class="muted">Ładowanie pojazdów…</p></div>
<p id="listError" class="error" role="alert"></p></section>
<section id="result" class="panel" hidden><h2 id="title">Szczegóły zlecenia</h2><div id="details"></div><img id="photo" alt="Zdjęcie pojazdu" hidden></section></main>
__RODO_NOTICE__
<script>
const $=id=>document.getElementById(id);
fetch('/api/me',{credentials:'same-origin',cache:'no-store'}).then(r=>r.ok?r.json():null).then(x=>{const n=x?.user?.login;if(n)$('awmWelcomeName').textContent=String(n)}).catch(()=>{});
$('exit').addEventListener('click',async()=>{const r=await fetch('/api/logout',{method:'POST',credentials:'same-origin'});if(!r.ok)throw Error('Błąd wylogowania');location.replace('/warsztat')});
function put(parent,key,val){const d=document.createElement('div');d.className='item';const b=document.createElement('strong');b.textContent=key+': ';d.appendChild(b);const t=document.createElement('span');t.textContent=typeof val==='object'?JSON.stringify(val,null,2):String(val??'');d.appendChild(t);parent.appendChild(d)}
let cases=[];
let awmGalleryReturnFocus=null;
function openVehicleGallery(urls,start,trigger){
 if(!urls.length)return;
 let index=Math.max(0,Math.min(start||0,urls.length-1));
 let overlay=document.getElementById('awmVehicleGallery');
 if(!overlay){
  overlay=document.createElement('div');overlay.id='awmVehicleGallery';overlay.className='awm-gallery';overlay.hidden=true;
  overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');overlay.setAttribute('aria-label','Zdjęcia pojazdu');
  overlay.innerHTML='<button type="button" class="awm-gallery-close" aria-label="Zamknij">×</button><button type="button" class="awm-gallery-prev" aria-label="Poprzednie zdjęcie">‹</button><img alt="Powiększone zdjęcie pojazdu"><button type="button" class="awm-gallery-next" aria-label="Następne zdjęcie">›</button><span class="awm-gallery-count"></span>';
  document.body.appendChild(overlay);
 }
 awmGalleryReturnFocus=trigger||document.activeElement;
 const image=overlay.querySelector('img'),counter=overlay.querySelector('.awm-gallery-count');
 const show=()=>{image.src=urls[index];counter.textContent=(index+1)+' / '+urls.length};
 const close=()=>{overlay.hidden=true;image.removeAttribute('src');document.removeEventListener('keydown',keys);if(awmGalleryReturnFocus&&awmGalleryReturnFocus.isConnected)awmGalleryReturnFocus.focus()};
 const keys=ev=>{if(ev.key==='Escape')close();else if(ev.key==='ArrowLeft'){index=(index-1+urls.length)%urls.length;show()}else if(ev.key==='ArrowRight'){index=(index+1)%urls.length;show()}};
 overlay.querySelector('.awm-gallery-close').onclick=close;
 overlay.querySelector('.awm-gallery-prev').onclick=()=>{index=(index-1+urls.length)%urls.length;show()};
 overlay.querySelector('.awm-gallery-next').onclick=()=>{index=(index+1)%urls.length;show()};
 overlay.querySelector('.awm-gallery-prev').hidden=urls.length<2;
 overlay.querySelector('.awm-gallery-next').hidden=urls.length<2;
 overlay.onclick=ev=>{if(ev.target===overlay)close()};
 overlay.hidden=false;show();document.addEventListener('keydown',keys);
 overlay.querySelector('.awm-gallery-close').focus();
}
function render(){
 const list=$('vehicles');list.replaceChildren();
 const filtered=cases;
 if(!filtered.length){const p=document.createElement('p');p.className='muted';p.textContent='Brak udostępnionych pojazdów.';list.appendChild(p);return}
 for(const c of filtered){
  const car=c.vehicle||{},status=(Array.isArray(c.stages)?c.stages.at(-1)?.name:'')||'Przyjęty do warsztatu';
  const item=document.createElement('article');item.className='vehicle';item.dataset.id=String(c.id);
  const header=document.createElement('div');header.className='vehicle-head';
  const info=document.createElement('div');info.className='vehicle-head-info';
  const h=document.createElement('h3');h.textContent=[car.marka,car.model].filter(Boolean).join(' ')||'Pojazd';info.appendChild(h);
  const meta=document.createElement('span');meta.className='meta';meta.textContent='Rejestracja: '+(car.rejestracja||'—')+(c.repair_no?'  •  Zlecenie: '+c.repair_no:'');info.appendChild(meta);
  const st=document.createElement('span');st.className='status';st.textContent='● '+status;info.appendChild(st);
  const base='/api/warsztat/cases/'+encodeURIComponent(c.id);
  const photos=[];
  if(c.has_photo)photos.push(base+'/photo');
  for(const a of (Array.isArray(c.attachments)?c.attachments:[])){
   if(!a||!a.id)continue;
   const kind=String(a.kind||'').toLowerCase(),name=String(a.name||'');
   if(['vehicle_photo','photo','defect_photo','damage_photo','image'].includes(kind)||(/\\.(?:jpe?g|png|webp|gif)$/i.test(name)&&kind!=='report'))
    photos.push(base+'/attachments/'+encodeURIComponent(a.id));
  }
  const thumb=document.createElement(photos.length?'button':'div');
  thumb.className='vehicle-thumb';if(photos.length){thumb.type='button';thumb.setAttribute('aria-label','Powiększ zdjęcie pojazdu');
   const img=document.createElement('img');img.alt='Miniaturka pojazdu';img.loading='lazy';img.src=photos[0];
   img.onerror=()=>{img.remove();thumb.textContent='🚘';thumb.setAttribute('aria-label','Zdjęcie chwilowo niedostępne')};
   thumb.appendChild(img);thumb.onclick=()=>openVehicleGallery(photos,0,thumb);
  }else{thumb.textContent='🚘';thumb.setAttribute('aria-label','Brak zdjęcia pojazdu')}
  header.appendChild(thumb);header.appendChild(info);item.appendChild(header);
  // Full authorized repair summary is always visible inside the vehicle card.
  const sec=c.sections||{};
  const details=document.createElement('div');details.className='vehicle-details';
  const add=(title,value)=>{
   if(value===undefined||value===null)return;
   const row=document.createElement('div');row.className='vehicle-detail';
   const key=document.createElement('strong');key.textContent=title;row.appendChild(key);
   const val=document.createElement('span');val.textContent=typeof value==='object'
     ?Object.entries(value).map(([k,v])=>k+': '+String(v??'')).join(' • '):String(value);
   row.appendChild(val);details.appendChild(row);
  };
  add('Usterka',sec.usterka||c.repair_title||'—');
  add('Diagnoza',sec.diagnoza||'—');
  add('Status',status);
  const cost=sec.koszty||{};
  add('Koszty netto',typeof cost==='object'
    ?'Części: '+String(cost.czesci??'0')+' zł  •  Robocizna: '+String(cost.robocizna??'0')+' zł  •  Razem: '+String(cost.razem??'0')+' zł'
    :cost||'—');
  if(sec.zakres)add('Zakres naprawy',sec.zakres);
  if(sec.czesci)add('Części',sec.czesci);
  if(sec.terminy)add('Terminy',sec.terminy);
  item.appendChild(details);
  const media=document.createElement('div');media.className='vehicle-media';
  for(const a of (Array.isArray(c.attachments)?c.attachments:[])){
   if(!a||!a.id)continue;
   const link=document.createElement('a');
   link.href='/api/warsztat/cases/'+encodeURIComponent(c.id)+'/attachments/'+encodeURIComponent(a.id);
   link.target='_blank';link.rel='noopener noreferrer';
   link.textContent=(a.kind==='report'?'📄 Raport PDF: ':a.kind==='vehicle_photo'?'🚘 Zdjęcie pojazdu: ':'📷 Zdjęcie usterki: ')+String(a.name||'Załącznik');
   media.appendChild(link);
  }
  if(media.childElementCount)item.appendChild(media);
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
 cases=x.cases;render();const requested=new URLSearchParams(location.search).get('case');if(requested){const card=[...document.querySelectorAll(".vehicle")].find(n=>n.dataset.id===requested);if(card)card.scrollIntoView({block:'start'})}
 }catch(e){$('vehicles').replaceChildren();$('listError').textContent=e.message||'Brak połączenia'}
}
load();
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
        extra_header = """
<style>
header.awm-workshop-header{background-color:#00291f!important;background-image:url('/static/awm_header_z_projektu.svg?v=r174-garage')!important;background-repeat:no-repeat!important;background-position:left center!important;background-size:min(1600px,94vw) auto!important;min-height:150px!important;border-bottom:3px solid #13ab77!important}
header.awm-workshop-header::before{display:none!important}
header.awm-workshop-header .awm-workshop-brand{visibility:hidden!important}
header.awm-workshop-header .topbuttons{background:linear-gradient(90deg,transparent,#002b23 18%);padding:12px!important;border-radius:10px}
@media(max-width:700px){header.awm-workshop-header{background-image:none!important;min-height:105px!important}header.awm-workshop-header .awm-workshop-brand{visibility:visible!important}header.awm-workshop-header .topbuttons{background:transparent}}
.awm-workshop-welcome{color:#f5fff9;font:600 15px 'Segoe UI',Arial,sans-serif;text-align:right;padding:8px 12px}
.awm-workshop-welcome strong{color:#72efb7}
@media(max-width:680px){.awm-workshop-welcome{font-size:13px;padding:5px}}
</style>
<script>
(function(){
  fetch('/api/me',{credentials:'same-origin',cache:'no-store'})
   .then(r=>r.ok?r.json():null)
   .then(x=>{
    const name=x?.user?.login;
    const top=document.querySelector('header.awm-workshop-header .topbuttons');
    if(!name||!top)return;
    const welcome=document.createElement('span');
    welcome.className='awm-workshop-welcome';
    welcome.appendChild(document.createTextNode('Witaj, '));
    const strong=document.createElement('strong');strong.textContent=String(name);
    welcome.appendChild(strong);
    top.insertBefore(welcome,top.firstChild);
   }).catch(()=>{});
})();
</script>
"""
        page=g["WORKSHOP_PAGE"].replace('href="/">← PRZEJDŹ DO PRZEGLĄDÓW', 'href="https://awm-portal-1.onrender.com/">← PRZEJDŹ DO PRZEGLĄDÓW').replace("</body>",RODO_NOTICE+extra_header+'<script src="/static/workshop_live.js?v=r51-single-vehicle-card"></script><script src="/static/workshop_access.js?v=2"></script></body>')
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
        if not re.fullmatch(r"[\w .-]{3,60}",login,flags=re.UNICODE) or not 4<=len(password)<=128:
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
                if not re.fullmatch(r"[\w .-]{3,60}",login,flags=re.UNICODE):return jsonify(error="Login: 3–60 znaków, polskie litery, spacje, cyfry, kropka, myślnik, _"),400
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
