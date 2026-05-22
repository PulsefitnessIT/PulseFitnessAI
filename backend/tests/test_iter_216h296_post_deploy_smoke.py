"""Iter 216h296 — `make post-deploy` smoke pin.

The post-deploy smoke target is the last layer of the operator
trust stack. It must:
  • exist as both a Python script and a Makefile target
  • exit non-zero when any required probe fails
  • exit zero when every required probe passes
  • degrade gracefully when optional env vars are missing
    (skip the probe rather than fail the run)
  • format a readable text summary AND a structured HTML body

This test exercises the helpers in-process (no HTTPS round-trip)
by stubbing httpx so the regression is fast and deterministic.

Pins covered
------------
* `_base_url` reads POST_DEPLOY_BASE_URL with fallback chain
* `_format_text` returns FAIL summary + sets all_ok=False on
  any non-skipped failure
* `_format_text` returns PASS when every probe is ok or skipped
* `_format_html` renders OK / FAIL / SKIP badges
* `run_probes` honours optional env vars (skips, doesn't fail)
* Makefile target `post-deploy` exists and is in `.PHONY`
* `make help` advertises the new target
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SCRIPT_PATH = Path("/app/scripts/post-deploy.py")
MAKEFILE = Path("/app/Makefile")


def _load_script_module():
    """Load post-deploy.py as a module since the hyphen in the
    filename blocks plain `import`."""
    spec = importlib.util.spec_from_file_location("post_deploy", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["post_deploy"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _base_url fallback chain ───────────────────────────────────────


def test_base_url_prefers_post_deploy_base_url(script, monkeypatch):
    monkeypatch.setenv("POST_DEPLOY_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("REACT_APP_BACKEND_URL", "https://preview.example.com")
    assert script._base_url() == "https://prod.example.com"


def test_base_url_falls_back_to_react_app_backend_url(script, monkeypatch):
    monkeypatch.delenv("POST_DEPLOY_BASE_URL", raising=False)
    monkeypatch.setenv("REACT_APP_BACKEND_URL", "https://preview.example.com")
    assert script._base_url() == "https://preview.example.com"


def test_base_url_returns_none_when_neither_set(script, monkeypatch):
    monkeypatch.delenv("POST_DEPLOY_BASE_URL", raising=False)
    monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
    assert script._base_url() is None


# ── _format_text PASS / FAIL ───────────────────────────────────────


def _ok(name="probe"):
    from post_deploy import ProbeResult
    return ProbeResult(name, "GET", "/x", True, 200, "ok", 50)


def _fail(name="probe"):
    from post_deploy import ProbeResult
    return ProbeResult(name, "GET", "/x", False, 500, "boom", 100)


def _skip(name="probe"):
    from post_deploy import ProbeResult
    return ProbeResult(name, "GET", "/x", True, 0, "skipped (no env)", 0, skipped=True)


def test_format_text_returns_pass_when_all_ok(script):
    text, ok = script._format_text([_ok("a"), _ok("b")], "https://x", 100)
    assert ok is True
    assert "PASS" in text
    assert "FAIL" not in text


def test_format_text_returns_fail_when_any_required_failed(script):
    text, ok = script._format_text([_ok("a"), _fail("b")], "https://x", 100)
    assert ok is False
    assert "FAIL" in text
    # Failed probe gets the ✗ mark
    assert "✗ b" in text


def test_format_text_skips_dont_break_pass(script):
    """A skipped probe is informational, not a fail."""
    text, ok = script._format_text([_ok("a"), _skip("b"), _ok("c")], "https://x", 100)
    assert ok is True
    assert "PASS" in text
    assert "○ b" in text  # skipped marker


# ── _format_html badges ────────────────────────────────────────────


def test_format_html_renders_three_badges(script):
    html = script._format_html(
        [_ok("a"), _fail("b"), _skip("c")], "https://x", 100, all_ok=False,
    )
    assert ">OK<" in html
    assert ">FAIL<" in html
    assert ">SKIP<" in html
    # Headline reflects overall state
    assert "Deploy regression detected" in html


def test_format_html_pass_headline(script):
    html = script._format_html([_ok("a")], "https://x", 100, all_ok=True)
    assert "Deploy healthy" in html
    assert "Deploy regression detected" not in html


# ── run_probes — graceful skips on missing env ────────────────────


def test_run_probes_skips_optional_probes_without_env(script, monkeypatch):
    """No optional env vars set → eref / reviews / auth probes are
    skipped (not failed)."""
    for k in ("POST_DEPLOY_REVIEW_PARTNER_ID", "POST_DEPLOY_EREF_CODE",
              "POST_DEPLOY_TEST_EMAIL", "POST_DEPLOY_TEST_PASSWORD"):
        monkeypatch.delenv(k, raising=False)

    # Stub the AsyncClient so we never hit the network — all required
    # probes return 200 OK with the expected keys.
    class _FakeResp:
        def __init__(self, status=200, body=None):
            self.status_code = status
            self._body = body or {"status": "ok"}
        def json(self):
            return self._body

    async def _fake_request(method, path, json=None, headers=None):
        # Match expect_keys per probe
        if path == "/api/health":
            return _FakeResp(200, {"status": "ok"})
        return _FakeResp(200, {})

    fake_client = MagicMock()
    fake_client.request = AsyncMock(side_effect=_fake_request)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("post_deploy.httpx.AsyncClient", return_value=fake_client):
        results = _run(script.run_probes("https://x", timeout_s=5))

    by_name = {r.name: r for r in results}
    assert by_name["api-health"].ok is True
    assert by_name["public-eref"].skipped is True
    assert by_name["public-reviews"].skipped is True
    assert by_name["auth-login"].skipped is True
    # Marketing root still ran
    assert by_name["marketing-root"].ok is True


def test_run_probes_runs_optional_probes_when_env_provided(script, monkeypatch):
    monkeypatch.setenv("POST_DEPLOY_EREF_CODE", "ABC123")
    monkeypatch.setenv("POST_DEPLOY_REVIEW_PARTNER_ID", "uuid-1")
    monkeypatch.setenv("POST_DEPLOY_TEST_EMAIL", "ops@x.io")
    monkeypatch.setenv("POST_DEPLOY_TEST_PASSWORD", "pw")

    paths_hit: list[str] = []

    async def _fake_request(method, path, json=None, headers=None):
        paths_hit.append(f"{method} {path}")
        class _R:
            status_code = 200
            def json(self):
                # Cover every expect_keys assertion the probes make
                return {
                    "status": "ok", "referral_code": "ABC123",
                    "apply_url": "/x", "partner": {}, "summary": {},
                    "token": "jwt",
                }
        return _R()

    fake_client = MagicMock()
    fake_client.request = AsyncMock(side_effect=_fake_request)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch("post_deploy.httpx.AsyncClient", return_value=fake_client):
        results = _run(script.run_probes("https://x", timeout_s=5))

    by_name = {r.name: r for r in results}
    assert by_name["public-eref"].skipped is False
    assert by_name["public-eref"].ok is True
    assert by_name["public-reviews"].ok is True
    assert by_name["auth-login"].ok is True
    # Auth probe was POST not GET
    assert any("POST /api/auth/login" in h for h in paths_hit)


# ── Makefile wiring ────────────────────────────────────────────────


def test_makefile_exposes_post_deploy_target():
    text = MAKEFILE.read_text(encoding="utf-8")
    # Listed in .PHONY
    phony = next((line for line in text.splitlines() if line.startswith(".PHONY:")), "")
    assert "post-deploy" in phony, "post-deploy missing from .PHONY"
    # Body invokes the python script
    assert "scripts/post-deploy.py" in text


def test_makefile_help_advertises_post_deploy():
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "make post-deploy" in text


def test_post_deploy_script_is_executable():
    import os
    assert SCRIPT_PATH.is_file()
    assert os.access(SCRIPT_PATH, os.X_OK), "post-deploy.py is not executable"
