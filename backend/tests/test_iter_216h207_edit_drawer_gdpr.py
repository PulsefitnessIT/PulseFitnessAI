"""Iter 216h207 — Edit drawer GDPR + Email/Phone validation parity.

Brings the Member / Instructor PATCH endpoints up to parity with their
Create counterparts:
  • Email format validation on change.
  • Empty phone / emergency_contact_phone rejected.
  • gdpr_consent / marketing_consent updates stamp audit timestamps.
  • Instructor POST requires gdpr_consent.
  • Instructor PATCH also stamps consent timestamps.

Run: pytest backend/tests/test_iter_216h207_edit_drawer_gdpr.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ───────────────────────── Member PATCH ─────────────────────────

def _member_db(existing=None):
    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=existing or {
        "id": "m1", "organization_id": "org-1",
        "email": "old@example.com", "phone": "+447700900000",
        "first_name": "Alex", "last_name": "Doe",
        "gdpr_consent": False, "marketing_consent": False,
    })
    fake.members.update_one = AsyncMock()
    return fake


def test_member_patch_rejects_invalid_email():
    from routes.memberships import members as m

    async def _org(_u): return "org-1"
    async def _load(mid, oid):
        return {"id": mid, "organization_id": oid, "email": "old@example.com",
                "gdpr_consent": False, "marketing_consent": False}

    fake = _member_db()
    with patch.object(m, "db", fake), \
         patch.object(m, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(m, "_load_member", new=AsyncMock(side_effect=_load)):
        with pytest.raises(HTTPException) as exc:
            _run(m.members_patch(member_id="m1",
                                 body={"email": "not-an-email"},
                                 user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "Invalid email" in str(exc.value.detail)


def test_member_patch_rejects_empty_phone():
    from routes.memberships import members as m

    async def _org(_u): return "org-1"
    async def _load(mid, oid):
        return {"id": mid, "organization_id": oid,
                "gdpr_consent": False, "marketing_consent": False}

    fake = _member_db()
    with patch.object(m, "db", fake), \
         patch.object(m, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(m, "_load_member", new=AsyncMock(side_effect=_load)):
        with pytest.raises(HTTPException) as exc:
            _run(m.members_patch(member_id="m1",
                                 body={"phone": "   "},
                                 user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "phone" in str(exc.value.detail).lower()


def test_member_patch_rejects_empty_emergency_phone():
    from routes.memberships import members as m

    async def _org(_u): return "org-1"
    async def _load(mid, oid):
        return {"id": mid, "organization_id": oid,
                "gdpr_consent": False, "marketing_consent": False}

    fake = _member_db()
    with patch.object(m, "db", fake), \
         patch.object(m, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(m, "_load_member", new=AsyncMock(side_effect=_load)):
        with pytest.raises(HTTPException) as exc:
            _run(m.members_patch(member_id="m1",
                                 body={"emergency_contact_phone": ""},
                                 user={"id": "u1"}))
        assert exc.value.status_code == 400


def test_member_patch_stamps_gdpr_consent_audit():
    """Setting gdpr_consent=true on a member who previously had false
    should write the consent flag, timestamp, and actor id."""
    from routes.memberships import members as m

    async def _org(_u): return "org-1"
    existing = {"id": "m1", "organization_id": "org-1",
                "gdpr_consent": False, "marketing_consent": False,
                "email": "x@y.com"}
    async def _load(_mid, _oid): return existing

    fake = _member_db(existing=existing)
    with patch.object(m, "db", fake), \
         patch.object(m, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(m, "_load_member", new=AsyncMock(side_effect=_load)):
        _run(m.members_patch(member_id="m1",
                             body={"gdpr_consent": True, "marketing_consent": True},
                             user={"id": "u-operator"}))

    fake.members.update_one.assert_called_once()
    _, kwargs = fake.members.update_one.call_args
    args, _ = fake.members.update_one.call_args
    set_doc = args[1]["$set"]
    assert set_doc.get("gdpr_consent") is True
    assert set_doc.get("gdpr_consent_at")
    assert set_doc.get("gdpr_consent_actor_id") == "u-operator"
    assert set_doc.get("marketing_consent") is True
    assert set_doc.get("marketing_consent_at")


def test_member_patch_skips_consent_when_unchanged():
    """If gdpr_consent is sent identical to existing, no audit re-stamp."""
    from routes.memberships import members as m

    async def _org(_u): return "org-1"
    existing = {"id": "m1", "organization_id": "org-1",
                "gdpr_consent": True, "marketing_consent": True,
                "gdpr_consent_at": "2025-01-01T00:00:00+00:00",
                "marketing_consent_at": "2025-01-01T00:00:00+00:00",
                "email": "x@y.com"}
    async def _load(_mid, _oid): return existing

    fake = _member_db(existing=existing)
    with patch.object(m, "db", fake), \
         patch.object(m, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(m, "_load_member", new=AsyncMock(side_effect=_load)):
        _run(m.members_patch(member_id="m1",
                             body={"gdpr_consent": True, "marketing_consent": True,
                                   "first_name": "Alex"},
                             user={"id": "u-operator"}))

    args, _ = fake.members.update_one.call_args
    set_doc = args[1]["$set"]
    # Audit fields NOT re-stamped (no key in $set)
    assert "gdpr_consent" not in set_doc
    assert "gdpr_consent_at" not in set_doc
    assert "marketing_consent" not in set_doc
    # The unrelated field IS updated
    assert set_doc.get("first_name") == "Alex"


# ───────────────────────── Instructor flows ─────────────────────────

def _instr_db(existing=None):
    fake = MagicMock()
    fake.membership_instructors = MagicMock()
    fake.membership_instructors.find_one = AsyncMock(return_value=existing or None)
    fake.membership_instructors.insert_one = AsyncMock()
    fake.membership_instructors.update_one = AsyncMock()
    return fake


def test_create_instructor_requires_gdpr_consent():
    from routes.memberships import instructors as inst
    from routes.memberships.instructors import InstructorIn

    body = InstructorIn(
        name="Test", email="test@example.com", phone="+447700900000",
        gdpr_consent=False,
    )
    fake = _instr_db()

    async def _org(_u): return "org-1"
    async def _slug(_o, _b, exclude_id=None): return "test"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(inst, "_unique_slug", new=AsyncMock(side_effect=_slug)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.create_instructor(body=body, user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "GDPR" in str(exc.value.detail)


def test_create_instructor_with_gdpr_stamps_audit():
    from routes.memberships import instructors as inst
    from routes.memberships.instructors import InstructorIn

    body = InstructorIn(
        name="Test", email="test@example.com", phone="+447700900000",
        gdpr_consent=True, marketing_consent=True,
    )
    fake = _instr_db()

    async def _org(_u): return "org-1"
    async def _slug(_o, _b, exclude_id=None): return "test"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org", new=AsyncMock(side_effect=_org)), \
         patch.object(inst, "_unique_slug", new=AsyncMock(side_effect=_slug)):
        result = _run(inst.create_instructor(body=body, user={"id": "u-op"}))

    doc = fake.membership_instructors.insert_one.call_args[0][0]
    assert doc["gdpr_consent"] is True
    assert doc["gdpr_consent_at"]
    assert doc["gdpr_consent_actor_id"] == "u-op"
    assert doc["marketing_consent"] is True
    assert doc["marketing_consent_at"]
    assert result["instructor"]["gdpr_consent"] is True


def test_patch_instructor_stamps_consent_on_change():
    from routes.memberships import instructors as inst
    from routes.memberships.instructors import InstructorPatch

    existing = {"id": "i1", "organization_id": "org-1",
                "name": "Test", "email": "old@example.com",
                "gdpr_consent": False, "marketing_consent": False}
    fake = _instr_db(existing=existing)
    fake.membership_instructors.find_one = AsyncMock(side_effect=[existing, existing])

    async def _org(_u): return "org-1"

    body = InstructorPatch(gdpr_consent=True, marketing_consent=True)

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org", new=AsyncMock(side_effect=_org)):
        _run(inst.patch_instructor(instructor_id="i1", body=body, user={"id": "u-op"}))

    # First update_one is the $set; second is the $unset for cached_og.
    args, _ = fake.membership_instructors.update_one.call_args_list[0]
    set_doc = args[1]["$set"]
    assert set_doc["gdpr_consent"] is True
    assert set_doc["gdpr_consent_at"]
    assert set_doc["gdpr_consent_actor_id"] == "u-op"
    assert set_doc["marketing_consent"] is True


def test_patch_instructor_rejects_invalid_email():
    from routes.memberships import instructors as inst
    from routes.memberships.instructors import InstructorPatch

    existing = {"id": "i1", "organization_id": "org-1",
                "name": "Test", "email": "old@example.com",
                "gdpr_consent": True}
    fake = _instr_db(existing=existing)

    async def _org(_u): return "org-1"

    body = InstructorPatch(email="not-an-email")

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org", new=AsyncMock(side_effect=_org)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.patch_instructor(instructor_id="i1", body=body, user={"id": "u-op"}))
        assert exc.value.status_code == 400
