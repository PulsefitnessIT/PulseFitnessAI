"""Pulse Fitness AI — parse a dropped email into clean text + usable images.

Supports raw .eml, Outlook .msg, HTML, plain text, PDF and image screenshots.
Returns a normalised dict the comms AI assistant can rebuild into blocks.
"""
from __future__ import annotations

import base64
import logging
from email import message_from_bytes
from email import policy

logger = logging.getLogger("email_ingest")

_IMG_EXT = ("png", "jpg", "jpeg", "webp", "gif", "bmp")


def _ext(name: str) -> str:
    name = (name or "").lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _html_to_parts(html: str) -> tuple[str, list]:
    """Return (plain_text, [{url, alt}]) from an HTML body."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html or "", []
    soup = BeautifulSoup(html or "", "lxml")
    images = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        alt = (img.get("alt") or "").strip()
        if src.startswith("http://") or src.startswith("https://"):
            images.append({"url": src, "alt": alt})
    # subject hint from <title>
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return text, images


def parse_email(file_bytes: bytes | None, filename: str, pasted_text: str = "",
                content_type: str = "") -> dict:
    """Normalise any supported input.

    Returns: {text, images:[{url,alt}], image_b64, file_path, file_mime,
              embedded_image_count, kind}
    """
    out = {"text": "", "images": [], "image_b64": None, "file_path": None,
           "file_mime": None, "embedded_image_count": 0, "kind": "text"}

    ext = _ext(filename)
    ctype = (content_type or "").lower()

    # 1. Pasted text / HTML (no file)
    if not file_bytes:
        txt = pasted_text or ""
        if "<" in txt and ">" in txt and ("</" in txt or "/>" in txt):
            out["text"], out["images"] = _html_to_parts(txt)
            out["kind"] = "html"
        else:
            out["text"] = txt
            out["kind"] = "text"
        return out

    # 2. Image screenshot → vision
    if ext in _IMG_EXT or ctype.startswith("image/"):
        out["image_b64"] = base64.b64encode(file_bytes).decode("ascii")
        out["kind"] = "image"
        return out

    # 3. PDF → vision/file content
    if ext == "pdf" or ctype == "application/pdf":
        import os
        import tempfile
        tmp = tempfile.mkdtemp(prefix="emailpdf_")
        path = os.path.join(tmp, "email.pdf")
        with open(path, "wb") as fh:
            fh.write(file_bytes)
        out["file_path"] = path
        out["file_mime"] = "application/pdf"
        out["kind"] = "pdf"
        # best-effort text extraction too
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            out["text"] = "\n".join((p.extract_text() or "") for p in reader.pages)[:18000]
        except Exception:
            pass
        return out

    # 4. Outlook .msg
    if ext == "msg":
        try:
            import extract_msg
            import io
            m = extract_msg.Message(io.BytesIO(file_bytes))
            html = ""
            try:
                hb = m.htmlBody
                html = hb.decode("utf-8", "ignore") if isinstance(hb, bytes) else (hb or "")
            except Exception:
                html = ""
            if html:
                out["text"], out["images"] = _html_to_parts(html)
            else:
                out["text"] = m.body or ""
            try:
                out["embedded_image_count"] = sum(
                    1 for a in (m.attachments or [])
                    if _ext(getattr(a, "longFilename", "") or getattr(a, "shortFilename", "")) in _IMG_EXT
                )
            except Exception:
                pass
            out["kind"] = "msg"
            if out["text"].strip():
                return out
        except Exception as exc:
            logger.warning("[email_ingest] .msg parse failed: %s", exc)

    # 5. Raw .eml (default for everything else / message types)
    try:
        msg = message_from_bytes(file_bytes, policy=policy.default)
        html_body, text_body = None, None
        embedded = 0
        for part in msg.walk():
            ctype_part = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype_part == "text/html" and html_body is None and "attachment" not in disp:
                try:
                    html_body = part.get_content()
                except Exception:
                    html_body = None
            elif ctype_part == "text/plain" and text_body is None and "attachment" not in disp:
                try:
                    text_body = part.get_content()
                except Exception:
                    text_body = None
            elif ctype_part.startswith("image/"):
                embedded += 1
        subject = msg.get("Subject", "")
        if html_body:
            text, images = _html_to_parts(html_body)
        else:
            text, images = (text_body or ""), []
        if subject:
            text = f"Subject: {subject}\n\n{text}"
        out["text"] = text
        out["images"] = images
        out["embedded_image_count"] = embedded
        out["kind"] = "eml"
        return out
    except Exception as exc:
        logger.warning("[email_ingest] .eml parse failed: %s", exc)

    # 6. Fallback: treat bytes as html/plain text
    try:
        decoded = file_bytes.decode("utf-8", "ignore")
    except Exception:
        decoded = ""
    if "<" in decoded and ">" in decoded:
        out["text"], out["images"] = _html_to_parts(decoded)
        out["kind"] = "html"
    else:
        out["text"] = decoded
    return out
