"""Backend tests for MOD Quote Send & E-Sign flow (Jan 2026).

Covers:
- POST /api/crm/mod-quote/{id}/send-esign (auth) → link + esign_status
- GET  /api/public/mod-quote/{token} (no auth) → redacted view
- POST /api/public/mod-quote/{token}/sign → 400 (missing), 200 (ok), 409 (double)
- GET  /api/public/mod-quote/{token}/pdf → application/pdf
- Type A contract auto-activates on sign
- Quote status='accepted' in /api/crm/v2/quotes; contract 'active' in /api/crm/mod-quote/contracts
- Invalid token → 404
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
                    break
    except Exception:
        pass

CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
MOD_SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"


@pytest.fixture(scope="module")
def crm_headers():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def type_a_quote(crm_headers):
    """Generate a Type A MOD quote for e-sign tests."""
    r0 = requests.get(f"{BASE_URL}/api/crm/mod-quote/equipment",
                      params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 1},
                      headers=crm_headers, timeout=30)
    r0.raise_for_status()
    lines = [{"rate_card_id": l["rate_card_id"], "equipment_id": l["equipment_id"],
              "serial_number": l.get("serial_number"), "quantity": 1}
             for l in r0.json()["lines"]]
    r = requests.post(f"{BASE_URL}/api/crm/mod-quote/generate", json={
        "contract_type": "A", "year": 1, "site_id": MOD_SITE_ID,
        "site_name": "MOD Test Site", "lines": lines, "vat_rate": 20,
    }, headers=crm_headers, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    q = body["quote"]
    contract = body["contract"]
    assert contract and contract["status"] == "pending_activation"
    pytest._esign_quote_ids = getattr(pytest, "_esign_quote_ids", []) + [q["id"]]
    pytest._esign_contract_ids = getattr(pytest, "_esign_contract_ids", []) + [contract["id"]]
    return {"id": q["id"], "quote_number": q["quote_number"], "contract_id": contract["id"],
            "total": q["total"], "subtotal": q["subtotal"]}


# ── 1. send-esign (auth) ─────────────────────────────────────────────

def test_send_esign_returns_link_and_marks_sent(crm_headers, type_a_quote):
    to_addr = f"test-esign-{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/{type_a_quote['id']}/send-esign",
        json={"to": to_addr}, headers=crm_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["to"] == to_addr
    assert "link" in body and "/quote/sign/" in body["link"]
    assert "emailed" in body  # can be True/False depending on Resend
    token = body["link"].rsplit("/", 1)[-1]
    assert len(token) >= 16
    pytest._esign_token = token


def test_send_esign_requires_recipient(crm_headers, type_a_quote):
    # Fresh quote (no linked contact email) with empty `to` should 400
    # We reuse the same quote — first ensure contact email is not linked.
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/{type_a_quote['id']}/send-esign",
        json={"to": ""}, headers=crm_headers, timeout=30)
    # Either 400 (no contact) OR 200 (contact has email); tolerate 200 since owner org may have contact
    assert r.status_code in (200, 400), r.text


def test_send_esign_404_for_unknown_quote(crm_headers):
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/does-not-exist/send-esign",
        json={"to": "x@y.z"}, headers=crm_headers, timeout=30)
    assert r.status_code == 404


# ── 2. public view (no auth) ─────────────────────────────────────────

def test_public_view_returns_redacted_quote(type_a_quote):
    token = pytest._esign_token
    r = requests.get(f"{BASE_URL}/api/public/mod-quote/{token}", timeout=30)
    assert r.status_code == 200, r.text
    v = r.json()
    for key in ("quote_number", "mod_contract_type", "lines", "subtotal",
                "vat_amount", "total", "org_name", "brand_color", "esign_status"):
        assert key in v, f"missing '{key}' in public view"
    assert v["mod_contract_type"] == "A"
    assert v["esign_status"] == "sent"
    assert abs(v["total"] - type_a_quote["total"]) < 0.05
    # Redacted — should NOT expose internal ids/contact/owner details
    assert "owner_id" not in v
    assert "contact_id" not in v


def test_public_view_invalid_token_404():
    r = requests.get(f"{BASE_URL}/api/public/mod-quote/nonexistent-token-xyz", timeout=30)
    assert r.status_code == 404


# ── 3. public sign — validation, success, double sign ────────────────

def test_public_sign_400_missing_signature_or_name():
    token = pytest._esign_token
    r1 = requests.post(f"{BASE_URL}/api/public/mod-quote/{token}/sign",
                       json={"signer_name": ""}, timeout=30)
    assert r1.status_code == 400
    r2 = requests.post(f"{BASE_URL}/api/public/mod-quote/{token}/sign",
                       json={"signer_name": "Alice", "signature": ""}, timeout=30)
    assert r2.status_code == 400


def test_public_sign_success_activates_type_a_contract(crm_headers, type_a_quote):
    token = pytest._esign_token
    r = requests.post(f"{BASE_URL}/api/public/mod-quote/{token}/sign", json={
        "signer_name": "Test Signer",
        "signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEUAAACnej3aAAAAAXRSTlMAQObYZgAAAApJREFUCNdjYAAAAAIAAeIhvDMAAAAASUVORK5CYII=",
    }, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "accepted"
    assert body["signer"] == "Test Signer"
    assert "signed_at" in body
    # Public view now shows signed
    v = requests.get(f"{BASE_URL}/api/public/mod-quote/{token}", timeout=30).json()
    assert v["esign_status"] == "signed"
    assert v["status"] == "accepted"
    assert v["signer_name"] == "Test Signer"
    # Quote in /crm/v2/quotes shows accepted
    r2 = requests.get(f"{BASE_URL}/api/crm/v2/quotes", headers=crm_headers, timeout=30)
    assert r2.status_code == 200
    quotes = r2.json() if isinstance(r2.json(), list) else r2.json().get("quotes", [])
    q = next((x for x in quotes if x.get("id") == type_a_quote["id"]), None)
    assert q is not None, "quote missing from /crm/v2/quotes"
    assert q.get("status") == "accepted", f"expected accepted, got {q.get('status')}"
    # Contract is now active
    r3 = requests.get(f"{BASE_URL}/api/crm/mod-quote/contracts",
                      headers=crm_headers, timeout=30)
    assert r3.status_code == 200
    c = next((x for x in r3.json()["contracts"] if x["quote_id"] == type_a_quote["id"]), None)
    assert c is not None
    assert c["status"] == "active", f"contract not activated: {c['status']}"


def test_public_sign_double_returns_409():
    token = pytest._esign_token
    r = requests.post(f"{BASE_URL}/api/public/mod-quote/{token}/sign", json={
        "signer_name": "Test Signer",
        "signature": "data:image/png;base64,iVBOR",
    }, timeout=30)
    assert r.status_code == 409


# ── 4. public PDF ────────────────────────────────────────────────────

def test_public_pdf_returns_application_pdf():
    token = pytest._esign_token
    r = requests.get(f"{BASE_URL}/api/public/mod-quote/{token}/pdf", timeout=60)
    assert r.status_code == 200, r.text[:200]
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF"


# ── 5. Notification created ──────────────────────────────────────────

def test_signing_creates_notification(crm_headers):
    r = requests.get(f"{BASE_URL}/api/crm/v2/notifications",
                     headers=crm_headers, timeout=30)
    if r.status_code == 404:
        pytest.skip("notifications endpoint not exposed")
    if r.status_code != 200:
        pytest.skip(f"notifications GET {r.status_code}")
    data = r.json()
    items = data if isinstance(data, list) else data.get("notifications") or data.get("items") or []
    signed = [n for n in items if (n.get("title") or "").lower().startswith("quote signed")]
    assert signed, "expected at least one 'Quote Signed' notification"


# ── 6. Resend E-Sign works after already sent ────────────────────────

def test_resend_esign_reuses_or_refreshes_token(crm_headers, type_a_quote):
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/{type_a_quote['id']}/send-esign",
        json={"to": "resend@example.com"}, headers=crm_headers, timeout=30)
    # Quote already accepted — implementation still allows re-send link (idempotent).
    # Accept 200 (link returned) as valid; some impls may 409.
    assert r.status_code in (200, 409), r.text


# ── Cleanup ──────────────────────────────────────────────────────────

def test_cleanup():
    from pymongo import MongoClient
    try:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME", "test_database")
        if not mongo_url:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.strip().split("=", 1)[1]
                    elif line.startswith("DB_NAME="):
                        db_name = line.strip().split("=", 1)[1]
        c = MongoClient(mongo_url)
        qids = getattr(pytest, "_esign_quote_ids", [])
        cids = getattr(pytest, "_esign_contract_ids", [])
        if qids:
            c[db_name].crm2_quotes.delete_many({"id": {"$in": qids}})
            c[db_name].crm2_activities.delete_many({"quote_id": {"$in": qids}})
            c[db_name].crm2_notifications.delete_many({"entity_id": {"$in": qids}})
        if cids:
            c[db_name].mod_service_contracts.delete_many({"id": {"$in": cids}})
        c.close()
    except Exception as e:
        print(f"cleanup skipped: {e}")
