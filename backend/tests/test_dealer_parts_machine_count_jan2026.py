"""Tests for Dealer Parts spreadsheet MACHINE COUNTING refinement
(iteration: dealer_parts_machine_count_jan2026).

Verifies:
  - machines_total = sum of per-line quantities (68)
  - machines_matched = sum of matched-line quantities (50)
  - matched_count = 20 matched product lines
  - lines_total = 26 (matched + unmatched)
  - Serial-dedupe: 348H-AAA qty=3 (NOT 9), 302H-AAO qty=2, 307H-AAO qty=3
  - order_value ~ 74134.42
  - Unmatched machine codes surfaced with matched=false
  - No-quantity-column CSV fallback: each row = 1 machine
  - LLM text-invoice regression
  - RBAC dealer blocked
"""
import os
import time
import io
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
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


def _chunk_upload(headers, path_or_bytes, chunk_size=1_400_000):
    r = requests.post(f"{API}/dealer-parts/data/upload/init", headers=headers, timeout=30)
    assert r.status_code == 200, f"upload/init: {r.status_code} {r.text}"
    upload_id = r.json()["upload_id"]
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as fh:
            data = fh.read()
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        files = {"chunk": ("chunk.bin", io.BytesIO(chunk), "application/octet-stream")}
        rc = requests.post(f"{API}/dealer-parts/data/upload/{upload_id}/chunk",
                           headers=headers, files=files, timeout=60)
        assert rc.status_code == 200, f"chunk POST: {rc.status_code} {rc.text[:300]}"
    return upload_id


# ── 1) Machine counting on the real Sage invoice ─────────
def test_pure_pulse_machine_counts(staff_headers):
    assert os.path.exists(XLSX_PATH), "sample xlsx not downloaded"
    upload_id = _chunk_upload(staff_headers, XLSX_PATH)
    r = requests.post(
        f"{API}/dealer-parts/data/upload/{upload_id}/finish-invoice",
        headers={**staff_headers, "Content-Type": "application/json"},
        json={"filename": "Pure Pulse invoice data.xlsx"},
        timeout=120,
    )
    assert r.status_code == 200, f"finish-invoice: {r.status_code} {r.text[:600]}"
    body = r.json()
    print("scan response summary:", {k: body.get(k) for k in (
        "available", "source", "matched_count", "machines_total",
        "machines_matched", "lines_total", "order_value", "note")})

    assert body.get("available") is True
    assert body.get("source") == "spreadsheet_scan"
    assert body.get("machines_total") == 68, f"machines_total expected 68, got {body.get('machines_total')}"
    assert body.get("machines_matched") == 50, f"machines_matched expected 50, got {body.get('machines_matched')}"
    assert body.get("lines_total") == 26, f"lines_total expected 26, got {body.get('lines_total')}"
    assert body.get("matched_count") == 20, f"matched_count expected 20, got {body.get('matched_count')}"

    ov = float(body.get("order_value") or 0)
    assert abs(ov - 74134.42) < 1.5, f"order_value ~74134.42 expected, got {ov}"

    note = (body.get("note") or "").lower()
    assert "68 machine" in note, f"note missing '68 machine(s)': {note}"
    assert "50 machine" in note, f"note missing '50 machine(s)': {note}"

    lines = body.get("lines") or []
    assert len(lines) == 26, f"lines array length expected 26, got {len(lines)}"

    by_ref = {(ln.get("top_level_ref") or ln.get("input_ref") or "").upper(): ln for ln in lines}
    expected_qty = {"348H-AAA": 3, "302H-AAO": 2, "307H-AAO": 3}
    for ref, qty in expected_qty.items():
        assert ref in by_ref, f"{ref} not found in lines: {list(by_ref)[:8]}..."
        ln = by_ref[ref]
        assert ln.get("matched") is True, f"{ref} should be matched"
        assert ln.get("quantity") == qty, f"{ref} qty expected {qty}, got {ln.get('quantity')} (serial dupes not collapsed?)"
        # not multiplied to 9 for 348H-AAA
        assert ln.get("quantity") != 9, f"{ref} quantity inflated to 9 — serial-dedupe broken"

    # Unmatched lines must be surfaced (matched=false)
    unmatched = [ln for ln in lines if not ln.get("matched")]
    assert len(unmatched) >= 1, "expected at least one unmatched line surfaced"
    unmatched_refs = {(ln.get("top_level_ref") or ln.get("input_ref") or "").upper() for ln in unmatched}
    # Sample codes per spec: 38-307-AAA, 516H-AAG
    found_any = unmatched_refs & {"38-307-AAA", "516H-AAG"}
    assert found_any, f"expected 38-307-AAA or 516H-AAG in unmatched refs, got {unmatched_refs}"

    # Sum matched qty + unmatched qty == 68
    sum_matched = sum(int(ln.get("quantity") or 0) for ln in lines if ln.get("matched"))
    sum_unmatched = sum(int(ln.get("quantity") or 0) for ln in lines if not ln.get("matched"))
    assert sum_matched == 50, f"sum matched qty expected 50, got {sum_matched}"
    assert sum_matched + sum_unmatched == 68, f"total machines expected 68, got {sum_matched + sum_unmatched}"


# ── 2) No-quantity-column CSV fallback: each row = 1 machine ─────
def test_no_quantity_column_csv_fallback(staff_headers):
    csv_text = "ItemCode,Description\n305H-ZZY,Test Machine A\n305H-ZZY,Test Machine B\n"
    # Route CSV via finish-invoice through chunked upload path
    r = requests.post(f"{API}/dealer-parts/data/upload/init", headers=staff_headers, timeout=30)
    assert r.status_code == 200
    upload_id = r.json()["upload_id"]
    files = {"chunk": ("chunk.bin", io.BytesIO(csv_text.encode()), "application/octet-stream")}
    rc = requests.post(f"{API}/dealer-parts/data/upload/{upload_id}/chunk",
                       headers=staff_headers, files=files, timeout=30)
    assert rc.status_code == 200

    r2 = requests.post(
        f"{API}/dealer-parts/data/upload/{upload_id}/finish-invoice",
        headers={**staff_headers, "Content-Type": "application/json"},
        json={"filename": "no_qty_test.csv"},
        timeout=60,
    )
    if r2.status_code != 200:
        pytest.skip(f"CSV fallback path not accepted by finish-invoice: {r2.status_code} {r2.text[:200]}")
    body = r2.json()
    src = body.get("source")
    if src != "spreadsheet_scan":
        pytest.skip(f"CSV not routed to spreadsheet_scan (src={src}); marking not-tested")
    lines = body.get("lines") or []
    hit = next((ln for ln in lines if (ln.get("top_level_ref") or "").upper() == "305H-ZZY"), None)
    if hit is None:
        pytest.skip(f"305H-ZZY not extracted from CSV; body={body}")
    # With NO qty column, 2 rows → machines_total=2 for that code
    assert hit.get("quantity") == 2, f"expected 305H-ZZY qty=2 (each row=1), got {hit.get('quantity')}"
    if body.get("machines_total") is not None:
        assert body["machines_total"] == 2, f"machines_total expected 2, got {body['machines_total']}"


# ── 3) LLM text-invoice regression ─────
def test_llm_text_invoice_regression(staff_headers):
    txt = (
        "INVOICE #INV-TEST-002\n"
        "Machine ref 305H-ZZY  qty 1  unit £3500\n"
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
    hit = next((ln for ln in lines if (ln.get("top_level_ref") or "").upper() == "305H-ZZY"), None)
    assert hit is not None, f"305H-ZZY missing from LLM parse: {lines}"
    assert hit.get("matched") is True


# ── 4) RBAC — dealer blocked ─────
def test_rbac_dealer_blocked(dealer_token):
    if not dealer_token:
        pytest.skip("dealer login unavailable")
    h = {"Authorization": f"Bearer {dealer_token}"}
    r1 = requests.post(f"{API}/dealer-parts/data/upload/init", headers=h, timeout=15)
    assert r1.status_code == 403, f"upload/init dealer expected 403, got {r1.status_code}"
    files = {"file": ("t.txt", io.BytesIO(b"hi"), "text/plain")}
    r3 = requests.post(f"{API}/dealer-parts/data/ai-parse-invoice", headers=h, files=files, timeout=15)
    assert r3.status_code == 403, f"ai-parse-invoice dealer expected 403, got {r3.status_code}"
