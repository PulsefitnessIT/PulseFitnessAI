"""Iter 220df — Engineer App Shell Nudge.

PWA install + push subscribe are both already wired (see
``PWAInstallPrompt`` and ``EngineerNotifications.PushSubscribeButton``),
but discoverability is the gap: field engineers rarely visit the
bell page and the global 30-second banner is easy to miss. This iter
adds ``EngineerAppShellNudge`` — a contextual card on
``EngineerHomeV2`` that surfaces BOTH affordances right next to the
"My Day" briefing.

Backend already exposes:
  * ``GET /api/svc/engineer/push/vapid-key``
  * ``POST /api/svc/engineer/push/subscribe``

This file pins:
  * Both endpoints remain registered on the engineer router.
  * The new component is mounted on EngineerHomeV2 with required
    test IDs and respects the 14-day cooldown.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1 · Backend endpoints still registered ──────────────────────


def test_push_endpoints_present_on_engineer_router():
    """Belt-and-braces: a regression that drops the push endpoints
    would silently break the new nudge. Pin both."""
    from routes.svc.notifications import router
    paths = {r.path for r in router.routes if hasattr(r, 'path')}
    # Endpoints live under the engineer prefix.
    assert any("/push/vapid-key" in p for p in paths)
    assert any("/push/subscribe" in p for p in paths)


def test_vapid_key_endpoint_returns_public_key():
    """Sanity check the helper that builds the VAPID dict so a
    refactor doesn't drop the 'public_key' field the client reads."""
    from unittest.mock import AsyncMock, MagicMock

    fdb = MagicMock()
    fdb.svc_vapid_keys.find_one = AsyncMock(return_value={
        "id": "singleton",
        "public": "BFAKE_PUB_KEY",
        "private": "FAKE_PRIV_KEY",
        "subject": "mailto:ops@gymaxis.com",
    })
    fdb.svc_vapid_keys.update_one = AsyncMock()

    async def run():
        with patch("routes.svc.notifications.db", fdb):
            from routes.svc.notifications import get_vapid_key
            return await get_vapid_key(user={"id": "eng-1", "organization_id": "org-1"})

    out = _run(run())
    assert "public_key" in out
    assert isinstance(out["public_key"], str)
    assert len(out["public_key"]) > 0


# ── 2 · Frontend wiring ─────────────────────────────────────────


def test_engineer_shell_nudge_component_exists():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAppShellNudge.js"
    ).read_text()
    assert "export default function EngineerAppShellNudge" in src
    # Test IDs are stable.
    for tid in (
        "engineer-shell-nudge", "engineer-shell-nudge-dismiss",
        "engineer-shell-nudge-push", "engineer-shell-nudge-install",
        "engineer-shell-nudge-ios-guide", "engineer-shell-nudge-ios-close",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"


def test_engineer_shell_nudge_calls_correct_endpoints():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAppShellNudge.js"
    ).read_text()
    assert "/svc/engineer/push/vapid-key" in src
    assert "/svc/engineer/push/subscribe" in src
    assert "/sw.js" in src
    assert "Notification.requestPermission" in src
    assert "beforeinstallprompt" in src


def test_engineer_shell_nudge_mounted_on_home():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text()
    assert "import EngineerAppShellNudge" in src
    assert "<EngineerAppShellNudge />" in src


def test_nudge_respects_14_day_cooldown():
    """Pin the dismiss-cooldown key + window so an accidental change
    doesn't make the nudge spam engineers."""
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAppShellNudge.js"
    ).read_text()
    assert "engineer_shell_nudge_dismissed_at" in src
    assert "14 * 24 * 60 * 60 * 1000" in src


def test_existing_pwa_install_prompt_still_mounted_globally():
    """The new engineer-app nudge is additive — the global
    PWAInstallPrompt must remain so non-engineer routes still get the
    promotion."""
    src = Path("/app/frontend/src/App.js").read_text()
    assert "import PWAInstallPrompt" in src
    assert "<PWAInstallPrompt />" in src


def test_manifest_and_sw_present():
    """Belt-and-braces: PWA infrastructure files exist."""
    assert Path("/app/frontend/public/manifest.json").exists()
    sw = Path("/app/frontend/public/sw.js").read_text()
    # Push event handler is wired so notifications actually display.
    assert "addEventListener('push'" in sw
    assert "addEventListener('notificationclick'" in sw
