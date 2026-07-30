"""Iter 220f — Customer typeahead on the New Job card.

GET /api/svc/engineer/customers/typeahead returns up to N matches from
two sources, deduped:
  1. `svc_engineer_customers` (saved address book, source="saved")
  2. `svc_cases` distinct customer/site rows (source="history")

Goal: engineer types "Pulse" → picks the right one → ALL customer + site
fields are auto-filled on the New Job form, saving keystrokes.
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
def cleanup(db, admin):
    """Track docs inserted during a test so we can scrub them afterwards
    without nuking the shared fixtures."""
    saved_ids: list[str] = []
    case_ids: list[str] = []
    yield {"saved": saved_ids, "cases": case_ids}
    if saved_ids:
        db.svc_engineer_customers.delete_many({"id": {"$in": saved_ids}})
    if case_ids:
        db.svc_cases.delete_many({"id": {"$in": case_ids}})


def _insert_saved(db, admin, name: str, **extra) -> str:
    cid = str(uuid.uuid4())
    db.svc_engineer_customers.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    })
    return cid


def _insert_case(db, admin, **fields) -> str:
    cid = f"caseh-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "reference": "TYP-T",
        "title": "Typeahead test",
        "status": "closed",
        "assigned_engineer_id": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    })
    return cid


# ─────────────────── Saved customer match ───────────────────


def test_typeahead_finds_saved_customer_by_name(db, admin, cleanup):
    cid = _insert_saved(
        db, admin, "Pulse Coventry typeahead220f",
        email="ops@pulse.test",
        phone="+44 7700 900100",
        site_name="Pulse Coventry HQ",
        site_address="12 Greyfriars Lane, Coventry",
    )
    cleanup["saved"].append(cid)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=typeahead220f",
            headers=_hdr(),
        )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    hit = next((x for x in results if x.get("id") == cid), None)
    assert hit is not None
    assert hit["source"] == "saved"
    assert hit["email"] == "ops@pulse.test"
    assert hit["site_address"] == "12 Greyfriars Lane, Coventry"


def test_typeahead_finds_saved_by_site_name(db, admin, cleanup):
    cid = _insert_saved(
        db, admin, "GreyfriarsClient220f",
        site_name="Greyfriars Sports Hub 220f",
    )
    cleanup["saved"].append(cid)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=Greyfriars Sports Hub 220f",
            headers=_hdr(),
        )
    results = r.json()["results"]
    assert any(x.get("id") == cid for x in results)


def test_typeahead_finds_saved_by_phone(db, admin, cleanup):
    cid = _insert_saved(
        db, admin, "PhoneSearch220f",
        phone="+44 7700 900220",
    )
    cleanup["saved"].append(cid)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=900220",
            headers=_hdr(),
        )
    results = r.json()["results"]
    assert any(x.get("id") == cid for x in results)


# ─────────────────── Case-history fallback ───────────────────


def test_typeahead_falls_back_to_case_history(db, admin, cleanup):
    """Customer logged via the email-parse flow → case row exists but
    they were never saved to the address book. The typeahead should
    still surface them so the engineer can re-use the details."""
    case_id = _insert_case(
        db, admin,
        customer_name="Acme Fitness History220f",
        customer_email="reception@acme.test",
        customer_phone="+44 7700 900321",
        site_name="Acme Soho Branch 220f",
        site_address="3 Wardour Street, London",
        site_postcode="W1D 6PE",
    )
    cleanup["cases"].append(case_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=History220f",
            headers=_hdr(),
        )
    results = r.json()["results"]
    hit = next((x for x in results if x.get("name") == "Acme Fitness History220f"), None)
    assert hit is not None
    assert hit["source"] == "history"
    # All fields surface so the form auto-fills with no extra typing.
    assert hit["email"] == "reception@acme.test"
    assert hit["site_postcode"] == "W1D 6PE"


def test_typeahead_dedupes_saved_over_history(db, admin, cleanup):
    """A customer who is BOTH in the saved book AND has prior cases
    should only appear once (saved version wins)."""
    saved_id = _insert_saved(
        db, admin, "DuplicateDedupe220f",
        site_name="Site 220f",
        email="dup@test.test",
    )
    cleanup["saved"].append(saved_id)
    case_id = _insert_case(
        db, admin,
        customer_name="DuplicateDedupe220f",
        site_name="Site 220f",
        site_postcode="CV1 1AA",
    )
    cleanup["cases"].append(case_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=DuplicateDedupe220f",
            headers=_hdr(),
        )
    results = r.json()["results"]
    matches = [x for x in results if x.get("name") == "DuplicateDedupe220f"]
    assert len(matches) == 1
    assert matches[0]["source"] == "saved"


def test_typeahead_limit_respected(db, admin, cleanup):
    """Adding 5 saved customers + asking limit=3 returns at most 3."""
    for i in range(5):
        cid = _insert_saved(db, admin, f"LimitTest220f {i}", site_name="Branch")
        cleanup["saved"].append(cid)
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/engineer/customers/typeahead?q=LimitTest220f&limit=3",
            headers=_hdr(),
        )
    results = r.json()["results"]
    assert len(results) == 3


def test_typeahead_org_isolation(db, cleanup):
    """A customer from a different org must NOT leak into our typeahead."""
    other_org = f"other-org-{uuid.uuid4().hex[:8]}"
    other_cid = str(uuid.uuid4())
    db.svc_engineer_customers.insert_one({
        "id": other_cid,
        "organization_id": other_org,
        "name": "Leak Test 220f UNIQUE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/engineer/customers/typeahead?q=Leak Test 220f UNIQUE",
                headers=_hdr(),
            )
        assert r.status_code == 200
        results = r.json()["results"]
        assert not any(x.get("name") == "Leak Test 220f UNIQUE" for x in results)
    finally:
        db.svc_engineer_customers.delete_one({"id": other_cid})


def test_typeahead_empty_query_400():
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/svc/engineer/customers/typeahead?q=", headers=_hdr())
    assert r.status_code == 422  # FastAPI validation on min_length
