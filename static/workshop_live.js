/* AWM workshop compact layout CSS embedded safely in JS. */
(function(){const style=document.createElement('style');style.textContent='#awmLiveList[hidden]{display:none!important} #repairPreview article.vehicle-card[hidden]{display:none!important} '+"/* AWM workshop compact two-column repair card; scoped to unlocked live details. */\n#awmLiveDetails .awm-detail-back{margin:12px 0}\n#awmLiveDetails .awm-repair-grid{display:grid;grid-template-columns:minmax(330px, 44%) minmax(0,1fr);gap:14px;align-items:stretch}\n#awmLiveDetails .awm-primary-vehicle{display:grid;grid-template-columns:42% minmax(0,1fr);min-height:142px}\n#awmLiveDetails .awm-primary-vehicle .car-photo{min-height:142px;overflow:hidden}\n#awmLiveDetails .awm-primary-vehicle .vehicle-info{padding:13px;min-width:0}\n#awmLiveDetails .awm-primary-vehicle h2{font-size:18px;overflow-wrap:anywhere}\n#awmLiveDetails .awm-primary-status{font-weight:700;color:#08734c!important}\n#awmLiveDetails .awm-repair-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:repeat(2,minmax(42px,1fr));gap:7px;align-content:center}\n#awmLiveDetails .awm-repair-tab{border:1px solid #d5e5db;background:#f5faf7;border-radius:10px;padding:7px 8px;font:600 12px/1.25 'Segoe UI',Arial,sans-serif;color:#174b36;cursor:pointer;text-align:center;min-width:0;overflow-wrap:anywhere}\n#awmLiveDetails .awm-repair-tab:hover,#awmLiveDetails .awm-repair-tab.active{background:#dcefe3;border-color:#67a985}\n#awmLiveDetails .awm-repair-tab:focus-visible{outline:3px solid #e7a640}\n#awmLiveDetails .awm-repair-content{margin-top:12px}\n#awmLiveDetails .awm-repair-panel:not([hidden]){display:block;background:#fff;border:1px solid #dce8df;border-radius:12px;padding:16px}\n#awmLiveDetails .awm-repair-panel h3{margin:0 0 10px;font-size:17px}\n#awmLiveDetails .awm-repair-panel .inner{white-space:pre-wrap;overflow-wrap:anywhere}\n@media(max-width:860px){#awmLiveDetails .awm-repair-grid{grid-template-columns:1fr}#awmLiveDetails .awm-repair-tabs{grid-template-columns:repeat(4,minmax(0,1fr))}}\n@media(max-width:500px){#awmLiveDetails .awm-repair-tabs{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:auto}#awmLiveDetails .awm-primary-vehicle{grid-template-columns:38% minmax(0,1fr)}}\n\n/* AWM R42 live workshop cases; demos are replaced only after successful load. */";document.head.appendChild(style);})();

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
 const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Zlecenia z programu AWM. Kliknij pojazd, aby otworzyć kartę bez dodatkowego PIN-u.';
 const cases=Array.isArray(data.cases)?data.cases:[];
 if(!cases.length){list.innerHTML='<div class="panel">Brak opublikowanych zleceń. W programie AWM WARSZTAT wybierz WYŚLIJ NA PORTAL.</div>';return}
 const selectedHead=root.querySelector('.preview-head h1');
 const originalTitle=selectedHead.textContent;
 let current=null;
 function card(v){
  const p=v.vehicle||{},sec=v.sections||{},name=[p.marka,p.model].filter(Boolean).join(' ')||v.label||'Pojazd';
  const div=document.createElement('article');div.className='vehicle-card';
  div.dataset.needle=[name,p.vin,p.rejestracja,v.repair_no,v.repair_title,sec.usterka,sec.diagnoza].join(' ').toLowerCase();
  const status=(Array.isArray(v.stages)?v.stages:[]).at(-1)?.name||'Przyjęty do warsztatu';
  const cost=sec.koszty||{},money=typeof cost==='object'
   ?'Części: '+String(cost.czesci??'0')+' zł • Robocizna: '+String(cost.robocizna??'0')+' zł • Razem: '+String(cost.razem??'0')+' zł'
   :String(cost||'—');
  div.innerHTML='<div class="vehicle-info" style="padding:12px;min-width:0"><h2>'+escape(name)+'</h2>'+
   '<p style="font-size:12px">Rejestracja: '+escape(p.rejestracja||'—')+(v.repair_no?' • Zlecenie: '+escape(v.repair_no):'')+'</p>'+
   '<div class="awm-all-fields" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px">'+
   [['Usterka',sec.usterka||v.repair_title||'—'],['Diagnoza',sec.diagnoza||'—'],['Status',status],['Koszty netto',money]].map(x=>
    '<div style="padding:8px;background:#f4faf6;border:1px solid #dfebe3;border-radius:7px;overflow-wrap:anywhere">'+
    '<small style="display:block;color:#627a6b">'+escape(x[0])+'</small><strong style="white-space:pre-wrap">'+escape(x[1])+'</strong></div>').join('')+
   '</div></div>';
  div.style.cssText='display:block!important;min-width:0!important;cursor:default!important;height:auto!important';
  if(v.has_photo){
   const img=document.createElement('img');img.alt='Zdjęcie pojazdu';img.loading='lazy';
   img.src='/api/warsztat/cases/'+encodeURIComponent(v.id)+'/photo';
   img.style.cssText='max-width:180px;max-height:110px;object-fit:contain;margin:8px;border-radius:8px';
   div.appendChild(img);
  }
  for(const a of (Array.isArray(v.attachments)?v.attachments:[])){
   if(!a?.id)continue;
   const link=document.createElement('a');link.textContent=(a.kind==='report'?'📄 Raport PDF: ':'📷 Zdjęcie: ')+String(a.name||'Plik');
   link.href='/api/warsztat/cases/'+encodeURIComponent(v.id)+'/attachments/'+encodeURIComponent(a.id);
   link.target='_blank';link.rel='noopener noreferrer';link.style.cssText='display:block;margin:5px 12px;font-weight:700';
   div.appendChild(link);
  }
  return div;
 }
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

  // Read-only consent and protected diagnostic reports / vehicle photos.
  const consent=current.approval||{};
  if(consent.status==='pending'||consent.status==='approved'){
   const info=document.createElement('p');
   info.style.cssText='padding:10px;background:#e7f4ed;border-radius:8px;font-weight:700;margin:10px 0';
   info.textContent=consent.status==='approved'
     ?'✓ Zgoda klienta: '+(consent.person||'—')+' • '+(consent.decided_at?new Date(consent.decided_at).toLocaleString('pl-PL'):'—')
     :'⏳ Oczekiwanie na zgodę klienta';
   section.appendChild(info);
  }
  if(Array.isArray(current.attachments)&&current.attachments.length){
   const files=document.createElement('div');files.style.cssText='padding:12px;background:white;border:1px solid #d1e4d8;border-radius:9px;margin:10px 0';
   const title=document.createElement('h3');title.textContent='Raporty PDF i zdjęcia';files.appendChild(title);
   for(const item of current.attachments){
    if(!item||!item.id)continue;
    const link=document.createElement('a');link.textContent=(item.kind==='report'?'📄 ':'📷 ')+String(item.name||'Załącznik');
    link.href='/api/warsztat/cases/'+encodeURIComponent(v.id)+'/attachments/'+encodeURIComponent(item.id);
    link.target='_blank';link.rel='noopener noreferrer';link.style.cssText='display:block;margin:6px 0;font-weight:700';
    files.appendChild(link);
   }
   section.appendChild(files);
  }
  list.after(section);
  list.hidden=true;
  list.style.setProperty('display','none','important');
  rows.forEach(c=>{c.hidden=true;c.style.setProperty('display','none','important')});
  root.querySelector('.awm-workshop-search').hidden=true;
  selectedHead.textContent='Karta naprawy — '+(current.label||current.repair_no||'Pojazd');
  section.querySelector('.back').onclick=()=>{section.remove();list.hidden=false;list.style.removeProperty('display');rows.forEach(c=>{c.hidden=false;c.style.removeProperty('display')});root.querySelector('.awm-workshop-search').hidden=false;selectedHead.textContent=originalTitle;};
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
