"""Pulse Fitness — printable 1-pager generator (sales + trust).

Three A4 PDF flows, generated on demand and auto-captured into the
Documents library so the master admin can re-grab them from any
device.

  • ``GET  /api/master-admin/sales-pack/sales``
  • ``GET  /api/master-admin/sales-pack/trust``
  • ``POST /api/master-admin/sales-pack/generate-all``  → both,
    returned as ``{sales: doc_id, trust: doc_id}`` so the UI can
    refresh and surface them immediately.
  • ``POST /api/master-admin/sales-pack/send``  → emails a 1-pager
    to a named recipient with a public share-link backup. Reuses the
    same ``invoice_share_links`` collection / TTL / audit shape as
    the invoice-send flow, distinguished by ``kind="sales_pack"``
    and ``variant="sales"|"trust"``.
  • ``GET  /api/public/sales-pack-share/{token}``  → public, no-auth
    download of the 1-pager via signed token. Token validation,
    expiry, and `used_count` audit mirrors invoice shares.

ReportLab is already in the backend's dependency tree (used by the
invoice renderer) so no new deps.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email


router = APIRouter()
logger = logging.getLogger(__name__)


# ── Brand palette (Pulse Fitness) ───────────────────────────────────


PULSE_PRIMARY   = "#19CDFF"  # cyan accent
PULSE_INK       = "#0A0C10"  # near-black background
PULSE_INK_2     = "#1F2329"
PULSE_FG        = "#0A0C10"
PULSE_MUTED     = "#6B7280"
PULSE_BORDER    = "#E5E7EB"


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Reusable PDF building blocks ────────────────────────────────────


def _drawing_libs():
    """Lazy import — keep startup cost zero for backends that never
    call this module."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Flowable,
    )
    return A4, colors, ParagraphStyle, getSampleStyleSheet, mm, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable


class _Hero:
    """Small flowable that paints the brand-coloured hero strip with the
    title + tagline. Avoids us reinventing per-page-break styling."""

    def __init__(self, title: str, kicker: str, tagline: str, width_mm: float, height_mm: float):
        self.title = title
        self.kicker = kicker
        self.tagline = tagline
        self.width_mm = width_mm
        self.height_mm = height_mm

    def to_table(self, mm, colors, ParagraphStyle, Paragraph, Table, TableStyle):
        kicker_style = ParagraphStyle(
            "kicker", fontSize=8, textColor=colors.HexColor(PULSE_PRIMARY),
            leading=10, fontName="Helvetica-Bold",
        )
        title_style = ParagraphStyle(
            "title", fontSize=22, textColor=colors.white, leading=24,
            spaceBefore=2, fontName="Helvetica-Bold",
        )
        tagline_style = ParagraphStyle(
            "tag", fontSize=10, textColor=colors.HexColor("#cfe9f5"),
            leading=13, fontName="Helvetica",
        )
        cell = [
            Paragraph(self.kicker.upper(), kicker_style),
            Paragraph(self.title, title_style),
            Paragraph(self.tagline, tagline_style),
        ]
        table = Table([[cell]], colWidths=[self.width_mm * mm], rowHeights=[self.height_mm * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PULSE_INK)),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor(PULSE_PRIMARY)),
        ]))
        return table


def _section_header(text: str, ParagraphStyle, Paragraph, colors):
    style = ParagraphStyle(
        "sec", fontSize=10, textColor=colors.HexColor(PULSE_PRIMARY),
        spaceAfter=4, spaceBefore=10, fontName="Helvetica-Bold",
    )
    return Paragraph(text.upper(), style)


def _bullet(text: str, ParagraphStyle, Paragraph, colors):
    style = ParagraphStyle(
        "bul", fontSize=10, textColor=colors.HexColor(PULSE_FG),
        leading=14, leftIndent=10, bulletIndent=0, spaceAfter=2,
        fontName="Helvetica",
    )
    return Paragraph(f"&bull; &nbsp; {text}", style)


def _footer_line(text: str, ParagraphStyle, Paragraph, colors):
    style = ParagraphStyle(
        "foot", fontSize=8, textColor=colors.HexColor(PULSE_MUTED),
        alignment=1, spaceBefore=10, fontName="Helvetica",
    )
    return Paragraph(text, style)


# ── Sales 1-pager ───────────────────────────────────────────────────


def _build_sales_pdf() -> bytes:
    (
        A4, colors, ParagraphStyle, _styles, mm,
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, _F,
    ) = _drawing_libs()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=12 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title="Pulse Fitness — platform 1-pager",
    )

    flow: list = []
    width_mm = 210 - 28  # A4 minus side margins
    flow.append(_Hero(
        title="The platform Pulse Fitness runs on.",
        kicker="Pulse Fitness · Operations + Memberships + CRM",
        tagline="One platform from front desk to plant room. Faster service, fewer breakdowns, more renewals.",
        width_mm=width_mm, height_mm=42,
    ).to_table(mm, colors, ParagraphStyle, Paragraph, Table, TableStyle))
    flow.append(Spacer(1, 10))

    # 3-up modules row
    module_strip_data = [[
        _module_cell("Operations", "Faults logged in 30 sec.", [
            "Floor staff QR-scan into the issue", "AI fault diagnosis on-device",
            "Engineer dispatch + SLA timer", "Live equipment availability",
        ], ParagraphStyle, Paragraph, colors),
        _module_cell("Memberships", "Joining, classes, renewals.", [
            "Stripe-ready join flow + waiver",
            "Class booking + waitlist + capacity",
            "Drop-in QR · printable receipts",
            "Family + corporate plans",
        ], ParagraphStyle, Paragraph, colors),
        _module_cell("CRM", "Win, retain, expand.", [
            "Pipelines + win-back automations",
            "Email + SMS sequences",
            "Activation funnel + churn signals",
            "Sales-team scoreboards",
        ], ParagraphStyle, Paragraph, colors),
    ]]
    cell_w = (width_mm - 6) / 3
    module_table = Table(module_strip_data, colWidths=[cell_w * mm] * 3, rowHeights=[None])
    module_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("BOX", (2, 0), (2, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    flow.append(module_table)
    flow.append(Spacer(1, 12))

    # Stat strip
    flow.append(_section_header("Why Pulse Fitness chose this stack", ParagraphStyle, Paragraph, colors))
    stat_table = Table([[
        _stat_cell("64+", "pieces of equipment online at Tottenham Green", ParagraphStyle, Paragraph, colors),
        _stat_cell("~30 sec", "to log a fault from the gym floor", ParagraphStyle, Paragraph, colors),
        _stat_cell("Single", "platform — no app shuffling", ParagraphStyle, Paragraph, colors),
        _stat_cell("UK-hosted", "GDPR-aligned, data stays at home", ParagraphStyle, Paragraph, colors),
    ]], colWidths=[((width_mm - 9) / 4) * mm] * 4)
    stat_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PULSE_INK)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    flow.append(stat_table)
    flow.append(Spacer(1, 12))

    # Outcome bullets
    flow.append(_section_header("What changes in week 1", ParagraphStyle, Paragraph, colors))
    for line in [
        "<b>Floor staff</b> stop scribbling on clipboards — every fault is timestamped and dispatched.",
        "<b>Members</b> book classes from the same app they use to scan in — drop-off falls.",
        "<b>Operations</b> sees every site's fault queue and CAPEX exposure on one screen.",
        "<b>Finance</b> chases overdue invoices automatically (7/14/28-day stages).",
        "<b>Sales</b> works the activation funnel with one source of truth, not three CRMs.",
    ]:
        flow.append(_bullet(line, ParagraphStyle, Paragraph, colors))

    flow.append(Spacer(1, 12))

    # Footer block
    flow.append(_footer_line(
        "Pulse Fitness · operations &amp; memberships platform — built with GymAxis AI · "
        f"generated {datetime.now(timezone.utc).strftime('%-d %b %Y')}",
        ParagraphStyle, Paragraph, colors,
    ))

    doc.build(flow)
    return buf.getvalue()


def _module_cell(title: str, subtitle: str, bullets: list[str], ParagraphStyle, Paragraph, colors):
    h = ParagraphStyle("mh", fontSize=12, textColor=colors.HexColor(PULSE_INK), fontName="Helvetica-Bold", spaceAfter=2)
    s = ParagraphStyle("ms", fontSize=9, textColor=colors.HexColor(PULSE_PRIMARY), fontName="Helvetica-Bold", spaceAfter=6)
    b = ParagraphStyle("mb", fontSize=9, textColor=colors.HexColor(PULSE_FG), leading=12, leftIndent=8, bulletIndent=0)
    cell = [Paragraph(title, h), Paragraph(subtitle.upper(), s)]
    cell += [Paragraph(f"&bull; {x}", b) for x in bullets]
    return cell


def _stat_cell(big: str, small: str, ParagraphStyle, Paragraph, colors):
    big_s = ParagraphStyle(
        "stat_big", fontSize=22, textColor=colors.HexColor(PULSE_PRIMARY),
        fontName="Helvetica-Bold", leading=26,
    )
    small_s = ParagraphStyle(
        "stat_small", fontSize=8, textColor=colors.white,
        leading=11, fontName="Helvetica",
    )
    return [Paragraph(big, big_s), Paragraph(small, small_s)]


# ── Trust 1-pager ───────────────────────────────────────────────────


def _build_trust_pdf() -> bytes:
    (
        A4, colors, ParagraphStyle, _styles, mm,
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, _F,
    ) = _drawing_libs()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=12 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title="Pulse Fitness — trust &amp; security 1-pager",
    )
    flow: list = []
    width_mm = 210 - 28

    flow.append(_Hero(
        title="Trust &amp; security at Pulse Fitness.",
        kicker="Pulse Fitness · platform security posture",
        tagline="Built so procurement, IT and data-protection officers can sign off in one read.",
        width_mm=width_mm, height_mm=42,
    ).to_table(mm, colors, ParagraphStyle, Paragraph, Table, TableStyle))
    flow.append(Spacer(1, 10))

    # 4 pillars
    pillars = [
        ("Encryption",   "TLS 1.2+ in transit. AES-256 at rest. Bcrypt password hashing."),
        ("Isolation",    "Per-tenant data scoping at the API layer. Master admin segregation enforced server-side."),
        ("Least-priv.",  "Role-based access — gym-floor / operator / admin / master-admin. Bypass header for tests, not prod."),
        ("Observability","All admin actions audited. Login events stored with IP + UA. Health checks public at /api/health."),
    ]
    pillar_cells = []
    for title, body in pillars:
        h = ParagraphStyle("ph", fontSize=11, textColor=colors.HexColor(PULSE_PRIMARY), fontName="Helvetica-Bold", spaceAfter=4)
        b = ParagraphStyle("pb", fontSize=9, textColor=colors.HexColor(PULSE_FG), leading=12, fontName="Helvetica")
        pillar_cells.append([Paragraph(title, h), Paragraph(body, b)])
    pillars_table = Table([pillar_cells], colWidths=[((width_mm - 9) / 4) * mm] * 4)
    pillars_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("BOX", (2, 0), (2, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("BOX", (3, 0), (3, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    flow.append(pillars_table)
    flow.append(Spacer(1, 12))

    # Controls coverage table
    flow.append(_section_header("Controls coverage", ParagraphStyle, Paragraph, colors))
    rows = [["Control", "State", "Evidence"]]
    rows += [
        ["Encryption in transit (TLS 1.2+)",      "Live",      "HSTS · CSP locked · /api/health"],
        ["Encryption at rest",                    "Live",      "MongoDB Atlas-class hosting"],
        ["Password hashing",                      "Live",      "bcrypt cost 12+"],
        ["Per-tenant data scoping",               "Live",      "Server-side org_id checks"],
        ["Role-based access control",             "Live",      "4-tier (floor / operator / admin / master)"],
        ["Audit log — admin actions",             "Live",      "documents access · login events"],
        ["Brute-force throttle",                  "Live",      "Per-IP login rate limit"],
        ["Data residency (UK)",                   "Live",      "EU-West region"],
        ["UK GDPR alignment",                     "Live",      "Public privacy policy"],
        ["SOC 2 Type II",                         "In flight", "Q3 2026 target"],
        ["ISO 27001",                             "Roadmap",   "FY2026/27"],
    ]
    ctl = Table(rows, colWidths=[80 * mm, 28 * mm, (width_mm - 108) * mm])
    ctl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PULSE_INK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor(PULSE_PRIMARY)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(ctl)
    flow.append(Spacer(1, 10))

    # Sub-processors
    flow.append(_section_header("Sub-processors", ParagraphStyle, Paragraph, colors))
    sub_rows = [["Vendor", "Role", "Region"]]
    sub_rows += [
        ["MongoDB Atlas",   "Primary database",   "EU"],
        ["Stripe",          "Payments",           "UK / EU"],
        ["Resend",          "Transactional email","EU"],
        ["Emergent.sh",     "Hosting / runtime",  "EU"],
    ]
    subt = Table(sub_rows, colWidths=[60 * mm, (width_mm - 100) * mm, 40 * mm])
    subt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor(PULSE_BORDER)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
    ]))
    flow.append(subt)
    flow.append(Spacer(1, 12))

    flow.append(_footer_line(
        "Pulse Fitness · trust posture — GymAxis AI · "
        f"generated {datetime.now(timezone.utc).strftime('%-d %b %Y')} · "
        "for procurement / DPO contact: <b>security@gymaxisai.com</b>",
        ParagraphStyle, Paragraph, colors,
    ))

    doc.build(flow)
    return buf.getvalue()


# ── Library auto-capture ────────────────────────────────────────────


async def _capture(title: str, pdf: bytes, filename: str, actor_id: str) -> str | None:
    try:
        from routes.master_admin_documents_lib import record_generated_document
        return await record_generated_document(
            title=title,
            category="onboarding",  # Sales/trust packs sit under Onboarding
            body=pdf,
            content_type="application/pdf",
            filename=filename,
            tags=["pulse-fitness", "1-pager"],
            actor_id=actor_id,
        )
    except Exception:
        logger.exception("sales pack auto-capture failed for %s", title)
        return None


# ── Endpoints ───────────────────────────────────────────────────────


def _pdf_response(body: bytes, filename: str) -> Response:
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/master-admin/sales-pack/sales")
async def download_sales_pager(user: dict = Depends(get_current_user)) -> Response:
    _require_master(user)
    pdf = _build_sales_pdf()
    await _capture(
        title="Pulse Fitness — sales 1-pager",
        pdf=pdf,
        filename="pulse-fitness-sales-1-pager.pdf",
        actor_id=user.get("id"),
    )
    return _pdf_response(pdf, "pulse-fitness-sales-1-pager.pdf")


@router.get("/master-admin/sales-pack/trust")
async def download_trust_pager(user: dict = Depends(get_current_user)) -> Response:
    _require_master(user)
    pdf = _build_trust_pdf()
    await _capture(
        title="Pulse Fitness — trust & security 1-pager",
        pdf=pdf,
        filename="pulse-fitness-trust-1-pager.pdf",
        actor_id=user.get("id"),
    )
    return _pdf_response(pdf, "pulse-fitness-trust-1-pager.pdf")


@router.post("/master-admin/sales-pack/generate-all")
async def generate_all_pagers(user: dict = Depends(get_current_user)) -> dict:
    """Render both PDFs and ensure they're captured into the documents
    library. Returns the freshly-created doc ids so the UI can refresh."""
    _require_master(user)
    sales = _build_sales_pdf()
    trust = _build_trust_pdf()
    sales_id = await _capture(
        title="Pulse Fitness — sales 1-pager",
        pdf=sales,
        filename="pulse-fitness-sales-1-pager.pdf",
        actor_id=user.get("id"),
    )
    trust_id = await _capture(
        title="Pulse Fitness — trust & security 1-pager",
        pdf=trust,
        filename="pulse-fitness-trust-1-pager.pdf",
        actor_id=user.get("id"),
    )
    return {
        "sales": {"document_id": sales_id, "size_bytes": len(sales)},
        "trust": {"document_id": trust_id, "size_bytes": len(trust)},
        "as_of": _now_iso(),
    }



# ── Send 1-pager to a named recipient ──────────────────────────────


SALES_PACK_TTL_DEFAULT = 30
SALES_PACK_TTL_MAX = 180

_VARIANT_RENDERERS = {
    "sales": ("Pulse Fitness — sales 1-pager",
              "pulse-fitness-sales-1-pager.pdf",
              "sales 1-pager"),
    "trust": ("Pulse Fitness — trust & security 1-pager",
              "pulse-fitness-trust-1-pager.pdf",
              "trust & security 1-pager"),
}


def _public_base() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


def _build_pdf_for_variant(variant: str) -> bytes:
    if variant == "sales":
        return _build_sales_pdf()
    if variant == "trust":
        return _build_trust_pdf()
    raise HTTPException(400, "variant must be 'sales' or 'trust'")


def _render_share_email_html(
    *,
    variant_label: str,
    download_url: str,
    sender_message: str,
    expires_at: datetime,
) -> str:
    """Pulse-branded email body for the share link."""
    expires_str = expires_at.strftime("%-d %b %Y")
    msg_block = ""
    if sender_message:
        safe = (
            sender_message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        msg_block = (
            f'<div style="background:#f0fbff;border-left:4px solid #19CDFF;'
            f'padding:14px 18px;margin:18px 0;border-radius:4px;color:#1a1a1a;'
            f'line-height:1.6;font-size:14px;">{safe}</div>'
        )
    return f"""<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;background:#fff;">
  <div style="background:#0A0C10;padding:28px 30px;text-align:center;">
    <div style="color:#19CDFF;font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px;">Pulse Fitness</div>
    <h1 style="color:#fff;margin:0;font-size:22px;letter-spacing:-0.3px;">A quick {variant_label}.</h1>
  </div>
  <div style="padding:32px 30px;color:#1a1a1a;">
    <p style="line-height:1.6;margin:0 0 14px;">Hi,</p>
    <p style="line-height:1.6;margin:0 0 16px;">
      Sharing the Pulse Fitness <strong>{variant_label}</strong>. The PDF is attached, and the secure link below works on any device.
    </p>
    {msg_block}
    <div style="text-align:center;margin:28px 0;">
      <a href="{download_url}" style="display:inline-block;background:#19CDFF;color:#0A0C10;padding:14px 32px;
         text-decoration:none;border-radius:8px;font-weight:700;font-size:14px;letter-spacing:0.3px;">
         Open the {variant_label} →
      </a>
    </div>
    <p style="color:#6b7280;font-size:12px;line-height:1.6;text-align:center;">
      Secure download link expires {expires_str}.
    </p>
  </div>
  <div style="background:#f5f5f5;padding:16px 30px;text-align:center;">
    <p style="color:#9ca3af;font-size:11px;margin:0;">Sent from Pulse Fitness · powered by GymAxis AI</p>
  </div>
</div>"""


@router.post("/master-admin/sales-pack/send")
async def send_pulse_pager(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Email a Pulse 1-pager to a named recipient with a signed share
    link backup."""
    _require_master(user)

    variant = (payload.get("variant") or "").strip().lower()
    if variant not in _VARIANT_RENDERERS:
        raise HTTPException(400, "variant must be 'sales' or 'trust'")
    title, filename, variant_label = _VARIANT_RENDERERS[variant]

    recipient = (payload.get("to_email") or "").strip()
    if "@" not in recipient:
        raise HTTPException(400, "Recipient email is required")

    try:
        ttl_days = int(payload.get("ttl_days") or SALES_PACK_TTL_DEFAULT)
    except (TypeError, ValueError):
        ttl_days = SALES_PACK_TTL_DEFAULT
    ttl_days = max(1, min(ttl_days, SALES_PACK_TTL_MAX))
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    sender_message = (payload.get("message") or "").strip()[:2000]

    pdf_bytes = _build_pdf_for_variant(variant)
    # Auto-capture so we have an audit row in the documents library too.
    await _capture(title=title, pdf=pdf_bytes, filename=filename, actor_id=user.get("id"))

    token = uuid.uuid4().hex
    share = {
        "id": str(uuid.uuid4()),
        "token": token,
        "organization_id": None,         # platform-level asset
        "invoice_id": None,              # n/a — not an invoice
        "kind": "sales_pack",
        "variant": variant,
        "recipient_email": recipient,
        "subject": f"Pulse Fitness — {variant_label}",
        "message": sender_message,
        "expires_at": expires_at.isoformat(),
        "used_count": 0,
        "last_used_at": None,
        "created_by": user.get("id"),
        "created_at": _now_iso(),
        "revoked": False,
    }
    await db.invoice_share_links.insert_one(dict(share))

    base = _public_base()
    download_url = f"{base}/api/public/sales-pack-share/{token}" if base else f"/api/public/sales-pack-share/{token}"

    html = _render_share_email_html(
        variant_label=variant_label,
        download_url=download_url,
        sender_message=sender_message,
        expires_at=expires_at,
    )
    attachments = [{
        "filename": filename,
        "content": base64.b64encode(pdf_bytes).decode(),
    }]
    sent_ok = await send_email(recipient, share["subject"], html, attachments=attachments)

    return {
        "sent": bool(sent_ok),
        "delivered_via_email": bool(sent_ok),
        "recipient": recipient,
        "share_id": share["id"],
        "share_url": download_url,
        "expires_at": share["expires_at"],
        "variant": variant,
    }


@router.get("/public/sales-pack-share/{token}")
async def public_sales_pack_share(token: str) -> Response:
    """Public, no-auth 1-pager download via signed token."""
    share = await db.invoice_share_links.find_one(
        {"token": token, "kind": "sales_pack"}, {"_id": 0},
    )
    if not share or share.get("revoked"):
        raise HTTPException(404, "Link not found or revoked")
    expires_at = share.get("expires_at") or ""
    try:
        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(404, "Link malformed")
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    if exp_dt < datetime.now(timezone.utc):
        raise HTTPException(410, "Link expired")

    variant = share.get("variant") or "sales"
    if variant not in _VARIANT_RENDERERS:
        raise HTTPException(404, "Unknown variant")
    _, filename, _ = _VARIANT_RENDERERS[variant]
    pdf_bytes = _build_pdf_for_variant(variant)

    await db.invoice_share_links.update_one(
        {"id": share["id"]},
        {"$inc": {"used_count": 1}, "$set": {"last_used_at": _now_iso()}},
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
