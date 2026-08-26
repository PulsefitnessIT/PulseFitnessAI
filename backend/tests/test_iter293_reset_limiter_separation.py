"""BUG 2 backend: forgot-password vs reset-password rate-limit bucket separation.

Public endpoints, NO auth, NO rate-limit bypass header (the point is to prove
the two limiters use DIFFERENT buckets).
"""
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def clean_reset_buckets():
    """Reset the shared per-IP reset buckets so burst tests are deterministic
    (previous manual curl runs otherwise pre-consume the allowance)."""
    backend_env = dotenv_values("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL/DB_NAME unavailable for bucket cleanup")
    from pymongo import MongoClient
    cli = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    col = cli[db_name]["rate_buckets"]
    col.delete_many({"_id": {"$regex": r"^(resetsubmit|resetreq):"}})
    yield col
    col.delete_many({"_id": {"$regex": r"^(resetsubmit|resetreq):"}})
    cli.close()


class TestForgotPasswordEndpoint:
    """POST /api/auth/forgot-password — generic 200 response (no user enumeration)."""

    def test_forgot_password_unknown_email_returns_200_generic(self, client, clean_reset_buckets):
        r = client.post(f"{BASE_URL}/api/auth/forgot-password",
                        json={"email": f"TEST_nobody_{uuid.uuid4().hex[:8]}@example.invalid"},
                        timeout=30)
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        msg = (data.get("message") or "").lower()
        assert msg, f"no message in body: {data}"
        # Generic wording — must not reveal whether the account exists
        assert "not found" not in msg and "no account" not in msg, msg

    def test_forgot_password_known_email_returns_200_same_message(self, client, clean_reset_buckets):
        r = client.post(f"{BASE_URL}/api/auth/forgot-password",
                        json={"email": "owner@isodemo.com"}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.json().get("message")


class TestResetPasswordSubmitLimiter:
    """POST /api/auth/reset-password — 400 validation, NOT 429, for repeat attempts.

    NOTE: the endpoint reads body key ``password`` (verified in routes/auth.py).
    """

    def test_invalid_token_weak_password_returns_400(self, client, clean_reset_buckets):
        r = client.post(f"{BASE_URL}/api/auth/reset-password",
                        json={"token": "invalidtoken" + uuid.uuid4().hex, "password": "weak"},
                        timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:400]}"
        detail = str(r.json().get("detail", "")).lower()
        # weak password must be rejected by the strength validator
        assert "password must contain" in detail or "12 characters" in detail, detail

    def test_invalid_token_strong_password_returns_400_invalid_token(self, client, clean_reset_buckets):
        r = client.post(f"{BASE_URL}/api/auth/reset-password",
                        json={"token": "invalidtoken" + uuid.uuid4().hex,
                              "password": "Str0ng!Passw0rd#2026"},
                        timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:400]}"
        detail = str(r.json().get("detail", "")).lower()
        assert "invalid or expired reset token" in detail, detail

    def test_ten_consecutive_reset_attempts_never_429(self, client, clean_reset_buckets):
        """The submit limiter is 15/15min — 10 tries must all be 400 (no lockout)."""
        codes = []
        for i in range(10):
            r = client.post(f"{BASE_URL}/api/auth/reset-password",
                            json={"token": f"bogus{i}{uuid.uuid4().hex}", "password": "weak"},
                            timeout=30)
            codes.append(r.status_code)
            time.sleep(0.15)
        assert 429 not in codes, f"got a 429 in submit burst: {codes}"
        assert all(c == 400 for c in codes), codes


class TestBucketSeparation:
    """Hammering reset-password must NOT consume the forgot-password allowance."""

    def test_forgot_password_still_works_after_reset_burst(self, client, clean_reset_buckets):
        # burst 12 reset submits (would blow a shared 5/15min bucket many times over)
        codes = []
        for i in range(12):
            r = client.post(f"{BASE_URL}/api/auth/reset-password",
                            json={"token": f"sep{i}{uuid.uuid4().hex}", "password": "weak"},
                            timeout=30)
            codes.append(r.status_code)
            time.sleep(0.1)
        assert 429 not in codes, f"submit burst hit 429 early: {codes}"
        r = client.post(f"{BASE_URL}/api/auth/forgot-password",
                        json={"email": f"TEST_sep_{uuid.uuid4().hex[:8]}@example.invalid"},
                        timeout=30)
        assert r.status_code == 200, (
            f"forgot-password blocked after reset burst (shared bucket regression): "
            f"{r.status_code} {r.text[:300]}")

    def test_separate_bucket_keys_exist_in_store(self, client, clean_reset_buckets):
        col = clean_reset_buckets
        client.post(f"{BASE_URL}/api/auth/forgot-password",
                    json={"email": f"TEST_k_{uuid.uuid4().hex[:8]}@example.invalid"}, timeout=30)
        client.post(f"{BASE_URL}/api/auth/reset-password",
                    json={"token": "k" + uuid.uuid4().hex, "password": "weak"}, timeout=30)
        keys = [d["_id"] for d in col.find({"_id": {"$regex": r"^(resetsubmit|resetreq):"}})]
        assert any(k.startswith("resetreq:") for k in keys), keys
        assert any(k.startswith("resetsubmit:") for k in keys), keys


# ── BUG 4 (partial, non-MFA sanity): /auth/refresh must preserve claims ──
class TestRefreshPreservesClaims:
    """Master-admin act_org is MFA-gated, so we assert the generic guarantee:
    refresh returns a working token whose org/user context is unchanged."""

    def _login(self, client):
        r = client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": "owner@isodemo.com", "password": "IsoDemo123!"},
                        headers={"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")},
                        timeout=40)
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert data.get("token"), data
        return data

    def test_refresh_returns_working_token_same_org(self, client):
        first = self._login(client)
        token = first["token"]
        me1 = client.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert me1.status_code == 200, me1.text[:300]
        org1 = me1.json().get("organization_id")

        r = client.post(f"{BASE_URL}/api/auth/refresh",
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200, f"refresh failed: {r.status_code} {r.text[:300]}"
        new_token = r.json().get("token")
        assert new_token and new_token != token, "refresh did not rotate the token"

        me2 = client.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {new_token}"}, timeout=30)
        assert me2.status_code == 200, me2.text[:300]
        assert me2.json().get("organization_id") == org1
        assert me2.json().get("email") == "owner@isodemo.com"
