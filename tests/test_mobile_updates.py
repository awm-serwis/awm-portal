import hashlib
import io
import json
import sys
from types import SimpleNamespace
import zipfile

from flask import Flask
import pytest

from mobile_updates import register_mobile_updates


def apk_bytes(label=b"old"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as apk:
        apk.writestr("AndroidManifest.xml", b"manifest")
        apk.writestr("classes.dex", label * 100)
    return stream.getvalue()


def stage(objects, build=122, label=b"old"):
    apk = apk_bytes(label)
    sha = hashlib.sha256(apk).hexdigest()
    path = f"packages/{build}_{sha[:16]}.apk"
    chunks = []
    # Exercise the same concatenation as the real three-object release.
    for n, part in enumerate((apk[:80], apk[80:200], apk[200:])):
        part_path = path + f".part{n:02d}"
        objects[part_path] = part
        chunks.append(dict(path=part_path, size=len(part), sha256=hashlib.sha256(part).hexdigest()))
    data = dict(version=f"1.0.{build}", build=build, path=path, size=len(apk), sha256=sha, chunks=chunks)
    release = f"{build}_{sha}"
    objects[f"releases/{release}.json"] = json.dumps(data).encode()
    return data, release, apk


@pytest.fixture
def ota(tmp_path, monkeypatch):
    objects = {}
    class Store:
        def download(self, path):
            return objects[path]
        def upload(self, path, data, options):
            if path in objects and options.get("upsert") != "true":
                raise ValueError("already exists")
            objects[path] = data
    store = Store()
    backend = SimpleNamespace(sb=SimpleNamespace(storage=SimpleNamespace(from_=lambda bucket: store)))
    monkeypatch.setitem(sys.modules, "supabase_backend", backend)
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test", AWM_OTA_CACHE_DIR=str(tmp_path))
    register_mobile_updates(app)
    return app.test_client(), objects, tmp_path


def live(objects, data):
    objects["manifest.json"] = json.dumps(data).encode()


def test_anonymous_manifest_and_three_part_download(ota):
    client, objects, cache = ota
    data, release, apk = stage(objects)
    live(objects, data)
    manifest = client.get("/api/awm-flutter/manifest.json", base_url="https://portal.test")
    assert manifest.status_code == 200
    assert manifest.json["build"] == 2122
    assert manifest.json["release_build"] == 122
    assert manifest.json["android_size"] == len(apk)
    assert manifest.json["android_url"] == "https://portal.test/api/awm-flutter/package.apk?release=" + release
    response = client.get(manifest.json["android_url"])
    assert response.status_code == 200
    assert response.data == apk
    assert hashlib.sha256(response.data).hexdigest() == manifest.json["android_sha256"]
    assert int(response.headers["Content-Length"]) == len(apk)
    assert manifest.headers["Cache-Control"].startswith("no-store")


@pytest.mark.parametrize("failure", ["missing", "truncated", "corrupt", "whole_digest", "order", "total"])
def test_never_serves_bytes_from_broken_release(ota, failure):
    client, objects, cache = ota
    data, release, apk = stage(objects)
    part = data["chunks"][1]["path"]
    if failure == "missing": del objects[part]
    elif failure == "truncated": objects[part] = objects[part][:-1]
    elif failure == "corrupt": objects[part] = b"X" * len(objects[part])
    elif failure == "whole_digest": data["sha256"] = "a" * 64
    elif failure == "order": data["chunks"].reverse()
    elif failure == "total": data["size"] += 1
    live(objects, data)
    for endpoint in ("manifest.json", "package.apk"):
        response = client.get("/api/awm-flutter/" + endpoint)
        assert response.status_code == 503
        assert response.is_json
        assert b"PK\x03\x04" not in response.data
    assert not list(cache.glob("*.partial"))
    assert not list(cache.glob("*.apk"))


def test_pinned_download_survives_new_manifest(ota):
    client, objects, _ = ota
    old, release, apk = stage(objects)
    live(objects, old)
    url = client.get("/api/awm-flutter/manifest.json").json["android_url"]
    new, _, _ = stage(objects, 123, b"new")
    live(objects, new)
    assert client.get(url).data == apk
    assert client.get("/api/awm-flutter/manifest.json").json["release_build"] == 123


def test_failed_transfer_can_be_retried(ota):
    client, objects, cache = ota
    data, release, apk = stage(objects)
    live(objects, data)
    path = data["chunks"][2]["path"]
    saved = objects.pop(path)
    assert client.get("/api/awm-flutter/package.apk").status_code == 503
    objects[path] = saved
    assert client.get("/api/awm-flutter/package.apk").data == apk
    assert not list(cache.glob("*.partial"))


def test_staged_candidate_does_not_switch_live_release(ota):
    client, objects, _ = ota
    data, _, _ = stage(objects)
    live(objects, data)
    _, release, apk = stage(objects, 123, b"new")
    assert client.get("/api/awm-flutter/package.apk?release=" + release).data == apk
    assert client.get("/api/awm-flutter/manifest.json").json["release_build"] == 122


def test_invalid_archive_and_cache_corruption_are_rejected(ota):
    client, objects, cache = ota
    data, release, apk = stage(objects)
    live(objects, data)
    assert client.get("/api/awm-flutter/package.apk").data == apk
    (cache / (release + ".apk")).write_bytes(b"corrupt cache")
    assert client.get("/api/awm-flutter/package.apk").data == apk
    payload = b"not an apk"
    sha = hashlib.sha256(payload).hexdigest()
    path = "packages/invalid.apk"
    objects[path] = payload
    live(objects, dict(version="1.0.123", build=123, path=path, sha256=sha))
    assert client.get("/api/awm-flutter/package.apk").status_code == 503


def test_legacy_manifest_is_pinned_before_new_release(ota):
    client, objects, _ = ota
    data, release, apk = stage(objects)
    del objects[f"releases/{release}.json"]
    live(objects, data)
    response = client.get("/api/awm-flutter/manifest.json")
    assert response.status_code == 200
    new, _, _ = stage(objects, 123, b"new")
    live(objects, new)
    assert client.get(response.json["android_url"]).data == apk


def test_range_download_and_no_manual_publication(ota):
    client, objects, _ = ota
    data, _, apk = stage(objects)
    live(objects, data)
    response = client.get("/api/awm-flutter/package.apk", headers={"Range": "bytes=5-15"})
    assert response.status_code == 206
    assert response.data == apk[5:16]
    assert client.post("/api/admin/awm-flutter/publish").status_code == 403
    with client.session_transaction() as session:
        session["user"] = {"role": "admin"}
    assert client.post("/api/admin/awm-flutter/publish").status_code == 410


def test_tls_terminating_proxy_still_gets_https_download_url(ota):
    client, objects, _ = ota
    data, _, _ = stage(objects)
    live(objects, data)
    response = client.get('/api/awm-flutter/manifest.json', base_url='http://portal.test',
                          headers={'X-Forwarded-Proto': 'https'})
    assert response.json['android_url'].startswith('https://portal.test/')


@pytest.mark.parametrize('extra', [dict(android_version_code=123), dict(package_id='other.app')])
def test_mismatched_android_metadata_is_not_announced(ota, extra):
    client, objects, _ = ota
    data, _, _ = stage(objects)
    data.update(extra)
    live(objects, data)
    assert client.get('/api/awm-flutter/manifest.json').status_code == 503
