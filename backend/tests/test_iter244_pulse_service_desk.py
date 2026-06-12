"""Iter 244 — Service Desk for the Pulse Fitness organisation + Engineer
App case allocation.

What changed:
- `utils/service_desk_auth._is_service_desk` now also passes Pulse Master
  Admins (`is_pulse_admin` / role `pulse_master_admin`) — Pulse runs the
  service operation, so the Service Desk is their Sicon case hub.
- Every `routes/svc/*` org scope falls back to `user.service_org_id` so
  platform-level (org-less) desk agents / pulse admins resolve a working
  service org. New users get it at provisioning; existing org-less users
  are backfilled at startup (`bootstrap.seed.backfill_service_org_ids`).
- `engineers_admin._require_admin` lets desk agents + pulse admins manage
  the engineer roster.
- Frontend: capability `view_service_desk` drives /service-desk routing,
  the ServiceDeskPage guard and the Master Admin sidebar switch.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()
SRC = "/app/frontend/src"

PULSE_ADMIN = ("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
DESK_AGENT = ("desk@pulsefitness.com", "DeskAgent123!")
ENGINEER = ("engineer.smoke@gymaxisai.com", "EngTest123!")
SMOKE_ENGINEER_ID = "7cc0455f-3206-4069-ab95-6db51276a553"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


# ── Access: who can enter the Service Desk ───────────────────────

def test_pulse_master_admin_passes_service_desk_guard():
    s = _login(*PULSE_ADMIN)
    r = s.get(f"{BASE_URL}/api/service-desk/summary", timeout=20)
    assert r.status_code == 200, r.text
    assert "organizations" in r.json()


def test_desk_agent_passes_service_desk_guard():
    s = _login(*DESK_AGENT)
    r = s.get(f"{BASE_URL}/api/service-desk/summary", timeout=20)
    assert r.status_code == 200, r.text


def test_regular_owner_still_403_on_service_desk():
    s = _login("owner@apexfitness.group", "ApexDemo2026!")
    r = s.get(f"{BASE_URL}/api/service-desk/summary", timeout=20)
    assert r.status_code == 403, f"plain org owner must NOT get desk access: {r.status_code}"


# ── Org-scoped Service Ops surfaces resolve for desk users ──────

def test_pulse_admin_sees_org_scoped_cases():
    s = _login(*PULSE_ADMIN)
    r = s.get(f"{BASE_URL}/api/svc/cases?limit=5", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "cases" in body and "total" in body


def test_desk_agent_sees_cases_and_engineers():
    s = _login(*DESK_AGENT)
    r = s.get(f"{BASE_URL}/api/svc/cases?limit=5", timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["total"] > 0, "desk agent must see the Sicon case hub"
    r = s.get(f"{BASE_URL}/api/svc/engineers", timeout=20)
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in r.json()["engineers"]]
    assert SMOKE_ENGINEER_ID in ids, "engineer roster must include the smoke engineer"


# ── Case allocation: desk → engineer app ─────────────────────────

def test_desk_agent_allocates_case_and_engineer_sees_it():
    desk = _login(*DESK_AGENT)
    # find an open case (assigned or not — we reassign + restore after)
    r = desk.get(f"{BASE_URL}/api/svc/cases?status=open&limit=50", timeout=20)
    assert r.status_code == 200, r.text
    cases = r.json()["cases"]
    assert cases, "need at least one open case in the service org"
    case = next((c for c in cases if not c.get("assigned_engineer_id")), cases[0])
    prev_eng = case.get("assigned_engineer_id") or ""
    prev_name = case.get("assigned_engineer_name") or ""

    r = desk.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
        "assigned_engineer_id": SMOKE_ENGINEER_ID,
        "assigned_engineer_name": "Smoke Engineer",
    }, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["assigned_engineer_id"] == SMOKE_ENGINEER_ID

    try:
        eng = _login(*ENGINEER)
        r = eng.get(f"{BASE_URL}/api/svc/engineer/jobs?when=open", timeout=20)
        assert r.status_code == 200, r.text
        refs = [j.get("reference") for j in r.json()["jobs"]]
        assert case["reference"] in refs, (
            f"allocated case {case['reference']} must appear in the Engineer App: {refs}"
        )
    finally:
        # restore the original assignment so the test is re-runnable
        desk.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "assigned_engineer_id": prev_eng,
            "assigned_engineer_name": prev_name,
        }, timeout=20)


# ── service_org_id provisioning + backfill wiring ────────────────

def test_backfill_helper_exists_and_seed_calls_it():
    src = open("/app/backend/bootstrap/seed.py", encoding="utf-8").read()
    assert "async def backfill_service_org_ids" in src
    assert "await backfill_service_org_ids()" in src


def test_provisioning_paths_attach_service_org():
    sd_admin = open("/app/backend/routes/service_desk_admin.py", encoding="utf-8").read()
    assert sd_admin.count("service_org_id") >= 2, "create + grant must attach service_org_id"
    pma = open("/app/backend/routes/pulse_master_admin.py", encoding="utf-8").read()
    assert '"service_org_id"' in pma, "pulse admin provisioning must attach service_org_id"


def test_svc_org_scope_falls_back_to_service_org_id():
    import glob
    missing = []
    for f in glob.glob("/app/backend/routes/svc/*.py"):
        src = open(f, encoding="utf-8").read()
        if 'user["organization_id"]' in src:
            missing.append(f)
    assert not missing, f"raw org access without service_org_id fallback: {missing}"


# ── Frontend wiring ──────────────────────────────────────────────

def test_frontend_uses_view_service_desk_capability():
    caps = open(f"{SRC}/utils/capabilities.js", encoding="utf-8").read()
    assert "view_service_desk" in caps
    routes = open(f"{SRC}/routes/AppRoutes.js", encoding="utf-8").read()
    assert "can(user, 'view_service_desk')" in routes
    page = open(f"{SRC}/pages/ServiceDeskPage.js", encoding="utf-8").read()
    assert "can(user, 'view_service_desk')" in page
    sidebar = open(f"{SRC}/pages/MasterAdmin/AdminSidebar.js", encoding="utf-8").read()
    # the Service Desk switch is no longer hidden from Pulse admins
    import re
    block = sidebar.split("portal-switch-service-desk")[0][-600:]
    assert "{!isPulseAdmin && (" not in block, "Service Desk switch must be visible to Pulse admins"
