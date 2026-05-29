"""Iter 220by — Public Security Document (HTML / TXT / PDF).

Covers:

  1. JSON endpoint returns markdown + rendered HTML + download
     links shape, all derived from the canonical `/app/SECURITY.md`.
  2. TXT endpoint returns the markdown source verbatim with the
     `text/plain` content-type and an `inline` Content-Disposition.
  3. PDF endpoint returns a valid PDF (starts with %PDF-) with the
     `attachment` Content-Disposition.
  4. Public no-auth: the route doesn't depend on any auth dependency.

We mount only the security_document router on a throwaway FastAPI
app so this test file never imports `server.py` — important because
the full app pulls in the Stripe SDK whose payments submodule isn't
guaranteed to be importable on every regression env.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from routes.security_document import router as security_document_router


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _app():
    """Throwaway FastAPI app — only the security_document router."""
    a = FastAPI()
    a.include_router(security_document_router)
    return a


def _client(a):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=a),
        base_url="http://test",
    )


# ══════════════════ 1 · JSON ═════════════════════════════════════════


def test_security_document_json_shape():
    a = _app()

    async def go():
        async with _client(a) as c:
            return await c.get("/security/document")

    r = _run(go())
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) >= {
        "markdown", "html", "source_filename", "generated_at", "downloads",
    }
    assert data["source_filename"] == "SECURITY.md"
    assert data["markdown"].startswith("# GymAxis AI — Security")
    assert "<h1" in data["html"]
    assert "<table" in data["html"]
    assert data["downloads"]["pdf"].endswith(".pdf")
    assert data["downloads"]["txt"].endswith(".txt")
    assert "public" in r.headers.get("cache-control", "")


# ══════════════════ 2 · TXT ══════════════════════════════════════════


def test_security_document_txt_serves_inline():
    a = _app()

    async def go():
        async with _client(a) as c:
            return await c.get("/security/document.txt")

    r = _run(go())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert "inline" in r.headers.get("content-disposition", "")
    assert r.text.startswith("# GymAxis AI — Security")


# ══════════════════ 3 · PDF ══════════════════════════════════════════


def test_security_document_pdf_returns_valid_binary():
    a = _app()

    async def go():
        async with _client(a) as c:
            return await c.get("/security/document.pdf")

    r = _run(go())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 3000


# ══════════════════ 4 · Public (no auth) ═════════════════════════════


@pytest.mark.parametrize("path", [
    "/security/document",
    "/security/document.txt",
    "/security/document.pdf",
])
def test_security_document_endpoints_are_public(path):
    a = _app()

    async def go():
        async with _client(a) as c:
            return await c.get(path)

    r = _run(go())
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
