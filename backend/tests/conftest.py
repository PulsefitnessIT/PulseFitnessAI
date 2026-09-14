"""Shared test configuration — credentials loaded from environment variables.

The `_ensure_regular_test_user` autouse fixture registers the default regular
test user via `/api/auth/register` at the start of the session so any test
file that logs in with `REGULAR_USER_EMAIL` / `REGULAR_USER_PASSWORD` can
authenticate without relying on externally-seeded data.

The `_patch_requests_with_ratelimit_bypass` autouse fixture transparently
attaches the `X-RateLimit-Bypass` header to every `requests` call so the
test suite doesn't trip the login brute-force guard mid-run. The bypass
secret is read from the backend's own `.env` — tests run on the same host
so no credential exchange is needed.

`drive_async(coro)` (iter 220m) is the canonical way for sync tests to
drive an async coroutine. It gracefully handles the Python 3.11+ case
where `asyncio.get_event_loop()` raises `RuntimeError: There is no
current event loop in thread 'MainThread'` once any earlier
`asyncio.run(...)` cleans up the global loop. The helper installs a
fresh loop if needed and returns the coroutine's result.
"""
import asyncio
import os
import pytest
import requests


def drive_async(coro):
    """Run *coro* to completion on a usable event loop.

    Prefers the thread-default loop if one already exists and is open;
    otherwise installs a fresh loop and registers it as the thread
    default. Safe to call repeatedly in the same test session.

    This is a drop-in replacement for the legacy
    ``asyncio.get_event_loop().run_until_complete(coro)`` idiom that
    breaks on Python 3.11+ after any earlier ``asyncio.run`` call.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

API_BASE_URL = os.environ.get("TEST_API_URL", "https://mod-only-deploy.preview.emergentagent.com")

MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")

REGULAR_USER_EMAIL = os.environ.get("TEST_REGULAR_USER_EMAIL", "test@gymaxisai.com")
REGULAR_USER_PASSWORD = os.environ.get("TEST_REGULAR_USER_PASSWORD", "Test123!")

# Pulse Pro user - has 66 equipment items, best for testing equipment/fault/CAPEX features
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")

CRM_ADMIN_EMAIL = os.environ.get("TEST_CRM_ADMIN_EMAIL", "crm@gymaxisai.com")
CRM_ADMIN_PASSWORD = os.environ.get("TEST_CRM_ADMIN_PASSWORD", "CRMAdmin123!")

# Org ID for tier toggle test
TOTTENHAM_GREEN_ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Iter 220m — guarantee every test sees a usable thread-default
    asyncio loop before it runs. On Python 3.11+, `get_event_loop()`
    raises `RuntimeError: There is no current event loop in thread
    'MainThread'` once any earlier `asyncio.run(...)` has cleared the
    thread default. That was producing the cascade of ~13
    pseudo-failures in `make regression` — tests that pass in
    isolation but trip the moment they run after an asyncio.run call.

    Function-scope (cheap) so motor's per-test connection pool stays
    bound to the same loop within a single test, and tests that mock
    out the motor `db` reference don't care about loop identity at
    all.

    Pairs with `_rebind_motor_to_current_loop` below — together they
    keep motor's connection pool aligned with the freshly-installed
    loop and prevent the
    ``RuntimeError: ... attached to a different loop`` cascade in
    220k/l/m."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield loop


@pytest.fixture(autouse=True)
def _rebind_motor_to_current_loop():
    """Iter 220m — refresh the shared Motor `client` and `db` so any
    pending future from a closed/different loop is dropped and the
    new pool binds to the *current* loop on next I/O. Motor v3's
    connection pool is lazy-bound to whichever loop drives the first
    query; the binding is not reset by `client.close()` alone (close
    is permanent). The robust pattern is to spin up a *fresh*
    AsyncIOMotorClient per-test and re-publish it to every module
    that imported the original. We patch the two we actually depend
    on (`utils.database`, `routes.partners`, `utils.reputation_reports`)
    — anything else that has a stale reference will get a working
    motor as soon as it goes through the canonical `utils.database`
    import path.

    Teardown closes the spun-up client so we don't leak MongoDB
    connection pools across the ~840-test session (which would
    otherwise blow past the server's pool ceiling)."""
    fresh = None
    previous_client = None
    previous_db = None
    patched_modules = []
    try:
        import os as _os
        from motor.motor_asyncio import AsyncIOMotorClient
        import utils.database as _db_mod
        previous_client = _db_mod.client
        previous_db = _db_mod.db
        fresh = AsyncIOMotorClient(_os.environ["MONGO_URL"], maxPoolSize=8)
        _db_mod.client = fresh
        _db_mod.db = fresh[_os.environ["DB_NAME"]]
        # Iter 230 — generically re-publish to EVERY loaded module that
        # imported `db` by value (`from utils.database import db`). The
        # previous hand-maintained allowlist was whack-a-mole: any new
        # by-value importer (e.g. utils.sales_to_service →
        # routes.svc.intake) re-introduced the "attached to a different
        # loop" cascade in full runs. Matching on TYPE (not identity)
        # matters: a module first imported mid-session grabs whichever
        # per-test fresh client was live at that moment — which is closed
        # by that test's teardown, leaving the module with a dead client
        # an identity check against the original would never find.
        import sys as _sys
        from motor.motor_asyncio import AsyncIOMotorDatabase as _MotorDB
        for _m in list(_sys.modules.values()):
            try:
                _attr = getattr(_m, "db", None) if _m is not None else None
                if isinstance(_attr, _MotorDB) and _attr is not _db_mod.db:
                    patched_modules.append(_m)
                    _m.db = _db_mod.db
            except Exception:
                pass
    except Exception:
        # Tests that don't import the backend at all can safely ignore.
        pass
    try:
        yield
    finally:
        # Restore the originally-imported client/db so the next test's
        # fixture sees a stable starting point, then close the temp
        # client we created to release its connection pool.
        try:
            if fresh is not None:
                import utils.database as _db_mod
                if previous_client is not None:
                    _db_mod.client = previous_client
                if previous_db is not None:
                    _db_mod.db = previous_db
                # Point the by-value importers back at the stable
                # canonical original so the next test's sweep starts
                # from a consistent baseline (never a closed client).
                for _m in patched_modules:
                    try:
                        _m.db = previous_db
                    except Exception:
                        pass
                fresh.close()
        except Exception:
            pass


def _test_backend_url() -> str:
    """Backend URL that tests hit. Prefer REACT_APP_BACKEND_URL (external), fall back to TEST_API_URL."""
    return (os.environ.get("REACT_APP_BACKEND_URL") or API_BASE_URL).rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def _patch_requests_with_ratelimit_bypass():
    """Transparently attach X-RateLimit-Bypass to every `requests.*` call.

    Tests make many rapid-fire logins; without the bypass, the login
    brute-force guard (5 req / 5 min / IP) kicks in and poisons downstream
    test suites with 429s. We read the secret directly from the running
    backend's .env file so there's no separate env plumbing needed.
    """
    secret = ""
    env_path = "/app/backend/.env"
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except OSError:
        pass
    if not secret:
        # No bypass configured — tests still run, just susceptible to 429s.
        yield
        return

    # Monkey-patch the `requests.Session.request` path (both module-level
    # shortcut functions and Session instances delegate through this).
    original_request = requests.Session.request

    def _patched(self, method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        # Don't stomp on tests that intentionally set something different.
        headers.setdefault("X-RateLimit-Bypass", secret)
        kwargs["headers"] = headers
        return original_request(self, method, url, **kwargs)

    requests.Session.request = _patched

    # Iter 220m — the 220k/l/m + several earlier suites use `httpx.Client`
    # instead of `requests`. Patch httpx too or the auth endpoint chokes
    # under the brute-force guard during regression-suite back-to-back
    # runs. We only need the sync client; no async paths in tests today.
    httpx_orig = None
    try:
        import httpx as _httpx
        httpx_orig = _httpx.Client.request

        def _httpx_patched(self, method, url, **kwargs):
            headers = kwargs.get("headers") or {}
            if isinstance(headers, dict):
                headers.setdefault("X-RateLimit-Bypass", secret)
                kwargs["headers"] = headers
            return httpx_orig(self, method, url, **kwargs)

        _httpx.Client.request = _httpx_patched
    except Exception:
        pass

    try:
        yield
    finally:
        requests.Session.request = original_request
        if httpx_orig is not None:
            try:
                import httpx as _httpx
                _httpx.Client.request = httpx_orig
            except Exception:
                pass


@pytest.fixture(scope="session", autouse=True)
def _ensure_regular_test_user():
    """Register the default regular test user if it doesn't already exist.

    Idempotent: a 200 (created) or 400 (already exists) response both count as success.
    Silently skipped if the backend is unreachable so offline `pytest --collect-only`
    and similar commands still work.
    """
    base = _test_backend_url()
    try:
        resp = requests.post(
            f"{base}/api/auth/register",
            json={
                "email": REGULAR_USER_EMAIL,
                "password": REGULAR_USER_PASSWORD,
                "full_name": "Regular Test User",
                "company_name": "Test Org",
            },
            timeout=5,
        )
        # 200 = newly created, 400 = already registered — both are fine.
        if resp.status_code not in (200, 400):
            print(f"[conftest] Regular user register returned {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as e:
        print(f"[conftest] Could not reach backend to seed regular user: {e}")
    yield


# ── Shared session-scoped auth tokens ──────────────────────────────
# Login is rate-limited to 5 requests / 5 minutes per IP. Module/class-scoped
# fixtures that each re-login blow past that threshold during full test runs.
# The fixtures below log in ONCE per session per user and expose the tokens
# to any test that opts in by depending on them.

def _login_for_token(email: str, password: str) -> str | None:
    base = _test_backend_url()
    try:
        resp = requests.post(
            f"{base}/api/auth/login",
            json={"email": email, "password": password},
            headers=rate_limit_bypass_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("token")
        print(f"[conftest] Login failed for {email}: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as e:
        print(f"[conftest] Login request failed for {email}: {e}")
    return None


def rate_limit_bypass_headers() -> dict:
    """Rate-limit bypass header for test runs.

    Reads the `RATE_LIMIT_BYPASS_SECRET` from the backend env (same file
    FastAPI loads) and returns the matching header. Returns an empty dict
    if the secret is unset — tests then behave like normal clients.

    Note: the helper name deliberately does NOT start with `test_` so pytest
    does not auto-collect it as a test.
    """
    # backend/.env is at /app/backend/.env. Prefer env var if already exported.
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if not secret:
        try:
            env_path = "/app/backend/.env"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                            secret = line.strip().split("=", 1)[1]
                            break
        except Exception:
            pass
    return {"X-RateLimit-Bypass": secret} if secret else {}


@pytest.fixture(scope="session")
def regular_user_token(_ensure_regular_test_user) -> str | None:
    """JWT for the regular test user (logs in once per session)."""
    return _login_for_token(REGULAR_USER_EMAIL, REGULAR_USER_PASSWORD)


@pytest.fixture(scope="session")
def master_admin_token_session() -> str | None:
    """JWT for the master admin user (logs in once per session)."""
    return _login_for_token(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def pulse_pro_token() -> str | None:
    """JWT for the Pulse Pro user (logs in once per session)."""
    return _login_for_token(PULSE_PRO_EMAIL, PULSE_PRO_PASSWORD)


# ── Process-wide asyncio loop for Motor helpers ────────────────────
# Iter 238g — the shared loop now lives in ``tests/shared_loop.py`` to
# avoid the "two conftests" bug: pytest auto-imports conftest as
# ``conftest`` while explicit ``from tests.conftest import run_async``
# creates a *second* module with its own ``_SHARED_LOOP``. Putting the
# loop in a single canonical module eliminates that split.
from tests.shared_loop import _SHARED_LOOP, run_async  # noqa: E402,F401



# ── Iter 238: ensure Pulse Pro test org keeps Pro entitlements ────
# The Iter 238 Lite gating defaults all bolt-on modules (Memberships,
# Marketing, CRM) to OFF when account_type='lite'. The shared test
# fixture user `lee.somers@pulsefitness.com` is the operator owner of
# Tottenham Green Leisure Centre, which historically has all modules
# enabled. To keep regression tests (Iter 229–235) green without
# weakening the gating logic, this fixture promotes the Pulse Pro test
# org to `pulse_pro` and ensures its module matrix is fully enabled at
# session start. Iter 238's own tests use isolated lite orgs spun up
# via master admin, so they are unaffected.
@pytest.fixture(scope="session", autouse=True)
def _ensure_pulse_pro_test_org_has_pro_access():
    """Promote the Pulse Pro test org to `pulse_pro` and enable all
    bolt-on modules so existing regression tests can hit Marketing/CRM
    endpoints. Idempotent — does nothing if Motor isn't reachable."""
    try:
        from utils.database import db  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[conftest] Could not import db for Pulse Pro fixture: {exc}")
        yield
        return

    async def _promote() -> None:
        await db.organizations.update_one(
            {"id": TOTTENHAM_GREEN_ORG_ID},
            {"$set": {
                "account_type": "pulse_pro",
                "modules.operations.enabled": True,
                "modules.memberships.enabled": True,
                "modules.marketing.enabled": True,
                "modules.crm.enabled": True,
            }},
        )
        await db.users.update_one(
            {"email": PULSE_PRO_EMAIL},
            {"$set": {"account_type": "pulse_pro"}},
        )

    try:
        run_async(_promote())
    except Exception as exc:  # pragma: no cover
        print(f"[conftest] Could not promote Pulse Pro test org: {exc}")
    yield



# ── CI live-server skip ────────────────────────────────────────────
#
# A subset of the regression suite is "live-server style": it logs into
# the preview API, seeds demo data, then assertions hit /api/* endpoints.
# Those tests cannot run inside the GitHub Quality Gate sandbox (no
# egress to the preview pod + a fresh empty Mongo). When the CI marker
# is set we skip them by file path. Local devs (CI unset) run the full
# suite as before.

_LIVE_SERVER_TEST_FILES = (
    # h120 — MOD HQ rollup / drilldown (needs preview seed + DB join)
    "test_iter_216h120_mod_scope_rollup.py",
    # h117 — MOD bulk-import (master-admin live endpoint)
    "test_iter_216h117_mod_bulk_import.py",
    # h113f — MOD portal isolation (preview seed dependency)
    "test_iter_216h113f_mod_portal_isolation.py",
    # h133 — Engineer phase 3 (inserts via local Mongo, reads via remote API)
    "test_iter_216h133_engineer_phase3.py",
)


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """Skip live-server tests when running inside GitHub Actions CI."""
    if not (os.environ.get("CI", "").lower() == "true" or os.environ.get("GITHUB_ACTIONS", "").lower() == "true"):
        return
    skip_marker = pytest.mark.skip(
        reason="Live-server test skipped in CI sandbox (no preview egress / DB mismatch).",
    )
    live_modules = {
        "tests.test_iter_216h120_mod_scope_rollup",
        "tests.test_iter_216h117_mod_bulk_import",
        "tests.test_iter_216h113f_mod_portal_isolation",
        "tests.test_iter_216h133_engineer_phase3",
    }
    for item in items:
        # Match via the source module of the underlying test function so
        # the regression suite's re-exported tests are also skipped.
        func = getattr(item, "function", None)
        module = getattr(func, "__module__", "") if func else ""
        path = str(getattr(item, "fspath", "")) or str(getattr(item, "path", ""))
        if module in live_modules or any(name in path for name in _LIVE_SERVER_TEST_FILES):
            item.add_marker(skip_marker)
