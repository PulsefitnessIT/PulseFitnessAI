"""Iter 270 — Partner approval email localized to the engineer's market.

The "You're approved" email previously hard-coded GBP pricing (£30 / £3 per
site) and UK compliance docs (DBS / Right-to-Work), regardless of where the
engineer signed up. These tests confirm the email now reflects the engineer's
country: USD/EUR pricing and the correct compliance doc set.
"""
import asyncio

import pytest

import utils.partner_emails as pe


def _render(country_code):
    captured = {}

    async def fake_send(*a, **k):
        captured["subject"] = k.get("subject")
        captured["html"] = k.get("html")
        return True

    orig = pe._send_email
    pe._send_email = fake_send
    try:
        asyncio.run(pe.send_application_approved(
            "x@example.com", "Test Engineer", "REF123",
            activation_token="tok", country_code=country_code,
        ))
    finally:
        pe._send_email = orig
    return captured["html"]


def test_us_email_is_usd_and_us_compliance():
    html = _render("US")
    assert "$39.99" in html and "$3/site" in html
    assert "I-9" in html and "background check" in html
    assert "£30" not in html and "DBS" not in html


def test_eur_email_is_euro():
    html = _render("IE")
    assert "€39.99" in html and "€3/site" in html
    assert "Garda" in html
    assert "£30" not in html


def test_gb_email_unchanged_gbp_and_dbs():
    html = _render("GB")
    assert "£30" in html and "£3/site" in html
    assert "DBS" in html and "Right-to-Work" in html


def test_missing_country_defaults_to_gb():
    html = _render(None)
    assert "£30" in html and "DBS" in html
