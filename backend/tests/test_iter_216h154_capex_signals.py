"""Iter 216h154 — SVC → CAPEX signal layer.

Closes the feedback loop identified in the Feb 2026 process audit:
the CAPEX board report now blends 12-month service spend + visit
counts from `svc_cases` + `svc_quotes` into the repair-vs-replace
recommendation, instead of relying solely on self-service `issues`.

Audits:
  • `/api/capex/analysis` exposes `service_signals` on each
    equipment item (visits, spend, downtime, BER ratio).
  • A high spend/replacement ratio surfaces the right BER label.
  • `/api/capex/service-signals/{asset_id}` drill-down returns
    matching case_ids + the asset's BER computation.
  • Assets with zero service history still appear with zeroed
    signals (no `None` in the JSON shape — board PDF assumes
    structured zeros, not nulls).
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
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
        "id": eid,
        "organization_id": org_id,
        "name": "Test Treadmill",
        "equipment_type": "Treadmill",
        "manufacturer": "Acme",
        "model": "TM-100",
        "serial_number": f"SN-{eid[:6]}",
        "replacement_cost": 4000,
        "expected_lifespan_years": 8,
        "purchase_date": "2020-01-01",
        "warranty_expiry": "2022-01-01",
        "location": "Studio 1",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    db["equipment"].insert_one(doc)
    return eid


def _seed_case(db, org_id, *, asset_id: str, status: str = "closed",
               on_site_minutes: int = 120):
    case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": case_id,
        "organization_id": org_id,
        "reference": f"CX-{case_id[:5]}",
        "title": "CAPEX signal test",
        "status": status,
        "priority": "P3",
        "asset_id": asset_id,
        "equipment_ids": [asset_id],
        "on_site_minutes": on_site_minutes,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": datetime.now(timezone.utc).isoformat(),
    })
    return case_id


def _seed_quote(db, org_id, case_id, *, net: float,
                status: str = "invoiced"):
    qid = str(uuid.uuid4())
    db["svc_quotes"].insert_one({
        "id": qid,
        "organization_id": org_id,
        "case_id": case_id,
        "reference": f"Q-{qid[:5]}",
        "status": status,
        "net": net,
        "subtotal": net,
        "vat": round(net * 0.2, 2),
        "gross": round(net * 1.2, 2),
        "total": round(net * 1.2, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return qid


# ── /capex/analysis exposes service_signals ─────────────────────

def test_analysis_includes_service_signals_zeroed_for_quiet_assets(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    eid = _seed_equipment(db, org_id, name="Quiet Asset Iter154")
    try:
        r = requests.get(
            f"{API}/api/capex/analysis", headers=_hdr(tok), timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        item = next((e for e in data["equipment"] if e["id"] == eid), None)
        assert item is not None, "seeded equipment missing from analysis"
        sig = item.get("service_signals")
        assert sig is not None, "service_signals must always be present"
        assert sig["service_visits_12mo"] == 0
        assert sig["service_spend_12mo"] == 0.0
        assert sig["downtime_hours_12mo"] == 0.0
        assert sig["last_service_at"] is None
        # BER computation should be 'keep' with a 0 ratio.
        assert sig["ber_recommendation"] == "keep"
        assert sig["service_to_replacement_ratio"] == 0.0
    finally:
        db["equipment"].delete_one({"id": eid})


def test_analysis_high_spend_triggers_replace_recommendation(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    # £4,000 replacement; £2,500 of service spend → ratio 0.625 → REPLACE.
    eid = _seed_equipment(db, org_id, name="Heavy Spend Iter154",
                          replacement_cost=4000)
    case_ids = []
    quote_ids = []
    try:
        for amt in (1500.0, 1000.0):
            cid = _seed_case(db, org_id, asset_id=eid, on_site_minutes=180)
            qid = _seed_quote(db, org_id, cid, net=amt)
            case_ids.append(cid)
            quote_ids.append(qid)
        r = requests.get(
            f"{API}/api/capex/analysis", headers=_hdr(tok), timeout=20,
        )
        assert r.status_code == 200
        item = next(e for e in r.json()["equipment"] if e["id"] == eid)
        sig = item["service_signals"]
        assert sig["service_visits_12mo"] == 2
        assert sig["service_spend_12mo"] == 2500.0
        # Downtime: 2 cases × 3hr = 6h.
        assert sig["downtime_hours_12mo"] == 6.0
        assert sig["service_to_replacement_ratio"] == 0.625
        assert sig["ber_recommendation"] == "replace"
        assert "Replace" in sig["ber_label"]
    finally:
        db["svc_cases"].delete_many({"id": {"$in": case_ids}})
        db["svc_quotes"].delete_many({"id": {"$in": quote_ids}})
        db["equipment"].delete_one({"id": eid})


def test_analysis_mid_ratio_triggers_watch(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    # £5,000 replacement, £1,500 spend → ratio 0.30 → WATCH.
    eid = _seed_equipment(db, org_id, name="Watch Asset Iter154",
                          replacement_cost=5000)
    cid = _seed_case(db, org_id, asset_id=eid)
    qid = _seed_quote(db, org_id, cid, net=1500.0)
    try:
        r = requests.get(
            f"{API}/api/capex/analysis", headers=_hdr(tok), timeout=20,
        )
        assert r.status_code == 200
        item = next(e for e in r.json()["equipment"] if e["id"] == eid)
        sig = item["service_signals"]
        assert sig["service_to_replacement_ratio"] == 0.30
        assert sig["ber_recommendation"] == "watch"
    finally:
        db["svc_cases"].delete_one({"id": cid})
        db["svc_quotes"].delete_one({"id": qid})
        db["equipment"].delete_one({"id": eid})


# ── Drill-down endpoint ─────────────────────────────────────────

def test_drilldown_returns_case_ids_and_ber(sess):
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    eid = _seed_equipment(db, org_id, name="Drill Asset Iter154",
                          replacement_cost=2000)
    cid = _seed_case(db, org_id, asset_id=eid)
    qid = _seed_quote(db, org_id, cid, net=900.0)  # ratio 0.45 → watch
    try:
        r = requests.get(
            f"{API}/api/capex/service-signals/{eid}",
            headers=_hdr(tok), timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["asset"]["id"] == eid
        assert body["replacement_cost"] == 2000
        assert cid in body["case_ids"]
        sig = body["service_signals"]
        assert sig["service_visits_12mo"] == 1
        assert sig["service_spend_12mo"] == 900.0
        assert sig["service_to_replacement_ratio"] == 0.45
        assert sig["ber_recommendation"] == "watch"
    finally:
        db["svc_cases"].delete_one({"id": cid})
        db["svc_quotes"].delete_one({"id": qid})
        db["equipment"].delete_one({"id": eid})


def test_drilldown_404_for_unknown_asset(sess):
    tok = sess["token"]
    r = requests.get(
        f"{API}/api/capex/service-signals/does-not-exist",
        headers=_hdr(tok), timeout=15,
    )
    assert r.status_code == 404


# ── Open cases counted, not spend-bearing ───────────────────────

def test_open_cases_count_but_spend_only_on_invoiced(sess):
    """Cases still in flight inflate `open_service_cases` and visit
    count, but `service_spend_12mo` stays at zero until a quote is
    approved/invoiced — protects the BER recommendation from
    speculative spend."""
    tok = sess["token"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    eid = _seed_equipment(db, org_id, name="Open Asset Iter154")
    cid = _seed_case(db, org_id, asset_id=eid, status="on_site")
    try:
        r = requests.get(
            f"{API}/api/capex/analysis", headers=_hdr(tok), timeout=20,
        )
        item = next(e for e in r.json()["equipment"] if e["id"] == eid)
        sig = item["service_signals"]
        assert sig["service_visits_12mo"] == 1
        assert sig["open_service_cases"] == 1
        assert sig["service_spend_12mo"] == 0.0
        assert sig["ber_recommendation"] == "keep"
    finally:
        db["svc_cases"].delete_one({"id": cid})
        db["equipment"].delete_one({"id": eid})
