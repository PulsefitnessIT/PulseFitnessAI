"""Marketing downloads — public, no-auth file streams.

Iter 216h302 — exposes the MOD briefing PDF (and any future marketing
collateral) as a direct, downloadable URL so the user doesn't have to
fish it out of GitHub.

Files served from `/app/marketing/`. The route is intentionally public
(no auth, no rate limit) because these are marketing assets the user
wants to be able to forward freely.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/marketing", tags=["marketing"])

MARKETING_ROOT = Path("/app/marketing")

# Whitelist of downloadable files — guards against path traversal.
DOWNLOADS: dict[str, tuple[str, str]] = {
    "mod-briefing.pdf": (
        "mod-presentation/GymAxis_MOD_Briefing.pdf",
        "GymAxis_MOD_Briefing.pdf",
    ),
    # Iter 216h302a — short alias, easier to type on mobile.
    "mod.pdf": (
        "mod-presentation/GymAxis_MOD_Briefing.pdf",
        "GymAxis_MOD_Briefing.pdf",
    ),
}


@router.get("/{slug}")
async def download_marketing_asset(slug: str) -> FileResponse:
    """Stream a whitelisted marketing asset as a download.

    Example:
        GET /api/marketing/mod-briefing.pdf
            → downloads the 16-slide MOD briefing PDF.
    """
    entry = DOWNLOADS.get(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="Not found")

    rel_path, download_name = entry
    abs_path = MARKETING_ROOT / rel_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not on disk")

    return FileResponse(
        path=str(abs_path),
        media_type="application/pdf",
        filename=download_name,
    )
