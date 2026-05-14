"""
GymAxis Service Operations — Pre-job Health & Safety / RAMS sign-off.

Iter 216h89 — Field-engineering compliance gate.

Before an engineer can start the **on-site** timer on a job, they must
complete a Health & Safety sign-off comprising:
  • Tick-box review of standard checklist items (org-configurable
    default; per-asset overrides parked for Phase 2).
  • Engineer signature (canvas → base64 data URL).
  • Free-text remarks (optional).

Compliance value:
  • MOD, NHS, large gym-chain contracts require RAMS evidence.
  • Reduces operator insurance premium claims.
  • Captured signoffs appear on the case timeline + the customer-facing
    service report PDF (h82).

Endpoints:
  GET    /svc/safety/template                                — org's active checklist (lazy-seeds default)
  PUT    /svc/safety/template                                — owner/manager updates checklist items
  GET    /svc/engineer/jobs/{case_id}/safety                 — what does this job need?
  POST   /svc/engineer/jobs/{case_id}/safety/signoff         — engineer submits the ticked items
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File

from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import append_event

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _require_admin(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    if (user.get("role") or "").lower() in ("owner", "manager"):
        return
    raise HTTPException(403, "Owner or Manager role required")


# Default checklist items — generic for UK gym/fitness field service.
# Operators can edit at /svc/safety/template.
DEFAULT_CHECKLIST = [
    {"id": "sign_in",       "label": "Signed in at site reception", "required": True},
    {"id": "ppe",           "label": "Wearing required PPE (hi-vis, safety glasses, steel-toe boots, gloves)", "required": True},
    {"id": "isolation",     "label": "Equipment isolated from power supply (where applicable)", "required": True},
    {"id": "cordoned",      "label": "Work area cordoned off — no members or staff within 2 m", "required": True},
    {"id": "rams_reviewed", "label": "Reviewed the RAMS / risk assessment for this asset type", "required": True},
    {"id": "first_aid",     "label": "Located first-aid kit and emergency exits", "required": False},
    {"id": "phone_charged", "label": "Mobile phone charged & reachable in case of emergency", "required": False},
    {"id": "lone_working",  "label": "Lone-working buddy notified of arrival (if applicable)", "required": False},
]


async def _resolve_template(org_id: str) -> dict:
    """Return the org's template, lazily seeding the default if missing."""
    tpl = await db.svc_safety_templates.find_one(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    )
    if tpl:
        return tpl
    tpl = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": "Standard pre-job H&S checklist",
        "items": list(DEFAULT_CHECKLIST),
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_safety_templates.insert_one(dict(tpl))
    return tpl


# ── Operator-side template CRUD ──────────────────────────────────

@router.get("/svc/safety/template")
async def get_template(user=Depends(get_current_user)):
    tpl = await _resolve_template(user.get("organization_id"))
    tpl.pop("_id", None)
    return tpl


@router.put("/svc/safety/template")
async def update_template(body: dict, user=Depends(get_current_user)):
    _require_admin(user)
    raw_items = (body or {}).get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(400, "items must be a non-empty list")
    cleaned = []
    seen_ids: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        label = (raw.get("label") or "").strip()
        if not label:
            continue
        item_id = (raw.get("id") or "").strip() or label.lower().replace(" ", "_")[:40]
        if item_id in seen_ids:
            item_id = f"{item_id}_{len(seen_ids)}"
        seen_ids.add(item_id)
        cleaned.append({
            "id": item_id,
            "label": label,
            "required": bool(raw.get("required")),
        })
    if not cleaned:
        raise HTTPException(400, "At least one valid checklist item is required")
    org_id = user.get("organization_id")
    now = _now()
    await db.svc_safety_templates.update_one(
        {"organization_id": org_id, "active": True},
        {"$set": {"items": cleaned, "updated_at": now, "active": True,
                  "organization_id": org_id},
         "$setOnInsert": {"id": str(uuid.uuid4()),
                          "name": (body or {}).get("name") or "Standard pre-job H&S checklist",
                          "created_at": now}},
        upsert=True,
    )
    tpl = await db.svc_safety_templates.find_one(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    )
    return tpl


# ── Engineer-side gate ───────────────────────────────────────────

@router.get("/svc/engineer/jobs/{case_id}/safety")
async def engineer_safety_state(case_id: str, user=Depends(get_current_user)):
    """Return the active checklist + any existing signoff on this case.

    The frontend uses this to decide whether the on-site timer is
    blocked and which items still need ticking.
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1, "assigned_engineer_id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    tpl = await _resolve_template(of["organization_id"])
    signoff = await db.svc_case_safety_signoffs.find_one(
        {"case_id": case_id, **of}, {"_id": 0}, sort=[("signed_at", -1)],
    )
    return {
        "template": {"id": tpl["id"], "name": tpl["name"], "items": tpl["items"]},
        "signoff": signoff,
        "completed": bool(signoff),
    }


@router.post("/svc/engineer/jobs/{case_id}/safety/signoff")
async def engineer_safety_signoff(case_id: str, body: dict, user=Depends(get_current_user)):
    """Engineer ticks the checklist + signs.

    Body: {
      ticked_item_ids: [str],
      signature_image: str (data: URL or empty),
      remarks: str (optional)
    }
    """
    of = _of(user)
    case = await db.svc_cases.find_one(
        {"id": case_id, **of},
        {"_id": 0, "id": 1, "reference": 1, "assigned_engineer_id": 1, "status": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"] \
            and not user.get("is_master_admin"):
        raise HTTPException(403, "Not assigned to this job")

    tpl = await _resolve_template(of["organization_id"])
    required_ids = {i["id"] for i in tpl["items"] if i.get("required")}
    ticked = set((body or {}).get("ticked_item_ids") or [])
    missing = required_ids - ticked
    if missing:
        raise HTTPException(
            400,
            f"Required items not ticked: {', '.join(sorted(missing))}",
        )

    signature = ((body or {}).get("signature_image") or "").strip()
    remarks = ((body or {}).get("remarks") or "").strip()
    if not signature:
        raise HTTPException(400, "Engineer signature is required")

    now = _now()
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_name": (user.get("full_name") or user.get("email") or "").strip(),
        "template_id": tpl["id"],
        "template_snapshot": tpl["items"],
        "ticked_item_ids": sorted(ticked),
        "signature_image": signature,
        "remarks": remarks,
        "signed_at": now,
        "created_at": now,
    }
    await db.svc_case_safety_signoffs.insert_one(dict(doc))
    # Persist a fast-read summary on the case for the drawer + PDF.
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {
            "safety_signoff_at": now,
            "safety_signoff_by": user["id"],
            "safety_ticked_count": len(ticked),
            "safety_total_count": len(tpl["items"]),
            "updated_at": now,
        }},
    )
    try:
        await append_event(
            case_id=case_id, organization_id=of["organization_id"],
            event_type="note", actor=user,
            body=f"H&S checklist completed ({len(ticked)}/{len(tpl['items'])} items)"
                 + (f" · Remarks: {remarks}" if remarks else ""),
            extra={"kind": "safety_signoff", "signoff_id": doc["id"]},
        )
    except Exception as e:
        logger.warning(f"safety: failed to append event: {e!r}")
    doc.pop("_id", None)
    return doc


# ── CSV import / export (iter 216h92) ────────────────────────────

@router.get("/svc/safety/template/export.csv")
async def export_csv(user=Depends(get_current_user)):
    """Download the org's active checklist as CSV (label, required, id)."""
    import csv
    import io
    tpl = await _resolve_template(user.get("organization_id"))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["label", "required", "id"])
    for item in tpl["items"]:
        w.writerow([
            item.get("label", ""),
            "true" if item.get("required") else "false",
            item.get("id", ""),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hs-checklist.csv"'},
    )


@router.post("/svc/safety/template/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    replace: bool = False,
    user=Depends(get_current_user),
):
    """Bulk-import checklist items from a CSV file.

    The CSV MUST have a header row containing `label` (case-insensitive).
    Optional columns: `required` (true/false, yes/no, 1/0), `id`.

    `replace=true` query param wipes existing items and uses the import.
    Default behaviour appends to the existing list.
    """
    _require_admin(user)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Uploaded file is empty")
    if len(raw) > 256_000:
        raise HTTPException(400, "CSV file too large (>250 KB)")
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    import csv
    import io
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if "label" not in fields:
        raise HTTPException(
            400,
            "CSV must contain a `label` column (and optionally `required` and `id`).",
        )
    imported: list = []
    for raw_row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        label = row.get("label", "")
        if not label:
            continue
        required_raw = row.get("required", "false").lower()
        required = required_raw in ("true", "yes", "1", "y", "required")
        item_id = row.get("id", "") or label.lower().replace(" ", "_")[:40]
        imported.append({"id": item_id, "label": label, "required": required})
    if not imported:
        raise HTTPException(400, "No valid rows found. Each row needs a non-empty `label`.")

    org_id = user.get("organization_id")
    existing = await _resolve_template(org_id)
    if replace:
        items = imported
    else:
        # Append, de-dupe by id (existing wins for collisions to preserve
        # operator-defined ordering of pre-existing items).
        seen_ids = {i["id"] for i in existing["items"]}
        items = list(existing["items"])
        for it in imported:
            if it["id"] in seen_ids:
                continue
            items.append(it)
            seen_ids.add(it["id"])

    now = _now()
    await db.svc_safety_templates.update_one(
        {"organization_id": org_id, "active": True},
        {"$set": {"items": items, "updated_at": now}},
    )
    return {"ok": True, "imported_count": len(imported), "total_count": len(items)}


__all__ = ["router"]
