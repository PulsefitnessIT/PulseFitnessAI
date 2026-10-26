# CRM MOD follow-ups retest: location role gate, rename/delete location, totals.sites,
# MOD contracts excluded from generic contracts list (and compliance feed check).
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"
CID = "modco-abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
ORG = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
PULSE_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
MAIN_GYM = "b71c80cb-e5e2-4e7c-aac1-bd79418dddd4"
FITNESS_SUITE = "b84f5a44-86f5-4682-a42e-6864ad4fe3aa"
ENV = dotenv_values("/app/backend/.env")
DB = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
REP_EMAIL = "test_rep_modfollow@pulsefitness.test"
REP_PW = "RepTest123!"


def _login(email, pw):
    r = requests.post(f"{API}/crm/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def H():
    return _login("craig.henshall@pulsefitness.com", "PulseMOD123!")


@pytest.fixture(scope="module")
def REP():
    import sys
    sys.path.insert(0, "/app/backend")
    from routes.crm_auth import crm_hash_password
    DB.crm_users.delete_many({"email": REP_EMAIL})
    DB.crm_users.insert_one({"id": f"TEST_{uuid.uuid4()}", "email": REP_EMAIL, "full_name": "TEST Rep",
                             "role": "sales_rep", "organization_id": PULSE_ORG, "module_overrides": {},
                             "password": crm_hash_password(REP_PW), "created_at": "2026-01-01T00:00:00+00:00"})
    try:
        yield _login(REP_EMAIL, REP_PW)
    finally:
        DB.crm_users.delete_many({"email": REP_EMAIL})


@pytest.fixture(scope="module")
def bag():
    b = {"locations": [], "contracts": []}
    yield b
    if b["locations"]:
        DB.sites.delete_many({"id": {"$in": b["locations"]}, "organization_id": ORG})
    if b["contracts"]:
        DB.crm2_contracts.delete_many({"id": {"$in": b["contracts"]}})


class TestLocationGate:
    def test_rep_cannot_add_location(self, REP):
        r = requests.post(f"{API}/crm/v2/companies/{CID}/locations", json={"name": "TEST_rep_loc"}, headers=REP)
        assert r.status_code == 403, r.text

    def test_rep_cannot_rename_or_delete(self, REP):
        r = requests.put(f"{API}/crm/v2/companies/{CID}/locations/{MAIN_GYM}", json={"name": "X"}, headers=REP)
        assert r.status_code == 403
        r = requests.delete(f"{API}/crm/v2/companies/{CID}/locations/{MAIN_GYM}", headers=REP)
        assert r.status_code == 403


class TestRenameDelete:
    def test_add_rename_delete_flow(self, H, bag):
        r = requests.post(f"{API}/crm/v2/companies/{CID}/locations", json={"name": "TEST_Loc A"}, headers=H)
        assert r.status_code == 200, r.text
        lid = r.json()["location"]["id"]
        bag["locations"].append(lid)
        r = requests.put(f"{API}/crm/v2/companies/{CID}/locations/{lid}", json={"name": "TEST_Loc Renamed"}, headers=H)
        assert r.status_code == 200 and r.json()["ok"]
        d = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H).json()
        names = {s["id"]: s["name"] for s in d["sites"]}
        assert names.get(lid) == "TEST_Loc Renamed"
        r = requests.delete(f"{API}/crm/v2/companies/{CID}/locations/{lid}", headers=H)
        assert r.status_code == 200
        d = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H).json()
        assert lid not in {s["id"] for s in d["sites"]}
        # also gone from MOD contract location picker
        ml = requests.get(f"{API}/crm/v2/mod-contracts/locations", params={"company_id": CID}, headers=H)
        if ml.status_code == 200:
            assert lid not in str(ml.json())

    def test_rename_validation(self, H):
        r = requests.put(f"{API}/crm/v2/companies/{CID}/locations/{MAIN_GYM}", json={"name": "  "}, headers=H)
        assert r.status_code == 400
        r = requests.put(f"{API}/crm/v2/companies/{CID}/locations/nope-{uuid.uuid4()}", json={"name": "A"}, headers=H)
        assert r.status_code == 404

    def test_delete_nonempty_blocked(self, H):
        d = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H).json()
        row = next(s for s in d["sites"] if s["id"] in (MAIN_GYM, FITNESS_SUITE) and s["equipment_count"] > 0)
        r = requests.delete(f"{API}/crm/v2/companies/{CID}/locations/{row['id']}", headers=H)
        assert r.status_code == 409
        assert DB.sites.find_one({"id": row["id"]})["status"] != "archived"

    def test_delete_unknown_404(self, H):
        r = requests.delete(f"{API}/crm/v2/companies/{CID}/locations/nope-{uuid.uuid4()}", headers=H)
        assert r.status_code == 404


class TestTotals:
    def test_totals_sites_real_only(self, H):
        d = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H).json()
        real = [s for s in d["sites"] if not s.get("virtual") and s["id"] != "__unassigned__"]
        assert d["totals"]["sites"] == len(real)
        assert d["totals"]["equipment"] == sum(s["equipment_count"] for s in d["sites"])


class TestModContractsHidden:
    def test_mod_contract_not_in_generic_list_and_compliance(self, H, bag):
        r = requests.post(f"{API}/crm/v2/mod-contracts", json={
            "company_id": CID, "reference": "TEST_MODF", "status": "active",
            "start_date": "2026-01-01", "end_date": "2026-12-31",
            "lines": [{"location_id": MAIN_GYM, "service_type": "A", "price": 100}]}, headers=H)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        mid = (body.get("contract") or body).get("id")
        bag["contracts"].append(mid)
        lst = requests.get(f"{API}/crm/v2/contracts", headers=H).json()
        items = lst.get("contracts", lst) if isinstance(lst, dict) else lst
        assert mid not in {c.get("id") for c in items}
        comp = requests.get(f"{API}/crm/v2/aftersales/contracts/compliance", headers=H)
        assert comp.status_code == 200
        assert mid not in str(comp.json()), "MOD contract still appears in Live compliance feed"
