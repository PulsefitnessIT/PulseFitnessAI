"""
Backend tests for the New Starter Portal "returning login" bug fix (Jan 2026).

Flow under test:
  GET  /api/new-starter/invite/{token}   -> {found, accepted, full_name}
  POST /api/new-starter/accept-invite    -> 200 first time, 409 once already accepted
  POST /api/new-starter/login            -> 200 with correct password, 401 with wrong
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
HR_EMAIL = "owner@isodemo.com"
HR_PASS = "IsoDemo123!"
RECRUIT_PASSWORD = "Recruit123!"


# ---------------------------------------------------------------------------
# HR auth (rate-limited login → reuse a single session/token for the module)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def hr_token():
    for attempt in range(4):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": HR_EMAIL, "password": HR_PASS}, timeout=30)
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(35)
            continue
        pytest.skip(f"HR login failed: {r.status_code} {r.text}")
    pytest.skip("HR login rate-limited")


@pytest.fixture(scope="module")
def hr_headers(hr_token):
    return {"Authorization": f"Bearer {hr_token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Create a fresh onboarding case + invite (unique per run to avoid collisions)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def invite(hr_headers):
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_nsp_{uniq}@example.com"
    body = {
        "title": "Mr",
        "legal_first_name": "Test",
        "surname": f"Recruit{uniq}",
        "preferred_name": "Testy",
        "personal_email": email,
        "mobile": "07000000000",
        "position": "Trainer",
        "proposed_start_date": "2026-02-01",
    }
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases",
                      headers=hr_headers, json=body, timeout=30)
    assert r.status_code in (200, 201), f"create case: {r.status_code} {r.text}"
    case = r.json()
    case_id = case["id"]

    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases/{case_id}/invite",
                      headers=hr_headers, json={"expiry_days": 14}, timeout=30)
    assert r.status_code == 200, f"invite: {r.status_code} {r.text}"
    token = r.json()["invite_token"]
    assert isinstance(token, str) and len(token) >= 32

    yield {"token": token, "case_id": case_id, "email": email}


# ---------------------------------------------------------------------------
# Tests (ordered — pytest runs top-to-bottom within a module by default)
# ---------------------------------------------------------------------------
def test_invite_status_before_setup(invite):
    r = requests.get(f"{BASE_URL}/api/new-starter/invite/{invite['token']}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["found"] is True
    assert data["accepted"] is False
    assert data.get("full_name")  # returned even before accept


def test_invite_status_unknown_token():
    r = requests.get(f"{BASE_URL}/api/new-starter/invite/does-not-exist", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"found": False} or r.json().get("found") is False


def test_login_before_setup_rejected(invite):
    r = requests.post(f"{BASE_URL}/api/new-starter/login",
                      json={"token": invite["token"], "password": RECRUIT_PASSWORD}, timeout=15)
    assert r.status_code == 400, f"expected 400 (password not set yet), got {r.status_code}: {r.text}"


def test_accept_invite_first_time(invite):
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": invite["token"], "password": RECRUIT_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("token"), str) and len(data["token"]) > 10
    assert data["user"]["role"] == "recruit"
    # cache the recruit token for the /me regression check
    invite["recruit_jwt"] = data["token"]


def test_invite_status_after_setup(invite):
    r = requests.get(f"{BASE_URL}/api/new-starter/invite/{invite['token']}", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is True
    assert data["accepted"] is True, f"invite should be accepted after setup: {data}"


def test_accept_invite_again_returns_409(invite):
    """Core bug fix — no silent password reset for a returning user."""
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": invite["token"], "password": "SomethingElse123!"},
                      timeout=15)
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"


def test_login_wrong_password(invite):
    r = requests.post(f"{BASE_URL}/api/new-starter/login",
                      json={"token": invite["token"], "password": "WrongPass999!"}, timeout=15)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_login_correct_password_returns_jwt(invite):
    r = requests.post(f"{BASE_URL}/api/new-starter/login",
                      json={"token": invite["token"], "password": RECRUIT_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("token"), str)
    assert data["user"]["role"] == "recruit"

    # The JWT should authorise the recruit /me endpoint.
    me = requests.get(f"{BASE_URL}/api/new-starter/me",
                      headers={"Authorization": f"Bearer {data['token']}"}, timeout=15)
    assert me.status_code == 200, f"/new-starter/me with fresh jwt: {me.status_code} {me.text}"
    assert "portal_name" in me.json() or "person" in me.json()


def test_login_unknown_token():
    r = requests.post(f"{BASE_URL}/api/new-starter/login",
                      json={"token": "not-a-real-token", "password": RECRUIT_PASSWORD}, timeout=15)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Cleanup — remove the TEST_ case/staff/user/invite we created
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(invite, hr_headers):
    yield
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        inv = db.staff_onboarding_invites.find_one({"token": invite["token"]})
        if inv:
            staff_id = inv.get("staff_id")
            staff = db.staff_members.find_one({"id": staff_id}) or {}
            user_id = staff.get("user_id")
            db.staff_onboarding_invites.delete_many({"token": invite["token"]})
            db.staff_onboarding_cases.delete_many({"id": invite["case_id"]})
            if staff_id:
                db.staff_members.delete_many({"id": staff_id})
            if user_id:
                db.users.delete_many({"id": user_id})
    except Exception as e:  # pragma: no cover
        print(f"cleanup warning: {e}")
