"""ASER exports — CSV / Excel register dumps, a PDF summary report, and the
per-asset "ASER Replacement Evidence Report".

MOD-only + site-scoped (reuses the scope helpers from routes.mod_aser).
Heavy libs (reportlab / openpyxl) are imported lazily inside the handlers
to keep module import non-blocking (K8s readiness).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from utils.auth import get_current_user
from utils.database import db
from routes.mod_aser import (
    _require_mod, _sites_in_scope, REMOVAL_FLAG_STATUSES, EVENT_TYPES,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["MOD ASER Exports"])

_EVENT_LABELS = {k: v for k, v in EVENT_TYPES}
_TC = lambda s: (s or "").replace("_", " ").title()


async def _scoped_entries(user: dict, *, site_id=None, event_type=None, risk=None,
                          status=None, start=None, end=None) -> tuple[list[dict], list[str]]:
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    q: dict = {"site_id": {"$in": site_ids}}
    if site_id and site_id in site_ids:
        q["site_id"] = site_id
    if event_type:
        q["event_type"] = event_type
    if risk:
        q["risk.rating"] = risk
    if status:
        q["status"] = status
    if start or end:
        rng: dict = {}
        if start:
            rng["$gte"] = start
        if end:
            rng["$lte"] = end + "T23:59:59"
        q["created_at"] = rng
    rows = await db.aser_entries.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return rows, site_ids


def _flatten(e: dict) -> dict:
    ai = e.get("activity_impact") or {}
    si = e.get("safety_impact") or {}
    r = e.get("risk") or {}
    snap = e.get("equipment_snapshot") or {}
    fu = e.get("follow_up") or {}
    return {
        "ASER Ref": e.get("aser_ref"),
        "Date Logged": (e.get("created_at") or "")[:10],
        "Site": e.get("site_name"),
        "Equipment": snap.get("name"),
        "Asset Number": snap.get("asset_number"),
        "Serial Number": snap.get("serial_number"),
        "Equipment Type": snap.get("equipment_type"),
        "Event Type": _EVENT_LABELS.get(e.get("event_type"), _TC(e.get("event_type"))),
        "Title": e.get("title"),
        "Description": e.get("description"),
        "Impacted Rehab": "Yes" if ai.get("impacted_rehab") else "No",
        "Group Programme": "Yes" if ai.get("impacted_group") else "No",
        "Individual Programme": "Yes" if ai.get("impacted_individual") else "No",
        "Sessions Affected": ai.get("sessions_affected", 0),
        "Patients Affected": ai.get("patients_affected", 0),
        "Injured": "Yes" if si.get("anyone_injured") else "No",
        "Near Miss": "Yes" if si.get("near_miss") else "No",
        "Risk Rating": _TC(r.get("rating")),
        "Potential Severity": _TC(r.get("potential_severity")),
        "Likelihood": _TC(r.get("likelihood")),
        "Equipment Status": _TC(e.get("equipment_status")),
        "Linked Fault": e.get("linked_fault_ref") or (e.get("linked_fault_id") or ""),
        "CAPEX Flagged": "Yes" if e.get("capex_flagged") else "No",
        "Repeated-Issue Label": _TC((e.get("repeated_issue") or {}).get("label")),
        "Action Owner": fu.get("action_owner") or "",
        "Due Date": fu.get("due_date") or "",
        "Status": _TC(e.get("status")),
    }


@router.get("/mod/aser/export/csv")
async def export_csv(
    site_id: Optional[str] = Query(None), event_type: Optional[str] = Query(None),
    risk: Optional[str] = Query(None), status: Optional[str] = Query(None),
    start: Optional[str] = Query(None), end: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    rows, _ = await _scoped_entries(user, site_id=site_id, event_type=event_type,
                                    risk=risk, status=status, start=start, end=end)
    flat = [_flatten(e) for e in rows]
    cols = list(flat[0].keys()) if flat else list(_flatten({}).keys())

    def gen():
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in flat:
            w.writerow(r)
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fn = f"ASER_Register_{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/mod/aser/export/xlsx")
async def export_xlsx(
    site_id: Optional[str] = Query(None), event_type: Optional[str] = Query(None),
    risk: Optional[str] = Query(None), status: Optional[str] = Query(None),
    start: Optional[str] = Query(None), end: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    rows, _ = await _scoped_entries(user, site_id=site_id, event_type=event_type,
                                    risk=risk, status=status, start=start, end=end)
    flat = [_flatten(e) for e in rows]
    cols = list(flat[0].keys()) if flat else list(_flatten({}).keys())

    wb = Workbook(); ws = wb.active; ws.title = "ASER Register"
    header_fill = PatternFill("solid", fgColor="0F1419")
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = header_fill
    for r in flat:
        ws.append([r.get(c, "") for c in cols])
    for i, col in enumerate(cols, 1):
        width = min(max(len(col) + 2, 12), 45)
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    ws.freeze_panes = "A2"

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    fn = f"ASER_Register_{datetime.now(timezone.utc):%Y%m%d}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# ── PDF helpers ───────────────────────────────────────────────────────
def _pdf_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=17, textColor=colors.HexColor("#0F1419"), spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280")),
        "section": ParagraphStyle("sec", parent=base["Heading2"], fontSize=11, textColor=colors.HexColor("#b91c1c"), spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#111827")),
        "muted": ParagraphStyle("m", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#6b7280")),
    }


@router.get("/mod/aser/export/pdf")
async def export_summary_pdf(
    site_id: Optional[str] = Query(None), start: Optional[str] = Query(None),
    end: Optional[str] = Query(None), user: dict = Depends(get_current_user),
):
    content, fn = await _build_summary_pdf(user, site_id=site_id, start=start, end=end)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


async def _build_summary_pdf(user: dict, *, site_id=None, start=None, end=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    rows, site_ids = await _scoped_entries(user, site_id=site_id, start=start, end=end)
    st = _pdf_styles()
    scope_name = "All permitted MOD sites"
    if site_id:
        s = await db.organizations.find_one({"id": site_id}, {"_id": 0, "name": 1})
        scope_name = (s or {}).get("name") or scope_name

    total = len(rows)
    high = sum(1 for e in rows if (e.get("risk") or {}).get("rating") in ("high", "critical"))
    removed = len({e["equipment_id"] for e in rows if e.get("equipment_status") in REMOVAL_FLAG_STATUSES})
    capex = sum(1 for e in rows if e.get("capex_flagged"))
    sessions = sum((e.get("activity_impact") or {}).get("sessions_affected", 0) or 0 for e in rows)
    linked = sum(1 for e in rows if e.get("linked_fault_id"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="ASER Report")
    story = [
        Paragraph("ASER — Activity Safety Events Register", st["title"]),
        Paragraph(f"MOD Service Portal · Report generated {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC", st["sub"]),
        Paragraph(f"Scope: <b>{scope_name}</b>&nbsp;&nbsp;|&nbsp;&nbsp;Period: {start or 'all time'} → {end or 'today'}", st["sub"]),
        Spacer(1, 8),
    ]

    summary = [["Total entries", str(total), "High/critical", str(high)],
               ["Equipment removed/for replacement", str(removed), "CAPEX evidence flags", str(capex)],
               ["Rehab sessions impacted", str(sessions), "Linked faults", str(linked)]]
    ts = Table(summary, colWidths=[62 * mm, 25 * mm, 62 * mm, 26 * mm])
    ts.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#6b7280")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    story += [st_para for st_para in [Paragraph("SUMMARY", st["section"]), ts]]

    # Repeated-issue equipment
    assets: dict = {}
    for e in rows:
        eid = e.get("equipment_id"); snap = e.get("equipment_snapshot") or {}
        a = assets.setdefault(eid, {"name": snap.get("name"), "serial": snap.get("serial_number"),
                                    "count": 0, "label": (e.get("repeated_issue") or {}).get("label")})
        a["count"] += 1
        lbl = (e.get("repeated_issue") or {}).get("label")
        if lbl:
            a["label"] = lbl
    repeated = [a for a in assets.values() if a.get("label") in {
        "repeated_issue", "escalation_recommended", "replacement_evidence_building", "replacement_strongly_recommended"}]
    if repeated:
        story.append(Paragraph("REPEATED-ISSUE EQUIPMENT (REPLACEMENT EVIDENCE)", st["section"]))
        rdata = [["Equipment", "Serial", "ASER events", "Assessment"]]
        for a in sorted(repeated, key=lambda x: x["count"], reverse=True):
            rdata.append([a["name"] or "-", a["serial"] or "-", str(a["count"]), _TC(a["label"])])
        rt = Table(rdata, colWidths=[62 * mm, 40 * mm, 25 * mm, 48 * mm])
        rt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1419")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fef2f2")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(rt)

    # Register table (compact)
    story.append(Paragraph("ASER ENTRIES", st["section"]))
    if not rows:
        story.append(Paragraph("No ASER entries in this period.", st["muted"]))
    else:
        data = [["Ref", "Date", "Equipment", "Event", "Risk", "Status"]]
        for e in rows[:120]:
            snap = e.get("equipment_snapshot") or {}
            data.append([
                e.get("aser_ref", ""), (e.get("created_at") or "")[:10], (snap.get("name") or "")[:28],
                _EVENT_LABELS.get(e.get("event_type"), "")[:24],
                _TC((e.get("risk") or {}).get("rating")), _TC(e.get("status")),
            ])
        t = Table(data, colWidths=[30 * mm, 20 * mm, 45 * mm, 40 * mm, 18 * mm, 22 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1419")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    story += [Spacer(1, 10), Paragraph(
        "This report summarises equipment safety events and their impact on rehab / activity delivery. "
        "It may support replacement / CAPEX review. It does not guarantee funding approval.", st["muted"])]

    doc.build(story)
    buf.seek(0)
    fn = f"ASER_Summary_{datetime.now(timezone.utc):%Y%m%d}.pdf"
    return buf.getvalue(), fn


@router.get("/mod/aser/export/replacement-evidence/{equipment_id}")
async def replacement_evidence_pdf(equipment_id: str, user: dict = Depends(get_current_user)):
    content, fn = await _build_replacement_pdf(user, equipment_id)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


async def _build_replacement_pdf(user: dict, equipment_id: str):
    """Per-asset evidence report supporting replacement of old/unreliable PTE."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    equipment = await db.equipment.find_one(
        {"id": equipment_id, "organization_id": {"$in": site_ids}}, {"_id": 0})
    if not equipment:
        raise HTTPException(404, "Equipment not found in your permitted scope")

    entries = await db.aser_entries.find(
        {"equipment_id": equipment_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    total_faults = await db.issues.count_documents({"equipment_id": equipment_id, "is_drill": {"$ne": True}})

    near_miss = sum(1 for e in entries if (e.get("safety_impact") or {}).get("near_miss"))
    incidents = sum(1 for e in entries if e.get("event_type") == "incident")
    high = sum(1 for e in entries if (e.get("risk") or {}).get("rating") in ("high", "critical"))
    removed = sum(1 for e in entries if e.get("equipment_status") in REMOVAL_FLAG_STATUSES)
    sessions = sum((e.get("activity_impact") or {}).get("sessions_affected", 0) or 0 for e in entries)
    groups = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_group"))
    individuals = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_individual"))

    install = equipment.get("install_date") or equipment.get("installed_at") or equipment.get("created_at")
    age = "-"
    try:
        if install:
            d = datetime.fromisoformat(str(install).replace("Z", "+00:00"))
            age = f"{(datetime.now(timezone.utc) - d).days // 365} years"
    except Exception:
        pass

    label = (entries[0].get("repeated_issue") or {}).get("label") if entries else "monitor"
    recommend = label in {"replacement_evidence_building", "replacement_strongly_recommended", "escalation_recommended"} or removed > 0 or high >= 2

    st = _pdf_styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="ASER Replacement Evidence Report")
    story = [
        Paragraph("ASER Replacement Evidence Report", st["title"]),
        Paragraph(f"MOD Service Portal · Generated {datetime.now(timezone.utc):%d %b %Y} · Assessment: <b>{_TC(label)}</b>", st["sub"]),
        Spacer(1, 8),
        Paragraph("EQUIPMENT", st["section"]),
    ]
    eq_rows = [
        ["Name", equipment.get("name") or "-", "Asset No.", equipment.get("asset_number") or equipment.get("asset_tag") or "-"],
        ["Serial", equipment.get("serial_number") or "-", "Model", equipment.get("model") or "-"],
        ["Type", equipment.get("machine_type") or equipment.get("category") or "-", "Age", age],
        ["Location", equipment.get("location") or "-", "Warranty", equipment.get("warranty_expiry") or "-"],
    ]
    et = Table(eq_rows, colWidths=[22 * mm, 65 * mm, 22 * mm, 66 * mm])
    et.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#6b7280")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    story.append(et)

    story.append(Paragraph("REPEATED ISSUE &amp; DELIVERY IMPACT EVIDENCE", st["section"]))
    ev = [["Total ASER events", str(len(entries)), "Total faults logged", str(total_faults)],
          ["High/critical events", str(high), "Times removed from use", str(removed)],
          ["Near-misses", str(near_miss), "Incidents", str(incidents)],
          ["Rehab sessions impacted", str(sessions), "Group programmes impacted", str(groups)],
          ["Individual programmes impacted", str(individuals), "CAPEX flagged", "Yes" if any(e.get("capex_flagged") for e in entries) else "No"]]
    evt = Table(ev, colWidths=[58 * mm, 24 * mm, 58 * mm, 35 * mm])
    evt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#6b7280")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    story.append(evt)

    if entries:
        story.append(Paragraph("ASER EVENT HISTORY", st["section"]))
        data = [["Ref", "Date", "Event", "Risk", "Status"]]
        for e in entries[:60]:
            data.append([e.get("aser_ref", ""), (e.get("created_at") or "")[:10],
                         _EVENT_LABELS.get(e.get("event_type"), "")[:26],
                         _TC((e.get("risk") or {}).get("rating")), _TC(e.get("equipment_status"))])
        t = Table(data, colWidths=[30 * mm, 20 * mm, 55 * mm, 20 * mm, 30 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F1419")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    rec = ("Based on repeated ASER events, safety concerns and rehab-delivery impact, "
           "<b>replacement of this equipment is recommended for review.</b>") if recommend else \
          ("This asset is currently under monitoring. Continued ASER events may build a "
           "replacement case.")
    story += [Spacer(1, 10), Paragraph("RECOMMENDATION", st["section"]), Paragraph(rec, st["body"]),
              Spacer(1, 6), Paragraph(
                  "This report evidences repeated PTE issues impacting rehab / activity delivery and may "
                  "support replacement / CAPEX review. It does not guarantee funding approval.", st["muted"])]

    doc.build(story)
    buf.seek(0)
    safe = (equipment.get("serial_number") or equipment_id)[:20]
    fn = f"ASER_Replacement_Evidence_{safe}.pdf"
    return buf.getvalue(), fn


# ══════════════════════════════════════════════════════════════════
#                 EMAIL THE REPORT
# ══════════════════════════════════════════════════════════════════
import base64 as _b64
from pydantic import BaseModel, Field


def _valid_emails(raw: list[str]) -> list[str]:
    import re
    rx = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    out = []
    for e in raw or []:
        e = (e or "").strip()
        if e and rx.match(e):
            out.append(e)
    return sorted(set(out))


async def _resolve_recipients(user: dict, site_id: Optional[str], emails: list[str],
                              to_managers: bool, to_service_desk: bool, to_account_manager: bool) -> list[str]:
    from routes.mod_aser import _site_manager_emails, _load_settings
    rcpts = set(_valid_emails(emails))
    settings = await _load_settings()
    notif = settings.get("notifications") or {}
    if to_managers and site_id:
        for e in await _site_manager_emails(site_id):
            rcpts.add(e)
    if to_service_desk and (notif.get("service_desk") or {}).get("email"):
        rcpts.add(notif["service_desk"]["email"])
    if to_account_manager and (notif.get("account_manager") or {}).get("email"):
        rcpts.add(notif["account_manager"]["email"])
    return _valid_emails(list(rcpts))


class EmailReportBody(BaseModel):
    emails: list[str] = Field(default_factory=list, max_length=10)
    to_managers: bool = False
    to_service_desk: bool = False
    to_account_manager: bool = False
    message: Optional[str] = Field(default=None, max_length=2000)
    site_id: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


def _report_email_html(title: str, note: Optional[str]) -> str:
    body = f'<p style="font-size:13px;color:#111827">{note}</p>' if note else ""
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px">
      <h2 style="color:#0F1419;margin:0 0 4px">{title}</h2>
      <p style="color:#6b7280;font-size:13px;margin:0 0 12px">MOD Service Portal · ASER register</p>
      {body}
      <p style="font-size:13px;color:#111827">The report is attached as a PDF. It evidences equipment safety events
      and their impact on rehab / activity delivery, and may support replacement / CAPEX review. It does not guarantee funding approval.</p>
      <p style="font-size:11px;color:#9ca3af;margin-top:16px">Generated from the Pulse Fitness MOD Service Portal.</p>
    </div>"""


@router.post("/mod/aser/email/summary")
async def email_summary(body: EmailReportBody, user: dict = Depends(get_current_user)):
    from utils.email import send_email
    content, fn = await _build_summary_pdf(user, site_id=body.site_id, start=body.start, end=body.end)
    rcpts = await _resolve_recipients(user, body.site_id, body.emails, body.to_managers,
                                      body.to_service_desk, body.to_account_manager)
    if not rcpts:
        raise HTTPException(400, "No valid recipients — add an email address or select a role")
    attach = [{"filename": fn, "content": _b64.b64encode(content).decode("ascii")}]
    html = _report_email_html("ASER Summary Report", body.message)
    sent = 0
    for r in rcpts:
        try:
            await send_email(r, "ASER Summary Report", html, attachments=attach,
                             kind="mod_aser_report", organization_id=body.site_id)
            sent += 1
        except Exception as e:
            logger.warning("ASER summary email failed for %s: %s", r, e)
    return {"ok": True, "sent": sent, "recipients": rcpts}


@router.post("/mod/aser/email/replacement-evidence/{equipment_id}")
async def email_replacement_evidence(equipment_id: str, body: EmailReportBody,
                                     user: dict = Depends(get_current_user)):
    from utils.email import send_email
    content, fn = await _build_replacement_pdf(user, equipment_id)
    # site_id for role-resolution: derive from equipment's org
    eq = await db.equipment.find_one({"id": equipment_id}, {"_id": 0, "organization_id": 1})
    site_id = body.site_id or (eq or {}).get("organization_id")
    rcpts = await _resolve_recipients(user, site_id, body.emails, body.to_managers,
                                      body.to_service_desk, body.to_account_manager)
    if not rcpts:
        raise HTTPException(400, "No valid recipients — add an email address or select a role")
    attach = [{"filename": fn, "content": _b64.b64encode(content).decode("ascii")}]
    html = _report_email_html("ASER Replacement Evidence Report", body.message)
    sent = 0
    for r in rcpts:
        try:
            await send_email(r, "ASER Replacement Evidence Report", html, attachments=attach,
                             kind="mod_aser_report", organization_id=site_id)
            sent += 1
        except Exception as e:
            logger.warning("ASER RE email failed for %s: %s", r, e)
    return {"ok": True, "sent": sent, "recipients": rcpts}
