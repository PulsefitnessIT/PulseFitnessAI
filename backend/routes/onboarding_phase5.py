"""Onboarding Phase 5 — reports & exports, email templates, customer portal."""
import csv
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from routes.pulse_master_admin import _require_pulse_or_master
from routes.onboarding_projects import _progress

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Reports ────────────────────────────────────────────────────────────────

async def _report_rows() -> list:
    docs = await db.onboarding_projects.find({}).sort("created_at", -1).to_list(2000)
    rows = []
    for d in docs:
        prog = _progress(d)
        rows.append({
            "customer_name": d.get("customer_name", ""),
            "customer_type": d.get("customer_type", ""),
            "status": d.get("status", ""),
            "progress": prog["percent"],
            "required_complete": prog["required_complete"],
            "required_total": prog["required_total"],
            "blocked": prog["blocked"],
            "owner": d.get("owner") or "Unassigned",
            "go_live_target": d.get("go_live_target") or "",
            "modules": ", ".join(d.get("modules") or []),
            "created_at": (d.get("created_at") or "")[:10],
            "linked_org": d.get("organization_id") or "",
        })
    return rows


@router.get("/onboarding/reports")
async def reports(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    rows = await _report_rows()
    by_status, by_type, by_owner = {}, {}, {}
    completed = 0
    imports = await db.onboarding_audit_events.count_documents({"action": "import_committed"})
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_type[r["customer_type"]] = by_type.get(r["customer_type"], 0) + 1
        by_owner[r["owner"]] = by_owner.get(r["owner"], 0) + 1
        if r["status"] == "complete":
            completed += 1
    total = len(rows)
    return {
        "total_projects": total,
        "completed": completed,
        "go_live_success_rate": round(completed / total * 100) if total else 0,
        "by_status": by_status,
        "by_type": by_type,
        "by_owner": by_owner,
        "imports_run": imports,
        "rows": rows,
    }


_EXPORT_COLS = [
    ("customer_name", "Customer"), ("customer_type", "Type"), ("status", "Status"),
    ("progress", "Progress %"), ("required_complete", "Req done"), ("required_total", "Req total"),
    ("owner", "Owner"), ("go_live_target", "Go-live target"), ("modules", "Modules"),
    ("created_at", "Created"),
]


@router.get("/onboarding/reports/export")
async def export_report(format: str = Query("csv"), user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    rows = await _report_rows()
    fmt = format.lower()
    fname = f"onboarding-report-{datetime.now(timezone.utc):%Y%m%d}"

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([c[1] for c in _EXPORT_COLS])
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in _EXPORT_COLS])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'})

    if fmt in ("xlsx", "excel"):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Onboarding"
        ws.append([c[1] for c in _EXPORT_COLS])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2563EB")
        for r in rows:
            ws.append([r.get(k, "") for k, _ in _EXPORT_COLS])
        for i, _ in enumerate(_EXPORT_COLS, 1):
            ws.column_dimensions[chr(64 + i)].width = 18
        out = io.BytesIO()
        wb.save(out)
        return Response(content=out.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})

    if fmt == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=landscape(A4), topMargin=1 * cm, bottomMargin=1 * cm)
        styles = getSampleStyleSheet()
        elems = [Paragraph("Onboarding Report", styles["Title"]),
                 Paragraph(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · {len(rows)} projects", styles["Normal"]),
                 Spacer(1, 0.5 * cm)]
        data = [[c[1] for c in _EXPORT_COLS]] + [[str(r.get(k, "")) for k, _ in _EXPORT_COLS] for r in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D4D4D8")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F4F5")]),
        ]))
        elems.append(t)
        doc.build(elems)
        return Response(content=out.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})

    raise HTTPException(status_code=400, detail="format must be csv, xlsx or pdf")


# ── Email templates ──────────────────────────────────────────────────────

EMAIL_TEMPLATES = {
    "welcome": {
        "label": "Welcome to onboarding",
        "subject": "Welcome aboard, {customer_name}!",
        "body": "Hi {contact_name},\n\nWelcome to Pulse Fitness! We're excited to get {customer_name} set up. Your onboarding owner is {owner}. We'll guide you through each step — you can track progress any time.\n\nFirst up: completing your business profile.\n\nThanks,\nThe Pulse Fitness team",
    },
    "request_missing_info": {
        "label": "Request missing information",
        "subject": "A few details needed to continue your setup",
        "body": "Hi {contact_name},\n\nTo keep your onboarding moving, we still need:\n{missing_list}\n\nPlease send these over when you can and we'll take it from there.\n\nThanks,\n{owner}",
    },
    "user_invitation": {
        "label": "User invitation",
        "subject": "You've been invited to {customer_name} on Pulse Fitness",
        "body": "Hi {contact_name},\n\nYou've been invited to the {customer_name} portal. You'll receive a separate secure link to set your password.\n\nSee you inside,\nThe Pulse Fitness team",
    },
    "go_live_prep": {
        "label": "Go-live preparation",
        "subject": "{customer_name} — preparing for go-live",
        "body": "Hi {contact_name},\n\nWe're almost there! Your go-live target is {go_live_target}. Before we flip the switch, please review the outstanding items:\n{missing_list}\n\nThanks,\n{owner}",
    },
    "go_live_complete": {
        "label": "Go-live complete",
        "subject": "🎉 {customer_name} is live on Pulse Fitness",
        "body": "Hi {contact_name},\n\nGreat news — {customer_name} is now live! Everything is set up and ready to use. Your customer success contact is {owner}.\n\nWelcome to the platform,\nThe Pulse Fitness team",
    },
    "onboarding_delayed": {
        "label": "Onboarding delayed",
        "subject": "Update on your {customer_name} setup",
        "body": "Hi {contact_name},\n\nA quick update — your onboarding is taking a little longer than planned. We're working to resolve the outstanding items:\n{missing_list}\n\nWe'll keep you posted.\n\n{owner}",
    },
    "data_issue": {
        "label": "Data issue found",
        "subject": "Action needed: data issue in your import",
        "body": "Hi {contact_name},\n\nWhile importing your data we spotted some issues that need a quick fix. We'll share the details and an error report so you can correct and resend.\n\nThanks,\n{owner}",
    },
    "training_reminder": {
        "label": "Training reminder",
        "subject": "Your Pulse Fitness training session",
        "body": "Hi {contact_name},\n\nThis is a friendly reminder about your upcoming Pulse Fitness training. It's a great chance to get your team confident before go-live.\n\nSee you there,\n{owner}",
    },
}


@router.get("/onboarding/email-templates")
async def list_templates(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    return {"templates": [{"id": k, "label": v["label"], "subject": v["subject"]} for k, v in EMAIL_TEMPLATES.items()]}


def _render(tpl: dict, project: dict) -> dict:
    prof = project.get("profile") or {}
    prog = _progress(project)
    ctx = {
        "customer_name": project.get("customer_name", "there"),
        "contact_name": prof.get("main_contact") or "there",
        "owner": project.get("owner") or "your onboarding team",
        "go_live_target": project.get("go_live_target") or "TBC",
        "missing_list": "\n".join(f"• {m}" for m in prog["missing"]) or "• (nothing outstanding)",
    }
    def fmt(s):
        try:
            return s.format(**ctx)
        except Exception:
            return s
    return {"subject": fmt(tpl["subject"]), "body": fmt(tpl["body"])}


class RenderBody(BaseModel):
    template_id: str
    project_id: str


@router.post("/onboarding/email-templates/render")
async def render_template(body: RenderBody, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    tpl = EMAIL_TEMPLATES.get(body.template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    proj = await db.onboarding_projects.find_one({"id": body.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return _render(tpl, proj)


class SendBody(BaseModel):
    template_id: str
    project_id: str
    to: str


@router.post("/onboarding/email-templates/send")
async def send_template(body: SendBody, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    tpl = EMAIL_TEMPLATES.get(body.template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    proj = await db.onboarding_projects.find_one({"id": body.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    rendered = _render(tpl, proj)
    html = "<div style='font-family:Arial,sans-serif;font-size:14px;line-height:1.6;white-space:pre-wrap'>" + rendered["body"] + "</div>"
    try:
        await send_email(to=body.to, subject=rendered["subject"], html=html,
                         organization_id=proj.get("organization_id"), kind="onboarding")
    except Exception as e:
        logger.exception("onboarding email send failed")
        raise HTTPException(status_code=502, detail=f"Email send failed: {e}")
    try:
        await db.onboarding_audit_events.insert_one({
            "id": str(uuid.uuid4()), "project_id": body.project_id, "action": "email_sent",
            "detail": {"template": body.template_id, "to": body.to}, "actor_email": user.get("email"), "at": _now(),
        })
    except Exception:
        pass
    return {"ok": True, "sent_to": body.to}


# ── Customer-facing portal ───────────────────────────────────────────────

async def _portal_enabled() -> bool:
    s = await db.onboarding_settings.find_one({"id": "onboarding-settings"}, {"_id": 0, "customer_portal_enabled": 1})
    return bool(s and s.get("customer_portal_enabled"))


@router.get("/onboarding/portal/me")
async def portal_me(user: dict = Depends(get_current_user)) -> dict:
    """Customer-facing onboarding view for the logged-in org user."""
    if not await _portal_enabled():
        raise HTTPException(status_code=403, detail="Customer onboarding portal is not enabled.")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organisation on this account")
    proj = await db.onboarding_projects.find_one({"organization_id": org_id, "status": {"$ne": "archived"}}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="No active onboarding for your organisation")
    prog = _progress(proj)
    # Customer-friendly subset — hide internal owner notes
    steps = [{"id": s["id"], "label": s["label"], "group": s["group"], "status": s["status"], "optional": s.get("optional")}
             for s in proj.get("checklist", [])]
    return {
        "customer_name": proj.get("customer_name"),
        "status": proj.get("status"),
        "progress": prog,
        "go_live_target": proj.get("go_live_target"),
        "steps": steps,
    }


class PortalStepBody(BaseModel):
    status: str


_CUSTOMER_STATUSES = {"in_progress", "ready_for_review", "complete"}


@router.patch("/onboarding/portal/me/steps/{step_id}")
async def portal_update_step(step_id: str, body: PortalStepBody, user: dict = Depends(get_current_user)) -> dict:
    if not await _portal_enabled():
        raise HTTPException(status_code=403, detail="Customer onboarding portal is not enabled.")
    if body.status not in _CUSTOMER_STATUSES:
        raise HTTPException(status_code=400, detail="Customers may only set in_progress, ready_for_review or complete")
    org_id = user.get("organization_id")
    proj = await db.onboarding_projects.find_one({"organization_id": org_id, "status": {"$ne": "archived"}})
    if not proj:
        raise HTTPException(status_code=404, detail="No active onboarding")
    checklist = proj.get("checklist", [])
    step = next((s for s in checklist if s["id"] == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    step["status"] = body.status
    await db.onboarding_projects.update_one({"id": proj["id"]}, {"$set": {"checklist": checklist, "updated_at": _now()}})
    try:
        await db.onboarding_audit_events.insert_one({
            "id": str(uuid.uuid4()), "project_id": proj["id"], "action": "portal_step_updated",
            "detail": {"step": step["key"], "status": body.status}, "actor_email": user.get("email"), "at": _now(),
        })
    except Exception:
        pass
    return {"ok": True}
