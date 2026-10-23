"""Shrink uploaded photos: fix rotation, cap the longest side, re-encode as JPEG."""
import io
import logging

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # HEIC support optional
    pass

logger = logging.getLogger(__name__)

MAX_SIDE = 2000
JPEG_QUALITY = 80


def compress_photo(data: bytes) -> bytes | None:
    """Return JPEG bytes, or None if the data isn't a readable image or it was
    already a JPEG that wouldn't get smaller (HEIC/PNG always convert)."""
    try:
        img = Image.open(io.BytesIO(data))
        was_jpeg = img.format == "JPEG"
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        small = out.getvalue()
    except Exception as e:
        logger.info("compress_photo skipped: %s", e)
        return None
    return small if (len(small) < len(data) or not was_jpeg) else None
