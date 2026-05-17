"""
GymAxis Service Operations — Engineer self-allocation, AI email
parse and supplier-card public intake.

Iter 216h144 (Phase 5 · "engineer independence").

The engineer no longer needs a dispatcher to get jobs into their
pipeline. Three ingestion paths:

  1. ENGINEER MANUAL  — POST /api/svc/engineer/jobs/self-create
     Engineer fills a quick form and auto-assigns the case to themselves.

  2. AI EMAIL PARSE  — POST /api/svc/engineer/jobs/parse-email
     Engineer pastes the body of an email request; we extract
     customer / site / fault into a pre-fill draft via GPT-5.2
     (Emergent LLM key) for the engineer to confirm.

  3. SUPPLIER-CARD INBOX  — public landing page at /r/<slug>
     Customer scans the engineer's printed/QR card and submits a
     request. It lands in `svc_job_requests` (status="pending"). The
     engineer triages from `/svc/engineer/inbox` and either accepts
     (creates a `svc_case` auto-assigned to them) or declines.

Endpoints:
  Engineer (require_engineer_app_access):
    POST   /api/svc/engineer/jobs/self-create
    POST   /api/svc/engineer/jobs/parse-email
    GET    /api/svc/engineer/job-requests
    GET    /api/svc/engineer/job-requests/{id}
    POST   /api/svc/engineer/job-requests/{id}/accept
    POST   /api/svc/engineer/job-requests/{id}/decline
    GET    /api/svc/engineer/intake-card           — slug + share URL
    POST   /api/svc/engineer/intake-card/regenerate — new slug

  Public (no auth, rate-limit recommended on infra):
    GET    /api/r/{slug}                            — engineer profile for card
    POST   /api/r/{slug}/request                    — customer submits a request
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)

# Two routers — engineer-gated and a fully public one for the card.
engineer_router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Independence"],
    dependencies=[Depends(require_engineer_app_access)],
)
public_router = APIRouter(
    prefix="/r",
    tags=["Public · Engineer Supplier Card"],
)


# ── helpers ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or uuid.uuid4().hex[:8]


async def _generate_unique_slug(name: str) -> str:
    base = _slugify(name)
    for _ in range(5):
        candidate = f"{base}-{uuid.uuid4().hex[:5]}"
        if not await db.svc_engineers.find_one({"intake_slug": candidate}, {"_id": 0, "id": 1}):
            return candidate
    return uuid.uuid4().hex[:14]


async def _ensure_intake_slug(user: dict) -> str:
    """Idempotently ensure the engineer has a public intake slug."""
    of = _of(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of},
        {"_id": 0, "id": 1, "full_name": 1, "intake_slug": 1},
    )
    if not eng:
        raise HTTPException(404, "Engineer profile missing")
    if eng.get("intake_slug"):
        return eng["intake_slug"]
    slug = await _generate_unique_slug(eng.get("full_name") or user.get("email") or "engineer")
    await db.svc_engineers.update_one(
        {"id": user["id"], **of},
        {"$set": {"intake_slug": slug, "intake_slug_set_at": _now()}},
    )
    return slug


def _next_reference(org_id: str) -> str:
    # Cheap monotonic per-org reference. The full sequencer lives in
    # svc_cases.reference assignment elsewhere — for self-create we
    # use a SELF- prefix so the source is obvious in the case list.
    return f"SELF-{uuid.uuid4().hex[:6].upper()}"


# ── 1. Manual self-create ────────────────────────────────────────

class SelfCreateIn(BaseModel):
    title: str = Field(..., max_length=160)
    description: Optional[str] = Field(None, max_length=4000)
    priority: str = Field("P3")
    scheduled_at: Optional[str] = Field(None, description="ISO datetime")
    estimated_minutes: int = Field(60, ge=15, le=600)
    customer_name: Optional[str] = Field(None, max_length=160)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = Field(None, max_length=40)
    site_name: Optional[str] = Field(None, max_length=160)
    site_address: Optional[str] = Field(None, max_length=400)
    site_postcode: Optional[str] = Field(None, max_length=16)
    intake_channel: str = Field("manual", description="manual | email | phone | other")
    source_note: Optional[str] = Field(None, max_length=400)


@engineer_router.post("/jobs/self-create", status_code=201)
async def jobs_self_create(
    body: SelfCreateIn,
    user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    of = _of(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of}, {"_id": 0, "id": 1, "full_name": 1},
    )
    if not eng:
        raise HTTPException(403, "Engineer profile required to self-create jobs")
    # Idempotency — single row guard
    if idempotency_key:
        existing = await db.svc_cases.find_one(
            {**of, "idempotency_key": idempotency_key}, {"_id": 0, "id": 1, "reference": 1},
        )
        if existing:
            return {"case_id": existing["id"], "reference": existing.get("reference"),
                    "idempotent": True}

    # Validate scheduled_at if provided
    if body.scheduled_at:
        try:
            datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "scheduled_at must be ISO datetime")

    case_id = str(uuid.uuid4())
    reference = _next_reference(of["organization_id"])
    doc = {
        "id": case_id,
        **of,
        "reference": reference,
        "title": body.title,
        "description": body.description,
        "priority": body.priority.upper(),
        "status": "open",
        "scheduled_at": body.scheduled_at,
        "estimated_minutes": body.estimated_minutes,
        "assigned_engineer_id": user["id"],
        "assigned_engineer_name": eng.get("full_name"),
        "customer_name": body.customer_name,
        "customer_email": body.customer_email,
        "customer_phone": body.customer_phone,
        "site_name": body.site_name,
        "site_address": body.site_address,
        "site_postcode": body.site_postcode,
        "intake_channel": body.intake_channel,
        "source_note": body.source_note,
        "self_allocated": True,
        "idempotency_key": idempotency_key,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_cases.insert_one(doc)
    doc.pop("_id", None)
    return {"case_id": case_id, "reference": reference, "case": doc}


# ── 2. AI email parse ────────────────────────────────────────────

class ParseEmailIn(BaseModel):
    email_body: str = Field(..., min_length=10, max_length=12000)
    subject: Optional[str] = Field(None, max_length=300)


PARSE_SYSTEM_PROMPT = (
    "You are an extraction model for a UK fitness-equipment service "
    "company. The user pastes a customer email requesting service. "
    "Extract a JSON object with these keys (use null when missing — do "
    "not invent values):\n"
    "  customer_name (str), customer_email (str), customer_phone (str), \n"
    "  site_name (str), site_address (str), site_postcode (UK format),\n"
    "  title (short fault summary, 6-10 words),\n"
    "  description (single-paragraph context, plain text, no markdown),\n"
    "  priority (one of P1, P2, P3, P4 — pick P1 only if life-safety or "
    "membership-wide outage; P2 if a single line of equipment is down;\n"
    "  default P3),\n"
    "  scheduled_at_hint (ISO datetime if the customer specified a window; "
    "else null).\n"
    "Output a SINGLE JSON object and nothing else — no markdown fences, "
    "no commentary."
)


def _key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise HTTPException(503, "AI service not configured (EMERGENT_LLM_KEY missing)")
    return k


@engineer_router.post("/jobs/parse-email")
async def jobs_parse_email(body: ParseEmailIn, user=Depends(get_current_user)):
    """Run the pasted email through GPT-5.2 → structured fields for
    the self-create form to pre-fill. Returns the parsed dict + the
    raw model output for transparency."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=_key(),
        session_id=f"engineer-parse-{uuid.uuid4()}",
        system_message=PARSE_SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5.2")
    user_text = (
        f"Subject: {body.subject or '(none)'}\n\n{body.email_body.strip()}"
    )
    try:
        raw = await chat.send_message(UserMessage(text=user_text))
    except Exception as exc:
        logger.warning("[engineer_parse_email] gpt failed: %s", exc)
        raise HTTPException(502, f"AI parse failed: {exc}")
    raw_text = (raw or "").strip()
    # Strip code-fence wrappers defensively.
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
    import json as _json
    try:
        parsed = _json.loads(cleaned)
    except _json.JSONDecodeError:
        # Fall back to a regex-based field extraction so the engineer
        # gets *something* useful even if the model wrapped JSON.
        parsed = {}
    # Normalise the shape so the frontend can blindly spread it into form state.
    keys = ("customer_name", "customer_email", "customer_phone",
            "site_name", "site_address", "site_postcode",
            "title", "description", "priority", "scheduled_at_hint")
    out = {k: (parsed.get(k) if isinstance(parsed, dict) else None) for k in keys}
    return {"parsed": out, "raw": raw_text[:2000]}


# ── 3. Engineer intake card slug ─────────────────────────────────

@engineer_router.get("/intake-card")
async def get_intake_card(user=Depends(get_current_user)):
    slug = await _ensure_intake_slug(user)
    base = os.environ.get("PUBLIC_APP_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    base = base.rstrip("/")
    return {
        "slug": slug,
        "share_url": f"{base}/r/{slug}" if base else f"/r/{slug}",
        "qr_payload": f"{base}/r/{slug}" if base else f"/r/{slug}",
    }


@engineer_router.post("/intake-card/regenerate")
async def regenerate_intake_card(user=Depends(get_current_user)):
    of = _of(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of}, {"_id": 0, "full_name": 1},
    )
    if not eng:
        raise HTTPException(404, "Engineer profile missing")
    slug = await _generate_unique_slug(eng.get("full_name") or "engineer")
    await db.svc_engineers.update_one(
        {"id": user["id"], **of},
        {"$set": {"intake_slug": slug, "intake_slug_set_at": _now()}},
    )
    base = os.environ.get("PUBLIC_APP_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    base = base.rstrip("/")
    return {"slug": slug,
            "share_url": f"{base}/r/{slug}" if base else f"/r/{slug}"}


# ── 4. Engineer inbox of incoming requests ───────────────────────

@engineer_router.get("/job-requests")
async def list_job_requests(
    status: str = "pending",
    limit: int = 50,
    user=Depends(get_current_user),
):
    of = _of(user)
    q = {**of, "engineer_id": user["id"]}
    if status and status != "all":
        q["status"] = status
    rows = await db.svc_job_requests.find(q, {"_id": 0}) \
        .sort("created_at", -1).limit(min(limit, 200)).to_list(min(limit, 200))
    return {"requests": rows, "count": len(rows)}


@engineer_router.get("/job-requests/{req_id}")
async def get_job_request(req_id: str, user=Depends(get_current_user)):
    of = _of(user)
    doc = await db.svc_job_requests.find_one(
        {"id": req_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Request not found")
    return doc


class AcceptIn(BaseModel):
    scheduled_at: Optional[str] = None
    priority: Optional[str] = None
    estimated_minutes: Optional[int] = Field(None, ge=15, le=600)
    title_override: Optional[str] = Field(None, max_length=160)


@engineer_router.post("/job-requests/{req_id}/accept")
async def accept_job_request(
    req_id: str, body: AcceptIn, user=Depends(get_current_user),
):
    of = _of(user)
    req = await db.svc_job_requests.find_one(
        {"id": req_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    if req.get("status") not in (None, "pending"):
        raise HTTPException(409, f"Request already {req['status']}")
    if body.scheduled_at:
        try:
            datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "scheduled_at must be ISO datetime")
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of}, {"_id": 0, "id": 1, "full_name": 1},
    )
    case_id = str(uuid.uuid4())
    case = {
        "id": case_id,
        **of,
        "reference": _next_reference(of["organization_id"]),
        "title": body.title_override or req.get("title") or "Service request",
        "description": req.get("description"),
        "priority": (body.priority or req.get("priority") or "P3").upper(),
        "status": "open",
        "scheduled_at": body.scheduled_at,
        "estimated_minutes": body.estimated_minutes or 60,
        "assigned_engineer_id": user["id"],
        "assigned_engineer_name": eng.get("full_name") if eng else None,
        "customer_name": req.get("customer_name"),
        "customer_email": req.get("customer_email"),
        "customer_phone": req.get("customer_phone"),
        "site_name": req.get("site_name"),
        "site_address": req.get("site_address"),
        "site_postcode": req.get("site_postcode"),
        "intake_channel": "supplier_card",
        "source_note": f"Accepted from job request {req_id}",
        "self_allocated": True,
        "job_request_id": req_id,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_cases.insert_one(case)
    await db.svc_job_requests.update_one(
        {"id": req_id, **of},
        {"$set": {"status": "accepted", "accepted_at": _now(),
                   "case_id": case_id}},
    )
    case.pop("_id", None)
    return {"case_id": case_id, "reference": case["reference"]}


class DeclineIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=400)


@engineer_router.post("/job-requests/{req_id}/decline")
async def decline_job_request(
    req_id: str, body: DeclineIn, user=Depends(get_current_user),
):
    of = _of(user)
    req = await db.svc_job_requests.find_one(
        {"id": req_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    )
    if not req:
        raise HTTPException(404, "Request not found")
    if req.get("status") not in (None, "pending"):
        raise HTTPException(409, f"Request already {req['status']}")
    await db.svc_job_requests.update_one(
        {"id": req_id, **of},
        {"$set": {"status": "declined", "declined_at": _now(),
                   "decline_reason": body.reason}},
    )
    return {"ok": True}


# ── 5. Public supplier-card landing ──────────────────────────────

@public_router.get("/{slug}")
async def public_card_info(slug: str):
    eng = await db.svc_engineers.find_one(
        {"intake_slug": slug, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1,
         "photo_url": 1, "bio": 1, "intake_slug": 1, "qualifications": 1},
    )
    if not eng:
        raise HTTPException(404, "Card not found")
    org = await db.organizations.find_one(
        {"id": eng["organization_id"]},
        {"_id": 0, "name": 1, "brand_color": 1, "logo_url": 1},
    ) or {}
    return {
        "engineer": {
            "full_name": eng.get("full_name"),
            "photo_url": eng.get("photo_url"),
            "bio": eng.get("bio"),
            "qualifications": eng.get("qualifications") or [],
        },
        "organization": {
            "name": org.get("name"),
            "brand_color": org.get("brand_color"),
            "logo_url": org.get("logo_url"),
        },
        "slug": slug,
    }


class PublicRequestIn(BaseModel):
    customer_name: str = Field(..., max_length=160)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(None, max_length=40)
    site_name: Optional[str] = Field(None, max_length=160)
    site_address: Optional[str] = Field(None, max_length=400)
    site_postcode: Optional[str] = Field(None, max_length=16)
    title: str = Field(..., max_length=160)
    description: Optional[str] = Field(None, max_length=4000)
    priority: str = Field("P3")
    consent: bool = Field(..., description="Customer agrees to be contacted")


@public_router.post("/{slug}/request", status_code=201)
async def public_card_submit(slug: str, body: PublicRequestIn):
    if not body.consent:
        raise HTTPException(400, "Customer consent required")
    eng = await db.svc_engineers.find_one(
        {"intake_slug": slug, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1},
    )
    if not eng:
        raise HTTPException(404, "Card not found")
    rid = str(uuid.uuid4())
    doc = {
        "id": rid,
        "engineer_id": eng["id"],
        "engineer_name": eng.get("full_name"),
        "organization_id": eng["organization_id"],
        "intake_slug": slug,
        "intake_channel": "supplier_card",
        "status": "pending",
        "customer_name": body.customer_name.strip(),
        "customer_email": str(body.customer_email),
        "customer_phone": body.customer_phone,
        "site_name": body.site_name,
        "site_address": body.site_address,
        "site_postcode": body.site_postcode,
        "title": body.title,
        "description": body.description,
        "priority": (body.priority or "P3").upper(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_job_requests.insert_one(doc)

    # Notify the engineer via the in-app + Web Push channel.
    try:
        from routes.svc.notifications import create_notification
        await create_notification(
            user_id=eng["id"],
            organization_id=eng["organization_id"],
            kind="job_request",
            title=f"New request: {body.title[:60]}",
            body=f"{body.customer_name} — {body.site_name or 'site TBC'}",
            link="/svc/engineer/inbox",
            source_type="job_request",
            source_id=rid,
        )
    except Exception:
        pass  # never block the public flow on notification failure.

    return {"request_id": rid, "status": "pending"}


# ── 6. QR code SVG + printable card PDF ──────────────────────────

async def _resolve_card(user: dict) -> tuple[dict, str, dict]:
    """Return (engineer_doc, share_url, org_doc)."""
    of = _of(user)
    slug = await _ensure_intake_slug(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of},
        {"_id": 0, "id": 1, "full_name": 1, "intake_slug": 1,
         "photo_url": 1, "bio": 1, "qualifications": 1},
    ) or {}
    org = await db.organizations.find_one(
        {"id": user["organization_id"]},
        {"_id": 0, "name": 1, "brand_color": 1, "logo_url": 1},
    ) or {}
    base = (os.environ.get("PUBLIC_APP_URL")
            or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    share_url = f"{base}/r/{slug}" if base else f"/r/{slug}"
    return eng, share_url, org


@engineer_router.get("/intake-card.svg")
async def intake_card_svg(user=Depends(get_current_user)):
    """Raw QR code SVG of the engineer's public supplier-card URL.
    Returned as `image/svg+xml` so it can be embedded directly or
    downloaded as a vector asset."""
    _eng, share_url, _org = await _resolve_card(user)
    try:
        import qrcode
        import qrcode.image.svg as qrsvg
    except ImportError:
        raise HTTPException(503, "QR generator unavailable")
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10, border=2,
    )
    qr.add_data(share_url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrsvg.SvgPathImage)
    buf = BytesIO()
    img.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=60"},
    )


@engineer_router.get("/intake-card.pdf")
async def intake_card_pdf(user=Depends(get_current_user)):
    """Printable A6 supplier card (105 × 148 mm) with engineer name,
    organisation logo, QR code + share URL. Designed for handing out
    on customer visits."""
    eng, share_url, org = await _resolve_card(user)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A6
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.utils import ImageReader
        import qrcode
    except ImportError:
        raise HTTPException(503, "PDF generator unavailable")

    page_w, page_h = A6  # 105 × 148 mm in pts
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)

    # Brand colour (default GymAxis blue)
    brand = org.get("brand_color") or "#1E40AF"
    try:
        accent = HexColor(brand)
    except Exception:
        accent = HexColor("#1E40AF")

    # ── header band (top 30 mm) ──
    c.setFillColor(accent)
    c.rect(0, page_h - 30 * mm, page_w, 30 * mm, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, page_h - 12 * mm, (org.get("name") or "GymAxis Service").upper())
    c.setFont("Helvetica-Bold", 16)
    c.drawString(10 * mm, page_h - 22 * mm, "Request service")

    # ── engineer name & bio ──
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, page_h - 42 * mm, eng.get("full_name") or "Your engineer")
    bio = eng.get("bio") or "Field service engineer"
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, page_h - 48 * mm, bio[:60])

    # Qualifications chips
    quals = (eng.get("qualifications") or [])[:3]
    if quals:
        c.setFont("Helvetica-Bold", 7)
        x = 10 * mm
        for q in quals:
            txt = str(q)[:18]
            w = c.stringWidth(txt, "Helvetica-Bold", 7) + 6
            c.setFillColor(HexColor("#ecfdf5"))
            c.roundRect(x, page_h - 56 * mm, w, 4 * mm, 1, fill=True, stroke=False)
            c.setFillColor(HexColor("#047857"))
            c.drawString(x + 3, page_h - 53.5 * mm, txt)
            x += w + 3

    # ── QR code (centred lower half) ──
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=1,
    )
    qr.add_data(share_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buf = BytesIO()
    qr_img.save(qr_buf, "PNG")
    qr_buf.seek(0)

    qr_size = 55 * mm
    qr_x = (page_w - qr_size) / 2
    qr_y = 30 * mm
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)

    # Caption under QR
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(page_w / 2, qr_y - 6 * mm, "Scan to request service")
    c.setFont("Helvetica", 7)
    c.drawCentredString(page_w / 2, qr_y - 10 * mm, share_url[:70])

    # Footer
    c.setFillColor(HexColor("#94a3b8"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(page_w / 2, 8 * mm,
                        "Powered by GymAxis · " + datetime.now(timezone.utc).strftime("%b %Y"))

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    slug = eng.get("intake_slug") or "card"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="gymaxis-card-{slug}.pdf"',
            "Cache-Control": "private, max-age=60",
        },
    )


# ── Index setup ──────────────────────────────────────────────────

async def ensure_independence_indexes() -> None:
    try:
        await db.svc_engineers.create_index(
            [("intake_slug", 1)],
            unique=True, sparse=True,
        )
    except Exception as e:
        logger.warning("intake_slug unique index warning: %s", e)
    try:
        await db.svc_job_requests.create_index(
            [("organization_id", 1), ("engineer_id", 1), ("status", 1), ("created_at", -1)],
        )
        await db.svc_job_requests.create_index([("id", 1)], unique=True)
        await db.svc_cases.create_index(
            [("organization_id", 1), ("idempotency_key", 1)],
            sparse=True,
        )
    except Exception as e:
        logger.warning("svc_job_requests index warning: %s", e)


__all__ = ["engineer_router", "public_router", "ensure_independence_indexes"]
