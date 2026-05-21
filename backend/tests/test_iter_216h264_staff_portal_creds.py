"""Iter 216h264 — Staffing portal preview + per-staff credentials.

User asks (Feb 21, 2026, with two screenshots):
1. "Rota template modal screen is 1/3 white" — the New shift
   template modal had no `createPortal` so the transformed parent
   left a white strip below it. Pattern matches the fix already
   done for the Add Staff modal in Iter 216h242.
2. "Arrange the staffing option bar in a more logical order" —
   staff-first flow (Dashboard → Staff → Rota → Templates → Time
   Off → Shift Market → Time Clock → Live Floor → Performance →
   Payroll → Announcements → Comms → Ops → HR → Rules → AI Rota →
   AI Insights).
3. "We need a staff portal preview button so managers/owners can
   see how the website app will look — Users will need to be
   assigned usernames and passwords too."

Backend:
* New endpoint `POST /api/staffing/staff/{id}/issue-credentials`:
  - Manager-only
  - Creates the `users` doc with role=staff if missing, otherwise
    resets the password (never downgrades an existing manager).
  - Returns `{ok, email, temp_password, created, email_sent}`.
  - Best-effort emails the staff member with their login details
    via `utils.email.send_email` (failure doesn't fail the call).
  - Stamps `portal_credentials_issued_at` on staff_members so the
    UI can show "Re-issue" instead of "Send login".

Frontend:
* StaffingConsole tab registry reordered.
* StaffingConsole detects `?as=staff` query param and renders only
  the staff-allowed tabs, with an "Exit preview" banner.
* StaffTab gains:
  - "Preview staff portal" header button (opens current URL with
    ?as=staff in a new tab).
  - "Send login / Re-issue" button per staff row that calls the
    new endpoint and surfaces a copyable dialog with the temp
    password.
* ShiftTemplatesTab modals now use createPortal (fixes the white
  strip the user saw).
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Backend: endpoint surface ───────────────────────────────────


def test_issue_credentials_route_registered():
    from routes.staffing import router
    paths = {r.path for r in router.routes}
    assert "/staffing/staff/{staff_id}/issue-credentials" in paths


def test_issue_credentials_rejects_non_managers():
    from routes.staffing import issue_staff_credentials
    from fastapi import HTTPException
    user = {"id": "u-1", "organization_id": "org-1", "role": "staff"}
    try:
        _run(issue_staff_credentials(staff_id="x", body=None, user=user))
    except HTTPException as e:
        assert e.status_code == 403
    else:
        raise AssertionError("expected 403 for non-manager")


def test_issue_credentials_creates_user_and_returns_temp_password():
    from routes.staffing import issue_staff_credentials

    staff_doc = {
        "id": "s-1", "organization_id": "org-1",
        "full_name": "New Joiner", "email": "new@example.com",
    }
    db_state = {"users": {}, "staff": {staff_doc["id"]: staff_doc.copy()}}

    async def fake_staff_find_one(query, projection=None):
        if query.get("id") == staff_doc["id"]:
            return {**db_state["staff"][staff_doc["id"]]}
        return None

    async def fake_user_find_one(query, projection=None):
        return db_state["users"].get(query.get("email"))

    async def fake_user_insert(doc):
        db_state["users"][doc["email"]] = {**doc}
        return MagicMock()

    async def fake_user_update(query, update):
        existing = db_state["users"].get(query.get("email"))
        if existing:
            existing.update(update["$set"])
        return MagicMock(matched_count=1 if existing else 0)

    async def fake_staff_update(query, update):
        sid = query.get("id")
        if sid in db_state["staff"]:
            db_state["staff"][sid].update(update["$set"])
        return MagicMock(matched_count=1)

    async def fake_org_find_one(query, projection=None):
        return {"id": "org-1", "name": "Acme"}

    fake_db = MagicMock()
    fake_db.staff_members.find_one = AsyncMock(side_effect=fake_staff_find_one)
    fake_db.users.find_one = AsyncMock(side_effect=fake_user_find_one)
    fake_db.users.insert_one = AsyncMock(side_effect=fake_user_insert)
    fake_db.users.update_one = AsyncMock(side_effect=fake_user_update)
    fake_db.staff_members.update_one = AsyncMock(side_effect=fake_staff_update)
    fake_db.organizations.find_one = AsyncMock(side_effect=fake_org_find_one)

    user = {"id": "u-1", "organization_id": "org-1", "role": "manager",
            "email": "boss@example.com", "full_name": "Manager"}

    with patch("routes.staffing.db", fake_db):
        result = _run(issue_staff_credentials(
            staff_id="s-1",
            body=None,
            user=user,
        ))

    assert result["ok"] is True
    assert result["email"] == "new@example.com"
    assert result["created"] is True
    assert isinstance(result["temp_password"], str)
    assert len(result["temp_password"]) == 10
    assert "new@example.com" in db_state["users"]
    # password is hashed
    stored_pw = db_state["users"]["new@example.com"]["password"]
    assert stored_pw != result["temp_password"]
    assert stored_pw.startswith("$2") or stored_pw.startswith("$") or len(stored_pw) > 30
    # must_change_password flag is set
    assert db_state["users"]["new@example.com"]["must_change_password"] is True
    # staff_member.email + portal_credentials_issued_at mirrored
    assert db_state["staff"]["s-1"]["portal_credentials_issued_at"]


def test_issue_credentials_resets_existing_user_without_downgrading_role():
    from routes.staffing import issue_staff_credentials

    db_state = {
        "users": {
            "owner@example.com": {
                "email": "owner@example.com",
                "role": "owner",
                "organization_id": "org-1",
                "password": "old-hash",
            }
        },
        "staff": {
            "s-1": {
                "id": "s-1",
                "organization_id": "org-1",
                "full_name": "Boss",
                "email": "owner@example.com",
            }
        },
    }

    async def find_staff(query, projection=None):
        return {**db_state["staff"][query["id"]]}

    async def find_user(query, projection=None):
        return db_state["users"].get(query.get("email"))

    async def update_user(query, update):
        u = db_state["users"][query["email"]]
        u.update(update["$set"])
        return MagicMock(matched_count=1)

    async def update_staff(query, update):
        db_state["staff"][query["id"]].update(update["$set"])
        return MagicMock(matched_count=1)

    fake_db = MagicMock()
    fake_db.staff_members.find_one = AsyncMock(side_effect=find_staff)
    fake_db.users.find_one = AsyncMock(side_effect=find_user)
    fake_db.users.update_one = AsyncMock(side_effect=update_user)
    fake_db.staff_members.update_one = AsyncMock(side_effect=update_staff)
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Acme"})

    with patch("routes.staffing.db", fake_db):
        result = _run(issue_staff_credentials(
            staff_id="s-1",
            body=None,
            user={"id": "u", "organization_id": "org-1", "role": "manager",
                  "email": "m@x.uk", "full_name": "Manager"},
        ))

    assert result["created"] is False
    # critical: role NOT downgraded to staff
    assert db_state["users"]["owner@example.com"]["role"] == "owner"
    # password WAS updated
    assert db_state["users"]["owner@example.com"]["password"] != "old-hash"


def test_issue_credentials_requires_email_on_file():
    from routes.staffing import issue_staff_credentials
    from fastapi import HTTPException

    staff_doc = {"id": "s-2", "organization_id": "org-1", "full_name": "No Email", "email": None}
    fake_db = MagicMock()
    fake_db.staff_members.find_one = AsyncMock(return_value=staff_doc)

    user = {"id": "u", "organization_id": "org-1", "role": "manager",
            "email": "m@x.uk", "full_name": "M"}

    with patch("routes.staffing.db", fake_db):
        try:
            _run(issue_staff_credentials(staff_id="s-2", body=None, user=user))
        except HTTPException as e:
            assert e.status_code == 400
            assert "email" in e.detail.lower()
        else:
            raise AssertionError("expected 400 for missing email")


# ─── 2. Frontend: tab order ─────────────────────────────────────────


def test_staffing_tab_order_is_logical_people_first():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/StaffingConsole.js"
    ).read_text()
    # Pull out the TABS_ALL ids in registry order
    block = src.split("const TABS_ALL = [")[1].split("];")[0]
    ids = re.findall(r"id:\s*'([^']+)'", block)

    def idx(_id):
        return ids.index(_id)

    # Headline expectations from the user's request
    assert idx("staff") < idx("rota"), "Staff must come before Rota"
    assert idx("rota") < idx("templates"), "Rota must come before Templates"
    assert idx("templates") < idx("leave"), "Templates must come before Time Off"
    assert idx("leave") < idx("market"), "Time Off must come before Shift Market"
    assert idx("market") < idx("timeclock"), "Shift Market must come before Time Clock"
    assert idx("performance") < idx("payroll"), "Performance comes before Payroll"
    # Live floor sits alongside daily ops, not buried near AI
    assert idx("live") < idx("ai"), "Live Floor comes before AI Insights"


# ─── 3. Frontend: preview portal + credentials UI ───────────────────


def test_staff_tab_has_preview_portal_button():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/StaffingConsole.js"
    ).read_text())
    assert 'data-testid="staff-preview-portal-btn"' in src
    assert "?as=staff" in src or "set('as', 'staff')" in src


def test_staff_tab_has_per_row_issue_creds_button():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/StaffingConsole.js"
    ).read_text()
    assert "staff-issue-creds-" in src
    assert "/staffing/staff/${s.id}/issue-credentials" in src or \
           "issue-credentials" in src


def test_credentials_dialog_renders_temp_password():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/StaffingConsole.js"
    ).read_text()
    assert 'data-testid="staff-creds-dialog"' in src
    assert "staff-creds-temp-password" in src
    assert "Copyable" in src or "navigator.clipboard.writeText" in src


def test_preview_mode_banner_present():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/StaffingConsole.js"
    ).read_text())
    assert "staff-portal-preview-banner" in src
    assert "previewAsStaff" in src
    # preview hides manager-only tabs by forcing role to 'staff'
    assert "if (previewAsStaff) return 'staff'" in src


# ─── 4. ShiftTemplatesTab modals use createPortal ───────────────────


def test_shift_templates_modals_use_create_portal():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/staffing/ShiftTemplatesTab.js"
    ).read_text()
    assert "import { createPortal } from 'react-dom'" in src
    assert "createPortal((" in src
    assert "), document.body)" in src
