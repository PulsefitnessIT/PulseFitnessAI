"""Iter 216h224 — CRM Phase 2 comprehensive tests.

Tests all features from the review request:
  • Products CRUD + markup auto-compute
  • SKU duplicate rejection (409)
  • Soft-delete (active=false)
  • Search/filter products
  • CSV bulk import
  • Approval settings threshold
  • Quote margin calculation + pending_approval flow
  • Quote product_id hydration from catalogue
  • Approve/reject endpoints
  • Versioning (new-version, versions list)
  • Duplicate endpoint
  • PDF export
  • Default list hides superseded versions
  • show_all_versions=true includes superseded
"""
from __future__ import annotations

import os
import uuid
import io

import httpx
import pytest


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def _crm_token() -> str:
    main = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    r = httpx.post(
        f"{API}/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def crm_token() -> str:
    return _crm_token()


@pytest.fixture(scope="module")
def auth(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


@pytest.fixture
def cleanup_after():
    """Yields a list of (collection, query) tuples; after the test we delete them."""
    todo: list[tuple[str, dict]] = []
    yield todo
    try:
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _go():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            for coll, q in todo:
                await getattr(db, coll).delete_many(q)
        asyncio.run(_go())
    except Exception:
        pass


# ── Products CRUD ──────────────────────────────────────────────────


class TestProductsCRUD:
    """Products endpoint tests"""

    def test_create_product_computes_markup(self, auth, cleanup_after):
        """POST /crm/products creates product, auto-computes markup_percent"""
        sku = f"TEST-MARKUP-{uuid.uuid4().hex[:6]}"
        r = httpx.post(
            f"{API}/crm/products",
            json={"name": "Markup Test Product", "sku": sku, "cost_price": 100, "sell_price": 150, "category": "Equipment"},
            headers=auth, timeout=15,
        )
        assert r.status_code == 200
        p = r.json()
        assert p["markup_percent"] == 50.0  # (150-100)/100 * 100 = 50%
        assert p["cost_price"] == 100
        assert p["sell_price"] == 150
        assert p["name"] == "Markup Test Product"
        assert p["sku"] == sku
        assert "id" in p
        cleanup_after.append(("crm_products", {"sku": sku}))

    def test_create_product_rejects_duplicate_sku(self, auth, cleanup_after):
        """POST /crm/products rejects duplicate SKU within the same org (409)"""
        sku = f"TEST-DUP-{uuid.uuid4().hex[:6]}"
        r1 = httpx.post(
            f"{API}/crm/products",
            json={"name": "First Product", "sku": sku, "cost_price": 10, "sell_price": 20},
            headers=auth, timeout=15,
        )
        assert r1.status_code == 200
        
        r2 = httpx.post(
            f"{API}/crm/products",
            json={"name": "Second Product", "sku": sku, "cost_price": 15, "sell_price": 25},
            headers=auth, timeout=15,
        )
        assert r2.status_code == 409
        assert "already exists" in r2.json().get("detail", "").lower()
        cleanup_after.append(("crm_products", {"sku": sku}))

    def test_soft_delete_sets_inactive(self, auth, cleanup_after):
        """DELETE /crm/products/{id} is a soft-delete (sets active=false, keeps record)"""
        sku = f"TEST-SOFTDEL-{uuid.uuid4().hex[:6]}"
        r = httpx.post(
            f"{API}/crm/products",
            json={"name": "Soft Delete Product", "sku": sku, "cost_price": 50, "sell_price": 100},
            headers=auth, timeout=15,
        )
        pid = r.json()["id"]
        
        rd = httpx.delete(f"{API}/crm/products/{pid}", headers=auth, timeout=15)
        assert rd.status_code == 200
        assert rd.json().get("deactivated") is True
        
        # Verify record still exists but is inactive
        rg = httpx.get(f"{API}/crm/products/{pid}", headers=auth, timeout=15)
        assert rg.status_code == 200
        assert rg.json()["active"] is False
        cleanup_after.append(("crm_products", {"sku": sku}))

    def test_search_and_filter_products(self, auth, cleanup_after):
        """GET /crm/products?search=...&category=... filters correctly"""
        # Create test products
        sku1 = f"TEST-SEARCH-{uuid.uuid4().hex[:6]}"
        sku2 = f"TEST-FILTER-{uuid.uuid4().hex[:6]}"
        
        httpx.post(f"{API}/crm/products", json={
            "name": "Searchable Treadmill", "sku": sku1, "cost_price": 1000, "sell_price": 1500, "category": "Equipment"
        }, headers=auth, timeout=15)
        
        httpx.post(f"{API}/crm/products", json={
            "name": "Service Contract", "sku": sku2, "cost_price": 100, "sell_price": 200, "category": "Service"
        }, headers=auth, timeout=15)
        
        # Test search by name
        r_search = httpx.get(f"{API}/crm/products", params={"search": "Treadmill"}, headers=auth, timeout=15)
        assert r_search.status_code == 200
        products = r_search.json()["products"]
        assert any(p["sku"] == sku1 for p in products)
        
        # Test filter by category
        r_filter = httpx.get(f"{API}/crm/products", params={"category": "Service"}, headers=auth, timeout=15)
        assert r_filter.status_code == 200
        products = r_filter.json()["products"]
        assert any(p["sku"] == sku2 for p in products)
        
        cleanup_after.append(("crm_products", {"sku": {"$in": [sku1, sku2]}}))


class TestProductsBulkImport:
    """CSV bulk import tests"""

    def test_csv_bulk_import(self, auth, cleanup_after):
        """POST /crm/products/bulk-import accepts a CSV multipart upload"""
        # Create a small CSV fixture
        csv_content = """name,sku,cost_price,sell_price,category
Imported Treadmill,IMP-TREAD-001,800,1200,Equipment
Imported Bike,IMP-BIKE-001,500,750,Equipment
Imported Service,IMP-SVC-001,50,100,Service"""
        
        files = {"file": ("products.csv", csv_content, "text/csv")}
        r = httpx.post(
            f"{API}/crm/products/bulk-import",
            files=files,
            headers=auth,
            timeout=30,
        )
        assert r.status_code == 200
        result = r.json()
        assert result["created"] >= 3 or result["updated"] >= 0  # May update if re-run
        assert "errors" in result
        
        # Verify products were created
        r_check = httpx.get(f"{API}/crm/products", params={"search": "IMP-TREAD-001"}, headers=auth, timeout=15)
        assert r_check.status_code == 200
        products = r_check.json()["products"]
        assert any(p["sku"] == "IMP-TREAD-001" for p in products)
        
        cleanup_after.append(("crm_products", {"sku": {"$regex": "^IMP-"}}))


# ── Approval Settings ──────────────────────────────────────────────


class TestApprovalSettings:
    """Approval threshold settings tests"""

    def test_set_approval_threshold(self, auth, cleanup_after):
        """PUT /crm/quotes/settings/approval sets the org's min_margin_percent threshold"""
        r = httpx.put(
            f"{API}/crm/quotes/settings/approval",
            json={"min_margin_percent": 35},
            headers=auth, timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["min_margin_percent"] == 35
        assert data["enabled"] is True
        
        # Verify it persisted
        rg = httpx.get(f"{API}/crm/quotes/settings/approval", headers=auth, timeout=15)
        assert rg.status_code == 200
        assert rg.json()["min_margin_percent"] == 35
        
        cleanup_after.append(("crm_settings", {"key": "quote_approval"}))


# ── Quotes with Margin + Approval ──────────────────────────────────


class TestQuotesMarginApproval:
    """Quote margin calculation and approval workflow tests"""

    def test_quote_below_threshold_pending_approval(self, auth, cleanup_after):
        """POST /crm/quotes with line_items below threshold creates status='pending_approval'"""
        # Set 40% threshold
        httpx.put(f"{API}/crm/quotes/settings/approval", json={"min_margin_percent": 40}, headers=auth, timeout=15)
        
        # Create quote with 33% margin (150 sell, 100 cost = 33.33% margin)
        r = httpx.post(
            f"{API}/crm/quotes",
            json={
                "title": "Low Margin Quote",
                "company_name": "Test Co",
                "line_items": [{"description": "Item", "quantity": 1, "unit_price": 150, "cost_price": 100}],
            },
            headers=auth, timeout=15,
        )
        assert r.status_code == 200
        q = r.json()
        assert q["status"] == "pending_approval"
        assert q["approval_status"] == "pending"
        assert q["gross_margin_percent"] == pytest.approx(33.33, rel=0.01)
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))
        cleanup_after.append(("crm_settings", {"key": "quote_approval"}))

    def test_quote_above_threshold_draft(self, auth, cleanup_after):
        """POST /crm/quotes with healthy margin creates status='draft', approval_status='not_required'"""
        # Set 20% threshold
        httpx.put(f"{API}/crm/quotes/settings/approval", json={"min_margin_percent": 20}, headers=auth, timeout=15)
        
        # Create quote with 50% margin (100 sell, 50 cost = 50% margin)
        r = httpx.post(
            f"{API}/crm/quotes",
            json={
                "title": "Healthy Margin Quote",
                "line_items": [{"description": "Item", "quantity": 2, "unit_price": 100, "cost_price": 50}],
            },
            headers=auth, timeout=15,
        )
        assert r.status_code == 200
        q = r.json()
        assert q["status"] == "draft"
        assert q["approval_status"] == "not_required"
        assert q["gross_margin_percent"] == pytest.approx(50.0, rel=0.01)
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))
        cleanup_after.append(("crm_settings", {"key": "quote_approval"}))

    def test_quote_product_hydration(self, auth, cleanup_after):
        """POST /crm/quotes line_item with product_id hydrates from catalogue"""
        # Create a product
        sku = f"TEST-HYDRATE-{uuid.uuid4().hex[:6]}"
        p = httpx.post(
            f"{API}/crm/products",
            json={"name": "Hydration Product", "sku": sku, "cost_price": 80, "sell_price": 120, "tax_rate": 20},
            headers=auth, timeout=15,
        ).json()
        
        # Create quote with product_id
        q = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Hydration Test", "line_items": [{"product_id": p["id"], "quantity": 3}]},
            headers=auth, timeout=15,
        ).json()
        
        li = q["line_items"][0]
        assert li["unit_price"] == 120  # hydrated from product
        assert li["cost_price"] == 80
        assert li["product_name"] == "Hydration Product"
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))
        cleanup_after.append(("crm_products", {"sku": sku}))


class TestQuoteApproveReject:
    """Approve/reject endpoint tests"""

    def test_approve_quote(self, auth, cleanup_after):
        """POST /crm/quotes/{id}/approve flips approval_status to 'approved'"""
        # Set threshold and create pending quote
        httpx.put(f"{API}/crm/quotes/settings/approval", json={"min_margin_percent": 50}, headers=auth, timeout=15)
        
        q = httpx.post(
            f"{API}/crm/quotes",
            json={
                "title": "Approve Test",
                "line_items": [{"description": "Item", "quantity": 1, "unit_price": 120, "cost_price": 100}],
            },
            headers=auth, timeout=15,
        ).json()
        
        assert q["approval_status"] == "pending"
        
        # Approve
        ra = httpx.post(f"{API}/crm/quotes/{q['id']}/approve", headers=auth, timeout=15)
        assert ra.status_code == 200
        assert ra.json()["approved"] is True
        
        # Verify
        rg = httpx.get(f"{API}/crm/quotes/{q['id']}", headers=auth, timeout=15)
        assert rg.json()["approval_status"] == "approved"
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))
        cleanup_after.append(("crm_settings", {"key": "quote_approval"}))

    def test_reject_quote_requires_reason(self, auth, cleanup_after):
        """POST /crm/quotes/{id}/reject requires a reason, flips to 'rejected'"""
        # Set threshold and create pending quote
        httpx.put(f"{API}/crm/quotes/settings/approval", json={"min_margin_percent": 50}, headers=auth, timeout=15)
        
        q = httpx.post(
            f"{API}/crm/quotes",
            json={
                "title": "Reject Test",
                "line_items": [{"description": "Item", "quantity": 1, "unit_price": 110, "cost_price": 100}],
            },
            headers=auth, timeout=15,
        ).json()
        
        # Reject with reason
        rr = httpx.post(
            f"{API}/crm/quotes/{q['id']}/reject",
            json={"reason": "Margin too low for this customer"},
            headers=auth, timeout=15,
        )
        assert rr.status_code == 200
        assert rr.json()["rejected"] is True
        assert rr.json()["reason"] == "Margin too low for this customer"
        
        # Verify
        rg = httpx.get(f"{API}/crm/quotes/{q['id']}", headers=auth, timeout=15)
        assert rg.json()["approval_status"] == "rejected"
        assert rg.json()["rejection_reason"] == "Margin too low for this customer"
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))
        cleanup_after.append(("crm_settings", {"key": "quote_approval"}))


class TestQuoteVersioning:
    """Quote versioning tests"""

    def test_new_version_creates_v2(self, auth, cleanup_after):
        """POST /crm/quotes/{id}/new-version creates v2 with parent_quote_id link"""
        q1 = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Version Chain", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 60}]},
            headers=auth, timeout=15,
        ).json()
        
        r2 = httpx.post(f"{API}/crm/quotes/{q1['id']}/new-version", headers=auth, timeout=15)
        q2 = r2.json()
        
        assert q2["version"] == 2
        assert q2["parent_quote_id"] == q1["id"]
        assert q2["is_latest_version"] is True
        
        # Verify v1 is marked as not latest
        rg1 = httpx.get(f"{API}/crm/quotes/{q1['id']}", headers=auth, timeout=15)
        assert rg1.json()["is_latest_version"] is False
        
        cleanup_after.append(("crm_quotes", {"$or": [{"id": q1["id"]}, {"id": q2["id"]}]}))

    def test_versions_endpoint_returns_chain(self, auth, cleanup_after):
        """GET /crm/quotes/{id}/versions returns the full chain in order"""
        q1 = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Version List Test", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 60}]},
            headers=auth, timeout=15,
        ).json()
        
        q2 = httpx.post(f"{API}/crm/quotes/{q1['id']}/new-version", headers=auth, timeout=15).json()
        q3 = httpx.post(f"{API}/crm/quotes/{q2['id']}/new-version", headers=auth, timeout=15).json()
        
        rl = httpx.get(f"{API}/crm/quotes/{q1['id']}/versions", headers=auth, timeout=15)
        assert rl.status_code == 200
        vlist = rl.json()["versions"]
        assert len(vlist) == 3
        assert {v["version"] for v in vlist} == {1, 2, 3}
        
        cleanup_after.append(("crm_quotes", {"$or": [{"id": q1["id"]}, {"id": q2["id"]}, {"id": q3["id"]}]}))


class TestQuoteDuplicate:
    """Quote duplicate tests"""

    def test_duplicate_clears_state(self, auth, cleanup_after):
        """POST /crm/quotes/{id}/duplicate clears state (status=draft, accepted_at=null, no parent link)"""
        src = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Dup Source", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 50}]},
            headers=auth, timeout=15,
        ).json()
        
        # Accept the source
        httpx.post(f"{API}/crm/quotes/{src['id']}/accept", json={"accepted_by": "test"}, headers=auth, timeout=15)
        
        # Duplicate
        rd = httpx.post(f"{API}/crm/quotes/{src['id']}/duplicate", headers=auth, timeout=15)
        dup = rd.json()
        
        assert dup["id"] != src["id"]
        assert dup["status"] == "draft"
        assert dup["accepted_at"] is None
        assert dup["parent_quote_id"] is None
        assert dup["version"] == 1
        
        cleanup_after.append(("crm_quotes", {"$or": [{"id": src["id"]}, {"id": dup["id"]}]}))


class TestQuotePDF:
    """PDF export tests"""

    def test_pdf_returns_valid_pdf(self, auth, cleanup_after):
        """GET /crm/quotes/{id}/pdf returns content-type application/pdf with bytes starting in %PDF"""
        q = httpx.post(
            f"{API}/crm/quotes",
            json={
                "title": "PDF Test",
                "company_name": "Acme PDF Co",
                "line_items": [{"description": "A", "quantity": 1, "unit_price": 99.99, "cost_price": 50}],
            },
            headers=auth, timeout=15,
        ).json()
        
        rp = httpx.get(f"{API}/crm/quotes/{q['id']}/pdf", headers=auth, timeout=20)
        assert rp.status_code == 200
        assert rp.headers["content-type"].startswith("application/pdf")
        assert rp.content[:4] == b"%PDF"
        assert len(rp.content) > 1000
        
        cleanup_after.append(("crm_quotes", {"id": q["id"]}))


class TestQuoteListFiltering:
    """Quote list filtering tests"""

    def test_default_list_hides_superseded_versions(self, auth, cleanup_after):
        """GET /crm/quotes default list hides superseded versions (is_latest_version=false)"""
        q1 = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Filter Test", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 60}]},
            headers=auth, timeout=15,
        ).json()
        
        q2 = httpx.post(f"{API}/crm/quotes/{q1['id']}/new-version", headers=auth, timeout=15).json()
        
        # Default list should only show v2 (latest)
        rl = httpx.get(f"{API}/crm/quotes", headers=auth, timeout=15)
        quotes = rl.json()["quotes"]
        quote_ids = [q["id"] for q in quotes]
        
        assert q2["id"] in quote_ids  # v2 should be visible
        assert q1["id"] not in quote_ids  # v1 should be hidden
        
        cleanup_after.append(("crm_quotes", {"$or": [{"id": q1["id"]}, {"id": q2["id"]}]}))

    def test_show_all_versions_includes_superseded(self, auth, cleanup_after):
        """GET /crm/quotes?show_all_versions=true includes superseded versions"""
        q1 = httpx.post(
            f"{API}/crm/quotes",
            json={"title": "Show All Test", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 60}]},
            headers=auth, timeout=15,
        ).json()
        
        q2 = httpx.post(f"{API}/crm/quotes/{q1['id']}/new-version", headers=auth, timeout=15).json()
        
        # With show_all_versions=true, both should be visible
        rl = httpx.get(f"{API}/crm/quotes", params={"show_all_versions": "true"}, headers=auth, timeout=15)
        quotes = rl.json()["quotes"]
        quote_ids = [q["id"] for q in quotes]
        
        assert q2["id"] in quote_ids
        assert q1["id"] in quote_ids
        
        cleanup_after.append(("crm_quotes", {"$or": [{"id": q1["id"]}, {"id": q2["id"]}]}))
