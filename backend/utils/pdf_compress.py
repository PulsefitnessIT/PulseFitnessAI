"""PDF compression utility using PyMuPDF.
Compresses PDFs by removing bloat, recompressing images, and deflating streams.
Typically reduces file size by 30-60% with no visible quality loss."""

import fitz
import logging

logger = logging.getLogger(__name__)


def _scrub_metadata(doc: fitz.Document):
    """Strip metadata bloat: thumbnails, XMP data."""
    doc.scrub(
        metadata=False,
        xml_metadata=True,
        attached_files=False,
        embedded_files=False,
        thumbnails=True,
        reset_fields=False,
        reset_responses=False,
    )


def _recompress_images(doc: fitz.Document, quality: int):
    """Downsample and recompress images (biggest space saver)."""
    doc.rewrite_images(
        dpi_threshold=150,
        dpi_target=120,
        quality=quality,
        lossy=True,
        lossless=True,
        color=True,
        gray=True,
    )


def _save_optimised(doc: fitz.Document) -> bytes:
    """Save with maximum garbage collection + stream deflation."""
    return doc.tobytes(
        garbage=4,
        deflate=True,
        use_objstms=True,
    )


def compress_pdf(data: bytes, quality: int = 75) -> bytes:
    """Compress a PDF file's bytes. Returns compressed bytes.

    Args:
        data: Raw PDF file bytes
        quality: JPEG quality for image recompression (1-100).

    Returns:
        Compressed PDF bytes. Falls back to original if compression fails or increases size.
    """
    original_size = len(data)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        _scrub_metadata(doc)
        _recompress_images(doc, quality)
        compressed = _save_optimised(doc)
        doc.close()

        if len(compressed) < original_size:
            savings = round((1 - len(compressed) / original_size) * 100, 1)
            logger.info(f"PDF compressed: {original_size:,} -> {len(compressed):,} bytes ({savings}% saved)")
            return compressed

        logger.info(f"PDF already optimal ({original_size:,} bytes), skipping compression")
        return data
    except Exception as e:
        logger.warning(f"PDF compression failed, using original: {e}")
        return data
