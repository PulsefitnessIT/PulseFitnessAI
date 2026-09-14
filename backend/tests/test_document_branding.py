"""Backend tests for Document Branding API + membership sample PDF."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = ("owner@isodemo.com", "IsoDemo123!")
MANAGER = ("manager@isodemo.com", "IsoDemo123!")


def _login(email, password, retries=3):
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token") or r.json().get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    pytest.skip(f"Login rate-limited for {email}")


@pytest.fixture(scope="module")
def owner_token():
    tok = _login(*OWNER)
    time.sleep(2)
    return tok


@pytest.fixture(scope="module")
def manager_token():
    time.sleep(35)
    tok = _login(*MANAGER)
    time.sleep(2)
    return tok


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---- GET /api/document-branding (owner) ----
def test_get_document_branding_owner(owner_token):
    r = requests.get(f"{API}/document-branding", headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "profile" in data and "placeholders" in data and "can_edit" in data
    assert data["can_edit"] is True
    # Pulse defaults exposed as placeholders (never persisted)
    assert data["placeholders"].get("bank_account_number") == "40023205"
    assert "pulse" in (data["placeholders"].get("email") or "").lower()


# ---- PUT for owner: persist a field ----
def test_put_document_branding_owner_persists(owner_token):
    payload = {
        "company_name": "IsoDemo Fitness Ltd",
        "bank_account_number": "12345678",
        "bank_sort_code": "20-00-00",
        "bank_name": "Owner Test Bank",
        "email": "owner-test@isodemo.com",
    }
    r = requests.put(f"{API}/document-branding", json=payload, headers=_h(owner_token), timeout=20)
    assert r.status_code == 200, r.text
    prof = r.json().get("profile") or {}
    assert prof.get("bank_account_number") == "12345678"

    # Re-GET
    r2 = requests.get(f"{API}/document-branding", headers=_h(owner_token), timeout=20)
    assert r2.status_code == 200
    prof2 = r2.json().get("profile") or {}
    assert prof2.get("bank_account_number") == "12345678"
    assert prof2.get("company_name") == "IsoDemo Fitness Ltd"


# ---- Manager RBAC ----
def test_get_document_branding_manager_can_edit(manager_token):
    r = requests.get(f"{API}/document-branding", headers=_h(manager_token), timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("can_edit") is True


def test_put_document_branding_manager_persists(manager_token):
    # Manager shares org with owner — this writes to same org profile.
    payload = {"payment_terms": "Net 30 (mgr edit)"}
    r = requests.put(f"{API}/document-branding", json=payload, headers=_h(manager_token), timeout=20)
    assert r.status_code == 200, r.text
    r2 = requests.get(f"{API}/document-branding", headers=_h(manager_token), timeout=20)
    assert r2.json().get("profile", {}).get("payment_terms") == "Net 30 (mgr edit)"


# ---- Sample PDF: tenant bank number appears, Pulse 40023205 does NOT ----
def test_sample_pdf_uses_tenant_bank(owner_token):
    # Ensure tenant number saved
    requests.put(f"{API}/document-branding",
                 json={"bank_account_number": "87654321", "company_name": "IsoDemo Fitness Ltd"},
                 headers=_h(owner_token), timeout=20)
    r = requests.get(f"{API}/document-branding/sample.pdf", headers=_h(owner_token), timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    body = r.content
    assert body[:4] == b"%PDF", "Not a PDF"
    import io, pypdf
    reader = pypdf.PdfReader(io.BytesIO(body))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "87654321" in text, f"Tenant bank number missing. Extracted:\n{text[:2000]}"
    assert "40023205" not in text, "Pulse hard-coded bank number leaked into tenant PDF"
    assert "IsoDemo Fitness" in text, "Tenant company name missing from sample PDF"


# ---- No leaked _id in responses ----
def test_no_mongo_id_in_response(owner_token):
    r = requests.get(f"{API}/document-branding", headers=_h(owner_token), timeout=20)
    data = r.json()
    # ensure no raw mongo _id key in profile
    assert "_id" not in (data.get("profile") or {})
