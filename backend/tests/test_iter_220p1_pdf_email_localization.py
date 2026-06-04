"""Iter 220p1 — PDF/email currency localization (USA readiness, slice 3).

Engineer invoice/quote PDFs + emails and the service-ops report PDF must
render the org's market currency + tax label (snapshotted on the document):
  GB → £ / VAT ;  US → $ / Sales Tax.
PDF builds are smoke-tested (no crash, non-trivial bytes); the email/notify
string builders are asserted on content.
"""
import pytest

GB = {
    "currency": "GBP", "currency_symbol": "£", "tax_label": "VAT",
    "country_code": "GB", "payment_method": "BACS",
}
US = {
    "currency": "USD", "currency_symbol": "$", "tax_label": "Sales Tax",
    "country_code": "US", "payment_method": "ACH",
}


def _inv(market):
    return {
        **market,
        "invoice_number": "INV-1", "customer_name": "Acme", "engineer_name": "Eng",
        "subtotal": 100.0, "vat_rate": market["tax_label"] == "VAT" and 20 or 0,
        "vat_amount": 20.0 if market["country_code"] == "GB" else 0.0,
        "total": 120.0 if market["country_code"] == "GB" else 100.0,
        "due_date": "2026-07-01", "description_of_work": "Repair",
        "lines": [{"kind": "labour", "description": "x", "quantity": 1,
                   "unit_price": 100, "line_total": 100}],
        "terms": "Payment due within 14 days.",
    }


def _quote(market):
    return {
        **market,
        "quote_number": "EQ-1", "customer_name": "Acme", "engineer_name": "Eng",
        "subtotal": 100.0, "vat_rate": 20 if market["country_code"] == "GB" else 0,
        "vat_amount": 20.0 if market["country_code"] == "GB" else 0.0,
        "total": 120.0 if market["country_code"] == "GB" else 100.0,
        "valid_until": "2026-07-30", "description_of_work": "Repair",
        "lines": [{"kind": "labour", "description": "x", "quantity": 1,
                   "unit_price": 100, "line_total": 100}],
    }


# ── invoice email ─────────────────────────────────────────────────

def test_invoice_email_html_us():
    from routes.svc.engineer_invoices import _email_html
    html = _email_html(_inv(US))
    assert "$100.00" in html
    assert "Sales Tax" in html
    assert "ACH" in html
    assert "£" not in html


def test_invoice_email_html_gb():
    from routes.svc.engineer_invoices import _email_html
    html = _email_html(_inv(GB))
    assert "£120.00" in html
    assert "VAT" in html
    assert "$" not in html


# ── quote email ───────────────────────────────────────────────────

def test_quote_email_html_us():
    from routes.svc.engineer_quotes import _email_html
    html = _email_html(_quote(US))
    assert "$100.00" in html
    assert "Sales Tax" in html
    assert "£" not in html


def test_quote_email_html_gb():
    from routes.svc.engineer_quotes import _email_html
    html = _email_html(_quote(GB))
    assert "£120.00" in html
    assert "VAT" in html


# ── PDF smoke (no crash, real bytes) ──────────────────────────────

@pytest.mark.parametrize("market", [GB, US])
def test_invoice_pdf_builds(market):
    from utils.engineer_invoice_pdf import build_engineer_invoice_pdf
    pdf = build_engineer_invoice_pdf(_inv(market))
    assert isinstance(pdf, bytes) and len(pdf) > 1000
    assert pdf[:4] == b"%PDF"


@pytest.mark.parametrize("market", [GB, US])
def test_quote_pdf_builds(market):
    from utils.engineer_quote_pdf import build_engineer_quote_pdf
    pdf = build_engineer_quote_pdf(_quote(market))
    assert isinstance(pdf, bytes) and len(pdf) > 1000
    assert pdf[:4] == b"%PDF"


# ── CRM quote / contract PDFs (localized symbol + tax label) ──────

def _crm_quote(market):
    return {
        "quote_number": "QT-1", "company_name": "Acme Inc", "contact_name": "Jo",
        "status": "draft", "valid_until": "2026-07-30",
        "currency": market["currency"], "tax_label": market["tax_label"],
        "subtotal": 100.0, "tax_rate": 0 if market["country_code"] == "US" else 20,
        "tax_amount": 0.0 if market["country_code"] == "US" else 20.0,
        "total": 100.0 if market["country_code"] == "US" else 120.0,
        "line_items": [{"description": "Service", "quantity": 1,
                        "unit_price": 100, "discount_percent": 0, "subtotal": 100}],
    }


@pytest.mark.parametrize("market", [GB, US])
def test_crm_quote_pdf_builds(market):
    from utils.crm_quote_pdf import build_crm_quote_pdf
    org = {"name": "Acme", "primary_color": "#1D4ED8", "country_code": market["country_code"]}
    pdf = build_crm_quote_pdf(_crm_quote(market), org)
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF" and len(pdf) > 1000


@pytest.mark.parametrize("market", [GB, US])
def test_crm_contract_pdf_builds(market):
    from utils.crm_contract_pdf import build_contract_pdf
    org = {"name": "Acme", "primary_color": "#0055FF", "country_code": market["country_code"]}
    contract = {
        "contract_number": "CT-1", "tier": "premium", "title": "Service contract",
        "annual_value": 1200, "consumables": [{"name": "Belt", "included": True, "charge": 5.0}],
        "pricing": {"annual_value": 1200, "monthly_value": 100, "setup_fee": 50,
                    "vat_percent": 0 if market["country_code"] == "US" else 20},
    }
    pdf = build_contract_pdf(contract, org, {})
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_crm_quote_pdf_falls_back_to_org_currency():
    """A quote without its own currency snapshot inherits the org market."""
    from utils.crm_quote_pdf import build_crm_quote_pdf
    q = _crm_quote(US)
    q.pop("currency"); q.pop("tax_label")
    org = {"name": "Acme", "primary_color": "#1D4ED8", "country_code": "US"}
    pdf = build_crm_quote_pdf(q, org)
    assert pdf[:4] == b"%PDF"
