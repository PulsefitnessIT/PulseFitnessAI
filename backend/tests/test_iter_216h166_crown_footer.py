"""Iter 216h166 — Crown copyright PDF footer for MOD tenants."""
import os
from datetime import datetime

import pytest

from utils.pdf_footer import (
    crown_copyright_line, is_mod_account_type, draw_pdf_footer,
)
from utils.engineer_invoice_pdf import build_engineer_invoice_pdf
from utils.engineer_quote_pdf import build_engineer_quote_pdf
from utils.capex_pdf_exporter import build_capex_board_pdf


# ── Pure helpers ─────────────────────────────────────────────────

class TestIsMod:
    @pytest.mark.parametrize("at", [
        "mod_org", "MOD_ORG", "mod_branch", "mod_site", "mod_custom",
    ])
    def test_mod_prefixes_detected(self, at):
        assert is_mod_account_type(at) is True

    @pytest.mark.parametrize("at", [None, "", "full", "lite", "modern", "moderator", "free"])
    def test_non_mod_account_types_rejected(self, at):
        assert is_mod_account_type(at) is False


class TestCrownLine:
    def test_includes_current_year_by_default(self):
        line = crown_copyright_line()
        assert str(datetime.utcnow().year) in line
        assert "Crown copyright" in line
        assert "Open Government Licence" in line
        assert "nationalarchives.gov.uk" in line

    def test_year_override_respected(self):
        line = crown_copyright_line(year=2024)
        assert "© Crown copyright 2024" in line


# ── PDF integration — check the footer bytes ─────────────────────

_QUOTE = {
    "quote_number": "Q-216H166-1", "engineer_name": "Test Engineer",
    "customer_name": "ACME Gym", "customer_email": "ops@acme.test",
    "valid_until": "2026-03-01", "subtotal": 100, "vat": 20, "total": 120,
    "line_items": [{"description": "Test", "qty": 1, "unit_price": 100, "total": 100}],
}
_INVOICE = {
    "invoice_number": "INV-216H166-1", "engineer_name": "Test Engineer",
    "customer_name": "ACME Gym", "customer_email": "ops@acme.test",
    "issue_date": "2026-02-17", "due_date": "2026-03-17",
    "subtotal": 100, "vat": 20, "total": 120,
    "line_items": [{"description": "Test", "qty": 1, "unit_price": 100, "total": 100}],
}
_CAPEX = {
    "fleet_intelligence": {
        "safety_distribution": {}, "ber_distribution": {},
    },
    "totals": {"recommend_replace_total": 0, "monitor_total": 0},
    "priority_replacements": [],
    "ber_service_spend": {"items": []},
}


def _pdf_text(pdf: bytes) -> str:
    """Extract all text from a PDF — ReportLab compresses content streams
    (FlateDecode + ASCII85Decode) so we can't grep the raw bytes. pypdf
    is already a project dependency for the BER export, so we reuse it
    rather than adding a parser."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _pdf_contains(pdf: bytes, needle: str) -> bool:
    return needle in _pdf_text(pdf)


# Quote --------------------------------------------------------------

def test_quote_pdf_non_mod_omits_crown():
    pdf = build_engineer_quote_pdf(_QUOTE, is_mod=False)
    assert pdf.startswith(b"%PDF")
    assert not _pdf_contains(pdf, "Crown copyright")
    assert _pdf_contains(pdf, "GymAxis")  # primary footer line preserved


def test_quote_pdf_mod_includes_crown():
    pdf = build_engineer_quote_pdf(_QUOTE, is_mod=True)
    assert pdf.startswith(b"%PDF")
    assert _pdf_contains(pdf, "Crown copyright")
    assert _pdf_contains(pdf, "Open Government Licence")


# Invoice ------------------------------------------------------------

def test_invoice_pdf_non_mod_omits_crown():
    pdf = build_engineer_invoice_pdf(_INVOICE, is_mod=False)
    assert pdf.startswith(b"%PDF")
    assert not _pdf_contains(pdf, "Crown copyright")


def test_invoice_pdf_mod_includes_crown():
    pdf = build_engineer_invoice_pdf(_INVOICE, is_mod=True)
    assert pdf.startswith(b"%PDF")
    assert _pdf_contains(pdf, "Crown copyright")
    # The primary footer line must still be there.
    assert _pdf_contains(pdf, "GymAxis")


# CAPEX board --------------------------------------------------------

def test_capex_board_pdf_mod_includes_crown():
    pdf = build_capex_board_pdf(_CAPEX, brand={"company_name": "MOD Test"}, is_mod=True)
    assert pdf.startswith(b"%PDF")
    assert _pdf_contains(pdf, "Crown copyright")
    assert _pdf_contains(pdf, "MOD Test")


def test_capex_board_pdf_default_omits_crown():
    pdf = build_capex_board_pdf(_CAPEX, brand={"company_name": "ACME Gym"})
    assert pdf.startswith(b"%PDF")
    assert not _pdf_contains(pdf, "Crown copyright")


# Default backward-compatibility — call sites that haven't been updated
# yet (e.g. tender PDF) must keep working unchanged.

def test_quote_pdf_default_kwarg_is_non_mod():
    pdf = build_engineer_quote_pdf(_QUOTE)
    assert pdf.startswith(b"%PDF")
    assert not _pdf_contains(pdf, "Crown copyright")


def test_invoice_pdf_default_kwarg_is_non_mod():
    pdf = build_engineer_invoice_pdf(_INVOICE)
    assert pdf.startswith(b"%PDF")
    assert not _pdf_contains(pdf, "Crown copyright")
