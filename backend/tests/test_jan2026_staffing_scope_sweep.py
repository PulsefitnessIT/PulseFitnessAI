# Sweep: every /api/staffing GET list endpoint must not expose Site B staff (deptdemo-sales-b) to the Site-A manager
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MARKERS = ("deptdemo-sales-b", "Sid Sales B", "sales.b@isodemo")
PATHS = [p.strip() for p in open("/tmp/staffing_gets.txt") if p.strip()] if os.path.exists("/tmp/staffing_gets.txt") else []


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "IsoDemo123!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip("login failed")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login("owner@isodemo.com")


@pytest.fixture(scope="module")
def manager():
    return _login("manager@isodemo.com")


@pytest.fixture(scope="module")
def visible(manager):
    d = manager.get(f"{BASE_URL}/api/staffing/staff", timeout=30).json()
    lst = d if isinstance(d, list) else d.get("staff") or d.get("items") or []
    return {s["id"] for s in lst}


@pytest.mark.parametrize("path", PATHS)
def test_no_site_b_leak(owner, manager, visible, path):
    ro = owner.get(f"{BASE_URL}/api{path}", timeout=60)
    rm = manager.get(f"{BASE_URL}/api{path}", timeout=60)
    owner_has = any(m in ro.content.decode("latin-1") for m in MARKERS)
    body = rm.content.decode("latin-1")
    leak = [m for m in MARKERS if m in body]
    ids = set(re.findall(r'"staff(?:_member)?_id"\s*:\s*"([^"]+)"', body)) - visible
    print(f"{path}: owner={ro.status_code}/{owner_has} manager={rm.status_code} leak={leak} extra_ids={len(ids)}")
    assert rm.status_code < 500, f"{path} 5xx {rm.text[:200]}"
    assert not leak, f"{path} leaks Site B staff to manager"
