"""Iter 220ea·22 — Stock Phase 4: Office/Admin stock overview.

Live HTTP contract tests for ``routes/svc/admin_stock.py`` plus
source-level guards for the responsive admin surface
(``AdminStock.js``). Read endpoints (overview / by-location / locations
/ cross-org) are asserted for shape; transfer is asserted on its
*validation* paths only (400 / 404 / 409) so the shared preview DB is
never mutated — the happy-path transfer + stock-take are covered by the
testing agent's UI run and manual live verification.

All requests use the master-admin token (owner/admin → can_manage +
can_cross_org). Tests skip gracefully if the token is unavailable.
"""
from pathlib import Path

import pytest
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def _need(token):
    if not token:
        pytest.skip("no master admin token (rate limited?)")


# ─────────────────────────── read contracts ───────────────────────

def test_overview_shape(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/overview", headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "warehouse" in b and "engineers" in b and "totals" in b
    assert isinstance(b["engineers"], list)
    for k in ("value_sell", "low", "zero", "engineers", "catalogue_parts"):
        assert k in b["totals"], f"missing totals.{k}"
    # master admin → cost visible + cross-org allowed
    assert b["show_cost"] is True
    assert b["can_cross_org"] is True


def test_by_location_warehouse_shape(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/by-location",
                     params={"location": "warehouse"}, headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["location"] == "warehouse"
    assert isinstance(b["items"], list)


def test_by_location_van_requires_engineer(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/by-location",
                     params={"location": "van"}, headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_locations_shape(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/locations", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b.get("warehouse") is True
    assert isinstance(b["engineers"], list)


def test_cross_org_master_admin_ok(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/cross-org", headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "organizations" in b and "totals" in b
    for k in ("orgs", "value_sell", "low", "zero"):
        assert k in b["totals"], f"missing totals.{k}"


# ───────────────────── transfer validation (no mutation) ──────────

def test_transfer_rejects_missing_part(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer",
                      json={"qty": 1, "from": {"type": "warehouse"}, "to": {"type": "warehouse"}},
                      headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_transfer_rejects_same_source_dest(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer",
                      json={"part_sku": "ANYTHING", "qty": 1,
                            "from": {"type": "warehouse"}, "to": {"type": "warehouse"}},
                      headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_transfer_unknown_part_404(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer",
                      json={"part_sku": "DEFINITELY-NOT-A-REAL-SKU-ZZZ", "qty": 1,
                            "from": {"type": "warehouse"},
                            "to": {"type": "van", "engineer_id": "someone"}},
                      headers=_h(token), timeout=20)
    assert r.status_code == 404, r.text


def test_stock_take_requires_counts(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/stock-take",
                      json={"location": "warehouse", "counts": []},
                      headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


# ───────────────── batch transfer validation (no mutation) ────────

def test_transfer_batch_requires_items(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer-batch",
                      json={"from": {"type": "warehouse"},
                            "to": {"type": "van", "engineer_id": "x"}, "items": []},
                      headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_transfer_batch_same_src_dest(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer-batch",
                      json={"from": {"type": "warehouse"}, "to": {"type": "warehouse"},
                            "items": [{"part_sku": "X", "qty": 1}]},
                      headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_transfer_batch_insufficient_returns_failures(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    # warehouse is empty in this org → any real qty from warehouse fails with
    # a structured failures list (404-for-part or 409-for-stock).
    r = requests.post(f"{BASE}/api/svc/admin/stock/transfer-batch",
                      json={"from": {"type": "warehouse"},
                            "to": {"type": "van", "engineer_id": "someone"},
                            "items": [{"part_sku": "DEFINITELY-NOT-REAL-SKU", "qty": 1}]},
                      headers=_h(token), timeout=20)
    assert r.status_code == 409, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and isinstance(detail.get("failures"), list)


def test_availability_endpoint_returns_qty_per_sku(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.post(f"{BASE}/api/svc/admin/stock/availability",
                      json={"location": "warehouse", "part_skus": ["ZZZ-NONE-1", "ZZZ-NONE-2"]},
                      headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    avail = r.json().get("availability") or {}
    # unknown skus resolve to 0 (so the cart can flag over-transfers)
    assert avail.get("ZZZ-NONE-1") == 0
    assert avail.get("ZZZ-NONE-2") == 0


def test_transfer_cart_shows_source_stock():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "AdminStock.js").read_text()
    assert "/svc/admin/stock/availability" in src
    assert "transfer-picked-avail" in src
    assert "transfer-shortfall-warning" in src
    assert "hasShortfall" in src


# ───────────────────── import stock destination ──────────────────

def test_import_commit_supports_warehouse_destination():
    """Source guard: commit honours options.stock_location warehouse/van."""
    src = (Path(__file__).resolve().parents[1] / "routes" / "svc" / "parts_import.py").read_text()
    assert "stock_location" in src
    assert "svc_warehouse_stock" in src
    assert '"location": "warehouse"' in src


# ───────────────────── frontend source guards ─────────────────────

def test_admin_stock_page_has_all_tabs():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "AdminStock.js").read_text()
    # tab testids are generated as admin-stock-tab-${t.k}
    assert "admin-stock-tab-${t.k}" in src
    for key in ("'overview'", "'transfer'", "'stocktake'", "'crossorg'"):
        assert key in src, f"missing tab key {key}"
    for tid in ("admin-stock-page", "transfer-submit", "stocktake-post",
                "admin-stock-overview", "admin-stock-transfer",
                "admin-stock-stocktake", "admin-stock-crossorg"):
        assert tid in src, f"missing {tid}"


def test_transfer_is_multi_part_cart():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "AdminStock.js").read_text()
    # multi-part cart wired to the batch endpoint
    assert "transfer-batch" in src
    assert "transfer-cart" in src
    assert "transfer-add-line" in src


def test_import_wizard_has_stock_destination_picker():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "PartsImportWizard.js").read_text()
    assert "opt-stock-location" in src
    assert "stock_location" in src
    assert "opt-target-engineer" in src


def test_admin_stock_route_and_entrypoints():
    routes = (FRONTEND / "routes" / "AppRoutes.js").read_text()
    settings = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerAccountSettings.js").read_text()
    desk = (FRONTEND / "pages" / "ServiceOps" / "ServiceDeskPage.js").read_text()
    # route lives under the /svc/engineer/* namespace (master-admin allow-listed)
    assert "/svc/engineer/stock-admin" in routes
    # reachable from both the engineer app settings and the desktop desk
    assert "engineer-settings-stock-admin-row" in settings
    assert "/svc/engineer/stock-admin" in settings
    assert "desk-stock-management" in desk
