"""Iter 216h241 — Staffing UX polish bugfix batch.

Validates the four behavioural changes the user surfaced from a
production review of the HR / Staffing console:

1. **DOB year input** — ``DatePicker`` now exports ``parseTypedDate``
   that round-trips typed DD/MM/YYYY input to ISO, and the new hybrid
   input mode is documented in the file header.
2. **Hours/week ↔ Hourly rate mirror** — backend POST / PATCH on
   ``staff_members`` keep ``hours_per_week`` and ``weekly_hours`` in
   lock-step so the staff list and HR profile never disagree.
3. **Multi-site allocation** — ``StaffUpdate`` accepts ``site_ids``
   (existing field, just confirmed) so the new HR panel can persist
   the array via the dedicated PATCH route.
4. **Phase Sx subheadings removed** — verified by grepping the
   staffing tab files: any remaining occurrences must carry the
   ``data-testid="*-subheading-removed-iter216h241"`` marker (hidden
   placeholder kept so the parent flex wrappers stay valid).
"""
from __future__ import annotations

import inspect
import pathlib


def test_staff_models_accept_hours_per_week():
    """Both StaffCreate and StaffUpdate must accept hours_per_week now."""
    from routes.staffing import StaffCreate, StaffUpdate
    assert "hours_per_week" in StaffCreate.model_fields
    assert "weekly_hours" in StaffCreate.model_fields  # legacy kept
    assert "hours_per_week" in StaffUpdate.model_fields
    assert "weekly_hours" in StaffUpdate.model_fields


def test_create_staff_mirrors_hours_keys():
    """The create_staff source must populate both keys when one is supplied."""
    from routes import staffing
    src = inspect.getsource(staffing.create_staff)
    assert 'doc["hours_per_week"] = h' in src
    assert 'doc["weekly_hours"] = h' in src


def test_update_staff_mirrors_hours_keys():
    """PATCH must mirror hours_per_week ↔ weekly_hours either direction."""
    from routes import staffing
    src = inspect.getsource(staffing.update_staff)
    assert '"hours_per_week" in patch' in src
    assert '"weekly_hours" in patch' in src


def test_hr_profile_patch_mirrors_to_weekly_hours():
    """HR PATCH writes hours_per_week → must also set weekly_hours."""
    from routes import staffing_hr
    src = inspect.getsource(staffing_hr.update_profile)
    assert '"hours_per_week" in patch' in src
    assert '"weekly_hours" = patch["hours_per_week"]' in src or 'patch["weekly_hours"] = patch["hours_per_week"]' in src


def test_staff_update_accepts_site_ids():
    """site_ids must remain on StaffUpdate (HR multi-site panel uses this)."""
    from routes.staffing import StaffUpdate
    assert "site_ids" in StaffUpdate.model_fields


def test_phase_subheadings_removed_from_staffing_tabs():
    """All 5 'Phase Sx · …' visible subheadings must be gone. The
    earlier (h241) hidden-placeholder approach left a lone icon next
    to the empty `<p>` — iter h242 removed the whole wrapper. So the
    test now just asserts no visible `>Phase S` strings remain."""
    base = pathlib.Path("/app/frontend/src/pages/LiteDashboard/staffing")
    targets = ["HRTab.js", "CommsTab.js", "OperationsTab.js", "AIWorkforceTab.js", "TimeClockTab.js"]
    for fname in targets:
        text = (base / fname).read_text(encoding="utf-8")
        # Strict check: no `>Phase S\d · ` substring anywhere in JSX.
        assert ">Phase S" not in text, f"{fname}: visible 'Phase S' subheading still present"


def test_enterprise_crm_subheadings_removed():
    """Iter 216h242 — the 'Enterprise CRM' eyebrow above Territory &
    coverage / Forecast & quotas / Reports & analytics was removed."""
    for path in (
        "/app/frontend/src/pages/CRM/CRMForecast.js",
        "/app/frontend/src/pages/CRM/CRMReports.js",
        "/app/frontend/src/pages/CRM/CRMTerritories.js",
    ):
        text = pathlib.Path(path).read_text(encoding="utf-8")
        assert ">Enterprise CRM<" not in text, f"{path}: 'Enterprise CRM' eyebrow still present"


def test_datepicker_exports_parse_typed_date():
    """DatePicker must export parseTypedDate (used for typed DD/MM/YYYY)."""
    src = pathlib.Path("/app/frontend/src/components/shared/DatePicker.jsx").read_text()
    assert "parseTypedDate" in src
    assert "export { formatDDMMYYYY, dateToIso, isoToDate, parseTypedDate }" in src


def test_staffing_console_has_hrs_per_week_column():
    """The Staff list must surface contracted hrs AND hourly rate as
    separate columns to remove the column-label ambiguity."""
    src = pathlib.Path("/app/frontend/src/pages/LiteDashboard/StaffingConsole.js").read_text()
    assert "Hrs/wk" in src
    assert "Hourly rate" in src
    assert "Hourly cost £" not in src  # old placeholder gone
    assert 'data-testid={`staff-row-${s.id}-hourly`}' in src
    assert 'data-testid={`staff-row-${s.id}-hrs`}' in src


def test_staffing_console_modal_uses_portal():
    """Iter 216h242 — modal must portal to document.body so the fixed
    inset-0 backdrop covers the whole viewport (parent transforms
    were creating a new containing block and leaving 1/3 of the
    screen un-dimmed). Also asserts explicit labels are present."""
    src = pathlib.Path("/app/frontend/src/pages/LiteDashboard/StaffingConsole.js").read_text()
    assert "createPortal" in src
    assert "document.body" in src
    # Explicit labels above the two number inputs.
    assert ">Hourly rate (£/hr)<" in src
    assert ">Contracted hours / week<" in src
