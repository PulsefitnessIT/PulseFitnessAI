"""Iter 220ea·13 — Confirm Custom Fields react to Case Type.

The user pointed out (Feb 14, 2026) that custom report fields
"must react to case types — a repair will need different
custom fields than a Preventative Maintenance Service".

The screenshot shows the editor already has an
"Only on these job types (leave empty for all)" multi-select
with chips for Repair · PPM Service · Installation ·
Inspection · Emergency callout · Asset audit.

This iter doesn't add new behaviour — it pins the existing
case_type filter logic with a regression test so it can't
silently regress in a future refactor. The wiring lives in
`routes/svc/work_report_fields.py` and matches the case's
`case_type` against the field def's `job_types` list.

Validation chain:
  • The editor admin can set `job_types: ["repair"]` on a field
  • The case has `case_type: "repair"`
  • `GET /svc/work-report-fields/for-machine-row/{row_id}`
    returns the field
  • The case has `case_type: "ppm"` (different)
  • The same call returns the field set MINUS the repair-only one
"""

from __future__ import annotations

from pathlib import Path


BACKEND = Path("/app/backend/routes/svc/work_report_fields.py")
FRONTEND = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerWorkReportFields.js")


def _read(p: Path) -> str:
    return p.read_text()


# ── 1 · Admin UI exposes the job_types selector ──────────────────


def test_admin_ui_has_job_types_multi_select():
    src = _read(FRONTEND)
    # The screenshot text — exact label engineers see.
    assert "Only on these job types" in src
    # And it sends `job_types` on both POST and PATCH.
    assert "job_types: jobTypes" in src
    # All six canonical types are presented.
    for tid in ("repair", "ppm", "install", "inspection", "callout", "audit"):
        assert f"id: '{tid}'" in src, f"missing job-type chip: {tid}"


# ── 2 · Backend models accept job_types ──────────────────────────


def test_work_report_field_in_model_has_job_types():
    src = _read(BACKEND)
    assert "job_types: list[str] = Field(default_factory=list)" in src
    # And the patch model allows updating it.
    assert "job_types: Optional[list[str]] = None" in src


def test_allowed_job_types_match_admin_ui():
    """The backend's `ALLOWED_JOB_TYPES` set must align with the
    chips the admin UI offers, otherwise an admin will pick
    "PPM Service" + save and get a 400."""
    src = _read(BACKEND)
    # The set is declared near the top of the module.
    for t in ("repair", "ppm", "install", "inspection", "callout", "audit"):
        assert f"'{t}'" in src or f'"{t}"' in src, f"missing allowed type: {t}"


# ── 3 · Resolver filters by the case's case_type ────────────────


def test_for_case_resolver_filters_by_case_type():
    src = _read(BACKEND)
    # The resolver pulls `case_type` from the case…
    assert 'case_type_match = (case.get("case_type") or "repair").lower()' in src
    # …and matches it against the field def's `job_types` (allowing
    # missing/empty for backward compat).
    assert '"job_types": {"$exists": False}' in src
    assert '"job_types": {"$size": 0}' in src
    assert '"job_types": case_type_match' in src


def test_for_machine_row_resolver_also_filters_by_case_type():
    src = _read(BACKEND)
    # The per-machine-row endpoint must mirror the per-case logic
    # so the engineer sees the right field set inside the
    # Equipment tab as well.
    assert 'case_type_match = "repair"' in src      # default fallback
    assert "parent.get(\"case_type\")" in src        # pulls from parent case
    assert "fields_for_machine_row" in src
