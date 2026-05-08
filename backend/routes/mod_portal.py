"""MOD Service Portal — all backend routes.

Single-file implementation covering all four phases of the MOD rollout:
  • Phase 1 — MVP: site dashboard, staff CRUD, fault wizard
  • Phase 2 — AI: Claude Haiku triage + escalation + engineer pre-visit pack
  • Phase 3 — PRO: branch + organisation multi-site dashboards
  • Phase 4 — Polish: proactive nudges, master-admin MOD console

Users authenticate through the normal Pulse /login flow; the user's
`organization.account_type` (one of `mod_site`, `mod_branch`, `mod_org`)
determines what endpoints and scopes they can reach.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field

from routes.master_admin import require_master_admin
from utils.auth import get_current_user, verify_token
from utils.database import db, APP_NAME, put_object, get_object
from utils.email import send_email
from utils.security import sanitise_string

logger = logging.getLogger(__name__)
router = APIRouter()

MOD_ACCOUNT_TYPES = {"mod_site", "mod_branch", "mod_org"}

FAULT_TYPE_LABELS = {
    "not_working": "Not working",
    "noise": "Noise issue",
    "electrical": "Electrical issue",
    "damage": "Damage",
    "safety": "Safety concern",
    "other": "Other",
}


# ══════════════════════════════════════════════════════════════════
#                     PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════
class StaffCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    role: Optional[str] = Field(default=None, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=40)


class StaffUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[str] = Field(default=None, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=5, max_length=40)


class FaultSubmit(BaseModel):
    equipment_id: str
    fault_type: str = Field(..., pattern=r"^(not_working|noise|electrical|damage|safety|other)$")
    description: str = Field(..., min_length=40, max_length=4000)
    onset: str = Field(..., pattern=r"^(today|yesterday|this_week|older)$")
    usable: str = Field(..., pattern=r"^(yes|limited|no)$")
    safe_in_service: str = Field(..., pattern=r"^(yes|no)$")
    # Reporter — either an existing staff_id OR inline details (one is required).
    reporter_staff_id: Optional[str] = None
    reporter_name: Optional[str] = Field(default=None, max_length=120)
    reporter_email: Optional[EmailStr] = None
    reporter_phone: Optional[str] = Field(default=None, max_length=40)
    # Attachments stored separately via existing /equipment upload — we accept URLs here.
    attachment_urls: list[str] = Field(default_factory=list, max_length=6)
    # If the UI accepted the AI triage preview without edits
    ai_triage_accepted: Optional[bool] = None
    ai_triage_preview: Optional[dict] = None


class BranchCreate(BaseModel):
    organisation_id: str
    branch: str = Field(..., pattern=r"^(Army|Navy|RAF)$")


class SiteCreate(BaseModel):
    branch_id: str
    name: str = Field(..., min_length=3, max_length=200)
    code: str = Field(..., min_length=3, max_length=30)  # used as username prefix
    login_email: EmailStr
    password: str = Field(..., min_length=10)
    address: Optional[str] = None
    access_notes: Optional[str] = None
    escort_required: bool = False
    oncall_phone: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
#                     SCOPE HELPERS
# ══════════════════════════════════════════════════════════════════
async def _org_of(user: dict) -> dict:
    org = await db.organizations.find_one(
        {"id": user["organization_id"]}, {"_id": 0},
    )
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


async def _require_mod_site(user: dict) -> dict:
    """Ensure the user is logged into an MOD site and return the org."""
    org = await _org_of(user)
    if org.get("account_type") != "mod_site":
        raise HTTPException(403, "MOD site access only")
    return org


async def _require_mod_pro(user: dict) -> dict:
    org = await _org_of(user)
    if org.get("account_type") not in {"mod_branch", "mod_org"}:
        raise HTTPException(403, "MOD PRO access only")
    return org


async def _sites_in_scope(pro_org: dict) -> list[str]:
    """Return the list of mod_site org IDs this PRO user can see."""
    q = {"account_type": "mod_site", "mod_root_id": pro_org["mod_root_id"]}
    if pro_org.get("account_type") == "mod_branch":
        q["mod_branch"] = pro_org["mod_branch"]
    sites = await db.organizations.find(q, {"_id": 0, "id": 1, "name": 1, "mod_branch": 1}).to_list(500)
    return [s["id"] for s in sites]


async def _audit(site_id: str, user_id: Optional[str], action: str, **kw) -> None:
    try:
        await db.mod_audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "site_id": site_id,
            "user_id": user_id,
            "action": action,
            "payload": {k: v for k, v in kw.items() if k not in {"password", "password_hash"}},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:  # pragma: no cover
        logger.warning("MOD audit failed: %s", e)


# ══════════════════════════════════════════════════════════════════
#                     PHASE 2 — AI TRIAGE
# ══════════════════════════════════════════════════════════════════
def _deterministic_priority(fault_type: str, safe: str, usable: str) -> str:
    """Matrix from the blueprint — server-side, cannot be gamed by the UI."""
    if fault_type in {"safety", "electrical"} or safe == "no":
        return "urgent"
    if usable == "no":
        return "high"
    if usable == "limited":
        return "medium"
    return "low"


async def _ai_triage(
    equipment: dict, fault_type: str, description: str,
    onset: str, usable: str, safe: str,
) -> dict:
    """Ask Claude Haiku 4.5 to suggest cause + quick fix. Safe to fail."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return {"cause": None, "quick_fix": None, "model": None, "skipped": True}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        session = f"mod-triage-{uuid.uuid4().hex[:8]}"
        system = (
            "You are a senior gym-equipment service engineer helping a gym user triage a fault. "
            "Reply with a JSON object containing: `likely_cause` (string, ≤160 chars), "
            "`quick_fix` (string, ≤200 chars — one or two steps the user could try safely, "
            "or empty if engineer required), `engineer_required` (bool), `confidence_pct` (0-100 int). "
            "Never suggest touching electrical components. Never override safety flags."
        )
        chat = LlmChat(api_key=key, session_id=session, system_message=system) \
            .with_model("openai", "gpt-4o-mini")
        prompt = (
            f"Equipment: {equipment.get('machine_type', equipment.get('category', 'gym machine'))} "
            f"({equipment.get('manufacturer', 'unknown')} {equipment.get('model_number', '')}).\n"
            f"Fault type: {FAULT_TYPE_LABELS.get(fault_type, fault_type)}.\n"
            f"Description: {description}\n"
            f"Onset: {onset}. Usable: {usable}. Safe in service: {safe}.\n"
            "Return JSON only, no prose wrapper."
        )
        reply = await chat.send_message(UserMessage(text=prompt))
        import json
        import re
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
        return {
            "cause": parsed.get("likely_cause"),
            "quick_fix": parsed.get("quick_fix"),
            "engineer_required": bool(parsed.get("engineer_required", True)),
            "confidence_pct": int(parsed.get("confidence_pct", 70)),
            "model": "gpt-4o-mini",
        }
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning("AI triage failed: %s", e)
        return {"cause": None, "quick_fix": None, "model": None, "error": str(e)[:120]}


# ══════════════════════════════════════════════════════════════════
#              PHASE 1 — SITE DASHBOARD + FAULT WIZARD
# ══════════════════════════════════════════════════════════════════
@router.get("/mod/me")
async def mod_whoami(user: dict = Depends(get_current_user)):
    """Return the MOD org context (site/branch/org) for the current user."""
    org = await _org_of(user)
    return {
        "org": {
            "id": org["id"],
            "name": org.get("name"),
            "account_type": org.get("account_type"),
            "mod_branch": org.get("mod_branch"),
            "mod_root_id": org.get("mod_root_id"),
            "site_code": org.get("site_code"),
        },
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
        },
    }


@router.get("/mod/site/dashboard")
async def mod_site_dashboard(user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    site_id = org["id"]
    now = datetime.now(timezone.utc)

    equip = await db.equipment.find(
        {"organization_id": site_id},
        {"_id": 0, "id": 1, "name": 1, "machine_type": 1, "serial_number": 1,
         "status": 1, "last_checked_at": 1}
    ).to_list(500)
    total = len(equip)
    working = sum(1 for e in equip if (e.get("status") or "working").lower() in {"working", "ok"})
    oos = sum(1 for e in equip if (e.get("status") or "").lower() in {"out_of_service", "oos"})

    # Overdue-check threshold: 30 days since last_checked_at
    cutoff = (now - timedelta(days=30)).isoformat()
    overdue_checks = sum(
        1 for e in equip
        if not e.get("last_checked_at") or str(e["last_checked_at"]) < cutoff
    )

    open_issues = await db.issues.find(
        {"organization_id": site_id, "status": {"$ne": "resolved"}},
        {"_id": 0},
    ).sort("created_at", -1).limit(25).to_list(25)

    # Repeat-offender: any equipment with >= 3 issues in last 30 days.
    since = (now - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"organization_id": site_id, "created_at": {"$gte": since},
                    "is_drill": {"$ne": True}}},
        {"$group": {"_id": "$equipment_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 3}}},
    ]
    repeat_ids = [r["_id"] async for r in db.issues.aggregate(pipeline)]

    return {
        "site": {"id": site_id, "name": org.get("name"), "code": org.get("site_code")},
        "stats": {
            "equipment_total": total,
            "equipment_working": working,
            "equipment_out_of_service": oos,
            "availability_pct": round(100 * working / total, 1) if total else 100.0,
            "overdue_checks": overdue_checks,
            "repeat_offenders": len(repeat_ids),
            "open_faults": len(open_issues),
        },
        "open_faults": open_issues,
        "repeat_offender_equipment_ids": repeat_ids,
    }


@router.get("/mod/site/equipment")
async def mod_site_equipment(user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    items = await db.equipment.find(
        {"organization_id": org["id"]}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    return {"equipment": items}


# ── QR sheet PDF (print-and-stick labels, 12 per A4 page) ─────
@router.get("/mod/site/qr-sheet.pdf")
async def mod_qr_sheet_pdf(user: dict = Depends(get_current_user)):
    """Generate an A4 PDF with a 3×4 grid of branded QR labels — one per
    asset. PTI staff print this once, cut, and physically stick onto each
    machine. Scan → lands on the existing /scan/{equipment_id} page which
    (for logged-in MOD users) hands them into the fault wizard.
    """
    import io
    import qrcode
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas

    org = await _require_mod_site(user)
    equipment = await db.equipment.find(
        {"organization_id": org["id"]}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    if not equipment:
        raise HTTPException(404, "No equipment to generate labels for.")

    frontend = os.environ.get("REACT_APP_BACKEND_URL", "").replace("/api", "").rstrip("/")

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # Page header on each page
    def draw_header(page_num: int, total_pages: int) -> None:
        c.setFillColorRGB(0.03, 0.05, 0.06)
        c.rect(0, page_h - 18 * mm, page_w, 18 * mm, stroke=0, fill=1)
        c.setFillColorRGB(0.098, 0.804, 1.0)  # Pulse cyan
        c.setFont("Helvetica-Bold", 7)
        c.drawString(10 * mm, page_h - 7 * mm, "PULSE FITNESS · MOD SERVICE PORTAL")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(10 * mm, page_h - 13 * mm, org.get("name", "MOD Site"))
        # Branch badge upper-right
        branch = org.get("mod_branch") or ""
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.098, 0.804, 1.0)
        c.drawRightString(page_w - 10 * mm, page_h - 8 * mm, branch.upper())
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 7)
        c.drawRightString(page_w - 10 * mm, page_h - 13 * mm,
                          f"Page {page_num}/{total_pages} · Scan to log a fault")

    # Label grid geometry — 3 cols × 4 rows, gutter 4mm, margins 8mm/side,
    # header band 18mm. Each cell ≈ 62mm × 62mm.
    cols, rows = 3, 4
    per_page = cols * rows
    margin_x = 8 * mm
    margin_top_below_header = 22 * mm
    gutter = 4 * mm
    grid_w = page_w - 2 * margin_x
    cell_w = (grid_w - (cols - 1) * gutter) / cols
    grid_h = page_h - margin_top_below_header - 15 * mm
    cell_h = (grid_h - (rows - 1) * gutter) / rows

    total_pages = (len(equipment) + per_page - 1) // per_page

    for idx, eq in enumerate(equipment):
        page_num = idx // per_page + 1
        position = idx % per_page
        if position == 0:
            if idx > 0:
                c.showPage()
            draw_header(page_num, total_pages)

        col = position % cols
        row = position // cols
        x = margin_x + col * (cell_w + gutter)
        y = page_h - margin_top_below_header - (row + 1) * cell_h - row * gutter

        # Card border
        c.setStrokeColorRGB(0.75, 0.78, 0.82)
        c.setLineWidth(0.5)
        c.roundRect(x, y, cell_w, cell_h, 4, stroke=1, fill=0)

        # Header strip
        strip_h = 8 * mm
        c.setFillColorRGB(0.03, 0.05, 0.06)
        c.roundRect(x, y + cell_h - strip_h, cell_w, strip_h, 4, stroke=0, fill=1)
        c.setFillColorRGB(0.098, 0.804, 1.0)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x + 3 * mm, y + cell_h - 3.3 * mm, "SCAN TO REPORT FAULT")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 6)
        c.drawRightString(x + cell_w - 3 * mm, y + cell_h - 3.3 * mm,
                          (org.get("mod_branch") or "MOD").upper())

        # QR code
        scan_url = f"{frontend}/scan/{eq['id']}"
        qr = qrcode.QRCode(version=None,
                           error_correction=qrcode.constants.ERROR_CORRECT_H,
                           box_size=10, border=2)
        qr.add_data(scan_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img_buf = io.BytesIO()
        qr_img.save(img_buf, format="PNG")
        img_buf.seek(0)
        qr_size = 32 * mm
        qr_x = x + (cell_w - qr_size) / 2
        qr_y = y + cell_h - strip_h - qr_size - 2 * mm
        c.drawImage(ImageReader(img_buf), qr_x, qr_y, qr_size, qr_size)

        # Machine name (truncate to ~20 chars)
        name = eq.get("name") or "Unnamed asset"
        if len(name) > 22:
            name = name[:20] + "…"
        c.setFillColorRGB(0.11, 0.12, 0.12)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + cell_w / 2, qr_y - 4 * mm, name)

        # Type + serial
        c.setFillColorRGB(0.43, 0.45, 0.47)
        c.setFont("Helvetica", 6.5)
        sub = f"{eq.get('machine_type') or eq.get('category') or ''} · {eq.get('serial_number') or ''}"
        if len(sub) > 36:
            sub = sub[:34] + "…"
        c.drawCentredString(x + cell_w / 2, qr_y - 7 * mm, sub)

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    await _audit(org["id"], user.get("id"), "qr_sheet.download",
                 equipment_count=len(equipment))

    filename = f"mod-qr-sheet-{org.get('site_code', 'site')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Attachment upload (wizard step 4 photo/video capture) ─────
MAX_IMAGE_BYTES = 10 * 1024 * 1024        # 10 MB post-client-compression
MAX_VIDEO_BYTES = 50 * 1024 * 1024        # 50 MB (short clips, pre-compressed)
_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_VIDEO = {"video/mp4", "video/quicktime", "video/webm"}


@router.post("/mod/site/attachments")
async def mod_attachment_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Single-file upload for fault-wizard attachments.

    Client compresses images to WebP before sending. Videos are accepted
    as-is up to 50 MB. Returns the public URL to be appended to the fault
    submission's `attachment_urls`. Scope-locked to MOD sites.
    """
    from utils.file_validation import validate_upload

    org = await _require_mod_site(user)
    data = await file.read()
    size = len(data)

    # Validate the actual bytes, not the client-supplied content_type. The
    # allow-list covers images + supported video containers.
    allowed_media = _ALLOWED_IMAGE | _ALLOWED_VIDEO
    ct = validate_upload(
        file_bytes=data,
        filename=file.filename,
        allowed=allowed_media,
        max_size=MAX_VIDEO_BYTES,
    )
    is_image = ct in _ALLOWED_IMAGE
    is_video = ct in _ALLOWED_VIDEO
    if is_image and size > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image too large (max 10 MB after compression)")
    if is_video and size > MAX_VIDEO_BYTES:
        raise HTTPException(413, "Video too large (max 50 MB)")

    # Quick sanity — reject zero-byte files.
    if size < 256:
        raise HTTPException(400, "File appears to be empty or corrupt")

    ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else
           ("webp" if ct == "image/webp" else
            "jpg" if ct == "image/jpeg" else
            "png" if ct == "image/png" else
            "mp4" if ct == "video/mp4" else
            "mov" if ct == "video/quicktime" else "webm"))
    path = f"{APP_NAME}/mod-attachments/{org['id']}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ct)
    stored_path = result.get("path", path)
    return {
        "path": stored_path,
        "kind": "image" if is_image else "video",
        "size": size,
        "content_type": ct,
    }


@router.get("/mod/site/attachments/serve")
async def mod_attachment_serve(
    path: str = Query(..., description="Storage path returned from the upload endpoint"),
    token: str = Query(..., description="JWT — browsers can't attach headers to <img>/<video> src"),
):
    """Serve an uploaded attachment to `<img>` / `<video>` elements.

    Auth goes via query-string because browsers strip Authorization headers
    on image/video loads. The token is validated, then the path is checked
    to confirm it lives inside the caller's MOD site folder — preventing a
    logged-in user at site A from snooping attachments from site B.
    """
    payload = verify_token(token)
    if not payload or payload.get("type") == "mfa_temp":
        raise HTTPException(401, "Invalid token")
    viewer = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0})
    if not viewer:
        raise HTTPException(401, "Invalid token")

    # Path must be under this user's MOD site bucket (or master admin override).
    expected_prefix_for_site = f"{APP_NAME}/mod-attachments/{viewer.get('organization_id', '')}/"
    if not viewer.get("is_master_admin") and not path.startswith(expected_prefix_for_site):
        raise HTTPException(403, "Cross-site attachment access denied")
    if not path.startswith(f"{APP_NAME}/mod-attachments/"):
        raise HTTPException(400, "Not a MOD attachment path")

    try:
        data, content_type = get_object(path)
    except Exception:  # pragma: no cover — storage outage
        raise HTTPException(404, "Attachment not found")
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


# ── Staff CRUD ────────────────────────────────────────────────
@router.get("/mod/site/staff")
async def mod_staff_list(user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    items = await db.mod_site_staff.find(
        {"site_id": org["id"], "is_active": {"$ne": False}}, {"_id": 0},
    ).sort("last_reported_at", -1).to_list(500)
    return {"staff": items}


@router.post("/mod/site/staff")
async def mod_staff_create(
    payload: StaffCreate, user: dict = Depends(get_current_user),
):
    org = await _require_mod_site(user)
    email_lc = payload.email.lower().strip()
    # Uniqueness per site
    exists = await db.mod_site_staff.find_one({
        "site_id": org["id"], "email_lc": email_lc, "is_active": {"$ne": False},
    }, {"_id": 0, "id": 1})
    if exists:
        raise HTTPException(400, "A staff member with this email already exists for this site")
    staff_id = str(uuid.uuid4())
    doc = {
        "id": staff_id,
        "site_id": org["id"],
        "name": sanitise_string(payload.name),
        "role": sanitise_string(payload.role) if payload.role else None,
        "email": payload.email,
        "email_lc": email_lc,
        "phone": sanitise_string(payload.phone),
        "is_active": True,
        "fault_count": 0,
        "last_reported_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.mod_site_staff.insert_one(doc)
    await _audit(org["id"], user.get("id"), "staff.create", staff_id=staff_id, email=email_lc)
    doc.pop("_id", None)
    doc.pop("email_lc", None)
    return doc


@router.patch("/mod/site/staff/{staff_id}")
async def mod_staff_update(
    staff_id: str, payload: StaffUpdate, user: dict = Depends(get_current_user),
):
    org = await _require_mod_site(user)
    existing = await db.mod_site_staff.find_one({"id": staff_id, "site_id": org["id"]})
    if not existing:
        raise HTTPException(404, "Staff not found")
    updates = {}
    if payload.name is not None:
        updates["name"] = sanitise_string(payload.name)
    if payload.role is not None:
        updates["role"] = sanitise_string(payload.role)
    if payload.email is not None:
        updates["email"] = payload.email
        updates["email_lc"] = payload.email.lower().strip()
    if payload.phone is not None:
        updates["phone"] = sanitise_string(payload.phone)
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.mod_site_staff.update_one({"id": staff_id}, {"$set": updates})
    await _audit(org["id"], user.get("id"), "staff.update", staff_id=staff_id)
    return {"ok": True}


@router.delete("/mod/site/staff/{staff_id}")
async def mod_staff_delete(staff_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    res = await db.mod_site_staff.update_one(
        {"id": staff_id, "site_id": org["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Staff not found")
    await _audit(org["id"], user.get("id"), "staff.delete", staff_id=staff_id)
    return {"ok": True}


# ── Fault wizard submit ──────────────────────────────────────
@router.post("/mod/site/faults")
async def mod_fault_submit(
    payload: FaultSubmit, request: Request, user: dict = Depends(get_current_user),
):
    org = await _require_mod_site(user)
    site_id = org["id"]

    # Resolve equipment + ensure it belongs to the site.
    equipment = await db.equipment.find_one(
        {"id": payload.equipment_id, "organization_id": site_id}, {"_id": 0},
    )
    if not equipment:
        raise HTTPException(404, "Equipment not found on this site")

    # Resolve reporter — either an existing staff row or inline details.
    reporter_name = reporter_email = reporter_phone = None
    staff_id_used = None
    if payload.reporter_staff_id:
        staff = await db.mod_site_staff.find_one(
            {"id": payload.reporter_staff_id, "site_id": site_id, "is_active": {"$ne": False}},
            {"_id": 0},
        )
        if not staff:
            raise HTTPException(400, "Reporter staff not found on this site")
        reporter_name, reporter_email, reporter_phone = staff["name"], staff["email"], staff["phone"]
        staff_id_used = staff["id"]
    else:
        if not (payload.reporter_name and payload.reporter_email and payload.reporter_phone):
            raise HTTPException(
                400,
                "A reporter is required. Either pick an existing staff member "
                "or supply name, email and phone.",
            )
        reporter_name, reporter_email, reporter_phone = (
            sanitise_string(payload.reporter_name),
            payload.reporter_email.lower().strip(),
            sanitise_string(payload.reporter_phone),
        )
        # Auto-add to the staff DB so they appear in the picker next time.
        staff_id_used = str(uuid.uuid4())
        await db.mod_site_staff.insert_one({
            "id": staff_id_used,
            "site_id": site_id,
            "name": reporter_name,
            "role": None,
            "email": reporter_email,
            "email_lc": reporter_email,
            "phone": reporter_phone,
            "is_active": True,
            "fault_count": 0,
            "last_reported_at": None,
            "auto_added_from_fault": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Duplicate check (same equip + fault_type + open) → surface a warning.
    dup = await db.issues.find_one({
        "organization_id": site_id,
        "equipment_id": payload.equipment_id,
        "fault_type_mod": payload.fault_type,
        "status": {"$ne": "resolved"},
    }, {"_id": 0, "id": 1, "mod_ticket_ref": 1})

    # Deterministic priority, then AI enrichment.
    priority = _deterministic_priority(payload.fault_type, payload.safe_in_service, payload.usable)
    ai = await _ai_triage(
        equipment, payload.fault_type, payload.description,
        payload.onset, payload.usable, payload.safe_in_service,
    )

    now = datetime.now(timezone.utc)
    ticket_ref = f"MOD-{now.year}-{str(uuid.uuid4().int)[:5].zfill(5)}"
    issue_id = str(uuid.uuid4())
    doc = {
        "id": issue_id,
        "organization_id": site_id,
        "user_id": user.get("id"),
        "equipment_id": payload.equipment_id,
        "machine_type": equipment.get("machine_type") or equipment.get("category"),
        "serial_number": equipment.get("serial_number"),
        "issue_description": payload.description,
        "severity": priority,          # re-uses existing severity field
        "status": "open",
        "mod_site_id": site_id,
        "mod_ticket_ref": ticket_ref,
        "fault_type_mod": payload.fault_type,
        "onset": payload.onset,
        "usable": payload.usable,
        "safe_in_service": payload.safe_in_service,
        "reporter_staff_id": staff_id_used,
        "reporter_name": reporter_name,
        "reporter_email": reporter_email,
        "reporter_phone": reporter_phone,
        "attachment_urls": payload.attachment_urls,
        "ai_triage": ai,
        "ai_triage_accepted": bool(payload.ai_triage_accepted),
        "priority": priority,
        "created_at": now.isoformat(),
    }
    await db.issues.insert_one(doc)

    # Equipment state updates.
    eq_updates = {"last_fault_at": now.isoformat()}
    if payload.safe_in_service == "no" or (payload.fault_type == "safety"):
        eq_updates["status"] = "out_of_service"
    await db.equipment.update_one({"id": payload.equipment_id}, {"$set": eq_updates})

    # Staff MRU update.
    await db.mod_site_staff.update_one(
        {"id": staff_id_used},
        {
            "$set": {"last_reported_at": now.isoformat()},
            "$inc": {"fault_count": 1},
        },
    )

    # Phase 2 — URGENT escalation email to the platform on-call.
    if priority == "urgent":
        oncall = os.environ.get("MOD_ONCALL_EMAIL") or os.environ.get(
            "TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com",
        )
        subject = f"[MOD URGENT] {ticket_ref} — {org.get('name')} — {equipment.get('name')}"
        html = _escalation_email_html(org, equipment, doc)
        try:
            asyncio.create_task(send_email(oncall, subject, html))
        except Exception as e:  # pragma: no cover
            logger.warning("MOD urgent escalation email failed: %s", e)

    # Confirmation email to the reporter.
    try:
        asyncio.create_task(send_email(
            reporter_email,
            f"Fault logged — {ticket_ref}",
            _confirmation_email_html(org, equipment, doc),
        ))
    except Exception:  # pragma: no cover
        pass

    await _audit(
        site_id, user.get("id"), "fault.create",
        ticket_ref=ticket_ref, priority=priority, equipment_id=payload.equipment_id,
    )

    return {
        "ok": True,
        "ticket_ref": ticket_ref,
        "issue_id": issue_id,
        "priority": priority,
        "duplicate_of": dup.get("mod_ticket_ref") if dup else None,
        "ai_triage": ai,
    }


@router.get("/mod/site/faults/{issue_id}")
async def mod_fault_detail(issue_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    doc = await db.issues.find_one(
        {"id": issue_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Fault not found")
    return doc


# ── Phase 2: AI triage endpoint called from the wizard preview ─
class TriagePreviewBody(BaseModel):
    equipment_id: str
    fault_type: str
    description: str = Field(..., min_length=10)
    onset: str
    usable: str
    safe_in_service: str


@router.post("/mod/site/faults/triage-preview")
async def mod_triage_preview(
    body: TriagePreviewBody, user: dict = Depends(get_current_user),
):
    org = await _require_mod_site(user)
    eq = await db.equipment.find_one(
        {"id": body.equipment_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not eq:
        raise HTTPException(404, "Equipment not found")
    priority = _deterministic_priority(body.fault_type, body.safe_in_service, body.usable)
    ai = await _ai_triage(
        eq, body.fault_type, body.description, body.onset, body.usable, body.safe_in_service,
    )
    return {"priority": priority, "ai": ai}


# ── Phase 2: Engineer pre-visit pack ──────────────────────────
@router.get("/mod/pre-visit-pack/{issue_id}")
async def mod_pre_visit_pack(issue_id: str, user: dict = Depends(get_current_user)):
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not issue:
        raise HTTPException(404, "Issue not found")
    site = await db.organizations.find_one({"id": issue["organization_id"]}, {"_id": 0})
    eq = await db.equipment.find_one({"id": issue["equipment_id"]}, {"_id": 0}) or {}
    # Previous resolved faults on the same asset (last 12m).
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    prior = await db.issues.find(
        {"equipment_id": issue["equipment_id"], "id": {"$ne": issue_id},
         "created_at": {"$gte": since}},
        {"_id": 0, "mod_ticket_ref": 1, "issue_description": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).limit(8).to_list(8)
    return {
        "ticket_ref": issue.get("mod_ticket_ref"),
        "site": {
            "name": site.get("name") if site else None,
            "access_notes": (site or {}).get("access_notes"),
            "escort_required": (site or {}).get("escort_required"),
            "oncall_phone": (site or {}).get("oncall_phone"),
        },
        "contact": {
            "name": issue.get("reporter_name"),
            "email": issue.get("reporter_email"),
            "phone": issue.get("reporter_phone"),
        },
        "equipment": {
            "name": eq.get("name"),
            "machine_type": eq.get("machine_type") or eq.get("category"),
            "serial_number": eq.get("serial_number"),
            "manufacturer": eq.get("manufacturer"),
            "model_number": eq.get("model_number"),
            "warranty_expires": eq.get("warranty_expires"),
            "location": eq.get("location"),
        },
        "fault": {
            "type": FAULT_TYPE_LABELS.get(issue.get("fault_type_mod"), issue.get("fault_type_mod")),
            "description": issue.get("issue_description"),
            "onset": issue.get("onset"),
            "usable": issue.get("usable"),
            "safe_in_service": issue.get("safe_in_service"),
            "priority": issue.get("priority"),
        },
        "ai_triage": issue.get("ai_triage"),
        "prior_faults": prior,
    }


# ══════════════════════════════════════════════════════════════════
#              PHASE 3 — PRO BRANCH + ORG DASHBOARDS
# ══════════════════════════════════════════════════════════════════
@router.get("/mod/pro/dashboard")
async def mod_pro_dashboard(user: dict = Depends(get_current_user)):
    org = await _require_mod_pro(user)
    site_ids = await _sites_in_scope(org)
    if not site_ids:
        return {
            "scope": org["account_type"], "branch": org.get("mod_branch"),
            "sites": [], "totals": {}, "top_offenders": [], "recent_urgent": [],
        }

    # Per-site rollup
    sites = await db.organizations.find(
        {"id": {"$in": site_ids}},
        {"_id": 0, "id": 1, "name": 1, "mod_branch": 1, "site_code": 1},
    ).to_list(500)

    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    # Top offenders: downtime proxy = open-fault age sum — drills excluded.
    agg = [
        {"$match": {"organization_id": {"$in": site_ids}, "created_at": {"$gte": since},
                    "is_drill": {"$ne": True}}},
        {"$group": {"_id": "$organization_id",
                    "fault_count": {"$sum": 1},
                    "urgent": {"$sum": {"$cond": [{"$eq": ["$priority", "urgent"]}, 1, 0]}}}},
        {"$sort": {"fault_count": -1}},
        {"$limit": 10},
    ]
    rollup = {r["_id"]: r async for r in db.issues.aggregate(agg)}
    site_map = {s["id"]: s for s in sites}
    top_offenders = [
        {**site_map.get(sid, {"id": sid, "name": "(missing)"}), **rollup[sid]}
        for sid in rollup
    ]

    # Platform-wide totals for the header — drills excluded.
    total_equip = await db.equipment.count_documents({"organization_id": {"$in": site_ids}})
    total_oos = await db.equipment.count_documents({
        "organization_id": {"$in": site_ids}, "status": "out_of_service",
    })
    open_urgent = await db.issues.count_documents({
        "organization_id": {"$in": site_ids}, "priority": "urgent",
        "status": {"$ne": "resolved"}, "is_drill": {"$ne": True},
    })
    recent_urgent = await db.issues.find(
        {"organization_id": {"$in": site_ids}, "priority": "urgent",
         "is_drill": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)
    # Decorate with site names
    for r in recent_urgent:
        r["site_name"] = (site_map.get(r["organization_id"]) or {}).get("name")

    # Branch split (only meaningful for org-level, included for both for symmetry)
    branch_split_agg = [
        {"$match": {"id": {"$in": site_ids}}},
        {"$group": {"_id": "$mod_branch", "sites": {"$sum": 1}}},
    ]
    branch_split = [r async for r in db.organizations.aggregate(branch_split_agg)]

    return {
        "scope": org["account_type"],
        "branch": org.get("mod_branch"),
        "totals": {
            "sites": len(sites),
            "equipment": total_equip,
            "out_of_service": total_oos,
            "availability_pct": round(100 * (total_equip - total_oos) / total_equip, 1) if total_equip else 100.0,
            "open_urgent": open_urgent,
        },
        "branch_split": branch_split,
        "top_offenders": top_offenders,
        "recent_urgent": recent_urgent,
        "sites": sites,
    }


# ══════════════════════════════════════════════════════════════════
#              PHASE 4 — PROACTIVE SCANNERS + MASTER ADMIN
# ══════════════════════════════════════════════════════════════════
@router.get("/mod/site/proactive-nudges")
async def mod_proactive_nudges(user: dict = Depends(get_current_user)):
    """Cheap, on-demand nudges. The expensive version runs on a nightly cron."""
    org = await _require_mod_site(user)
    site_id = org["id"]
    now = datetime.now(timezone.utc)
    thirty_ago = (now - timedelta(days=30)).isoformat()
    sixty_ago = (now - timedelta(days=60)).isoformat()

    nudges: list[dict] = []

    # 1) Overdue checks
    overdue = await db.equipment.count_documents({
        "organization_id": site_id,
        "$or": [
            {"last_checked_at": {"$exists": False}},
            {"last_checked_at": {"$lt": thirty_ago}},
        ],
    })
    if overdue > 0:
        nudges.append({
            "level": "warn",
            "code": "overdue_checks",
            "title": f"{overdue} machine{'s' if overdue > 1 else ''} overdue a check",
            "body": "Run a quick daily check to keep availability and compliance green.",
        })

    # 2) Repeat-offender equipment
    agg = [
        {"$match": {"organization_id": site_id, "created_at": {"$gte": thirty_ago}}},
        {"$group": {"_id": "$equipment_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 3}}},
        {"$limit": 10},
    ]
    repeat = [r async for r in db.issues.aggregate(agg)]
    if repeat:
        eq_ids = [r["_id"] for r in repeat]
        eq_docs = {
            e["id"]: e for e in await db.equipment.find(
                {"id": {"$in": eq_ids}}, {"_id": 0, "id": 1, "name": 1},
            ).to_list(10)
        }
        for r in repeat:
            name = (eq_docs.get(r["_id"]) or {}).get("name", "Machine")
            nudges.append({
                "level": "warn", "code": "repeat_offender",
                "title": f"{name} has {r['n']} faults in 30 days",
                "body": "Consider a depth inspection / warranty claim.",
            })

    # 3) No activity
    any_recent = await db.issues.count_documents({
        "organization_id": site_id, "created_at": {"$gte": sixty_ago},
    })
    if any_recent == 0:
        nudges.append({
            "level": "info", "code": "no_activity",
            "title": "No faults logged in 60 days — nice.",
            "body": "Encourage staff to still log cosmetic / noise issues early — easier fixes.",
        })

    return {"nudges": nudges}


# ── Master Admin — MOD console (Phase 4) ──────────────────────
@router.get("/master-admin/mod/sites")
async def mod_admin_list_sites(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    from utils.mod_password_rotation import _days_until_expiry
    sites = await db.organizations.find(
        {"account_type": "mod_site"}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    # Annotate each site with basic counts + password rotation status.
    for s in sites:
        s["equipment_count"] = await db.equipment.count_documents({"organization_id": s["id"]})
        s["staff_count"] = await db.mod_site_staff.count_documents({
            "site_id": s["id"], "is_active": {"$ne": False},
        })
        s["open_faults"] = await db.issues.count_documents({
            "organization_id": s["id"], "status": {"$ne": "resolved"},
            "is_drill": {"$ne": True},
        })
        site_user = await db.users.find_one(
            {"organization_id": s["id"], "account_type": "mod_site"},
            {"_id": 0, "username": 1, "password_updated_at": 1},
        )
        if site_user:
            s["username"] = site_user.get("username")
            s["password_updated_at"] = site_user.get("password_updated_at")
            s["password_days_until_expiry"] = _days_until_expiry(site_user.get("password_updated_at"))
    return {"sites": sites}


@router.get("/master-admin/mod/audit-log/{site_id}")
async def mod_admin_audit_log(site_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    rows = await db.mod_audit_log.find(
        {"site_id": site_id}, {"_id": 0},
    ).sort("created_at", -1).limit(200).to_list(200)
    return {"log": rows}


@router.post("/master-admin/mod/sites/{site_id}/rotate-password")
async def mod_admin_rotate_password(site_id: str, user: dict = Depends(get_current_user)):
    """Master-admin-only one-click rotation of a MOD site's shared login code.

    Emails the new code to the configured rotation notify address. Response
    includes the plaintext code ONCE so the admin can also copy it
    immediately. The code is NOT persisted in plaintext — only bcrypt hash.
    """
    require_master_admin(user)
    from utils.mod_password_rotation import perform_rotation
    try:
        result = await perform_rotation(site_id, user.get("id", "master-admin"))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "ok": True,
        "site_name": result["site_name"],
        "username": result["username"],
        "new_password": result["new_password"],
        "note": "A copy has been emailed to the MOD rotation notify address.",
    }


# ── Red Team Drill mode ──────────────────────────────────────────
# Lets a master admin inject a simulated URGENT fault into a MOD site so
# the PTI, on-call engineer routing, and escalation email flows can be
# rehearsed end-to-end — WITHOUT polluting real KPIs or paging real
# engineers. Drill faults:
#   • are flagged `is_drill: true` on the issue doc
#   • route escalation email to MOD_DRILL_OBSERVERS_EMAIL (falls back to
#     the master-admin rotation notify address) instead of real on-call
#   • never flip the machine's real status (no auto-isolate)
#   • are filtered out of PRO-tier top-offender / urgent feed aggregations
#   • still appear on the site dashboard with a DRILL badge so PTI know
#     they are being tested
# Observations: time-to-acknowledge and time-to-resolution are captured
# and compiled into a report on drill completion.

class DrillStartPayload(BaseModel):
    scenario: str = Field(..., description="One-liner — e.g. 'Power fail on cardio bank'")
    equipment_id: str | None = None            # if None, pick first working
    fault_type: str = Field(default="electrical")
    description: str = Field(default="DRILL: simulated fault — PTI please run through full response.")
    safe_in_service: str = Field(default="no")


@router.post("/master-admin/mod/sites/{site_id}/drill/start")
async def mod_drill_start(site_id: str, payload: DrillStartPayload, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    site = await db.organizations.find_one({"id": site_id, "account_type": "mod_site"}, {"_id": 0})
    if not site:
        raise HTTPException(404, "MOD site not found")

    # Pick target equipment
    eq_id = payload.equipment_id
    if not eq_id:
        eq = await db.equipment.find_one(
            {"organization_id": site_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "id": 1},
        )
        if not eq:
            raise HTTPException(400, "No usable equipment to drill against.")
        eq_id = eq["id"]
    equipment = await db.equipment.find_one({"id": eq_id}, {"_id": 0})
    if not equipment or equipment.get("organization_id") != site_id:
        raise HTTPException(400, "Equipment not on this site.")

    now = datetime.now(timezone.utc)
    drill_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())
    ticket_ref = f"DRILL-{now.year}-{str(uuid.uuid4().int)[:5].zfill(5)}"

    doc = {
        "id": issue_id,
        "organization_id": site_id,
        "user_id": user.get("id"),
        "equipment_id": eq_id,
        "machine_type": equipment.get("machine_type") or equipment.get("category"),
        "serial_number": equipment.get("serial_number"),
        "issue_description": f"[DRILL] {payload.description}",
        "severity": "urgent",
        "status": "open",
        "mod_site_id": site_id,
        "mod_ticket_ref": ticket_ref,
        "fault_type_mod": payload.fault_type,
        "onset": "today",
        "usable": "no",
        "safe_in_service": payload.safe_in_service,
        "reporter_name": f"DRILL · {user.get('email', 'master-admin')}",
        "reporter_email": user.get("email", "admin@gymaxisai.com"),
        "reporter_phone": "N/A",
        "attachment_urls": [],
        "priority": "urgent",
        "is_drill": True,
        "drill_id": drill_id,
        "drill_scenario": payload.scenario,
        "drill_started_by": user.get("id"),
        "drill_started_at": now.isoformat(),
        "created_at": now.isoformat(),
    }
    await db.issues.insert_one(doc)

    # Drill-only escalation email to observers (NOT real on-call).
    observers_raw = os.environ.get(
        "MOD_DRILL_OBSERVERS_EMAIL",
        os.environ.get("MOD_ROTATION_NOTIFY_EMAIL",
                       os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL", "Lee@gymaxisai.com")),
    )
    observers = [e.strip() for e in observers_raw.split(",") if e.strip()]
    subject = f"[MOD DRILL · {payload.scenario}] {ticket_ref} — {site.get('name')} — SIMULATION"
    html = f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#7c3aed;padding:20px 28px;border-bottom:3px solid #c4b5fd;">
    <div style="color:#e9d5ff;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">DRILL · SIMULATION · DO NOT DISPATCH</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{ticket_ref} — {site.get('name')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p><strong>Scenario:</strong> {payload.scenario}</p>
    <p><strong>Target asset:</strong> {equipment.get('name')} ({equipment.get('serial_number', '—')})</p>
    <p><strong>Started by:</strong> {user.get('email', 'master-admin')} at {now.strftime('%Y-%m-%d %H:%M UTC')}</p>
    <p style="color:#6E7476;font-size:13px;margin-top:18px;">This is a drill. The machine has NOT been isolated. KPIs will NOT include this fault. On completion a drill report will compile response metrics (acknowledge time, resolution time, attachments captured).</p>
  </div>
</div>"""
    for target in observers:
        try:
            asyncio.create_task(send_email(target, subject, html))
        except Exception:
            pass

    await _audit(site_id, user.get("id"), "drill.start",
                 drill_id=drill_id, scenario=payload.scenario, ticket_ref=ticket_ref)

    return {"ok": True, "drill_id": drill_id, "issue_id": issue_id,
            "ticket_ref": ticket_ref, "observers_notified": len(observers)}


@router.get("/master-admin/mod/drills")
async def mod_drill_list(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    drills = await db.issues.find(
        {"is_drill": True},
        {"_id": 0},
    ).sort("drill_started_at", -1).limit(100).to_list(100)
    # Decorate with site name
    for d in drills:
        org = await db.organizations.find_one({"id": d.get("organization_id")}, {"_id": 0, "name": 1, "mod_branch": 1})
        if org:
            d["site_name"] = org.get("name")
            d["site_branch"] = org.get("mod_branch")
    return {"drills": drills}


@router.post("/master-admin/mod/drills/{drill_id}/complete")
async def mod_drill_complete(drill_id: str, user: dict = Depends(get_current_user)):
    """Close a drill and compile its response-time metrics."""
    require_master_admin(user)
    drill = await db.issues.find_one({"drill_id": drill_id, "is_drill": True}, {"_id": 0})
    if not drill:
        raise HTTPException(404, "Drill not found")
    if drill.get("status") == "resolved":
        raise HTTPException(400, "Drill already completed")

    now = datetime.now(timezone.utc)
    started = datetime.fromisoformat(drill["drill_started_at"].replace("Z", "+00:00"))
    ack_at = drill.get("drill_acknowledged_at")
    ack = datetime.fromisoformat(ack_at.replace("Z", "+00:00")) if ack_at else None
    time_to_ack = int((ack - started).total_seconds()) if ack else None
    time_to_resolve = int((now - started).total_seconds())

    report = {
        "drill_id": drill_id,
        "scenario": drill.get("drill_scenario"),
        "ticket_ref": drill.get("mod_ticket_ref"),
        "site_id": drill.get("organization_id"),
        "started_at": drill["drill_started_at"],
        "acknowledged_at": ack_at,
        "completed_at": now.isoformat(),
        "time_to_acknowledge_s": time_to_ack,
        "time_to_resolve_s": time_to_resolve,
        "attachments_captured": len(drill.get("attachment_urls") or []),
    }

    await db.issues.update_one(
        {"drill_id": drill_id},
        {"$set": {
            "status": "resolved",
            "drill_completed_at": now.isoformat(),
            "drill_report": report,
        }},
    )
    await _audit(drill.get("organization_id"), user.get("id"), "drill.complete",
                 drill_id=drill_id, time_to_ack=time_to_ack, time_to_resolve=time_to_resolve)
    return {"ok": True, "report": report}


@router.get("/mod/site/drills/active")
async def mod_site_active_drills(user: dict = Depends(get_current_user)):
    """Returns the currently-active drill (if any) for the PTI user's site."""
    org = await _require_mod_site(user)
    drill = await db.issues.find_one(
        {"organization_id": org["id"], "is_drill": True, "status": {"$ne": "resolved"}},
        {"_id": 0},
    )
    return {"drill": drill}


@router.post("/mod/site/drills/{drill_id}/acknowledge")
async def mod_site_acknowledge_drill(drill_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    drill = await db.issues.find_one(
        {"drill_id": drill_id, "organization_id": org["id"], "is_drill": True},
        {"_id": 0},
    )
    if not drill:
        raise HTTPException(404, "Drill not found on this site")
    if drill.get("drill_acknowledged_at"):
        return {"ok": True, "already_acknowledged": True, "acknowledged_at": drill["drill_acknowledged_at"]}
    now = datetime.now(timezone.utc).isoformat()
    await db.issues.update_one(
        {"drill_id": drill_id},
        {"$set": {
            "drill_acknowledged_at": now,
            "drill_acknowledged_by": user.get("id"),
        }},
    )
    await _audit(org["id"], user.get("id"), "drill.acknowledge", drill_id=drill_id)
    return {"ok": True, "acknowledged_at": now}


# ══════════════════════════════════════════════════════════════════
#              EMAIL TEMPLATES
# ══════════════════════════════════════════════════════════════════
def _attachment_viewer_url(path: str, token: str, api_base: str = "") -> str:
    """Compose the signed viewer URL used by <img>/<video> tags.

    `api_base` should be an absolute URL for emails (e.g. the public
    REACT_APP_BACKEND_URL). Empty string = relative (fine for in-app use).
    """
    from urllib.parse import quote
    return f"{api_base}/api/mod/site/attachments/serve?path={quote(path)}&token={quote(token)}"


def _inline_attachment_block(doc: dict, max_images: int = 4) -> str:
    """Render an HTML strip of inline-base64 image thumbnails + video links
    suitable for email clients that strip query-string authed URLs.

    Silently returns "" if the issue has no usable image attachments. All
    image thumbs are fetched via `get_object`, downscaled isn't done here
    — the client has already compressed images to ~1920px WebP on upload,
    so typical total email size stays under ~1.5 MB for 4 photos.
    """
    paths = doc.get("attachment_urls") or []
    if not paths:
        return ""

    img_html_parts: list[str] = []
    video_html_parts: list[str] = []
    for p in paths[:max_images]:
        try:
            data, ct = get_object(p)
        except Exception:
            continue
        if (ct or "").startswith("image/"):
            b64 = base64.b64encode(data).decode("ascii")
            img_html_parts.append(
                f'<img src="data:{ct};base64,{b64}" alt="Fault photo" '
                f'style="width:160px;height:160px;border-radius:10px;'
                f'object-fit:cover;border:1px solid #334155;" />'
            )
        elif (ct or "").startswith("video/"):
            video_html_parts.append(
                '<div style="display:inline-block;width:160px;height:160px;'
                'border-radius:10px;border:1px dashed #64748b;background:#0f172a;'
                'color:#94a3b8;text-align:center;line-height:160px;font-size:12px;'
                'font-weight:600;">📹 Video attached</div>'
            )
    if not img_html_parts and not video_html_parts:
        return ""
    return (
        '<div style="padding:0 28px 22px 28px;">'
        '<div style="font-size:11px;font-weight:800;letter-spacing:0.18em;'
        'text-transform:uppercase;color:#64748b;margin-bottom:10px;">Attachments</div>'
        '<div style="display:flex;gap:8px;flex-wrap:wrap;">'
        + "".join(img_html_parts + video_html_parts)
        + '</div></div>'
    )


def _escalation_email_html(site: dict, eq: dict, doc: dict) -> str:
    attachment_block = _inline_attachment_block(doc)
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#0A0B10;color:#fff;border-radius:12px;overflow:hidden;">
  <div style="background:#b91c1c;padding:20px 28px;">
    <div style="font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;opacity:0.9;">MOD · URGENT</div>
    <h1 style="margin:8px 0 0 0;font-size:22px;">{doc['mod_ticket_ref']} — {site.get('name')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <table style="width:100%;color:#e5e7eb;font-size:14px;border-collapse:collapse;">
      <tr><td style="padding:6px 0;color:#9ca3af;width:130px;">Asset</td><td style="padding:6px 0;font-weight:600;">{eq.get('name')} ({eq.get('machine_type','')})</td></tr>
      <tr><td style="padding:6px 0;color:#9ca3af;">Fault</td><td style="padding:6px 0;">{FAULT_TYPE_LABELS.get(doc.get('fault_type_mod'), doc.get('fault_type_mod'))} · Safe to use? {doc.get('safe_in_service')} · Usable? {doc.get('usable')}</td></tr>
      <tr><td style="padding:6px 0;color:#9ca3af;">Description</td><td style="padding:6px 0;">{doc.get('issue_description','')}</td></tr>
      <tr><td style="padding:6px 0;color:#9ca3af;">Reporter</td><td style="padding:6px 0;">{doc.get('reporter_name')} · <a href="mailto:{doc.get('reporter_email')}" style="color:#19CDFF;">{doc.get('reporter_email')}</a> · {doc.get('reporter_phone')}</td></tr>
    </table>
  </div>
  {attachment_block}
</div>"""


def _confirmation_email_html(site: dict, eq: dict, doc: dict) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:22px;">Fault logged — {doc['mod_ticket_ref']}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>Thanks {doc.get('reporter_name','').split(' ')[0]} — we have your fault report for <strong>{eq.get('name')}</strong> at {site.get('name')}.</p>
    <p style="color:#6E7476;font-size:13px;">Priority: <strong style="color:#1B1D1D;">{doc.get('priority','').upper()}</strong>. We'll be in touch on {doc.get('reporter_email')} or {doc.get('reporter_phone')} as the engineer is assigned.</p>
  </div>
</div>"""
