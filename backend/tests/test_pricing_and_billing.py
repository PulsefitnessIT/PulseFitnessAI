"""Pricing engine + per-org manual billing regression tests."""
import requests
import os
import sys

# Add backend to path for conftest imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers, TOTTENHAM_GREEN_ORG_ID


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


# ── Pricing engine ──────────────────────────────────────────────────


def test_seed_defaults_idempotent(master_admin_token_session):
    base = _test_backend_url()
    r1 = requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    assert r1.status_code == 200
    # Second call must be idempotent (created either 0 or fewer than the first).
    r2 = requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    assert r2.status_code == 200
    assert r2.json()["created"] == 0


def test_list_plans_returns_both_brands(master_admin_token_session):
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    rg = requests.get(f"{base}/api/master-admin/pricing?brand=gymaxis", headers=_h(master_admin_token_session), timeout=10)
    rp = requests.get(f"{base}/api/master-admin/pricing?brand=pulse", headers=_h(master_admin_token_session), timeout=10)
    assert rg.status_code == 200 and rp.status_code == 200
    g_ids = {p["module_id"] for p in rg.json()["plans"]}
    p_ids = {p["module_id"] for p in rp.json()["plans"]}
    expected = {"operations", "memberships", "crm", "marketing", "bundle_all"}
    assert expected.issubset(g_ids)
    assert expected.issubset(p_ids)


def test_public_pricing_returns_calculated_quotes_with_volume_discount(master_admin_token_session):
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    # 1 site → 0% off
    r1 = requests.get(f"{base}/api/pricing/public?brand=gymaxis&currency=GBP&sites=1", timeout=10)
    assert r1.status_code == 200
    op_1 = next(p for p in r1.json()["plans"] if p["module_id"] == "operations")
    assert op_1["quote_monthly"]["discount_pct"] == 0
    base_total = op_1["quote_monthly"]["total_amount"]
    # 4 sites → 10% off
    r4 = requests.get(f"{base}/api/pricing/public?brand=gymaxis&currency=GBP&sites=4", timeout=10)
    op_4 = next(p for p in r4.json()["plans"] if p["module_id"] == "operations")
    assert op_4["quote_monthly"]["discount_pct"] == 10
    assert op_4["quote_monthly"]["total_amount"] < base_total


def test_public_pricing_currency_switch(master_admin_token_session):
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    r_gbp = requests.get(f"{base}/api/pricing/public?brand=gymaxis&currency=GBP&sites=1", timeout=10)
    r_eur = requests.get(f"{base}/api/pricing/public?brand=gymaxis&currency=EUR&sites=1", timeout=10)
    r_usd = requests.get(f"{base}/api/pricing/public?brand=gymaxis&currency=USD&sites=1", timeout=10)
    assert r_gbp.json()["currency"] == "GBP"
    assert r_eur.json()["currency"] == "EUR"
    assert r_usd.json()["currency"] == "USD"


def test_update_plan_writes_audit_log(master_admin_token_session):
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    plans = requests.get(f"{base}/api/master-admin/pricing?brand=gymaxis", headers=_h(master_admin_token_session), timeout=10).json()["plans"]
    target = next(p for p in plans if p["module_id"] == "marketing")
    new_price = (target["prices"]["GBP"]["monthly"] or 0) + 100
    r = requests.put(
        f"{base}/api/master-admin/pricing/{target['id']}",
        json={"prices": {"GBP": {"monthly": new_price, "annual": target["prices"]["GBP"]["annual"]}}},
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["plan"]["prices"]["GBP"]["monthly"] == new_price
    audit = requests.get(f"{base}/api/master-admin/pricing/audit?plan_id={target['id']}", headers=_h(master_admin_token_session), timeout=10)
    assert audit.status_code == 200
    entries = audit.json()["entries"]
    assert any(e["action"] == "update" and e["plan_id"] == target["id"] for e in entries)


def test_unauthenticated_can_read_public_endpoint():
    base = _test_backend_url()
    r = requests.get(f"{base}/api/pricing/public?brand=gymaxis", timeout=10)
    # Public endpoint must succeed without auth.
    assert r.status_code == 200


# ── Org billing ────────────────────────────────────────────────────


def test_activate_subscription_for_org(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/activate",
        json={
            "active_modules": ["operations", "memberships"],
            "billing_cycle": "monthly",
            "billing_currency": "GBP",
            "sites": 2,
            "manual_billing": True,
            "status": "active",
        },
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r.status_code == 200
    sub = r.json()["subscription"]
    assert sub["active_modules"] == ["operations", "memberships"]
    assert sub["sites"] == 2


def test_invoice_lifecycle_with_manual_payment(master_admin_token_session):
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    # Activate subscription first
    requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/activate",
        json={
            "active_modules": ["crm"],
            "billing_cycle": "monthly",
            "billing_currency": "GBP",
            "sites": 1,
            "manual_billing": True,
            "status": "active",
        },
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    # Generate invoice
    r_inv = requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/invoice",
        json={},
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r_inv.status_code == 200
    inv = r_inv.json()["invoice"]
    assert inv["status"] == "issued"
    assert inv["total"] > 0

    # Record full payment
    r_pay = requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/payment",
        json={
            "invoice_id": inv["id"],
            "amount": inv["total"],
            "currency": inv["currency"],
            "method": "bacs",
            "reference": "TEST-PAY",
        },
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r_pay.status_code == 200

    # Summary should now show paid + balance 0
    r_sum = requests.get(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r_sum.status_code == 200
    body = r_sum.json()
    paid_inv = next((i for i in body["invoices"] if i["id"] == inv["id"]), None)
    assert paid_inv is not None and paid_inv["status"] == "paid"


def test_invoice_pdf_returns_bytes(master_admin_token_session):
    base = _test_backend_url()
    # Make sure there's at least one invoice for the org
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/activate",
        json={"active_modules": ["operations"], "billing_cycle": "monthly", "billing_currency": "GBP", "sites": 1, "manual_billing": True, "status": "active"},
        headers=_h(master_admin_token_session), timeout=10,
    )
    r_inv = requests.post(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/invoice",
        json={}, headers=_h(master_admin_token_session), timeout=10,
    )
    inv_id = r_inv.json()["invoice"]["id"]
    r_pdf = requests.get(
        f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing/invoice/{inv_id}/pdf",
        headers=_h(master_admin_token_session), timeout=10,
    )
    assert r_pdf.status_code == 200
    assert r_pdf.headers.get("content-type", "").startswith("application/pdf")
    assert r_pdf.content[:4] == b"%PDF"


def test_partial_price_update_preserves_other_currencies(master_admin_token_session):
    """Updating only GBP must NOT wipe EUR / USD to zero."""
    base = _test_backend_url()
    requests.post(f"{base}/api/master-admin/pricing/seed-defaults", headers=_h(master_admin_token_session), timeout=10)
    plans = requests.get(f"{base}/api/master-admin/pricing?brand=pulse", headers=_h(master_admin_token_session), timeout=10).json()["plans"]
    target = next(p for p in plans if p["module_id"] == "operations")
    eur_before = target["prices"]["EUR"]["monthly"]
    usd_before = target["prices"]["USD"]["monthly"]
    assert eur_before > 0 and usd_before > 0, "seed should have populated EUR and USD"
    # Send a partial PUT — only GBP.
    new_gbp = target["prices"]["GBP"]["monthly"] + 250
    r = requests.put(
        f"{base}/api/master-admin/pricing/{target['id']}",
        json={"prices": {"GBP": {"monthly": new_gbp, "annual": target["prices"]["GBP"]["annual"]}}},
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r.status_code == 200
    saved = r.json()["plan"]
    assert saved["prices"]["GBP"]["monthly"] == new_gbp
    assert saved["prices"]["EUR"]["monthly"] == eur_before, "EUR price was wiped by GBP-only update"
    assert saved["prices"]["USD"]["monthly"] == usd_before, "USD price was wiped by GBP-only update"


def test_non_master_admin_cannot_access(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/pricing", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403
    r = requests.get(f"{base}/api/master-admin/orgs/{TOTTENHAM_GREEN_ORG_ID}/billing", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403
