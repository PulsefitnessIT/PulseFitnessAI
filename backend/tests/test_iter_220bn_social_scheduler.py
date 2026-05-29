"""Iter 220bn — Daily Social Autopilot scheduler wiring.

Locks in:

1. ``run_daily_social_loop`` is exported from the route module.
2. ``server.py`` schedules the loop at startup, gated by the
   ``SOCIAL_AUTOPILOT_ENABLED`` env var.
3. The idempotency stamp uses a dedicated ``social_autopilot_runs``
   collection (separate from SEO so a same-day SEO run doesn't gate
   the social run, and vice-versa).
"""
from __future__ import annotations

import pathlib


REPO = pathlib.Path(__file__).resolve().parent.parent.parent


def test_route_module_exports_loop():
    src = (REPO / "backend" / "routes" / "marketing" / "social_autopilot.py").read_text(encoding="utf-8")
    assert "async def run_daily_social_loop" in src, (
        "Daily loop function missing from social_autopilot module"
    )
    assert "__all__" in src and "run_daily_social_loop" in src
    # Idempotency stamp must use its own collection (not seo's).
    assert "social_autopilot_runs" in src
    assert "_social_already_ran_today" in src


def test_server_schedules_social_loop_alongside_seo():
    src = (REPO / "backend" / "server.py").read_text(encoding="utf-8")
    assert "run_daily_social_loop" in src, (
        "server.py must import the social daily loop at startup"
    )
    assert "SOCIAL_AUTOPILOT_ENABLED" in src, (
        "Loop must be gateable via env var, same pattern as SEO"
    )
    # Sanity check that we're using asyncio.create_task (consistent
    # with every other long-running loop in server.py).
    assert "asyncio.create_task(run_daily_social_loop" in src


def test_loop_reads_config_each_iteration():
    """Re-reading config inside the loop is what makes the UI's
    Enabled / hour toggle take effect without a backend restart."""
    src = (REPO / "backend" / "routes" / "marketing" / "social_autopilot.py").read_text(encoding="utf-8")
    # Grab the function body.
    start = src.find("async def run_daily_social_loop")
    assert start > 0
    body = src[start:start + 2000]
    assert "_load_config()" in body, (
        "Loop body must call _load_config() so UI changes propagate live"
    )
    assert "channels_enabled" in src, (
        "Daily run helper must honour channels_enabled from config"
    )


def test_loop_uses_15_minute_cadence():
    src = (REPO / "backend" / "routes" / "marketing" / "social_autopilot.py").read_text(encoding="utf-8")
    assert "15 * 60" in src, (
        "Daily loop should sleep 15 minutes between hour-checks — "
        "same as the SEO loop"
    )


def test_separate_runs_collection_from_seo():
    """Critical safety: social and SEO runs collections must be
    independent. Otherwise enabling one would silently lock the
    other for the day."""
    src = (REPO / "backend" / "routes" / "marketing" / "social_autopilot.py").read_text(encoding="utf-8")
    assert "seo_autopilot_runs" not in src, (
        "Social loop must NOT touch seo_autopilot_runs"
    )
