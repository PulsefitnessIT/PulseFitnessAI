# Retest of iteration_280 fixes: auth bypass 403, emailed null on Resend failure, no duplicates, estate scoping, $literal
import os

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
OTHER_SITE = "382db6bd-4c27-413d-a8e8-35e5a33940f0"
EST_ID = "f339c46a-f2c2-4508-81ed-b11d44551b5c"
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw, portal=None):
    _db.rate_buckets.delete_many({"_id": {"$regex": "^login"}})
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/auth/login", json=body, timeout=20)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def site_h():
    return _login("test@army.mod.test", "ModTest123!", "mod")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    _db.suppliers.delete_many({"organization_id": SITE_ID, "name": {"$regex": "^(TEST_|\\$)"}})


class TestAuthBypassFixed:
    @pytest.mark.parametrize("site", [SITE_ID, OTHER_SITE])
    @pytest.mark.parametrize("body", [{"estate_supplier_id": "nope"}, {"clear": True}, {}])
    def test_mod_site_user_403(self, site_h, site, body):
        r = requests.put(f"{BASE_URL}/master-admin/mod-estate/sites/{site}/service-provider",
                         json=body, headers=site_h, timeout=20)
        assert r.status_code == 403, r.text

    def test_unauth_401(self):
        r = requests.put(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/service-provider", json={"clear": True})
        assert r.status_code in (401, 403)

    def test_iso_demo_owner(self):
        """Non-MOD operator org owner — informational: does it pass the guard?"""
        h = _login("owner@isodemo.com", "IsoDemo123!")
        r = requests.put(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/service-provider",
                         json={"estate_supplier_id": "does-not-exist"}, headers=h, timeout=20)
        print("iso-demo owner status:", r.status_code, r.text[:200])
        assert r.status_code == 403, f"non-MOD-org owner passes guard: {r.status_code} {r.text}"


class TestListing:
    def test_no_duplicate_names(self, site_h):
        r = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20)
        assert r.status_code == 200
        o = r.json()["options"]
        names = [p["name"].strip().lower() for p in o["providers"]] + [s["name"].strip().lower() for s in o["third_party"]]
        assert len(names) == len(set(names)), names
        assert sum(1 for n in names if n == "inda fitness") <= 1

    def test_providers_scoped_to_estate(self, site_h):
        org = _db.organizations.find_one({"id": SITE_ID}, {"_id": 0, "mod_estate_id": 1})
        r = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20)
        ids = {p["id"] for p in r.json()["options"]["providers"]}
        est = org.get("mod_estate_id")
        if est:
            for pid in ids:
                assert _db.mod_estate_suppliers.find_one({"id": pid})["mod_estate_id"] == est

    def test_foreign_estate_provider_404(self, site_h):
        org = _db.organizations.find_one({"id": SITE_ID}, {"_id": 0, "mod_estate_id": 1})
        other = _db.mod_estate_suppliers.find_one({"mod_estate_id": {"$ne": org.get("mod_estate_id") or "uk-mod"}}, {"_id": 0, "id": 1})
        if not other:
            pytest.skip("no provider in another estate")
        eq = _db.equipment.find_one({"organization_id": SITE_ID}, {"_id": 0, "id": 1})
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign",
                          json={"equipment_ids": [eq["id"]], "target": f"provider:{other['id']}"}, headers=site_h, timeout=20)
        assert r.status_code == 404, r.text


class TestEmailedAndLiteral:
    def test_emailed_null_and_dollar_name(self, site_h):
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/third-party",
                          json={"name": "$ave Repairs", "email": "test_dollar@example.com"}, headers=site_h, timeout=20)
        assert r.status_code == 200, r.text
        sid = r.json()["supplier"]["id"]
        eq = [e["id"] for e in _db.equipment.find({"organization_id": SITE_ID}, {"_id": 0, "id": 1}).limit(2)]
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign",
                          json={"equipment_ids": eq, "target": f"supplier:{sid}"}, headers=site_h, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        print("bulk resp:", d)
        assert d["emailed"] is None  # Resend key invalid in preview
        for e in _db.equipment.find({"id": {"$in": eq}}, {"_id": 0}):
            assert e["supplier"] == "$ave Repairs" and e["supplier_id"] == sid and e["supplier_override"] is True
        # reset
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign",
                          json={"equipment_ids": eq, "target": "site_default"}, headers=site_h, timeout=30)
        assert r.status_code == 200
