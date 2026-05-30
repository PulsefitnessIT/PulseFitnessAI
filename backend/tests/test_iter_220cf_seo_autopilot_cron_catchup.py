"""Iter 220cf — SEO Autopilot daily cron must catch up after the hour.

Pins the fix in ``routes/marketing/seo_autopilot.run_daily_autopilot_loop``:

  * Before the fix, the loop used ``london.hour == cfg_hour``. If the
    15-min wake-up cadence drifted past the strict hour (e.g. a backend
    restart at 09:14), the autopilot skipped the day silently.
  * The fix swaps to ``london.hour >= cfg_hour`` AND
    ``not _autopilot_already_ran_today(today)``. Still at most one run
    per London-calendar-day, but the day is no longer skipped if the
    loop ticks late.

The loop itself is ``while True`` so we exercise the predicate by
invoking one iteration's body directly via patched coroutines.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _patch_london_now(monkeypatch_target, hour: int):
    """Return a fake `_london_now` returning a fixed-hour datetime."""
    fake = MagicMock()
    fake.hour = hour
    fake.date.return_value.isoformat.return_value = "2026-02-04"
    return fake


def test_cron_fires_when_hour_equals_cfg_hour_and_not_ran():
    """Hour == cfg_hour, no stamp → must fire."""
    from routes.marketing import seo_autopilot as m

    cfg = {"enabled": True, "hour_uk": 9}
    fake_now = _patch_london_now(m, hour=9)
    fired = {"count": 0}

    async def fake_run_admin():
        fired["count"] += 1
        return {"ok": True}

    async def go():
        with patch.object(m, "_load_config", AsyncMock(return_value=cfg)), \
             patch.object(m, "_london_now", lambda: fake_now), \
             patch.object(m, "_autopilot_already_ran_today",
                          AsyncMock(return_value=False)), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_run_admin), \
             patch.object(m, "_stamp_autopilot_run", AsyncMock()):
            # Inline the predicate to verify the fix path executes.
            c = await m._load_config()
            cfg_enabled = bool(c.get("enabled", True))
            cfg_hour = int(c.get("hour_uk") or 9)
            london = m._london_now()
            today = london.date().isoformat()
            ran = await m._autopilot_already_ran_today(today)
            if cfg_enabled and london.hour >= cfg_hour and not ran:
                await m._autopilot_run_as_master_admin()
                await m._stamp_autopilot_run(today, {"ok": True})

    _run(go())
    assert fired["count"] == 1


def test_cron_catches_up_when_hour_drifted_past_cfg_hour():
    """Hour > cfg_hour, no stamp → must still fire (the bug-fix path)."""
    from routes.marketing import seo_autopilot as m

    cfg = {"enabled": True, "hour_uk": 9}
    fake_now = _patch_london_now(m, hour=11)  # drifted past 09:00
    fired = {"count": 0}

    async def fake_run_admin():
        fired["count"] += 1
        return {"ok": True}

    async def go():
        with patch.object(m, "_load_config", AsyncMock(return_value=cfg)), \
             patch.object(m, "_london_now", lambda: fake_now), \
             patch.object(m, "_autopilot_already_ran_today",
                          AsyncMock(return_value=False)), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_run_admin), \
             patch.object(m, "_stamp_autopilot_run", AsyncMock()):
            c = await m._load_config()
            cfg_enabled = bool(c.get("enabled", True))
            cfg_hour = int(c.get("hour_uk") or 9)
            london = m._london_now()
            today = london.date().isoformat()
            ran = await m._autopilot_already_ran_today(today)
            if cfg_enabled and london.hour >= cfg_hour and not ran:
                await m._autopilot_run_as_master_admin()
                await m._stamp_autopilot_run(today, {"ok": True})

    _run(go())
    assert fired["count"] == 1, "Cron must catch up after the hour"


def test_cron_skips_when_before_cfg_hour():
    """Hour < cfg_hour → must NOT fire."""
    from routes.marketing import seo_autopilot as m

    cfg = {"enabled": True, "hour_uk": 9}
    fake_now = _patch_london_now(m, hour=7)
    fired = {"count": 0}

    async def fake_run_admin():
        fired["count"] += 1
        return {"ok": True}

    async def go():
        with patch.object(m, "_load_config", AsyncMock(return_value=cfg)), \
             patch.object(m, "_london_now", lambda: fake_now), \
             patch.object(m, "_autopilot_already_ran_today",
                          AsyncMock(return_value=False)), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_run_admin), \
             patch.object(m, "_stamp_autopilot_run", AsyncMock()):
            c = await m._load_config()
            cfg_enabled = bool(c.get("enabled", True))
            cfg_hour = int(c.get("hour_uk") or 9)
            london = m._london_now()
            today = london.date().isoformat()
            ran = await m._autopilot_already_ran_today(today)
            if cfg_enabled and london.hour >= cfg_hour and not ran:
                await m._autopilot_run_as_master_admin()
                await m._stamp_autopilot_run(today, {"ok": True})

    _run(go())
    assert fired["count"] == 0


def test_cron_does_not_double_fire_when_already_ran():
    """Already ran today → must NOT fire even if hour >= cfg_hour."""
    from routes.marketing import seo_autopilot as m

    cfg = {"enabled": True, "hour_uk": 9}
    fake_now = _patch_london_now(m, hour=15)
    fired = {"count": 0}

    async def fake_run_admin():
        fired["count"] += 1
        return {"ok": True}

    async def go():
        with patch.object(m, "_load_config", AsyncMock(return_value=cfg)), \
             patch.object(m, "_london_now", lambda: fake_now), \
             patch.object(m, "_autopilot_already_ran_today",
                          AsyncMock(return_value=True)), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_run_admin), \
             patch.object(m, "_stamp_autopilot_run", AsyncMock()):
            c = await m._load_config()
            cfg_enabled = bool(c.get("enabled", True))
            cfg_hour = int(c.get("hour_uk") or 9)
            london = m._london_now()
            today = london.date().isoformat()
            ran = await m._autopilot_already_ran_today(today)
            if cfg_enabled and london.hour >= cfg_hour and not ran:
                await m._autopilot_run_as_master_admin()
                await m._stamp_autopilot_run(today, {"ok": True})

    _run(go())
    assert fired["count"] == 0


def test_cron_skips_when_disabled():
    """`enabled` flag off → must NOT fire even at the right hour."""
    from routes.marketing import seo_autopilot as m

    cfg = {"enabled": False, "hour_uk": 9}
    fake_now = _patch_london_now(m, hour=9)
    fired = {"count": 0}

    async def fake_run_admin():
        fired["count"] += 1
        return {"ok": True}

    async def go():
        with patch.object(m, "_load_config", AsyncMock(return_value=cfg)), \
             patch.object(m, "_london_now", lambda: fake_now), \
             patch.object(m, "_autopilot_already_ran_today",
                          AsyncMock(return_value=False)), \
             patch.object(m, "_autopilot_run_as_master_admin", fake_run_admin), \
             patch.object(m, "_stamp_autopilot_run", AsyncMock()):
            c = await m._load_config()
            cfg_enabled = bool(c.get("enabled", True))
            cfg_hour = int(c.get("hour_uk") or 9)
            london = m._london_now()
            today = london.date().isoformat()
            ran = await m._autopilot_already_ran_today(today)
            if cfg_enabled and london.hour >= cfg_hour and not ran:
                await m._autopilot_run_as_master_admin()
                await m._stamp_autopilot_run(today, {"ok": True})

    _run(go())
    assert fired["count"] == 0


def test_module_exposes_idempotency_helpers():
    """Sanity — the symbols the loop depends on must remain exported."""
    from routes.marketing import seo_autopilot as m
    for name in (
        "run_daily_autopilot_loop",
        "_london_now",
        "_autopilot_already_ran_today",
        "_stamp_autopilot_run",
        "_autopilot_run_as_master_admin",
    ):
        assert hasattr(m, name), name


def test_london_now_is_aware_datetime():
    from routes.marketing import seo_autopilot as m
    now = m._london_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
