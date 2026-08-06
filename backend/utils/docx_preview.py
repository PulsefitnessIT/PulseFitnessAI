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
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return pix.tobytes("png")
        finally:
            doc.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
