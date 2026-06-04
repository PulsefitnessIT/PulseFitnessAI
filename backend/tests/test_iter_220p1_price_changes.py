"""Iter 220 P1 — price-change computation unit tests."""
from routes.crm_price_changes import _new_value
from routes.crm_products import _calc_markup


def test_pct_uplift():
    assert _new_value(100, 60, "pct", 10, "sell_price") == 110.0
    assert _new_value(100, 60, "pct", -5, "sell_price") == 95.0


def test_fixed_uplift():
    assert _new_value(100, 60, "fixed", 25, "cost_price") == 125.0


def test_set_value():
    assert _new_value(100, 60, "set", 250, "sell_price") == 250.0


def test_margin_mode_sets_sell_from_cost():
    # 40% margin on sell, cost 60 → sell = 60 / (1 - 0.40) = 100.0
    assert _new_value(0, 60, "margin", 40, "sell_price") == 100.0
    # margin only valid for sell_price with a cost
    assert _new_value(0, 60, "margin", 40, "cost_price") is None
    assert _new_value(0, 0, "margin", 40, "sell_price") is None
    assert _new_value(0, 60, "margin", 100, "sell_price") is None


def test_calc_markup_roundtrip():
    # sell 100 cost 60 → markup = (100-60)/60 = 66.67%
    assert round(_calc_markup(60, 100), 1) == 66.7
