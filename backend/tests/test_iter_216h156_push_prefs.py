"""Iter 216h156 — Engineer push prefs + quiet hours.

Audits the PECR / GDPR posture improvement identified in the Feb 2026
process review: engineers can now opt out of individual notification
kinds, set quiet hours, and one-tap snooze all pushes. The in-app row
always lands (catch-up timeline); only the disruptive Web Push channel
is gated.

Audits:
  • GET /api/svc/engineer/notification-prefs returns defaults and the
    list of toggleable kinds.
  • PUT updates quiet hours + kind_prefs, validates HH:MM format.
  • POST /snooze sets `dnd_until` N minutes ahead; DELETE clears.
  • `_push_allowed()` correctly suppresses for: explicit kind=False,
    in-DND window, in quiet-hours window (incl. midnight crossing).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://rbac-modules.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def sess():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


@pytest.fixture(autouse=True)
def _cleanup_prefs(sess):
    """Each test starts with no prefs doc — keeps the suite hermetic."""
    db = _mongo()
    db["svc_engineer_push_prefs"].delete_many(
        {"user_id": sess["user"]["id"]},
    )
    yield
    db["svc_engineer_push_prefs"].delete_many(
        {"user_id": sess["user"]["id"]},
    )


# ── GET defaults & PUT update ──────────────────────────────────

def test_get_prefs_returns_defaults_and_kinds(sess):
    tok = sess["token"]
    r = requests.get(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok), timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "prefs" in body
    assert body["prefs"]["dnd_until"] is None
    assert body["prefs"]["kind_prefs"] == {}
    assert isinstance(body["kinds"], list)
    assert "job_assigned" in body["kinds"]
    assert "test" in body["kinds"]
    assert body["currently_in_quiet_hours"] is False
    assert body["currently_in_dnd"] is False


def test_put_prefs_persists_quiet_hours_and_kind_toggles(sess):
    tok = sess["token"]
    r = requests.put(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok),
        json={
            "timezone": "Europe/London",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
            "kind_prefs": {"attachment": False, "ppm_due": False,
                            "not_a_real_kind": True},  # must be filtered
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    prefs = r.json()["prefs"]
    assert prefs["quiet_hours_start"] == "22:00"
    assert prefs["quiet_hours_end"] == "07:00"
    assert prefs["kind_prefs"]["attachment"] is False
    assert prefs["kind_prefs"]["ppm_due"] is False
    # Whitelist rejection of unknown kind
    assert "not_a_real_kind" not in prefs["kind_prefs"]


def test_put_prefs_rejects_bad_time_format(sess):
    tok = sess["token"]
    r = requests.put(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok),
        json={"quiet_hours_start": "25:99"},
        timeout=15,
    )
    assert r.status_code == 422


# ── Snooze ──────────────────────────────────────────────────────

def test_snooze_then_clear(sess):
    tok = sess["token"]
    r = requests.post(
        f"{API}/api/svc/engineer/notification-prefs/snooze",
        headers=_hdr(tok), json={"minutes": 60}, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dnd_until"] is not None
    # Verify it's in the future.
    until = datetime.fromisoformat(body["dnd_until"])
    assert until > datetime.now(timezone.utc)
    # GET reflects DND.
    g = requests.get(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok), timeout=15,
    )
    assert g.status_code == 200
    assert g.json()["currently_in_dnd"] is True
    # Clear and re-check.
    d = requests.delete(
        f"{API}/api/svc/engineer/notification-prefs/snooze",
        headers=_hdr(tok), timeout=15,
    )
    assert d.status_code == 200
    g2 = requests.get(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok), timeout=15,
    )
    assert g2.json()["currently_in_dnd"] is False


def test_snooze_rejects_out_of_range_minutes(sess):
    tok = sess["token"]
    r = requests.post(
        f"{API}/api/svc/engineer/notification-prefs/snooze",
        headers=_hdr(tok), json={"minutes": 2}, timeout=15,
    )
    assert r.status_code == 422
    r2 = requests.post(
        f"{API}/api/svc/engineer/notification-prefs/snooze",
        headers=_hdr(tok), json={"minutes": 2000}, timeout=15,
    )
    assert r2.status_code == 422


# ── Gate logic (unit-level via the helper) ─────────────────────

def test_push_allowed_helpers():
    """Direct unit checks against the gate helpers — keeps the
    semantic guarantee documented even if a refactor moves the
    suppression rules."""
    from routes.svc.notifications import (
        _push_allowed, _in_quiet_hours, _in_dnd,
    )

    # Default prefs allow everything.
    prefs = {"timezone": "Europe/London",
             "quiet_hours_start": None, "quiet_hours_end": None,
             "dnd_until": None, "kind_prefs": {}}
    assert _push_allowed(prefs, "job_assigned") is True

    # Kind explicitly disabled.
    prefs_off = {**prefs, "kind_prefs": {"attachment": False}}
    assert _push_allowed(prefs_off, "attachment") is False
    assert _push_allowed(prefs_off, "job_assigned") is True

    # DND beats everything.
    future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    prefs_dnd = {**prefs, "dnd_until": future}
    assert _in_dnd(prefs_dnd) is True
    assert _push_allowed(prefs_dnd, "job_assigned") is False

    # DND in the past is a no-op.
    past = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    prefs_expired = {**prefs, "dnd_until": past}
    assert _in_dnd(prefs_expired) is False
    assert _push_allowed(prefs_expired, "job_assigned") is True


def test_quiet_hours_window_midnight_crossing():
    """Quiet hours 22:00 → 07:00 must include 02:00 and 23:30 but
    not 12:00."""
    from routes.svc.notifications import _in_quiet_hours

    base = {"timezone": "UTC",
            "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}
    # Midnight crossing — 02:00 UTC is inside the window.
    night = datetime(2026, 2, 17, 2, 0, tzinfo=timezone.utc)
    assert _in_quiet_hours(base, now=night) is True
    # Same window — 23:30 is inside.
    late = datetime(2026, 2, 17, 23, 30, tzinfo=timezone.utc)
    assert _in_quiet_hours(base, now=late) is True
    # 12:00 is outside.
    noon = datetime(2026, 2, 17, 12, 0, tzinfo=timezone.utc)
    assert _in_quiet_hours(base, now=noon) is False
    # Empty / equal start/end is a no-op.
    assert _in_quiet_hours({}, now=noon) is False
    assert _in_quiet_hours(
        {"quiet_hours_start": "10:00", "quiet_hours_end": "10:00"},
        now=noon,
    ) is False


def test_quiet_hours_same_day_window():
    """Quiet hours 13:00 → 14:00 (lunch DND): 13:30 inside, 14:00 outside."""
    from routes.svc.notifications import _in_quiet_hours
    p = {"timezone": "UTC",
         "quiet_hours_start": "13:00", "quiet_hours_end": "14:00"}
    inside = datetime(2026, 2, 17, 13, 30, tzinfo=timezone.utc)
    assert _in_quiet_hours(p, now=inside) is True
    on_end = datetime(2026, 2, 17, 14, 0, tzinfo=timezone.utc)
    assert _in_quiet_hours(p, now=on_end) is False
    before = datetime(2026, 2, 17, 12, 59, tzinfo=timezone.utc)
    assert _in_quiet_hours(p, now=before) is False


# ── In-app row still lands when push is gated ──────────────────

def test_inapp_row_lands_even_when_push_disabled(sess):
    """Critically — disabling a kind silences the disruptive push but
    must NOT drop the in-app notification row. That's the catch-up
    timeline; required by PECR's "soft opt-in" doctrine."""
    tok = sess["token"]
    user_id = sess["user"]["id"]
    db = _mongo()
    # Disable all `test` kind pushes for this engineer.
    r = requests.put(
        f"{API}/api/svc/engineer/notification-prefs",
        headers=_hdr(tok),
        json={"kind_prefs": {"test": False}}, timeout=15,
    )
    assert r.status_code == 200
    # Trigger the self-test push.
    before = db["svc_notifications"].count_documents(
        {"user_id": user_id, "kind": "test"},
    )
    t = requests.post(
        f"{API}/api/svc/engineer/push/test",
        headers=_hdr(tok), timeout=15,
    )
    assert t.status_code == 200, t.text
    after = db["svc_notifications"].count_documents(
        {"user_id": user_id, "kind": "test"},
    )
    assert after == before + 1, "in-app row must still be written"
    notif_id = t.json().get("notification_id")
    if notif_id:
        db["svc_notifications"].delete_one({"id": notif_id})
