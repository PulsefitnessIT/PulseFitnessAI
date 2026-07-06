"""P0 test: crm-only login fallback + self-heal + forgot/reset regression.

Backend URL from REACT_APP_BACKEND_URL; uses X-RateLimit-Bypass header.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')
BYPASS = os.environ.get('RATE_LIMIT_BYPASS_SECRET', 'test-bypass-secret-for-ci-runs-only-2026')
HDRS = {"X-RateLimit-Bypass": BYPASS, "Content-Type": "application/json"}

CRM_EMAIL = "crmonly.manager@pulsedemo.test"
CRM_PASS = "CrmOnly123!"
MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASS = os.environ.get("MASTER_ADMIN_PASSWORD", "C2s9yJ3YAhydB4d34-Bykg")


def _post(path, payload, headers=None):
    h = dict(HDRS)
    if headers:
        h.update(headers)
    return requests.post(f"{BASE_URL}{path}", json=payload, headers=h, timeout=20)


# ------ crm-only login fallback ------
class TestCrmOnlyLoginFallback:
    def test_crm_only_login_returns_token(self):
        r = _post("/api/auth/login", {"email": CRM_EMAIL, "password": CRM_PASS})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        # token might be under 'token' or 'access_token'
        token = data.get("token") or data.get("access_token")
        assert token, f"no token in response: {data}"
        pytest.crm_token = token

    def test_me_after_crm_login(self):
        token = getattr(pytest, 'crm_token', None)
        if not token:
            pytest.skip("no token from prior test")
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}", **HDRS},
            timeout=15,
        )
        assert r.status_code == 200, f"/me failed: {r.status_code} {r.text[:300]}"
        me = r.json()
        assert (me.get("email") or "").lower() == CRM_EMAIL

    def test_self_healed_mirror_row_in_users(self):
        """After login the account should have been mirrored into db.users."""
        from pymongo import MongoClient  # type: ignore
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not (mongo_url and db_name):
            pytest.skip("Mongo env not set")
        cli = MongoClient(mongo_url)
        db = cli[db_name]
        u = db.users.find_one({"email": CRM_EMAIL})
        assert u, "user row not mirrored into db.users after login"
        crm = db.crm_users.find_one({"email": CRM_EMAIL})
        assert crm, "crm_users row missing"
        assert u.get("id") == crm.get("id"), "user.id must equal crm_users.id (same identity)"

    def test_wrong_password_still_401(self):
        r = _post("/api/auth/login", {"email": CRM_EMAIL, "password": "WrongPass!!"})
        assert r.status_code == 401, f"wrong password not rejected: {r.status_code} {r.text[:200]}"

    def test_nonexistent_email_still_401(self):
        r = _post(
            "/api/auth/login",
            {"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "whatever"},
        )
        assert r.status_code == 401, f"non-existent must 401, got {r.status_code}"


# ------ forgot/reset for crm-only ------
class TestForgotResetCrmOnly:
    def test_forgot_password_finds_crm_only(self):
        # Re-seed to reset password before reset flow
        import subprocess
        subprocess.run(
            ["python", "/app/backend/scripts/seed_crm_only_login_demo.py"],
            capture_output=True, timeout=30,
        )
        r = _post("/api/auth/forgot-password", {"email": CRM_EMAIL})
        assert r.status_code == 200, f"forgot returned {r.status_code}: {r.text[:200]}"

    def test_reset_flow_via_verify_script(self):
        """Run the end-to-end verify script that seeds → forgot → reset → login."""
        import subprocess
        # Re-seed first so account is in known state
        subprocess.run(
            ["python", "/app/backend/scripts/seed_crm_only_login_demo.py"],
            capture_output=True, timeout=30,
        )
        p = subprocess.run(
            ["python", "/app/backend/scripts/verify_crm_login_fix.py"],
            capture_output=True, timeout=60, text=True,
        )
        combined = (p.stdout or "") + (p.stderr or "")
        assert p.returncode == 0, f"verify_crm_login_fix.py failed:\n{combined[-1500:]}"


# ------ regression: master admin still logs in ------
class TestMasterAdminRegression:
    def test_master_admin_login(self):
        r = _post("/api/auth/login", {"email": MASTER_EMAIL, "password": MASTER_PASS})
        assert r.status_code == 200, f"master admin login broken: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert data.get("token") or data.get("access_token")


# ------ lite docs test user login (frontend prerequisite) ------
class TestLiteDocsUserExists:
    def test_lite_docs_user_login(self):
        r = _post("/api/auth/login", {"email": "lite.docs@pulsedemo.test", "password": "LiteDocs123!"})
        assert r.status_code == 200, f"lite.docs login: {r.status_code} {r.text[:300]}"
