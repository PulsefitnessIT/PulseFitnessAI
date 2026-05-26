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

The `_shared_event_loop` autouse session fixture (iter 220m) gives the
whole pytest session ONE shared asyncio event loop. Many of our tests
call `asyncio.get_event_loop().run_until_complete(...)` to drive a
coroutine synchronously. On Python 3.11+, `get_event_loop()` raises
`RuntimeError: There is no current event loop in thread 'MainThread'`
as soon as any earlier `asyncio.run(...)` closes the previous loop —
which is what was producing the cascading regression-suite failures.
Pre-registering a single session-wide loop also keeps every Motor
connection pool bound to the same loop, eliminating the
`Future attached to a different loop` errors we'd otherwise hit.
"""
import asyncio
import os
import pytest
import requests

API_BASE_URL = os.environ.get("TEST_API_URL", "https://maintenance-hub-357.preview.emergentagent.com")

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


@pytest.fixture(scope="session", autouse=True)
def _shared_event_loop():
    """Install a single shared asyncio event loop for the entire pytest
    session. See module docstring for the full rationale (iter 220m)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()


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
    try:
        yield
    finally:
        requests.Session.request = original_request


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
