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
