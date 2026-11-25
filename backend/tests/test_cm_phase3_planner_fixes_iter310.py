"""Iteration 310 — CM Phase 3 Service Planner fixes (public URL), needs `_seed_p3ui.py seed` data.
Run: cd /app/backend && PYTHONPATH=. python -m pytest -q -p no:xdist tests/test_cm_phase3_planner_fixes_iter310.py
"""
from tests._paths import REPO  # noqa: E402
import os
import time
from datetime import date, timedelta

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token


def _pub():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for ln in open(REPO + "/frontend/.env"):
            if ln.startswith("REACT_APP_BACKEND_URL="):
                v = ln.split("=", 1)[1].strip()
    return v.rstrip("/")


API = _pub() + "/api"
AFS = f"{API}/crm/v2/aftersales"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
T = "TEST_p3ui_"


def _h(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def ctx():
    c1 = mdb.crm2_contracts.find_one({"company_id": f"{T}co", "source_agreement_id": {"$exists": True}}, sort=[("created_at", 1)])
    if not c1:
        pytest.skip("seed TEST_p3ui data first")
    sched = mdb.crm2_afs_service_schedules.find_one({"contract_id": c1["id"]})
    return {"cid": c1["id"], "end": c1.get("end_date"), "visits": sched["visits"], "co": _h("cm-test-coord")}


# FIX 5 — totals respect q
def test_totals_respect_search(ctx):
    allr = requests.get(f"{AFS}/service-planner", headers=ctx["co"]).json()
    r = requests.get(f"{AFS}/service-planner", headers=ctx["co"], params={"q": "TEST North Gym"}).json()
    assert r["count"] == len(r["rows"]) > 0
    assert sum(r["totals"].values()) == r["count"]
    assert sum(allr["totals"].values()) > sum(r["totals"].values())
    none = requests.get(f"{AFS}/service-planner", headers=ctx["co"], params={"q": "zzz_nomatch_zzz"}).json()
    assert sum(none["totals"].values()) == 0


# FIX 6 — booking date validation
def test_book_past_date_400(ctx):
    o2 = ctx["visits"][1]["obligation_id"]
    r = requests.post(f"{AFS}/contracts/{ctx['cid']}/obligations/{o2}/book", headers=ctx["co"],
                      json={"scheduled_date": (date.today() - timedelta(days=3)).isoformat()})
    assert r.status_code == 400 and "future" in r.json()["detail"]


def test_book_after_end_400(ctx):
    o2 = ctx["visits"][1]["obligation_id"]
    end = date.fromisoformat(ctx["end"][:10])
    r = requests.post(f"{AFS}/contracts/{ctx['cid']}/obligations/{o2}/book", headers=ctx["co"],
                      json={"scheduled_date": (end + timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and "cover ends" in r.json()["detail"]
    v = next(x for x in mdb.crm2_afs_service_schedules.find_one({"contract_id": ctx["cid"]})["visits"] if x["obligation_id"] == o2)
    assert not v.get("case_id") and not v.get("booking_lock")


# FIX 7 — sync endpoint
def test_sync_endpoint(ctx):
    r = requests.post(f"{AFS}/service-planner/sync", headers=ctx["co"])
    assert r.status_code == 200, r.text
    assert requests.post(f"{AFS}/service-planner/sync").status_code == 401


# FIX 8 — throttled sync on GET + live bookings always re-read
def test_get_throttles_unbooked_contract(ctx):
    requests.get(f"{AFS}/service-planner", headers=ctx["co"])
    c2 = mdb.crm2_contracts.find_one({"company_id": f"{T}co", "id": {"$ne": ctx["cid"]}})
    s1 = mdb.crm2_afs_service_schedules.find_one({"contract_id": c2["id"]})
    live = any(v.get("case_id") and v.get("status") not in ("completed", "verified", "excluded") for v in s1["visits"])
    time.sleep(1)
    requests.get(f"{AFS}/service-planner", headers=ctx["co"])
    s2 = mdb.crm2_afs_service_schedules.find_one({"contract_id": c2["id"]})
    if not live:
        assert s1.get("synced_at") == s2.get("synced_at"), "non-live contract re-synced within 60s"


def test_service_desk_change_shows_on_next_load(ctx):
    o2 = ctx["visits"][1]["obligation_id"]
    day = (date.today() + timedelta(days=30)).isoformat()
    r = requests.post(f"{AFS}/contracts/{ctx['cid']}/obligations/{o2}/book", headers=ctx["co"], json={"scheduled_date": day})
    assert r.status_code == 200, r.text
    case_id = r.json()["case_id"]
    new_day = (date.today() + timedelta(days=45)).isoformat()
    mdb.svc_cases.update_one({"id": case_id}, {"$set": {"scheduled_at": f"{new_day}T09:00:00+00:00",
                                                         "assigned_engineer_name": "Erin Engineer",
                                                         "assigned_engineer_id": f"{T}eng"}})
    rows = requests.get(f"{AFS}/service-planner", headers=ctx["co"], params={"q": "TEST_p3ui"}).json()["rows"]
    row = next(x for x in rows if x["obligation_id"] == o2)
    assert row["booking_date"] == new_day and row["engineer"] == "Erin Engineer"
    assert row["bucket"] == "booked"
