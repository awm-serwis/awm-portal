/* AWM Warsztat — administrator access panel, standalone service. */
(function(){
'use strict';
const css=document.createElement('style');
css.textContent='.awm-access-link{border:1px solid #58d0a0;border-radius:8px;padding:10px 13px;background:#06764e;color:#fff;font-weight:800;cursor:pointer}.awm-access-link:hover{background:#039565}.awm-access-modal[hidden]{display:none!important}.awm-access-modal{position:fixed;inset:0;z-index:19000;background:rgba(0,30,19,.75);display:flex;align-items:center;justify-content:center;padding:20px}.awm-access-card{background:#fff;color:#173b2b;border-radius:15px;box-shadow:0 16px 70px #0005;width:min(850px,100%);max-height:90vh;overflow:auto;padding:25px}.awm-access-card h2{margin:0 0 6px}.awm-access-card .awm-access-hint{color:#627e70;font-size:13px}.awm-access-card input{border:1px solid #abcbbb;border-radius:8px;padding:10px;font:inherit;min-width:0}.awm-access-card button{border:0;border-radius:8px;padding:10px 12px;background:#007d55;color:white;font-weight:700;cursor:pointer}.awm-access-card .awm-access-danger{background:#9d2832}.awm-access-card .awm-access-muted{background:#647970}.awm-access-card .awm-access-entry{border:1px solid #dae7df;border-radius:10px;padding:13px;margin:10px 0}.awm-access-card .awm-access-row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.awm-access-card .awm-access-create{display:grid;grid-template-columns:1fr 1fr auto;gap:9px;align-items:end;margin:17px 0}.awm-access-card label{display:block;font-weight:700;font-size:12px;margin-bottom:5px}.awm-access-card .awm-access-entry-name{font-weight:900;margin-right:auto;overflow-wrap:anywhere}.awm-access-card .awm-access-msg{min-height:25px;color:#075b3c;font-weight:650}.awm-access-card .awm-access-entry input{width:210px;max-width:100%}@media(max-width:650px){.awm-access-card .awm-access-create{grid-template-columns:1fr}.awm-access-card{padding:15px}.awm-access-card .awm-access-entry input{width:100%}}';
document.head.appendChild(css);
function elem(tag,props,parent){const x=document.createElement(tag);Object.keys(props||{}).forEach(k=>{if(k==='text')x.textContent=props[k];else if(k==='class')x.className=props[k];else x.setAttribute(k,props[k]);});if(parent)parent.appendChild(x);return x}
async function api(method,body){const res=await fetch('/api/warsztat/access-users',{method:method,headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});const data=await res.json().catch(()=>({}));if(!res.ok)throw Error(data.error||'Błąd serwera');return data}
function message(text,error){const el=document.getElementById('awmAccessMessage');if(el){el.textContent=text;el.style.color=error?'#b42532':'#075b3c'}}
const modal=elem('div',{class:'awm-access-modal',hidden:''},document.body);
modal.id='awmAccessModal';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label','Panel dostępu do Warsztatu');
const card=elem('section',{class:'awm-access-card'},modal);
const top=elem('div',{class:'awm-access-row'},card);
elem('h2',{text:'🔐 Panel dostępu — AWM Warsztat'},top);
const close=elem('button',{type:'button',class:'awm-access-muted',text:'ZAMKNIJ'},top);
close.addEventListener('click',()=>{modal.hidden=true});
elem('p',{class:'awm-access-hint',text:'Administrator zarządza kontami pracowników Warsztatu. Hasła są przechowywane jako skróty i nie można ich odczytać — można nadać nowe.'},card);
const form=elem('form',{class:'awm-access-create'},card);
const lf=elem('div',{},form);
elem('label',{for:'awmNewLogin',text:'Login pracownika'},lf);
const login=elem('input',{id:'awmNewLogin',required:'',autocomplete:'off',placeholder:'np. mechanik01'},lf);
const pf=elem('div',{},form);
elem('label',{for:'awmNewPass',text:'Hasło (min. 10 znaków)'},pf);
const pass=elem('input',{id:'awmNewPass',type:'password',required:'',autocomplete:'new-password',minlength:'10',placeholder:'Nowe hasło'},pf);
elem('button',{type:'submit',text:'DODAJ KONTO'},form);
const status=elem('p',{id:'awmAccessMessage',class:'awm-access-msg','aria-live':'polite'},card);
const list=elem('div',{},card);
async function refresh(){
 const result=await api('GET');list.replaceChildren();
 if(!result.users || !result.users.length){elem('p',{text:'Brak kont pracowników. Dodaj pierwsze konto powyżej.'},list);return}
 result.users.forEach(user=>{
  const entry=elem('div',{class:'awm-access-entry'},list);
  const row=elem('div',{class:'awm-access-row'},entry);
  elem('span',{class:'awm-access-entry-name',text:user.login},row);
  const disabled=user.role==='workshop_disabled';
  elem('span',{text:disabled?'● ZABLOKOWANE':'● AKTYWNE'},row).style.color=disabled?'#b42532':'#087951';
  const toggle=elem('button',{type:'button',class:disabled?'':'awm-access-muted',text:disabled?'ODBLOKUJ':'ZABLOKUJ'},row);
  toggle.addEventListener('click',async()=>{
   if(!disabled&&!confirm('Zablokować konto '+user.login+'?'))return;
   try{await api('PATCH',{id:user.id,action:disabled?'enable':'disable'});message('Zmieniono dostęp: '+user.login);await refresh()}catch(e){message(e.message,true)}
  });
  const remove=elem('button',{type:'button',class:'awm-access-danger',text:'USUŃ'},row);
  remove.addEventListener('click',async()=>{
   const value=prompt('Aby trwale usunąć konto, wpisz dokładnie login: '+user.login,'');
   if(value!==user.login)return;
   try{await api('PATCH',{id:user.id,action:'delete',confirm_login:value});message('Usunięto konto: '+user.login);await refresh()}catch(e){message(e.message,true)}
  });
  const passrow=elem('div',{class:'awm-access-row'},entry);passrow.style.marginTop='10px';
  const newPass=elem('input',{type:'password',autocomplete:'new-password',placeholder:'Nowe hasło (min. 10 znaków)'},passrow);
  const save=elem('button',{type:'button',text:'ZMIEŃ HASŁO'},passrow);
  save.addEventListener('click',async()=>{
   if(newPass.value.length<10){message('Hasło musi mieć minimum 10 znaków',true);return}
   try{await api('PATCH',{id:user.id,action:'password',password:newPass.value});newPass.value='';message('Hasło zostało zmienione: '+user.login)}catch(e){message(e.message,true)}
  });
 });
}
form.addEventListener('submit',async e=>{
 e.preventDefault();
 try{await api('POST',{login:login.value.trim(),password:pass.value});const name=login.value.trim();form.reset();message('Dodano konto: '+name);await refresh()}catch(err){message(err.message,true)}
});
modal.addEventListener('click',e=>{if(e.target===modal)modal.hidden=true});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden)modal.hidden=true});
async function start(){
 const topbuttons=document.querySelector('.awm-workshop-header .topbuttons');
 if(!topbuttons)return;
 const logout=elem('button',{type:'button',class:'awm-access-link',text:'⏻ WYLOGUJ'},topbuttons);
 logout.addEventListener('click',async()=>{await fetch('/api/logout',{method:'POST'});location.replace('/warsztat')});
 try{
  const r=await fetch('/api/me',{cache:'no-store'});const data=await r.json();
  if(!data.user||data.user.role!=='admin')return;
  const button=elem('button',{type:'button',class:'awm-access-link',text:'🔐 PANEL DOSTĘPU'},topbuttons);
  topbuttons.insertBefore(button,logout);
  button.addEventListener('click',async()=>{modal.hidden=false;message('');try{await refresh()}catch(e){message(e.message,true)}});
 }catch(e){/* access panel remains hidden when session cannot be verified */}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();