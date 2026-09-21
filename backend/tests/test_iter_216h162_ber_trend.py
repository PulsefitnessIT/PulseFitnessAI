"""Iter 216h162 — BER trend (6mo vs 12mo) endpoint."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://aftersales-engine.preview.emergentagent.com").rstrip("/")
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


def _seed_equipment(db, org_id, **overrides):
    eid = str(uuid.uuid4())
    doc = {
        "id": eid, "organization_id": org_id,
        "name": "Trend Treadmill",
        "equipment_type": "Treadmill",
        "manufacturer": "Acme",
        "model": "X100",
        "serial_number": f"SN-{eid[:6]}",
        "replacement_cost": 4000,
        "expected_lifespan_years": 8,
        "purchase_date": "2020-01-01",
        "warranty_expiry": "2022-01-01",
        "location": "Studio",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["equipment"].insert_one(doc)
    return eid


def _seed_case(db, org_id, *, asset_id, days_ago=30, on_site_minutes=60):
    case_id = str(uuid.uuid4())
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db["svc_cases"].insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": f"TR-{case_id[:5]}", "title": "BER trend test",
        "status": "closed", "priority": "P3",
        "asset_id": asset_id, "equipment_ids": [asset_id],
        "on_site_minutes": on_site_minutes,
        "created_at": when.isoformat(),
        "updated_at": when.isoformat(),
        "closed_at": when.isoformat(),
    })
    return case_id


def _seed_quote(db, org_id, case_id, *, net, status="invoiced"):
    qid = str(uuid.uuid4())
    db["svc_quotes"].insert_one({
        "id": qid, "organization_id": org_id, "case_id": case_id,
        "reference": f"Q-{qid[:5]}", "status": status,
        "net": net, "subtotal": net,
        "gross": round(net * 1.2, 2),
        "total": round(net * 1.2, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return qid


# ── Trend endpoint structure ────────────────────────────────────

def test_ber_trend_returns_window_shape(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/capex/ber-trend", headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "windows" in body
    assert set(body["windows"].keys()) == {"6mo", "12mo"}
    for w in ("6mo", "12mo"):
        for bucket in ("replace", "watch", "keep", "insufficient_data"):
            assert bucket in body["windows"][w]
            assert isinstance(body["windows"][w][bucket], int)
    assert isinstance(body["movers"], list)
    assert isinstance(body["totals"]["6mo"], int)
    assert isinstance(body["totals"]["12mo"], int)


# ── Worsening asset is flagged as a mover ───────────────────────

def test_ber_trend_detects_worsening_asset(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    # £2,000 replacement. Last 5 months spent £900 (recent burst);
    # months 6–12 had £100. So:
    #   12mo ratio = (900+100) / 2000 = 0.5   → replace boundary
    #   6mo  ratio = 900 / 2000 = 0.45;  annualised = 0.90 → replace
    # The asset's bucket *moved* (was 'replace' borderline at 12mo,
    # solidly 'replace' annualised at 6mo) OR its ratio jumped enough
    # to qualify as a worsening mover.
    eid = _seed_equipment(db, org_id, name="Worsening Asset Iter162",
                          replacement_cost=2000)
    c1 = _seed_case(db, org_id, asset_id=eid, days_ago=30)  # recent
    q1 = _seed_quote(db, org_id, c1, net=900.0)
    c2 = _seed_case(db, org_id, asset_id=eid, days_ago=300)  # old
    q2 = _seed_quote(db, org_id, c2, net=100.0)
    try:
        r = requests.get(f"{API}/api/capex/ber-trend",
                         headers=_hdr(tok), timeout=20)
        assert r.status_code == 200
        body = r.json()
        ours = next((m for m in body["movers"] if m["id"] == eid), None)
        assert ours is not None, "worsening asset missing from movers"
        # 6-month annualised ratio > 12-month ratio → worsening direction.
        assert ours["direction"] == "worsening"
        assert ours["ratio_6mo"] >= 0.85   # 900*2/2000 = 0.9
        assert ours["ratio_12mo"] == 0.5
        # Ratio delta meaningful
        assert ours["ratio_delta"] >= 0.10
    finally:
        db["svc_cases"].delete_many({"id": {"$in": [c1, c2]}})
        db["svc_quotes"].delete_many({"id": {"$in": [q1, q2]}})
        db["equipment"].delete_one({"id": eid})


# ── Stable asset is NOT flagged ─────────────────────────────────

def test_ber_trend_omits_stable_assets(sess):
    """An asset with even spend across both periods should not appear
    in the movers list — same bucket, no ratio jump."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    # £4,000 replacement, £100 in last 90 days, £100 in months 6-9.
    # 12mo ratio = 200/4000 = 0.05 → keep
    # 6mo annualised = 100*2/4000 = 0.05 → keep
    eid = _seed_equipment(db, org_id, name="Stable Asset Iter162",
                          replacement_cost=4000)
    c1 = _seed_case(db, org_id, asset_id=eid, days_ago=60)
    q1 = _seed_quote(db, org_id, c1, net=100.0)
    c2 = _seed_case(db, org_id, asset_id=eid, days_ago=240)
    q2 = _seed_quote(db, org_id, c2, net=100.0)
    try:
        r = requests.get(f"{API}/api/capex/ber-trend",
                         headers=_hdr(tok), timeout=20)
        body = r.json()
        ours = next((m for m in body["movers"] if m["id"] == eid), None)
        assert ours is None, f"stable asset should not be a mover: {ours}"
    finally:
        db["svc_cases"].delete_many({"id": {"$in": [c1, c2]}})
        db["svc_quotes"].delete_many({"id": {"$in": [q1, q2]}})
        db["equipment"].delete_one({"id": eid})


# ── Improving asset (recent quiet, old noisy) ───────────────────

def test_ber_trend_detects_improving_asset(sess):
    """Mostly-old spend should produce an 'improving' direction tag."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    # £2,000 replacement, £950 spent 240 days ago, nothing recent.
    # 12mo ratio = 950/2000 = 0.475  → watch
    # 6mo ratio  = 0/2000 = 0       → keep (annualised still 0)
    # bucket moves watch→keep, direction = improving
    eid = _seed_equipment(db, org_id, name="Improving Asset Iter162",
                          replacement_cost=2000)
    c1 = _seed_case(db, org_id, asset_id=eid, days_ago=240)
    q1 = _seed_quote(db, org_id, c1, net=950.0)
    try:
        r = requests.get(f"{API}/api/capex/ber-trend",
                         headers=_hdr(tok), timeout=20)
        body = r.json()
        ours = next((m for m in body["movers"] if m["id"] == eid), None)
        assert ours is not None, "bucket change must surface as a mover"
        assert ours["direction"] == "improving"
        assert ours["from_recommendation"] in ("watch", "keep")
        assert ours["to_recommendation"] == "keep"
    finally:
        db["svc_cases"].delete_one({"id": c1})
        db["svc_quotes"].delete_one({"id": q1})
        db["equipment"].delete_one({"id": eid})
