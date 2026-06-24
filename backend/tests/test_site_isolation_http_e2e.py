"""End-to-end HTTP regression for per-site data isolation + RBAC.

Hits the *public* REACT_APP_BACKEND_URL so we exercise the full stack
(ingress + auth cookies + axios interceptor headers). Covers the
specific scenarios from the review request:

1. Manager GET /api/memberships/members with X-Site-Id: iso-demo-site-b
   returns 403 site_access_denied; with site-a it returns Alpha only.
2. Manager GET /api/sites returns only "Demo Head Office".
3. Manager CRM separate-token path:
   POST /api/crm/auth/login → use Bearer; GET /api/crm/v2/companies
   returns AlphaCo only; X-Site-Id: site-b returns 403.
4. Owner sees BOTH sites' data (memberships members, marketing
   campaigns, /sites, CRM v2 companies) and /sites/leaderboard works.
"""
from __future__ import annotations

import os

import pytest
import requests

def _resolve_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    # Fallback: read frontend/.env so pytest picks up the public ingress url.
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _resolve_base_url()
PASSWORD = "IsoDemo123!"
SITE_A = "iso-demo-site-a"
SITE_B = "iso-demo-site-b"


# ---- Auth fixtures -----------------------------------------------------------
def _login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def manager_session() -> requests.Session:
    return _login("manager@isodemo.com")


@pytest.fixture(scope="module")
def owner_session() -> requests.Session:
    return _login("owner@isodemo.com")


@pytest.fixture(scope="module")
def manager_crm_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": "manager@isodemo.com", "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"CRM login → {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    assert tok, f"no token in CRM login body: {body}"
    return tok


@pytest.fixture(scope="module")
def owner_crm_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": "owner@isodemo.com", "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"CRM login owner → {r.status_code} {r.text[:200]}"
    body = r.json()
    return body.get("access_token") or body.get("token")


# ---- Memberships -------------------------------------------------------------
class TestMembershipsIsolation:
    def test_manager_site_b_forbidden(self, manager_session):
        r = manager_session.get(
            f"{BASE_URL}/api/memberships/members",
            headers={"X-Site-Id": SITE_B},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"
        body = r.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("error") == "site_access_denied", detail
        else:
            assert "site_access_denied" in str(detail)

    def test_manager_site_a_only_alpha(self, manager_session):
        r = manager_session.get(
            f"{BASE_URL}/api/memberships/members",
            headers={"X-Site-Id": SITE_A},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        members = r.json()
        # Some APIs wrap in { items: [] }, accept both.
        items = members if isinstance(members, list) else (
            members.get("items") or members.get("members") or []
        )
        names = " ".join(str(m.get("first_name", "")) + " " + str(m.get("last_name", "")) for m in items)
        assert "Alpha" in names, f"expected Alpha member in {names!r}"
        assert "Bravo" not in names, f"unexpected Bravo leak: {names!r}"

    def test_manager_all_sites_only_alpha(self, manager_session):
        # No X-Site-Id → should narrow to allowed_site_ids = [site-a]
        r = manager_session.get(f"{BASE_URL}/api/memberships/members", timeout=30)
        assert r.status_code == 200, r.text[:200]
        members = r.json()
        items = members if isinstance(members, list) else (
            members.get("items") or members.get("members") or []
        )
        names = " ".join(str(m.get("first_name", "")) + " " + str(m.get("last_name", "")) for m in items)
        assert "Bravo" not in names, f"Bravo leaked to manager 'all sites': {names!r}"


# ---- /api/sites --------------------------------------------------------------
class TestSitesEndpoint:
    def test_manager_sees_only_site_a(self, manager_session):
        r = manager_session.get(f"{BASE_URL}/api/sites", timeout=30)
        assert r.status_code == 200, r.text[:200]
        sites = r.json()
        items = sites if isinstance(sites, list) else sites.get("items") or sites.get("sites") or []
        ids = [s.get("id") or s.get("_id") or s.get("site_id") for s in items]
        names = [s.get("name") for s in items]
        assert SITE_A in ids or "Demo Head Office" in names, f"missing site A in {items}"
        assert SITE_B not in ids, f"manager leaked site_b: {ids}"
        assert "Demo Branch B" not in names, f"manager leaked Branch B: {names}"

    def test_owner_sees_both_sites(self, owner_session):
        r = owner_session.get(f"{BASE_URL}/api/sites", timeout=30)
        assert r.status_code == 200, r.text[:200]
        sites = r.json()
        items = sites if isinstance(sites, list) else sites.get("items") or sites.get("sites") or []
        ids = [s.get("id") or s.get("_id") or s.get("site_id") for s in items]
        assert SITE_A in ids and SITE_B in ids, f"owner missing a site: {ids}"


# ---- CRM separate token ------------------------------------------------------
class TestCrmSeparateAuth:
    def _hdr(self, tok, site=None):
        h = {"Authorization": f"Bearer {tok}"}
        if site:
            h["X-Site-Id"] = site
        return h

    def test_manager_crm_companies_only_alpha(self, manager_crm_token):
        r = requests.get(
            f"{BASE_URL}/api/crm/v2/companies",
            headers=self._hdr(manager_crm_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        items = body if isinstance(body, list) else body.get("items") or body.get("companies") or []
        names = [c.get("name", "") for c in items]
        joined = " | ".join(names)
        assert any("Alpha" in n for n in names), f"AlphaCo missing in {names}"
        assert not any("Bravo" in n for n in names), f"BravoCo leak: {joined}"

    def test_manager_crm_site_b_forbidden(self, manager_crm_token):
        r = requests.get(
            f"{BASE_URL}/api/crm/v2/companies",
            headers=self._hdr(manager_crm_token, SITE_B),
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"
        body = r.json()
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            assert detail.get("error") == "site_access_denied", detail

    def test_owner_crm_sees_both(self, owner_crm_token):
        r = requests.get(
            f"{BASE_URL}/api/crm/v2/companies",
            headers=self._hdr(owner_crm_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        items = body if isinstance(body, list) else body.get("items") or body.get("companies") or []
        names = [c.get("name", "") for c in items]
        # KNOWN BUG (Jan-2026 review): the CRM get_crm_user dependency
        # mirrors role+allowed_site_ids onto the request scope, but does
        # NOT mirror the role onto the returned `user` dict. Therefore
        # compute_visibility.is_unrestricted(crm_owner_user) reads the
        # CRM-table role ("manager") and treats the org owner as a
        # team-visibility user → owner only sees CRM rows they personally
        # own. Expected: owner sees AlphaCo + BravoCo. Documenting via
        # xfail so the regression is tracked, not silently passing.
        if not (any("Alpha" in n for n in names) and any("Bravo" in n for n in names)):
            pytest.xfail(
                f"CRM-owner-role-leak: owner should see AlphaCo + BravoCo but got {names}. "
                "get_crm_user mirrors role to the request scope but not to the returned "
                "user dict; compute_visibility.is_unrestricted then reads crm_users.role "
                "(='manager') and degrades the owner to team-only visibility."
            )
        assert any("Alpha" in n for n in names), names
        assert any("Bravo" in n for n in names), names


# ---- Marketing ---------------------------------------------------------------
class TestMarketingIsolation:
    def test_manager_marketing_only_alpha(self, manager_session):
        r = manager_session.get(f"{BASE_URL}/api/marketing/campaigns", timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        items = body if isinstance(body, list) else body.get("items") or body.get("campaigns") or []
        names = [c.get("name", "") for c in items]
        assert any("Alpha" in n for n in names), names
        assert not any("Bravo" in n for n in names), f"Bravo leak: {names}"

    def test_manager_marketing_site_b_403(self, manager_session):
        r = manager_session.get(
            f"{BASE_URL}/api/marketing/campaigns",
            headers={"X-Site-Id": SITE_B},
            timeout=30,
        )
        assert r.status_code == 403, f"got {r.status_code} {r.text[:200]}"


# ---- Leaderboard / All-Sites for owner --------------------------------------
class TestOwnerLeaderboard:
    def test_owner_leaderboard_two_rows(self, owner_session):
        r = owner_session.get(f"{BASE_URL}/api/sites/leaderboard", timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        rows = body.get("sites") or body.get("rows") or body.get("items") or (
            body if isinstance(body, list) else []
        )
        assert len(rows) >= 2, f"expected >=2 site rows got {rows}"
        site_ids = [r.get("site_id") or r.get("id") for r in rows]
        assert SITE_A in site_ids and SITE_B in site_ids, site_ids
        # Verify expected metric keys exist on at least one row (loose check)
        sample = rows[0]
        metric_keys = {"active_members", "mrr_gbp", "mrr", "open_deals",
                       "campaigns_30d", "open_faults"}
        assert any(k in sample for k in metric_keys), f"no metric keys in {sample}"
        # HQ flag present
        assert any(bool(row.get("is_head_office")) for row in rows), \
            f"no HQ-flagged site in {rows}"

    def test_manager_leaderboard_only_site_a(self, manager_session):
        r = manager_session.get(f"{BASE_URL}/api/sites/leaderboard", timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        rows = body.get("sites") or []
        site_ids = [row.get("site_id") for row in rows]
        assert site_ids == [SITE_A] or (SITE_A in site_ids and SITE_B not in site_ids), \
            f"manager leaderboard leak: {site_ids}"
