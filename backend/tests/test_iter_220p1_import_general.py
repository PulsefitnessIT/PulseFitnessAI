"""Iter 220 P1 — generalized spreadsheet import engine.

Pure in-memory unit tests for utils/price_list_import.py covering the
"complicated spreadsheet" generalisations: no-code (name-only) catalogues,
score-based header detection, repeated header rows (stacked tables),
section bands, robust number parsing and the confidence score.
"""
import io

import openpyxl

from utils.price_list_import import (
    analyze_workbook, extract_products, _coerce_number,
)


def _wb_bytes(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---- number coercion ----
def test_coerce_numbers():
    assert _coerce_number("£1,234.56") == 1234.56
    assert _coerce_number("(123)") == -123.0          # accounting negative
    assert _coerce_number("20%") == 20.0
    assert _coerce_number("  $2,000 ") == 2000.0
    assert _coerce_number("n/a") is None
    assert _coerce_number(None) is None
    assert _coerce_number(42) == 42.0


# ---- name-only catalogue (NO product code column) ----
def test_name_only_catalogue_imports_with_synth_sku():
    raw = _wb_bytes({"Catalogue": [
        ["Product Name", "Cost", "Sell"],
        ["Olympic Barbell 20kg", 80, 150],
        ["Rubber Bumper Plate 10kg", 12, 25],
        ["Olympic Barbell 20kg", 80, 150],   # duplicate name -> distinct synth SKU
    ]})
    analysis = analyze_workbook(raw)
    sheet = analysis["sheets"][0]
    assert sheet["has_code"] is False
    assert sheet["product_count"] == 3
    assert any("SKU will be generated" in w or "generated from" in w for w in sheet["warnings"])

    cfg = {"name": "Catalogue", "header_row": sheet["header_row"],
           "header_band": sheet["header_band"], "code_col": sheet["code_col"],
           "name_col": sheet["name_col"], "mappings": sheet["auto_mapping"]}
    prods = extract_products(raw, cfg)
    assert len(prods) == 3
    skus = [p["sku"] for p in prods]
    assert all(skus), "every product got a synthesised SKU"
    assert len(set(skus)) == 3, "duplicate names disambiguated"
    assert all(p.get("sku_synthesized") for p in prods)
    # cost/sell parsed
    assert prods[0]["name"] == "Olympic Barbell 20kg"
    assert prods[0]["cost_price"] == 80 and prods[0]["sell_price"] == 150


# ---- score-based header detection (title/blank rows above header) ----
def test_header_detection_with_preamble():
    raw = _wb_bytes({"Price": [
        ["ACME 2026 PRICE LIST", None, None],
        ["Exchange rate: 1.27", None, None],
        ["SKU", "Description", "Trade Price"],
        ["AC-1", "Widget", 9.99],
        ["AC-2", "Gadget", 19.99],
    ]})
    sheet = analyze_workbook(raw)["sheets"][0]
    assert sheet["header_row"] == 3
    assert sheet["has_code"] is True
    assert sheet["product_count"] == 2
    assert len(sheet["preamble"]) >= 1  # title + fx row preserved


# ---- repeated header rows (two stacked tables) are not ingested ----
def test_repeated_header_rows_skipped():
    raw = _wb_bytes({"Multi": [
        ["SKU", "Name", "Cost"],
        ["A1", "Alpha", 1],
        ["A2", "Beta", 2],
        ["SKU", "Name", "Cost"],   # repeated header for a second block
        ["B1", "Gamma", 3],
    ]})
    sheet = analyze_workbook(raw)["sheets"][0]
    # 3 real products, the repeated header row must NOT count as a product
    assert sheet["product_count"] == 3
    cfg = {"name": "Multi", "header_row": sheet["header_row"],
           "header_band": sheet["header_band"], "code_col": sheet["code_col"],
           "name_col": sheet["name_col"], "mappings": sheet["auto_mapping"]}
    prods = extract_products(raw, cfg)
    assert [p["sku"] for p in prods] == ["A1", "A2", "B1"]


# ---- section bands applied to following products ----
def test_section_headings_applied():
    raw = _wb_bytes({"Sectioned": [
        ["Code", "Name", "Price"],
        ["CARDIO", None, None],          # section heading (blank code)
        ["C1", "Treadmill", 1000],
        ["STRENGTH", None, None],        # section heading
        ["S1", "Bench", 300],
    ]})
    sheet = analyze_workbook(raw)["sheets"][0]
    assert sheet["product_count"] == 2
    cfg = {"name": "Sectioned", "header_row": sheet["header_row"],
           "header_band": sheet["header_band"], "code_col": sheet["code_col"],
           "name_col": sheet["name_col"], "mappings": sheet["auto_mapping"]}
    prods = extract_products(raw, cfg)
    assert prods[0]["section"] == "CARDIO"
    assert prods[1]["section"] == "STRENGTH"


# ---- confidence score ----
def test_confidence_high_for_clean_sheet_low_for_empty():
    clean = analyze_workbook(_wb_bytes({"S": [
        ["SKU", "Name", "Cost", "Sell"], ["X1", "Item", 1, 2],
    ]})) ["sheets"][0]
    assert clean["confidence"] >= 80

    empty = analyze_workbook(_wb_bytes({"S": [
        ["just some notes"], [None],
    ]})) ["sheets"][0]
    assert empty["confidence"] <= 50
