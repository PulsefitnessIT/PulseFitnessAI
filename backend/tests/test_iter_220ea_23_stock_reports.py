"""Iter 220ea·23 — Stock Phase 5: reports (CSV/PDF) + min/max reorder levels.

Live HTTP tests for the reorder report + weekly/monthly stock report
endpoints (incl. CSV + PDF exports) on ``routes/svc/admin_stock.py``,
plus source guards for the min/max reorder fields (catalogue + import)
and the Reports tab UI.
"""
from pathlib import Path

import pytest
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
BACKEND = Path(__file__).resolve().parents[1]


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def _need(token):
    if not token:
        pytest.skip("no master admin token (rate limited?)")


# ───────────────────────── reorder report ─────────────────────────

def test_reorder_report_shape(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/reorder-report",
                     params={"location": "warehouse"}, headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert isinstance(b["items"], list)
    for k in ("parts", "suggested_units"):
        assert k in b["totals"]


def test_reorder_report_van_requires_engineer(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/reorder-report",
                     params={"location": "van"}, headers=_h(token), timeout=20)
    assert r.status_code == 400, r.text


def test_reorder_report_csv(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/reorder-report.csv",
                     params={"location": "warehouse"}, headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Suggested order" in r.text.splitlines()[0]


# ───────────────────────── stock report ───────────────────────────

def test_stock_report_shape(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/report",
                     params={"location": "warehouse", "period": "week"},
                     headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["period"] == "week"
    assert "snapshot" in b and "movements" in b
    for k in ("lines", "units", "below_min", "out", "value_sell"):
        assert k in b["snapshot"]


def test_stock_report_csv(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/report.csv",
                     params={"location": "warehouse"}, headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Max" in r.text.splitlines()[0]


def test_stock_report_pdf(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/admin/stock/report.pdf",
                     params={"location": "warehouse", "period": "month"},
                     headers=_h(token), timeout=40)
    assert r.status_code == 200, r.text
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:5] == b"%PDF-"


# ─────────────────── min/max source guards ────────────────────────

def test_catalogue_and_import_support_reorder_max():
    cat = (BACKEND / "routes" / "svc" / "parts_catalogue.py").read_text()
    imp = (BACKEND / "routes" / "svc" / "parts_import.py").read_text()
    assert "reorder_max" in cat  # editable + int field
    assert "reorder_max" in imp  # canonical + numeric + commit mapping


def test_admin_stock_computes_reorder_suggestion():
    src = (BACKEND / "routes" / "svc" / "admin_stock.py").read_text()
    assert "_reorder_suggestion" in src
    assert "suggested_order" in src
    assert "_build_report_pdf" in src


# ─────────────────── frontend source guards ───────────────────────

def test_catalogue_edit_drawer_has_max_field():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "PartsCatalogue.js").read_text()
    assert "edit-max" in src
    assert "reorder_max" in src


def test_admin_stock_has_reports_tab_and_exports():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "AdminStock.js").read_text()
    assert "admin-stock-reports" in src
    assert "reports-export-stock-csv" in src
    assert "reports-export-reorder-csv" in src
    assert "reports-export-pdf" in src
    assert "report.pdf" in src
