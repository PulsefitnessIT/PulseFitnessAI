"""Iter 216h84 + h85 — Parts allocation on engineer screen + Asset history.

Verifies:
  • Engineer can search & allocate a part via existing POST /svc/parts/allocate
    while engineer-app guard is active (master admin bypasses).
  • Engineer GET /svc/engineer/jobs/{id} now returns `asset_history` of
    prior closed cases for the same asset.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://aftersales-engine-1.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


@pytest.fixture
def admin_user(db):
    return db.users.find_one(
        {"email": ADMIN_EMAIL},
        {"_id": 0, "id": 1, "organization_id": 1},
    )


class TestPartsAllocationEngineer:
    def test_allocate_part_to_case(self, admin_headers, db, admin_user):
        org = admin_user["organization_id"]
        sku = f"PARTTEST-{uuid.uuid4().hex[:6].upper()}"
        # Seed catalogue part
        db.svc_parts.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": org,
            "sku": sku,
            "name": "Test belt 95T",
            "active": True,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        # Seed van stock so source=van succeeds
        db.svc_van_stock.insert_one({
            "organization_id": org,
            "engineer_id": admin_user["id"],
            "part_sku": sku,
            "qty": 5,
        })
        case_id = f"partalloc-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": case_id,
            "organization_id": org,
            "assigned_engineer_id": admin_user["id"],
            "status": "on_site", "priority": "p2",
            "title": "Belt slip",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        try:
            # Type-ahead search should find the SKU
            r = requests.get(
                f"{BASE_URL}/api/svc/parts?search={sku[:8]}&limit=5",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            assert any(p["sku"] == sku for p in r.json().get("parts", []))
            # Allocate from van
            r = requests.post(
                f"{BASE_URL}/api/svc/parts/allocate",
                json={
                    "case_id": case_id,
                    "part_sku": sku,
                    "qty": 2,
                    "source": "van",
                    "engineer_id": admin_user["id"],
                },
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            allocation_id = r.json()["id"]
            # Case now carries the embedded allocated_parts entry
            case = db.svc_cases.find_one({"id": case_id}, {"_id": 0, "allocated_parts": 1})
            assert any(p["id"] == allocation_id for p in (case["allocated_parts"] or []))
            # Van stock decreased
            van = db.svc_van_stock.find_one(
                {"organization_id": org, "engineer_id": admin_user["id"], "part_sku": sku},
                {"_id": 0, "qty": 1},
            )
            assert van["qty"] == 3
            # Deallocate restores van stock
            r = requests.delete(
                f"{BASE_URL}/api/svc/parts/allocate/{allocation_id}",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200
            van = db.svc_van_stock.find_one(
                {"organization_id": org, "engineer_id": admin_user["id"], "part_sku": sku},
                {"_id": 0, "qty": 1},
            )
            assert van["qty"] == 5
        finally:
            db.svc_cases.delete_many({"id": case_id})
            db.svc_parts.delete_many({"sku": sku})
            db.svc_van_stock.delete_many({"part_sku": sku})


class TestAssetHistory:
    def test_engineer_job_detail_returns_asset_history(self, admin_headers, db, admin_user):
        org = admin_user["organization_id"]
        asset_name = f"ASSET-HIST-{uuid.uuid4().hex[:6]}"
        now = dt.datetime.now(dt.timezone.utc)
        # Three prior closed cases on the same asset.
        prior_ids = []
        for i in range(3):
            cid = f"hist-prior-{uuid.uuid4()}"
            prior_ids.append(cid)
            db.svc_cases.insert_one({
                "id": cid,
                "reference": f"REF-PRIOR-{i}",
                "organization_id": org,
                "assigned_engineer_id": admin_user["id"],
                "asset_name": asset_name,
                "status": "closed", "priority": "p3",
                "title": f"Belt slip · prior visit {i}",
                "fault_code": "BELT_SLIP",
                "closed_at": (now - dt.timedelta(days=10 + i)).isoformat(),
                "created_at": (now - dt.timedelta(days=12 + i)).isoformat(),
                "updated_at": (now - dt.timedelta(days=10 + i)).isoformat(),
                "customer_rating": 5,
            })
        # New open case on the same asset.
        current = f"hist-current-{uuid.uuid4()}"
        db.svc_cases.insert_one({
            "id": current,
            "reference": "REF-CURRENT",
            "organization_id": org,
            "assigned_engineer_id": admin_user["id"],
            "asset_name": asset_name,
            "status": "assigned", "priority": "p2",
            "title": "Belt slip again",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/engineer/jobs/{current}",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert "asset_history" in body
            assert len(body["asset_history"]) == 3
            # Most recent (smallest day-offset) first
            refs = [h["reference"] for h in body["asset_history"]]
            assert refs == ["REF-PRIOR-0", "REF-PRIOR-1", "REF-PRIOR-2"]
            # And carries the rating + fault code
            assert all(h.get("fault_code") == "BELT_SLIP" for h in body["asset_history"])
        finally:
            db.svc_cases.delete_many({"id": {"$in": [current, *prior_ids]}})

    def test_asset_history_empty_when_no_prior_visits(self, admin_headers, db, admin_user):
        org = admin_user["organization_id"]
        cid = f"hist-empty-{uuid.uuid4()}"
        now = dt.datetime.now(dt.timezone.utc)
        db.svc_cases.insert_one({
            "id": cid,
            "organization_id": org,
            "assigned_engineer_id": admin_user["id"],
            "asset_name": f"UNIQUE-{uuid.uuid4().hex}",
            "status": "assigned", "priority": "p3",
            "title": "Brand new asset",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/svc/engineer/jobs/{cid}",
                headers=admin_headers, timeout=10,
            )
            assert r.status_code == 200
            body = r.json()
            assert body.get("asset_history") == []
        finally:
            db.svc_cases.delete_many({"id": cid})
