"""Iter 216h208 — new fault inherits site_id from equipment.

Previously /api/issues POST stamped only organization_id on the new
issue document, leaving site_id absent. Any dashboard filtering by
site_id (LiteDashboardPage, useDashboardData when an active site is
selected) then dropped the just-logged fault from the list.

Fix: at intake we already do an equipment lookup for the coverage
resolver — extend it to surface site_id and stamp it on the issue.

Run: pytest backend/tests/test_iter_216h208_issue_site_inherit.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from models.schemas import IssueCreate


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_db_with_equipment(equip_doc: dict | None):
    fake = MagicMock()
    fake.equipment = MagicMock()
    fake.equipment.find_one = AsyncMock(return_value=equip_doc)
    fake.issues = MagicMock()
    fake.issues.insert_one = AsyncMock()
    fake.issues.find_one = AsyncMock(return_value=None)
    fake.fix_history = MagicMock()
    fake.fix_history.insert_one = AsyncMock()
    fake.svc_cases = MagicMock()
    fake.svc_cases.find_one = AsyncMock(return_value=None)
    return fake


def test_resolve_coverage_includes_site_id():
    """The shared coverage helper now exposes equipment_site_id so the
    POST handler can stamp it on the issue."""
    from routes import issues

    equip = {"id": "eq-1", "site_id": "site-A",
             "organization_id": "org-1",
             "serial_number": "TM-001",
             "name": "Treadmill 1"}
    fake = _fake_db_with_equipment(equip)
    with patch.object(issues, "db", fake), \
         patch("utils.coverage.resolve_equipment_coverage",
               new=AsyncMock(return_value={"status": "uncovered"})):
        meta = _run(issues._resolve_coverage_for_issue("TM-001", "org-1"))

    assert meta.get("equipment_id") == "eq-1"
    assert meta.get("equipment_site_id") == "site-A"


def test_resolve_coverage_handles_no_equipment_site_id():
    """When equipment has no site_id, meta.equipment_site_id is None."""
    from routes import issues

    equip = {"id": "eq-1", "organization_id": "org-1",
             "serial_number": "TM-001"}
    fake = _fake_db_with_equipment(equip)
    with patch.object(issues, "db", fake), \
         patch("utils.coverage.resolve_equipment_coverage",
               new=AsyncMock(return_value={"status": "uncovered"})):
        meta = _run(issues._resolve_coverage_for_issue("TM-001", "org-1"))

    assert meta.get("equipment_site_id") is None


def test_create_issue_stamps_site_id_from_equipment():
    """POST /api/issues stamps issue.site_id = equipment.site_id when
    the equipment row carries one."""
    from routes import issues as ri

    equip = {"id": "eq-1", "site_id": "site-A",
             "organization_id": "org-1",
             "serial_number": "TM-001",
             "name": "Treadmill 1"}
    fake = _fake_db_with_equipment(equip)
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Test"}
    body = IssueCreate(
        serial_number="TM-001",
        machine_type="Treadmill",
        issue_description="not turning on",
        severity="operational_minor",
    )

    with patch.object(ri, "db", fake), \
         patch.object(ri, "store_fix_history", new=AsyncMock()), \
         patch.object(ri, "handle_engineer_escalation", new=AsyncMock()), \
         patch.object(ri, "_publish_issue_event", new=AsyncMock()), \
         patch.object(ri, "_mirror_issue_to_svc_case", new=AsyncMock()), \
         patch("utils.coverage.resolve_equipment_coverage",
               new=AsyncMock(return_value={"status": "uncovered"})):
        result = _run(ri.create_issue(issue=body, user=user))

    assert result["site_id"] == "site-A"
    assert result["organization_id"] == "org-1"
    # Insert was called with the same doc shape.
    args, _ = fake.issues.insert_one.call_args
    assert args[0]["site_id"] == "site-A"


def test_create_issue_omits_site_id_when_equipment_has_none():
    """If the matched equipment has no site_id, the issue stays
    site-less (no spurious empty-string)."""
    from routes import issues as ri

    equip = {"id": "eq-1", "organization_id": "org-1",
             "serial_number": "TM-001"}
    fake = _fake_db_with_equipment(equip)
    user = {"id": "u1", "organization_id": "org-1", "full_name": "Test"}
    body = IssueCreate(
        serial_number="TM-001",
        machine_type="Treadmill",
        issue_description="x",
        severity="operational_minor",
    )

    with patch.object(ri, "db", fake), \
         patch.object(ri, "store_fix_history", new=AsyncMock()), \
         patch.object(ri, "handle_engineer_escalation", new=AsyncMock()), \
         patch.object(ri, "_publish_issue_event", new=AsyncMock()), \
         patch.object(ri, "_mirror_issue_to_svc_case", new=AsyncMock()), \
         patch("utils.coverage.resolve_equipment_coverage",
               new=AsyncMock(return_value={"status": "uncovered"})):
        result = _run(ri.create_issue(issue=body, user=user))

    assert "site_id" not in result or result["site_id"] is None
