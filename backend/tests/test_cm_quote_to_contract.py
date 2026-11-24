"""Phase C — accepted maintenance quote → pre-filled agreement → signature →
activation → service plan + billing, with one Action Centre item per stage.

Fictional data only (prefix ``cm_qc_``); everything is removed afterwards.
"""
import os
import subprocess

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_qc_"
AFS = f"{API}/crm/v2/aftersales"


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _quote(qid, **kw):
    doc = {"id": qid, "organization_id": OP, "company_id": f"{T}co", "quote_number": qid.upper(),
           "status": "sent", "contract_type": "qc_plan", "linked_organization_id": f"{T}cust",
           "visits_per_year": 4, "preferred_payment": "quarterly", "requested_start_date": "2026-01-31",
           "source_sales_quote_id": f"{T}sale",
           "summary": {"final_annual": 1200.0, "term_years": 2, "vat_pct": 20},
           "grouped_lines": [{"model": "TM1", "qty": 2, "serials": ["S1", "S2"], "annual_total": 1200.0}],
           "asset_register": [{"id": f"{T}eq1", "annual": 600}, {"id": f"{T}eq2", "annual": 600}]}
    doc.update(kw)
    mdb.crm2_afs_quotes.insert_one(doc)


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)
    mdb.organizations.insert_one({"id": f"{T}cust", "name": "QC Leisure Ltd"})
    mdb.crm2_companies.insert_one({"id": f"{T}co", "organization_id": OP, "name": "QC Leisure",
                                   "legal_name": "QC Leisure Ltd", "linked_organization_id": f"{T}cust",
                                   "coordinator_id": "cm-test-coord", "coordinator_name": "Casey Coordinator"})
    mdb.sites.insert_one({"id": f"{T}site", "organization_id": f"{T}cust", "name": "Main Gym"})
    for i in (1, 2):
        mdb.equipment.insert_one({"id": f"{T}eq{i}", "organization_id": f"{T}cust", "name": "Treadmill", "serial_number": f"S{i}"})
    yield
    rx = {"$regex": f"^{T}"}
    for coll in ("crm2_contracts", "crm2_companies", "organizations", "sites", "equipment", "crm2_afs_quotes",
                 "crm2_afs_agreements", "crm2_afs_service_schedules", "crm2_afs_billing", "crm2_afs_finance_sync"):
        mdb[coll].delete_many({"$or": [{"id": rx}, {"organization_id": rx}, {"company_id": rx}, {"quote_id": rx}]})
    ag_ids = [a["id"] for a in mdb.crm2_afs_agreements.find({"quote_id": rx}, {"id": 1})]
    for coll in ("crm2_contracts", "crm2_afs_service_schedules", "crm2_afs_billing", "crm2_afs_finance_sync"):
        mdb[coll].delete_many({"$or": [{"source_agreement_id": {"$in": ag_ids}}, {"agreement_id": {"$in": ag_ids}},
                                       {"company_id": f"{T}co"}]})
    mdb.crm2_afs_agreements.delete_many({"quote_id": rx})
    mdb.crm2_activities.delete_many({"$or": [{"company_id": rx}, {"quote_id": rx}]})


def _open(key):
    return list(mdb.crm2_activities.find({"organization_id": OP, "dedupe_key": key, "status": "open"}))


def test_accepted_quote_flows_to_active_contract_with_plan_and_billing():
    _quote(f"{T}q1")
    h = _crm("cm-test-coord")
    r = requests.post(f"{AFS}/quotes/{T}q1/accept", headers=h, json={})
    assert r.status_code == 200, r.text
    aid = r.json()["agreement_id"]
    # Accepting again (or the portal replaying) never creates a second agreement.
    assert requests.post(f"{AFS}/quotes/{T}q1/accept", headers=h, json={}).json()["agreement_id"] == aid
    assert mdb.crm2_afs_agreements.count_documents({"quote_id": f"{T}q1"}) == 1
    assert mdb.crm2_afs_quotes.find_one({"id": f"{T}q1"})["agreement_id"] == aid

    ag = requests.get(f"{AFS}/agreements/{aid}", headers=h).json()
    assert ag["status"] == "draft" and ag["health"]["ready"], ag["health"]
    assert (ag["start_date"], ag["end_date"]) == ("2026-01-31", "2028-01-30")
    assert ag["visits_per_year"] == 4 and ag["billing_frequency"] == "quarterly"
    assert ag["source_sales_quote_id"] == f"{T}sale"
    assert ag["schedules"]["schedule1_parties"]["customer"]["legal_name"] == "QC Leisure Ltd"
    task = _open(f"cm:agreement-complete:{aid}")
    assert len(task) == 1 and task[0]["owner_id"] == "cm-test-coord"

    assert requests.post(f"{AFS}/agreements/{aid}/generate", headers=h).status_code == 200
    assert not _open(f"cm:agreement-complete:{aid}") and len(_open(f"cm:agreement-sign:{aid}")) == 1
    assert requests.patch(f"{AFS}/agreements/{aid}", headers=h, json={"start_date": "2026-03-01"}).status_code == 400

    sig = {"signatory_name": "Alex QC", "position": "Director", "email": "alex@qc.example", "authority_confirmed": True}
    assert requests.post(f"{AFS}/agreements/{aid}/sign", headers=h, json=sig).status_code == 200
    assert not _open(f"cm:agreement-sign:{aid}") and len(_open(f"cm:agreement-activate:{aid}")) == 1

    r = requests.post(f"{AFS}/agreements/{aid}/activate", headers=h, json={})
    assert r.status_code == 200, r.text
    act = r.json()
    cid = act["contract_id"]
    assert not _open(f"cm:agreement-activate:{aid}")
    c = mdb.crm2_contracts.find_one({"id": cid})
    assert c["source_quote_id"] == f"{T}q1" and c["source_sales_quote_id"] == f"{T}sale" and c["status"] == "active"
    plan = requests.get(f"{AFS}/contracts/{cid}/schedules", headers=h).json()
    assert plan["service"]["required"] == 8  # 4 visits × 2 years
    due = [i["due_date"] for i in plan["billing"]]
    assert len(due) == 8 and due[:3] == ["2026-01-31", "2026-04-30", "2026-07-31"]
    assert plan["billing"][0]["amount"] == 300.0
    assert plan["contract"]["sage_sync_status"] != "synced" or c.get("sage_reference")
    eq = mdb.equipment.find_one({"id": f"{T}eq1"})
    assert eq["contract_cover"]["contract_id"] == cid
    again = requests.post(f"{AFS}/agreements/{aid}/activate", headers=h, json={}).json()
    assert again["already_active"] and again["contract_id"] == cid
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": aid}) == 1


def test_draft_dates_and_visits_can_be_completed_on_the_agreement():
    _quote(f"{T}q2", requested_start_date=None, preferred_payment=None, status="accepted")
    h = _crm("cm-test-coord")
    aid = requests.post(f"{AFS}/quotes/{T}q2/accept", headers=h, json={}).json()["agreement_id"]
    ag = requests.get(f"{AFS}/agreements/{aid}", headers=h).json()
    assert not ag.get("start_date") and "Start / end dates not set" in ag["health"]["reasons"]
    assert "Start / end dates not set" in _open(f"cm:agreement-complete:{aid}")[0]["body"]
    assert requests.post(f"{AFS}/agreements/{aid}/generate", headers=h).status_code == 400
    assert requests.patch(f"{AFS}/agreements/{aid}", headers=h, json={"start_date": "bad"}).status_code == 400
    assert requests.patch(f"{AFS}/agreements/{aid}", headers=h, json={"visits_per_year": 0}).status_code == 400
    r = requests.patch(f"{AFS}/agreements/{aid}", headers=h, json={"start_date": "2028-02-29", "visits_per_year": 3})
    assert r.status_code == 200
    ag = r.json()
    assert (ag["start_date"], ag["end_date"], ag["visits_per_year"]) == ("2028-02-29", "2030-02-27", 3)
    assert ag["health"]["ready"] and "Start / end" not in _open(f"cm:agreement-complete:{aid}")[0]["body"]


def test_acceptance_guards_and_permissions():
    _quote(f"{T}q3", unpriced_count=2)
    _quote(f"{T}q4", status="declined")
    assert requests.post(f"{AFS}/quotes/{T}q3/accept", headers=_crm("cm-test-coord"), json={}).status_code == 400
    assert requests.post(f"{AFS}/quotes/{T}q4/accept", headers=_crm("cm-test-coord"), json={}).status_code == 400
    assert mdb.crm2_afs_agreements.count_documents({"quote_id": {"$in": [f"{T}q3", f"{T}q4"]}}) == 0
    assert requests.post(f"{AFS}/quotes/{T}q3/accept", headers=_crm("cm-test-fin"), json={}).status_code == 403
