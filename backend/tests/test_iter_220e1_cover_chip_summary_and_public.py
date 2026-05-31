"""Iter 220e1 — Cover chip + banner on Summary, cover chip on public tracking.

Operator follow-up (Feb 2026):

  > The engineer also needs to see what type of cover if any the
  > gym has on the summary screen so they know they can work on
  > the machines and fit parts or they have to wait for
  > authorisation.

Wires the shared `computeCoverState(job)` helper into:

  * **Engineer Summary (JobAtAGlance)** — a small chip in the chip
    row (`jaag-cover-chip`) plus a fuller actionable banner above
    the existing warnings (`jaag-cover-banner` + `-label` /
    `-detail`) that tells the engineer either "proceed without
    spend approval" (covered) or "confirm any spend with the
    customer" (chargeable).
  * **Complete tab** — refactored to consume the same helper so
    the two surfaces can't drift.
  * **Public live-tracking** — additional `cover` block on the
    payload + a green emerald chip on `/svc/public/track/{token}`
    that says "Covered by service contract · no charge" /
    "Under manufacturer warranty". Chargeable cases get nothing
    (no point worrying the customer pre-quote).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── 1 · Shared helper exported once and consumed in two places ────


def test_compute_cover_state_helper_is_exported():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert "export function computeCoverState" in src
    # Recognises contract / warranty / explicit cover_type and
    # treats 'chargeable' / 'none' slugs as no-cover.
    assert "warrantyActive = !!meta.warranty_active" in src
    assert "Under manufacturer warranty" in src
    assert "service contract" in src
    assert "cover !== 'chargeable' && cover !== 'none'" in src
    # Chargeable path returns an actionable "confirm spend" detail
    # so engineers know to call ops before fitting parts.
    assert "Confirm any spend with the customer before fitting parts." in src


def test_complete_tab_reuses_shared_cover_helper():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The Complete tab's `coverState` memo is now a one-liner that
    # delegates to the shared helper instead of duplicating the
    # logic (which was the iter 220e0 implementation).
    assert "useMemo(() => computeCoverState(job)" in src


# ── 2 · JobAtAGlance chip + banner ────────────────────────────────


def test_summary_renders_cover_chip():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Chip lives next to priority + case-type so engineer sees
    # cover state at the same glance as everything else.
    assert 'data-testid="jaag-cover-chip"' in src
    # Chip uses the short label when covered (Warranty / GOLD
    # contract / etc) and "Chargeable" when not.
    assert "cover.covered ? (cover.short || 'Covered') : 'Chargeable'" in src


def test_summary_renders_cover_banner_with_actionable_detail():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="jaag-cover-banner"' in src
    assert 'data-testid="jaag-cover-banner-label"' in src
    assert 'data-testid="jaag-cover-banner-detail"' in src
    # Detail wording for the two states (proven via the helper test
    # already — re-pin so future copy tweaks intentionally break
    # both tests together).
    assert "Parts + labour covered by the contract." in src
    assert "Parts + labour are warranty-funded." in src


# ── 3 · Public tracking payload + chip ────────────────────────────


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
        "id": "eng-1", "full_name": "Sam Engineer", "verified": True,
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


def test_public_track_returns_contract_cover_label():
    out = _track(_stub_pt_db({
        "source_meta": {"coverage_status": "covered", "contract_tier": "gold"},
    }))
    assert out["cover"]["covered"] is True
    assert out["cover"]["kind"] == "contract"
    assert "Covered by service contract" in out["cover"]["label"]


def test_public_track_returns_warranty_cover_label():
    out = _track(_stub_pt_db({
        "source_meta": {"warranty_active": True},
    }))
    assert out["cover"]["covered"] is True
    assert out["cover"]["kind"] == "warranty"
    assert out["cover"]["label"] == "Under manufacturer warranty"


def test_public_track_returns_chargeable_when_no_cover():
    out = _track(_stub_pt_db({
        "cover_type": "chargeable",
    }))
    assert out["cover"]["covered"] is False
    assert out["cover"]["kind"] == "chargeable"


def test_public_track_does_not_leak_contract_numbers_to_customer():
    """The customer payload should NEVER expose contract numbers,
    titles, tier-internal ids, or warranty expiry dates. Only the
    short reassurance label."""
    out = _track(_stub_pt_db({
        "source_meta": {
            "coverage_status": "covered",
            "contract_number": "C-123",
            "contract_title": "Internal Pulse contract",
            "contract_end_date": "2027-12-31",
            "contract_id": "ct-internal",
            "warranty_expiry": "2030-01-01",
        },
    }))
    cover = out["cover"]
    for leaky in (
        "contract_number", "contract_title", "contract_id",
        "contract_end_date", "warranty_expiry",
    ):
        assert leaky not in cover, f"`{leaky}` leaked into customer payload"


def test_public_tracking_page_renders_cover_chip():
    src = _read("pages/PublicTracking/PublicTrackingPage.js")
    # Conditional render — present whenever the payload includes a
    # cover block (iter 220e2 added the chargeable red variant, so
    # we no longer gate on `covered` truthiness).
    assert "data.cover ? (" in src
    assert 'data-testid="track-cover-chip"' in src
    assert 'data-testid="track-cover-label"' in src
    # Uses ShieldCheck (we imported it for the broader cover ux).
    assert "ShieldCheck" in src
