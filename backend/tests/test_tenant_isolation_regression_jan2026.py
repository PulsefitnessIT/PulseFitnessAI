"""Tenant-isolation regression guard (2026-08-01).

Locks in the cross-tenant boundaries hardened during the founder compliance
review so a future feature cannot silently reopen a leak:

  1. MOD Quote Writer is Pulse-operator-only — any other org (CRM) gets 403 on
     every /crm/mod-quote/* endpoint. (GDPR incident fixed 2026-07-31.)
  2. Supplier Insights is a Pro/Full feature — Lite orgs get 403.
  3. Lite orgs cannot add suppliers (403); the locked Pulse Fitness Ltd default
     supplier cannot be edited or deleted (403).

Run:  cd /app/backend && REACT_APP_BACKEND_URL=<url> python -m pytest tests/test_tenant_isolation_regression_jan2026.py -q
"""
import os
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

# Non-operator CRM tenant (must NOT see MOD data)
CRM_NONOP_EMAIL = "owner@isodemo.com"
CRM_NONOP_PASS = "IsoDemo123!"
# Platform logins
PRO_EMAIL, PRO_PASS = "owner@isodemo.com", "IsoDemo123!"          # account_type=full
LITE_EMAIL, LITE_PASS = "lite.suptest@pulsedemo.test", "LiteSup123!"
# Operator / platform admin (password may rotate — positive check is best-effort)
MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASS = os.environ.get("MASTER_ADMIN_PASSWORD", "C2s9yJ3YAhydB4d34-Bykg")

MOD_QUOTE_ENDPOINTS = ["mod-sites", "equipment?site_id=x", "rate-card", "contracts"]


def _crm_login(email, password):
    r = requests.post(f"{BASE}/api/crm/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    return r.json().get("token", "") if r.status_code == 200 else ""


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    return r.json().get("token", "") if r.status_code == 200 else ""


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ── 1. MOD Quote Writer: non-operator org is denied everywhere ──
def test_mod_quote_denied_for_non_operator_crm_user():
    tok = _crm_login(CRM_NONOP_EMAIL, CRM_NONOP_PASS)
    assert tok, "CRM login for non-operator tenant failed"
    for ep in MOD_QUOTE_ENDPOINTS:
        r = requests.get(f"{BASE}/api/crm/mod-quote/{ep}", headers=_h(tok), timeout=30)
        assert r.status_code == 403, f"/crm/mod-quote/{ep} must be 403 for non-operator, got {r.status_code}"
    r = requests.post(f"{BASE}/api/crm/mod-quote/generate", headers=_h(tok),
                      json={"contract_type": "A"}, timeout=30)
    assert r.status_code == 403, f"generate must be 403 for non-operator, got {r.status_code}"


def test_mod_quote_allowed_for_operator():
    """Best-effort positive check — skips if the master password has rotated."""
    tok = _crm_login(MASTER_EMAIL, MASTER_PASS)
    if not tok:
        import pytest
        pytest.skip("operator/master-admin login unavailable (password rotated?)")
    r = requests.get(f"{BASE}/api/crm/mod-quote/mod-sites", headers=_h(tok), timeout=30)
    assert r.status_code == 200, f"operator must get 200 on mod-sites, got {r.status_code}"


# ── 2. Supplier Insights: Pro/Full only ──
def test_supplier_insights_denied_for_lite():
    tok = _login(LITE_EMAIL, LITE_PASS)
    assert tok, "Lite login failed"
    for path in ("/api/suppliers/insights", "/api/suppliers/insights/faults?unassigned=true"):
        r = requests.get(f"{BASE}{path}", headers=_h(tok), timeout=30)
        assert r.status_code == 403, f"{path} must be 403 for Lite, got {r.status_code}"


def test_supplier_insights_allowed_for_pro():
    tok = _login(PRO_EMAIL, PRO_PASS)
    assert tok, "Pro login failed"
    r = requests.get(f"{BASE}/api/suppliers/insights", headers=_h(tok), timeout=30)
    assert r.status_code == 200, f"Pro must get 200 on insights, got {r.status_code}"


# ── 3. Suppliers: Lite cannot add; default supplier is locked ──
def test_lite_cannot_add_supplier():
    tok = _login(LITE_EMAIL, LITE_PASS)
    assert tok, "Lite login failed"
    r = requests.post(f"{BASE}/api/suppliers", headers=_h(tok),
                      json={"name": "Nope", "send_welcome": False}, timeout=30)
    assert r.status_code == 403, f"Lite add-supplier must be 403, got {r.status_code}"


def test_default_pulse_supplier_is_locked():
    tok = _login(PRO_EMAIL, PRO_PASS)
    assert tok, "Pro login failed"
    r = requests.get(f"{BASE}/api/suppliers", headers=_h(tok), timeout=30)
    assert r.status_code == 200
    suppliers = r.json().get("suppliers", [])
    default = next((s for s in suppliers if s.get("is_default_pulse")), None)
    assert default, "Pulse Fitness Ltd default supplier missing"
    assert default.get("name") == "Pulse Fitness Ltd"
    sid = default["id"]
    r_put = requests.put(f"{BASE}/api/suppliers/{sid}", headers=_h(tok),
                         json={"email": "x@x.com"}, timeout=30)
    assert r_put.status_code == 403, f"editing default must be 403, got {r_put.status_code}"
    r_del = requests.delete(f"{BASE}/api/suppliers/{sid}", headers=_h(tok), timeout=30)
    assert r_del.status_code == 403, f"deleting default must be 403, got {r_del.status_code}"
