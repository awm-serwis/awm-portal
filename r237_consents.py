"""R237: izolowany formularz zgody. Moduł nie jest aktywny bez rejestracji blueprintu.
Przed wdrożeniem wymagane: trwały AWM_DATA_DIR, kopie zapasowe i testy integracji.
"""
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, abort, jsonify, request, render_template_string

bp = Blueprint("awm_r237_consents", __name__)
DATA_DIR = Path(os.environ.get("AWM_DATA_DIR", "/var/data/awm_portal"))
DB_PATH = DATA_DIR / "r237_consents.sqlite3"
ADMIN_TOKEN = os.environ.get("AWM_CONSENTS_ADMIN_TOKEN", "")

def connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS repair_consents(
        id INTEGER PRIMARY KEY, invitation_token TEXT UNIQUE NOT NULL,
        order_id TEXT NOT NULL, registration TEXT NOT NULL,
        order_snapshot TEXT NOT NULL, customer_name TEXT,
        authorization_number TEXT, consent_text TEXT,
        consent_utc TEXT, client_ip TEXT, user_agent TEXT
    )""")
    db.commit()
    return db

def admin_only():
    supplied = request.headers.get("X-AWM-Consents-Token", "")
    if not ADMIN_TOKEN or not hmac.compare_digest(supplied, ADMIN_TOKEN):
        abort(403)

@bp.post("/api/r237/consents/invitations")
def invite():
    admin_only()
    payload = request.get_json(silent=True) or {}
    order_id = str(payload.get("order_id", "")).strip()
    registration = str(payload.get("registration", "")).strip()
    snapshot = str(payload.get("order_snapshot", "")).strip()
    if not order_id or not registration or not snapshot or len(snapshot) > 50000:
        return jsonify(error="Wymagane: order_id, registration, order_snapshot"), 400
    token = secrets.token_urlsafe(32)
    with connection() as db:
        db.execute("INSERT INTO repair_consents(invitation_token,order_id,registration,order_snapshot) VALUES(?,?,?,?)",
                   (token, order_id[:120], registration[:40], snapshot))
    return jsonify(url=request.url_root.rstrip("/") + "/r237/consent/" + token), 201

FORM = """<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWM — zgoda na naprawę</title>
<style>body{font:16px system-ui;max-width:700px;margin:40px auto;padding:20px;color:#20312b}
fieldset{border:1px solid #ccd7d1;border-radius:12px;padding:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
input[type=text]{box-sizing:border-box;width:100%;padding:12px}
label{display:block;margin:12px 0}button{padding:12px 20px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f4;padding:15px}
@media(max-width:560px){.grid{grid-template-columns:1fr}}</style>
<h1>Zgoda na naprawę</h1><p>Numer zlecenia: <strong>{{ order_id }}</strong>.
Pojazd: <strong>{{ registration }}</strong></p>
<h2>Treść zlecenia przedstawiona do akceptacji</h2><pre>{{ snapshot }}</pre>
<form method="post"><fieldset><div class="grid">
<label>Imię i nazwisko osoby udzielającej zgody
<input type="text" name="customer_name" maxlength="180" required></label>
<label>Nr autoryzacji (opcjonalny)
<input type="text" name="authorization_number" maxlength="120"></label>
</div><label><input type="checkbox" name="confirmed" value="yes" required>
Potwierdzam, że zapoznałem(-am) się z powyższym zakresem i udzielam zgody na naprawę wskazanego pojazdu.</label>
<button type="submit">UDZIELAM ZGODY</button></fieldset></form></html>"""

@bp.route("/r237/consent/<token>", methods=["GET", "POST"])
def consent(token):
    with connection() as db:
        row = db.execute("SELECT * FROM repair_consents WHERE invitation_token=?", (token,)).fetchone()
        if row is None: abort(404)
        if row["consent_utc"]: return "Zgoda została już zapisana.", 409
        if request.method == "GET":
            return render_template_string(FORM, order_id=row["order_id"],
                                          registration=row["registration"],
                                          snapshot=row["order_snapshot"])
        name = request.form.get("customer_name", "").strip()
        number = request.form.get("authorization_number", "").strip()
        if not name or len(name) > 180 or len(number) > 120 or request.form.get("confirmed") != "yes":
            return "Nieprawidłowe dane zgody.", 400
        statement = "Potwierdzam, że zapoznałem(-am) się z powyższym zakresem i udzielam zgody na naprawę wskazanego pojazdu."
        cursor = db.execute("""UPDATE repair_consents SET customer_name=?, authorization_number=?,
            consent_text=?, consent_utc=?, client_ip=?, user_agent=?
            WHERE invitation_token=? AND consent_utc IS NULL""",
            (name, number, statement, datetime.now(timezone.utc).isoformat(),
             request.remote_addr or "", request.user_agent.string[:500], token))
        if cursor.rowcount != 1: return "Zgoda została już zapisana.", 409
    return "Zgoda na naprawę została zapisana. Dziękujemy.", 200

@bp.get("/api/r237/consents")
def list_consents():
    admin_only()
    with connection() as db:
        rows = db.execute("""SELECT id,order_id,registration,customer_name,authorization_number,
            consent_utc,consent_text,order_snapshot FROM repair_consents
            WHERE consent_utc IS NOT NULL ORDER BY id DESC LIMIT 500""").fetchall()
    return jsonify([dict(row) for row in rows])
