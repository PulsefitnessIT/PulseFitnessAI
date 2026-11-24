"""Contract Management Phase A + B — approval policy, calendar dates,
idempotent activation, truthful renewal comms, sales → coordinator handover.

Fictional data only (prefix ``cm_ab_``); everything is removed afterwards.
"""
import asyncio
import os
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token
from utils.cm_dates import billing_schedule, service_schedule

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_ab_"
TODAY = datetime.now(timezone.utc).date()


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)
    yield
    rx = {"$regex": f"^{T}"}
    for coll in ("crm2_contracts", "crm2_companies", "crm2_contacts", "organizations", "sites", "equipment",
                 "crm2_afs_quotes", "crm2_afs_agreements", "crm_quotes", "crm2_afs_service_schedules",
                 "crm2_afs_billing", "crm2_afs_finance_sync", "crm2_contract_assets"):
        mdb[coll].delete_many({"$or": [{"id": rx}, {"organization_id": rx}, {"company_id": rx}, {"contract_id": rx},
                                       {"previous_contract_id": rx}, {"source_agreement_id": rx}, {"source_sales_quote_id": rx}]})
    mdb.crm2_activities.delete_many({"$or": [{"company_id": rx}, {"contract_id": rx}, {"dedupe_key": {"$regex": f"{T}"}}]})


# ── A3 calendar ──────────────────────────────────────────────────────────

def test_monthly_billing_month_end_and_leap_year():
    rows = billing_schedule(1200, "monthly", "2024-01-31", "2025-01-30", 1)
    assert [r["due_date"] for r in rows[:3]] == ["2024-01-31", "2024-02-29", "2024-03-31"]
    assert len(rows) == 12 and rows[-1]["due_date"] == "2024-12-31" and rows[0]["amount"] == 100.0


def test_annual_billing_leap_day_and_multi_year():
    rows = billing_schedule(500, "annual", "2024-02-29", "2027-02-27", 3)
    assert [r["due_date"] for r in rows] == ["2024-02-29", "2025-02-28", "2026-02-28"]
    q = billing_schedule(1000, "quarterly", "2025-01-15", "2026-01-14", 1)
    assert [r["due_date"] for r in q] == ["2025-01-15", "2025-04-15", "2025-07-15", "2025-10-15"] and q[0]["amount"] == 250.0


def test_missing_start_never_becomes_today():
    assert billing_schedule(1000, "monthly", None) == [] and service_schedule("", 2) == []
    assert billing_schedule(1000, None, "2025-01-01") == []


def test_service_schedule_calendar_months():
    rows = service_schedule("2025-03-31", 2, "2027-03-30", 2)
    # No visit at commencement; the year's last visit is on the anniversary (final one clamped to cover).
    assert [r["planned_date"] for r in rows] == ["2025-09-30", "2026-03-31", "2026-09-30", "2027-03-30"]
    for years in (1, 2, 3, 4):  # one annual visit per contract year, first on the anniversary
        dates = [r["planned_date"] for r in service_schedule("2026-01-01", 1, None, years)]
        assert len(dates) == years and dates[0] == ("2026-12-31" if years == 1 else "2027-01-01")
        assert dates[-1] == f"{2025 + years}-12-31"


# ── A4 atomic actions ────────────────────────────────────────────────────

def test_concurrent_raise_action_creates_one_item():
    from utils.cm_actions import raise_action, ensure_indexes

    async def go():
        await ensure_indexes()
        await asyncio.gather(*[raise_action(OP, f"cm:test:{T}race", type_="contract_missing_info", subject="x", body="y",
                                            contract={"id": f"{T}race", "company_id": f"{T}co"}) for _ in range(8)])
    asyncio.run(go())
    assert mdb.crm2_activities.count_documents({"dedupe_key": f"cm:test:{T}race"}) == 1


# ── A1 / A5 renewal approval + comms ─────────────────────────────────────

def _renewal_draft(rid, prev_id):
    mdb.crm2_contacts.insert_one({"id": f"{T}ct", "organization_id": OP, "company_id": f"{T}co-r", "email": "ren@example.test"})
    mdb.crm2_contracts.insert_one({"id": prev_id, "organization_id": OP, "contract_number": prev_id.upper(), "company_id": f"{T}co-r",
                                   "status": "active", "annual_value": 1000.0, "end_date": (TODAY + timedelta(days=20)).isoformat()})
    mdb.crm2_contracts.insert_one({"id": rid, "organization_id": OP, "contract_number": rid.upper(), "company_id": f"{T}co-r",
                                   "company_name": "AB Gym", "contact_id": f"{T}ct", "status": "renewal_pending_approval",
                                   "previous_contract_id": prev_id, "annual_value": 1000.0, "renewal_uplift_percent": 0,
                                   "start_date": (TODAY + timedelta(days=21)).isoformat(), "end_date": (TODAY + timedelta(days=385)).isoformat()})


def test_coordinator_needs_manager_for_non_standard_increase():
    rid, prev = f"{T}ren1", f"{T}prev1"
    _renewal_draft(rid, prev)
    coord, asm = _crm("cm-test-coord"), _crm("cm-test-asm")
    r = requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=coord, json={"uplift_percent": 5})
    assert r.status_code == 403 and "manager approval" in r.json()["detail"]
    assert mdb.crm2_contracts.find_one({"id": rid})["status"] == "renewal_pending_approval"
    r = requests.post(f"{API}/crm/workspace/renewals/{rid}/request-approval", headers=coord, json={"uplift_percent": 5, "reason": "Parts costs"})
    assert r.status_code == 200
    assert mdb.crm2_activities.count_documents({"type": "renewal_price_approval", "renewal_contract_id": rid, "status": "open"}) == 1
    r = requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=asm, json={"uplift_percent": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["annual_value"] == 1050.0 and body["accept_link"].endswith(mdb.crm2_contracts.find_one({"id": rid})["accept_token"])
    doc = mdb.crm2_contracts.find_one({"id": rid})
    ev = [e["action"] for e in doc["approval_evidence"]]
    assert ev == ["price_increase_requested", "approved_and_issued"]
    assert doc["approval_evidence"][1]["basis"] == "manager-approved increase"
    assert doc["renewal_comms_status"] == ("delivered" if body["email_delivered"] else "approved_not_delivered")
    assert mdb.crm2_activities.count_documents({"type": "renewal_price_approval", "renewal_contract_id": rid, "status": "open"}) == 0
    lst = requests.get(f"{API}/crm/workspace/renewals", headers=coord).json()["renewals"]
    row = next(x for x in lst if x["id"] == rid)
    assert row["renewal_accept_link"] == body["accept_link"] and row["comms_status"] in ("delivered", "approved_not_delivered")
    if not body["email_delivered"]:
        assert mdb.crm2_activities.count_documents({"dedupe_key": f"cm:renewal-undelivered:{rid}", "status": "open"}) == 1
    assert requests.post(f"{API}/crm/workspace/renewals/{rid}/resend", headers=coord).status_code == 200
    assert requests.post(f"{API}/crm/workspace/renewals/{rid}/declined", headers=coord, json={}).status_code == 200
    assert next(x for x in requests.get(f"{API}/crm/workspace/renewals", headers=coord).json()["renewals"] if x["id"] == rid)["comms_status"] == "declined"


def test_coordinator_can_issue_standard_renewal():
    rid, prev = f"{T}ren2", f"{T}prev2"
    mdb.crm2_contacts.delete_many({"id": f"{T}ct"})
    _renewal_draft(rid, prev)
    r = requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=_crm("cm-test-coord"), json={})
    assert r.status_code == 200 and r.json()["annual_value"] == 1000.0
    assert mdb.crm2_contracts.find_one({"id": rid})["approval_evidence"][0]["basis"].startswith("standard")


# ── A2 activation ────────────────────────────────────────────────────────

def _agreement(aid, company, **kw):
    doc = {"id": aid, "organization_id": OP, "company_id": company, "company_name": "AB Leisure", "status": "signed",
           "agreement_number": aid.upper(), "schedules": {"schedule2_agreement": {"agreement_type": "Gold"}},
           "annual_value": 1200.0, "term_years": 1, "start_date": "2026-01-31", "end_date": "2027-01-30",
           "billing_frequency": "monthly", "visits_per_year": 2, "contract_type": "gold",
           "linked_organization_id": f"{T}org", "asset_register": [{"id": f"{T}eq1", "annual": 100}], "timeline": []}
    doc.update(kw)
    mdb.crm2_afs_agreements.insert_one(doc)


def test_activation_is_idempotent_and_preserves_history():
    mdb.equipment.insert_one({"id": f"{T}eq1", "organization_id": f"{T}org", "name": "Bike", "serial_number": "AB1"})
    _agreement(f"{T}ag1", f"{T}co-a")
    h = _crm("cm-test-coord")
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag1/activate", headers=h, json={})
    assert r.status_code == 200, r.text
    cid = r.json()["contract_id"]
    again = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag1/activate", headers=h, json={}).json()
    assert again["already_active"] and again["contract_id"] == cid
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": f"{T}ag1"}) == 1
    bill = mdb.crm2_afs_billing.find_one({"contract_id": cid})
    assert [i["due_date"] for i in bill["invoices"][:2]] == ["2026-01-31", "2026-02-28"]
    # Simulate completed service + posted invoice, then a retry.
    svc = mdb.crm2_afs_service_schedules.find_one({"contract_id": cid})
    svc["visits"][0].update({"status": "completed", "completed_case_id": "case-1"})
    mdb.crm2_afs_service_schedules.update_one({"contract_id": cid}, {"$set": {"visits": svc["visits"]}})
    bill["invoices"][0].update({"status": "posted", "sage_invoice_ref": "INV-REAL-1"})
    mdb.crm2_afs_billing.update_one({"contract_id": cid}, {"$set": {"invoices": bill["invoices"]}})
    mdb.crm2_contracts.update_one({"id": cid}, {"$set": {"sage_reference": "SO-REAL-9"}})
    mdb.crm2_afs_agreements.update_one({"id": f"{T}ag1"}, {"$set": {"status": "activation_attention"}})
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag1/activate", headers=h, json={})
    assert r.status_code == 200 and r.json()["contract_id"] == cid
    v = mdb.crm2_afs_service_schedules.find_one({"contract_id": cid})["visits"]
    assert v[0]["status"] == "completed" and len(v) == 2
    inv = mdb.crm2_afs_billing.find_one({"contract_id": cid})["invoices"]
    assert inv[0]["sage_invoice_ref"] == "INV-REAL-1" and len(inv) == 12
    assert mdb.crm2_contracts.find_one({"id": cid})["sage_reference"] == "SO-REAL-9"
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": f"{T}ag1"}) == 1


def test_activation_conflict_requires_authorised_review():
    mdb.crm2_contracts.insert_one({"id": f"{T}existing", "organization_id": OP, "company_id": f"{T}co-b", "status": "active",
                                   "contract_number": "AB-OLD", "end_date": "2026-12-31"})
    _agreement(f"{T}ag2", f"{T}co-b", asset_register=[])
    coord, asm = _crm("cm-test-coord"), _crm("cm-test-asm")
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag2/activate", headers=coord, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "activation_conflict"
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": f"{T}ag2"}) == 0
    assert requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag2/activate", headers=coord,
                         json={"conflict_review_note": "ok"}).status_code == 403
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag2/activate", headers=asm,
                      json={"conflict_review_note": "Old contract ends before new term — replacement"})
    assert r.status_code == 200 and r.json()["steps"][0]["status"] == "approved_override"


def test_activation_blocked_without_dates():
    _agreement(f"{T}ag3", f"{T}co-c", start_date=None, asset_register=[])
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/{T}ag3/activate", headers=_crm("cm-test-coord"), json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "missing_information"
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": f"{T}ag3"}) == 0


def test_agreement_requires_accepted_maintenance_quote():
    mdb.crm2_afs_quotes.insert_one({"id": f"{T}q-draft", "organization_id": OP, "company_id": f"{T}co-c", "status": "draft"})
    r = requests.post(f"{API}/crm/v2/aftersales/agreements/from-quote/{T}q-draft", headers=_crm("cm-test-coord"),
                      json={"start_date": "2026-01-01"})
    assert r.status_code == 400


def test_finance_sync_never_double_posts():
    from utils.finance_sync import enqueue_finance_sync
    mdb.crm2_contracts.insert_one({"id": f"{T}fin", "organization_id": OP, "company_id": f"{T}co-f", "status": "active"})
    mdb.crm2_afs_finance_sync.insert_one({"contract_id": f"{T}fin", "organization_id": OP, "status": "synced", "external_ref": "SO-1"})
    res = asyncio.run(enqueue_finance_sync(OP, f"{T}fin", "retry", "test"))
    assert res["duplicate_prevented"] and res["external_ref"] == "SO-1"


# ── B sales handover ─────────────────────────────────────────────────────

def test_accepted_sale_creates_one_opportunity_and_prefilled_quote():
    mdb.organizations.insert_one({"id": f"{T}cust", "name": "AB Sale Gym"})
    mdb.crm2_companies.insert_one({"id": f"{T}co-s", "organization_id": OP, "name": "AB Sale Gym", "tenant_org_id": f"{T}cust",
                                   "coordinator_id": "cm-test-coord", "coordinator_name": "Casey Coordinator"})
    mdb.sites.insert_one({"id": f"{T}site", "organization_id": f"{T}cust", "name": "Main"})
    mdb.crm_quotes.insert_one({"id": f"{T}sale", "organization_id": OP, "company_id": f"{T}co-s", "status": "accepted", "quote_number": "Q-AB-1"})
    mdb.crm_quotes.insert_one({"id": f"{T}sale-noeq", "organization_id": OP, "company_id": f"{T}co-s", "status": "accepted"})
    for i in (1, 2):
        mdb.equipment.insert_one({"id": f"{T}seq{i}", "organization_id": f"{T}cust", "site_id": f"{T}site", "quote_id": f"{T}sale",
                                  "name": "Treadmill", "model": "TM1", "serial_number": f"S{i}" if i == 1 else None})
    h = _crm("cm-test-sales")
    assert requests.post(f"{API}/crm/workspace/sales-handover/{T}sale-noeq", headers=h).json()["created"] is False
    for _ in range(3):
        assert requests.post(f"{API}/crm/workspace/sales-handover/{T}sale", headers=h).status_code == 200
    acts = list(mdb.crm2_activities.find({"dedupe_key": f"cm:sale-handover:{T}sale"}))
    assert len(acts) == 1
    a = acts[0]
    assert a["owner_id"] == "cm-test-coord" and a["equipment_count"] == 2 and a["serials_confirmed"] == 1
    assert sorted(a["equipment_ids"]) == [f"{T}seq1", f"{T}seq2"] and a["site_ids"] == [f"{T}site"]
    assert mdb.crm2_companies.find_one({"id": f"{T}co-s"})["linked_organization_id"] == f"{T}cust"
    pr = requests.get(f"{API}/crm/v2/aftersales/priorities", headers=_crm("cm-test-coord")).json()["priorities"]
    assert not any(p.get("quote_id") == f"{T}sale" and p["kind"] == "agreement" for p in pr)
    coord = _crm("cm-test-coord")
    body = {"company_id": f"{T}co-s", "site_ids": a["site_ids"], "asset_ids": a["equipment_ids"], "save": True,
            "source_sales_quote_id": f"{T}sale", "source": "sales_handover"}
    r1 = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=coord, json=body)
    assert r1.status_code == 200, r1.text
    q1 = r1.json()["saved_quote_id"]
    q = mdb.crm2_afs_quotes.find_one({"id": q1})
    assert q["source_sales_quote_id"] == f"{T}sale" and q["company_id"] == f"{T}co-s"
    assert len(q["asset_register"]) == 2
    assert mdb.crm2_activities.find_one({"dedupe_key": f"cm:sale-handover:{T}sale"})["status"] == "done"
    r2 = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=coord, json=body).json()
    assert r2["existing"] is True and r2["saved_quote_id"] == q1
    assert mdb.crm2_afs_quotes.count_documents({"source_sales_quote_id": f"{T}sale"}) == 1
