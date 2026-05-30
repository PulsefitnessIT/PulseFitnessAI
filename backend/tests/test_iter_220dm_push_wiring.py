"""Iter 220dm — Push-backend wiring sweep.

The ``EngineerAppShellNudge`` (Iter 220df) enables engineers to
subscribe to Web Push, but the value only lands when real events
actually fire. This iter pins:

  * **``job_assigned``** fires when an engineer is assigned via the
    diary dispatch endpoint.
  * **``job_rescheduled``** fires when the same engineer keeps the
    job but the time changes.
  * **``job_unassigned``** fires to the previous engineer when a
    job is reassigned to someone else.
  * **``ppm_due``** fires from the new sweeper endpoint for PPM
    cases scheduled within the window.
  * The dispatcher now LOGS failures instead of swallowing them
    silently (regression visibility win).
  * Dedupe guard prevents the same ``ppm_due`` notification firing
    twice within 18 hours.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _admin():
    return {
        "id": "admin-1", "organization_id": "org-1",
        "role": "owner", "is_master_admin": False,
        "email": "a@x.test", "full_name": "Admin",
    }


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


# ── 1 · ``ppm_due`` sweeper ──────────────────────────────────────


def test_ppm_due_endpoint_requires_admin():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.ppm_reminders import fire_ppm_due_reminders
        return await fire_ppm_due_reminders(
            hours_ahead=24,
            user={"id": "u-1", "organization_id": "org-1",
                  "role": "staff", "is_master_admin": False},
        )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 403


def test_ppm_due_sweeper_fires_one_per_case_and_returns_counts():
    fdb = MagicMock()
    when = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    fdb.svc_cases.find = MagicMock(return_value=_chain([
        {
            "id": "case-1", "organization_id": "org-1",
            "reference": "GA-100", "title": "Treadmill PPM",
            "site_name": "London HQ", "scheduled_at": when,
            "assigned_engineer_id": "eng-1",
        },
        {
            "id": "case-2", "organization_id": "org-1",
            "reference": "GA-101", "title": "Bike PPM",
            "site_name": "Manchester", "scheduled_at": when,
            "assigned_engineer_id": "eng-2",
        },
    ]))
    fdb.svc_notifications.find_one = AsyncMock(return_value=None)
    notify = AsyncMock()

    async def run():
        with patch("routes.svc.ppm_reminders.db", fdb), \
             patch("routes.svc.notifications.create_notification", notify):
            from routes.svc.ppm_reminders import fire_ppm_due_reminders
            return await fire_ppm_due_reminders(
                hours_ahead=24, organization_id=None,
                user=_admin(),
            )

    out = _run(run())
    assert out["scanned"] == 2
    assert out["fired"] == 2
    assert out["skipped_dupe"] == 0
    # ``create_notification`` called twice with kind='ppm_due'.
    assert notify.await_count == 2
    kinds = {c.kwargs["kind"] for c in notify.await_args_list}
    assert kinds == {"ppm_due"}


def test_ppm_due_skips_when_recent_notification_exists():
    fdb = MagicMock()
    when = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    fdb.svc_cases.find = MagicMock(return_value=_chain([{
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "scheduled_at": when,
        "assigned_engineer_id": "eng-1",
    }]))
    # A previous ppm_due notification within the dedupe window exists.
    fdb.svc_notifications.find_one = AsyncMock(return_value={"id": "n-old"})
    notify = AsyncMock()

    async def run():
        with patch("routes.svc.ppm_reminders.db", fdb), \
             patch("routes.svc.notifications.create_notification", notify):
            from routes.svc.ppm_reminders import fire_ppm_due_reminders
            return await fire_ppm_due_reminders(
                hours_ahead=24, organization_id=None, user=_admin(),
            )

    out = _run(run())
    assert out["fired"] == 0
    assert out["skipped_dupe"] == 1
    notify.assert_not_called()


def test_ppm_due_query_is_scoped_to_ppm_open_states_and_window():
    """Pin the Mongo filter so a refactor can't widen scope to
    repair / install / closed cases — that would spam engineers."""
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.ppm_reminders.db", fdb):
            from routes.svc.ppm_reminders import fire_ppm_due_reminders
            await fire_ppm_due_reminders(
                hours_ahead=24, organization_id=None, user=_admin(),
            )

    _run(run())
    flt = fdb.svc_cases.find.call_args.args[0]
    assert flt["case_type"] == "ppm"
    assert set(flt["status"]["$in"]) == {"new", "scheduled", "assigned"}
    assert flt["assigned_engineer_id"]["$exists"] is True
    # Window narrowed to (now, now + hours_ahead).
    assert "$gte" in flt["scheduled_at"]
    assert "$lte" in flt["scheduled_at"]
    # Non-master-admin → always scoped to caller's org.
    assert flt["organization_id"] == "org-1"


def test_ppm_due_master_admin_can_target_a_different_org():
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.ppm_reminders.db", fdb):
            from routes.svc.ppm_reminders import fire_ppm_due_reminders
            await fire_ppm_due_reminders(
                hours_ahead=24, organization_id="org-pulse",
                user={
                    "id": "ma-1", "organization_id": "org-internal",
                    "is_master_admin": True,
                },
            )

    _run(run())
    flt = fdb.svc_cases.find.call_args.args[0]
    assert flt["organization_id"] == "org-pulse"


# ── 2 · Dispatch fires `job_assigned` / `job_rescheduled` ────────


def _diary_db(*, prev_engineer=None, status="new"):
    """Set up the bare minimum Mongo doubles for ``dispatch`` to run
    end-to-end without exploding."""
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill belt",
        "site_name": "London HQ",
        "status": status,
        "assigned_engineer_id": prev_engineer,
        "comms_auto_notify": False,
    })
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_engineers.find_one = AsyncMock(return_value={
        "id": "eng-new", "user_id": "eng-new",
        "full_name": "Eng New", "email": "e@x.test",
    })
    fdb.svc_engineer_availability.find_one = AsyncMock(return_value=None)
    fdb.svc_case_events.insert_one = AsyncMock()
    fdb.organizations.find_one = AsyncMock(return_value={
        "id": "org-1", "name": "Acme",
    })
    return fdb


def test_dispatch_fires_job_assigned_for_new_engineer():
    fdb = _diary_db(prev_engineer=None, status="new")
    notify = AsyncMock()

    async def run():
        with patch("routes.svc.diary.db", fdb), \
             patch("utils.svc_state.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", notify):
            from routes.svc.diary import admin_assign_case as dispatch
            from routes.svc.diary import AssignIn as DispatchIn
            return await dispatch(
                case_id="case-1",
                body=DispatchIn(
                    engineer_id="eng-new",
                    scheduled_at="2026-06-01T09:00:00Z",
                    estimated_minutes=60,
                ),
                user=_admin(),
            )

    _run(run())
    kinds = [c.kwargs["kind"] for c in notify.await_args_list]
    assert "job_assigned" in kinds
    # Notification routed to the new engineer.
    assigned = next(c for c in notify.await_args_list
                    if c.kwargs["kind"] == "job_assigned")
    assert assigned.kwargs["user_id"] == "eng-new"
    assert assigned.kwargs["source_id"] == "case-1"


def test_dispatch_fires_job_rescheduled_when_same_engineer():
    fdb = _diary_db(prev_engineer="eng-new", status="scheduled")
    notify = AsyncMock()

    async def run():
        with patch("routes.svc.diary.db", fdb), \
             patch("utils.svc_state.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", notify):
            from routes.svc.diary import admin_assign_case as dispatch
            from routes.svc.diary import AssignIn as DispatchIn
            return await dispatch(
                case_id="case-1",
                body=DispatchIn(
                    engineer_id="eng-new",
                    scheduled_at="2026-06-01T15:00:00Z",
                    estimated_minutes=60,
                ),
                user=_admin(),
            )

    _run(run())
    kinds = {c.kwargs["kind"] for c in notify.await_args_list}
    assert "job_rescheduled" in kinds
    # No job_assigned fires when engineer is unchanged.
    assert "job_assigned" not in kinds


def test_dispatch_fires_job_unassigned_to_previous_engineer():
    fdb = _diary_db(prev_engineer="eng-old", status="scheduled")
    notify = AsyncMock()

    async def run():
        with patch("routes.svc.diary.db", fdb), \
             patch("utils.svc_state.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", notify):
            from routes.svc.diary import admin_assign_case as dispatch
            from routes.svc.diary import AssignIn as DispatchIn
            return await dispatch(
                case_id="case-1",
                body=DispatchIn(
                    engineer_id="eng-new",
                    scheduled_at="2026-06-01T15:00:00Z",
                    estimated_minutes=60,
                ),
                user=_admin(),
            )

    _run(run())
    by_kind = {c.kwargs["kind"]: c.kwargs for c in notify.await_args_list}
    assert "job_assigned" in by_kind
    assert "job_unassigned" in by_kind
    assert by_kind["job_assigned"]["user_id"] == "eng-new"
    assert by_kind["job_unassigned"]["user_id"] == "eng-old"


def test_dispatch_logs_but_does_not_raise_on_notification_failure():
    """The notification failure path must NOT break dispatch — the
    job assignment write has already happened. Pin that the function
    swallows the exception (after logging) and continues."""
    fdb = _diary_db(prev_engineer=None, status="new")
    broken = AsyncMock(side_effect=RuntimeError("Push provider down"))

    async def run():
        with patch("routes.svc.diary.db", fdb), \
             patch("utils.svc_state.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", broken):
            from routes.svc.diary import admin_assign_case as dispatch
            from routes.svc.diary import AssignIn as DispatchIn
            return await dispatch(
                case_id="case-1",
                body=DispatchIn(
                    engineer_id="eng-new",
                    scheduled_at="2026-06-01T09:00:00Z",
                    estimated_minutes=60,
                ),
                user=_admin(),
            )

    out = _run(run())
    # Dispatch returned successfully.
    assert out is not None


# ── 3 · TOGGLEABLE_PUSH_KINDS still pins the three event kinds ───


def test_push_kinds_pin_the_audit_targets():
    """A regression dropping any of these kinds would silently mute
    the corresponding notification channel."""
    from routes.svc.notifications import TOGGLEABLE_PUSH_KINDS
    for kind in ("job_assigned", "job_rescheduled", "ppm_due"):
        assert kind in TOGGLEABLE_PUSH_KINDS, f"{kind} dropped from toggleable kinds"


# ── 4 · Dispatch log line replaces silent bare ``pass`` ──────────


def test_dispatch_notification_error_is_logged_not_swallowed():
    """Belt-and-braces: the iter explicitly swapped ``pass`` for a
    warning log so future regressions are visible. Pin the source."""
    src = Path("/app/backend/routes/svc/diary.py").read_text()
    assert 'logger.warning("dispatch notification failed' in src
    # The bare-except pass we replaced must NOT be there any more.
    assert "pass  # never let notifications break the dispatch flow." not in src
