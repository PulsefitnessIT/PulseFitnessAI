"""Iter 216h197 — Craig's "Invalid Credentials" bug + portal pill bug.

Two regressions reported on production gymaxisai.com:

  1. Module pills on People Directory user detail showed only
     "Service Portal" for the OWNER even though their org has CRM
     enabled (Lee's screenshot). Pills were being derived from the
     existence of a `crm_users` row, which only gets created on first
     cross-login — not from actual CRM module access.

  2. Craig (a platform user with CRM access) typed his GymAxis
     password into the standalone /crm login form and got
     "Invalid credentials". His crm_users row was cross-login
     provisioned with a random hex password he doesn't know.

Tests run hermetically against mocked Mongo.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── BUG 1 — Portal pills ────────────────────────────────────────────────

def test_portal_pills_owner_with_crm_enabled_module() -> None:
    """OWNER whose org has 'crm' in enabled_modules must show both
    'service_portal' AND 'crm' pills, regardless of crm_users row."""
    from routes import master_admin_users as mu

    users = [{
        "id": "u-owner", "email": "owner@x.com", "full_name": "Owner",
        "role": "owner", "organization_id": "org-1", "user_type": "service_portal",
        "portals": ["service_portal"],
    }]

    fake_db = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=[
        {"id": "org-1", "name": "Pulse Fitness", "status": "active",
         "enabled_modules": ["crm", "memberships"], "account_type": "pulse_pro"}
    ])
    fake_db.organizations.find = MagicMock(return_value=fake_cursor)

    with patch.object(mu, "db", fake_db):
        _run(mu._enrich_with_orgs(users))

    portals = users[0]["portals"]
    assert "service_portal" in portals
    assert "crm" in portals, "owner with enabled_modules=['crm'] must show CRM pill"


def test_portal_pills_account_type_full_implies_crm() -> None:
    """Legacy: account_type='full' bundles CRM, so the pill must show
    even when enabled_modules is missing."""
    from routes import master_admin_users as mu

    users = [{"id": "u1", "email": "x@y.com", "organization_id": "org-1",
              "portals": ["service_portal"], "user_type": "service_portal"}]
    fake_db = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=[
        {"id": "org-1", "name": "Acme", "status": "active",
         "account_type": "full"}  # no enabled_modules
    ])
    fake_db.organizations.find = MagicMock(return_value=fake_cursor)

    with patch.object(mu, "db", fake_db):
        _run(mu._enrich_with_orgs(users))

    assert "crm" in users[0]["portals"]


def test_portal_pills_no_crm_for_basic_org() -> None:
    """An org without CRM in enabled_modules and a 'basic' account_type
    must NOT show the CRM pill."""
    from routes import master_admin_users as mu

    users = [{"id": "u1", "email": "x@y.com", "organization_id": "org-1",
              "portals": ["service_portal"], "user_type": "service_portal"}]
    fake_db = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=[
        {"id": "org-1", "name": "Basic Gym", "status": "active",
         "enabled_modules": ["memberships"], "account_type": "basic"}
    ])
    fake_db.organizations.find = MagicMock(return_value=fake_cursor)

    with patch.object(mu, "db", fake_db):
        _run(mu._enrich_with_orgs(users))

    assert "crm" not in users[0]["portals"]
    assert "service_portal" in users[0]["portals"]


def test_portal_pills_master_admin_always_has_crm_and_pulse_platform() -> None:
    """Master / pulse admins always have CRM + pulse_platform pills."""
    from routes import master_admin_users as mu

    users = [{"id": "u-pulse", "email": "lee@gymaxisai.com",
              "role": "pulse_master_admin", "is_master_admin": True,
              "organization_id": "org-1", "portals": [], "user_type": "service_portal"}]
    fake_db = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=[
        {"id": "org-1", "name": "GymAxis AI", "status": "active"}
    ])
    fake_db.organizations.find = MagicMock(return_value=fake_cursor)

    with patch.object(mu, "db", fake_db):
        _run(mu._enrich_with_orgs(users))

    assert "service_portal" in users[0]["portals"]
    assert "crm" in users[0]["portals"]
    assert "pulse_platform" in users[0]["portals"]


# ── BUG 2 — CRM login fallback to platform credentials ──────────────────

def test_crm_login_falls_back_to_platform_password_for_cross_provisioned() -> None:
    """A user whose crm_users row was cross-login provisioned (random
    hex password) must be able to log in via /crm/auth/login using
    their GymAxis platform password."""
    from routes import crm_auth as ca

    email = "craig@pulsefitness.ai"
    # Simulate: crm_users has a row with cross_login_provisioned=True,
    # password is a random hex (won't match user's actual password).
    crm_user = {
        "id": "u-craig", "email": email, "full_name": "Craig Henshall",
        "role": "manager", "organization_id": "org-pulse",
        "password": ca.crm_hash_password("random-hex-craig-does-not-know"),
        "cross_login_provisioned": True,
    }
    platform_user = {
        "id": "u-craig", "email": email, "full_name": "Craig Henshall",
        "organization_id": "org-pulse",
        "password_hash": "$2b$12$placeholder",
        "is_master_admin": False,
    }

    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value=crm_user)
    fake_db.crm_users.update_one = AsyncMock()
    fake_db.users.find_one = AsyncMock(return_value=platform_user)
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-pulse", "name": "Pulse Fitness"})

    # Stub `verify_password` from utils.security so we don't need a real bcrypt round.
    with patch.object(ca, "db", fake_db), \
         patch("utils.auth.verify_password", return_value=True), \
         patch("routes.crm_auth.crm_create_token", return_value="fake-crm-jwt"), \
         patch("routes.crm_auth._resolve_crm_brand_flags", new=AsyncMock(return_value=("pulse", True))):
        result = _run(ca.crm_login(data={"email": email, "password": "my-real-gymaxis-pwd"}))

    assert result.get("token") == "fake-crm-jwt"
    assert result["user"]["email"] == email
    fake_db.crm_users.update_one.assert_called_once()


def test_crm_login_creates_crm_users_row_when_missing() -> None:
    """A platform user with CRM access who has never visited CRM has no
    crm_users row at all. /crm/auth/login must create one on-the-fly
    when the platform credentials check passes."""
    from routes import crm_auth as ca

    email = "lee@gymaxisai.com"
    platform_user = {
        "id": "u-lee", "email": email, "full_name": "Lee Somers",
        "organization_id": "org-1", "password_hash": "$2b$12$placeholder",
        "is_master_admin": True,
    }

    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value=None)
    fake_db.crm_users.insert_one = AsyncMock()
    fake_db.crm_users.update_one = AsyncMock()
    fake_db.users.find_one = AsyncMock(return_value=platform_user)
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "GymAxis AI"})

    with patch.object(ca, "db", fake_db), \
         patch("utils.auth.verify_password", return_value=True), \
         patch("routes.crm_auth.crm_create_token", return_value="fake-crm-jwt"), \
         patch("routes.crm_auth._resolve_crm_brand_flags", new=AsyncMock(return_value=("gymaxis", False))):
        result = _run(ca.crm_login(data={"email": email, "password": "real-platform-pwd"}))

    assert result["token"] == "fake-crm-jwt"
    fake_db.crm_users.insert_one.assert_called_once()
    inserted = fake_db.crm_users.insert_one.call_args[0][0]
    assert inserted["email"] == email
    assert inserted["cross_login_provisioned"] is True
    # Master admin → role = 'admin'
    assert inserted["role"] == "admin"


def test_crm_login_rejects_wrong_platform_password() -> None:
    """Wrong password against both crm_users + platform must reject."""
    from routes import crm_auth as ca

    email = "craig@pulsefitness.ai"
    crm_user = {"id": "u1", "email": email, "password": "wrong-hash",
                "cross_login_provisioned": True}
    platform_user = {"id": "u1", "email": email,
                     "password_hash": "$2b$12$placeholder"}

    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value=crm_user)
    fake_db.users.find_one = AsyncMock(return_value=platform_user)

    with patch.object(ca, "db", fake_db), \
         patch("utils.auth.verify_password", return_value=False):
        with pytest.raises(Exception) as excinfo:
            _run(ca.crm_login(data={"email": email, "password": "nope"}))
        assert "Invalid credentials" in str(excinfo.value)


def test_crm_login_native_password_still_works() -> None:
    """Users whose crm_users row has a known native password (not
    cross-login provisioned) must still authenticate against it
    without fallback. Backwards-compat for legacy CRM-only accounts."""
    from routes import crm_auth as ca

    email = "native@example.com"
    crm_user = {
        "id": "u-native", "email": email, "full_name": "Native",
        "role": "manager", "organization_id": "org-1",
        "password": ca.crm_hash_password("native_pwd"),
        # No cross_login_provisioned flag.
    }

    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value=crm_user)
    fake_db.users.find_one = AsyncMock(return_value=None)
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "X"})

    with patch.object(ca, "db", fake_db), \
         patch("routes.crm_auth.crm_create_token", return_value="fake-crm-jwt"), \
         patch("routes.crm_auth._resolve_crm_brand_flags", new=AsyncMock(return_value=("gymaxis", False))):
        result = _run(ca.crm_login(data={"email": email, "password": "native_pwd"}))

    assert result["token"] == "fake-crm-jwt"
