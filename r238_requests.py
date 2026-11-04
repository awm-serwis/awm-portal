"""R238 — isolated workshop intake and repair-stage workflow.
Requires persistent AWM_DATA_DIR; no automatic import into desktop AWM PRO yet.
"""
import os, sqlite3, secrets, hmac, re
from pathlib import Path
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session

bp = Blueprint("r238_workshop", __name__)
DB = Path(os.environ.get("AWM_DATA_DIR", "/var/data/awm_portal")) / "r238_requests.sqlite3"

def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS workshop_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      public_ref TEXT NOT NULL UNIQUE, created_utc TEXT NOT NULL,
      customer TEXT NOT NULL, email TEXT, phone TEXT,
      registration TEXT NOT NULL, vehicle TEXT, description TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'new',
      repair_started_utc TEXT, updated_utc TEXT NOT NULL)""")
    con.commit()
    return con

def authorized():
    user = session.get("user") or {}
    token = request.headers.get("X-AWM-Intake-Token", "")
    expected = os.environ.get("AWM_INTAKE_ADMIN_TOKEN", "")
    return user.get("role") == "admin" or bool(expected and hmac.compare_digest(token, expected))

@bp.post("/api/warsztat/r238/requests")
def create_request():
    data = request.get_json(silent=True) or {}
    customer = str(data.get("customer") or "").strip()[:180]
    registration = str(data.get("registration") or "").strip().upper()[:40]
    description = str(data.get("description") or "").strip()[:5000]
    email = str(data.get('email') or '').strip()[:254]
    if email and not re.fullmatch(r'[^\\s@]+@[^\\s@]+\\.[^\\s@]+', email):
        return jsonify(error='Nieprawidłowy adres e-mail'), 400
    if not customer or not registration or not description:
        return jsonify(error="Wymagane: klient, rejestracja, opis"), 400
    now = datetime.now(timezone.utc).isoformat()
    ref = "AWM-" + secrets.token_hex(6).upper()
    with db() as con:
        con.execute("""INSERT INTO workshop_requests
        (public_ref,created_utc,customer,email,phone,registration,vehicle,description,updated_utc)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (ref,now,customer,email,
         str(data.get("phone") or "")[:50],registration,
         str(data.get("vehicle") or "")[:200],description,now))
    return jsonify(ok=True, reference=ref, status="new"), 201

@bp.get("/api/warsztat/r238/requests")
def list_requests():
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    with db() as con:
        rows = con.execute("SELECT * FROM workshop_requests ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify(ok=True, requests=[dict(r) for r in rows])

@bp.post("/api/warsztat/r238/requests/<int:item_id>/start-repair")
def start_repair(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    now = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT status FROM workshop_requests WHERE id=?", (item_id,)).fetchone()
        if row is None: return jsonify(error="Nie znaleziono zgłoszenia"), 404
        if row["status"] == "repair": return jsonify(ok=True, already_moved=True)
        if row["status"] != "new": return jsonify(error="Nieprawidłowy status"), 409
        con.execute("""UPDATE workshop_requests SET status='repair',
            repair_started_utc=?,updated_utc=? WHERE id=? AND status='new'""",
            (now,now,item_id))
    return jsonify(ok=True, status="repair")
