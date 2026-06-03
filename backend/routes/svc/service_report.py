"""
GymAxis Service Operations — Customer-facing Service Report.

Iter 216h82 — Phase 1 of the "customer happiness" pack.

Generates a one-page branded PDF that an engineer can hand or email to a
customer at sign-off. Bundles everything customers expect to see after a
visit: case meta, time on site, parts used, work-done summary, before/
after photos, customer signature, post-visit star rating.

Endpoints (mounted ungated so both engineers and operators can use them
— authorisation is performed by case scoping + engineer-assignment check):

    GET  /svc/cases/{case_id}/service-report.pdf
    POST /svc/cases/{case_id}/service-report/email
"""
from __future__ import annotations

import io
import os
import logging
import base64
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _hex(value: str | None, fallback: str) -> str:
    v = (value or "").strip()
    if not v:
        return fallback
    if not v.startswith("#"):
        v = "#" + v
    if len(v) not in (4, 7):
        return fallback
    return v


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y · %H:%M")
    except Exception:
        return iso.split("T")[0] if "T" in iso else iso


# Iter 220eb — Friendly job-type labels mirrored from the engineer app
# (CASE_TYPE_LABELS in EngineerJobDetailV2.js). Drives the report's
# "Job type" row so a PPM visit reads "PPM Service", not the raw slug.
CASE_TYPE_LABELS = {
    "repair": "Repair",
    "ppm": "PPM Service",
    "install": "Installation",
    "inspection": "Inspection",
    "callout": "Emergency callout",
    "audit": "Asset audit",
}


def _case_type_label(slug: str | None) -> str:
    if not slug:
        return ""
    return CASE_TYPE_LABELS.get(
        str(slug).lower(), str(slug).replace("_", " ").title(),
    )


def _fmt_minutes(mins: float | int) -> str:
    mins = int(round(mins or 0))
    if mins <= 0:
        return "0 min"
    h, m = divmod(mins, 60)
    if h <= 0:
        return f"{m} min"
    return f"{h}h {m:02d}m" if m else f"{h}h"


async def _gather_report_data(case_id: str, of: dict) -> dict:
    """Pull everything the report needs in one helper."""
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    photos = (
        await db.svc_engineer_photos
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("taken_at", 1).limit(6).to_list(6)
    )
    signature = await db.svc_signatures.find_one(
        {"case_id": case_id, **of}, {"_id": 0}, sort=[("signed_at", -1)],
    )
    time_entries = await db.svc_time_entries.find(
        {"case_id": case_id, **of}, {"_id": 0},
    ).to_list(50)
    org = await db.organizations.find_one(
        {"id": of["organization_id"]}, {"_id": 0},
    ) or {}
    # Pull engineer profile if a primary one is assigned.
    eng_id = case.get("assigned_engineer_id") or ""
    engineer = None
    engineer_user = None
    if eng_id:
        engineer = await db.svc_engineers.find_one(
            {"id": eng_id, **of}, {"_id": 0, "password": 0},
        ) or {}
        # Iter 220i — pick up the engineer's branding override (logo/colours)
        # from their user record so per-engineer brand carries onto the PDF.
        engineer_user = await db.users.find_one(
            {"id": eng_id}, {"_id": 0, "branding": 1},
        )
    # Iter 216h89 — H&S signoff
    safety_signoff = await db.svc_case_safety_signoffs.find_one(
        {"case_id": case_id, **of}, {"_id": 0}, sort=[("signed_at", -1)],
    )
    # Iter 220dj — Compliance evidence pack (PTW / LOTO / COSHH).
    # All three were captured per-case by Iter 220de; we surface
    # them on the customer-facing PDF so each visit ships with a
    # complete audit trail. Only issued/completed PTWs are shown
    # (a stale "requested" permit isn't evidence of anything).
    ptw_records = await db.svc_ptw_requests.find(
        {"case_id": case_id, **of,
         "status": {"$in": ["issued", "completed"]}},
        {"_id": 0, "template_name": 1, "hazard_category": 1,
         "status": 1, "valid_from": 1, "valid_until": 1, "completed_at": 1,
         "issued_by_name": 1, "requested_by_name": 1, "hazards_noted": 1,
         "completed_by_id": 1},
    ).sort([("issued_at", 1)]).to_list(20)
    loto_records = await db.svc_loto_checklists.find(
        {"case_id": case_id, **of}, {"_id": 0},
    ).sort([("completed_at", 1)]).to_list(20)
    coshh_records = await db.svc_coshh_usage.find(
        {"case_id": case_id, **of}, {"_id": 0},
    ).sort([("recorded_at", 1)]).to_list(20)
    # Default LOTO step labels (Iter 220de) so we can render checked
    # boxes even when the snapshot didn't preserve labels.
    loto_step_labels = {
        s["id"]: s["label"]
        for s in __import__("routes.svc.compliance", fromlist=["DEFAULT_LOTO_STEPS"]).DEFAULT_LOTO_STEPS
    }
    # Get post-visit rating if captured (iter 216h81).
    rating = case.get("customer_rating")
    rating_comment = case.get("customer_rating_comment")
    # Iter 220 — Custom-field defs referenced by the persisted values so
    # the PDF can render labels in declaration order.
    cf_values = case.get("work_report_custom_fields") or {}
    custom_field_defs: list[dict] = []
    if cf_values:
        custom_field_defs = await db.svc_work_report_field_defs.find(
            {"organization_id": of["organization_id"], "key": {"$in": list(cf_values.keys())}},
            {"_id": 0},
        ).to_list(200)
    # Iter 220d/e — per-machine work report rows.
    machines = await db.svc_work_visit_machines.find(
        {"organization_id": of["organization_id"], "case_id": case_id},
        {"_id": 0},
    ).sort([("order_index", 1), ("created_at", 1)]).to_list(80)
    if machines:
        row_ids = [m["id"] for m in machines]
        machine_photos = await db.svc_engineer_photos.find(
            {"organization_id": of["organization_id"], "case_id": case_id,
             "machine_row_id": {"$in": row_ids}},
            {"_id": 0, "id": 1, "machine_row_id": 1, "file_url": 1,
             "mime_type": 1, "caption": 1, "taken_at": 1, "kind": 1},
        ).sort([("taken_at", 1)]).to_list(500)
        bucket: dict[str, list[dict]] = {}
        for p in machine_photos:
            if (p.get("kind") or "photo") == "photo":
                bucket.setdefault(p["machine_row_id"], []).append(p)
        for m in machines:
            m["photos"] = bucket.get(m["id"], [])
    # Iter 220ea·24 — Return Visit Brief inputs:
    #   • parts the engineer flagged to bring on the return visit
    #     (Equipment tab "Parts for return" → urgency=next_visit)
    #   • per-machine "further work required" (already on the machine docs)
    return_parts = await db.svc_parts_requests.find(
        {"case_id": case_id, **of, "urgency": "next_visit",
         "status": {"$nin": ["cancelled", "rejected"]}},
        {"_id": 0, "part_sku": 1, "part_name": 1, "qty": 1,
         "machine_name": 1, "notes": 1, "status": 1},
    ).sort([("created_at", 1)]).to_list(50)
    return {
        "case": case,
        "photos": photos,
        "signature": signature,
        "time_entries": time_entries,
        "org": org,
        "engineer": engineer,
        "safety_signoff": safety_signoff,
        "ptw_records": ptw_records,
        "loto_records": loto_records,
        "coshh_records": coshh_records,
        "loto_step_labels": loto_step_labels,
        "rating": rating,
        "rating_comment": rating_comment,
        "custom_field_defs": custom_field_defs,
        "machines": machines,
        "return_parts": return_parts,
        "engineer_branding": (engineer_user or {}).get("branding") or {},
    }


async def _fetch_image_bytes(url: str) -> bytes | None:
    """Resolve a photo or signature URL to raw bytes.

    Handles:
      • data: URLs (signatures are stored as base64 data URIs)
      • absolute http(s) URLs (Sicon-style external mirrors)
      • relative URLs starting with /api/files/... (resolve against BACKEND)
    """
    if not url:
        return None
    if url.startswith("data:"):
        try:
            _, b64 = url.split(",", 1)
            return base64.b64decode(b64)
        except Exception:
            return None
    full = url
    if url.startswith("/"):
        import os
        base = os.environ.get("INTERNAL_BACKEND_URL", "http://localhost:8001")
        full = f"{base.rstrip('/')}{url}"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(full)
            r.raise_for_status()
            return r.content
    except Exception as e:
        logger.warning(f"service-report: failed to fetch image {url!r}: {e!r}")
        return None


def _build_pdf(payload: dict, image_bytes: list[bytes | None], sig_bytes: bytes | None, logo_bytes: bytes | None = None) -> bytes:
    """Render the branded service report PDF.

    Layout is deliberately one-page-target with overflow tolerated.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )

    case = payload["case"]
    org = payload["org"]
    engineer = payload["engineer"] or {}
    sig = payload["signature"]
    time_entries = payload["time_entries"] or []
    rating = payload["rating"]
    rating_comment = payload["rating_comment"]
    safety = payload.get("safety_signoff")
    # Iter 220dj — Compliance evidence pack pulled per case.
    ptw_records = payload.get("ptw_records") or []
    loto_records = payload.get("loto_records") or []
    coshh_records = payload.get("coshh_records") or []
    loto_step_labels = payload.get("loto_step_labels") or {}
    # Iter 220i — engineer override beats org default for brand colour.
    eng_brand = payload.get("engineer_branding") or {}
    brand_primary = _hex(
        eng_brand.get("primary_color")
        or org.get("brand_primary_color")
        or (org.get("brand_kit") or {}).get("primary_color"),
        "#0055FF",
    )
    brand_dark = "#0F172A"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=14 * mm,
        title=f"Service Report · {case.get('reference', '')}",
    )
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "h_title", parent=styles["Title"], fontSize=20, leading=24,
        textColor=colors.HexColor(brand_primary), spaceAfter=0,
    )
    h_sub = ParagraphStyle(
        "h_sub", parent=styles["Normal"], fontSize=10, leading=12,
        textColor=colors.HexColor("#64748B"), spaceAfter=0,
    )
    h_section = ParagraphStyle(
        "h_section", parent=styles["Heading4"], fontSize=10, leading=12,
        textColor=colors.HexColor(brand_dark),
        spaceBefore=4, spaceAfter=4,
        textTransform="uppercase",
    )
    body = ParagraphStyle(
        "body", parent=styles["BodyText"], fontSize=9.5, leading=13,
        textColor=colors.HexColor("#1F2937"),
    )
    muted = ParagraphStyle(
        "muted", parent=body, fontSize=8.5,
        textColor=colors.HexColor("#64748B"),
    )

    story: list = []

    # ── Header band ────────────────────────────────────────────────
    org_name = org.get("name") or "GymAxis"
    # Iter 220i — when a custom logo is provided (engineer override or
    # org default), float it on the left of the title row.
    if logo_bytes:
        try:
            logo_img = Image(io.BytesIO(logo_bytes), width=24 * mm, height=12 * mm, kind="proportional")
            header_left = Table(
                [[logo_img, Paragraph(f"<b>{org_name}</b>", h_title)]],
                colWidths=[28 * mm, 82 * mm],
            )
            header_left.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
        except Exception:
            header_left = Paragraph(f"<b>{org_name}</b>", h_title)
    else:
        header_left = Paragraph(f"<b>{org_name}</b>", h_title)
    header_right = Paragraph(
        "<b>Service Report</b><br/>"
        f"Ref: {case.get('reference', case.get('id', '')[:8])}<br/>"
        f"Generated: {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}",
        h_sub,
    )
    header_table = Table([[header_left, header_right]], colWidths=[110 * mm, 65 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor(brand_primary)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # ── Job & site meta ───────────────────────────────────────────
    story.append(Paragraph("VISIT DETAILS", h_section))
    cust_lines = list(filter(None, [
        case.get("customer_name") or "",
        case.get("site_name") or "",
        " ".join(filter(None, [case.get("site_address", ""), case.get("site_postcode", "")])),
    ]))
    meta_rows = [
        ["Site",     "<br/>".join(cust_lines) or "—"],
        ["Job type", case.get("_case_type_label") or _case_type_label(case.get("case_type")) or "—"],
    ]
    # Iter 220eb — Only show a machine/asset row when it's a real,
    # customer-meaningful value. Empty fields and internal scheduling
    # slugs (e.g. "ASSET_Sched_Case_…") are noise on a customer report.
    asset_name = (case.get("asset_name") or "").strip()
    if asset_name and not asset_name.upper().startswith("ASSET_"):
        meta_rows.append(["Asset", asset_name])
    meta_rows += [
        ["Issue",    case.get("title") or "—"],
        ["Priority", (case.get("priority") or "p3").upper()],
        ["Status",   (case.get("status") or "").replace("_", " ").title() or "—"],
        ["Visit closed", _fmt_date(case.get("closed_at") or case.get("updated_at"))],
    ]
    if engineer.get("full_name") or engineer.get("email"):
        eng_line = engineer.get("full_name") or engineer.get("email")
        if engineer.get("vehicle_reg"):
            eng_line += f"  ·  Van: {engineer['vehicle_reg']}"
        skills = engineer.get("skills") or []
        if skills:
            eng_line += f"  ·  {', '.join(skills[:4])}"
        meta_rows.append(["Engineer", eng_line])
    rows = [[Paragraph(f"<b>{k}</b>", muted), Paragraph(v, body)] for (k, v) in meta_rows]
    t = Table(rows, colWidths=[28 * mm, 147 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # ── Time on site ──────────────────────────────────────────────
    travel = sum(int(e.get("duration_minutes") or 0) for e in time_entries if e.get("category") == "travel")
    on_site = sum(int(e.get("duration_minutes") or 0) for e in time_entries if e.get("category") == "on_site")
    if travel or on_site:
        story.append(Paragraph("TIME ON SITE", h_section))
        time_table = Table(
            [
                ["Travel", _fmt_minutes(travel), "On site", _fmt_minutes(on_site), "Total", _fmt_minutes(travel + on_site)],
            ],
            colWidths=[22 * mm, 26 * mm, 22 * mm, 26 * mm, 22 * mm, 26 * mm],
        )
        time_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#FEF9C3")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ]))
        story.append(time_table)
        story.append(Spacer(1, 4 * mm))

    # ── Parts used ────────────────────────────────────────────────
    parts = case.get("allocated_parts") or []
    if parts:
        story.append(Paragraph("PARTS USED", h_section))
        rows = [["SKU", "Description", "Qty", "Source"]]
        for p in parts:
            rows.append([
                p.get("part_sku", ""),
                p.get("part_name", ""),
                str(p.get("qty", "")),
                (p.get("source") or "warehouse").title(),
            ])
        parts_table = Table(rows, colWidths=[28 * mm, 95 * mm, 16 * mm, 36 * mm])
        parts_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(parts_table)
        story.append(Spacer(1, 4 * mm))

    # ── Work done summary (pulled from the engineer's fix_summary event) ──
    work_summary = case.get("resolution_notes") or payload.get("fix_summary") or ""
    if work_summary or case.get("description"):
        story.append(Paragraph("WORK COMPLETED", h_section))
        if case.get("description"):
            story.append(Paragraph(f"<i>Reported:</i> {case['description']}", muted))
            story.append(Spacer(1, 2 * mm))
        if work_summary:
            story.append(Paragraph(work_summary, body))
        story.append(Spacer(1, 4 * mm))

    # ── Iter 220 · Machine-specific custom fields ─────────────────
    custom_fields = case.get("work_report_custom_fields") or {}
    field_defs = payload.get("custom_field_defs") or []
    if custom_fields and field_defs:
        defs_by_key = {d["key"]: d for d in field_defs if d.get("key")}
        ordered = [k for k in custom_fields if k in defs_by_key]
        if ordered:
            story.append(Paragraph("MACHINE READINGS &amp; DETAILS", h_section))
            rows = [["Field", "Value"]]
            for k in ordered:
                d = defs_by_key[k]
                raw = custom_fields.get(k)
                ftype = d.get("field_type", "text")
                if ftype == "checkbox":
                    val = "Yes" if raw else "No"
                elif ftype == "file" and isinstance(raw, dict):
                    val = raw.get("original_filename") or raw.get("storage_path") or "—"
                elif raw in (None, ""):
                    val = "—"
                else:
                    val = str(raw)
                rows.append([d.get("name") or k, val[:200]])
            cf_table = Table(rows, colWidths=[70 * mm, 105 * mm])
            cf_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(cf_table)
            story.append(Spacer(1, 4 * mm))

    # ── Iter 220d/e · Per-machine work report cards (with photos) ────
    machines = payload.get("machines") or []
    if machines:
        story.append(Paragraph("MACHINES ON THIS VISIT", h_section))
        for idx, m in enumerate(machines, start=1):
            name = (m.get("asset_name") or "Unnamed machine")[:120]
            serial = (m.get("asset_serial") or "").strip()
            mtype = (m.get("asset_type") or "").strip()
            chips_html = []
            if m.get("serviced"):
                chips_html.append("<font color='#047857'><b>✓ SERVICED</b></font>")
            if m.get("cleaned"):
                chips_html.append("<font color='#0369A1'><b>✓ CLEANED</b></font>")
            chip_line = " &nbsp;·&nbsp; ".join(chips_html) if chips_html else "<font color='#94A3B8'><i>No work ticked</i></font>"

            meta_bits = []
            if mtype:
                meta_bits.append(mtype)
            if serial:
                meta_bits.append(f"S/N {serial}")
            meta_line = " · ".join(meta_bits) if meta_bits else ""

            # Header row inside the card: number badge + name + chips.
            header_html = (
                f"<font color='{brand_primary}'><b>#{idx}</b></font> &nbsp; "
                f"<b>{name}</b>"
                + (f"  <font color='#64748B' size='8'>{meta_line}</font>" if meta_line else "")
            )
            header_para = Paragraph(header_html, body)
            chip_para = Paragraph(chip_line, muted)

            block_rows: list = [[header_para], [chip_para]]

            notes_txt = (m.get("notes") or "").strip()
            if notes_txt:
                # Convert simple newlines to <br/> for paragraph rendering.
                safe_notes = (
                    notes_txt
                    .replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br/>")
                )
                block_rows.append([Paragraph(safe_notes, body)])

            # Photos: render up to 4 as a 2-col strip beneath this card.
            photos = [p for p in (m.get("photos") or []) if p.get("_bytes")]
            if photos:
                imgs: list = []
                for p in photos[:4]:
                    try:
                        img = Image(io.BytesIO(p["_bytes"]), width=78 * mm, height=52 * mm, kind="proportional")
                        cap = (p.get("caption") or "").strip()
                        if cap:
                            cap_p = Paragraph(
                                f"<font color='#64748B' size='8'>{cap[:140]}</font>",
                                muted,
                            )
                            imgs.append([img, cap_p])
                        else:
                            imgs.append([img])
                    except Exception as exc:
                        logger.warning(f"service-report machine photo invalid: {exc!r}")
                if imgs:
                    # 2 photos per row in the strip.
                    photo_grid_rows = []
                    for i in range(0, len(imgs), 2):
                        pair = imgs[i:i + 2]
                        # Flatten captions onto same cell as image stack.
                        cells = []
                        for stack in pair:
                            inner = Table([[el] for el in stack], colWidths=[80 * mm])
                            inner.setStyle(TableStyle([
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ]))
                            cells.append(inner)
                        while len(cells) < 2:
                            cells.append("")
                        photo_grid_rows.append(cells)
                    photo_grid = Table(photo_grid_rows, colWidths=[85 * mm, 85 * mm])
                    photo_grid.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ]))
                    block_rows.append([photo_grid])

            # Wrap each card in a 1-col table with a soft border.
            card = Table(block_rows, colWidths=[175 * mm])
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("LINEBEFORE", (0, 0), (0, -1), 2, colors.HexColor(brand_primary)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(card)
            story.append(Spacer(1, 3 * mm))
        story.append(Spacer(1, 1 * mm))

    # ── Iter 220ea·24 · Return Visit Brief ────────────────────────
    # Consolidates everything still outstanding after this visit:
    # per-machine "further work required" + the parts the engineer
    # flagged to bring back. Renders only when there's something to
    # carry forward so a fully-closed visit stays clean.
    return_parts = payload.get("return_parts") or []
    further_machines = [
        m for m in (payload.get("machines") or [])
        if (m.get("further_work") or "").strip()
    ]
    if return_parts or further_machines:
        story.append(Paragraph("RETURN VISIT BRIEF", h_section))
        brief_rows: list = []
        intro = Paragraph(
            "<font color='#B45309'><b>This visit isn't fully closed.</b></font> "
            "The items below are outstanding and should be scheduled for a "
            "return visit.",
            muted,
        )
        brief_rows.append([intro])
        # Outstanding work per machine.
        if further_machines:
            work_lines = []
            for m in further_machines:
                nm = (m.get("asset_name") or "Machine").strip()[:120]
                txt = (
                    (m.get("further_work") or "").strip()
                    .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br/>")
                )
                work_lines.append(
                    f"<b>{nm}</b><br/><font color='#475569'>{txt}</font>"
                )
            brief_rows.append([Paragraph(
                "<font color='#0F172A'><b>Outstanding work</b></font>", muted)])
            brief_rows.append([Paragraph("<br/><br/>".join(work_lines), body)])
        # Parts to bring next visit.
        if return_parts:
            prows = [["SKU", "Part", "Qty", "For machine"]]
            for p in return_parts:
                prows.append([
                    p.get("part_sku", ""),
                    (p.get("part_name") or "")[:60],
                    str(p.get("qty", "")),
                    (p.get("machine_name") or "—")[:40],
                ])
            parts_tbl = Table(prows, colWidths=[26 * mm, 78 * mm, 14 * mm, 45 * mm])
            parts_tbl.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FEF3C7")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#FCD34D")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            brief_rows.append([Paragraph(
                "<font color='#0F172A'><b>Parts to bring next visit</b></font>", muted)])
            brief_rows.append([parts_tbl])
        brief_card = Table(brief_rows, colWidths=[175 * mm])
        brief_card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
            ("LINEBEFORE", (0, 0), (0, -1), 2, colors.HexColor("#F59E0B")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FDE68A")),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(brief_card)
        story.append(Spacer(1, 4 * mm))

    # ── Photos ────────────────────────────────────────────────────
    valid_images = []
    for raw in image_bytes:
        if not raw:
            continue
        try:
            img = Image(io.BytesIO(raw), width=78 * mm, height=58 * mm, kind="proportional")
            valid_images.append(img)
        except Exception as e:
            logger.warning(f"service-report: invalid image bytes: {e!r}")
    if valid_images:
        section_title = "ADDITIONAL PHOTOS" if (payload.get("machines") and any((m.get("photos") or []) for m in payload["machines"])) else f"PHOTOS ({len(valid_images)})"
        story.append(Paragraph(section_title, h_section))
        # 2-column grid
        grid_rows = []
        for i in range(0, len(valid_images), 2):
            row = valid_images[i:i + 2]
            while len(row) < 2:
                row.append("")
            grid_rows.append(row)
        photo_table = Table(grid_rows, colWidths=[85 * mm, 85 * mm])
        photo_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(photo_table)
        story.append(Spacer(1, 3 * mm))

    # ── Sign-off ──────────────────────────────────────────────────
    sig_blocks: list = []
    if sig_bytes:
        try:
            sig_img = Image(io.BytesIO(sig_bytes), width=70 * mm, height=24 * mm, kind="proportional")
            sig_blocks.append(sig_img)
        except Exception:
            pass
    sig_text = "—"
    if sig:
        sig_text = (
            f"<b>{sig.get('signed_by_name') or 'Customer'}</b>"
            + (f" · {sig['signed_by_role']}" if sig.get("signed_by_role") else "")
            + f"<br/><font color='#64748B' size='8.5'>{_fmt_date(sig.get('signed_at'))}</font>"
        )
    story.append(Paragraph("CUSTOMER SIGN-OFF", h_section))
    if sig_blocks:
        sign_table = Table(
            [[sig_blocks[0], Paragraph(sig_text, body)]],
            colWidths=[78 * mm, 97 * mm],
        )
    else:
        sign_table = Table(
            [[Paragraph("<i>No signature captured.</i>", muted), Paragraph(sig_text, body)]],
            colWidths=[78 * mm, 97 * mm],
        )
    sign_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 3 * mm))

    # ── H&S / RAMS signoff (iter 216h89) ──────────────────────────
    if safety:
        story.append(Paragraph("HEALTH &amp; SAFETY · PRE-JOB SIGN-OFF", h_section))
        items_by_id = {i["id"]: i for i in (safety.get("template_snapshot") or [])}
        ticked = set(safety.get("ticked_item_ids") or [])
        # Render checklist with ticked items only (the ones the engineer confirmed)
        lines: list = []
        for tid in safety.get("ticked_item_ids") or []:
            label = (items_by_id.get(tid, {}).get("label") or tid).replace("&", "&amp;")
            lines.append(f"<font color='#10b981'>✓</font>&nbsp;{label}")
        # Untickled but required items become a warning row
        unticked_required = [
            i for i in (safety.get("template_snapshot") or [])
            if i.get("required") and i["id"] not in ticked
        ]
        for i in unticked_required:
            lines.append(f"<font color='#dc2626'>⚠</font>&nbsp;{i['label'].replace('&', '&amp;')} (not ticked)")
        story.append(Paragraph("<br/>".join(lines) or "No items recorded.", body))
        meta = (
            f"<font size='8.5' color='#64748B'>Signed by <b>{safety.get('engineer_name', 'Engineer')}</b>"
            f" at {_fmt_date(safety.get('signed_at'))}"
            + (f" · Remarks: <i>{safety['remarks']}</i>" if safety.get("remarks") else "")
            + "</font>"
        )
        story.append(Paragraph(meta, muted))
        story.append(Spacer(1, 3 * mm))

    # ── Iter 220dj — Compliance evidence pack ───────────────────
    # Customer-facing audit trail of every safety/regulatory hurdle
    # the engineer cleared on this visit. Mandatory for MOD / NHS /
    # national-chain contracts; high-value differentiator on tenders.
    if ptw_records or loto_records or coshh_records:
        story.append(Paragraph("COMPLIANCE EVIDENCE PACK", h_section))
        # PTW
        if ptw_records:
            ptw_lines = []
            for p in ptw_records:
                hz = (p.get("hazard_category") or "").replace("_", " ")
                status_chip = (
                    "<font color='#10b981'><b>✓ completed</b></font>"
                    if p.get("status") == "completed"
                    else "<font color='#0369a1'><b>✓ issued</b></font>"
                )
                valid = ""
                if p.get("valid_until"):
                    valid = (
                        f" · valid until {_fmt_date(p.get('valid_until'))}"
                    )
                issuer = p.get("issued_by_name") or "Admin"
                ptw_lines.append(
                    f"{status_chip}&nbsp;"
                    f"<b>{(p.get('template_name') or 'Permit')}</b>"
                    f" <font color='#64748B'>({hz})</font>{valid}"
                    f" · issued by {issuer}"
                )
            story.append(Paragraph(
                "<b>Permit to Work</b><br/>" + "<br/>".join(ptw_lines), body,
            ))
            story.append(Spacer(1, 2 * mm))
        # LOTO
        if loto_records:
            loto_lines = []
            for rec in loto_records:
                ticked = list(rec.get("ticked_step_ids") or [])
                labels = [
                    loto_step_labels.get(t, t).replace("&", "&amp;")
                    for t in ticked
                ]
                step_str = (
                    ", ".join(labels) if labels else "no steps recorded"
                )
                eng = rec.get("engineer_name") or "Engineer"
                energy = ", ".join(rec.get("energy_sources") or [])
                energy_html = f" · energy: <i>{energy}</i>" if energy else ""
                loto_lines.append(
                    f"<font color='#10b981'>✓</font>&nbsp;"
                    f"<b>{eng}</b> "
                    f"<font color='#64748B'>at {_fmt_date(rec.get('completed_at'))}</font>"
                    f" — {len(ticked)} steps ticked{energy_html}"
                    f"<br/><font size='8' color='#64748B'>{step_str}</font>"
                )
            story.append(Paragraph(
                "<b>Lockout / Tagout</b><br/>" + "<br/>".join(loto_lines), body,
            ))
            story.append(Spacer(1, 2 * mm))
        # COSHH
        if coshh_records:
            coshh_lines = []
            for u in coshh_records:
                chems = [
                    f"{e.get('name', '')} <font color='#64748B'>({e.get('hazard_class', '')})</font>"
                    for e in (u.get("entries") or [])
                ]
                eng = u.get("engineer_name") or "Engineer"
                coshh_lines.append(
                    f"<font color='#10b981'>✓</font>&nbsp;"
                    f"<b>{eng}</b> "
                    f"<font color='#64748B'>at {_fmt_date(u.get('recorded_at'))}</font>"
                    f": {', '.join(chems) if chems else 'no chemicals'}"
                    + (f"<br/><font size='8' color='#64748B'>{u['notes']}</font>"
                       if u.get("notes") else "")
                )
            story.append(Paragraph(
                "<b>COSHH usage</b><br/>" + "<br/>".join(coshh_lines), body,
            ))
            story.append(Spacer(1, 3 * mm))
        else:
            story.append(Spacer(1, 1 * mm))

    # ── Customer rating (h81) ─────────────────────────────────────
    if rating:
        stars = "★" * int(rating) + "☆" * (5 - int(rating))
        story.append(Paragraph(
            f"<font color='{brand_primary}' size='14'>{stars}</font>  "
            f"<b>{rating}/5</b> from the customer"
            + (f"  ·  <i>“{rating_comment}”</i>" if rating_comment else ""),
            body,
        ))
        story.append(Spacer(1, 3 * mm))

    # ── Footer ────────────────────────────────────────────────────
    footer = Paragraph(
        f"Generated by {org_name} via GymAxis · Questions? Reply to this email or contact your service desk.",
        muted,
    )
    story.append(footer)

    doc.build(story, onFirstPage=_paint_page_chrome, onLaterPages=_paint_page_chrome)
    return buf.getvalue()


def _paint_page_chrome(canv, doc) -> None:
    """Iter 220e — Add a subtle footer with page numbers + a generation
    timestamp so a printed/PDF copy never looks like an unsigned draft.
    Called by ReportLab for every page."""
    from reportlab.lib import colors as _colors
    canv.saveState()
    width, _ = doc.pagesize
    page_num = canv.getPageNumber()
    # Hairline separator above the footer
    canv.setStrokeColor(_colors.HexColor("#E2E8F0"))
    canv.setLineWidth(0.4)
    canv.line(15, 14, width - 15, 14)
    # Footer text
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(_colors.HexColor("#94A3B8"))
    canv.drawString(15, 6, f"GymAxis Service Report · Page {page_num}")
    canv.drawRightString(
        width - 15, 6,
        datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC"),
    )
    canv.restoreState()


def _resolve_brand_dark() -> str:
    return "#0F172A"


async def _resolve_fix_summary(case_id: str, of: dict) -> str:
    """Most recent kind=fix_summary event, used when the case doc lacks a
    resolution_notes field (common path)."""
    ev = await db.svc_case_events.find_one(
        {"case_id": case_id, **of, "extra.kind": "fix_summary"},
        {"_id": 0, "body": 1},
        sort=[("at", -1)],
    )
    if ev:
        return ev.get("body") or ""
    return ""


async def _build_report(case_id: str, user: dict) -> tuple[bytes, dict]:
    of = _of(user)
    payload = await _gather_report_data(case_id, of)
    # Authorisation: engineers may only fetch reports for jobs they're
    # assigned to. Owners / managers / master admins have full org access.
    role = (user.get("role") or "").lower()
    is_privileged = (
        user.get("is_master_admin")
        or role in ("owner", "manager")
    )
    if not is_privileged:
        case = payload["case"]
        if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != user["id"]:
            # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer.
            raise HTTPException(404, "Job not found")

    payload["fix_summary"] = await _resolve_fix_summary(case_id, of)
    # Iter 220ec — resolve the org's friendly label for this case type
    # (supports custom types defined in Account Settings → Case Types).
    try:
        from routes.svc.case_types import resolve_case_type_label
        payload["case"]["_case_type_label"] = await resolve_case_type_label(
            of["organization_id"], payload["case"].get("case_type"),
        )
    except Exception as e:
        logger.warning(f"service-report: case type label resolve failed: {e!r}")

    # Iter 220e — Resolve image bytes for per-machine photos in parallel
    # with the global photos. Also exclude any already-tagged photo from
    # the global PHOTOS section to avoid duplication on the PDF.
    tagged_photo_ids: set[str] = set()
    for m in payload.get("machines") or []:
        for p in (m.get("photos") or []):
            tagged_photo_ids.add(p["id"])
            p["_bytes"] = await _fetch_image_bytes(p.get("file_url") or "")

    # Fetch image bytes for the global photo strip (un-tagged only).
    photo_bytes: list[bytes | None] = []
    for p in payload["photos"]:
        if p.get("id") in tagged_photo_ids:
            continue
        photo_bytes.append(await _fetch_image_bytes(p.get("file_url") or ""))
    sig_bytes = None
    if payload["signature"] and payload["signature"].get("image_data"):
        sig_bytes = await _fetch_image_bytes(payload["signature"]["image_data"])

    # Iter 220i — resolve effective logo bytes (engineer override > org)
    eng_brand = payload.get("engineer_branding") or {}
    org_doc = payload.get("org") or {}
    logo_src = (
        eng_brand.get("logo_url")
        or org_doc.get("logo_url")
        or (f"/api/account/logo/{org_doc.get('id')}" if org_doc.get("id") and org_doc.get("logo_path") else None)
    )
    logo_bytes = await _fetch_image_bytes(logo_src) if logo_src else None
    # Iter 220eb — Default GymAxis brand mark so every report ships
    # branded even before the org uploads their own logo
    # (Account Settings → Upload logo writes org.logo_url).
    if not logo_bytes:
        try:
            default_logo = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "static", "brand", "gymaxis-full.png",
            )
            with open(default_logo, "rb") as fh:
                logo_bytes = fh.read()
        except Exception as e:
            logger.warning(f"service-report: default logo load failed: {e!r}")
            logo_bytes = None

    pdf = _build_pdf(payload, photo_bytes, sig_bytes, logo_bytes=logo_bytes)
    return pdf, payload


@router.get("/svc/cases/{case_id}/service-report.pdf")
async def service_report_pdf(case_id: str, user=Depends(get_current_user)):
    """Stream a branded one-page service report PDF for the given case."""
    pdf, payload = await _build_report(case_id, user)
    case = payload["case"]
    filename = f"service-report-{case.get('reference', case_id[:8])}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/svc/cases/{case_id}/service-report/email")
async def service_report_email(case_id: str, data: dict | None = None, user=Depends(get_current_user)):
    """Email the service report to the customer (or override `to`).

    Body (optional): {to: 'name@domain.com', note: 'Optional cover note'}
    """
    pdf, payload = await _build_report(case_id, user)
    case = payload["case"]
    org = payload["org"]
    body_data = data or {}
    to = ((body_data.get("to") or "").strip() or (case.get("customer_email") or "").strip()).lower()
    if not to or "@" not in to:
        raise HTTPException(400, "Customer email is missing. Provide `to` or set customer_email on the case.")

    note = (body_data.get("note") or "").strip()
    org_name = org.get("name") or "Your service team"
    customer_first = (case.get("customer_name") or "there").split()[0]
    subject = f"Service report · {case.get('reference', case_id[:8])} — {case.get('title', 'Visit complete')}"
    note_html = (
        f"<p style='margin:0 0 16px 0;color:#1f2937;font-size:14px;line-height:1.6'>{note}</p>"
        if note else ""
    )
    html = (
        f"<div style='font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px'>"
        f"<h2 style='color:#0f172a;font-size:18px;margin:0 0 12px 0'>Hi {customer_first},</h2>"
        f"<p style='color:#1f2937;font-size:14px;line-height:1.6;margin:0 0 16px 0'>"
        f"Your service visit <b>{case.get('reference', '')}</b> is complete. "
        f"The full report is attached as a PDF. It includes photos, parts used, time on site "
        f"and your sign-off.</p>"
        f"{note_html}"
        f"<p style='color:#64748B;font-size:13px;line-height:1.5;margin:24px 0 0 0'>"
        f"Thanks,<br/><b>{org_name}</b></p>"
        f"</div>"
    )
    filename = f"service-report-{case.get('reference', case_id[:8])}.pdf"
    attachments = [{
        "filename": filename,
        "content": base64.b64encode(pdf).decode("ascii"),
    }]
    ok = await send_email(
        to=to,
        subject=subject,
        html=html,
        attachments=attachments,
        organization_id=user.get("organization_id"),
        category="service",
    )
    if not ok:
        raise HTTPException(502, "Email send failed — check sender domain verification.")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.svc_cases.update_one(
        {"id": case_id, "organization_id": user.get("organization_id")},
        {"$set": {
            "service_report_sent_at": now_iso,
            "service_report_sent_to": to,
            "updated_at": now_iso,
        }},
    )
    # Audit event
    try:
        from utils.svc_state import append_event
        await append_event(
            case_id=case_id,
            organization_id=user.get("organization_id"),
            event_type="note",
            actor=user,
            body=f"Service report emailed to {to}",
            extra={"kind": "service_report_emailed", "to": to},
        )
    except Exception as e:
        logger.warning(f"service-report: failed to append audit event: {e!r}")
    return {
        "ok": True,
        "to": to,
        "sent_at": now_iso,
        "filename": filename,
    }


# Iter 220cy — NPS feedback request.
# Fires a short "how did we do?" email pointing the customer at the
# public tracking page where the rating + NPS + comment form already
# lives (added in 216h90). Designed to be called from the fast-path
# close-out so the engineer ↔ customer feedback loop closes itself.
@router.post("/svc/cases/{case_id}/feedback-request/send")
async def send_feedback_request(
    case_id: str,
    data: dict | None = None,
    user=Depends(get_current_user),
):
    of_clause = {"organization_id": user.get("organization_id")}
    case = await db.svc_cases.find_one({"id": case_id, **of_clause})
    if not case:
        raise HTTPException(404, "Case not found")
    if case.get("feedback_request_sent_at") and not (data or {}).get("force"):
        # Already asked once — don't pester the customer twice.
        return {
            "ok": True, "skipped": True, "reason": "already_sent",
            "sent_at": case["feedback_request_sent_at"],
        }
    to = (data or {}).get("to") or case.get("customer_email") or ""
    if not to:
        raise HTTPException(400, "No customer email on case")
    if case.get("customer_rating"):
        # Customer already left a rating — no need to ask.
        return {"ok": True, "skipped": True, "reason": "already_rated"}

    # Mint or reuse the public tracking token so the link lands them
    # straight on the page that already has the feedback form.
    from routes.svc.public_tracking import _mint_or_get_token  # noqa: WPS433
    token = await _mint_or_get_token(case_id, of_clause)

    # Public URL: prefer X-Forwarded-Host, else REACT_APP_BACKEND_URL.
    base = (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or "https://app.gymaxis.ai"
    ).rstrip("/")
    track_url = f"{base}/track/{token}"

    org_name = case.get("organization_name") or "GymAxis"
    customer_first = (case.get("customer_name") or "").split()[0] or "there"
    subject = f"How did we do? · {case.get('reference', '')}".strip()
    html = (
        f"<div style='font-family:Helvetica,Arial,sans-serif;max-width:520px;margin:0 auto;padding:16px'>"
        f"<h2 style='color:#0f172a;font-size:18px;margin:0 0 12px 0'>Hi {customer_first},</h2>"
        f"<p style='color:#1f2937;font-size:14px;line-height:1.6;margin:0 0 16px 0'>"
        f"Thanks for letting us take care of <b>{case.get('reference', '')}</b>. "
        f"Could you spare 30 seconds to tell us how we did? Your feedback goes "
        f"straight to the engineer who attended.</p>"
        f"<p style='margin:24px 0'>"
        f"<a href='{track_url}' style='display:inline-block;background:#1d4ed8;"
        f"color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;"
        f"font-weight:700;font-size:14px'>Leave feedback</a>"
        f"</p>"
        f"<p style='color:#64748B;font-size:13px;line-height:1.5;margin:24px 0 0 0'>"
        f"Or paste this into your browser: <span style='word-break:break-all'>{track_url}</span>"
        f"</p>"
        f"<p style='color:#64748B;font-size:13px;line-height:1.5;margin:16px 0 0 0'>"
        f"Thanks,<br/><b>{org_name}</b></p>"
        f"</div>"
    )
    ok = await send_email(
        to=to, subject=subject, html=html,
        organization_id=user.get("organization_id"),
        category="service",
    )
    if not ok:
        raise HTTPException(502, "Email send failed — check sender domain verification.")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.svc_cases.update_one(
        {"id": case_id, **of_clause},
        {"$set": {
            "feedback_request_sent_at": now_iso,
            "feedback_request_sent_to": to,
            "updated_at": now_iso,
        }},
    )
    try:
        from utils.svc_state import append_event
        await append_event(
            case_id=case_id,
            organization_id=user.get("organization_id"),
            event_type="note",
            actor=user,
            body=f"Feedback request emailed to {to}",
            extra={"kind": "feedback_request_sent", "to": to, "track_url": track_url},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"feedback-request: append_event failed: {e!r}")
    return {"ok": True, "to": to, "sent_at": now_iso, "track_url": track_url}


__all__ = ["router"]

