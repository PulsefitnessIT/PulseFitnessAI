"""Document text extraction (Iter 216h101 — Tender Engine v2).

Turns raw uploaded PDF/Word/Excel bytes into clean searchable text so
the tender AI can read what it's been given. Used by:

* ``crm_v2.upload_tender_doc``  — extracts on upload, persists alongside
  the binary blob.
* ``crm_v2.upload_kb_doc``      — same, for the bid library.

Strategy: text-first (pypdf / python-docx / openpyxl). Image-heavy
scanned PDFs that yield <40 chars of text are NOT auto-OCR'd in this
release — the UI surfaces a warning instead so the operator can paste
the text manually (vision fallback can be added later without changing
this API).
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_pdf(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        parts: list[str] = []
        # Cap at first 60 pages — runaway 500-pager PDFs would otherwise
        # blow the request timeout. 60 pages comfortably covers every
        # PQQ/ITT we've seen historically.
        for page in reader.pages[:60]:
            try:
                parts.append(page.extract_text() or "")
            except Exception as e:
                logger.debug(f"pdf page extract failed: {e}")
        return "\n\n".join(p.strip() for p in parts if p.strip())
    except Exception as e:
        logger.warning(f"pdf extraction failed: {e}")
        return ""


def _extract_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        # Tables — common in tender response forms — are flattened
        # row by row, cell by cell.
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        return "\n".join(paragraphs)
    except Exception as e:
        logger.warning(f"docx extraction failed: {e}")
        return ""


def _extract_xlsx(data: bytes) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        parts: list[str] = []
        for sheet in wb.sheetnames[:20]:  # cap sheets
            ws = wb[sheet]
            parts.append(f"# {sheet}")
            for row in ws.iter_rows(values_only=True, max_row=500):
                cells = [str(v) for v in row if v is not None and str(v).strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"xlsx extraction failed: {e}")
        return ""


def _extract_plain(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""


def extract_text(filename: str, content_type: Optional[str], data: bytes) -> str:
    """Best-effort plain-text extraction for tender documents.

    Returns an empty string for unsupported formats (UI surfaces a
    "couldn't extract text" warning when this happens).
    """
    if not data:
        return ""
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".pdf") or "pdf" in ct:
        return _extract_pdf(data)
    if name.endswith(".docx") or "wordprocessingml" in ct:
        return _extract_docx(data)
    if name.endswith(".xlsx") or "spreadsheetml" in ct:
        return _extract_xlsx(data)
    if name.endswith(".txt") or name.endswith(".md") or "text/" in ct:
        return _extract_plain(data)
    return ""


# ── Chunking + retrieval (no vector DB — lightweight TF lookup) ─────


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Split into overlapping windows for retrieval.

    1200 chars ≈ 200 words ≈ one PQQ paragraph. Overlap of 150 chars
    keeps key bridging sentences in both neighbouring chunks so we
    don't drop evidence at the seam.
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + chunk_size])
        i += chunk_size - overlap
    return chunks


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "we", "our", "your", "you", "this", "their", "they",
    "do", "have", "or", "but", "not", "if", "than", "then", "so", "such",
}


def _tokens(s: str) -> list[str]:
    out: list[str] = []
    word: list[str] = []
    for ch in s.lower():
        if ch.isalnum():
            word.append(ch)
        else:
            if word:
                w = "".join(word)
                if len(w) > 2 and w not in _STOPWORDS:
                    out.append(w)
                word = []
    if word:
        w = "".join(word)
        if len(w) > 2 and w not in _STOPWORDS:
            out.append(w)
    return out


def retrieve_relevant(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Score candidate chunks against the query using simple keyword
    overlap + IDF-ish weighting. Good-enough retrieval without
    pinecone / Atlas Vector Search.

    Each candidate must have a ``text`` field. The returned list is
    enriched with a ``score`` value and sorted descending.
    """
    if not query or not candidates:
        return []
    q_tokens = _tokens(query)
    if not q_tokens:
        return candidates[:top_k]
    # Document frequency for IDF.
    df: dict[str, int] = {}
    for c in candidates:
        seen = set(_tokens(c.get("text", "")))
        for t in seen:
            df[t] = df.get(t, 0) + 1
    n = len(candidates) or 1
    scored: list[tuple[float, dict]] = []
    for c in candidates:
        c_tokens = _tokens(c.get("text", ""))
        if not c_tokens:
            continue
        # Simple weighted sum: each query token contributes log(N/df+1).
        score = 0.0
        c_set = set(c_tokens)
        for qt in q_tokens:
            if qt in c_set:
                import math
                score += math.log((n + 1) / (df.get(qt, 1)))
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{**c, "score": round(s, 2)} for s, c in scored[:top_k]]
