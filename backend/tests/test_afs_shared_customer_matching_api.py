"""API regression: Aftersales Estate Onboarding reconcile/commit use the shared customer identity (Sage matching).
Also Sicon classify/sync + Sage _crm_company linking at unit level. All data tagged TEST_<tag> and cleaned by id."""
import asyncio
import io
import os
import uuid

import openpyxl
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for ln in open("/app/frontend/.env"):
        if ln.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = ln.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api/crm/v2/aftersales/onboarding"
OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
TAG = uuid.uuid4().hex[:6].upper()
MDB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

CREATED = {"orgs": [], "crm": [], "imports": [], "refs": []}


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _mk_org(name, ref="", account_type="lite"):
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.customer_identity import lite_org_doc
    oid = f"TEST_{TAG}_{uuid.uuid4().hex[:8]}"
    d = lite_org_doc(oid, {"name": name}, ref=ref, company="", source="test", job_id=None)
    d["account_type"] = account_type
    MDB.organizations.insert_one(d)
    CREATED["orgs"].append(oid)
    if ref:
        MDB.customer_account_refs.insert_one({"system": "sage", "company": "", "ref": ref, "org_id": oid, "source": "test"})
        CREATED["refs"].append(ref)
    return oid


def _mk_crm(name, **extra):
    cid = f"TEST_{TAG}_crm_{uuid.uuid4().hex[:8]}"
    MDB.crm2_companies.insert_one({"id": cid, "organization_id": OP, "name": name, "type": "customer",
                                   "created_at": _now(), **extra})
    CREATED["crm"].append(cid)
    return cid


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login", json={"email": "admin@pulsefitness.com", "password": "C2s9yJ3YAhydB4d34-Bykg"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"CRM login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    orgs = CREATED["orgs"]
    imps = CREATED["imports"]
    # everything committed into my orgs / by my imports
    crm_ids = set(CREATED["crm"]) | {c["id"] for c in MDB.crm2_companies.find({"linked_organization_id": {"$in": orgs}}, {"id": 1})}
    for i in MDB.crm2_afs_onboarding.find({"id": {"$in": imps}}, {"committed": 1}):
        com = i.get("committed") or {}
        if com.get("crm_company_id"):
            crm_ids.add(com["crm_company_id"])
        if com.get("customer_org_id") and com["customer_org_id"] not in orgs and \
                (MDB.organizations.find_one({"id": com["customer_org_id"], "created_via": "afs_estate_onboarding",
                                             "name": {"$regex": f"TEST_{TAG}"}})):
            orgs.append(com["customer_org_id"])
    site_ids = [s["id"] for s in MDB.sites.find({"organization_id": {"$in": orgs}}, {"id": 1})]
    for coll in MDB.list_collection_names():
        if orgs:
            MDB[coll].delete_many({"organization_id": {"$in": orgs}})
        if site_ids:
            MDB[coll].delete_many({"site_id": {"$in": site_ids}})
    MDB.crm2_contracts.delete_many({"source_import_id": {"$in": imps}})
    crm_ids |= {f"tenant-{o}" for o in orgs}  # platform-admin tenant mirror auto-created per org
    MDB.crm2_companies.delete_many({"id": {"$in": list(crm_ids)}})
    MDB.crm2_afs_onboarding.delete_many({"id": {"$in": imps}})
    MDB.customer_account_refs.delete_many({"org_id": {"$in": orgs}})
    MDB.onboarding_audit_events.delete_many({"detail.org_id": {"$in": orgs}})
    MDB.organizations.delete_many({"id": {"$in": orgs}})


def _import(H, customer_name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Site Name", "Description", "Make", "Model", "Serial Number", "Contract Start"])
    ws.append([f"TEST_{TAG} Main Site", "Treadmill", "Life Fitness", "95T", f"SN{TAG}{uuid.uuid4().hex[:4]}", "2026-01-01"])
    bio = io.BytesIO()
    wb.save(bio)
    r = requests.post(f"{API}/analyze", headers=H, timeout=60,
                      files={"file": ("t.xlsx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    j = r.json()
    CREATED["imports"].append(j["import_id"])
    cmap = {"site_name": 0, "description": 1, "make": 2, "model": 3, "serial": 4, "contract_start": 5}
    b = requests.post(f"{API}/{j['import_id']}/build", headers=H, timeout=60,
                      json={"sheet_name": j["suggested_sheet"], "header_row": 1, "column_map": cmap,
                            "customer_name": customer_name})
    assert b.status_code == 200, b.text
    assert b.json()["rows"], b.text
    # ensure rows included
    rows = MDB.crm2_afs_onboarding.find_one({"id": j["import_id"]})["rows"]
    assert any(r.get("include") for r in rows), rows[:1]
    return j["import_id"]


def _commit(H, iid, **body):
    return requests.post(f"{API}/{iid}/commit", headers=H, json={"billing_frequency": "annual", **body}, timeout=90)


def _status(iid):
    return MDB.crm2_afs_onboarding.find_one({"id": iid}, {"status": 1})["status"]


def _n_orgs():
    return MDB.organizations.count_documents({})


# Reconcile: org candidates from shared identity service
class TestReconcileCandidates:
    def test_org_candidate_listed(self, H):
        org = _mk_org(f"TEST_{TAG} Zephyr Leisure")
        iid = _import(H, f"TEST_{TAG} Zephyr Leisure")
        r = requests.get(f"{API}/{iid}/reconcile", headers=H, timeout=30)
        assert r.status_code == 200
        c = [x for x in r.json()["candidates"] if x["id"] == f"org:{org}"]
        assert c and c[0]["kind"] == "organisation" and r.json()["decision_required"] is True

    def test_linked_org_not_duplicated(self, H):
        org = _mk_org(f"TEST_{TAG} Quokka Gym")
        crm = _mk_crm(f"TEST_{TAG} Quokka Gym", linked_organization_id=org)
        iid = _import(H, f"TEST_{TAG} Quokka Gym")
        ids = [x["id"] for x in requests.get(f"{API}/{iid}/reconcile", headers=H, timeout=30).json()["candidates"]]
        assert crm in ids and f"org:{org}" not in ids


# Commit linking to existing orgs
class TestCommitLinking:
    def test_commit_org_prefix_links_existing(self, H):
        org = _mk_org(f"TEST_{TAG} Orca Fitness")
        iid = _import(H, f"TEST_{TAG} Orca Fitness")
        n = _n_orgs()
        r = _commit(H, iid, company_id=f"org:{org}")
        assert r.status_code == 200, r.text
        com = r.json()["committed"]
        assert com["customer_org_id"] == org
        assert _n_orgs() == n
        assert MDB.crm2_companies.count_documents({"organization_id": OP, "linked_organization_id": org}) == 1
        # second import for same org via customer_org_id -> reuses CRM company
        iid2 = _import(H, f"TEST_{TAG} Orca Fitness")
        r2 = _commit(H, iid2, customer_org_id=org)
        assert r2.status_code == 200, r2.text
        assert r2.json()["committed"]["crm_company_id"] == com["crm_company_id"]
        assert MDB.crm2_companies.count_documents({"organization_id": OP, "linked_organization_id": org}) == 1
        assert _n_orgs() == n

    def test_commit_account_ref_autolinks(self, H):
        ref = f"TREF{TAG}A"
        org = _mk_org(f"TEST_{TAG} Narwhal Sports", ref=ref)
        iid = _import(H, f"TEST_{TAG} Totally Other Name")
        n = _n_orgs()
        r = _commit(H, iid, account_ref=ref.lower())
        assert r.status_code == 200, r.text
        assert r.json()["committed"]["customer_org_id"] == org
        assert _n_orgs() == n

    def test_crm_company_with_account_number_links(self, H):
        ref = f"TREF{TAG}B"
        org = _mk_org(f"TEST_{TAG} Ibis Health", ref=ref)
        crm = _mk_crm(f"TEST_{TAG} Ibis Health CRM", account_number=ref)
        iid = _import(H, f"TEST_{TAG} Ibis Health CRM")
        n = _n_orgs()
        r = _commit(H, iid, company_id=crm)
        assert r.status_code == 200, r.text
        assert r.json()["committed"]["customer_org_id"] == org
        assert r.json()["committed"]["crm_company_id"] == crm
        assert MDB.crm2_companies.find_one({"id": crm})["linked_organization_id"] == org
        assert _n_orgs() == n

    def test_crm_company_no_ref_similar_org_409_then_retry(self, H):
        org = _mk_org(f"TEST_{TAG} Pangolin Club")
        crm = _mk_crm(f"TEST_{TAG} Pangolin Club")
        iid = _import(H, f"TEST_{TAG} Pangolin Club")
        prev = _status(iid)
        n = _n_orgs()
        r = _commit(H, iid, company_id=crm)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "customer_match_required"
        assert any(c["id"] == f"org:{org}" for c in d["candidates"])
        assert _status(iid) == prev, _status(iid)
        assert _n_orgs() == n
        r2 = _commit(H, iid, company_id=f"org:{org}")
        assert r2.status_code == 200, r2.text
        assert r2.json()["committed"]["customer_org_id"] == org
        assert _n_orgs() == n
        # record CRM duplication side-effect (informational)
        print("CRM companies named Pangolin:",
              MDB.crm2_companies.count_documents({"organization_id": OP, "name": f"TEST_{TAG} Pangolin Club"}),
              "original crm linked:", MDB.crm2_companies.find_one({"id": crm}).get("linked_organization_id"))


# create_new_customer & guards
class TestCreateNewAndGuards:
    def test_create_new_lite(self, H):
        name = f"TEST_{TAG} Brandnew Xylophone"
        iid = _import(H, name)
        n = _n_orgs()
        r = _commit(H, iid, create_new_customer=True)
        assert r.status_code == 200, r.text
        oid = r.json()["committed"]["customer_org_id"]
        CREATED["orgs"].append(oid)
        assert _n_orgs() == n + 1
        o = MDB.organizations.find_one({"id": oid})
        assert o["enabled_modules"] == ["operations"] and o["subscription_tier"] == "free"
        assert o["onboarding_status"] == "pending_activation"
        assert MDB.users.count_documents({"organization_id": oid}) == 0

    def test_operator_org_404(self, H):
        iid = _import(H, f"TEST_{TAG} Guard One")
        r = _commit(H, iid, company_id=f"org:{OP}")
        assert r.status_code == 404
        r = _commit(H, iid, customer_org_id="does-not-exist-" + TAG)
        assert r.status_code == 404
        assert _status(iid) != "committing"

    def test_invalid_billing_frequency_no_partial_writes(self, H):
        org = _mk_org(f"TEST_{TAG} Freq Guard")
        iid = _import(H, f"TEST_{TAG} Freq Guard")
        r = _commit(H, iid, company_id=f"org:{org}", billing_frequency="weekly")
        assert r.status_code == 400
        assert _status(iid) != "committing"
        n_sites = MDB.sites.count_documents({"organization_id": org})
        n_eq = MDB.equipment.count_documents({"organization_id": org})
        assert n_sites == 0 and n_eq == 0, f"partial writes on 400: sites={n_sites} equipment={n_eq}"

    def test_other_tenant_org_listed_and_linkable(self, H):
        """Security probe: a full (operator) org of another tenant should not be a customer candidate."""
        other = _mk_org(f"TEST_{TAG} Rival Operator Gym", account_type="full")
        iid = _import(H, f"TEST_{TAG} Rival Operator Gym")
        ids = [x["id"] for x in requests.get(f"{API}/{iid}/reconcile", headers=H, timeout=30).json()["candidates"]]
        assert f"org:{other}" not in ids, "other tenant's operator org offered as customer candidate"


# Sicon + Sage unit-level shared matching
class TestSiconSageUnit:
    def test_sicon_and_sage_link(self):
        import sys
        sys.path.insert(0, "/app/backend")

        async def run():
            from utils import sicon_onboarding as SO
            from routes import customer_account_import as CAI
            from utils.database import db
            op = f"TEST_{TAG}_OP"
            ref = f"SIC{TAG}"
            org = _mk_org(f"TEST_{TAG} Sicon Org", ref=ref)
            try:
                n = await db.organizations.count_documents({})
                r1 = await SO.sync_customer(op, None, ref, "Sicon Name", True, "run-t")
                r2 = await SO.sync_customer(op, None, ref, "Sicon Name", True, "run-t")
                assert r1["bucket"] == "new" and r2["bucket"] == "matched" and r2["pulse_id"] == r1["pulse_id"]
                assert await db.crm2_companies.count_documents({"organization_id": op}) == 1
                assert await db.organizations.count_documents({}) == n
                # Sage _crm_company links a pre-existing unlinked Sicon CRM company by sage_customer_id
                ref2 = f"SIC{TAG}2"
                org2 = _mk_org(f"TEST_{TAG} Sage Org2", ref=ref2)
                sic = {"id": f"TEST_{TAG}_sic", "organization_id": op, "name": "S", "sage_customer_id": ref2,
                       "linked_organization_id": None}
                await db.crm2_companies.insert_one(dict(sic))
                cid = await CAI._crm_company({"id": op}, org2, ref2, {"id": "u"}, {"id": f"TEST_{TAG}_job"})
                assert cid == sic["id"]
                assert (await db.crm2_companies.find_one({"id": cid}))["linked_organization_id"] == org2
            finally:
                await db.crm2_companies.delete_many({"organization_id": op})
                await db.customer_import_undo.delete_many({"job_id": f"TEST_{TAG}_job"})
        asyncio.run(run())
