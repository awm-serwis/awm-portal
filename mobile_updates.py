"""AWM Mobile OTA: separate from desktop updater and vehicle APIs."""
import hashlib
import io
import json
import logging
import os
import re
import zipfile
from urllib.request import urlopen
from urllib.parse import urljoin, urlsplit

from flask import Response, jsonify, request, send_file, session, stream_with_context

BUCKET = "awm-mobile-updates"
MAX_APK_BYTES = 160_000_000  # maximum whole release size
MAX_CHUNK_BYTES = 20_000_000  # safely below the 50 MB Supabase per-object cap


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
            chunks = data.get("chunks")
            if chunks is not None:
                if (not isinstance(chunks, list) or not 1 <= len(chunks) <= 8
                        or not isinstance(data.get("size"), int)
                        or not 0 < data["size"] <= MAX_APK_BYTES):
                    raise ValueError("Nieprawidlowy manifest podzielonego APK")
                total = 0
                for chunk in chunks:
                    if (not isinstance(chunk, dict)
                            or not re.fullmatch(r"packages/[A-Za-z0-9_.-]+", str(chunk.get("path", "")))
                            or not isinstance(chunk.get("size"), int)
                            or not 0 < chunk["size"] <= MAX_CHUNK_BYTES
                            or not re.fullmatch(r"[a-f0-9]{64}", str(chunk.get("sha256", "")))):
                        raise ValueError("Nieprawidlowy fragment aktualizacji")
                    total += chunk["size"]
                if total != data["size"]:
                    raise ValueError("Niezgodny calkowity rozmiar aktualizacji")
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
        response = jsonify(
            version=data["version"],
            build=data["build"] + 2000,  # Android ARM64 split APK uses ABI_VERSION*1000 offset
            release_build=data["build"],
            notes=data.get("notes", ""),
            android_url=request.url_root.rstrip("/") + "/api/awm-flutter/package.apk?direct=1",
            android_sha256=data["sha256"],
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/api/awm-flutter/package.apk")
    def awm_mobile_package():
        try:
            data = manifest_data()
        except RuntimeError:
            return jsonify(error="Manifest aktualizacji niedostepny"), 503
        if data.get("chunks"):
            # Supabase Free limits one OBJECT to 50 MB. Stream the verified
            # 20 MB pieces as one original APK, without holding it in Render RAM.
            # The Android client also checks the full APK SHA-256 from manifest.
            try:
                urls = []
                base_url = os.environ["SUPABASE_URL"].rstrip("/") + "/"
                for chunk in data["chunks"]:
                    signed = storage().create_signed_url(chunk["path"], 1800)
                    raw_url = signed.get("signedURL") or signed.get("signedUrl")
                    if not raw_url:
                        raise RuntimeError("Brak adresu fragmentu APK")
                    target = urljoin(base_url, raw_url)
                    parsed_target, parsed_base = urlsplit(target), urlsplit(base_url)
                    if parsed_target.scheme != "https" or parsed_target.hostname != parsed_base.hostname:
                        raise RuntimeError("Nieprawidlowy adres fragmentu APK")
                    urls.append(target)

                def package_stream():
                    whole_digest = hashlib.sha256()
                    for chunk, url in zip(data["chunks"], urls):
                        chunk_digest = hashlib.sha256()
                        count = 0
                        try:
                            with urlopen(url, timeout=90) as source:
                                if source.status != 200:
                                    raise IOError("Supabase nie udostepnil fragmentu")
                                while True:
                                    block = source.read(256 * 1024)
                                    if not block:
                                        break
                                    count += len(block)
                                    chunk_digest.update(block)
                                    whole_digest.update(block)
                                    yield block
                        except Exception:
                            app.logger.exception("AWM Mobile: przerwany transfer fragmentu APK")
                            raise
                        if count != chunk["size"] or chunk_digest.hexdigest() != chunk["sha256"]:
                            raise IOError("Niezgodny rozmiar lub SHA-256 fragmentu APK")
                    if whole_digest.hexdigest() != data["sha256"]:
                        raise IOError("Niezgodny SHA-256 calego APK")

                return Response(
                    stream_with_context(package_stream()),
                    mimetype="application/vnd.android.package-archive",
                    headers={
                        "Content-Disposition": 'attachment; filename="AWM-Mobile-' + data["version"] + '.apk"',
                        "Content-Length": str(data["size"]),
                        "Cache-Control": "no-store, max-age=0",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
            except Exception:
                app.logger.exception("AWM Mobile: nie mozna przygotowac transferu fragmentow")
                return jsonify(error="Fragmenty aktualizacji niedostepne"), 503
        # Large APKs must not pass through Render memory. The tablet already
        # verifies the final file against SHA-256 supplied by the manifest.
        # Signed URLs also let Android use HTTP Range/resume on Supabase directly.
        if request.args.get("direct") == "1":
            try:
                signed = storage().create_signed_url(data["path"], 1800, {"download": True})
                raw_url = signed.get("signedURL") or signed.get("signedUrl")
                if not raw_url:
                    raise RuntimeError("Supabase nie zwrócił podpisanego adresu APK")
                base_url = os.environ["SUPABASE_URL"].rstrip("/") + "/"
                target = urljoin(base_url, raw_url)
                parsed_target, parsed_base = urlsplit(target), urlsplit(base_url)
                if parsed_target.scheme != "https" or parsed_target.hostname != parsed_base.hostname:
                    raise RuntimeError("Nieprawidłowy adres pobierania z Supabase")
                response = Response(status=302, headers={"Location": target})
                response.headers["Cache-Control"] = "no-store, max-age=0"
                return response
            except Exception:
                app.logger.exception("AWM Mobile: nie mozna utworzyc linku pobierania APK; uzywam trybu zgodnosci")
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
            app.logger.exception("AWM Mobile: blad pobierania APK z Supabase")
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
            return jsonify(error="APK jest pusty lub przekracza maksymalny rozmiar 160 MB."), 413
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
                sb.storage.create_bucket(BUCKET, options={"public": False, "file_size_limit": MAX_CHUNK_BYTES})
            except Exception:
                pass
            store = sb.storage.from_(BUCKET)
            if len(payload) <= MAX_CHUNK_BYTES:
                store.upload(path, payload, {"content-type": "application/vnd.android.package-archive"})
                if hashlib.sha256(store.download(path)).hexdigest() != digest:
                    raise RuntimeError("Niezgodna suma SHA-256 po przesłaniu")
            else:
                chunks = []
                for index, start in enumerate(range(0, len(payload), MAX_CHUNK_BYTES)):
                    part = payload[start:start + MAX_CHUNK_BYTES]
                    part_path = path + ".part%02d" % index
                    part_sha = hashlib.sha256(part).hexdigest()
                    store.upload(part_path, part, {"content-type": "application/octet-stream"})
                    if hashlib.sha256(store.download(part_path)).hexdigest() != part_sha:
                        raise RuntimeError("Niezgodna suma SHA-256 fragmentu %s" % index)
                    chunks.append(dict(path=part_path, size=len(part), sha256=part_sha))
                manifest["size"] = len(payload)
                manifest["chunks"] = chunks
            # Atomically switch clients to the new release only once every
            # uploaded fragment has passed the integrity check.
            store.upload("manifest.json", json.dumps(manifest).encode("utf-8"),
                         {"content-type": "application/json", "upsert": "true"})
            return jsonify(ok=True, version=version, build=build, sha256=digest)
        except Exception as exc:
            return jsonify(error="Nie udało się opublikować: " + str(exc)[:180]), 503
