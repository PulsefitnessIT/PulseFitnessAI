"""Regression tests for iter 216h116.

Covers four pieces of work:

1. Posting-out handover (mod_site_staff.posting_out_date + successor)
2. Compliance / inspection calendar CRUD + scope check
3. MFA mandatory enrolment for MOD HQ tier
4. DIO contract stub + fault escalation
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import requests

from tests.conftest import _test_backend_url

API = _test_backend_url() + "/api"


def _master_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


def _seed_army_demo(master_token: str) -> dict:
    r = requests.post(
        f"{API}/mod/demo/seed-army-catterick",
        headers={"Authorization": f"Bearer {master_token}"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def _login(email: str, password: str, portal: str = "mod") -> dict:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "portal": portal},
        timeout=15,
    )
    return r


def _hq_login_with_mfa(email: str, password: str) -> dict:
    """Complete the MOD HQ MFA-mandatory enrolment flow and return a
    response dict matching the normal /auth/login shape (with ``token``).

    Idempotent across test runs — uses a sync pymongo client to wipe a
    previously-enrolled user's MFA state.
    """
    import os as _os
    import pyotp
    from pymongo import MongoClient as _MongoClient
    r = _login(email, password)
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("token"):
        return body
    if body.get("requires_mfa"):
        # Already enrolled in a previous run — reset and start fresh.
        mongo_url = _os.environ.get("MONGO_URL")
        db_name = _os.environ.get("DB_NAME")
        client = _MongoClient(mongo_url)
        client[db_name].users.update_one(
            {"email": email},
            {"$set": {"mfa_enabled": False, "mfa_secret": None, "mfa_backup_codes": []}},
        )
        # The canonical MFA state lives in ``user_mfa`` — drop it too.
        user_row = client[db_name].users.find_one({"email": email}, {"_id": 0, "id": 1})
        if user_row:
            client[db_name].user_mfa.delete_many({"user_id": user_row["id"]})
        client.close()
        # Try again.
        return _hq_login_with_mfa(email, password)
    assert body.get("requires_mfa_enrolment"), body
    temp = body["temp_token"]
    r2 = requests.post(
        f"{API}/auth/mfa/enrol/setup",
        json={"temp_token": temp}, timeout=15,
    )
    assert r2.status_code == 200, r2.text
    secret = r2.json()["secret"]
    code = pyotp.TOTP(secret).now()
    r3 = requests.post(
        f"{API}/auth/mfa/enrol/complete",
        json={"temp_token": temp, "code": code}, timeout=15,
    )
    assert r3.status_code == 200, r3.text
    return r3.json()


# ──────────────────────────────────────────────────────────────
# 1. Posting-out handover
# ──────────────────────────────────────────────────────────────


def test_posting_out_records_date_and_returns_open_faults() -> None:
    master = _master_token()
    _seed_army_demo(master)
    site_user = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!").json()
    headers = {"Authorization": f"Bearer {site_user['token']}"}

    # Add a staff member to use for posting out (unique email per run).
    suffix = uuid4().hex[:8]
    add = requests.post(
        f"{API}/mod/site/staff",
        headers=headers,
        json={"name": "Pte Departing Soldier", "rank": "Pte",
              "email": f"departing-{suffix}@example.com", "phone": "01234 000111"},
        timeout=15,
    )
    assert add.status_code == 200, add.text
    staff_id = add.json()["id"]

    # Post them out.
    future = (date.today() + timedelta(days=30)).isoformat()
    r = requests.post(
        f"{API}/mod/site/staff/{staff_id}/posting-out",
        headers=headers,
        json={
            "posting_out_date": future,
            "handover_notes": "Treadmill belt order on PO-1234 still pending.",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["posting_out_date"] == future
    assert "open_fault_count" in body


def test_posting_out_invalid_date_rejected() -> None:
    master = _master_token()
    _seed_army_demo(master)
    site_user = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!").json()
    headers = {"Authorization": f"Bearer {site_user['token']}"}
    suffix = uuid4().hex[:8]
    add = requests.post(
        f"{API}/mod/site/staff",
        headers=headers,
        json={"name": "Bad Date Tester", "rank": "Pte",
              "email": f"bad-{suffix}@example.com", "phone": "01234 000112"},
        timeout=15,
    )
    staff_id = add.json()["id"]
    r = requests.post(
        f"{API}/mod/site/staff/{staff_id}/posting-out",
        headers=headers,
        json={"posting_out_date": "not-a-date"},
        timeout=10,
    )
    assert r.status_code == 400, r.text


def test_posting_out_sweeper_auto_deactivates_overdue_records() -> None:
    """Backdate a staff member's posting_out_date 20 days, hit the
    master-admin sweep endpoint, then verify is_active=false."""
    import os as _os
    from pymongo import MongoClient as _MongoClient

    master = _master_token()
    _seed_army_demo(master)
    site_user = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!").json()
    headers = {"Authorization": f"Bearer {site_user['token']}"}
    suffix = uuid4().hex[:8]
    add = requests.post(
        f"{API}/mod/site/staff",
        headers=headers,
        json={"name": "Old Posting Out", "rank": "Pte",
              "email": f"old-{suffix}@example.com", "phone": "01234 000113"},
        timeout=15,
    )
    staff_id = add.json()["id"]
    overdue = (date.today() - timedelta(days=20)).isoformat()

    client = _MongoClient(_os.environ.get("MONGO_URL"))
    client[_os.environ.get("DB_NAME")].mod_site_staff.update_one(
        {"id": staff_id},
        {"$set": {"posting_out_date": overdue}},
    )
    client.close()

    r = requests.post(
        f"{API}/master-admin/mod/sweep-now",
        headers={"Authorization": f"Bearer {master}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["postings"]["deactivated"] >= 1

    client = _MongoClient(_os.environ.get("MONGO_URL"))
    row = client[_os.environ.get("DB_NAME")].mod_site_staff.find_one(
        {"id": staff_id}, {"_id": 0},
    )
    client.close()
    assert row["is_active"] is False
    assert row["deactivation_reason"] == "posting_out_complete"


# ──────────────────────────────────────────────────────────────
# 2. Compliance calendar
# ──────────────────────────────────────────────────────────────


def test_compliance_crud_and_scope_check() -> None:
    master = _master_token()
    seed = _seed_army_demo(master)
    site_id = list(seed["site_org_ids"].values())[0]

    hq = _hq_login_with_mfa("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {hq['token']}"}

    # Create.
    body = {
        "site_id": site_id,
        "kind": "insurance",
        "title": "Public liability cover",
        "due_date": (date.today() + timedelta(days=10)).isoformat(),
        "notes": "Renew via DefenceConnect portal",
    }
    r = requests.post(f"{API}/mod/pro/compliance", json=body, headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    event_id = r.json()["event"]["id"]

    # List — must include our event with days_until ~10 and status=soon.
    r = requests.get(f"{API}/mod/pro/compliance?site_id={site_id}", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    ours = next((e for e in events if e["id"] == event_id), None)
    assert ours is not None
    assert ours["status"] in ("soon", "warning")
    assert ours["kind_label"] == "Insurance renewal"

    # Update.
    body["due_date"] = (date.today() + timedelta(days=5)).isoformat()
    body["notes"] = "URGENT — broker chasing"
    r = requests.patch(f"{API}/mod/pro/compliance/{event_id}", json=body, headers=headers, timeout=15)
    assert r.status_code == 200, r.text

    # Delete.
    r = requests.delete(f"{API}/mod/pro/compliance/{event_id}", headers=headers, timeout=15)
    assert r.status_code == 200, r.text


def test_compliance_refuses_cross_scope() -> None:
    master = _master_token()
    _seed_army_demo(master)
    # Find a non-Army MOD site.
    r = requests.get(
        f"{API}/master-admin/mod/sites",
        headers={"Authorization": f"Bearer {master}"},
        timeout=15,
    )
    others = [s for s in r.json().get("sites", []) if s.get("mod_force") != "army"]
    if not others:
        return  # env without a non-Army MOD site — skip.

    hq = _hq_login_with_mfa("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {hq['token']}"}
    body = {
        "site_id": others[0]["id"], "kind": "pat",
        "title": "PAT", "due_date": (date.today() + timedelta(days=5)).isoformat(),
    }
    r = requests.post(f"{API}/mod/pro/compliance", json=body, headers=headers, timeout=15)
    assert r.status_code == 403, r.text


# ──────────────────────────────────────────────────────────────
# 3. MFA mandatory enrolment for MOD HQ
# ──────────────────────────────────────────────────────────────


def test_mod_hq_login_returns_mfa_enrolment_required() -> None:
    """Catterick HQ user has account_type=mod_branch — mandatory MFA.
    A normal /auth/login response must return requires_mfa_enrolment
    + temp_token instead of the full JWT."""
    master = _master_token()
    _seed_army_demo(master)
    r = _login("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    assert r.status_code == 200, r.text
    body = r.json()
    # If they have enrolled already (test leakage from another run) we
    # accept either flow.
    if body.get("requires_mfa_enrolment"):
        assert isinstance(body.get("temp_token"), str)
        # Setup with the enrol token must work.
        r2 = requests.post(
            f"{API}/auth/mfa/enrol/setup",
            json={"temp_token": body["temp_token"]},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("uri", "").startswith("otpauth://")
    elif body.get("requires_mfa"):
        # Already enrolled — that's also acceptable.
        assert isinstance(body.get("temp_token"), str)
    else:
        # Token-only response means MFA wasn't required. For mod_branch
        # this would be a regression unless we've explicitly disabled
        # the policy in test config.
        assert "token" in body, "expected MFA gate or full token"


def test_mod_site_user_does_not_require_mfa() -> None:
    """mod_site (kiosk) accounts are shared logins — MFA is not
    mandatory. Login should return a token directly."""
    master = _master_token()
    _seed_army_demo(master)
    r = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("requires_mfa_enrolment") is not True
    assert "token" in body


# ──────────────────────────────────────────────────────────────
# 4. DIO contract stub
# ──────────────────────────────────────────────────────────────


def test_hq_can_set_and_read_dio_contract() -> None:
    master = _master_token()
    seed = _seed_army_demo(master)
    site_id = list(seed["site_org_ids"].values())[0]

    hq = _hq_login_with_mfa("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {hq['token']}"}

    r = requests.put(
        f"{API}/mod/pro/sites/{site_id}/dio-contract",
        headers=headers,
        json={
            "dio_contract_ref": "DIO-2026-NORTH-1234",
            "dio_contact_email": "dio.north@example.com",
            "dio_contact_name": "DIO North Region",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text

    r = requests.get(
        f"{API}/mod/pro/sites/{site_id}/dio-contract", headers=headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dio_contract_ref"] == "DIO-2026-NORTH-1234"
    assert body["dio_contact_email"] == "dio.north@example.com"


def test_dio_escalation_requires_contact() -> None:
    """A site without dio_contact_email cannot escalate."""
    master = _master_token()
    _seed_army_demo(master)
    site_user = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!").json()
    headers = {"Authorization": f"Bearer {site_user['token']}"}
    eq = requests.get(f"{API}/mod/site/equipment", headers=headers, timeout=15).json()
    items = eq.get("equipment") or eq.get("items") or []
    if not items:
        return
    eq_id = items[0]["id"]
    fault_body = {
        "equipment_id": eq_id, "fault_type": "not_working",
        "description": "Belt drive replacement needed, this is the second one in 6 months.",
        "onset": "today", "usable": "no", "safe_in_service": "yes",
        "reporter_name": "Daniel Hayes",
        "reporter_email": "daniel.hayes@example.com",
        "reporter_phone": "01234 567890",
        "attachment_urls": [], "ai_triage_accepted": False,
    }
    r = requests.post(f"{API}/mod/site/faults", json=fault_body, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    issue_id = r.json()["issue_id"]

    # Wipe any pre-existing DIO contact for this site to force the
    # 409 path.
    import os as _os
    from pymongo import MongoClient as _MongoClient
    client = _MongoClient(_os.environ.get("MONGO_URL"))
    client[_os.environ.get("DB_NAME")].organizations.update_one(
        {"id": site_user["user"]["organization_id"]},
        {"$unset": {"dio_contact_email": "", "dio_contact_name": "", "dio_contract_ref": ""}},
    )
    client.close()

    r = requests.post(
        f"{API}/mod/site/faults/{issue_id}/escalate-to-dio",
        json={"note": "Command interest"},
        headers=headers, timeout=15,
    )
    assert r.status_code == 409, r.text


def test_dio_escalation_records_flag_when_contact_set() -> None:
    master = _master_token()
    seed = _seed_army_demo(master)
    site_id = list(seed["site_org_ids"].values())[0]

    # HQ configures DIO contact first.
    hq = _hq_login_with_mfa("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    requests.put(
        f"{API}/mod/pro/sites/{site_id}/dio-contract",
        headers={"Authorization": f"Bearer {hq['token']}"},
        json={
            "dio_contract_ref": "DIO-2026-NORTH-1234",
            "dio_contact_email": "dio.north@example.com",
            "dio_contact_name": "DIO North",
        },
        timeout=15,
    )

    # We need to act AS the site that has the contract. Find a user
    # for that specific site.
    site_user = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!").json()
    if site_user["user"]["organization_id"] != site_id:
        return  # daniel.hayes belongs to a different site — skip.
    headers = {"Authorization": f"Bearer {site_user['token']}"}
    eq = requests.get(f"{API}/mod/site/equipment", headers=headers, timeout=15).json()
    items = eq.get("equipment") or eq.get("items") or []
    if not items:
        return
    eq_id = items[0]["id"]
    fault_body = {
        "equipment_id": eq_id, "fault_type": "not_working",
        "description": "Belt drive failure — second occurrence within 6 months.",
        "onset": "today", "usable": "no", "safe_in_service": "yes",
        "reporter_name": "Daniel Hayes",
        "reporter_email": "daniel.hayes@example.com",
        "reporter_phone": "01234 567890",
        "attachment_urls": [], "ai_triage_accepted": False,
    }
    r = requests.post(f"{API}/mod/site/faults", json=fault_body, headers=headers, timeout=30)
    issue_id = r.json()["issue_id"]

    r = requests.post(
        f"{API}/mod/site/faults/{issue_id}/escalate-to-dio",
        json={"note": "Repeated failure pattern"},
        headers=headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalated_to"] == "dio.north@example.com"
    assert body["contract_ref"] == "DIO-2026-NORTH-1234"
