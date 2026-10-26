"""External Service Providers — engineer site allocation without territories (Jan 2026).

Covers:
- GET /api/master-admin/mod-estate/bfpo-sites returns BFPO estate sites + mod_site orgs (is_mod_org)
- Create provider + engineer with site_ids (incl. mod_site org) -> persisted, card shows site names
- Engineer scope: /api/bfpo/sites, /jobs, /equipment, /equipment/{id} include allocated mod org only
- Equipment search must not leak out of scope
- PATCH engineer site_ids persistence
- Regression: territory engineer (engineer.gib) + lead unrestricted /bfpo/sites
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
BYPASS = {"x-ratelimit-bypass": "test-bypass-secret-for-ci-runs-only-2026"}

ADMIN = ("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
GIB = ("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!")
LEAD = ("lead@bfpo.pulsefitness.test", "Bfpo123!")

ALDERSHOT = "e6ae0215-2fe2-4458-8c9b-e5f6e94f1ce7"   # mod_site org
BARRACKS_A = "f917152d-6472-4bcf-b74b-28d96ce473b3"  # mod_site org (NOT allocated)
HMS_ROOKE_NAME = "HMS Rooke Gymnasium"

RUN = uuid.uuid4().hex[:8]
ENG_EMAIL = f"test_esp_{RUN}@example.com"
TEMP_PW = f"TempPw!{RUN}"


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


def _mdb():
    return MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, headers=BYPASS, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    assert tok, f"no token for {email}: {j}"
    return tok


def _h(t):
    return {"Authorization": f"Bearer {t}", **BYPASS}


@pytest.fixture(scope="module")
def ctx():
    db = _mdb()
    admin = _login(*ADMIN)
    rooke = db.sites.find_one({"organization_id": "bfpo-mod-org", "name": HMS_ROOKE_NAME}, {"_id": 0, "id": 1})
    hq = db.sites.find_one({"organization_id": "bfpo-mod-org", "territory_id": None}, {"_id": 0, "id": 1})
    # Seed TEST_ cases + equipment on mod orgs
    case_in, case_out = f"TEST_case_in_{RUN}", f"TEST_case_out_{RUN}"
    eq_in = f"TEST_eq_in_{RUN}"
    db.svc_cases.insert_many([
        {"id": case_in, "organization_id": ALDERSHOT, "title": f"TEST_ Aldershot fault {RUN}", "status": "new",
         "priority": "p3", "created_at": "2026-01-10T00:00:00Z"},
        {"id": case_out, "organization_id": BARRACKS_A, "title": f"TEST_ Barracks A fault {RUN}", "status": "new",
         "priority": "p3", "created_at": "2026-01-10T00:00:00Z"},
    ])
    db.equipment.insert_one({"id": eq_in, "organization_id": ALDERSHOT, "name": f"TEST_ZZTreadmill {RUN}",
                             "serial_number": f"TESTSER{RUN}", "model": "TESTMODEL"})
    eq_out = db.equipment.find_one({"organization_id": BARRACKS_A}, {"_id": 0, "id": 1, "name": 1, "serial_number": 1})
    c = {"db": db, "admin": admin, "rooke": rooke["id"], "hq": hq["id"] if hq else None,
         "case_in": case_in, "case_out": case_out, "eq_in": eq_in, "eq_out": eq_out, "sup_id": None, "eng_id": None}
    yield c
    db.svc_cases.delete_many({"id": {"$in": [case_in, case_out]}})
    db.equipment.delete_many({"id": eq_in})
    if c["sup_id"]:
        db.mod_estate_suppliers.delete_one({"id": c["sup_id"]})
    db.users.delete_many({"email": ENG_EMAIL})
    if c["eng_id"]:
        db.svc_engineers.delete_many({"id": c["eng_id"]})


# --- allocatable sites endpoint ---
class TestAllocatableSites:
    def test_bfpo_sites_includes_estate_and_mod_orgs(self, ctx):
        r = requests.get(f"{API}/master-admin/mod-estate/bfpo-sites", headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        sites = r.json()["sites"]
        ids = {s["id"]: s for s in sites}
        assert ctx["rooke"] in ids and not ids[ctx["rooke"]].get("is_mod_org")
        if ctx["hq"]:
            assert ctx["hq"] in ids, "BFPO site without territory missing"
        assert ALDERSHOT in ids and ids[ALDERSHOT]["is_mod_org"] is True
        assert ids[ALDERSHOT]["name"] == "Aldershot Garrison Gym"
        n_mod = ctx["db"].organizations.count_documents({"account_type": "mod_site"})
        n_bfpo = ctx["db"].sites.count_documents({"organization_id": "bfpo-mod-org"})
        assert len(sites) == n_mod + n_bfpo
        names = [(s.get("name") or "").lower() for s in sites]
        assert names == sorted(names)

    def test_bfpo_sites_requires_master_admin(self):
        tok = _login(*GIB, portal="mod")
        r = requests.get(f"{API}/master-admin/mod-estate/bfpo-sites", headers=_h(tok), timeout=30)
        assert r.status_code in (401, 403)


# --- create / update provider with site_ids ---
class TestProviderSiteAllocation:
    def test_create_provider_with_sites(self, ctx):
        payload = {"name": f"TEST_ESP {RUN}", "mod_bfpo_default": "yes", "country": "UK",
                   "engineers": [{"full_name": f"TEST Eng {RUN}", "email": ENG_EMAIL, "mod_bfpo": "yes",
                                  "site_ids": [ALDERSHOT, ctx["rooke"]], "password_mode": "temp",
                                  "temp_password": TEMP_PW}]}
        r = requests.post(f"{API}/master-admin/mod-estate/external-providers", json=payload,
                          headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        ctx["sup_id"] = j["provider"]["id"]
        ctx["eng_id"] = j["engineers"][0]["id"]
        assert set(j["engineers"][0]["site_ids"]) == {ALDERSHOT, ctx["rooke"]}
        assert j["engineers"][0]["territory_ids"] == []

    def test_provider_card_shows_site_names(self, ctx):
        r = requests.get(f"{API}/master-admin/mod-estate/external-providers", headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200
        p = next(p for p in r.json()["providers"] if p["id"] == ctx["sup_id"])
        eng = p["engineers"][0]
        assert set(eng["site_names"]) == {"Aldershot Garrison Gym", HMS_ROOKE_NAME}
        assert {s["name"] for s in p["sites"]} == {"Aldershot Garrison Gym", HMS_ROOKE_NAME}
        assert p["is_mod_bfpo"] is True


# --- engineer access with mod org allocated ---
class TestEngineerScope:
    @pytest.fixture(scope="class")
    def etok(self, ctx):
        return _login(ENG_EMAIL, TEMP_PW, portal="mod")

    def test_sites(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/sites", headers=_h(etok), timeout=30)
        assert r.status_code == 200, r.text
        ids = {s["id"] for s in r.json()["sites"]}
        assert ids == {ALDERSHOT, ctx["rooke"]}, ids

    def test_site_detail(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/sites/{ALDERSHOT}", headers=_h(etok), timeout=30)
        assert r.status_code == 200
        assert any(e["id"] == ctx["eq_in"] for e in r.json()["equipment"])
        r2 = requests.get(f"{API}/bfpo/sites/{BARRACKS_A}", headers=_h(etok), timeout=30)
        assert r2.status_code == 404

    def test_jobs(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/jobs", headers=_h(etok), timeout=60)
        assert r.status_code == 200, r.text
        ids = {j["id"] for j in r.json()["jobs"]}
        assert ctx["case_in"] in ids
        assert ctx["case_out"] not in ids

    def test_equipment_list(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/equipment", headers=_h(etok), timeout=30)
        assert r.status_code == 200
        rows = r.json()["equipment"]
        ids = {e["id"] for e in rows}
        assert ctx["eq_in"] in ids
        orgs = {e.get("organization_id") for e in rows}
        assert orgs <= {ALDERSHOT, "bfpo-mod-org"}, orgs
        if ctx["eq_out"]:
            assert ctx["eq_out"]["id"] not in ids

    def test_equipment_search_does_not_leak(self, ctx, etok):
        # Searching for equipment in a NON-allocated org must return nothing from it
        term = (ctx["eq_out"] or {}).get("serial_number") or (ctx["eq_out"] or {}).get("name")
        if not term:
            pytest.skip("no out-of-scope equipment to search")
        r = requests.get(f"{API}/bfpo/equipment", params={"search": term}, headers=_h(etok), timeout=30)
        assert r.status_code == 200
        orgs = {e.get("organization_id") for e in r.json()["equipment"]}
        assert orgs <= {ALDERSHOT, "bfpo-mod-org"}, f"search leaked orgs: {orgs}"

    def test_equipment_search_in_scope(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/equipment", params={"search": f"TESTSER{RUN}"}, headers=_h(etok), timeout=30)
        assert r.status_code == 200
        assert [e["id"] for e in r.json()["equipment"]] == [ctx["eq_in"]]

    def test_equipment_detail(self, ctx, etok):
        r = requests.get(f"{API}/bfpo/equipment/{ctx['eq_in']}", headers=_h(etok), timeout=30)
        assert r.status_code == 200
        assert r.json()["equipment"]["id"] == ctx["eq_in"]
        if ctx["eq_out"]:
            r2 = requests.get(f"{API}/bfpo/equipment/{ctx['eq_out']['id']}", headers=_h(etok), timeout=30)
            assert r2.status_code == 404

    def test_patch_engineer_sites_and_scope_follows(self, ctx, etok):
        r = requests.patch(
            f"{API}/master-admin/mod-estate/external-providers/{ctx['sup_id']}/engineers/{ctx['eng_id']}",
            json={"mod_bfpo": "yes", "site_ids": [BARRACKS_A], "territory_ids": []},
            headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        u = ctx["db"].users.find_one({"id": ctx["eng_id"]}, {"_id": 0, "bfpo_site_ids": 1})
        assert u["bfpo_site_ids"] == [BARRACKS_A]
        r2 = requests.get(f"{API}/bfpo/sites", headers=_h(etok), timeout=30)
        assert {s["id"] for s in r2.json()["sites"]} == {BARRACKS_A}
        jobs = {j["id"] for j in requests.get(f"{API}/bfpo/jobs", headers=_h(etok), timeout=60).json()["jobs"]}
        assert ctx["case_out"] in jobs and ctx["case_in"] not in jobs

    def test_patch_mod_no_clears_sites(self, ctx):
        r = requests.patch(
            f"{API}/master-admin/mod-estate/external-providers/{ctx['sup_id']}/engineers/{ctx['eng_id']}",
            json={"mod_bfpo": "no"}, headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200
        u = ctx["db"].users.find_one({"id": ctx["eng_id"]}, {"_id": 0, "bfpo_site_ids": 1, "is_mod_bfpo": 1})
        assert u["bfpo_site_ids"] == [] and u["is_mod_bfpo"] is False


# --- regression ---
class TestRegression:
    def test_territory_engineer_still_scoped(self, ctx):
        tok = _login(*GIB, portal="mod")
        r = requests.get(f"{API}/bfpo/sites", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        sites = r.json()["sites"]
        ids = {s["id"] for s in sites}
        gib_ids = {s["id"] for s in ctx["db"].sites.find({"organization_id": "bfpo-mod-org", "territory_id": "terr-gib"}, {"id": 1})}
        assert gib_ids <= ids
        assert ALDERSHOT not in ids
        jobs = {j["id"] for j in requests.get(f"{API}/bfpo/jobs", headers=_h(tok), timeout=60).json()["jobs"]}
        assert ctx["case_in"] not in jobs and ctx["case_out"] not in jobs

    def test_lead_sites_unchanged(self, ctx):
        tok = _login(*LEAD, portal="mod")
        r = requests.get(f"{API}/bfpo/sites", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        sites = r.json()["sites"]
        assert len(sites) == ctx["db"].sites.count_documents({"organization_id": "bfpo-mod-org"})
        assert ALDERSHOT not in {s["id"] for s in sites}

    def test_update_provider_company_fields(self, ctx):
        r = requests.patch(f"{API}/master-admin/mod-estate/external-providers/{ctx['sup_id']}",
                           json={"notes": "TEST_ notes"}, headers=_h(ctx["admin"]), timeout=30)
        assert r.status_code == 200
        assert ctx["db"].mod_estate_suppliers.find_one({"id": ctx["sup_id"]})["notes"] == "TEST_ notes"
