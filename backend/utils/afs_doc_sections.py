"""Aftersales document reading for large files: split a document into bounded, labelled sections
(PDF pages, worksheet rows, CSV rows, Word blocks) so nothing past an arbitrary character limit is
silently dropped. Each section is interpreted separately and the caller merges the results
deterministically; `coverage` reports exactly what was read."""
from __future__ import annotations

import base64
import csv
import io

from fastapi import HTTPException

SECTION_CHARS = 30000
MAX_VISION_PAGES = 60          # scanned pages read with vision; any beyond are reported, never hidden
VISION_BATCH = 10


def _pack(blocks: list[tuple[str, str]], max_chars: int) -> list[dict]:
    """Group (ref, text) blocks into sections under max_chars, keeping first/last ref as the label."""
    out, cur, size, first, last = [], [], 0, None, None
    for ref, text in blocks:
        text = text.strip()
        if not text:
            continue
        while len(text) > max_chars:  # one oversized block → split, never truncate
            out.append({"label": ref, "text": text[:max_chars]})
            text = text[max_chars:]
        if size + len(text) > max_chars and cur:
            out.append({"label": first if first == last else f"{first} – {last}", "text": "\n".join(cur)})
            cur, size, first = [], 0, None
        first = first or ref
        last = ref
        cur.append(text)
        size += len(text) + 1
    if cur:
        out.append({"label": first if first == last else f"{first} – {last}", "text": "\n".join(cur)})
    return out


def pdf_pages(data: bytes) -> list[str]:
    import fitz
    with fitz.open(stream=data, filetype="pdf") as doc:
        return [page.get_text("text") or "" for page in doc]


def page_images(data: bytes, page_numbers: list[int]) -> list[str]:
    import fitz
    from PIL import Image
    out = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for n in page_numbers:
            pix = doc[n - 1].get_pixmap(dpi=120)
            img = Image.frombytes("RGB" if pix.n < 4 else "RGBA", [pix.width, pix.height], pix.samples).convert("RGB")
            if img.width > 1000:
                img = img.resize((1000, int(img.height * 1000 / img.width)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_document(filename: str, data: bytes, max_chars: int = SECTION_CHARS) -> dict:
    """→ {"kind", "sections": [{label, text}], "vision_batches": [[page,...]], "coverage": {...}}"""
    name = (filename or "").lower()
    cov: dict = {"unread": [], "notes": []}
    try:
        if name.endswith(".pdf") or data[:4] == b"%PDF":
            pages = pdf_pages(data)
            blocks, scanned = [], []
            for i, t in enumerate(pages, 1):
                (blocks.append((f"page {i}", f"=== Page {i} ===\n{t}")) if len(t.strip()) >= 30 else scanned.append(i))
            vision = scanned[:MAX_VISION_PAGES]
            if len(scanned) > MAX_VISION_PAGES:
                cov["unread"] = scanned[MAX_VISION_PAGES:]
                cov["notes"].append(f"{len(cov['unread'])} scanned page(s) beyond the first {MAX_VISION_PAGES} were not read")
            cov.update(pages_total=len(pages), pages_text=len(pages) - len(scanned), pages_scanned=len(vision))
            return {"kind": "pdf", "sections": _pack(blocks, max_chars),
                    "vision_batches": [vision[i:i + VISION_BATCH] for i in range(0, len(vision), VISION_BATCH)], "coverage": cov}
        if name.endswith((".xlsx", ".xlsm")):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            blocks, rows = [], 0
            for ws in wb.worksheets:
                for r, row in enumerate(ws.iter_rows(values_only=True), 1):
                    cells = [str(c).strip() for c in row if c not in (None, "")]
                    if cells:
                        rows += 1
                        blocks.append((f"{ws.title}!row {r}", f"[{ws.title} row {r}] " + " | ".join(cells)))
            cov.update(sheets=[ws.title for ws in wb.worksheets], rows=rows)
            return {"kind": "xlsx", "sections": _pack(blocks, max_chars), "vision_batches": [], "coverage": cov}
        if name.endswith(".csv") or name.endswith(".txt"):
            text = _decode(data)
            blocks, bad = [], 0
            reader = csv.reader(io.StringIO(text))
            header = None
            for r, row in enumerate(reader, 1):
                cells = [c.strip() for c in row]
                if not any(cells):
                    continue
                if header is None:
                    header = cells
                elif len(cells) != len(header):
                    bad += 1
                blocks.append((f"row {r}", f"[row {r}] " + " | ".join(cells)))
            cov.update(rows=len(blocks), malformed_rows=bad, header=header or [])
            if bad:
                cov["notes"].append(f"{bad} row(s) have a different number of columns from the header — check them")
            return {"kind": "csv", "sections": _pack(blocks, max_chars), "vision_batches": [], "coverage": cov}
        if name.endswith(".docx"):
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            doc = Document(io.BytesIO(data))
            blocks, heading, tables = [], "start", 0
            for el in doc.element.body.iterchildren():
                if el.tag.endswith("}p"):
                    p = Paragraph(el, doc)
                    if p.style is not None and (p.style.name or "").lower().startswith("heading") and p.text.strip():
                        heading = p.text.strip()[:80]
                    blocks.append((heading, p.text))
                elif el.tag.endswith("}tbl"):
                    tables += 1
                    rows = [" | ".join(c.text.strip() for c in row.cells) for row in Table(el, doc).rows]
                    blocks.append((heading, f"[Table {tables} under '{heading}']\n" + "\n".join(rows)))
            cov.update(tables=tables, blocks=len(blocks))
            return {"kind": "docx", "sections": _pack(blocks, max_chars), "vision_batches": [], "coverage": cov}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not read that document ({type(exc).__name__}). Try a text-based PDF, Excel, CSV or Word file.")
    raise HTTPException(415, "File type not supported — use PDF, Excel (.xlsx), CSV or Word (.docx).")
