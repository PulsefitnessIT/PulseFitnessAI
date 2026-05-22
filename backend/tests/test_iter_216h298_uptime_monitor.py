"""Iter 216h298 — `make uptime-check` state-change-only monitor pin.

Cron-friendly uptime monitor that re-uses the post-deploy probe
set but emails only on state change (green→red or red→green).
Lives downstream of post-deploy.py — both contracts must keep
working in lockstep.

Pins covered
------------
* `_state_path` honours `UPTIME_STATE_PATH` override
* `load_state` returns None on missing / unreadable JSON
* `save_state` round-trips through json.load
* `overall_status` ignores skipped probes; flips to "fail" on
  any required probe failure
* `decide_action` first-run / state-change / steady transitions
* `decide_action` increments the consecutive counter on steady
* `_format_subject` distinguishes ONLINE / DOWN / RECOVERED
* Cron-safe: `main()` exits 0 even on probe failure (otherwise
  cron itself sends "command failed" mail and defeats the point)
* Makefile `.PHONY` + `make help` wiring
* Script is executable
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SCRIPT_PATH = Path("/app/scripts/uptime_monitor.py")
MAKEFILE = Path("/app/Makefile")


def _load_module():
    spec = importlib.util.spec_from_file_location("uptime_monitor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["uptime_monitor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_module()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# Re-define the dataclass shape locally so the tests don't need to
# import post-deploy.py through hyphenated importlib gymnastics.
@dataclass
class _ProbeStub:
    name: str
    method: str = "GET"
    path: str = "/x"
    ok: bool = True
    status: int = 200
    detail: str = "ok"
    duration_ms: int = 50
    skipped: bool = False


# ── State path resolution ──────────────────────────────────────────


def test_state_path_default(script, monkeypatch):
    monkeypatch.delenv("UPTIME_STATE_PATH", raising=False)
    assert str(script._state_path()).endswith("uptime-state.json")


def test_state_path_honours_override(script, monkeypatch, tmp_path):
    override = tmp_path / "custom.json"
    monkeypatch.setenv("UPTIME_STATE_PATH", str(override))
    assert script._state_path() == override


# ── load / save state ──────────────────────────────────────────────


def test_load_state_missing_file_returns_none(script, tmp_path):
    assert script.load_state(tmp_path / "nonexistent.json") is None


def test_load_state_corrupt_json_returns_none(script, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not-valid-json {", encoding="utf-8")
    assert script.load_state(bad) is None


def test_save_state_creates_parent_dir(script, tmp_path):
    nested = tmp_path / "deep" / "nest" / "state.json"
    payload = {"last_status": "ok", "consecutive": 3}
    script.save_state(nested, payload)
    assert nested.exists()
    assert json.loads(nested.read_text())["consecutive"] == 3


# ── overall_status ────────────────────────────────────────────────


def test_overall_status_ok_when_all_pass(script):
    results = [_ProbeStub("a", ok=True), _ProbeStub("b", ok=True)]
    assert script.overall_status(results) == "ok"


def test_overall_status_fail_on_any_required_failure(script):
    results = [
        _ProbeStub("a", ok=True),
        _ProbeStub("b", ok=False, detail="boom"),
        _ProbeStub("c", ok=True),
    ]
    assert script.overall_status(results) == "fail"


def test_overall_status_ignores_skipped_probes(script):
    """A skipped probe is informational — it must not flip the
    overall status to fail (otherwise the operator's first run on
    a fresh deploy host would always alert)."""
    results = [
        _ProbeStub("a", ok=True),
        _ProbeStub("b", ok=True, skipped=True, detail="skipped"),
    ]
    assert script.overall_status(results) == "ok"


# ── decide_action ──────────────────────────────────────────────────


def test_decide_action_first_run(script):
    action, state = script.decide_action(
        prev_state=None, new_status="ok", now_iso="2026-05-22T08:00:00+00:00",
    )
    assert action == "first-run"
    assert state["last_status"] == "ok"
    assert state["consecutive"] == 1
    assert state["last_changed_at"] == "2026-05-22T08:00:00+00:00"


def test_decide_action_steady_increments_consecutive(script):
    prev = {
        "last_status": "ok",
        "last_changed_at": "2026-05-22T07:55:00+00:00",
        "last_checked_at": "2026-05-22T07:55:00+00:00",
        "consecutive": 5,
    }
    action, state = script.decide_action(
        prev_state=prev, new_status="ok", now_iso="2026-05-22T08:00:00+00:00",
    )
    assert action == "steady"
    assert state["consecutive"] == 6
    # last_changed_at is preserved on steady
    assert state["last_changed_at"] == prev["last_changed_at"]


def test_decide_action_green_to_red(script):
    prev = {"last_status": "ok", "consecutive": 12,
             "last_changed_at": "2026-05-22T01:00:00+00:00"}
    action, state = script.decide_action(
        prev_state=prev, new_status="fail",
        now_iso="2026-05-22T08:00:00+00:00",
    )
    assert action == "state-change"
    assert state["last_status"] == "fail"
    assert state["consecutive"] == 1
    assert state["previous_status"] == "ok"


def test_decide_action_red_to_green(script):
    prev = {"last_status": "fail", "consecutive": 3,
             "last_changed_at": "2026-05-22T07:30:00+00:00"}
    action, state = script.decide_action(
        prev_state=prev, new_status="ok",
        now_iso="2026-05-22T08:00:00+00:00",
    )
    assert action == "state-change"
    assert state["previous_status"] == "fail"


# ── _format_subject ────────────────────────────────────────────────


def test_format_subject_first_run_online(script):
    s = script._format_subject("first-run", "ok", "https://prod")
    assert "monitoring started" in s
    assert "ONLINE" in s


def test_format_subject_first_run_down(script):
    s = script._format_subject("first-run", "fail", "https://prod")
    assert "DOWN" in s


def test_format_subject_state_change_recovered(script):
    s = script._format_subject("state-change", "ok", "https://prod")
    assert "RECOVERED" in s


def test_format_subject_state_change_down(script):
    s = script._format_subject("state-change", "fail", "https://prod")
    assert "DOWN" in s
    assert "🚨" in s


def test_format_subject_steady_returns_empty(script):
    """Steady-state must not produce a subject — the email helper
    short-circuits on empty subjects so no notification fires."""
    assert script._format_subject("steady", "ok", "https://prod") == ""


# ── run_once / cron-safe exit ──────────────────────────────────────


def test_run_once_first_run_persists_state(script, tmp_path, monkeypatch):
    """First run with no prior state writes a state-change-flagged
    record and (when an email recipient is set) attempts a
    notification."""
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("POST_DEPLOY_BASE_URL", "https://example.com")
    monkeypatch.setenv("UPTIME_NOTIFY_EMAIL", "ops@example.com")

    fake_probes = [_ProbeStub("a", ok=True), _ProbeStub("b", ok=True)]
    sender = AsyncMock(return_value=True)

    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: "https://example.com"
    pd_mock.run_probes = AsyncMock(return_value=fake_probes)
    pd_mock._format_html = lambda *a, **k: "<div>ok</div>"

    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock), \
         patch("uptime_monitor._maybe_email", sender):
        action, status = _run(script.run_once(state_path=state_path))

    assert action == "first-run"
    assert status == "ok"
    assert state_path.exists()
    persisted = json.loads(state_path.read_text())
    assert persisted["last_status"] == "ok"
    assert persisted["consecutive"] == 1
    assert persisted["base_url"] == "https://example.com"
    sender.assert_awaited_once()


def test_run_once_steady_state_does_not_email(script, tmp_path, monkeypatch):
    """Once the monitor has been running and the system is healthy,
    every 5-minute tick must be silent. If we email on steady-state
    OK, the operator's inbox dies."""
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "last_status": "ok",
        "last_changed_at": "2026-05-22T01:00:00+00:00",
        "last_checked_at": "2026-05-22T07:55:00+00:00",
        "consecutive": 50,
    }))
    monkeypatch.setenv("POST_DEPLOY_BASE_URL", "https://example.com")
    monkeypatch.setenv("UPTIME_NOTIFY_EMAIL", "ops@example.com")

    sender = AsyncMock(return_value=True)
    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: "https://example.com"
    pd_mock.run_probes = AsyncMock(return_value=[_ProbeStub("a", ok=True)])
    pd_mock._format_html = lambda *a, **k: "<div>ok</div>"

    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock), \
         patch("uptime_monitor._maybe_email", sender):
        action, _ = _run(script.run_once(state_path=state_path))

    assert action == "steady"
    sender.assert_not_awaited()
    # Counter ticks up
    assert json.loads(state_path.read_text())["consecutive"] == 51


def test_run_once_state_change_emails_with_banner(script, tmp_path, monkeypatch):
    """The most important pin — green→red MUST emit an email with
    a clearly-marked "state change detected" banner."""
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "last_status": "ok", "consecutive": 12,
        "last_changed_at": "2026-05-22T01:00:00+00:00",
        "last_checked_at": "2026-05-22T07:55:00+00:00",
    }))
    monkeypatch.setenv("POST_DEPLOY_BASE_URL", "https://example.com")
    monkeypatch.setenv("UPTIME_NOTIFY_EMAIL", "ops@example.com")

    captured = {}

    async def fake_send(subject, html):
        captured["subject"] = subject
        captured["html"] = html
        return True

    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: "https://example.com"
    pd_mock.run_probes = AsyncMock(return_value=[
        _ProbeStub("a", ok=True), _ProbeStub("b", ok=False, detail="boom"),
    ])
    pd_mock._format_html = lambda *a, **k: "<table>probes</table>"

    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock), \
         patch("uptime_monitor._maybe_email", fake_send):
        action, status = _run(script.run_once(state_path=state_path))

    assert (action, status) == ("state-change", "fail")
    assert "DOWN" in captured["subject"]
    assert "ok → fail" in captured["html"]
    assert "State change detected" in captured["html"]


def test_run_once_no_base_url_returns_sentinel(script, tmp_path, monkeypatch):
    """Without a base URL the script can't probe anything. Return a
    distinct action sentinel + non-zero exit — but ONLY for this
    catastrophic case."""
    monkeypatch.delenv("POST_DEPLOY_BASE_URL", raising=False)
    monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: None
    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock):
        action, status = _run(script.run_once(state_path=tmp_path / "s.json"))
    assert action == "no-base-url"


def test_main_exits_zero_on_probe_failure(script, tmp_path, monkeypatch):
    """Cron emails on non-zero scripts. Since this monitor's whole
    point is to control its own notifications, it must NEVER let
    cron get involved — even when a probe fails."""
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("UPTIME_STATE_PATH", str(state_path))
    monkeypatch.setenv("POST_DEPLOY_BASE_URL", "https://example.com")
    monkeypatch.delenv("UPTIME_NOTIFY_EMAIL", raising=False)
    monkeypatch.delenv("POST_DEPLOY_NOTIFY_EMAIL", raising=False)

    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: "https://example.com"
    pd_mock.run_probes = AsyncMock(return_value=[_ProbeStub("a", ok=False, detail="500")])
    pd_mock._format_html = lambda *a, **k: "<div/>"

    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock):
        rc = _run(script.main())

    assert rc == 0, "main() must exit 0 even on probe failure (cron-safety)"


def test_main_exits_two_when_no_base_url(script, monkeypatch):
    monkeypatch.delenv("POST_DEPLOY_BASE_URL", raising=False)
    monkeypatch.delenv("REACT_APP_BACKEND_URL", raising=False)
    pd_mock = type("PD", (), {})()
    pd_mock._base_url = lambda: None
    with patch("uptime_monitor._load_post_deploy", return_value=pd_mock):
        rc = _run(script.main())
    # Catastrophic-config exit is the one exception to the cron-safety rule
    assert rc == 2


# ── Makefile + executability ───────────────────────────────────────


def test_makefile_exposes_uptime_check_target():
    text = MAKEFILE.read_text(encoding="utf-8")
    phony = next((line for line in text.splitlines() if line.startswith(".PHONY:")), "")
    assert "uptime-check" in phony
    assert "scripts/uptime_monitor.py" in text


def test_makefile_help_advertises_uptime_check():
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "make uptime-check" in text


def test_script_is_executable():
    import os
    assert SCRIPT_PATH.is_file()
    assert os.access(SCRIPT_PATH, os.X_OK)
