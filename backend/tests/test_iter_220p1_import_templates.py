"""Iter 220 P1 — reusable mapping templates for recurring price-list imports.

Endpoints:
  - GET    /api/crm/price-list/import-templates
  - POST   /api/crm/price-list/import-templates   (upsert by name)
  - DELETE /api/crm/price-list/import-templates/{id}
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL, ADMIN_PASS = "admin@gymaxisai.com", "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_template_crud_and_upsert(admin_h):
    name = f"pytest-tmpl-{uuid.uuid4().hex[:8]}"
    base = f"{BASE_URL}/api/crm/price-list/import-templates"
    try:
        # save
        r = requests.post(base, headers=admin_h, json={
            "name": name,
            "sheets": [{"name": "Sheet1", "mappings": {"1": "sku", "2": "name", "3": "cost_price"},
                        "header_row": 1, "code_col": 1, "name_col": 2}],
        }, timeout=30)
        assert r.status_code == 200, r.text[:200]
        t = r.json()["template"]
        assert t["name"] == name and len(t["sheets"]) == 1
        assert t["sheets"][0]["mappings"]["3"] == "cost_price"
        tid = t["id"]

        # appears in list
        lst = requests.get(base, headers=admin_h, timeout=30).json()["templates"]
        assert any(x["id"] == tid for x in lst)

        # upsert by name updates in place (no duplicate)
        r2 = requests.post(base, headers=admin_h, json={
            "name": name, "sheets": [{"name": "Sheet1", "mappings": {"1": "sku", "2": "name"}}],
        }, timeout=30)
        assert r2.status_code == 200
        lst2 = requests.get(base, headers=admin_h, timeout=30).json()["templates"]
        assert sum(1 for x in lst2 if x["name"] == name) == 1
        again = next(x for x in lst2 if x["name"] == name)
        assert "3" not in again["sheets"][0]["mappings"]  # cost_price removed by re-save
    finally:
        # cleanup (find current id by name in case upsert changed nothing)
        lst = requests.get(base, headers=admin_h, timeout=30).json()["templates"]
        for x in [x for x in lst if x["name"] == name]:
            requests.delete(f"{base}/{x['id']}", headers=admin_h, timeout=30)


def test_template_requires_name(admin_h):
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import-templates",
                      headers=admin_h, json={"sheets": [{"name": "S", "mappings": {"1": "sku"}}]}, timeout=30)
    assert r.status_code == 400


def test_template_requires_sheets(admin_h):
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import-templates",
                      headers=admin_h, json={"name": "empty-tmpl", "sheets": []}, timeout=30)
    assert r.status_code == 400


def test_delete_unknown_template_404(admin_h):
    r = requests.delete(f"{BASE_URL}/api/crm/price-list/import-templates/nope", headers=admin_h, timeout=30)
    assert r.status_code == 404
