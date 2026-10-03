import os, json, zipfile, shutil, tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string

app=Flask(__name__)
DATA=Path(os.environ.get('AWM_DATA_DIR','/tmp/awm_portal'))
VEH=DATA/'POJAZDY'; VEH.mkdir(parents=True,exist_ok=True)
API_KEY=os.environ.get('AWM_API_KEY','')

CSS='''body{font-family:Arial,sans-serif;background:#f4f7fb;margin:0;color:#182230}.top{background:#fff;padding:18px 28px;border-bottom:1px solid #dde3ea;font-weight:800;font-size:24px}.wrap{max-width:1150px;margin:30px auto;padding:0 18px}.empty,.card{background:white;border-radius:16px;padding:28px;box-shadow:0 4px 18px #00000012}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}.muted{color:#667085}.btn{display:inline-block;padding:10px 14px;border-radius:10px;background:#0b6bcb;color:white;text-decoration:none;margin:5px 5px 0 0}.photo{width:100%;height:190px;object-fit:cover;border-radius:12px;background:#eef2f6}.meta{line-height:1.6}'''

def safe(s):
    return ''.join(c for c in s if c.isalnum() or c in '._-')[:100]

@app.get('/')
def index():
    cars=[]
    for d in sorted(VEH.iterdir(), key=lambda p:p.stat().st_mtime, reverse=True):
        if not d.is_dir(): continue
        try: m=json.loads((d/'vehicle.json').read_text(encoding='utf-8'))
        except: m={}
        photos=list((d/'ZDJECIA').glob('*')) if (d/'ZDJECIA').exists() else []
        m['_id']=d.name; m['_photo']=photos[0].name if photos else None; cars.append(m)
    return render_template_string('''<!doctype html><meta charset="utf-8"><title>AWM Portal</title><style>{{css}}</style><div class=top>PRZEGLĄD AWM <span class=muted>• Portal rzeczoznawcy</span></div><div class=wrap>{% if not cars %}<div class=empty><h2>Brak pojazdów na portalu</h2><p class=muted>Po wysłaniu pojazdu z programu PRZEGLĄD AWM pojawi się on tutaj.</p></div>{% else %}<div class=grid>{% for c in cars %}<div class=card>{% if c._photo %}<img class=photo src="/vehicle/{{c._id}}/ZDJECIA/{{c._photo}}">{% endif %}<h2>{{c.marka}} {{c.model}}</h2><div class=meta><b>VIN:</b> {{c.vin or '—'}}<br><b>Rejestracja:</b> {{c.rejestracja or '—'}}<br><b>Rok:</b> {{c.rok or '—'}} &nbsp; <b>Przebieg:</b> {{c.przebieg or '—'}}</div><p><a class=btn href="/vehicle/{{c._id}}">Otwórz pojazd</a></p></div>{% endfor %}</div>{% endif %}</div>''',cars=cars,css=CSS)

@app.get('/vehicle/<vid>')
def vehicle(vid):
    d=VEH/safe(vid)
    if not d.is_dir(): abort(404)
    try:m=json.loads((d/'vehicle.json').read_text(encoding='utf-8'))
    except:m={}
    groups={}
    for g in ['ZDJECIA','OPIS','WYCENA','DIAG']:
        gd=d/g; groups[g]=[x.name for x in gd.iterdir() if x.is_file()] if gd.exists() else []
    return render_template_string('''<!doctype html><meta charset="utf-8"><title>AWM Portal</title><style>{{css}}</style><div class=top>PRZEGLĄD AWM</div><div class=wrap><div class=card><a href="/">← Lista pojazdów</a><h1>{{m.marka}} {{m.model}}</h1><p><b>VIN:</b> {{m.vin or '—'}} &nbsp; <b>Rejestracja:</b> {{m.rejestracja or '—'}} &nbsp; <b>Rok:</b> {{m.rok or '—'}} &nbsp; <b>Przebieg:</b> {{m.przebieg or '—'}}</p>{% for g,fs in groups.items() %}<h3>{{g}}</h3>{% if fs %}{% for f in fs %}<a class=btn target=_blank href="/vehicle/{{vid}}/{{g}}/{{f}}">{{f}}</a>{% endfor %}{% else %}<span class=muted>Brak</span>{% endif %}{% endfor %}</div></div>''',m=m,groups=groups,vid=vid,css=CSS)

@app.get('/vehicle/<vid>/<group>/<path:name>')
def file(vid,group,name):
    if group not in ['ZDJECIA','OPIS','WYCENA','DIAG']: abort(404)
    return send_from_directory(VEH/safe(vid)/group,name)

@app.post('/api/upload')
def upload():
    if API_KEY and request.headers.get('X-AWM-Key')!=API_KEY: abort(401)
    f=request.files.get('file')
    if not f: return jsonify(error='missing file'),400
    tmp=Path(tempfile.mkdtemp())
    try:
        z=tmp/'u.zip'; f.save(z)
        with zipfile.ZipFile(z) as zz: zz.extractall(tmp/'x')
        roots=[p for p in (tmp/'x').iterdir() if p.is_dir()]
        src=roots[0] if len(roots)==1 else tmp/'x'
        mp=src/'vehicle.json'
        if not mp.exists(): return jsonify(error='vehicle.json missing'),400
        m=json.loads(mp.read_text(encoding='utf-8')); vid=safe(m.get('vin') or m.get('rejestracja') or 'AUTO')
        dst=VEH/vid
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(src,dst)
        return jsonify(ok=True,id=vid)
    finally: shutil.rmtree(tmp,ignore_errors=True)

@app.get('/health')
def health(): return jsonify(ok=True)

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')))
