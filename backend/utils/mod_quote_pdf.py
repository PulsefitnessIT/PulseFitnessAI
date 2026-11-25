"""Sage-style Pulse Fitness sales quotation PDF (matches QT9410/QT9411/QT9412 layout)."""
from __future__ import annotations

import io
import os

from reportlab.lib.colors import Color, white, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "mod_quote")
GREY = Color(0.827, 0.827, 0.827)
W, H = A4
ROW_BOTTOM_LIMIT = 630
CONT_BOTTOM_LIMIT = 740
DESC_W = 190


def _y(top: float) -> float:
    return H - top


def _txt(c, x, top, s, bold=False, size=8, right=False, color=black):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    (c.drawRightString if right else c.drawString)(x, _y(top) - size * 0.8, str(s))


def _fmt(v) -> str:
    return f"{float(v or 0):.2f}"


def _header(c, q):
    c.drawImage(ImageReader(os.path.join(_STATIC, "header.png")), 35, _y(100), 521.5, 62.6, mask="auto")
    c.setFillColor(GREY)
    c.rect(355, _y(152), 170, 25, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(440, _y(149), "Quotation")
    _txt(c, 46, 184, "Customer", bold=True)
    top = 197
    for ln in [q.get("customer_name")] + list(q.get("address_lines") or []):
        if ln:
            _txt(c, 46, top, ln)
            top += 12.7
    _txt(c, 276, 184, "Sales Quotation Number", bold=True)
    _txt(c, 381, 184, q.get("quote_number", ""))
    _txt(c, 276, 199, "Date", bold=True)
    _txt(c, 381, 199, q.get("quote_date", ""))
    _txt(c, 276, 213, "Customer Reference", bold=True)
    _txt(c, 381, 213, q.get("customer_reference") or "")


def _table_header(c, top=286):
    c.setFillColor(GREY)
    c.rect(12, _y(top + 22), 547, 22, stroke=0, fill=1)
    c.setStrokeColor(white)
    c.rect(12.5, _y(top + 21), 546, 20, stroke=1, fill=0)
    for x, label, right in ((24, "Line", False), (44, "Item Code", False), (145, "Description", False),
                            (339, "Quantity", False), (374, "Unit", False), (482, "Unit Price", True),
                            (553, "Total", True)):
        _txt(c, x, top + 6, label, bold=True, right=right, color=white)
    return top + 24


def _footer(c, q):
    _txt(c, 46, 645, "Deliver To", bold=True)
    for i, ln in enumerate(q.get("delivery_lines") or ["As Above"]):
        _txt(c, 46, 658 + i * 11, ln)
    _txt(c, 352, 663, "TOTAL NET", bold=True)
    _txt(c, 541, 663, _fmt(q.get("net")), right=True)
    _txt(c, 352, 678, " TOTAL VAT", bold=True)
    _txt(c, 541, 678, _fmt(q.get("vat")), right=True)
    _txt(c, 352, 691, "TOTAL GROSS", bold=True)
    _txt(c, 541, 693, _fmt(q.get("gross")), right=True)
    _txt(c, 352, 725, "All Amounts in", bold=True)
    _txt(c, 480, 725, "Pound Sterling")


def _footer_image(c):
    c.drawImage(ImageReader(os.path.join(_STATIC, "footer.png")), 345.6, _y(800.5), 211.8, 45.7, mask="auto")


def render_mod_quote_pdf(q: dict) -> bytes:
    """q: quote_number, quote_date, customer_reference, customer_name, address_lines,
    delivery_lines, lines[{line_no,item_code,description,qty,unit,unit_price,total}], net, vat, gross."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Quotation {q.get('quote_number', '')}")
    lines = q.get("lines") or []
    page = 1
    _header(c, q)
    top = _table_header(c)
    for i, ln in enumerate(lines):
        wrapped = simpleSplit(str(ln.get("description") or "").lstrip(" -"), "Helvetica", 8, DESC_W)
        h = max(1, len(wrapped)) * 9 + 2
        if top + h > CONT_BOTTOM_LIMIT:
            _txt(c, 553, 805, f"Page {page} — continued", right=True, size=7)
            _footer_image(c)
            c.showPage()
            page += 1
            _header(c, q)
            top = _table_header(c)
        _txt(c, 24, top, ln.get("line_no", i + 1))
        _txt(c, 44, top, "MOD-CALLOUT" if ln.get("kind") == "call_out" and ln.get("item_code") == "1B" else ln.get("item_code", ""))
        for k, w in enumerate(wrapped):
            _txt(c, 145, top + k * 9, w)
        _txt(c, 345, top, ln.get("qty", ""))
        _txt(c, 374, top, ln.get("unit", "Each"))
        _txt(c, 482, top, _fmt(ln.get("unit_price")), right=True)
        _txt(c, 553, top, _fmt(ln.get("total")), right=True)
        top += h
    if top > ROW_BOTTOM_LIMIT:
        _footer_image(c)
        c.showPage()
        page += 1
        _header(c, q)
        _table_header(c)
    _footer(c, q)
    if page > 1:
        _txt(c, 553, 805, f"Page {page}", right=True, size=7)
    _footer_image(c)
    c.showPage()
    c.save()
    return buf.getvalue()
