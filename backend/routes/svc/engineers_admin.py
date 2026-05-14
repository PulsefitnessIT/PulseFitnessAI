"""
GymAxis Service Operations — Engineers Admin & Reorder Alerts.

Iter 216v (Phase 3).

Surface:
    GET    /svc/engineers                  — list engineers (admin/manager)
    POST   /svc/engineers                  — create engineer profile
    PATCH  /svc/engineers/{user_id}        — update profile
    DELETE /svc/engineers/{user_id}        — soft-deactivate
    GET    /svc/parts/reorder-alerts       — low-stock list (qty ≤ reorder_threshold)
    GET    /svc/billing/{case_id}/quote.pdf  — customer-facing quote PDF
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_ENGINEER_FIELDS = {
    "full_name", "email", "mobile", "home_address", "vehicle_reg",
    "skills", "working_hours", "active", "sage_user_id",
    # Iter 216h87 — trust signals surfaced on the public tracking card.
    "photo_url", "qualifications", "years_experience", "verified",
}


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _require_admin(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Owners and managers only")


def _public(eng: dict) -> dict:
    eng.pop("_id", None)
    eng.pop("password", None)
    return eng


# ── Engineer admin CRUD ──────────────────────────────────────────

@router.get("/svc/engineers")
async def list_engineers(user=Depends(get_current_user)) -> dict:
    cursor = db.svc_engineers.find(_of(user), {"_id": 0}).sort("full_name", 1)
    rows = [_public(e) async for e in cursor]
    # Annotate each engineer with current open-job count for the admin UI.
    of = _of(user)
    pipeline = [
        {"$match": {**of, "status": {"$nin": ["closed", "invoiced", "void", "cancelled"]},
                    "assigned_engineer_id": {"$ne": ""}}},
        {"$group": {"_id": "$assigned_engineer_id", "n": {"$sum": 1}}},
    ]
    load: dict[str, int] = {}
    async for d in db.svc_cases.aggregate(pipeline):
        load[d["_id"]] = d["n"]
    for r in rows:
        r["open_jobs"] = load.get(r.get("id"), 0)
    return {"engineers": rows}


@router.post("/svc/engineers")
async def create_engineer(body: dict, user=Depends(get_current_user)) -> dict:
    _require_admin(user)
    email = (body.get("email") or "").strip().lower()
    full_name = (body.get("full_name") or "").strip()
    if not email or not full_name:
        raise HTTPException(status_code=400, detail="full_name and email are required")
    user_doc = await db.users.find_one(
        {"email": email, "organization_id": user.get("organization_id")},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1},
    )
    if not user_doc:
        raise HTTPException(
            status_code=404,
            detail=("User not found in this organisation. "
                    "Invite them via Account Settings → Team & Roles first."),
        )
    existing = await db.svc_engineers.find_one(
        {"id": user_doc["id"]}, {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(status_code=409, detail="Engineer profile already exists for this user")
    now_iso = datetime.now(timezone.utc).isoformat()
    eng = {
        "id": user_doc["id"],
        "organization_id": user.get("organization_id"),
        "sage_user_id": (body.get("sage_user_id") or "").strip(),
        "full_name": user_doc["full_name"],
        "email": user_doc["email"],
        "mobile": (body.get("mobile") or "").strip(),
        "home_address": (body.get("home_address") or "").strip(),
        "vehicle_reg": (body.get("vehicle_reg") or "").strip(),
        "skills": list(body.get("skills") or []),
        "working_hours": dict(body.get("working_hours") or {}),
        # Iter 216h87 — trust card fields (settable at creation time)
        "photo_url": (body.get("photo_url") or "").strip(),
        "qualifications": list(body.get("qualifications") or []),
        "years_experience": (
            int(body["years_experience"])
            if body.get("years_experience") not in (None, "", 0, "0")
            else None
        ),
        "verified": bool(body.get("verified")),
        "active": True,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.svc_engineers.insert_one(eng)
    return _public(eng)


@router.patch("/svc/engineers/{user_id}")
async def update_engineer(user_id: str, body: dict, user=Depends(get_current_user)) -> dict:
    _require_admin(user)
    of = _of(user)
    target = await db.svc_engineers.find_one({"id": user_id, **of}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Engineer not found")
    updates = {k: (v.strip() if isinstance(v, str) else v)
               for k, v in (body or {}).items() if k in ALLOWED_ENGINEER_FIELDS}
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.svc_engineers.update_one({"id": user_id, **of}, {"$set": updates})
    fresh = await db.svc_engineers.find_one({"id": user_id, **of}, {"_id": 0})
    return _public(fresh or target)


@router.delete("/svc/engineers/{user_id}")
async def deactivate_engineer(user_id: str, user=Depends(get_current_user)) -> dict:
    _require_admin(user)
    of = _of(user)
    target = await db.svc_engineers.find_one({"id": user_id, **of}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Engineer not found")
    await db.svc_engineers.update_one(
        {"id": user_id, **of},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}


@router.get("/svc/engineers/{user_id}/preview-tracking-link")
async def preview_engineer_tracking(user_id: str, request: Request,
                                    user=Depends(get_current_user)) -> dict:
    """Iter 216h87 follow-up — Operator "what does the customer see?" preview.

    Picks the engineer's most recent active assignment (or, failing that,
    the most recently closed case) and returns a tokenised tracking URL
    operators can open to see the live customer view. Lazily mints a
    token if one doesn't yet exist on the case.
    """
    of = _of(user)
    target = await db.svc_engineers.find_one({"id": user_id, **of}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Engineer not found")

    # Prefer an in-flight case, fall back to most recent closed.
    case = await db.svc_cases.find_one(
        {**of, "assigned_engineer_id": user_id,
         "status": {"$nin": ["closed", "invoiced", "void", "cancelled"]}},
        {"_id": 0, "id": 1, "track_token": 1, "status": 1},
        sort=[("updated_at", -1)],
    )
    if not case:
        case = await db.svc_cases.find_one(
            {**of, "assigned_engineer_id": user_id},
            {"_id": 0, "id": 1, "track_token": 1, "status": 1},
            sort=[("closed_at", -1), ("updated_at", -1)],
        )
    if not case:
        raise HTTPException(
            status_code=404,
            detail="This engineer has no jobs yet — preview is available once a case is assigned.",
        )

    # Reuse the public_tracking helpers to mint+resolve.
    from routes.svc.public_tracking import _mint_or_get_token, _origin
    token = await _mint_or_get_token(case["id"], of)
    return {
        "url": f"{_origin(request)}/track/{token}",
        "token": token,
        "case_id": case["id"],
        "case_status": case.get("status"),
    }


# ── Reorder alerts ───────────────────────────────────────────────

@router.get("/svc/parts/reorder-alerts")
async def reorder_alerts(user=Depends(get_current_user)) -> dict:
    """Return parts whose total stock has dropped at/below their reorder
    threshold. Aggregates van + warehouse rows so a part with 1 in van and
    0 in warehouse is correctly compared against its threshold."""
    of = _of(user)
    # 1. Pull catalogue (rows where engineer_id is empty are the canonical
    # part record carrying the threshold + reorder_qty).
    catalogue: dict[str, dict] = {}
    async for row in db.svc_parts.find({**of, "engineer_id": ""}, {"_id": 0}):
        catalogue[row["part_sku"]] = row

    # 2. Sum van stock per SKU.
    pipeline = [
        {"$match": of},
        {"$group": {"_id": "$part_sku", "total_qty": {"$sum": "$qty"}}},
    ]
    totals: dict[str, int] = {}
    async for d in db.svc_parts.aggregate(pipeline):
        totals[d["_id"]] = d["total_qty"]

    alerts = []
    for sku, cat in catalogue.items():
        threshold = int(cat.get("reorder_threshold", 0) or 0)
        if threshold <= 0:
            continue
        on_hand = totals.get(sku, 0)
        if on_hand <= threshold:
            alerts.append({
                "part_sku": sku,
                "part_name": cat.get("part_name", ""),
                "supplier": cat.get("supplier", ""),
                "reorder_threshold": threshold,
                "reorder_qty": int(cat.get("reorder_qty", 1) or 1),
                "on_hand": on_hand,
                "shortfall": max(0, threshold - on_hand),
            })
    alerts.sort(key=lambda a: a["shortfall"], reverse=True)
    return {"count": len(alerts), "alerts": alerts}


# ── Customer-facing quote PDF ────────────────────────────────────

def _build_quote_pdf(case: dict, quote: dict, org: dict) -> bytes:
    """Render a branded customer-facing quote PDF in-memory."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=22, leading=26,
                        textColor=colors.HexColor("#0055FF"))
    body = styles["BodyText"]
    muted = ParagraphStyle("muted", parent=body, textColor=colors.HexColor("#52525B"), fontSize=9)

    story = [
        Paragraph(org.get("name") or "GymAxis", h1),
        Paragraph("Service Quote", styles["Heading2"]),
        Spacer(1, 6 * mm),
    ]

    # Customer block.
    cust_lines = [
        case.get("customer_name") or "",
        case.get("site_name") or "",
        " ".join(filter(None, [case.get("site_address", ""), case.get("site_postcode", "")])),
    ]
    story.append(Paragraph("<b>Quote for</b><br/>" + "<br/>".join(filter(None, cust_lines)), body))
    story.append(Spacer(1, 5 * mm))

    issued = (quote.get("approved_at") or quote.get("updated_at") or quote.get("created_at") or "")
    if "T" in issued:
        issued = issued.split("T")[0]
    expires = (quote.get("expires_at") or "")
    if "T" in expires:
        expires = expires.split("T")[0]

    meta = Table([
        ["Quote #",       quote.get("reference") or quote.get("id", "")[:12]],
        ["Case",          case.get("reference") or ""],
        ["Issued",        issued],
        ["Valid until",   expires or "30 days from issue"],
        ["Status",        (quote.get("status") or "draft").upper()],
        ["Cover type",    (case.get("cover_type") or "chargeable").title()],
    ], colWidths=[40 * mm, 110 * mm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#52525B")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [meta, Spacer(1, 6 * mm)]

    if case.get("title"):
        story.append(Paragraph(f"<b>Work description</b><br/>{case['title']}", body))
        if case.get("description"):
            story.append(Paragraph(case["description"], body))
        story.append(Spacer(1, 5 * mm))

    # Line items.
    rows = [["Description", "Qty", "Unit", "Amount"]]
    items = quote.get("lines") or quote.get("line_items") or []
    subtotal = 0.0
    for li in items:
        qty = float(li.get("qty") or li.get("quantity") or 0)
        unit = float(li.get("unit_price") or li.get("price") or 0)
        amount = qty * unit
        subtotal += amount
        rows.append([
            li.get("description") or li.get("name") or "—",
            f"{qty:g}",
            f"£{unit:.2f}",
            f"£{amount:.2f}",
        ])
    if subtotal == 0:
        subtotal = float(quote.get("total") or quote.get("amount") or 0)
    vat_rate = float(quote.get("vat_rate", 0.20))
    vat = round(subtotal * vat_rate, 2)
    grand = round(subtotal + vat, 2)
    rows.append(["", "", "Subtotal", f"£{subtotal:.2f}"])
    rows.append(["", "", f"VAT @ {int(vat_rate*100)}%", f"£{vat:.2f}"])
    rows.append(["", "", "TOTAL", f"£{grand:.2f}"])

    items_table = Table(rows, colWidths=[90 * mm, 18 * mm, 22 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F7")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#C4C4CC")),
        ("LINEABOVE", (0, -3), (-1, -3), 0.5, colors.HexColor("#C4C4CC")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items_table, Spacer(1, 8 * mm)]

    story.append(Paragraph(
        "Quote validity: 30 days from the issue date unless stated otherwise. "
        "Acceptance constitutes a purchase order under our standard terms. "
        "Reply to your service desk contact to approve, or contact "
        "service@gymaxisai.com.", muted,
    ))
    doc.build(story)
    return buf.getvalue()


@router.get("/svc/billing/{case_id}/quote.pdf")
async def quote_pdf(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    quote = await db.svc_quotes.find_one({"case_id": case_id, **of}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="No quote attached to this case")
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0}) or {}
    pdf = _build_quote_pdf(case, quote, org)
    filename = f"quote-{case.get('reference', case_id[:8])}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
