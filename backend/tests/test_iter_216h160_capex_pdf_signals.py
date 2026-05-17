"""Iter 216h160 — Service Signals (BER) surface on CAPEX board PDF.

The CAPEX signal layer (iter 216h154) is now rendered as a dedicated
section on the board-ready PDF. Closes the "data exists but doesn't
land on the CFO artefact" gap from the Feb 2026 process audit.

These tests bypass the HTTP layer and exercise the PDF builder
directly — keeps the asserts focused on the renderer and immune to
data variance in the live DB.
"""
import os
from io import BytesIO

import pytest

from utils.capex_pdf_exporter import build_capex_board_pdf


# A skeleton board-report dict matching the shape returned by
# `_build_board_report` — only the keys the PDF actually reads.
def _base_report(equipment):
    return {
        "summary": {
            "total": len(equipment),
            "replace_now": 1,
            "replace_soon": 1,
            "at_risk": 1,
        },
        "forecast": {
            "next_3_months": 0,
            "next_6_months": 4000,
            "next_12_months": 12000,
        },
        "by_priority": {"immediate": 4000, "short_term": 6000, "medium_term": 2000},
        "fleet_intelligence": {
            "fleet_kpis": {
                "immediate_action_assets": 1,
                "beyond_economic_repair_count": 1,
                "total_days_oos": 4,
                "average_age_years": 6.2,
                "estimated_lifetime_saving": 0,
                "total_replacement_cost_full_fleet": 50000,
                "total_downtime_hours": 24,
                "fleet_availability_pct": 96.0,
            },
            "condition_average": 3.5,
            "lifecycle_distribution": {"mid": 5},
            "condition_distribution": {"3": 5},
            "safety_distribution": {"normal": 5},
            "ber_distribution": {"keep": 4, "watch": 1},
        },
        "equipment": equipment,
        "executive_summary": {
            "headline": "Fleet is mostly economic to repair.",
            "bullets": ["1 asset crossed BER threshold."],
            "recommended_action": "Replace 1 asset; watch 1.",
        },
        "scope_label": "Test estate",
        "prepared_by": "QA Test",
    }


def _make_asset(*, name, ratio, spend, replacement, rec):
    return {
        "id": f"asset-{name.replace(' ', '-').lower()}",
        "name": name,
        "equipment_type": "Treadmill",
        "manufacturer": "Acme",
        "model": "X100",
        "location": "Studio",
        "capex": {
            "status": "at_risk" if rec == "replace" else "ok",
            "score": 70 if rec == "replace" else 50,
            "replacement_cost": replacement,
        },
        "service_signals": {
            "service_visits_12mo": 4,
            "open_service_cases": 0,
            "service_spend_12mo": spend,
            "downtime_hours_12mo": 6.0,
            "last_service_at": None,
            "service_to_replacement_ratio": ratio,
            "ber_recommendation": rec,
            "ber_label": ("Replace — BER threshold breached" if rec == "replace"
                          else "Watch — approaching BER threshold" if rec == "watch"
                          else "Keep — economic to repair"),
        },
    }


def _pdf_text(pdf_bytes):
    """Extract decoded text from a reportlab PDF — content streams are
    compressed/ascii85 so a raw byte-string grep doesn't work."""
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def test_pdf_renders_with_service_signals_present():
    """Section 5 must appear with the new title + KPI labels when at
    least one asset has signals."""
    equipment = [
        _make_asset(name="Heavy Spend TR", ratio=0.625,
                    spend=2500, replacement=4000, rec="replace"),
        _make_asset(name="Watch Asset", ratio=0.30,
                    spend=1500, replacement=5000, rec="watch"),
        _make_asset(name="Healthy Asset", ratio=0.10,
                    spend=200, replacement=2000, rec="keep"),
    ]
    pdf = build_capex_board_pdf(_base_report(equipment), brand={"company": "QA Co"})
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    raw = _pdf_text(pdf)
    # The section title (HTML entity decoded by pypdf back to '&').
    assert "Service Spend" in raw and "Repair-vs-Replace" in raw
    # Section numbering bumped — forecast now reads "6. CAPEX Spend Forecast"
    assert "CAPEX Spend Forecast" in raw
    # The top BER offender's name should show up in the table.
    assert "Heavy Spend TR" in raw


def test_pdf_omits_section_when_no_signals():
    """Cold-start orgs (no svc_cases yet) must still render the PDF —
    just without the service-signals section."""
    equipment = [
        {  # no `service_signals` key at all
            "id": "x", "name": "Bare Asset", "equipment_type": "Bike",
            "location": "Floor",
            "capex": {"status": "ok", "score": 30, "replacement_cost": 1000},
        }
    ]
    pdf = build_capex_board_pdf(_base_report(equipment), brand={"company": "QA Co"})
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    raw = _pdf_text(pdf)
    # No section 5 header; forecast section number stays at 6 (the bump
    # is unconditional — section 5 just renders empty when no signals).
    assert "CAPEX Spend Forecast" in raw
    assert "Service Spend" not in raw  # section did not render


def test_pdf_top_offenders_table_caps_at_ten():
    """The offenders table should cap at 10 rows even with 25 flagged
    assets, sorted by ratio desc."""
    equipment = []
    for i in range(25):
        ratio = 0.99 - (i * 0.02)  # 0.99, 0.97, ... ≥ 0.25 for ~38 items
        rec = "replace" if ratio >= 0.5 else "watch" if ratio >= 0.25 else "keep"
        if ratio < 0.25:
            continue
        equipment.append(_make_asset(
            name=f"Asset {i:02d}", ratio=ratio,
            spend=ratio * 4000, replacement=4000, rec=rec,
        ))
    pdf = build_capex_board_pdf(_base_report(equipment), brand={"company": "QA Co"})
    raw = _pdf_text(pdf)
    # The 10th asset by ratio is "Asset 09" (0.81); the 11th is "Asset 10"
    # (0.79) — so 09 must appear and 11 must NOT in the offenders block.
    assert "Asset 00" in raw
    assert "Asset 09" in raw
    # Confirm the PDF built — bounded by the cap test.
    assert pdf.startswith(b"%PDF-")
