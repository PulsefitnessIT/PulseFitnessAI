"""Iter 245 — Service Desk brand scoping.

Desk users provisioned with `service_desk_brand == "pulse"` and Pulse
Master Admins see only Pulse-visible customer organisations
(`PULSE_DESK_ACCOUNT_TYPES`) across the cross-org Service Desk surfaces:
summary, customers list/detail/edit, global equipment search, supplier
health, impersonation. GymAxis master admins remain platform-wide.
Out-of-scope orgs return 404 (indistinguishable from non-existent).
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
PULSE_ADMIN = ("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
DESK_AGENT = ("desk@pulsefitness.com", "DeskAgent123!")  # service_desk_brand=pulse

PULSE_DESK_ACCOUNT_TYPES = {
    "pulse_pro", "pulse_lite", "lite",
    "mod", "mod_site", "mod_org", "mod_branch",
    "full",
}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


def _out_of_scope_org_id(master: requests.Session) -> str:
    """Find an org whose account_type is NOT Pulse-visible (master view)."""
    r = master.get(f"{BASE_URL}/api/service-desk/customers?limit=100", timeout=20)
    assert r.status_code == 200, r.text
    for o in r.json()["organizations"]:
        if (o.get("account_type") or "") not in PULSE_DESK_ACCOUNT_TYPES:
            return o["id"]
    raise AssertionError("no out-of-scope org found in first 100 — seed data changed?")


# ── Summary + customers list scoping ─────────────────────────────

def test_master_admin_is_platform_wide():
    s = _login(*MASTER_ADMIN)
    r = s.get(f"{BASE_URL}/api/service-desk/summary", timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["scoped_to_pulse"] is False
    r = s.get(f"{BASE_URL}/api/service-desk/customers?limit=1", timeout=20)
    assert r.json()["scoped_to_pulse"] is False


def test_pulse_admin_summary_and_customers_are_scoped():
    master = _login(*MASTER_ADMIN)
    pulse = _login(*PULSE_ADMIN)
    m = master.get(f"{BASE_URL}/api/service-desk/summary", timeout=20).json()
    p = pulse.get(f"{BASE_URL}/api/service-desk/summary", timeout=20).json()
    assert p["scoped_to_pulse"] is True
    assert p["organizations"]["total"] < m["organizations"]["total"], (
        "pulse scope must exclude the untyped/GymAxis-internal orgs"
    )
    r = pulse.get(f"{BASE_URL}/api/service-desk/customers?limit=100", timeout=20)
    body = r.json()
    assert body["scoped_to_pulse"] is True
    bad = [o for o in body["organizations"]
           if (o.get("account_type") or "") not in PULSE_DESK_ACCOUNT_TYPES]
    assert not bad, f"non-Pulse orgs leaked into a scoped list: {bad[:3]}"


def test_pulse_brand_desk_agent_is_scoped():
    s = _login(*DESK_AGENT)
    r = s.get(f"{BASE_URL}/api/service-desk/customers?limit=5", timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["scoped_to_pulse"] is True


# ── Out-of-scope org → 404 on detail / edit / impersonate / kit ─

def test_out_of_scope_org_is_invisible_to_pulse_users():
    master = _login(*MASTER_ADMIN)
    org_id = _out_of_scope_org_id(master)
    # master admin still sees it
    assert master.get(f"{BASE_URL}/api/service-desk/customers/{org_id}", timeout=20).status_code == 200

    pulse = _login(*PULSE_ADMIN)
    assert pulse.get(f"{BASE_URL}/api/service-desk/customers/{org_id}", timeout=20).status_code == 404
    assert pulse.patch(f"{BASE_URL}/api/service-desk/customers/{org_id}",
                       json={"notes": "x"}, timeout=20).status_code == 404
    assert pulse.post(f"{BASE_URL}/api/service-desk/customers/{org_id}/impersonate",
                      timeout=20).status_code == 404
    assert pulse.get(f"{BASE_URL}/api/service-desk/equipment?org_id={org_id}",
                     timeout=20).status_code == 404


# ── Supplier health scoped flag ──────────────────────────────────

def test_supplier_health_reports_scope():
    pulse = _login(*PULSE_ADMIN)
    r = pulse.get(f"{BASE_URL}/api/service-desk/suppliers/health?days=7", timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["scoped_to_pulse"] is True


# ── Frontend wiring ──────────────────────────────────────────────

def test_desk_customers_shows_scope_badge():
    src = open("/app/frontend/src/pages/ServiceDesk/DeskCustomers.js", encoding="utf-8").read()
    assert "scoped_to_pulse" in src
    assert "desk-scope-pulse-badge" in src
