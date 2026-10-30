"""Heartbeat aktywnego komputera AWM. Bez ujawniania klucza w przegladarce."""
import os, hmac, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from flask import request, jsonify, session

def install_desktop_presence(app):
    from portal_app import DATA, API_KEY
    database=Path(DATA)/"desktop_presence.db"
    def connect():
        c=sqlite3.connect(database,timeout=5)
        c.execute("CREATE TABLE IF NOT EXISTS heartbeat(id INTEGER PRIMARY KEY CHECK(id=1), timestamp INTEGER NOT NULL)")
        return c
    @app.post("/api/awm-desktop/heartbeat")
    def desktop_heartbeat():
        supplied=request.headers.get("X-AWM-Key","")
        if API_KEY=="AWM-CHANGE-ME" or not supplied or not hmac.compare_digest(supplied,API_KEY):
            return jsonify(error="Brak dostepu"),403
        now=int(datetime.now(timezone.utc).timestamp())
        c=connect()
        try:
            c.execute("INSERT INTO heartbeat(id,timestamp) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET timestamp=excluded.timestamp",(now,))
            c.commit()
        finally:c.close()
        return jsonify(ok=True)
    @app.get("/api/awm-desktop/status")
    def desktop_status():
        if not session.get("user"):return jsonify(error="Wymagane logowanie"),401
        c=connect()
        try:
            row=c.execute("SELECT timestamp FROM heartbeat WHERE id=1").fetchone()
        finally:c.close()
        now=int(datetime.now(timezone.utc).timestamp())
        age=(now-int(row[0])) if row else None
        return jsonify(online=(age is not None and 0<=age<=75))
