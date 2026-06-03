"""Iter 220x — membership member payments route to the gym's connected
Stripe account (destination charge + platform fee), with platform fallback.

Unit-level guards for the pure routing helpers (no Stripe calls).
"""
from utils.stripe_connect_routing import (
    payment_intent_connect_kwargs,
    subscription_connect_kwargs,
)


def test_payment_fragment_none_routing_is_empty():
    assert payment_intent_connect_kwargs(None, 5000) == {}
    assert subscription_connect_kwargs(None) == {}


def test_payment_fragment_destination_and_fee():
    routing = {"destination": "acct_123", "fee_pct": 1.0}
    frag = payment_intent_connect_kwargs(routing, 10000)  # £100.00
    assert frag["transfer_data"] == {"destination": "acct_123"}
    assert frag["application_fee_amount"] == 100  # 1% of 10000 pence


def test_payment_fee_capped_below_amount():
    routing = {"destination": "acct_123", "fee_pct": 100.0}
    frag = payment_intent_connect_kwargs(routing, 5000)
    # Fee must be < amount so Stripe doesn't reject it.
    assert frag["application_fee_amount"] == 4999


def test_zero_fee_omits_application_fee():
    routing = {"destination": "acct_123", "fee_pct": 0}
    frag = payment_intent_connect_kwargs(routing, 5000)
    assert "application_fee_amount" not in frag
    assert frag["transfer_data"] == {"destination": "acct_123"}


def test_subscription_fragment_uses_percent():
    routing = {"destination": "acct_xyz", "fee_pct": 1.5}
    frag = subscription_connect_kwargs(routing)
    assert frag["transfer_data"] == {"destination": "acct_xyz"}
    assert frag["application_fee_percent"] == 1.5
