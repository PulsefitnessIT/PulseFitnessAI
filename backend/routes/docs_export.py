"""PDF export endpoint for platform documentation.

Generates a professionally formatted portrait-orientation PDF from the
PLATFORM_DOCUMENTATION.md file with proper margins, text wrapping, and
table handling.
"""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Response
from fpdf import FPDF

router = APIRouter()

DOCS_PATH = Path(__file__).parent.parent.parent / "memory" / "PLATFORM_DOCUMENTATION.md"

# Brand colours
ACCENT = (37, 99, 210)
HEADING2 = (30, 41, 59)
HEADING3 = (51, 65, 85)
BODY = (40, 40, 40)
BODY_LIGHT = (70, 70, 70)
MUTED = (120, 120, 120)
WHITE = (255, 255, 255)
TABLE_HEADER_BG = (37, 99, 210)
TABLE_ROW_EVEN = (245, 247, 250)
TABLE_ROW_ODD = (255, 255, 255)
TABLE_BORDER = (210, 215, 225)
RULE_COLOR = (200, 210, 225)
COVER_BG = (15, 23, 42)

# Layout
LEFT_MARGIN = 20
RIGHT_MARGIN = 20
TOP_MARGIN = 20
BOTTOM_MARGIN = 25
PAGE_W = 210  # A4 width mm
CONTENT_W = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN  # 170mm usable


# ── Text helpers ─────────────────────────────────────────────────

_UNICODE_REPLACEMENTS = {
    "\u2014": " - ", "\u2013": " - ", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2192": "->",
    "\u2022": "-", "\u00a0": " ", "\u2122": "(TM)", "\u00ae": "(R)",
    "\u00b7": ".", "\u2265": ">=", "\u2264": "<=", "\u00d7": "x",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2015": " - ",
}


def _sanitize(text: str) -> str:
    """Replace Unicode chars unsupported by Helvetica with ASCII equivalents."""
    for k, v in _UNICODE_REPLACEMENTS.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _strip_md(text: str) -> str:
    """Remove markdown formatting."""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    return text.replace("`", "")


def _clean(text: str) -> str:
    return _sanitize(_strip_md(text))


# ── PDF class ────────────────────────────────────────────────────

class DocPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(LEFT_MARGIN, TOP_MARGIN, RIGHT_MARGIN)
        self.set_auto_page_break(auto=True, margin=BOTTOM_MARGIN)
        self._is_cover = True

    def header(self):
        if self._is_cover or self.page_no() <= 1:
            return
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*MUTED)
        self.set_y(8)
        self.cell(CONTENT_W / 2, 6, "GymAxis AI - Platform Documentation v1.0", align="L")
        self.cell(CONTENT_W / 2, 6, f"Page {self.page_no()}", align="R")
        self.ln(10)

    def footer(self):
        if self._is_cover:
            return
        self.set_y(-18)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*MUTED)
        self.set_draw_color(*RULE_COLOR)
        self.line(LEFT_MARGIN, self.get_y(), PAGE_W - RIGHT_MARGIN, self.get_y())
        self.ln(3)
        self.cell(0, 5, "Confidential - GymAxis AI Ltd. - April 2026", align="C")

    def ensure_space(self, min_y: int = 270):
        """Add page if near bottom."""
        if self.get_y() > min_y:
            self.add_page()


# ── Rendering helpers ────────────────────────────────────────────

def _render_cover(pdf: DocPDF):
    """Render a professional cover page."""
    pdf.add_page()
    pdf._is_cover = True
    pdf.set_fill_color(*COVER_BG)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 100, 210, 3, "F")

    pdf.set_y(115)
    pdf.set_font("Helvetica", "B", 38)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 16, "GymAxis AI", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 10, "Complete Platform Documentation", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 7, "Version 1.0  |  April 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 7, "AI-Native CRM & Service-Connected Commercial Platform", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "for the Fitness & Leisure Industry", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 195, 210, 1, "F")

    pdf.set_y(210)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, "This document covers every feature, workflow, data model,", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "and API endpoint across all GymAxis AI systems.", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(260)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 5, "CONFIDENTIAL - For Internal Use Only", align="C", new_x="LMARGIN", new_y="NEXT")


def _compute_col_widths(rows: list[list[str]]) -> list[float]:
    """Calculate table column widths proportional to content."""
    n_cols = len(rows[0])
    max_lens = [0] * n_cols
    for row in rows:
        for ci in range(min(n_cols, len(row))):
            max_lens[ci] = max(max_lens[ci], len(row[ci]))

    total = sum(max_lens) or 1
    widths = [max(20, (ml / total) * CONTENT_W) for ml in max_lens]

    total_mm = sum(widths)
    if total_mm > CONTENT_W:
        scale = CONTENT_W / total_mm
        widths = [w * scale for w in widths]
    return widths


def _render_table_row(pdf: DocPDF, row: list[str], col_widths: list[float],
                      is_header: bool, row_index: int):
    """Render a single table row."""
    row_h = 7
    if is_header:
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_fill_color(*TABLE_HEADER_BG)
        pdf.set_text_color(*WHITE)
    else:
        pdf.set_font("Helvetica", "", 7.5)
        bg = TABLE_ROW_EVEN if row_index % 2 == 0 else TABLE_ROW_ODD
        pdf.set_fill_color(*bg)
        pdf.set_text_color(*BODY)

    pdf.set_draw_color(*TABLE_BORDER)
    for ci, w in enumerate(col_widths):
        cell_text = row[ci] if ci < len(row) else ""
        max_chars = int(w / 1.8)
        if len(cell_text) > max_chars:
            cell_text = cell_text[:max_chars - 2] + ".."
        pdf.cell(w, row_h, " " + cell_text, border=1, fill=True)
    pdf.ln(row_h)


def _render_table(pdf: DocPDF, rows: list[list[str]]):
    """Render a table that fits within margins."""
    if not rows or not rows[0]:
        return
    col_widths = _compute_col_widths(rows)
    for ri, row in enumerate(rows):
        if pdf.get_y() + 7 > 297 - BOTTOM_MARGIN:
            pdf.add_page()
        _render_table_row(pdf, row, col_widths, is_header=(ri == 0), row_index=ri)
    pdf.ln(3)


@dataclass
class _TextStyle:
    """Groups formatting options for _write_wrapped."""
    font: str = "Helvetica"
    style: str = ""
    size: float = 9
    color: tuple = BODY
    indent: float = 0
    line_h: float = 5.5


def _write_wrapped(pdf: DocPDF, text: str, fmt: _TextStyle | None = None):
    """Write text that wraps within margins."""
    fmt = fmt or _TextStyle()
    pdf.set_font(fmt.font, fmt.style, fmt.size)
    pdf.set_text_color(*fmt.color)
    effective_w = CONTENT_W - fmt.indent
    if fmt.indent > 0:
        pdf.set_x(LEFT_MARGIN + fmt.indent)
    pdf.multi_cell(effective_w, fmt.line_h, text)


# ── Line renderers (one per markdown element type) ───────────────

def _render_h1(pdf: DocPDF, text: str):
    if pdf.get_y() > 60:
        pdf.add_page()
    else:
        pdf.ln(6)
    pdf.set_fill_color(*ACCENT)
    pdf.rect(LEFT_MARGIN, pdf.get_y(), 4, 14, "F")
    pdf.set_x(LEFT_MARGIN + 8)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*ACCENT)
    pdf.cell(CONTENT_W - 8, 14, text)
    pdf.ln(16)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.4)
    pdf.line(LEFT_MARGIN, pdf.get_y(), LEFT_MARGIN + 60, pdf.get_y())
    pdf.ln(6)


def _render_h2(pdf: DocPDF, text: str):
    pdf.ensure_space(255)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*HEADING2)
    pdf.multi_cell(CONTENT_W, 7, text)
    pdf.ln(2)


def _render_h3(pdf: DocPDF, text: str):
    pdf.ensure_space(260)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*HEADING3)
    pdf.multi_cell(CONTENT_W, 6, text)
    pdf.ln(2)


def _render_numbered(pdf: DocPDF, num: str, text: str):
    pdf.ensure_space()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*ACCENT)
    pdf.set_x(LEFT_MARGIN)
    pdf.cell(8, 5.5, f"{num}.")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*BODY)
    pdf.multi_cell(CONTENT_W - 8, 5.5, text)


def _render_bullet(pdf: DocPDF, text: str):
    pdf.ensure_space()
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*ACCENT)
    pdf.set_x(LEFT_MARGIN + 3)
    pdf.cell(5, 5.5, "-")
    pdf.set_text_color(*BODY)
    pdf.multi_cell(CONTENT_W - 8, 5.5, text)


def _render_sub_bullet(pdf: DocPDF, text: str):
    pdf.ensure_space(272)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*BODY_LIGHT)
    pdf.set_x(LEFT_MARGIN + 10)
    pdf.cell(4, 5, "-")
    pdf.multi_cell(CONTENT_W - 14, 5, text)


def _render_hrule(pdf: DocPDF):
    pdf.ln(2)
    pdf.set_draw_color(*RULE_COLOR)
    pdf.set_line_width(0.3)
    pdf.line(LEFT_MARGIN, pdf.get_y(), PAGE_W - RIGHT_MARGIN, pdf.get_y())
    pdf.ln(4)


# ── Line classifier ──────────────────────────────────────────────

_NUM_RE = re.compile(r'^(\d+)\.\s+(.*)')
_SUB_BULLET_RE = re.compile(r'^(\s{2,})[-*]\s+(.*)')


def _process_line(pdf: DocPDF, line: str, stripped: str):
    """Classify a single markdown line and render it."""
    # Headings (most specific first)
    if stripped.startswith("### "):
        return _render_h3(pdf, _clean(stripped[4:]))
    if stripped.startswith("## "):
        return _render_h2(pdf, _clean(stripped[3:]))
    if stripped.startswith("# "):
        return _render_h1(pdf, _clean(stripped[2:]))

    # Numbered list
    m = _NUM_RE.match(stripped)
    if m:
        return _render_numbered(pdf, m.group(1), _clean(m.group(2)))

    # Bullets
    if stripped.startswith("- ") or stripped.startswith("* "):
        return _render_bullet(pdf, _clean(stripped[2:]))

    # Indented sub-bullets (check raw line for leading whitespace)
    m = _SUB_BULLET_RE.match(line)
    if m:
        return _render_sub_bullet(pdf, _clean(m.group(2)))

    # Empty line
    if not stripped:
        pdf.ln(2)
        return

    # Regular paragraph
    pdf.ensure_space()
    _write_wrapped(pdf, _clean(stripped))
    pdf.ln(1.5)


# ── Main builder ─────────────────────────────────────────────────

def _is_header_title_skip(stripped: str, line_index: int) -> bool:
    """Skip the redundant markdown title/version lines (already rendered on cover)."""
    return line_index < 5 and (stripped.startswith("# GymAxis") or stripped.startswith("## Version"))


def _parse_table_cells(stripped: str) -> list[str] | None:
    """Return table cell list if line is a table row, otherwise None. Returns [] for separator rows."""
    if not (stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:]):
        return None
    cells = [_clean(c.strip()) for c in stripped.split("|")[1:-1]]
    if all(re.match(r'^[-:]+$', c) for c in cells):
        return []  # separator — ignore
    return cells


class _BodyRenderState:
    """Tiny state container so table-buffering helpers can flush cleanly."""
    def __init__(self) -> None:
        self.in_table: bool = False
        self.rows: list[list[str]] = []

    def flush(self, pdf) -> None:
        if self.rows:
            _render_table(pdf, self.rows)
        self.in_table = False
        self.rows = []


def _handle_table_cells(state: _BodyRenderState, cells: list[str]) -> None:
    """Buffer a non-separator table row into the current state."""
    if not cells:
        return
    if not state.in_table:
        state.in_table = True
        state.rows = []
    state.rows.append(cells)


def _process_body_line(pdf, state: _BodyRenderState, line: str, stripped: str, index: int) -> None:
    """Dispatch a single markdown body line to the right renderer."""
    if _is_header_title_skip(stripped, index):
        return
    if stripped == "---":
        if state.in_table:
            state.flush(pdf)
        _render_hrule(pdf)
        return
    cells = _parse_table_cells(stripped)
    if cells is not None:
        _handle_table_cells(state, cells)
        return
    if state.in_table:
        state.flush(pdf)
    _process_line(pdf, line, stripped)


def _process_body_lines(pdf, lines: list[str]) -> None:
    """Walk the markdown body lines, handling horizontal rules, tables, and regular prose."""
    state = _BodyRenderState()
    for i, line in enumerate(lines):
        _process_body_line(pdf, state, line, line.strip(), i)
    if state.in_table:
        state.flush(pdf)


def _build_pdf() -> bytes:
    """Parse markdown documentation and build the full PDF."""
    pdf = DocPDF()
    _render_cover(pdf)
    pdf._is_cover = False
    pdf.add_page()

    lines = DOCS_PATH.read_text(encoding="utf-8").split("\n")
    _process_body_lines(pdf, lines)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ── API endpoint ─────────────────────────────────────────────────

@router.get("/platform-docs/pdf")
async def download_platform_docs_pdf():
    """Generate and return the platform documentation as a PDF."""
    return Response(
        content=_build_pdf(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=GymAxis_AI_Platform_Documentation.pdf",
            "Cache-Control": "no-cache",
        },
    )
