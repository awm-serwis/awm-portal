import os, json, sqlite3, secrets, hashlib, hmac, zipfile, tempfile, shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, session, Response

app = Flask(__name__)
app.secret_key = os.getenv('AWM_SECRET_KEY', 'awm-portal-53-change-me')
BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv('AWM_DATA_DIR', str(BASE / 'data')))
FILES = DATA / 'files'
DATA.mkdir(parents=True, exist_ok=True); FILES.mkdir(parents=True, exist_ok=True)
DB = DATA / 'portal.db'
API_KEY = os.getenv('AWM_API_KEY', 'AWM-CHANGE-ME')
ADMIN_USER = os.getenv('AWM_ADMIN_USER', 'AWM')
ADMIN_PASS = os.getenv('AWM_ADMIN_PASS', 'AWM-START-2026')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def ph(p,s=None):
    s=s or secrets.token_hex(16)
    return s+'$'+hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),120000).hex()

def okp(p,h):
    try:
        s,_=h.split('$',1); return hmac.compare_digest(ph(p,s),h)
    except: return False

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,login TEXT UNIQUE,pass TEXT,role TEXT);
    CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,portal_id TEXT UNIQUE,marka TEXT,model TEXT,rej TEXT,vin TEXT,przebieg TEXT,rok TEXT,updated TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY,vehicle_id INTEGER,kind TEXT,name TEXT,path TEXT);
    ''')
    if not c.execute('select 1 from users where login=?',(ADMIN_USER,)).fetchone():
        c.execute('insert into users(login,pass,role) values(?,?,?)',(ADMIN_USER,ph(ADMIN_PASS),'admin'))
    c.commit(); c.close()
init_db()

def api_ok(): return hmac.compare_digest(request.headers.get('X-AWM-Key',''), API_KEY)
def safe(n): return ''.join(ch for ch in Path(n).name if ch.isalnum() or ch in ' ._-()[]')[:160] or 'plik'
def vdict(r):
    return {'id':r['portal_id'] or str(r['id']),'marka':r['marka'],'model':r['model'],'rejestracja':r['rej'],'rej':r['rej'],'vin':r['vin'],'przebieg':r['przebieg'],'rok':r['rok'],'aktualizacja':r['updated'],'updated':r['updated'],'active':bool(r['active'])}

HTML = r'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AWM Portal</title><style>
*{box-sizing:border-box}body{margin:0;font:14px Segoe UI,Arial;background:#f3f7f5;color:#14241e}.top{background:linear-gradient(90deg,#031d16,#07533a);color:#fff;padding:22px 5%;display:flex;align-items:center}.brand{font-size:32px;font-weight:900}.brand b{color:#21d17d}.sub{opacity:.85}.who{margin-left:auto}.wrap{max-width:1450px;margin:auto;padding:28px}.card,.row{background:#fff;border:1px solid #dce7e2;border-radius:12px;box-shadow:0 2px 10px #0000000b}.login{max-width:430px;margin:8vh auto;padding:30px}.login input,.search{width:100%;padding:13px;border:1px solid #cbd8d3;border-radius:8px;margin:7px 0}.btn{border:0;border-radius:7px;padding:11px 15px;font-weight:800;cursor:pointer;background:#0a9a57;color:#fff}.ghost{background:#eaf2ee;color:#17352a}.toolbar{display:flex;gap:10px;margin-bottom:18px}.row{display:grid;grid-template-columns:150px 1.3fr 1.1fr .7fr 2fr;gap:16px;align-items:center;padding:14px;margin-bottom:10px}.pic{width:140px;height:90px;object-fit:cover;border-radius:8px;background:#e7eeeb}.actions{display:flex;gap:7px;flex-wrap:wrap}.a{padding:10px 12px;border-radius:7px;color:#fff;text-decoration:none;font-weight:800;background:#176fd0}.green{background:#0b9b56}.dark{background:#26332e}.muted{color:#6d7d76}.hidden{display:none}.empty{padding:50px;text-align:center}.status{font-weight:700;color:#21d17d}@media(max-width:900px){.row{grid-template-columns:1fr}.pic{width:100%;height:200px}}</style></head><body>
<header class="top"><div><div class="brand">PRZEGLĄD <b>AWM</b></div><div class="sub">PORTAL RZECZOZNAWCÓW</div></div><div class="who" id="who"><span class="status">● ONLINE</span></div></header>
<main class="wrap"><section id="login" class="card login"><h2>Logowanie do AWM Portal</h2><input id="lu" placeholder="Login"><input id="lp" type="password" placeholder="Hasło"><button class="btn" onclick="login()">ZALOGUJ</button><p id="err"></p></section><section id="app" class="hidden"><div class="toolbar"><input id="q" class="search" placeholder="Szukaj: marka, model, VIN, rejestracja..."><button class="btn ghost" onclick="logout()">Wyloguj</button></div><div id="list"></div></section></main>
<script>
let V=[];const $=x=>document.getElementById(x);async function j(u,o){let r=await fetch(u,o);let x={};try{x=await r.json()}catch(e){}return[r,x]}
async function boot(){let[r,x]=await j('/api/me');if(x.user){$('login').classList.add('hidden');$('app').classList.remove('hidden');$('who').innerHTML='<span class="status">● ONLINE</span> &nbsp; '+x.user.login;load()}}
async function login(){let[r,x]=await j('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:$('lu').value,password:$('lp').value})});if(r.ok)location.reload();else $('err').textContent=x.error||'Błąd logowania'}
async function logout(){await fetch('/api/logout',{method:'POST'});location.reload()}
async function load(){let[r,x]=await j('/api/vehicles');V=Array.isArray(x)?x:[];render()}
function e(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function render(){let s=($('q').value||'').toLowerCase();let a=V.filter(v=>JSON.stringify(v).toLowerCase().includes(s));$('list').innerHTML=a.map(v=>{let b=k=>v.docs.filter(d=>d.kind===k).map(d=>`<a class="a ${k==='wycena'?'green':k==='raport'?'dark':''}" href="/file/${d.id}" target="_blank">${k==='opis'?'📄 PODGLĄD OPISU':k==='wycena'?'💰 PODGLĄD WYCENY':'🔧 PODGLĄD RAPORTU DIAG'}</a>`).join('');return `<div class="row">${v.photo?`<img class="pic" src="/file/${v.photo}">`:'<div class="pic"></div>'}<div><b style="font-size:18px">${e(v.marka)} ${e(v.model)}</b><div class="muted">${e(v.rok)}</div></div><div><b>${e(v.rej)}</b><div class="muted">${e(v.vin)}</div></div><div>${e(v.przebieg||'—')}</div><div class="actions">${b('opis')}${b('wycena')}${b('raport')}</div></div>`}).join('')||'<div class="card empty">Brak udostępnionych pojazdów.</div>'}
$('q').oninput=render;boot();</script></body></html>'''

@app.get('/')
def home(): return Response(HTML, mimetype='text/html')
@app.get('/health')
def health(): return jsonify(ok=True, version='5.3-web-fix')
@app.get('/api/me')
def me(): return jsonify(user=session.get('user'))
@app.post('/api/login')
def login():
    x=request.get_json(silent=True) or {}; c=db(); r=c.execute('select * from users where login=?',(x.get('login',''),)).fetchone(); c.close()
    if not r or not okp(x.get('password',''),r['pass']): return jsonify(error='Błędny login lub hasło'),401
    session['user']={'id':r['id'],'login':r['login'],'role':r['role']}; return jsonify(ok=True)
@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)
@app.get('/api/vehicles')
def vehicles():
    if not session.get('user'): return jsonify(error='login'),401
    c=db(); out=[]
    for r in c.execute('select * from vehicles where active=1 order by updated desc'):
        x=dict(r); ds=[dict(d) for d in c.execute('select id,kind,name from docs where vehicle_id=?',(r['id'],))]; x['docs']=ds; x['photo']=next((d['id'] for d in ds if d['kind']=='photo'),None); out.append(x)
    c.close(); return jsonify(out)
@app.get('/file/<int:i>')
def file(i):
    if not session.get('user'): return jsonify(error='login'),401
    c=db(); r=c.execute('select * from docs where id=?',(i,)).fetchone(); c.close()
    if not r or not Path(r['path']).is_file(): return jsonify(error='404'),404
    return send_file(r['path'], as_attachment=False, download_name=r['name'])
@app.get('/api/admin/vehicles')
def admin_vehicles():
    if not api_ok(): return jsonify(error='bad key'),403
    c=db(); out=[vdict(r) for r in c.execute('select * from vehicles order by updated desc')]; c.close(); return jsonify(vehicles=out)
@app.delete('/api/admin/vehicles/<path:pid>')
def expire(pid):
    if not api_ok(): return jsonify(error='bad key'),403
    c=db(); c.execute('update vehicles set active=0,updated=? where portal_id=?',(datetime.now().isoformat(timespec='minutes'),pid)); c.commit(); c.close(); return jsonify(ok=True,active=False)
@app.post('/api/publish')
def publish():
    if not api_ok(): return jsonify(error='bad key'),403
    pid=(request.args.get('id') or '').strip()
    if not pid: return jsonify(error='missing id'),400
    td=Path(tempfile.mkdtemp(prefix='awm53_'))
    try:
        zp=td/'p.zip'; zp.write_bytes(request.get_data())
        with zipfile.ZipFile(zp) as z: z.extractall(td/'x')
        meta=json.loads((td/'x'/'vehicle.json').read_text(encoding='utf-8'))
        c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
        if r:
            vid=r['id']
            for old in c.execute('select path from docs where vehicle_id=?',(vid,)).fetchall(): Path(old['path']).unlink(missing_ok=True)
            c.execute('delete from docs where vehicle_id=?',(vid,))
            c.execute('update vehicles set marka=?,model=?,rej=?,vin=?,przebieg=?,rok=?,updated=?,active=1 where id=?',(meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes'),vid))
        else:
            cur=c.execute('insert into vehicles(portal_id,marka,model,rej,vin,przebieg,rok,updated,active) values(?,?,?,?,?,?,?,?,1)',(pid,meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes'))); vid=cur.lastrowid
        d=FILES/str(vid); shutil.rmtree(d,ignore_errors=True); d.mkdir(parents=True,exist_ok=True)
        for folder,kind in {'ZDJECIA':'photo','OPIS':'opis','WYCENA':'wycena','DIAG':'raport'}.items():
            src=td/'x'/folder
            if src.is_dir():
                for f in src.iterdir():
                    if f.is_file():
                        dst=d/(secrets.token_hex(4)+'_'+safe(f.name)); shutil.copy2(f,dst); c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,f.name,str(dst)))
        c.commit(); c.close(); return jsonify(ok=True,id=pid)
    except Exception as ex: return jsonify(error=str(ex)),400
    finally: shutil.rmtree(td,ignore_errors=True)
