"""Iter 220e2 — Cover banner three-tone trichotomy.

Operator follow-up (Feb 2026):

    > Chargeable red banner — Warranty/Contract green banner.
    > Orange banner if the warranty/contract is due to end within 3
    > months.

Extends the iter 220e1 cover chip with a `tone` discriminator that
drives the Tailwind palette on both the Engineer Summary chip/banner
and the Public Tracking chip:

  * `red`   → chargeable
  * `amber` → covered, but ≤90 days of runway left on the warranty or
              service contract (gives ops a renewal signal *before*
              the customer becomes a chargeable case).
  * `green` → comfortably covered.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def _today_plus(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


# ── 1 · Backend public payload tone ──────────────────────────────


def _stub_pt_db(case_extras: dict):
    base = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill",
        "status": "scheduled", "priority": "P3",
        "site_name": "London HQ", "customer_name": "Chris",
        "assigned_engineer_id": "eng-1",
        "scheduled_at": "2026-06-04T09:30:00+00:00",
        "updated_at": "2026-06-01T12:00:00+00:00",
    }
    base.update(case_extras)
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=base)
    fdb.svc_engineers.find_one = AsyncMock(return_value={
        "id": "eng-1", "full_name": "Sam", "verified": True,
    })

    def _events(*_a, **_k):
        cur = MagicMock()
        cur.sort.return_value = cur
        cur.limit.return_value = cur
        cur.to_list = AsyncMock(return_value=[])
        return cur

    fdb.svc_case_events.find = MagicMock(side_effect=_events)
    fdb.organizations.find_one = AsyncMock(return_value={
        "id": "org-1", "name": "Acme",
    })
    return fdb


def _track(fdb):
    async def go():
        with patch("routes.svc.public_tracking.db", fdb), \
             patch(
                 "routes.svc.public_tracking._engineer_live_location",
                 AsyncMock(return_value=None),
             ), \
             patch(
                 "routes.svc.public_tracking._engineer_public_stats",
                 AsyncMock(return_value={}),
             ), \
             patch(
                 "routes.svc.public_tracking._public_compliance_summary",
                 AsyncMock(return_value={}),
             ):
            from routes.svc.public_tracking import public_track
            return await public_track(token="tok-xyzlongtoken")

    return _run(go())


def test_chargeable_returns_red_tone():
    out = _track(_stub_pt_db({"cover_type": "chargeable"}))
    cover = out["cover"]
    assert cover["covered"] is False
    assert cover["tone"] == "red"
    assert cover["expiring_soon"] is False


def test_contract_with_runway_returns_green_tone():
    out = _track(_stub_pt_db({
        "source_meta": {
            "coverage_status": "covered",
            "contract_end_date": _today_plus(365),  # plenty of runway
        },
    }))
    cover = out["cover"]
    assert cover["covered"] is True
    assert cover["tone"] == "green"
    assert cover["expiring_soon"] is False
    assert "Covered by service contract" in cover["label"]


def test_contract_expiring_within_three_months_returns_amber_tone():
    out = _track(_stub_pt_db({
        "source_meta": {
            "coverage_status": "covered",
            "contract_end_date": _today_plus(30),
        },
    }))
    cover = out["cover"]
    assert cover["covered"] is True
    assert cover["tone"] == "amber"
    assert cover["expiring_soon"] is True
    assert cover["days_remaining"] is not None and 0 <= cover["days_remaining"] <= 90
    # Customer-facing label includes the countdown so they know to
    # talk renewal with ops.
    assert "ends in" in cover["label"]


def test_warranty_expiring_within_three_months_returns_amber_tone():
    out = _track(_stub_pt_db({
        "source_meta": {
            "warranty_active": True,
            "warranty_expiry": _today_plus(45),
        },
    }))
    cover = out["cover"]
    assert cover["covered"] is True
    assert cover["kind"] == "warranty"
    assert cover["tone"] == "amber"
    assert cover["expiring_soon"] is True
    assert "Warranty ends in" in cover["label"]


def test_warranty_with_runway_returns_green_tone():
    out = _track(_stub_pt_db({
        "source_meta": {
            "warranty_active": True,
            "warranty_expiry": _today_plus(400),
        },
    }))
    cover = out["cover"]
    assert cover["tone"] == "green"
    assert cover["expiring_soon"] is False


def test_contract_exactly_at_90_day_boundary_is_amber():
    """90 days is the inclusive upper bound — anything ≤90d trips
    the renewal warning."""
    out = _track(_stub_pt_db({
        "source_meta": {
            "coverage_status": "covered",
            "contract_end_date": _today_plus(90),
        },
    }))
    assert out["cover"]["tone"] == "amber"


def test_contract_at_91_days_is_green():
    out = _track(_stub_pt_db({
        "source_meta": {
            "coverage_status": "covered",
            "contract_end_date": _today_plus(91),
        },
    }))
    assert out["cover"]["tone"] == "green"


# ── 2 · Frontend wiring (engineer + public chip) ─────────────────


def test_compute_cover_state_helper_emits_tone():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Helper exposes a `tone` field consumed by the chip + banner.
    assert "tone: 'red'" in src
    assert "tone: expiringSoon ? 'amber' : 'green'" in src
    # 90-day threshold lives in the helper, not sprinkled into UI.
    assert "days <= 90" in src


def test_engineer_chip_and_banner_render_three_tones():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Chip switches palette on cover.tone (green / amber / red).
    assert "data-testid=\"jaag-cover-chip\"" in src
    assert "cover.tone === 'green'" in src
    assert "cover.tone === 'amber'" in src
    # The chargeable branch falls through to rose.
    assert "bg-rose-50 text-rose-800" in src
    # Banner mirrors the same trichotomy.
    assert "data-testid=\"jaag-cover-banner\"" in src
    assert "bg-rose-50 border-rose-300" in src


def test_public_tracking_chip_renders_three_tones():
    src = _read("pages/PublicTracking/PublicTrackingPage.js")
    # Always renders when cover is present (chargeable now shown too).
    assert "data.cover ? (" in src
    # Three-way palette on data.cover.tone.
    assert "data.cover.tone === 'green'" in src
    assert "data.cover.tone === 'amber'" in src
    assert "bg-rose-50 border-rose-300" in src
