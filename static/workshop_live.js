/* AWM R42 live workshop cases; demos are replaced only after successful load. */
(async function(){
 const root=document.getElementById('repairPreview');if(!root)return;
 const rows=Array.from(root.querySelectorAll('article.vehicle-card'));
 const details=document.getElementById('repairDetailArea');
 const search=document.getElementById('workshopSearch');
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let data;
 try{const r=await fetch('/api/warsztat/cases',{credentials:'same-origin'});if(!r.ok)throw Error('offline');data=await r.json();}
 catch(e){const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Brak połączenia z listą zleceń AWM. Odśwież stronę lub sprawdź usługę portalu.';return}
 if(!data.ok){throw Error('Nie udało się pobrać listy pojazdów');}
 rows.forEach(c=>c.remove());if(details){details.hidden=true;}
 const list=document.createElement('div');list.id='awmLiveList';root.querySelector('.awm-workshop-search').insertAdjacentElement('afterend',list);
 const banner=root.querySelector('.preview-head .tag');if(banner)banner.textContent='ZLECENIA Z PROGRAMU AWM';
 const hint=root.querySelector('.demo-note');if(hint)hint.textContent='Zlecenia z programu AWM. Po kliknięciu PIN wyświetlą się szczegóły wybranego pojazdu.';
 const cases=data.cases||[];
 if(!cases.length){list.innerHTML='<div class="panel">Brak opublikowanych zleceń. W programie AWM WARSZTAT wybierz WYŚLIJ NA PORTAL.</div>';return}
 const modal=document.createElement('div');modal.className='voice-overlay hidden';modal.style.zIndex=1250;
 modal.innerHTML='<div class="panel" style="width:min(420px,94vw)"><h2>PIN pojazdu</h2><p>Wpisz PIN, aby otworzyć kartę naprawy.</p><input type="password" inputmode="numeric" autocomplete="off" maxlength="12" aria-label="PIN pojazdu" style="font-size:22px;letter-spacing:6px;text-align:center"><p role="alert" class="error"></p><button type="button" class="btn accept">Otwórz kartę</button> <button type="button" class="btn cancel" style="background:#607c70">Anuluj</button></div>';
 document.body.appendChild(modal);let selected=null;
 modal.querySelector('.cancel').onclick=()=>modal.classList.add('hidden');
 function closeModal(){modal.classList.add('hidden');modal.querySelector('input').value='';}
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
 const stages=['Przyjęty do warsztatu','W naprawie','Oczekuje na części','Zgoda na naprawę','Gotowy do wydania','Wydany klientowi'];
 let current=null;
 function card(v){const p=v.vehicle||{};const name=[p.marka,p.model].filter(Boolean).join(' ')||v.label||'Pojazd';
  const div=document.createElement('article');div.className='vehicle-card';div.dataset.needle=[name,p.vin,p.rejestracja,v.repair_no,v.repair_title].join(' ').toLowerCase();
  const status=(v.stages||[]).at(-1)?.name||'Przyjęty do warsztatu';
  div.innerHTML='<div class="car-photo"><span>🚘</span><small>Zdjęcie po PIN</small></div><div class="vehicle-info"><h2>'+escape(name)+'</h2><div class="awm-fields"><div><small>Rok</small><strong>'+escape(p.rok||'—')+'</strong></div><div><small>Rejestracja</small><strong>'+escape(p.rejestracja||'—')+'</strong></div><div><small>VIN</small><strong>'+escape(p.vin||'—')+'</strong></div><div><small>Status</small><strong class="awm-status">'+escape(status)+'</strong></div></div></div><div class="side"><button class="awm-open-repair" type="button">🔒 PIN</button></div>';
  div.querySelector('button').onclick=()=>{selected=v;modal.querySelector('[role=alert]').textContent='';modal.classList.remove('hidden');modal.querySelector('input').focus()};
  return div;}
 const nodes=cases.map(card);nodes.forEach(n=>list.appendChild(n));
 search.oninput=()=>{let s=search.value.toLowerCase().trim();nodes.forEach(n=>n.hidden=!n.dataset.needle.includes(s))};
 const searchBtn=document.querySelector('.awm-workshop-search button');if(searchBtn)searchBtn.onclick=()=>search.dispatchEvent(new Event('input'));
 async function open(v){
  const r=await fetch('/api/warsztat/cases/'+encodeURIComponent(v.id),{credentials:'same-origin'});
  const x=await r.json().catch(()=>({}));
  if(!r.ok||!x.ok||!x.case)throw Error(x.error||'Nie udało się pobrać szczegółów pojazdu ('+r.status+').');
  document.getElementById('awmLiveDetails')?.remove();
  current=x.case;list.hidden=true;root.querySelector('.awm-workshop-search').hidden=true;selectedHead.textContent='Karta naprawy — '+(current.label||current.repair_no||'Pojazd');
  const section=document.createElement('section');section.id='awmLiveDetails';
  const p=current.vehicle||{},s=current.sections||{};
  const parts=Array.isArray(s.czesci)?s.czesci.map(z=>escape(z.name)+' — '+escape(z.price)+' zł').join('<hr>'):'';
  const ct=s.koszty||{};
  const sections=[['💬 Usterka zgłoszona przez klienta','usterka',escape(s.usterka)],['🧰 Raport DTC','dtc','Raport skanera może zostać dołączony w kolejnej aktualizacji'],['🩺 Diagnoza warsztatu','diagnoza',escape(s.diagnoza)],['🛠 Zakres naprawy','zakres',escape(s.zakres)],['📦 Zastosowane części','czesci',parts],['💰 Koszty naprawy','koszty','Części: '+escape(ct.czesci||0)+' zł; robocizna: '+escape(ct.robocizna||0)+' zł; razem: '+escape(ct.razem||0)+' zł'],['📅 Terminy','terminy',escape(JSON.stringify(s.terminy||{}))],['✅ Zgody i akceptacje','zgody',escape(JSON.stringify(s.zgody||{}))]];
  if(s.notatki)sections.push(['📝 Notatki warsztatu','notatki',escape(s.notatki)]);
  section.innerHTML='<div style="margin:14px 0"><button class="btn back" type="button">← Powrót do pojazdów</button></div>'+
   '<div class="vehicle-card"><div class="car-photo photo-slot">'+(current.has_photo?'Ładowanie zdjęcia…':'🚘')+'</div><div class="vehicle-info"><h2>'+escape([p.marka,p.model].join(' '))+'</h2><p>VIN: '+escape(p.vin)+' · Rejestracja: '+escape(p.rejestracja)+'</p><p>'+escape(current.repair_no||'')+'</p></div></div>'+
   '<div class="timeline">'+stages.map(t=>'<div class="step '+(current.stages||[]).some(z=>z.name===t?'on':'')+'"><b>✓</b>'+escape(t)+'</div>').join('')+'</div><div class="accordions">'+sections.filter(z=>z[1]==='dtc'||Object.hasOwn(s,z[1])).map(z=>'<details><summary>'+z[0]+'</summary><div class="inner">'+(z[2]||'Brak danych')+'</div></details>').join('')+'</div>';
  list.after(section);section.querySelector('.back').onclick=()=>{section.remove();list.hidden=false;root.querySelector('.awm-workshop-search').hidden=false;selectedHead.textContent=originalTitle;};
  if(current.has_photo){const img=document.createElement('img');img.alt='Zdjęcie pojazdu';img.src='/api/warsztat/cases/'+v.id+'/photo';img.style.cssText='width:100%;height:100%;object-fit:cover;border-radius:6px';const slot=section.querySelector('.photo-slot');slot.innerHTML='';slot.appendChild(img)}
 }
})();
