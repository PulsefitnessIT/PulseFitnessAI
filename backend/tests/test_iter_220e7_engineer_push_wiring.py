"""Iter 220e7 — Engineer Web Push subscribe + notification preferences.

Pins that the FE plumbing matches the backend endpoints already
present on ``routes/svc/notifications.py``. No new backend endpoints —
this is pure FE wire-up of the existing push infrastructure.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_engineer_push_helper_targets_correct_endpoints():
    src = _read("utils/engineerPush.js")
    # Exports the canonical API surface used by the settings drawer.
    for fn in ("isPushSupported", "getPushStatus", "enablePush",
               "disablePush", "sendPushTest",
               "getNotificationPrefs", "saveNotificationPrefs",
               "snoozeNotifications", "clearSnooze"):
        assert f"export async function {fn}" in src or f"export function {fn}" in src, (
            f"engineerPush.js missing export {fn}"
        )
    # Targets the existing backend endpoints — not a parallel scheme.
    for endpoint in (
        "/svc/engineer/push/vapid-key",
        "/svc/engineer/push/subscribe",
        "/svc/engineer/push/subscriptions/",
        "/svc/engineer/push/test",
        "/svc/engineer/notification-prefs",
        "/svc/engineer/notification-prefs/snooze",
    ):
        assert endpoint in src, f"engineerPush.js missing endpoint {endpoint}"


def test_notification_drawer_renders_subscribe_test_snooze_kinds():
    src = _read("pages/ServiceOps/Engineer/NotificationSettings.js")
    for tid in (
        "notification-settings-drawer",
        "notif-subscribe-toggle",
        "notif-send-test-btn",
    ):
        assert f'data-testid="{tid}"' in src, f"NotificationSettings missing {tid}"
    # Snooze testids use a template literal — check the pattern + all three values.
    assert "notif-snooze-${m}-btn" in src
    assert "[30, 60, 120]" in src
    # Per-kind toggle uses the kind list returned by the backend.
    assert "notif-kind-${kind}" in src


def test_engineer_account_settings_mounts_notifications_row_and_drawer():
    src = _read("pages/ServiceOps/Engineer/EngineerAccountSettings.js")
    # New "Alerts" section with the row.
    assert 'engineer-settings-section-notifications' in src
    assert 'engineer-settings-notifications-row' in src
    # Drawer is mounted with state-driven open flag.
    assert "import NotificationSettings" in src
    assert "<NotificationSettings" in src


def test_service_worker_supports_push_and_click():
    # Already shipped, just guard the regression — `sw.js` must keep
    # both push + notificationclick listeners so the FE wire-up
    # actually reaches the user's lock screen.
    sw = (Path("/app/frontend/public") / "sw.js").read_text(encoding="utf-8")
    assert "addEventListener('push'" in sw
    assert "addEventListener('notificationclick'" in sw
