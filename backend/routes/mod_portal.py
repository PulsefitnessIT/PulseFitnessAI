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
    # Iter 216h113h — MOD staff records have a `rank` field
    # (Sgt, Cpl, LCpl, etc.). Stored alongside the historical `role`
    # column (which now defaults to "PT Instructor" for MOD).
    rank: Optional[str] = Field(default=None, max_length=40)
    role: Optional[str] = Field(default=None, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=40)


class StaffUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    rank: Optional[str] = Field(default=None, max_length=40)
    role: Optional[str] = Field(default=None, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=5, max_length=40)


class StaffTransferRequest(BaseModel):
    """Move one staff record from this site to another site within the
    same MOD force (Army/RAF/Navy). The destination site_id MUST belong
    to the same force or the request is rejected."""
    staff_id: str
    destination_site_id: str
    reason: Optional[str] = Field(default=None, max_length=400)


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


async def _audit(
    site_id: str,
    user_id: Optional[str],
    action: str,
    *,
    request: Optional[Request] = None,
    user: Optional[dict] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    **kw,
) -> None:
    """Iter 216h115 — delegates to the tamper-evident audit module.

    Kept as a thin wrapper so existing call sites that pass positional
    ``site_id, user_id, action`` continue to work. ``request`` and
    ``user`` are optional for richer context.
    """
    try:
        from utils.mod_audit import audit_event
        ip = None
        user_agent = None
        if request is not None:
            try:
                ip = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
            except Exception:
                pass
        actor = user
        if actor is None and user_id:
            actor = {"id": user_id}
        await audit_event(
            site_id=site_id, action=action,
            user=actor,
            target_type=target_type, target_id=target_id,
            payload=kw, ip=ip, user_agent=user_agent,
        )
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


async def _gather_triage_context(equipment: dict, organization_id: str | None) -> str:
    """Iter 216bn — pull relevant indexed manuals + spec-sheet content
    for this equipment so AI triage doesn't hallucinate. Uses the
    `ai_extraction` payloads written by the silent file-upload indexer
    (see routes/files.py::upload_file). Best-effort, returns "" on any
    failure so triage still runs.
    """
    if not organization_id:
        return ""
    try:
        manufacturer = (equipment.get("manufacturer") or "").lower()
        model = (equipment.get("model_number") or equipment.get("model") or "").lower()
        machine_type = (equipment.get("machine_type") or equipment.get("category") or "").lower()
        # Pull at most 3 indexed files for this org. Match on manufacturer
        # OR model first; fall back to machine type. We rank by extraction
        # presence, so newer/richer documents bubble up.
        cur = db.files.find(
            {
                "organization_id": organization_id,
                "ai_extracted": True,
                "ai_extraction": {"$exists": True},
            },
            {"_id": 0, "original_filename": 1, "ai_extraction": 1},
        ).sort("ai_indexed_at", -1).limit(20)
        rows = await cur.to_list(20)
        scored = []
        for f in rows:
            ext = f.get("ai_extraction") or {}
            ei = ext.get("equipment_info") or {}
            haystack = " ".join([
                str(ei.get("manufacturer", "")),
                str(ei.get("model", "")),
                str(ei.get("equipment_type", "")),
                f.get("original_filename", ""),
            ]).lower()
            score = 0
            if manufacturer and manufacturer in haystack:
                score += 3
            if model and model in haystack:
                score += 5
            if machine_type and machine_type in haystack:
                score += 1
            if score > 0:
                scored.append((score, ext))
        scored.sort(key=lambda t: -t[0])
        if not scored:
            return ""
        chunks = []
        for _, ext in scored[:3]:
            common_faults = ext.get("common_faults") or []
            if common_faults:
                fault_lines = [
                    f"- {fb.get('fault', '?')}: {fb.get('symptoms', '')}; fix: {fb.get('fix', '')}"
                    for fb in common_faults[:5]
                ]
                chunks.append("Known faults:\n" + "\n".join(fault_lines))
            tips = ext.get("troubleshooting_tips") or []
            if tips:
                chunks.append("Troubleshooting tips:\n- " + "\n- ".join(str(t) for t in tips[:5]))
        return ("\n\n".join(chunks))[:1800]
    except Exception as e:
        logger.warning("triage context lookup failed: %s", e)
        return ""


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
        # Iter 216bn — enrich the prompt with content from the org's
        # indexed manuals/spec sheets if any match this equipment.
        org_id = equipment.get("organization_id")
        manual_context = await _gather_triage_context(equipment, org_id)
        prompt = (
            f"Equipment: {equipment.get('machine_type', equipment.get('category', 'gym machine'))} "
            f"({equipment.get('manufacturer', 'unknown')} {equipment.get('model_number', '')}).\n"
            f"Fault type: {FAULT_TYPE_LABELS.get(fault_type, fault_type)}.\n"
            f"Description: {description}\n"
            f"Onset: {onset}. Usable: {usable}. Safe in service: {safe}.\n"
        )
        if manual_context:
            prompt += (
                "\nReference excerpts from the customer's uploaded manuals/spec sheets "
                "for this equipment:\n" + manual_context + "\n"
                "Lean on these excerpts when they match the symptoms.\n"
            )
        prompt += "Return JSON only, no prose wrapper."
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
            "manual_context_used": bool(manual_context),
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
        "rank": sanitise_string(payload.rank) if payload.rank else None,
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
    if payload.rank is not None:
        updates["rank"] = sanitise_string(payload.rank) if payload.rank else None
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


# ── Personnel rotation: "Posting out" handover (Iter 216h116) ──
# Service personnel typically rotate every 2-3 years. Civilian PTI
# also turn over. We let a site formally "post out" a staff member,
# nominate a successor, and capture the open work they're leaving
# behind. The record auto-deactivates 14 days after the posting_out
# date via the proactive-nudges cron.

class PostingOutPayload(BaseModel):
    posting_out_date: str  # ISO date (yyyy-mm-dd)
    successor_id: Optional[str] = None
    handover_notes: Optional[str] = Field(default=None, max_length=2000)
    notify_successor_email: Optional[EmailStr] = None


@router.post("/mod/site/staff/{staff_id}/posting-out")
async def mod_staff_posting_out(
    staff_id: str,
    payload: PostingOutPayload,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Record a posting-out for a staff member.

    Captures the leave date, optional successor, and (if requested)
    emails the successor a handover pack listing the items the
    departing person still owns. Triggers a ``staff.posting_out``
    audit event.
    """
    org = await _require_mod_site(user)
    staff = await db.mod_site_staff.find_one(
        {"id": staff_id, "site_id": org["id"]},
        {"_id": 0},
    )
    if not staff:
        raise HTTPException(404, "Staff not found")
    try:
        posting_date = datetime.fromisoformat(payload.posting_out_date).date()
    except Exception:
        raise HTTPException(400, "posting_out_date must be ISO yyyy-mm-dd")

    successor_doc = None
    if payload.successor_id:
        successor_doc = await db.mod_site_staff.find_one(
            {"id": payload.successor_id, "site_id": org["id"]},
            {"_id": 0},
        )
        if not successor_doc:
            raise HTTPException(404, "Successor not found within this site")

    # Build a handover summary — open faults this person reported in
    # the last 90 days serve as a proxy for "stuff they still own".
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    open_faults = await db.issues.find(
        {
            "organization_id": org["id"],
            "status": {"$in": ["open", "in_progress", "awaiting_parts"]},
            "$or": [
                {"reporter_name": staff.get("name")},
                {"reporter_staff_id": staff_id},
            ],
            "created_at": {"$gte": since},
        },
        {"_id": 0, "id": 1, "mod_ticket_ref": 1, "machine_type": 1, "priority": 1},
    ).limit(100).to_list(100)

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.mod_site_staff.update_one(
        {"id": staff_id},
        {"$set": {
            "posting_out_date": posting_date.isoformat(),
            "successor_id": payload.successor_id,
            "handover_notes": (payload.handover_notes or "").strip()[:2000] or None,
            "posting_out_recorded_at": now_iso,
            "posting_out_recorded_by": user.get("id"),
        }},
    )

    # Optional handover email to the nominated successor.
    if payload.notify_successor_email:
        try:
            html = _posting_out_email_html(staff, successor_doc, posting_date, open_faults, payload.handover_notes)
            await send_email(
                payload.notify_successor_email,
                f"[Handover] {staff.get('name')} is posting out on {posting_date.isoformat()}",
                html,
            )
        except Exception as e:  # pragma: no cover
            logger.warning("Posting-out handover email failed: %s", e)

    await _audit(
        org["id"], user.get("id"), "staff.posting_out",
        request=request, user=user,
        target_type="staff", target_id=staff_id,
        posting_out_date=posting_date.isoformat(),
        successor_id=payload.successor_id,
        open_fault_count=len(open_faults),
    )
    return {
        "ok": True,
        "staff_id": staff_id,
        "posting_out_date": posting_date.isoformat(),
        "open_fault_count": len(open_faults),
        "open_faults": open_faults,
        "successor": {"id": successor_doc["id"], "name": successor_doc["name"]} if successor_doc else None,
    }


def _posting_out_email_html(
    staff: dict,
    successor: Optional[dict],
    posting_date,
    open_faults: list,
    notes: Optional[str],
) -> str:
    rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #eee;font-weight:700;'>{f.get('mod_ticket_ref','')}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;'>{f.get('machine_type','')}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-transform:uppercase;font-size:11px;'>{f.get('priority','')}</td></tr>"
        for f in open_faults
    ) or "<tr><td colspan='3' style='padding:10px;color:#6E7476;'>No outstanding open tickets — clean handover.</td></tr>"
    note_block = (
        f"<p style='margin:14px 0;padding:10px 14px;background:#F5F7F8;border-left:3px solid #19CDFF;'>{notes}</p>"
        if notes else ""
    )
    successor_line = (
        f"<p>You have been named the successor for <strong>{staff.get('name')}</strong> "
        f"who is posting out on <strong>{posting_date.isoformat()}</strong>.</p>"
        if successor else
        f"<p><strong>{staff.get('name')}</strong> is posting out on "
        f"<strong>{posting_date.isoformat()}</strong> — please brief in their successor.</p>"
    )
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Posting-out handover</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{staff.get('name','')}</h1>
  </div>
  <div style="padding:22px 28px;">
    {successor_line}
    {note_block}
    <h3 style="margin:16px 0 8px 0;font-size:14px;">Open tickets to take over</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #eee;">
      <thead><tr style="background:#F5F7F8;">
        <th style='text-align:left;padding:6px 10px;'>Ticket</th>
        <th style='text-align:left;padding:6px 10px;'>Asset</th>
        <th style='text-align:left;padding:6px 10px;'>Priority</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""


# ── Force-scoped staff search + transfer (Iter 216h113e) ─────
# Lets a MOD site move one of its staff to another site within the
# SAME MOD force (Army↔Army, RAF↔RAF, Navy↔Navy). This is a Pulse
# Fitness "Staffing" feature for MOD tenants — Army can never see or
# transfer to RAF/Navy sites and vice-versa.
@router.get("/mod/site/staff-search")
async def mod_staff_search(
    q: str = Query("", max_length=120),
    user: dict = Depends(get_current_user),
):
    """Search active staff across all sites in the caller's force.
    Returns matches with their current site_name so the caller can
    decide who to transfer. The caller's own site is excluded from
    results to avoid confusion (use the standard /staff list for
    your own staff)."""
    org = await _require_mod_site(user)
    force = (org.get("mod_force") or "").lower()
    if force not in {"army", "navy", "raf"}:
        raise HTTPException(400, "Site has no force assignment")

    # All sites in the same force.
    sites = await db.organizations.find(
        {"account_type": "mod_site", "mod_force": force, "is_mod": True},
        {"_id": 0, "id": 1, "name": 1, "mod_branch": 1},
    ).to_list(2000)
    site_by_id = {s["id"]: s for s in sites}
    if not site_by_id:
        return {"results": [], "force": force.upper()}

    # Build query — case-insensitive name OR email contains.
    needle = (q or "").strip()
    staff_q: dict = {
        "site_id": {"$in": list(site_by_id.keys())},
        "is_active": {"$ne": False},
    }
    if needle:
        # Escape regex special chars to avoid ReDoS / surprises.
        import re as _re
        rx = {"$regex": _re.escape(needle), "$options": "i"}
        staff_q["$or"] = [{"name": rx}, {"email": rx}]

    rows = await db.mod_site_staff.find(
        staff_q,
        {"_id": 0, "id": 1, "name": 1, "rank": 1, "role": 1, "email": 1, "phone": 1, "site_id": 1, "last_reported_at": 1},
    ).sort("name", 1).limit(50).to_list(50)

    own_site_id = org["id"]
    out = []
    for r in rows:
        site = site_by_id.get(r["site_id"]) or {}
        out.append({
            "id": r["id"],
            "name": r.get("name"),
            "rank": r.get("rank"),
            "role": r.get("role"),
            "email": r.get("email"),
            "phone": r.get("phone"),
            "current_site_id": r["site_id"],
            "current_site_name": site.get("name") or "(unknown site)",
            "current_branch": site.get("mod_branch"),
            "is_own_site": r["site_id"] == own_site_id,
            "last_reported_at": r.get("last_reported_at"),
        })
    return {"results": out, "force": force.upper(), "matches": len(out)}


@router.get("/mod/site/transfer-targets")
async def mod_transfer_targets(user: dict = Depends(get_current_user)):
    """List sites the caller can transfer staff TO — every other site
    in the same force. Used to populate the destination picker."""
    org = await _require_mod_site(user)
    force = (org.get("mod_force") or "").lower()
    if force not in {"army", "navy", "raf"}:
        raise HTTPException(400, "Site has no force assignment")
    sites = await db.organizations.find(
        {
            "account_type": "mod_site",
            "mod_force": force,
            "is_mod": True,
            "id": {"$ne": org["id"]},
        },
        {"_id": 0, "id": 1, "name": 1, "mod_branch": 1},
    ).sort("name", 1).to_list(2000)
    return {
        "force": force.upper(),
        "current_site_id": org["id"],
        "current_site_name": org.get("name"),
        "sites": [
            {"id": s["id"], "name": s["name"], "branch": s.get("mod_branch")}
            for s in sites
        ],
    }


@router.post("/mod/site/staff/transfer")
async def mod_staff_transfer(
    payload: StaffTransferRequest,
    user: dict = Depends(get_current_user),
):
    """Move a single staff record to a destination site WITHIN THE
    SAME FORCE. Caller must be at a site that currently owns the
    staff member, OR at the destination site (i.e. either side of a
    transfer can initiate it). Cross-force transfers are rejected."""
    org = await _require_mod_site(user)
    caller_site_id = org["id"]
    caller_force = (org.get("mod_force") or "").lower()
    if caller_force not in {"army", "navy", "raf"}:
        raise HTTPException(400, "Caller site has no force assignment")

    # Fetch the staff record (it can live at ANY site in the force).
    staff = await db.mod_site_staff.find_one({"id": payload.staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "Staff member not found")

    source_site = await db.organizations.find_one(
        {"id": staff["site_id"]}, {"_id": 0, "id": 1, "name": 1, "mod_force": 1, "mod_branch": 1},
    )
    dest_site = await db.organizations.find_one(
        {"id": payload.destination_site_id, "account_type": "mod_site"},
        {"_id": 0, "id": 1, "name": 1, "mod_force": 1, "mod_branch": 1, "is_mod": 1},
    )
    if not source_site or not dest_site:
        raise HTTPException(404, "Source or destination site not found")

    # Force lock — Army↔Army, RAF↔RAF, Navy↔Navy only.
    src_force = (source_site.get("mod_force") or "").lower()
    dst_force = (dest_site.get("mod_force") or "").lower()
    if src_force != caller_force or dst_force != caller_force:
        raise HTTPException(
            403,
            f"Cross-force transfers are not permitted. Staff member belongs "
            f"to {src_force.upper() or 'unknown'}; destination is "
            f"{dst_force.upper() or 'unknown'}; you are at {caller_force.upper()}.",
        )

    # Caller must be either the source or destination site (auditable).
    if caller_site_id not in {source_site["id"], dest_site["id"]}:
        raise HTTPException(
            403,
            "You can only initiate transfers involving your own site.",
        )

    if source_site["id"] == dest_site["id"]:
        raise HTTPException(400, "Source and destination sites are the same")

    # Idempotency / collision: same email already exists at destination?
    email_lc = (staff.get("email_lc") or (staff.get("email") or "").lower().strip())
    if email_lc:
        clash = await db.mod_site_staff.find_one({
            "site_id": dest_site["id"],
            "email_lc": email_lc,
            "is_active": {"$ne": False},
            "id": {"$ne": staff["id"]},
        }, {"_id": 0, "id": 1})
        if clash:
            raise HTTPException(
                409,
                f"A staff member with this email is already active at "
                f"{dest_site['name']}. Resolve the duplicate before transferring.",
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    transfer_record = {
        "from_site_id": source_site["id"],
        "from_site_name": source_site.get("name"),
        "to_site_id": dest_site["id"],
        "to_site_name": dest_site.get("name"),
        "transferred_at": now_iso,
        "transferred_by": user.get("email") or user.get("id"),
        "reason": (payload.reason or "").strip() or None,
    }
    await db.mod_site_staff.update_one(
        {"id": staff["id"]},
        {
            "$set": {
                "site_id": dest_site["id"],
                "updated_at": now_iso,
            },
            "$push": {"transfer_history": transfer_record},
        },
    )

    # Audit at BOTH sites so the trail is visible to either operator.
    await _audit(
        source_site["id"], user.get("id"), "staff.transfer.out",
        staff_id=staff["id"], to_site_id=dest_site["id"], reason=transfer_record["reason"],
    )
    await _audit(
        dest_site["id"], user.get("id"), "staff.transfer.in",
        staff_id=staff["id"], from_site_id=source_site["id"], reason=transfer_record["reason"],
    )

    # Email both unit PTIs (best-effort — never fail the transfer).
    try:
        await _send_transfer_emails(
            staff=staff,
            source_site=source_site,
            dest_site=dest_site,
            actor_email=user.get("email") or "MOD Service Portal",
            reason=transfer_record["reason"],
            transferred_at=now_iso,
        )
    except Exception:
        logger.exception("transfer email dispatch failed staff=%s", staff.get("id"))

    return {
        "ok": True,
        "staff_id": staff["id"],
        "staff_name": staff.get("name"),
        "from_site_name": source_site.get("name"),
        "to_site_name": dest_site.get("name"),
        "transferred_at": now_iso,
    }


async def _site_pti_recipients(site_id: str) -> list[str]:
    """Return the email addresses to notify for a MOD site — the
    owners/managers (`role in ['owner','manager']`) of that site.
    Falls back to the org's `primary_contact_email` if no users are
    enrolled yet."""
    users = await db.users.find(
        {
            "organization_id": site_id,
            "is_mod_user": True,
            "role": {"$in": ["owner", "manager"]},
            "status": "active",
        },
        {"_id": 0, "email": 1},
    ).to_list(20)
    out = [u["email"] for u in users if u.get("email")]
    if not out:
        org = await db.organizations.find_one(
            {"id": site_id}, {"_id": 0, "primary_contact_email": 1},
        )
        if org and org.get("primary_contact_email"):
            out.append(org["primary_contact_email"])
    # De-dupe while preserving order.
    seen, dedup = set(), []
    for e in out:
        e_lc = e.lower()
        if e_lc not in seen:
            seen.add(e_lc)
            dedup.append(e)
    return dedup


def _format_transfer_email(
    *,
    staff_name: str,
    direction: str,            # "out" | "in"
    counterpart_site: str,
    own_site: str,
    actor_email: str,
    reason: Optional[str],
    transferred_at: str,
) -> tuple[str, str]:
    """Return (subject, html) for the transfer email. Identical
    structure for the source + destination side — the wording flips
    on `direction`."""
    if direction == "out":
        verb = "transferred from your site"
        prep = "to"
        intro = (
            f"<strong>{staff_name}</strong> has been transferred from "
            f"<strong>{own_site}</strong> to <strong>{counterpart_site}</strong>."
        )
    else:
        verb = "transferred to your site"
        prep = "from"
        intro = (
            f"<strong>{staff_name}</strong> has been transferred from "
            f"<strong>{counterpart_site}</strong> to <strong>{own_site}</strong>."
        )
    subject = f"MOD staff {verb}: {staff_name} {prep} {counterpart_site}"

    reason_block = ""
    if reason:
        reason_block = (
            f'<p style="margin:12px 0 0;color:#505759;"><strong>Reason:</strong> '
            f'{reason}</p>'
        )

    html = f"""
    <div style="font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#F8F9FA;padding:24px;">
      <div style="max-width:600px;margin:0 auto;background:#FFFFFF;border:1px solid #E4E4E7;border-radius:18px;overflow:hidden;">
        <div style="background:#212721;padding:16px 24px;color:#66CCFF;font-size:11px;letter-spacing:0.28em;font-weight:700;text-transform:uppercase;">
          MOD Service Portal · Staff Transfer
        </div>
        <div style="padding:24px;color:#212721;line-height:1.55;">
          <h2 style="margin:0 0 12px;font-size:20px;font-weight:800;letter-spacing:-0.01em;">
            {staff_name} {verb}
          </h2>
          <p style="margin:0;color:#505759;">{intro}</p>
          {reason_block}
          <table style="margin:18px 0 0;border-collapse:collapse;width:100%;font-size:13px;">
            <tr>
              <td style="padding:6px 0;color:#A2ACAB;width:40%;">Transferred at</td>
              <td style="padding:6px 0;color:#212721;">{transferred_at}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#A2ACAB;">Initiated by</td>
              <td style="padding:6px 0;color:#212721;">{actor_email}</td>
            </tr>
          </table>
          <p style="margin:20px 0 0;color:#A2ACAB;font-size:11px;line-height:1.6;">
            This is an automated notification from the Pulse Fitness Service Portal for the
            Ministry of Defence. Access is monitored and recorded.
          </p>
        </div>
      </div>
    </div>
    """
    return subject, html


async def _send_transfer_emails(
    *,
    staff: dict,
    source_site: dict,
    dest_site: dict,
    actor_email: str,
    reason: Optional[str],
    transferred_at: str,
):
    """Email the unit PTIs at BOTH the source and destination sites
    so the in-bound + out-bound chains stay informed. Best-effort —
    each recipient is sent in parallel; failures are logged but never
    bubble back to the API caller."""
    from utils.email import send_email

    src_recipients = await _site_pti_recipients(source_site["id"])
    dst_recipients = await _site_pti_recipients(dest_site["id"])
    staff_name = staff.get("name") or "Staff member"

    # Source side
    if src_recipients:
        subject, html = _format_transfer_email(
            staff_name=staff_name,
            direction="out",
            counterpart_site=dest_site.get("name") or "destination site",
            own_site=source_site.get("name") or "your site",
            actor_email=actor_email,
            reason=reason,
            transferred_at=transferred_at,
        )
        for r in src_recipients:
            try:
                await send_email(to=r, subject=subject, html=html, organization_id=source_site["id"])
            except Exception:
                logger.warning("transfer email to %s failed", r)

    # Destination side
    if dst_recipients:
        subject, html = _format_transfer_email(
            staff_name=staff_name,
            direction="in",
            counterpart_site=source_site.get("name") or "source site",
            own_site=dest_site.get("name") or "your site",
            actor_email=actor_email,
            reason=reason,
            transferred_at=transferred_at,
        )
        for r in dst_recipients:
            try:
                await send_email(to=r, subject=subject, html=html, organization_id=dest_site["id"])
            except Exception:
                logger.warning("transfer email to %s failed", r)


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

    # Iter 216h115 — Scan free-text inputs for OFFICIAL-SENSITIVE-or-
    # higher markers. We DON'T block; instead we persist the flags
    # and let HQ review the record. Caller is told via the response
    # so the UI can prompt the reporter to redact if needed.
    from utils.mod_classification import scan_many
    classification_flags = scan_many([
        payload.description, payload.onset,
        payload.reporter_name, payload.reporter_phone,
    ])

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
        "classification_flags": classification_flags,
        "classification_flagged": bool(classification_flags),
        "created_at": now.isoformat(),
    }
    await db.issues.insert_one(doc)

    # Iter 216h115 — When a classification flag is raised, email HQ +
    # the on-call mailbox so a human reviews the record.
    if classification_flags:
        try:
            await _audit(
                site_id, user.get("id"), "fault.classification_flag",
                request=request, user=user,
                target_type="issue", target_id=issue_id,
                ticket_ref=ticket_ref,
                flag_count=len(classification_flags),
                flag_labels=sorted({f["label"] for f in classification_flags}),
            )
        except Exception:  # pragma: no cover
            pass

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

    # Iter 216h114 — Route fault to the machine's configured supplier so
    # MOD sites can address requests to decentralised suppliers (each
    # MOD site may have a different DIO / DEFCON service contract).
    # Order of resolution:
    #   1. Equipment's explicit `supplier_id` (preferred — direct link)
    #   2. Equipment's `supplier` name (matched on supplier directory)
    #   3. Fall back to manufacturer_keywords auto-match
    try:
        supplier_doc = await _resolve_equipment_supplier(equipment, site_id)
        supplier_email = (supplier_doc or {}).get("email", "").strip() if supplier_doc else ""
        if supplier_email:
            asyncio.create_task(send_email(
                supplier_email,
                f"[Fault Log] {ticket_ref} — {org.get('name')} — {equipment.get('name')}",
                _supplier_fault_email_html(org, equipment, doc, supplier_doc),
            ))
            doc["supplier_notified_email"] = supplier_email
            doc["supplier_notified_name"] = supplier_doc.get("name", "")
            await db.issues.update_one(
                {"id": issue_id},
                {"$set": {
                    "supplier_notified_email": supplier_email,
                    "supplier_notified_name": supplier_doc.get("name", ""),
                }},
            )
    except Exception as e:  # pragma: no cover
        logger.warning("MOD supplier-routed fault email failed: %s", e)

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
        "classification_flags": classification_flags,
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


# Iter 216h115 — Acceptance / closure loop.
# When a fault is marked resolved we email the original reporter a
# secret token link. They tap "Confirm fix" (or "Still broken") which
# hits a public endpoint that captures their verdict + a 1-5 rating.
# Faults left unconfirmed after 48h get reopened by the daily cron in
# ``utils/mod_acceptance.py`` and flagged ``awaiting_reporter_review``.

import secrets as _secrets_acc


class ResolveBody(BaseModel):
    resolution_note: str = Field(default="", max_length=2000)


def _confirm_fix_token() -> str:
    return _secrets_acc.token_urlsafe(24)


def _confirm_fix_email_html(site: dict, issue: dict, link: str) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Confirm fix</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{issue.get('mod_ticket_ref','')} marked resolved</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>The fault you raised at <strong>{site.get('name','')}</strong> has been marked resolved.</p>
    <p>Please confirm whether the machine is back in service. If we don't hear from you in 48 hours the ticket will auto-reopen.</p>
    <div style="margin:18px 0;">
      <a href="{link}" style="display:inline-block;background:#19CDFF;color:#0A0B10;padding:12px 18px;border-radius:8px;font-weight:800;text-decoration:none;">Confirm fix &amp; rate</a>
    </div>
    <p style="color:#6E7476;font-size:12px;">Link is single-use and expires in 14 days.</p>
  </div>
</div>"""


@router.post("/mod/site/faults/{issue_id}/mark-resolved")
async def mod_mark_fault_resolved(
    issue_id: str,
    body: ResolveBody,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Site user (PTI or shared kiosk) marks a fault resolved.

    Triggers the acceptance email to the original reporter so they can
    independently confirm the machine is back in service.
    """
    org = await _require_mod_site(user)
    issue = await db.issues.find_one(
        {"id": issue_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not issue:
        raise HTTPException(404, "Fault not found")
    if issue.get("status") == "resolved":
        return {"ok": True, "already_resolved": True}

    now = datetime.now(timezone.utc)
    token = _confirm_fix_token()
    await db.issues.update_one(
        {"id": issue_id},
        {"$set": {
            "status": "resolved",
            "resolved_at": now.isoformat(),
            "resolved_by_user_id": user.get("id"),
            "resolved_by_email": user.get("email"),
            "resolution_note": (body.resolution_note or "").strip(),
            "acceptance_token": token,
            "acceptance_sent_at": now.isoformat(),
            "acceptance_status": "pending",
        }},
    )

    # Also bring the equipment back into service if it was isolated.
    try:
        await db.equipment.update_one(
            {"id": issue.get("equipment_id"), "status": "out_of_service"},
            {"$set": {"status": "active"}},
        )
    except Exception:
        pass

    # Email the reporter with the confirm-fix link.
    base = (os.environ.get("FRONTEND_URL")
            or os.environ.get("REACT_APP_BACKEND_URL", "")).replace("/api", "").rstrip("/")
    link = f"{base}/mod/confirm-fix/{token}"
    try:
        if issue.get("reporter_email"):
            asyncio.create_task(send_email(
                issue["reporter_email"],
                f"Confirm fix — {issue.get('mod_ticket_ref','')}",
                _confirm_fix_email_html(org, issue, link),
            ))
    except Exception:  # pragma: no cover
        pass

    await _audit(
        org["id"], user.get("id"), "fault.resolve",
        request=request, user=user,
        target_type="issue", target_id=issue_id,
        ticket_ref=issue.get("mod_ticket_ref"),
        resolution_note=(body.resolution_note or "")[:200],
    )
    return {"ok": True, "issue_id": issue_id, "acceptance_token_sent": True}


class ConfirmFixBody(BaseModel):
    confirmed: bool
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=2000)


@router.post("/public/mod-fault-confirm/{token}")
async def public_confirm_fix(token: str, body: ConfirmFixBody):
    """Public endpoint hit by the email-link. Records the reporter's
    verdict. No auth required — the token IS the auth."""
    issue = await db.issues.find_one(
        {"acceptance_token": token},
        {"_id": 0, "id": 1, "organization_id": 1, "mod_ticket_ref": 1,
         "acceptance_status": 1, "acceptance_sent_at": 1,
         "reporter_email": 1, "supplier_notified_email": 1,
         "supplier_notified_name": 1},
    )
    if not issue:
        raise HTTPException(404, "Invalid or expired link")
    if issue.get("acceptance_status") == "confirmed":
        return {"ok": True, "already_confirmed": True}

    # Token expiry (14 days).
    try:
        sent_at = datetime.fromisoformat(issue.get("acceptance_sent_at"))
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - sent_at).days > 14:
            raise HTTPException(410, "Link has expired")
    except HTTPException:
        raise
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).isoformat()
    update: dict = {
        "acceptance_status": "confirmed" if body.confirmed else "rejected",
        "acceptance_confirmed_at": now_iso,
        "acceptance_rating": body.rating,
        "acceptance_comment": (body.comment or "").strip()[:2000] or None,
        # Invalidate the token so the link is single-use.
        "acceptance_token": None,
    }
    if not body.confirmed:
        # Reporter says still broken — auto-reopen.
        update.update({
            "status": "open",
            "reopened_at": now_iso,
            "reopened_reason": "reporter_rejected_fix",
        })

    await db.issues.update_one({"id": issue["id"]}, {"$set": update})

    # Audit
    await _audit(
        issue["organization_id"], None,
        "fault.confirm_fix" if body.confirmed else "fault.reopen",
        target_type="issue", target_id=issue["id"],
        ticket_ref=issue.get("mod_ticket_ref"),
        confirmed=body.confirmed, rating=body.rating,
    )

    # If a supplier was on the ticket and the reporter rated us, mirror
    # that onto a supplier-scorecard collection so HQ rollups can use it.
    if body.rating is not None and issue.get("supplier_notified_name"):
        try:
            await db.mod_supplier_scorecard.insert_one({
                "id": str(uuid.uuid4()),
                "site_id": issue["organization_id"],
                "issue_id": issue["id"],
                "supplier_name": issue.get("supplier_notified_name"),
                "supplier_email": issue.get("supplier_notified_email"),
                "rating": body.rating,
                "confirmed": body.confirmed,
                "comment": (body.comment or "")[:500] or None,
                "created_at": now_iso,
            })
        except Exception:  # pragma: no cover
            pass

    return {
        "ok": True,
        "ticket_ref": issue.get("mod_ticket_ref"),
        "confirmed": body.confirmed,
        "rating": body.rating,
    }


@router.get("/public/mod-fault-confirm/{token}")
async def public_confirm_fix_lookup(token: str):
    """Read-only lookup — lets the frontend confirm a token is still
    valid before showing the rating form."""
    issue = await db.issues.find_one(
        {"acceptance_token": token},
        {"_id": 0, "id": 1, "mod_ticket_ref": 1, "acceptance_sent_at": 1,
         "acceptance_status": 1, "machine_type": 1, "serial_number": 1,
         "organization_id": 1},
    )
    if not issue:
        raise HTTPException(404, "Invalid or expired link")
    site = await db.organizations.find_one(
        {"id": issue["organization_id"]}, {"_id": 0, "name": 1},
    )
    return {
        "ticket_ref": issue.get("mod_ticket_ref"),
        "machine_type": issue.get("machine_type"),
        "serial_number": issue.get("serial_number"),
        "site_name": (site or {}).get("name"),
        "acceptance_status": issue.get("acceptance_status"),
    }


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


# Iter 216h115 — HQ-level audit visibility + verifiable export.
# MOD HQ users (mod_org / mod_branch) can browse and export the audit
# trail for any site within their scope. The export PDF/CSV walks the
# tamper-evident hash chain and includes a chain-integrity verdict so
# DIO / ISO 27001 auditors can trust the file at face value.

@router.get("/mod/pro/audit-log/{site_id}")
async def mod_hq_audit_log(
    site_id: str,
    limit: int = 500,
    user: dict = Depends(get_current_user),
):
    """Return the most-recent audit rows for ``site_id``. Caller must
    be a MOD HQ user with the target site in their scope."""
    org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id}, {"_id": 0, "mod_root_id": 1, "mod_branch": 1,
                          "account_type": 1, "name": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != org.get("mod_root_id"):
        raise HTTPException(403, "Site is outside your MOD organisation scope")
    if org.get("account_type") == "mod_branch" and site.get("mod_branch") != org.get("mod_branch"):
        raise HTTPException(403, "Site is outside your branch scope")
    from utils.mod_audit import list_audit_for_site, verify_audit_chain
    rows = await list_audit_for_site(site_id, limit=max(1, min(int(limit), 2000)))
    integrity = await verify_audit_chain(site_id)
    return {
        "site_id": site_id,
        "site_name": site.get("name"),
        "rows": rows,
        "integrity": integrity,
    }


@router.get("/mod/pro/audit-log/{site_id}/export.csv")
async def mod_hq_audit_export_csv(
    site_id: str, user: dict = Depends(get_current_user),
):
    """Stream the entire site audit log as CSV with a footer line that
    declares the chain-integrity result. Suitable for DIO inspection
    packs and ISO 27001 evidence bundles."""
    import csv as _csv
    import io as _io
    org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id}, {"_id": 0, "mod_root_id": 1, "mod_branch": 1,
                          "account_type": 1, "name": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != org.get("mod_root_id"):
        raise HTTPException(403, "Site is outside your MOD organisation scope")
    if org.get("account_type") == "mod_branch" and site.get("mod_branch") != org.get("mod_branch"):
        raise HTTPException(403, "Site is outside your branch scope")

    from utils.mod_audit import verify_audit_chain
    integrity = await verify_audit_chain(site_id)

    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow([
        "created_at", "action", "actor_email", "actor_role",
        "target_type", "target_id", "payload_json", "ip",
        "prev_hash", "row_hash",
    ])
    cursor = db.mod_audit_log.find(
        {"site_id": site_id}, {"_id": 0},
    ).sort("created_at", 1)
    rows = 0
    async for r in cursor:
        rows += 1
        import json as _json
        writer.writerow([
            r.get("created_at", ""),
            r.get("action", ""),
            r.get("actor_email", ""),
            r.get("actor_role", ""),
            r.get("target_type", ""),
            r.get("target_id", ""),
            _json.dumps(r.get("payload", {}), separators=(",", ":")),
            r.get("ip", ""),
            r.get("prev_hash", ""),
            r.get("row_hash", ""),
        ])
    writer.writerow([])
    writer.writerow([
        f"# CHAIN INTEGRITY: {'VALID' if integrity['valid'] else 'BROKEN'} · "
        f"rows={integrity['rows']} · "
        f"first_break_at={integrity.get('first_break_at') or 'n/a'} · "
        f"exported_at={datetime.now(timezone.utc).isoformat()} · "
        f"exported_by={user.get('email','')}",
    ])
    csv_body = buf.getvalue()
    filename = f"mod-audit-{site_id}-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/master-admin/mod/sweep-now")
async def mod_admin_sweep_now(user: dict = Depends(get_current_user)) -> dict:
    """Manually trigger MOD background sweepers (posting-outs, compliance
    reminders, acceptance timeouts). Master admin only — primarily a
    test / ops hook."""
    require_master_admin(user)
    from utils.mod_postings import sweep_posting_outs
    from utils.mod_acceptance import sweep_pending_acceptances
    from routes.mod_compliance import sweep_compliance_reminders
    postings = await sweep_posting_outs()
    acceptances = await sweep_pending_acceptances()
    compliance = await sweep_compliance_reminders()
    return {
        "postings": postings,
        "acceptances": acceptances,
        "compliance": compliance,
    }


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


# ── DIO contract integration stub (Iter 216h116) ───────────────
# Defence Infrastructure Organisation manages base maintenance
# contracts. We can't talk to their API yet but we can capture the
# contract reference + escalation contact per site, and selectively
# route faults to DIO when they're command-significant.

class DIOContractPayload(BaseModel):
    dio_contract_ref: Optional[str] = Field(default=None, max_length=120)
    dio_contact_email: Optional[EmailStr] = None
    dio_contact_name: Optional[str] = Field(default=None, max_length=120)


@router.put("/mod/pro/sites/{site_id}/dio-contract")
async def mod_hq_set_dio_contract(
    site_id: str,
    payload: DIOContractPayload,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """HQ owner/manager records the DIO contract reference + the
    nominated escalation contact for a child site."""
    org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"},
        {"_id": 0, "mod_root_id": 1, "mod_branch": 1, "name": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != org.get("mod_root_id"):
        raise HTTPException(403, "Site is outside your MOD organisation scope")
    if org.get("account_type") == "mod_branch" and site.get("mod_branch") != org.get("mod_branch"):
        raise HTTPException(403, "Site is outside your branch scope")

    updates = payload.model_dump(exclude_unset=True)
    updates["dio_updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["dio_updated_by"] = user.get("id")
    await db.organizations.update_one({"id": site_id}, {"$set": updates})
    await _audit(
        site_id, user.get("id"), "compliance.event",
        request=request, user=user,
        target_type="organization", target_id=site_id,
        kind="dio_contract.set",
        dio_contract_ref=updates.get("dio_contract_ref"),
    )
    return {"ok": True, **updates}


@router.get("/mod/pro/sites/{site_id}/dio-contract")
async def mod_hq_get_dio_contract(site_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"},
        {"_id": 0, "mod_root_id": 1, "mod_branch": 1, "name": 1,
         "dio_contract_ref": 1, "dio_contact_email": 1, "dio_contact_name": 1,
         "dio_updated_at": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != org.get("mod_root_id"):
        raise HTTPException(403, "Site is outside your MOD organisation scope")
    if org.get("account_type") == "mod_branch" and site.get("mod_branch") != org.get("mod_branch"):
        raise HTTPException(403, "Site is outside your branch scope")
    return {
        "site_id": site_id,
        "site_name": site.get("name"),
        "dio_contract_ref": site.get("dio_contract_ref"),
        "dio_contact_email": site.get("dio_contact_email"),
        "dio_contact_name": site.get("dio_contact_name"),
        "dio_updated_at": site.get("dio_updated_at"),
    }


class DIOEscalateBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/mod/site/faults/{issue_id}/escalate-to-dio")
async def mod_escalate_to_dio(
    issue_id: str,
    body: DIOEscalateBody,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Site user or HQ flags a fault for DIO. Sends a structured email
    to the site's configured DIO contact (if one exists) and stamps
    ``escalate_to_dio=true`` on the issue."""
    org = await _require_mod_site(user)
    issue = await db.issues.find_one(
        {"id": issue_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not issue:
        raise HTTPException(404, "Fault not found")
    site = await db.organizations.find_one(
        {"id": org["id"]},
        {"_id": 0, "name": 1, "dio_contract_ref": 1,
         "dio_contact_email": 1, "dio_contact_name": 1},
    )
    if not site or not site.get("dio_contact_email"):
        raise HTTPException(
            409,
            "Site has no DIO contact configured. Ask HQ to set it in the site drawer.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.issues.update_one(
        {"id": issue_id},
        {"$set": {
            "escalated_to_dio": True,
            "dio_escalated_at": now_iso,
            "dio_escalated_by": user.get("id"),
            "dio_escalation_note": (body.note or "").strip()[:2000] or None,
        }},
    )

    # Best-effort email.
    try:
        equipment = await db.equipment.find_one(
            {"id": issue.get("equipment_id")},
            {"_id": 0, "name": 1, "manufacturer": 1, "model": 1, "serial_number": 1},
        ) or {}
        html = _dio_escalation_email_html(site, issue, equipment, body.note)
        await send_email(
            site["dio_contact_email"],
            f"[DIO Escalation] {issue.get('mod_ticket_ref')} — {site.get('name')}",
            html,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("DIO escalation email failed: %s", e)

    await _audit(
        org["id"], user.get("id"), "compliance.event",
        request=request, user=user,
        target_type="issue", target_id=issue_id,
        kind="dio.escalate",
        ticket_ref=issue.get("mod_ticket_ref"),
    )
    return {
        "ok": True,
        "escalated_to": site["dio_contact_email"],
        "contract_ref": site.get("dio_contract_ref"),
    }


def _dio_escalation_email_html(site: dict, issue: dict, eq: dict, note: Optional[str]) -> str:
    note_block = (
        f"<p style='margin:14px 0;padding:10px 14px;background:#F5F7F8;border-left:3px solid #19CDFF;'><strong>Escalation note:</strong><br>{note}</p>"
        if note else ""
    )
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#0A2540;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · DIO Escalation</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{issue.get('mod_ticket_ref','')} — {site.get('name','')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>Dear {site.get('dio_contact_name','Team')},</p>
    <p>This fault has been escalated to DIO under contract reference <strong>{site.get('dio_contract_ref','—')}</strong>.</p>
    {note_block}
    <table style="width:100%;font-size:13px;margin-top:10px;">
      <tr><td style='padding:6px 0;color:#6E7476;'>Ticket</td><td style='font-weight:700;'>{issue.get('mod_ticket_ref','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Priority</td><td style='font-weight:700;text-transform:uppercase;'>{issue.get('priority','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Asset</td><td>{eq.get('name','')} · {eq.get('manufacturer','')} {eq.get('model','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Serial</td><td style='font-family:ui-monospace,Menlo,monospace;'>{eq.get('serial_number','—')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;vertical-align:top;'>Description</td><td>{issue.get('issue_description','')}</td></tr>
    </table>
  </div>
</div>"""


# ── HQ-level (mod_org / mod_branch) Site Login provisioning ───────
# Iter 216h114 — Owner/Manager of a MOD HQ org (e.g. British Army Head
# Office, Catterick Garrison) needs to roll out site logins for each
# of their child sites WITHOUT going through a master admin. This
# endpoint provisions (or rotates) a site's shared login on behalf of
# the HQ user, returns the new plaintext password ONCE, and optionally
# emails the credentials to a nominated contact.

class HQProvisionPayload(BaseModel):
    notify_email: EmailStr | None = None
    rotate_if_exists: bool = True


@router.post("/mod/pro/sites/{site_id}/provision-credentials")
async def mod_hq_provision_site_credentials(
    site_id: str,
    payload: HQProvisionPayload,
    user: dict = Depends(get_current_user),
):
    """Iter 216h114 — Generate / rotate a site login for a child MOD site
    on behalf of a MOD HQ user.

    Caller must be `mod_org` or `mod_branch` AND the target site must
    fall within their scope (same `mod_root_id`, plus matching
    `mod_branch` for branch-tier callers).

    Behaviour:
      • If the site has no `mod_site` user yet, one is created using a
        slug derived from the site name as the username, and a fresh
        password is minted.
      • If a `mod_site` user already exists and ``rotate_if_exists`` is
        ``True``, the password is rotated.
      • The new plaintext password is returned exactly once — the
        server only stores the bcrypt hash thereafter.
      • If ``notify_email`` is supplied, the credentials are emailed to
        that address using the standard rotation email template.
    """
    org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"}, {"_id": 0},
    )
    if not site:
        raise HTTPException(404, "MOD site not found")
    # Scope check: must share root + (branch if branch-tier)
    if site.get("mod_root_id") != org.get("mod_root_id"):
        raise HTTPException(403, "Site is outside your MOD organisation scope")
    if org.get("account_type") == "mod_branch" and site.get("mod_branch") != org.get("mod_branch"):
        raise HTTPException(403, "Site is outside your branch scope")

    from passlib.context import CryptContext
    from utils.mod_password_rotation import mint_site_password

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # Look specifically for a SHARED SITE LOGIN — a mod_site user
    # that authenticates by `username` (no email). This differentiates
    # the shared kiosk login from personnel records that may also be
    # account_type=mod_site (they sign in by email).
    site_user = await db.users.find_one(
        {
            "organization_id": site_id,
            "account_type": "mod_site",
            "username": {"$exists": True, "$nin": [None, ""]},
        },
        {"_id": 0},
    )

    # Compute the canonical username for this site (slug-based) so
    # we can rotate when it exists OR create when it doesn't.
    base_slug = (site.get("site_code") or site.get("name") or "mod-site").lower()
    base_slug = "".join(c if c.isalnum() else "-" for c in base_slug).strip("-")

    if site_user:
        if not payload.rotate_if_exists:
            raise HTTPException(
                409,
                "Site already has a login. Set rotate_if_exists=true to mint a new password.",
            )
        username = site_user["username"]
        new_password = mint_site_password(username)
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.users.update_one(
            {"id": site_user["id"]},
            {"$set": {
                "password": pwd_ctx.hash(new_password),
                "password_updated_at": now_iso,
                "rotation_reminder_stage": None,
                "rotation_reminder_sent_at": None,
            }},
        )
        await _audit(
            site_id, user.get("id"), "site_login.rotate",
            username=username, by_role=org.get("account_type"),
        )
    else:
        username = base_slug or f"mod-site-{uuid.uuid4().hex[:6]}"
        # If username collision (with a different org), append suffix.
        if await db.users.find_one({"username": username}, {"_id": 0, "id": 1}):
            username = f"{username}-{uuid.uuid4().hex[:4]}"
        new_password = mint_site_password(username)
        now_iso = datetime.now(timezone.utc).isoformat()
        # NOTE: The `users.email` index is unique and treats `null` as
        # a key value, so we MUST give shared-site logins a unique
        # placeholder email instead of `None`. The username remains
        # the actual sign-in identifier.
        placeholder_email = f"{username}@mod.site.local"
        # Just in case of collision, append a uuid suffix.
        if await db.users.find_one({"email": placeholder_email}, {"_id": 0, "id": 1}):
            placeholder_email = f"{username}+{uuid.uuid4().hex[:6]}@mod.site.local"
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "username": username,
            "email": placeholder_email,
            "password": pwd_ctx.hash(new_password),
            "full_name": site.get("name") or "MOD Site",
            "role": "owner",
            "account_type": "mod_site",
            "organization_id": site_id,
            "is_site_account": True,
            "is_mod_user": True,
            "mod_force": site.get("mod_force"),
            "password_updated_at": now_iso,
            "created_at": now_iso,
            "created_by": user.get("id"),
        })
        await _audit(
            site_id, user.get("id"), "site_login.provision",
            username=username, by_role=org.get("account_type"),
        )

    # Optional: email the credentials to the nominated contact.
    notified = False
    if payload.notify_email:
        try:
            html = _hq_provision_email_html(site, username, new_password)
            subject = f"[MOD site login] {site.get('name')} — credentials"
            await send_email(payload.notify_email, subject, html)
            notified = True
        except Exception as e:  # pragma: no cover
            logger.warning("HQ provision email failed: %s", e)

    return {
        "ok": True,
        "site_id": site_id,
        "site_name": site.get("name"),
        "username": username,
        "password": new_password,
        "rotated": bool(site_user),
        "notified_email": payload.notify_email if notified else None,
        "note": (
            "This password is shown ONCE. Copy it now — the server only "
            "stores a bcrypt hash going forward."
        ),
    }


def _hq_provision_email_html(site: dict, username: str, new_password: str) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Site Login</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{site.get('name')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>The site login for <strong>{site.get('name')}</strong> has been provisioned by your HQ.</p>
    <table style="margin-top:14px;border-collapse:collapse;">
      <tr><td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;color:#6E7476;font-size:11px;font-weight:800;text-transform:uppercase;">Username</td>
          <td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;font-weight:700;"><code>{username}</code></td></tr>
      <tr><td style="padding:8px 14px;background:#0A0B10;color:#19CDFF;border:1px solid #0A0B10;font-size:11px;font-weight:800;text-transform:uppercase;">Site code</td>
          <td style="padding:8px 14px;background:#0A0B10;color:#fff;border:1px solid #0A0B10;font-family:ui-monospace,Menlo,monospace;font-weight:700;">{new_password}</td></tr>
    </table>
    <p style="color:#6E7476;font-size:13px;margin-top:18px;">Share this with the on-site PTI via a secure channel. Sign in at <a href="https://maintenance-hub-357.preview.emergentagent.com/MODService" style="color:#19CDFF;">/MODService</a> using the username + site code.</p>
  </div>
</div>"""


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


async def _resolve_equipment_supplier(eq: dict, site_id: str) -> Optional[dict]:
    """Iter 216h114 — Resolve the supplier responsible for an equipment row.

    Resolution order:
      1. ``supplier_id`` field on the equipment (direct link)
      2. ``supplier`` name (exact match against the site/org's supplier dir)
      3. ``manufacturer`` matched against any supplier's
         ``manufacturer_keywords`` (case-insensitive)

    Returns the supplier doc or ``None`` if no match. Scope is restricted
    to the same organisation (site_id is the MOD site's organization_id).
    """
    if not eq:
        return None
    # 1. Direct id link
    supplier_id = (eq.get("supplier_id") or "").strip()
    if supplier_id:
        doc = await db.suppliers.find_one(
            {"id": supplier_id, "organization_id": site_id}, {"_id": 0},
        )
        if doc:
            return doc
    # 2. Name match
    supplier_name = (eq.get("supplier") or "").strip()
    if supplier_name:
        doc = await db.suppliers.find_one(
            {"organization_id": site_id, "name": supplier_name}, {"_id": 0},
        )
        if doc:
            return doc
    # 3. Manufacturer keyword auto-match
    manufacturer = (eq.get("manufacturer") or "").strip().lower()
    if manufacturer:
        cursor = db.suppliers.find(
            {"organization_id": site_id, "manufacturer_keywords": {"$exists": True, "$ne": []}},
            {"_id": 0},
        )
        async for s in cursor:
            for kw in (s.get("manufacturer_keywords") or []):
                if kw and kw.strip().lower() in manufacturer:
                    return s
    return None


def _supplier_fault_email_html(site: dict, eq: dict, doc: dict, supplier: dict) -> str:
    """Iter 216h114 — Email sent to a machine's configured supplier when a
    fault is logged. Contains the ticket, equipment details, reporter
    contact, and a CTA to the public case page (handled by the existing
    supplier portal flow). Branded for MOD-as-Pulse."""
    contact = (supplier or {}).get("contact_name") or (supplier or {}).get("name", "Service Team")
    attachment_block = _inline_attachment_block(doc)
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Supplier Notification</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{doc['mod_ticket_ref']} — {site.get('name')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>Dear {contact},</p>
    <p>A fault has been logged on a machine you service at <strong>{site.get('name')}</strong>. Details below — please follow up directly with the reporter.</p>
    <table style="width:100%;color:#1B1D1D;font-size:14px;border-collapse:collapse;margin-top:14px;">
      <tr><td style="padding:6px 0;color:#6E7476;width:140px;">Ticket</td><td style="padding:6px 0;font-weight:700;">{doc['mod_ticket_ref']}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Priority</td><td style="padding:6px 0;font-weight:700;">{doc.get('priority','').upper()}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Asset</td><td style="padding:6px 0;">{eq.get('name','')} ({eq.get('equipment_type', eq.get('machine_type',''))})</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Manufacturer</td><td style="padding:6px 0;">{eq.get('manufacturer','—')} · {eq.get('model','')}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Serial</td><td style="padding:6px 0;font-family:ui-monospace,Menlo,monospace;">{eq.get('serial_number','—')}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Fault</td><td style="padding:6px 0;">{FAULT_TYPE_LABELS.get(doc.get('fault_type_mod'), doc.get('fault_type_mod'))} · Safe? {doc.get('safe_in_service')} · Usable? {doc.get('usable')}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;vertical-align:top;">Description</td><td style="padding:6px 0;">{doc.get('issue_description','')}</td></tr>
      <tr><td style="padding:6px 0;color:#6E7476;">Reporter</td><td style="padding:6px 0;">{doc.get('reporter_name','')} · <a href="mailto:{doc.get('reporter_email','')}" style="color:#19CDFF;">{doc.get('reporter_email','')}</a> · {doc.get('reporter_phone','')}</td></tr>
    </table>
  </div>
  {attachment_block}
</div>"""



# ══════════════════════════════════════════════════════════════════
#         Iter 216h109 — Demo seed (Catterick Garrison) + dropdown
# ══════════════════════════════════════════════════════════════════
import secrets as _secrets
import string as _string


def _gen_pwd(n: int = 10) -> str:
    return "".join(_secrets.choice(_string.ascii_letters + _string.digits) for _ in range(n))


_CATTERICK_SUBSITES = [
    ("Vimy Lines Gym",         "ARMY-CAT-VIM"),
    ("Helles Barracks Gym",    "ARMY-CAT-HEL"),
    ("Bruneval Barracks Gym",  "ARMY-CAT-BRU"),
    ("Cambrai Lines Gym",      "ARMY-CAT-CAM"),
    ("Marne Barracks Gym",     "ARMY-CAT-MAR"),
    ("Le Cateau Barracks Gym", "ARMY-CAT-LEC"),
    ("Bourlon Barracks Gym",   "ARMY-CAT-BOU"),
]

_DEMO_PERSONNEL_TEMPLATE = [
    ("Sgt",  "Daniel Hayes",   "Vimy Lines Gym",          "+44 7700 900111"),
    ("Cpl",  "Megan Allen",    "Helles Barracks Gym",     ""),
    ("LCpl", "James OBrien",   "Bruneval Barracks Gym",   "+44 7700 900222"),
    ("WO2",  "Sarah Mitchell", "Cambrai Lines Gym",       ""),
    ("Capt", "Ben Foster",     "Marne Barracks Gym",      "+44 7700 900333"),
    ("Maj",  "Olivia Carter",  "Le Cateau Barracks Gym",  ""),
    ("Sgt",  "Tom Walker",     "Bourlon Barracks Gym",    "+44 7700 900444"),
]


@router.post("/mod/demo/seed-army-catterick")
async def seed_army_catterick(user: dict = Depends(get_current_user)):
    """Idempotent seed of the Army HQ → Catterick Garrison hierarchy.

    Creates / refreshes:
      • Army HQ                — account_type=mod_org, mod_force=army
      • Catterick Garrison     — account_type=mod_branch, mod_root_id=Army HQ
      • 7 Catterick sub-sites  — account_type=mod_site, mod_branch="Catterick Garrison"
      • One demo user per site (rank/name/site_number/mobile)
      • One owner-level demo login on Catterick Garrison

    The single demo password is returned in the response so the
    presenter has a fresh set of credentials.
    """
    require_master_admin(user)
    from utils.auth import hash_password
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    demo_password = "ArmyDemo2026!"
    pwd_hash = hash_password(demo_password)
    created = {"orgs": [], "users": []}

    # ── Army HQ ─────────────────────────────────────────────────
    army_hq = await db.organizations.find_one(
        {"account_type": "mod_org", "mod_force": "army"}, {"_id": 0},
    )
    if not army_hq:
        army_id = str(uuid.uuid4())
        army_hq = {
            "id": army_id,
            "name": "British Army — Head Office",
            "account_type": "mod_org",
            "subscription_tier": "mod_org",
            "portal_type": "service_portal",
            "enabled_modules": ["service_portal"],
            "status": "active", "created_at": now,
            "is_mod": True, "mod_force": "army",
            "mod_root_id": army_id,            # self
            "company_code": "ARMY-HQ",
            "primary_contact_name": "Army Land Forces — Health & Wellbeing",
            "primary_contact_email": "armyhq.demo@army.mod.local",
        }
        await db.organizations.insert_one(army_hq)
        created["orgs"].append({"name": army_hq["name"], "created": True})
    else:
        # Backfill missing flags so the dashboard rollup works.
        await db.organizations.update_one(
            {"id": army_hq["id"]},
            {"$set": {"is_mod": True, "mod_force": "army", "mod_root_id": army_hq["id"]}},
        )
        created["orgs"].append({"name": army_hq["name"], "created": False})

    # ── Catterick Garrison (mod_branch) ─────────────────────────
    cat = await db.organizations.find_one(
        {"account_type": "mod_branch", "name": "Catterick Garrison"}, {"_id": 0},
    )
    if not cat:
        cat_id = str(uuid.uuid4())
        cat = {
            "id": cat_id,
            "name": "Catterick Garrison",
            "account_type": "mod_branch",
            "subscription_tier": "mod_branch",
            "portal_type": "service_portal",
            "enabled_modules": ["service_portal"],
            "status": "active", "created_at": now,
            "is_mod": True, "mod_force": "army",
            "mod_root_id": army_hq["id"],
            "mod_branch": "Catterick Garrison",
            "address_line1": "Catterick Garrison",
            "city": "Catterick", "county": "North Yorkshire",
            "postcode": "DL9 3PS", "country": "United Kingdom",
            "address": "Catterick Garrison, Catterick, North Yorkshire DL9 3PS",
            "company_code": "ARMY-CAT",
            "primary_contact_name": "Catterick Garrison — Fitness HQ",
            "primary_contact_email": "catterick.demo@army.mod.local",
        }
        await db.organizations.insert_one(cat)
        created["orgs"].append({"name": cat["name"], "created": True})
    else:
        await db.organizations.update_one(
            {"id": cat["id"]},
            {"$set": {"is_mod": True, "mod_force": "army", "mod_root_id": army_hq["id"], "mod_branch": "Catterick Garrison"}},
        )
        created["orgs"].append({"name": cat["name"], "created": False})

    # ── Sub-sites (mod_site, one org per gym) ───────────────────
    site_org_map: dict[str, str] = {}
    for site_name, site_code in _CATTERICK_SUBSITES:
        existing = await db.organizations.find_one(
            {"account_type": "mod_site", "mod_branch": "Catterick Garrison", "name": site_name},
            {"_id": 0},
        )
        if existing:
            site_org_map[site_name] = existing["id"]
            await db.organizations.update_one(
                {"id": existing["id"]},
                {"$set": {"is_mod": True, "mod_force": "army", "mod_root_id": army_hq["id"], "mod_branch": "Catterick Garrison", "site_code": site_code}},
            )
            created["orgs"].append({"name": site_name, "created": False})
            continue
        oid = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": oid, "name": site_name,
            "account_type": "mod_site", "subscription_tier": "mod_site",
            "portal_type": "service_portal", "enabled_modules": ["service_portal"],
            "status": "active", "created_at": now,
            "is_mod": True, "mod_force": "army",
            "mod_root_id": army_hq["id"], "mod_branch": "Catterick Garrison",
            "site_code": site_code,
            "company_code": site_code,
        })
        site_org_map[site_name] = oid
        created["orgs"].append({"name": site_name, "created": True})

    # ── Demo personnel (one per gym, plus the Catterick HQ owner) ─
    for rank, full_name, site_name, mobile in _DEMO_PERSONNEL_TEMPLATE:
        email = f"{full_name.lower().replace(' ', '.')}@army.mod.local"
        site_org_id = site_org_map[site_name]
        parts = full_name.split(maxsplit=1)
        first_name, last_name = parts[0], (parts[1] if len(parts) > 1 else "")
        body = {
            "name": full_name, "full_name": full_name, "first_name": first_name, "last_name": last_name,
            "rank": rank, "mobile": mobile or None,
            "site_number": next((c for n, c in _CATTERICK_SUBSITES if n == site_name), None),
            "role": "staff",
            "organization_id": site_org_id,
            "account_type": "mod_site",
            "is_mod_user": True, "mod_force": "army",
            "password": pwd_hash,
            "status": "active",
        }
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing:
            await db.users.update_one({"email": email}, {"$set": body})
            created["users"].append({"email": email, "rank": rank, "name": full_name, "created": False})
        else:
            uid = str(uuid.uuid4())
            await db.users.insert_one({**body, "id": uid, "email": email, "created_at": now})
            created["users"].append({"email": email, "rank": rank, "name": full_name, "created": True})

        # Iter 216h113e — also seed a parallel `mod_site_staff` record so
        # the cross-site staff transfer feature can find these personnel
        # via search. Idempotent: upsert by (site_id, email_lc).
        # Iter 216h113h — Force-reset the staff record's site_id to
        # the canonical seed site so prior in-flight transfers don't
        # leave demo personnel stuck at the wrong gym between runs.
        # Deduplicate first (a previous bug could have created
        # multiple staff rows with the same email at different sites
        # — keep one canonical record).
        staff_email_lc = email.lower().strip()
        dupes = await db.mod_site_staff.find(
            {"email_lc": staff_email_lc}, {"_id": 0, "id": 1},
        ).to_list(20)
        if len(dupes) > 1:
            keep_id = dupes[0]["id"]
            await db.mod_site_staff.delete_many({
                "email_lc": staff_email_lc, "id": {"$ne": keep_id},
            })
        await db.mod_site_staff.update_one(
            {"email_lc": staff_email_lc},
            {"$set": {"site_id": site_org_id, "is_active": True}},
        )
        await db.mod_site_staff.update_one(
            {"site_id": site_org_id, "email_lc": staff_email_lc},
            {
                "$set": {
                    "name": full_name,
                    "rank": rank,
                    "role": "PT Instructor",
                    "email": email,
                    "email_lc": staff_email_lc,
                    "phone": mobile or "",
                    "is_active": True,
                    "site_id": site_org_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "fault_count": 0,
                    "last_reported_at": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    # Catterick Garrison HQ owner (demo presenter login)
    hq_email = "catterick.demo.lead@army.mod.local"
    hq_body = {
        "name": "Col. Catterick Demo Lead", "full_name": "Col. Catterick Demo Lead",
        "first_name": "Catterick", "last_name": "Demo Lead",
        "rank": "Col", "mobile": "+44 7700 900555",
        "site_number": "ARMY-CAT-HQ",
        "role": "owner",
        "organization_id": cat["id"],
        "account_type": "mod_branch",
        "is_mod_user": True, "mod_force": "army",
        "password": pwd_hash,
        "status": "active",
    }
    existing = await db.users.find_one({"email": hq_email}, {"_id": 0})
    if existing:
        await db.users.update_one({"email": hq_email}, {"$set": hq_body})
    else:
        await db.users.insert_one({**hq_body, "id": str(uuid.uuid4()), "email": hq_email, "created_at": now})

    # Army HQ owner (mod_org) — useful for the Head-Office rollup demo
    hq_org_email = "army.command@army.mod.local"
    hq_org_body = {
        "name": "Brig. Army Land Command", "full_name": "Brig. Army Land Command",
        "first_name": "Army", "last_name": "Land Command",
        "rank": "Brig",  "mobile": "+44 7700 900666",
        "site_number": "ARMY-HQ-001",
        "role": "owner",
        "organization_id": army_hq["id"],
        "account_type": "mod_org",
        "is_mod_user": True, "mod_force": "army",
        "password": pwd_hash, "status": "active",
    }
    existing = await db.users.find_one({"email": hq_org_email}, {"_id": 0})
    if existing:
        await db.users.update_one({"email": hq_org_email}, {"$set": hq_org_body})
    else:
        await db.users.insert_one({**hq_org_body, "id": str(uuid.uuid4()), "email": hq_org_email, "created_at": now})

    # ── Demo equipment (8 machines × per sub-site) + a few faults
    # so CAPEX + Reports panels render with realistic-looking data.
    DEMO_MACHINES = [
        ("Treadmill — Life Fitness Integrity", "Treadmill", "Life Fitness", "Integrity X", 3, 0),
        ("Treadmill — Life Fitness Integrity", "Treadmill", "Life Fitness", "Integrity X", 8, 5),
        ("Rower — Concept2 RowErg",            "Rower",     "Concept 2",    "RowErg",     2, 0),
        ("Rower — Concept2 RowErg",            "Rower",     "Concept 2",    "RowErg",     6, 1),
        ("Bike — Wattbike Atom",               "Bike",      "Wattbike",     "Atom",       4, 2),
        ("Cable Cross — Technogym Selection",  "Strength",  "Technogym",    "Selection",  9, 4),
        ("Smith Machine — Pulse 350g",         "Strength",  "Pulse Fitness","350g Smith",10, 7),
        ("Functional Trainer — Pulse FT100",   "Strength",  "Pulse Fitness","FT100",      5, 1),
    ]
    DEMO_FAULT_TYPES = ["mechanical", "electrical", "wear", "safety", "cosmetic"]
    eq_created = 0
    fa_created = 0
    for site_name, _site_code in _CATTERICK_SUBSITES:
        site_org_id = site_org_map[site_name]
        # Skip if equipment already exists for this site (idempotent)
        existing_eq = await db.equipment.count_documents({"organization_id": site_org_id, "imported_via": "mod_demo_seed"})
        if existing_eq > 0:
            continue
        for idx, (name, etype, mfr, model, age_yrs, faults_12mo) in enumerate(DEMO_MACHINES):
            purchase_iso = (now_dt - timedelta(days=int(age_yrs * 365))).isoformat()
            eq_id = str(uuid.uuid4())
            replacement_cost = {"Treadmill": 5500, "Rower": 1200, "Bike": 2800, "Strength": 4800}.get(etype, 3000)
            await db.equipment.insert_one({
                "id": eq_id,
                "organization_id": site_org_id,
                "name": name,
                "equipment_type": etype,
                "manufacturer": mfr,
                "model": model,
                "serial_number": f"{mfr[:3].upper()}-{site_org_id[:4].upper()}-{idx:03d}",
                "purchase_date": purchase_iso,
                "purchase_price": replacement_cost,
                "replacement_cost": replacement_cost,
                "status": "active" if faults_12mo < 6 else "out_of_service",
                "supplier": mfr,
                "created_at": now,
                "imported_via": "mod_demo_seed",
            })
            eq_created += 1
            # Seed `faults_12mo` issues over the last year so the
            # CAPEX recommender + Reports panel show real numbers.
            for j in range(faults_12mo):
                fa_id = str(uuid.uuid4())
                offset_days = int((j + 1) * (365 / max(faults_12mo + 1, 1)))
                created_at = now_dt - timedelta(days=offset_days)
                ft = DEMO_FAULT_TYPES[j % len(DEMO_FAULT_TYPES)]
                await db.issues.insert_one({
                    "id": fa_id,
                    "organization_id": site_org_id,
                    "equipment_id": eq_id,
                    "fault_type_mod": ft,
                    "issue_description": f"Demo fault — {ft} reported at {site_name}",
                    "status": "closed" if offset_days > 30 else "open",
                    "priority": "urgent" if ft == "safety" and j == 0 else "high" if j < 2 else "normal",
                    "severity": "urgent" if ft == "safety" and j == 0 else "high" if j < 2 else "normal",
                    "reporter_name": "Demo seed",
                    "reporter_email": "demo@army.mod.local",
                    "created_at": created_at.isoformat(),
                    "imported_via": "mod_demo_seed",
                })
                fa_created += 1

    created["equipment"] = eq_created
    created["faults"] = fa_created

    return {
        "ok": True,
        "demo_password": demo_password,
        "presenter_credentials": {
            "url": "/MODService",
            "logins": [
                {"label": "Catterick Garrison (branch view)", "email": hq_email, "password": demo_password},
                {"label": "Army Head Office (Command Centre rollup)", "email": hq_org_email, "password": demo_password},
                {"label": "Site-level (Vimy Lines)", "email": "daniel.hayes@army.mod.local", "password": demo_password},
            ],
        },
        "created": created,
        "army_hq_org_id": army_hq["id"],
        "catterick_org_id": cat["id"],
        "site_org_ids": site_org_map,
    }


@router.get("/mod/site/users-roster")
async def mod_site_users_roster(user: dict = Depends(get_current_user)):
    """Iter 216h109 — dropdown source for the fault wizard. Lists every
    real (non-shared) user assigned to the caller's site or org so that
    a shared-kiosk login can still attribute the fault to a named
    person."""
    org = await _org_of(user)
    q = {"organization_id": org["id"], "is_site_account": {"$ne": True}}
    items = await db.users.find(
        q,
        {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1,
         "rank": 1, "email": 1, "site_number": 1, "mobile": 1},
    ).sort("name", 1).to_list(500)
    return {"users": items, "total": len(items), "site_name": org.get("name")}



# ══════════════════════════════════════════════════════════════════
#     Iter 216h110 — CAPEX + Reports rollups (MOD only modules)
# ══════════════════════════════════════════════════════════════════
async def _resolve_org_scope(user: dict) -> tuple[list[str], str]:
    """Resolve the org-IDs in scope for a MOD user's rollup view.

    • mod_org   → all orgs with the same mod_force
    • mod_branch→ all orgs with the same mod_branch
    • mod_site  → just the caller's org
    Returns (org_ids, scope_label).
    """
    at = user.get("account_type")
    org_id = user.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    if at == "mod_site" or not at:
        return [org_id], org.get("name", "site")
    if at == "mod_branch":
        rows = await db.organizations.find(
            {"mod_branch": org.get("mod_branch"), "mod_root_id": org.get("mod_root_id"), "is_mod": True},
            {"_id": 0, "id": 1},
        ).to_list(500)
        return [r["id"] for r in rows] or [org_id], f"{org.get('mod_branch')} branch"
    # mod_org → whole force
    rows = await db.organizations.find(
        {"mod_force": org.get("mod_force"), "is_mod": True}, {"_id": 0, "id": 1},
    ).to_list(2000)
    return [r["id"] for r in rows] or [org_id], (org.get("mod_force") or "force").upper()


@router.get("/mod/capex/overview")
async def mod_capex_overview(user: dict = Depends(get_current_user)):
    """Equipment-driven CAPEX projection across the caller's scope.

    No fancy ML — we bucket equipment by age and recommend replacement
    when age > 7 yrs OR last 12-month fault count > 3. Replacement
    cost defaults to the stored `replacement_cost` (or `purchase_price`).
    """
    org_ids, scope = await _resolve_org_scope(user)
    now = datetime.now(timezone.utc)
    one_year_ago = (now - timedelta(days=365)).isoformat()
    items = await db.equipment.find(
        {"organization_id": {"$in": org_ids}}, {"_id": 0},
    ).to_list(20000)
    fault_counts: dict[str, int] = {}
    fault_cursor = db.issues.find(
        {"organization_id": {"$in": org_ids}, "created_at": {"$gte": one_year_ago}},
        {"_id": 0, "equipment_id": 1},
    )
    async for f in fault_cursor:
        eid = f.get("equipment_id")
        if eid:
            fault_counts[eid] = fault_counts.get(eid, 0) + 1

    age_buckets = {"<2 yrs": 0, "2–4 yrs": 0, "4–7 yrs": 0, "7+ yrs": 0, "unknown": 0}
    recommendations: list[dict] = []
    total_replacement_cost = 0.0
    flagged_replacement_cost = 0.0

    for eq in items:
        rep = float(eq.get("replacement_cost") or eq.get("purchase_price") or 0)
        total_replacement_cost += rep
        purchase = (eq.get("purchase_date") or "")[:10]
        age_yrs = None
        if purchase:
            try:
                pdt = datetime.fromisoformat(purchase)
                age_yrs = (now.replace(tzinfo=None) - pdt).days / 365.25
            except ValueError:
                age_yrs = None
        if age_yrs is None:
            age_buckets["unknown"] += 1
        elif age_yrs < 2:
            age_buckets["<2 yrs"] += 1
        elif age_yrs < 4:
            age_buckets["2–4 yrs"] += 1
        elif age_yrs < 7:
            age_buckets["4–7 yrs"] += 1
        else:
            age_buckets["7+ yrs"] += 1

        fc = fault_counts.get(eq.get("id"), 0)
        reasons = []
        if age_yrs is not None and age_yrs >= 7:
            reasons.append(f"{age_yrs:.1f} yrs old")
        if fc >= 4:
            reasons.append(f"{fc} faults in 12 mo")
        if reasons:
            flagged_replacement_cost += rep
            recommendations.append({
                "equipment_id": eq.get("id"),
                "name": eq.get("name"),
                "manufacturer": eq.get("manufacturer"),
                "site_organization_id": eq.get("organization_id"),
                "age_years": round(age_yrs, 1) if age_yrs is not None else None,
                "faults_12mo": fc,
                "replacement_cost": rep,
                "reasons": reasons,
                "priority": "high" if (age_yrs and age_yrs >= 10) or fc >= 6 else "medium",
            })

    recommendations.sort(key=lambda r: (0 if r["priority"] == "high" else 1, -r["replacement_cost"]))
    return {
        "scope": scope,
        "total_equipment": len(items),
        "age_buckets": age_buckets,
        "fleet_replacement_cost_total": round(total_replacement_cost, 2),
        "fleet_replacement_cost_flagged": round(flagged_replacement_cost, 2),
        "recommendations": recommendations[:50],
        "recommendation_total": len(recommendations),
    }


@router.get("/mod/reports/summary")
async def mod_reports_summary(user: dict = Depends(get_current_user)):
    """Service / availability / fault rollup for the caller's scope."""
    org_ids, scope = await _resolve_org_scope(user)
    now = datetime.now(timezone.utc)
    thirty_ago = (now - timedelta(days=30)).isoformat()
    ninety_ago = (now - timedelta(days=90)).isoformat()

    eq_total = await db.equipment.count_documents({"organization_id": {"$in": org_ids}})
    eq_oos   = await db.equipment.count_documents({"organization_id": {"$in": org_ids}, "status": "out_of_service"})
    availability = round((eq_total - eq_oos) * 100 / eq_total, 1) if eq_total else 100.0

    faults_30 = await db.issues.count_documents({"organization_id": {"$in": org_ids}, "created_at": {"$gte": thirty_ago}})
    faults_90 = await db.issues.count_documents({"organization_id": {"$in": org_ids}, "created_at": {"$gte": ninety_ago}})
    urgent_30 = await db.issues.count_documents({"organization_id": {"$in": org_ids}, "created_at": {"$gte": thirty_ago}, "priority": "urgent"})
    open_now  = await db.issues.count_documents({"organization_id": {"$in": org_ids}, "status": {"$in": ["open", "in_progress", "assigned"]}})

    by_type_cursor = db.issues.aggregate([
        {"$match": {"organization_id": {"$in": org_ids}, "created_at": {"$gte": ninety_ago}}},
        {"$group": {"_id": "$fault_type_mod", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    by_type = []
    async for r in by_type_cursor:
        by_type.append({"type": r["_id"] or "unspecified", "count": r["count"]})

    return {
        "scope": scope,
        "kpis": {
            "equipment_total": eq_total,
            "out_of_service": eq_oos,
            "availability_pct": availability,
            "faults_30d": faults_30,
            "faults_90d": faults_90,
            "urgent_30d": urgent_30,
            "open_now": open_now,
        },
        "fault_by_type_90d": by_type[:10],
        "generated_at": now.isoformat(),
    }
