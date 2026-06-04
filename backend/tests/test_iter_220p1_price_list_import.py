"""Iter 220 P1 — CRM Master Price List spreadsheet migration parser.

Locks down the zero-data-loss behaviour of utils/price_list_import.py
against the real Pulse cost-engineering workbook shape.
"""
import os

import openpyxl
import pytest

from utils.price_list_import import (
    analyze_workbook, extract_products, auto_map, CANONICAL_FIELDS,
)

SAMPLE = "/app/test_samples/pulse_master_price_list_sample.xlsx"


def _make_workbook_bytes():
    """Build a tiny messy workbook mimicking the real structure:
    exchange-rate preamble + multi-row header band + section heading +
    product rows + a blank separator."""
    import io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Main Gym"
    ws["A1"] = "Exchange Rate $ to £"; ws["B1"] = 1.27
    ws["A3"] = "Pulse Fitness"
    ws["C3"] = "Units"; ws["D3"] = "Export Price"; ws["E3"] = "Cost"
    ws["C4"] = "in 40ft"; ws["D4"] = "FOB Taiwan"; ws["E4"] = "US $"
    ws["A5"] = "Product Code"; ws["B5"] = "Description"
    ws["A6"] = None; ws["B6"] = "Cardiovascular Range"   # section heading
    ws["A7"] = "260G-ABZ"; ws["B7"] = "Classic Treadmill"; ws["C7"] = 35; ws["D7"] = 4369.40; ws["E7"] = 1189.07; ws["F7"] = "spare-cable-xyz"
    ws["A8"] = "260G-ACA"; ws["B8"] = "Club Treadmill"; ws["C8"] = 35; ws["D8"] = 4635.70; ws["E8"] = 1189.07
    ws["A9"] = None  # blank separator
    ws["A10"] = "270R-AAA"; ws["B10"] = "Rower"; ws["D10"] = 2200
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


def test_analyze_detects_header_and_products():
    data = _make_workbook_bytes()
    a = analyze_workbook(data)
    assert len(a["sheets"]) == 1
    s = a["sheets"][0]
    assert s["name"] == "Main Gym"
    assert s["header_row"] == 5
    assert s["code_col"] == 1
    # 3 product rows (260G-ABZ, 260G-ACA, 270R-AAA); section + blank skipped
    assert s["product_count"] == 3
    # preamble (exchange rate) preserved
    assert any("Exchange Rate" in str(p["cells"]) for p in s["preamble"])
    # section heading captured
    assert any("Cardiovascular" in sec["heading"] for sec in s["section_headings"])


def test_composite_header_labels_merge_band():
    data = _make_workbook_bytes()
    s = analyze_workbook(data)["sheets"][0]
    labels = {col["index"]: col["label"] for col in s["columns"]}
    # column D merges the multi-row header band
    assert "Export Price" in labels[4] and "FOB Taiwan" in labels[4]


def test_extract_preserves_every_cell_as_unmapped():
    data = _make_workbook_bytes()
    s = analyze_workbook(data)["sheets"][0]
    cfg = {
        "name": "Main Gym", "header_row": 5, "header_band": s["header_band"],
        "code_col": 1, "name_col": 2,
        "mappings": {"4": "cost_price"},   # map export price → cost
    }
    prods = extract_products(data, cfg)
    assert len(prods) == 3
    p = prods[0]
    assert p["sku"] == "260G-ABZ"
    assert p["name"] == "Classic Treadmill"
    assert p["cost_price"] == 4369.40
    assert p["source_sheet"] == "Main Gym"
    assert p["source_row"] == 7
    assert p["section"] == "Cardiovascular Range"
    # unmapped cells (Units, Cost, spare-cable) preserved — nothing lost
    vals = {u["value"] for u in p["unmapped_fields"]}
    assert "35" in vals and "1189.07" in vals and "spare-cable-xyz" in vals


def test_section_applies_to_following_products():
    data = _make_workbook_bytes()
    s = analyze_workbook(data)["sheets"][0]
    cfg = {"name": "Main Gym", "header_row": 5, "header_band": s["header_band"],
           "code_col": 1, "name_col": 2, "mappings": {}}
    prods = extract_products(data, cfg)
    assert all(p["section"] == "Cardiovascular Range" for p in prods)


def test_auto_map_keyword_matching():
    cols = [
        {"index": 1, "label": "Product Code"},
        {"index": 2, "label": "Description"},
        {"index": 3, "label": "Sage Item Code"},
        {"index": 4, "label": "Cost Price US $"},
    ]
    m = auto_map(cols)
    assert m[1] == "sku"
    assert m[3] == "sage_code"
    assert m[4] == "cost_price"


def test_canonical_fields_present():
    keys = {f["key"] for f in CANONICAL_FIELDS}
    for k in ("sku", "sage_code", "name", "cost_price", "sell_price", "manufacturer"):
        assert k in keys


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="sample workbook not staged")
def test_real_workbook_no_data_loss():
    data = open(SAMPLE, "rb").read()
    a = analyze_workbook(data)
    assert len(a["sheets"]) == 4
    total = sum(s["product_count"] for s in a["sheets"])
    assert total > 7000  # ~7193 detected rows
    main = next(s for s in a["sheets"] if s["name"] == "Main Gym")
    cfg = {"name": "Main Gym", "header_row": main["header_row"], "header_band": main["header_band"],
           "code_col": main["code_col"], "name_col": main["name_col"], "mappings": {"4": "cost_price"}}
    prods = extract_products(data, cfg)
    assert len(prods) > 3000
    # every product carries provenance + preserved cells
    assert all(p.get("source_row") and p.get("sku") for p in prods[:50])
    assert sum(len(p["unmapped_fields"]) for p in prods[:50]) > 100
