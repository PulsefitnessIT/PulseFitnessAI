"""Iter 220y — outbound email category → verified sending domain routing.

Each email category ships from the matching verified Resend domain:
  billing  → billing.gymaxisai.com
  support  → support.gymaxisai.com
  service  → service.gymaxisai.com
  (default/unknown) → the configured root SENDER_EMAIL
"""
from utils.email import (
    _bare_addr,
    _category_for_kind,
    _category_sender,
    SENDER_EMAIL,
)


def test_bare_addr_extracts_email():
    assert _bare_addr("GymAxis Billing <billing@billing.gymaxisai.com>") == "billing@billing.gymaxisai.com"
    assert _bare_addr("plain@gymaxisai.com") == "plain@gymaxisai.com"


def test_category_sender_uses_verified_subdomains():
    assert "billing@billing.gymaxisai.com" in _category_sender("billing")
    assert "support@support.gymaxisai.com" in _category_sender("support")
    assert "service@service.gymaxisai.com" in _category_sender("service")


def test_category_sender_default_falls_back_to_root():
    assert _category_sender(None) == SENDER_EMAIL
    assert _category_sender("marketing") == SENDER_EMAIL  # unknown → root


def test_category_sender_lowercases_domain():
    # even if an env override has mixed case, the domain is normalised.
    sender = _category_sender("billing")
    domain = _bare_addr(sender).split("@", 1)[1]
    assert domain == domain.lower()


def test_kind_to_category_mapping():
    assert _category_for_kind("engineer.invoice_paid") == "billing"
    assert _category_for_kind("billing.receipt") == "billing"
    assert _category_for_kind("payment.failed") == "billing"
    assert _category_for_kind("service.report_ready") == "service"
    assert _category_for_kind("engineer.eta_update") == "service"
    assert _category_for_kind("auth.password_reset") == "support"
    assert _category_for_kind("account.welcome") == "support"
    assert _category_for_kind(None) is None
    assert _category_for_kind("marketing.newsletter") is None
