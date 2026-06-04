"""Iter 220 P1 — AI support enhancements for the CRM Master Price List.

Endpoints under test (registered in /app/backend/route_registry/crm.py):
  - POST /api/crm/products/{id}/ai-clean-description
  - POST /api/crm/price-list/import/ai-error-summary
  - GET  /api/crm/price-list/ai-bundle-suggestions

These hit the real Emergent LLM key, so they are tolerant of transient
503s (AI unavailable) but assert the contract/shape when the call lands.
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASS = "MasterAdmin123!"


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, "no token field in login response"
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def a_product_id(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/products?limit=1", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    items = r.json().get("products") or []
    if not items:
        pytest.skip("no products in this org to test against")
    return items[0]["id"]


# ---- 1. clean description ----
def test_clean_description_preserves_and_fixes_grammar(auth_headers, a_product_id):
    bad = "this is a high qualty treadmil,its got  bluetooth console and is grate for gyms"
    r = requests.post(f"{BASE_URL}/api/crm/products/{a_product_id}/ai-clean-description",
                      json={"description": bad}, headers=auth_headers, timeout=60)
    if r.status_code == 503:
        pytest.skip("AI temporarily unavailable")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["original"] == bad
    assert isinstance(body["suggestion"], str) and body["suggestion"].strip()
    # grammar-only: the cleaned text should still mention the core nouns
    low = body["suggestion"].lower()
    assert "treadmill" in low and "bluetooth" in low


def test_clean_description_empty_is_422(auth_headers, a_product_id):
    r = requests.post(f"{BASE_URL}/api/crm/products/{a_product_id}/ai-clean-description",
                      json={"description": "   "}, headers=auth_headers, timeout=30)
    assert r.status_code == 422


def test_clean_description_unknown_product_404(auth_headers):
    r = requests.post(f"{BASE_URL}/api/crm/products/does-not-exist/ai-clean-description",
                      json={"description": "hello"}, headers=auth_headers, timeout=30)
    assert r.status_code == 404


# ---- 2. import error summary ----
def test_error_summary_shape(auth_headers):
    preview = {
        "total": 120, "ready": 100, "warnings": 12, "errors": 8,
        "missing_name": 4, "duplicates_in_file": 3, "cost_gt_sell": 2,
        "issues": [
            {"row": 5, "sheet": "Main Gym", "level": "error", "msg": "Missing product code"},
            {"row": 12, "sheet": "Main Gym", "code": "AB1", "level": "warning", "msg": "cost > sell"},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/ai-error-summary",
                      json={"preview": preview}, headers=auth_headers, timeout=60)
    if r.status_code == 503:
        pytest.skip("AI temporarily unavailable")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert isinstance(body.get("summary"), str) and body["summary"].strip()
    assert isinstance(body.get("flagged"), list) and len(body["flagged"]) <= 8
    assert isinstance(body.get("next_steps"), list) and len(body["next_steps"]) <= 4


def test_error_summary_clean_preview_is_ok(auth_headers):
    preview = {"total": 50, "ready": 50, "warnings": 0, "errors": 0, "issues": []}
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/ai-error-summary",
                      json={"preview": preview}, headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.json().get("severity") == "ok"


def test_error_summary_requires_preview(auth_headers):
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/ai-error-summary",
                      json={}, headers=auth_headers, timeout=30)
    assert r.status_code == 422


# ---- 3. bundle suggestions ----
def test_bundle_suggestions_shape(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/ai-bundle-suggestions",
                     headers=auth_headers, timeout=90)
    if r.status_code == 503:
        pytest.skip("AI temporarily unavailable")
    if r.status_code == 422:
        pytest.skip("fewer than 3 products in org")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert isinstance(body.get("suggestions"), list)
    for s in body["suggestions"]:
        assert s["name"]
        assert len(s["components"]) >= 2  # only valid, real product ids survive
        assert s["total_sell_price"] == round(sum(c["sell_price"] for c in s["components"]), 2)
