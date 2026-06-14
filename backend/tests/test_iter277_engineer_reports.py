"""Iter 277 — Engineer field-performance analytics reports.

Aggregates EVERY case assigned to the engineer (cross-org) into:
problematic machines/sites, most-used parts, response time (created →
first time_start event), and first-time-fix rate (return visit ≤ 30d).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()


def _db():
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        pytest.skip("MONGO_URL/DB_NAME not set")
    return MongoClient(url)[name]


def _hash(pw):
    from utils.auth import hash_password
    return hash_password(pw)


def _iso(dt):
    return dt.isoformat()


def test_engineer_field_performance_reports():
    db = _db()
    org = f"perf-org-{uuid.uuid4().hex}"
    email = f"perf.{uuid.uuid4().hex[:8]}@example.com"
    uid = f"perfeng-{uuid.uuid4().hex}"
    pw = "PerfEng123!"
    now = datetime.now(timezone.utc)
    asset_a = f"asset-a-{uuid.uuid4().hex}"   # problematic: 3 jobs, 1 repeat
    asset_b = f"asset-b-{uuid.uuid4().hex}"   # 1 job, FTF
    case_ids = []
    try:
        db.organizations.insert_one({"id": org, "name": "Pulse Croydon", "account_type": "pulse_pro"})
        db.users.insert_one({
            "id": uid, "email": email, "password": _hash(pw),
            "role": "engineer", "account_type": "engineer", "organization_id": org,
            "full_name": "Perf Engineer", "active": True,
        })
        # Make them an engineer for the org so require_engineer_app_access passes.
        db.svc_engineers.insert_one({"id": uid, "organization_id": org, "full_name": "Perf Engineer", "active": True})

        def mk(asset, site, created, status, parts=None):
            cid = f"perfcase-{uuid.uuid4().hex}"
            case_ids.append(cid)
            db.svc_cases.insert_one({
                "id": cid, "organization_id": org, "assigned_engineer_id": uid,
                "assigned_engineer_name": "Perf Engineer", "asset_id": asset,
                "asset_name": "Treadmill" if asset == asset_a else "Bike",
                "site_name": site, "status": status,
                "created_at": _iso(created),
                "sla_response_at": _iso(created + timedelta(hours=4)),
                "allocated_parts": parts or [],
            })
            return cid

        # Asset A: job1 (closed) + follow-up job2 10 days later → job1 is a repeat.
        c1 = mk(asset_a, "Croydon Gym", now - timedelta(days=40), "closed",
                parts=[{"part_name": "Drive belt", "part_sku": "BELT-1", "qty": 2}])
        mk(asset_a, "Croydon Gym", now - timedelta(days=30), "closed",
           parts=[{"part_name": "Drive belt", "part_sku": "BELT-1", "qty": 1}])
        mk(asset_a, "Croydon Gym", now - timedelta(days=5), "assigned")
        # Asset B: single completed job, no follow-up → FTF.
        c4 = mk(asset_b, "Sutton Gym", now - timedelta(days=20), "closed",
                parts=[{"part_name": "Pedal", "part_sku": "PED-9", "qty": 1}])

        # Response timer: engineer started travel 90 min after c4 created (within SLA).
        db.svc_case_events.insert_one({
            "id": str(uuid.uuid4()), "case_id": c4, "organization_id": org,
            "type": "time_start", "actor_id": uid, "actor_name": "Perf Engineer",
            "at": _iso(now - timedelta(days=20) + timedelta(minutes=90)),
            "extra": {"category": "travel"},
        })

        tok = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw},
                            headers=rate_limit_bypass_headers(), timeout=15).json()["token"]
        r = requests.get(f"{BASE}/api/svc/engineer/analytics/reports?range=all",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()

        assert d["total_jobs"] == 4
        # Problematic machines: asset A on top with 3 jobs.
        pm = d["problematic_machines"]
        assert pm[0]["equipment_id"] == asset_a and pm[0]["jobs"] == 3
        assert pm[0]["site_name"] == "Croydon Gym"
        # Sites: Croydon (3) > Sutton (1).
        assert d["problematic_sites"][0]["site_name"] == "Croydon Gym"
        assert d["problematic_sites"][0]["jobs"] == 3
        # Parts: Drive belt qty 3 (2+1) on top, Pedal 1.
        belt = next(p for p in d["top_parts"] if p["part_sku"] == "BELT-1")
        assert belt["qty"] == 3 and belt["jobs"] == 2
        # Response: 1 measured sample (~90 min), within SLA.
        assert d["response"]["sample"] == 1
        assert 80 <= d["response"]["avg_minutes"] <= 100
        assert d["response"]["within_sla_pct"] == 100.0
        # FTF: completed = c1, c2, c4 (3). c1 has follow-up (c2) within 30d → repeat.
        # c2's follow-up would be c3 but c3 is 25 days later (assigned, still counts as a date on asset A) → c2 also repeat.
        ftf = d["first_time_fix"]
        assert ftf["total"] == 3
        assert ftf["fixed"] >= 1  # at least asset B's job
        assert ftf["repeat_visits"] >= 1
    finally:
        db.svc_cases.delete_many({"organization_id": org})
        db.svc_case_events.delete_many({"organization_id": org})
        db.svc_engineers.delete_many({"organization_id": org})
        db.organizations.delete_one({"id": org})
        db.users.delete_many({"email": email})
