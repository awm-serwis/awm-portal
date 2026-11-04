"""R238 — durable workshop intake stored in Supabase. No automatic desktop import."""
import os, secrets, hmac, re
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session

bp = Blueprint("r238_workshop", __name__)

def store():
    from supabase_backend import sb
    return sb.table("awm_intake_requests")

def authorized():
    user = session.get("user") or {}
    token = request.headers.get("X-AWM-Intake-Token", "")
    expected = os.environ.get("AWM_INTAKE_ADMIN_TOKEN", "")
    return user.get("role") == "admin" or bool(expected and hmac.compare_digest(token, expected))

@bp.post("/api/warsztat/r238/requests")
def create_request():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="Nieprawidłowe dane"), 400
    customer = str(data.get("customer") or "").strip()[:180]
    registration = str(data.get("registration") or "").strip().upper()[:80]
    description = str(data.get("description") or "").strip()[:5000]
    email = str(data.get("email") or "").strip()[:254]
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Nieprawidłowy adres e-mail"), 400
    if not registration or not description:
        return jsonify(error="Wymagane: rej / marka i model oraz opis usterki"), 400
    now = datetime.now(timezone.utc).isoformat()
    ref = "AWM-" + secrets.token_hex(8).upper()
    try:
        store().insert({"public_ref":ref, "created_utc":now, "customer":customer,
          "email":email, "phone":str(data.get("phone") or "")[:50],
          "registration":registration, "vehicle":str(data.get("vehicle") or "")[:200],
          "description":description, "status":"new", "updated_utc":now}).execute()
    except Exception:
        bp.logger.exception("R238 intake write failed") if hasattr(bp,"logger") else None
        return jsonify(error="Nie udało się zapisać zgłoszenia"), 503
    return jsonify(ok=True, reference=ref, status="new"), 201

@bp.get("/api/warsztat/r238/requests")
def list_requests():
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    try:
        rows = store().select("*").order("id", desc=True).limit(500).execute().data or []
    except Exception:
        return jsonify(error="Nie udało się pobrać zgłoszeń"), 503
    return jsonify(ok=True, requests=rows)

@bp.post("/api/warsztat/r238/requests/<int:item_id>/start-repair")
def start_repair(item_id):
    if not authorized(): return jsonify(error="Brak autoryzacji"), 403
    try:
        rows = store().select("id,status").eq("id",item_id).limit(1).execute().data or []
        if not rows: return jsonify(error="Nie znaleziono zgłoszenia"), 404
        if rows[0]["status"] == "repair": return jsonify(ok=True, already_moved=True)
        if rows[0]["status"] != "new": return jsonify(error="Nieprawidłowy status"), 409
        now = datetime.now(timezone.utc).isoformat()
        changed = store().update({"status":"repair","repair_started_utc":now,"updated_utc":now}).eq("id",item_id).eq("status","new").execute().data or []
        if not changed: return jsonify(error="Zgłoszenie zostało już zmienione"), 409
    except Exception:
        return jsonify(error="Nie udało się zmienić statusu"), 503
    return jsonify(ok=True, status="repair")
