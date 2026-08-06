"""Render the first page of a .docx as a PNG thumbnail (LibreOffice → PDF → PyMuPDF).

Used by the CRM Tender Submission Pack Wizard so bidders can eyeball the cover
page (true house style — headers/footers/logo/fonts) before downloading.
"""
from __future__ import annotations
import os
import shutil
import tempfile
import subprocess

import fitz  # PyMuPDF


def render_docx_first_page_png(docx_bytes: bytes, zoom: float = 1.6) -> bytes:
    """Convert docx bytes to a PNG of page 1. Raises on failure."""
    pages = render_docx_pages_png(docx_bytes, max_pages=1, zoom=zoom)
    if not pages:
        raise RuntimeError("No pages rendered")
    return pages[0]


def render_docx_pages_png(docx_bytes: bytes, max_pages: int = 6, zoom: float = 1.6) -> list[bytes]:
    """Convert docx bytes to a list of PNGs (first ``max_pages`` pages).
    One LibreOffice conversion; PyMuPDF then renders each page. Raises on failure."""
    tmp = tempfile.mkdtemp(prefix="docxprev_")
    try:
        docx_path = os.path.join(tmp, "in.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
        profile = os.path.join(tmp, "profile")
        cmd = [
            "soffice", "--headless", "--norestore", "--invisible", "--nodefault",
            "--nologo", "--nofirststartwizard",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", "pdf", "--outdir", tmp, docx_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
        pdf_path = os.path.join(tmp, "in.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("PDF conversion produced no output")
        doc = fitz.open(pdf_path)
        try:
            out: list[bytes] = []
            n = min(len(doc), max(1, max_pages))
            for i in range(n):
                pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                out.append(pix.tobytes("png"))
            return out
        finally:
            doc.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

