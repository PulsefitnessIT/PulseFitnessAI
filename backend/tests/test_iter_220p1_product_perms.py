"""Iter 220 P1 — Product cost/margin field-level security.

Secure by default: restricted roles (sales_rep) never see product cost/margin
unless an admin grants their role cost visibility.

Endpoints under test:
  - GET  /api/crm/product-perms/me
  - GET/PUT /api/crm/product-perms        (admin only)
  - GET  /api/crm/products                (redacted for restricted)
  - GET  /api/crm/price-list/quality      (403 for restricted)
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL, ADMIN_PASS = "admin@gymaxisai.com", "MasterAdmin123!"
SALES_EMAIL, SALES_PASS = "sales.rep.test@gymaxisai.com", "SalesRep123!"
COST_FIELDS = ("cost_price", "markup_percent", "trade_price", "list_price",
               "retail_price", "installation_cost", "delivery_cost", "discount", "margin")


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/crm/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_h():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def sales_h():
    # The restricted sales_rep user is seeded by the main agent in the admin's org.
    try:
        return _login(SALES_EMAIL, SALES_PASS)
    except AssertionError:
        pytest.skip("sales.rep.test user not seeded")


@pytest.fixture(autouse=True)
def _reset_grant(admin_h):
    # Ensure sales_rep starts WITHOUT a grant for each test.
    requests.put(f"{BASE_URL}/api/crm/product-perms",
                 json={"role": "sales_rep", "can_see_cost": False}, headers=admin_h, timeout=30)
    yield
    requests.put(f"{BASE_URL}/api/crm/product-perms",
                 json={"role": "sales_rep", "can_see_cost": False}, headers=admin_h, timeout=30)


def test_admin_sees_cost(admin_h):
    assert requests.get(f"{BASE_URL}/api/crm/product-perms/me", headers=admin_h, timeout=30).json()["can_see_cost"] is True
    r = requests.get(f"{BASE_URL}/api/crm/products?limit=1", headers=admin_h, timeout=30)
    p = r.json()["products"][0]
    assert "cost_price" in p and "markup_percent" in p


def test_sales_cost_hidden_by_default(sales_h):
    assert requests.get(f"{BASE_URL}/api/crm/product-perms/me", headers=sales_h, timeout=30).json()["can_see_cost"] is False
    p = requests.get(f"{BASE_URL}/api/crm/products?limit=1", headers=sales_h, timeout=30).json()["products"][0]
    for f in COST_FIELDS:
        assert f not in p, f"cost field {f} leaked to sales_rep"
    assert "sell_price" in p  # sell price stays visible


def test_sales_quality_dashboard_403(sales_h):
    assert requests.get(f"{BASE_URL}/api/crm/price-list/quality", headers=sales_h, timeout=30).status_code == 403
    assert requests.get(f"{BASE_URL}/api/crm/price-list/quality/list?issue=missing_sage", headers=sales_h, timeout=30).status_code == 403
    assert requests.get(f"{BASE_URL}/api/crm/price-list/quality/report.csv?issue=missing_sage", headers=sales_h, timeout=30).status_code == 403


def test_admin_grant_then_sales_sees_cost(admin_h, sales_h):
    requests.put(f"{BASE_URL}/api/crm/product-perms",
                 json={"role": "sales_rep", "can_see_cost": True}, headers=admin_h, timeout=30)
    assert requests.get(f"{BASE_URL}/api/crm/product-perms/me", headers=sales_h, timeout=30).json()["can_see_cost"] is True
    p = requests.get(f"{BASE_URL}/api/crm/products?limit=1", headers=sales_h, timeout=30).json()["products"][0]
    assert "cost_price" in p
    assert requests.get(f"{BASE_URL}/api/crm/price-list/quality", headers=sales_h, timeout=30).status_code == 200


def test_cannot_grant_privileged_role(admin_h):
    r = requests.put(f"{BASE_URL}/api/crm/product-perms",
                     json={"role": "manager", "can_see_cost": True}, headers=admin_h, timeout=30)
    assert r.status_code == 400


def test_sales_cannot_admin_perms(sales_h):
    assert requests.get(f"{BASE_URL}/api/crm/product-perms", headers=sales_h, timeout=30).status_code == 403
    assert requests.put(f"{BASE_URL}/api/crm/product-perms",
                        json={"role": "rep", "can_see_cost": True}, headers=sales_h, timeout=30).status_code == 403
