"""
Iter 216h18 — Master Admin brand-context query filter (Phase 2).

Pins the canonical brand classification across users + organizations,
and verifies the `?brand=` query param actually scopes the
/master-admin/organizations + /master-admin/users endpoints.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

from utils.brand_filter import (
    normalise_brand,
    brand_filter_clause,
    merge_brand_filter,
)

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


# ── Pure helper tests ──────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("pulse", "pulse"),
    ("pulse_fitness", "pulse"),
    ("Pulse", "pulse"),
    ("gymaxis", "gymaxis"),
    ("GymAxis", "gymaxis"),
    ("all", "all"),
    ("", "all"),
    (None, "all"),
    ("nonsense", "all"),
])
def test_normalise_brand_canonicalises_strings(raw, expected):
    assert normalise_brand(raw) == expected


def test_brand_filter_clause_returns_empty_for_all():
    assert brand_filter_clause("all", "users") == {}
    assert brand_filter_clause(None, "organizations") == {}


def test_brand_filter_clause_pulse_users_includes_three_paths():
    clause = brand_filter_clause("pulse", "users")
    assert "$or" in clause
    or_clauses = clause["$or"]
    assert len(or_clauses) == 3
    # Pulse account_type match
    assert any("account_type" in c and "$in" in c.get("account_type", {}) for c in or_clauses)
    # is_pulse_admin TRUE match
    assert any(c.get("is_pulse_admin") is True for c in or_clauses)
    # `brand` field match
    assert any("brand" in c for c in or_clauses)


def test_brand_filter_clause_gymaxis_orgs_includes_null_account_type():
    """GymAxis must include legacy orgs where account_type is missing
    entirely (21 such orgs exist in production)."""
    clause = brand_filter_clause("gymaxis", "organizations")
    or_clauses = clause["$or"]
    # Must include either account_type=null, $exists=false, or empty string
    has_null_path = any(
        ("$exists" in c.get("account_type", {})) or
        (c.get("account_type", {}).get("$in", []) and "" in c["account_type"]["$in"])
        for c in or_clauses
    )
    assert has_null_path


def test_merge_brand_filter_preserves_existing_query():
    existing = {"organization_id": "abc"}
    merged = merge_brand_filter(existing, "pulse", "organizations")
    assert merged["organization_id"] == "abc"
    assert "$or" in merged


def test_merge_brand_filter_promotes_double_or_to_and():
    """When both `query` and the brand filter have their own $or, we
    must promote them to an $and so neither is lost."""
    existing = {"$or": [{"foo": 1}, {"foo": 2}]}
    merged = merge_brand_filter(existing, "pulse", "organizations")
    # Both $or clauses preserved inside an $and
    assert "$and" in merged
    inner_ors = [c for c in merged["$and"] if "$or" in c]
    assert len(inner_ors) == 2


def test_merge_brand_filter_no_op_when_brand_all():
    existing = {"foo": "bar"}
    assert merge_brand_filter(existing, "all", "organizations") == existing


# ── End-to-end endpoint tests ──────────────────────────────────────

@pytest.fixture
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def master_headers():
    bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    login_headers = {"X-RateLimit-Bypass": bypass} if bypass else None
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        headers=login_headers, timeout=15,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def seeded_two_orgs(db):
    """One Pulse org + one GymAxis org, each with one staff user."""
    pulse_org_id = f"test-h18-pulse-{uuid.uuid4().hex[:8]}"
    gymaxis_org_id = f"test-h18-gymaxis-{uuid.uuid4().hex[:8]}"
    pulse_user_id = f"test-h18-pulse-staff-{uuid.uuid4().hex[:8]}"
    gymaxis_user_id = f"test-h18-gymaxis-staff-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    db.organizations.insert_many([
        {"id": pulse_org_id, "name": "Pulse Brand Test", "account_type": "pulse_pro", "created_at": now},
        {"id": gymaxis_org_id, "name": "GymAxis Brand Test", "account_type": "full", "created_at": now},
    ])
    db.users.insert_many([
        {"id": pulse_user_id, "email": f"pulse-{uuid.uuid4().hex[:6]}@example.com",
         "organization_id": pulse_org_id, "account_type": "pulse_pro", "role": "staff",
         "password": "x", "created_at": now},
        {"id": gymaxis_user_id, "email": f"gymaxis-{uuid.uuid4().hex[:6]}@example.com",
         "organization_id": gymaxis_org_id, "account_type": "full", "role": "staff",
         "password": "x", "created_at": now},
    ])
    yield {
        "pulse_org_id": pulse_org_id, "gymaxis_org_id": gymaxis_org_id,
        "pulse_user_id": pulse_user_id, "gymaxis_user_id": gymaxis_user_id,
    }
    db.users.delete_many({"id": {"$in": [pulse_user_id, gymaxis_user_id]}})
    db.organizations.delete_many({"id": {"$in": [pulse_org_id, gymaxis_org_id]}})


def test_organizations_endpoint_brand_pulse_excludes_gymaxis_orgs(master_headers, seeded_two_orgs):
    r = httpx.get(f"{API_URL}/api/master-admin/organizations?brand=pulse", headers=master_headers, timeout=15)
    assert r.status_code == 200
    org_ids = {o["id"] for o in r.json()["organizations"]}
    assert seeded_two_orgs["pulse_org_id"] in org_ids
    assert seeded_two_orgs["gymaxis_org_id"] not in org_ids


def test_organizations_endpoint_brand_gymaxis_excludes_pulse_orgs(master_headers, seeded_two_orgs):
    r = httpx.get(f"{API_URL}/api/master-admin/organizations?brand=gymaxis", headers=master_headers, timeout=15)
    assert r.status_code == 200
    org_ids = {o["id"] for o in r.json()["organizations"]}
    assert seeded_two_orgs["gymaxis_org_id"] in org_ids
    assert seeded_two_orgs["pulse_org_id"] not in org_ids


def test_organizations_endpoint_brand_all_returns_both(master_headers, seeded_two_orgs):
    r = httpx.get(f"{API_URL}/api/master-admin/organizations?brand=all", headers=master_headers, timeout=15)
    assert r.status_code == 200
    org_ids = {o["id"] for o in r.json()["organizations"]}
    assert seeded_two_orgs["pulse_org_id"] in org_ids
    assert seeded_two_orgs["gymaxis_org_id"] in org_ids


def test_users_endpoint_brand_pulse_excludes_gymaxis_users(master_headers, seeded_two_orgs):
    """Users endpoint scopes by parent-org brand (the org is the
    source of truth — a user with `account_type=null` belonging to a
    Pulse org is still a Pulse user)."""
    r = httpx.get(f"{API_URL}/api/master-admin/users?brand=pulse", headers=master_headers, timeout=15)
    assert r.status_code == 200
    user_ids = {u["id"] for u in r.json()["users"]}
    assert seeded_two_orgs["pulse_user_id"] in user_ids
    assert seeded_two_orgs["gymaxis_user_id"] not in user_ids


def test_users_endpoint_brand_gymaxis_excludes_pulse_users(master_headers, seeded_two_orgs):
    r = httpx.get(f"{API_URL}/api/master-admin/users?brand=gymaxis", headers=master_headers, timeout=15)
    assert r.status_code == 200
    user_ids = {u["id"] for u in r.json()["users"]}
    assert seeded_two_orgs["gymaxis_user_id"] in user_ids
    assert seeded_two_orgs["pulse_user_id"] not in user_ids


def test_users_endpoint_brand_omitted_defaults_to_all(master_headers, seeded_two_orgs):
    """Backwards compat — when the param is missing, return everything."""
    r = httpx.get(f"{API_URL}/api/master-admin/users", headers=master_headers, timeout=15)
    assert r.status_code == 200
    user_ids = {u["id"] for u in r.json()["users"]}
    assert seeded_two_orgs["pulse_user_id"] in user_ids
    assert seeded_two_orgs["gymaxis_user_id"] in user_ids


def test_organizations_endpoint_unknown_brand_treated_as_all(master_headers, seeded_two_orgs):
    """Defensive — a typo'd brand value must not silently 500 or hide data."""
    r = httpx.get(f"{API_URL}/api/master-admin/organizations?brand=hotpink", headers=master_headers, timeout=15)
    assert r.status_code == 200
    org_ids = {o["id"] for o in r.json()["organizations"]}
    assert seeded_two_orgs["pulse_org_id"] in org_ids
    assert seeded_two_orgs["gymaxis_org_id"] in org_ids
