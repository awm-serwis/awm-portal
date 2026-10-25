"""AWM Mobile OTA: separate from desktop updater and vehicle APIs."""
import hashlib
import io
import json
import logging
import os
import re
import zipfile

from flask import Response, jsonify, request, send_file, session

BUCKET = "awm-mobile-updates"
MAX_APK_BYTES = 160 * 1024 * 1024


def register_mobile_updates(app):
    def storage():
        import supabase_backend as backend
        sb = getattr(backend, "sb", None)
        if sb is None:
            raise RuntimeError("Supabase niedostępna")
        return sb.storage.from_(BUCKET)

    def manifest_data():
        try:
            raw = storage().download("manifest.json")
        except Exception as exc:
            app.logger.exception("AWM Mobile: nie mozna odczytac manifest.json z Supabase")
            raise RuntimeError("Nie mozna odczytac manifestu z Supabase") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
            if (not isinstance(data, dict)
                    or not isinstance(data.get("build"), int)
                    or not re.fullmatch(r"[a-f0-9]{64}", str(data.get("sha256", "")))
                    or not str(data.get("path", "")).startswith("packages/")
                    or not isinstance(data.get("version"), str)):
                raise ValueError("Nieprawidlowy format manifestu")
            return data
        except (UnicodeError, ValueError, TypeError) as exc:
            app.logger.exception("AWM Mobile: uszkodzony manifest.json")
            raise RuntimeError("Nieprawidlowy manifest aktualizacji") from exc

    @app.get("/api/awm-flutter/manifest.json")
    def awm_mobile_manifest():
        try:
            data = manifest_data()
        except RuntimeError:
            return jsonify(error="Manifest aktualizacji niedostepny; sprawdz logi serwera AWM Portal"), 503
        return jsonify(
            version=data["version"],
            build=data["build"],
            notes=data.get("notes", ""),
            android_url=request.url_root.rstrip("/") + "/api/awm-flutter/package.apk",
            android_sha256=data["sha256"],
        )

    @app.get("/api/awm-flutter/package.apk")
    def awm_mobile_package():
        try:
            data = manifest_data()
        except RuntimeError:
            return jsonify(error="Manifest aktualizacji niedostepny"), 503
        try:
            payload = storage().download(data["path"])
            if hashlib.sha256(payload).hexdigest() != data["sha256"]:
                return jsonify(error="Kontrola integralności APK nie powiodła się"), 503
            return send_file(
                io.BytesIO(payload),
                mimetype="application/vnd.android.package-archive",
                as_attachment=True,
                download_name="AWM-Mobile-" + data["version"] + ".apk",
            )
        except Exception:
            return jsonify(error="APK chwilowo niedostępne"), 503

    @app.get("/admin/awm-mobile-aktualizacje")
    def awm_mobile_admin():
        if (session.get("user") or {}).get("role") != "admin":
            return Response("Wymagane logowanie administratora AWM.", status=403)
        return Response("""<!doctype html><html lang="pl"><meta charset="utf-8">
<title>AWM Mobile — aktualizacje</title><style>
body{font:16px Arial;background:#eef4f2;max-width:650px;margin:45px auto}
main{background:white;border-radius:14px;padding:28px}
label{display:block;margin-top:16px}input,textarea{width:96%;padding:10px;margin-top:6px}
button{margin-top:20px;padding:12px;background:#a71d35;color:white;border:0;border-radius:7px}
</style><main><h2>AWM Mobile — publikuj APK</h2>
<p>Publikuj wyłącznie sprawdzony APK podpisany kluczem zgodnym z Lenovo.
Nowy manifest pojawi się dopiero po weryfikacji pliku na serwerze.</p>
<form id="f"><label>Wersja<input name="version" placeholder="1.0.104" required></label>
<label>Numer kompilacji<input name="build" type="number" min="104" required></label>
<label>Plik APK<input name="package" type="file" accept=".apk" required></label>
<label>Opis zmian<textarea name="notes" rows="3"></textarea></label>
<button>Opublikuj aktualizację</button></form><p id="result"></p></main>
<script>document.getElementById('f').onsubmit=async e=>{
e.preventDefault();const el=document.getElementById('result');el.textContent='Przesyłanie APK…';
try{const r=await fetch('/api/admin/awm-flutter/publish',{method:'POST',body:new FormData(e.target)});
const body=await r.text();let d;try{d=JSON.parse(body)}catch(_){throw Error('Serwer zwrócił HTTP '+r.status+' zamiast JSON. '+(r.status===502||r.status===504?'Przekroczono czas przetwarzania APK.':'Sprawdź logi Render.'))}el.textContent=d.ok?'Opublikowano '+d.version+' ('+d.build+')':('HTTP '+r.status+': '+(d.error||'Błąd publikacji'));}
catch(ex){el.textContent='Błąd połączenia: '+ex.message;}};</script></html>""", mimetype="text/html")

    @app.post("/api/admin/awm-flutter/publish")
    def awm_mobile_publish():
        if (session.get("user") or {}).get("role") != "admin":
            return jsonify(error="Brak uprawnień administratora"), 403
        version = str(request.form.get("version", "")).strip()
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            return jsonify(error="Nieprawidłowy numer wersji"), 400
        try:
            build = int(request.form.get("build", "0"))
        except ValueError:
            return jsonify(error="Nieprawidłowy numer kompilacji"), 400
        if build <= 103:
            return jsonify(error="Numer kompilacji musi być większy niż 103"), 400
        try:
            current = manifest_data()
        except RuntimeError:
            current = None
        if current is not None and build <= current["build"]:
            return jsonify(error="Nowa kompilacja musi być nowsza od opublikowanej"), 409
        uploaded = request.files.get("package")
        if uploaded is None:
            return jsonify(error="Brak pliku APK"), 400
        payload = uploaded.read(MAX_APK_BYTES + 1)
        if not payload or len(payload) > MAX_APK_BYTES:
            return jsonify(error="APK jest pusty lub przekracza 160 MiB"), 413
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as apk:
                names = set(apk.namelist())
                if "AndroidManifest.xml" not in names or not any(x.startswith("classes") and x.endswith(".dex") for x in names):
                    return jsonify(error="Plik nie wygląda na APK Androida"), 400
                if apk.testzip() is not None:
                    return jsonify(error="Uszkodzony plik APK"), 400
        except zipfile.BadZipFile:
            return jsonify(error="Nieprawidłowy APK"), 400
        digest = hashlib.sha256(payload).hexdigest()
        path = "packages/" + str(build) + "_" + digest[:16] + ".apk"
        manifest = dict(version=version, build=build, sha256=digest,
                        path=path, notes=str(request.form.get("notes", ""))[:500])
        try:
            import supabase_backend as backend
            sb = getattr(backend, "sb", None)
            if sb is None:
                raise RuntimeError("Supabase niedostępna")
            try:
                sb.storage.create_bucket(BUCKET, options={"public": False, "file_size_limit": MAX_APK_BYTES})
            except Exception:
                pass
            store = sb.storage.from_(BUCKET)
            store.upload(path, payload, {"content-type": "application/vnd.android.package-archive"})
            if hashlib.sha256(store.download(path)).hexdigest() != digest:
                raise RuntimeError("Niezgodna suma SHA-256 po przesłaniu")
            store.upload("manifest.json", json.dumps(manifest).encode("utf-8"),
                         {"content-type": "application/json", "upsert": "true"})
            return jsonify(ok=True, version=version, build=build, sha256=digest)
        except Exception as exc:
            return jsonify(error="Nie udało się opublikować: " + str(exc)[:180]), 503
