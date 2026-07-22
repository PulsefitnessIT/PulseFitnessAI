"""Iter 220ea·34 — Programmatic equipment-type (category) landing pages.

The category axis (/equipment/{type}) that complements the manufacturer
axis (/maintenance/{brand}). Data-driven from manufacturer_catalogue +
spec_sheets with curated faults/PM-task editorial; gated on a minimum
real-machine count so thin types 404 (no doorway pages).
"""
from __future__ import annotations

import os
import pathlib

import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://platform-doctor.preview.emergentagent.com").rstrip("/")
FRONT = pathlib.Path("/app/frontend/src/pages/Marketing/Landing")


# ─── Backend constants ──────────────────────────────────────────────

def test_equipment_types_catalogue_shape():
    from routes.seo_public import EQUIPMENT_TYPES, EQUIPMENT_MIN_PRODUCTS
    assert EQUIPMENT_MIN_PRODUCTS >= 4
    assert len(EQUIPMENT_TYPES) >= 6
    slugs = {t["slug"] for t in EQUIPMENT_TYPES}
    assert {"treadmill", "exercise-bike", "rowing-machine", "strength-machine"} <= slugs
    for t in EQUIPMENT_TYPES:
        for k in ("slug", "name", "plural", "term", "match", "intro", "faults", "tasks"):
            assert t.get(k), f"{t.get('slug')} missing {k}"
        assert len(t["faults"]) >= 3 and len(t["tasks"]) >= 3


# ─── Live endpoints ─────────────────────────────────────────────────

def test_landing_equipment_list_live():
    r = requests.get(f"{BASE}/api/seo/landing/equipment", timeout=30)
    assert r.status_code == 200
    items = r.json()["equipment"]
    assert isinstance(items, list) and len(items) >= 1  # at least one qualifying type
    for it in items:
        assert it["product_count"] >= 6
        for k in ("slug", "name", "plural", "term", "brands"):
            assert k in it


def test_qualifying_equipment_detail_live():
    # Take the first qualifying type from the list and assert a rich detail.
    lst = requests.get(f"{BASE}/api/seo/landing/equipment", timeout=30).json()["equipment"]
    assert lst, "no qualifying equipment types — catalogue may be empty"
    slug = lst[0]["slug"]
    d = requests.get(f"{BASE}/api/seo/landing/equipment/{slug}", timeout=30).json()
    assert d["slug"] == slug
    assert d["product_count"] >= 6
    assert len(d["products"]) >= 6
    assert len(d["faults"]) >= 3 and len(d["tasks"]) >= 3
    assert all(p.get("image_url") for p in d["products"])
    assert d.get("brands")


def test_unknown_equipment_slug_404():
    r = requests.get(f"{BASE}/api/seo/landing/equipment/not-a-real-type-xyz", timeout=30)
    assert r.status_code == 404


def test_thin_equipment_type_404():
    """A defined type that has fewer than the minimum real machines must
    404 (no thin/doorway pages) — find one not in the live qualifying list."""
    from routes.seo_public import EQUIPMENT_TYPES
    qualifying = {it["slug"] for it in requests.get(f"{BASE}/api/seo/landing/equipment", timeout=30).json()["equipment"]}
    thin = [t["slug"] for t in EQUIPMENT_TYPES if t["slug"] not in qualifying]
    if not thin:  # every defined type qualified — nothing to assert
        return
    r = requests.get(f"{BASE}/api/seo/landing/equipment/{thin[0]}", timeout=30)
    assert r.status_code == 404


def test_sitemap_includes_equipment():
    r = requests.get(f"{BASE}/api/seo/sitemap.xml", timeout=30)
    assert r.status_code == 200
    assert "/equipment" in r.text


# ─── Frontend wiring guards ─────────────────────────────────────────

def test_equipment_landing_component():
    src = (FRONT / "EquipmentLanding.js").read_text()
    for tid in ("equipment-faults", "equipment-tasks", "equipment-products", "equipment-brands"):
        assert f'data-testid="{tid}"' in src, f"missing {tid}"
    assert "/api/seo/landing/equipment/" in src
    assert "FAQPage" in src and "BreadcrumbList" in src and "Service" in src


def test_equipment_index_component():
    src = (FRONT / "EquipmentIndex.js").read_text()
    assert 'data-testid="equipment-index"' in src
    assert "/api/seo/landing/equipment" in src
    assert "/maintenance" in src  # cross-link to brand axis


def test_routes_and_footer_wired():
    routes = pathlib.Path("/app/frontend/src/routes/AppRoutes.js").read_text()
    assert "EquipmentIndex" in routes and "EquipmentLanding" in routes
    assert '"/equipment"' in routes and '"/equipment/:slug"' in routes
    shell = pathlib.Path("/app/frontend/src/pages/Marketing/MarketingShell.js").read_text()
    assert 'to="/equipment"' in shell
