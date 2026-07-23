"""
Inventory & Distribution — branded INSTALLATION CERTIFICATE (proof-of-install).

Generated automatically when an install is signed off (commissioned). Captures the
machine + serial, the Health & Safety acknowledgement, the customer's signature and
the warranty dates, then stores the PDF in object storage against the asset. This is
the physical proof-of-install lifecycle HubSpot's Service Hub structurally cannot do.
"""
from __future__ import annotations

import io
import base64
import logging
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool
from utils.database import db, put_object, APP_NAME

logger = logging.getLogger(__name__)


def _fmt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return str(iso)[:10]


def _sig_bytes(data_url: str | None) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return None


def build_certificate_pdf(payload: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

    org = payload.get("org") or {}
    alloc = payload.get("allocation") or {}
    rec = payload.get("installation") or {}
    warranty = payload.get("warranty") or {}
    hs = payload.get("hs") or {}
    brand = "#0B3D91"
    accent = "#19CDFF"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=20 * mm,
                            title=f"Installation Certificate · {alloc.get('reference', '')}")
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle("t", parent=styles["Title"], fontSize=20, leading=24, textColor=colors.HexColor(brand), spaceAfter=0)
    h_sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=9.5, leading=12, textColor=colors.HexColor("#64748B"))
    h_sec = ParagraphStyle("sec", parent=styles["Heading4"], fontSize=10, leading=12, textColor=colors.HexColor("#0F172A"), spaceBefore=6, spaceAfter=4, textTransform="uppercase")
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#1F2937"))
    muted = ParagraphStyle("m", parent=body, fontSize=8.5, textColor=colors.HexColor("#64748B"))
    story: list = []

    org_name = org.get("name") or "Pulse Fitness"
    header_left = Paragraph(f"<b>{org_name}</b>", h_title)
    header_right = Paragraph(
        "<b>Installation Certificate</b><br/>"
        f"Ref: {alloc.get('reference', '')}<br/>"
        f"Issued: {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}",
        h_sub)
    header = Table([[header_left, header_right]], colWidths=[110 * mm, 64 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.4, colors.HexColor(accent)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [header, Spacer(1, 4 * mm)]

    def kv_table(rows):
        t = Table([[Paragraph(f"<b>{k}</b>", muted), Paragraph(str(v or "—"), body)] for k, v in rows], colWidths=[42 * mm, 132 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#E2E8F0")),
        ]))
        return t

    story.append(Paragraph("Customer & site", h_sec))
    story.append(kv_table([
        ("Customer", alloc.get("customer_company_name")),
        ("Site", alloc.get("customer_site")),
        ("Installed on", _fmt(alloc.get("installed_at") or rec.get("commissioned_at"))),
        ("Installed by", rec.get("engineer_name")),
    ]))

    story.append(Paragraph("Equipment installed", h_sec))
    story.append(kv_table([
        ("Model", alloc.get("model") or alloc.get("product_code")),
        ("Product code", alloc.get("product_code")),
        ("Serial number", alloc.get("serial_number")),
        ("Condition on install", rec.get("condition")),
    ]))

    story.append(Paragraph("Warranty", h_sec))
    story.append(kv_table([
        ("Warranty start", _fmt(warranty.get("warranty_start"))),
        ("Warranty end", _fmt(warranty.get("warranty_end"))),
        ("Activation basis", (warranty.get("warranty_source") or "installation_date").replace("_", " ")),
    ]))

    checks = rec.get("checklist") or {}
    done = [k.replace("_", " ").title() for k, v in checks.items() if v]
    story.append(Paragraph("Health &amp; Safety and completion", h_sec))
    story.append(Paragraph(
        f"Health &amp; Safety requirements followed and site left safe: <b>{'Yes' if rec.get('hs_acknowledged') else 'Not recorded'}</b>.", body))
    if done:
        story.append(Paragraph("Install checks completed: " + ", ".join(done) + ".", muted))
    if hs.get("access_risk_level"):
        story.append(Paragraph(f"Pre-install survey access risk: {hs.get('access_risk_level')}.", muted))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Customer sign-off", h_sec))
    sig = _sig_bytes(rec.get("customer_signature"))
    sig_cell = "Signature on file"
    if sig:
        try:
            sig_cell = Image(io.BytesIO(sig), width=55 * mm, height=20 * mm, kind="proportional")
        except Exception:
            sig_cell = "Signature on file"
    signoff = Table([
        [Paragraph("<b>Signed by</b>", muted), Paragraph(rec.get("customer_name") or "—", body)],
        [Paragraph("<b>Date</b>", muted), Paragraph(_fmt(rec.get("signed_at")), body)],
        [Paragraph("<b>Signature</b>", muted), sig_cell],
    ], colWidths=[42 * mm, 132 * mm])
    signoff.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(signoff)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "This certificate confirms the equipment above was installed and commissioned, and accepted by the customer "
        "on the date shown. Retain for warranty and service records.", muted))

    doc.build(story)
    return buf.getvalue()


async def generate_and_store_certificate(alloc: dict, rec: dict, warranty: dict, user: dict, hs: dict | None = None) -> dict:
    """Build the certificate PDF and store it against the asset. Returns
    {certificate_id, storage_path, filename}. Non-fatal on failure (returns {})."""
    try:
        org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0, "name": 1, "brand_kit": 1}) or {}
        payload = {"org": org, "allocation": alloc, "installation": rec, "warranty": warranty or {}, "hs": hs or {}}
        pdf = await run_in_threadpool(build_certificate_pdf, payload)
        cert_id = rec.get("id")
        path = f"{APP_NAME}/install-certificates/{user.get('organization_id')}/{cert_id}.pdf"
        res = await run_in_threadpool(put_object, path, pdf, "application/pdf")
        storage_path = (res or {}).get("path", path)
        filename = f"installation-certificate-{alloc.get('reference', cert_id)}.pdf"
        await db.installation_commissioning_records.update_one(
            {"id": cert_id}, {"$set": {"certificate_storage_path": storage_path, "certificate_filename": filename}})
        if alloc.get("asset_id"):
            await db.equipment.update_one(
                {"id": alloc["asset_id"], "organization_id": user.get("organization_id")},
                {"$set": {"install_certificate_path": storage_path, "install_certificate_record_id": cert_id}})
        return {"certificate_id": cert_id, "storage_path": storage_path, "filename": filename}
    except Exception as e:
        logger.exception(f"[install-certificate] generation failed: {e!r}")
        return {}
