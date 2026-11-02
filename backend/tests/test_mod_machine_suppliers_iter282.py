# Iter282 retest: _can_manage_mod_site operator-company authz + follows-default display name normalisation
import os

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
EST_ID = "f339c46a-f2c2-4508-81ed-b11d44551b5c"
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SP = f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/service-provider"


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
def admin_h():
    return _login("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")


@pytest.fixture(scope="module")
def iso_h():
    return _login("owner@isodemo.com", "IsoDemo123!")


@pytest.fixture(scope="module")
def site_h():
    return _login("test@army.mod.test", "ModTest123!", "mod")


@pytest.fixture(scope="module")
def op_h():
    return _login("portal@pulsefitness.ltd", "PulseFleet123!")


# Non-operator owner must be blocked everywhere
class TestNonOperatorBlocked:
    @pytest.mark.parametrize("body", [{"estate_supplier_id": EST_ID}, {"clear": True}, {"name": "TEST_x"}])
    def test_iso_owner_put_provider_403(self, iso_h, body):
        r = requests.put(SP, json=body, headers=iso_h, timeout=20)
        assert r.status_code == 403, r.text

    def test_iso_owner_readiness_403(self, iso_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/site-readiness", headers=iso_h, timeout=30)
        assert r.status_code == 403, r.text

    def test_iso_owner_equipment_by_cat_403(self, iso_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/site/{SITE_ID}/equipment-by-category",
                         params={"category": "Cardio"}, headers=iso_h, timeout=20)
        assert r.status_code == 403, r.text

    def test_iso_owner_sla_403(self, iso_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/sla", headers=iso_h, timeout=20)
        assert r.status_code == 403, r.text

    def test_iso_owner_delete_403(self, iso_h):
        r = requests.delete(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}",
                            params={"confirm_name": "nope"}, headers=iso_h, timeout=20)
        assert r.status_code == 403, r.text
        assert _db.organizations.find_one({"id": SITE_ID}) is not None

    def test_mod_site_user_still_403(self, site_h):
        r = requests.put(SP, json={"clear": True}, headers=site_h, timeout=20)
        assert r.status_code == 403


# Master admin + operator-company owner still allowed
class TestAllowed:
    def test_admin_readiness(self, admin_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/site-readiness", headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:300]

    def test_admin_equipment_by_cat(self, admin_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/site/{SITE_ID}/equipment-by-category",
                         params={"category": "Uncategorised"}, headers=admin_h, timeout=20)
        assert r.status_code == 200 and r.json()["site_id"] == SITE_ID

    def test_admin_sla(self, admin_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/sla", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text

    def test_admin_delete_guard_wrong_name(self, admin_h):
        r = requests.delete(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}",
                            params={"confirm_name": "WRONG NAME"}, headers=admin_h, timeout=20)
        assert r.status_code in (400, 409, 422), r.text
        assert _db.organizations.find_one({"id": SITE_ID}) is not None

    def test_operator_owner_passes_guard(self, op_h):
        r = requests.get(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/sla", headers=op_h, timeout=20)
        assert r.status_code == 200, r.text

    def test_admin_assign_then_clear(self, admin_h, site_h):
        r = requests.put(SP, json={"estate_supplier_id": EST_ID}, headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["machines_moved"] == 8
        lst = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20).json()
        assert lst["site_default"] and all(m["supplier"] == "Inda Fitness" for m in lst["machines"])
        r = requests.put(SP, json={"clear": True}, headers=admin_h, timeout=30)
        assert r.status_code == 200 and r.json()["cleared"] is True
        lst = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20).json()
        assert lst["site_default"] is None
        # (2) every default-following row reads Pulse Fitness (MOD Service)
        for m in lst["machines"]:
            if m["follows_default"]:
                assert m["supplier"] == "Pulse Fitness (MOD Service)", m


# Display-name normalisation with legacy stored text
class TestDisplayName:
    def test_legacy_supplier_text_normalised(self, site_h):
        _db.equipment.update_many({"organization_id": SITE_ID}, {"$set": {"supplier": "Pulse Fitness"}})
        lst = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20).json()
        fd = [m for m in lst["machines"] if m["follows_default"]]
        assert fd, "no default-following machines"
        assert all(m["supplier"] == "Pulse Fitness (MOD Service)" for m in fd), [m["supplier"] for m in fd]
