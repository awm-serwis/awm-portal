import os,json,sqlite3,secrets,hashlib,hmac,mimetypes,threading,webbrowser,zipfile,shutil,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs,quote,unquote
from http.cookies import SimpleCookie
from datetime import datetime
BASE=Path(__file__).resolve().parent; INDEX_HTML='<!doctype html><html lang=pl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>AWM Portal</title><style>*{box-sizing:border-box}body{margin:0;font:14px Segoe UI,Arial;background:#f3f7f5;color:#15241e}.top{background:linear-gradient(90deg,#031c15,#075237);color:#fff;padding:24px 5%;display:flex;align-items:center}.brand{font-size:34px;font-weight:900}.brand b{color:#19d27c}.right{margin-left:auto}.wrap{max-width:1500px;margin:auto;padding:28px}.card,.row{background:#fff;border:1px solid #dce7e2;border-radius:12px;box-shadow:0 2px 10px #0000000b}.login{max-width:420px;margin:8vh auto;padding:30px}.login input,.field{width:100%;padding:13px;margin:7px 0;border:1px solid #ccd9d4;border-radius:7px}.btn{border:0;border-radius:7px;padding:11px 15px;font-weight:800;cursor:pointer;background:#0a9a57;color:white}.ghost{background:#eef4f1;color:#17352a}.toolbar{display:flex;gap:10px;margin-bottom:18px}.search{flex:1;padding:13px;border:1px solid #ccd9d4;border-radius:8px}.row{display:grid;grid-template-columns:150px 1.3fr 1.1fr .7fr 1.8fr;gap:16px;align-items:center;padding:14px;margin-bottom:10px}.pic{width:140px;height:90px;object-fit:cover;border-radius:8px;background:#e8efec}.actions{display:flex;gap:7px;flex-wrap:wrap}.a{padding:10px 12px;border-radius:7px;color:white;text-decoration:none;font-weight:800;background:#176fd0}.green{background:#0b9b56}.dark{background:#26332e}.admin{background:#fff5d9;border:1px solid #ead18a;padding:16px;border-radius:10px;margin-bottom:18px}.admin input{padding:10px;border:1px solid #ccc;border-radius:6px;margin:3px}.hidden{display:none}.muted{color:#6e7d77}.x{background:#b93838}@media(max-width:900px){.row{grid-template-columns:1fr}.pic{width:100%;height:190px}}</style></head><body><header class=top><div><div class=brand>PRZEGLĄD <b>AWM</b></div><div>PORTAL DOKUMENTACJI POJAZDÓW</div></div><div class=right id=who></div></header><main class=wrap><section id=login class="card login"><h2>Logowanie do AWM</h2><input id=lu placeholder=Login><input id=lp type=password placeholder=Hasło><button class=btn onclick=login()>ZALOGUJ</button><p id=err></p></section><section id=app class=hidden><div id=admin class="admin hidden"><b>PANEL ADMINISTRATORA</b><div style="margin-top:10px"><button class=btn onclick="up.classList.toggle(\'hidden\')">+ DODAJ POJAZD / DOKUMENTY</button> <button class="btn ghost" onclick="newUser()">+ KONTO RZECZOZNAWCY</button></div><form id=up class=hidden style="margin-top:12px"><input name=marka placeholder=Marka required><input name=model placeholder=Model required><input name=rej placeholder=Rejestracja><input name=vin placeholder=VIN><input name=przebieg placeholder=Przebieg><input name=rok placeholder=Rok><br>Zdjęcie: <input type=file name=photo accept="image/*"> Opis: <input type=file name=opis accept=".doc,.docx,.pdf" multiple> Wycena: <input type=file name=wycena accept=.pdf multiple> Raport diagnostyczny: <input type=file name=raport accept=.pdf multiple><button class=btn>WYŚLIJ DO PORTALU</button></form></div><div class=toolbar><input id=q class=search placeholder="Szukaj po marce, modelu, VIN, rejestracji..."><button class="btn ghost" onclick=logout()>Wyloguj</button></div><div id=list></div></section></main><script>let me=null,V=[];const $=id=>document.getElementById(id);async function api(u,o){let r=await fetch(u,o);return [r,await r.json().catch(()=>({}))]}async function start(){let[,x]=await api(\'/api/me\');me=x.user;if(!me)return;$(\'login\').classList.add(\'hidden\');$(\'app\').classList.remove(\'hidden\');$(\'who\').textContent=me.login+\' • \'+(me.role===\'admin\'?\'ADMIN\':\'RZECZOZNAWCA\');if(me.role===\'admin\')$(\'admin\').classList.remove(\'hidden\');load()}async function login(){let[r,x]=await api(\'/api/login\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({login:$(\'lu\').value,password:$(\'lp\').value})});if(r.ok)location.reload();$(\'err\').textContent=x.error||\'Błąd\'}async function logout(){await fetch(\'/api/logout\',{method:\'POST\'});location.reload()}async function load(){[,V]=await api(\'/api/vehicles\');render()}function esc(s){return String(s||\'\').replace(/[&<>"\']/g,m=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[m]))}function render(){let s=$(\'q\').value.toLowerCase(),a=V.filter(v=>JSON.stringify(v).toLowerCase().includes(s));$(\'list\').innerHTML=a.map(v=>{let d=k=>v.docs.filter(x=>x.kind===k).map(x=>`<a class="a ${k===\'wycena\'?\'green\':k===\'raport\'?\'dark\':\'\'}" href="/file/${x.id}" target="_blank">${k===\'opis\'?\'📄 PODGLĄD OPISU\':k===\'wycena\'?\'💰 PODGLĄD WYCENY\':\'🔧 PODGLĄD RAPORTU DIAG\'}</a>`).join(\'\');return `<div class=row>${v.photo?`<img class=pic src="/file/${v.photo}">`:\'<div class=pic></div>\'}<div><b style="font-size:18px">${esc(v.marka)} ${esc(v.model)}</b><div class=muted>${esc(v.rok)}</div></div><div><b>${esc(v.rej)}</b><div class=muted>${esc(v.vin)}</div></div><div>${esc(v.przebieg||\'—\')}</div><div class=actions>${d(\'opis\')}${d(\'wycena\')}${d(\'raport\')}${me.role===\'admin\'?`<button class="btn x" onclick="delv(${v.id})">USUŃ</button>`:\'\'}</div></div>`}).join(\'\')||\'<div class="card" style="padding:50px;text-align:center">Brak udostępnionych pojazdów.</div>\'}$(\'q\').oninput=render;$(\'up\').onsubmit=async e=>{e.preventDefault();let r=await fetch(\'/api/upload\',{method:\'POST\',body:new FormData(e.target)});if(r.ok){e.target.reset();e.target.classList.add(\'hidden\');load()}else alert(\'Błąd wysyłania\')};async function newUser(){let l=prompt(\'Login rzeczoznawcy:\');if(!l)return;let p=prompt(\'Hasło:\');if(!p)return;let[r,x]=await api(\'/api/user\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({login:l,password:p})});alert(r.ok?\'Konto utworzone\':x.error)}async function delv(id){if(confirm(\'Usunąć pojazd z portalu?\')){await fetch(\'/api/vehicle/\'+id,{method:\'DELETE\'});load()}}start()</script></body></html>\n'; DATA=Path(os.getenv('AWM_DATA_DIR',str(BASE/'data'))); DATA.mkdir(parents=True,exist_ok=True); DB=DATA/'portal.db'; FILES=DATA/'files'; FILES.mkdir(exist_ok=True)
PORT=int(os.getenv('PORT','8093')); HOST=os.getenv('HOST','0.0.0.0'); ADMIN_USER=os.getenv('AWM_ADMIN_USER','AWM'); ADMIN_PASS=os.getenv('AWM_ADMIN_PASS','AWM-START-2026'); API_KEY=os.getenv('AWM_API_KEY','AWM-CHANGE-ME')
SESS={}
def db(): c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def ph(p,s=None): s=s or secrets.token_hex(16);return s+'$'+hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),120000).hex()
def okp(p,h):
 try:s,x=h.split('$',1);return hmac.compare_digest(ph(p,s),h)
 except:return False
def init():
 c=db();c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,login TEXT UNIQUE,pass TEXT,role TEXT);CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,portal_id TEXT UNIQUE,marka TEXT,model TEXT,rej TEXT,vin TEXT,przebieg TEXT,rok TEXT,updated TEXT,active INTEGER DEFAULT 1);CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY,vehicle_id INTEGER,kind TEXT,name TEXT,path TEXT);''')
 cols={r[1] for r in c.execute('pragma table_info(vehicles)')}
 if 'portal_id' not in cols:c.execute('alter table vehicles add column portal_id TEXT')
 if 'active' not in cols:c.execute('alter table vehicles add column active INTEGER DEFAULT 1')
 if not c.execute('select 1 from users where login=?',(ADMIN_USER,)).fetchone():c.execute('insert into users(login,pass,role) values(?,?,?)',(ADMIN_USER,ph(ADMIN_PASS),'admin'))
 c.commit();c.close()
init()
def user(req):
 ck=SimpleCookie(req.headers.get('Cookie',''));sid=ck.get('awm_session');return SESS.get(sid.value) if sid else None
def keyok(req):return hmac.compare_digest(req.headers.get('X-AWM-Key',''),API_KEY)
def js(h,x,code=200):h.send_response(code);h.send_header('Content-Type','application/json; charset=utf-8');h.end_headers();h.wfile.write(json.dumps(x,ensure_ascii=False).encode())
def safe(n):return ''.join(ch for ch in Path(n).name if ch.isalnum() or ch in ' ._-()[]')[:160] or 'plik'
def vdict(r):return {'id':r['portal_id'] or str(r['id']),'marka':r['marka'],'model':r['model'],'rejestracja':r['rej'],'rej':r['rej'],'vin':r['vin'],'przebieg':r['przebieg'],'rok':r['rok'],'aktualizacja':r['updated'],'updated':r['updated'],'active':bool(r['active'])}
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def sendfile(self,p,download=False):
  p=Path(p);self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream');
  if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(p.name))
  self.end_headers();self.wfile.write(p.read_bytes())
 def do_GET(self):
  u=urlparse(self.path);p=u.path;me=user(self)
  if p in ('/','/index.html'):
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(INDEX_HTML.encode('utf-8'));return
  if p=='/api/me':return js(self,{'user':me})
  if p=='/api/admin/vehicles':
   if not keyok(self):return js(self,{'error':'bad key'},403)
   c=db();rows=[vdict(r) for r in c.execute('select * from vehicles order by updated desc')];c.close();return js(self,{'vehicles':rows})
  if p=='/api/vehicles':
   if not me:return js(self,{'error':'login'},401)
   c=db();rows=[]
   for r in c.execute('select * from vehicles where active=1 order by updated desc'):
    x=dict(r);ds=[dict(d) for d in c.execute('select id,kind,name from docs where vehicle_id=?',(r['id'],))];x['docs']=ds;x['photo']=next((d['id'] for d in ds if d['kind']=='photo'),None);rows.append(x)
   c.close();return js(self,rows)
  if p=='/api/users':
   if not me or me['role']!='admin':return js(self,{'error':'forbidden'},403)
   c=db();x=[dict(r) for r in c.execute('select id,login,role from users order by login')];c.close();return js(self,x)
  if p.startswith('/file/'):
   if not me:return js(self,{'error':'login'},401)
   try:i=int(p.rsplit('/',1)[1]);c=db();r=c.execute('select * from docs where id=?',(i,)).fetchone();c.close();return self.sendfile(r['path'],parse_qs(u.query).get('download',['0'])[0]=='1') if r else js(self,{'error':'404'},404)
   except:return js(self,{'error':'404'},404)
  return js(self,{'error':'404'},404)
 def do_POST(self):
  u=urlparse(self.path);p=u.path;me=user(self)
  if p=='/api/publish':
   if not keyok(self):return js(self,{'error':'bad key'},403)
   pid=parse_qs(u.query).get('id',[''])[0].strip()
   if not pid:return js(self,{'error':'missing id'},400)
   n=int(self.headers.get('Content-Length','0'));raw=self.rfile.read(n);td=Path(tempfile.mkdtemp(prefix='awmweb_'))
   try:
    zp=td/'p.zip';zp.write_bytes(raw)
    with zipfile.ZipFile(zp) as z:z.extractall(td/'x')
    meta=json.loads((td/'x'/'vehicle.json').read_text(encoding='utf-8'));c=db();r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
    if r:
     vid=r['id'];old=c.execute('select path from docs where vehicle_id=?',(vid,)).fetchall();[Path(x['path']).unlink(missing_ok=True) for x in old];c.execute('delete from docs where vehicle_id=?',(vid,));c.execute('update vehicles set marka=?,model=?,rej=?,vin=?,przebieg=?,rok=?,updated=?,active=1 where id=?',(meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes'),vid))
    else:
     cur=c.execute('insert into vehicles(portal_id,marka,model,rej,vin,przebieg,rok,updated,active) values(?,?,?,?,?,?,?,?,1)',(pid,meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes')));vid=cur.lastrowid
    d=FILES/str(vid);shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True,exist_ok=True)
    mapping={'ZDJECIA':'photo','OPIS':'opis','WYCENA':'wycena','DIAG':'raport'}
    for folder,kind in mapping.items():
     for f in (td/'x'/folder).glob('*') if (td/'x'/folder).is_dir() else []:
      if f.is_file():dst=d/(secrets.token_hex(4)+'_'+safe(f.name));shutil.copy2(f,dst);c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,f.name,str(dst)))
    c.commit();c.close();return js(self,{'ok':True,'id':pid})
   except Exception as e:return js(self,{'error':str(e)},400)
   finally:shutil.rmtree(td,ignore_errors=True)
  if p=='/api/login':
   n=int(self.headers.get('Content-Length','0'));x=json.loads(self.rfile.read(n) or b'{}');c=db();r=c.execute('select * from users where login=?',(x.get('login',''),)).fetchone();c.close()
   if not r or not okp(x.get('password',''),r['pass']):return js(self,{'error':'Błędny login lub hasło'},401)
   sid=secrets.token_urlsafe(32);SESS[sid]={'id':r['id'],'login':r['login'],'role':r['role']};self.send_response(200);self.send_header('Set-Cookie',f'awm_session={sid}; HttpOnly; SameSite=Lax; Path=/');self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}');return
  if p=='/api/logout':
   ck=SimpleCookie(self.headers.get('Cookie',''));sid=ck.get('awm_session');SESS.pop(sid.value,None) if sid else None;self.send_response(200);self.send_header('Set-Cookie','awm_session=; Max-Age=0; Path=/');self.end_headers();return
  if not me:return js(self,{'error':'login'},401)
  if p=='/api/user' and me['role']=='admin':
   n=int(self.headers.get('Content-Length','0'));x=json.loads(self.rfile.read(n) or b'{}')
   try:c=db();c.execute('insert into users(login,pass,role) values(?,?,?)',(x['login'].strip(),ph(x['password']),'appraiser'));c.commit();c.close();return js(self,{'ok':True})
   except Exception as e:return js(self,{'error':str(e)},400)
  return js(self,{'error':'forbidden'},403)
 def do_DELETE(self):
  p=urlparse(self.path).path
  if p.startswith('/api/admin/vehicles/'):
   if not keyok(self):return js(self,{'error':'bad key'},403)
   pid=unquote(p.split('/api/admin/vehicles/',1)[1]);c=db();c.execute('update vehicles set active=0,updated=? where portal_id=?',(datetime.now().isoformat(timespec='minutes'),pid));c.commit();c.close();return js(self,{'ok':True,'active':False})
  return js(self,{'error':'404'},404)
if __name__=='__main__':
 print(f'AWM PORTAL: http://127.0.0.1:{PORT}');
 if os.getenv('AWM_NO_BROWSER')!='1' and HOST in ('127.0.0.1','localhost'):threading.Timer(1,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
 ThreadingHTTPServer((HOST,PORT),H).serve_forever()
