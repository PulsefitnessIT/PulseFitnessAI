"""Test MOD org creation (Task 2 backend) + non-MOD regression."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://aftersales-engine.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


created_ids = []


def test_create_mod_org_raf(client):
    payload = {
        "name": f"ZZ QA MOD RAF (test) {int(time.time())}",
        "account_type": "mod_site",
        "subscription_tier": "mod_site",
        "is_mod": True,
        "mod_force": "raf",
        "enabled_modules": ["operations"],
        "industry": "Defence — Royal Air Force",
        "primary_contact_email": f"qa+mod+raf+{int(time.time())}@example.com",
        "primary_contact_name": "QA MOD Contact",
    }
    r = client.post(f"{BASE_URL}/api/master-admin/organizations", json=payload, timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    org_id = data["id"]
    created_ids.append(org_id)
    assert data["enabled_modules"] == ["operations"], f"got {data['enabled_modules']}"
    assert data["is_mod"] is True
    assert data["mod_force"] == "raf"
    assert data["industry"] == "Defence — Royal Air Force"
    assert data["account_type"] == "mod_site"

    # GET verify persistence via org list
    lr = client.get(f"{BASE_URL}/api/master-admin/organizations", timeout=60)
    assert lr.status_code == 200
    orgs = lr.json()
    orgs_list = orgs if isinstance(orgs, list) else orgs.get("organizations", orgs.get("items", []))
    found = next((o for o in orgs_list if o.get("id") == org_id), None)
    assert found is not None, "created org not found in list"
    assert found.get("enabled_modules") == ["operations"]
    assert found.get("industry") == "Defence — Royal Air Force"


def test_create_mod_org_army(client):
    payload = {
        "name": f"ZZ QA MOD ARMY (test) {int(time.time())}",
        "account_type": "mod_site",
        "is_mod": True,
        "mod_force": "army",
        "enabled_modules": ["operations"],
        "industry": "Defence — British Army",
    }
    r = client.post(f"{BASE_URL}/api/master-admin/organizations", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    created_ids.append(d["id"])
    assert d["enabled_modules"] == ["operations"]
    assert d["mod_force"] == "army"
    assert d["industry"] == "Defence — British Army"


def test_create_nonmod_org_multi_modules_regression(client):
    payload = {
        "name": f"ZZ QA STD (test) {int(time.time())}",
        "account_type": "full",
        "subscription_tier": "starter",
        "is_mod": False,
        "enabled_modules": ["operations", "crm", "memberships", "marketing"],
        "industry": "Health & Fitness",
    }
    r = client.post(f"{BASE_URL}/api/master-admin/organizations", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    created_ids.append(d["id"])
    assert set(d["enabled_modules"]) == {"operations", "crm", "memberships", "marketing"}
    assert d["is_mod"] is False
    assert d["industry"] == "Health & Fitness"


def test_invalid_mod_force_rejected(client):
    payload = {
        "name": f"ZZ QA MOD BAD {int(time.time())}",
        "account_type": "mod_site",
        "is_mod": True,
        "mod_force": "space_force",
        "enabled_modules": ["operations"],
    }
    r = client.post(f"{BASE_URL}/api/master-admin/organizations", json=payload, timeout=60)
    assert r.status_code == 400


def test_cleanup(client):
    # Best-effort cleanup
    for oid in created_ids:
        try:
            client.delete(f"{BASE_URL}/api/master-admin/organizations/{oid}", timeout=30)
        except Exception:
            pass
