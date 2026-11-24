"""Maintenance Master bridge — fictional multi-customer workbook end to end.
Prefix ``mmt_`` / contract numbers ``MMT-``; everything removed afterwards."""
import io
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import openpyxl
import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token
from utils.mm_import import FIELDS

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
MM = f"{API}/crm/v2/aftersales/maintenance-master"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
HEAD = list(FIELDS)[:29]


def _h(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _row(name, acct, num, start, end, amount, freq="Annually", dd="No", rec=None, visits="1"):
    d = {"Customer / site": name, "Site account": acct, "Invoice account": acct, "Contract number": num,
         "Start date": start, "Expiry date": end, "Contract term": "3 Years", "Contract / warranty type": "Contract",
         "Services per year": visits, "Payment frequency": freq, "Contract amount (£)": amount,
         "Original amount (£)": amount, "Paid by Direct Debit": dd, "Invoice numbers": f"IN-{num}",
         "Last service recorded": "2026-02-13"}
    return [d.get(h) for h in HEAD] + ([rec] if rec else [])


def workbook(extra_amount=1500.0):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Maintenance Database"
    ws.append(HEAD)
    ws.append(_row("MMT Alpha Gym", "MMTA01 / 00990001 (Sage)", "MMT-1001", "2025-12-01", "2028-11-30", extra_amount, rec="MAIN-99001"))
    ws.append(_row("MMT Beta Leisure", "MMTB01", "MMT-1002", "2026-01-10", "2027-01-09", 900.0, freq="Monthly", dd="Yes", rec="MAIN-99002"))
    ws.append(_row("MMT Gamma Club", "MMTC01", "MMT-1003", "2026-03-01", "2029-02-28", 1200.0, rec="MAIN-99003"))
    ws.append(_row("MMT Gamma Club", "MMTC01", "MMT-1003", "2026-03-01", "2029-02-28", 1200.0, rec="MAIN-99004"))  # duplicate
    ws.append(_row("MMT Delta Fitness", "", "", "2026-02-01", None, None, rec="MAIN-99005"))  # missing info
    ws.append(_row("MMT Epsilon", "MMTE01", "MMT-1006", "2026-04-01", "2027-03-31", 700.0, rec="MAIN-99006"))
    ex = wb.create_sheet("Expired")
    ex.append(HEAD)
    ex.append(_row("MMT Alpha Gym", "MMTA01", "MMT-0901", "2022-12-01", "2025-11-30", 1400.0))
    sp = wb.create_sheet("Service Planner")
    sp.append(["Customer / site", "Contract number", "Latest service on record", "PPM completed - ENTER DATE",
               "Assigned engineer", "Sicon case reference", "Record ID (internal)"])
    sp.append(["MMT Alpha Gym", "MMT-1001", "2026-02-13", None, "Ryan", "SC-555", "MAIN-99001"])
    sc = wb.create_sheet("Sicon Contracts")
    sc.append(["Customer / site", "Contract number", "Sicon contract ID", "Sicon line ID"])
    sc.append(["MMT Alpha Gym", "MMT-1001", "7700001", "7700002"])
    mod = wb.create_sheet("MOD")
    mod.append(HEAD)
    mod.append(_row("MMT Barracks", "MMTM01", "MMT-M1", "2025-01-01", "2028-12-31", 500.0))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _cleanup():
    cids = [c["id"] for c in mdb.crm2_contracts.find({"$or": [{"contract_number": {"$regex": "^MMT-"}},
                                                               {"company_name": {"$regex": "^MMT "}},
                                                               {"mm_record_key": {"$regex": "^(MAIN-990|Expired\\|MMT-)"}}]}, {"id": 1})]
    mdb.crm2_contract_changes.delete_many({"contract_id": {"$in": cids}})
    mdb.crm2_sicon_contract_queue.delete_many({"contract_id": {"$in": cids}})
    mdb.crm2_contracts.delete_many({"id": {"$in": cids}})
    mdb.crm2_companies.delete_many({"$or": [{"id": {"$regex": "^mmt_"}}, {"name": {"$regex": "^MMT "}}]})
    ups = [u["id"] for u in mdb.crm2_mm_uploads.find({"filename": {"$regex": "^mmt_"}}, {"id": 1})]
    mdb.crm2_mm_rows.delete_many({"upload_id": {"$in": ups}})
    for f in mdb["mm_workbooks.files"].find({"metadata.upload_id": {"$in": ups}}, {"_id": 1}):
        mdb["mm_workbooks.chunks"].delete_many({"files_id": f["_id"]})
        mdb["mm_workbooks.files"].delete_one({"_id": f["_id"]})
    mdb.crm2_mm_uploads.delete_many({"id": {"$in": ups}})
    mdb.crm2_mm_cutover.delete_many({"filename": {"$regex": "^mmt_"}})


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)
    _cleanup()
    mdb.crm2_companies.insert_many([
        {"id": "mmt_alpha", "organization_id": OP, "name": "MMT Alpha Gym", "sage_account": "00990001"},
        {"id": "mmt_eps1", "organization_id": OP, "name": "MMT Epsilon"},  # name-only → review
    ])
    yield
    _cleanup()


def _upload(name, blob, h, chunk=40_000):
    total = (len(blob) + chunk - 1) // chunk
    uid = requests.post(f"{MM}/uploads", headers=h, json={"filename": name, "size": len(blob), "total_chunks": total}).json()["upload_id"]
    for n in range(total):
        assert requests.put(f"{MM}/uploads/{uid}/chunks/{n}", headers={**h, "Content-Type": "application/octet-stream"},
                            data=blob[n * chunk:(n + 1) * chunk]).status_code == 200
    assert requests.post(f"{MM}/uploads/{uid}/complete", headers=h).status_code == 200
    return _wait(uid, h, ("ready", "failed"))


def _wait(uid, h, states, t=60):
    for _ in range(t * 2):
        u = requests.get(f"{MM}/uploads/{uid}", headers=h).json()
        if u["state"] in states:
            return u
        time.sleep(0.5)
    raise AssertionError(u["state"])


def _rows(uid, h, cls=""):
    return requests.get(f"{MM}/uploads/{uid}/rows", headers=h, params={"cls": cls}).json()["rows"]


def test_full_interim_workflow():
    coord, mgr = _h("cm-test-coord"), _h("cm-test-asm")
    blob = workbook()
    u = _upload("mmt_master_v1.xlsx", blob, coord)
    assert u["state"] == "ready", u.get("error")
    import hashlib
    assert u["sha256"] == hashlib.sha256(blob).hexdigest()
    c = u["summary"]["counts"]
    # Expired Alpha row has only a name match (account ref differs) → review, never auto-merged.
    assert c["duplicate_overlap"] == 2 and c["missing_information"] == 1 and c["requires_review"] == 2
    assert c["new_contract"] == 2 and u["summary"]["held_mod"] == 1
    t = u["summary"]["totals"]["Maintenance Database"]
    assert t["rows"] == 6 and t["contract_amount"] == 1500 + 900 + 1200 + 1200 + 700
    # Coordinator can preview but not commit.
    assert requests.post(f"{MM}/uploads/{u['id']}/commit", headers=coord, json={}).status_code == 403
    # Interrupted commit (1 row), then retry — no duplicates.
    assert requests.post(f"{MM}/uploads/{u['id']}/commit", headers=mgr, json={"create_missing_customers": True, "limit": 1}).status_code == 200
    assert _wait(u["id"], mgr, ("partial", "committed"))["state"] == "partial"
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda _: requests.post(f"{MM}/uploads/{u['id']}/commit", headers=mgr,
                                                  json={"create_missing_customers": True}), range(3)))
    assert sorted(r.status_code for r in res).count(200) >= 1
    u = _wait(u["id"], mgr, ("partial", "committed"))
    alpha = mdb.crm2_contracts.find_one({"contract_number": "MMT-1001"})
    assert mdb.crm2_contracts.count_documents({"contract_number": "MMT-1001"}) == 1
    assert alpha["company_id"] == "mmt_alpha" and alpha["start_date"] == "2025-12-01" and alpha["annual_value"] == 1500
    assert alpha["mm_source"]["sheet"] == "Maintenance Database" and alpha["mm_source"]["row"] == 2
    assert alpha["sicon_contract_id"] == "7700001" and alpha["sicon_sync"]["state"] == "awaiting_sicon_matching" or alpha["sicon_sync"]["state"] in SYNC_OK
    assert alpha["mm_service_history"]["latest_service"] == "2026-02-13" and alpha["mm_service_history"]["engineer"] == "Ryan"
    beta = mdb.crm2_contracts.find_one({"contract_number": "MMT-1002"})
    assert beta["annual_value"] is None and beta["direct_debit"] == "Yes" and beta["mm"]["contract_amount"] == 900
    assert any("annual value" in e for e in beta["mm_exceptions"])
    assert mdb.crm2_companies.count_documents({"name": "MMT Beta Leisure"}) == 1
    assert mdb.crm2_contracts.count_documents({"contract_number": "MMT-1003"}) == 0  # duplicate held
    assert not mdb.crm2_contracts.find_one({"contract_number": "MMT-M1"})  # MOD held
    # No service, billing, email or Sicon side effects.
    assert not mdb.crm2_afs_service_schedules.find_one({"contract_id": alpha["id"]})
    assert not mdb.crm2_afs_billing.find_one({"contract_id": alpha["id"]})
    # Name-only Epsilon: coordinator links it to the existing customer, then commits.
    assert not mdb.crm2_contracts.find_one({"contract_number": "MMT-0901"})
    for r in _rows(u["id"], mgr, "requires_review"):
        cid_ = "mmt_eps1" if r["mapped"]["contract_number"] == "MMT-1006" else "mmt_alpha"
        assert requests.post(f"{MM}/uploads/{u['id']}/rows/{r['id']}/decision", headers=coord,
                             json={"action": "link_company", "company_id": cid_}).status_code == 200
    requests.post(f"{MM}/uploads/{u['id']}/commit", headers=mgr, json={"create_missing_customers": True})
    _wait(u["id"], mgr, ("partial", "committed"))
    assert mdb.crm2_contracts.find_one({"contract_number": "MMT-1006"})["company_id"] == "mmt_eps1"
    old = mdb.crm2_contracts.find_one({"contract_number": "MMT-0901"})
    assert old["status"] == "expired" and old["company_id"] == "mmt_alpha"

    # Edit with revision + audit; stale revision rejected (multi-user).
    r = requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                       json={"revision": 1, "changes": {"coordinator_name": "Casey Coordinator", "annual_value": 1600}, "reason": "RPI 2026"})
    assert r.status_code == 200 and sorted(r.json()["changed"]) == ["annual_value", "coordinator_name"]
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                          json={"revision": 1, "changes": {"comments": "x"}}).status_code == 409
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                          json={"revision": 2, "changes": {"sicon_contract_id": "1"}}).status_code == 403
    got = requests.get(f"{MM}/contracts/{alpha['id']}", headers=coord).json()
    assert got["contract"]["annual_value"] == 1600 and got["contract"]["revision"] == 2
    ch = {h["field"]: h for h in got["changes"]}
    assert ch["annual_value"]["old"] == 1500 and ch["annual_value"]["new"] == 1600 and ch["annual_value"]["by"]
    assert requests.post(f"{MM}/contracts/{alpha['id']}/notes", headers=coord, json={"text": "Called site"}).status_code == 200

    # Re-import a newer workbook that changes Alpha's amount: app edit kept, conflict flagged.
    u2 = _upload("mmt_master_v2.xlsx", workbook(extra_amount=1550.0), coord)
    a2 = next(r for r in _rows(u2["id"], mgr) if r["record_key"] == "MAIN-99001")
    assert a2["cls"] == "matched_differences" and "annual_value" in a2["conflicts"]
    requests.post(f"{MM}/uploads/{u2['id']}/commit", headers=mgr, json={})
    _wait(u2["id"], mgr, ("partial", "committed"))
    after = mdb.crm2_contracts.find_one({"id": alpha["id"]})
    assert after["annual_value"] == 1600 and "annual_value" in after["mm_conflicts"]
    assert mdb.crm2_contracts.count_documents({"contract_number": {"$regex": "^MMT-"}}) == 4  # 1001, 1002, 1006, 0901 (no duplicate created)

    # Deferred Sicon: queue is held, nothing sent; simulated reconciliation is idempotent.
    q = requests.post(f"{MM}/contracts/{alpha['id']}/sicon-queue", headers=mgr).json()
    assert q["state"] == "held_writes_disabled" and q["external_write_attempted"] is False
    assert requests.post(f"{MM}/contracts/{alpha['id']}/sicon-queue", headers=mgr).json()["id"] == q["id"]
    sim = {"matches": [{"contract_number": "MMT-1001", "sicon_contract_id": "7700001", "sicon_line_ids": ["7700002"]},
                       {"contract_number": "MMT-1002", "sicon_contract_id": "7700001"}]}
    dry = requests.post(f"{MM}/sicon-reconcile", headers=mgr, json=sim).json()
    assert dry["matched"] == ["MMT-1001"] and dry["conflict"] and dry["external_writes"] == 0
    requests.post(f"{MM}/sicon-reconcile", headers=mgr, json={**sim, "apply": True})
    assert requests.post(f"{MM}/sicon-reconcile", headers=mgr, json={**sim, "apply": True}).json()["already"] == ["MMT-1001"]
    assert mdb.crm2_contracts.find_one({"id": alpha["id"]})["sicon_sync"]["state"] == "ready_for_sync"
    assert mdb.crm2_contracts.count_documents({"contract_number": "MMT-1001"}) == 1

    # Exports: reports, current data, and the original-layout workbook with the edit applied.
    for path in (f"/uploads/{u['id']}/report?kind=reconciliation", f"/uploads/{u['id']}/report?kind=exceptions", "/export/current"):
        r = requests.get(f"{MM}{path}", headers=coord)
        assert r.status_code == 200 and openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames
    r = requests.get(f"{MM}/export/master", headers=coord, timeout=120)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Maintenance Database", "Expired", "Service Planner", "Sicon Contracts", "MOD"]
    hdr = [c.value for c in wb["Maintenance Database"][1]]
    assert wb["Maintenance Database"].cell(row=2, column=hdr.index("Contract amount (£)") + 1).value == 1550  # source row untouched
    assert wb["Maintenance Database"].cell(row=2, column=hdr.index("Contract number") + 1).value == "MMT-1001"
    # Original preserved byte-for-byte.
    assert requests.get(f"{MM}/uploads/{u['id']}/original", headers=coord).content == blob

    # Renewal draft from an imported contract keeps the contract reference and links back.
    from datetime import date, timedelta
    mdb.crm2_contracts.update_one({"id": alpha["id"]}, {"$set": {"end_date": (date.today() + timedelta(days=30)).isoformat()}})
    import asyncio
    from utils.cm_renewals import _create_draft
    rid = asyncio.run(_create_draft(OP, mdb.crm2_contracts.find_one({"id": alpha["id"]}, {"_id": 0}),
                                    {"new_start": "2029-01-01", "new_end": "2031-12-31", "new_value": 1648.0,
                                     "uplift_percent": 3, "uplift_status": "needs_approval", "uplift_basis": "test"}, "test"))
    ren = mdb.crm2_contracts.find_one({"id": rid})
    assert ren["contract_number"].startswith("MMT-1001/R") and ren["previous_contract_id"] == alpha["id"]
    assert ren["status"] == "renewal_pending_approval" and ren["renewed_from_mm_record_key"] == "MAIN-99001"
    assert "mm_record_key" not in ren and ren["annual_value"] == 1648.0

    # Survives a backend restart.
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
    for _ in range(60):
        try:
            if requests.get(f"{MM}/contracts/{alpha['id']}", headers=coord, timeout=3).status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    assert requests.get(f"{MM}/contracts/{alpha['id']}", headers=coord).json()["contract"]["annual_value"] == 1600


SYNC_OK = ("awaiting_sicon_matching", "not_reconciled", "awaiting_customer_mapping")


def test_failed_import_is_reported():
    coord = _h("cm-test-coord")
    u = _upload("mmt_broken.xlsx", b"not a workbook", coord)
    assert u["state"] == "failed" and u.get("error")
    assert requests.post(f"{MM}/uploads", headers=coord, json={"filename": "x.csv", "size": 1, "total_chunks": 1}).status_code == 400
