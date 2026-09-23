"""Public download endpoints for generated artifacts (no auth — contents are
templates with no secrets)."""
import os
import subprocess

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

_INTEGRATIONS_DIR = "/app/integrations"
_BRUNO_ZIP = os.path.join(_INTEGRATIONS_DIR, "PulseFitness-Sicon-WebAPI.zip")
_BRUNO_BUILDER = os.path.join(_INTEGRATIONS_DIR, "build_bruno_collection.py")


@router.get("/downloads/sicon-bruno-collection.zip")
async def download_sicon_bruno_collection():
    """The Bruno collection mirroring our Sicon Service WebAPI v1 payloads."""
    if not os.path.exists(_BRUNO_ZIP) and os.path.exists(_BRUNO_BUILDER):
        try:
            subprocess.run(["python", _BRUNO_BUILDER], check=True, cwd="/app/backend", timeout=30)
        except Exception:
            pass
    if not os.path.exists(_BRUNO_ZIP):
        raise HTTPException(404, "Bruno collection not available")
    return FileResponse(_BRUNO_ZIP, media_type="application/zip",
                        filename="PulseFitness-Sicon-WebAPI.zip")
