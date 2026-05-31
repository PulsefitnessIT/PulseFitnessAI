"""Iter 220ea — Engineer App Playwright smoke spec source guard.

Pure static-source check (mirrors the pattern of
``test_iter_220db_image_compression.py``) so the regression suite
catches drift in the new Engineer App E2E smoke spec — drift such
as someone renaming a critical testid that the spec asserts on, or
deleting a route from the smoke list, even when no preview backend
is available to actually run Playwright.

The spec itself lives at
``/app/frontend/tests/mobile-regression/engineer-smoke.spec.js``
and is invoked via ``yarn test:mobile-regression``.
"""
from __future__ import annotations

from pathlib import Path


SPEC = Path("/app/frontend/tests/mobile-regression/engineer-smoke.spec.js")
GLOBAL_SETUP = Path("/app/frontend/tests/mobile-regression/global-setup.js")
PW_CONFIG = Path("/app/frontend/playwright.config.js")


def _spec_src() -> str:
    return SPEC.read_text()


# ── 1 · The spec file exists and lists every smoke route ─────────


def test_engineer_smoke_spec_exists():
    assert SPEC.is_file(), f"missing Playwright spec: {SPEC}"
    src = _spec_src()
    assert "Engineer App — smoke" in src
    assert "Engineer App — offline pill wiring" in src


def test_engineer_smoke_covers_all_required_routes():
    src = _spec_src()
    required = [
        ("/svc/engineer",          "engineer-home-v2"),
        ("/svc/engineer/jobs",     "engineer-home"),
        ("/svc/engineer/quotes",   "engineer-quotes"),
        ("/svc/engineer/invoices", "engineer-invoices"),
        ("/svc/engineer/diary",    "engineer-diary"),
        ("/svc/engineer/inbox",    "engineer-inbox"),
    ]
    for path, happy_testid in required:
        assert f"'{path}'" in src, f"smoke spec missing route {path}"
        assert f"'{happy_testid}'" in src, (
            f"smoke spec missing happy-path testid {happy_testid}"
        )


# ── 2 · The spec checks for the error boundary + access gate ────


def test_engineer_smoke_asserts_against_error_boundary():
    src = _spec_src()
    assert "engineer-error-boundary" in src, (
        "spec must catch the EngineerErrorBoundary fallback"
    )
    # Allow either happy testid OR access-gate landing — Master Admin
    # without partner-engineer onboarding legitimately lands on the gate.
    assert "engineer-access-gate-" in src


def test_engineer_smoke_asserts_offline_pill_wiring():
    src = _spec_src()
    assert "offline-pill" in src
    # navigator.onLine flip + manual event dispatch.
    assert "context.setOffline(true)" in src
    assert "context.setOffline(false)" in src
    assert "new Event('offline')" in src
    assert "new Event('online')" in src


def test_engineer_smoke_filters_known_console_noise():
    """The spec must NOT fail on benign dev-mode console noise
    (React DevTools, posthog, 401 warmup). Anything outside the
    allow-list is a real regression."""
    src = _spec_src()
    assert "CONSOLE_NOISE" in src
    assert "/Download the React DevTools/i" in src
    assert "/posthog/i" in src
    assert "/401/i" in src


# ── 3 · Global setup uses the resilient API-driven login ────────


def test_global_setup_uses_api_login_not_ui_flow():
    """The previous UI-driven global setup was intermittently flaky
    on the preview env (cookie banner race + lazy-bundle hydration
    delay). The current version POSTs the credentials directly and
    seeds the JWT into localStorage via addInitScript."""
    src = GLOBAL_SETUP.read_text()
    assert "fetchAdminToken" in src
    assert "/api/auth/login" in src
    assert "addInitScript" in src
    assert "localStorage.setItem('token'" in src
    # The UI-driven flow has been removed.
    assert "waitForURL(/" not in src, (
        "global-setup should not rely on UI-driven waitForURL anymore"
    )


def test_global_setup_resolves_backend_url_from_dotenv():
    """When REACT_APP_BACKEND_URL isn't exported in the shell, the
    helper should fall back to /app/frontend/.env so the preview
    URL is used instead of localhost:3000."""
    src = GLOBAL_SETUP.read_text()
    assert "resolveBaseURL" in src
    assert "REACT_APP_BACKEND_URL=" in src or "REACT_APP_BACKEND_URL" in src
    assert ".env" in src


def test_playwright_config_resolves_baseurl_from_dotenv():
    """Mirror of the global-setup fix — the runner config itself
    must consult /app/frontend/.env for the backend URL when shell
    env is empty, otherwise baseURL silently defaults to localhost."""
    src = PW_CONFIG.read_text()
    assert "resolveBaseURL" in src
    assert "REACT_APP_BACKEND_URL" in src


# ── 4 · package.json wires the runner ───────────────────────────


def test_package_json_exposes_mobile_regression_script():
    pkg = Path("/app/frontend/package.json").read_text()
    assert "test:mobile-regression" in pkg
    assert "playwright" in pkg
