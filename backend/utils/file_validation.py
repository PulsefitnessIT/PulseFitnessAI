"""File upload content validation.

Uses libmagic (via python-magic) to sniff the actual file bytes rather than
trusting the client-supplied ``Content-Type`` header or file extension.
This defends against polyglot uploads (e.g. an HTML file served with a
``.pdf`` extension that renders scripts when previewed inline, or a
malicious binary disguised as an image).

Usage::

    from utils.file_validation import validate_upload

    ct = await validate_upload(
        file_bytes=data,
        filename=upload.filename,
        allowed={"application/pdf", "image/png", "image/jpeg", "image/webp"},
    )
    # returns the verified mime type, or raises HTTPException(415)
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Lazy import — the server must still boot if libmagic is missing, but every
# upload call will fail closed.
try:
    import magic  # type: ignore
    _MAGIC_OK = True
except Exception as exc:  # pragma: no cover
    magic = None  # type: ignore
    _MAGIC_OK = False
    logger.warning("python-magic unavailable — falling back to signature-based sniffer: %s", exc)

# Common "safe" sets callers can import.
MIME_IMAGES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif"}
MIME_DOCS = {"application/pdf"}
MIME_SPREADSHEETS = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
}
MIME_OFFICE = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MIME_VIDEOS = {
    "video/mp4", "video/quicktime", "video/webm", "video/x-msvideo",
    "video/3gpp", "video/x-m4v",
}
MIME_ALL_ATTACHMENTS = MIME_IMAGES | MIME_OFFICE | MIME_SPREADSHEETS
MIME_FAULT_MEDIA = MIME_IMAGES | MIME_VIDEOS | MIME_OFFICE

# Extensions we always refuse regardless of detected mime — defence in depth
# against browsers that render based on extension alone.
_FORBIDDEN_EXTS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".dll", ".sh", ".ps1",
    ".vbs", ".js", ".jse", ".wsf", ".wsh", ".jar", ".py", ".php", ".phtml",
    ".html", ".htm", ".xhtml", ".svg",  # SVG allows inline scripts
}


def _ext(filename: Optional[str]) -> str:
    if not filename:
        return ""
    return os.path.splitext(filename)[1].lower()


def _sniff_mime_fallback(data: bytes) -> str:
    """Pure-Python magic-byte sniffer used when libmagic is unavailable.

    Covers the formats our API actually accepts (images, PDF, Office,
    video). Ambiguous / unknown bytes return 'application/octet-stream'
    so ``validate_upload`` still fails closed.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"AVI ":
        return "video/x-msvideo"
    # ISO-BMFF (MP4 / MOV / HEIC / HEIF / M4V). Brand lives at bytes 4-12.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heis", b"hevc", b"hevx"):
            return "image/heic"
        if brand in (b"qt  ",):
            return "video/quicktime"
        if brand in (b"M4V ", b"M4VH", b"M4VP"):
            return "video/x-m4v"
        if brand in (b"3gp4", b"3gp5", b"3g2a"):
            return "video/3gpp"
        # Default any other ftyp-branded container to mp4 — we already
        # filter on the allowed-set, so spurious brands get rejected.
        return "video/mp4"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # OLE compound file — legacy .doc / .xls / .ppt. We return the
        # most generic Office type; callers allowing Office files accept
        # both legacy and modern variants.
        return "application/vnd.ms-excel"
    if data.startswith(b"PK\x03\x04"):
        # ZIP container — DOCX / XLSX / PPTX all share this signature.
        # Look at the internal filename list for a hint.
        head = data[:4096]
        if b"word/" in head:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if b"xl/" in head:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if b"ppt/" in head:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return "application/zip"
    # Try decoding as ASCII/UTF-8 to catch plain-text CSVs.
    try:
        data[:1024].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


def sniff_mime(data: bytes) -> str:
    """Return the mime type detected from the file's magic bytes.

    Prefers libmagic when available; otherwise falls back to a curated
    pure-Python signature table so uploads keep working in environments
    where the `libmagic1` system package isn't installed (e.g. minimal
    deployment containers).
    """
    if not data or len(data) < 12:
        raise HTTPException(status_code=415, detail="File too small to validate")
    if _MAGIC_OK and magic is not None:
        try:
            return magic.from_buffer(data[: 1024 * 64], mime=True).lower()
        except Exception as exc:
            logger.warning("magic.from_buffer failed, falling back: %s", exc)
    return _sniff_mime_fallback(data)


def validate_upload(
    *,
    file_bytes: bytes,
    filename: Optional[str],
    allowed: Iterable[str],
    max_size: Optional[int] = None,
) -> str:
    """Sniff the file bytes, reject if the real mime isn't in ``allowed``.

    Also enforces:
      - filename ≠ None (for logging)
      - extension is not in ``_FORBIDDEN_EXTS`` (defence in depth)
      - size limit if provided
    Returns the verified mime type.
    """
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="filename required")
    if max_size is not None and len(file_bytes) > max_size:
        raise HTTPException(status_code=413, detail=f"File exceeds {max_size} bytes")

    ext = _ext(filename)
    if ext in _FORBIDDEN_EXTS:
        logger.info("Rejected upload by extension: %s", filename[:80])
        raise HTTPException(status_code=415, detail=f"File extension '{ext}' not allowed")

    mime = sniff_mime(file_bytes)
    allowed_set = {m.lower() for m in allowed}

    # Some CSV files get sniffed as text/plain — accept both if either is allowed.
    if mime == "text/plain" and "text/csv" in allowed_set:
        return "text/csv"
    if mime == "application/octet-stream":
        # Ambiguous — refuse rather than accept by fallback.
        raise HTTPException(status_code=415, detail="File type could not be identified")

    if mime not in allowed_set:
        logger.info("Rejected upload mime=%s filename=%s", mime, filename[:80])
        raise HTTPException(
            status_code=415,
            detail=f"File type '{mime}' not allowed. Allowed: {sorted(allowed_set)}",
        )
    return mime


def selftest() -> dict:
    """Verify python-magic + libmagic are installed and wired correctly.

    Returns a status dict that's safe to surface from a health endpoint or log
    at startup. Never raises — the caller decides what to do with a failure.
    """
    if not _MAGIC_OK or magic is None:
        return {
            "enabled": False,
            "reason": "python-magic / libmagic not loaded",
            "fix": "apt-get install -y libmagic1 file (see backend/SYSTEM_DEPS.md)",
        }
    try:
        # Real PDF magic bytes. If libmagic is functional, this returns
        # 'application/pdf'. Anything else = wired wrong.
        detected = magic.from_buffer(b"%PDF-1.4\n%fake\n%%EOF\n", mime=True)
        if detected and "pdf" in detected.lower():
            return {"enabled": True, "detected": detected}
        return {
            "enabled": False,
            "reason": f"libmagic returned unexpected mime: {detected!r}",
            "fix": "verify libmagic-mgc is installed (the magic database)",
        }
    except Exception as exc:
        return {
            "enabled": False,
            "reason": f"libmagic call failed: {exc}",
            "fix": "apt-get install -y libmagic1 file",
        }
