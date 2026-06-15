"""
iter273 — Engineer App full audit for the INDEPENDENT (org-less) partner engineer.

KEY assertion: NO endpoint returns a 403 'Organization context required' for
indie.engineer@gymaxisai.com after login (personal org should auto-provision
via the claim hook).

Also runs two regression logins:
- engineer.smoke@gymaxisai.com (existing org-attached engineer)
- admin@gymaxisai.com (master admin — must not be routed to partner Apply)
"""

import os
import time
import pytest
import requests


def _load_frontend_env_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_frontend_env_url()

INDIE = ("indie.engineer@gymaxisai.com", "IndieEng123!")
ORG_ENG = ("engineer.smoke@gymaxisai.com", "EngTest123!")
ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text[:300]}"
    return s


def _assert_not_org_context_error(r: requests.Response, label: str):
    """Allow 200/404/empty; FAIL only on the specific 403 org-context error."""
    if r.status_code == 403:
        body = r.text or ""
        assert "Organization context required" not in body, (
            f"[{label}] 403 Organization context required for indie engineer: "
            f"{r.request.method} {r.request.url} -> {body[:200]}"
        )


# ---------------- Indie engineer audit ----------------

@pytest.fixture(scope="module")
def indie_session():
    return _login(*INDIE)


def test_indie_login_and_me_returns_org(indie_session):
    r = indie_session.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert r.status_code == 200, r.text
    me = r.json()
    # After claim hook ran, the user should be tied to a personal organization.
    org_id = me.get("organization_id") or me.get("org_id")
    assert org_id, f"indie engineer has no organization_id after login: {me}"


def test_indie_partner_me(indie_session):
    r = indie_session.get(f"{BASE_URL}/api/partners/me", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    # partner record should exist and be approved (per seed)
    assert body.get("status") in ("approved", "active", "trial", "pending"), body


def test_indie_engineer_dashboard_loads(indie_session):
    """Engineer App HOME — the original failure point."""
    r = indie_session.get(f"{BASE_URL}/api/svc/engineer/dashboard", timeout=30)
    _assert_not_org_context_error(r, "engineer.dashboard")
    assert r.status_code == 200, f"dashboard -> {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, dict), data


@pytest.mark.parametrize(
    "path,label",
    [
        ("/api/svc/engineer/me", "engineer.me"),
        ("/api/svc/engineer/jobs?when=today", "engineer.jobs.today"),
        ("/api/svc/engineer/jobs?when=upcoming", "engineer.jobs.upcoming"),
        ("/api/svc/engineer/jobs?when=open", "engineer.jobs.open"),
        ("/api/svc/engineer/visits", "engineer.visits"),
        ("/api/svc/engineer/customers", "engineer.customers"),
        ("/api/svc/engineer/quotes", "engineer.quotes"),
        ("/api/svc/engineer/invoices", "engineer.invoices"),
    ],
)
def test_indie_engineer_app_tabs_no_org_error(indie_session, path, label):
    r = indie_session.get(f"{BASE_URL}{path}", timeout=30)
    _assert_not_org_context_error(r, label)
    # 200 expected; 404 tolerated only if a particular path isn't exposed,
    # but never 403 with org-context error.
    assert r.status_code in (200, 404), f"{label} -> {r.status_code}: {r.text[:200]}"


def test_indie_create_customer_persists(indie_session):
    """Write path: create a customer; must not 403 with org-context error."""
    payload = {
        "name": f"TEST_IndieCust_{int(time.time())}",
        "email": f"indie_cust_{int(time.time())}@example.com",
        "phone": "+447000000001",
    }
    r = indie_session.post(
        f"{BASE_URL}/api/svc/engineer/customers", json=payload, timeout=30
    )
    _assert_not_org_context_error(r, "engineer.customers.create")
    assert r.status_code in (200, 201), f"create customer -> {r.status_code}: {r.text[:300]}"
    created = r.json()
    cust_id = created.get("id") or created.get("_id") or created.get("customer_id")
    assert cust_id, f"no id in created customer: {created}"

    # GET list and confirm it shows up
    r2 = indie_session.get(f"{BASE_URL}/api/svc/engineer/customers", timeout=30)
    assert r2.status_code == 200
    items = r2.json()
    items_list = items if isinstance(items, list) else items.get("items", [])
    names = [c.get("name") for c in items_list if isinstance(c, dict)]
    assert payload["name"] in names, f"created customer not in list: {names[:10]}"


def test_indie_create_quote_no_org_error(indie_session):
    """Optional write: quote create — only assert no org-context 403."""
    payload = {
        "customer_name": f"TEST_IndieQuoteCust_{int(time.time())}",
        "lines": [{"description": "Test line", "qty": 1, "unit_price": 100.0}],
    }
    r = indie_session.post(
        f"{BASE_URL}/api/svc/engineer/quotes", json=payload, timeout=30
    )
    _assert_not_org_context_error(r, "engineer.quotes.create")
    # Accept 200/201 or 400/422 (validation). NEVER 403 org-context.
    assert r.status_code in (200, 201, 400, 404, 422), (
        f"quote create -> {r.status_code}: {r.text[:300]}"
    )


# ---------------- Regressions ----------------

def test_existing_org_engineer_login_and_dashboard():
    s = _login(*ORG_ENG)
    r = s.get(f"{BASE_URL}/api/svc/engineer/dashboard", timeout=30)
    _assert_not_org_context_error(r, "org_engineer.dashboard")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    # Partner /me should also load
    rp = s.get(f"{BASE_URL}/api/partners/me", timeout=20)
    assert rp.status_code == 200


def test_master_admin_login_and_not_partner_apply():
    s = _login(*ADMIN)
    r = s.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert r.status_code == 200, r.text
    me = r.json()
    role = (me.get("role") or "").lower()
    # Master admin has role 'owner' in this app; just confirm NOT partner_engineer
    assert "partner" not in role, f"master admin routed as partner: {me}"
    # Sanity: partners/me should not push them into an Apply state
    rp = s.get(f"{BASE_URL}/api/partners/me", timeout=20)
    # Admin may not have a partner record -> 404 acceptable. 403 acceptable.
    # The critical thing is no 500.
    assert rp.status_code in (200, 401, 403, 404), rp.status_code
