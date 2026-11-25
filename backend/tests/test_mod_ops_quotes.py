"""MOD Operations quotation system — HMNB Clyde reference quotations (QT9410/QT9411/QT9412) and full workflow.

Synthetic contact data only. Runs in-process against the real Mongo via ASGI with auth overridden.
"""
import io
import os
import uuid
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from routes.bfpo import _require_staff
from server import app
from utils.auth import get_current_user
from utils.database import db
from utils.mod_quote_engine import build_quote, parse_schedule_b

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mod_quotes")
SOR = os.path.join(FIX, "schedule_b_sor.xlsx")
RUN = uuid.uuid4().hex[:6]
SITE_A, SITE_B, OP_ORG = f"t-modq-site-a-{RUN}", f"t-modq-site-b-{RUN}", f"t-modq-op-{RUN}"
STAFF = {"id": f"t-staff-{RUN}", "email": "sales@example.test", "full_name": "Test MOD Sales", "organization_id": OP_ORG,
         "is_master_admin": False, "mod_quote_role": "pricing_admin_manager"}
CUST_A = {"id": f"t-cust-a-{RUN}", "email": "officer@example.test", "full_name": "Test Officer", "organization_id": SITE_A}
CUST_B = {"id": f"t-cust-b-{RUN}", "email": "other@example.test", "full_name": "Other Site", "organization_id": SITE_B}

CLYDE = [("sor-5", "Benches", 2, "B", ""), ("sor-20", "Single Station Strength", 4, "B", ""),
         ("sor-23", "Multigym 2 Station", 1, "B", ""), ("sor-2", "Treadmills", 2, "A", ""),
         ("sor-8", "Cross Trainer", 1, "A", ""), ("sor-4", "Rowers", 2, "A", "Rowers"),
         ("sor-4", "Ski-Ergs", 2, "A", "Ski-Ergs"), ("sor-18", "Airbikes", 2, "A", "Airbikes"),
         ("sor-18", "Assault Bikes", 2, "A", "Assault Bikes")]
ROWS = [{"row_id": f"r{i}", "rate_card_id": rid, "description": d, "qty": q, "coverage": cv, "label": lb}
        for i, (rid, d, q, cv, lb) in enumerate(CLYDE)]

EXPECTED = {
    "A": [("CON-MOD-001", "Type A: 1 Year Fully Inclusive MOD Aftersales Maintenance Contract", 1, 0.0),
          ("MOD-BENCH-A", "SER100144 - Benches - Type A Service", 2, 43.53),
          ("MOD-STRENGTH-A", "SER100191 - SingleStation Strength Machine - Type A Service", 4, 90.0),
          ("MOD-MULTI2-A", "SER100167 - Multigym, 2 Station - Type A Service", 1, 145.12),
          ("MOD-TREAD-A", "SER100201 - Treadmill - Type A Service", 2, 255.0),
          ("MOD-XT-A", "SER100151 - Cross Trainer, Non Powered - Type A Service", 1, 157.2),
          ("MOD-ROW-A", "SER100189 - Rowing Machine - Type A Service (Rowers)", 2, 72.56),
          ("MOD-ROW-A", "SER100189 - Rowing Machine - Type A Service (Ski-Ergs)", 2, 72.56),
          ("MOD-UBIKE-A", "SER100203 - Upright Bike, Non Powered - Type A Service (Airbikes)", 2, 157.2),
          ("MOD-UBIKE-A", "SER100203 - Upright Bike, Non Powered - Type A Service (Assault Bikes)", 2, 157.2)],
    "B": [("CON-MOD-002", "Type B: One-Off Service or Repair.", 1, 0.0),
          ("MOD-CALLOUT", "SER100146 - Call Out Charge - Type B Only", 1, 80.0),
          ("MOD-BENCH-B", "SER100145 - Benches - Type B Service", 2, 7.0),
          ("MOD-STRENGTH-B", "SER100192 - SingleStation Strength Machine - Type B Service", 4, 16.0),
          ("MOD-MULTI2-B", "SER100168 - Multigym, 2 Station - Type B Service", 1, 21.0),
          ("MOD-TREAD-B", "SER100202 - Treadmill - Type B Service", 2, 24.0),
          ("MOD-XT-B", "SER100152 - Cross Trainer, Non Powered - Type B Service", 1, 24.0),
          ("MOD-ROW-B", "SER100190 - Rowing Machine - Type B Service (Rowers)", 2, 16.0),
          ("MOD-ROW-B", "SER100190 - Rowing Machine - Type B Service (Ski-Ergs)", 2, 16.0),
          ("MOD-UBIKE-B", "SER100204 - Upright Bike, Non Powered - Type B Service (Airbikes)", 2, 16.0),
          ("MOD-UBIKE-B", "SER100204 - Upright Bike, Non Powered - Type B Service (Assault Bikes)", 2, 16.0)],
    "AB": [("CON-MOD-001", "Type A: 1 Year Fully Inclusive MOD Aftersales Maintenance Contract", 1, 0.0),
           ("CON-MOD-002", "Type B: One-Off Service or Repair.", 1, 0.0),
           ("MOD-BENCH-B", "SER100145 - Benches - Type B Service", 2, 7.0),
           ("MOD-STRENGTH-B", "SER100192 - SingleStation Strength Machine - Type B Service", 4, 16.0),
           ("MOD-MULTI2-B", "SER100168 - Multigym, 2 Station - Type B Service", 1, 21.0),
           ("MOD-TREAD-A", "SER100201 - Treadmill - Type A Service", 2, 255.0),
           ("MOD-XT-A", "SER100151 - Cross Trainer, Non Powered - Type A Service", 1, 157.2),
           ("MOD-ROW-A", "SER100189 - Rowing Machine - Type A Service (Rowers)", 2, 72.56),
           ("MOD-ROW-A", "SER100189 - Rowing Machine - Type A Service (Ski-Ergs)", 2, 72.56),
           ("MOD-UBIKE-A", "SER100203 - Upright Bike, Non Powered - Type A Service (Airbikes)", 2, 157.2),
           ("MOD-UBIKE-A", "SER100203 - Upright Bike, Non Powered - Type A Service (Assault Bikes)", 2, 157.2)],
}
TOTALS = {"A": (2178.42, 435.68, 2614.10), "B": (379.00, 75.80, 454.80), "AB": (1685.24, 337.05, 2022.29)}

_who = {"user": STAFF}
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _override():
    return _who["user"]


@pytest.fixture
async def client():
    from routes.mod_ops_quotes import _ensure_rate_card
    await _ensure_rate_card()
    snapshot = await db.mod_sor_rate_card.find({}, {"_id": 0}).to_list(200)
    await db.organizations.insert_many([
        {"id": OP_ORG, "name": "Test Operator", "is_operator_company": True, "account_type": "full"},
        {"id": SITE_A, "name": f"HMNB Clyde Test {RUN}", "account_type": "mod_site", "address_line1": "Faslane",
         "city": "Helensburgh", "county": "Dunbartonshire", "postcode": "G84 0EH", "country": "Great Britain",
         "primary_contact_name": "Test Officer", "primary_contact_email": "officer@example.test"},
        {"id": SITE_B, "name": f"Other Site {RUN}", "account_type": "mod_site"}])
    app.dependency_overrides[_require_staff] = _override
    app.dependency_overrides[get_current_user] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.pop(_require_staff, None)
    app.dependency_overrides.pop(get_current_user, None)
    gids = [g["id"] async for g in db.mod_quote_groups.find({"mod_site_id": {"$in": [SITE_A, SITE_B]}}, {"id": 1})]
    for coll, key in (("crm2_quotes", "mod_group_id"), ("mod_quote_events", "group_id"),
                      ("mod_quote_authorisations", "group_id"), ("mod_quote_handovers", "group_id")):
        await db[coll].delete_many({key: {"$in": gids}})
    await db.mod_quote_groups.delete_many({"id": {"$in": gids}})
    await db.organizations.delete_many({"id": {"$in": [OP_ORG, SITE_A, SITE_B]}})
    for e in snapshot:
        await db.mod_sor_rate_card.replace_one({"id": e["id"]}, e)
    await db.mod_sor_price_lists.delete_many({"uploaded_by": STAFF["full_name"]})


async def _import_rates(c):
    with open(SOR, "rb") as fh:
        r = await c.post("/api/mod-ops/quotes/rates/import-preview", files={"file": ("sor.xlsx", fh.read())})
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = {i["kind"] for i in body["issues"]}
    assert {"duplicate_sage_code", "reference_conflict"} <= kinds
    assert any(i.get("uid") == "2A" and i["schedule_b_ref"] == "SER100135" and i["printed_ref"] == "SER100201" for i in body["issues"])
    r = await c.post(f"/api/mod-ops/quotes/rates/{body['price_list_id']}/approve", json={"effective_from": "2026-11-20", "confirm": True})
    assert r.status_code == 200, r.text


def _customer():
    return {"site_id": SITE_A, "name": f"HMNB Clyde Test {RUN}", "address_lines": ["Faslane", "Helensburgh", "Dunbartonshire", "G84 0EH", "Great Britain"]}


def test_schedule_b_parser_reads_actual_layout():
    p = parse_schedule_b(open(SOR, "rb").read())
    by = {e["uid"]: e for e in p["entries"]}
    assert by["1B"]["price"] == 80 and by["2A"]["sage_code"] == "MOD-TREAD-A" and by["2A"]["tl_ref"] == "SER100135"
    assert by["28C"]["is_poa"] and by["26A"]["ambiguous_sage_code"] and by["27A"]["ambiguous_sage_code"]


async def test_reference_quotations_line_by_line(client):
    await _import_rates(client)
    r = await client.post("/api/mod-ops/quotes/preview", json={"customer": _customer(), "rows": ROWS, "options": ["A", "B", "AB"]})
    assert r.status_code == 200, r.text
    for t, opt in r.json()["options"].items():
        got = [(ln["item_code"], ln["description"], ln["qty"], ln["unit_price"]) for ln in opt["lines"]]
        assert got == EXPECTED[t], t
        assert (opt["net"], opt["vat"], round(opt["gross"], 2)) == TOTALS[t], t
        assert all(ln["unit"] == "Each" for ln in opt["lines"])
        assert all(round(ln["qty"] * ln["unit_price"], 2) == ln["total"] for ln in opt["lines"])
    assert not any(ln["item_code"] == "MOD-CALLOUT" for ln in r.json()["options"]["AB"]["lines"])


async def test_mixed_requires_coverage_and_recalculates(client):
    await _import_rates(client)
    rows = [dict(r) for r in ROWS]
    rows[0]["coverage"] = None
    r = await client.post("/api/mod-ops/quotes/groups", json={"customer": _customer(), "rows": rows, "options": ["AB"]})
    assert r.status_code == 422
    rows[0]["coverage"] = "A"
    rows[3]["qty"] = 3
    r = await client.post("/api/mod-ops/quotes/preview", json={"customer": _customer(), "rows": rows, "options": ["A", "B", "AB"]})
    o = r.json()["options"]
    assert o["A"]["net"] == round(2178.42 + 255.0, 2) and o["B"]["net"] == 379.0 + 24.0
    assert o["AB"]["net"] == round(1685.24 - 14.0 + 87.06 + 255.0, 2)


async def test_full_workflow_isolation_and_handover(client):
    await _import_rates(client)
    r = await client.post("/api/mod-ops/quotes/groups", json={"customer": _customer(), "rows": ROWS, "options": ["A", "B", "AB"]})
    assert r.status_code == 200, r.text
    g = r.json()
    gid, quotes = g["id"], g["quotes"]
    assert len(quotes) == 3 and all(q["status"] == "draft" and q["quote_number"].startswith("PFQ-") for q in quotes)

    _who["user"] = CUST_A
    r = await client.get("/api/mod/site/quotes")
    assert r.status_code == 200 and not [q for q in r.json()["quotes"] if q.get("mod_group_id") == gid], "drafts must be hidden"
    assert (await client.get(f"/api/mod/site/quotes/{quotes[0]['id']}/pdf")).status_code == 404
    _who["user"] = STAFF

    assert (await client.post(f"/api/mod-ops/quotes/groups/{gid}/publish", json={"quote_ids": [quotes[0]["id"]]})).status_code == 409
    assert (await client.post(f"/api/mod-ops/quotes/groups/{gid}/submit")).status_code == 200
    assert (await client.post(f"/api/mod-ops/quotes/groups/{gid}/approve", json={})).status_code == 200
    r = await client.post(f"/api/mod-ops/quotes/groups/{gid}/publish", json={"quote_ids": [q["id"] for q in quotes]})
    assert r.status_code == 200, r.text

    _who["user"] = CUST_A
    r = await client.get("/api/mod/site/quotes")
    grp = next(x for x in r.json()["groups"] if x["id"] == gid)
    assert len(grp["quotes"]) == 3
    pdf = await client.get(f"/api/mod/site/quotes/{quotes[0]['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "attachment" in pdf.headers["content-disposition"]
    z = await client.get(f"/api/mod/site/quote-groups/{gid}/zip")
    assert z.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 3
    assert (await db.mod_quote_groups.find_one({"id": gid}))["status"] == "published", "download must not accept"
    assert (await client.post(f"/api/mod/site/quotes/{quotes[0]['id']}/sign", json={"signature": "x"})).status_code == 409

    _who["user"] = CUST_B
    assert (await client.get(f"/api/mod/site/quotes/{quotes[0]['id']}")).status_code == 404
    assert (await client.get(f"/api/mod/site/quote-groups/{gid}/zip")).status_code == 404

    _who["user"] = STAFF
    r = await client.put(f"/api/mod-ops/quotes/groups/{gid}", json={"customer": _customer(), "rows": ROWS, "options": ["A", "B", "AB"]})
    assert r.status_code == 200 and r.json()["revision"] == 2 and len(r.json()["superseded"]) == 3
    old_mix = next(q for q in quotes if q["mod_quote_type"] == "AB")
    _who["user"] = CUST_A
    r = await client.post(f"/api/mod/site/quotes/{old_mix['id']}/authorise",
                          data={"authorising_officer": "Test Officer", "authorisation_date": "2026-11-25"})
    assert r.status_code == 404, "superseded version must not be authorisable"
    _who["user"] = STAFF
    await client.post(f"/api/mod-ops/quotes/groups/{gid}/submit")
    await client.post(f"/api/mod-ops/quotes/groups/{gid}/approve", json={})
    new = (await client.get(f"/api/mod-ops/quotes/groups/{gid}")).json()["quotes"]
    await client.post(f"/api/mod-ops/quotes/groups/{gid}/publish", json={"quote_ids": [q["id"] for q in new]})
    mix = next(q for q in new if q["mod_quote_type"] == "AB")

    _who["user"] = CUST_A
    r = await client.post(f"/api/mod/site/quotes/{mix['id']}/authorise",
                          data={"po_reference": "PO-TEST-1", "authorising_officer": "Test Officer", "authorisation_date": "2026-11-25"},
                          files={"evidence": ("approval.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200, r.text
    aid = r.json()["authorisation"]["id"]
    assert await db.mod_quote_handovers.count_documents({"group_id": gid}) == 0

    _who["user"] = STAFF
    r = await client.post(f"/api/mod-ops/quotes/authorisations/{aid}/verify", json={"accept": True})
    assert r.status_code == 200, r.text
    assert (await client.post(f"/api/mod-ops/quotes/authorisations/{aid}/verify", json={"accept": True})).status_code == 409
    h = await db.mod_quote_handovers.find_one({"group_id": gid})
    assert h["annual_type_a_value"] == 1586.24 and h["one_off_type_b_value"] == 99.0
    assert {c["coverage"] for c in h["coverage"] if c["annual_obligation"]} == {"A"}
    from routes.mod_ops_quotes import handover_quote
    q = await db.crm2_quotes.find_one({"id": mix["id"]}, {"_id": 0})
    await handover_quote(q, await db.mod_quote_groups.find_one({"id": gid}, {"_id": 0}), STAFF)
    assert await db.mod_quote_handovers.count_documents({"group_id": gid}) == 1
    kinds = {e["kind"] async for e in db.mod_quote_events.find({"group_id": gid})}
    assert {"created", "approved", "published", "customer_downloaded", "revised", "authorisation_submitted", "accepted", "operations_handover"} <= kinds
