"""Iter 222 — Master Admin role is brand-aware.

Assigning "Master Admin" to a user in a Pulse org must provision a
data-scoped Pulse Master Admin (not a full platform admin). The pure
brand discriminator is unit-tested here; the full promote/demote flow is
curl-verified against the live edit endpoint.
"""
from routes.master_admin_users import _org_is_pulse


def test_pulse_account_types_are_pulse():
    for at in ("pulse_pro", "pulse_lite", "pulse"):
        assert _org_is_pulse({"account_type": at}) is True


def test_pulse_brand_values_are_pulse():
    assert _org_is_pulse({"brand": "Pulse"}) is True
    assert _org_is_pulse({"brand": "pulse_fitness"}) is True
    assert _org_is_pulse({"account_type": "full", "brand": "PULSE_FITNESS"}) is True


def test_gymaxis_orgs_are_not_pulse():
    assert _org_is_pulse({"account_type": "full"}) is False
    assert _org_is_pulse({"account_type": "starter", "brand": "gymaxis"}) is False
    assert _org_is_pulse({}) is False
    assert _org_is_pulse(None) is False
