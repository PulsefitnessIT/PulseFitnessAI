"""Iter 216d — Site bulk-import endpoints.

Mirrors the equipment-import flow: download a template, upload a CSV,
preview parsed rows, then commit. Designed for the head-office onboarding
wizard (step 3: SITES) and for the existing-org "Sites" tab.

Two endpoints:
  • GET  /api/master-admin/sites/template.csv
        → Returns a starter CSV with the canonical column headers and
          two example rows. Operator fills it in and re-uploads.
  • POST /api/master-admin/sites/preview-csv
        → Accepts a CSV upload, returns parsed site rows for the wizard
          to render. Does NOT persist — wizard handles commit via the
          existing onboard-head-office or add-site flow.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
import csv
import io
import logging

from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def require_master_admin(user: dict):
    """Inline guard — mirrors the one in routes/master_admin.py to avoid
    a cross-module import cycle."""
    from fastapi import HTTPException as _H
    if not (user.get("is_master_admin") or user.get("role") in ("master_admin", "master")):
        raise _H(status_code=403, detail="Master admin access required")


# Canonical CSV columns — keep in lock-step with the wizard's site form
# fields so the preview-csv endpoint can map directly to that shape.
_SITE_CSV_HEADERS = [
    "site_name",
    "address_line1",
    "address_line2",
    "address_line3",
    "city",
    "county",
    "postcode",
    "country",
    "phone",
    "email",
    "site_manager_name",
    "site_manager_email",
    "is_head_office",
    "default_location",
]

_SITE_CSV_EXAMPLE_ROWS = [
    [
        "Example Site Name", "1 High Street", "", "",
        "London", "Greater London", "SW1A 1AA", "United Kingdom",
        "020 0000 0000", "site@example.com",
        "Jane Doe", "jane.doe@example.com",
        "", "Main Floor",
    ],
]


@router.get("/master-admin/sites/template.csv")
async def download_sites_csv_template(user: dict = Depends(get_current_user)):
    """Download a starter CSV. Pre-filled with two example rows the
    operator can replace. Idempotent — safe to download repeatedly."""
    require_master_admin(user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_SITE_CSV_HEADERS)
    for row in _SITE_CSV_EXAMPLE_ROWS:
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="gymaxis-sites-template.csv"'},
    )


def _coerce_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "head_office", "hq")


@router.post("/master-admin/sites/preview-csv")
async def preview_sites_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Parse an uploaded sites CSV and return normalised rows ready for
    the wizard to display. We deliberately do NOT persist here — the
    operator reviews on screen and confirms before commit."""
    require_master_admin(user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    try:
        raw = (await file.read()).decode("utf-8-sig", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is empty or missing a header row")

    # Accept loose/extra columns but require at least site_name.
    headers_lower = [h.strip().lower() for h in reader.fieldnames]
    if "site_name" not in headers_lower:
        raise HTTPException(
            status_code=400,
            detail="CSV must include a 'site_name' column. Download the template via the wizard's 'Download CSV template' button.",
        )

    rows: list[dict] = []
    errors: list[dict] = []
    for i, raw_row in enumerate(reader, start=2):  # start=2 because line 1 is header
        # Lower-case all keys so 'Site_Name', 'site_name', 'SITE_NAME' all work.
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        name = row.get("site_name", "")
        if not name:
            errors.append({"line": i, "error": "Missing site_name"})
            continue
        rows.append({
            "name": name,
            "address_line1": row.get("address_line1", "") or row.get("address", ""),
            "address_line2": row.get("address_line2", ""),
            "address_line3": row.get("address_line3", ""),
            "city": row.get("city", ""),
            "county": row.get("county", ""),
            "postcode": row.get("postcode", "") or row.get("post_code", ""),
            "country": row.get("country", "") or "United Kingdom",
            "phone": row.get("phone", ""),
            "email": row.get("email", ""),
            "site_manager_name": row.get("site_manager_name", "") or row.get("manager_name", ""),
            "site_manager_email": row.get("site_manager_email", "") or row.get("manager_email", ""),
            "is_head_office": _coerce_bool(row.get("is_head_office")),
            "default_location": row.get("default_location", "") or "Main Floor",
        })

    if not rows:
        raise HTTPException(status_code=400, detail="No valid site rows found in CSV")

    # Iter 216e — respect the operator's choice. Previously we force-marked
    # the first site as HQ when the CSV had none; that confused users who
    # intentionally left HQ blank (their HQ is the org itself, with no
    # equipment). Now: if >1 HQ rows, demote the later ones so the backend
    # invariant (≤1 HQ per org) is preserved; otherwise leave as-is.
    hq_indices = [i for i, r in enumerate(rows) if r["is_head_office"]]
    if len(hq_indices) > 1:
        for idx in hq_indices[1:]:
            rows[idx]["is_head_office"] = False

    return {"sites": rows, "count": len(rows), "errors": errors}
