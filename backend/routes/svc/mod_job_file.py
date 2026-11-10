"""MOD job file for the Pulse Service Desk + provider take-over.

GET  /svc/cases/{id}/job-file   — everything about a job in one payload:
     the logged fault (reporter, photos), the outside provider's updates and
     messages, visits / time on site, reports & certificates, quotes, POs.
POST /svc/cases/{id}/take-over  — Pulse takes a MOD job back from an outside
     provider; the desk then has full control.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.esp_engineer import mod_job_context
from utils.svc_desk_scope import as_case_org, external_provider
from utils.svc_state import append_event

router = APIRouter(prefix="/svc", tags=["Service Ops · MOD job file"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _case_for(user: dict, case_id: str):
    user = await as_case_org(user, case_id)
    org = user.get("organization_id") or user.get("service_org_id")
    case = await db.svc_cases.find_one({"id": case_id, "organization_id": org}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    return user, org, case


def _photos(issue: dict) -> list:
    out = [{"url": u, "name": ""} for u in issue.get("attachment_urls") or [] if isinstance(u, str)]
    for a in issue.get("attachments") or []:
        if isinstance(a, dict) and (a.get("url") or a.get("path")):
            out.append({"url": a.get("url") or a.get("path"), "name": a.get("filename") or a.get("name") or "",
                        "content_type": a.get("content_type") or ""})
    return out


@router.get("/cases/{case_id}/job-file")
async def case_job_file(case_id: str, user=Depends(get_current_user)):
    user, org, case = await _case_for(user, case_id)
    issue = await db.issues.find_one({"id": case.get("mod_issue_id")}, {"_id": 0}) if case.get("mod_issue_id") else None
    issue = issue or {}
    supplier_cases = await db.supplier_cases.find(
        {"issue_id": case.get("mod_issue_id")} if case.get("mod_issue_id") else {"id": "__none__"},
        {"_id": 0, "token": 0, "token_expires_at": 0}).sort("created_at", 1).to_list(10)
    sc_ids = [s["id"] for s in supplier_cases]
    messages = await db.supplier_case_comments.find(
        {"case_id": {"$in": sc_ids}}, {"_id": 0}).sort("created_at", 1).to_list(200) if sc_ids else []
    q = {"organization_id": org, "case_id": case_id}
    visits = await db.svc_diary_blocks.find(q, {"_id": 0}).sort("start_at", 1).to_list(50)
    time_entries = await db.svc_time_entries.find(
        q, {"_id": 0, "category": 1, "duration_minutes": 1, "started_at": 1, "engineer_name": 1}).to_list(200)
    quotes = await db.svc_quotes.find(q, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(20)
    eng_quotes = await db.svc_engineer_quotes.find(
        {"organization_id": org, "$or": [{"case_id": case_id}, {"converted_case_id": case_id}]},
        {"_id": 0, "status_history": 0}).sort("created_at", -1).to_list(20)
    pos = await db.svc_purchase_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(20)
    machine_reports = await db.svc_work_visit_machines.count_documents(q)
    signed = bool(case.get("signed_off_at") or case.get("customer_signature") or case.get("status") in ("closed", "invoiced"))
    return {
        "case_id": case_id,
        "is_mod": bool(case.get("bfpo") or case.get("mod_issue_id")),
        "logged": {
            "ticket_ref": issue.get("mod_ticket_ref") or case.get("reference"),
            "title": issue.get("title") or case.get("title"),
            "description": issue.get("description") or case.get("description"),
            "reported_at": issue.get("created_at") or case.get("created_at"),
            "photos": _photos(issue),
            **(await mod_job_context(case) if case.get("mod_issue_id") or case.get("bfpo") else {}),
        },
        "provider": {
            "active": await external_provider(case),
            "taken_over_at": case.get("provider_taken_over_at"),
            "cases": supplier_cases,
            "messages": messages,
        },
        "work": {
            "status": case.get("status"),
            "assigned_engineer_name": case.get("assigned_engineer_name"),
            "resolution_note": case.get("resolution_note"),
            "visits": visits,
            "time_minutes": sum(int(t.get("duration_minutes") or 0) for t in time_entries),
            "closed_at": case.get("closed_at"),
        },
        "documents": {
            "service_report_available": signed,
            "calibration_certificate_available": bool(case.get("calibration_captured")),
            "per_machine_reports": machine_reports,
        },
        "commercial": {
            "customer_po_number": case.get("customer_po_number") or case.get("customer_po"),
            "quotes": quotes + eng_quotes,
            "purchase_orders": pos,
        },
    }


@router.post("/cases/{case_id}/take-over")
async def take_over_case(case_id: str, data: dict | None = None, user=Depends(get_current_user)):
    user, org, case = await _case_for(user, case_id)
    prov = await external_provider(case)
    if not prov:
        raise HTTPException(400, "This job isn't with an outside provider.")
    reason = ((data or {}).get("reason") or "").strip()
    now = _now()
    who = user.get("full_name") or user.get("email") or "Pulse Service Desk"
    await db.supplier_cases.update_one({"id": prov["id"]}, {
        "$set": {"current_status": "taken_over", "updated_at": now},
        "$push": {"status_history": {"status": "taken_over", "notes": reason or f"Taken over by {who}",
                                     "updated_at": now}}})
    await db.issues.update_one({"id": case.get("mod_issue_id")}, {"$set": {
        "supplier_status": "taken_over", "updated_at": now}})
    await db.svc_cases.update_one({"id": case_id}, {"$set": {
        "provider_taken_over_at": now, "provider_taken_over_by": user.get("id"), "updated_at": now}})
    await append_event(case_id=case_id, organization_id=org, event_type="provider_taken_over", actor=user,
                       body=f"Pulse took this job over from {prov.get('supplier_name') or 'the outside provider'}"
                            + (f" — {reason}" if reason else ""))
    return {"ok": True, "taken_over_at": now}
