"""Iter 220ea·7 — Summary tab follow-up cleanups.

Source-level guards covering four small fixes on the Engineer App
Summary tab + Time tab in `EngineerJobDetailV2.js`:

1. The cover banner (`jaag-cover-banner`) has been moved to the
   TOP of the Summary card — right under the tabs / safety
   banner. Engineer reads "Chargeable visit · confirm spend"
   before they look at anything else when there's no cover.
2. The Photo action has been removed from the Summary action
   row. The Equipment tab owns per-machine capture; a second
   entry-point was clutter on a 412 px phone.
3. The `EngineerEntitlementPanel` ("No contract on file ·
   Send feedback to coordinator") has been removed from Summary.
4. The duplicate H&S "checklist required" warning on the Time
   tab is gone. The Summary tab's amber banner is now the
   single source of truth for the pre-job signoff requirement.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"


def _read() -> str:
    return JOB_DETAIL.read_text()


# ── 1 · Cover banner moved to top ────────────────────────────────


def test_cover_banner_renders_at_top_of_summary_card():
    """Visual hierarchy: safety banner → cover banner → status
    pill row → action row → stats grid → customer block."""
    src = _read()
    safety   = src.index('data-testid="summary-safety-checklist-banner"')
    cover    = src.index('data-testid="jaag-cover-banner"')
    pill     = src.index('<SummaryStatusPill ')
    actions  = src.index('<SummaryActionRow')
    stats    = src.index('<SummaryStatsGrid')
    customer = src.index('data-testid="jaag-customer-name"')
    assert safety < cover < pill < actions < stats < customer, (
        "Summary tab order regressed — expected "
        "safety → cover → status-pill → action-row → stats-grid → customer"
    )


def test_cover_banner_renders_only_once_on_summary():
    """Iter 220ea·7 moved the cover banner up; the old slot below
    the chip row was deleted. Exactly ONE `jaag-cover-banner` div
    must remain in the source."""
    src = _read()
    # Each render has one data-testid="jaag-cover-banner" — count occurrences
    assert src.count('data-testid="jaag-cover-banner"') == 1


# ── 2 · Photo action removed ─────────────────────────────────────


def test_photo_action_removed_from_summary():
    src = _read()
    assert "summary-action-photo" not in src
    # And the icon import is no longer needed in this file.
    assert "Camera," not in src.split("import {")[1].split("}")[0]


def test_action_row_is_three_columns():
    src = _read()
    # The action grid changed from 4-up to 3-up.
    assert "grid grid-cols-3 gap-2\" data-testid=\"summary-action-row\"" in src
    # And the descriptor list for the three remaining actions is
    # exactly Call / Navigate / Email.
    assert "key: 'call'" in src
    assert "key: 'navigate'" in src
    assert "key: 'email'" in src
    assert "key: 'photo'" not in src


# ── 3 · EngineerEntitlementPanel removed ─────────────────────────


def test_entitlement_panel_removed_from_summary():
    """The `<EngineerEntitlementPanel ... />` JSX must be gone —
    only a deletion-marker comment remains documenting the
    decision."""
    src = _read()
    assert "<EngineerEntitlementPanel" not in src
    # Import is no longer needed in this file.
    assert "import EngineerEntitlementPanel" not in src


# ── 4 · Time tab H&S warning removed ─────────────────────────────


def test_time_tab_safety_warning_removed():
    """The `time-safety-warning` block has been deleted from
    `TimeTab` — Summary is now the canonical surface for the
    pre-job H&S signoff requirement."""
    src = _read()
    assert 'data-testid="time-safety-warning"' not in src
    assert "Pre-job H&amp;S checklist required" not in src
    # The supporting state variable is also gone.
    assert "blockedBySafety" not in src
