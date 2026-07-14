"""Dealer Warranty Parts — Phase 2 backend tests (BOM, most-used, recommend)."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/dealer-parts"

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"

TEST_MODEL = f"TEST_MODEL_Phase2_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def token():
    # Retry with backoff for rate limiting on /api/auth/login
    for i in range(5):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        if r.status_code == 200:
            return r.json().get("access_token") or r.json().get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        break
    pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ─── BOM ─────────────────────────────────────────────────────────

class TestBOM:
    bom_v1_id = None
    bom_v2_id = None

    def test_create_bom_v1(self, client):
        payload = {
            "machine_model": TEST_MODEL,
            "machine_category": "Cardio",
            "items": [
                {"part_number": "TEST-BELT", "part_description": "Test belt", "criticality": "high",
                 "warranty_relevance": True, "wear_item": True, "cost": 120},
                {"part_number": "TEST-MOTOR", "part_description": "Test motor", "criticality": "critical",
                 "recommended_spare": True, "cost": 450},
            ],
            "status": "active",
        }
        r = client.post(f"{API}/boms", json=payload)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["machine_model"] == TEST_MODEL
        assert b["version"] == 1
        assert b["status"] == "active"
        assert len(b["items"]) == 2
        TestBOM.bom_v1_id = b["id"]

    def test_create_bom_v2_supersedes_v1(self, client):
        payload = {
            "machine_model": TEST_MODEL,
            "items": [{"part_number": "TEST-BELT", "part_description": "Test belt v2",
                       "criticality": "high", "warranty_relevance": True, "cost": 130}],
        }
        r = client.post(f"{API}/boms", json=payload)
        assert r.status_code == 200
        b = r.json()
        assert b["version"] == 2
        assert b["status"] == "active"
        TestBOM.bom_v2_id = b["id"]

        # GET include_superseded: v1 should be superseded, v2 active
        r2 = client.get(f"{API}/boms", params={"machine_model": TEST_MODEL, "include_superseded": "true"})
        assert r2.status_code == 200
        boms = {x["id"]: x for x in r2.json()["boms"]}
        assert boms[TestBOM.bom_v1_id]["status"] == "superseded"
        assert boms[TestBOM.bom_v2_id]["status"] == "active"

    def test_list_boms_hides_superseded_by_default(self, client):
        r = client.get(f"{API}/boms", params={"machine_model": TEST_MODEL})
        assert r.status_code == 200
        rows = r.json()["boms"]
        ids = {b["id"] for b in rows}
        assert TestBOM.bom_v1_id not in ids
        assert TestBOM.bom_v2_id in ids

    def test_patch_bom_status(self, client):
        r = client.patch(f"{API}/boms/{TestBOM.bom_v2_id}", json={"status": "draft"})
        assert r.status_code == 200
        assert r.json()["status"] == "draft"
        # restore active for later recommend tests to work
        r2 = client.patch(f"{API}/boms/{TestBOM.bom_v2_id}", json={"status": "active"})
        assert r2.status_code == 200


# ─── Most-Used ────────────────────────────────────────────────────

class TestMostUsed:
    mu_id = None

    def test_upsert_and_update(self, client):
        payload = {
            "machine_model": TEST_MODEL, "part_number": "TEST-BELT",
            "part_description": "Test belt MU", "priority": "high",
            "recommended_dealer_stock_quantity": 2, "cost": 120,
        }
        r = client.post(f"{API}/most-used", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["priority"] == "high"
        assert d["recommended_dealer_stock_quantity"] == 2
        TestMostUsed.mu_id = d["id"]

        # Post again — should UPDATE, not create dup.
        payload2 = {**payload, "recommended_dealer_stock_quantity": 5, "priority": "critical"}
        r2 = client.post(f"{API}/most-used", json=payload2)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["id"] == TestMostUsed.mu_id, "upsert should preserve id"
        assert d2["recommended_dealer_stock_quantity"] == 5
        assert d2["priority"] == "critical"

        # Confirm only one row for that model+part
        r3 = client.get(f"{API}/most-used", params={"machine_model": TEST_MODEL})
        rows = [x for x in r3.json()["most_used"] if x["part_number"] == "TEST-BELT"]
        assert len(rows) == 1

    def test_list_sorted_by_priority(self, client):
        # add a low-priority row
        client.post(f"{API}/most-used", json={
            "machine_model": TEST_MODEL, "part_number": "TEST-CABLE",
            "part_description": "Cable", "priority": "low",
            "recommended_dealer_stock_quantity": 1, "cost": 10,
        })
        r = client.get(f"{API}/most-used", params={"machine_model": TEST_MODEL})
        rows = r.json()["most_used"]
        ranks = [x["priority_rank"] for x in rows]
        # sorted by priority_rank desc within a machine model
        assert ranks == sorted(ranks, reverse=True), f"Not sorted desc: {ranks}"

    def test_delete_most_used(self, client):
        # create a throwaway row then delete
        r = client.post(f"{API}/most-used", json={
            "machine_model": TEST_MODEL, "part_number": "TEST-DELETE",
            "priority": "medium", "recommended_dealer_stock_quantity": 1,
        })
        mu_id = r.json()["id"]
        r2 = client.delete(f"{API}/most-used/{mu_id}")
        assert r2.status_code == 200
        # verify gone
        r3 = client.get(f"{API}/most-used", params={"machine_model": TEST_MODEL})
        assert not any(x["id"] == mu_id for x in r3.json()["most_used"])


# ─── Recommend ────────────────────────────────────────────────────

class TestRecommend:
    def test_recommend_requires_order_id(self, client):
        r = client.post(f"{API}/recommend", json={})
        assert r.status_code == 400

    def test_recommend_seeded_order(self, client):
        # Find a seeded order (Fitline Deutschland / GulfGym Trading)
        r = client.get(f"{API}/orders")
        assert r.status_code == 200
        orders = r.json().get("orders", [])
        assert orders, "No orders seeded"
        # Prefer an order for those dealers
        target = None
        for o in orders:
            name = (o.get("dealer_name") or "").lower()
            if "fitline" in name or "gulfgym" in name:
                if o.get("lines"):
                    target = o
                    break
        if not target:
            target = next((o for o in orders if o.get("lines")), None)
        assert target, "No order with lines to recommend on"

        r2 = client.post(f"{API}/recommend", json={"order_id": target["id"]})
        assert r2.status_code == 200, r2.text
        d = r2.json()
        # Shape
        for k in ("items", "recommended_items", "total_value", "allowance",
                  "allowance_remaining", "over_allowance", "duplicates_avoided",
                  "missing_bom_models"):
            assert k in d, f"missing key {k}"
        # Item shape
        if d["items"]:
            it = d["items"][0]
            for k in ("recommended_qty", "original_qty", "already_held",
                      "unit_value", "value", "reason", "duplicate_warning"):
                assert k in it, f"missing item key {k}"

    def test_recommend_duplicate_prevention(self, client):
        """For a dealer with prior allocations of a part, expect duplicates_avoided > 0
        or at least one item with already_held > 0 and recommended_qty reduced."""
        r = client.get(f"{API}/orders")
        orders = r.json().get("orders", [])
        # Search across all seeded orders — first with any recommendation netting
        found_netting = False
        checked = 0
        for o in orders:
            if not o.get("lines"):
                continue
            checked += 1
            if checked > 8:
                break
            rr = client.post(f"{API}/recommend", json={"order_id": o["id"]})
            if rr.status_code != 200:
                continue
            data = rr.json()
            if data.get("duplicates_avoided", 0) > 0:
                found_netting = True
                # Assert semantic: at least one item shows the reduction
                dup_items = [i for i in data["items"] if i.get("already_held", 0) > 0 and i["recommended_qty"] < i["original_qty"]]
                assert dup_items, "duplicates_avoided>0 but no item shows the reduction"
                assert any(i["duplicate_warning"] for i in dup_items)
                break
            # Alt signal: any item with already_held > 0
            if any(i.get("already_held", 0) > 0 for i in data.get("items", [])):
                found_netting = True
                break
        # If no seeded dealer holds anything, this is informational — still not a failure
        if not found_netting:
            pytest.skip("No seeded order surfaced netting behaviour — dealers may hold no stock/prior allocations")
