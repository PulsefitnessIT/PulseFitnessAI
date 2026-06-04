"""Iter 220 P1 — Master Admin can switch an org's CRM between Gym (leisure)
and Corporate (business) via the Feature Control Panel / features endpoint.

Regression for the bug where `modules.crm.business_enabled` sent to
PUT /master-admin/organizations/{id}/features was silently dropped, so an
org (Pulse Fitness) could never be switched to Corporate.
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MA_EMAIL, MA_PASS = "admin@gymaxisai.com", "MasterAdmin123!"


@pytest.fixture(scope="module")
def ma_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": MA_EMAIL, "password": MA_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def org_id(ma_headers):
    # find a CRM-capable org to flip (prefer Pulse Fitness)
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations?limit=500", headers=ma_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    orgs = data.get("organizations") if isinstance(data, dict) else data
    pulse = next((o for o in orgs if "pulse" in (o.get("name", "").lower())), None)
    target = pulse or (orgs[0] if orgs else None)
    if not target:
        pytest.skip("no organizations available")
    return target["id"]


def _set_business(ma_headers, org_id, on: bool):
    return requests.put(
        f"{BASE_URL}/api/master-admin/organizations/{org_id}/features",
        headers=ma_headers,
        json={"modules": {"crm": {"enabled": True, "tier": "pro", "business_enabled": on}}},
        timeout=30,
    )


def _read_crm_module(ma_headers, org_id):
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations?limit=500", headers=ma_headers, timeout=30)
    data = r.json()
    orgs = data.get("organizations") if isinstance(data, dict) else data
    o = next(x for x in orgs if x["id"] == org_id)
    return (o.get("modules") or {}).get("crm") or {}


def test_master_admin_can_enable_corporate(ma_headers, org_id):
    try:
        assert _set_business(ma_headers, org_id, True).status_code == 200
        crm = _read_crm_module(ma_headers, org_id)
        assert crm.get("business_enabled") is True
        assert crm.get("enabled") is True  # business implies CRM enabled
    finally:
        _set_business(ma_headers, org_id, True)  # leave it on (intended state for Pulse)


def test_master_admin_can_disable_corporate(ma_headers, org_id):
    try:
        assert _set_business(ma_headers, org_id, False).status_code == 200
        crm = _read_crm_module(ma_headers, org_id)
        assert crm.get("business_enabled") is False
        assert crm.get("enabled") is True  # CRM itself stays on
    finally:
        _set_business(ma_headers, org_id, True)  # restore Corporate
