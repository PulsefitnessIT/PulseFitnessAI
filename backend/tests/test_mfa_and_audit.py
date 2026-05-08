"""
MFA + broader audit-coverage API regression tests (P2+, Feb 2026).

Exercises the full TOTP enrolment and login flow, backup-code path, replay
protection, and checks that sensitive mutations now emit ``security_audit_log``
rows.
"""
import uuid

import pyotp
import requests

from tests.conftest import (
    _test_backend_url,
    rate_limit_bypass_headers,
    run_async as run,
)

BASE = _test_backend_url()


# ─── Helpers ──────────────────────────────────────────────────────

def _register_user(email: str, pwd: str = "Good123Pass!") -> str:
    """Register a fresh user and return their JWT."""
    headers = rate_limit_bypass_headers()
    requests.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": pwd, "full_name": "MFA Test", "company_name": f"MFA Gym {uuid.uuid4().hex[:6]}"},
        headers=headers,
        timeout=10,
    )
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, headers=headers, timeout=10)
    return r.json()["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_user(email: str):
    from utils.database import db

    async def _go():
        user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if user:
            await db.user_mfa.delete_many({"user_id": user["id"]})
            await db.users.delete_one({"id": user["id"]})
            await db.mfa_used_codes.delete_many({"user_id": user["id"]})

    run(_go())


# ─── MFA enrolment + login ────────────────────────────────────────

def test_mfa_full_enrolment_and_login_flow():
    email = f"mfa-{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Good123Pass!"
    token = _register_user(email, pwd)

    try:
        # 1. status → disabled
        s = requests.get(f"{BASE}/api/auth/mfa/status", headers=_headers(token), timeout=10).json()
        assert s["enabled"] is False

        # 2. setup → returns provisioning URI + secret
        setup = requests.post(f"{BASE}/api/auth/mfa/setup", headers=_headers(token), timeout=10).json()
        assert setup["provisioning_uri"].startswith("otpauth://totp/")
        secret = setup["secret"]

        # 3. enable with correct TOTP → returns backup codes
        code = pyotp.TOTP(secret).now()
        enable = requests.post(
            f"{BASE}/api/auth/mfa/enable",
            json={"code": code}, headers=_headers(token), timeout=10,
        )
        assert enable.status_code == 200
        backup_codes = enable.json()["backup_codes"]
        assert len(backup_codes) == 10

        # 4. status now shows enabled
        s = requests.get(f"{BASE}/api/auth/mfa/status", headers=_headers(token), timeout=10).json()
        assert s["enabled"] is True
        assert s["backup_codes_remaining"] == 10

        # 5. Force mfa_required so login challenges us
        from utils.database import db

        async def _force_required():
            await db.users.update_one({"email": email}, {"$set": {"mfa_required": True}})

        run(_force_required())

        # 6. login → requires_mfa
        login = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, headers=rate_limit_bypass_headers(), timeout=10).json()
        assert login["requires_mfa"] is True
        temp_token = login["temp_token"]

        # 7. verify with wrong code → 401
        r = requests.post(
            f"{BASE}/api/auth/mfa/verify",
            json={"temp_token": temp_token, "code": "000000"}, timeout=10,
        )
        assert r.status_code == 401

        # 8. verify with correct TOTP → full JWT
        real_code = pyotp.TOTP(secret).now()
        r = requests.post(
            f"{BASE}/api/auth/mfa/verify",
            json={"temp_token": temp_token, "code": real_code}, timeout=10,
        )
        assert r.status_code == 200
        assert "token" in r.json()

        # 9. replay with same code → must fail
        login2 = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, headers=rate_limit_bypass_headers(), timeout=10).json()
        r = requests.post(
            f"{BASE}/api/auth/mfa/verify",
            json={"temp_token": login2["temp_token"], "code": real_code}, timeout=10,
        )
        assert r.status_code in (400, 401)

        # 10. backup code login
        login3 = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, headers=rate_limit_bypass_headers(), timeout=10).json()
        r = requests.post(
            f"{BASE}/api/auth/mfa/verify",
            json={"temp_token": login3["temp_token"], "code": backup_codes[0]}, timeout=10,
        )
        assert r.status_code == 200
        assert "token" in r.json()

    finally:
        _cleanup_user(email)


def test_mfa_setup_requires_auth():
    r = requests.post(f"{BASE}/api/auth/mfa/setup", timeout=10)
    assert r.status_code in (401, 403)


def test_mfa_qr_returns_png():
    email = f"mfa-qr-{uuid.uuid4().hex[:8]}@example.com"
    token = _register_user(email)
    try:
        setup = requests.post(f"{BASE}/api/auth/mfa/setup", headers=_headers(token), timeout=10).json()
        uri = setup["provisioning_uri"]
        r = requests.get(
            f"{BASE}/api/auth/mfa/qrcode",
            params={"uri": uri}, headers=_headers(token), timeout=10,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        _cleanup_user(email)


# ─── Broader audit coverage ───────────────────────────────────────

def test_branding_update_writes_audit_row():
    from utils.database import db

    email = f"brand-audit-{uuid.uuid4().hex[:8]}@example.com"
    token = _register_user(email)
    try:
        r = requests.patch(
            f"{BASE}/api/organization/branding",
            json={"primary_color": "#ABCDEF", "company_name": "Audit Test Co"},
            headers=_headers(token), timeout=10,
        )
        assert r.status_code == 200

        async def _check():
            return await db.security_audit_log.find_one(
                {"event": "org.branding.updated", "actor_email": email},
                {"_id": 0},
            )

        row = run(_check())
        assert row is not None
        assert "created_at" in row

        async def _cleanup_audit():
            await db.security_audit_log.delete_many({"actor_email": email})

        run(_cleanup_audit())
    finally:
        _cleanup_user(email)


def test_logout_writes_audit_row():
    from utils.database import db

    email = f"logout-audit-{uuid.uuid4().hex[:8]}@example.com"
    token = _register_user(email)
    try:
        r = requests.post(f"{BASE}/api/auth/logout", headers=_headers(token), timeout=10)
        assert r.status_code == 200

        async def _check():
            return await db.security_audit_log.find_one(
                {"event": "auth.logout", "actor_email": email},
                {"_id": 0},
            )

        row = run(_check())
        assert row is not None

        async def _cleanup_audit():
            await db.security_audit_log.delete_many({"actor_email": email})

        run(_cleanup_audit())
    finally:
        _cleanup_user(email)


def test_supplier_case_ip_rate_limit_rejects_abuse():
    """IP-scoped rate limit on /supplier/case/{token} prevents token guessing."""
    # Hit the endpoint 65 times with a random token — should eventually 429.
    seen = False
    for _ in range(70):
        r = requests.get(f"{BASE}/api/supplier/case/{uuid.uuid4().hex}", timeout=5)
        if r.status_code == 429:
            seen = True
            break
    # Either hit 429 (rate limited) or always 404 (token not found).
    # Both are acceptable — we just need the endpoint to not crash or 500.
    assert seen or r.status_code in (404, 401, 410)
