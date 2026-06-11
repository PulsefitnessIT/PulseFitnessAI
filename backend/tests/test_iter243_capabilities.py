"""Iter 243 — Centralised `can(user, capability)` helper + fault-template
role fix for Pulse Master Admins.

Root pattern (3rd occurrence): features hand-listed roles
("owner || manager") and forgot pulse_master_admin. Now:
- Frontend: utils/capabilities.js is the single source of truth;
  LiteDashboardPage, DashboardPage, ReportsSection and
  FaultTemplatesManager consume `can()` instead of inline role lists.
- Backend: fault_templates.py `_can_manage_org_templates` includes
  pulse admins (was a LIVE bug — Pulse Settings → fault templates).
"""

import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()
SRC = "/app/frontend/src"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_pulse_admin_can_manage_org_fault_templates():
    """Backend fix — pulse_master_admin can create + delete ORG-scoped
    fault templates (was 403 'Only owner/manager...')."""
    s = _login("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
    r = s.post(f"{BASE_URL}/api/fault-templates", json={
        "name": f"Iter243 audit {uuid.uuid4().hex[:6]}",
        "machine_type": "Treadmill",
        "issue_description": "Belt slipping under load",
        "severity": "operational_fault",
        "scope": "org",
    }, timeout=30)
    assert r.status_code == 200, f"pulse admin must manage org templates: {r.text}"
    tpl_id = r.json()["id"]
    r = s.delete(f"{BASE_URL}/api/fault-templates/{tpl_id}", timeout=30)
    assert r.status_code == 200, r.text


def test_backend_privileged_roles_include_pulse_admin():
    src = open("/app/backend/routes/fault_templates.py", encoding="utf-8").read()
    assert '"pulse_master_admin"' in src
    assert 'user.get("is_pulse_admin")' in src


def test_capabilities_helper_is_single_source_of_truth():
    src = open(f"{SRC}/utils/capabilities.js", encoding="utf-8").read()
    assert "export const can =" in src
    assert "isPulseAdmin" in src and "pulse_master_admin" in src
    # every declared capability rides the shared managerial rule or an
    # explicit named rule — no anonymous inline role lists.
    for cap in ("manage_operations", "switch_sites", "dismiss_nudges",
                "view_suppliers", "view_capex", "manage_fault_templates"):
        assert f"{cap}:" in src, f"capability {cap} missing from RULES"


def test_consumers_use_can_not_inline_role_lists():
    consumers = {
        f"{SRC}/pages/LiteDashboardPage.js": "can(user, 'manage_operations', { role: userRole })",
        f"{SRC}/pages/DashboardPage.js": "can(user, 'view_suppliers')",
        f"{SRC}/pages/Dashboard/ReportsSection.js": "can(user, 'view_capex')",
        f"{SRC}/pages/Dashboard/FaultTemplatesManager.js": "can(user, 'manage_fault_templates')",
    }
    for path, pin in consumers.items():
        src = open(path, encoding="utf-8").read()
        assert pin in src, f"{path} must consume the capability helper: {pin}"
        assert "user?.role === 'owner' || user?.role === 'manager'" not in src, (
            f"{path} still hand-lists roles — use can() from utils/capabilities"
        )
