# seed_master_admin() — LEGACY_GYMAXIS_CLEANUP opt-in gate (no destructive deletes by default)
import asyncio
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import dotenv_values  # noqa: E402

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
_FE = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _FE.get("REACT_APP_BACKEND_URL")).rstrip("/")

from utils.database import db  # noqa: E402
from bootstrap.seed import seed_master_admin  # noqa: E402

MASTER_EMAIL = _ENV.get("MASTER_ADMIN_EMAIL")
MASTER_PWD = _ENV.get("MASTER_ADMIN_PASSWORD")


@pytest.fixture(scope="module")
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


def run(loop, coro):
    return loop.run_until_complete(coro)


def test_preview_db_only():
    # Safety: never run against production
    assert db.name == "test_database"


def _make_rows():
    tag = uuid.uuid4().hex[:8]
    ids = {
        "legacy_user": str(uuid.uuid4()),
        "gym_org": str(uuid.uuid4()),
        "gym_org_user": str(uuid.uuid4()),
        "pulse_org": str(uuid.uuid4()),
        "pulse_org_user": str(uuid.uuid4()),
    }
    users = [
        {"id": ids["legacy_user"], "email": f"legacy_TEST_{tag}@gymaxisai.com", "full_name": "TEST_legacy"},
        {"id": ids["gym_org_user"], "email": f"TEST_gymorg_{tag}@example.test",
         "organization_id": ids["gym_org"], "full_name": "TEST_gymorg"},
        {"id": ids["pulse_org_user"], "email": f"TEST_pulseorg_{tag}@example.test",
         "organization_id": ids["pulse_org"], "full_name": "TEST_pulseorg"},
    ]
    orgs = [
        {"id": ids["gym_org"], "name": f"GymAxis TEST Org {tag}"},
        {"id": ids["pulse_org"], "name": f"Pulse TEST Org {tag}"},
    ]
    return ids, users, orgs


async def _insert(users, orgs):
    await db.users.insert_many([dict(u) for u in users])
    await db.organizations.insert_many([dict(o) for o in orgs])


async def _cleanup(ids):
    await db.users.delete_many({"id": {"$in": [ids["legacy_user"], ids["gym_org_user"], ids["pulse_org_user"]]}})
    await db.organizations.delete_many({"id": {"$in": [ids["gym_org"], ids["pulse_org"]]}})


async def _exists(coll, _id):
    return await db[coll].find_one({"id": _id}, {"_id": 0, "id": 1}) is not None


async def _master():
    return await db.users.find_one({"email": MASTER_EMAIL}, {"_id": 0})


def _assert_master_healed(m):
    assert m is not None
    assert m["is_master_admin"] is True
    assert m["active"] is True
    assert m["must_change_password"] is False


class TestDefaultNoCleanup:
    def test_default_mode_deletes_nothing(self, loop, monkeypatch):
        monkeypatch.delenv("LEGACY_GYMAXIS_CLEANUP", raising=False)
        monkeypatch.setenv("MASTER_ADMIN_EMAIL", MASTER_EMAIL)
        monkeypatch.setenv("MASTER_ADMIN_PASSWORD", MASTER_PWD)
        monkeypatch.setenv("MASTER_ADMIN_RESET_ON_BOOT", "1")
        ids, users, orgs = _make_rows()
        run(loop, _insert(users, orgs))
        try:
            master_before = run(loop, _master())
            run(loop, seed_master_admin())
            for k in ("legacy_user", "gym_org_user", "pulse_org_user"):
                assert run(loop, _exists("users", ids[k])), f"{k} deleted in default mode"
            for k in ("gym_org", "pulse_org"):
                assert run(loop, _exists("organizations", ids[k])), f"{k} deleted in default mode"
            m = run(loop, _master())
            _assert_master_healed(m)
            assert m["id"] == master_before["id"]
        finally:
            run(loop, _cleanup(ids))

    def test_explicit_zero_also_no_cleanup(self, loop, monkeypatch):
        monkeypatch.setenv("LEGACY_GYMAXIS_CLEANUP", "0")
        monkeypatch.setenv("MASTER_ADMIN_EMAIL", MASTER_EMAIL)
        monkeypatch.setenv("MASTER_ADMIN_PASSWORD", MASTER_PWD)
        ids, users, orgs = _make_rows()
        run(loop, _insert(users, orgs))
        try:
            run(loop, seed_master_admin())
            assert run(loop, _exists("users", ids["legacy_user"]))
            assert run(loop, _exists("organizations", ids["gym_org"]))
            assert run(loop, _exists("users", ids["gym_org_user"]))
        finally:
            run(loop, _cleanup(ids))


class TestOptInCleanup:
    def test_opt_in_removes_only_legacy(self, loop, monkeypatch):
        monkeypatch.setenv("LEGACY_GYMAXIS_CLEANUP", "1")
        monkeypatch.setenv("MASTER_ADMIN_EMAIL", MASTER_EMAIL)
        monkeypatch.setenv("MASTER_ADMIN_PASSWORD", MASTER_PWD)
        monkeypatch.setenv("MASTER_ADMIN_RESET_ON_BOOT", "1")
        ids, users, orgs = _make_rows()
        run(loop, _insert(users, orgs))
        try:
            master_before = run(loop, _master())
            run(loop, seed_master_admin())
            assert not run(loop, _exists("users", ids["legacy_user"]))
            assert not run(loop, _exists("organizations", ids["gym_org"]))
            assert not run(loop, _exists("users", ids["gym_org_user"]))
            # control rows untouched
            assert run(loop, _exists("organizations", ids["pulse_org"]))
            assert run(loop, _exists("users", ids["pulse_org_user"]))
            m = run(loop, _master())
            _assert_master_healed(m)
            assert m["id"] == master_before["id"]
        finally:
            run(loop, _cleanup(ids))


class TestMasterAdminHeal:
    def test_reset_off_keeps_password_hash(self, loop, monkeypatch):
        monkeypatch.delenv("LEGACY_GYMAXIS_CLEANUP", raising=False)
        monkeypatch.setenv("MASTER_ADMIN_EMAIL", MASTER_EMAIL)
        monkeypatch.setenv("MASTER_ADMIN_PASSWORD", MASTER_PWD)
        monkeypatch.setenv("MASTER_ADMIN_RESET_ON_BOOT", "0")
        before = run(loop, _master())
        run(loop, seed_master_admin())
        after = run(loop, _master())
        _assert_master_healed(after)
        assert after["password"] == before["password"]

    def test_reset_on_resyncs_password(self, loop, monkeypatch):
        from utils.auth import verify_password
        monkeypatch.setenv("MASTER_ADMIN_EMAIL", MASTER_EMAIL)
        monkeypatch.setenv("MASTER_ADMIN_PASSWORD", MASTER_PWD)
        monkeypatch.setenv("MASTER_ADMIN_RESET_ON_BOOT", "1")
        before = run(loop, _master())
        run(loop, seed_master_admin())
        after = run(loop, _master())
        _assert_master_healed(after)
        assert after["password"] != before["password"]  # fresh bcrypt salt
        assert verify_password(MASTER_PWD, after["password"])


class TestRegression:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=20)
        assert r.status_code == 200

    def test_master_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": MASTER_EMAIL, "password": MASTER_PWD}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("access_token") or d.get("token")

    def test_provision_email_url(self, monkeypatch):
        from routes.mod_portal import _hq_provision_email_html
        monkeypatch.setenv("MOD_PORTAL_URL", "https://modservice.example.test/")
        html = _hq_provision_email_html({"name": "TEST site"}, "u", "p")
        assert 'href="https://modservice.example.test/MODService"' in html
