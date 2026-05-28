"""Iter 220au — Wave 3 Security Hardening · Auth tightening.

Closes 6 risk-register findings:

  * F-02 — Password-reset token TTL: 1 h → 15 min (env-tunable).
  * F-03 — Role-tiered access-token TTL: master_admin = 1 h, default = 24 h.
  * F-08 — PII strip on /auth/me (``sanitize_me_response`` allow-list).
  * F-17 — MFA enforcement for master_admin (``ENFORCE_MASTER_ADMIN_MFA``).
  * F-18 — ``require_role(*roles)`` FastAPI dependency factory.
  * F-19 — ``revoke_user_sessions(user_id)`` for RBAC mutations.

Tests are pure-unit. Heavier path-integration coverage (live login,
MFA challenge, master-admin gate) lives in the existing
``test_iter_215f1_security_hardening.py`` regression file.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── F-02 — password-reset TTL pinned to 15 min ────────────────────


def test_password_reset_ttl_default_is_15_minutes(monkeypatch):
    monkeypatch.delenv("PASSWORD_RESET_TTL_MINUTES", raising=False)
    # Reimport to pick up the default.
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    assert g.PASSWORD_RESET_TTL_MINUTES == 15


def test_password_reset_ttl_env_override(monkeypatch):
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "10")
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    assert g.PASSWORD_RESET_TTL_MINUTES == 10
    monkeypatch.delenv("PASSWORD_RESET_TTL_MINUTES")
    importlib.reload(g)


# ── F-03 — role-tiered access-token TTL ───────────────────────────


def test_access_token_ttl_master_admin_dict_is_1h():
    from utils.auth_guards import access_token_ttl_hours
    assert access_token_ttl_hours({"is_master_admin": True}) == 1
    assert access_token_ttl_hours({"is_pulse_admin": True}) == 1
    assert access_token_ttl_hours({"role": "master_admin"}) == 1
    assert access_token_ttl_hours({"role": "pulse_master_admin"}) == 1


def test_access_token_ttl_normal_user_is_24h():
    from utils.auth_guards import access_token_ttl_hours
    assert access_token_ttl_hours({"role": "owner"}) == 24
    assert access_token_ttl_hours({"role": "staff"}) == 24
    assert access_token_ttl_hours({}) == 24
    assert access_token_ttl_hours(None) == 24


def test_access_token_ttl_string_input():
    from utils.auth_guards import access_token_ttl_hours
    assert access_token_ttl_hours("master_admin") == 1
    assert access_token_ttl_hours("owner") == 24
    assert access_token_ttl_hours("PULSE_MASTER_ADMIN") == 1  # case-insensitive


# ── create_token surface (mfa_verified claim + role-tier TTL) ─────


def test_create_token_records_mfa_verified_claim():
    import jwt as _jwt
    from utils.auth import create_token
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    tok = create_token("user-1", mfa_verified=True)
    payload = _jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["mfa_verified"] is True
    assert payload["user_id"] == "user-1"
    assert "jti" in payload


def test_create_token_default_mfa_verified_is_false():
    import jwt as _jwt
    from utils.auth import create_token
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    tok = create_token("user-1")
    payload = _jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["mfa_verified"] is False


# ── F-08 — sanitize_me_response strips PII ────────────────────────


def test_sanitize_me_response_strips_password_and_secrets():
    from utils.auth_guards import sanitize_me_response
    raw = {
        "id": "u1", "email": "x@y.com", "full_name": "X Y",
        "password": "$2b$12$abc",
        "password_hash": "$2b$12$abc",
        "mfa_secret": "ABCDEF",
        "mfa_backup_codes": ["a", "b"],
        "stripe_customer_id": "cus_123",
        "stripe_subscription_id": "sub_123",
        "reset_token": "tok",
        "tokens_revoked_before": 123,
        "_id": "mongo-id",
    }
    clean = sanitize_me_response(raw)
    for forbidden in ("password", "password_hash", "mfa_secret", "mfa_backup_codes",
                      "stripe_customer_id", "stripe_subscription_id", "reset_token",
                      "tokens_revoked_before", "_id"):
        assert forbidden not in clean
    assert clean["email"] == "x@y.com"
    assert clean["id"] == "u1"


def test_sanitize_me_response_idempotent():
    from utils.auth_guards import sanitize_me_response
    once = sanitize_me_response({"id": "u1", "email": "x@y.com"})
    twice = sanitize_me_response(once)
    assert twice == once


def test_sanitize_me_response_handles_none():
    from utils.auth_guards import sanitize_me_response
    assert sanitize_me_response(None) == {}
    assert sanitize_me_response({}) == {}


# ── F-17 — MFA enforcement for master admin ───────────────────────


def test_enforce_master_admin_mfa_off_by_default(monkeypatch):
    monkeypatch.setenv("ENFORCE_MASTER_ADMIN_MFA", "false")
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    # Master admin without MFA → no raise.
    g.enforce_master_admin_mfa({"is_master_admin": True, "_jwt_mfa_verified": False})


def test_enforce_master_admin_mfa_blocks_when_enabled(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("ENFORCE_MASTER_ADMIN_MFA", "true")
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    try:
        g.enforce_master_admin_mfa({"is_master_admin": True, "_jwt_mfa_verified": False})
        assert False, "expected HTTPException(401)"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert "mfa" in exc.detail.lower()
    monkeypatch.delenv("ENFORCE_MASTER_ADMIN_MFA")
    importlib.reload(g)


def test_enforce_master_admin_mfa_passes_with_verified_session(monkeypatch):
    monkeypatch.setenv("ENFORCE_MASTER_ADMIN_MFA", "true")
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    # Should not raise.
    g.enforce_master_admin_mfa({"is_master_admin": True, "_jwt_mfa_verified": True})
    g.enforce_master_admin_mfa({"is_pulse_admin": True, "_jwt_mfa_verified": True})
    monkeypatch.delenv("ENFORCE_MASTER_ADMIN_MFA")
    importlib.reload(g)


def test_enforce_master_admin_mfa_noop_for_non_admins(monkeypatch):
    monkeypatch.setenv("ENFORCE_MASTER_ADMIN_MFA", "true")
    import importlib
    import utils.auth_guards as g
    importlib.reload(g)
    # Regular user — never blocked.
    g.enforce_master_admin_mfa({"role": "staff", "_jwt_mfa_verified": False})
    g.enforce_master_admin_mfa({"role": "owner", "_jwt_mfa_verified": False})
    monkeypatch.delenv("ENFORCE_MASTER_ADMIN_MFA")
    importlib.reload(g)


# ── F-18 — require_role / assert_role gates ───────────────────────


def test_assert_role_allows_master_admin_for_any_role():
    from utils.auth_guards import assert_role
    # No raise.
    assert_role({"is_master_admin": True}, {"owner", "manager"})
    assert_role({"is_pulse_admin": True}, {"owner"})


def test_assert_role_allows_matching_role():
    from utils.auth_guards import assert_role
    assert_role({"role": "manager"}, ["manager", "owner"])
    assert_role({"role": "OWNER"}, ["owner"])  # case-insensitive


def test_assert_role_rejects_non_matching_role():
    from fastapi import HTTPException
    from utils.auth_guards import assert_role
    try:
        assert_role({"role": "staff"}, ["manager", "owner"])
        assert False, "expected HTTPException(403)"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "manager" in exc.detail or "owner" in exc.detail


def test_assert_role_rejects_user_with_no_role():
    from fastapi import HTTPException
    from utils.auth_guards import assert_role
    try:
        assert_role({}, ["manager"])
        assert False, "expected HTTPException(403)"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_require_role_is_callable_factory():
    """``require_role`` returns a FastAPI dep — callable that accepts
    a user dict and returns either the user or raises."""
    from utils.auth_guards import require_role
    dep = require_role("owner", "manager")
    assert callable(dep)
    # Direct invocation with master_admin must pass.
    assert dep(user={"is_master_admin": True}) == {"is_master_admin": True}


# ── F-19 — revoke_user_sessions ───────────────────────────────────


def test_revoke_user_sessions_stamps_users_doc():
    from utils.auth_guards import revoke_user_sessions

    with patch("utils.auth_guards.db") as mock_db:
        mock_db.users.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.crm_users.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
        _run(revoke_user_sessions("user-1", reason="role_change"))
        # Both updates should be called once.
        mock_db.users.update_one.assert_called_once()
        mock_db.crm_users.update_one.assert_called_once()
        body = mock_db.users.update_one.call_args[0][1]["$set"]
        assert body["tokens_revoked_reason"] == "role_change"
        assert isinstance(body["tokens_revoked_before"], int)
        assert body["tokens_revoked_before"] > 0


def test_revoke_user_sessions_noop_on_empty_id():
    from utils.auth_guards import revoke_user_sessions

    with patch("utils.auth_guards.db") as mock_db:
        mock_db.users.update_one = AsyncMock()
        _run(revoke_user_sessions("", reason="x"))
        _run(revoke_user_sessions(None, reason="x"))
        mock_db.users.update_one.assert_not_called()


def test_revoke_user_sessions_swallows_db_errors():
    from utils.auth_guards import revoke_user_sessions

    with patch("utils.auth_guards.db") as mock_db:
        mock_db.users.update_one = AsyncMock(side_effect=RuntimeError("mongo down"))
        mock_db.crm_users.update_one = AsyncMock(side_effect=RuntimeError("mongo down"))
        # Should not raise — best-effort.
        _run(revoke_user_sessions("user-1"))


# ── F-19 end-to-end: get_current_user rejects pre-revocation iat ──


def test_get_current_user_rejects_token_minted_before_revoke():
    """Smoke: a JWT minted before ``users.tokens_revoked_before`` 401s
    with 'Session revoked by admin'."""
    import asyncio
    from datetime import datetime, timezone, timedelta
    from fastapi import HTTPException
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    from utils.auth import get_current_user

    # Build a token whose `iat` is 1 hour in the past.
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = _jwt.encode({
        "user_id": "u1",
        "jti": "j1",
        "iat": past,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "mfa_verified": False,
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
    revoked_before = int(datetime.now(timezone.utc).timestamp())  # now > iat

    class _DummyRequest:
        def __init__(self):
            self.cookies = {}
        @property
        def client(self):
            return None

    class _DummyCreds:
        def __init__(self, tok):
            self.credentials = tok

    with patch("utils.auth.db") as mock_db, \
         patch("utils.security_plus.is_jwt_revoked", new=AsyncMock(return_value=False)):
        mock_db.users.find_one = AsyncMock(return_value={
            "id": "u1", "email": "x@y.com",
            "tokens_revoked_before": revoked_before,
        })
        mock_db.organizations.find_one = AsyncMock(return_value=None)
        try:
            asyncio.new_event_loop().run_until_complete(
                get_current_user(_DummyRequest(), _DummyCreds(token))
            )
            assert False, "expected HTTPException(401)"
        except HTTPException as exc:
            assert exc.status_code == 401
            assert "revoked" in exc.detail.lower()


def test_get_current_user_accepts_token_minted_after_revoke():
    """Inverse: a fresh token (iat > tokens_revoked_before) still passes."""
    import asyncio
    from datetime import datetime, timezone, timedelta
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    from utils.auth import get_current_user

    # Stamp the cutoff 1 hour in the past, mint the token NOW.
    revoked_before = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    token = _jwt.encode({
        "user_id": "u1",
        "jti": "j2",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "mfa_verified": True,
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    class _DummyRequest:
        def __init__(self):
            self.cookies = {}
        @property
        def client(self):
            return None

    class _DummyCreds:
        def __init__(self, tok):
            self.credentials = tok

    with patch("utils.auth.db") as mock_db, \
         patch("utils.security_plus.is_jwt_revoked", new=AsyncMock(return_value=False)):
        mock_db.users.find_one = AsyncMock(return_value={
            "id": "u1", "email": "x@y.com",
            "tokens_revoked_before": revoked_before,
        })
        mock_db.organizations.find_one = AsyncMock(return_value=None)
        out = asyncio.new_event_loop().run_until_complete(
            get_current_user(_DummyRequest(), _DummyCreds(token))
        )
        assert out["id"] == "u1"
        assert out["_jwt_mfa_verified"] is True
