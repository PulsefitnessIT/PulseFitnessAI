#!/usr/bin/env python3
"""uptime_monitor.py — Iter 216h298

State-change-only uptime monitor for GymAxis production. Designed
to run on a 5-minute cron via the deploy host's scheduler.

Behaviour
---------
1. Runs the same 6-probe smoke as `make post-deploy` (DRY — we
   import `run_probes` from `post-deploy.py` rather than duplicate).
2. Loads the previous state from `/app/reports/uptime-state.json`.
3. Emails the operator **only when state changes** (green→red or
   red→green). Steady-state runs are silent.
4. Persists the new state. Always exits 0 so cron doesn't itself
   email about non-zero scripts.

State file shape
----------------
    {
      "last_status": "ok" | "fail",
      "last_changed_at": ISO8601,
      "last_checked_at": ISO8601,
      "consecutive": int,            # how long the current state has held
      "results": [{name, ok, status_code, detail, duration_ms}, …]
    }

Env contract
------------
Same as `post-deploy` (POST_DEPLOY_BASE_URL et al). Plus:
    UPTIME_NOTIFY_EMAIL   — recipient for state-change emails.
                            Falls back to POST_DEPLOY_NOTIFY_EMAIL.
    UPTIME_STATE_PATH     — override state file location (default
                            `/app/reports/uptime-state.json`).

Cron suggestion (every 5 minutes):
    */5 * * * * cd /app && UPTIME_NOTIFY_EMAIL=ops@yourco.com \\
                 POST_DEPLOY_BASE_URL=https://gymaxisai.com \\
                 make uptime-check >>/var/log/uptime.log 2>&1
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/app")
DEFAULT_STATE_PATH = REPO_ROOT / "reports" / "uptime-state.json"


def _load_post_deploy():
    """post-deploy.py has a hyphen in its name so we can't `import` it
    directly. Load it via importlib so we can re-use `run_probes` and
    the HTML body builder verbatim — DRY beats copy-paste."""
    spec = importlib.util.spec_from_file_location(
        "post_deploy", REPO_ROOT / "scripts" / "post-deploy.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["post_deploy"] = module
    spec.loader.exec_module(module)
    return module


def _state_path() -> Path:
    raw = os.environ.get("UPTIME_STATE_PATH")
    return Path(raw) if raw else DEFAULT_STATE_PATH


def load_state(path: Path) -> dict | None:
    """Return ``None`` on a missing or unreadable state file (treated
    the same as a fresh install)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def overall_status(results) -> str:
    """Aggregate probe results into "ok" or "fail". A skipped probe
    does NOT contribute to status — the operator opts probes in/out
    explicitly via env vars."""
    for r in results:
        if r.skipped:
            continue
        if not r.ok:
            return "fail"
    return "ok"


def decide_action(prev_state: dict | None, new_status: str, *, now_iso: str) -> tuple[str, dict]:
    """Compute the next state file payload AND whether we should
    email. Returns ``(action, new_state)`` where ``action`` is one
    of:
        "first-run"        — no prior state; record + notify so the
                             operator knows monitoring is active
        "state-change"     — green→red or red→green; notify
        "steady"           — same status as before; silent
    """
    if prev_state is None:
        return "first-run", {
            "last_status": new_status,
            "last_changed_at": now_iso,
            "last_checked_at": now_iso,
            "consecutive": 1,
        }
    prev_status = prev_state.get("last_status")
    if prev_status == new_status:
        return "steady", {
            **prev_state,
            "last_checked_at": now_iso,
            "consecutive": int(prev_state.get("consecutive", 1)) + 1,
        }
    return "state-change", {
        "last_status": new_status,
        "last_changed_at": now_iso,
        "last_checked_at": now_iso,
        "consecutive": 1,
        "previous_status": prev_status,
    }


def _format_subject(action: str, new_status: str, base: str) -> str:
    if action == "first-run":
        flag = "ONLINE" if new_status == "ok" else "DOWN"
        return f"[uptime] {base} · monitoring started · {flag}"
    if action == "state-change":
        if new_status == "ok":
            return f"[uptime] ✅ RECOVERED · {base}"
        return f"[uptime] 🚨 DOWN · {base}"
    return ""


async def _maybe_email(subject: str, html: str) -> bool:
    if not subject:
        return False
    recipient = (
        os.environ.get("UPTIME_NOTIFY_EMAIL")
        or os.environ.get("POST_DEPLOY_NOTIFY_EMAIL")
    )
    if not recipient:
        return False
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        from utils.email import send_email
    except Exception as exc:  # pragma: no cover — environmental
        print(f"!  notify email skipped — backend imports unavailable: {exc}",
              file=sys.stderr)
        return False
    return await send_email(recipient, subject, html)


# ── Entrypoint ─────────────────────────────────────────────────────


async def run_once(state_path: Path | None = None) -> tuple[str, str]:
    """Single uptime check. Returns ``(action, new_status)`` so the
    test suite can assert on outcomes without inspecting global state.
    """
    path = state_path or _state_path()
    pd = _load_post_deploy()
    base = pd._base_url()
    if not base:
        print("✗ POST_DEPLOY_BASE_URL (or REACT_APP_BACKEND_URL) is not set.",
              file=sys.stderr)
        return "no-base-url", "unknown"

    timeout_s = float(os.environ.get("POST_DEPLOY_TIMEOUT_S", "10"))
    start = time.monotonic()
    results = await pd.run_probes(base, timeout_s)
    total_ms = int((time.monotonic() - start) * 1000)

    new_status = overall_status(results)
    now_iso = datetime.now(timezone.utc).isoformat()
    prev = load_state(path)
    action, new_state = decide_action(prev, new_status, now_iso=now_iso)

    # Persist the probe details on the new state so the operator can
    # eyeball the state file directly without firing a fresh check.
    new_state["results"] = [asdict(r) for r in results]
    new_state["base_url"] = base
    new_state["total_ms"] = total_ms
    save_state(path, new_state)

    print(f"[uptime] {action} · status={new_status} · "
          f"consecutive={new_state.get('consecutive')} · {total_ms}ms")

    if action in ("state-change", "first-run"):
        subject = _format_subject(action, new_status, base)
        all_ok = (new_status == "ok")
        html_body = pd._format_html(results, base, total_ms, all_ok=all_ok)
        # Add a tiny header on top so the operator sees the change
        # context without reading the table.
        if action == "state-change":
            prev_status = (prev or {}).get("last_status", "?")
            banner = (
                f'<p style="background:#FEF3C7;border-left:3px solid #F59E0B;'
                f'padding:10px 14px;margin:0 0 12px;color:#78350F;">'
                f'State change detected: <strong>{prev_status} → {new_status}</strong>'
                f'</p>'
            )
            html_body = banner + html_body
        if await _maybe_email(subject, html_body):
            print("[uptime] notification dispatched")

    return action, new_status


async def main() -> int:
    action, status = await run_once()
    # Exit 0 even on probe failure — a non-zero exit makes cron itself
    # send "command failed" emails which would defeat the whole point
    # of this state-change-only design.
    if action == "no-base-url":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
