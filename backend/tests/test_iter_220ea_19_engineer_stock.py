"""Iter 220ea·19 — Engineer App Phase 5: Stock Control hub (read layer).

Live HTTP smoke + contract tests for the engineer-scoped stock
endpoints added in ``routes/svc/engineer_stock.py``. These build on the
existing parts collections (svc_parts / svc_van_stock /
svc_part_movements) — we only assert the read/aggregation contract and
the cost-visibility gate, never duplicate-record behaviour.

All requests use the master-admin token (which passes
``require_engineer_app_access``). Tests skip gracefully if the token is
unavailable (e.g. rate-limited).
"""
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_van_endpoint_shape(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token (rate limited?)")
    r = requests.get(f"{BASE}/api/svc/engineer/stock/van", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert "summary" in body
    for k in ("lines", "low", "zero", "value_sell"):
        assert k in body["summary"], f"missing summary.{k}"
    # Master admin is an owner/admin → cost visible.
    assert body["show_cost"] is True


def test_van_filters_and_sort_accept(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    for f in ("all", "low", "zero", "most_used", "recent"):
        r = requests.get(f"{BASE}/api/svc/engineer/stock/van",
                         params={"filter": f}, headers=_h(token), timeout=20)
        assert r.status_code == 200, f"filter={f} → {r.status_code}"
    for s in ("name", "qty", "most_used", "recent"):
        r = requests.get(f"{BASE}/api/svc/engineer/stock/van",
                         params={"sort": s}, headers=_h(token), timeout=20)
        assert r.status_code == 200, f"sort={s} → {r.status_code}"


def test_low_endpoint_shape(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    r = requests.get(f"{BASE}/api/svc/engineer/stock/low", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body and "count" in body
    for row in body["rows"]:
        assert row["qty"] <= row["min_qty"]
        assert row["suggested_qty"] >= 1


def test_history_endpoint_paged(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    r = requests.get(f"{BASE}/api/svc/engineer/stock/history",
                     params={"limit": 10}, headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "next_cursor" in body
    assert len(body["items"]) <= 10


def test_asset_endpoint_requires_target(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    # No machine target → empty, never an error.
    r = requests.get(f"{BASE}/api/svc/engineer/stock/asset", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0 and body["total_qty"] == 0


def test_stock_endpoints_require_auth():
    r = requests.get(f"{BASE}/api/svc/engineer/stock/van", timeout=20)
    assert r.status_code in (401, 403)


def test_van_replenish_validates_qty(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    # qty must be > 0.
    r = requests.post(f"{BASE}/api/svc/engineer/stock/replenish",
                      json={"part_sku": "TEST-NEG", "qty": 0},
                      headers=_h(token), timeout=20)
    assert r.status_code == 422, r.text
    # bad urgency rejected.
    r = requests.post(f"{BASE}/api/svc/engineer/stock/replenish",
                      json={"part_sku": "TEST-X", "qty": 1, "urgency": "whenever"},
                      headers=_h(token), timeout=20)
    assert r.status_code == 422, r.text
