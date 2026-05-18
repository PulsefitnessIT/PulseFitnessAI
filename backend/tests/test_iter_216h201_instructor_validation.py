"""Iter 216h201 — Memberships UX & instructor validation.

Backend-layer coverage for Craig & Lee's reported issues:
  (A) Instructor create now requires email + phone (Craig's screenshot
      called out missing validation on these fields).
  (B) Email format is enforced server-side.

UI fixes (cursor loss in Add Instructor, light-mode leakage on member
portal, $→£ icon swap, Open Wizard logout) are covered by the
testing-agent frontend pass — no Pytest applicable.

Run: pytest backend/tests/test_iter_216h201_instructor_validation.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_fake_db():
    fake = MagicMock()
    fake.membership_instructors = MagicMock()
    fake.membership_instructors.find_one = AsyncMock(return_value=None)
    fake.membership_instructors.insert_one = AsyncMock()
    return fake


def _make_body(**overrides):
    from routes.memberships.instructors import InstructorIn

    base = {
        "name": "Chuck Brown",
        "email": "chuck@example.com",
        "phone": "07700900000",
        # Iter 216h207 — GDPR consent is now mandatory on instructor
        # creation (parity with the Add member modal).
        "gdpr_consent": True,
    }
    base.update(overrides)
    return InstructorIn(**base)


def test_create_instructor_rejects_missing_email() -> None:
    from routes.memberships import instructors as inst

    body = _make_body(email=None)
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.create_instructor(body=body, user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "email" in str(exc.value.detail).lower()


def test_create_instructor_rejects_invalid_email_format() -> None:
    from routes.memberships import instructors as inst

    body = _make_body(email="not-an-email")
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.create_instructor(body=body, user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "email" in str(exc.value.detail).lower()


def test_create_instructor_rejects_missing_phone() -> None:
    from routes.memberships import instructors as inst

    body = _make_body(phone="")
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.create_instructor(body=body, user={"id": "u1"}))
        assert exc.value.status_code == 400
        assert "phone" in str(exc.value.detail).lower()


def test_create_instructor_rejects_whitespace_only_phone() -> None:
    from routes.memberships import instructors as inst

    body = _make_body(phone="   ")
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)):
        with pytest.raises(HTTPException) as exc:
            _run(inst.create_instructor(body=body, user={"id": "u1"}))
        assert exc.value.status_code == 400


def test_create_instructor_happy_path_inserts_doc() -> None:
    from routes.memberships import instructors as inst

    body = _make_body()
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"
    async def _stub_unique_slug(o, b, exclude_id=None): return "chuck-brown"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)), \
         patch.object(inst, "_unique_slug",
                      new=AsyncMock(side_effect=_stub_unique_slug)):
        result = _run(inst.create_instructor(body=body, user={"id": "u1"}))

    assert "instructor" in result
    fake.membership_instructors.insert_one.assert_called_once()
    doc = fake.membership_instructors.insert_one.call_args[0][0]
    assert doc["email"] == "chuck@example.com"
    assert doc["phone"] == "07700900000"
    assert doc["slug"] == "chuck-brown"
    assert doc["organization_id"] == "org-1"


def test_create_instructor_trims_whitespace_on_email_and_phone() -> None:
    from routes.memberships import instructors as inst

    body = _make_body(email="  chuck@example.com  ", phone="  07700900000  ")
    fake = _build_fake_db()

    async def _stub_require_operator_org(u): return "org-1"
    async def _stub_unique_slug(o, b, exclude_id=None): return "chuck-brown"

    with patch.object(inst, "db", fake), \
         patch.object(inst, "_require_operator_org",
                      new=AsyncMock(side_effect=_stub_require_operator_org)), \
         patch.object(inst, "_unique_slug",
                      new=AsyncMock(side_effect=_stub_unique_slug)):
        _run(inst.create_instructor(body=body, user={"id": "u1"}))

    doc = fake.membership_instructors.insert_one.call_args[0][0]
    assert doc["email"] == "chuck@example.com"
    assert doc["phone"] == "07700900000"
