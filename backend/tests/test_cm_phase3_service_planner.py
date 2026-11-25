"""Phase 3 — contractual PPM obligations ↔ Service Desk bookings ↔ verified
completions (+ historical reconciliation, Action Centre, autogen guard).

Fictional data only (prefix ``cm_p3_``); everything is removed afterwards.
"""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import asyncio
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token
from utils.cm_dates import service_schedule
from utils.cm_service_link import merge_obligations, plan_obligations

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_p3_"
AFS = f"{API}/crm/v2/aftersales"
CUST = f"{T}cust"
S1, S2 = f"{T}site1", f"{T}site2"


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cleanup():
    rx = {"$regex": f"^{T}"}
    ag_ids = [a["id"] for a in mdb.crm2_afs_agreements.find({"quote_id": rx}, {"id": 1})]
    cids = [c["id"] for c in mdb.crm2_contracts.find({"$or": [{"source_agreement_id": {"$in": ag_ids}}, {"company_id": rx}]}, {"id": 1})]
    case_ids = [c["id"] for c in mdb.svc_cases.find({"$or": [{"site_id": rx}, {"contract_id": {"$in": cids}}]}, {"id": 1})]
    mdb.svc_work_visit_machines.delete_many({"case_id": {"$in": case_ids}})
    mdb.svc_case_events.delete_many({"case_id": {"$in": case_ids}})
    mdb.svc_cases.delete_many({"id": {"$in": case_ids}})
    mdb.crm2_activities.delete_many({"$or": [{"contract_id": {"$in": cids}}, {"company_id": rx}]})
    for coll in ("crm2_afs_service_schedules", "crm2_afs_billing", "crm2_afs_finance_sync"):
        mdb[coll].delete_many({"$or": [{"contract_id": {"$in": cids}}, {"agreement_id": {"$in": ag_ids}}]})
    mdb.crm2_contracts.delete_many({"id": {"$in": cids}})
    mdb.crm2_afs_agreements.delete_many({"quote_id": rx})
    for coll in ("crm2_companies", "organizations", "sites", "equipment", "crm2_afs_quotes", "svc_engineers", "ppm_schedules"):
        mdb[coll].delete_many({"$or": [{"id": rx}, {"organization_id": rx}]})


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd=REPO + "/backend",
                   env={**os.environ, "PYTHONPATH": REPO + "/backend"}, check=True)
    _cleanup()
    mdb.organizations.insert_one({"id": CUST, "name": "P3 Leisure Ltd"})
    mdb.crm2_companies.insert_one({"id": f"{T}co", "organization_id": OP, "name": "P3 Leisure", "legal_name": "P3 Leisure Ltd",
                                   "linked_organization_id": CUST, "coordinator_id": "cm-test-coord",
                                   "coordinator_name": "Casey Coordinator"})
    mdb.sites.insert_many([{"id": S1, "organization_id": CUST, "name": "North Gym", "postcode": "N1 1AA"},
                           {"id": S2, "organization_id": CUST, "name": "South Gym", "postcode": "S1 1AA"}])
    for i, site in ((1, S1), (2, S1), (3, S1), (4, S1), (5, S2)):
        mdb.equipment.insert_one({"id": f"{T}eq{i}", "organization_id": CUST, "site_id": site, "name": "Treadmill",
                                  "serial_number": f"P3S{i}", "status": "active", "install_date": "2024-01-10"})
    mdb.svc_engineers.insert_many([{"id": f"{T}eng", "organization_id": OP, "full_name": "Erin Engineer", "status": "active"},
                                   {"id": f"{T}eng2", "organization_id": OP, "full_name": "Ray Engineer", "status": "active"}])
    yield
    _cleanup()


def _activate(qid, start, term, visits, assets, override=None):
    mdb.crm2_afs_quotes.insert_one({
        "id": qid, "organization_id": OP, "company_id": f"{T}co", "quote_number": qid.upper(), "status": "sent",
        "contract_type": "p3_plan", "linked_organization_id": CUST, "visits_per_year": visits,
        "preferred_payment": "annual", "requested_start_date": start,
        "summary": {"final_annual": 300.0 * len(assets), "term_years": term, "vat_pct": 20},
        "grouped_lines": [{"model": "TM1", "qty": len(assets), "annual_total": 300.0 * len(assets),
                           "serials": ["P3S" + a[-1] for a, _ in assets]}],
        "asset_register": [{"id": a, "annual": 300, "site_id": s} for a, s in assets]})
    h = _crm("cm-test-coord")
    aid = requests.post(f"{AFS}/quotes/{qid}/accept", headers=h, json={}).json()["agreement_id"]
    g = requests.post(f"{AFS}/agreements/{aid}/generate", headers=h)
    assert g.status_code == 200, g.text
    sig = {"signatory_name": "Pat P3", "position": "Director", "email": "pat@p3.example", "authority_confirmed": True}
    assert requests.post(f"{AFS}/agreements/{aid}/sign", headers=h, json=sig).status_code == 200
    r = requests.post(f"{AFS}/agreements/{aid}/activate", headers=_crm("cm-test-asm") if override else h,
                      json={"conflict_review_note": override} if override else {})
    assert r.status_code == 200, r.text
    return r.json()["contract_id"]


def _open(key):
    return list(mdb.crm2_activities.find({"organization_id": OP, "dedupe_key": key, "status": "open"}))


def _visits(cid):
    return mdb.crm2_afs_service_schedules.find_one({"contract_id": cid})["visits"]


def _plan(h, cid):
    return requests.get(f"{AFS}/contracts/{cid}/schedules", headers=h).json()["service"]


def _close(case_id, done="2026-11-20", serviced=(), report=True, **kw):
    mdb.svc_work_visit_machines.delete_many({"case_id": case_id})
    for i, eq in enumerate(serviced):
        mdb.svc_work_visit_machines.insert_one({"case_id": case_id, "asset_id": eq, "serviced": True, "order_index": i})
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"status": "closed", "completed_at": f"{done}T15:00:00+00:00",
                                                        "engineer_report": {"summary": "PPM done"} if report else None, **kw}})


# ───────────────────────────── pure scheduling rules

@pytest.mark.parametrize("years", [1, 2, 3, 4])
def test_multi_year_annual_first_anniversary(years):
    rows = service_schedule("2026-03-15", 1, None, years)
    dates = [r["planned_date"] for r in rows]
    # Each anniversary; the anniversary at expiry falls on the last day of cover.
    assert dates == [f"{2026 + y}-03-15" for y in range(1, years)] + [f"{2026 + years}-03-14"]


def test_two_visits_per_year_and_leap_year():
    rows = service_schedule("2028-02-29", 2, None, 2)
    assert [r["planned_date"] for r in rows] == ["2028-08-29", "2029-02-28", "2029-08-29", "2030-02-27"]


def test_multi_site_and_approved_dates_and_merge_preserves_history():
    ag = {"start_date": "2026-01-01", "asset_register": [{"id": "a", "annual": 1, "site_id": "s1"},
                                                         {"id": "b", "annual": 1, "site_id": "s2"}]}
    planned = plan_obligations("c1", ag, service_schedule("2026-01-01", 1, None, 2))
    assert len(planned) == 4 and {p["site_id"] for p in planned} == {"s1", "s2"}
    assert all(p["equipment_ids"] == (["a"] if p["site_id"] == "s1" else ["b"]) for p in planned)
    custom = plan_obligations("c1", {**ag, "service_dates": ["2026-06-10", "2027-06-10"]}, [])
    assert sorted({p["planned_date"] for p in custom}) == ["2026-06-10", "2027-06-10"]
    done = {**planned[0], "status": "completed", "completion": {"case_id": "x"}, "case_id": "x"}
    merged = merge_obligations("c1", [done] + planned[1:], planned)
    assert len(merged) == 4 and next(v for v in merged if v["obligation_id"] == done["obligation_id"])["status"] == "completed"
    assert plan_obligations("c1", ag, service_schedule("2026-01-01", 1, None, 2))[0]["obligation_id"] == planned[0]["obligation_id"]


# ───────────────────────────── core end-to-end acceptance

def test_end_to_end_contract_to_completion():
    h, mgr = _crm("cm-test-coord"), _crm("cm-test-asm")
    assets = [(f"{T}eq1", S1), (f"{T}eq2", S1), (f"{T}eq3", S1)]
    cid = _activate(f"{T}q1", "2025-11-01", 2, 1, assets)
    bills_before = mdb.crm2_afs_billing.find_one({"contract_id": cid})["invoices"]

    # STEP 1 — correct obligations (first anniversary, then within cover).
    vs = _visits(cid)
    assert [v["planned_date"] for v in vs] == ["2026-11-01", "2027-10-31"]
    assert all(v["obligation_id"] and v["site_id"] == S1 and len(v["equipment_ids"]) == 3 for v in vs)
    o1, o2 = vs[0]["obligation_id"], vs[1]["obligation_id"]

    # STEP 2 — next outstanding visit + coordinator task.
    svc = _plan(h, cid)
    assert svc["next_due"] == "2026-11-01" and svc["next_due_overdue"]
    book_task = _open(f"svc:{o1}:book")
    assert len(book_task) == 1 and book_task[0]["owner_id"] == "cm-test-coord"
    assert not _open(f"svc:{o2}:book")

    # A reactive repair at the same site never fulfils the PPM.
    mdb.svc_cases.insert_one({"id": f"{T}repair", "organization_id": OP, "reference": "P3-R1", "case_type": "repair",
                              "site_id": S1, "equipment_ids": [f"{T}eq1"], "status": "new", "created_at": "2026-11-02"})
    _close(f"{T}repair", serviced=[f"{T}eq1", f"{T}eq2", f"{T}eq3"])
    _plan(h, cid)
    assert not _visits(cid)[0].get("case_id") and _visits(cid)[0]["status"] == "planned"

    # STEP 3 — book through Service Desk; double-clicks / concurrency create one job.
    body = {"scheduled_date": "2026-12-03", "engineer_id": f"{T}eng"}
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(lambda _: requests.post(f"{AFS}/contracts/{cid}/obligations/{o1}/book", headers=h, json=body), range(5)))
    assert all(r.status_code in (200, 409) for r in res), [r.text for r in res]
    assert mdb.svc_cases.count_documents({"contract_obligation_id": o1}) == 1
    case = mdb.svc_cases.find_one({"contract_obligation_id": o1})
    assert case["case_type"] == "ppm" and case["assigned_engineer_name"] == "Erin Engineer" and case["contract_id"] == cid
    assert requests.post(f"{AFS}/contracts/{cid}/obligations/{o1}/book", headers=h, json=body).json()["existing"]

    # STEP 4 — Contract Management shows booking date + engineer; booking task closes.
    rows = requests.get(f"{AFS}/service-planner", headers=h, params={"q": "P3 Leisure"}).json()["rows"]
    r1 = next(r for r in rows if r["obligation_id"] == o1)
    assert (r1["bucket"], r1["booking_date"], r1["engineer"]) == ("booked", "2026-12-03", "Erin Engineer")
    assert not _open(f"svc:{o1}:book")
    mdb.svc_cases.update_one({"id": case["id"]}, {"$set": {"assigned_engineer_name": "Ray Engineer",
                                                           "scheduled_at": "2026-12-05T09:00:00+00:00"}})
    r1 = next(r for r in requests.get(f"{AFS}/service-planner", headers=h).json()["rows"] if r["obligation_id"] == o1)
    assert (r1["booking_date"], r1["engineer"]) == ("2026-12-05", "Ray Engineer")

    # Cancel without replacement → back to needing a booking; replacement re-uses the obligation.
    mdb.svc_cases.update_one({"id": case["id"]}, {"$set": {"status": "rejected"}})
    _plan(h, cid)
    v1 = _visits(cid)[0]
    assert v1["status"] == "planned" and not v1.get("case_id") and len(_open(f"svc:{o1}:cancelled")) == 1
    r = requests.post(f"{AFS}/contracts/{cid}/obligations/{o1}/book", headers=h, json=body)
    assert r.status_code == 200 and not r.json()["existing"]
    case_id = r.json()["case_id"]
    _plan(h, cid)
    assert len(_visits(cid)) == 2 and not _open(f"svc:{o1}:cancelled")

    # STEP 5/6 — partial service does not complete the site obligation.
    _close(case_id, serviced=[f"{T}eq1", f"{T}eq2"])
    _plan(h, cid)
    v1 = _visits(cid)[0]
    assert v1["status"] == "booked" and v1["review_reason"] == "partial" and len(_open(f"svc:{o1}:review")) == 1
    # Missing engineer report also blocks completion.
    _close(case_id, serviced=[f"{T}eq1", f"{T}eq2", f"{T}eq3"], report=False)
    _plan(h, cid)
    assert _visits(cid)[0]["review_reason"] == "report_missing"

    # STEP 7/8 — verified completion closes obligation + tasks; actual date kept.
    _close(case_id, serviced=[f"{T}eq1", f"{T}eq2", f"{T}eq3"])
    svc = _plan(h, cid)
    v1 = _visits(cid)[0]
    assert v1["status"] == "completed" and v1["completion"]["completed_date"] == "2026-11-20"
    assert v1["completion"]["case_id"] == case_id and v1["completion"]["report"]
    assert not _open(f"svc:{o1}:review") and not _open(f"svc:{o1}:book")

    # STEP 9 — the next obligation is still correctly planned.
    assert svc["next_due"] == "2027-10-31" and _visits(cid)[1]["status"] == "planned"

    # STEP 10 — repeated Sicon/completion events are idempotent; Sicon's actual date wins.
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"sicon_completed_at": "2026-11-19T10:00:00"}})
    for _ in range(3):
        _plan(h, cid)
        requests.get(f"{AFS}/service-planner", headers=h)
    v1 = _visits(cid)[0]
    assert v1["completion"]["completed_date"] == "2026-11-19" and v1["completion"]["date_source"] == "sicon"
    assert len(_visits(cid)) == 2 and mdb.svc_cases.count_documents({"contract_obligation_id": o1, "status": {"$ne": "rejected"}}) == 1
    assert sum(1 for e in v1["history"] if e["event"] == "completed") == 1
    assert mdb.crm2_activities.count_documents({"dedupe_key": f"svc:{o1}:book"}) == 1

    # Reopened case → back to booked with audit; closing again restores completion.
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"status": "on_site"}})
    _plan(h, cid)
    v1 = _visits(cid)[0]
    assert v1["status"] == "booked" and v1["completion_history"] and any(e["event"] == "reopened" for e in v1["history"])
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"status": "closed"}})
    _plan(h, cid)
    assert _visits(cid)[0]["status"] == "completed"
    assert mdb.svc_cases.find_one({"id": case_id})["engineer_report"]  # evidence never erased

    # Billing schedule untouched by service planning.
    assert mdb.crm2_afs_billing.find_one({"contract_id": cid})["invoices"] == bills_before

    # Automatic annual equipment PPM does not duplicate contract cover.
    from routes.svc.ppm_calendar import ensure_annual_ppm
    covered = mdb.equipment.find_one({"id": f"{T}eq1"}, {"_id": 0})
    free = mdb.equipment.find_one({"id": f"{T}eq4"}, {"_id": 0})
    async def both():
        return await ensure_annual_ppm(covered), await ensure_annual_ppm(free)
    assert asyncio.run(both()) == (False, True)  # covered skipped; unrelated PPM still created

    # Permissions — finance can read, not book; coordinator cannot approve reviews.
    fin = _crm("cm-test-fin")
    assert requests.get(f"{AFS}/service-planner", headers=fin).status_code == 200
    assert requests.post(f"{AFS}/contracts/{cid}/obligations/{o2}/book", headers=fin, json=body).status_code == 403
    assert requests.post(f"{AFS}/contracts/{cid}/obligations/{o2}/review", headers=h,
                         json={"action": "exclude", "note": "x"}).status_code == 403
    assert requests.get(f"{AFS}/service-planner", headers=_crm("cm-test-sales")).status_code in (200, 403)
    _ = mgr


# ───────────────────────────── historical reconciliation (multi-site)

def test_historical_reconciliation_preview_and_review():
    h, mgr = _crm("cm-test-coord"), _crm("cm-test-asm")
    mdb.ppm_schedules.delete_many({"equipment_id": f"{T}eq4"})
    mdb.equipment.update_one({"id": f"{T}eq4"}, {"$unset": {"contract_cover": ""}})
    hist = [
        # S2 — canonical (covered equipment) completed visit near year-1 obligation.
        {"id": f"{T}hA", "reference": "P3-HA", "site_id": S2, "equipment_ids": [f"{T}eq5"], "serviced": [f"{T}eq5"],
         "done": "2025-06-03"},
        # S1 — two site-only PPMs in the same window → ambiguous.
        {"id": f"{T}hB", "reference": "P3-HB", "site_id": S1, "equipment_ids": [], "serviced": [f"{T}eq4"], "done": "2025-05-28"},
        {"id": f"{T}hC", "reference": "P3-HC", "site_id": S1, "equipment_ids": [], "serviced": [], "done": "2025-06-20"},
    ]
    for x in hist:
        mdb.svc_cases.insert_one({"id": x["id"], "organization_id": OP, "reference": x["reference"], "case_type": "ppm",
                                  "site_id": x["site_id"], "equipment_ids": x["equipment_ids"], "status": "new",
                                  "created_at": "2026-11-01T00:00:00+00:00", "scheduled_at": f"{x['done']}T09:00:00+00:00"})
        _close(x["id"], done=x["done"], serviced=x["serviced"])
    cid = _activate(f"{T}q2", "2024-06-01", 3, 1, [(f"{T}eq4", S1), (f"{T}eq5", S2)],
                    override="Separate fictional estate contract for reconciliation test")
    assert len(_visits(cid)) == 6  # 3 years × 2 sites

    # Preview changes nothing.
    rep = requests.get(f"{AFS}/contracts/{cid}/service-reconciliation", headers=h).json()
    assert [m["case_id"] for m in rep["matched_completed"]] == [f"{T}hA"]
    assert len(rep["ambiguous"]) == 1 and {c["case_id"] for c in rep["ambiguous"][0]["candidates"]} == {f"{T}hB", f"{T}hC"}
    assert not mdb.svc_cases.find_one({"id": f"{T}hA"}).get("contract_obligation_id")

    # Live sync links only the canonical match, keeps the real completion date, no new case.
    n_cases = mdb.svc_cases.count_documents({"site_id": {"$in": [S1, S2]}})
    _plan(h, cid)
    vs = _visits(cid)
    s2y1 = next(v for v in vs if v["site_id"] == S2 and v["year"] == 1)
    s1y1 = next(v for v in vs if v["site_id"] == S1 and v["year"] == 1)
    assert s2y1["status"] == "completed" and s2y1["completion"]["completed_date"] == "2025-06-03"
    assert s1y1["status"] == "planned" and s1y1["review_reason"] == "ambiguous_match"
    assert len(_open(f"svc:{s1y1['obligation_id']}:review")) == 1
    assert mdb.svc_cases.count_documents({"site_id": {"$in": [S1, S2]}}) == n_cases

    # Coordinator can't approve; manager links B → completed; C stays independent.
    url = f"{AFS}/contracts/{cid}/obligations/{s1y1['obligation_id']}/review"
    assert requests.post(url, headers=h, json={"action": "link", "case_id": f"{T}hB"}).status_code == 403
    r = requests.post(url, headers=mgr, json={"action": "link", "case_id": f"{T}hB", "note": "Confirmed with engineer"})
    assert r.status_code == 200, r.text
    assert r.json()["visit"]["status"] == "completed"
    assert not _open(f"svc:{s1y1['obligation_id']}:review")
    assert not mdb.svc_cases.find_one({"id": f"{T}hC"}).get("contract_obligation_id")
    # Cross-site link refused.
    s2y2 = next(v for v in vs if v["site_id"] == S2 and v["year"] == 2)
    assert requests.post(f"{AFS}/contracts/{cid}/obligations/{s2y2['obligation_id']}/review", headers=mgr,
                         json={"action": "link", "case_id": f"{T}hC"}).status_code == 400
    # Overdue older visits stay visible even with a later booking.
    s1y2 = next(v for v in vs if v["site_id"] == S1 and v["year"] == 2)
    assert requests.post(f"{AFS}/contracts/{cid}/obligations/{next(v for v in vs if v['site_id'] == S1 and v['year'] == 3)['obligation_id']}/book",
                         headers=h, json={"scheduled_date": "2027-05-20"}).status_code == 200
    rows = {r["obligation_id"]: r for r in requests.get(f"{AFS}/service-planner", headers=h).json()["rows"]}
    assert rows[s1y2["obligation_id"]]["bucket"] == "overdue"
    assert _plan(h, cid)["next_due"] == s1y2["planned_date"]
    # Daily checks do not duplicate tasks.
    for _ in range(2):
        requests.get(f"{AFS}/service-planner", headers=h)
    assert mdb.crm2_activities.count_documents({"dedupe_key": f"svc:{s1y2['obligation_id']}:book"}) == 1
