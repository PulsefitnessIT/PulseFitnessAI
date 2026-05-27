"""Iter 220p — Engineer queue "My gyms" filter pill.

When a Partner Engineer brings in a gym (via referral; iter 220n
auto-attaches them as the gym's primary auto_dispatch=True supplier),
and that gym subsequently logs a fault, a supplier_case is auto-minted
addressed to the engineer's email. This iter surfaces those cases as a
"My gyms" tab on the engineer's queue page so they have a single
inbox for all their referred-gym work without trawling email.

API contract:
  GET /api/svc/engineer/queue/my-gyms  (engineer-only)
  →
  {
    "jobs": [
      {
        "id": "...", "supplier_case_token": "...",
        "issue_id": "...", "title": "...", "priority": "...",
        "organization_name": "...", "site_name": "...",
        "machine_name": "...", "sla_resolve_at": "...",
        "from_referred_gym": true|false,
        "is_primary_supplier": true|false,
        "status": "in_progress", "created_at": "..."
      }, ...
    ],
    "total": int, "gyms_count": int,
    "is_partner_engineer": true,
    "no_gyms_yet": bool   # set when partner has zero supplier rows yet
  }

Frontend pin (source-level):
  * EngineerQueue.js mounts a hidden-when-not-applicable view switcher
    pill ("Up for grabs" / "My gyms"). Pill is gated on
    `is_partner_engineer` so non-engineer users don't see it.
  * Rows from "My gyms" view get a violet "★ Referred" badge when
    `from_referred_gym` is true, and an "Open ticket" CTA instead of
    the claim button (those cases came in via the supplier-portal
    token flow — they're already dispatched).
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Backend endpoint shape ─────────────────────────────────────────


def test_my_gyms_returns_empty_when_user_not_partner_engineer():
    """Master admins / dispatchers / non-engineer users that hit the
    endpoint must get a soft empty result, NOT a 500. The route is
    mounted under the engineer-access gate but we still need a
    defensive return."""
    from routes.svc.engineer_queue import my_gyms_queue

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)

    with patch("routes.svc.engineer_queue.db", fake_db):
        res = _run(my_gyms_queue(user={"id": "u1", "email": "admin@x.com"}))

    assert res == {"jobs": [], "total": 0, "is_partner_engineer": False}


def test_my_gyms_returns_no_gyms_yet_when_partner_has_no_supplier_rows():
    """A Partner Engineer who hasn't been auto-attached to any gym
    yet gets the friendly empty state so the UI can show 'Share your
    referral link to onboard gyms.' instead of an unhelpful blank."""
    from routes.svc.engineer_queue import my_gyms_queue

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "email": "eng@example.com", "full_name": "Test",
    })

    # No supplier rows yet — fresh engineer with no referrals onboarded.
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    fake_db.suppliers.find = MagicMock(return_value=cursor)

    with patch("routes.svc.engineer_queue.db", fake_db):
        res = _run(my_gyms_queue(user={"id": "u1", "email": "eng@example.com"}))

    assert res["is_partner_engineer"] is True
    assert res["no_gyms_yet"] is True
    assert res["jobs"] == []


def test_my_gyms_returns_decorated_jobs_for_referred_gyms():
    """End-to-end: partner has 2 referred-gym supplier rows, 3 open
    supplier_cases routed to their email. The endpoint must return
    3 jobs, each carrying `from_referred_gym: true` and a stable
    `supplier_case_token` the row uses to open the supplier portal."""
    from routes.svc.engineer_queue import my_gyms_queue

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "email": "engineer@example.com", "full_name": "Sarah",
    })

    supplier_rows = [
        {"id": "s1", "organization_id": "org_a", "name": "Acme Gym Ltd",
         "email": "engineer@example.com", "is_primary_supplier": True,
         "auto_created_from_referral": True},
        {"id": "s2", "organization_id": "org_b", "name": "Beta Gym Ltd",
         "email": "engineer@example.com", "is_primary_supplier": True,
         "auto_created_from_referral": True},
    ]
    sup_cursor = MagicMock()
    sup_cursor.to_list = AsyncMock(return_value=supplier_rows)
    fake_db.suppliers.find = MagicMock(return_value=sup_cursor)

    supplier_cases = [
        {"id": "sc1", "token": "tok1", "issue_id": "iss_1",
         "supplier_email": "engineer@example.com",
         "organization_name": "Acme Gym Ltd", "status": "in_progress",
         "created_at": "2026-05-26T10:00Z", "title": "Treadmill belt slip",
         "priority": "P2", "site_name": "Acme HQ"},
        {"id": "sc2", "token": "tok2", "issue_id": "iss_2",
         "supplier_email": "engineer@example.com",
         "organization_name": "Beta Gym Ltd", "status": "new",
         "created_at": "2026-05-26T09:30Z", "title": "Rower display",
         "priority": "P3"},
        {"id": "sc3", "token": "tok3", "issue_id": "iss_3",
         "supplier_email": "engineer@example.com",
         "organization_name": "Acme Gym Ltd", "status": "scheduled",
         "created_at": "2026-05-25T15:00Z", "title": "Cable machine"},
    ]
    sc_cursor = MagicMock()
    sc_cursor.to_list = AsyncMock(return_value=supplier_cases)
    fake_db.supplier_cases.find = MagicMock(return_value=sc_cursor)

    with patch("routes.svc.engineer_queue.db", fake_db):
        res = _run(my_gyms_queue(user={"id": "u1", "email": "engineer@example.com"}))

    assert res["is_partner_engineer"] is True
    assert res["total"] == 3
    assert res["gyms_count"] == 2
    # Each job carries the supplier_case_token so the UI can deeplink
    # to the supplier portal.
    tokens = sorted(j["supplier_case_token"] for j in res["jobs"])
    assert tokens == ["tok1", "tok2", "tok3"]
    # Every job from these gyms is flagged as "Referred" (the badge).
    assert all(j["from_referred_gym"] is True for j in res["jobs"])
    # And carries the org name so the row's site/customer subtitle
    # has something to render.
    org_names = {j["organization_name"] for j in res["jobs"]}
    assert org_names == {"Acme Gym Ltd", "Beta Gym Ltd"}


def test_my_gyms_filters_to_open_statuses_only():
    """Closed / resolved supplier_cases must NOT appear in the queue —
    only actively-open work. Pin the Mongo filter at the source level
    so a future tweak to the open-status list can't silently regress."""
    import pathlib
    src = pathlib.Path("/app/backend/routes/svc/engineer_queue.py").read_text()
    # The endpoint must enumerate open statuses + filter with $in.
    assert "open_statuses" in src
    for status in ["new", "in_progress", "awaiting_parts", "scheduled"]:
        assert f'"{status}"' in src, f"Open status `{status}` must be in the whitelist"
    assert '"$in": open_statuses' in src or "{'$in': open_statuses}" in src


# ── Frontend wiring (source-level pins) ─────────────────────────────


def test_engineer_queue_imports_and_renders_view_switcher():
    """The view-switcher pill must be conditionally rendered (only for
    Partner Engineers) and must call `/queue/my-gyms` to pre-populate
    the badge count."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerQueue.js").read_text()
    assert "/svc/engineer/queue/my-gyms" in src, (
        "Queue must fetch the my-gyms endpoint on mount"
    )
    assert "queue-view-switcher" in src, "View switcher must have a testid"
    assert "queue-view-org" in src and "queue-view-my-gyms" in src, (
        "Both view-mode pills must have testids"
    )
    # Must gate on `is_partner_engineer` so non-engineer users don't
    # see a confusing 'My gyms (0)' tab.
    assert "is_partner_engineer" in src


def test_engineer_queue_row_handles_my_gyms_view():
    """My-gyms rows route to the supplier-portal token URL, NOT the
    normal claim modal — those cases are already dispatched."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerQueue.js").read_text()
    assert "isMyGymRow" in src or "viewMode === 'my-gyms'" in src, (
        "Row must branch on view mode"
    )
    assert "/supplier/case/" in src, (
        "Row must deeplink to the supplier-portal token URL"
    )
    assert "supplier_case_token" in src, (
        "Row must read the supplier_case_token from the job payload"
    )
    assert "queue-open-supplier-case-" in src, (
        "Open-ticket CTA needs a testid for E2E"
    )
    # The "★ Referred" provenance badge must be wired in too.
    assert "queue-row-referred-" in src
    assert "from_referred_gym" in src


def test_engineer_queue_my_gyms_uses_brand_gradient_not_legacy_cyan():
    """The active "My gyms" pill must use the canonical GymAxis
    navy→purple gradient — NEVER the legacy Pulse cyan. Pin against
    a brand regression."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerQueue.js").read_text()
    # The gradient is set inline on the active pill button
    assert "#2563EB" in src and "#9D4CDD" in src, (
        "My-gyms pill must use the canonical navy→purple gradient — see "
        "/app/BRAND_PALETTE.md"
    )
    # Sanity: no legacy Pulse cyan literal sneaking into the pill area.
    # (We allow #19CDFF only in legacy / Pulse files — this is GymAxis ops.)
    assert "#19CDFF" not in src, (
        "Engineer queue is a GymAxis surface — Pulse cyan #19CDFF must "
        "not appear. See /app/BRAND_PALETTE.md §2."
    )
