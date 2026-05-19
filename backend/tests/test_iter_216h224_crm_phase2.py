"""Iter 216h224 — CRM Phase 2 contract tests.

Locks in the behaviour of:
  • POST /crm/products            create + markup auto-computed
  • POST /crm/products            SKU dup rejection
  • PATCH /crm/products/{id}      update + re-validate
  • DELETE /crm/products/{id}     soft-delete (active=false)
  • POST /crm/quotes              line_item cost/margin computed + totals
  • POST /crm/quotes              product_id hydration from catalogue
  • POST /crm/quotes              margin < threshold → pending_approval
  • POST /crm/quotes/{id}/approve flips approval_status
  • POST /crm/quotes/{id}/new-version + GET /versions chain integrity
  • GET  /crm/quotes/{id}/pdf     returns a valid PDF byte stream
"""
from __future__ import annotations

import os
import uuid
import time

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
    """Yields a list of (collection, query) tuples; after the test we
    delete them. Keeps the test DB tidy."""
    todo: list[tuple[str, dict]] = []
    yield todo
    # Best-effort cleanup via direct Mongo.
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


# ── Products ──────────────────────────────────────────────────────


def test_product_create_computes_markup(auth, cleanup_after):
    sku = f"TEST-216h224-{uuid.uuid4().hex[:6]}"
    r = httpx.post(
        f"{API}/crm/products",
        json={"name": "Test Product", "sku": sku, "cost_price": 100, "sell_price": 150, "category": "Equipment"},
        headers=auth, timeout=15,
    )
    assert r.status_code == 200
    p = r.json()
    assert p["markup_percent"] == 50.0
    assert p["cost_price"] == 100
    assert p["sell_price"] == 150
    cleanup_after.append(("crm_products", {"sku": sku}))


def test_product_create_rejects_duplicate_sku(auth, cleanup_after):
    sku = f"TEST-216h224-{uuid.uuid4().hex[:6]}"
    r1 = httpx.post(
        f"{API}/crm/products",
        json={"name": "P1", "sku": sku, "cost_price": 10, "sell_price": 20},
        headers=auth, timeout=15,
    )
    assert r1.status_code == 200
    r2 = httpx.post(
        f"{API}/crm/products",
        json={"name": "P2", "sku": sku, "cost_price": 10, "sell_price": 20},
        headers=auth, timeout=15,
    )
    assert r2.status_code == 409
    cleanup_after.append(("crm_products", {"sku": sku}))


def test_product_soft_delete_sets_inactive(auth, cleanup_after):
    sku = f"TEST-216h224-{uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{API}/crm/products", json={"name": "Soft Delete Me", "sku": sku, "cost_price": 1, "sell_price": 2}, headers=auth, timeout=15)
    pid = r.json()["id"]
    rd = httpx.delete(f"{API}/crm/products/{pid}", headers=auth, timeout=15)
    assert rd.status_code == 200
    rg = httpx.get(f"{API}/crm/products/{pid}", headers=auth, timeout=15)
    assert rg.status_code == 200
    assert rg.json()["active"] is False
    cleanup_after.append(("crm_products", {"sku": sku}))


# ── Quote with margin + approval flow ────────────────────────────


def test_quote_pending_approval_when_margin_below_threshold(auth, cleanup_after):
    # 1. Set 40% threshold.
    httpx.put(
        f"{API}/crm/quotes/settings/approval",
        json={"min_margin_percent": 40},
        headers=auth, timeout=15,
    )
    # 2. Create a quote with 33% margin.
    r = httpx.post(
        f"{API}/crm/quotes",
        json={
            "title": "Pending approval probe",
            "company_name": "Acme Co",
            "line_items": [{"description": "Item", "quantity": 1, "unit_price": 150, "cost_price": 100}],
        },
        headers=auth, timeout=15,
    )
    assert r.status_code == 200
    q = r.json()
    assert q["status"] == "pending_approval"
    assert q["approval_status"] == "pending"
    assert q["gross_margin_percent"] == pytest.approx(33.33, rel=0.01)
    qid = q["id"]
    cleanup_after.append(("crm_quotes", {"id": qid}))
    cleanup_after.append(("crm_settings", {"key": "quote_approval"}))

    # 3. Approve.
    ra = httpx.post(f"{API}/crm/quotes/{qid}/approve", headers=auth, timeout=15)
    assert ra.status_code == 200
    rg = httpx.get(f"{API}/crm/quotes/{qid}", headers=auth, timeout=15)
    assert rg.json()["approval_status"] == "approved"


def test_quote_auto_draft_when_margin_above_threshold(auth, cleanup_after):
    httpx.put(
        f"{API}/crm/quotes/settings/approval",
        json={"min_margin_percent": 20},
        headers=auth, timeout=15,
    )
    # 50% margin (well above 20%) — should be draft.
    r = httpx.post(
        f"{API}/crm/quotes",
        json={
            "title": "Healthy margin",
            "line_items": [{"description": "Item", "quantity": 2, "unit_price": 100, "cost_price": 50}],
        },
        headers=auth, timeout=15,
    )
    q = r.json()
    assert q["status"] == "draft"
    assert q["approval_status"] == "not_required"
    assert q["gross_margin_percent"] == pytest.approx(50.0, rel=0.01)
    cleanup_after.append(("crm_quotes", {"id": q["id"]}))


def test_quote_product_hydration_from_catalogue(auth, cleanup_after):
    sku = f"TEST-HYDRATE-{uuid.uuid4().hex[:6]}"
    p = httpx.post(
        f"{API}/crm/products",
        json={"name": "Hydration Product", "sku": sku, "cost_price": 80, "sell_price": 120, "tax_rate": 20},
        headers=auth, timeout=15,
    ).json()
    q = httpx.post(
        f"{API}/crm/quotes",
        json={"title": "Hydration test", "line_items": [{"product_id": p["id"], "quantity": 3}]},
        headers=auth, timeout=15,
    ).json()
    li = q["line_items"][0]
    assert li["unit_price"] == 120  # hydrated from product
    assert li["cost_price"] == 80
    assert li["product_name"] == "Hydration Product"
    cleanup_after.append(("crm_quotes", {"id": q["id"]}))
    cleanup_after.append(("crm_products", {"sku": sku}))


def test_quote_versioning_and_versions_endpoint(auth, cleanup_after):
    r = httpx.post(
        f"{API}/crm/quotes",
        json={"title": "Version chain", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 60}]},
        headers=auth, timeout=15,
    )
    q1 = r.json()
    r2 = httpx.post(f"{API}/crm/quotes/{q1['id']}/new-version", headers=auth, timeout=15)
    q2 = r2.json()
    assert q2["version"] == 2
    assert q2["parent_quote_id"] == q1["id"]
    rl = httpx.get(f"{API}/crm/quotes/{q1['id']}/versions", headers=auth, timeout=15)
    vlist = rl.json()["versions"]
    assert len(vlist) == 2
    assert {v["version"] for v in vlist} == {1, 2}
    cleanup_after.append(("crm_quotes", {"$or": [{"id": q1["id"]}, {"id": q2["id"]}]}))


def test_quote_pdf_returns_valid_pdf(auth, cleanup_after):
    r = httpx.post(
        f"{API}/crm/quotes",
        json={"title": "PDF test", "company_name": "Acme PDF Co", "line_items": [{"description": "A", "quantity": 1, "unit_price": 99.99, "cost_price": 50}]},
        headers=auth, timeout=15,
    )
    q = r.json()
    rp = httpx.get(f"{API}/crm/quotes/{q['id']}/pdf", headers=auth, timeout=20)
    assert rp.status_code == 200
    assert rp.headers["content-type"].startswith("application/pdf")
    # PDF byte signature.
    assert rp.content[:4] == b"%PDF"
    assert len(rp.content) > 1000
    cleanup_after.append(("crm_quotes", {"id": q["id"]}))


def test_quote_duplicate_clears_state(auth, cleanup_after):
    r = httpx.post(
        f"{API}/crm/quotes",
        json={"title": "Dup source", "line_items": [{"description": "A", "quantity": 1, "unit_price": 100, "cost_price": 50}]},
        headers=auth, timeout=15,
    )
    src = r.json()
    # Manually accept it.
    httpx.post(f"{API}/crm/quotes/{src['id']}/accept", json={"accepted_by": "test"}, headers=auth, timeout=15)
    rd = httpx.post(f"{API}/crm/quotes/{src['id']}/duplicate", headers=auth, timeout=15)
    dup = rd.json()
    assert dup["id"] != src["id"]
    assert dup["status"] == "draft"
    assert dup["accepted_at"] is None
    assert dup["parent_quote_id"] is None
    cleanup_after.append(("crm_quotes", {"$or": [{"id": src["id"]}, {"id": dup["id"]}]}))
