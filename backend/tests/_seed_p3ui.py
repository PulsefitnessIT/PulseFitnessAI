"""Seed/cleanup fictional TEST_p3ui_ data for Phase 3 Service Planner UI testing.
Usage: PYTHONPATH=. python tests/_seed_p3ui.py seed|cleanup|complete|partial
"""
import json
import os
import sys

import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
AFS = f"{API}/crm/v2/aftersales"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "TEST_p3ui_"
CUST, S1, S2 = f"{T}cust", f"{T}site1", f"{T}site2"


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def cleanup():
    rx = {"$regex": f"^{T}"}
    ag_ids = [a["id"] for a in mdb.crm2_afs_agreements.find({"quote_id": rx}, {"id": 1})]
    cids = [c["id"] for c in mdb.crm2_contracts.find({"$or": [{"source_agreement_id": {"$in": ag_ids}}, {"company_id": rx}]}, {"id": 1})]
    case_ids = [c["id"] for c in mdb.svc_cases.find({"$or": [{"site_id": rx}, {"contract_id": {"$in": cids}}, {"id": rx}]}, {"id": 1})]
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
    print("cleaned", len(cids), "contracts", len(case_ids), "cases")


def _activate(qid, start, term, visits, assets, override=None):
    mdb.crm2_afs_quotes.insert_one({
        "id": qid, "organization_id": OP, "company_id": f"{T}co", "quote_number": qid.upper(), "status": "sent",
        "contract_type": "p3_plan", "linked_organization_id": CUST, "visits_per_year": visits,
        "preferred_payment": "annual", "requested_start_date": start,
        "summary": {"final_annual": 300.0 * len(assets), "term_years": term, "vat_pct": 20},
        "grouped_lines": [{"model": "TM1", "qty": len(assets), "annual_total": 300.0 * len(assets),
                           "serials": ["P3UI" + a[-1] for a, _ in assets]}],
        "asset_register": [{"id": a, "annual": 300, "site_id": s} for a, s in assets]})
    h = _crm("cm-test-coord")
    aid = requests.post(f"{AFS}/quotes/{qid}/accept", headers=h, json={}).json()["agreement_id"]
    assert requests.post(f"{AFS}/agreements/{aid}/generate", headers=h).status_code == 200
    sig = {"signatory_name": "Pat Test", "position": "Director", "email": "pat@p3ui.example", "authority_confirmed": True}
    assert requests.post(f"{AFS}/agreements/{aid}/sign", headers=h, json=sig).status_code == 200
    r = requests.post(f"{AFS}/agreements/{aid}/activate", headers=_crm("cm-test-asm") if override else h,
                      json={"conflict_review_note": override} if override else {})
    assert r.status_code == 200, r.text
    return r.json()["contract_id"]


def seed():
    cleanup()
    mdb.organizations.insert_one({"id": CUST, "name": "TEST_p3ui Leisure Ltd"})
    mdb.crm2_companies.insert_one({"id": f"{T}co", "organization_id": OP, "name": "TEST_p3ui Leisure",
                                   "legal_name": "TEST_p3ui Leisure Ltd", "linked_organization_id": CUST,
                                   "coordinator_id": "cm-test-coord", "coordinator_name": "Casey Coordinator"})
    mdb.sites.insert_many([{"id": S1, "organization_id": CUST, "name": "TEST North Gym", "postcode": "N1 1AA"},
                           {"id": S2, "organization_id": CUST, "name": "TEST South Gym", "postcode": "S1 1AA"}])
    for i, site in ((1, S1), (2, S1), (3, S1), (4, S2)):
        mdb.equipment.insert_one({"id": f"{T}eq{i}", "organization_id": CUST, "site_id": site, "name": "Treadmill",
                                  "serial_number": f"P3UI{i}", "status": "active", "install_date": "2024-01-10"})
    mdb.svc_engineers.insert_one({"id": f"{T}eng", "organization_id": OP, "full_name": "Erin Engineer", "status": "active"})
    cid = _activate(f"{T}q1", "2025-11-01", 2, 1, [(f"{T}eq1", S1), (f"{T}eq2", S1), (f"{T}eq3", S1)])
    # Contract 2 — site S2 with two ambiguous historical PPMs → review candidates
    for cid_, ref, done in ((f"{T}hB", "P3UI-HB", "2025-05-28"), (f"{T}hC", "P3UI-HC", "2025-06-20")):
        mdb.svc_cases.insert_one({"id": cid_, "organization_id": OP, "reference": ref, "case_type": "ppm", "site_id": S2,
                                  "equipment_ids": [], "status": "closed", "created_at": "2025-05-01T00:00:00+00:00",
                                  "scheduled_at": f"{done}T09:00:00+00:00", "completed_at": f"{done}T15:00:00+00:00",
                                  "engineer_report": {"summary": "PPM done"}})
    cid2 = _activate(f"{T}q2", "2024-06-01", 3, 1, [(f"{T}eq4", S2)],
                     override="TEST_p3ui separate estate contract for review UI test")
    vis = mdb.crm2_afs_service_schedules.find_one({"contract_id": cid})["visits"]
    print(json.dumps({"cid": cid, "cid2": cid2, "o1": vis[0]["obligation_id"], "dates": [v["planned_date"] for v in vis]}))


def close(machines):
    cid = mdb.crm2_contracts.find_one({"company_id": f"{T}co", "source_agreement_id": {"$exists": True}},
                                      sort=[("created_at", 1)])["id"]
    sched = mdb.crm2_afs_service_schedules.find_one({"contract_id": cid})
    v = next(x for x in sched["visits"] if x.get("case_id"))
    case_id = v["case_id"]
    mdb.svc_work_visit_machines.delete_many({"case_id": case_id})
    for i, eq in enumerate(machines):
        mdb.svc_work_visit_machines.insert_one({"case_id": case_id, "asset_id": eq, "serviced": True, "order_index": i})
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"status": "closed", "completed_at": "2026-11-20T15:00:00+00:00",
                                                        "engineer_report": {"summary": "PPM done"}}})
    print("closed", case_id, machines)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "seed":
        seed()
    elif cmd == "cleanup":
        cleanup()
    elif cmd == "complete":
        close([f"{T}eq1", f"{T}eq2", f"{T}eq3"])
    elif cmd == "partial":
        close([f"{T}eq1", f"{T}eq2"])
