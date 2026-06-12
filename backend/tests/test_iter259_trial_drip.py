"""Iter 259 — Provider-aware trial reminder drip.

The existing lifecycle worker (utils/trial_lifecycle.run_trial_lifecycle_once,
driven by the sicon poller loop) already scans every `is_trial` org and
sends day-10 / day-13 reminders with dedup. This suite locks in:
1. Service Provider orgs get the desk-specific template + the
   /service-desk/upgrade CTA (not the gym /choose-plan URL).
2. Gym orgs keep the original template/URL (regression).
3. Reminder scheduling maths + dedup markers are unchanged.
4. New provider signups carry the fields the worker needs.
"""

import uuid

import requests

from tests.conftest import _test_backend_url
from utils.trial_lifecycle import (
    PROVIDER_UPGRADE_URL, CHOOSE_PLAN_URL,
    _provider_trial_reminder_html, _trial_reminder_html, _pick_due_reminder,
)

BASE_URL = _test_backend_url()


def test_provider_template_has_desk_copy_and_upgrade_url():
    html = _provider_trial_reminder_html("FitFix Ltd", 4, PROVIDER_UPGRADE_URL)
    assert PROVIDER_UPGRADE_URL in html
    assert "/service-desk/upgrade" in PROVIDER_UPGRADE_URL
    assert "Service Desk trial" in html
    assert "cases, customers, engineers and SLA history" in html
    assert "&pound;99/month" in html
    # final-day variant flips to the red urgency hero
    final = _provider_trial_reminder_html("FitFix Ltd", 1, PROVIDER_UPGRADE_URL)
    assert "Final day" in final and "#EF4444" in final


def test_gym_template_unchanged():
    html = _trial_reminder_html("Apex Gym", 4, CHOOSE_PLAN_URL)
    assert CHOOSE_PLAN_URL in html and "choose-plan" in CHOOSE_PLAN_URL
    assert "GymAxis trial" in html
    assert "Service Desk" not in html


def test_reminder_schedule_and_dedup():
    # Day 10 of a 14-day trial → day10 marker
    assert _pick_due_reminder(10, 4, set()) == "day10"
    # Already sent → nothing
    assert _pick_due_reminder(10, 4, {"day10"}) is None
    # Day 13, 1 day left → day13 (even if day10 went earlier)
    assert _pick_due_reminder(13, 1, {"day10"}) == "day13"
    # Early in the trial → nothing
    assert _pick_due_reminder(3, 11, set()) is None


def test_new_provider_signup_carries_worker_fields():
    """Signup must seed trial_started_at/trial_ends_at + account_type so the
    lifecycle worker can compute day-10/day-13 windows and pick the
    provider template."""
    email = f"sp.drip.{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/service-provider/signup", json={
        "company_name": "Drip Test Co", "full_name": "D Rip",
        "email": email, "password": "Str0ngPass!23",
    }, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    me = requests.get(f"{BASE_URL}/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=20).json()
    assert me["account_type"] == "service_provider"
    trial = me.get("trial") or {}
    assert trial.get("status") == "active"
    assert trial.get("days_left", 0) >= 13  # full 14-day window seeded
