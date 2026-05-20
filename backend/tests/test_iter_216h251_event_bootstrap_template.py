"""Iter 216h251 — Bootstrap event from kind.

Auto-populates rehearsals + costume rows for a new event based on its
kind, saving the operator (especially dance-studio prospects setting
up a recital) ~15–20 minutes of manual data entry.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _async_iter(items):
    """Helper: convert a list into an async iterator for db.find()."""
    async def _gen():
        for i in items:
            yield i
    return _gen()


def _fake_events_db(event, existing_rehearsals=None, existing_costumes=None, members=None):
    """Stub for the bootstrap path. find() returns a cursor we make
    iterable; insert_one is just observed for call_count."""
    fake = MagicMock()

    # studio_events.find_one — return the event
    fake.studio_events = MagicMock()
    fake.studio_events.find_one = AsyncMock(return_value=event)

    # event_rehearsals.find — async-iterable cursor
    rehearsal_cursor = MagicMock()
    rehearsal_cursor.__aiter__ = lambda self: _async_iter(existing_rehearsals or [])
    fake.event_rehearsals = MagicMock()
    fake.event_rehearsals.find = MagicMock(return_value=rehearsal_cursor)
    fake.event_rehearsals.insert_one = AsyncMock()

    # event_costumes.find — async-iterable cursor
    costume_cursor = MagicMock()
    costume_cursor.__aiter__ = lambda self: _async_iter(existing_costumes or [])
    fake.event_costumes = MagicMock()
    fake.event_costumes.find = MagicMock(return_value=costume_cursor)
    fake.event_costumes.insert_one = AsyncMock()

    # members.find().limit().to_list() — return the seeded members
    members_chain = MagicMock()
    members_chain.limit = MagicMock(return_value=members_chain)
    members_chain.to_list = AsyncMock(return_value=members or [])
    fake.members = MagicMock()
    fake.members.find = MagicMock(return_value=members_chain)
    return fake


def test_bootstrap_recital_creates_rehearsals_and_costumes():
    from routes.memberships import events as ev

    event = {
        "id": "evt-1", "organization_id": "org-1", "kind": "recital",
        "starts_at": "2026-06-15T18:00:00+00:00",
        "ends_at":   "2026-06-15T20:00:00+00:00",
    }
    members = [
        {"id": "m1", "first_name": "Aiden", "last_name": "Rowe"},
        {"id": "m2", "first_name": "Bella", "last_name": "Khan"},
        {"id": "m3", "first_name": "Chloe", "last_name": "Day"},
    ]
    fake = _fake_events_db(event, members=members)

    user = {"id": "u-1", "organization_id": "org-1", "role": "owner"}
    body = ev.BootstrapIn()

    with patch.object(ev, "db", fake), \
         patch.object(ev, "_require_operator_org", AsyncMock(return_value="org-1")):
        out = _run(ev.bootstrap_event_from_kind("evt-1", body=body, user=user))

    assert out["ok"] is True
    assert out["kind"] == "recital"
    # Recital template has 2 rehearsals.
    assert out["rehearsals_created"] == 2
    assert fake.event_rehearsals.insert_one.await_count == 2
    # 3 members → 3 costume rows.
    assert out["costumes_created"] == 3
    assert fake.event_costumes.insert_one.await_count == 3


def test_bootstrap_workshop_skips_costumes():
    """Workshops + camps don't auto-create costumes — only a prep meeting."""
    from routes.memberships import events as ev

    event = {
        "id": "evt-2", "organization_id": "org-1", "kind": "workshop",
        "starts_at": "2026-07-01T10:00:00+00:00",
        "ends_at":   "2026-07-01T12:00:00+00:00",
    }
    fake = _fake_events_db(event, members=[{"id": "m1", "first_name": "X", "last_name": "Y"}])
    user = {"id": "u-1", "organization_id": "org-1", "role": "owner"}

    with patch.object(ev, "db", fake), \
         patch.object(ev, "_require_operator_org", AsyncMock(return_value="org-1")):
        out = _run(ev.bootstrap_event_from_kind("evt-2", body=ev.BootstrapIn(), user=user))

    assert out["rehearsals_created"] == 1  # "Prep meeting"
    assert out["costumes_created"] == 0
    assert fake.event_costumes.insert_one.await_count == 0


def test_bootstrap_idempotent_on_existing_rehearsal_name():
    """Re-running on a populated event skips rehearsals whose names
    already exist (case-insensitive)."""
    from routes.memberships import events as ev

    event = {
        "id": "evt-3", "organization_id": "org-1", "kind": "recital",
        "starts_at": "2026-06-15T18:00:00+00:00",
        "ends_at":   "2026-06-15T20:00:00+00:00",
    }
    existing = [{"name": "TECH REHEARSAL"}]  # uppercase to verify case-insensitive
    fake = _fake_events_db(event, existing_rehearsals=existing, members=[])
    user = {"id": "u-1", "organization_id": "org-1", "role": "owner"}

    with patch.object(ev, "db", fake), \
         patch.object(ev, "_require_operator_org", AsyncMock(return_value="org-1")):
        out = _run(ev.bootstrap_event_from_kind("evt-3", body=ev.BootstrapIn(), user=user))

    # Tech rehearsal pre-exists → only "Dress rehearsal" should be added.
    assert out["rehearsals_created"] == 1
    assert out["rehearsals_skipped"] == 1


def test_bootstrap_respects_include_flags():
    """Operator can disable rehearsal OR costume bootstrapping."""
    from routes.memberships import events as ev

    event = {
        "id": "evt-4", "organization_id": "org-1", "kind": "recital",
        "starts_at": "2026-06-15T18:00:00+00:00",
        "ends_at":   "2026-06-15T20:00:00+00:00",
    }
    fake = _fake_events_db(event, members=[{"id": "m1", "first_name": "A", "last_name": "B"}])
    user = {"id": "u-1", "organization_id": "org-1", "role": "owner"}

    with patch.object(ev, "db", fake), \
         patch.object(ev, "_require_operator_org", AsyncMock(return_value="org-1")):
        out = _run(ev.bootstrap_event_from_kind(
            "evt-4",
            body=ev.BootstrapIn(include_rehearsals=False, include_costumes=False),
            user=user,
        ))

    assert out["rehearsals_created"] == 0
    assert out["costumes_created"] == 0


def test_bootstrap_404_for_unknown_event():
    from routes.memberships import events as ev
    from fastapi import HTTPException

    fake = MagicMock()
    fake.studio_events = MagicMock()
    fake.studio_events.find_one = AsyncMock(return_value=None)

    user = {"id": "u-1", "organization_id": "org-1", "role": "owner"}
    with patch.object(ev, "db", fake), \
         patch.object(ev, "_require_operator_org", AsyncMock(return_value="org-1")):
        try:
            _run(ev.bootstrap_event_from_kind("nope", body=ev.BootstrapIn(), user=user))
            raise AssertionError("expected 404")
        except HTTPException as e:
            assert e.status_code == 404


# ─── Frontend assertions ───────────────────────────────────────────

def test_create_event_modal_offers_template_toggle():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/EventsTab.js").read_text()
    # Toggle state present.
    assert "useTemplate" in src
    # Default templated kinds include the 3 high-value ones.
    assert "new Set(['recital', 'showcase', 'competition'])" in src
    # Bootstrap endpoint called on save when toggle is on.
    assert "/bootstrap-from-kind" in src
    # Checkbox testId surfaced.
    assert 'data-testid="events-create-template"' in src


def test_bootstrap_endpoint_registered():
    src = pathlib.Path("/app/backend/routes/memberships/events.py").read_text()
    assert '/memberships/events/{event_id}/bootstrap-from-kind' in src
    assert 'class BootstrapIn(BaseModel)' in src
    # Templates list the expected kinds.
    for kind in ("recital", "showcase", "competition", "workshop", "camp"):
        assert f'"{kind}":' in src
