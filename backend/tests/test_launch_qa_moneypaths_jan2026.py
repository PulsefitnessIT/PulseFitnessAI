"""Launch QA — money/critical paths (Jan 2026).

Focus: Auth (master, operator, CRM, site-restricted manager), CRM data
scoping, Memberships list/create, monthly invoice generation + PDF.

NOTE: /api/auth/login is rate-limited. We reuse tokens aggressively via
module-scoped fixtures and space fresh logins by ~35 s.
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests


def _load_backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        try:
            with open("/app/frontend/.env", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE_URL = _load_backend_url()
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"
MANAGER_EMAIL = "manager@isodemo.com"
MANAGER_PASSWORD = "IsoDemo123!"

SITE_A = "iso-demo-site-a"
SITE_B = "iso-demo-site-b"

LOGIN_SPACING_SEC = 35  # avoid 429

_last_login_ts = [0.0]


def _wait_before_login():
    delta = time.time() - _last_login_ts[0]
    if delta < LOGIN_SPACING_SEC:
        time.sleep(LOGIN_SPACING_SEC - delta + 1)
    _last_login_ts[0] = time.time()


def _platform_login(email: str, password: str) -> requests.Response:
    _wait_before_login()
    return requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def master_token():
    r = _platform_login(MASTER_EMAIL, MASTER_PASSWORD)
    assert r.status_code == 200, f"master login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in master login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def owner_token():
    r = _platform_login(OWNER_EMAIL, OWNER_PASSWORD)
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def manager_token():
    r = _platform_login(MANAGER_EMAIL, MANAGER_PASSWORD)
    assert r.status_code == 200, f"manager login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def owner_crm_token():
    _wait_before_login()
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"crm login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok, f"no crm token: {body}"
    return tok


def _auth(tok: str, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {tok}"}
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

class TestAuth:
    def test_master_login_and_me(self, master_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth(master_token), timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("email", "").lower() == MASTER_EMAIL
        assert d.get("is_master_admin") is True or d.get("role") == "master_admin" or "master" in str(d.get("role", "")).lower()

    def test_owner_login_and_me_module_access(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth(owner_token), timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("email", "").lower() == OWNER_EMAIL
        # org_module_access should be present (per problem statement)
        assert "org_module_access" in d, f"missing org_module_access in /me: keys={list(d.keys())}"
        mods = d.get("org_module_access") or {}
        # memberships/crm should be enabled for iso-demo-org
        assert isinstance(mods, dict), f"org_module_access should be dict, got {type(mods)}"

    def test_crm_login_returns_distinct_token(self, owner_token, owner_crm_token):
        assert owner_crm_token and owner_token
        assert owner_crm_token != owner_token, "CRM token must be distinct from platform token"

    def test_manager_site_b_denied(self, manager_token):
        # First confirm manager can access site A data
        rA = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=_auth(manager_token, {"X-Site-Id": SITE_A}),
            timeout=20,
        )
        assert rA.status_code == 200, f"manager site A denied unexpectedly: {rA.status_code} {rA.text[:200]}"
        # Site B must be forbidden
        rB = requests.get(
            f"{BASE_URL}/api/memberships/members",
            headers=_auth(manager_token, {"X-Site-Id": SITE_B}),
            timeout=20,
        )
        assert rB.status_code == 403, f"expected 403 site_access_denied, got {rB.status_code}: {rB.text[:300]}"
        body = rB.json() if rB.headers.get("content-type", "").startswith("application/json") else {}
        detail = str(body.get("detail") or body).lower()
        assert "site" in detail and ("access" in detail or "denied" in detail), f"unexpected error detail: {detail}"


# ---------------------------------------------------------------------------
# CRM (v2)
# ---------------------------------------------------------------------------

class TestCRMv2Scope:
    def test_companies_list_org_scoped(self, owner_crm_token):
        r = requests.get(f"{BASE_URL}/api/crm/v2/companies", headers=_auth(owner_crm_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("companies") or data.get("data") or [])
        assert isinstance(rows, list), f"expected list-like response, got: {type(data)} {str(data)[:200]}"
        # All rows should belong to iso-demo-org (if org_id exposed)
        for row in rows[:50]:
            oid = row.get("organization_id") or row.get("org_id")
            if oid is not None:
                assert oid == "iso-demo-org", f"cross-tenant leak: company org_id={oid}"

    def test_opportunities_list(self, owner_crm_token):
        r = requests.get(f"{BASE_URL}/api/crm/v2/opportunities", headers=_auth(owner_crm_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("opportunities") or data.get("data") or [])
        assert isinstance(rows, list)
        for row in rows[:50]:
            oid = row.get("organization_id") or row.get("org_id")
            if oid is not None:
                assert oid == "iso-demo-org", f"cross-tenant leak: opp org_id={oid}"

    def test_platform_token_rejected_on_crm(self, owner_token):
        """A platform (auth/login) token should NOT be accepted by CRM auth guard."""
        r = requests.get(f"{BASE_URL}/api/crm/v2/companies", headers=_auth(owner_token), timeout=20)
        # Either 401/403 accepted — must not return data with a platform token
        assert r.status_code in (401, 403), f"platform token unexpectedly accepted by CRM: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# MEMBERSHIPS list + create
# ---------------------------------------------------------------------------

class TestMemberships:
    def test_list_members_owner(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/memberships/members", headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("members") or [])
        assert isinstance(rows, list)

    def test_create_member_persists(self, owner_token):
        suffix = uuid.uuid4().hex[:10]
        email = f"TEST_qa_{suffix}@example.com"
        payload = {
            "email": email,
            "first_name": "QA",
            "last_name": f"Test-{suffix}",
            "phone": "07000 000000",
            "emergency_contact_phone": "07000 111111",
            "gdpr_consent": True,
            "site_id": SITE_A,
        }
        r = requests.post(
            f"{BASE_URL}/api/memberships/members",
            headers=_auth(owner_token),
            json=payload,
            timeout=30,
        )
        assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:400]}"
        raw = r.json()
        created = raw.get("member") if isinstance(raw, dict) and "member" in raw else raw
        assert created.get("email", "").lower() == email.lower()
        mid = created.get("id")
        assert mid, f"no id returned: {created}"

        # GET back
        g = requests.get(f"{BASE_URL}/api/memberships/members/{mid}", headers=_auth(owner_token), timeout=20)
        assert g.status_code == 200, g.text[:300]
        gr = g.json()
        fetched = gr.get("member") if isinstance(gr, dict) and "member" in gr else gr
        assert fetched.get("email", "").lower() == email.lower()
        assert fetched.get("first_name") == "QA"


# ---------------------------------------------------------------------------
# MEMBERSHIPS BILLING — monthly invoice generation + PDF render
# ---------------------------------------------------------------------------

class TestBilling:
    def test_generate_monthly_invoices_no_500(self, owner_token):
        # Use previous month to maximize the chance we have attendance/data
        import datetime as dt
        today = dt.date.today().replace(day=1)
        prev = (today - dt.timedelta(days=1)).replace(day=1)
        period = prev.strftime("%Y-%m")
        body = {
            "period": period,
            "include_smoothed": True,
            "send_email": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            headers=_auth(owner_token),
            json=body,
            timeout=90,
        )
        # Must not 500; 200 expected. 400/404 acceptable if no data, but not 500.
        assert r.status_code != 500, f"invoice generate 500: {r.text[:500]}"
        assert r.status_code in (200, 201), f"invoice generate status={r.status_code}: {r.text[:400]}"
        data = r.json()
        # If invoices produced, snag one id for PDF verification
        invoice_ids = []
        if isinstance(data, dict):
            for k in ("invoice_ids", "invoices", "created", "results"):
                v = data.get(k)
                if isinstance(v, list):
                    for it in v:
                        iid = it if isinstance(it, str) else (it.get("id") if isinstance(it, dict) else None)
                        if iid:
                            invoice_ids.append(iid)
        pytest.shared_invoice_ids = invoice_ids  # type: ignore[attr-defined]
        # Not asserting count — depends on seed data — but log it.
        print(f"generated {len(invoice_ids)} invoices for period {period}")

    def test_invoice_pdf_renders(self, owner_token):
        """Verify studio_billing._render_invoice_pdf produces valid PDF bytes
        via the sample-statement endpoint (uses the same renderer)."""
        r = requests.get(
            f"{BASE_URL}/api/document-branding/sample.pdf",
            headers=_auth(owner_token),
            timeout=60,
        )
        assert r.status_code == 200, f"sample.pdf failed: {r.status_code} {r.text[:300]}"
        assert r.headers.get("content-type", "").startswith("application/pdf"), \
            f"unexpected content-type: {r.headers.get('content-type')}"
        assert r.content.startswith(b"%PDF"), f"not a PDF (first 16 bytes): {r.content[:16]!r}"
        assert len(r.content) > 500, f"suspiciously small PDF: {len(r.content)} bytes"
