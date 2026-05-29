"""Public Security Document — HTML / TXT / PDF renderings of `/app/SECURITY.md`.

Iter 220by — replaces the broken `https://github.com/gymaxis/security`
link on the marketing /security page. Procurement and IT teams expect
the document in three formats:

* `GET /api/security/document`          → JSON `{markdown, html, ...}`
                                           for the in-browser page
* `GET /api/security/document.txt`      → plain text, served inline
* `GET /api/security/document.pdf`      → brandable PDF download

All three derive from the same canonical source file
(`/app/SECURITY.md`) so they cannot drift. Cached at the CDN edge for
5 minutes so a viral pen-test thread doesn't hammer the renderer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from utils.security import rate_limit_by_ip

logger = logging.getLogger(__name__)

router = APIRouter()

# Canonical source — committed at the repo root next to /app/backend.
SECURITY_DOC_PATH = Path(__file__).parent.parent.parent / "SECURITY.md"

# Shared cache headers — same policy as /security/manifest.
_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=300, s-maxage=600",
    "CDN-Cache-Control": "public, max-age=600",
    "Surrogate-Control": "public, max-age=600",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_markdown() -> str:
    try:
        return SECURITY_DOC_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        logger.error("SECURITY.md missing at %s", SECURITY_DOC_PATH)
        raise HTTPException(500, "Security document not found") from exc


def _render_html(markdown_text: str) -> str:
    """Convert the markdown source to safe inline HTML for the
    in-browser page. ``markdown2`` is already a backend dependency."""
    import markdown2
    return markdown2.markdown(
        markdown_text,
        extras=[
            "fenced-code-blocks", "tables", "header-ids",
            "strike", "task_list", "break-on-newline",
        ],
    )


# ── JSON (drives the /security/details React page) ──────────────────


@router.get("/security/document")
async def get_security_document(request: Request, response: Response) -> dict:
    """Return the SECURITY.md source + rendered HTML so the React
    page can paint without a second round-trip."""
    rate_limit_by_ip(request, max_requests=30, window_seconds=60)
    for k, v in _CACHE_HEADERS.items():
        response.headers[k] = v
    response.headers.setdefault("Vary", "Accept-Encoding")
    md = _read_markdown()
    return {
        "markdown": md,
        "html": _render_html(md),
        "source_filename": "SECURITY.md",
        "generated_at": _now_iso(),
        "downloads": {
            "pdf": "/api/security/document.pdf",
            "txt": "/api/security/document.txt",
        },
    }


# ── Plain text (inline) ──────────────────────────────────────────────


@router.get("/security/document.txt")
async def get_security_document_txt(request: Request) -> Response:
    rate_limit_by_ip(request, max_requests=30, window_seconds=60)
    md = _read_markdown()
    return Response(
        content=md,
        media_type="text/plain; charset=utf-8",
        headers={
            **_CACHE_HEADERS,
            # `inline` (not `attachment`) so it opens in-browser.
            "Content-Disposition": 'inline; filename="GymAxis_Security.txt"',
        },
    )


# ── PDF download ─────────────────────────────────────────────────────


def _build_pdf(markdown_text: str) -> bytes:
    """Render the markdown to a branded A4 PDF. Re-uses the helpers
    in ``routes.docs_export`` so the visual style matches the platform
    documentation export."""
    from routes.docs_export import (
        DocPDF, _process_body_lines, _sanitize,
        ACCENT, BODY_LIGHT, WHITE, COVER_BG,
    )

    pdf = DocPDF()
    # Custom cover overlay so the doc isn't mislabelled "Platform
    # Documentation" — we keep the same chrome but swap the title.
    pdf.add_page()
    pdf._is_cover = True
    pdf.set_fill_color(*COVER_BG)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 100, 210, 3, "F")

    pdf.set_y(115)
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 16, "Security", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 10, _sanitize("GymAxis AI — Posture & Hardening"),
             align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 7, _sanitize(f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y')}"),
             align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 195, 210, 1, "F")

    pdf.set_y(210)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, _sanitize("Procurement and IT teams can verify the live posture at"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _sanitize("/api/security/manifest and /.well-known/security.txt."),
             align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(260)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*BODY_LIGHT)
    pdf.cell(0, 5, _sanitize("GymAxis AI Ltd — security@gymaxisai.com"),
             align="C", new_x="LMARGIN", new_y="NEXT")

    # Body
    pdf._is_cover = False
    pdf.add_page()
    _process_body_lines(pdf, markdown_text.split("\n"))

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


@router.get("/security/document.pdf")
async def get_security_document_pdf(request: Request) -> Response:
    rate_limit_by_ip(request, max_requests=20, window_seconds=60)
    md = _read_markdown()
    pdf_bytes = _build_pdf(md)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            **_CACHE_HEADERS,
            "Content-Disposition": 'attachment; filename="GymAxis_Security.pdf"',
        },
    )
