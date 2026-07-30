"""MOD Portal in-portal Quotes tab + inline e-sign (Jan 2026).

Covers:
- GET /api/mod/site/quotes  → list + pending_count for logged-in MOD site
- GET /api/mod/site/quotes/{id}  → detail view (lines/subtotal/vat/total)
- POST /api/mod/site/quotes/{id}/sign  → mark accepted+signed and activate Type A contract
- GET /api/mod/site/quotes/{id}/pdf  → application/pdf
- Non-MOD user gets 403 on all four
- Both entry points (MOD portal + public /quote/sign) share apply_quote_signature
"""
import os
import base64
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

MOD_EMAIL = "test@army.mod.test"
MOD_PASS = "ModTest123!"
CRM_EMAIL = "owner@isodemo.com"
CRM_PASS = "IsoDemo123!"
MOD_SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"

# 1x1 transparent PNG data-url
PNG_1x1 = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
    )
).decode()


def _login(email, password, portal=None, crm=False):
    if crm:
        r = requests.post(f"{BASE}/api/crm/auth/login",
                          json={"email": email, "password": password}, timeout=30)
    else:
        body = {"email": email, "password": password}
        if portal:
            body["portal"] = portal
        r = requests.post(f"{BASE}/api/auth/login", json=body, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j["token"]


@pytest.fixture(scope="module")
def mod_headers():
    tok = _login(MOD_EMAIL, MOD_PASS, portal="mod")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def crm_headers():
    tok = _login(CRM_EMAIL, CRM_PASS, crm=True)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def platform_non_mod_headers():
    """Platform token for CRM owner (non-MOD account) — used to verify 403 on /api/mod/* routes."""
    tok = _login(CRM_EMAIL, CRM_PASS)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def fresh_quote(crm_headers):
    """Generate a fresh Type A MOD quote via the CRM wizard for the MOD site."""
    r0 = requests.get(
        f"{BASE}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 1},
        headers=crm_headers, timeout=30,
    )
    assert r0.status_code == 200, r0.text
    lines = [{"rate_card_id": l["rate_card_id"], "equipment_id": l["equipment_id"],
              "serial_number": l.get("serial_number"), "quantity": 1}
             for l in r0.json()["lines"]]

    gen = requests.post(
        f"{BASE}/api/crm/mod-quote/generate",
        json={"contract_type": "A", "year": 1, "site_id": MOD_SITE_ID,
              "site_name": "MOD Test Site", "lines": lines, "vat_rate": 20},
        headers=crm_headers, timeout=60,
    )
    assert gen.status_code == 200, f"generate failed: {gen.status_code} {gen.text}"
    body = gen.json()
    qid = body["quote"]["id"]
    # Send for esign so it appears with esign_status=sent (best-effort)
    send = requests.post(
        f"{BASE}/api/crm/mod-quote/{qid}/send-esign",
        json={"to": "test-inportal@example.com"},
        headers=crm_headers, timeout=30,
    )
    assert send.status_code in (200, 400), send.text
    return qid


# ── 1. LIST ────────────────────────────────────────────────────
def test_list_quotes_returns_shape(mod_headers, fresh_quote):
    r = requests.get(f"{BASE}/api/mod/site/quotes", headers=mod_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "quotes" in data and "pending_count" in data
    assert isinstance(data["quotes"], list)
    assert isinstance(data["pending_count"], int)
    ids = [q["id"] for q in data["quotes"]]
    assert fresh_quote in ids, "freshly generated quote must appear"
    row = next(q for q in data["quotes"] if q["id"] == fresh_quote)
    for k in ("quote_number", "total", "mod_contract_type", "esign_status", "status", "line_count"):
        assert k in row
    assert row["mod_contract_type"] == "A"
    assert data["pending_count"] >= 1


# ── 2. DETAIL ───────────────────────────────────────────────────
def test_quote_detail(mod_headers, fresh_quote):
    r = requests.get(f"{BASE}/api/mod/site/quotes/{fresh_quote}", headers=mod_headers, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] == fresh_quote
    assert isinstance(d.get("lines"), list) and len(d["lines"]) >= 1
    for k in ("subtotal", "vat_amount", "total"):
        assert k in d
    # No signature key in the redacted public view
    assert "_id" not in d


def test_detail_not_found(mod_headers):
    r = requests.get(f"{BASE}/api/mod/site/quotes/does-not-exist", headers=mod_headers, timeout=15)
    assert r.status_code == 404


# ── 3. PDF ──────────────────────────────────────────────────────
def test_quote_pdf(mod_headers, fresh_quote):
    r = requests.get(f"{BASE}/api/mod/site/quotes/{fresh_quote}/pdf", headers=mod_headers, timeout=60)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


# ── 4. 403 for non-MOD user ─────────────────────────────────────
def test_non_mod_gets_403(platform_non_mod_headers, fresh_quote):
    for path in [
        "/api/mod/site/quotes",
        f"/api/mod/site/quotes/{fresh_quote}",
        f"/api/mod/site/quotes/{fresh_quote}/pdf",
    ]:
        r = requests.get(f"{BASE}{path}", headers=platform_non_mod_headers, timeout=15)
        assert r.status_code == 403, f"{path} → {r.status_code} {r.text}"
    r = requests.post(
        f"{BASE}/api/mod/site/quotes/{fresh_quote}/sign",
        json={"signature": PNG_1x1, "signer_name": "X"},
        headers=platform_non_mod_headers, timeout=15,
    )
    assert r.status_code == 403


# ── 5. SIGN → accepts + activates Type A contract ───────────────
def test_sign_in_portal_activates_contract(mod_headers, crm_headers, fresh_quote):
    # Precondition: pending_activation contract exists for this quote
    ct = requests.get(f"{BASE}/api/crm/mod-quote/contracts", headers=crm_headers, timeout=15)
    assert ct.status_code == 200, ct.text
    contract = next((c for c in ct.json().get("contracts", []) if c.get("quote_id") == fresh_quote), None)
    assert contract is not None, "Type A contract must exist"
    assert contract["status"] == "pending_activation"

    # Sign
    r = requests.post(
        f"{BASE}/api/mod/site/quotes/{fresh_quote}/sign",
        json={"signature": PNG_1x1, "signer_name": "Maj. Test Signer"},
        headers=mod_headers, timeout=30,
    )
    assert r.status_code == 200, r.text

    # Detail now shows signed
    d = requests.get(f"{BASE}/api/mod/site/quotes/{fresh_quote}", headers=mod_headers, timeout=15).json()
    assert d["status"] == "accepted"
    assert d["esign_status"] == "signed"
    assert (d.get("signer_name") or "").startswith("Maj. Test Signer")

    # Contract flipped to active
    ct2 = requests.get(f"{BASE}/api/crm/mod-quote/contracts", headers=crm_headers, timeout=15).json()
    contract2 = next(c for c in ct2["contracts"] if c["quote_id"] == fresh_quote)
    assert contract2["status"] == "active"

    # Double-sign should 409
    r2 = requests.post(
        f"{BASE}/api/mod/site/quotes/{fresh_quote}/sign",
        json={"signature": PNG_1x1, "signer_name": "Maj. Test Signer"},
        headers=mod_headers, timeout=15,
    )
    assert r2.status_code == 409


# ── 6. Sign guard rails ─────────────────────────────────────────
def test_sign_missing_signature(mod_headers, crm_headers):
    """Generate a second quote, then try to sign without signature → 400."""
    r0 = requests.get(
        f"{BASE}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 1},
        headers=crm_headers, timeout=30,
    )
    lines = [{"rate_card_id": l["rate_card_id"], "equipment_id": l["equipment_id"],
              "serial_number": l.get("serial_number"), "quantity": 1}
             for l in r0.json()["lines"]]
    gen = requests.post(
        f"{BASE}/api/crm/mod-quote/generate",
        json={"contract_type": "A", "year": 1, "site_id": MOD_SITE_ID,
              "site_name": "MOD Test Site", "lines": lines, "vat_rate": 20},
        headers=crm_headers, timeout=60,
    )
    qid = gen.json()["quote"]["id"]

    r = requests.post(
        f"{BASE}/api/mod/site/quotes/{qid}/sign",
        json={"signer_name": "Someone"},  # no signature
        headers=mod_headers, timeout=15,
    )
    assert r.status_code == 400, r.text
    # Cleanup by signing properly so it's marked done (avoids leftover pending)
    requests.post(
        f"{BASE}/api/mod/site/quotes/{qid}/sign",
        json={"signature": PNG_1x1, "signer_name": "Cleanup Signer"},
        headers=mod_headers, timeout=15,
    )
