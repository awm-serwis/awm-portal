/* AWM workshop compact layout CSS embedded safely in JS. */
(function(){const style=document.createElement('style');style.textContent="/* AWM workshop compact two-column repair card; scoped to unlocked live details. */\n#awmLiveDetails .awm-detail-back{margin:12px 0}\n#awmLiveDetails .awm-repair-grid{display:grid;grid-template-columns:minmax(330px, 44%) minmax(0,1fr);gap:14px;align-items:stretch}\n#awmLiveDetails .awm-primary-vehicle{display:grid;grid-template-columns:42% minmax(0,1fr);min-height:142px}\n#awmLiveDetails .awm-primary-vehicle .car-photo{min-height:142px;overflow:hidden}\n#awmLiveDetails .awm-primary-vehicle .vehicle-info{padding:13px;min-width:0}\n#awmLiveDetails .awm-primary-vehicle h2{font-size:18px;overflow-wrap:anywhere}\n#awmLiveDetails .awm-primary-status{font-weight:700;color:#08734c!important}\n#awmLiveDetails .awm-repair-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:repeat(2,minmax(42px,1fr));gap:7px;align-content:center}\n#awmLiveDetails .awm-repair-tab{border:1px solid #d5e5db;background:#f5faf7;border-radius:10px;padding:7px 8px;font:600 12px/1.25 'Segoe UI',Arial,sans-serif;color:#174b36;cursor:pointer;text-align:center;min-width:0;overflow-wrap:anywhere}\n#awmLiveDetails .awm-repair-tab:hover,#awmLiveDetails .awm-repair-tab.active{background:#dcefe3;border-color:#67a985}\n#awmLiveDetails .awm-repair-tab:focus-visible{outline:3px solid #e7a640}\n#awmLiveDetails .awm-repair-content{margin-top:12px}\n#awmLiveDetails .awm-repair-panel:not([hidden]){display:block;background:#fff;border:1px solid #dce8df;border-radius:12px;padding:16px}\n#awmLiveDetails .awm-repair-panel h3{margin:0 0 10px;font-size:17px}\n#awmLiveDetails .awm-repair-panel .inner{white-space:pre-wrap;overflow-wrap:anywhere}\n@media(max-width:860px){#awmLiveDetails .awm-repair-grid{grid-template-columns:1fr}#awmLiveDetails .awm-repair-tabs{grid-template-columns:repeat(4,minmax(0,1fr))}}\n@media(max-width:500px){#awmLiveDetails .awm-repair-tabs{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:auto}#awmLiveDetails .awm-primary-vehicle{grid-template-columns:38% minmax(0,1fr)}}\n\n/* AWM R42 live workshop cases; demos are replaced only after successful load. */";document.head.appendChild(style);})();

(async function(){
 const root=document.getElementById('repairPreview');if(!root)return;
 const rows=Array.from(root.querySelectorAll('article.vehicle-card'));
 const details=document.getElementById('repairDetailArea');
 const search=document.getElementById('workshopSearch');
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let data;
 try{const r=await fetch('/api/warsztat/cases',{credentials:'same-origin'});if(!r.ok)throw Error('offline');data=await r.json();}
 catch(e){const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Brak połączenia z listą zleceń AWM. Odśwież stronę lub sprawdź usługę portalu.';return}
 if(!data.ok){const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Nie udało się pobrać listy pojazdów.';return;}
 rows.forEach(c=>c.remove());if(details){details.hidden=true;}
 const list=document.createElement('div');list.id='awmLiveList';root.querySelector('.awm-workshop-search').insertAdjacentElement('afterend',list);
 const banner=root.querySelector('.preview-head .tag');if(banner)banner.textContent='ZLECENIA Z PROGRAMU AWM';
 const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Zlecenia z programu AWM. Po kliknięciu PIN wyświetlą się szczegóły wybranego pojazdu.';
 const cases=Array.isArray(data.cases)?data.cases:[];
 if(!cases.length){list.innerHTML='<div class="panel">Brak opublikowanych zleceń. W programie AWM WARSZTAT wybierz WYŚLIJ NA PORTAL.</div>';return}
 const modal=document.createElement('dialog');modal.className='awm-vehicle-pin-modal';modal.style.cssText='border:0;border-radius:14px;padding:0;width:min(420px,94vw);max-width:94vw;box-shadow:0 20px 70px #001b1380';
 modal.innerHTML='<div class="panel" style="width:min(420px,94vw)"><h2>PIN pojazdu</h2><p>Wpisz PIN nadany w programie AWM (1–8 cyfr).</p><input type="password" inputmode="numeric" autocomplete="off" maxlength="8" aria-label="PIN pojazdu" style="font-size:22px;letter-spacing:6px;text-align:center"><p role="alert" class="error"></p><button type="button" class="btn accept">Otwórz kartę</button> <button type="button" class="btn cancel" style="background:#607c70">Anuluj</button></div>';
 document.body.appendChild(modal);let selected=null;
 modal.addEventListener('cancel',e=>{e.preventDefault();closeModal()});
 modal.querySelector('.cancel').onclick=()=>closeModal();
 function closeModal(){if(modal.open)modal.close();modal.querySelector('input').value='';}
 modal.querySelector('.accept').onclick=async()=>{
  const input=modal.querySelector('input'),alert=modal.querySelector('[role=alert]');
  alert.textContent='Sprawdzanie…';
  const button=modal.querySelector('.accept');
  if(button.disabled)return;
  if(!selected){alert.textContent='Najpierw wybierz pojazd.';return;}
  const chosen=selected;
  button.disabled=true;
  try{
   const r=await fetch('/api/warsztat/cases/'+encodeURIComponent(chosen.id)+'/unlock',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:input.value})});
   const x=await r.json().catch(()=>({}));
   if(!r.ok||!x.ok)throw Error(x.error||'Nie udało się zweryfikować PIN-u ('+r.status+').');
   alert.textContent='Otwieranie karty…';
   await open(chosen);
   closeModal();
  }catch(e){alert.textContent=e.message||'Nie udało się otworzyć karty pojazdu.';}
  finally{button.disabled=false;}
 };
 modal.querySelector('input').onkeydown=e=>{if(e.key==='Enter')modal.querySelector('.accept').click();if(e.key==='Escape')closeModal()};
 const selectedHead=root.querySelector('.preview-head h1');
 const originalTitle=selectedHead.textContent;
 let current=null;
 function card(v){const p=v.vehicle||{};const name=[p.marka,p.model].filter(Boolean).join(' ')||v.label||'Pojazd';
  const div=document.createElement('article');div.className='vehicle-card';div.dataset.needle=[name,p.vin,p.rejestracja,v.repair_no,v.repair_title].join(' ').toLowerCase();
  const status=(Array.isArray(v.stages)?v.stages:[]).at(-1)?.name||'Przyjęty do warsztatu';
  div.innerHTML='<div class="car-photo"><span>🚘</span><small>Zdjęcie po PIN</small></div><div class="vehicle-info"><h2>'+escape(name)+'</h2><div class="awm-fields"><div><small>Rejestracja</small><strong>'+escape(p.rejestracja||'—')+'</strong></div><div><small>Status</small><strong class="awm-status">'+escape(status)+'</strong></div></div></div><div class="side"><button class="awm-open-repair" type="button">🔒 PIN</button></div>';
  div.querySelector('button').onclick=(event)=>{event.preventDefault();event.stopPropagation();selected=v;modal.querySelector('[role=alert]').textContent='';modal.querySelector('input').value='';if(!modal.open)modal.showModal();modal.querySelector('input').focus()};
  return div;}
 const nodes=cases.map(card);nodes.forEach(n=>list.appendChild(n));
 search.oninput=()=>{let s=search.value.toLowerCase().trim();nodes.forEach(n=>n.hidden=!n.dataset.needle.includes(s))};
 const searchBtn=document.querySelector('.awm-workshop-search button');if(searchBtn)searchBtn.onclick=()=>search.dispatchEvent(new Event('input'));
 async function open(v){
  const r=await fetch('/api/warsztat/cases/'+encodeURIComponent(v.id),{credentials:'same-origin'});
  const x=await r.json().catch(()=>({}));
  if(!r.ok||!x.ok||!x.case)throw Error(x.error||'Nie udało się pobrać szczegółów pojazdu ('+r.status+').');
  document.getElementById('awmLiveDetails')?.remove();
  current=x.case;
  const section=document.createElement('section');section.id='awmLiveDetails';
  const p=current.vehicle||{},s=(current.sections&&typeof current.sections==='object'&&!Array.isArray(current.sections))?current.sections:{};
  const activeStages=Array.isArray(current.stages)?current.stages.filter(z=>z&&typeof z.name==='string'&&z.name.trim()):[];
  const parts=Array.isArray(s.czesci)?s.czesci.map(z=>escape(z?.name||z?.nazwa||'Część')+' — '+escape(z?.price||z?.cena||0)+' zł').join('<hr>'):escape(s.czesci||'');
  const ct=(s.koszty&&typeof s.koszty==='object')?s.koszty:{};
  const sections=[['💬 Usterka zgłoszona przez klienta','usterka',escape(s.usterka)],['🩺 Diagnoza warsztatu','diagnoza',escape(s.diagnoza)],['🛠 Zakres naprawy','zakres',escape(s.zakres)],['📦 Zastosowane części','czesci',parts],['💰 Koszty naprawy','koszty','Części: '+escape(ct.czesci||0)+' zł; robocizna: '+escape(ct.robocizna||0)+' zł; razem: '+escape(ct.razem||0)+' zł'],['📅 Terminy','terminy',escape(JSON.stringify(s.terminy||{}))],['✅ Zgody i akceptacje','zgody',escape(JSON.stringify(s.zgody||{}))]];
  if(s.notatki)sections.push(['📝 Notatki warsztatu','notatki',escape(s.notatki)]);
  const shown=sections.filter(z=>Object.hasOwn(s,z[1])&&z[2]&&z[2].trim()&&z[2]!=='{}');
  const status=activeStages.at(-1)?.name||'Przyjęty do warsztatu';
  section.innerHTML='<div class="awm-detail-back"><button class="btn back" type="button">← Powrót do pojazdów</button></div>'+
   '<div class="awm-repair-grid"><div class="vehicle-card awm-primary-vehicle"><div class="car-photo photo-slot">'+(current.has_photo?'Ładowanie zdjęcia…':'🚘')+'</div><div class="vehicle-info"><h2>'+escape([p.marka,p.model].filter(Boolean).join(' '))+'</h2><p>Rejestracja: '+escape(p.rejestracja||'—')+'</p><p class="awm-primary-status">Status: '+escape(status)+'</p></div></div>'+
   '<nav class="awm-repair-tabs" aria-label="Sekcje naprawy">'+shown.map((z,i)=>'<button type="button" class="awm-repair-tab" data-section="'+escape(z[1])+'" aria-expanded="false">'+z[0]+'</button>').join('')+'</nav></div>'+
   '<div class="awm-repair-content" aria-live="polite">'+shown.map(z=>'<div class="awm-repair-panel" data-panel="'+escape(z[1])+'" hidden><h3>'+z[0]+'</h3><div class="inner">'+z[2]+'</div></div>').join('')+'</div>';
  list.after(section);
  list.hidden=true;
  rows.forEach(c=>c.hidden=true);
  root.querySelector('.awm-workshop-search').hidden=true;
  selectedHead.textContent='Karta naprawy — '+(current.label||current.repair_no||'Pojazd');
  section.querySelector('.back').onclick=()=>{section.remove();list.hidden=false;rows.forEach(c=>c.hidden=false);root.querySelector('.awm-workshop-search').hidden=false;selectedHead.textContent=originalTitle;};
  const tabs=[...section.querySelectorAll('.awm-repair-tab')];
  const panels=[...section.querySelectorAll('.awm-repair-panel')];
  tabs.forEach(tab=>tab.addEventListener('click',()=>{
   const wasOpen=tab.getAttribute('aria-expanded')==='true';
   tabs.forEach(t=>{t.setAttribute('aria-expanded','false');t.classList.remove('active')});
   panels.forEach(panel=>panel.hidden=true);
   if(!wasOpen){tab.setAttribute('aria-expanded','true');tab.classList.add('active');const panel=panels.find(p=>p.dataset.panel===tab.dataset.section);if(panel)panel.hidden=false;}
  }));
  if(current.has_photo){const img=document.createElement('img');img.alt='Zdjęcie pojazdu z programu AWM';img.src='/api/warsztat/cases/'+encodeURIComponent(v.id)+'/photo';img.style.cssText='width:100%;height:100%;object-fit:contain';const slot=section.querySelector('.photo-slot');slot.innerHTML='';slot.appendChild(img)}
  section.scrollIntoView({block:'start',behavior:'smooth'});
 }
})();
