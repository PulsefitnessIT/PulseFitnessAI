"""Iter 265 — USA readiness for INDEPENDENT engineers.

An independent partner engineer is created org-less, so until now every
localization read fell back to GB: a US engineer's invoices rendered in £,
Stripe Connect created a UK Express account and compliance asked for DBS/RTW.

These tests cover the fixes that thread the engineer's chosen market through:
  • ``engineer_localization`` resolves the partner-record country when the
    user has no org (and the org country still wins when present).
  • The Partner Plan checkout picks the USD price for US engineers, falling
    back to the GBP price when the USD price ID isn't seeded yet.
"""
import asyncio
import types

import pytest


# ── Fake async db so engineer_localization can be unit-tested ──────────

class _FakeColl:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, *_a, **_k):
        return self._doc


class _FakeDB:
    def __init__(self, org=None, partner=None):
        self.organizations = _FakeColl(org)
        self.partner_engineers = _FakeColl(partner)


def _patch_db(monkeypatch, *, org=None, partner=None):
    import utils.database as database
    monkeypatch.setattr(database, "db", _FakeDB(org=org, partner=partner))


def test_engineer_localization_partner_market_when_orgless(monkeypatch):
    """Org-less US engineer → USD / Sales Tax from the partner record."""
    from utils.localization import engineer_localization
    _patch_db(monkeypatch, org=None, partner={"country_code": "US"})
    loc = asyncio.run(engineer_localization({"id": "eng-1", "organization_id": None}))
    assert loc["country_code"] == "US"
    assert loc["currency"] == "USD"
    assert loc["currency_symbol"] == "$"
    assert loc["tax_label"] == "Sales Tax"


def test_engineer_localization_org_country_wins(monkeypatch):
    """An explicit org country beats the partner fallback."""
    from utils.localization import engineer_localization
    _patch_db(monkeypatch, org={"country_code": "US"}, partner={"country_code": "GB"})
    loc = asyncio.run(engineer_localization({"id": "eng-2", "organization_id": "org-2"}))
    assert loc["country_code"] == "US"
    assert loc["currency"] == "USD"


def test_engineer_localization_defaults_gb(monkeypatch):
    """No org, no partner market → UK / GBP / VAT (back-compat)."""
    from utils.localization import engineer_localization
    _patch_db(monkeypatch, org=None, partner=None)
    loc = asyncio.run(engineer_localization({"id": "eng-3", "organization_id": None}))
    assert loc["country_code"] == "GB"
    assert loc["currency"] == "GBP"
    assert loc["tax_label"] == "VAT"


# ── USD Partner Plan price selection ──────────────────────────────────

def test_partner_plan_price_usd_when_set(monkeypatch):
    from routes.partners import _partner_plan_price_id_for_tier
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30", "price_gbp_30")
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30_USD", "price_usd_30")
    tier = {"price_gbp": 30}
    assert _partner_plan_price_id_for_tier(tier, "US") == "price_usd_30"
    assert _partner_plan_price_id_for_tier(tier, "GB") == "price_gbp_30"
    # No country → GBP default.
    assert _partner_plan_price_id_for_tier(tier) == "price_gbp_30"


def test_partner_plan_price_us_falls_back_to_gbp(monkeypatch):
    """US engineer but no USD price seeded → fall back to the GBP price so
    checkout never breaks (operator just hasn't created the USD price yet)."""
    from routes.partners import _partner_plan_price_id_for_tier
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30", "price_gbp_30")
    monkeypatch.delenv("STRIPE_PRICE_PARTNER_PLAN_30_USD", raising=False)
    assert _partner_plan_price_id_for_tier({"price_gbp": 30}, "US") == "price_gbp_30"


def test_partner_plan_price_free_tier_none():
    from routes.partners import _partner_plan_price_id_for_tier
    assert _partner_plan_price_id_for_tier({"price_gbp": 0}, "US") is None


def test_partner_plan_price_eur_for_european_country(monkeypatch):
    """Iter 269 — European engineers (e.g. IE → EUR) get the EUR price."""
    from routes.partners import _partner_plan_price_id_for_tier
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30", "price_gbp_30")
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30_EUR", "price_eur_30")
    tier = {"price_gbp": 30}
    assert _partner_plan_price_id_for_tier(tier, "IE") == "price_eur_30"
    # GB still GBP.
    assert _partner_plan_price_id_for_tier(tier, "GB") == "price_gbp_30"


def test_partner_plan_price_eur_falls_back_to_gbp(monkeypatch):
    from routes.partners import _partner_plan_price_id_for_tier
    monkeypatch.setenv("STRIPE_PRICE_PARTNER_PLAN_30", "price_gbp_30")
    monkeypatch.delenv("STRIPE_PRICE_PARTNER_PLAN_30_EUR", raising=False)
    assert _partner_plan_price_id_for_tier({"price_gbp": 30}, "IE") == "price_gbp_30"
