"""Regression tests for iter 216h115 (audit + classification + acceptance loop).

Pure-pure pytest via HTTP — no asyncio.run() (Motor's singleton client
gets bound to the app's event loop so cross-loop asyncio.run() fails).
"""
from __future__ import annotations

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
    r.raise_for_status()
    return r.json()


def _submit_mod_fault(headers: dict, equipment_id: str, description: str) -> dict:
    body = {
        "equipment_id": equipment_id,
        "fault_type": "not_working",
        "description": description,
        "onset": "today",
        "usable": "no",
        "safe_in_service": "yes",
        "reporter_name": "Daniel Hayes",
        "reporter_email": "daniel.hayes@example.com",
        "reporter_phone": "01234 567890",
        "attachment_urls": [],
        "ai_triage_accepted": False,
    }
    r = requests.post(f"{API}/mod/site/faults", json=body, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ───────────────────────────────────────────────
# 1. Classification scanner (pure function)
# ───────────────────────────────────────────────


def test_classification_scanner_flags_known_patterns() -> None:
    from utils.mod_classification import scan_text

    flags = scan_text("Treadmill 1234-12-345-6789 broken")
    assert any(f["label"] == "NSN" for f in flags)

    flags = scan_text("Belt failed during Operation HERRICK rotation")
    assert any(f["label"] == "Operation name" for f in flags)

    flags = scan_text("Issue raised by C/S A1B")
    assert any(f["label"] == "Callsign" for f in flags)

    flags = scan_text("Marked SECRET document on the wall")
    assert any(f["label"] == "Higher classification" for f in flags)


def test_classification_scanner_clean_text() -> None:
    from utils.mod_classification import scan_text
    assert scan_text("Belt slipping on the treadmill under heavy use") == []


# ───────────────────────────────────────────────
# 2. End-to-end audit chain via the HQ endpoint
# ───────────────────────────────────────────────


def test_audit_endpoint_chain_grows_and_verifies() -> None:
    master = _master_token()
    seed = _seed_army_demo(master)
    site_ids = list(seed["site_org_ids"].values())
    assert site_ids
    target = site_ids[0]

    hq = _login("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {hq['token']}"}

    # Provision the site credentials twice — produces audit rows for
    # both the initial provision and a rotation.
    requests.post(
        f"{API}/mod/pro/sites/{target}/provision-credentials",
        json={"rotate_if_exists": True}, headers=headers, timeout=20,
    )
    requests.post(
        f"{API}/mod/pro/sites/{target}/provision-credentials",
        json={"rotate_if_exists": True}, headers=headers, timeout=20,
    )

    r = requests.get(f"{API}/mod/pro/audit-log/{target}", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["integrity"]["valid"] is True
    assert body["integrity"]["rows"] >= 1
    assert isinstance(body["rows"], list)
    # At least the rows that have a row_hash should also expose a
    # prev_hash — both fields are written together by the new module.
    chained = [r_ for r_ in body["rows"] if r_.get("row_hash")]
    assert chained, "expected at least one tamper-evident row"
    assert all("prev_hash" in r_ for r_ in chained)


def test_audit_csv_export_includes_integrity_footer() -> None:
    master = _master_token()
    seed = _seed_army_demo(master)
    target = list(seed["site_org_ids"].values())[0]

    hq = _login("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {hq['token']}"}

    requests.post(
        f"{API}/mod/pro/sites/{target}/provision-credentials",
        json={"rotate_if_exists": True}, headers=headers, timeout=20,
    )

    r = requests.get(
        f"{API}/mod/pro/audit-log/{target}/export.csv",
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text
    text = r.text
    assert "created_at,action" in text  # header
    assert "row_hash" in text
    assert "# CHAIN INTEGRITY:" in text


def test_audit_endpoint_refuses_cross_scope() -> None:
    master = _master_token()
    _ = _seed_army_demo(master)
    # Find a non-Army MOD site (skip when env doesn't have one).
    r = requests.get(
        f"{API}/master-admin/mod/sites",
        headers={"Authorization": f"Bearer {master}"},
        timeout=15,
    )
    others = [s for s in r.json().get("sites", []) if s.get("mod_force") != "army"]
    if not others:
        return

    hq = _login("catterick.demo.lead@army.mod.local", "ArmyDemo2026!")
    r = requests.get(
        f"{API}/mod/pro/audit-log/{others[0]['id']}",
        headers={"Authorization": f"Bearer {hq['token']}"},
        timeout=15,
    )
    assert r.status_code == 403, r.text


# ───────────────────────────────────────────────
# 3. Acceptance / closure loop
# ───────────────────────────────────────────────


def _first_equipment_id(headers: dict) -> str | None:
    r = requests.get(f"{API}/mod/site/equipment", headers=headers, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    items = data.get("equipment") or data.get("items") or []
    return items[0]["id"] if items else None


def test_acceptance_loop_end_to_end() -> None:
    master = _master_token()
    _seed_army_demo(master)

    site_login = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {site_login['token']}"}
    eq_id = _first_equipment_id(headers)
    if not eq_id:
        return

    submitted = _submit_mod_fault(headers, eq_id, "Belt slipping intermittently under heavy load, please investigate further.")
    issue_id = submitted["issue_id"]
    ticket = submitted["ticket_ref"]

    r = requests.post(
        f"{API}/mod/site/faults/{issue_id}/mark-resolved",
        json={"resolution_note": "Belt tensioned"},
        headers=headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("acceptance_token_sent") is True

    # Pull the token from the fault detail.
    r = requests.get(
        f"{API}/mod/site/faults/{issue_id}", headers=headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    acc_token = r.json().get("acceptance_token")
    assert acc_token, "expected an acceptance_token on the resolved fault"

    # Public lookup → confirm → token invalidated.
    r = requests.get(f"{API}/public/mod-fault-confirm/{acc_token}", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("ticket_ref") == ticket

    r = requests.post(
        f"{API}/public/mod-fault-confirm/{acc_token}",
        json={"confirmed": True, "rating": 5, "comment": "Quick fix"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("confirmed") is True

    r = requests.get(f"{API}/public/mod-fault-confirm/{acc_token}", timeout=15)
    assert r.status_code == 404, r.text


def test_acceptance_rejection_reopens_issue() -> None:
    master = _master_token()
    _seed_army_demo(master)
    site_login = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {site_login['token']}"}
    eq_id = _first_equipment_id(headers)
    if not eq_id:
        return

    submitted = _submit_mod_fault(headers, eq_id, "Clicking noise on belt drive, has continued for two days now.")
    issue_id = submitted["issue_id"]

    requests.post(
        f"{API}/mod/site/faults/{issue_id}/mark-resolved",
        json={"resolution_note": "Looks fine on test"},
        headers=headers, timeout=15,
    )
    r = requests.get(f"{API}/mod/site/faults/{issue_id}", headers=headers, timeout=15)
    acc_token = r.json()["acceptance_token"]

    requests.post(
        f"{API}/public/mod-fault-confirm/{acc_token}",
        json={"confirmed": False, "rating": 2, "comment": "still broken"},
        timeout=15,
    )

    # Issue should be re-opened with the right reason.
    r = requests.get(f"{API}/mod/site/faults/{issue_id}", headers=headers, timeout=15)
    issue = r.json()
    assert issue.get("status") == "open"
    assert issue.get("reopened_reason") == "reporter_rejected_fix"


def test_classification_flag_persists_on_mod_fault() -> None:
    master = _master_token()
    _seed_army_demo(master)
    site_login = _login("daniel.hayes@army.mod.local", "ArmyDemo2026!")
    headers = {"Authorization": f"Bearer {site_login['token']}"}
    eq_id = _first_equipment_id(headers)
    if not eq_id:
        return

    # Description contains an NSN — should flag.
    body = {
        "equipment_id": eq_id,
        "fault_type": "not_working",
        "description": "Treadmill 1234-12-345-6789 belt drive failure under load — needs inspection.",
        "onset": "today",
        "usable": "no",
        "safe_in_service": "yes",
        "reporter_name": "Daniel Hayes",
        "reporter_email": "daniel.hayes@example.com",
        "reporter_phone": "01234 567890",
        "attachment_urls": [],
        "ai_triage_accepted": False,
    }
    r = requests.post(f"{API}/mod/site/faults", json=body, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    flags = r.json().get("classification_flags") or []
    assert any(f.get("label") == "NSN" for f in flags), flags
