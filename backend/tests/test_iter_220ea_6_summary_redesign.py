"""Iter 220ea·6 — Engineer App Summary tab redesign.

Source-level guards covering the deeper Summary redesign:

* Status pill row (status + SLA countdown + priority) is rendered
  at the top of the JobAtAGlance card.
* Action row (Call · Navigate · Email · Photo) sits between the
  status pill row and the customer/fault block.
* 2x3 Stats grid (on-site time, photos, parts, machines, safety,
  mileage) is rendered with a stable test-id per stat.

The visual hierarchy is asserted by document-order on
``data-testid`` markers — that's the same pattern the rest of the
Engineer App regression tests use.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"


def _read() -> str:
    return JOB_DETAIL.read_text()


# ── 1 · Status pill row ──────────────────────────────────────────


def test_status_pill_component_exists():
    src = _read()
    assert "function SummaryStatusPill(" in src
    assert 'data-testid="summary-status-pill-row"' in src
    assert 'data-testid="summary-status-pill"' in src


def test_status_pill_uses_status_tone_map():
    """We map case status → tone (label, colours, dot). Asserting on
    a couple of well-known statuses keeps the map honest."""
    src = _read()
    assert "const STATUS_TONE" in src
    for status in ("scheduled", "en_route", "in_progress", "awaiting_parts", "closed"):
        assert f"{status}:" in src, f"missing tone for status={status}"


def test_status_pill_renders_sla_countdown():
    src = _read()
    assert "_formatSlaCountdown" in src
    assert "sla_resolve_at" in src
    assert 'data-testid="summary-sla-pill"' in src
    # We surface overdue / urgent / ok state so styles can differ.
    assert "data-sla-state=" in src


def test_status_pill_renders_priority():
    src = _read()
    assert 'data-testid="summary-priority-pill"' in src
    # Iter 220ea·6 — high-priority (P1/CRITICAL/HIGH) gets a rose
    # treatment so it can't be missed; everything else is muted.
    assert "isHighPriority" in src


# ── 2 · Action row ───────────────────────────────────────────────


def test_action_row_component_exists():
    src = _read()
    assert "function SummaryActionRow(" in src
    assert 'data-testid="summary-action-row"' in src


def test_action_row_has_three_canonical_actions():
    """Iter 220ea·7 — Call · Navigate · Email. The Photo action
    was removed (Equipment tab owns per-machine capture)."""
    src = _read()
    # Call / Navigate / Email reuse the pre-existing jaag-* test-ids
    # so existing E2E assertions keep working. The IDs are set
    # dynamically via the action descriptor `testid:` field.
    assert "testid: 'jaag-call'" in src
    assert "testid: 'jaag-maps'" in src
    assert "testid: 'jaag-email'" in src
    # Photo action is gone — both the descriptor and the route.
    assert "testid: 'summary-action-photo'" not in src
    assert "summary-action-photo" not in src
    # Grid stays geometrically stable — 3 columns now, not 4.
    assert "grid grid-cols-3 gap-2\" data-testid=\"summary-action-row\"" in src


def test_photo_action_jumps_to_equipment_tab():
    """Photo action has been removed in iter 220ea·7."""
    src = _read()
    assert "onJumpToTab('equipment')" not in src


def test_action_row_disabled_state_when_no_target():
    """If we don't have a phone / email / address we still render
    the slot but mark it disabled — keeps the 4-up grid stable."""
    src = _read()
    assert 'aria-disabled="true"' in src
    assert "opacity-40 cursor-not-allowed" in src


# ── 3 · Stats grid ───────────────────────────────────────────────


def test_stats_grid_component_exists():
    src = _read()
    assert "function SummaryStatsGrid(" in src
    assert 'data-testid="summary-stats-grid"' in src


def test_stats_grid_has_six_canonical_stats():
    """Time · Photos · Parts · Machines · Safety · Mileage."""
    src = _read()
    for tid in (
        "summary-stat-time",
        "summary-stat-photos",
        "summary-stat-parts",
        "summary-stat-machines",
        "summary-stat-safety",
        "summary-stat-mileage",
    ):
        # IDs are set via descriptor `testid:` strings.
        assert f"testid: '{tid}'" in src, f"missing stat: {tid}"


def test_stats_grid_handles_running_on_site_timer():
    """The on-site stat must count BOTH closed entries' duration
    AND any currently-running entry's elapsed time. Otherwise the
    engineer sees stale 0s while they're literally on the clock."""
    src = _read()
    assert "activeOnSiteStart" in src
    assert "Date.now() - activeOnSiteStart" in src


def test_stats_grid_reads_parts_consumed_vs_total():
    """Parts stat shows `consumed/total` (e.g. 2/3) so the engineer
    can see at a glance how much of the BoM they've fitted."""
    src = _read()
    assert "partsConsumed" in src
    assert "partsTotal" in src
    assert "All fitted" in src


# ── 4 · Visual hierarchy ─────────────────────────────────────────


def test_summary_render_order():
    """Document order in the JobAtAGlance JSX: safety banner →
    status pill → action row → stats grid → customer/site/fault.
    Asserts on the call sites (not test-ids which live inside the
    component definitions further down the file)."""
    src = _read()
    safety   = src.index('data-testid="summary-safety-checklist-banner"')
    pill     = src.index('<SummaryStatusPill ')
    actions  = src.index('<SummaryActionRow')
    stats    = src.index('<SummaryStatsGrid')
    customer = src.index('data-testid="jaag-customer-name"')
    assert safety < pill < actions < stats < customer, (
        "Summary tab order regressed — expected "
        "safety → status-pill → action-row → stats-grid → customer"
    )


# ── 5 · JobAtAGlance plumbing ────────────────────────────────────


def test_jobataglance_receives_mileage_and_jump_callback():
    """The parent EngineerJobDetailV2 must wire `mileage` and
    `onJumpToTab` so the stats grid and Photo action work."""
    src = _read()
    assert "<JobAtAGlance" in src
    assert "mileage={mileage}" in src
    assert "onJumpToTab={setActiveTab}" in src
    assert "function JobAtAGlance({ job, mileage" in src
    assert "onJumpToTab" in src
