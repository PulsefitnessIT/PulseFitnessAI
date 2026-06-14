"""
Iter 275 — Engineer QR fault-logging for off-platform customers.

When an independent engineer's customer is NOT on the Operations portal,
the engineer still wants the convenience of QR stickers on each machine so
the customer can scan and report a fault that lands STRAIGHT in the
engineer's job queue.

The Operations portal already has a QR flow (`routes/qr_codes.py` →
`/scan/{id}` → `db.issues`), but that writes to the operator-side `issues`
collection which the Engineer App never reads — engineers work from
`svc_cases`. This module is the engineer-native counterpart:

  Authenticated (engineer):
    * GET /api/svc/engineer/equipment/{id}/qr-card?size=  — branded QR
      label PNG with the engineer's *company name* (their own branding,
      not GymAxis). The QR encodes the public report URL `/r/{id}`.
    * GET /api/svc/engineer/equipment/{id}/qr-label       — JSON metadata
      (scan_url, brand_name, machine info) for the in-app preview.

  Public (no auth — the customer scanning is not logged in):
    * GET  /api/public/r/{id}              — machine info + engineer brand
      for the report page.
    * POST /api/public/r/{id}/report-fault — creates a `svc_case` in the
      engineer's org, assigned directly to the engineer, runs AI triage,
      and returns the case reference.

The case is created with `assigned_engineer_id = <engineer user id>` and
status `assigned`, because the Engineer App lists jobs by
`assigned_engineer_id == user["id"]` (see `routes/svc/engineer.py`).
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import ASSIGNED, append_event

logger = logging.getLogger(__name__)

# Authenticated engineer router (QR generation).
router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer QR (iter 275)"],
)

# Public router (no auth) — customer-facing fault report.
public_router = APIRouter(
    prefix="/public",
    tags=["Service Ops · Engineer QR — Public (iter 275)"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


# ─────────────────────────────────────────────────────────────────────
# Branding resolution — whose company name goes on the QR?
# ─────────────────────────────────────────────────────────────────────

async def _engineer_brand_for_user_id(user_id: str | None, org: dict | None) -> str:
    """Resolve the company / trading name to print on the QR sticker.

    Order: partner_engineers.company_name → partner_engineers.full_name →
    the engineer's personal org name (with the " (Engineer)" suffix the
    auto-provisioner adds stripped) → "Service Engineer".
    """
    brand = ""
    if user_id:
        pe = await db.partner_engineers.find_one(
            {"user_id": user_id},
            {"_id": 0, "company_name": 1, "full_name": 1},
        )
        if pe:
            brand = (pe.get("company_name") or pe.get("full_name") or "").strip()
    if not brand and org:
        brand = (org.get("name") or "").strip()
        if brand.endswith(" (Engineer)"):
            brand = brand[: -len(" (Engineer)")].strip()
    return brand or "Service Engineer"


async def _resolve_engineer_for_equipment(equipment: dict) -> dict:
    """Resolve the engineer who should receive faults for this machine.

    Returns ``{user_id, name, brand_name, org}``. The owning engineer is
    the equipment's creator (``user_id``/``created_by_id``) when that user
    still belongs to the equipment's org, else any partner-engineer user
    in that (personal) org.
    """
    org_id = equipment.get("organization_id")
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    ) if org_id else None

    candidate_id = equipment.get("user_id") or equipment.get("created_by_id")
    user_doc = None
    if candidate_id:
        user_doc = await db.users.find_one(
            {"id": candidate_id, "organization_id": org_id},
            {"_id": 0, "id": 1, "full_name": 1, "email": 1},
        )
    if not user_doc and org_id:
        # Fall back to the (typically sole) partner engineer in this org.
        user_doc = await db.users.find_one(
            {
                "organization_id": org_id,
                "$or": [
                    {"is_partner_engineer": True},
                    {"account_type": "partner_engineer"},
                ],
            },
            {"_id": 0, "id": 1, "full_name": 1, "email": 1},
        )

    user_id = (user_doc or {}).get("id")
    name = (user_doc or {}).get("full_name") or (user_doc or {}).get("email") or ""
    brand_name = await _engineer_brand_for_user_id(user_id, org)
    if not name:
        name = brand_name
    return {"user_id": user_id, "name": name, "brand_name": brand_name, "org": org}


# ─────────────────────────────────────────────────────────────────────
# Authenticated: QR label + branded card
# ─────────────────────────────────────────────────────────────────────


async def _load_engineer_equipment(equipment_id: str, user: dict) -> dict:
    of = _of(user)
    eq = await db.equipment.find_one({"id": equipment_id, **of}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    return eq


@router.get("/equipment/{equipment_id}/qr-label")
async def engineer_qr_label(
    equipment_id: str,
    request: Request,
    user=Depends(get_current_user),
):
    """Metadata for the in-app QR preview (scan URL + brand + machine)."""
    from routes.qr_codes import resolve_frontend_url

    eq = await _load_engineer_equipment(equipment_id, user)
    brand_name = await _engineer_brand_for_user_id(
        user.get("id"),
        await db.organizations.find_one(
            {"id": eq.get("organization_id")}, {"_id": 0, "name": 1},
        ),
    )
    base_url = resolve_frontend_url(request)
    return {
        "equipment_id": equipment_id,
        "name": eq.get("name", ""),
        "equipment_type": eq.get("equipment_type", ""),
        "manufacturer": eq.get("manufacturer", ""),
        "model": eq.get("model", ""),
        "serial_number": eq.get("serial_number", ""),
        "location": eq.get("location", ""),
        "customer_name": eq.get("customer_name", ""),
        "brand_name": brand_name,
        "scan_url": f"{base_url}/r/{equipment_id}",
        # Iter 275b — pre-printed sticker linkage.
        "sticker_code": eq.get("sticker_code") or "",
        "code_scan_url": (
            f"{base_url}/r/c/{eq['sticker_code']}" if eq.get("sticker_code") else ""
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 275b — Link a PRE-PRINTED sticker code to a machine.
# Engineers (esp. in the US) already have asset QR stickers on machines.
# They register the code printed on the sticker against the equipment so
# a sticker that encodes `…/r/c/<code>` resolves to this machine — no
# per-machine UUID reprint needed. Codes are globally unique among
# engineer-set sticker codes so the public resolver is unambiguous.
# ─────────────────────────────────────────────────────────────────────


class StickerCodeBody(BaseModel):
    code: Optional[str] = None


def _normalize_sticker_code(raw: str | None) -> str:
    code = " ".join((raw or "").split()).strip()
    return code[:120]


@router.post("/equipment/{equipment_id}/sticker-code")
async def set_sticker_code(
    equipment_id: str,
    payload: StickerCodeBody,
    request: Request,
    user=Depends(get_current_user),
):
    """Set (or clear, with an empty code) the pre-printed sticker code on a
    machine. Enforces global uniqueness among engineer-set sticker codes."""
    from routes.qr_codes import resolve_frontend_url

    of = _of(user)
    eq = await db.equipment.find_one({"id": equipment_id, **of}, {"_id": 0, "id": 1})
    if not eq:
        raise HTTPException(404, "Equipment not found")

    code = _normalize_sticker_code(payload.code)
    if not code:
        await db.equipment.update_one(
            {"id": equipment_id, **of},
            {"$unset": {"sticker_code": "", "sticker_code_lc": ""}},
        )
        return {"ok": True, "sticker_code": "", "code_scan_url": ""}

    code_lc = code.lower()
    try:
        await db.equipment.create_index("sticker_code_lc")
    except Exception:  # noqa: BLE001
        pass
    clash = await db.equipment.find_one(
        {"sticker_code_lc": code_lc, "id": {"$ne": equipment_id}},
        {"_id": 0, "id": 1},
    )
    if clash:
        raise HTTPException(
            409,
            "That sticker code is already linked to another machine. "
            "Add a unique prefix (e.g. your company initials).",
        )
    await db.equipment.update_one(
        {"id": equipment_id, **of},
        {"$set": {"sticker_code": code, "sticker_code_lc": code_lc}},
    )
    base_url = resolve_frontend_url(request)
    return {
        "ok": True,
        "sticker_code": code,
        "code_scan_url": f"{base_url}/r/c/{code}",
    }


@router.get("/equipment/{equipment_id}/qr-card")
async def engineer_qr_card(
    equipment_id: str,
    request: Request,
    size: str = "62x35",
    user=Depends(get_current_user),
):
    """Branded QR label PNG — the engineer's company name on top, the
    machine make/model/serial, a QR encoding `/r/{id}`, and a
    "Scan to report a fault" footer. Sizes mirror the operations card
    presets (62x35 default, 62x62, 50x50, card, a4)."""
    from PIL import Image, ImageDraw
    import qrcode

    from routes.qr_codes import (
        QR_CARD_PRESETS, _mm_to_px, _load_qr_fonts, _wrap_text_to_width,
        resolve_frontend_url,
    )

    eq = await _load_engineer_equipment(equipment_id, user)
    if size not in QR_CARD_PRESETS:
        raise HTTPException(400, f"Unknown size preset. Options: {list(QR_CARD_PRESETS)}")

    brand_name = await _engineer_brand_for_user_id(
        user.get("id"),
        await db.organizations.find_one(
            {"id": eq.get("organization_id")}, {"_id": 0, "name": 1},
        ),
    )

    width_mm, height_mm, dpi = QR_CARD_PRESETS[size]
    w_px, h_px = _mm_to_px(width_mm, dpi), _mm_to_px(height_mm, dpi)
    margin = _mm_to_px(2, dpi)
    landscape = width_mm >= height_mm

    base_url = resolve_frontend_url(request)
    scan_url = f"{base_url}/r/{equipment_id}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1)
    qr.add_data(scan_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    fonts = _load_qr_fonts(h_px, landscape)
    card = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(card)

    # Engineer orange brand palette.
    BRAND = (249, 115, 22)
    INK = (20, 20, 20)
    MUTED = (120, 120, 120)
    header = brand_name[:40]

    if landscape:
        qr_size = h_px - 2 * margin
        card.paste(qr_img.resize((qr_size, qr_size)), (margin, margin))
        text_x = margin + qr_size + margin
        text_width = w_px - text_x - margin
        draw.text((text_x, margin), header, fill=BRAND, font=fonts["header"])
        y = draw.textbbox((text_x, margin), header, font=fonts["header"])[3] + int(margin * 0.3)
        draw.line([(text_x, y), (w_px - margin, y)], fill=BRAND, width=3)
        y += int(margin * 0.5)
        for piece, font in (
            (eq.get("manufacturer") or eq.get("name") or "", fonts["model"]),
            (eq.get("model") or "", fonts["sub"]),
        ):
            if not piece:
                continue
            for line in _wrap_text_to_width(draw, piece, font, text_width):
                draw.text((text_x, y), line, fill=INK, font=font)
                y += draw.textbbox((0, 0), line, font=font)[3] + 2
        serial = eq.get("serial_number") or ""
        if serial:
            draw.text((text_x, y), serial, fill=(40, 40, 40), font=fonts["mono"])
        scan_text = "Scan to report a fault"
        sb = draw.textbbox((0, 0), scan_text, font=fonts["scan"])
        draw.text((text_x, h_px - margin - (sb[3] - sb[1])), scan_text, fill=MUTED, font=fonts["scan"])
    else:
        draw.text((margin, margin), header, fill=BRAND, font=fonts["header"])
        y = draw.textbbox((margin, margin), header, font=fonts["header"])[3] + int(margin * 0.2)
        draw.line([(margin, y), (w_px - margin, y)], fill=BRAND, width=3)
        y += int(margin * 0.3)
        manufacturer = eq.get("manufacturer") or eq.get("name") or ""
        if manufacturer:
            draw.text((margin, y), manufacturer[:30], fill=INK, font=fonts["model"])
            y += draw.textbbox((0, 0), "Ag", font=fonts["model"])[3] + 2
        if eq.get("model"):
            draw.text((margin, y), eq["model"][:30], fill=INK, font=fonts["sub"])
            y += draw.textbbox((0, 0), "Ag", font=fonts["sub"])[3] + int(margin * 0.4)
        available = h_px - y - margin - int(margin * 2)
        qr_size = min(w_px - 2 * margin, available)
        card.paste(qr_img.resize((qr_size, qr_size)), ((w_px - qr_size) // 2, y))
        y += qr_size + int(margin * 0.4)
        serial = eq.get("serial_number") or ""
        if serial:
            sb = draw.textbbox((0, 0), serial, font=fonts["mono"])
            draw.text(((w_px - (sb[2] - sb[0])) // 2, y), serial, fill=(40, 40, 40), font=fonts["mono"])
        scan_text = "Scan to report a fault"
        sb = draw.textbbox((0, 0), scan_text, font=fonts["scan"])
        draw.text(((w_px - (sb[2] - sb[0])) // 2, h_px - margin - (sb[3] - sb[1])), scan_text, fill=MUTED, font=fonts["scan"])

    buf = io.BytesIO()
    card.save(buf, format="PNG", dpi=(dpi, dpi))
    buf.seek(0)
    fname = (eq.get("serial_number") or equipment_id).replace("/", "-")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="qr-{fname}-{size}.png"'},
    )


# ─────────────────────────────────────────────────────────────────────
# Public: machine info + fault report → engineer's job queue
# ─────────────────────────────────────────────────────────────────────


@public_router.get("/r/{equipment_id}")
async def public_engineer_equipment(equipment_id: str):
    """Public machine info + engineer brand for the report page."""
    eq = await db.equipment.find_one({"id": equipment_id}, {"_id": 0, "manuals": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    resolved = await _resolve_engineer_for_equipment(eq)
    return {
        "id": eq["id"],
        "name": eq.get("name", ""),
        "equipment_type": eq.get("equipment_type", ""),
        "manufacturer": eq.get("manufacturer", ""),
        "model": eq.get("model", ""),
        "serial_number": eq.get("serial_number", ""),
        "location": eq.get("location", ""),
        "customer_name": eq.get("customer_name", ""),
        "brand_name": resolved["brand_name"],
    }


@public_router.get("/r/c/{code}")
async def public_engineer_equipment_by_code(code: str):
    """Resolve a PRE-PRINTED sticker code → machine info (iter 275b).

    Lets a sticker that encodes `…/r/c/<code>` open the fault-report page
    for the linked machine. Returns the same shape as `/public/r/{id}`
    (incl. `id`) so the page posts to the existing report-fault endpoint.
    """
    code_lc = _normalize_sticker_code(code).lower()
    if not code_lc:
        raise HTTPException(404, "Unknown sticker")
    eq = await db.equipment.find_one(
        {"sticker_code_lc": code_lc}, {"_id": 0, "manuals": 0},
    )
    if not eq:
        raise HTTPException(404, "This sticker isn't linked to a machine yet")
    resolved = await _resolve_engineer_for_equipment(eq)
    return {
        "id": eq["id"],
        "name": eq.get("name", ""),
        "equipment_type": eq.get("equipment_type", ""),
        "manufacturer": eq.get("manufacturer", ""),
        "model": eq.get("model", ""),
        "serial_number": eq.get("serial_number", ""),
        "location": eq.get("location", ""),
        "customer_name": eq.get("customer_name", ""),
        "brand_name": resolved["brand_name"],
    }


_SEVERITY_TO_PRIORITY = {"low": "p4", "medium": "p3", "critical": "p1"}


async def _engineer_qr_triage(eq: dict, description: str, severity: str,
                              photo_base64: str | None) -> dict | None:
    """Lightweight AI triage (Emergent LLM key). Returns parsed dict or None."""
    try:
        import json as _json
        from utils.database import EMERGENT_LLM_KEY
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        system = (
            "You are an expert gym-equipment technician triaging a fault "
            "reported via a QR scan. Return ONLY valid JSON: {\"severity\":"
            " \"low|medium|critical\", \"diagnosis\": \"...\", "
            "\"likely_cause\": \"...\", \"recommended_action\": \"...\", "
            "\"safety_note\": \"... or null\"}"
        )
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"eng_qr_triage_{uuid.uuid4()}",
            system_message=system,
        ).with_model("openai", "gpt-4o")
        prompt = (
            f"Machine: {eq.get('equipment_type', 'Unknown')} - {eq.get('name', '')}\n"
            f"Make/Model: {eq.get('manufacturer', '')} {eq.get('model', '')}\n"
            f"Serial: {eq.get('serial_number', 'N/A')}\n"
            f"Reported severity: {severity}\nFault: {description}\n"
            f"{'Photo attached.' if photo_base64 else 'No photo.'}\nTriage."
        )
        msg = (
            UserMessage(text=prompt, file_contents=[ImageContent(image_base64=photo_base64)])
            if photo_base64 else UserMessage(text=prompt)
        )
        raw = await chat.send_message(msg)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        return _json.loads(cleaned)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[engineer-qr] triage failed: %s", exc)
        return None


@public_router.post("/r/{equipment_id}/report-fault")
async def public_report_engineer_fault(
    equipment_id: str,
    description: str = Form(...),
    severity: str = Form("medium"),
    reporter_name: str = Form(...),
    reporter_phone: str = Form(""),
    reporter_email: str = Form(""),
    photo: Optional[UploadFile] = File(None),
):
    """Public: create a case in the engineer's queue from a QR fault report."""
    description = (description or "").strip()
    reporter_name = (reporter_name or "").strip()
    if not description:
        raise HTTPException(400, "Please describe the fault")
    if not reporter_name:
        raise HTTPException(400, "Please tell us your name")

    eq = await db.equipment.find_one({"id": equipment_id}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    org_id = eq.get("organization_id")
    if not org_id:
        raise HTTPException(400, "This machine isn't linked to a service account")

    resolved = await _resolve_engineer_for_equipment(eq)

    severity = severity if severity in ("low", "medium", "critical") else "medium"
    priority = _SEVERITY_TO_PRIORITY.get(severity, "p3")

    # Photo upload (reuse the operations helper).
    photo_url = photo_base64 = None
    if photo and photo.filename:
        from routes.qr_codes import _upload_fault_photo
        photo_url, photo_base64 = await _upload_fault_photo(photo, org_id)

    triage = await _engineer_qr_triage(eq, description, severity, photo_base64)

    from routes.svc.cases import compute_sla_targets, next_reference
    sla = await compute_sla_targets(organization_id=org_id, priority=priority, cover_type="")
    reference = await next_reference(org_id)

    machine_label = (
        f"{eq.get('manufacturer') or ''} {eq.get('model') or ''}".strip()
        or eq.get("name") or "Equipment"
    )
    title = f"{eq.get('name') or machine_label} — fault reported"
    serial = eq.get("serial_number") or ""

    now = _now()
    case = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "reference": reference,
        "status": ASSIGNED,
        "priority": priority,
        "cover_type": "",
        "case_type": "repair",
        "title": title[:120],
        "description": description,
        "fault_code": "",
        "fault_category": "",
        "asset_id": equipment_id,
        "asset_name": machine_label[:200],
        "equipment_ids": [equipment_id],
        "equipment_serials": [serial] if serial else [],
        "allocated_parts": [],
        "site_id": eq.get("site_id") or "",
        "site_name": eq.get("customer_name") or "",
        "site_postcode": "",
        "contract_id": "",
        "contact_id": "",
        "customer_name": eq.get("customer_name") or reporter_name,
        "customer_email": reporter_email.strip(),
        "customer_phone": reporter_phone.strip(),
        "quote_required": False,
        "customer_po_number": "",
        "attachments": ([photo_url] if photo_url else []),
        "tags": ["qr_scan"],
        "required_skills": [],
        "source": "qr_scan",
        "intake_channel": "qr_scan",
        "source_meta": {
            "reporter_name": reporter_name,
            "reporter_phone": reporter_phone.strip(),
            "reporter_email": reporter_email.strip(),
            "photo_url": photo_url,
            "ai_triage": triage,
        },
        "logged_by_id": "qr-scan",
        "logged_by_name": reporter_name,
        "assigned_engineer_id": resolved.get("user_id") or "",
        "assigned_engineer_name": resolved.get("name") or "",
        "scheduled_at": None,
        "estimated_minutes": 0,
        "sla_response_at": sla["sla_response_at"],
        "sla_resolve_at": sla["sla_resolve_at"],
        "sla_paused_at": None,
        "closed_at": None,
        "created_at": now,
        "updated_at": now,
        "ai_triage_parsed": triage,
    }
    # If no engineer resolved, fall back to an unassigned NEW case so it
    # still lands in the org's desk rather than vanishing.
    if not case["assigned_engineer_id"]:
        from utils.svc_state import NEW
        case["status"] = NEW

    await db.svc_cases.insert_one(case)

    actor = {"id": "qr-scan", "full_name": reporter_name or "QR report"}
    await append_event(
        case_id=case["id"], organization_id=org_id,
        event_type="intake", actor=actor,
        body=f"Fault reported via QR by {reporter_name}",
        extra={"source": "qr_scan", "priority": priority, "severity": severity},
    )

    return {
        "success": True,
        "case_id": case["id"],
        "reference": reference,
        "message": "Fault reported. Your engineer has been notified.",
        "ai_triage": triage,
    }


__all__ = ["router", "public_router"]
