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
_MAPPING_CSV = os.path.join(_INTEGRATIONS_DIR, "Pulse-Sicon-Field-Mapping.csv")
_MAPPING_BUILDER = os.path.join(_INTEGRATIONS_DIR, "build_mapping_csv.py")


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


@router.get("/downloads/sicon-field-mapping.csv")
async def download_sicon_field_mapping():
    """CSV of every Pulse ↔ Sicon Service WebAPI v1 mapped field."""
    if not os.path.exists(_MAPPING_CSV) and os.path.exists(_MAPPING_BUILDER):
        try:
            subprocess.run(["python", _MAPPING_BUILDER], check=True, cwd="/app/backend", timeout=30)
        except Exception:
            pass
    if not os.path.exists(_MAPPING_CSV):
        raise HTTPException(404, "Field-mapping CSV not available")
    return FileResponse(_MAPPING_CSV, media_type="text/csv",
                        filename="Pulse-Sicon-Field-Mapping.csv")
