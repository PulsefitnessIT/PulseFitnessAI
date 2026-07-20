"""E2E tests for staff portal login + forgot/reset password (Jan 2026).

Covers:
- POST /api/new-starter/staff-login (200 + JWT / 401 wrong)
- POST /api/new-starter/forgot-password (generic 200 for both known & unknown)
- POST /api/new-starter/reset-password (400 invalid, ok on valid, single-use)
- Regression: invite-based /api/new-starter/accept-invite still works
"""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") \
    else open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip().strip('"')
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"

TEST_TAG = f"TEST_{uuid.uuid4().hex[:8]}"
RECRUIT_EMAIL = f"test_staff_{TEST_TAG}@example.com".lower()
INITIAL_PASSWORD = "InitialPass123!"
NEW_PASSWORD = "NewPass456!"


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"owner login failed {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


created_ids = {"case_id": None, "staff_id": None, "user_id": None, "invite_id": None}


@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    # Teardown
    if created_ids["case_id"]:
        db.staff_onboarding_cases.delete_many({"id": created_ids["case_id"]})
        db.staff_onboarding_invites.delete_many({"onboarding_case_id": created_ids["case_id"]})
        db.staff_onboarding_audit.delete_many({"onboarding_case_id": created_ids["case_id"]})
    if created_ids["staff_id"]:
        db.staff_members.delete_many({"id": created_ids["staff_id"]})
    if created_ids["user_id"]:
        db.users.delete_many({"id": created_ids["user_id"]})
        db.staff_password_resets.delete_many({"user_id": created_ids["user_id"]})
    db.staff_members.delete_many({"email": RECRUIT_EMAIL})
    db.users.delete_many({"email": RECRUIT_EMAIL})


# ── setup: create case → invite → accept-invite (sets password) ────────────
def test_01_create_onboarding_case(owner_headers):
    payload = {
        "legal_first_name": "Testy",
        "surname": "McRecruit",
        "personal_email": RECRUIT_EMAIL,
        "position": "Fitness Instructor",
    }
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases",
                      json=payload, headers=owner_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    created_ids["case_id"] = data["id"]
    created_ids["staff_id"] = data["staff_id"]


def test_02_create_invite(owner_headers):
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/cases/{created_ids['case_id']}/invite",
                      json={"expiry_days": 7}, headers=owner_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("invite_token")
    created_ids["invite_token"] = data["invite_token"]


def test_03_accept_invite_sets_password(db):
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": created_ids["invite_token"], "password": INITIAL_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["user"]["role"] == "recruit"
    created_ids["user_id"] = data["user"]["id"]
    # persistence
    user = db.users.find_one({"id": created_ids["user_id"]})
    assert user and user.get("password")


# ── staff-login ─────────────────────────────────────────────────────────────
def test_04_staff_login_wrong_password_401():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": RECRUIT_EMAIL, "password": "wrong-password-x"}, timeout=20)
    assert r.status_code == 401, r.text
    assert "Incorrect" in r.text or "incorrect" in r.text.lower()


def test_05_staff_login_unknown_email_401():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": f"nobody_{TEST_TAG}@example.com", "password": "whatever123"}, timeout=20)
    assert r.status_code == 401


def test_06_staff_login_success():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": RECRUIT_EMAIL, "password": INITIAL_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 10
    assert data["user"]["id"] == created_ids["user_id"]


# ── forgot-password (no enumeration) ────────────────────────────────────────
def test_07_forgot_password_known_email_generic(db):
    r = requests.post(f"{BASE_URL}/api/new-starter/forgot-password",
                      json={"email": RECRUIT_EMAIL}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert "reset link" in data.get("message", "").lower()
    # confirm token created
    time.sleep(0.5)
    rec = db.staff_password_resets.find_one({"user_id": created_ids["user_id"], "used": False})
    assert rec, "reset row not created"


def test_08_forgot_password_unknown_email_same_message():
    r = requests.post(f"{BASE_URL}/api/new-starter/forgot-password",
                      json={"email": f"ghost_{TEST_TAG}@example.com"}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    # Message must be identical (no enumeration)
    assert "reset link" in data.get("message", "").lower()


# ── reset-password ──────────────────────────────────────────────────────────
def test_09_reset_password_invalid_token_400():
    r = requests.post(f"{BASE_URL}/api/new-starter/reset-password",
                      json={"token": "not-a-real-token-xyz", "password": NEW_PASSWORD}, timeout=20)
    assert r.status_code == 400


def test_10_reset_password_short_password_400(db):
    rec = db.staff_password_resets.find_one({"user_id": created_ids["user_id"], "used": False})
    assert rec
    r = requests.post(f"{BASE_URL}/api/new-starter/reset-password",
                      json={"token": rec["token"], "password": "short"}, timeout=20)
    assert r.status_code == 400


def test_11_reset_password_valid_ok(db):
    rec = db.staff_password_resets.find_one({"user_id": created_ids["user_id"], "used": False})
    assert rec, "no active reset token"
    r = requests.post(f"{BASE_URL}/api/new-starter/reset-password",
                      json={"token": rec["token"], "password": NEW_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    # verify token was marked used
    rec2 = db.staff_password_resets.find_one({"id": rec["id"]})
    assert rec2.get("used") is True
    # keep token for reuse test
    globals()["_used_reset_token"] = rec["token"]


def test_12_reset_token_reuse_400():
    r = requests.post(f"{BASE_URL}/api/new-starter/reset-password",
                      json={"token": globals()["_used_reset_token"], "password": "AnotherPass789!"}, timeout=20)
    assert r.status_code == 400


def test_13_login_new_password_works():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": RECRUIT_EMAIL, "password": NEW_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    assert "token" in r.json()


def test_14_login_old_password_rejected():
    r = requests.post(f"{BASE_URL}/api/new-starter/staff-login",
                      json={"email": RECRUIT_EMAIL, "password": INITIAL_PASSWORD}, timeout=20)
    assert r.status_code == 401


# ── regression: invite-based returning login still works ────────────────────
def test_15_regression_invite_returning_login():
    r = requests.post(f"{BASE_URL}/api/new-starter/login",
                      json={"token": created_ids["invite_token"], "password": NEW_PASSWORD}, timeout=20)
    # should be 200 (returning login using invite token)
    assert r.status_code == 200, r.text
    assert "token" in r.json()
