import os, json, sqlite3, secrets, hashlib, hmac, zipfile, tempfile, shutil, subprocess
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
    CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,portal_id TEXT UNIQUE,marka TEXT,model TEXT,rej TEXT,vin TEXT,przebieg TEXT,rok TEXT,updated TEXT,active INTEGER DEFAULT 1,show_opis INTEGER DEFAULT 1,show_wycena INTEGER DEFAULT 1,show_raport INTEGER DEFAULT 1,show_wycena_ai INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY,vehicle_id INTEGER,kind TEXT,name TEXT,path TEXT);
    ''')
    cols={r[1] for r in c.execute('pragma table_info(vehicles)').fetchall()}
    for col in ('show_opis','show_wycena','show_raport','show_wycena_ai'):
        if col not in cols: c.execute(f'alter table vehicles add column {col} INTEGER DEFAULT 1')
    if not c.execute('select 1 from users where login=?',(ADMIN_USER,)).fetchone():
        c.execute('insert into users(login,pass,role) values(?,?,?)',(ADMIN_USER,ph(ADMIN_PASS),'admin'))
    c.commit(); c.close()
init_db()

def api_ok(): return hmac.compare_digest(request.headers.get('X-AWM-Key',''), API_KEY)
def safe(n): return ''.join(ch for ch in Path(n).name if ch.isalnum() or ch in ' ._-()[]')[:160] or 'plik'
def vdict(r):
    return {'id':r['portal_id'] or str(r['id']),'marka':r['marka'],'model':r['model'],'rejestracja':r['rej'],'rej':r['rej'],'vin':r['vin'],'przebieg':r['przebieg'],'rok':r['rok'],'aktualizacja':r['updated'],'updated':r['updated'],'active':bool(r['active']),'show_opis':bool(r['show_opis']),'show_wycena':bool(r['show_wycena']),'show_raport':bool(r['show_raport']),'show_wycena_ai':bool(r['show_wycena_ai'])}

HTML = r'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AWM Portal</title><style>
*{box-sizing:border-box}html,body{min-height:100%}body{margin:0;font:14px "Segoe UI",Arial,sans-serif;color:#14241e;background:#eef5f2}.top{height:142px;color:#fff;display:flex;align-items:center;padding:0 4.5%;position:relative;overflow:hidden;background:linear-gradient(90deg,#003c2c 0%,#004c37 34%,#00533b 100%);box-shadow:0 5px 18px #063b2b22}.top:before{content:"";position:absolute;inset:0 31% 0 34%;background-image:linear-gradient(90deg,#004633 0%,transparent 22%,transparent 78%,#005039 100%),url("data:image/jpeg;base64,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");background-size:cover;background-position:center;opacity:.78}.brandbox,.slogan,.who{position:relative;z-index:2}.brand{font-size:36px;font-weight:950;letter-spacing:.3px}.brand b{color:#22d17d}.sub{font-size:15px;opacity:.88;margin-top:5px}.slogan{margin-left:auto;margin-right:60px;font-family:Georgia,serif;font-style:italic;font-size:22px;line-height:1.05;text-align:center;transform:rotate(-2deg)}.slogan:after{content:"";display:block;width:82px;height:3px;background:#16d878;margin:7px auto 0;transform:skew(-24deg)}.who{display:flex;align-items:center;gap:12px;font-weight:700}.status{color:#20dd83}.avatar{width:42px;height:42px;border-radius:50%;background:#fff;color:#08704d;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:17px}.wrap{max-width:1600px;margin:auto;padding:20px 34px 60px;position:relative}.wrap:before{content:"";position:fixed;z-index:-2;inset:142px 0 0;background:linear-gradient(#f7faf9dd,#edf5f2e8),radial-gradient(circle at 20% 20%,#fff 0,#eaf3ef 45%,#dceae4 100%)}.watermark{position:fixed;z-index:-1;left:50%;top:73%;transform:translate(-50%,-50%);width:min(760px,62vw);opacity:.065;pointer-events:none}.watermark .car{height:115px;border:12px solid #174c3b;border-color:#174c3b transparent transparent transparent;border-radius:55% 55% 0 0;transform:skew(-12deg);margin:0 80px -25px}.watermark .awm{font-size:min(16vw,220px);line-height:.78;font-weight:950;letter-spacing:-12px;color:#174c3b;text-align:center}.watermark .wm-sub{text-align:center;font-size:28px;font-weight:700;color:#174c3b;letter-spacing:1px}.card,.row,.stat{background:#fff;border:1px solid #dce7e2;box-shadow:0 8px 24px #0a3d2b12}.login{max-width:430px;margin:8vh auto;padding:30px;border-radius:18px}.login input,.search{width:100%;padding:15px 18px;border:1px solid #cbd8d3;border-radius:12px;background:#fff;font-size:15px;outline:none}.login input{margin:7px 0}.btn{border:0;border-radius:12px;padding:14px 22px;font-weight:800;cursor:pointer;background:#0a9a57;color:#fff;font-size:14px}.ghost{background:#edf4f1;color:#17352a}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-bottom:24px}.stat{border-radius:16px;padding:18px 22px;display:flex;gap:16px;align-items:center;min-height:96px}.ico{width:56px;height:56px;border-radius:15px;background:#edf7f3;display:flex;align-items:center;justify-content:center;font-size:28px}.stat:nth-child(3) .ico{background:#fff6df}.stat strong{font-size:26px}.stat span{display:block;color:#62766e;font-weight:800;margin-top:4px;font-size:13px}.toolbar{display:grid;grid-template-columns:1fr auto auto;gap:12px;margin-bottom:22px}.searchbox{position:relative}.searchbox:before{content:"⌕";position:absolute;left:16px;top:8px;font-size:31px;color:#0d2019}.search{padding-left:52px;height:58px;box-shadow:0 3px 14px #0a3d2b0c}.searchbtn{min-width:135px;font-size:16px}.row{display:grid;grid-template-columns:190px minmax(275px,1.05fr) minmax(320px,.95fr);gap:11px;align-items:center;padding:8px 10px;border-radius:11px;margin-bottom:9px}.picwrap{position:relative}.pic{width:180px;height:110px;object-fit:cover;border-radius:12px;background:#e7eeeb;cursor:zoom-in}.photocount{position:absolute;left:12px;bottom:12px;background:#183c32dd;color:#fff;border-radius:9px;padding:7px 10px;font-weight:800}.vtitle{display:flex;align-items:center;gap:14px;flex-wrap:wrap}.vtitle b{font-size:18px}.badge{background:#dff7e9;color:#0b9b56;border-radius:18px;padding:8px 13px;font-weight:900}.details{display:grid;grid-template-columns:repeat(4,minmax(72px,1fr));gap:7px;margin-top:9px}.label{color:#6d7d76;font-size:12px}.val{font-weight:800;margin-top:3px;word-break:break-word}.tags{display:flex;gap:9px;margin-top:20px}.tag{background:#edf3f1;border-radius:10px;padding:9px 14px;font-size:12px;font-weight:800;color:#3b554c}.actions{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:stretch}.a{padding:16px 10px;border-radius:13px;min-height:112px;display:flex;align-items:center;justify-content:center;text-align:center;box-shadow:0 7px 15px #0002;color:#fff;text-decoration:none;font-weight:900;font-size:13px;line-height:1.35;background:linear-gradient(#278ef1,#1168c7)}.docempty{background:#e6ece9!important;color:#6f7e77!important;box-shadow:none!important;border:1px dashed #b9c7c1!important;cursor:default}.docempty small{font-size:9px;font-weight:700}.green{background:linear-gradient(#12b967,#087c45)}.dark{background:linear-gradient(#28443c,#142a24)}.gold{background:linear-gradient(#f2b40f,#c47d00)}.muted{color:#6d7d76}.hidden{display:none}.empty{padding:58px;text-align:center;border-radius:18px}.aimodal{display:none;position:fixed;z-index:130;inset:0;background:#000b;padding:2vh 2vw;overflow:auto}.aimodal.on{display:block}.aipanel{max-width:1420px;margin:auto;background:#f7faf8;border-radius:16px;min-height:92vh;padding:18px;box-shadow:0 18px 60px #0005}.aihead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.aihead h2{margin:0;font-size:27px}.aihead h2 span{color:#0b8c4a}.aiclose{border:0;border-radius:10px;padding:8px 13px;font-size:22px;cursor:pointer}.aigrid{display:grid;grid-template-columns:280px 1fr;gap:16px}.aiveh,.aibox{background:white;border:1px solid #dbe7e1;border-radius:12px;padding:14px}.aiveh img{width:100%;height:170px;object-fit:cover;border-radius:9px;background:#e9efec}.aiveh h3{font-size:22px;margin:12px 0 4px}.aikv{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}.aikv div:nth-child(odd){color:#65756e}.aikv div:nth-child(even){font-weight:800}.aicontent{display:grid;gap:12px}.aimetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.aimetric{background:white;border:1px solid #dbe7e1;border-radius:12px;padding:16px}.aimetric b{display:block;font-size:24px;margin-top:8px}.aimetric.red{background:#fff3f1;color:#c52218}.aivalue{background:#eaf8ef;border:1px solid #c7ead3;border-radius:12px;padding:18px;display:flex;justify-content:space-between;align-items:center}.aivalue strong{font-size:35px}.aibodygrid{display:grid;grid-template-columns:1.25fr .75fr;gap:12px}.aifact{padding:9px 0;border-bottom:1px solid #e4ece8;display:flex;justify-content:space-between}.aiplaceholder{background:#f1f5f3;border:1px dashed #b9cbc2;border-radius:10px;padding:16px;color:#60726a;line-height:1.5}.aibadge{background:#dff4e7;color:#087c45;border-radius:20px;padding:5px 10px;font-weight:800;font-size:12px}@media(max-width:900px){.aigrid,.aibodygrid{grid-template-columns:1fr}.aimetrics{grid-template-columns:repeat(2,1fr)}}.docmodal{display:none;position:fixed;z-index:120;inset:0;background:#000b;padding:3vh 3vw;align-items:center;justify-content:center}.docmodal.on{display:flex}.docbox{width:min(1200px,94vw);height:92vh;background:#fff;border-radius:14px;overflow:hidden;display:flex;flex-direction:column}.dochead{min-height:58px;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #dce7e2}.dochead>div{display:flex;gap:8px;align-items:center}.docdownload,.docclose{border:0;border-radius:9px;padding:9px 13px;background:#edf4f1;color:#17352a;text-decoration:none;font-weight:800;cursor:pointer}.docclose{font-size:22px;padding:5px 12px}.docbox iframe{width:100%;flex:1;border:0;background:#f3f5f4}.docfallback{padding:7px 14px;font-size:12px;color:#6d7d76;text-align:center}.modal{display:none;position:fixed;z-index:99;inset:0;background:#000d;align-items:center;justify-content:center}.modal.on{display:flex}.modal img{max-width:92vw;max-height:90vh;object-fit:contain;border-radius:8px}.nav{position:fixed;top:50%;font-size:48px;color:#fff;cursor:pointer;padding:20px;user-select:none}.prev{left:2vw}.next{right:2vw}.close{position:fixed;right:3vw;top:2vh;color:#fff;font-size:38px;cursor:pointer}@media(max-width:1150px){.row{grid-template-columns:240px 1fr}.actions{grid-column:1/-1}.pic{width:230px}.details{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.top{height:auto;min-height:120px}.top:before,.slogan{display:none}.brand{font-size:29px}.stats{grid-template-columns:repeat(2,1fr)}.toolbar{grid-template-columns:1fr auto}.toolbar .filterbtn{display:none}.row{grid-template-columns:1fr}.pic{width:100%;height:220px}.actions{grid-template-columns:repeat(2,1fr)}.details{grid-template-columns:repeat(2,1fr)}}

/* User appearance controls */
body{font-size:calc(14px * var(--ui-scale,1))}.vehicle{transform-origin:top left}.compact .vehicle{padding:12px 14px;margin-bottom:10px}.compact .vehicle h2{font-size:20px}.largecards .vehicle{padding:28px;margin-bottom:24px}.bw{filter:grayscale(1)}.highcontrast{filter:contrast(1.22)}
.appearance-head{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin:0 0 8px;color:#62766e;font-size:12px;font-weight:700}.gearbtn{width:38px;height:38px;border:1px solid #bfd0c9;background:#fff;border-radius:9px;font-size:20px;cursor:pointer;color:#19352c}.appearance-panel{display:none;background:#fff;border:1px solid #d3dfda;border-radius:12px;padding:12px 14px;margin:0 0 14px;box-shadow:0 4px 16px #0a3d2b12}.appearance-panel.open{display:block}.appearance{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.appearance select,.appearance button{height:36px;border:1px solid #bfd0c9;background:#fff;border-radius:8px;padding:0 10px;color:#19352c}.appearance label{font-size:12px;font-weight:700}.darkmode{background:#18201e;color:#eef6f2}.darkmode .card,.darkmode .vehicle,.darkmode .stat,.darkmode .toolbar{background:#26312e;color:#eef6f2}.compact .row{grid-template-columns:112px minmax(185px,.95fr) minmax(220px,.9fr);gap:6px;padding:5px 7px;margin-bottom:6px;border-radius:8px;min-height:0}.compact .pic{width:108px;height:68px;border-radius:6px}.compact .photocount{left:4px;bottom:4px;padding:2px 4px;font-size:8px}.compact .vtitle{gap:4px}.compact .vtitle b{font-size:12px}.compact .badge{padding:2px 5px;font-size:7px}.compact .details{gap:3px;margin-top:4px}.compact .label{font-size:7px}.compact .val{font-size:9px}.compact .tags{margin-top:4px;gap:3px}.compact .tag{padding:2px 5px;font-size:7px}.compact .actions{gap:3px}.compact .a{min-height:34px;padding:3px;font-size:7px;line-height:1.05}.largecards .row{grid-template-columns:225px minmax(315px,1.1fr) minmax(365px,1fr);gap:14px;padding:9px 11px;margin-bottom:10px;border-radius:12px}.largecards .pic{width:215px;height:130px}.largecards .vtitle b{font-size:20px}.largecards .details{gap:9px;margin-top:11px}.tiles #list{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;align-items:start}.tiles .row{display:flex;flex-direction:column;align-items:stretch;gap:8px;margin:0;padding:10px;border-radius:12px;min-width:0}.tiles .picwrap{width:100%}.tiles .pic{width:100%;height:145px}.tiles .vtitle{gap:6px}.tiles .vtitle b{font-size:17px}.tiles .badge{padding:4px 7px;font-size:9px}.tiles .details{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:8px}.tiles .tags{margin-top:8px;gap:5px;flex-wrap:wrap}.tiles .tag{padding:5px 7px;font-size:9px}.tiles .actions{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.tiles .a{min-height:48px;padding:6px;font-size:9px;line-height:1.15}.tiles-small #list{grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.tiles-small .pic{height:105px}.tiles-small .row{padding:7px;gap:5px}.tiles-small .vtitle b{font-size:14px}.tiles-small .details{gap:4px;margin-top:5px}.tiles-small .actions{gap:4px}.tiles-small .a{min-height:40px;padding:4px;font-size:8px}.tiles-large #list{grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:16px}.tiles-large .pic{height:190px}.tiles-large .row{padding:14px;gap:11px}.tiles-large .vtitle b{font-size:20px}.tiles-large .a{min-height:58px;font-size:10px}@media(max-width:760px){.tiles #list{grid-template-columns:1fr}}

.tile-bold #list{font-weight:700}.tile-italic #list{font-style:italic}.tile-left #list{text-align:left}.tile-center #list{text-align:center}.tile-right #list{text-align:right}.tile-left #list .row *{text-align:left}.tile-center #list .row *{text-align:center}.tile-right #list .row *{text-align:right}.tile-size-wrap{display:none;align-items:center;gap:8px}.tiles .tile-size-wrap{display:contents}.tile-settings{display:flex;gap:7px;align-items:center;flex-wrap:wrap;width:100%;padding:8px 0;border-top:1px solid #dce7e2;margin-top:3px}.tile-settings-title{font-weight:800;margin-right:4px}.tile-settings.open{display:flex}.tile-settings button{height:34px;border:1px solid #bfd0c9;background:#fff;border-radius:7px;padding:0 10px}.tile-settings button.on{outline:2px solid #1a8f63}

/* AWM compact vehicle action tiles */
.actions{gap:5px!important;justify-content:flex-end!important}
.actions .a{width:100px!important;min-width:100px!important;max-width:100px!important;min-height:30px!important;height:30px!important;padding:2px 5px!important;border-radius:8px!important;font-size:8px!important;line-height:8px!important;box-shadow:0 2px 4px #0003!important}
.actions .a small{font-size:6px!important;line-height:6px!important}
@media(max-width:700px){
 .actions{gap:4px!important;display:grid!important;grid-template-columns:repeat(2,78px)!important;justify-content:start!important}
 .actions .a{width:78px!important;min-width:78px!important;max-width:78px!important;height:28px!important;min-height:28px!important;font-size:7px!important;line-height:7px!important;border-radius:7px!important}
}

/* AWM compact top statistics */
.stats{gap:14px!important;margin-bottom:12px!important}
.stat{min-height:58px!important;height:58px!important;padding:8px 16px!important;border-radius:12px!important}
.stat .ico{width:36px!important;height:36px!important;border-radius:10px!important;font-size:19px!important}
.stat strong{font-size:20px!important;line-height:20px!important}
.stat span{font-size:9px!important;margin-top:3px!important}
@media(max-width:700px){
 .stats{gap:7px!important;grid-template-columns:repeat(2,1fr)!important}
 .stat{height:52px!important;min-height:52px!important;padding:6px 9px!important}
 .stat .ico{width:32px!important;height:32px!important;font-size:16px!important}
 .stat strong{font-size:17px!important}
 .stat span{font-size:8px!important}
}

/* AWM softer action tiles */
.actions .a{filter:saturate(.55)!important;box-shadow:0 1px 3px #0002!important;border-color:#9aa9a3!important}
.actions .a.blue{background:#75a9cf!important}
.actions .a.dark{background:#60736d!important}
.actions .a.green{background:#66a98a!important}
.actions .a.orange{background:#d6ad54!important}
.actions .a.disabled{background:#e7eeeb!important;color:#71807a!important;filter:saturate(.3)!important}

/* AWM text-only action tiles */
.actions .a{font-size:10px!important;font-weight:800!important;line-height:1!important;letter-spacing:.15px!important;display:flex!important;align-items:center!important;justify-content:center!important}
.actions .a br{display:none!important}
.actions .a .ico,.actions .a .icon,.actions .a i,.actions .a svg{display:none!important}

/* AWM force text-only vehicle buttons */
.actions .a::before,.actions .a::after{content:none!important;display:none!important}
.actions .a{background-image:none!important;text-indent:0!important;font-size:10px!important;font-weight:800!important;line-height:1!important;text-align:center!important}
</style></head><body>
<header class="top"><div class="brandbox"><div class="brand">PRZEGLĄD <b>AWM</b></div><div class="sub">PORTAL RZECZOZNAWCÓW</div></div><div class="slogan">Diagnostyka<br>Wycena<br>Pewność</div><div class="who" id="who"><span class="status">● ONLINE</span><span>AWM</span><span class="avatar">W</span></div></header>
<div class="watermark"><div class="car"></div><div class="awm">AWM</div><div class="wm-sub">DIAGNOSTYKA POJAZDÓW</div></div>
<main class="wrap"><section id="login" class="card login"><h2>Logowanie do AWM Portal</h2><input id="lu" placeholder="Login"><input id="lp" type="password" placeholder="Hasło"><button class="btn" onclick="login()">ZALOGUJ</button><p id="err"></p></section><section id="app" class="hidden"><div class="appearance-head"><button type="button" class="gearbtn" onclick="toggleAppearance()">⚙</button><span>Ustawienia wyglądu</span></div><div id="appearancePanel" class="appearance-panel"><div class="appearance"><label>Rozmiar kart</label><select id="cardSize" onchange="applyAppearance()"><option value="">Normalne</option><option value="compact">Małe</option><option value="largecards">Duże</option></select><label>Widok pojazdów</label><select id="layoutMode" onchange="applyAppearance()"><option value="">Lista — karty poziome</option><option value="tiles">Kafelki — obok siebie</option></select><span id="tileSizeWrap" class="tile-size-wrap"><label>Wielkość kafelków</label><select id="tileSize" onchange="applyAppearance()"><option value="tiles-small">Małe — więcej w rzędzie</option><option value="" selected>Normalne</option><option value="tiles-large">Duże — mniej w rzędzie</option></select></span><label>Czcionka</label><select id="fontSize" onchange="applyAppearance()"><option value="0.9">Mała</option><option value="1" selected>Normalna</option><option value="1.15">Duża</option></select><label>Kontrast</label><select id="theme" onchange="applyAppearance()"><option value="">Jasny</option><option value="darkmode">Ciemny</option><option value="bw">Czarno-biały</option><option value="highcontrast">Wysoki kontrast</option></select><div class="tile-settings open"><span class="tile-settings-title">Tekst kart / kafelków</span><button id="tbBold" onclick="setTileOpt('bold')">Pogrubiona</button><button id="tbItalic" onclick="setTileOpt('italic')">Kursywa</button><button onclick="setAlign('left')">Do lewej</button><button onclick="setAlign('center')">Wyśrodkuj</button><button onclick="setAlign('right')">Do prawej</button></div></div></div><div class="stats"><div class="stat"><div class="ico">▣</div><div><strong id="sc">0</strong><span>POJAZDÓW W PORTALU</span></div></div><div class="stat"><div class="ico">▤</div><div><strong id="sd">0</strong><span>RAPORTÓW DIAG</span></div></div><div class="stat"><div class="ico">$</div><div><strong id="sa">0</strong><span>WYCEN AI</span></div></div><div class="stat"><div class="ico">▧</div><div><strong id="sp">0</strong><span>ZDJĘĆ</span></div></div></div><div class="toolbar"><div class="searchbox"><input id="q" class="search" placeholder="Szukaj: marka, model, VIN, rejestracja, klient..."></div><button class="btn searchbtn" onclick="render()">⌕ &nbsp;Szukaj</button><button class="btn ghost filterbtn" onclick="logout()">Wyloguj</button></div><div id="list"></div></section></main><div id="aiModal" class="aimodal"><div class="aipanel"><div class="aihead"><h2>▣ WYCENA AI <span>AWM</span> <small class="aibadge">Wersja beta</small></h2><button class="aiclose" onclick="closeAI()">×</button></div><div id="aiBody"></div></div></div><div id="docModal" class="docmodal"><div class="docbox"><div class="dochead"><strong id="docTitle">Podgląd dokumentu</strong><div><a id="docDownload" class="docdownload">Pobierz</a><button type="button" class="docclose" onclick="closeDoc()">×</button></div></div><iframe id="docFrame" title="Podgląd dokumentu"></iframe><div class="docfallback">PDF i pliki obsługiwane przez przeglądarkę otwierają się tutaj. Dla pozostałych użyj „Pobierz”.</div></div></div><div id=modal class=modal onclick=closePic(event)><span class=close onclick=closePic(event)>×</span><span class="nav prev" onclick=stepPic(-1,event)>‹</span><img id=bigpic><span class="nav next" onclick=stepPic(1,event)>›</span></div>
<script>
function toggleAppearance(){document.getElementById('appearancePanel')?.classList.toggle('open')}let tileCfg={bold:false,italic:false,align:'left'};function toggleTileSettings(){document.getElementById('tileSettings')?.classList.toggle('open')}function applyTileCfg(){document.body.classList.toggle('tile-bold',!!tileCfg.bold);document.body.classList.toggle('tile-italic',!!tileCfg.italic);document.body.classList.remove('tile-left','tile-center','tile-right');document.body.classList.add('tile-'+(tileCfg.align||'left'));document.getElementById('tbBold')?.classList.toggle('on',!!tileCfg.bold);document.getElementById('tbItalic')?.classList.toggle('on',!!tileCfg.italic);localStorage.setItem('awmTileCfg',JSON.stringify(tileCfg))}function setTileOpt(k){tileCfg[k]=!tileCfg[k];applyTileCfg()}function setAlign(a){tileCfg.align=a;applyTileCfg()}function restoreTileCfg(){try{tileCfg=Object.assign(tileCfg,JSON.parse(localStorage.getItem('awmTileCfg')||'{}'))}catch(e){}applyTileCfg()}function applyAppearance(){let cs=document.getElementById('cardSize')?.value||'';let lm=document.getElementById('layoutMode')?.value||'';let ts=document.getElementById('tileSize')?.value||'';let fs=document.getElementById('fontSize')?.value||'1';let th=document.getElementById('theme')?.value||'';document.body.classList.remove('compact','largecards','tiles','tiles-small','tiles-large','darkmode','bw','highcontrast');if(lm==='tiles'){document.body.classList.add('tiles');if(ts)document.body.classList.add(ts)}else if(cs)document.body.classList.add(cs);let tw=document.getElementById('tileSizeWrap');if(tw)tw.style.display=lm==='tiles'?'contents':'none';let csEl=document.getElementById('cardSize');if(csEl)csEl.disabled=lm==='tiles';if(th)document.body.classList.add(th);document.documentElement.style.setProperty('--ui-scale',fs);localStorage.setItem('awmAppearance',JSON.stringify({cs,lm,ts,fs,th}))}function restoreAppearance(){try{let x=JSON.parse(localStorage.getItem('awmAppearance')||'{}');if(x.cs==='tiles'){x.lm='tiles';x.cs=''}if(x.cs!==undefined&&document.getElementById('cardSize'))document.getElementById('cardSize').value=x.cs;if(x.lm&&document.getElementById('layoutMode'))document.getElementById('layoutMode').value=x.lm;if(x.ts!==undefined&&document.getElementById('tileSize'))document.getElementById('tileSize').value=x.ts;if(x.fs&&document.getElementById('fontSize'))document.getElementById('fontSize').value=x.fs;if(x.th&&document.getElementById('theme'))document.getElementById('theme').value=x.th;applyAppearance()}catch(e){}}document.addEventListener('DOMContentLoaded',()=>{restoreAppearance();restoreTileCfg()});
let V=[];const $=x=>document.getElementById(x);async function j(u,o){let r=await fetch(u,o);let x={};try{x=await r.json()}catch(e){}return[r,x]}
async function boot(){let[r,x]=await j('/api/me');if(x.user){$('login').classList.add('hidden');$('app').classList.remove('hidden');$('who').innerHTML='<span class="status">● ONLINE</span><span>'+e(x.user.login)+'</span><span class="avatar">'+e((x.user.login||'W')[0].toUpperCase())+'</span>';load()}}
async function login(){let[r,x]=await j('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:$('lu').value,password:$('lp').value})});if(r.ok)location.reload();else $('err').textContent=x.error||'Błąd logowania'}
async function logout(){await fetch('/api/logout',{method:'POST'});location.reload()}
async function load(){let[r,x]=await j('/api/vehicles');V=Array.isArray(x)?x:[];$('sc').textContent=V.length;$('sd').textContent=V.filter(v=>v.docs.some(d=>d.kind==='raport')).length;$('sa').textContent=V.filter(v=>v.docs.some(d=>d.kind==='wycena_ai')).length;$('sp').textContent=V.reduce((n,v)=>n+(v.photos||[]).length,0);render()}
function e(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function render(){let s=($('q').value||'').toLowerCase();let a=V.filter(v=>JSON.stringify(v).toLowerCase().includes(s));$('list').innerHTML=a.map(v=>{let b=k=>{if(k==='wycena_ai')return `<button class="a gold" onclick="openAI('${e(v.id)}')">WYCENA AI</button>`;let d=v.docs.find(d=>d.kind===k);let pv=(k==='opis'?v.docs.find(x=>x.kind==='opis_pdf'):null);if(!d)return `<div class="a docempty">${k==='opis'?'▤<br>OPIS':k==='raport'?'🔧<br>RAPORT DIAG':'WYCENA'}<br><small>BRAK DOKUMENTU</small></div>`;return `<button class="a ${k==='wycena'?'green':k==='raport'?'dark':''}" onclick="openDoc(${pv?pv.id:d.id},'${e(d.name||k)}',${d.id})">${k==='opis'?'▤<br>OPIS':k==='wycena'?'WYCENA':'🔧<br>RAPORT DIAG'}</button>`};let pc=(v.photos||[]).length;return `<div class="row"><div class="picwrap">${v.photo?`<img class="pic" src="/file/${v.photo}" onclick="openPic('${e(v.id)}')" title="Kliknij, aby powiększyć">`:'<div class="pic"></div>'}${pc?`<span class="photocount">▧ ${pc}</span>`:''}</div><div><div class="vtitle"><b>${e(v.marka)} ${e(v.model)}</b><span class="badge">↗ UDOSTĘPNIONY</span></div><div class="details"><div><div class="label">Rok</div><div class="val">${e(v.rok||'—')}</div></div><div><div class="label">Rejestracja</div><div class="val">${e(v.rej||'—')}</div></div><div><div class="label">VIN</div><div class="val">${e(v.vin||'—')}</div></div><div><div class="label">Przebieg</div><div class="val">${e(v.przebieg||'—')} km</div></div></div><div class="tags"><span class="tag">SAMOCHÓD OSOBOWY</span><span class="tag">AWM</span></div></div><div class="actions">${b('opis')}${b('raport')}${b('wycena')}${b('wycena_ai')}</div></div>`}).join('')||'<div class="card empty">Brak udostępnionych pojazdów.</div>'}
async function openAI(id){let v=V.find(x=>String(x.id)===String(id));if(!v)return;let img=v.photo?'/file/'+v.photo:'';let has=k=>v.docs.some(d=>d.kind===k);let aid=v.docs.find(d=>d.kind==='wycena_ai');document.getElementById('aiBody').innerHTML=`<div class="aigrid"><aside class="aiveh">${img?`<img src="${img}">`:'<div style="height:170px;background:#e9efec;border-radius:9px"></div>'}<h3>${e(v.marka)} ${e(v.model)}</h3><div class="aikv"><div>VIN</div><div>${e(v.vin||'—')}</div><div>Rejestracja</div><div>${e(v.rej||'—')}</div><div>Rok</div><div>${e(v.rok||'—')}</div><div>Przebieg</div><div>${e(v.przebieg||'—')} km</div></div></aside><section class="aicontent"><div class="aimetrics"><div class="aimetric">Średnia cena rynkowa<b>—</b><small>do pobrania z ofert rynkowych</small></div><div class="aimetric red">Korekta za przebieg<b>—</b><small>po analizie rynku</small></div><div class="aimetric red">Korekta za stan<b>—</b><small>na podstawie dokumentów</small></div><div class="aimetric">Koszty napraw<b>—</b><small>z raportów AWM</small></div></div><div class="aivalue"><div><b>SZACOWANA WARTOŚĆ POJAZDU</b><br><small>Wynik pojawi się po uruchomieniu silnika wyceny</small></div><strong>— zł</strong></div><div class="aibodygrid"><div class="aibox"><h3>Dane dostępne do analizy</h3><div class="aifact"><span>Opis / kontrola pojazdu</span><b>${has('opis')?'✓ dostępny':'— brak'}</b></div><div class="aifact"><span>Raport diagnostyczny</span><b>${has('raport')?'✓ dostępny':'— brak'}</b></div><div class="aifact"><span>Wycena / koszty</span><b>${has('wycena')?'✓ dostępna':'— brak'}</b></div><div class="aifact"><span>Zdjęcia</span><b>${(v.photos||[]).length} szt.</b></div></div><div class="aibox"><h3>WYCENA AI AWM</h3><div class="aiplaceholder">Analiza pojazdu jest aktywna. AWM wykorzystuje dostępne dane pojazdu, OPIS, raport DIAG, wycenę i zdjęcia. Wartość rynkowa pojawi się dopiero po podłączeniu źródła aktualnych ofert — portal nie będzie zgadywał ceny.</div>${aid?`<button class="a gold" style="min-height:58px;margin-top:12px;width:100%" onclick="openDoc(${aid.id},'${e(aid.name||'Wycena AI')}')">OTWÓRZ ZAPISANĄ WYCENĘ AI</button>`:''}</div></div></section></div>`;document.getElementById('aiModal').classList.add('on')}function closeAI(){document.getElementById('aiModal').classList.remove('on')}
async function openDoc(id,name,downloadId){let url='/file/'+id;document.getElementById('docTitle').textContent=name||'Podgląd dokumentu';document.getElementById('docDownload').href='/file/'+(downloadId||id)+'?download=1';let frame=document.getElementById('docFrame');let low=String(name||'').toLowerCase();frame.src=low.endsWith('.pdf')?(url+'#page=1&zoom=page-width&view=FitH&toolbar=1'):low.match(/\.(png|jpg|jpeg|webp|gif)$/)?url:'/preview/'+id;document.getElementById('docModal').classList.add('on');try{frame.scrollTop=0;frame.contentWindow&&frame.contentWindow.scrollTo(0,0)}catch(e){}}function closeDoc(){document.getElementById('docModal').classList.remove('on');document.getElementById('docFrame').src='about:blank'}
let PV=[],PI=0;function openPic(id){let v=V.find(x=>String(x.id)===String(id));PV=(v&&v.photos)||[];if(!PV.length&&v&&v.photo)PV=[v.photo];PI=0;if(PV.length){$('bigpic').src='/file/'+PV[0];$('modal').classList.add('on')}}function stepPic(n,ev){if(ev)ev.stopPropagation();if(!PV.length)return;PI=(PI+n+PV.length)%PV.length;$('bigpic').src='/file/'+PV[PI]}function closePic(ev){if(ev&&ev.target&&ev.target.id==='bigpic')return;$('modal').classList.remove('on');$('bigpic').src=''}document.addEventListener('keydown',e=>{if(!$('modal').classList.contains('on'))return;if(e.key==='Escape')closePic();if(e.key==='ArrowLeft')stepPic(-1);if(e.key==='ArrowRight')stepPic(1)});$('q').oninput=render;boot();
</script></body></html>'''

@app.get('/')
def home(): return Response(HTML, mimetype='text/html')
@app.get('/health')
def health(): return jsonify(ok=True, version='5.3-v49-premium-ui')
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
        x=dict(r); ds=[dict(d) for d in c.execute('select id,kind,name from docs where vehicle_id=? order by id desc',(r['id'],))]; ds=[d for d in ds if d['kind'] not in ('opis','opis_pdf','wycena','raport','wycena_ai') or (d['kind']=='opis' and r['show_opis']) or (d['kind']=='wycena' and r['show_wycena']) or (d['kind']=='raport' and r['show_raport']) or (d['kind']=='wycena_ai' and r['show_wycena_ai'])]; seen=set(); clean=[]
        for d in ds:
            if d['kind'] in ('opis','wycena','raport','wycena_ai'):
                if d['kind'] in seen: continue
                seen.add(d['kind'])
            clean.append(d)
        ds=clean; x['docs']=ds; x['photos']=[d['id'] for d in ds if d['kind']=='photo']; x['photo']=next((d['id'] for d in ds if d['kind']=='thumb'),None) or next(iter(x['photos']),None); out.append(x)
    c.close(); return jsonify(out)
def _doc_path(r):
    if not r: return None
    p=Path(r['path']) if r['path'] else None
    if p and p.is_file(): return p
    # Recover stale DB paths. Older desktop builds could leave a DB row while the file
    # was saved under another generated prefix in the vehicle directory.
    d=FILES/str(r['vehicle_id'])
    if d.is_dir():
        want=safe(r['name']).lower()
        def norm(n):
            n=safe(n).lower()
            return n.split('_',1)[-1] if '_' in n else n
        files=[x for x in d.rglob('*') if x.is_file()]
        exact=[x for x in files if x.name.lower()==want or x.name.lower().endswith('_'+want) or norm(x.name)==want]
        if exact:
            q=max(exact,key=lambda x:x.stat().st_mtime)
            try:
                c=db(); c.execute('update docs set path=? where id=?',(str(q),r['id'])); c.commit(); c.close()
            except Exception: pass
            return q
    return None

@app.get('/api/doc-status/<int:i>')
def doc_status(i):
    if not session.get('user'): return jsonify(error='login'),401
    c=db(); r=c.execute('select * from docs where id=?',(i,)).fetchone(); c.close()
    p=_doc_path(r)
    return jsonify(ok=bool(p),id=i,name=(r['name'] if r else None),kind=(r['kind'] if r else None),size=(p.stat().st_size if p else 0))

@app.get('/preview/<int:i>')
def preview(i):
    if not session.get('user'): return jsonify(error='login'),401
    c=db(); r=c.execute('select * from docs where id=?',(i,)).fetchone(); c.close()
    p=_doc_path(r)
    if not r or not p: return Response('<!doctype html><meta charset="utf-8"><div style="font:16px Segoe UI;padding:30px">Nie znaleziono pliku dokumentu na serwerze. Wyślij dokument ponownie z programu AWM.</div>',status=404,mimetype='text/html')
    ext=p.suffix.lower()
    if ext in ('.pdf','.png','.jpg','.jpeg','.webp','.gif'):
        return send_file(p,as_attachment=False,download_name=r['name'])
    if ext=='.docx':
        try:
            from markupsafe import escape
            with zipfile.ZipFile(p) as z:
                xml=z.read('word/document.xml').decode('utf-8','ignore')
            import re
            xml=xml.replace('</w:p>','\\n').replace('</w:tr>','\\n')
            txt=re.sub(r'<[^>]+>','',xml)
            import html as _html
            txt=_html.unescape(txt)
            body='<br>'.join(str(escape(x)) for x in txt.splitlines() if x.strip())
            return Response(f'''<!doctype html><meta charset="utf-8"><style>body{{font-family:Segoe UI,Arial;background:#eef2f0;margin:0;padding:24px;color:#18251f}}.page{{background:white;max-width:900px;min-height:1000px;margin:auto;padding:55px 65px;box-shadow:0 3px 18px #0002;line-height:1.55}}</style><div class="page">{body}</div>''',mimetype='text/html')
        except Exception:
            pass
    from markupsafe import escape
    n=escape(r['name'])
    return Response(f'''<!doctype html><meta charset="utf-8"><style>body{{font-family:Segoe UI,Arial;background:#f3f5f4;display:grid;place-items:center;height:90vh}}.b{{background:white;padding:28px;border-radius:14px}}</style><div class="b"><h2>{n}</h2><p>Podgląd tego formatu nie jest dostępny. Użyj przycisku Pobierz.</p></div>''',mimetype='text/html')

@app.get('/file/<int:i>')
def file(i):
    if not session.get('user'): return jsonify(error='login'),401
    c=db(); r=c.execute('select * from docs where id=?',(i,)).fetchone(); c.close()
    p=_doc_path(r)
    if not r or not p: return jsonify(error='404'),404
    return send_file(p, as_attachment=request.args.get('download')=='1', download_name=r['name'])

@app.route('/api/admin/access', methods=['GET','POST'])
def admin_access():
    if not api_ok(): return jsonify(error='bad key'),403
    c=db()
    if request.method=='GET':
        r=c.execute('select id,login from users order by id limit 1').fetchone(); c.close()
        return jsonify(login=(r['login'] if r else ''))
    x=request.get_json(silent=True) or {}
    login_name=str(x.get('login','')).strip()
    password=str(x.get('password',''))
    if len(login_name)<3: c.close(); return jsonify(error='Login musi mieć co najmniej 3 znaki'),400
    if len(password)<6: c.close(); return jsonify(error='Hasło musi mieć co najmniej 6 znaków'),400
    r=c.execute('select id from users order by id limit 1').fetchone()
    if r:
        c.execute('update users set login=?,pass=? where id=?',(login_name,ph(password),r['id']))
        c.execute('delete from users where id<>?',(r['id'],))
    else:
        c.execute('insert into users(login,pass,role) values(?,?,?)',(login_name,ph(password),'admin'))
    c.commit(); c.close()
    return jsonify(ok=True,login=login_name)

@app.get('/api/admin/vehicles')
def admin_vehicles():
    if not api_ok(): return jsonify(error='bad key'),403
    c=db(); out=[]
    for r in c.execute('select * from vehicles order by updated desc'):
        x=vdict(r); kinds={d['kind'] for d in c.execute('select kind from docs where vehicle_id=?',(r['id'],)).fetchall()}; x.update(has_opis='opis' in kinds,has_wycena='wycena' in kinds,has_raport='raport' in kinds,has_wycena_ai='wycena_ai' in kinds); out.append(x)
    c.close(); return jsonify(vehicles=out)

@app.post('/api/admin/vehicles/<path:pid>/visibility')
def visibility(pid):
    if not api_ok(): return jsonify(error='bad key'),403
    x=request.get_json(silent=True) or {}; c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
    if not r: c.close(); return jsonify(error='vehicle not found'),404
    vals=[1 if x.get(k,False) else 0 for k in ('opis','wycena','raport','wycena_ai')]
    c.execute('update vehicles set show_opis=?,show_wycena=?,show_raport=?,show_wycena_ai=? where id=?',(*vals,r['id'])); c.commit(); c.close(); return jsonify(ok=True)

@app.post('/api/admin/vehicles/<path:pid>/document/<kind>')
def add_document(pid,kind):
    if not api_ok(): return jsonify(error='bad key'),403
    if kind not in ('opis','opis_pdf','wycena','raport','wycena_ai'): return jsonify(error='bad kind'),400
    c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
    if not r: c.close(); return jsonify(error='vehicle not found'),404
    vid=r['id']; name=safe(request.args.get('name') or ('dokument_'+kind))
    data=request.get_data()
    if not data or len(data)<32: c.close(); return jsonify(error='empty document'),400
    d=FILES/str(vid); d.mkdir(parents=True,exist_ok=True)
    dst=d/(secrets.token_hex(4)+'_'+name); dst.write_bytes(data)
    preview=None
    if kind=='opis' and dst.suffix.lower()=='.docx':
        td=Path(tempfile.mkdtemp(dir=str(d)))
        try:
            office=shutil.which('libreoffice') or shutil.which('soffice') or '/usr/bin/libreoffice'
            profile=td/'profile'; profile.mkdir()
            env=os.environ.copy(); env['HOME']=str(td)
            rr=subprocess.run([office,'-env:UserInstallation=file://'+str(profile),'--headless','--convert-to','pdf','--outdir',str(td),str(dst)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,env=env)
            made=td/(dst.stem+'.pdf')
            if rr.returncode!=0 or not made.is_file() or made.stat().st_size<1000:
                msg=(rr.stderr or rr.stdout or b'').decode(errors='ignore')[-600:]
                dst.unlink(missing_ok=True); c.close(); return jsonify(error='server pdf conversion failed',detail=msg),500
            preview=d/(secrets.token_hex(4)+'_'+Path(name).stem+'.pdf'); shutil.copy2(made,preview)
        except Exception as ex:
            dst.unlink(missing_ok=True); c.close(); return jsonify(error='server pdf conversion unavailable',detail=str(ex)),500
        finally: shutil.rmtree(td,ignore_errors=True)
    for old in c.execute('select id,path from docs where vehicle_id=? and kind=?',(vid,kind)).fetchall():
        try: Path(old['path']).unlink(missing_ok=True)
        except: pass
    c.execute('delete from docs where vehicle_id=? and kind=?',(vid,kind))
    c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,name,str(dst)))
    preview_id=None
    if preview is not None:
        for old in c.execute("select id,path from docs where vehicle_id=? and kind='opis_pdf'",(vid,)).fetchall():
            try: Path(old['path']).unlink(missing_ok=True)
            except: pass
        c.execute("delete from docs where vehicle_id=? and kind='opis_pdf'",(vid,))
        cur=c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,'opis_pdf',preview.name,str(preview)))
        preview_id=cur.lastrowid
    c.execute('update vehicles set '+{'opis':'show_opis','opis_pdf':'show_opis','wycena':'show_wycena','raport':'show_raport','wycena_ai':'show_wycena_ai'}[kind]+'=1 where id=?',(vid,))
    c.commit(); c.close()
    return jsonify(ok=True,size=len(data),preview_generated=bool(preview),preview_id=preview_id)

@app.delete('/api/admin/vehicles/<path:pid>')
def expire(pid):
    # DELETE oznacza faktyczne usuniecie kopii z Portalu. AWM Cloud pozostaje nietkniety.
    if not api_ok(): return jsonify(error='bad key'),403
    c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
    if not r:
        c.close(); return jsonify(ok=True,deleted=False)
    vid=r['id']
    paths=[x['path'] for x in c.execute('select path from docs where vehicle_id=?',(vid,)).fetchall()]
    c.execute('delete from docs where vehicle_id=?',(vid,))
    c.execute('delete from vehicles where id=?',(vid,))
    c.commit(); c.close()
    for pp in paths:
        try: Path(pp).unlink(missing_ok=True)
        except Exception: pass
    shutil.rmtree(FILES/str(vid),ignore_errors=True)
    return jsonify(ok=True,deleted=True)
def _zip_request_to_temp(prefix):
    td=Path(tempfile.mkdtemp(prefix=prefix))
    zp=td/'p.zip'
    # Keep the original, known-working request.get_data() transport.
    zp.write_bytes(request.get_data())
    with zipfile.ZipFile(zp) as z:
        z.extractall(td/'x')
    return td

@app.route('/api/publish-auto', methods=['GET','HEAD','OPTIONS','POST'])
def publish_auto():
    if request.method != 'POST':
        return jsonify(ok=True, publish=True, endpoint='/api/publish-auto')
    if not api_ok(): return jsonify(error='bad key'),403
    pid=(request.args.get('id') or '').strip()
    if not pid: return jsonify(error='missing id'),400
    td=None
    try:
        td=_zip_request_to_temp('awm_auto_')
        meta=json.loads((td/'x'/'vehicle.json').read_text(encoding='utf-8'))
        c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
        if r:
            vid=r['id']
            # AUTO refreshes only photos/thumbs; documents remain untouched.
            olds=c.execute("select id,path from docs where vehicle_id=? and kind in ('photo','thumb')",(vid,)).fetchall()
            for old in olds:
                try: Path(old['path']).unlink(missing_ok=True)
                except Exception: pass
            c.execute("delete from docs where vehicle_id=? and kind in ('photo','thumb')",(vid,))
            c.execute('update vehicles set marka=?,model=?,rej=?,vin=?,przebieg=?,rok=?,updated=?,active=1 where id=?',
                      (meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),
                       meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes'),vid))
        else:
            cur=c.execute('insert into vehicles(portal_id,marka,model,rej,vin,przebieg,rok,updated,active) values(?,?,?,?,?,?,?,?,1)',
                          (pid,meta.get('marka',''),meta.get('model',''),meta.get('rejestracja',''),meta.get('vin',''),
                           meta.get('przebieg',''),meta.get('rok',''),datetime.now().isoformat(timespec='minutes')))
            vid=cur.lastrowid
        d=FILES/str(vid); d.mkdir(parents=True,exist_ok=True)
        counts={}
        for folder,kind in {'ZDJECIA':'photo','MINIATURY':'thumb'}.items():
            src=td/'x'/folder; n=0
            if src.is_dir():
                for f in src.iterdir():
                    if f.is_file():
                        dst=d/(secrets.token_hex(4)+'_'+safe(f.name)); shutil.copy2(f,dst)
                        c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,f.name,str(dst))); n+=1
            counts[kind]=n
        c.commit(); c.close()
        return jsonify(ok=True,id=pid,files=counts)
    except Exception as ex:
        return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)

@app.route('/api/publish-docs', methods=['GET','HEAD','OPTIONS','POST'])
def publish_docs():
    if request.method != 'POST':
        return jsonify(ok=True, publish=True, endpoint='/api/publish-docs')
    if not api_ok(): return jsonify(error='bad key'),403
    pid=(request.args.get('id') or '').strip()
    if not pid: return jsonify(error='missing id'),400
    td=None
    try:
        td=_zip_request_to_temp('awm_docs_')
        c=db(); r=c.execute('select id from vehicles where portal_id=?',(pid,)).fetchone()
        if not r: c.close(); return jsonify(error='vehicle not found - send AUTO first'),404
        vid=r['id']; d=FILES/str(vid); d.mkdir(parents=True,exist_ok=True)
        counts={}
        for folder,kind in {'OPIS':'opis','WYCENA':'wycena','DIAG':'raport'}.items():
            # Replace only this document type; AUTO/photos remain untouched.
            olds=c.execute('select id,path from docs where vehicle_id=? and kind=?',(vid,kind)).fetchall()
            for old in olds:
                try: Path(old['path']).unlink(missing_ok=True)
                except Exception: pass
            c.execute('delete from docs where vehicle_id=? and kind=?',(vid,kind))
            src=td/'x'/folder; files=[f for f in src.iterdir() if f.is_file()] if src.is_dir() else []
            if files: files=[max(files,key=lambda f:f.stat().st_mtime)]
            for f in files:
                dst=d/(secrets.token_hex(4)+'_'+safe(f.name)); shutil.copy2(f,dst)
                c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,f.name,str(dst)))
            counts[kind]=len(files)
        c.execute('update vehicles set updated=? where id=?',(datetime.now().isoformat(timespec='minutes'),vid))
        c.commit(); c.close()
        return jsonify(ok=True,id=pid,files=counts)
    except Exception as ex:
        return jsonify(error=str(ex)),400
    finally:
        if td: shutil.rmtree(td,ignore_errors=True)

@app.route('/api/publish', methods=['GET','HEAD','OPTIONS','POST'])
def publish():
    if request.method != 'POST':
        return jsonify(ok=True, publish=True, endpoint='/api/publish')
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
        for folder,kind in {'ZDJECIA':'photo','MINIATURY':'thumb','OPIS':'opis','WYCENA':'wycena','DIAG':'raport'}.items():
            src=td/'x'/folder
            if src.is_dir():
                files=[f for f in src.iterdir() if f.is_file()]
                if kind in ('opis','wycena','raport') and files:
                    files=[max(files,key=lambda f:f.stat().st_mtime)]
                for f in files:
                    dst=d/(secrets.token_hex(4)+'_'+safe(f.name)); shutil.copy2(f,dst); c.execute('insert into docs(vehicle_id,kind,name,path) values(?,?,?,?)',(vid,kind,f.name,str(dst)))
        c.commit()
        counts={k:c.execute('select count(*) n from docs where vehicle_id=? and kind=?',(vid,k)).fetchone()['n'] for k in ('photo','thumb','opis','wycena','raport')}
        c.close(); return jsonify(ok=True,id=pid,files=counts)
    except Exception as ex: return jsonify(error=str(ex)),400
    finally: shutil.rmtree(td,ignore_errors=True)

# Persistent Supabase backend (enabled only when configured on the host)
if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SECRET_KEY'):
    from supabase_backend import install_supabase
    install_supabase(app)

if __name__ == '__main__':
    port = int(os.getenv('PORT', '10000'))
    app.run(host='0.0.0.0', port=port, debug=False)
