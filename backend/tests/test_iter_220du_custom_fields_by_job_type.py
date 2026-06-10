"""Iter 220du — Custom Fields × Job Type admin (Account Settings link).

Extends the existing ``svc_work_report_field_defs`` collection
(iter 220) with a parallel **job_types** filter dimension. Admins
can now scope a custom field by:

  * existing scope_kind (global / equipment_type / manufacturer /
    model / asset), AND
  * NEW job_types list (repair / ppm / install / inspection /
    callout / audit) — empty list = matches every job type
    (backwards compatible).

Resolvers (`for-case`, `for-machine-row`) honour the filter so the
engineer auto-loads ONLY the fields relevant to the case's
``case_type``.

Frontend:
  * ``EngineerWorkReportFields.js`` editor gains a chip group for
    job-type toggling; the list view surfaces selected types.
  * ``AccountPanel.js`` exposes a "Manage custom fields" link so
    operators discover the admin without hunting through the
    engineer module.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="u1", org="org-1"):
    return {"id": uid, "organization_id": org, "full_name": "Admin",
            "email": "a@x.test"}


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


# ── 1 · Backend accepts job_types + validates the whitelist ───────


def test_create_field_persists_job_types():
    from routes.svc.work_report_fields import (
        create_work_report_field, WorkReportFieldIn,
    )

    fdb = MagicMock()
    fdb.svc_work_report_field_defs.count_documents = AsyncMock(return_value=0)
    fdb.svc_work_report_field_defs.find_one = AsyncMock(return_value=None)
    fdb.svc_work_report_field_defs.insert_one = AsyncMock()

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await create_work_report_field(
                payload=WorkReportFieldIn(
                    name="PPM checklist - lubrication",
                    field_type="checkbox",
                    scope_kind="equipment_type",
                    scope_value="Treadmill",
                    job_types=["ppm", "inspection"],
                ),
                user=_user(),
            )

    out = _run(go())
    assert out["job_types"] == ["ppm", "inspection"]
    # Doc shape persisted correctly.
    inserted = fdb.svc_work_report_field_defs.insert_one.await_args.args[0]
    assert inserted["job_types"] == ["ppm", "inspection"]


def test_create_field_keeps_custom_slugs_drops_malformed_job_types():
    """Iter 220ec — job_types are org-configurable case-type slugs, not a
    fixed enum. Any slug-formatted value is kept (custom case types can
    scope questions too); malformed values are silently dropped."""
    from routes.svc.work_report_fields import _clean_job_types

    assert _clean_job_types(["repair", "shenanigans"]) == ["repair", "shenanigans"]
    # Malformed values (spaces / punctuation / over-long) are dropped.
    assert _clean_job_types(["repair", "Not A Slug!", "x" * 41]) == ["repair"]
    # Case-insensitive + de-duplicated.
    assert _clean_job_types(["PPM", "ppm", "repair"]) == ["ppm", "repair"]


def test_create_field_with_empty_job_types_is_backwards_compatible():
    """Empty job_types list = "all jobs", matching iter-220 behaviour."""
    from routes.svc.work_report_fields import (
        create_work_report_field, WorkReportFieldIn,
    )

    fdb = MagicMock()
    fdb.svc_work_report_field_defs.count_documents = AsyncMock(return_value=0)
    fdb.svc_work_report_field_defs.find_one = AsyncMock(return_value=None)
    fdb.svc_work_report_field_defs.insert_one = AsyncMock()

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await create_work_report_field(
                payload=WorkReportFieldIn(
                    name="Global field",
                    field_type="text",
                    scope_kind="global",
                ),
                user=_user(),
            )

    out = _run(go())
    assert out["job_types"] == []


def test_patch_field_can_update_job_types():
    from routes.svc.work_report_fields import (
        update_work_report_field, WorkReportFieldPatch,
    )

    fdb = MagicMock()
    fdb.svc_work_report_field_defs.find_one = AsyncMock(side_effect=[
        # Initial lookup
        {"id": "f-1", "organization_id": "org-1",
         "name": "Belt slip count", "field_type": "number",
         "job_types": ["repair"]},
        # Refresh after PATCH
        {"id": "f-1", "organization_id": "org-1",
         "name": "Belt slip count", "field_type": "number",
         "job_types": ["ppm", "inspection"]},
    ])
    fdb.svc_work_report_field_defs.update_one = AsyncMock()

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await update_work_report_field(
                field_id="f-1",
                payload=WorkReportFieldPatch(
                    job_types=["ppm", "inspection"],
                ),
                user=_user(),
            )

    out = _run(go())
    assert out["job_types"] == ["ppm", "inspection"]


# ── 2 · Resolver honours the job_types filter ────────────────────


def test_fields_for_case_filters_by_case_type():
    from routes.svc.work_report_fields import fields_for_case

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1",
        "asset_id": "", "asset_name": "Treadmill",
        "case_type": "ppm",
    })
    # Only PPM-tagged + universal fields should be returned by Mongo.
    returned = [
        {"id": "f-univ", "name": "Universal",
         "scope_kind": "global", "scope_value": None,
         "job_types": [], "position": 0, "created_at": "2025-01-01",
         "key": "universal", "field_type": "text"},
        {"id": "f-ppm", "name": "PPM checklist",
         "scope_kind": "global", "scope_value": None,
         "job_types": ["ppm"], "position": 1, "created_at": "2025-01-02",
         "key": "ppm_checklist", "field_type": "checkbox"},
    ]
    fdb.svc_work_report_field_defs.find = MagicMock(return_value=_chain(returned))
    # Asset lookup returns nothing (asset_id empty)
    fdb.equipment.find_one = AsyncMock(return_value=None)
    # No history pre-fill required for this assertion.
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await fields_for_case(case_id="c-1", user=_user())

    out = _run(go())
    # Filter passed to Mongo must include the job_types $or clause.
    q = fdb.svc_work_report_field_defs.find.call_args[0][0]
    assert "$and" in q
    # Inner filter must match "no job_types stamped", "empty list",
    # OR the case's slug.
    and_clauses = q["$and"][0]["$or"]
    by_kind = {
        next(iter(c)): c for c in and_clauses
    }
    assert "job_types" in by_kind
    # The case_type slug we pass in must be one of the matchers.
    flattened = [c.get("job_types") for c in and_clauses]
    assert "ppm" in flattened


def test_fields_for_case_defaults_case_type_to_repair():
    """Legacy cases without a stamped `case_type` get treated as
    `repair` so they still resolve a sensible field set."""
    from routes.svc.work_report_fields import fields_for_case

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "c-legacy", "organization_id": "org-1",
        "asset_id": "", "asset_name": "Treadmill",
        # case_type field missing entirely (pre-220dt case)
    })
    fdb.svc_work_report_field_defs.find = MagicMock(return_value=_chain([]))
    fdb.equipment.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.find = MagicMock(return_value=_chain([]))

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await fields_for_case(case_id="c-legacy", user=_user())

    _run(go())
    q = fdb.svc_work_report_field_defs.find.call_args[0][0]
    flattened = [c.get("job_types") for c in q["$and"][0]["$or"]]
    assert "repair" in flattened


# ── 3 · Frontend admin page + AccountPanel link ──────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_admin_page_has_job_type_chips_editor():
    src = _read("pages/ServiceOps/Engineer/EngineerWorkReportFields.js")
    assert "JOB_TYPE_OPTIONS" in src
    assert 'data-testid="wrf-editor-job-types"' in src
    # Per-job-type chip testids are templated (backtick literal).
    assert 'data-testid={`wrf-editor-job-${j.id}`}' in src
    # All six slugs are present in the JOB_TYPE_OPTIONS array.
    for slug in ('repair', 'ppm', 'install', 'inspection', 'callout', 'audit'):
        assert f"id: '{slug}'" in src, f"missing job-type option {slug}"
    # Editor passes job_types in POST / PATCH bodies.
    assert "job_types: jobTypes" in src
    # List view surfaces selected job types.
    assert "row.job_types" in src


def test_account_panel_links_to_custom_fields_admin():
    src = _read("pages/AccountPanel.js")
    assert 'data-testid="account-link-custom-fields"' in src
    assert '/svc/engineer/work-report-fields' in src
    assert "Manage custom fields" in src
