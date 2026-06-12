"""Iter 256 — Provider-native desk Customers tab.

/api/service-desk/provider-customers (require_service_desk, org-scoped):
list/search, detail with recent cases (matched by email or exact name —
links the iter-255 imported history), create/patch/delete, tenant
isolation, auth guard. Frontend swaps the desk Customers tab to this
surface when user.account_type === 'service_provider'.
"""

import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

PROVIDER = ("sp.fe.1781277405@example.com", "Str0ngPass!23")
MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")

_TAG = uuid.uuid4().hex[:6]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth():
    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers", timeout=20)
    assert r.status_code in (401, 403)


def test_crud_and_search():
    h = _login(*PROVIDER)
    name = f"PC Test Gym {_TAG}"
    r = requests.post(f"{BASE_URL}/api/service-desk/provider-customers", headers=h,
                      json={"name": name, "email": f"pc.{_TAG}@example.com",
                            "postcode": "M1 1AA", "site_name": "Main"}, timeout=20)
    assert r.status_code == 201, r.text
    cid = r.json()["customer"]["id"]

    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers",
                     headers=h, params={"q": _TAG}, timeout=20)
    assert r.status_code == 200
    assert any(c["id"] == cid for c in r.json()["customers"])

    r = requests.patch(f"{BASE_URL}/api/service-desk/provider-customers/{cid}",
                       headers=h, json={"phone": "0161 000"}, timeout=20)
    assert r.status_code == 200 and r.json()["customer"]["phone"]

    # Empty patch → 400
    r = requests.patch(f"{BASE_URL}/api/service-desk/provider-customers/{cid}",
                       headers=h, json={}, timeout=20)
    assert r.status_code == 400

    r = requests.delete(f"{BASE_URL}/api/service-desk/provider-customers/{cid}",
                        headers=h, timeout=20)
    assert r.status_code == 200 and r.json()["ok"] is True

    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers/{cid}",
                     headers=h, timeout=20)
    assert r.status_code == 404


def test_detail_links_imported_cases():
    """'Acme Gyms Ltd' was imported in iter 255 with closed case J-1001 —
    the detail endpoint must surface it by exact-name match."""
    h = _login(*PROVIDER)
    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers",
                     headers=h, params={"q": "Acme Gyms"}, timeout=20)
    rows = r.json()["customers"]
    assert rows, "iter-255 imported customer missing"
    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers/{rows[0]['id']}",
                     headers=h, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case_count"] >= 1
    refs = [c["reference"] for c in d["recent_cases"]]
    assert "J-1001" in refs
    assert all(c["status"] in ("closed", "invoiced") for c in d["recent_cases"])


def test_tenant_isolation():
    h_admin = _login(*MASTER_ADMIN)
    r = requests.get(f"{BASE_URL}/api/service-desk/provider-customers",
                     headers=h_admin, params={"q": "Acme Gyms"}, timeout=20)
    assert r.status_code == 200
    assert r.json()["total"] == 0  # provider's book is invisible to other orgs
