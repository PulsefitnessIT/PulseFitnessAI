"""Sicon appointments ↔ Pulse engineer allocation.

Sicon allocates engineers to *appointments* (visits), not cases:
  • a Pulse job == Sicon case; each visit == Sicon appointment
  • engineers come from Appointment.EmployeeIDs (matched on SIJCEMPID)
  • case.AssignedToSageUserID is the case admin, never the engineer
Sicon wins: inbound changes always apply; outbound PUTs are skipped (flagged
as a conflict) when Sicon's EmployeeIDs no longer match what we last read.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from utils.database import db
from utils.sicon_client import build_appointment_payload, map_sicon_appointment_to_gymaxis
from utils.svc_state import append_event

logger = logging.getLogger(__name__)

SICON_ACTOR = {"id": "sicon", "full_name": "Sicon Service Desk"}


class SiconAllocationConflict(Exception):
    """Sicon's engineers changed since we last read them — Sicon wins."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ids(values: Any) -> list[str]:
    return sorted({str(v).strip() for v in (values or []) if str(v).strip()})


async def resolve_engineers_by_employee_ids(organization_id: str, employee_ids: list) -> list[dict]:
    """SIJCEMPID → svc_engineers. Falls back to the Sicon directory email and
    back-fills `sicon_employee_id` so the next lookup is direct."""
    out: list[dict] = []
    for emp in _ids(employee_ids):
        eng = await db.svc_engineers.find_one(
            {"organization_id": organization_id, "sicon_employee_id": emp}, {"_id": 0})
        if not eng:
            src = await db.sicon_engineers.find_one(
                {"organization_id": organization_id, "sicon_employee_id": {"$in": [emp, _int(emp)]}},
                {"_id": 0, "email": 1})
            email = ((src or {}).get("email") or "").strip().lower()
            if email:
                eng = await db.svc_engineers.find_one(
                    {"organization_id": organization_id, "email": email}, {"_id": 0})
                if eng:
                    await db.svc_engineers.update_one({"id": eng["id"]}, {"$set": {"sicon_employee_id": emp}})
        if eng:
            out.append(eng)
    return out


def _int(v: str):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _current_appointment(appointments: list[dict]) -> Optional[dict]:
    """Next upcoming open visit; else the most recent one."""
    if not appointments:
        return None
    open_ = [a for a in appointments if not a.get("appointment_complete")]
    if open_:
        return sorted(open_, key=lambda a: a.get("scheduled_start") or "")[0]
    return sorted(appointments, key=lambda a: a.get("scheduled_start") or "")[-1]


async def apply_current_allocation(case: dict, *, actor: dict = SICON_ACTOR, notify: bool = True) -> dict:
    """Derive the case's engineer(s) from its current Sicon appointment."""
    appt = _current_appointment(case.get("sicon_appointments") or [])
    if not appt:
        return case
    engineers = await resolve_engineers_by_employee_ids(case["organization_id"], appt.get("employee_ids"))
    new_ids = [e["id"] for e in engineers]
    fields: dict[str, Any] = {
        "sicon_current_appointment_id": appt.get("sicon_appointment_id"),
        "sicon_employee_ids": _ids(appt.get("employee_ids")),
        "assigned_engineer_ids": new_ids,
        "assigned_engineer_names": [e.get("full_name") or e.get("email") or "" for e in engineers],
        "assigned_engineer_id": new_ids[0] if new_ids else None,
        "assigned_engineer_name": (engineers[0].get("full_name") or engineers[0].get("email") or "") if engineers else None,
        "updated_at": _now_iso(),
    }
    if appt.get("scheduled_start"):
        fields["scheduled_at"] = appt["scheduled_start"]
    unmatched = len(_ids(appt.get("employee_ids"))) - len(engineers)
    fields["sicon_unmatched_employee_count"] = max(unmatched, 0)
    if new_ids and case.get("status") in ("new", "triaged"):
        fields["status"] = "assigned"
    before = case.get("assigned_engineer_ids") or ([case["assigned_engineer_id"]] if case.get("assigned_engineer_id") else [])
    await db.svc_cases.update_one({"id": case["id"]}, {"$set": fields})
    if sorted(before) != sorted(new_ids):
        names = ", ".join(fields["assigned_engineer_names"]) or "no engineer"
        await append_event(
            case_id=case["id"], organization_id=case["organization_id"], event_type="note", actor=actor,
            body=f"Engineers changed in Sicon → {names}",
            extra={"kind": "sicon_engineer_change", "from": before, "to": new_ids,
                   "sicon_appointment_id": appt.get("sicon_appointment_id")},
        )
        if notify:
            await _notify_engineers(case, added=[e for e in engineers if e["id"] not in before],
                                    removed=[i for i in before if i not in new_ids])
    return {**case, **fields}


async def _notify_engineers(case: dict, *, added: list[dict], removed: list[str]) -> None:
    """In-app notification for engineers gaining / losing the job."""
    ref = case.get("reference") or case["id"][:8]
    rows = [(e.get("user_id") or e["id"], f"New job {ref} allocated to you in Sicon") for e in added]
    rows += [(eid, f"Job {ref} has been reallocated to another engineer") for eid in removed]
    from routes.svc.notifications import create_notification
    for user_id, title in rows:
        await create_notification(user_id=user_id, organization_id=case["organization_id"], kind="svc_job",
                                  title=title, body=case.get("title") or "", link=f"/svc/engineer/jobs/{case['id']}",
                                  source_type="svc_case", source_id=case["id"])


async def merge_sicon_appointment(organization_id: str, payload: dict) -> Optional[dict]:
    """Upsert one Sicon appointment onto its case and re-derive engineers."""
    a = map_sicon_appointment_to_gymaxis(payload)
    if not a.get("sicon_appointment_id") or not a.get("sicon_case_id"):
        return None
    case = await db.svc_cases.find_one(
        {"organization_id": organization_id, "sicon_case_id": {"$in": [a["sicon_case_id"], str(a["sicon_case_id"])]}},
        {"_id": 0})
    if not case:
        return None
    a["employee_ids"] = _ids(a.get("employee_ids"))
    a["synced_at"] = _now_iso()
    appts = [x for x in (case.get("sicon_appointments") or [])
             if str(x.get("sicon_appointment_id")) != str(a["sicon_appointment_id"])] + [a]
    await db.svc_cases.update_one({"id": case["id"]}, {"$set": {"sicon_appointments": appts}})
    return await apply_current_allocation({**case, "sicon_appointments": appts})


# ── Outbound (Pulse → Sicon). Enqueued only; drained when SICON_ALLOW_WRITES. ──

async def push_engineer_allocation(case: dict, engineer_ids: list[str]) -> dict:
    """Queue an engineer allocation for Sicon. Returns {queued, reason}."""
    from routes.svc.integrations.sicon_sync import _enqueue
    if not case.get("sicon_case_id") and not case.get("sicon_current_appointment_id"):
        return {"queued": False, "reason": "Case not yet in Sicon"}
    engs = await db.svc_engineers.find(
        {"organization_id": case["organization_id"], "id": {"$in": engineer_ids}},
        {"_id": 0, "id": 1, "full_name": 1, "sicon_employee_id": 1}).to_list(50)
    missing = [e.get("full_name") or e["id"] for e in engs if not e.get("sicon_employee_id")]
    if missing or not engs:
        reason = f"Not sent to Sicon — no Sicon Employee ID for {', '.join(missing) or 'engineer'}"
        await append_event(case_id=case["id"], organization_id=case["organization_id"], event_type="note",
                           actor=SICON_ACTOR, body=reason, extra={"kind": "sicon_allocation_skipped"})
        return {"queued": False, "reason": reason}
    emp_ids = [_int(e["sicon_employee_id"]) for e in engs]
    appt_id = case.get("sicon_current_appointment_id")
    try:
        if appt_id:
            await _enqueue(organization_id=case["organization_id"], kind="appointment_engineers",
                           sicon_endpoint=f"/api/Service/Appointments/{appt_id}",
                           payload={"OurReference": f"{case['id']}:alloc:{appt_id}", "AppointmentID": appt_id,
                                    "CaseID": case["id"], "EmployeeIDs": emp_ids,
                                    "ExpectedEmployeeIDs": case.get("sicon_employee_ids") or []})
        else:
            start = case.get("scheduled_at") or _now_iso()
            try:
                end = (datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                       + timedelta(minutes=int(case.get("estimated_minutes") or 60))).isoformat()
            except ValueError:
                end = start
            payload = build_appointment_payload(case, start, end, emp_ids, work_briefing=case.get("title") or "")
            payload["OurReference"] = f"{case['id']}:visit:new"
            await _enqueue(organization_id=case["organization_id"], kind="appointment",
                           sicon_endpoint="/api/Service/Appointments", payload=payload)
    except Exception as exc:
        logger.warning("sicon push_engineer_allocation failed: %s", exc)
        return {"queued": False, "reason": str(exc)}
    return {"queued": True, "reason": None}


async def send_engineer_allocation(client, payload: dict) -> dict:
    """Worker side: GET the appointment, PUT only if Sicon still matches."""
    appt_id = payload["AppointmentID"]
    current = map_sicon_appointment_to_gymaxis(await client.get_appointment(appt_id))
    if _ids(current.get("employee_ids")) != _ids(payload.get("ExpectedEmployeeIDs")):
        raise SiconAllocationConflict(
            f"Sicon engineers changed (now {_ids(current.get('employee_ids'))}); Pulse change not sent")
    return await client.update_appointment(appt_id, {"EmployeeIDs": payload["EmployeeIDs"]})


async def flag_allocation_conflict(row: dict, error: str) -> None:
    case_id = (row.get("payload") or {}).get("CaseID")
    if not case_id:
        return
    await db.svc_cases.update_one({"id": case_id}, {"$set": {
        "sicon_allocation_conflict": {"at": _now_iso(), "detail": error,
                                      "wanted_employee_ids": (row.get("payload") or {}).get("EmployeeIDs")}}})
    await append_event(case_id=case_id, organization_id=row.get("organization_id") or "", event_type="note",
                       actor=SICON_ACTOR, body=f"Allocation conflict — {error}. Review in Sicon.",
                       extra={"kind": "sicon_allocation_conflict"})
