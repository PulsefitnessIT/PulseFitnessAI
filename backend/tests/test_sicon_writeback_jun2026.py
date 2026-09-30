"""Offline tests for Phase 2 Sicon write-back scaffolding:
- outbox worker safety-gate: real drains DO NOT send while SICON_ALLOW_WRITES is
  false; rows stay 'pending' (no dead_letter churn), reported via writes_disabled.
- write-back facade: report_case enqueues an idempotent intent; outbox_summary
  counts by status; nothing is sent.
"""
import uuid
import pytest

from tests.conftest import drive_async
from utils.database import db
import utils.sicon_outbox_worker as worker
import utils.sicon_writeback as wb


@pytest.fixture
def org():
    o = f"itest-wb-{uuid.uuid4().hex[:8]}"
    yield o
    drive_async(db.svc_sicon_outbox.delete_many({"organization_id": o}))


async def _seed_row(org, ref="C-1", status="pending"):
    await db.svc_sicon_outbox.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "kind": "case",
        "our_reference": ref, "endpoint": "/api/Service/Calls",
        "payload": {"OurReference": ref}, "status": status, "attempts": 0,
        "created_at": "2026-06-01T00:00:00+00:00"})


def test_worker_gate_leaves_rows_pending_when_writes_disabled(org, monkeypatch):
    monkeypatch.setattr(worker, "env_allow_writes", lambda: False)
    async def run():
        await _seed_row(org)
        res = await worker.tick(organization_id=org, simulate=False)
        row = await db.svc_sicon_outbox.find_one({"organization_id": org}, {"_id": 0})
        return res, row
    res, row = drive_async(run())
    assert res.writes_disabled is True
    assert res.skipped_writes_disabled == 1
    assert res.succeeded == 0 and res.failed == 0 and res.dead_letter == 0
    assert row["status"] == "pending"          # preserved, not churned to dead_letter
    assert row["attempts"] == 0                 # never attempted a send


def test_worker_simulate_still_runs_when_writes_disabled(org, monkeypatch):
    monkeypatch.setattr(worker, "env_allow_writes", lambda: False)
    async def run():
        await _seed_row(org, ref="C-SIM")
        res = await worker.tick(organization_id=org, simulate=True)
        row = await db.svc_sicon_outbox.find_one({"organization_id": org}, {"_id": 0})
        return res, row
    res, row = drive_async(run())
    assert res.writes_disabled is False         # demo mode is exempt from the gate
    assert row["status"] == "simulated_succeeded"


def test_facade_report_case_enqueues_idempotently(org, monkeypatch):
    monkeypatch.setattr(wb, "env_allow_writes", lambda: False)
    case = {"id": "case-xyz", "organization_id": org, "reference": "SVC-1",
            "title": "Belt fault", "status": "open", "priority": "high"}
    async def run():
        await wb.report_case(case)
        await wb.report_case(case)  # replay must not duplicate
        rows = await db.svc_sicon_outbox.find({"organization_id": org}, {"_id": 0}).to_list(10)
        summary = await wb.outbox_summary(org)
        return rows, summary
    rows, summary = drive_async(run())
    assert len(rows) == 1                        # idempotent on (kind, OurReference)
    assert rows[0]["kind"] == "case" and rows[0]["status"] == "pending"
    assert summary["enabled"] is False           # writes still gated off
    assert summary["pending"] == 1 and summary["total"] == 1


def test_facade_writeback_enabled_reflects_flag(monkeypatch):
    monkeypatch.setattr(wb, "env_allow_writes", lambda: True)
    assert wb.writeback_enabled() is True
    monkeypatch.setattr(wb, "env_allow_writes", lambda: False)
    assert wb.writeback_enabled() is False
