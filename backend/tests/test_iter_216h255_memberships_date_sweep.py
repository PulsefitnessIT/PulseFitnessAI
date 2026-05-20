"""Iter 216h255 — Memberships module-wide date-field consistency sweep.

Replaces every remaining native `<input type="date">` in the
Memberships module with the shared DD/MM/YYYY DatePicker so operators
have one consistent date paradigm across every modal and drawer.

Surfaces swept:
- PromotionsTab — promo expiry date.
- StudioBuilderTab — academic term starts / ends.
- FamilyTab — sub-profile DOB (member portal).
- PlanEditorModal — first session date + excluded dates (via new
  `ExcludedDateAdder` helper that replaces the brittle
  `document.getElementById` trick).
- InstructorRosterView — payroll date range + DOB + DBS issued/expires
  + safeguarding completed/expires + first aid completed/expires
  (8 native inputs swapped).
- EventsTab — CreateEventModal + RehearsalModal date fields.
"""
from __future__ import annotations

import pathlib


_MEMBERSHIPS_ROOT = pathlib.Path("/app/frontend/src/pages/Memberships")

_SWEPT_FILES = [
    "PromotionsTab.js",
    "StudioBuilderTab.js",
    "FamilyTab.js",
    "InstructorRosterView.js",
    "EventsTab.js",
    "modals/PlanEditorModal.js",
]


def test_no_native_date_inputs_in_memberships():
    """Every swept file imports DatePicker and contains no native
    `type="date"` JSX attribute. The AddMemberModal docstring mentions
    the migration but no active input — verified separately below."""
    for name in _SWEPT_FILES:
        src = (_MEMBERSHIPS_ROOT / name).read_text()
        # No active native date inputs.
        assert 'type="date"' not in src, (
            f"{name} still contains a native <input type=\"date\">"
        )
        # Shared DatePicker imported (or component is used as a child).
        assert "DatePicker" in src, f"{name} must use the shared DatePicker"


def test_add_member_modal_docstring_only_reference_preserved():
    """AddMemberModal already uses DatePicker — the only `type="date"`
    occurrence is the docstring comment from Iter 216h200. Make sure
    that didn't accidentally turn back into an actual input."""
    src = (_MEMBERSHIPS_ROOT / "modals/AddMemberModal.js").read_text()
    # The docstring mention is allowed (in JSDoc, prefixed by *).
    docstring_hits = [
        line for line in src.splitlines()
        if 'type="date"' in line and line.lstrip().startswith("*")
    ]
    active_hits = [
        line for line in src.splitlines()
        if 'type="date"' in line and not line.lstrip().startswith("*")
    ]
    assert not active_hits, f"AddMemberModal has an active type=date: {active_hits}"
    assert docstring_hits, "Expected the docstring reference to still be present"


def test_plan_editor_uses_excluded_date_adder():
    """The PlanEditorModal excluded-dates flow no longer relies on
    `document.getElementById`. It uses a clean React component instead."""
    src = (_MEMBERSHIPS_ROOT / "modals/PlanEditorModal.js").read_text()
    assert "function ExcludedDateAdder" in src
    assert 'getElementById("mbr-excluded-date-picker")' not in src
    assert 'data-testid="mbr-plan-course-excluded-add"' in src


def test_instructor_roster_payroll_dates_use_datepicker():
    src = (_MEMBERSHIPS_ROOT / "InstructorRosterView.js").read_text()
    # Both range pickers + the 6 HR date fields now flow through DatePicker.
    for tid in (
        "mbr-payroll-from", "mbr-payroll-to",
        "mbr-instructor-dob",
        "mbr-instructor-dbs-issued", "mbr-instructor-dbs-expires",
        "mbr-instructor-sg-completed", "mbr-instructor-sg-expires",
        "mbr-instructor-fa-completed", "mbr-instructor-fa-expires",
    ):
        assert f'testid="{tid}"' in src, f"missing DatePicker testid={tid}"


def test_promotions_tab_uses_datepicker_with_min_today():
    """Promo expiry must clamp to today as the minimum so an operator
    can't accidentally back-date a promotion."""
    src = (_MEMBERSHIPS_ROOT / "PromotionsTab.js").read_text()
    assert "minDate={new Date().toISOString().slice(0, 10)}" in src
    assert 'testid="mbr-promo-valid-until"' in src
