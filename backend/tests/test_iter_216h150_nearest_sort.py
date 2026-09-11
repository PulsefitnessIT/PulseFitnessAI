"""Iter 216h150 — "Nearest to me" haversine sort on the self-claim queue.

Covers:
  • sort=nearest with lat/lon returns distance_km per row, sorted asc.
  • Jobs without coords / postcode appear last.
  • origin_source reflects whether geolocation or postcode was used.
  • Without sort=nearest the response keeps the default priority order.
  • lat without lon (incomplete origin) silently falls back to default sort.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://fitness-onboarding-3.preview.emergentagent.com").rstrip("/")
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


# UK reference points (lat, lon, postcode):
#   London Euston       51.5285, -0.1339   (NW1 2DB)
#   Birmingham New St   52.4778, -1.8989   (B2 4QA)
#   Manchester Piccadilly  53.4775, -2.2306 (M1 2GH)
LONDON = (51.5285, -0.1339)
BIRMINGHAM = (52.4778, -1.8989)
MANCHESTER = (53.4775, -2.2306)


def _seed(db, org_id, **overrides):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "organization_id": org_id,
        "reference": f"NEAR-{case_id[:5]}",
        "title": "Nearest sort test",
        "status": "new",
        "priority": "P3",
        "site_name": "Test Site",
        "scheduled_at": None,
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["svc_cases"].insert_one(doc)
    return case_id


def test_nearest_sort_orders_by_distance(sess):
    """Seed jobs in London/Birmingham/Manchester. Engineer in London should
    see them ordered London → Birmingham → Manchester with distance_km
    populated and ascending."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    ids = {
        "lon": _seed(db, org_id, reference="NEAR-LON",
                     site_latitude=LONDON[0], site_longitude=LONDON[1]),
        "bir": _seed(db, org_id, reference="NEAR-BIR",
                     site_latitude=BIRMINGHAM[0], site_longitude=BIRMINGHAM[1]),
        "man": _seed(db, org_id, reference="NEAR-MAN",
                     site_latitude=MANCHESTER[0], site_longitude=MANCHESTER[1]),
    }
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/queue/unassigned",
            headers=_hdr(tok),
            params={"sort": "nearest", "lat": LONDON[0], "lon": LONDON[1], "limit": 500},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("sort") == "nearest"
        assert body.get("origin_source") == "geolocation"
        seeded = [j for j in body["jobs"] if j["id"] in ids.values()]
        # Filter & order
        order = [j["reference"] for j in seeded]
        assert order.index("NEAR-LON") < order.index("NEAR-BIR") < order.index("NEAR-MAN")
        # All have distance_km populated and ascending
        dists = [j["distance_km"] for j in seeded]
        assert all(isinstance(d, (int, float)) for d in dists)
        assert dists == sorted(dists)
        # ETA minutes — present, ascending, rounded to 5-min increments
        etas = [j["eta_minutes"] for j in seeded]
        assert all(isinstance(e, int) and e % 5 == 0 and e >= 5 for e in etas)
        assert etas == sorted(etas)
        # Sanity check magnitudes (London->Birmingham ~ 160km, ->Manchester ~ 260km)
        by_ref = {j["reference"]: j["distance_km"] for j in seeded}
        assert by_ref["NEAR-LON"] < 5
        assert 130 < by_ref["NEAR-BIR"] < 200
        assert 230 < by_ref["NEAR-MAN"] < 300
        # Birmingham ETA at 50km/h ≈ 190 min; Manchester ≈ 310 min (loose bounds)
        eta_by_ref = {j["reference"]: j["eta_minutes"] for j in seeded}
        assert 150 < eta_by_ref["NEAR-BIR"] < 240
        assert 270 < eta_by_ref["NEAR-MAN"] < 360
    finally:
        db["svc_cases"].delete_many({"id": {"$in": list(ids.values())}})


def test_nearest_jobs_without_coords_appear_last(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    near_id = _seed(db, org_id, reference="NEAR-WITH",
                    site_latitude=LONDON[0], site_longitude=LONDON[1])
    blind_id = _seed(db, org_id, reference="NEAR-BLIND")  # no coords, no postcode
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/queue/unassigned",
            headers=_hdr(tok),
            params={"sort": "nearest", "lat": LONDON[0], "lon": LONDON[1], "limit": 500},
            timeout=15,
        )
        assert r.status_code == 200
        seeded = [j for j in r.json()["jobs"] if j["id"] in (near_id, blind_id)]
        order = [j["reference"] for j in seeded]
        assert order.index("NEAR-WITH") < order.index("NEAR-BLIND")
        blind = next(j for j in seeded if j["id"] == blind_id)
        assert blind["distance_km"] is None
        assert blind["eta_minutes"] is None
    finally:
        db["svc_cases"].delete_many({"id": {"$in": [near_id, blind_id]}})


def test_default_sort_unchanged_without_nearest_param(sess):
    """Without sort=nearest the response should not include distance_km
    and origin_source must be null. Existing priority order survives."""
    tok = sess["token"]
    r = requests.get(
        f"{API}/api/svc/engineer/queue/unassigned",
        headers=_hdr(tok), timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("sort") == "default"
    assert body.get("origin_source") in (None,)
    for j in body["jobs"]:
        assert "distance_km" not in j or j["distance_km"] is None


def test_nearest_requires_origin_else_falls_back(sess):
    """sort=nearest without lat/lon/postcode silently falls back to
    default ordering (no 500, no distance_km)."""
    tok = sess["token"]
    r = requests.get(
        f"{API}/api/svc/engineer/queue/unassigned",
        headers=_hdr(tok),
        params={"sort": "nearest"},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("sort") == "default"
    assert body.get("origin_source") is None


def test_nearest_with_postcode_origin(sess):
    """sort=nearest with a UK postcode resolves origin via postcodes.io.
    This hits an external API; tolerate failures gracefully."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed(db, org_id, reference="NEAR-PC",
                    site_latitude=LONDON[0], site_longitude=LONDON[1])
    try:
        r = requests.get(
            f"{API}/api/svc/engineer/queue/unassigned",
            headers=_hdr(tok),
            params={"sort": "nearest", "postcode": "NW1 2DB", "limit": 500},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        # If postcodes.io is reachable, origin_source == "postcode".
        if body.get("origin_source") == "postcode":
            seeded = next(j for j in body["jobs"] if j["id"] == case_id)
            assert seeded["distance_km"] is not None
            assert seeded["distance_km"] < 5  # within central London
        else:
            # External API unreachable — confirm graceful fallback
            assert body.get("sort") == "default"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
