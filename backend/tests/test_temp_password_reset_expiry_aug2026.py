"""Master-Admin reset-password must refresh temp_password_expires_at.

Bug: PUT /api/master-admin/users/{id}/reset-password set a new password +
password_reset_required but left a STALE `temp_password_expires_at`, so
`_enforce_account_status` blocked the login with
"Temporary password has expired — ask the platform admin to reissue.".

Covered here (backend only):
  1. Repro of the seeded stuck state (login 401 "expired").
  2. Real master-admin reset (handling TOTP MFA) → login with the returned
     temp password must NOT be blocked by the expiry gate.
  3. Regression: reset response shape + old password now fails as INVALID
     credentials (not "expired").
"""
import base64
import hashlib
import os
import time

import pytest
import pyotp
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

MASTER_EMAIL = backend_env.get("MASTER_ADMIN_EMAIL") or "admin@pulsefitness.com"
MASTER_PASSWORD = backend_env.get("MASTER_ADMIN_PASSWORD")

HONEY_EMAIL = "honey.test@pulsefitness.com"
HONEY_ID = "5f10e6f3-b0ff-461b-bdc4-224923b01a0c"
HONEY_OLD_PASSWORD = "OldTempPass123!"

EXPIRED_MSG = "Temporary password has expired"

# module-level state shared across the ordered tests
STATE: dict = {}


# ── helpers ──────────────────────────────────────────────────────────────

def _login(email: str, password: str) -> requests.Response:
    return requests.post(
        f"{API}/auth/login", json={"email": email, "password": password}, timeout=60
    )


def _mfa_secret_from_db(user_id: str) -> str:
    """Decrypt the live TOTP secret for an already-enrolled user."""
    from cryptography.fernet import Fernet
    from pymongo import MongoClient

    mongo_url = backend_env.get("MONGO_URL") or os.environ.get("MONGO_URL")
    db_name = backend_env.get("DB_NAME") or os.environ.get("DB_NAME")
    doc = MongoClient(mongo_url)[db_name].user_mfa.find_one({"user_id": user_id})
    assert doc and doc.get("secret_encrypted"), "no enrolled MFA secret found"
    key = (backend_env.get("MFA_ENCRYPTION_KEY") or "").strip()
    if not key:
        jwt_secret = (backend_env.get("JWT_SECRET") or "").strip()
        key = base64.urlsafe_b64encode(hashlib.sha256(jwt_secret.encode()).digest()).decode()
    return Fernet(key.encode()).decrypt(doc["secret_encrypted"].encode()).decode()


def _totp(secret: str, used: set | None = None) -> str:
    """Return a fresh TOTP code, avoiding replay of an already-used code."""
    totp = pyotp.TOTP(secret)
    code = totp.now()
    if used is not None and code in used:
        time.sleep(31)
        code = totp.now()
    if used is not None:
        used.add(code)
    return code


def _master_token() -> str:
    """Full master-admin JWT, completing the mandatory TOTP MFA flow."""
    if STATE.get("master_token"):
        return STATE["master_token"]
    assert MASTER_PASSWORD, "MASTER_ADMIN_PASSWORD missing from backend/.env"
    resp = _login(MASTER_EMAIL, MASTER_PASSWORD)
    assert resp.status_code == 200, f"master login failed {resp.status_code}: {resp.text[:300]}"
    data = resp.json()

    if data.get("token"):
        STATE["master_token"] = data["token"]
        return data["token"]

    temp_token = data.get("temp_token")
    assert temp_token, f"unexpected master login payload: {data}"

    if data.get("requires_mfa_enrolment"):
        setup = requests.post(
            f"{API}/auth/mfa/enrol/setup", json={"temp_token": temp_token}, timeout=60
        )
        assert setup.status_code == 200, f"enrol/setup {setup.status_code}: {setup.text[:300]}"
        secret = setup.json()["secret"]
        done = requests.post(
            f"{API}/auth/mfa/enrol/complete",
            json={"temp_token": temp_token, "code": _totp(secret)},
            timeout=60,
        )
        assert done.status_code == 200, f"enrol/complete {done.status_code}: {done.text[:300]}"
        token = done.json().get("token")
    else:
        assert data.get("requires_mfa"), f"unexpected master login payload: {data}"
        secret = _mfa_secret_from_db(data["user"].get("id") or STATE.get("master_id") or _master_id())
        verify = requests.post(
            f"{API}/auth/mfa/verify",
            json={"temp_token": temp_token, "code": _totp(secret)},
            timeout=60,
        )
        assert verify.status_code == 200, f"mfa/verify {verify.status_code}: {verify.text[:300]}"
        token = verify.json().get("token")

    assert token, "MFA flow did not return a JWT"
    STATE["master_token"] = token
    return token


def _master_id() -> str:
    from pymongo import MongoClient
    mongo_url = backend_env.get("MONGO_URL")
    db_name = backend_env.get("DB_NAME")
    doc = MongoClient(mongo_url)[db_name].users.find_one({"email": MASTER_EMAIL.lower()})
    assert doc, "master admin user row not found"
    return doc["id"]


# ── 1. bug repro (seeded stuck state) ────────────────────────────────────

def test_repro_seeded_stuck_temp_password_expired():
    resp = _login(HONEY_EMAIL, HONEY_OLD_PASSWORD)
    detail = ""
    try:
        detail = resp.json().get("detail", "")
    except Exception:  # noqa: BLE001
        detail = resp.text
    if resp.status_code == 401 and EXPIRED_MSG in str(detail):
        STATE["repro_confirmed"] = True
        return
    # The repro user may have been consumed by an earlier run; record and skip.
    STATE["repro_confirmed"] = False
    pytest.skip(
        f"seeded stuck state not present (status={resp.status_code}, detail={detail!r}); "
        "re-seed honey.test@pulsefitness.com to re-verify the repro"
    )


# ── 2. the fix: real master-admin reset then login ───────────────────────

def test_master_admin_reset_password_returns_temp_password():
    token = _master_token()
    resp = requests.put(
        f"{API}/master-admin/users/{HONEY_ID}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    assert resp.status_code == 200, f"reset failed {resp.status_code}: {resp.text[:400]}"
    data = resp.json()
    assert data.get("success") is True
    temp_password = data.get("temp_password")
    assert isinstance(temp_password, str) and len(temp_password) >= 16, data
    assert data.get("user_email") == HONEY_EMAIL, data
    STATE["temp_password"] = temp_password


def test_login_with_fresh_temp_password_not_blocked_by_expiry():
    temp_password = STATE.get("temp_password")
    assert temp_password, "reset step did not produce a temp password"
    resp = _login(HONEY_EMAIL, temp_password)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    detail = str(body.get("detail", ""))
    assert EXPIRED_MSG not in detail, f"expiry gate still blocks login: {detail}"
    assert resp.status_code == 200, f"login failed {resp.status_code}: {resp.text[:400]}"
    assert body.get("token"), f"no JWT in login response: {list(body)}"
    # Honey has no MFA — a plain token is expected, no MFA step.
    assert not body.get("requires_mfa"), body
    assert not body.get("requires_mfa_enrolment"), body
    # Forced-change flag should still be advertised to the client.
    user = body.get("user") or {}
    assert user.get("email") == HONEY_EMAIL, user
    STATE["forced_change_flag"] = (
        body.get("must_change_password")
        or body.get("password_reset_required")
        or user.get("must_change_password")
        or user.get("password_reset_required")
    )


# ── 3. regression: old password now invalid, not "expired" ───────────────

def test_old_password_now_invalid_credentials_not_expired():
    resp = _login(HONEY_EMAIL, HONEY_OLD_PASSWORD)
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}: {resp.text[:300]}"
    detail = str(resp.json().get("detail", ""))
    assert EXPIRED_MSG not in detail, f"still reporting expiry for a wrong password: {detail}"
    assert "invalid" in detail.lower() or "credential" in detail.lower(), detail


def test_reset_persisted_fresh_expiry_and_forced_change():
    """DB-level assertion: fresh expiry in the future + must_change_password."""
    from datetime import datetime, timezone

    from pymongo import MongoClient

    client = MongoClient(backend_env.get("MONGO_URL"))
    doc = client[backend_env.get("DB_NAME")].users.find_one({"id": HONEY_ID})
    assert doc, "repro user missing from db.users"
    assert doc.get("must_change_password") is True
    assert doc.get("password_reset_required") is True
    expires = doc.get("temp_password_expires_at")
    assert expires and expires > datetime.now(timezone.utc).isoformat(), expires
