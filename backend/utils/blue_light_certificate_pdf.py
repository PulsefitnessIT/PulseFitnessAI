"""Blue Light Service & Calibration Certificate PDF.

Laid out to match Pulse Fitness's master "Certificate of Service" template:
a full-bleed dark banner with the pulsefitness wordmark + tagline, a two-tone
"CERTIFICATE / OF SERVICE" title, a swappable customer crest top-right, the
treadmill calibration table, a 2x2 service-detail block, and Managing Director
(left) + Engineer (right) signature blocks, closed by a dark footer with the
website. The customer crest is swappable per contract (uploaded or URL).
"""
from __future__ import annotations
import os

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)

TEMPLATE_VERSION = 2

# ── Palette (sampled from the master certificate) ──
BANNER = colors.HexColor("#2D2D32")      # dark charcoal header/footer
BANNER_TOP = colors.HexColor("#565A61")  # lighter strip across the very top
CYAN = colors.HexColor("#33BEE8")        # Pulse cyan — "OF SERVICE" + logo ring
TITLE_DARK = colors.HexColor("#3F3F45")  # "CERTIFICATE" + site name
SUBGREY = colors.HexColor("#6E747B")     # caps sub-text / labels
TABLE_HEAD = colors.HexColor("#1B1B1F")  # calibration table header row
BORDER = colors.HexColor("#C9D4E5")
LIGHT = colors.HexColor("#EEF3FB")

_PASS = colors.HexColor("#16a34a")
_REVIEW = colors.HexColor("#d97706")
_FAIL = colors.HexColor("#dc2626")
_RESULT = {"pass": _PASS, "review": _REVIEW, "fail": _FAIL}

PAGE_W, PAGE_H = A4
MARGIN_X = 42
BANNER_H = 84
TOPSTRIP_H = 14
FOOTER_H = 48


def _esc(t) -> str:
    if t is None:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fetch_logo_bytes(url):
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        import httpx
        r = httpx.get(url, timeout=4.0, follow_redirects=True)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def _resolve_logo_bytes(config):
    """Prefer an uploaded logo from object storage (customer_logo_path); fall
    back to a hosted URL (customer_logo_url) for backwards compatibility."""
    cfg = config or {}
    path = cfg.get("customer_logo_path")
    if path:
        try:
            from utils.database import get_object
            data, _ct = get_object(path)
            if data:
                return data
        except Exception:
            pass
    return _fetch_logo_bytes(cfg.get("customer_logo_url"))


def _fmt_month_year(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt).strftime("%B %Y")
        except Exception:
            continue
    return s


def _fmt_date(v) -> str:
    s = str(v or "").strip()[:10]
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d %B %Y")
    except Exception:
        return s


_LIGHT_LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pulse-logo-wide-light.png")


def _draw_wordmark(c, x, baseline):
    c.setStrokeColor(CYAN)
    c.setLineWidth(2.2)
    c.circle(x + 9, baseline + 5, 9, stroke=1, fill=0)
    c.setFillColor(CYAN)
    c.circle(x + 9, baseline + 5, 3.1, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 23)
    c.drawString(x + 27, baseline, "pulse")
    w = c.stringWidth("pulse", "Helvetica-Bold", 23)
    c.setFont("Helvetica", 23)
    c.drawString(x + 27 + w, baseline, "fitness")


def _page_furniture_factory(logo_bytes):
    def _draw(c, doc):
        c.saveState()
        # Header banner
        c.setFillColor(BANNER)
        c.rect(0, PAGE_H - BANNER_H, PAGE_W, BANNER_H, fill=1, stroke=0)
        c.setFillColor(BANNER_TOP)
        c.rect(0, PAGE_H - TOPSTRIP_H, PAGE_W, TOPSTRIP_H, fill=1, stroke=0)
        band_mid = PAGE_H - TOPSTRIP_H - (BANNER_H - TOPSTRIP_H) / 2
        if os.path.exists(_LIGHT_LOGO):
            lw = 150
            iw, ih = ImageReader(_LIGHT_LOGO).getSize()
            lh = lw * ih / iw
            c.drawImage(_LIGHT_LOGO, MARGIN_X, band_mid - lh / 2, width=lw, height=lh, mask="auto")
        else:
            _draw_wordmark(c, MARGIN_X, band_mid - 8)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 14.5)
        c.drawRightString(PAGE_W - MARGIN_X, band_mid - 5, "Qualified to deliver the best")
        # Customer crest (top-right, below banner)
        if logo_bytes:
            try:
                ir = ImageReader(BytesIO(logo_bytes))
                iw, ih = ir.getSize()
                max_h, max_w = 150, 155
                h = max_h
                w = h * (iw / ih) if ih else max_w
                if w > max_w:
                    w = max_w
                    h = w * (ih / iw) if iw else max_h
                top = PAGE_H - BANNER_H - 6
                c.drawImage(ir, PAGE_W - MARGIN_X - w, top - h, width=w, height=h,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        # Footer banner
        c.setFillColor(BANNER)
        c.rect(0, 0, PAGE_W, FOOTER_H, fill=1, stroke=0)
        c.setStrokeColor(CYAN)
        c.setLineWidth(1.6)
        c.circle(MARGIN_X + 7, FOOTER_H / 2, 7.5, stroke=1, fill=0)
        c.setFillColor(CYAN)
        c.circle(MARGIN_X + 7, FOOTER_H / 2, 2.4, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 11)
        c.drawRightString(PAGE_W - MARGIN_X, FOOTER_H / 2 - 4, "www.pulsefitness.com")
        c.restoreState()
    return _draw


def build_certificate_pdf(*, contract: dict, station: dict, visit: dict,
                          treadmills: list[dict], config: dict) -> bytes:
    """treadmills: [{serial_number, asset_name, speed:[{target,measured,result}],
    incline:[{target,measured,result}], overall}] using the FINAL measured values."""
    buf = BytesIO()
    logo_bytes = _resolve_logo_bytes(config)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="Service & Calibration Certificate",
        leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=BANNER_H + 22, bottomMargin=FOOTER_H + 14,
    )
    content_w = PAGE_W - 2 * MARGIN_X

    cert_big = ParagraphStyle("cert_big", fontName="Helvetica-Bold", fontSize=48,
                              leading=48, textColor=TITLE_DARK, alignment=TA_LEFT)
    cert_cyan = ParagraphStyle("cert_cyan", fontName="Helvetica-Bold", fontSize=29,
                               leading=32, textColor=CYAN, alignment=TA_LEFT, spaceBefore=2)
    caps = ParagraphStyle("caps", fontName="Helvetica", fontSize=12.5, leading=17,
                          textColor=SUBGREY, alignment=TA_LEFT)
    site = ParagraphStyle("site", fontName="Helvetica-Bold", fontSize=16, leading=20,
                          textColor=TITLE_DARK, alignment=TA_LEFT)
    caps_body = ParagraphStyle("caps_body", parent=caps, fontSize=13, leading=18)
    label = ParagraphStyle("label", fontName="Helvetica", fontSize=9, leading=12, textColor=SUBGREY)
    note = ParagraphStyle("note", fontName="Helvetica", fontSize=7.5, leading=10, textColor=SUBGREY)
    sig_script = ParagraphStyle("sig_script", fontName="Helvetica-Oblique", fontSize=22,
                                leading=24, textColor=colors.HexColor("#222222"))
    sig_label = ParagraphStyle("sig_label", fontName="Helvetica", fontSize=9.5, leading=13,
                               textColor=colors.HexColor("#33383F"))

    story = []
    # Two-tone title (left aligned; crest is drawn top-right on the canvas)
    story.append(Paragraph("CERTIFICATE", cert_big))
    story.append(Paragraph("OF SERVICE", cert_cyan))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("IS TO CERTIFY THAT ALL PULSE FITNESS EQUIPMENT AT", caps))
    site_name = _esc(station.get("site_name"))
    if site_name:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(site_name, site))
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("HAS BEEN CHECKED, SERVICED AND CALIBRATED", caps_body))
    story.append(Paragraph("TO MEET PULSE FITNESS OPERATIONAL STANDARDS", caps_body))
    story.append(Spacer(1, 9 * mm))

    # ── Treadmill calibration table ──
    speed_pts = (config or {}).get("speed_points_mph", [3, 6, 9, 12])
    incline_pts = (config or {}).get("incline_points_pct", [0, 5, 10, 15])
    header = ["Serial Number"] + [f"{_num(p)} mph" for p in speed_pts] + [f"{_num(p)}%" for p in incline_pts]
    data = [header]
    cell_colors = []
    if treadmills:
        for r_i, t in enumerate(treadmills, start=1):
            speed_map = {round(float(x["target"]), 3): x for x in (t.get("speed") or [])}
            incl_map = {round(float(x["target"]), 3): x for x in (t.get("incline") or [])}
            row = [_esc(t.get("serial_number") or t.get("asset_name") or "—")]
            for p in speed_pts:
                x = speed_map.get(round(float(p), 3), {})
                row.append(f"{x.get('measured', '—')}")
                cell_colors.append((r_i, len(row) - 1, _RESULT.get(x.get("result"))))
            for p in incline_pts:
                x = incl_map.get(round(float(p), 3), {})
                row.append(f"{x.get('measured', '—')}")
                cell_colors.append((r_i, len(row) - 1, _RESULT.get(x.get("result"))))
            data.append(row)
    else:
        # keep the template's grid look with a few empty rows
        for _ in range(3):
            data.append([""] * len(header))

    ncols = len(header)
    first_w = 44 * mm
    rest_w = (content_w - first_w) / (ncols - 1)
    tbl = Table(data, colWidths=[first_w] + [rest_w] * (ncols - 1), repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if treadmills:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]))
    for (ri, ci, col) in cell_colors:
        if col is not None:
            style.append(("TEXTCOLOR", (ci, ri), (ci, ri), col))
            style.append(("FONTNAME", (ci, ri), (ci, ri), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    if treadmills:
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(
            f"Speed measured in mph, incline in %. Readings within "
            f"{(config or {}).get('tolerance_pct', 5)}% of target meet Pulse Fitness "
            f"operational tolerance.", note))
    story.append(Spacer(1, 8 * mm))

    # ── Service detail block (2x2, underlined rows) ──
    def _field(lbl, val):
        return Paragraph(
            f"<font color='#6E747B' size='9.5'>{_esc(lbl)}</font>"
            f"&nbsp;&nbsp;&nbsp;&nbsp;<b><font size='12' color='#20242A'>{_esc(val)}</font></b>",
            label)
    details = Table([
        [_field("Service Contract Number", contract.get("contract_number")),
         _field("Engineer Name", visit.get("engineer_name"))],
        [_field("Service & Calibration Date", _fmt_date(visit.get("completed_at"))),
         _field("Next Service Due Date", _fmt_month_year(visit.get("next_service_due")))],
    ], colWidths=[content_w / 2, content_w / 2])
    details.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(details)
    story.append(Spacer(1, 10 * mm))

    # ── Signature blocks: Managing Director (left) + Engineer (right) ──
    md_sig = Paragraph("Chris Johnson", sig_script)
    try:
        import os as _os
        _md_path = _os.path.join(_os.path.dirname(__file__), "assets", "md_signature.png")
        if _os.path.exists(_md_path):
            md_sig = Image(_md_path, width=46 * mm, height=46 * mm * (114 / 212))
            md_sig.hAlign = "LEFT"
    except Exception:
        pass
    sig_bytes = visit.get("_signature_image_bytes")
    eng_sig = Paragraph(_esc(visit.get("engineer_name")) or "&nbsp;", sig_script)
    if sig_bytes:
        try:
            eng_sig = Image(BytesIO(sig_bytes), width=52 * mm, height=18 * mm)
            eng_sig.hAlign = "LEFT"
        except Exception:
            pass
    md_lbl = Paragraph("<b>Chris Johnson</b><br/>Managing Director<br/>Pulse Fitness", sig_label)
    eng_lbl = Paragraph("<b>Engineer</b><br/>Service Team<br/>Pulse Fitness", sig_label)
    sig_tbl = Table([[md_sig, eng_sig], [md_lbl, eng_lbl]],
                    colWidths=[content_w / 2, content_w / 2])
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("VALIGN", (0, 1), (-1, 1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
    ]))
    story.append(sig_tbl)

    furniture = _page_furniture_factory(logo_bytes)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return buf.getvalue()


def _num(p):
    """Render 3.0 -> 3 but keep 3.5 as 3.5."""
    try:
        f = float(p)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return p


def certificate_filename(contract: dict, station: dict, service_date: str) -> str:
    import re

    def clean(x):
        return re.sub(r"[^A-Za-z0-9]+", "-", str(x or "")).strip("-")
    return (f"{clean(contract.get('company_name'))}_{clean(station.get('site_name'))}"
            f"_Service-and-Calibration_{(service_date or datetime.now().strftime('%Y-%m-%d'))[:10]}.pdf")
