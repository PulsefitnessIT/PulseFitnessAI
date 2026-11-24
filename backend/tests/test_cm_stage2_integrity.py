"""Contract Management stage 2 — integrity fixes, approval-first renewals,
estate-onboarding reconciliation, MOD rate verification and daily checks.

Fictional data only; every record created here is tagged ``cm_t2_`` and
removed at the end. The MOD rate card is snapshotted and restored.
"""
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
TAG = "cm_t2_"


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)
    rate_backup = list(mdb.mod_sor_rate_card.find({}))
    yield
    mdb.mod_sor_rate_card.delete_many({})
    if rate_backup:
        mdb.mod_sor_rate_card.insert_many(rate_backup)
    for coll in ("crm2_contracts", "crm2_companies", "crm2_contacts", "organizations", "sites", "equipment",
                 "crm2_afs_onboarding", "crm2_quotes", "crm2_contract_assets"):
        mdb[coll].delete_many({"$or": [{"id": {"$regex": f"^{TAG}"}}, {"organization_id": {"$regex": f"^{TAG}"}},
                                       {"company_id": {"$regex": f"^{TAG}"}}, {"previous_contract_id": {"$regex": f"^{TAG}"}},
                                       {"source_import_id": {"$regex": f"^{TAG}"}}]})
    mdb.crm2_activities.delete_many({"$or": [{"contract_id": {"$regex": f"^{TAG}"}}, {"company_id": {"$regex": f"^{TAG}"}}]})


def _contract(cid, **kw):
    today = datetime.now(timezone.utc).date()
    doc = {"id": cid, "organization_id": OP, "contract_number": cid.upper(), "company_id": f"{TAG}co-ren",
           "company_name": "CM Test Gym", "status": "active", "annual_value": 1000.0,
           "start_date": (today - timedelta(days=335)).isoformat(), "end_date": (today + timedelta(days=30)).isoformat(),
           "billing_frequency": "annual", "contact_id": f"{TAG}ct-1", "created_at": datetime.now(timezone.utc).isoformat()}
    doc.update(kw)
    mdb.crm2_contracts.insert_one(doc)
    return doc


def test_sicon_and_sage_never_fabricate_references():
    _contract(f"{TAG}sync")
    h = _crm("cm-test-admin")
    r = requests.post(f"{API}/crm/v2/contracts/{TAG}sync/sync-sicon", headers=h).json()
    assert r["success"] is False and r["status"] in ("pending", "not_configured") and not r["sicon_contract_id"]
    r = requests.post(f"{API}/crm/v2/contracts/{TAG}sync/sync-sage", headers=h).json()
    assert r["success"] is False and r["status"] in ("queued", "failed") and not r["sage_reference"]
    c = mdb.crm2_contracts.find_one({"id": f"{TAG}sync"})
    assert not c.get("sicon_contract_id") and not c.get("sage_reference")
    assert c["sicon_sync_status"] in ("pending", "queued") and c["sage_sync_status"] != "synced"
    bad = requests.post(f"{API}/crm/v2/aftersales/finance/sync/{TAG}sync/mark-synced", headers=h, json={})
    assert bad.status_code == 400


def _row(site, serial, start=None):
    return {"include": True, "chosen_price": "inherited", "inherited": {"annual": 100.0}, "pulse": {"annual": 0},
            "match": {"matched_code": "TM1"},
            "clean": {"site_name": site, "site_code": "", "description": "Treadmill", "model": "TM1", "make": "Pulse",
                      "serial": serial, "install_date": None, "warranty_end": None, "contract_start": start,
                      "warranty_status": ""}}


def test_estate_onboarding_reconciles_existing_customer():
    org = f"{TAG}custorg"
    mdb.organizations.insert_one({"id": org, "name": "Riverside Leisure", "account_type": "lite"})
    mdb.crm2_companies.insert_one({"id": f"{TAG}co-river", "organization_id": OP, "name": "Riverside Leisure Ltd",
                                   "linked_organization_id": org})
    mdb.sites.insert_one({"id": f"{TAG}site-main", "organization_id": org, "name": "Main Gym"})
    mdb.equipment.insert_one({"id": f"{TAG}eq-1", "organization_id": org, "site_id": f"{TAG}site-main", "serial_number": "SN-001"})
    imp = f"{TAG}imp1"
    mdb.crm2_afs_onboarding.insert_one({"id": imp, "organization_id": OP, "customer_name": "Riverside Leisure Limited",
                                        "status": "ready", "grouping": "per_site", "contract_type": "gold",
                                        "rows": [_row("Main Gym", "sn-001"), _row("Pool Hall", "SN-002")]})
    h = _crm("cm-test-coord")
    rec = requests.get(f"{API}/crm/v2/aftersales/onboarding/{imp}/reconcile", headers=h).json()
    assert rec["decision_required"] and rec["candidates"][0]["id"] == f"{TAG}co-river"
    r = requests.post(f"{API}/crm/v2/aftersales/onboarding/{imp}/commit", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "customer_match_required"
    r = requests.post(f"{API}/crm/v2/aftersales/onboarding/{imp}/commit", headers=h, json={"company_id": f"{TAG}co-river"})
    assert r.status_code == 200, r.text
    done = r.json()["committed"]
    assert done["crm_company_id"] == f"{TAG}co-river" and done["customer_org_id"] == org
    assert done["reused"] == {"customer": True, "sites": 1, "equipment": 1}
    assert done["new_sites"] == 1 and done["new_equipment"] == 1
    assert mdb.equipment.count_documents({"organization_id": org, "serial_number": {"$in": ["SN-001", "sn-001"]}}) == 1
    for ct in done["contracts"]:
        c = mdb.crm2_contracts.find_one({"id": ct["id"]})
        mdb.crm2_contracts.update_one({"id": ct["id"]}, {"$set": {"source_import_id": imp}})
        assert c["start_date"] is None and c["billing_frequency"] is None
        assert set(c["missing_fields"]) == {"start_date", "billing_frequency"}
        assert mdb.crm2_activities.count_documents({"dedupe_key": f"cm:missing:{ct['id']}"}) == 1
    assert requests.post(f"{API}/crm/v2/aftersales/onboarding/{imp}/commit", headers=h,
                         json={"company_id": f"{TAG}co-river"}).status_code == 409
    assert requests.post(f"{API}/crm/v2/aftersales/onboarding/{imp}/commit", headers=_crm("cm-test-sales"),
                         json={"company_id": f"{TAG}co-river"}).status_code == 403


def test_renewals_are_prepared_once_and_sent_only_on_approval():
    mdb.crm2_contacts.insert_one({"id": f"{TAG}ct-1", "organization_id": OP, "company_id": f"{TAG}co-ren", "email": "renew@example.test"})
    _contract(f"{TAG}ren-ok")
    _contract(f"{TAG}ren-noemail", contact_id=None, company_id=f"{TAG}co-none")
    h = _crm("cm-test-coord")
    dry = requests.post(f"{API}/crm/workspace/renewals/prepare?dry_run=true", headers=h).json()
    ids = {w["contract_id"] for w in dry["would_prepare"]}
    assert f"{TAG}ren-ok" in ids and not dry["prepared"]
    assert f"{TAG}ren-noemail" in {b["contract_id"] for b in dry["blocked"]}
    assert mdb.crm2_contracts.count_documents({"previous_contract_id": f"{TAG}ren-ok"}) == 0
    real = requests.post(f"{API}/crm/workspace/renewals/prepare?dry_run=false", headers=h).json()
    rid = next(p["renewal_contract_id"] for p in real["prepared"] if p["contract_id"] == f"{TAG}ren-ok")
    again = requests.post(f"{API}/crm/workspace/renewals/prepare?dry_run=false", headers=h).json()
    assert f"{TAG}ren-ok" in {s["contract_id"] for s in again["skipped"]}
    assert mdb.crm2_contracts.count_documents({"previous_contract_id": f"{TAG}ren-ok"}) == 1
    ren = mdb.crm2_contracts.find_one({"id": rid})
    old_end = datetime.fromisoformat(mdb.crm2_contracts.find_one({"id": f"{TAG}ren-ok"})["end_date"]).date()
    assert ren["status"] == "renewal_pending_approval"
    assert ren["start_date"] == (old_end + timedelta(days=1)).isoformat()
    assert mdb.crm2_activities.count_documents({"dedupe_key": f"cm:renewal-approval:{rid}", "status": "open"}) == 1
    assert requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=_crm("cm-test-sales"), json={}).status_code == 403
    r = requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=h, json={"uplift_percent": 3.5})
    assert r.status_code == 200, r.text
    assert r.json()["annual_value"] == 1035.0
    assert mdb.crm2_contracts.find_one({"id": rid})["status"] == "sent"
    assert mdb.crm2_activities.find_one({"dedupe_key": f"cm:renewal-approval:{rid}"})["status"] == "done"
    assert requests.post(f"{API}/crm/workspace/renewals/{rid}/approve-send", headers=h, json={}).status_code == 409


def test_mod_placeholder_rates_block_sending_until_verified(tmp_path):
    h = _crm("cm-test-admin")
    mdb.mod_sor_rate_card.update_many({}, {"$set": {"price_status": "placeholder"}, "$unset": {"valid_to": "", "valid_from": ""}})
    q = requests.post(f"{API}/crm/mod-quote/generate", headers=h, json={
        "contract_type": "A", "site_name": "CM Test Site", "lines": [{"rate_card_id": "sor-2", "quantity": 1}]}).json()
    qid = q.get("id") or q.get("quote", {}).get("id")
    mdb.crm2_quotes.update_one({"id": qid}, {"$set": {"company_id": f"{TAG}mod"}})
    blocked = requests.post(f"{API}/crm/mod-quote/{qid}/send-esign", headers=h, json={"to": "mod@example.test"})
    assert blocked.status_code == 409 and "verified" in blocked.json()["detail"]
    csv = tmp_path / "mod.csv"
    csv.write_text("Item No,Description,Type A Price,Type B Price\n2,Treadmill,60.00,17.00\n999,Unknown,1,1\n")
    files = {"file": ("mod.csv", csv.read_bytes(), "text/csv")}
    prev = requests.post(f"{API}/crm/mod-quote/rate-card/import", headers=h, files=files, data={"dry_run": "true"}).json()
    assert [m["id"] for m in prev["matched"]] == ["sor-2"] and prev["unmatched"][0]["key"] == "999"
    assert mdb.mod_sor_rate_card.find_one({"id": "sor-2"})["price_status"] == "placeholder"
    files = {"file": ("mod.csv", csv.read_bytes(), "text/csv")}
    assert requests.post(f"{API}/crm/mod-quote/rate-card/import", headers=h, files=files,
                         data={"dry_run": "false"}).status_code == 400  # dates required
    files = {"file": ("mod.csv", csv.read_bytes(), "text/csv")}
    today = datetime.now(timezone.utc).date()
    ok = requests.post(f"{API}/crm/mod-quote/rate-card/import", headers=h, files=files, data={
        "dry_run": "false", "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=1095)).isoformat()})
    assert ok.status_code == 200, ok.text
    rc = mdb.mod_sor_rate_card.find_one({"id": "sor-2"})
    assert rc["price_status"] == "verified" and rc["type_a_price"] == 60.0
    assert mdb.mod_sor_rate_card_history.count_documents({"item_id": "sor-2"}) >= 1
    sent = requests.post(f"{API}/crm/mod-quote/{qid}/send-esign", headers=h, json={"to": "mod@example.test"})
    assert sent.status_code == 200, sent.text
    coord = requests.post(f"{API}/crm/mod-quote/rate-card/import", headers=_crm("cm-test-coord"),
                          files={"file": ("mod.csv", csv.read_bytes(), "text/csv")}, data={"dry_run": "true"})
    assert coord.status_code == 403


def test_daily_checks_cron_and_manual_run():
    assert requests.post(f"{API}/crm/workspace/cron/daily-checks", json={}).status_code == 401
    assert requests.post(f"{API}/crm/workspace/cron/daily-checks", headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    secret = [ln.split("=", 1)[1].strip() for ln in open("/app/backend/.env") if ln.startswith("WEBHOOK_CRON_SECRET=")][0]
    run_id = f"{TAG}{uuid.uuid4()}"
    hdr = {"Authorization": f"Bearer {secret}", "X-Webhook-Id": run_id}
    r = requests.post(f"{API}/crm/workspace/cron/daily-checks", headers=hdr, json={"event": "schedule.triggered", "run_id": run_id})
    assert r.status_code == 200 and r.json()["accepted"] and not r.json().get("duplicate")
    r = requests.post(f"{API}/crm/workspace/cron/daily-checks", headers=hdr, json={"run_id": run_id})
    assert r.json()["duplicate"] is True
    mdb.cm_daily_check_runs.delete_many({"run_id": run_id})
    assert requests.post(f"{API}/crm/workspace/daily-checks/run", headers=_crm("cm-test-sales")).status_code == 403
    res = requests.post(f"{API}/crm/workspace/daily-checks/run", headers=_crm("cm-test-coord"))
    assert res.status_code == 200 and "contract_admin" in res.json()


def test_missing_info_item_auto_resolves_when_fixed():
    c = _contract(f"{TAG}miss", billing_frequency=None)
    h = _crm("cm-test-coord")
    requests.post(f"{API}/crm/workspace/daily-checks/run", headers=h)
    key = f"cm:missing:{c['id']}"
    assert mdb.crm2_activities.find_one({"dedupe_key": key})["status"] == "open"
    mdb.crm2_contracts.update_one({"id": c["id"]}, {"$set": {"billing_frequency": "monthly"}})
    requests.post(f"{API}/crm/workspace/daily-checks/run", headers=h)
    a = mdb.crm2_activities.find_one({"dedupe_key": key})
    assert a["status"] == "done" and a["auto_resolved"] is True
    assert mdb.crm2_activities.count_documents({"dedupe_key": key}) == 1
