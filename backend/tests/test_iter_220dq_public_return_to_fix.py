"""Iter 220dq — Public live-tracking surfaces Return-to-fix.

The engineer can flag a case as "needs a second visit" via Iter
220dp's ``POST /svc/engineer/jobs/{id}/return-to-fix``. This iter
closes the customer-side loop:

  * ``GET /api/svc/public/track/{token}`` exposes a customer-safe
    ``return_to_fix`` block (``return_at`` + truncated ``reason``).
  * ``PublicTrackingPage.js`` renders an amber "Return visit
    booked" banner with the formatted date + reason whenever the
    field is set — so the customer doesn't phone in to ask "when
    are they coming back?".
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _case(extra: dict | None = None) -> dict:
    base = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill belt",
        "status": "scheduled", "priority": "P3",
        "site_name": "London HQ", "customer_name": "Chris Smith",
        "assigned_engineer_id": "eng-1",
        "scheduled_at": "2026-06-04T09:30:00+00:00",
        "updated_at": "2026-06-01T12:00:00+00:00",
    }
    base.update(extra or {})
    return base


def _stub_db(case: dict) -> MagicMock:
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=case)
    fdb.svc_engineers.find_one = AsyncMock(return_value={
        "id": "eng-1", "full_name": "Sam Engineer", "verified": True,
    })

    def _events_chain(*_a, **_k):
        cur = MagicMock()
        cur.sort.return_value = cur
        cur.limit.return_value = cur
        cur.to_list = AsyncMock(return_value=[])
        return cur

    fdb.svc_case_events.find = MagicMock(side_effect=_events_chain)
    fdb.organizations.find_one = AsyncMock(return_value={
        "id": "org-1", "name": "Acme", "brand_primary_color": "#0055FF",
    })
    return fdb


def _patches(fdb):
    return (
        patch("routes.svc.public_tracking.db", fdb),
        patch(
            "routes.svc.public_tracking._engineer_live_location",
            AsyncMock(return_value=None),
        ),
        patch(
            "routes.svc.public_tracking._engineer_public_stats",
            AsyncMock(return_value={}),
        ),
        patch(
            "routes.svc.public_tracking._public_compliance_summary",
            AsyncMock(return_value={}),
        ),
    )


# ── 1 · Backend exposes a customer-safe `return_to_fix` block ────


def test_public_track_returns_null_return_to_fix_when_not_flagged():
    fdb = _stub_db(_case())

    async def go():
        with _patches(fdb)[0], _patches(fdb)[1], \
             _patches(fdb)[2], _patches(fdb)[3]:
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    out = _run(go())
    assert "return_to_fix" in out
    assert out["return_to_fix"] is None


def test_public_track_surfaces_return_visit_when_set():
    fdb = _stub_db(_case({
        "return_to_fix": {
            "id": "rtf-1",
            "engineer_id": "eng-1",
            "engineer_name": "Sam",
            "reason": "Parts on order — drive belt due Tuesday",
            "return_at": "2026-06-09T09:00:00+00:00",
            "created_at": "2026-06-04T17:30:00+00:00",
        },
    }))

    async def go():
        with _patches(fdb)[0], _patches(fdb)[1], \
             _patches(fdb)[2], _patches(fdb)[3]:
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    out = _run(go())
    assert out["return_to_fix"] is not None
    assert out["return_to_fix"]["return_at"] == "2026-06-09T09:00:00+00:00"
    assert out["return_to_fix"]["reason"] == "Parts on order — drive belt due Tuesday"
    # Internal-only fields must NOT leak to the customer payload.
    for leaky in ("engineer_id", "engineer_name", "created_at", "id"):
        assert leaky not in out["return_to_fix"], (
            f"`{leaky}` leaked into customer-facing payload"
        )


def test_public_track_return_reason_truncated_at_240_chars():
    long_reason = "a" * 500
    fdb = _stub_db(_case({
        "return_to_fix": {
            "reason": long_reason,
            "return_at": "2026-06-09T09:00:00+00:00",
        },
    }))

    async def go():
        with _patches(fdb)[0], _patches(fdb)[1], \
             _patches(fdb)[2], _patches(fdb)[3]:
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    out = _run(go())
    assert len(out["return_to_fix"]["reason"]) == 240


def test_public_track_return_reason_blank_becomes_none():
    fdb = _stub_db(_case({
        "return_to_fix": {
            "reason": "",
            "return_at": "2026-06-09T09:00:00+00:00",
        },
    }))

    async def go():
        with _patches(fdb)[0], _patches(fdb)[1], \
             _patches(fdb)[2], _patches(fdb)[3]:
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    out = _run(go())
    assert out["return_to_fix"]["reason"] is None


def test_public_track_return_skipped_when_return_at_missing():
    """Guard: a `return_to_fix` block without a `return_at` (corrupt
    data) must NOT render — the customer banner would be useless and
    misleading."""
    fdb = _stub_db(_case({
        "return_to_fix": {"reason": "Parts on order"},
    }))

    async def go():
        with _patches(fdb)[0], _patches(fdb)[1], \
             _patches(fdb)[2], _patches(fdb)[3]:
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    out = _run(go())
    assert out["return_to_fix"] is None


# ── 2 · Frontend banner pinned in the page source ────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_public_tracking_page_renders_return_to_fix_banner():
    src = _read("pages/PublicTracking/PublicTrackingPage.js")
    # Conditional render guard pinned.
    assert "data.return_to_fix?.return_at" in src
    # The amber visual treatment + testids the test agent watches.
    assert 'data-testid="track-return-to-fix"' in src
    assert 'data-testid="track-return-to-fix-date"' in src
    assert 'data-testid="track-return-to-fix-reason"' in src
    # Friendly formatter for the booked date.
    assert "function fmtReturnAt" in src
    assert "fmtReturnAt(data.return_to_fix.return_at)" in src
