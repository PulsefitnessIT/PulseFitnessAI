"""MOD quotation chase-ups (2/4/6 weeks) and the LSLDC0186 'Pricing Schedule' Schedule B layout."""
import io
import uuid
from datetime import date

import openpyxl
import pytest

from utils.database import db
from utils.mod_quote_chase import chase_schedule, run_chases
from utils.mod_quote_engine import diff_against_card, parse_schedule_b, schedule_label

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _pricing_schedule_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "1. Pricing Schedule "
    ws.append(["SYNTHETIC TEST DATA"])
    ws.append(["Item no", "TL Number", "Domestic Management Code (DMC)", "Supplier Part Number", "NSN (from Msys.PDM)",
               "Short Item Description \n(max char 30)", "Extended Item Description\n(max char 30)", "Service (S) or Goods (G)",
               "Year 3 Price", "Year 4 Estimated Quantity", "Year 4 Price"])
    ws.append([1, "SER1", "PAT", "MOD-CALLOUT", "N/A", "Call Out Charge,", "Type B Only", "S", 70, None, 75])
    ws.append(["2A", "SER2", "PAT", "MOD-TREAD-A", "N/A", "Treadmill,", "Type A Service", "S", 200, None, 210])
    ws.append(["2B", "SER3", "PAT", "MOD-TREAD-B", "N/A", "Treadmill,", "Type B Service", "S", 20, None, 22])
    ws.append(["9A", "SER4", "PAT", "MOD-MULTI9-A", "N/A", "Multigym,", "9 Station, Type A Service", "S", 300, None, 310])
    ws.append([33, "SER5", "PAT", "SER5", "N/A", "Overseas", "Type C Service, POA", "S", None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_chase_schedule_is_2_4_6_weeks():
    s = chase_schedule(date(2026, 11, 25))
    assert [c["due"] for c in s] == ["2026-12-09", "2026-12-23", "2027-01-06"]
    assert all(c["status"] == "pending" for c in s)


def test_pricing_schedule_uses_latest_year_and_matches_by_name_then_code():
    parsed = parse_schedule_b(_pricing_schedule_bytes())
    assert parsed["price_year"] == 4 and parsed["synthetic"] is True
    by_uid = {e["uid"]: e for e in parsed["entries"]}
    assert set(by_uid) == {"1B", "2A", "2B", "9A"}  # Type C POA row is not an A/B rate
    assert by_uid["1B"]["price"] == 75 and by_uid["2A"]["price"] == 210
    assert schedule_label(by_uid["9A"]) == "Multigym — 9 Station"
    card = [{"id": "c1", "item_no": "1", "kind": "call_out", "label": "Call Out Charge (Type B / UK Only)", "sage_code_b": "MOD-CALLOUT", "type_b_price": 80},
            {"id": "c2", "item_no": "7", "kind": "service", "label": "Treadmill", "sage_code_a": "MOD-TREAD-A", "type_a_price": 200}]
    rows = {r["uid"]: r for r in diff_against_card(parsed["entries"], card)}
    assert rows["1B"]["rate_card_id"] == "c1" and rows["1B"]["change"] == "changed"
    assert rows["2A"]["rate_card_id"] == "c2"  # matched despite different item numbering
    assert rows["9A"]["change"] == "new"


async def _group(status="published", due="2026-01-01"):
    gid = f"chase-test-{uuid.uuid4().hex[:8]}"
    await db.mod_quote_groups.insert_one({
        "id": gid, "organization_id": "chase-test-org", "status": status, "revision": 1, "created_by": "chase-test-user",
        "created_by_name": "Chase Tester", "customer": {"name": "Synthetic Barracks", "contact_email": "officer@example.invalid"},
        "chase_schedule": [{"n": 1, "weeks": 2, "due": due, "status": "pending"},
                           {"n": 2, "weeks": 4, "due": "2999-01-01", "status": "pending"}]})
    return gid


async def _cleanup(gid):
    await db.mod_quote_groups.delete_one({"id": gid})
    await db.mod_quote_followups.delete_many({"group_id": gid})
    await db.mod_quote_events.delete_many({"group_id": gid})


async def test_due_chase_raises_one_followup_and_is_idempotent(monkeypatch):
    monkeypatch.delenv("MOD_QUOTE_NOTIFY_LIVE", raising=False)
    gid = await _group()
    try:
        await run_chases(date(2026, 1, 2))
        await run_chases(date(2026, 1, 2))
        fus = await db.mod_quote_followups.find({"group_id": gid}, {"_id": 0}).to_list(10)
        assert len(fus) == 1 and fus[0]["chase_no"] == 1 and fus[0]["assigned_to"] == "chase-test-user"
        g = await db.mod_quote_groups.find_one({"id": gid}, {"_id": 0})
        assert [c["status"] for c in g["chase_schedule"]] == ["done", "pending"]
    finally:
        await _cleanup(gid)


async def test_chase_cancelled_once_customer_has_authorised():
    gid = await _group(status="authorisation_submitted")
    try:
        await run_chases(date(2026, 1, 2))
        assert await db.mod_quote_followups.count_documents({"group_id": gid}) == 0
        g = await db.mod_quote_groups.find_one({"id": gid}, {"_id": 0})
        assert g["chase_schedule"][0]["status"] == "cancelled"
    finally:
        await _cleanup(gid)
