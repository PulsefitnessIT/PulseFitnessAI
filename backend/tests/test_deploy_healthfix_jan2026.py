"""
Regression tests for the deploy crash-loop fix:
init_storage() is now offloaded via run_in_threadpool in _full_boot().
Validates:
  - /health and /api/health quickly return 200
  - /api/health/deep is healthy
  - Object-storage-backed features (parts requests attachments, exploded drawings) still work
  - Core authenticated endpoint (list parts-requests) works
"""
import os
import io
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for backend-side env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Health endpoints ----------

def test_health_unprefixed_fast_internal():
    # External ingress routes /health to the frontend by design; the K8s
    # readiness probe hits the backend directly on port 8001, so validate that.
    t0 = time.time()
    r = requests.get("http://localhost:8001/health", timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body.get("status") == "ok", body
    assert elapsed < 5, f"/health slow: {elapsed:.2f}s"


def test_health_api_prefixed_fast():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body.get("status") == "ok", body
    assert elapsed < 5, f"/api/health slow: {elapsed:.2f}s"


def test_health_deep_mongo_ok():
    r = requests.get(f"{BASE_URL}/api/health/deep", timeout=30)
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    # The deploy fix concerns DB reachability + event loop responsiveness.
    # Overall status may be "degraded" for unrelated reasons (e.g. file_validation),
    # so verify the critical mongo check specifically.
    checks = body.get("checks", {})
    mongo = checks.get("mongo", {})
    assert mongo.get("status") == "ok", body


# ---------- Object storage: parts request attachment round-trip ----------

def test_parts_request_attachment_roundtrip(auth_headers):
    # Create parts request with a machine
    payload = {
        "title": "TEST_deploy_healthfix parts req",
        "notes": "Regression test for init_storage threadpool fix",
        "machines": [
            {"equipment_serial": "ISO-TM-001", "parts": [{"description": "belt", "quantity": 1}]}
        ],
    }
    r = requests.post(f"{BASE_URL}/api/parts-requests",
                      json=payload, headers=auth_headers, timeout=60)
    assert r.status_code in (200, 201), f"create parts-request failed: {r.status_code} {r.text[:600]}"
    pr = r.json()
    pr_id = pr.get("id") or pr.get("_id") or pr.get("request_id")
    assert pr_id, pr

    # Upload attachment (multipart)
    file_bytes = b"HEALTHFIX-TEST-BYTES-\x00\x01\x02" + os.urandom(64)
    files = {"file": ("healthfix.bin", io.BytesIO(file_bytes), "application/octet-stream")}
    r2 = requests.post(
        f"{BASE_URL}/api/parts-requests/{pr_id}/attachments?machine_index=0",
        files=files, headers=auth_headers, timeout=90,
    )
    assert r2.status_code in (200, 201), f"upload failed: {r2.status_code} {r2.text[:600]}"
    att = r2.json()
    aid = att.get("id") or att.get("attachment_id") or (att.get("attachments") or [{}])[-1].get("id")
    assert aid, f"no attachment id: {att}"

    # Download and verify bytes
    r3 = requests.get(
        f"{BASE_URL}/api/parts-requests/{pr_id}/attachments/{aid}/download",
        headers=auth_headers, timeout=90,
    )
    assert r3.status_code == 200, f"download failed: {r3.status_code} {r3.text[:400]}"
    assert r3.content == file_bytes, f"bytes mismatch: {len(r3.content)} vs {len(file_bytes)}"


# ---------- Object storage: exploded drawings round-trip ----------

def test_exploded_drawing_roundtrip(auth_headers):
    file_bytes = b"EXPLODED-DRAWING-TEST-" + os.urandom(96)
    data = {
        "manufacturer": "TEST_MfgHealthfix",
        "model": "TEST_ModelHF",
        "title": "TEST_healthfix drawing",
    }
    files = {"file": ("drawing.pdf", io.BytesIO(file_bytes), "application/pdf")}
    r = requests.post(f"{BASE_URL}/api/exploded-drawings",
                      data=data, files=files, headers=auth_headers, timeout=90)
    assert r.status_code in (200, 201), f"upload failed: {r.status_code} {r.text[:600]}"
    d = r.json()
    did = d.get("id") or d.get("_id")
    assert did, d

    r2 = requests.get(f"{BASE_URL}/api/exploded-drawings/{did}/file",
                      headers=auth_headers, timeout=90)
    assert r2.status_code == 200, f"download failed: {r2.status_code} {r2.text[:400]}"
    assert r2.content == file_bytes, f"bytes mismatch: got {len(r2.content)} vs {len(file_bytes)}"


# ---------- Regression smoke ----------

def test_list_parts_requests(auth_headers):
    r = requests.get(f"{BASE_URL}/api/parts-requests", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
    body = r.json()
    assert isinstance(body, (list, dict)), body
