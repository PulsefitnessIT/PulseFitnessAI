# Creative Studio: Nano Banana generation, object storage, file serving, role gating
import io
import os
import struct
import zlib

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PW = "IsoDemo123!"
_tokens = {}


def _login(email):
    if email in _tokens:
        return _tokens[email]
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    _tokens[email] = r.json()["token"]
    return _tokens[email]


def H(email):
    return {"Authorization": f"Bearer {_login(email)}"}


def _png(w=64, h=64, rgb=(200, 30, 90)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


OWNER = "owner@isodemo.com"
LEAD = "lead@isodemo.com"
state = {}


def _check_variants(asset):
    for v in asset.get("variants") or []:
        assert "storage_path" not in v, v
        assert not (v.get("url") or "").startswith("data:"), "data: URL leaked"


# --- List + can_create flags
class TestList:
    def test_owner_list(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative", headers=H(OWNER), timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["can_create"] is True
        for a in d["assets"]:
            _check_variants(a)
        state["owner_assets"] = d["assets"]

    def test_lead_list(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative", headers=H(LEAD), timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["can_create"] is False
        for a in d["assets"]:
            _check_variants(a)


# --- Upload, file serving, reference generation, delete
class TestUploadAndServe:
    def test_owner_upload(self):
        files = {"file": ("TEST_creative.png", _png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/marketing/creative/upload", headers=H(OWNER),
                          files=files, data={"category": "logo", "label": "TEST_logo"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        a = r.json()["asset"]
        _check_variants(a)
        v = a["variants"][0]
        assert v["url"].startswith("/api/marketing/creative/file/")
        assert v["token"] and v["mime"] == "image/png"
        state["upload"] = a

    def test_file_serving(self):
        a = state.get("upload") or pytest.skip("no upload")
        url = BASE_URL + a["variants"][0]["url"]
        r = requests.get(url, timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert "attachment" not in (r.headers.get("content-disposition") or "")
        r2 = requests.get(url + "?download=1", timeout=30)
        assert r2.status_code == 200
        assert "attachment" in r2.headers.get("content-disposition", "")

    def test_unknown_token_404(self):
        r = requests.get(f"{BASE_URL}/api/marketing/creative/file/nonexistent-token-xyz", timeout=30)
        assert r.status_code == 404

    def test_lead_forbidden(self):
        a = state.get("upload") or pytest.skip("no upload")
        h = H(LEAD)
        r = requests.post(f"{BASE_URL}/api/marketing/creative/generate", headers=h,
                          json={"prompt": "x", "n": 1}, timeout=60)
        assert r.status_code == 403, r.text[:200]
        r = requests.post(f"{BASE_URL}/api/marketing/creative/upload", headers=h,
                          files={"file": ("x.png", _png(), "image/png")}, data={"category": "photo"}, timeout=60)
        assert r.status_code == 403, r.text[:200]
        r = requests.delete(f"{BASE_URL}/api/marketing/creative/{a['id']}", headers=h, timeout=30)
        assert r.status_code == 403, r.text[:200]
        r = requests.post(f"{BASE_URL}/api/marketing/creative/import-brand-asset", headers=h,
                          json={"library_id": "x"}, timeout=30)
        assert r.status_code == 403, r.text[:200]
        r = requests.post(f"{BASE_URL}/api/marketing/creative/director/expand-from-asset/{a['id']}",
                          headers=h, json={}, timeout=30)
        assert r.status_code == 403, r.text[:200]
        # lead can still download the file
        r = requests.get(BASE_URL + a["variants"][0]["url"] + "?download=1", timeout=30)
        assert r.status_code == 200

    def test_generate_with_reference(self):
        a = state.get("upload") or pytest.skip("no upload")
        r = requests.post(f"{BASE_URL}/api/marketing/creative/generate", headers=H(OWNER), json={
            "prompt": "TEST_ energetic gym class poster", "type": "social_post", "n": 2,
            "resolution_preset": "instagram_square", "reference_asset_ids": [a["id"]],
        }, timeout=180)
        assert r.status_code == 200, r.text[:300]
        g = r.json()["asset"]
        assert g["source"] == "gemini-3.1-flash-image-preview"
        assert g["reference_count"] == 1
        assert len(g["variants"]) >= 1
        _check_variants(g)
        for v in g["variants"]:
            assert v["url"].startswith("/api/marketing/creative/file/")
            assert v["token"] and v["mime"].startswith("image/")
            f = requests.get(BASE_URL + v["url"], timeout=30)
            assert f.status_code == 200 and f.headers["content-type"].startswith("image/")
            assert len(f.content) > 1000
        state["gen"] = g
        print("variants:", len(g["variants"]))

    def test_generated_in_list(self):
        g = state.get("gen") or pytest.skip("no gen")
        r = requests.get(f"{BASE_URL}/api/marketing/creative", headers=H(LEAD), timeout=60)
        ids = [x["id"] for x in r.json()["assets"]]
        assert g["id"] in ids

    def test_owner_delete_upload(self):
        a = state.get("upload") or pytest.skip("no upload")
        r = requests.delete(f"{BASE_URL}/api/marketing/creative/{a['id']}", headers=H(OWNER), timeout=30)
        assert r.status_code == 200 and r.json()["deleted"] is True
        r = requests.delete(f"{BASE_URL}/api/marketing/creative/{a['id']}", headers=H(OWNER), timeout=30)
        assert r.status_code == 404
        r = requests.get(f"{BASE_URL}/api/marketing/creative", headers=H(OWNER), timeout=60)
        assert a["id"] not in [x["id"] for x in r.json()["assets"]]
        # file of deleted asset no longer served
        r = requests.get(BASE_URL + a["variants"][0]["url"], timeout=30)
        assert r.status_code == 404
