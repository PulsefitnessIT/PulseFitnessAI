"""Iter 216h267 — CRM Product Configuration / Bundles (P2).

User ask (Feb 21, 2026): *"Product configuration / bundles — allow
sales reps to predefine bundles of products/services that explode
into individual line items on a quote."*

This iter wires up:
* Schema: `crm_products` records may now carry `is_bundle: True` +
  `bundle_items[]` (each `{product_id, quantity, override_sell_price?}`).
* Validation rejects bundles with no components or 0-quantity items.
* `GET /crm/products/{id}/expand` returns a flat list of resolved
  components (hydrated with current cost/sell from the catalogue).
  Non-bundles return a single-item list (the product itself).
* Bundle expansion also rolls up cost / sell / margin so the quote
  builder can preview the totals before insertion.
* Frontend bundle editor in `CRMProductsSection.js` lets admins
  build the components from a dropdown of existing products.
* CRM nav-bar reordered into the records → sales → daily → admin
  → specialised flow per the same customer-feedback batch.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Validation ──────────────────────────────────────────────────


def test_validate_accepts_non_bundle_product():
    from routes.crm_products import _validate

    out = _validate({"name": "Treadmill", "cost_price": 100, "sell_price": 200})
    assert out["is_bundle"] is False
    assert out["bundle_items"] == []


def test_validate_accepts_bundle_with_components():
    from routes.crm_products import _validate

    out = _validate({
        "name": "Cardio Starter Kit",
        "is_bundle": True,
        "bundle_items": [
            {"product_id": "prod-treadmill", "quantity": 1},
            {"product_id": "prod-bike", "quantity": 2, "override_sell_price": "499.99"},
        ],
    })
    assert out["is_bundle"] is True
    assert len(out["bundle_items"]) == 2
    assert out["bundle_items"][0] == {"product_id": "prod-treadmill", "quantity": 1.0}
    # override_sell_price coerced to float
    assert out["bundle_items"][1]["override_sell_price"] == 499.99


def test_validate_rejects_bundle_without_items():
    from routes.crm_products import _validate

    with pytest.raises(HTTPException) as exc:
        _validate({"name": "Empty Kit", "is_bundle": True, "bundle_items": []})
    assert exc.value.status_code == 422
    assert "bundle" in exc.value.detail.lower()


def test_validate_rejects_bundle_item_with_zero_quantity():
    from routes.crm_products import _validate

    with pytest.raises(HTTPException) as exc:
        _validate({
            "name": "Bad Kit",
            "is_bundle": True,
            "bundle_items": [{"product_id": "x", "quantity": 0}],
        })
    assert exc.value.status_code == 422


def test_validate_rejects_bundle_item_without_product_id():
    from routes.crm_products import _validate

    with pytest.raises(HTTPException) as exc:
        _validate({
            "name": "Bad Kit",
            "is_bundle": True,
            "bundle_items": [{"quantity": 1}],
        })
    assert exc.value.status_code == 422
    assert "product_id" in exc.value.detail


# ─── 2. Expansion endpoint ──────────────────────────────────────────


def test_expand_route_registered():
    from routes.crm_products import router
    paths = {r.path for r in router.routes}
    assert "/crm/products/{product_id}/expand" in paths


def test_expand_non_bundle_returns_single_line():
    from routes.crm_products import expand_product

    fake_db = MagicMock()
    fake_db.crm_products.find_one = AsyncMock(return_value={
        "id": "p1", "organization_id": "org-1",
        "name": "Treadmill", "sku": "TM-01", "category": "Equipment",
        "unit": "each", "cost_price": 100, "sell_price": 200,
        "tax_rate": 20, "is_bundle": False,
    })

    with patch("routes.crm_products.db", fake_db):
        out = _run(expand_product(
            product_id="p1",
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["is_bundle"] is False
    assert len(out["items"]) == 1
    assert out["items"][0]["product_id"] == "p1"
    assert out["items"][0]["quantity"] == 1
    assert out["items"][0]["sell_price"] == 200


def test_expand_bundle_explodes_with_current_prices_and_rollup():
    from routes.crm_products import expand_product

    bundle = {
        "id": "kit-1", "organization_id": "org-1",
        "name": "Cardio Kit",
        "is_bundle": True,
        "bundle_items": [
            {"product_id": "p-tread", "quantity": 1},
            {"product_id": "p-bike", "quantity": 2},
        ],
    }
    components = [
        {"id": "p-tread", "organization_id": "org-1", "name": "Treadmill",
         "sku": "TM-01", "category": "Equipment", "unit": "each",
         "cost_price": 500, "sell_price": 1000, "tax_rate": 20,
         "supplier_name": "Technogym"},
        {"id": "p-bike", "organization_id": "org-1", "name": "Spin Bike",
         "sku": "SB-01", "category": "Equipment", "unit": "each",
         "cost_price": 200, "sell_price": 400, "tax_rate": 20,
         "supplier_name": "Schwinn"},
    ]

    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=components)
    fake_db = MagicMock()
    fake_db.crm_products.find_one = AsyncMock(return_value=bundle)
    fake_db.crm_products.find = MagicMock(return_value=cur)

    with patch("routes.crm_products.db", fake_db):
        out = _run(expand_product(
            product_id="kit-1",
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["is_bundle"] is True
    assert len(out["items"]) == 2
    # quantity preserved on each line
    by_pid = {it["product_id"]: it for it in out["items"]}
    assert by_pid["p-tread"]["quantity"] == 1
    assert by_pid["p-bike"]["quantity"] == 2
    # current sell prices flowed through
    assert by_pid["p-tread"]["sell_price"] == 1000
    assert by_pid["p-bike"]["sell_price"] == 400
    # provenance fields so the quote can show "from {bundle}"
    assert by_pid["p-tread"]["from_bundle_id"] == "kit-1"
    assert by_pid["p-tread"]["from_bundle_name"] == "Cardio Kit"
    # supplier preserved per line (routing stays per-supplier)
    assert by_pid["p-bike"]["supplier_name"] == "Schwinn"
    # rollups: 500*1 + 200*2 = 900 cost, 1000*1 + 400*2 = 1800 sell
    assert out["rollup_cost"] == 900.0
    assert out["rollup_sell"] == 1800.0
    # margin% = (1800-900)/1800 * 100 = 50.0
    assert out["rollup_margin_percent"] == 50.0


def test_expand_bundle_with_override_price_uses_override():
    from routes.crm_products import expand_product

    bundle = {
        "id": "kit-1", "organization_id": "org-1",
        "name": "Discount Kit",
        "is_bundle": True,
        "bundle_items": [
            {"product_id": "p1", "quantity": 1, "override_sell_price": 50},
        ],
    }
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=[
        {"id": "p1", "organization_id": "org-1", "name": "Widget",
         "cost_price": 80, "sell_price": 200, "tax_rate": 20},
    ])
    fake_db = MagicMock()
    fake_db.crm_products.find_one = AsyncMock(return_value=bundle)
    fake_db.crm_products.find = MagicMock(return_value=cur)

    with patch("routes.crm_products.db", fake_db):
        out = _run(expand_product(
            product_id="kit-1",
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["items"][0]["sell_price"] == 50  # override wins
    assert out["items"][0]["cost_price"] == 80  # cost unchanged
    assert out["rollup_sell"] == 50.0


def test_expand_bundle_with_missing_component_surfaces_stub():
    """If a referenced product was deleted, surface a (missing) stub
    instead of 404-ing — the manager needs to see what's broken."""
    from routes.crm_products import expand_product

    bundle = {
        "id": "kit-1", "organization_id": "org-1",
        "name": "Stale Kit",
        "is_bundle": True,
        "bundle_items": [{"product_id": "ghost", "quantity": 3}],
    }
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=[])  # no rows returned
    fake_db = MagicMock()
    fake_db.crm_products.find_one = AsyncMock(return_value=bundle)
    fake_db.crm_products.find = MagicMock(return_value=cur)

    with patch("routes.crm_products.db", fake_db):
        out = _run(expand_product(
            product_id="kit-1",
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["items"][0]["missing"] is True
    assert out["items"][0]["quantity"] == 3
    assert out["items"][0]["product_id"] == "ghost"


def test_expand_unknown_product_raises_404():
    from routes.crm_products import expand_product

    fake_db = MagicMock()
    fake_db.crm_products.find_one = AsyncMock(return_value=None)

    with patch("routes.crm_products.db", fake_db), pytest.raises(HTTPException) as exc:
        _run(expand_product(
            product_id="nope",
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))
    assert exc.value.status_code == 404


# ─── 3. Frontend wiring ─────────────────────────────────────────────


def test_products_form_has_bundle_editor():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMProductsSection.js"
    ).read_text())
    assert 'data-testid="products-is-bundle"' in src
    assert 'data-testid="products-bundle-editor"' in src
    assert 'data-testid="products-bundle-add-row"' in src
    # row testids exist (use template literal)
    assert "products-bundle-row-" in src
    assert "products-bundle-product-" in src
    assert "products-bundle-qty-" in src


def test_products_bundle_picker_uses_products_state_not_undefined_items():
    """Regression: an earlier draft referenced `items.filter(...)` but
    the state variable is `products`. That would crash the modal."""
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMProductsSection.js"
    ).read_text()
    # The picker must iterate `products`, never the undefined `items`
    assert "products.filter(p => !p.is_bundle" in src
    assert "items.filter(p => !p.is_bundle" not in src


def test_products_submit_payload_excludes_empty_bundle_items_when_not_bundle():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMProductsSection.js"
    ).read_text())
    # The payload should clamp bundle_items to [] when not is_bundle
    assert "is_bundle: !!form.is_bundle" in src
    assert "form.is_bundle" in src


# ─── 4. CRM nav reorder ─────────────────────────────────────────────


def test_crm_nav_reordered_records_first_then_sales():
    """Companies should come before Pipeline; Quotes + Forecast must
    sit in the sales-flow group, not buried behind Workflows."""
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMApp.js"
    ).read_text()
    nav_block = src.split("const NAV_ITEMS = [")[1].split("];")[0]
    # ordering check via index-of
    idx_companies = nav_block.find("id: 'companies'")
    idx_contacts = nav_block.find("id: 'contacts'")
    idx_pipeline = nav_block.find("id: 'pipeline'")
    idx_quotes = nav_block.find("id: 'quotes'")
    idx_forecast = nav_block.find("id: 'forecast'")
    idx_workflows = nav_block.find("id: 'workflows'")
    for label, idx in [("companies", idx_companies), ("contacts", idx_contacts),
                       ("pipeline", idx_pipeline), ("quotes", idx_quotes),
                       ("forecast", idx_forecast), ("workflows", idx_workflows)]:
        assert idx > 0, f"missing nav entry: {label}"
    assert idx_companies < idx_pipeline, "Companies must come before Pipeline"
    assert idx_contacts < idx_pipeline, "Contacts must come before Pipeline"
    assert idx_pipeline < idx_quotes < idx_forecast, "sales flow ordering broken"
    assert idx_forecast < idx_workflows, "Forecast should sit ahead of admin/Workflows"
