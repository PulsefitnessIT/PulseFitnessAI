"""Iter 220p1 — Org localization foundation (USA readiness, slice 1).

Covers:
- utils.localization: defaults to GB, resolves US, currency formatting.
- GET/PUT /api/org/localization (master admin): default GB, set US, validation,
  tz override, then revert to GB so the shared admin org isn't left as US.
- Engineer invoice payload snapshots currency + tax vocabulary from the market.
"""
import os
import uuid

import pytest
import requests

from conftest import _test_backend_url, MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD

BASE_URL = _test_backend_url()


def _bypass():
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")
    if not s:
        try:
            with open("/app/backend/.env", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                        s = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            pass
    return {"X-RateLimit-Bypass": s} if s else {}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
                      headers=_bypass(), timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


# ── utils.localization ────────────────────────────────────────────

def test_org_localization_defaults_to_gb():
    from utils.localization import org_localization
    loc = org_localization(None)
    assert loc["country_code"] == "GB"
    assert loc["currency"] == "GBP"
    assert loc["currency_symbol"] == "£"
    assert loc["tax_label"] == "VAT"
    assert loc["default_tax_rate"] == 20.0


def test_org_localization_resolves_us():
    from utils.localization import org_localization
    loc = org_localization({"country_code": "US"})
    assert loc["currency"] == "USD"
    assert loc["currency_symbol"] == "$"
    assert loc["tax_label"] == "Sales Tax"
    assert loc["default_tax_rate"] == 0.0
    assert loc["timezone"] == "America/New_York"


def test_org_localization_currency_override():
    from utils.localization import org_localization
    loc = org_localization({"country_code": "US", "currency": "USD", "timezone": "America/Los_Angeles"})
    assert loc["timezone"] == "America/Los_Angeles"


def test_format_currency():
    from utils.localization import format_currency
    assert format_currency(1234.5, "USD") == "$1,234.50"
    assert format_currency(1234.5, "GBP") == "£1,234.50"


# ── endpoint ──────────────────────────────────────────────────────

def test_get_localization_default(admin_token):
    r = requests.get(f"{BASE_URL}/api/org/localization",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["can_edit"] is True
    codes = {c["code"] for c in body["supported_countries"]}
    assert {"GB", "US"}.issubset(codes)


def test_companies_house_region_gated(admin_token):
    """Companies House is UK-only: a US org gets region_supported=False,
    a UK org gets region_supported=True. Always reverts to GB."""
    h = {"Authorization": f"Bearer {admin_token}"}
    try:
        requests.put(f"{BASE_URL}/api/org/localization", json={"country_code": "US"},
                     headers=h, timeout=30)
        r = requests.get(f"{BASE_URL}/api/account/companies-house/status",
                         headers=h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["region_supported"] is False
        assert r.json()["enabled"] is False  # UK-only registry off for US
    finally:
        requests.put(f"{BASE_URL}/api/org/localization", json={"country_code": "GB"},
                     headers=h, timeout=30)
    r = requests.get(f"{BASE_URL}/api/account/companies-house/status",
                     headers=h, timeout=30)
    assert r.json()["region_supported"] is True



def test_set_localization_us_then_revert(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.put(f"{BASE_URL}/api/org/localization", json={"country_code": "US"},
                         headers=h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        loc = r.json()["localization"]
        assert loc["currency"] == "USD" and loc["tax_label"] == "Sales Tax"
        # bad country / currency
        assert requests.put(f"{BASE_URL}/api/org/localization", json={"country_code": "ZZ"},
                            headers=h, timeout=30).status_code == 400
        assert requests.put(f"{BASE_URL}/api/org/localization", json={"currency": "XYZ"},
                            headers=h, timeout=30).status_code == 400
    finally:
        # Always revert so the shared admin org stays UK for other suites.
        rv = requests.put(f"{BASE_URL}/api/org/localization", json={"country_code": "GB"},
                          headers=h, timeout=30)
        assert rv.status_code == 200
        assert rv.json()["localization"]["country_code"] == "GB"


# ── engineer invoice payload snapshot ─────────────────────────────

def test_invoice_payload_snapshots_us_market():
    from datetime import datetime, timezone
    from routes.svc.engineer_invoices import _build_invoice_payload
    from utils.localization import org_localization

    loc = org_localization({"country_code": "US"})
    inv = _build_invoice_payload(
        user={"organization_id": "o1", "id": "u1", "email": "e@x.com"},
        engineer={"full_name": "Eng", "email": "e@x.com", "mobile": ""},
        issue_date=datetime.now(timezone.utc),
        payment_terms_days=14,
        body={"lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 100}]},
        loc=loc,
    )
    assert inv["currency"] == "USD"
    assert inv["currency_symbol"] == "$"
    assert inv["tax_label"] == "Sales Tax"
    assert inv["country_code"] == "US"
    # No tax rate supplied → defaults to US market rate (0%), so VAT amount is 0.
    assert inv["vat_rate"] == 0.0
    assert inv["vat_amount"] == 0.0
    # US invoices don't get the UK Late Payment Act terms.
    assert "Late Payment of Commercial Debts" not in inv["terms"]
    assert inv["payment_method"] == "ACH"


def test_invoice_payload_defaults_gb():
    from datetime import datetime, timezone
    from routes.svc.engineer_invoices import _build_invoice_payload
    from utils.localization import org_localization

    inv = _build_invoice_payload(
        user={"organization_id": "o1", "id": "u1", "email": "e@x.com"},
        engineer={"full_name": "Eng", "email": "e@x.com", "mobile": ""},
        issue_date=datetime.now(timezone.utc),
        payment_terms_days=14,
        body={"lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 100}]},
        loc=org_localization(None),
    )
    assert inv["currency"] == "GBP"
    assert inv["tax_label"] == "VAT"
    assert inv["vat_rate"] == 20.0
    assert inv["vat_amount"] == 20.0  # 20% of 100
    assert "Late Payment of Commercial Debts" in inv["terms"]
