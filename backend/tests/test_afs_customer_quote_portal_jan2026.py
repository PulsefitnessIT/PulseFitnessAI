"""Backend tests for Aftersales Customer Quote PDF + Portal Acceptance (Task 1, P0).

Covers:
- CRM: build-quote-from-estate (save), get PDF, mint portal-link.
- Public (no auth): view redacted quote, PDF, accept -> agreement, decline.
- Guards: double accept -> 410, decline-after-accept -> 410, accept-after-decline -> 410.
"""

import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
COMPANY_ID = "iso-cA"

# tiny PNG signature data URL
SIG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAf"
    "kEeYQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": CRM_EMAIL, "password": CRM_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def crm_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


def _build_quote(crm_headers):
    r = requests.post(
        f"{BASE_URL}/api/crm/v2/aftersales/build-quote-from-estate",
        headers=crm_headers,
        json={
            "company_id": COMPANY_ID,
            "contract_type": "gold",
            "pricing_level": "standard",
            "term_years": 1,
            "quote_discount_pct": 0,
            "save": True,
        },
        timeout=60,
    )
    assert r.status_code == 200, f"build-quote failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    qid = data.get("saved_quote_id") or (data.get("quote") or {}).get("id")
    assert qid, f"no saved_quote_id in response: {data}"
    return qid


def _mint_link(crm_headers, qid, valid_days=30, name="Dan Hayes"):
    r = requests.post(
        f"{BASE_URL}/api/crm/v2/aftersales/quotes/{qid}/portal-link",
        headers=crm_headers,
        json={"valid_days": valid_days, "contact_name": name},
        timeout=30,
    )
    assert r.status_code == 200, f"portal-link failed: {r.status_code} {r.text[:400]}"
    return r.json()


class TestCrmSide:
    def test_build_quote(self, crm_headers):
        qid = _build_quote(crm_headers)
        assert isinstance(qid, str) and len(qid) > 3
        pytest.qid = qid  # stash

    def test_crm_pdf(self, crm_headers):
        qid = pytest.qid
        r = requests.get(
            f"{BASE_URL}/api/crm/v2/aftersales/quotes/{qid}/pdf",
            headers=crm_headers,
            timeout=60,
        )
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "").lower()
        assert r.content[:4] == b"%PDF"

    def test_portal_link_mint(self, crm_headers):
        qid = pytest.qid
        data = _mint_link(crm_headers, qid)
        assert "shortcode" in data and data["shortcode"]
        assert "url" in data and data["url"]
        assert "valid_until" in data
        assert data.get("status") == "sent"
        pytest.shortcode = data["shortcode"]


class TestPublicView:
    def test_public_get(self):
        sc = pytest.shortcode
        r = requests.get(f"{BASE_URL}/api/public/afs/quote/{sc}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        for k in [
            "quote_number",
            "company_name",
            "contract_type",
            "grouped_lines",
            "summary",
            "valid_until",
            "expired",
            "portal_status",
        ]:
            assert k in j, f"missing key {k}"
        assert j["expired"] is False
        assert j["portal_status"] in (None, "sent")
        s = j["summary"]
        for k in [
            "final_annual",
            "monthly",
            "term_total",
            "vat_amount",
            "final_annual_inc_vat",
        ]:
            assert k in s

    def test_public_pdf(self):
        sc = pytest.shortcode
        r = requests.get(f"{BASE_URL}/api/public/afs/quote/{sc}/pdf", timeout=60)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "").lower()
        assert r.content[:4] == b"%PDF"


class TestAcceptFlow:
    def test_accept(self, crm_headers):
        sc = pytest.shortcode
        r = requests.post(
            f"{BASE_URL}/api/public/afs/quote/{sc}/accept",
            json={
                "name": "Dan Hayes",
                "note": "Approved via portal test",
                "signature_data_url": SIG_DATA_URL,
            },
            timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert j.get("ok") is True
        assert j.get("quote_number")
        agr_num = j.get("agreement_number") or ""
        assert agr_num.startswith("PF-MA-"), f"unexpected agreement_number: {agr_num}"
        pytest.agreement_number = agr_num

        # Verify agreement created and quote portal_status flipped
        ar = requests.get(
            f"{BASE_URL}/api/crm/v2/aftersales/agreements",
            headers=crm_headers,
            timeout=30,
        )
        assert ar.status_code == 200
        agrs = ar.json()
        items = agrs.get("agreements") if isinstance(agrs, dict) else agrs
        if items is None and isinstance(agrs, dict):
            items = agrs.get("items")
        assert isinstance(items, list)
        match = [a for a in items if a.get("agreement_number") == agr_num]
        assert match, f"agreement {agr_num} not found in list"
        a = match[0]
        assert (a.get("status") or "").lower() == "draft"
        assert (a.get("created_by") or "").startswith("portal:"), a.get("created_by")

        # public view should now show portal_status accepted
        pv = requests.get(f"{BASE_URL}/api/public/afs/quote/{sc}", timeout=30).json()
        assert pv.get("portal_status") == "accepted"

    def test_double_accept_returns_410(self):
        sc = pytest.shortcode
        r = requests.post(
            f"{BASE_URL}/api/public/afs/quote/{sc}/accept",
            json={"name": "Dan Hayes", "signature_data_url": SIG_DATA_URL},
            timeout=30,
        )
        assert r.status_code == 410, f"expected 410, got {r.status_code}: {r.text[:200]}"

    def test_decline_after_accept_returns_410(self):
        sc = pytest.shortcode
        r = requests.post(
            f"{BASE_URL}/api/public/afs/quote/{sc}/decline",
            json={"name": "Dan Hayes", "reason": "nope"},
            timeout=30,
        )
        assert r.status_code == 410


class TestDeclineFlow:
    def test_decline_and_then_accept_410(self, crm_headers):
        # Build a fresh quote + link
        qid = _build_quote(crm_headers)
        link = _mint_link(crm_headers, qid, name="Decliner Dan")
        sc = link["shortcode"]

        r = requests.post(
            f"{BASE_URL}/api/public/afs/quote/{sc}/decline",
            json={"name": "Decliner Dan", "reason": "Budget"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("ok") is True

        pv = requests.get(f"{BASE_URL}/api/public/afs/quote/{sc}", timeout=30).json()
        assert pv.get("portal_status") == "declined"

        r2 = requests.post(
            f"{BASE_URL}/api/public/afs/quote/{sc}/accept",
            json={"name": "Decliner Dan", "signature_data_url": SIG_DATA_URL},
            timeout=30,
        )
        assert r2.status_code == 410
