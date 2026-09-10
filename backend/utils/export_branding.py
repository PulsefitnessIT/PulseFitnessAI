"""Client-ready branding for generated documents (Employee File, timesheets,
payroll pack).

Resolves the org's logo + name and provides small helpers to stamp a brand
header onto ReportLab (PDF) and openpyxl (Excel) documents. When an org hasn't
uploaded its own logo we fall back to the Pulse Fitness badge (the same asset
the app UI uses), so the documents are always client-ready.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Pulse Fitness primary badge — the client-ready default when an org has not
# uploaded its own logo. Same asset used across the app chrome.
DEFAULT_PULSE_LOGO_URL = (
    "https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/"
    "iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg"
)

_INK = "#0B0C10"
_ACCENT = "#0E7490"

# In-process cache of fetched URL logos.
_url_cache: dict[str, bytes | None] = {}


def _fetch_url_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    if url in _url_cache:
        return _url_cache[url]
    data: bytes | None = None
    try:
        import httpx
        with httpx.Client(timeout=8.0, follow_redirects=True) as c:
            r = c.get(url)
            if r.status_code == 200 and r.content:
                data = r.content
    except Exception as e:  # noqa: BLE001
        logger.warning("export logo fetch failed %s: %s", url, e)
    _url_cache[url] = data
    return data


async def resolve_export_brand(db, org_id: str | None) -> dict:
    """Return {name, logo_bytes} for the given org. Priority: document-branding
    profile logo → org.logo_path (object storage) → org.logo_url (http) →
    default Pulse badge."""
    org = None
    if org_id:
        try:
            org = await db.organizations.find_one(
                {"id": org_id}, {"_id": 0, "name": 1, "logo_url": 1, "logo_path": 1})
        except Exception:  # noqa: BLE001
            org = None
    org = org or {}
    name = (org.get("name") or "Pulse Fitness").strip() or "Pulse Fitness"
    logo: bytes | None = None

    # 1) per-tenant document-branding profile (object storage)
    try:
        from utils.document_branding import get_branding_profile
        from utils.database import get_object
        prof = await get_branding_profile(db, org_id) or {}
        if prof.get("logo_storage_path"):
            logo, _ = get_object(prof["logo_storage_path"])
    except Exception as e:  # noqa: BLE001
        logger.warning("branding-profile logo failed for %s: %s", org_id, e)

    # 2) org's own uploaded logo (object storage path or http url)
    if not logo and org.get("logo_path"):
        try:
            from utils.database import get_object
            logo, _ = get_object(org["logo_path"])
        except Exception:  # noqa: BLE001
            logo = None
    if not logo:
        u = org.get("logo_url") or ""
        if u.startswith("http"):
            logo = _fetch_url_bytes(u)

    # 3) default Pulse badge
    if not logo:
        logo = _fetch_url_bytes(DEFAULT_PULSE_LOGO_URL)

    return {"name": name, "logo_bytes": logo}


# ───────────────────────── PDF (ReportLab) ─────────────────────────

def pdf_logo_image(logo_bytes: bytes | None, max_h_mm: float = 13, max_w_mm: float = 46):
    """A ReportLab Image scaled to fit within the given box, aspect preserved."""
    if not logo_bytes:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
        ir = ImageReader(io.BytesIO(logo_bytes))
        iw, ih = ir.getSize()
        ratio = (iw / ih) if ih else 1.0
        h = max_h_mm * mm
        w = h * ratio
        if w > max_w_mm * mm:
            w = max_w_mm * mm
            h = w / ratio
        return Image(io.BytesIO(logo_bytes), width=w, height=h)
    except Exception as e:  # noqa: BLE001
        logger.warning("pdf logo image failed: %s", e)
        return None


def pdf_brand_header(brand: dict | None) -> list:
    """A compact brand strip (logo left, org name right + divider) to prepend
    to a ReportLab story. Returns [] when there's no brand."""
    if not brand:
        return []
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    name_st = ParagraphStyle("brand_name", parent=styles["Normal"], fontName="Helvetica-Bold",
                             fontSize=12, leading=14, alignment=2, textColor=colors.HexColor(_INK))
    img = pdf_logo_image(brand.get("logo_bytes"))
    left = img if img else Paragraph(f"<b>{brand.get('name', '')}</b>", name_st)
    right = Paragraph(brand.get("name", ""), name_st)
    tbl = Table([[left, right]], colWidths=[60 * mm, None])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [tbl, HRFlowable(width="100%", thickness=1.1, color=colors.HexColor(_ACCENT),
                            spaceBefore=2, spaceAfter=8), Spacer(1, 2)]


# ───────────────────────── Excel (openpyxl) ─────────────────────────

def xlsx_brand_band(ws, brand: dict | None) -> int:
    """Stamp a brand band (logo + org name) at the top of a worksheet.
    Returns the number of rows the band occupies (0 when no brand), so callers
    can offset their content below it."""
    if not brand:
        return 0
    from openpyxl.styles import Font

    name_cell = ws.cell(row=1, column=1, value=brand.get("name") or "")
    name_cell.font = Font(bold=True, size=14, color="0B0C10")
    ws.cell(row=2, column=1, value="").font = Font(size=9, color="0E7490")

    logo = brand.get("logo_bytes")
    if logo:
        try:
            from openpyxl.drawing.image import Image as XLImage
            xi = XLImage(io.BytesIO(logo))
            target_h = 46.0
            ratio = (xi.width / xi.height) if xi.height else 3.8
            xi.height = target_h
            xi.width = int(target_h * ratio)
            # Anchor top-right of the header band so it never sits over the name.
            xi.anchor = "E1"
            ws.add_image(xi)
        except Exception as e:  # noqa: BLE001
            logger.warning("xlsx logo failed: %s", e)
    # Band occupies 4 rows (logo ~ 46px ≈ 2.5 rows + name + spacer).
    return 4
