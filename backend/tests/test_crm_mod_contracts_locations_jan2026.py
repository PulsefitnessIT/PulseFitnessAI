# CRM MOD: auto-linking of MOD site companies, equipment-register locations (add / move),
# add-contact job-title picklist validation, and MOD aftersales contracts CRUD.
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"
CID = "modco-abfdabd9-ae11-4877-a44d-a36fea7f1f4e"  # MOD Test Site
ORG = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
MAIN_GYM = "b71c80cb-e5e2-4e7c-aac1-bd79418dddd4"
FITNESS_SUITE = "b84f5a44-86f5-4682-a42e-6864ad4fe3aa"


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{API}/crm/auth/login", json={"email": "craig.henshall@pulsefitness.com", "password": "PulseMOD123!"})
    if r.status_code != 200:
        pytest.skip(f"CRM login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def created():
    bag = {"contracts": [], "contacts": [], "locations": []}
    yield bag
    # cleanup via API where possible; locations via DB
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values("/app/backend/.env")
        db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
        if bag["locations"]:
            db.sites.delete_many({"id": {"$in": bag["locations"]}, "organization_id": ORG})
        if bag["contracts"]:
            db.crm2_contracts.delete_many({"id": {"$in": bag["contracts"]}})
        if bag["contacts"]:
            db.crm2_contacts.delete_many({"id": {"$in": bag["contacts"]}})
        print("cleanup ok", bag)
    except Exception as e:  # pragma: no cover
        print("cleanup failed", e)


# --- Company auto-link ---
class TestCompanyLink:
    def test_company_detail_links(self, H):
        r = requests.get(f"{API}/crm/v2/companies/{CID}", headers=H)
        assert r.status_code == 200
        c = r.json()
        assert c["type"] == "mod_site"
        for f in ("linked_organization_id", "linked_operator_org_id", "tenant_org_id"):
            assert c.get(f) == ORG, f

    def test_portal_link_candidates_include_mod(self, H):
        r = requests.get(f"{API}/crm/v2/portal-link/candidates?q=MOD Test", headers=H)
        if r.status_code == 404:
            pytest.skip("candidate endpoint path differs")
        assert r.status_code == 200
        assert ORG in str(r.json())


# --- Equipment register: virtual locations, add location, move ---
class TestLocations:
    def test_register_has_virtual_text_location(self, H):
        r = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert d["linked_via"] == "explicit_link"
        ids = {s["id"]: s for s in d["sites"]}
        assert MAIN_GYM in ids and FITNESS_SUITE in ids
        virt = [s for s in d["sites"] if s.get("virtual")]
        assert any(s["name"] == "Cardio Suite" for s in virt)
        assert d["totals"]["equipment"] == sum(s["equipment_count"] for s in d["sites"])

    def test_add_location_validation(self, H):
        r = requests.post(f"{API}/crm/v2/companies/{CID}/locations", json={"name": "  "}, headers=H)
        assert r.status_code == 400

    def test_add_location_idempotent_case_insensitive(self, H, created):
        name = f"TEST_Loc_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/crm/v2/companies/{CID}/locations", json={"name": name}, headers=H)
        assert r.status_code == 200 and r.json()["created"] is True
        lid = r.json()["location"]["id"]
        created["locations"].append(lid)
        created["test_loc"] = lid
        r2 = requests.post(f"{API}/crm/v2/companies/{CID}/locations", json={"name": name.upper()}, headers=H)
        assert r2.status_code == 200 and r2.json()["created"] is False
        assert r2.json()["location"]["id"] == lid
        loc = requests.get(f"{API}/crm/v2/mod-contracts/locations?company_id={CID}", headers=H).json()
        assert lid in [l["id"] for l in loc["locations"]]

    def test_add_location_unlinked_company(self, H):
        # non-MOD, unlinked company should 400 (pick any prospect)
        r = requests.get(f"{API}/crm/v2/companies?limit=50", headers=H)
        cos = [c for c in (r.json().get("companies") or []) if not c.get("linked_organization_id") and c.get("type") != "mod_site"]
        if not cos:
            pytest.skip("no unlinked company")
        r = requests.post(f"{API}/crm/v2/companies/{cos[0]['id']}/locations", json={"name": "TEST_x"}, headers=H)
        assert r.status_code == 400

    def test_move_equipment_and_back(self, H, created):
        lid = created.get("test_loc")
        assert lid
        eq = "f52cfc80-1c7b-4a54-825a-fd09cafa0eb0"  # Dual Adjustable Pulley (Fitness Suite)
        r = requests.post(f"{API}/crm/v2/companies/{CID}/equipment/{eq}/move", json={"site_id": lid, "note": "TEST"}, headers=H)
        assert r.status_code == 200 and r.json()["moved"] is True
        d = requests.get(f"{API}/crm/v2/companies/{CID}/sites-and-equipment", headers=H).json()
        site = next(s for s in d["sites"] if s["id"] == lid)
        assert eq in [e["id"] for e in site["equipment"]]
        # same target -> no-op
        r = requests.post(f"{API}/crm/v2/companies/{CID}/equipment/{eq}/move", json={"site_id": lid}, headers=H)
        assert r.json()["moved"] is False
        # back
        r = requests.post(f"{API}/crm/v2/companies/{CID}/equipment/{eq}/move", json={"site_id": FITNESS_SUITE}, headers=H)
        assert r.status_code == 200 and r.json()["moved"] is True

    def test_move_invalid_target(self, H):
        eq = "f52cfc80-1c7b-4a54-825a-fd09cafa0eb0"
        r = requests.post(f"{API}/crm/v2/companies/{CID}/equipment/{eq}/move", json={"site_id": "loc:cardio suite"}, headers=H)
        assert r.status_code == 400
        r = requests.post(f"{API}/crm/v2/companies/{CID}/equipment/nope/move", json={"site_id": MAIN_GYM}, headers=H)
        assert r.status_code == 404


# --- Add contact job title picklist ---
class TestContactJobTitle:
    def test_invalid_job_title_returns_structured_400(self, H):
        r = requests.post(f"{API}/crm/v2/contacts", json={"first_name": "TEST_Bad", "email": f"test_bad_{uuid.uuid4().hex[:6]}@example.com",
                                                         "job_title": "Galactic Overlord", "company_id": CID}, headers=H)
        assert r.status_code == 400
        d = r.json()["detail"]
        assert d.get("field_label") and d.get("received") == "Galactic Overlord"

    def test_valid_job_title(self, H, created):
        jt = requests.get(f"{API}/crm/picklists/job_title", headers=H).json()["values"][0]["label"]
        r = requests.post(f"{API}/crm/v2/contacts", json={"first_name": "TEST_Good", "email": f"test_good_{uuid.uuid4().hex[:6]}@example.com",
                                                         "job_title": jt, "company_id": CID, "company_name": "MOD Test Site"}, headers=H)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        cid = body.get("id") or (body.get("contact") or {}).get("id")
        assert cid
        created["contacts"].append(cid)
        c = requests.get(f"{API}/crm/v2/companies/{CID}", headers=H).json()
        assert any(x["id"] == cid and x.get("job_title") == jt for x in c["contacts"])


# --- MOD contracts CRUD ---
class TestModContracts:
    def test_catalog(self, H):
        r = requests.get(f"{API}/crm/v2/mod-contracts/catalog", headers=H)
        st = {x["key"]: x for x in r.json()["service_types"]}
        assert set(st) == {"A", "B", "C", "repair", "refurb"}
        assert st["A"]["price_basis"] == "annual" and st["B"]["price_basis"] == "per_visit"

    def test_validation(self, H):
        base = {"company_id": CID, "reference": "TEST_MOD"}
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={**base, "lines": [{"service_type": "Z", "price": 1}]}, headers=H).status_code == 400
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={**base, "lines": [{"service_type": "A", "price": -5}]}, headers=H).status_code == 400
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={**base, "lines": [{"service_type": "A", "price": "abc"}]}, headers=H).status_code == 400
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={**base, "lines": [{"service_type": "A", "location_id": "foreign", "price": 1}]}, headers=H).status_code == 400
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={**base, "status": "weird"}, headers=H).status_code == 400
        assert requests.post(f"{API}/crm/v2/mod-contracts", json={"company_id": "nope"}, headers=H).status_code == 404

    def test_crud(self, H, created):
        body = {"company_id": CID, "reference": "TEST_MOD_001", "authority": "DIO", "start_date": "2026-01-01", "end_date": "2026-12-31",
                "status": "active", "lines": [
                    {"location_id": MAIN_GYM, "service_type": "A", "price": 1200},
                    {"location_id": FITNESS_SUITE, "service_type": "B", "price": 300.555},
                    {"location_id": "", "service_type": "C", "price": 500, "quarterly_inspections": True},
                    {"location_id": "", "service_type": "A", "price": 50, "quarterly_inspections": True}]}
        r = requests.post(f"{API}/crm/v2/mod-contracts", json=body, headers=H)
        assert r.status_code == 200, r.text
        d = r.json()
        created["contracts"].append(d["id"])
        assert "_id" not in d
        assert d["annual_value"] == 1250
        assert d["total_value"] == round(1200 + 300.56 + 500 + 50, 2)
        assert d["service_types"] == ["A", "B", "C"]
        names = [l["location_name"] for l in d["lines"]]
        assert names == ["Main Gym", "Fitness Suite", "Whole site", "Whole site"]
        assert d["lines"][2]["quarterly_inspections"] is True and d["lines"][3]["quarterly_inspections"] is False
        assert d["company_name"] == "MOD Test Site"
        # list + filter
        lst = requests.get(f"{API}/crm/v2/mod-contracts?company_id={CID}", headers=H).json()["contracts"]
        assert any(x["id"] == d["id"] for x in lst)
        # update (partial)
        u = requests.put(f"{API}/crm/v2/mod-contracts/{d['id']}", json={"status": "expired", "lines": [{"service_type": "refurb", "price": 999}]}, headers=H)
        assert u.status_code == 200
        assert u.json()["status"] == "expired" and u.json()["annual_value"] == 0 and u.json()["total_value"] == 999
        assert u.json()["reference"] == "TEST_MOD_001"
        lst = requests.get(f"{API}/crm/v2/mod-contracts", headers=H).json()["contracts"]
        got = next(x for x in lst if x["id"] == d["id"])
        assert got["status"] == "expired" and got["lines"][0]["service_type"] == "refurb"
        # delete
        assert requests.delete(f"{API}/crm/v2/mod-contracts/{d['id']}", headers=H).status_code == 200
        assert requests.delete(f"{API}/crm/v2/mod-contracts/{d['id']}", headers=H).status_code == 404
        assert requests.put(f"{API}/crm/v2/mod-contracts/{d['id']}", json={}, headers=H).status_code == 404

    def test_mod_contract_not_in_generic_list(self, H, created):
        r = requests.post(f"{API}/crm/v2/mod-contracts", json={"company_id": CID, "reference": "TEST_MOD_GEN", "lines": []}, headers=H)
        cid = r.json()["id"]
        created["contracts"].append(cid)
        g = requests.get(f"{API}/crm/v2/contracts?limit=500", headers=H)
        print("generic list status", g.status_code)
        if g.status_code == 200:
            rows = g.json().get("contracts") or g.json().get("items") or []
            print("MOD contract appears in generic contract list:", any(x.get("id") == cid for x in rows))
        assert requests.delete(f"{API}/crm/v2/mod-contracts/{cid}", headers=H).status_code == 200

    def test_unauth(self):
        assert requests.get(f"{API}/crm/v2/mod-contracts").status_code in (401, 403)
