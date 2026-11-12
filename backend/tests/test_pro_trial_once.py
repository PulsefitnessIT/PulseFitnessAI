# Pulse Pro trial: once-per-org, dismissible banner, master-admin re-grant
import os, sys, asyncio, pytest, requests
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ORG_ID = "12cba6ed-6f87-40a6-be51-e19d0ba60c2d"
LITE = {"email": "lite.suptest@pulsedemo.test", "password": "LiteSup123!"}
MASTER = {"email": "admin@pulsefitness.com", "password": "C2s9yJ3YAhydB4d34-Bykg"}


def _db(coro_fn):
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    async def run():
        c = AsyncIOMotorClient(env["MONGO_URL"])
        try:
            return await coro_fn(c[env["DB_NAME"]])
        finally:
            c.close()
    return asyncio.run(run())


def reset_org():
    async def f(db):
        await db.organizations.update_one({"id": ORG_ID}, {
            "$set": {"account_type": "lite",
                     "modules.memberships": {"enabled": False, "source": "admin"},
                     "modules.crm": {"enabled": False, "source": "admin"},
                     "modules.marketing": {"enabled": False, "source": "admin"}},
            "$unset": {"pro_trial_used_at": "", "pro_trial_granted": "", "pro_trial_granted_at": "",
                       "pro_trial_granted_by": "", "pro_trial_banner_dismissed_at": "",
                       "pro_trial_banner_dismissed_by": "", "module_trials": "",
                       "previous_account_type": "", "upgraded_at": "", "upgraded_by": ""}})
    _db(f)


def set_lite():
    async def f(db):
        await db.organizations.update_one({"id": ORG_ID}, {"$set": {"account_type": "lite"}})
    _db(f)


def login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed {creds['email']}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def lite():
    return login(LITE)


@pytest.fixture(scope="module")
def master():
    return login(MASTER)


@pytest.fixture(scope="module", autouse=True)
def clean():
    reset_org()
    yield
    reset_org()


def state(s):
    r = s.get(f"{BASE_URL}/api/me/pro-trial")
    assert r.status_code == 200, r.text
    return r.json()


def test_flow(lite, master):
    st = state(lite)
    assert st["available"] is True and st["used_at"] is None
    assert st["granted"] is False and st["banner_dismissed"] is False and st["is_owner"] is True

    # dismiss banner
    r = lite.post(f"{BASE_URL}/api/me/pro-trial/dismiss-banner")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert state(lite)["banner_dismissed"] is True
    assert state(lite)["available"] is True  # still available in settings

    # first upgrade with trials
    r = lite.post(f"{BASE_URL}/api/me/upgrade-to-pro", json={"start_trials": ["memberships", "crm", "marketing"]})
    assert r.status_code == 200, r.text
    st = state(lite)
    assert st["available"] is False and st["used_at"]

    # simulate trial end -> back to lite
    set_lite()
    st = state(lite)
    assert st["available"] is False
    r = lite.post(f"{BASE_URL}/api/me/upgrade-to-pro", json={"start_trials": ["memberships"]})
    assert r.status_code == 409, r.text
    assert "already used" in r.text

    # non-master cannot grant
    r = lite.post(f"{BASE_URL}/api/master-admin/organizations/{ORG_ID}/grant-pro-trial")
    assert r.status_code == 403, r.text

    # master grant
    r = master.post(f"{BASE_URL}/api/master-admin/organizations/{ORG_ID}/grant-pro-trial")
    assert r.status_code == 200, r.text
    st = state(lite)
    assert st["available"] is True and st["granted"] is True

    # use granted trial
    r = lite.post(f"{BASE_URL}/api/me/upgrade-to-pro", json={"start_trials": ["crm"]})
    assert r.status_code == 200, r.text
    set_lite()
    st = state(lite)
    assert st["available"] is False and st["granted"] is False
    r = lite.post(f"{BASE_URL}/api/me/upgrade-to-pro", json={"start_trials": ["crm"]})
    assert r.status_code == 409


def test_grant_404(master):
    r = master.post(f"{BASE_URL}/api/master-admin/organizations/nonexistent-org-xyz/grant-pro-trial")
    assert r.status_code == 404
