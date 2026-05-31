"""Iter 220dv — Per-machine custom-field render auto-loads via job type.

The frontend ``MachineRowCustomFields`` component (iter 220) calls
``GET /api/svc/work-report-fields/for-machine-row/{row_id}`` to
resolve its field set. Iter 220du extended that resolver with a
``case_type`` filter via the row's parent case.

This iter pins the end-to-end flow: a PPM-tagged field auto-loads
on a PPM case's machine row, but NOT on a Repair case's row of
the same machine.

The frontend pin proves the wiring contract — `MachineRowCustomFields`
already uses the same `for-machine-row` endpoint that is now
case_type-aware, so the per-machine auto-load is live without any
frontend change.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user():
    return {"id": "eng-1", "organization_id": "org-1",
            "full_name": "Eng One", "email": "e@x.test"}


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _machine_row(case_id="c-1", asset_id="asset-1", equipment_type="Treadmill"):
    return {
        "id": "row-1",
        "organization_id": "org-1",
        "case_id": case_id,
        "asset_id": asset_id,
        "asset_name": "Treadmill #14",
        "asset_type": equipment_type,
        "custom_fields": {"existing_key": "value"},
    }


# Three defs in the org:
#   universal_field       → job_types=[] (matches every case_type)
#   ppm_only_field        → job_types=["ppm"]
#   repair_only_field     → job_types=["repair"]
DEFS = [
    {"id": "f-univ", "key": "universal_key", "name": "Universal",
     "field_type": "text", "scope_kind": "global", "scope_value": None,
     "job_types": [], "position": 0, "created_at": "2025-01-01"},
    {"id": "f-ppm", "key": "ppm_key", "name": "PPM lube check",
     "field_type": "checkbox", "scope_kind": "global", "scope_value": None,
     "job_types": ["ppm"], "position": 1, "created_at": "2025-01-02"},
    {"id": "f-rep", "key": "repair_key", "name": "Repair belt mileage",
     "field_type": "number", "scope_kind": "global", "scope_value": None,
     "job_types": ["repair"], "position": 2, "created_at": "2025-01-03"},
]


def _run_resolver(case_type: str, *, parent_present: bool = True):
    """Helper — call ``fields_for_machine_row`` with a stub DB that
    returns DEFS filtered by Mongo to whatever the query would return."""
    from routes.svc.work_report_fields import fields_for_machine_row

    fdb = MagicMock()
    fdb.svc_work_visit_machines.find_one = AsyncMock(
        return_value=_machine_row(),
    )
    fdb.equipment.find_one = AsyncMock(return_value={
        "id": "asset-1", "equipment_type": "Treadmill",
        "manufacturer": "Life Fitness", "model": "Integrity",
    })
    parent_doc = None if not parent_present else {"case_type": case_type}
    fdb.svc_cases.find_one = AsyncMock(return_value=parent_doc)

    captured_queries: list[dict] = []

    def _defs_find(query, *args, **kwargs):
        captured_queries.append(query)
        # Emulate Mongo $and/$or behaviour on the DEFS list.
        and_clauses = query.get("$and") or []
        wanted_job_types = None
        for ac in and_clauses:
            for or_clause in (ac.get("$or") or []):
                if "job_types" in or_clause and or_clause["job_types"] not in (
                    {"$exists": False}, {"$size": 0},
                ):
                    wanted_job_types = or_clause["job_types"]
        # Filter
        out = []
        for d in DEFS:
            jt = d.get("job_types") or []
            # Apply the "job_types" filter the way Mongo would:
            if jt and (wanted_job_types is not None) and wanted_job_types not in jt:
                continue
            out.append(d)
        return _chain(out)

    fdb.svc_work_report_field_defs.find = MagicMock(side_effect=_defs_find)

    async def go():
        with patch("routes.svc.work_report_fields.db", fdb):
            return await fields_for_machine_row(row_id="row-1", user=_user())

    return _run(go()), captured_queries


def test_machine_row_ppm_case_returns_universal_plus_ppm_only():
    out, _q = _run_resolver("ppm")
    keys = {f["key"] for f in out["fields"]}
    assert "universal_key" in keys
    assert "ppm_key" in keys
    # The repair-only field MUST NOT bleed onto the PPM row.
    assert "repair_key" not in keys


def test_machine_row_repair_case_returns_universal_plus_repair_only():
    out, _q = _run_resolver("repair")
    keys = {f["key"] for f in out["fields"]}
    assert "universal_key" in keys
    assert "repair_key" in keys
    assert "ppm_key" not in keys


def test_machine_row_install_case_only_universal():
    """Install case has no install-tagged field defs — engineer
    sees only the universal field, NOT either tagged one."""
    out, _q = _run_resolver("install")
    keys = {f["key"] for f in out["fields"]}
    assert keys == {"universal_key"}


def test_machine_row_legacy_parent_case_defaults_to_repair():
    """When the parent case is missing entirely (corrupt/legacy data),
    the resolver falls back to "repair" — the iter-220dt default for
    pre-220dt cases — so the engineer still sees a sensible field set."""
    out, queries = _run_resolver("ignored", parent_present=False)
    # The Mongo query's job_types filter must include "repair" as
    # the case-type match (proves the fallback runs).
    and_clauses = queries[0]["$and"][0]["$or"]
    flat = [c.get("job_types") for c in and_clauses]
    assert "repair" in flat
    # And the resulting field set excludes ppm_key.
    keys = {f["key"] for f in out["fields"]}
    assert "ppm_key" not in keys


def test_machine_row_carries_saved_values_for_prefill():
    """``values`` payload echoes the row's persisted ``custom_fields``
    so the React component can pre-fill inputs without a second hop."""
    out, _q = _run_resolver("ppm")
    assert out["values"] == {"existing_key": "value"}


# ── Frontend contract pin: the React component already uses the
#    case_type-aware endpoint, so no FE change was needed. Pin it
#    so a future refactor doesn't accidentally regress. ────────────


def test_machine_row_custom_fields_uses_for_machine_row_endpoint():
    src = (Path("/app/frontend/src")
           / "pages/ServiceOps/Engineer/MachineRowCustomFields.js"
           ).read_text(encoding="utf-8")
    # Endpoint pinned + still scoped per-row.
    assert "/svc/work-report-fields/for-machine-row/${row.id}" in src
    # Per-row PATCH path stays so the saved value lands on the row's
    # custom_fields map, NOT the case-level dict.
    assert "custom_fields: next" in src
