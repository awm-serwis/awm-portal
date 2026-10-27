"""AWM Mobile OTA: verify a complete immutable release before serving any bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import zipfile

from flask import Response, jsonify, request, send_file, session

BUCKET = "awm-mobile-updates"
MAX_APK_BYTES = 160_000_000
MAX_CHUNK_BYTES = 20_000_000
RELEASE_PATTERN = r"[1-9][0-9]*_[a-f0-9]{64}"


def register_mobile_updates(app):
    cache_lock = threading.Lock()

    def storage():
        import supabase_backend as backend
        if backend.sb is None:
            raise RuntimeError("Supabase niedostępna")
        return backend.sb.storage.from_(BUCKET)

    def release_id(data):
        return f'{data["build"]}_{data["sha256"]}'

    def manifest_data(release=None):
        if release is not None and not re.fullmatch(RELEASE_PATTERN, release):
            raise ValueError("Nieprawidłowy identyfikator wydania")
        path = f"releases/{release}.json" if release else "manifest.json"
        data = json.loads(storage().download(path))
        if (not isinstance(data, dict)
                or type(data.get("build")) is not int or data["build"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", str(data.get("sha256", "")))
                or not re.fullmatch(r"packages/[A-Za-z0-9_.-]+\.apk", str(data.get("path", "")))
                or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(data.get("version", "")))):
            raise ValueError("Nieprawidłowy manifest aktualizacji")
        if release and release_id(data) != release:
            raise ValueError("Manifest wskazuje inne wydanie")
        if data.get("android_version_code", data["build"] + 2000) != data["build"] + 2000:
            raise ValueError("Numer Android versionCode nie odpowiada wydaniu ARM64")
        if data.get("package_id", "pl.automechanika.awm_flutter") != "pl.automechanika.awm_flutter":
            raise ValueError("Niezgodny identyfikator pakietu")
        chunks = data.get("chunks")
        if chunks is not None:
            if (not isinstance(chunks, list) or not 1 <= len(chunks) <= 8
                    or type(data.get("size")) is not int
                    or not 0 < data["size"] <= MAX_APK_BYTES):
                raise ValueError("Nieprawidłowy manifest podzielonego APK")
            paths = set()
            for index, chunk in enumerate(chunks):
                if (not isinstance(chunk, dict)
                        or chunk.get("path") != data["path"] + f".part{index:02d}"
                        or type(chunk.get("size")) is not int
                        or not 0 < chunk["size"] <= MAX_CHUNK_BYTES
                        or not re.fullmatch(r"[a-f0-9]{64}", str(chunk.get("sha256", "")))):
                    raise ValueError("Nieprawidłowy fragment aktualizacji")
                paths.add(chunk["path"])
            if len(paths) != len(chunks) or sum(c["size"] for c in chunks) != data["size"]:
                raise ValueError("Niezgodny całkowity rozmiar aktualizacji")
        return data

    def verified_package(data):
        # Each worker may race to fill the same cache. Temporary files and atomic
        # rename ensure that readers only ever see a fully verified APK.
        cache = Path(app.config.get("AWM_OTA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "awm-ota")))
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / (release_id(data) + ".apk")
        with cache_lock:
            if target.exists():
                with target.open("rb") as existing:
                    digest = hashlib.file_digest(existing, "sha256").hexdigest()
                if digest == data["sha256"] and (not data.get("size") or target.stat().st_size == data["size"]):
                    return target
                target.unlink()
            staging = None
            try:
                with tempfile.NamedTemporaryFile(dir=cache, suffix=".partial", delete=False) as output:
                    staging = Path(output.name)
                    digest = hashlib.sha256()
                    total = 0
                    chunks = data.get("chunks") or [dict(path=data["path"], sha256=data["sha256"], size=data.get("size"))]
                    for chunk in chunks:
                        # At most one 20 MB storage object in memory for chunked releases.
                        payload = storage().download(chunk["path"])
                        total += len(payload)
                        if (total > MAX_APK_BYTES
                                or (chunk.get("size") is not None and len(payload) != chunk["size"])
                                or hashlib.sha256(payload).hexdigest() != chunk["sha256"]):
                            raise ValueError("Niezgodny rozmiar lub SHA-256 fragmentu APK")
                        digest.update(payload)
                        output.write(payload)
                    if digest.hexdigest() != data["sha256"]:
                        raise ValueError("Niezgodny SHA-256 całego APK")
                with zipfile.ZipFile(staging) as apk:
                    names = set(apk.namelist())
                    if ("AndroidManifest.xml" not in names
                            or "classes.dex" not in names or apk.testzip() is not None):
                        raise ValueError("Uszkodzone archiwum APK")
                os.replace(staging, target)
                return target
            finally:
                if staging is not None:
                    staging.unlink(missing_ok=True)

    @app.get("/api/awm-flutter/manifest.json")
    def awm_mobile_manifest():
        try:
            data = manifest_data()
            package = verified_package(data)
            # Preserve legacy releases by giving their verified descriptor an
            # immutable storage identity before returning the pinned URL.
            release = release_id(data)
            descriptor = f"releases/{release}.json"
            try:
                pinned = manifest_data(release)
                if pinned != data:
                    raise ValueError("Konflikt deskryptora wydania")
            except Exception:
                storage().upload(descriptor, json.dumps(data).encode(),
                                 {"content-type": "application/json", "upsert": "false"})
            response = jsonify(
                version=data["version"], build=data.get("android_version_code", data["build"] + 2000),
                release_build=data["build"], notes=data.get("notes", ""),
                source_commit=data.get("source_commit", ""),
                android_url=request.url_root.replace("http://", "https://", 1).rstrip("/") + f"/api/awm-flutter/package.apk?release={release}",
                android_sha256=data["sha256"], android_size=package.stat().st_size,
            )
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response
        except Exception:
            app.logger.exception("AWM Mobile: wydanie nie przeszło weryfikacji")
            return jsonify(error="Aktualizacja niedostępna lub niekompletna. Spróbuj ponownie później."), 503

    @app.get("/api/awm-flutter/package.apk")
    def awm_mobile_package():
        try:
            data = manifest_data(request.args.get("release"))
            package = verified_package(data)
            response = send_file(package, mimetype="application/vnd.android.package-archive",
                                 as_attachment=True, download_name=f'AWM-Mobile-{data["version"]}.apk',
                                 conditional=True, etag=data["sha256"])
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except Exception:
            app.logger.exception("AWM Mobile: APK niedostępne lub uszkodzone")
            return jsonify(error="Nie można pobrać kompletnego APK. Spróbuj ponownie."), 503

    @app.get("/admin/awm-mobile-aktualizacje")
    def awm_mobile_admin():
        if (session.get("user") or {}).get("role") != "admin":
            return Response("Wymagane logowanie administratora AWM.", status=403)
        return Response("Aktualizacje AWM Mobile publikuje automatycznie GitHub Actions w repozytorium AWM-MOBILE. "
                        "Publikacja manifestu następuje po weryfikacji podpisu i publicznego pobrania całego APK.",
                        mimetype="text/plain")

    @app.post("/api/admin/awm-flutter/publish")
    def awm_mobile_publish():
        if (session.get("user") or {}).get("role") != "admin":
            return jsonify(error="Brak uprawnień administratora"), 403
        return jsonify(error="Użyj procesu publikacji GitHub Actions w AWM-MOBILE; ręczne publikowanie wyłączono."), 410
