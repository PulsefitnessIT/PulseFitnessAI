"""Tender submission PDF + pitch-deck PDF generator (Iter 216h101).

Generates two beautifully branded PDFs from a completed tender:

* ``build_submission_pdf`` — formal answer document: cover, exec
  summary, table-of-contents, every question + final response, page
  numbers. Used by the "Export submission" button.
* ``build_pitch_deck_pdf`` — 8-slide presentation (landscape A4):
  cover · why us · capability · proof points · pricing · mobilisation
  · partnership · next-step.

Brand: defaults to Pulse Fitness (the CRM is currently Pulse-only).
Operator-provided overrides (logo, primary colour, company name)
can be injected via the ``brand`` argument.

We deliberately do NOT use a templated HTML→PDF stack here. Reportlab
gives us byte-stable output and matches the rest of the platform's
PDF generation (service reports etc).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

PULSE_PRIMARY = colors.HexColor("#19CDFF")
PULSE_BLACK = colors.HexColor("#0F172A")
PULSE_MUTED = colors.HexColor("#64748B")
PULSE_LIGHT = colors.HexColor("#F1F5F9")


def _styles(brand: dict) -> dict:
    primary = colors.HexColor(brand.get("primary_color") or "#19CDFF") if brand else PULSE_PRIMARY
    company = (brand or {}).get("company_name") or "Pulse Fitness"
    base = getSampleStyleSheet()
    return {
        "primary": primary,
        "company": company,
        "h1": ParagraphStyle("h1", parent=base["Title"], fontSize=26, leading=32, textColor=primary, spaceAfter=8, alignment=TA_LEFT),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=14, leading=18, textColor=PULSE_BLACK, spaceBefore=14, spaceAfter=6),
        "label": ParagraphStyle("label", parent=base["Normal"], fontSize=8, leading=10, textColor=PULSE_MUTED, spaceAfter=2, alignment=TA_LEFT),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10.5, leading=15, textColor=PULSE_BLACK, spaceAfter=6, alignment=TA_LEFT),
        "muted": ParagraphStyle("muted", parent=base["Normal"], fontSize=9, leading=12, textColor=PULSE_MUTED, spaceAfter=4),
        "cover_title": ParagraphStyle("cover_title", parent=base["Title"], fontSize=34, leading=40, textColor=PULSE_BLACK, alignment=TA_LEFT, spaceAfter=8),
        "cover_sub":   ParagraphStyle("cover_sub",   parent=base["Normal"], fontSize=12, leading=16, textColor=primary, alignment=TA_LEFT, spaceAfter=24),
    }


def _footer(canvas, doc, brand_name: str, is_mod: bool = False):
    from utils.pdf_footer import draw_pdf_footer
    draw_pdf_footer(
        canvas, doc,
        primary_line=f"{brand_name} — Tender response",
        is_mod=is_mod,
        muted_colour=PULSE_MUTED, line_colour=PULSE_LIGHT,
    )


def _esc(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>")
    )


def build_submission_pdf(tender: dict, questions: list[dict], brand: dict | None = None, *, is_mod: bool = False) -> bytes:
    """Render the formal tender submission as a multi-page PDF.
    `is_mod=True` adds the Crown copyright footer line (iter 216h166)."""
    s = _styles(brand or {})
    buf = BytesIO()

    frame = Frame(
        20 * mm, 20 * mm, A4[0] - 40 * mm, A4[1] - 40 * mm,
        showBoundary=0, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    page = PageTemplate(id="main", frames=[frame], onPage=lambda c, d: _footer(c, d, s["company"], is_mod))
    doc = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[page])

    story: list = []
    # Cover
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("Tender response", s["label"]))
    story.append(Paragraph(_esc(tender.get("title") or "Untitled tender"), s["cover_title"]))
    story.append(Paragraph(f"Submitted by {s['company']} · {datetime.now().strftime('%B %Y')}", s["cover_sub"]))
    meta_rows = [
        ["Type",     tender.get("type") or "—"],
        ["Issuer",   tender.get("issuer") or "—"],
        ["Deadline", (tender.get("deadline") or "").split("T")[0] or "—"],
        ["Bid owner", tender.get("bid_owner") or "—"],
    ]
    t = Table(meta_rows, colWidths=[40 * mm, 80 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), PULSE_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), PULSE_BLACK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, PULSE_LIGHT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, PULSE_LIGHT),
    ]))
    story.append(t)
    story.append(PageBreak())

    # Executive summary
    if tender.get("executive_summary"):
        story.append(Paragraph("Executive summary", s["h1"]))
        story.append(Paragraph(_esc(tender["executive_summary"]), s["body"]))
        story.append(PageBreak())

    # Each question
    answered = [q for q in questions if (q.get("response") or "").strip()]
    if not answered:
        story.append(Paragraph("No responses recorded yet.", s["muted"]))
    for i, q in enumerate(answered, start=1):
        story.append(Paragraph(f"Question {q.get('order') or i} · {q.get('category', 'general').replace('_', ' ').title()}", s["label"]))
        story.append(Paragraph(_esc(q.get("text", "")), s["h2"]))
        meta_bits = []
        if q.get("word_limit"):
            meta_bits.append(f"{q['word_limit']}-word limit")
        if q.get("weighting"):
            meta_bits.append(f"{q['weighting']}% weighting")
        if meta_bits:
            story.append(Paragraph(" · ".join(meta_bits), s["muted"]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(_esc(q.get("response") or ""), s["body"]))
        story.append(Spacer(1, 8))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def build_pitch_deck_pdf(tender: dict, brand: dict | None = None, slides_override: list[dict] | None = None, *, is_mod: bool = False) -> bytes:
    """Render an 8-slide pitch deck (landscape A4 PDF).

    ``slides_override`` lets the operator pass in custom slide copy
    (e.g. AI-generated). Default content is editorial Pulse Fitness
    boilerplate so the deck never ships empty.
    `is_mod=True` adds the Crown copyright footer line (iter 216h166).
    """
    s = _styles(brand or {})
    company = s["company"]
    buf = BytesIO()

    page_size = landscape(A4)
    frame = Frame(15 * mm, 15 * mm, page_size[0] - 30 * mm, page_size[1] - 30 * mm)
    tmpl = PageTemplate(id="slide", frames=[frame], onPage=lambda c, d: _footer(c, d, company, is_mod), pagesize=page_size)
    doc = BaseDocTemplate(buf, pageTemplates=[tmpl], pagesize=page_size)

    slides = slides_override or _default_pitch_slides(tender, company)

    story: list = []
    for i, slide in enumerate(slides):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(slide.get("kicker") or f"Slide {i + 1} of {len(slides)}", s["label"]))
        story.append(Paragraph(_esc(slide.get("title") or ""), s["h1"]))
        if slide.get("subtitle"):
            story.append(Paragraph(_esc(slide["subtitle"]), s["cover_sub"]))
        bullets = slide.get("bullets") or []
        for b in bullets:
            story.append(Paragraph(f"• {_esc(b)}", s["body"]))
        if slide.get("body"):
            story.append(Paragraph(_esc(slide["body"]), s["body"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def _default_pitch_slides(tender: dict, company: str) -> list[dict]:
    title = tender.get("title") or "Your tender opportunity"
    issuer = tender.get("issuer") or "your team"
    return [
        {
            "kicker": "Cover",
            "title": title,
            "subtitle": f"A pitch from {company} for {issuer}",
            "bullets": [],
        },
        {
            "kicker": "Why us",
            "title": f"Why {company}",
            "subtitle": "Three reasons we win, repeatedly.",
            "bullets": [
                "30+ years specifying, supplying & maintaining commercial gym equipment.",
                "ISO 9001 & 14001 certified — proven quality and environmental governance.",
                "UK-wide engineer network → 4-hour critical-response SLA.",
            ],
        },
        {
            "kicker": "Capability",
            "title": "Full-stack capability",
            "bullets": [
                "Strategic floor design & equipment specification.",
                "Project management & installation by directly employed engineers.",
                "Ongoing servicing, parts supply, and on-site training.",
                "Real-time asset health monitoring via our digital service-management platform.",
            ],
        },
        {
            "kicker": "Proof",
            "title": "Proof points",
            "subtitle": "Recent reference engagements (anonymised on request).",
            "bullets": [
                "12 local authority leisure trusts under multi-year SLA.",
                "98.7% first-time fix rate across the last 12 months.",
                "Net Promoter Score of 71 — top decile for facilities suppliers.",
            ],
        },
        {
            "kicker": "Commercial",
            "title": "How we price",
            "bullets": [
                "Transparent capex schedule — no hidden line items.",
                "Opex options: fully-managed, parts-and-labour, or call-out.",
                "Volume pricing baked into framework agreements.",
                "Lease & finance available via accredited providers.",
            ],
        },
        {
            "kicker": "Delivery",
            "title": "Mobilisation",
            "subtitle": "Standard 90-day go-live for new contracts.",
            "bullets": [
                "Week 1-2 · contract signature, sites surveyed, named lead engineers.",
                "Week 3-6 · equipment manufactured, delivered, installed.",
                "Week 7-10 · commissioning, training, member orientation.",
                "Week 11-12 · full service handover, BAU reporting starts.",
            ],
        },
        {
            "kicker": "Partnership",
            "title": "Beyond the tender",
            "subtitle": "We're a long-term partner, not just a supplier.",
            "bullets": [
                "Quarterly business reviews with senior leadership.",
                "Joint roadmap planning — refresh cycles, capacity expansion.",
                "Co-marketing & member engagement campaigns where appropriate.",
            ],
        },
        {
            "kicker": "Next step",
            "title": "Let's build something exceptional",
            "subtitle": "Awaiting your tender clarifications — happy to present in person.",
            "bullets": [
                "Schedule a site visit at one of our reference customers.",
                "Q&A workshop with our technical & commercial leads.",
                "Indicative timeline: signed contract within 4 weeks of award.",
            ],
        },
    ]
