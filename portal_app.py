import os, json, zipfile, shutil, tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string, redirect

app = Flask(__name__)

DATA = Path(os.environ.get("AWM_DATA_DIR", "/tmp/awm_portal"))
VEH = DATA / "POJAZDY"
HIDDEN = DATA / "WYGASZONE"
VEH.mkdir(parents=True, exist_ok=True)
HIDDEN.mkdir(parents=True, exist_ok=True)
API_KEY = os.environ.get("AWM_API_KEY", "")

CSS = r"""
*{box-sizing:border-box}body{margin:0;background:#eef2f1;color:#1e2926;font-family:"Segoe UI",Arial,sans-serif}
.top{height:138px;background:linear-gradient(110deg,#111917 0%,#172722 55%,#0e1715 100%);color:#fff;display:flex;align-items:center;padding:18px 30px;gap:28px;border-bottom:3px solid #35a86b}
.logo{min-width:300px}.logo b{font-size:38px;letter-spacing:-1px}.logo b span{color:#43c878}.sub{font-size:14px;letter-spacing:1px;color:#c6d2cd;margin-top:5px}.sub2{font-size:12px;color:#91a19b;margin-top:4px}
.carhead{flex:1;height:105px;border-radius:12px;background:radial-gradient(circle at 60% 50%,#315448 0,#172722 48%,#111917 80%);position:relative;overflow:hidden}.carhead:after{content:"AWM";position:absolute;right:30px;bottom:-28px;font-size:120px;font-weight:900;color:#ffffff08}
.account{min-width:220px;text-align:right}.account strong{display:block}.logout{display:inline-block;margin-top:8px;padding:8px 14px;border-radius:8px;background:#9e302f;color:#fff;text-decoration:none;font-weight:700}
.wrap{max-width:1380px;margin:0 auto;padding:20px}
.search{background:#fff;border:1px solid #d2dcd8;border-radius:12px;padding:12px 15px;display:flex;gap:10px;align-items:center;margin-bottom:18px;box-shadow:0 2px 8px #0000000a}
.search input,.search select{height:40px;border:1px solid #cbd7d2;border-radius:8px;padding:0 12px;background:#fff;color:#33413d}.search input{flex:1}.search select{min-width:180px}
.titlebar{display:flex;justify-content:space-between;align-items:end;margin:8px 2px 12px}.titlebar h1{font-size:24px;margin:0}.muted{color:#72817c;font-size:13px}
.table{background:#fff;border:1px solid #ccd8d3;border-radius:14px;overflow:hidden;box-shadow:0 4px 16px #0000000b}
.headrow,.row{display:grid;grid-template-columns:90px 1.25fr 1.35fr .85fr .9fr 2.4fr;gap:14px;align-items:center;padding:12px 15px}.headrow{background:#e7eeeb;color:#60716b;font-size:12px;font-weight:800;text-transform:uppercase}.row{border-top:1px solid #e3e9e6;min-height:112px}.row:hover{background:#f8fbfa}
.thumb{width:78px;height:58px;border-radius:8px;object-fit:cover;background:#e8eeeb}.noimg{width:78px;height:58px;border-radius:8px;background:#e8eeeb;display:flex;align-items:center;justify-content:center;color:#82918c;font-size:10px}
.make{font-weight:800;font-size:16px}.model{font-size:13px;color:#65746e;margin-top:3px}.small{font-size:12px;line-height:1.55}.status{display:inline-block;background:#d9f0e2;color:#187344;border-radius:20px;padding:6px 10px;font-size:11px;font-weight:800}
.docs{display:flex;flex-wrap:wrap;gap:7px}.doc{display:inline-flex;align-items:center;justify-content:center;min-width:91px;min-height:39px;padding:6px 8px;border-radius:8px;border:1px solid #cbd7d2;background:#f7faf9;color:#273631;text-decoration:none;font-size:11px;font-weight:700}.doc:hover{border-color:#39a96d;background:#edf8f1}.open{background:#238c59;color:#fff;border-color:#238c59}.empty{padding:55px;text-align:center}.detail{background:#fff;border:1px solid #ccd8d3;border-radius:14px;padding:22px}.detailhead{display:flex;gap:20px;align-items:flex-start}.heroimg{width:300px;height:190px;object-fit:cover;border-radius:12px;background:#e8eeeb}.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:20px}.tile{border:1px solid #cbd7d2;border-radius:12px;padding:16px;background:#fbfdfc}.tile h3{margin:0 0 12px;font-size:14px}.file{display:block;margin:6px 0;padding:9px;border-radius:8px;background:#edf3f1;color:#25342f;text-decoration:none;font-size:12px}.file:hover{background:#dff1e7}.back{color:#208754;text-decoration:none;font-weight:700}.danger{margin-top:20px;padding-top:15px;border-top:1px solid #e1e7e4}.danger button{border:1px solid #c95d5d;background:#fff;color:#a82e2e;border-radius:8px;padding:9px 13px;font-weight:700}
@media(max-width:1000px){.top{height:auto;flex-wrap:wrap}.carhead{display:none}.account{min-width:auto}.headrow,.row{grid-template-columns:75px 1fr 1fr}.headrow div:nth-child(n+4),.row>div:nth-child(n+4){display:none}.tiles{grid-template-columns:1fr 1fr}}
"""

INDEX = r"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRZEGLĄD AWM • Portal rzeczoznawcy</title><style>{{css}}</style>
<header class="top"><div class="logo"><b>PRZEGLĄD <span>AWM</span></b><div class="sub">DOKUMENTACJA POJAZDÓW</div><div class="sub2">DLA RZECZOZNAWCÓW</div></div><div class="carhead"></div><div class="account">👤 <strong>Rzeczoznawca</strong><span class="sub2">Portal AWM</span><br><a class="logout" href="/">Odśwież</a></div></header>
<main class="wrap">
<div class="search"><span>🔎</span><input id="q" placeholder="Szukaj po marce, modelu, VIN, rejestracji..." oninput="filterRows()"><select><option>Wybierz zakres dat</option></select><select><option>Wszystkie statusy</option><option>Udostępniony</option></select></div>
<div class="titlebar"><div><h1>Pojazdy udostępnione rzeczoznawcom</h1><div class="muted">Dokumentacja udostępniona z programu PRZEGLĄD AWM</div></div><span class="status">{{count}} UDOSTĘPNIONYCH</span></div>
<div class="table"><div class="headrow"><div>POJAZD</div><div>MARKA / MODEL</div><div>REJESTRACJA / VIN</div><div>PRZEBIEG</div><div>STATUS</div><div>DOKUMENTY</div></div>
{% if cars %}{% for c in cars %}<div class="row" data-search="{{(c.marka or '')}} {{(c.model or '')}} {{(c.vin or '')}} {{(c.rejestracja or '')}}">
<div>{% if c._photo %}<img class="thumb" src="/vehicle/{{c._id}}/ZDJECIA/{{c._photo}}">{% else %}<div class="noimg">BRAK ZDJĘCIA</div>{% endif %}</div>
<div><div class="make">{{c.marka or 'POJAZD'}}</div><div class="model">{{c.model or ''}}</div></div>
<div class="small"><b>{{c.rejestracja or '—'}}</b><br>{{c.vin or '—'}}</div>
<div class="small"><b>{{c.przebieg or '—'}}</b><br>{{c.data or ''}}</div>
<div><span class="status">UDOSTĘPNIONY</span></div>
<div class="docs">
<a class="doc open" href="/vehicle/{{c._id}}">POJAZD</a>
{% if c._has_opis %}<a class="doc" target="_blank" href="/vehicle/{{c._id}}#opis">OPIS</a>{% endif %}
{% if c._has_wycena %}<a class="doc" target="_blank" href="/vehicle/{{c._id}}#wycena">WYCENA</a>{% endif %}
{% if c._has_diag %}<a class="doc" target="_blank" href="/vehicle/{{c._id}}#diag">RAPORT DIAG</a>{% endif %}
{% if c._has_photo %}<a class="doc" target="_blank" href="/vehicle/{{c._id}}#zdjecia">ZDJĘCIA</a>{% endif %}
</div></div>{% endfor %}{% else %}<div class="empty"><h2>Brak pojazdów na portalu</h2><div class="muted">Po wysłaniu pojazdu z programu PRZEGLĄD AWM pojawi się on tutaj.</div></div>{% endif %}</div>
</main>
<script>function filterRows(){let q=document.getElementById('q').value.toLowerCase();document.querySelectorAll('.row').forEach(r=>r.style.display=r.dataset.search.toLowerCase().includes(q)?'grid':'none')}</script>"""

DETAIL = r"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{m.marka or ''}} {{m.model or ''}} • AWM</title><style>{{css}}</style>
<header class="top"><div class="logo"><b>PRZEGLĄD <span>AWM</span></b><div class="sub">DOKUMENTACJA POJAZDÓW</div></div><div class="carhead"></div><div class="account"><a class="logout" href="/">← LISTA POJAZDÓW</a></div></header>
<main class="wrap"><div class="detail"><a class="back" href="/">← Lista pojazdów</a><div class="detailhead" style="margin-top:15px">
{% if photo %}<img class="heroimg" src="/vehicle/{{vid}}/ZDJECIA/{{photo}}">{% endif %}
<div><h1>{{m.marka or ''}} {{m.model or ''}}</h1><div class="small"><b>Rejestracja:</b> {{m.rejestracja or '—'}}<br><b>VIN:</b> {{m.vin or '—'}}<br><b>Rok:</b> {{m.rok or '—'}}<br><b>Przebieg:</b> {{m.przebieg or '—'}}</div></div></div>
<div class="tiles">
<section class="tile" id="opis"><h3>📄 PODGLĄD OPISU</h3>{% if groups.OPIS %}{% for f in groups.OPIS %}<a class="file" target="_blank" href="/vehicle/{{vid}}/OPIS/{{f}}">{{f}}</a>{% endfor %}{% else %}<span class="muted">Brak opisu</span>{% endif %}</section>
<section class="tile" id="wycena"><h3>💰 PODGLĄD WYCENY</h3>{% if groups.WYCENA %}{% for f in groups.WYCENA %}<a class="file" target="_blank" href="/vehicle/{{vid}}/WYCENA/{{f}}">{{f}}</a>{% endfor %}{% else %}<span class="muted">Brak wyceny</span>{% endif %}</section>
<section class="tile" id="diag"><h3>🔧 PODGLĄD RAPORTU DIAG</h3>{% if groups.DIAG %}{% for f in groups.DIAG %}<a class="file" target="_blank" href="/vehicle/{{vid}}/DIAG/{{f}}">{{f}}</a>{% endfor %}{% else %}<span class="muted">Brak raportu DIAG</span>{% endif %}</section>
<section class="tile" id="zdjecia"><h3>📷 ZDJĘCIA</h3>{% if groups.ZDJECIA %}{% for f in groups.ZDJECIA %}<a class="file" target="_blank" href="/vehicle/{{vid}}/ZDJECIA/{{f}}">{{f}}</a>{% endfor %}{% else %}<span class="muted">Brak zdjęć</span>{% endif %}</section>
</div><div class="danger"><form method="post" action="/vehicle/{{vid}}/hide" onsubmit="return confirm('Wygasić udostępnienie tego pojazdu?');"><button>WYGASIĆ UDOSTĘPNIENIE</button></form><span class="muted"> Pojazd nie jest kasowany z bazy AWM.</span></div></div></main>"""

def safe(s):
    return ''.join(c for c in str(s) if c.isalnum() or c in '._-')[:100]

def read_meta(d):
    try:return json.loads((d/'vehicle.json').read_text(encoding='utf-8'))
    except:return {}

def groups_for(d):
    return {g:([x.name for x in (d/g).iterdir() if x.is_file()] if (d/g).exists() else []) for g in ['ZDJECIA','OPIS','WYCENA','DIAG']}

@app.get('/')
def index():
    cars=[]
    for d in sorted(VEH.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
        if not d.is_dir():continue
        m=read_meta(d); gs=groups_for(d)
        m['_id']=d.name; m['_photo']=(gs['ZDJECIA'][0] if gs['ZDJECIA'] else None)
        m['_has_photo']=bool(gs['ZDJECIA']); m['_has_opis']=bool(gs['OPIS']); m['_has_wycena']=bool(gs['WYCENA']); m['_has_diag']=bool(gs['DIAG'])
        cars.append(m)
    return render_template_string(INDEX,css=CSS,cars=cars,count=len(cars))

@app.get('/vehicle/<vid>')
def vehicle(vid):
    d=VEH/safe(vid)
    if not d.is_dir():abort(404)
    gs=groups_for(d); photo=gs['ZDJECIA'][0] if gs['ZDJECIA'] else None
    return render_template_string(DETAIL,css=CSS,m=read_meta(d),groups=gs,vid=safe(vid),photo=photo)

@app.get('/vehicle/<vid>/<group>/<path:name>')
def file(vid,group,name):
    if group not in ['ZDJECIA','OPIS','WYCENA','DIAG']:abort(404)
    return send_from_directory(VEH/safe(vid)/group,name)

@app.post('/vehicle/<vid>/hide')
def hide_vehicle(vid):
    src=VEH/safe(vid)
    if not src.is_dir():abort(404)
    dst=HIDDEN/safe(vid)
    if dst.exists():shutil.rmtree(dst)
    shutil.move(str(src),str(dst))
    return redirect('/')

@app.post('/api/upload')
def upload():
    if API_KEY and request.headers.get('X-AWM-Key')!=API_KEY:abort(401)
    f=request.files.get('file')
    if f:
        data=f.read(); filename=f.filename or 'vehicle.zip'
    else:
        data=request.get_data(); filename='vehicle.zip'
    if not data:return jsonify(error='missing file'),400
    tmp=Path(tempfile.mkdtemp())
    try:
        z=tmp/filename; z.write_bytes(data)
        if not zipfile.is_zipfile(z):return jsonify(error='invalid ZIP file'),400
        extract=tmp/'x'; extract.mkdir()
        with zipfile.ZipFile(z) as zz:zz.extractall(extract)
        roots=[p for p in extract.iterdir() if p.is_dir()]
        src=roots[0] if len(roots)==1 else extract
        mp=src/'vehicle.json'
        if not mp.exists():
            found=list(extract.rglob('vehicle.json'))
            if not found:return jsonify(error='vehicle.json missing'),400
            mp=found[0]; src=mp.parent
        m=json.loads(mp.read_text(encoding='utf-8'))
        vid=safe(m.get('vin') or m.get('rejestracja') or 'AUTO')
        dst=VEH/vid
        if dst.exists():shutil.rmtree(dst)
        shutil.copytree(src,dst)
        return jsonify(ok=True,id=vid,message='Pojazd został udostępniony na portal')
    except zipfile.BadZipFile:return jsonify(error='invalid ZIP file'),400
    except Exception as e:return jsonify(error=str(e)),500
    finally:shutil.rmtree(tmp,ignore_errors=True)

@app.get('/health')
def health():return jsonify(ok=True)

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')))
