"""Iter 220 P1 — quote → Sage export prep unit tests."""
from routes.crm_quote_sage import vat_code, _margin_pct, _build_sage_lines


def test_vat_code_mapping():
    assert vat_code(20) == "T1"
    assert vat_code(0) == "T0"
    assert vat_code(5) == "T5"
    assert vat_code(12) == "T2"   # anything else → exempt fallback
    assert vat_code(None) == "T2"


def test_margin_pct():
    assert _margin_pct(60, 100) == 40.0    # margin on sell
    assert _margin_pct(0, 0) == 0.0
    assert _margin_pct(50, 0) == 0.0


def test_build_sage_lines_uses_codes_and_net():
    quote = {
        "vat_rate": 20,
        "lines": [
            {"sku": "AAA", "sage_code": "S-AAA", "description": "Tread", "quantity": 2, "unit_price": 100, "discount": 0, "tax_rate": 20},
            {"sku": "BBB", "sage_code": "S-BBB", "description": "Bike", "quantity": 1, "unit_price": 200, "discount": 10, "tax_rate": 0},
        ],
    }
    lines = _build_sage_lines(quote, default_nominal="4000")
    assert lines[0]["sage_item_code"] == "S-AAA"
    assert lines[0]["net_amount"] == 200.0
    assert lines[0]["vat_code"] == "T1"
    assert lines[0]["nominal_code"] == "4000"
    # 10% discount on 200 → 180 net; tax_rate 0 → T0
    assert lines[1]["net_amount"] == 180.0
    assert lines[1]["vat_code"] == "T0"


def test_build_sage_lines_line_nominal_override():
    quote = {"vat_rate": 20, "lines": [{"sku": "X", "sage_code": "S-X", "description": "d", "quantity": 1, "unit_price": 10, "nominal_code": "4100"}]}
    lines = _build_sage_lines(quote, default_nominal="4000")
    assert lines[0]["nominal_code"] == "4100"
