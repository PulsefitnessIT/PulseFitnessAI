"""Iter 220ea·27 — Parts/stock → Sicon mapping + field-correctness fixes.

The Service WebAPI exposes no parts/stock object on a case, so parts used
on a job are booked through the CoreWebAPI stock surface (InternalIssue /
TransferStock / AddStock / WriteOffStock). These tests cover:

  • the three pure stock mappers (exact Sicon field names + types),
  • the two field-correctness fixes (`FaultCode` first-class field, and the
    tracking-note `VisibleToEngineers` plural key),
  • the sync hooks' dry-run gating — no-op unless the org has both
    `enabled` and `auto_sync_stock` true,
  • the warehouse resolver (van mapping → Sage warehouse name),
  • the retry dispatcher knows the four new stock operations.
"""
import uuid

from tests.shared_loop import run_async
from utils.database import db
from utils.sicon_client import (
    build_internal_issue_payload,
    build_stock_adjustment_payload,
    build_stock_transfer_payload,
    build_tracking_note_payload,
    map_gymaxis_to_sicon_case,
)
from utils.sicon_sync import (
    _warehouse_for,
    on_part_consumed,
    on_stock_adjusted,
    on_stock_transferred,
)


# ───────────────────────── Pure mappers ──────────────────────────

def test_internal_issue_payload_fields_and_types():
    p = build_internal_issue_payload(
        "belt-01", 2, "VAN-07", reference="C123", second_ref="issue-9",
        cover_category="wear_tear", narrative="Drive belt")
    # exact Sicon CoreWebAPI StockItem/InternalIssue field names
    assert p["ItemCode"] == "BELT-01"  # uppercased
    assert p["WarehouseName"] == "VAN-07"
    assert p["Quantity"] == 2.0 and isinstance(p["Quantity"], float)
    assert p["Reference"] == "C123"
    assert p["SecondRef"] == "issue-9"
    assert p["AnalysisCode1"] == "wear_tear"
    assert p["DefaultNarrative"] == "Drive belt"
    assert "IssueDate" in p


def test_stock_transfer_payload_fields():
    p = build_stock_transfer_payload("belt-01", 5, "MAIN", "VAN-07",
                                     reference="T9", second_reference="Drive belt")
    assert p["ItemCode"] == "BELT-01"
    assert p["FromWarehouse"] == "MAIN"
    assert p["ToWarehouse"] == "VAN-07"
    assert p["Quantity"] == 5.0
    assert p["Reference"] == "T9"
    assert p["SecondReference"] == "Drive belt"


def test_stock_adjustment_positive_is_add_negative_is_writeoff():
    op_add, add = build_stock_adjustment_payload("belt-01", 4, "MAIN")
    assert op_add == "stock_add"
    assert add["Quantity"] == 4.0
    assert add["MovementDate"] and "SecondRef" in add  # AddStock schema

    op_wo, wo = build_stock_adjustment_payload("belt-01", -3, "MAIN")
    assert op_wo == "stock_writeoff"
    assert wo["Quantity"] == 3.0  # absolute value
    assert wo["WriteOffCategory"] == "Stock take"
    assert "SecondReference" in wo  # WriteOffStock uses the long key


# ─────────────── Field-correctness fixes (audit) ──────────────────

def test_case_maps_fault_code_to_first_class_field():
    """`FaultCode` is a real field on Sicon CreateCaseRequest — not just
    AnalysisField9."""
    case = map_gymaxis_to_sicon_case(
        {"fault_code": "E07", "issue_description": "Belt slipping"}, {})
    assert case["FaultCode"] == "E07"
    # still also carried in the analytics slot for reporting
    assert case["AnalysisField9"] == "E07"


def test_tracking_note_sends_both_visibility_keys():
    """UpdateTrackingNoteRequest uses the plural `VisibleToEngineers`; the
    create schema is published empty — we send both to be safe."""
    p = build_tracking_note_payload("hello", visible_to_engineer=True)
    assert p["VisibleToEngineer"] is True
    assert p["VisibleToEngineers"] is True


# ───────────────────── Warehouse resolver ─────────────────────────

def test_warehouse_resolver_van_mapping_and_default():
    cfg = {"default_warehouse_name": "MAIN",
           "van_warehouse_mapping": {"eng1": "VAN-1"}}
    assert _warehouse_for(cfg, "van", "eng1") == "VAN-1"
    assert _warehouse_for(cfg, "van", "unknown") == "MAIN"  # fallback
    assert _warehouse_for(cfg, "warehouse", "") == "MAIN"
    assert _warehouse_for({}, "warehouse", "") == "Warehouse"  # hard default


# ─────────────────── Dry-run gating of hooks ──────────────────────

def test_hooks_are_noop_without_sicon_config():
    """No Sicon config for the org → every stock hook returns False and
    enqueues nothing (the production default — Sicon is dry-run)."""
    org = "i27_" + uuid.uuid4().hex[:8]

    async def scenario():
        await db.sicon_config.delete_many({"organization_id": org})
        r1 = await on_part_consumed(org, {
            "part_sku": "BELT-01", "qty": 1, "engineer_id": "e1",
            "case_id": "c1", "case_reference": "C1"})
        r2 = await on_stock_transferred(org, {
            "part_sku": "BELT-01", "qty": 1, "transfer_id": "t1",
            "from": {"type": "warehouse"}, "to": {"type": "van", "engineer_id": "e1"}})
        r3 = await on_stock_adjusted(org, {
            "part_sku": "BELT-01", "qty_delta": -1, "location": "warehouse"})
        queued = await db.sicon_sync_queue.count_documents({"organization_id": org})
        return r1, r2, r3, queued

    r1, r2, r3, queued = run_async(scenario())
    assert r1 is False and r2 is False and r3 is False
    assert queued == 0


def test_hooks_noop_when_enabled_but_stock_sync_off():
    """`enabled` but `auto_sync_stock` not set → still a no-op (stock sync
    is opt-in on top of case sync)."""
    org = "i27_" + uuid.uuid4().hex[:8]

    async def scenario():
        await db.sicon_config.insert_one({
            "organization_id": org, "enabled": True, "auto_sync_stock": False,
            "base_url": "https://sicon.example", "company_id": 1})
        r = await on_part_consumed(org, {
            "part_sku": "BELT-01", "qty": 1, "engineer_id": "e1", "case_id": "c1"})
        await db.sicon_config.delete_many({"organization_id": org})
        return r

    assert run_async(scenario()) is False


# ─────────────── Retry dispatcher knows the new ops ───────────────

def test_retry_dispatcher_registers_stock_operations():
    import inspect

    from utils import sicon_sync
    src = inspect.getsource(sicon_sync._retry_item)
    for op in ("stock_internal_issue", "stock_transfer", "stock_add", "stock_writeoff"):
        assert op in src, f"retry handler missing for {op}"


# ─────────────── Endpoints carry the sync hooks ───────────────────

def test_consume_and_transfer_endpoints_wire_sync_hooks():
    import inspect

    from routes.svc import admin_stock, engineer_phase3
    consume_src = inspect.getsource(engineer_phase3.consume_allocation)
    assert "on_part_consumed" in consume_src

    transfer_src = inspect.getsource(admin_stock.transfer)
    assert "_sync_transfer_to_sicon" in transfer_src

    take_src = inspect.getsource(admin_stock.stock_take)
    assert "on_stock_adjusted" in take_src
