"""Iter 220g — Smart scheduling suggestions (proximity-based).

Given a target postcode, /api/svc/engineer/scheduling-suggestions
returns up to 5 dates in the next 14 days where the engineer already
has jobs booked within 10 miles. Tests use direct DB inserts into
`postcode_cache` to dodge the live postcodes.io API.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://mod-hq-email.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
    _CACHE[email] = r.json()["token"]
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def admin(db):
    return db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0})


@pytest.fixture
def cleanup(db):
    case_ids: list[str] = []
    geo_codes: list[str] = []
    yield {"cases": case_ids, "geo": geo_codes}
    if case_ids:
        db.svc_cases.delete_many({"id": {"$in": case_ids}})
    if geo_codes:
        db.postcode_cache.delete_many({"postcode": {"$in": geo_codes}})


def _seed_geo(db, postcode_norm: str, lat: float, lng: float, cleanup_bag) -> None:
    db.postcode_cache.update_one(
        {"postcode": postcode_norm},
        {
            "$set": {
                "postcode": postcode_norm, "lat": lat, "lng": lng,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
            "$unset": {"miss": ""},  # Remove miss flag if present
        },
        upsert=True,
    )
    cleanup_bag["geo"].append(postcode_norm)


def _seed_case(db, admin, postcode: str, scheduled_at: str, cleanup_bag, ref: str = "SCH") -> str:
    cid = f"sched-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "reference": ref,
        "title": "Nearby booked job",
        "status": "scheduled",
        "assigned_engineer_id": admin["id"],
        "site_postcode": postcode,
        "site_name": "Site",
        "scheduled_at": scheduled_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    cleanup_bag["cases"].append(cid)
    return cid


# ─────────────────── Happy path ───────────────────


def test_suggests_dates_with_nearby_jobs_grouped_and_sorted(db, admin, cleanup):
    """Coventry test:
      Target: CV1 1AA (52.408, -1.510)
      Nearby (within 10 miles):
        - CV1 2AB → same day as another nearby job → should be combined
        - CV3 4XX (~5 mi)
      Out of range:
        - SW1A 1AA (London, ~80 mi) → must NOT appear
    """
    # Seed geocodes.
    _seed_geo(db, "CV1 1AA", 52.408054, -1.510556, cleanup)   # target
    _seed_geo(db, "CV1 2AB", 52.410, -1.515, cleanup)         # ~0.4 mi
    _seed_geo(db, "CV3 4XX", 52.380, -1.480, cleanup)         # ~3 mi
    _seed_geo(db, "SW1A 1AA", 51.501009, -0.141588, cleanup)  # ~80 mi
    today = datetime.now(timezone.utc).date()
    day3 = (today + timedelta(days=3)).isoformat()
    day5 = (today + timedelta(days=5)).isoformat()
    # Two jobs on day3 (CV1 + CV3), one on day5 (CV1 2AB), one far away
    _seed_case(db, admin, "CV1 2AB", f"{day3}T10:00:00+00:00", cleanup, ref="N-1")
    _seed_case(db, admin, "CV3 4XX", f"{day3}T14:00:00+00:00", cleanup, ref="N-2")
    _seed_case(db, admin, "CV1 2AB", f"{day5}T09:00:00+00:00", cleanup, ref="N-3")
    _seed_case(db, admin, "SW1A 1AA", f"{day3}T11:00:00+00:00", cleanup, ref="FAR")

    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA",
            headers=_hdr(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_geocoded"] is True
    suggestions = body["suggestions"]
    # day3 must come first (job_count=2), then day5 (job_count=1).
    assert len(suggestions) == 2
    assert suggestions[0]["date"] == day3
    assert suggestions[0]["job_count"] == 2
    assert suggestions[1]["date"] == day5
    assert suggestions[1]["job_count"] == 1
    # Far-away job must be excluded.
    refs_returned = {j["reference"] for s in suggestions for j in s["jobs"]}
    assert "FAR" not in refs_returned


def test_returns_empty_when_postcode_has_no_nearby_jobs(db, admin, cleanup):
    _seed_geo(db, "EH1 1AA", 55.952, -3.190, cleanup)
    # No cases seeded for this engineer in the window.
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=EH1+1AA",
            headers=_hdr(),
        )
    assert r.status_code == 200
    assert r.json()["suggestions"] == []


def test_outward_code_fallback_when_geocoder_says_miss(db, admin, cleanup):
    """Both target and candidate fail to geocode → outward-code match
    kicks in and the same outward code still counts as 'near'."""
    # Mark both as known misses (postcodes.io won't be called).
    db.postcode_cache.update_one(
        {"postcode": "XX1 1AA"},
        {"$set": {"postcode": "XX1 1AA", "miss": True}},
        upsert=True,
    )
    cleanup["geo"].append("XX1 1AA")
    db.postcode_cache.update_one(
        {"postcode": "XX1 9ZZ"},
        {"$set": {"postcode": "XX1 9ZZ", "miss": True}},
        upsert=True,
    )
    cleanup["geo"].append("XX1 9ZZ")

    today = datetime.now(timezone.utc).date()
    day7 = (today + timedelta(days=7)).isoformat()
    _seed_case(db, admin, "XX1 9ZZ", f"{day7}T09:00:00+00:00", cleanup, ref="OUT")

    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=XX1+1AA",
            headers=_hdr(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["target_geocoded"] is False
    suggestions = body["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["jobs"][0]["reference"] == "OUT"


def test_jobs_outside_window_are_excluded(db, admin, cleanup):
    _seed_geo(db, "CV1 1AA", 52.408054, -1.510556, cleanup)
    _seed_geo(db, "CV1 9AA", 52.410, -1.520, cleanup)
    # Schedule for 30 days from now → outside default 14-day window.
    far = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    _seed_case(db, admin, "CV1 9AA", f"{far}T10:00:00+00:00", cleanup, ref="OUTSIDE-WINDOW")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA",
            headers=_hdr(),
        )
    assert r.json()["suggestions"] == []


def test_radius_param_tightens_results(db, admin, cleanup):
    _seed_geo(db, "CV1 1AA", 52.408054, -1.510556, cleanup)
    _seed_geo(db, "CV3 4XX", 52.380, -1.480, cleanup)  # ~3 mi
    today = datetime.now(timezone.utc).date()
    day4 = (today + timedelta(days=4)).isoformat()
    _seed_case(db, admin, "CV3 4XX", f"{day4}T09:00:00+00:00", cleanup, ref="3MI")
    with httpx.Client(timeout=15.0) as c:
        r10 = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA&radius_miles=10",
            headers=_hdr(),
        )
        r1 = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA&radius_miles=1",
            headers=_hdr(),
        )
    assert r10.json()["suggestions"]
    assert r1.json()["suggestions"] == []


def test_invalid_postcode_returns_empty_with_reason():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=XXX",
            headers=_hdr(),
        )
    # min_length=3 in the query schema → "XXX" is the boundary;
    # we expect a 200 with reason=invalid_postcode since normalise
    # rejects sub-5 characters.
    assert r.status_code == 200
    body = r.json()
    assert body["suggestions"] == []
    assert body.get("reason") == "invalid_postcode"


def test_org_isolation(db, admin, cleanup):
    """Job scheduled by a DIFFERENT engineer in the same org must NOT
    appear in our suggestions."""
    _seed_geo(db, "CV1 1AA", 52.408054, -1.510556, cleanup)
    _seed_geo(db, "CV1 5BB", 52.412, -1.515, cleanup)
    today = datetime.now(timezone.utc).date()
    day2 = (today + timedelta(days=2)).isoformat()
    other_id = f"other-eng-{uuid.uuid4().hex[:8]}"
    cid = f"sched-other-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],  # SAME org
        "reference": "OTHER-ENG",
        "title": "Other engineer's job",
        "status": "scheduled",
        "assigned_engineer_id": other_id,  # DIFFERENT engineer
        "site_postcode": "CV1 5BB",
        "scheduled_at": f"{day2}T09:00:00+00:00",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    cleanup["cases"].append(cid)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA",
            headers=_hdr(),
        )
    refs = {j["reference"] for s in r.json()["suggestions"] for j in s["jobs"]}
    assert "OTHER-ENG" not in refs


def test_max_5_suggestions(db, admin, cleanup):
    """7 different dates with nearby jobs → only the top 5 are returned."""
    _seed_geo(db, "CV1 1AA", 52.408054, -1.510556, cleanup)
    _seed_geo(db, "CV1 5BB", 52.412, -1.515, cleanup)
    today = datetime.now(timezone.utc).date()
    for i in range(1, 8):
        d = (today + timedelta(days=i)).isoformat()
        _seed_case(db, admin, "CV1 5BB", f"{d}T09:00:00+00:00", cleanup, ref=f"MAX-{i}")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/scheduling-suggestions?postcode=CV1+1AA",
            headers=_hdr(),
        )
    assert len(r.json()["suggestions"]) == 5
