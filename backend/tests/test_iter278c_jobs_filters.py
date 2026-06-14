"""Iter 278c/d — Engineer jobs-list filter audit regression.

The "Overdue" and "Return to Fix" KPI tiles used to deep-link to the
generic ``?when=open`` list. They now have dedicated ``when`` filters that
must return EXACTLY the jobs the matching dashboard KPI counts:
  • ``when=overdue``       → open status set + scheduled_at < today
  • ``when=return_to_fix`` → open jobs that either carry a ``return_to_fix``
    stamp OR are parked for parts (paused_parts / legacy awaiting_parts).

Uses the provisioned independent-engineer account (the engineer app is
subscription-gated, so a throwaway org would be blocked with HTTP 402).
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
ENG_EMAIL = "indie.engineer@gymaxisai.com"
ENG_PW = "IndieEng123!"


def _db():
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        pytest.skip("MONGO_URL/DB_NAME not set")
    return MongoClient(url)[name]


def _eng(db):
    eng = db.users.find_one({"email": ENG_EMAIL}, {"_id": 0, "id": 1, "organization_id": 1})
    if not eng:
        pytest.skip("indie engineer test account not provisioned")
    return eng["id"], eng["organization_id"]


def _login():
    return requests.post(f"{BASE}/api/auth/login", json={"email": ENG_EMAIL, "password": ENG_PW},
                         headers=rate_limit_bypass_headers(), timeout=15).json()["token"]


def test_overdue_filter_matches_kpi():
    db = _db()
    uid, org = _eng(db)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=2)).date().isoformat() + "T09:00:00+00:00"
    future = (now + timedelta(days=3)).date().isoformat() + "T09:00:00+00:00"

    def case(ref, status, sched):
        return {"id": str(uuid.uuid4()), "organization_id": org, "assigned_engineer_id": uid,
                "reference": ref, "status": status, "scheduled_at": sched, "created_at": now.isoformat()}

    db.svc_cases.delete_many({"reference": {"$regex": "^JFAUDIT-"}})
    db.svc_cases.insert_many([
        case("JFAUDIT-FUTURE", "on_site", future),
        case("JFAUDIT-OVERDUE", "assigned", past),
    ])
    try:
        h = {"Authorization": f"Bearer {_login()}"}
        ov = requests.get(f"{BASE}/api/svc/engineer/jobs?when=overdue", headers=h, timeout=15).json()
        refs = {j["reference"] for j in ov["jobs"]}
        assert "JFAUDIT-OVERDUE" in refs and "JFAUDIT-FUTURE" not in refs
    finally:
        db.svc_cases.delete_many({"reference": {"$regex": "^JFAUDIT-"}})


def test_return_to_fix_filter_and_kpi():
    db = _db()
    uid, org = _eng(db)
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=3)).isoformat()

    def case(ref, status, **extra):
        return {"id": str(uuid.uuid4()), "organization_id": org, "assigned_engineer_id": uid,
                "reference": ref, "status": status, "scheduled_at": future,
                "created_at": now.isoformat(), **extra}

    db.svc_cases.delete_many({"reference": {"$regex": "^RTFAUDIT-"}})
    db.svc_cases.insert_many([
        case("RTFAUDIT-PARTS", "awaiting_parts"),                                 # legacy parts
        case("RTFAUDIT-PAUSED", "paused_parts"),                                  # canonical parts
        case("RTFAUDIT-RETURN", "scheduled", return_to_fix={"id": "x", "reason": "ran out of time"}),
        case("RTFAUDIT-NORMAL", "on_site"),                                       # not a return
        case("RTFAUDIT-CLOSED", "closed", return_to_fix={"id": "y", "reason": "done"}),  # finished
    ])
    try:
        h = {"Authorization": f"Bearer {_login()}"}
        # Snapshot the org's baseline counts (other real jobs may exist), then
        # assert our seeded rows are correctly included / excluded.
        rtf = requests.get(f"{BASE}/api/svc/engineer/jobs?when=return_to_fix", headers=h, timeout=15).json()
        refs = {j["reference"] for j in rtf["jobs"]}
        assert {"RTFAUDIT-PARTS", "RTFAUDIT-PAUSED", "RTFAUDIT-RETURN"} <= refs
        assert "RTFAUDIT-NORMAL" not in refs and "RTFAUDIT-CLOSED" not in refs

        # Legacy alias still resolves to the same filter.
        alias = requests.get(f"{BASE}/api/svc/engineer/jobs?when=awaiting_parts", headers=h, timeout=15).json()
        assert {j["reference"] for j in alias["jobs"]} == refs

        # The dashboard KPI count agrees with the filtered list length.
        kpis = requests.get(f"{BASE}/api/svc/engineer/dashboard", headers=h, timeout=15).json().get("kpis", {})
        assert kpis.get("return_to_fix") == rtf["count"]
        assert kpis.get("awaiting_parts") == kpis.get("return_to_fix")  # back-compat alias
    finally:
        db.svc_cases.delete_many({"reference": {"$regex": "^RTFAUDIT-"}})

