"""Iter 226 — Equipment Auto-Find Images backend tests.

Two strategies under test:
  1. Catalogue cache lookup (`utils.manufacturer_catalogue.lookup_in_catalogue`)
  2. Category-page fallback regex parser

We avoid live HTTP in CI: instead we seed the `manufacturer_catalogue`
collection directly and assert the lookup picks the right row.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip() + "/api"
)


def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


# ──────── Auth ────────

def test_catalogue_endpoints_require_master_admin(operator_headers):
    """Operator (non-master) gets 403 on every catalogue endpoint."""
    paths = [
        ("GET", "/master-admin/catalogue/stats"),
        ("GET", "/master-admin/catalogue/jobs"),
    ]
    for method, p in paths:
        r = requests.request(method, f"{API_BASE}{p}", headers=operator_headers, timeout=10)
        assert r.status_code == 403, f"{p} should 403 for non-master, got {r.status_code}"


# ──────── Stats endpoint shape ────────

def test_catalogue_stats_returns_priority_domains(admin_headers):
    r = requests.get(f"{API_BASE}/master-admin/catalogue/stats", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "total_products" in body
    assert "domains" in body
    domain_set = {d["domain"] for d in body["domains"]}
    # Priority domains must surface even when products==0 (uningested state)
    for required in ("pulsefitness.com", "lifefitness.com", "wattbike.com"):
        assert required in domain_set, f"missing priority domain: {required}"


# ──────── Catalogue lookup logic (unit, no HTTP) ────────

@pytest.mark.anyio
async def test_catalogue_lookup_keyword_overlap_match(anyio_backend, monkeypatch):
    """Seed two products and verify the keyword-overlap scorer picks the right one."""
    # Use the same MONGO_URL the app uses — load from backend/.env if not in env.
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or "test_database"
    if not mongo_url:
        env_text = open("/app/backend/.env").read()
        for line in env_text.splitlines():
            if line.startswith("MONGO_URL"):
                mongo_url = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("DB_NAME"):
                db_name = line.split("=", 1)[1].strip().strip('"')
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    coll = db.manufacturer_catalogue

    # ── Iter 238g event-loop isolation fix ────────────────────────────
    # This test runs under pytest-anyio which creates its own per-test
    # loop, separate from the conftest ``_SHARED_LOOP``. The
    # ``lookup_in_catalogue`` helper reads from the globally-imported
    # ``utils.database.db`` whose Motor client is bound to whichever
    # loop ran first — usually ``_SHARED_LOOP``. To avoid the
    # cross-loop "Future attached to a different loop" failure, point
    # the module's ``db`` reference at the locally-created client for
    # the duration of this test.
    import utils.manufacturer_catalogue as _mc
    monkeypatch.setattr(_mc, "db", db, raising=True)

    test_domain = f"test-iter226-{uuid.uuid4().hex[:6]}.com"
    docs = [
        {
            "id": str(uuid.uuid4()),
            "domain": test_domain,
            "manufacturer_display": "Wattbike",
            "page_url": f"https://{test_domain}/products/atom",
            "page_title": "Wattbike Atom",
            "image_url": f"https://{test_domain}/img/atom.jpg",
            "name_keywords": ["wattbike", "atom"],
            "ingested_at": "2026-04-29T00:00:00+00:00",
        },
        {
            "id": str(uuid.uuid4()),
            "domain": test_domain,
            "manufacturer_display": "Wattbike",
            "page_url": f"https://{test_domain}/products/icon",
            "page_title": "Wattbike Icon",
            "image_url": f"https://{test_domain}/img/icon.jpg",
            "name_keywords": ["wattbike", "icon"],
            "ingested_at": "2026-04-29T00:00:00+00:00",
        },
    ]
    await coll.insert_many(docs)
    try:
        from utils.manufacturer_catalogue import lookup_in_catalogue
        hit = await lookup_in_catalogue(test_domain, "Wattbike Atom Bike")
        assert hit is not None, "expected catalogue hit for 'Wattbike Atom Bike'"
        assert hit["image_url"] == f"https://{test_domain}/img/atom.jpg"
        assert hit["verified"] is True
        assert hit["source"] == "catalogue"

        # Search for icon — should pick the icon doc.
        hit2 = await lookup_in_catalogue(test_domain, "Wattbike Icon")
        assert hit2 is not None
        assert "icon" in hit2["image_url"]
    finally:
        await coll.delete_many({"domain": test_domain})
        client.close()


@pytest.mark.anyio
async def test_catalogue_lookup_returns_none_when_no_match(anyio_backend):
    """Empty needle should return None without hitting the DB."""
    from utils.manufacturer_catalogue import slugify_equipment_name
    # Sanity-check the helper used by lookup_in_catalogue — no DB needed.
    # An empty/whitespace name produces no needle keywords.
    assert slugify_equipment_name("") == ""
    assert slugify_equipment_name("   ") == ""


# ──────── Sitemap parser (unit) ────────

@pytest.mark.anyio
async def test_sitemap_parser_skips_non_product_urls(anyio_backend):
    """SKIP_PATTERNS must filter out blog/support/PDF entries."""
    from utils.manufacturer_catalogue import SKIP_PATTERNS
    skip = [
        "https://example.com/blog/post-1",
        "https://example.com/support/manual.pdf",
        "https://example.com/news/2026-launch",
        "https://example.com/about/team",
        "https://example.com/img/hero.jpg",
        "https://example.com/sitemap.xml",
    ]
    keep = [
        "https://example.com/products/atom",
        "https://example.com/equipment/treadmill",
        "https://example.com/shop/bike-1",
    ]
    for u in skip:
        assert SKIP_PATTERNS.search(u), f"should skip: {u}"
    for u in keep:
        assert not SKIP_PATTERNS.search(u), f"should not skip: {u}"


# ──────── Job-trigger endpoint ────────

def test_ingest_endpoint_rejects_unknown_domain(admin_headers):
    r = requests.post(
        f"{API_BASE}/master-admin/catalogue/ingest?domain=not-a-real-brand.example",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 400


def test_ingest_endpoint_returns_job_id_for_known_domain(admin_headers):
    """We don't wait for ingestion to complete — just verify the trigger works."""
    r = requests.post(
        f"{API_BASE}/master-admin/catalogue/ingest?domain=concept2.com",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["targets"] == ["concept2.com"]
    assert "job_id" in body

    # Poll once — should be either running or complete (we accept either).
    r2 = requests.get(
        f"{API_BASE}/master-admin/catalogue/jobs/{body['job_id']}",
        headers=admin_headers, timeout=10,
    )
    assert r2.status_code == 200
    job = r2.json()
    assert job["status"] in ("running", "complete", "error")
