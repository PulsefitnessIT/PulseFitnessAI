"""Iter 220by — Public Security Document (HTML / TXT / PDF).

Covers:

  1. JSON endpoint returns markdown + rendered HTML + download
     links shape, all derived from the canonical `/app/SECURITY.md`.
  2. TXT endpoint returns the markdown source verbatim with the
     `text/plain` content-type and an `inline` Content-Disposition.
  3. PDF endpoint returns a valid PDF (starts with %PDF-) with the
     `attachment` Content-Disposition.
  4. Public no-auth: every endpoint is reachable without a token.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from server import app


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _client():
    """ASGI client — runs the FastAPI app in-memory, no live server."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


# ══════════════════ 1 · JSON ═════════════════════════════════════════


def test_security_document_json_shape():
    async def go():
        async with _client() as c:
            r = await c.get("/api/security/document")
            return r

    r = _run(go())
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) >= {
        "markdown", "html", "source_filename", "generated_at", "downloads",
    }
    assert data["source_filename"] == "SECURITY.md"
    assert data["markdown"].startswith("# GymAxis AI — Security")
    # markdown2 turns the heading into an <h1>
    assert "<h1" in data["html"]
    # Table converted to HTML
    assert "<table" in data["html"]
    # Download links present
    assert data["downloads"]["pdf"].endswith(".pdf")
    assert data["downloads"]["txt"].endswith(".txt")
    # Cache headers — same policy as /security/manifest
    assert "public" in r.headers.get("cache-control", "")


# ══════════════════ 2 · TXT ══════════════════════════════════════════


def test_security_document_txt_serves_inline():
    async def go():
        async with _client() as c:
            return await c.get("/api/security/document.txt")

    r = _run(go())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    # `inline` so the browser doesn't force a download.
    assert "inline" in r.headers.get("content-disposition", "")
    # Body is the markdown source verbatim.
    assert r.text.startswith("# GymAxis AI — Security")


# ══════════════════ 3 · PDF ══════════════════════════════════════════


def test_security_document_pdf_returns_valid_binary():
    async def go():
        async with _client() as c:
            return await c.get("/api/security/document.pdf")

    r = _run(go())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers.get("content-disposition", "")
    # Sanity — fpdf2 always opens with "%PDF-".
    assert r.content[:5] == b"%PDF-"
    # Not a 1-page stub — real content runs ≥ 4 KB.
    assert len(r.content) > 3000


# ══════════════════ 4 · Public (no auth) ═════════════════════════════


@pytest.mark.parametrize("path", [
    "/api/security/document",
    "/api/security/document.txt",
    "/api/security/document.pdf",
])
def test_security_document_endpoints_are_public(path):
    """No Authorization header → must still return 200."""
    async def go():
        async with _client() as c:
            return await c.get(path)

    r = _run(go())
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
