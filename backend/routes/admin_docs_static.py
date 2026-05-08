"""Static admin documents — security briefings, integration fact-sheets, etc.

Accessed by Master Admin + Service Desk to share printable briefings with customers.
"""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from utils.service_desk_auth import require_service_desk
from scripts.generate_security_briefing import build_pdf, PDF_PATH
from scripts.generate_craig_response import build_pdf as build_craig_pdf, PDF_PATH as CRAIG_PDF_PATH

router = APIRouter(prefix="/admin-docs", tags=["Admin Documents"])


def _ensure_pdf(path: str, builder) -> None:
    if not Path(path).exists():
        builder(path)
    if not Path(path).exists():
        raise HTTPException(status_code=500, detail="Failed to generate PDF")


@router.get("/security-briefing")
async def get_security_briefing(_: dict = Depends(require_service_desk)):
    """Return the pre-built Pulse Fitness security briefing PDF (regenerates if missing)."""
    _ensure_pdf(PDF_PATH, build_pdf)
    return FileResponse(
        PDF_PATH,
        media_type="application/pdf",
        filename="Pulse_Fitness_Security_Briefing.pdf",
    )


@router.post("/security-briefing/regenerate")
async def regenerate_security_briefing(_: dict = Depends(require_service_desk)):
    """Rebuild the briefing PDF (picks up any source edits to the generator)."""
    path = build_pdf(PDF_PATH)
    return {"success": True, "path": path}


@router.get("/craig-response")
async def get_craig_response(_: dict = Depends(require_service_desk)):
    """Return the point-by-point response to Craig's technical review, for the Pulse MD."""
    _ensure_pdf(CRAIG_PDF_PATH, build_craig_pdf)
    return FileResponse(
        CRAIG_PDF_PATH,
        media_type="application/pdf",
        filename="Pulse_Fitness_Response_To_Craig.pdf",
    )


@router.post("/craig-response/regenerate")
async def regenerate_craig_response(_: dict = Depends(require_service_desk)):
    """Rebuild the Craig-response PDF (picks up any source edits to the generator)."""
    path = build_craig_pdf(CRAIG_PDF_PATH)
    return {"success": True, "path": path}
