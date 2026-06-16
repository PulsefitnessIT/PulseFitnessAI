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
        "mod-presentation/PulseFitness_MOD_Briefing.pdf",
        "PulseFitness_MOD_Briefing.pdf",
    ),
    # Iter 216h302a — short alias, easier to type on mobile.
    "mod.pdf": (
        "mod-presentation/PulseFitness_MOD_Briefing.pdf",
        "PulseFitness_MOD_Briefing.pdf",
    ),
    # Iter 216h303 — Sicon WebAPI access request for Pulse Fitness Test.
    "sicon-access.pdf": (
        "sicon-access/PulseFitness_Sicon_Access_Request.pdf",
        "PulseFitness_Sicon_Access_Request.pdf",
    ),
}


def _serve_marketing_asset(slug: str) -> FileResponse:
    """Stream a whitelisted marketing asset as a download."""
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


def _make_handler(slug: str):
    async def _handler() -> FileResponse:
        return _serve_marketing_asset(slug)
    return _handler


# Register one EXPLICIT route per whitelisted slug rather than a greedy
# `/{slug}` catch-all. The catch-all previously shadowed the marketing app
# routes (`/marketing/campaigns`, `/marketing/audiences`, `/marketing/templates`),
# 404-ing them platform-wide. Explicit paths only match their exact URL, so
# the public download links keep working while the app routes resolve.
for _slug in DOWNLOADS:
    router.add_api_route(
        f"/{_slug}", _make_handler(_slug), methods=["GET"],
        name=f"download_marketing_asset_{_slug}",
    )
