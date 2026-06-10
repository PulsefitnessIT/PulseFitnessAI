"""Iter 227 — SEC-006: upload content-type validation.

These assert the validator's *behaviour* (accept real images, reject
disguised polyglots) which holds whether libmagic is present or the
pure-Python signature fallback is in use. A separate check confirms the
self-test reports libmagic when the system lib is installed.
"""
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from utils.file_validation import validate_upload, sniff_mime, selftest


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_real_png_accepted():
    mime = validate_upload(
        file_bytes=_png_bytes(), filename="photo.png",
        allowed=["image/png", "image/jpeg"],
    )
    assert mime == "image/png"


def test_html_disguised_as_png_rejected():
    html = b"<html><script>alert(1)</script></html>" + b" " * 64
    with pytest.raises(HTTPException) as exc:
        validate_upload(
            file_bytes=html, filename="evil.png",
            allowed=["image/png", "image/jpeg"],
        )
    assert exc.value.status_code == 415


def test_forbidden_extension_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_upload(
            file_bytes=_png_bytes(), filename="payload.svg",
            allowed=["image/png"],
        )
    # .svg is in the forbidden-extension list (defence in depth).
    assert exc.value.status_code in (415, 400)


def test_pdf_sniffed():
    assert "pdf" in sniff_mime(b"%PDF-1.4\n%test\n%%EOF\n").lower()


def test_selftest_shape():
    res = selftest()
    assert "enabled" in res
    # When libmagic is wired (prod target), it reports the detected mime.
    if res["enabled"]:
        assert "pdf" in (res.get("detected") or "").lower()
