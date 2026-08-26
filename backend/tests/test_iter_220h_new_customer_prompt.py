"""Iter 220h — Proactive "save new customer" prompt on the New Job card.

When the engineer types a customer name that isn't in their saved
address book, GET /api/svc/engineer/customers/lookup?name=… now also
matches on name (previously: email/phone only). The frontend uses that
signal to surface an inline confirm strip so the engineer doesn't have
to rely on a passive checkbox.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://photo-fix-verify.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass(),
        )
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
    ids: list[str] = []
    yield ids
    if ids:
        db.svc_engineer_customers.delete_many({"id": {"$in": ids}})


def _seed(db, admin, name: str, cleanup_bag, **extra) -> str:
    cid = str(uuid.uuid4())
    db.svc_engineer_customers.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    })
    cleanup_bag.append(cid)
    return cid


# ─────────────────── Name match ───────────────────


def test_lookup_finds_customer_by_exact_name_case_insensitive(db, admin, cleanup):
    cid = _seed(db, admin, "Pulse Health Club 220h", cleanup, site_name="Coventry")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/lookup?name=PULSE HEALTH CLUB 220H",
            headers=_hdr(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["match_via"] == "name"
    assert body["customer"]["id"] == cid


def test_lookup_returns_not_found_for_unknown_name(db, admin):
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/lookup?name=UnknownBrandNoWayThisExists220h",
            headers=_hdr(),
        )
    assert r.status_code == 200
    assert r.json() == {"found": False}


def test_lookup_distinguishes_same_name_different_site(db, admin, cleanup):
    """Two saved customers with the same brand but different sites —
    passing site_name as a tiebreaker should match the correct row."""
    a = _seed(db, admin, "Acme Gyms 220h", cleanup, site_name="Soho")
    b = _seed(db, admin, "Acme Gyms 220h", cleanup, site_name="Bristol")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/lookup?name=Acme Gyms 220h&site_name=Bristol",
            headers=_hdr(),
        )
    body = r.json()
    assert body["found"] is True
    assert body["customer"]["id"] == b
    assert body["customer"]["id"] != a


def test_lookup_contact_match_wins_over_name(db, admin, cleanup):
    """email match short-circuits the name match (a single source of
    truth — if someone updates the name in their phone, we still
    surface the same record)."""
    cid = _seed(
        db, admin, "Old Brand Name 220h", cleanup,
        email="hello@oldbrand.test", phone="+447700900222",
    )
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/lookup?name=Renamed Brand 220h&email=hello@oldbrand.test",
            headers=_hdr(),
        )
    body = r.json()
    assert body["found"] is True
    assert body["match_via"] == "contact"
    assert body["customer"]["id"] == cid


def test_lookup_with_no_inputs_returns_not_found():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/lookup",
            headers=_hdr(),
        )
    assert r.status_code == 200
    assert r.json() == {"found": False}


def test_lookup_org_isolation(db):
    """Different org's customer with the same name must NOT leak."""
    other_org = f"other-{uuid.uuid4().hex[:8]}"
    other_id = str(uuid.uuid4())
    db.svc_engineer_customers.insert_one({
        "id": other_id,
        "organization_id": other_org,
        "name": "Leak Test 220h Unique",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/engineer/customers/lookup?name=Leak Test 220h Unique",
                headers=_hdr(),
            )
        assert r.status_code == 200
        assert r.json() == {"found": False}
    finally:
        db.svc_engineer_customers.delete_one({"id": other_id})
