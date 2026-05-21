"""Iter 216h269 — Quote builder bundle auto-expansion (P2).

Closes the loop on iter 216h267 (CRM Product Bundles). The bundle
schema + `/expand` endpoint shipped in h267, but reps still had
to type each component manually when raising a quote. This iter
wires up the **client-side** expansion:

* Quote builder loads the master price list when the modal opens.
* "Add from catalogue" picker lists every active product, with a
  Bundle badge on `is_bundle: true` rows.
* Picking a bundle calls `GET /crm/products/{id}/expand` and
  appends one line per component, hydrated with the current
  `cost_price`, `sell_price`, and bundle provenance
  (`from_bundle_id`, `from_bundle_name`).
* New **Margin badge** in the totals strip — colour-coded
  (green ≥30%, amber ≥15%, red <15%) — only renders when at
  least one line carries a `cost_price`.

All work is in the frontend (`CRMCPQ.js`); the backend bundle
schema + expand endpoint from h267 stays unchanged.
"""
from __future__ import annotations

import pathlib
import re


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


def _cpq() -> str:
    return _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCPQ.js"
    ).read_text())


# ─── 1. Product picker UI ───────────────────────────────────────────


def test_quote_builder_has_add_from_catalogue_button():
    src = _cpq()
    assert 'data-testid="quote-add-from-catalogue-btn"' in src
    assert 'Add from catalogue' in src


def test_quote_builder_loads_products_when_modal_opens():
    src = _cpq()
    # Lookup pre-load now includes the products endpoint
    assert "/crm/products?active=true" in src
    # Stored in `products` state via setProducts
    assert "setProducts(" in src


def test_quote_builder_picker_renders_bundle_badge():
    src = _cpq()
    # When the picker row is a bundle, show a Bundle pill
    assert 'data-testid={`quote-product-bundle-badge-${p.id}`}' in src
    assert "is_bundle" in src
    # Picker exposes a search input for SKU / name / category
    assert 'data-testid="quote-product-search"' in src
    assert 'data-testid="quote-product-picker"' in src


def test_quote_builder_picker_filters_by_name_sku_category():
    """The search filter has to be case-insensitive across multiple
    fields — reps don't always remember the exact product name."""
    src = _cpq()
    assert "(p.name || '').toLowerCase().includes(q)" in src
    assert "(p.sku || '').toLowerCase().includes(q)" in src
    assert "(p.category || '').toLowerCase().includes(q)" in src


# ─── 2. Bundle expansion ────────────────────────────────────────────


def test_quote_builder_calls_expand_endpoint_for_bundles():
    src = _cpq()
    assert "/crm/products/${p.id}/expand" in src or "/crm/products/${p.id}/expand`" in src


def test_quote_builder_appends_one_line_per_component():
    """The expand endpoint returns `items[]`; the handler maps over
    those items and appends them as quote lines."""
    src = _cpq()
    # maps over the returned items
    assert "components.map" in src or ".items || [])" in src
    # provenance fields persisted on each line
    assert "from_bundle_id" in src
    assert "from_bundle_name" in src
    # current prices carry through
    assert "cost_price: Number(item.cost_price)" in src or "cost_price: Number(item.cost_price) || 0" in src
    assert "unit_price: Number(item.sell_price)" in src or "unit_price: Number(item.sell_price) || 0" in src


def test_quote_builder_non_bundle_appends_single_line():
    """Picking a non-bundle product should NOT call /expand."""
    src = _cpq()
    # Branching logic on the is_bundle flag
    assert "if (!p.is_bundle)" in src
    # Direct push of a single line carrying product_id + cost_price
    assert "product_id: p.id" in src
    assert "cost_price: Number(p.cost_price)" in src or "cost_price: Number(p.cost_price) || 0" in src


def test_bundle_line_description_includes_provenance():
    """When a bundle explodes, each line's description should hint
    at the bundle source so the rep can see the lineage."""
    src = _cpq()
    # Description template includes "from {bundle name}" suffix
    assert "from ${item.from_bundle_name}" in src


# ─── 3. Margin badge ────────────────────────────────────────────────


def test_quote_builder_renders_margin_badge():
    src = _cpq()
    assert 'data-testid="quote-margin-badge"' in src
    # Margin maths uses cost_price * quantity, and sell_price * quantity * (1-discount/100)
    assert "totalCost" in src and "sellOfCosted" in src
    # Colour bands: green ≥ 30, amber ≥ 15, red < 15
    assert "marginPercent >= 30" in src
    assert "marginPercent >= 15" in src


def test_margin_badge_only_renders_when_costed_lines_exist():
    """If the rep typed every line manually (no `cost_price`), the
    badge should hide — meaningless to show 0% margin on manual lines."""
    src = _cpq()
    assert "hasCostedLines" in src
    assert "totalCost > 0" in src


# ─── 4. Backwards compatibility ─────────────────────────────────────


def test_existing_add_line_button_still_works():
    """The legacy "+ Add line" affordance must still be reachable so
    reps can drop in one-off services that aren't in the catalogue."""
    src = _cpq()
    assert 'data-testid="quote-add-line-btn"' in src
    # Function reference unchanged
    assert "onClick={addLine}" in src


def test_quote_builder_does_not_force_product_id_on_manual_lines():
    """Manual lines must NOT carry product_id / cost_price so the
    backend stores them as free-text items (existing schema)."""
    src = _cpq()
    # The legacy addLine() pushes a line WITHOUT product_id / cost_price
    addline_block = src.split("const addLine = () =>")[1].split("};")[0]
    assert "product_id" not in addline_block
    assert "cost_price" not in addline_block


# ─── 5. Backend stability ───────────────────────────────────────────


def test_backend_quote_lines_round_trip_new_fields():
    """The backend stores lines verbatim — assert it still passes
    `lines` through to the persisted doc, so the new fields the
    frontend adds (`product_id`, `cost_price`, `from_bundle_id`,
    `from_bundle_name`) are preserved on the quote doc."""
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    create_block = src.split('@router.post("/quotes")')[1].split('@router')[0]
    # The body assigns the lines list directly onto the quote doc
    assert '"lines": lines' in create_block
