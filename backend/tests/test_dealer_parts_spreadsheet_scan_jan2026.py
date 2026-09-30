"""Tests for the Dealer Parts spreadsheet full-sheet scan + chunked invoice upload
(iteration: dealer_parts_spreadsheet_scan_jan2026)."""
import os
import time
import io
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

STAFF_EMAIL = "owner@isodemo.com"
STAFF_PASS = "IsoDemo123!"
DEALER_EMAIL = "portal2@fitline.test"
DEALER_PASS = "DealerDemo123!"

XLSX_PATH = "/tmp/pure_pulse_invoice.xlsx"


def _login(email, password, retries=3):
    last = None
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        last = r
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        break
    pytest.skip(f"login failed for {email}: {last.status_code} {last.text[:200]}")


@pytest.fixture(scope="module")
def staff_token():
    return _login(STAFF_EMAIL, STAFF_PASS)


@pytest.fixture(scope="module")
def dealer_token():
    return _login(DEALER_EMAIL, DEALER_PASS)


@pytest.fixture(scope="module")
def staff_headers(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}


def _chunk_upload(headers, path, chunk_size=1_400_000):
    """upload/init → chunk → returns upload_id."""
    r = requests.post(f"{API}/dealer-parts/data/upload/init", headers=headers, timeout=30)
    assert r.status_code == 200, f"upload/init: {r.status_code} {r.text}"
    upload_id = r.json()["upload_id"]
    with open(path, "rb") as fh:
        data = fh.read()
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        files = {"chunk": ("chunk.bin", io.BytesIO(chunk), "application/octet-stream")}
        rc = requests.post(f"{API}/dealer-parts/data/upload/{upload_id}/chunk",
                           headers=headers, files=files, timeout=60)
        assert rc.status_code == 200, f"chunk POST: {rc.status_code} {rc.text[:300]}"
    return upload_id


# ── 1) Full-sheet spreadsheet scan on the real Sage-export xlsx ─────────
def test_spreadsheet_full_sheet_scan(staff_headers):
    assert os.path.exists(XLSX_PATH), "sample xlsx not downloaded"
    upload_id = _chunk_upload(staff_headers, XLSX_PATH)
    r = requests.post(
        f"{API}/dealer-parts/data/upload/{upload_id}/finish-invoice",
        headers={**staff_headers, "Content-Type": "application/json"},
        json={"filename": "Pure Pulse invoice data.xlsx"},
        timeout=90,
    )
    assert r.status_code == 200, f"finish-invoice: {r.status_code} {r.text[:500]}"
    body = r.json()
    print("scan response summary:", {k: body.get(k) for k in ("available","source","matched_count","order_value")})
    assert body.get("available") is True
    assert body.get("source") == "spreadsheet_scan"
    assert body.get("matched_count") == 20, f"expected 20 matched, got {body.get('matched_count')}"
    ov = float(body.get("order_value") or 0)
    assert abs(ov - 63505.64) < 1.0, f"order_value ~63505.64 expected, got {ov}"

    lines = body.get("lines") or []
    by_ref = {ln.get("top_level_ref") or ln.get("input_ref"): ln for ln in lines}
    for ref, expected_qty in (("348H-AAA", 3), ("695C-AAA", 1), ("302H-AAO", 2)):
        assert ref in by_ref, f"machine {ref} missing from scan; got {list(by_ref)[:5]}..."
        ln = by_ref[ref]
        assert ln.get("matched") is True
        assert ln.get("match_method") == "exact_ref"
        assert ln.get("quantity") == expected_qty, f"{ref} qty expected {expected_qty}, got {ln.get('quantity')}"
        # description present
        assert ln.get("machine_description") or ln.get("description"), f"{ref} missing description"

    # Also confirm no line has an inflated (traceable-serial duplicate) qty for 348H-AAA
    assert by_ref["348H-AAA"]["quantity"] != 9, "traceable-serial duplicates were NOT deduped"

    # Persist upload_id for the temp-file test
    globals()["_LAST_UPLOAD_ID"] = upload_id


# ── 2) Temp file removed after finish-invoice (2nd finish returns 404) ─
def test_finish_invoice_session_consumed(staff_headers):
    uid = globals().get("_LAST_UPLOAD_ID")
    assert uid, "no upload_id available from previous test"
    r = requests.post(
        f"{API}/dealer-parts/data/upload/{uid}/finish-invoice",
        headers={**staff_headers, "Content-Type": "application/json"},
        json={"filename": "Pure Pulse invoice data.xlsx"},
        timeout=30,
    )
    assert r.status_code == 404, f"expected 404 after temp file removal, got {r.status_code} {r.text[:200]}"


# ── 3) LLM path still works for a plain-text invoice with a real BOM ref ─
def test_llm_path_text_invoice(staff_headers):
    txt = (
        "INVOICE #INV-TEST-001\n"
        "Ship to: Fitline\n"
        "Line 1: Machine ref 305H-ZZY   qty 1   unit £3500\n"
        "TOTAL: £3500\n"
    )
    files = {"file": ("invoice.txt", io.BytesIO(txt.encode()), "text/plain")}
    r = requests.post(f"{API}/dealer-parts/data/ai-parse-invoice", headers=staff_headers,
                      files=files, timeout=120)
    assert r.status_code == 200, f"ai-parse-invoice: {r.status_code} {r.text[:400]}"
    body = r.json()
    if not body.get("available"):
        pytest.skip(f"LLM unavailable: {body}")
    lines = body.get("lines") or []
    assert body.get("matched_count", 0) >= 1, f"no matches; body={body}"
    hit = next((ln for ln in lines if (ln.get("top_level_ref") or "").upper() == "305H-ZZY"), None)
    assert hit is not None, f"305H-ZZY line missing from {lines}"
    assert hit.get("matched") is True
    assert hit.get("match_method") == "exact_ref"


# ── 4) RBAC — dealer_user must be blocked on all three endpoints ────────
def test_rbac_dealer_blocked(dealer_token):
    if not dealer_token:
        pytest.skip("dealer login unavailable")
    h = {"Authorization": f"Bearer {dealer_token}"}
    r1 = requests.post(f"{API}/dealer-parts/data/upload/init", headers=h, timeout=15)
    assert r1.status_code == 403, f"upload/init dealer expected 403, got {r1.status_code}"

    r2 = requests.post(f"{API}/dealer-parts/data/upload/nonexistent-id/finish-invoice",
                       headers={**h, "Content-Type": "application/json"},
                       json={"filename": "x.xlsx"}, timeout=15)
    assert r2.status_code == 403, f"finish-invoice dealer expected 403, got {r2.status_code}"

    files = {"file": ("t.txt", io.BytesIO(b"hi"), "text/plain")}
    r3 = requests.post(f"{API}/dealer-parts/data/ai-parse-invoice", headers=h, files=files, timeout=15)
    assert r3.status_code == 403, f"ai-parse-invoice dealer expected 403, got {r3.status_code}"
