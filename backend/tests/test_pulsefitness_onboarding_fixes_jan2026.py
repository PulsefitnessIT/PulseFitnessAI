"""Backend tests for PulseFitness onboarding fixes (Jan 2026):
Bug1: site cap raised from 50 → 500 in POST /api/master-admin/onboard-head-office
Bug3: CSV template Content-Disposition uses pulsefitness-* (not gymaxis-*)
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def token():
    t = open("/tmp/tok").read().strip()
    assert t
    return t


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_sites(n: int):
    sites = []
    for i in range(n):
        sites.append({
            "name": f"TEST Site {i+1} {uuid.uuid4().hex[:6]}",
            "address_line1": f"{i+1} Test Rd",
            "city": "London",
            "postcode": "SW1A 1AA",
            "country": "United Kingdom",
            "is_head_office": (i == 0),
        })
    return sites


# ── Bug1: 60 sites should succeed ─────────────────────────────────────
def test_onboard_60_sites_success(headers):
    email = f"TEST_owner_{uuid.uuid4().hex[:10]}@example.com"
    payload = {
        "org_name": f"TEST Multi Org {uuid.uuid4().hex[:8]}",
        "tier": "lite",
        "owner_email": email,
        "owner_name": "Test Owner",
        "owner_password": "TempPass1234!",
        "sites": _make_sites(60),
    }
    r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=headers, timeout=120)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    data = r.json()
    assert data.get("success") is True
    assert data["organization"]["site_count"] == 60
    assert len(data["sites"]) == 60


# ── Bug1: 501 sites should be rejected with new 500-cap message ───────
def test_onboard_501_sites_rejected(headers):
    email = f"TEST_owner_{uuid.uuid4().hex[:10]}@example.com"
    payload = {
        "org_name": f"TEST Overflow Org {uuid.uuid4().hex[:8]}",
        "tier": "lite",
        "owner_email": email,
        "owner_name": "Test Owner",
        "owner_password": "TempPass1234!",
        "sites": _make_sites(501),
    }
    r = requests.post(f"{BASE_URL}/api/master-admin/onboard-head-office", json=payload, headers=headers, timeout=60)
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "500" in detail, f"Expected 500-cap message, got: {detail}"


# ── Bug3: CSV template filenames ──────────────────────────────────────
def test_sites_csv_template_filename(headers):
    r = requests.get(f"{BASE_URL}/api/master-admin/sites/template.csv", headers=headers, timeout=30)
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "pulsefitness-sites-template.csv" in cd, f"Content-Disposition: {cd}"
    assert "gymaxis" not in cd.lower()


def test_equipment_csv_template_filename(headers):
    r = requests.get(f"{BASE_URL}/api/master-admin/equipment/template.csv", headers=headers, timeout=30)
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "pulsefitness-equipment-template.csv" in cd, f"Content-Disposition: {cd}"
    assert "gymaxis" not in cd.lower()
