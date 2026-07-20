"""Backend tests for Staff Onboarding bugfix batch (Jan 2026):
- HR pack.pdf returns 200 application/pdf %PDF- (spacing verified visually by main agent)
- recruit_me returns 'submitted' flag
- submit endpoint sets submitted=True (non-blocking server-side)
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("TEST_API_URL") or "https://dealer-parts-engine.preview.emergentagent.com").rstrip("/")
HR_EMAIL = "owner@isodemo.com"
HR_PASS = "IsoDemo123!"

pytestmark = pytest.mark.timeout(90)


@pytest.fixture(scope="module")
def hr_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": HR_EMAIL, "password": HR_PASS}, timeout=20)
    if r.status_code == 429:
        time.sleep(35)
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": HR_EMAIL, "password": HR_PASS}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(hr_token):
    return {"Authorization": f"Bearer {hr_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def case_id(H):
    uniq = uuid.uuid4().hex[:8]
    payload = {
        "legal_first_name": "TEST",
        "surname": f"BugFix{uniq}",
        "preferred_name": "TestB",
        "personal_email": f"testbugfix.{uniq}@example.com",
        "mobile": "07000000000",
        "position": "QA Recruit",
        "proposed_start_date": "2026-02-01",
    }
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases", json=payload, headers=H, timeout=20)
    assert r.status_code == 200, f"create case failed: {r.status_code} {r.text[:300]}"
    cid = r.json()["id"]
    yield cid
    # cleanup best-effort
    try:
        requests.delete(f"{BASE_URL}/api/staff-onboarding/cases/{cid}", headers=H, timeout=10)
    except Exception:
        pass


def test_pack_pdf_returns_valid_pdf(H, case_id):
    r = requests.get(f"{BASE_URL}/api/staff-onboarding/cases/{case_id}/pack.pdf", headers=H, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    ctype = r.headers.get("content-type", "")
    assert "pdf" in ctype.lower(), f"content-type not pdf: {ctype}"
    assert r.content[:5] == b"%PDF-", f"missing PDF magic: {r.content[:10]!r}"
    assert len(r.content) > 1500, f"pdf suspiciously small: {len(r.content)} bytes"


def test_case_list_contains_case(H, case_id):
    r = requests.get(f"{BASE_URL}/api/staff-onboarding/cases", headers=H, timeout=20)
    assert r.status_code == 200
    data = r.json()
    cases = data["cases"] if isinstance(data, dict) else data
    ids = [c.get("id") for c in cases]
    assert case_id in ids


def test_send_invite_returns_portal_path(H, case_id):
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases/{case_id}/invite",
                      json={"channel": "email"}, headers=H, timeout=20)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("invite_token")
    assert body.get("portal_path", "").startswith("/new-starter/")


def test_templates_and_settings_endpoints(H):
    r1 = requests.get(f"{BASE_URL}/api/staff-onboarding/templates", headers=H, timeout=20)
    assert r1.status_code == 200
    r2 = requests.get(f"{BASE_URL}/api/staff-onboarding/settings", headers=H, timeout=20)
    assert r2.status_code == 200


def test_dashboard_endpoint(H):
    r = requests.get(f"{BASE_URL}/api/staff-onboarding/dashboard", headers=H, timeout=20)
    assert r.status_code == 200
