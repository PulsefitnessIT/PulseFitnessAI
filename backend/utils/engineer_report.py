"""Engineer report fields shared by every engineer close-out (service desk, MOD jobs, MOD PPM)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

_UK = ZoneInfo("Europe/London")


def _iso(v) -> str:
    if not v:
        return ""
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(400, f"Invalid time: {v}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def clean_report(data: dict | None, *, summary: str = "") -> dict:
    r = (data or {}).get("report") or {}
    parts = []
    for p in r.get("further_parts_required") or []:
        name = str((p or {}).get("name") or "").strip()[:200]
        if not name:
            continue
        try:
            qty = max(1, int(p.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        parts.append({"name": name, "qty": qty, "sku": str(p.get("sku") or "")[:60], "part_id": p.get("part_id") or None})
    start, end = _iso(r.get("start_time")), _iso(r.get("end_time"))
    if start and end and end <= start:
        raise HTTPException(400, "End time must be after the start time")
    return {
        "work_completed": (r.get("work_completed") or summary or "").strip()[:5000],
        "further_work_required": (r.get("further_work_required") or "").strip()[:5000],
        "further_parts_required": parts,
        "start_time": start,
        "end_time": end,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone(_UK).strftime("%d %b %Y %H:%M")
    except ValueError:
        return iso


def duration(report: dict) -> str:
    try:
        mins = int((datetime.fromisoformat(report["end_time"]) - datetime.fromisoformat(report["start_time"])).total_seconds() // 60)
    except (KeyError, ValueError, TypeError):
        return ""
    return f"{mins // 60}h {mins % 60:02d}m"


def report_rows(report: dict) -> list[tuple[str, str]]:
    parts = report.get("further_parts_required") or []
    return [
        ("Start time", fmt_time(report.get("start_time"))),
        ("End time", fmt_time(report.get("end_time")) + (f"  ({duration(report)})" if duration(report) else "")),
        ("Description of Work Completed", report.get("work_completed") or "—"),
        ("Further Work Required", report.get("further_work_required") or "None"),
        ("Further Parts Required", "\n".join(f"{p['qty']} × {p['name']}" + (f" ({p['sku']})" if p.get("sku") else "") for p in parts) or "None"),
    ]


def report_flowables(report: dict, h_section, body):
    """Reportlab flowables for the platypus-based service report."""
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    rows = [[Paragraph(f"<b>{k}</b>", body), Paragraph(escape(v).replace("\n", "<br/>"), body)] for k, v in report_rows(report)]
    t = Table(rows, colWidths=[55 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E0E0E0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph("ENGINEER REPORT", h_section), t, Spacer(1, 4 * mm)]


def draw_report_canvas(c, x: float, y: float, width: float, report: dict) -> float:
    """Draw the report rows on a raw reportlab canvas; returns the new y."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.lib import colors
    c.setFillColor(colors.HexColor("#1B1C1D"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "ENGINEER REPORT")
    y -= 6 * mm
    for label, val in report_rows(report):
        lines = [ln for chunk in val.split("\n") for ln in (simpleSplit(chunk, "Helvetica", 9, width - 55 * mm) or [""])]
        if y - len(lines) * 4.5 * mm < 20 * mm:
            c.showPage()
            y = 280 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, label)
        c.setFont("Helvetica", 9)
        for ln in lines:
            c.drawString(x + 55 * mm, y, ln)
            y -= 4.5 * mm
        y -= 1.5 * mm
    return y


FURTHER_PARTS_SOURCE = "further_parts_required"


async def raise_further_parts(case: dict, report: dict, user: dict) -> int:
    """Turn the report's Further Parts Required into pending stores parts requests (idempotent per case)."""
    import uuid
    from utils.database import db
    from utils.svc_state import append_event
    parts = report.get("further_parts_required") or []
    if not parts or await db.svc_parts_requests.find_one({"origin_case_id": case["id"], "source": FURTHER_PARTS_SOURCE}, {"_id": 1}):
        return 0
    org_id = case["organization_id"]
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for p in parts:
        sku = (p.get("sku") or "").strip().upper()
        cat = await db.svc_parts.find_one({"organization_id": org_id, "sku": sku}, {"_id": 0}) if sku else None
        docs.append({
            "id": str(uuid.uuid4()), "organization_id": org_id,
            "case_id": case["id"], "case_reference": case.get("reference"),
            "engineer_id": user.get("id"), "engineer_name": user.get("full_name") or user.get("email") or "",
            "part_sku": sku or "TBC", "part_name": p["name"], "qty": int(p.get("qty") or 1),
            "list_price_gbp": float((cat or {}).get("list_price") or 0), "urgency": "normal",
            "notes": "Further parts required — for the next visit", "status": "pending",
            "in_catalogue": bool(cat), "machine_id": None, "machine_name": case.get("asset_name") or None,
            "source": FURTHER_PARTS_SOURCE, "origin_case_id": case["id"], "origin_case_reference": case.get("reference"),
            "created_at": now, "updated_at": now,
        })
    await db.svc_parts_requests.insert_many(docs)
    await append_event(
        case_id=case["id"], organization_id=org_id, event_type="note", actor=user,
        body="Parts requested for the next visit: " + ", ".join(f"{d['qty']} × {d['part_name']}" for d in docs),
        extra={"kind": "parts_request", "source": FURTHER_PARTS_SOURCE, "request_ids": [d["id"] for d in docs]},
    )
    return len(docs)


async def follow_up_draft(case: dict) -> dict:
    from utils.database import db
    report = case.get("engineer_report") or {}
    site = await db.sites.find_one({"id": case.get("site_id")}, {"_id": 0, "organization_id": 1}) if case.get("site_id") else None
    parts = report.get("further_parts_required") or []
    lines = [f"Follow-up to {case.get('reference') or 'previous visit'}."]
    if report.get("further_work_required"):
        lines += ["", "Further work required:", report["further_work_required"]]
    if parts:
        lines += ["", "Parts required (requested from stores):"] + [f"- {p['qty']} × {p['name']}" for p in parts]
    return {
        "follow_up_of": case["id"], "reference": case.get("reference"),
        "customerOrgId": (site or {}).get("organization_id") or "",
        "siteId": case.get("site_id") or "",
        "equipmentIds": [x for x in dict.fromkeys([case.get("asset_id"), *(case.get("equipment_ids") or [])]) if x],
        "title": f"Follow-up: {case.get('title') or case.get('reference') or ''}"[:120],
        "description": "\n".join(lines),
        "existing_follow_up": case.get("follow_up_case_reference") or None,
        "priority": case.get("priority") or "p3", "coverType": case.get("cover_type") or "contract",
        "customerName": case.get("customer_name") or "", "customerEmail": case.get("customer_email") or "",
        "customerPhone": case.get("customer_phone") or "",
    }


async def link_follow_up(new_case: dict, original_id: str, user: dict) -> None:
    """Mark the original job, and move its further-parts requests onto the follow-up job."""
    from utils.database import db
    from utils.svc_state import append_event
    from utils.svc_desk_scope import as_case_org
    org_id = new_case["organization_id"]
    orig = await db.svc_cases.find_one({"id": original_id}, {"_id": 0, "id": 1, "reference": 1, "organization_id": 1, "follow_up_case_id": 1})
    if not orig or orig.get("follow_up_case_id"):
        return
    # Only link jobs the caller can see: same org, or a MOD job visible to the Pulse desk.
    if orig["organization_id"] != org_id and (await as_case_org(user, original_id)).get("organization_id") != orig["organization_id"]:
        return
    now = datetime.now(timezone.utc).isoformat()
    await db.svc_cases.update_one({"id": new_case["id"]}, {"$set": {"follow_up_of": orig["id"], "follow_up_of_reference": orig.get("reference")}})
    await db.svc_cases.update_one({"id": orig["id"]}, {"$set": {
        "follow_up_case_id": new_case["id"], "follow_up_case_reference": new_case.get("reference"), "updated_at": now}})
    moved = await db.svc_parts_requests.update_many(
        {"case_id": orig["id"], "organization_id": orig["organization_id"], "source": FURTHER_PARTS_SOURCE,
         "status": {"$nin": ["rejected", "cancelled"]}},
        {"$set": {"case_id": new_case["id"], "case_reference": new_case.get("reference"), "organization_id": org_id, "updated_at": now}},
    )
    suffix = f" · {moved.modified_count} parts request(s) moved to it" if moved.modified_count else ""
    await append_event(case_id=orig["id"], organization_id=orig["organization_id"], event_type="note", actor=user,
                       body=f"Follow-up job {new_case.get('reference')} booked{suffix}", extra={"kind": "follow_up", "case_id": new_case["id"]})
    await append_event(case_id=new_case["id"], organization_id=org_id, event_type="note", actor=user,
                       body=f"Follow-up to {orig.get('reference')}{suffix}", extra={"kind": "follow_up", "case_id": orig["id"]})


_DONE_STATUSES = ["closed", "invoiced", "repaired", "resolved", "completed", "awaiting_sign_off"]


async def backfill_engineer_reports() -> int:
    """Give already-completed jobs an engineer report built from their notes and timers (no-op once done)."""
    from utils.database import db
    n = 0
    async for c in db.svc_cases.find(
        {"status": {"$in": _DONE_STATUSES}, "engineer_report": {"$exists": False}},
        {"_id": 0, "id": 1, "resolution_notes": 1, "arrived_at": 1, "completed_at": 1, "closed_at": 1, "resolved_at": 1, "updated_at": 1},
    ):
        starts, ends = [], []
        async for e in db.svc_time_entries.find({"case_id": c["id"]}, {"_id": 0, "start_at": 1, "end_at": 1, "category": 1}):
            if e.get("category") == "travel":
                continue
            if e.get("start_at"):
                starts.append(e["start_at"])
            if e.get("end_at"):
                ends.append(e["end_at"])
        start = min(starts) if starts else (c.get("arrived_at") or "")
        end = max(ends) if ends else (c.get("completed_at") or c.get("resolved_at") or c.get("closed_at") or "")
        if start and end and end < start:
            end = ""
        await db.svc_cases.update_one({"id": c["id"], "engineer_report": {"$exists": False}}, {"$set": {"engineer_report": {
            "work_completed": (c.get("resolution_notes") or "").strip(), "further_work_required": "",
            "further_parts_required": [], "start_time": start, "end_time": end,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "backfilled": True,
        }}})
        n += 1
    async for s in db.bfpo_ppm_services.find(
        {"status": "completed", "engineer_report": {"$exists": False}},
        {"_id": 0, "id": 1, "notes": 1, "started_at": 1, "completed_at": 1},
    ):
        await db.bfpo_ppm_services.update_one({"id": s["id"], "engineer_report": {"$exists": False}}, {"$set": {"engineer_report": {
            "work_completed": (s.get("notes") or "").strip(), "further_work_required": "", "further_parts_required": [],
            "start_time": s.get("started_at") or "", "end_time": s.get("completed_at") or "",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "backfilled": True,
        }}})
        n += 1
    return n
