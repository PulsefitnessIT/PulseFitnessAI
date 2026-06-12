"""Iter 261 — Engineer App header shows the engineer's organisation name,
and internal engineers don't see the legacy-report self-upload.

User report (production): "Engineer App — instead of GymAxis Engineer as a
title in the header — this should be the name of the organisation the
engineer is associated with. Also engineers that are associated with
organisations and service desk will not need to upload legacy reports —
these can be imported via settings in service desk."

Covers:
1. GET /svc/engineer/me returns `organization_name` + the internal/partner
   split (`internal_engineer` / `is_partner_engineer`).
2. An internally provisioned engineer (master-admin add-user, role=engineer)
   resolves internal_engineer=True with the org's name.
3. A partner engineer (engineer.smoke has an approved partner_engineers row)
   resolves is_partner_engineer=True / internal_engineer=False — they keep
   the legacy import.
4. Source pins — header brand + legacy-tile gating wired in the frontend.
"""

import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()
PASSWORD = "EngineerIter261!xyz"


def _admin() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
               timeout=20)
    assert r.status_code == 200, r.text
    return s


def _pulse_org_id(s: requests.Session) -> str:
    orgs = s.get(f"{BASE_URL}/api/master-admin/organizations", timeout=30).json()
    rows = orgs.get("organizations", orgs if isinstance(orgs, list) else [])
    for o in rows:
        if o.get("name") == "Pulse Fitness":
            return o["id"]
    raise AssertionError("Pulse Fitness org not found")


def test_internal_engineer_me_has_org_name_and_internal_flag():
    admin = _admin()
    org_id = _pulse_org_id(admin)
    email = f"iter261.eng+{uuid.uuid4().hex[:8]}@example.com"

    r = admin.post(
        f"{BASE_URL}/api/master-admin/organizations/{org_id}/users",
        json={"email": email, "full_name": "Iter261 Engineer",
              "role": "engineer", "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    user_id = r.json()["id"]

    try:
        eng = requests.Session()
        r = eng.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": PASSWORD}, timeout=20)
        assert r.status_code == 200, r.text
        me = eng.get(f"{BASE_URL}/api/svc/engineer/me", timeout=30).json()
        assert me.get("organization_name") == "Pulse Fitness", me
        assert me.get("internal_engineer") is True, me
        assert me.get("is_partner_engineer") is False, me
    finally:
        admin.put(f"{BASE_URL}/api/master-admin/users/{user_id}/archive",
                  json={"archived": True}, timeout=30)
        r = admin.delete(f"{BASE_URL}/api/master-admin/users/{user_id}",
                         json={"confirm_email": email}, timeout=30)
        assert r.status_code == 200, f"cleanup failed: {r.text}"


def test_partner_engineer_me_keeps_partner_flag():
    """engineer.smoke has an approved partner_engineers row — they are NOT
    internal, so the legacy import stays available to them."""
    eng = requests.Session()
    r = eng.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "engineer.smoke@gymaxisai.com",
                       "password": "EngTest123!"}, timeout=20)
    assert r.status_code == 200, r.text
    me = eng.get(f"{BASE_URL}/api/svc/engineer/me", timeout=30).json()
    assert me.get("is_partner_engineer") is True, me
    assert me.get("internal_engineer") is False, me
    # Org name still resolves for partner engineers (header falls back to
    # the org they operate under).
    assert me.get("organization_name"), me


def test_frontend_wiring_pins():
    """Source pins — header brand hook + legacy gating must stay wired."""
    base = "/app/frontend/src/pages/ServiceOps/Engineer"
    hook = open(f"{base}/hooks/useEngineerOrgBrand.js", encoding="utf-8").read()
    assert "organization_name" in hook and "internal_engineer" in hook

    home = open(f"{base}/EngineerHomeV2.js", encoding="utf-8").read()
    assert "useEngineerOrgBrand" in home
    assert "{orgBrand.label}" in home, "home header must show the org brand"
    assert "!legacyTileHidden && !orgBrand.internal" in home, (
        "legacy import tile must be hidden for internal engineers"
    )

    settings = open(f"{base}/EngineerAccountSettings.js", encoding="utf-8").read()
    assert "{!orgBrand.internal && (" in settings, (
        "Settings → Tools legacy import row must be hidden for internal engineers"
    )

    # Every Engineer App page header carries the org brand — no hardcoded
    # "GymAxis · Engineer" eyebrow remains.
    import glob
    for path in glob.glob(f"{base}/*.js"):
        src = open(path, encoding="utf-8").read()
        if path.endswith("useEngineerOrgBrand.js"):
            continue
        assert "GymAxis \u00b7 Engineer" not in src, (
            f"hardcoded engineer brand left in {path}"
        )
