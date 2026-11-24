"""Phase 3 Stage 1 — Build Quote apply: concurrency + serial-less machines are never
merged on model/site alone. Imports are seeded directly (no AI extraction).
Fictional data only (prefix ``cm_p3i_``), removed afterwards."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
AFS = f"{API}/crm/v2/aftersales"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_p3i_"
CUST, SITE = f"{T}cust", f"{T}site"


def _h():
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token('cm-test-coord')}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cleanup():
    rx = {"$regex": f"^{T}"}
    eq_ids = [e["id"] for e in mdb.equipment.find({"organization_id": CUST}, {"id": 1})]
    mdb.crm2_afs_equipment_claims.delete_many({"equipment_id": {"$in": eq_ids}})
    mdb.crm2_afs_equipment_claims.delete_many({"key": {"$regex": f"^{CUST}:"}})
    mdb.equipment.delete_many({"organization_id": CUST})
    mdb.crm2_activities.delete_many({"company_id": f"{T}co"})
    for coll in ("crm2_afs_quote_imports", "crm2_companies", "sites", "organizations"):
        mdb[coll].delete_many({"id": rx})


@pytest.fixture(scope="module", autouse=True)
def setup():
    _cleanup()
    mdb.organizations.insert_one({"id": CUST, "name": "P3i Leisure"})
    mdb.sites.insert_one({"id": SITE, "organization_id": CUST, "name": "P3i Gym"})
    mdb.crm2_companies.insert_one({"id": f"{T}co", "organization_id": OP, "name": "P3i Leisure", "linked_organization_id": CUST})
    yield
    _cleanup()


def _imp(iid, doc_type, lines):
    mdb.crm2_afs_quote_imports.insert_one({
        "id": iid, "organization_id": OP, "company_id": f"{T}co", "doc_type": doc_type, "sha256": iid,
        "filename": f"{iid}.pdf", "status": "review", "extracted": {"document_ref": iid.upper()},
        "lines": [{"line_no": i + 1, "decision": "accepted", "flags": [], "model": m, "quantity": q, "serials": s,
                   "matched": {"config_id": "x", "model": m}} for i, (m, q, s) in enumerate(lines)]})


def _apply(iid, decisions=()):
    return requests.post(f"{AFS}/build-quote/imports/{iid}/apply", headers=_h(),
                         json={"site_id": SITE, "decisions": list(decisions)}, timeout=30)


def test_concurrent_apply_creates_each_machine_once():
    _imp(f"{T}inv", "sales_invoice", [("P3i Run", 2, []), ("P3i Bike", 1, ["P3I-B-1"])])
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda _: _apply(f"{T}inv"), range(6)))
    assert all(r.status_code in (200, 409) for r in res), [r.text for r in res]
    assert any(r.status_code == 200 for r in res)
    assert mdb.equipment.count_documents({"organization_id": CUST}) == 3
    again = _apply(f"{T}inv").json()
    assert again["equipment_created"] == 0 and len(again["asset_ids"]) == 3


def test_serialless_identical_machines_are_not_silently_merged():
    # Delivery note for the same model at the same site: separate provisional records + review.
    _imp(f"{T}dn", "delivery_note", [("P3i Run", 2, [])])
    r = _apply(f"{T}dn").json()
    assert r["equipment_created"] == 2 and r["equipment_reused"] == 0
    assert r["possible_duplicates"] and len(r["possible_duplicates"][0]["candidates"]) == 2
    assert mdb.crm2_activities.count_documents({"dedupe_key": f"import:{T}dn:serialless", "status": "open"}) == 1
    assert mdb.equipment.count_documents({"organization_id": CUST, "model": "P3i Run"}) == 4

    # Coordinator confirms which existing units a later document refers to → reused, not duplicated.
    first = [e["id"] for e in mdb.equipment.find({"organization_id": CUST, "source_import_line": {"$regex": f"^{T}inv:1:"}})]
    _imp(f"{T}dn2", "delivery_note", [("P3i Run", 2, [])])
    r = _apply(f"{T}dn2", [{"line_no": 1, "decision": "accepted", "reuse_equipment_ids": first}]).json()
    assert r["equipment_created"] == 0 and r["equipment_reused"] == 2 and sorted(r["asset_ids"]) == sorted(first)
    assert all(e["lifecycle_stage"] == "delivered" for e in mdb.equipment.find({"id": {"$in": first}}))
    assert mdb.equipment.count_documents({"organization_id": CUST, "model": "P3i Run"}) == 4

    # A verified/active machine can't be claimed as a pending serial-less unit.
    mdb.equipment.insert_one({"id": f"{T}active", "organization_id": CUST, "site_id": SITE, "model": "P3i Run",
                              "serial_number": "", "status": "active", "lifecycle_stage": "installed"})
    _imp(f"{T}dn3", "delivery_note", [("P3i Run", 1, [])])
    bad = _apply(f"{T}dn3", [{"line_no": 1, "decision": "accepted", "reuse_equipment_ids": [f"{T}active"]}])
    assert bad.status_code == 400


def test_two_documents_with_same_serial_applied_together_create_one_machine():
    _imp(f"{T}a", "sales_invoice", [("P3i Row", 1, ["P3I-R-9"])])
    _imp(f"{T}b", "delivery_note", [("P3i Row", 1, ["P3I-R-9"])])
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(_apply, [f"{T}a", f"{T}b"]))
    assert all(r.status_code == 200 for r in res), [r.text for r in res]
    assert mdb.equipment.count_documents({"organization_id": CUST, "serial_number": "P3I-R-9"}) == 1
