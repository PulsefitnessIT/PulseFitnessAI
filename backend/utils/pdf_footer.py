"""Iter 216h166 — Shared PDF footer with optional Crown copyright line.

Every PDF builder in `backend/utils/*_pdf*.py` was duplicating its own
ReportLab `_footer` callback. They all draw:

    {brand text} ──────────────────────────────── Page {n}

UK-government tenants (MOD HQ + child sites — `account_type` begins
with `mod_`) need an additional line carrying the Crown copyright
notice, per the contract clauses in the MOD onboarding pack. The
notice is *only* rendered for MOD tenants; commercial gym tenants get
the original footer untouched.

The line wording follows the Open Government Licence v3.0 short form,
which is the format the Cabinet Office's "Producing Documents" guidance
mandates for documents shared under government contracts:

    © Crown copyright {year}. This material is licensed under the Open
    Government Licence v3.0 (nationalarchives.gov.uk/doc/open-government-licence).

`draw_pdf_footer` is the single place that draws the footer. It keeps
the visual identity (separator line, brand colour, page number on the
right) of the existing exporters bit-for-bit identical when called
without `is_mod=True`, so this refactor is invisible to commercial
tenants.
"""
from __future__ import annotations

from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

_DEFAULT_MUTED = colors.HexColor("#6B7280")
_DEFAULT_LINE = colors.HexColor("#E5E7EB")


def is_mod_account_type(account_type: str | None) -> bool:
    """Iter 216h113h convention: MOD tenants have `account_type`
    `mod_org`, `mod_branch`, or `mod_site`. Everything else is commercial."""
    if not account_type:
        return False
    return str(account_type).lower().startswith("mod_")


def crown_copyright_line(year: int | None = None) -> str:
    """The Crown copyright + OGL v3.0 attribution rendered on MOD PDFs.

    Year defaults to the current UTC year so re-issued documents in
    January don't accidentally carry the previous year's notice."""
    y = year if year is not None else datetime.utcnow().year
    return (
        f"© Crown copyright {y}. Licensed under the Open Government Licence v3.0 — "
        "nationalarchives.gov.uk/doc/open-government-licence"
    )


def draw_pdf_footer(
    canvas, doc, *,
    primary_line: str,
    is_mod: bool = False,
    muted_colour=_DEFAULT_MUTED,
    line_colour=_DEFAULT_LINE,
) -> None:
    """Draw the standard footer on every page of a ReportLab document.

    Layout (commercial tenant):
        ──────────────────────────────────────────────
        {primary_line}                          Page {n}

    Layout (MOD tenant — Crown copyright bar lifts everything up 4mm):
        ──────────────────────────────────────────────
        {primary_line}                          Page {n}
        © Crown copyright {year}. Licensed under …
    """
    canvas.saveState()
    canvas.setFillColor(muted_colour)
    canvas.setFont("Helvetica", 8)
    # Existing two-column row, exactly as before.
    canvas.drawString(20 * mm, 12 * mm, primary_line)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
    # Separator line above the row.
    canvas.setStrokeColor(line_colour)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    # Crown copyright line drops just BELOW the existing line so it
    # never overlaps the page number column.
    if is_mod:
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawString(20 * mm, 7 * mm, crown_copyright_line())
    canvas.restoreState()


async def is_mod_for_case(db_obj, case_id: str | None) -> bool:
    """Return True iff the case's customer organisation is a MOD tenant.

    Used by every engineer-facing PDF (quote, invoice, service report)
    to decide whether the Crown copyright footer should be drawn. Safe
    to call with a missing case_id — returns False in every error path
    so non-MOD documents are never accidentally branded as Crown."""
    if not case_id:
        return False
    case = await db_obj.svc_cases.find_one(
        {"id": case_id}, {"_id": 0, "organization_id": 1},
    )
    if not case or not case.get("organization_id"):
        return False
    org = await db_obj.organizations.find_one(
        {"id": case["organization_id"]}, {"_id": 0, "account_type": 1},
    )
    return is_mod_account_type((org or {}).get("account_type"))


__all__ = [
    "draw_pdf_footer", "crown_copyright_line",
    "is_mod_account_type", "is_mod_for_case",
]
