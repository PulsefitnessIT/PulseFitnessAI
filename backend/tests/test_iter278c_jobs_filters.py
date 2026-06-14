"""Iter 278c — Engineer jobs-list filter audit regression.

The "Overdue" and "Awaiting parts" KPI tiles used to deep-link to the
generic ``?when=open`` list. They now have dedicated ``when`` filters that
must return EXACTLY the jobs the matching dashboard KPI counts:
  • ``when=awaiting_parts`` → status == "awaiting_parts"
  • ``when=overdue``        → open status set + scheduled_at < today

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


def test_overdue_and_awaiting_parts_filters_match_kpis():
    db = _db()
    eng = db.users.find_one({"email": ENG_EMAIL}, {"_id": 0, "id": 1, "organization_id": 1})
    if not eng:
        pytest.skip("indie engineer test account not provisioned")
    uid, org = eng["id"], eng["organization_id"]
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=2)).date().isoformat() + "T09:00:00+00:00"
    future = (now + timedelta(days=3)).date().isoformat() + "T09:00:00+00:00"

    def case(ref, status, sched):
        return {"id": str(uuid.uuid4()), "organization_id": org, "assigned_engineer_id": uid,
                "reference": ref, "status": status, "scheduled_at": sched,
                "created_at": now.isoformat()}

    db.svc_cases.delete_many({"reference": {"$regex": "^JFAUDIT-"}})
    db.svc_cases.insert_many([
        case("JFAUDIT-FUTURE", "on_site", future),       # open, not overdue
        case("JFAUDIT-OVERDUE", "assigned", past),       # open + scheduled in the past
        case("JFAUDIT-PARTS", "awaiting_parts", future), # blocked on parts
    ])
    try:
        login = requests.post(f"{BASE}/api/auth/login", json={"email": ENG_EMAIL, "password": ENG_PW},
                              headers=rate_limit_bypass_headers(), timeout=15).json()
        h = {"Authorization": f"Bearer {login['token']}"}

        ov = requests.get(f"{BASE}/api/svc/engineer/jobs?when=overdue", headers=h, timeout=15).json()
        ov_refs = {j["reference"] for j in ov["jobs"]}
        assert "JFAUDIT-OVERDUE" in ov_refs
        assert "JFAUDIT-FUTURE" not in ov_refs and "JFAUDIT-PARTS" not in ov_refs

        ap = requests.get(f"{BASE}/api/svc/engineer/jobs?when=awaiting_parts", headers=h, timeout=15).json()
        ap_refs = {j["reference"] for j in ap["jobs"]}
        assert "JFAUDIT-PARTS" in ap_refs
        assert "JFAUDIT-OVERDUE" not in ap_refs and "JFAUDIT-FUTURE" not in ap_refs
    finally:
        db.svc_cases.delete_many({"reference": {"$regex": "^JFAUDIT-"}})
