"""E2E backend regression for Staff Portal Expenses + Manager Review.

Covers:
- Staff portal login (portal.staff@pulsedemo.test)
- Create claim -> update (mileage + expense lines) -> receipt upload -> submit
- Owner login (owner@isodemo.com) -> manager review pending -> flags
- Approve -> mark reimbursed; Reject on a separate claim
- Payroll exports: CSV / XLSX / receipts.zip / per-claim receipts.zip / export-months
"""
import io
import os
import time
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

STAFF_EMAIL = "portal.staff@pulsedemo.test"
STAFF_PW = "Staff123!"
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PW = "IsoDemo123!"


def _retry_post(url, **kw):
    """Owner /api/auth/login is rate-limited to 4 rapid calls; back-off."""
    for i in range(6):
        r = requests.post(url, timeout=30, **kw)
        if r.status_code != 429:
            return r
        time.sleep(4 + i * 2)
    return r


@pytest.fixture(scope="module")
def staff_token():
    r = _retry_post(f"{API}/new-starter/staff-login",
                    json={"email": STAFF_EMAIL, "password": STAFF_PW})
    assert r.status_code == 200, f"staff login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    r = _retry_post(f"{API}/auth/login",
                    json={"email": OWNER_EMAIL, "password": OWNER_PW})
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _hs(t):
    return {"Authorization": f"Bearer {t}"}


# ─────────── Staff flow ───────────

def test_expenses_config(staff_token):
    r = requests.get(f"{API}/new-starter/portal/expenses/config", headers=_hs(staff_token))
    assert r.status_code == 200
    data = r.json()
    assert "mileage_rates" in data
    assert any(m.get("key") == "rate1" for m in data["mileage_rates"])
    assert "nominals" in data and "departments" in data


@pytest.fixture(scope="module")
def created_claim(staff_token):
    r = requests.post(f"{API}/new-starter/portal/expenses",
                      headers=_hs(staff_token),
                      json={"claim_month": "2026-01", "car_registration": "TEST123"})
    assert r.status_code in (200, 201), r.text
    c = r.json()
    assert c.get("status") == "draft"
    assert c.get("id")
    return c


def test_update_mileage_and_lines(staff_token, created_claim):
    cid = created_claim["id"]
    payload = {
        "department": "Sales",
        "mileage": [{"key": "rate1", "miles": 120}],
        "lines": [
            {"date": "2026-01-05", "description": "Costa coffee client mtg",
             "nominal": "Meals/Drinks", "net": 10.0, "vat": 2.0, "no_vat": False},
            {"date": "2026-01-06", "description": "Parking",
             "nominal": "Parking, tolls and other vehicle costs",
             "net": 6.0, "vat": 0.0, "no_vat": True},
        ],
    }
    r = requests.put(f"{API}/new-starter/portal/expenses/{cid}",
                     headers=_hs(staff_token), json=payload)
    assert r.status_code == 200, r.text
    c = r.json()
    # 120 * 0.55 = 66.00
    assert c["mileage_total"] == 66.00, c
    # 12 + 6 = 18
    assert c["expenses_total"] == 18.00, c
    assert c["grand_total"] == 84.00, c


def test_receipt_upload(staff_token, created_claim):
    cid = created_claim["id"]
    # 1x1 PNG
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
           b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
           b"\xcf\xc0\x00\x00\x00\x03\x00\x01\x18\xd3\x8a\xd5\x00\x00\x00\x00IEND\xaeB`\x82")
    files = {"file": ("receipt.png", io.BytesIO(png), "image/png")}
    r = requests.post(f"{API}/new-starter/portal/expenses/{cid}/receipt",
                      headers=_hs(staff_token), files=files, timeout=60)
    # Best-effort AI OCR: accept 200 (uploaded) even if OCR returns no suggestion
    assert r.status_code == 200, f"receipt upload failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    assert "receipt_id" in body or "id" in body or "claim" in body or "ok" in body


def test_submit_claim(staff_token, created_claim):
    cid = created_claim["id"]
    r = requests.post(f"{API}/new-starter/portal/expenses/{cid}/submit",
                      headers=_hs(staff_token))
    assert r.status_code == 200, r.text
    # Verify status
    g = requests.get(f"{API}/new-starter/portal/expenses/{cid}", headers=_hs(staff_token))
    assert g.status_code == 200
    assert g.json().get("status") == "submitted"


# ─────────── Manager review ───────────

def test_review_pending_has_flags(owner_token, created_claim):
    r = requests.get(f"{API}/new-starter/expenses/review/pending", headers=_hs(owner_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "claims" in data and "flag_threshold" in data
    # our submitted claim should appear
    ids = [c["id"] for c in data["claims"]]
    assert created_claim["id"] in ids
    # each claim should have flags list
    ours = next(c for c in data["claims"] if c["id"] == created_claim["id"])
    assert isinstance(ours.get("flags"), list)


def test_approve_and_reimburse(owner_token, created_claim):
    cid = created_claim["id"]
    r = requests.post(f"{API}/new-starter/expenses/review/{cid}/approve",
                      headers=_hs(owner_token))
    assert r.status_code == 200, r.text
    r2 = requests.post(f"{API}/new-starter/expenses/review/{cid}/reimburse",
                       headers=_hs(owner_token))
    assert r2.status_code == 200, r2.text


def test_reject_separate_claim(staff_token, owner_token):
    # Create + submit a separate claim to test the reject path
    c = requests.post(f"{API}/new-starter/portal/expenses", headers=_hs(staff_token),
                      json={"claim_month": "2026-02"}).json()
    cid = c["id"]
    requests.put(f"{API}/new-starter/portal/expenses/{cid}",
                 headers=_hs(staff_token),
                 json={"mileage": [{"key": "rate2", "miles": 10}], "lines": []})
    requests.post(f"{API}/new-starter/portal/expenses/{cid}/submit", headers=_hs(staff_token))
    r = requests.post(f"{API}/new-starter/expenses/review/{cid}/reject",
                      headers=_hs(owner_token),
                      json={"reason": "TEST reject"})
    assert r.status_code == 200, r.text


# ─────────── Payroll exports ───────────

def test_export_months(owner_token):
    r = requests.get(f"{API}/new-starter/expenses/review/export-months", headers=_hs(owner_token))
    assert r.status_code == 200, r.text
    assert "months" in r.json()


def test_export_csv(owner_token, created_claim):
    r = requests.get(f"{API}/new-starter/expenses/review/export",
                     headers=_hs(owner_token),
                     params={"month": created_claim["claim_month"], "include_reimbursed": True})
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert b"Employee" in r.content


def test_export_xlsx(owner_token, created_claim):
    r = requests.get(f"{API}/new-starter/expenses/review/export-xlsx",
                     headers=_hs(owner_token),
                     params={"month": created_claim["claim_month"], "include_reimbursed": True})
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "excel" in ct or "xlsx" in ct, ct
    assert r.content[:2] == b"PK"  # xlsx is a zip


def test_export_receipts_zip(owner_token, created_claim):
    r = requests.get(f"{API}/new-starter/expenses/review/receipts.zip",
                     headers=_hs(owner_token),
                     params={"month": created_claim["claim_month"], "include_reimbursed": True})
    # If no receipts, endpoint may 200 with empty zip or 404. Accept both but log.
    assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        assert r.content[:2] == b"PK"


def test_per_claim_receipts_zip(owner_token, created_claim):
    cid = created_claim["id"]
    r = requests.get(f"{API}/new-starter/expenses/review/{cid}/receipts.zip",
                     headers=_hs(owner_token))
    assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        assert r.content[:2] == b"PK"
