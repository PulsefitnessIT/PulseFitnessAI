"""Iter 220 P1 — Data Quality dashboard tests for the CRM Master Price List.

Endpoints under test (router prefix /api/crm/price-list, registered in
/app/backend/route_registry/crm.py):
  - GET /quality
  - GET /quality/list?issue=...
  - GET /quality/report.csv?issue=...
"""
import csv
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASS = "MasterAdmin123!"

ALL_ISSUES = {
    "missing_sage", "missing_sell", "missing_cost", "no_category", "low_margin",
    "cost_gt_sell", "duplicate_sku", "obsolete", "never_quoted",
    "with_unmapped", "recently_changed",
}


# ---- Auth ----
@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, "no token field in login response"
    return tok


@pytest.fixture(scope="module")
def auth_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# ---- /quality dashboard ----
def test_quality_dashboard_shape(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality",
                     headers=auth_headers, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    # Top-level keys
    for k in ("total", "archived", "margin_threshold", "counts", "labels",
              "by_category", "health_score", "blocked_count"):
        assert k in data, f"missing key {k}"
    # 11 issue keys, all present in counts + labels
    assert set(data["labels"].keys()) == ALL_ISSUES
    assert set(data["counts"].keys()) == ALL_ISSUES
    # Types
    assert isinstance(data["total"], int) and data["total"] >= 0
    assert isinstance(data["archived"], int) and data["archived"] >= 0
    assert isinstance(data["health_score"], int) and 0 <= data["health_score"] <= 100
    assert isinstance(data["blocked_count"], int) and data["blocked_count"] >= 0
    assert isinstance(data["margin_threshold"], (int, float))
    assert isinstance(data["by_category"], list)
    if data["by_category"]:
        c0 = data["by_category"][0]
        for k in ("category", "count", "avg_margin", "total_sell"):
            assert k in c0


# ---- /quality/list drill-downs ----
@pytest.mark.parametrize("issue", ["missing_sage", "never_quoted", "with_unmapped", "recently_changed"])
def test_quality_list_drilldown(auth_headers, issue):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality/list",
                     headers=auth_headers, params={"issue": issue, "limit": 50}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["issue"] == issue
    assert "label" in data and data["label"]
    assert isinstance(data["total"], int) and data["total"] >= 0
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 50
    # margin_percent is computed on each item
    for it in data["items"]:
        assert "margin_percent" in it
        assert "id" in it


def test_quality_list_unknown_issue_returns_422(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality/list",
                     headers=auth_headers, params={"issue": "totally_not_real"}, timeout=30)
    assert r.status_code == 422, f"got {r.status_code}: {r.text[:200]}"


def test_quality_requires_auth():
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality", timeout=30)
    assert r.status_code in (401, 403), r.status_code


# ---- /quality/report.csv ----
def test_quality_report_csv_attachment(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality/report.csv",
                     headers=auth_headers, params={"issue": "missing_cost"}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct, ct
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd and ".csv" in cd, cd
    # Decode (utf-8-sig because backend writes BOM)
    text = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows, "csv empty"
    header = rows[0]
    assert header == ["Product Code", "Name", "Category", "Sage Code",
                      "Cost Price", "Sell Price", "Margin %", "Status"], header


def test_quality_report_csv_unknown_issue_422(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/quality/report.csv",
                     headers=auth_headers, params={"issue": "nope"}, timeout=30)
    assert r.status_code == 422
