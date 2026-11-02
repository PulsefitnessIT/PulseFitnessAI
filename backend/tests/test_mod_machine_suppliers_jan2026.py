# MOD machine suppliers: site provider allocation (master admin) + site-staff bulk reassign
import os
import uuid

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


def _login(email, pw, portal=None):
    _db.rate_buckets.delete_many({"_id": {"$regex": "^login"}})
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/auth/login", json=body, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    if not tok:
        pytest.skip(f"no token for {email}: {r.json()}")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def site_h():
    return _login("test@army.mod.test", "ModTest123!", "mod")


@pytest.fixture(scope="module")
def admin_h():
    return _login("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    _db.suppliers.delete_many({"organization_id": SITE_ID, "name": {"$regex": "^TEST_"}})


def _eq():
    return {e["id"]: e for e in _db.equipment.find({"organization_id": SITE_ID}, {"_id": 0})}


def _put_provider(h, body):
    return requests.put(f"{BASE_URL}/master-admin/mod-estate/sites/{SITE_ID}/service-provider",
                        json=body, headers=h, timeout=30)


class TestFlow:
    state = {}

    def test_01_admin_assign_moves_all(self, admin_h):
        r = _put_provider(admin_h, {"estate_supplier_id": EST_ID})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["machines_moved"] == 8
        sid = d["service_supplier_id"]
        TestFlow.state["default_row"] = sid
        for e in _eq().values():
            assert e["supplier_id"] == sid and e["supplier_override"] is False and e["supplier_mode"] == "site_default"
            assert e["supplier"] == "Inda Fitness"

    def test_02_list(self, site_h):
        r = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["site_default"]["id"] == TestFlow.state["default_row"]
        assert len(d["machines"]) == 8 and all(m["follows_default"] for m in d["machines"])
        assert "pulse" in d["options"] and isinstance(d["options"]["providers"], list)
        assert any(p["id"] == EST_ID for p in d["options"]["providers"])
        assert not any("in-house" in p["name"].lower() for p in d["options"]["providers"])
        TestFlow.state["ids"] = [m["id"] for m in d["machines"]]

    def test_03_add_third_party(self, site_h):
        em = f"test_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/third-party", headers=site_h, timeout=20,
                          json={"name": "TEST_Local Fix", "email": em, "contact_name": "Bob", "phone": "0123"})
        assert r.status_code == 200, r.text
        TestFlow.state["tp"] = r.json()["supplier"]["id"]
        assert r.json()["supplier"]["email"] == em
        # validation
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/third-party", headers=site_h, json={"email": em})
        assert r.status_code == 400
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/third-party", headers=site_h,
                          json={"name": "TEST_x", "email": "bad"})
        assert r.status_code == 400
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/third-party", headers=site_h,
                          json={"name": "TEST_dup", "email": em.upper()})
        assert r.status_code == 409
        r = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h)
        assert any(s["id"] == TestFlow.state["tp"] for s in r.json()["options"]["third_party"])

    def test_04_bulk_validation(self, site_h):
        u = f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign"
        assert requests.post(u, headers=site_h, json={"equipment_ids": [], "target": "pulse"}).status_code == 400
        assert requests.post(u, headers=site_h, json={"equipment_ids": TestFlow.state["ids"][:1],
                                                       "target": "bogus"}).status_code == 400
        assert requests.post(u, headers=site_h, json={"equipment_ids": TestFlow.state["ids"][:1],
                                                       "target": "provider:nope"}).status_code == 404
        assert requests.post(u, headers=site_h, json={"equipment_ids": ["foreign-id"],
                                                       "target": "pulse"}).status_code == 404

    def test_05_bulk_pulse_third_party_and_foreign_ignored(self, site_h):
        u = f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign"
        ids = TestFlow.state["ids"]
        r = requests.post(u, headers=site_h, json={"equipment_ids": ids[:2] + ["foreign-x"], "target": "pulse"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 2
        r = requests.post(u, headers=site_h, json={"equipment_ids": ids[2:4],
                                                    "target": f"supplier:{TestFlow.state['tp']}"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["supplier"] == "TEST_Local Fix"
        eq = _eq()
        for i in ids[:2]:
            assert eq[i]["supplier_mode"] == "pulse" and eq[i]["supplier_override"] is True and eq[i]["supplier_id"] is None
        for i in ids[2:4]:
            assert eq[i]["supplier_id"] == TestFlow.state["tp"] and eq[i]["supplier_override"] is True
        lst = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=site_h).json()["machines"]
        m = {x["id"]: x for x in lst}
        assert m[ids[0]]["follows_default"] is False and m[ids[0]]["supplier"].startswith("Pulse")
        assert m[ids[5]]["follows_default"] is True

    def test_06_bulk_site_default(self, site_h):
        ids = TestFlow.state["ids"]
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign", headers=site_h,
                          json={"equipment_ids": [ids[3]], "target": "site_default"}, timeout=30)
        assert r.status_code == 200, r.text
        e = _eq()[ids[3]]
        assert e["supplier_override"] is False and e["supplier_id"] == TestFlow.state["default_row"]

    def test_07_provider_target_equals_default_not_override(self, site_h):
        ids = TestFlow.state["ids"]
        r = requests.post(f"{BASE_URL}/mod/site/machine-suppliers/bulk-reassign", headers=site_h,
                          json={"equipment_ids": [ids[6]], "target": f"provider:{EST_ID}"}, timeout=30)
        assert r.status_code == 200, r.text
        e = _eq()[ids[6]]
        assert e["supplier_override"] is False and e["supplier_id"] == TestFlow.state["default_row"]

    def test_08_reallocate_wipes_overrides(self, admin_h):
        r = _put_provider(admin_h, {"estate_supplier_id": EST_ID})
        assert r.status_code == 200, r.text
        for e in _eq().values():
            assert e["supplier_override"] is False and e["supplier_id"] == TestFlow.state["default_row"]
            assert e["supplier_mode"] == "site_default"

    def test_09_clear(self, admin_h):
        r = _put_provider(admin_h, {"clear": True})
        assert r.status_code == 200 and r.json()["cleared"] is True
        for e in _eq().values():
            assert e["supplier_id"] is None and e["supplier_override"] is False

    def test_10_non_mod_forbidden(self, admin_h):
        r = requests.get(f"{BASE_URL}/mod/site/machine-suppliers", headers=admin_h)
        assert r.status_code in (401, 403, 404), r.status_code
