"""
Digest email regression tests (P4, Feb 2026).

Covers scheduling math, preference CRUD, authorization, and the full API
surface for ``/api/digest/*``.
"""
import uuid
from datetime import datetime, timezone

import requests

from tests.conftest import (
    _test_backend_url,
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    run_async as run,
)

BASE = _test_backend_url()


# ─── Scheduling math ────────────────────────────────────────────

def test_next_due_at_disabled_returns_none():
    from utils.digest import next_due_at
    assert next_due_at({"enabled": False, "frequency": "weekly"}, datetime.now(timezone.utc)) is None
    assert next_due_at({"enabled": True, "frequency": "off"}, datetime.now(timezone.utc)) is None


def test_next_due_at_daily_first_send():
    from utils.digest import next_due_at
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    nxt = next_due_at({"enabled": True, "frequency": "daily", "hour_of_day": 8}, now)
    assert nxt.hour == 8
    assert nxt.date() == now.date()


def test_next_due_at_weekly_picks_right_day():
    from utils.digest import next_due_at
    # Sunday → next Monday (dow=0)
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)  # Sunday
    assert now.weekday() == 6
    nxt = next_due_at(
        {"enabled": True, "frequency": "weekly", "day_of_week": 0, "hour_of_day": 8},
        now,
    )
    assert nxt.weekday() == 0
    assert nxt.date() == datetime(2026, 3, 16).date()


def test_next_due_at_weekly_already_sent():
    from utils.digest import next_due_at
    last = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc).isoformat()
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    nxt = next_due_at(
        {"enabled": True, "frequency": "weekly", "day_of_week": 0,
         "hour_of_day": 8, "last_sent_at": last},
        now,
    )
    assert nxt > now


def test_is_due_respects_last_sent():
    from utils.digest import is_due
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    prefs_sent_today = {
        "enabled": True, "frequency": "daily", "hour_of_day": 8,
        "last_sent_at": datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc).isoformat(),
    }
    assert is_due(prefs_sent_today, now) is False
    prefs_sent_yesterday = {
        "enabled": True, "frequency": "daily", "hour_of_day": 8,
        "last_sent_at": datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc).isoformat(),
    }
    assert is_due(prefs_sent_yesterday, now) is True


# ─── Preferences CRUD ────────────────────────────────────────────

def test_set_preferences_validates_frequency():
    from utils.digest import set_preferences
    user_id = f"test-{uuid.uuid4()}"
    result = run(set_preferences(user_id, {"frequency": "not-a-valid-value", "enabled": True}))
    assert result["frequency"] == "weekly"

    from utils.database import db

    async def _cleanup():
        await db.digest_preferences.delete_many({"user_id": user_id})

    run(_cleanup())


def test_set_preferences_clamps_day_of_week():
    from utils.digest import set_preferences
    user_id = f"test-{uuid.uuid4()}"
    result = run(set_preferences(user_id, {"day_of_week": 42}))
    assert 0 <= result["day_of_week"] <= 6

    from utils.database import db

    async def _cleanup():
        await db.digest_preferences.delete_many({"user_id": user_id})

    run(_cleanup())


def test_set_preferences_merges_channels():
    from utils.digest import set_preferences, get_preferences
    user_id = f"test-{uuid.uuid4()}"
    # Disable only one channel
    run(set_preferences(user_id, {"channels": {"ppm_overdue": False}}))
    got = run(get_preferences(user_id))
    assert got["channels"]["warranty_expiring"] is True
    assert got["channels"]["ppm_overdue"] is False
    assert got["channels"]["supplier_sla_drift"] is True

    from utils.database import db

    async def _cleanup():
        await db.digest_preferences.delete_many({"user_id": user_id})

    run(_cleanup())


# ─── API endpoints ───────────────────────────────────────────────

def test_get_preferences_returns_defaults(pulse_pro_token):
    if not pulse_pro_token:
        return
    r = requests.get(
        f"{BASE}/api/digest/preferences",
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert "enabled" in body
    assert "frequency" in body
    assert "channels" in body
    assert set(body["channels"].keys()) >= {"warranty_expiring", "ppm_overdue", "supplier_sla_drift"}


def test_put_preferences_saves_and_returns_merged(pulse_pro_token):
    if not pulse_pro_token:
        return
    patch = {"enabled": True, "frequency": "daily", "hour_of_day": 14}
    r = requests.put(
        f"{BASE}/api/digest/preferences",
        json=patch,
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["frequency"] == "daily"
    assert body["hour_of_day"] == 14

    # Cleanup: disable + wipe
    from utils.database import db

    async def _cleanup():
        await db.digest_preferences.delete_many({})

    run(_cleanup())


def test_send_now_with_no_open_nudges_returns_sent_false(pulse_pro_token):
    if not pulse_pro_token:
        return
    from utils.database import db

    async def _prep():
        # Clear any stray nudges for Pulse
        await db.trust_events.delete_many({"type": {"$regex": "^nudge\\."}})

    run(_prep())

    r = requests.post(
        f"{BASE}/api/digest/send-now",
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["sent"] is False
    # New multi-channel shape
    assert body["email"] is False
    assert body["teams"] is False


def test_digest_run_requires_master_admin(pulse_pro_token):
    if not pulse_pro_token:
        return
    r = requests.post(
        f"{BASE}/api/digest/run",
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 403


def test_digest_run_as_master_admin():
    # Login as master admin
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        timeout=10,
    )
    body = r.json()
    if r.status_code != 200:
        return
    token = body.get("token")
    # MFA path yields temp_token instead — skip if master admin has MFA on.
    if not token:
        return
    resp = requests.post(
        f"{BASE}/api/digest/run",
        headers={"Authorization": f"Bearer {token}"}, timeout=15,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "considered" in body
    assert "sent" in body


# ─── Render path ─────────────────────────────────────────────────

def test_render_digest_html_includes_summary_and_items():
    from utils.digest import render_digest_html
    user = {"full_name": "Lee Somers", "email": "lee@example.com", "company_name": "Pulse Fitness"}
    payload = {
        "summary": "3 items need your attention at Pulse Fitness",
        "items": [
            {"type": "nudge.warranty_expiring", "severity": "med",
             "customer_safe_message": "5 pieces go out of warranty by 2026-05-01"},
            {"type": "nudge.ppm_overdue", "severity": "high",
             "customer_safe_message": "2 PPM tasks overdue"},
        ],
    }
    html = render_digest_html(user, payload, "weekly")
    assert "Lee" in html
    assert "weekly digest" in html
    assert "Warranty expiring" in html
    assert "Planned maintenance overdue" in html
    assert "out of warranty" in html


# ─── Unauthorized dismiss-style paths ────────────────────────────

def test_put_preferences_rejects_staff_role():
    """A user with role='staff' cannot manage the digest."""
    from utils.database import db

    email = f"staff-digest-{uuid.uuid4().hex[:8]}@example.com"
    requests.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": "Staff123!Good", "full_name": "S", "company_name": f"G-{uuid.uuid4().hex[:4]}"},
        timeout=10,
    )
    token = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": "Staff123!Good"}, timeout=10,
    ).json().get("token")
    if not token:
        return

    async def _downgrade():
        await db.users.update_one({"email": email}, {"$set": {"role": "staff"}})

    run(_downgrade())

    r = requests.put(
        f"{BASE}/api/digest/preferences",
        json={"enabled": True}, headers={"Authorization": f"Bearer {token}"}, timeout=10,
    )
    assert r.status_code == 403

    async def _cleanup():
        await db.users.delete_many({"email": email})
        await db.digest_preferences.delete_many({})

    run(_cleanup())
