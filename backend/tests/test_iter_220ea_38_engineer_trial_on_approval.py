"""Iter 220ea·38 — Every approved engineer auto-starts the 10-day trial.

Root cause of "engineer stuck on the landing page / Billing in progress…":
on approval, only *tester-cohort* applicants were enrolled onto the proper
10-day trial. Non-tester engineers got a bare `subscription.status='trialing'`
with no `current_period_end` and no `trial` object, so the dashboard showed
"Active · Billing in progress…" forever with no countdown and no way forward.

Fix: the approve flow now auto-starts the real trial for every engineer-level
approval, writing `trial.status='active'`, `trial.ends_at` (+10 days) and
`subscription.current_period_end`.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import rate_limit_bypass_headers

load_dotenv("/app/backend/.env")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://dealer-parts-engine.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
ADMIN_PW = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _admin_token() -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
        headers=rate_limit_bypass_headers(), timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture()
def mongo():
    c = MongoClient(MONGO_URL)
    try:
        yield c[DB_NAME]
    finally:
        c.close()


def test_non_tester_approval_auto_starts_10_day_trial(mongo):
    token = _admin_token()
    h = {"Authorization": f"Bearer {token}"}
    email = f"pytest.trial.{uuid.uuid4().hex[:10]}@example.com"
    app_id = str(uuid.uuid4())

    # A plain (NON tester-cohort) public engineer application.
    mongo.partner_applications.insert_one({
        "id": app_id,
        "email": email,
        "full_name": "Pytest Trial Engineer",
        "company_name": "Pytest Services Ltd",
        "status": "pending",
        "tester_cohort": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        # Approve as master admin (default level = engineer_partner).
        r = requests.post(f"{BASE}/api/partners/applications/{app_id}/approve", json={}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["partner_id"]

        # The new partner must be on a live 10-day trial.
        pe = mongo.partner_engineers.find_one({"id": pid})
        assert pe is not None
        trial = pe.get("trial") or {}
        assert trial.get("status") == "active", f"expected active trial, got {trial}"
        assert trial.get("ends_at"), "trial has no end date (10-day timer not set)"
        assert pe.get("trial_used") is True
        # Subscription reflects the trial window so the dashboard shows a
        # countdown instead of the stuck 'Billing in progress…'.
        assert (pe.get("subscription") or {}).get("current_period_end") == trial.get("ends_at")

        # ~10 days out (allow a little clock skew).
        ends = datetime.fromisoformat(trial["ends_at"])
        days = (ends - datetime.now(timezone.utc)).total_seconds() / 86400
        assert 9.5 <= days <= 10.5, f"trial window {days:.2f} days, expected ~10"
    finally:
        mongo.partner_applications.delete_one({"id": app_id})
        mongo.partner_engineers.delete_many({"email": email})
