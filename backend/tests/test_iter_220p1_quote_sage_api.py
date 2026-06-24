"""Iter 220 P1 — Quote intelligence + Sage 200 export API integration tests.

Hits the live preview backend with CRM admin creds; covers intelligence,
hydration via quote create, Sage meta/validate/export/CSV/exports.
"""
from __future__ import annotations

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://admin-setup-portal.preview.emergentagent.com").rstrip("/")
EMAIL = "admin@gymaxisai.com"
PASSWORD = "MasterAdmin123!"

# --- shared session/token ---


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"CRM login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def products(client):
    """Self-seed two deterministic products: one WITH a Sage code + a
    non-zero price (so price_changed can be exercised), one WITHOUT a Sage
    code. Avoids depending on ambient catalogue state."""
    suffix = uuid.uuid4().hex[:6].upper()
    with_body = {"name": f"TEST Sage Tread {suffix}", "sku": f"TST-WS-{suffix}",
                 "sage_code": f"SAGE-{suffix}", "category": "Equipment",
                 "cost_price": 300, "sell_price": 500, "tax_rate": 20}
    without_body = {"name": f"TEST NoSage Bike {suffix}", "sku": f"TST-NS-{suffix}",
                    "category": "Equipment", "cost_price": 300, "sell_price": 400, "tax_rate": 20}
    rw = client.post(f"{BASE_URL}/api/crm/products", json=with_body, timeout=30)
    assert rw.status_code in (200, 201), f"create with_sage failed: {rw.status_code} {rw.text[:300]}"
    rn = client.post(f"{BASE_URL}/api/crm/products", json=without_body, timeout=30)
    assert rn.status_code in (200, 201), f"create without_sage failed: {rn.status_code} {rn.text[:300]}"
    with_sage = rw.json()
    without_sage = rn.json()
    with_sage = with_sage.get("product", with_sage)
    without_sage = without_sage.get("product", without_sage)
    assert (with_sage.get("sage_code") or "").strip(), f"sage_code not saved: {with_sage}"
    return {"with_sage": with_sage, "without_sage": without_sage}


@pytest.fixture(scope="module")
def created_quote(client, products):
    """Create a quote with one line that has sage_code product and one without."""
    payload = {
        "quote_number": f"TEST-Q-{uuid.uuid4().hex[:6].upper()}",
        "title": "TEST_Iter220 Sage Export",
        "lines": [
            {"product_id": products["with_sage"]["id"], "quantity": 2, "unit_price": 150.0},
            {"product_id": products["without_sage"]["id"], "quantity": 1, "unit_price": 99.99},
        ],
        "vat_rate": 20,
    }
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"Create quote failed: {r.status_code} {r.text[:400]}"
    q = r.json()
    if "quote" in q:
        q = q["quote"]
    assert q.get("id"), f"No quote id: {q}"
    return q


# ── Hydration on create ─────────────────────────────────────────────


def test_quote_create_hydrates_lines(client, created_quote, products):
    # No single GET endpoint exists — fetch via list and filter by id.
    r = client.get(f"{BASE_URL}/api/crm/v2/quotes?limit=100", timeout=30)
    assert r.status_code == 200, r.text
    quotes = r.json().get("quotes", [])
    q = next((qq for qq in quotes if qq.get("id") == created_quote["id"]), None)
    assert q, f"Created quote {created_quote['id']} not found in list"
    lines = q.get("lines") or []
    assert len(lines) >= 2
    # Verify sku + sage_code snapshot
    skus = [ln.get("sku") for ln in lines]
    assert products["with_sage"].get("sku") in skus, f"with_sage sku not snapshotted: {skus}"
    assert products["without_sage"].get("sku") in skus
    # The with_sage line should carry sage_code
    line_with_sage = next(ln for ln in lines if ln.get("sku") == products["with_sage"]["sku"])
    assert (line_with_sage.get("sage_code") or "") == (products["with_sage"].get("sage_code") or ""), \
        f"sage_code not hydrated: line={line_with_sage.get('sage_code')} vs prod={products['with_sage'].get('sage_code')}"
    # Rep's unit_price preserved
    assert float(line_with_sage.get("unit_price")) == 150.0


# ── Intelligence endpoint ───────────────────────────────────────────


def test_intelligence_flags_missing_sage_and_price_changed(client, products):
    """Quoted unit_price != catalogue sell_price → price_changed flag.
       Missing sage_code product → missing_sage flag."""
    catalogue_with = float(products["with_sage"].get("sell_price") or 0) or 100.0
    body = {
        "lines": [
            {"product_id": products["with_sage"]["id"], "description": "Tread",
             "quantity": 1, "unit_price": catalogue_with + 50.0, "cost_price": 10.0},
            {"product_id": products["without_sage"]["id"], "description": "Bike",
             "quantity": 1, "unit_price": 99.99, "cost_price": 10.0},
            # missing description case
            {"product_id": products["with_sage"]["id"], "description": "",
             "quantity": 1, "unit_price": catalogue_with, "cost_price": 10.0},
        ]
    }
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes/intelligence", json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "lines" in data and "totals" in data and "suggestions" in data
    assert "margin_threshold" in data and "sage_ready" in data
    totals = data["totals"]
    # Missing sage from the without_sage product line
    assert totals["missing_sage"] >= 1
    # Price changed because unit_price != catalogue sell_price
    assert totals["price_changed"] >= 1
    # missing_description flag should be present somewhere
    all_codes = [f["code"] for ln in data["lines"] for f in ln["flags"]]
    assert "missing_description" in all_codes
    assert data["sage_ready"] is False  # because missing_sage + missing_description


# ── Sage meta PUT ───────────────────────────────────────────────────


def test_sage_meta_persists(client, created_quote):
    r = client.put(
        f"{BASE_URL}/api/crm/v2/quotes/{created_quote['id']}/sage/meta",
        json={"sage_account_ref": "TEST-ACCT-001", "sage_default_nominal": "4000", "sage_ack_obsolete": False},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out.get("updated") is True
    assert out.get("sage_account_ref") == "TEST-ACCT-001"
    assert out.get("sage_default_nominal") == "4000"
    # Verify GET sees it (via list)
    r2 = client.get(f"{BASE_URL}/api/crm/v2/quotes?limit=100", timeout=30)
    quotes = r2.json().get("quotes", [])
    q = next((qq for qq in quotes if qq.get("id") == created_quote["id"]), None)
    assert q, "Quote not found in list"
    assert q.get("sage_account_ref") == "TEST-ACCT-001"
    assert q.get("sage_default_nominal") == "4000"


# ── Validate (should FAIL because one line is missing sage_code) ────


def test_validate_fails_when_line_missing_sage(client, created_quote):
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes/{created_quote['id']}/sage/validate", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    rep = body["report"]
    assert rep["ready"] is False
    assert any("Sage" in e or "sage" in e for e in rep["errors"]), f"No sage error: {rep['errors']}"
    assert body["sage_status"] == "validation_failed"


# ── Export should 422 when validation failing ───────────────────────


def test_export_blocked_when_validation_fails(client, created_quote):
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes/{created_quote['id']}/sage/export", timeout=30)
    assert r.status_code == 422, r.text
    body = r.json()
    detail = body.get("detail") or body
    if isinstance(detail, dict):
        assert "errors" in detail
        assert any("Sage" in e or "sage" in e for e in detail.get("errors") or [])


# ── Build a CLEAN quote (only product with sage_code) → end-to-end ──


@pytest.fixture(scope="module")
def clean_quote(client, products):
    payload = {
        "quote_number": f"TEST-Q-{uuid.uuid4().hex[:6].upper()}",
        "title": "TEST_Iter220 Clean Sage Export",
        "lines": [
            {"product_id": products["with_sage"]["id"], "quantity": 2, "unit_price": 150.0},
        ],
        "vat_rate": 20,
    }
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    q = r.json()
    if "quote" in q:
        q = q["quote"]
    # Set sage meta
    client.put(
        f"{BASE_URL}/api/crm/v2/quotes/{q['id']}/sage/meta",
        json={"sage_account_ref": "TESTACCT-CLEAN", "sage_default_nominal": "4000"},
        timeout=30,
    )
    return q


def test_clean_quote_validate_ready(client, clean_quote):
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes/{clean_quote['id']}/sage/validate", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    rep = body["report"]
    assert rep["ready"] is True, f"Clean quote not ready: errors={rep['errors']}"
    assert body["sage_status"] == "ready_for_sage"
    assert rep["account_ref"] == "TESTACCT-CLEAN"
    assert rep["net_total"] > 0


def test_clean_quote_export_returns_record(client, clean_quote):
    r = client.post(f"{BASE_URL}/api/crm/v2/quotes/{clean_quote['id']}/sage/export", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    rec = body["export"]
    assert rec["status"] == "exported"
    assert rec["pushed_to_sage"] is False
    assert rec["line_count"] == 1
    assert rec["net_total"] == 300.0  # 2 * 150
    assert rec["vat_total"] == 60.0   # 20% of 300
    assert rec["gross_total"] == 360.0
    assert "note" in rec
    assert rec["account_ref"] == "TESTACCT-CLEAN"


def test_clean_quote_csv_download(client, clean_quote):
    r = client.get(f"{BASE_URL}/api/crm/v2/quotes/{clean_quote['id']}/sage/export.csv", timeout=30)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "").lower()
    csv_text = r.text
    expected_header = "QuoteNumber,AccountRef,ProductCode,SageItemCode,Description,Quantity,UnitPrice,DiscountPercent,NetAmount,VATCode,NominalCode"
    assert csv_text.splitlines()[0] == expected_header
    # Body row contains T1 vat code + nominal 4000
    body_line = csv_text.splitlines()[1]
    assert "T1" in body_line
    assert "4000" in body_line
    assert "TESTACCT-CLEAN" in body_line


def test_clean_quote_exports_history(client, clean_quote):
    r = client.get(f"{BASE_URL}/api/crm/v2/quotes/{clean_quote['id']}/sage/exports", timeout=30)
    assert r.status_code == 200, r.text
    exports = r.json().get("exports") or []
    assert len(exports) >= 1
    assert exports[0]["status"] == "exported"
    # Ensure csv not leaking on the list endpoint
    assert "csv" not in exports[0]
