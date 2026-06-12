"""Iter 246 — Master Admin Access Matrix.

Live role × capability grid at GET /api/master-admin/access-matrix.
Evaluates the REAL backend guard functions against synthetic personas
(plus live headcounts); the frontend mirrors the personas against
utils/capabilities.js for the UI rows.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
PULSE_ADMIN = ("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
OWNER = ("owner@apexfitness.group", "ApexDemo2026!")

EXPECTED_PERSONAS = [
    "staff", "engineer", "manager", "owner",
    "desk_gymaxis", "desk_pulse", "pulse_master_admin", "master_admin",
]


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


def _matrix(session: requests.Session) -> dict:
    r = session.get(f"{BASE_URL}/api/master-admin/access-matrix", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_access_matrix_personas_and_counts():
    body = _matrix(_login(*MASTER_ADMIN))
    keys = [p["key"] for p in body["personas"]]
    assert keys == EXPECTED_PERSONAS
    for p in body["personas"]:
        assert isinstance(p["count"], int) and p["count"] >= 0
        assert isinstance(p["user"], dict) and p["user"], "persona user dict required for frontend can()"


def test_access_matrix_gate_truth_table():
    """The gates must reflect the REAL guards — pin the expected truth
    table so any accidental privilege change fails loudly here."""
    body = _matrix(_login(*MASTER_ADMIN))
    gates = {g["key"]: g["access"] for g in body["gates"]}

    sd = gates["service_desk_access"]
    assert [sd[k] for k in EXPECTED_PERSONAS] == [
        False, False, False, False, True, True, True, True]

    scoped = gates["desk_scoped_to_pulse"]
    assert [scoped[k] for k in EXPECTED_PERSONAS] == [
        False, False, False, False, False, True, True, False]

    roster = gates["manage_engineer_roster"]
    assert [roster[k] for k in EXPECTED_PERSONAS] == [
        False, False, True, True, True, True, True, True]

    console = gates["master_admin_console"]
    assert [console[k] for k in EXPECTED_PERSONAS] == [
        False, False, False, False, False, False, True, True]

    gymaxis_only = gates["gymaxis_platform_controls"]
    assert [gymaxis_only[k] for k in EXPECTED_PERSONAS] == [
        False, False, False, False, False, False, False, True]


def test_access_matrix_marks_informational_rows():
    body = _matrix(_login(*MASTER_ADMIN))
    info = {g["key"]: g["informational"] for g in body["gates"]}
    assert info["desk_scoped_to_pulse"] is True
    assert info["service_desk_access"] is False


def test_access_matrix_auth():
    # Pulse Master Admin may read it (shares the Master Admin console).
    assert _matrix(_login(*PULSE_ADMIN))["gates"]
    # Plain org owner must not.
    s = _login(*OWNER)
    r = s.get(f"{BASE_URL}/api/master-admin/access-matrix", timeout=20)
    assert r.status_code == 403, r.status_code


def test_frontend_wiring():
    caps = open("/app/frontend/src/utils/capabilities.js", encoding="utf-8").read()
    assert "export const listCapabilities" in caps
    assert "export const CAPABILITY_LABELS" in caps
    panel = open("/app/frontend/src/pages/MasterAdmin/AccessMatrixPanel.js", encoding="utf-8").read()
    assert "master-admin/access-matrix" in panel
    assert "access-matrix-table" in panel
    sidebar = open("/app/frontend/src/pages/MasterAdmin/SidebarConfig.js", encoding="utf-8").read()
    assert "'access-matrix'" in sidebar
    page = open("/app/frontend/src/pages/MasterAdminPage.js", encoding="utf-8").read()
    assert "case 'access-matrix':" in page
