"""
Sicon inbound worker (Iter 248).

Closes the loop the outbox worker opened: the service team schedules /
amends cases **in Sicon**, and this worker pulls them into Pulse Fitness
`svc_cases` so the assigned engineer receives the job in the Engineer
App. Together with `utils/sicon_outbox_worker.py` (Pulse Fitness → Sicon)
this gives the full bi-directional cycle:

    Sicon Service Desk ──poll──▶ svc_cases ──▶ Engineer App
    Engineer App actions ──outbox──▶ Sicon (notes / appointments /
                                            signatures / photos / parts)

Flow per organisation (sicon_config.enabled == True):
  1. `client.list_cases_updated_since(last_inbound_poll_at)`
  2. every Sicon ServiceCall is stashed raw in `svc_sicon_inbox`
     (audit + replay), then merged into `svc_cases` via
     `merge_sicon_case` — idempotent on Sicon id / case reference.
  3. Engineers come from each case's Sicon *appointments* (EmployeeIDs →
     `svc_engineers.sicon_employee_id`, see utils/sicon_appointments.py).
     `AssignedToSageUserID` is the Sicon case admin, stored separately.

Anti-echo: merges write straight to Mongo (no `push_case`), so an
inbound update never re-enqueues itself to the outbox.

Demand-driven endpoints live in `routes/svc/integrations/health.py`
(`/sicon/poll-now`, `/sicon/simulate-inbound`). The background loop is
env-gated behind SICON_AUTOSTART_WORKER until live credentials land.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from utils.database import db
from utils.sicon_common import get_sicon_client, get_sicon_config, log_sicon_event
from utils.svc_state import append_event, OPEN_STATES

logger = logging.getLogger(__name__)

INBOX = "svc_sicon_inbox"

# Reverse crosswalks — built from the authoritative outbound maps so the
# two directions can never drift apart.
from routes.svc.integrations.sicon_sync import PRIORITY_CROSSWALK, STATUS_CROSSWALK  # noqa: E402

REVERSE_STATUS: dict[str, str] = {v: k for k, v in STATUS_CROSSWALK.items()}
REVERSE_PRIORITY: dict[int, str] = {v: k for k, v in PRIORITY_CROSSWALK.items()}

SICON_ACTOR = {"id": "sicon", "full_name": "Sicon Service Desk"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────
# Engineer resolution
# ─────────────────────────────────────────────────────────────────

async def resolve_engineer(organization_id: str, payload: dict) -> Optional[dict]:
    """Map a Sicon assignment onto a provisioned `svc_engineers` row.

    Only engineer-level hints: ResourceID / AppointmentResourceID →
    `sage_user_id`/`id`, then EngineerEmail. `AssignedToSageUserID` is the
    case admin (confirmed by Sicon) and is never treated as the engineer.
    """
    sage_ids = [
        str(payload.get("ResourceID") or "").strip(),
        str(payload.get("AppointmentResourceID") or "").strip(),
    ]
    for sid in sage_ids:
        if not sid:
            continue
        eng = await db.svc_engineers.find_one(
            {"organization_id": organization_id, "sage_user_id": sid}, {"_id": 0})
        if eng:
            return eng
        eng = await db.svc_engineers.find_one(
            {"organization_id": organization_id, "id": sid}, {"_id": 0})
        if eng:
            return eng
    email = (payload.get("EngineerEmail") or "").strip().lower()
    if email:
        eng = await db.svc_engineers.find_one(
            {"organization_id": organization_id, "email": email}, {"_id": 0})
        if eng:
            return eng
    return None


# ─────────────────────────────────────────────────────────────────
# Merge: Sicon ServiceCall → svc_cases
# ─────────────────────────────────────────────────────────────────

def _entity(payload: dict) -> dict:
    """Sicon responses wrap rows in `entity`; accept both shapes."""
    if isinstance(payload, dict) and isinstance(payload.get("entity"), dict):
        return payload["entity"]
    return payload or {}


async def _find_existing(organization_id: str, e: dict) -> Optional[dict]:
    sicon_id = e.get("SiSMCaseId") or e.get("ServiceCallID") or e.get("Id")
    if sicon_id:
        case = await db.svc_cases.find_one(
            {"organization_id": organization_id, "sicon_case_id": sicon_id}, {"_id": 0})
        if case:
            return case
    our_ref = (e.get("OurReference") or "").strip()
    if our_ref:
        case = await db.svc_cases.find_one(
            {"organization_id": organization_id, "id": our_ref}, {"_id": 0})
        if case:
            return case
    for ref in ((e.get("CallReference") or "").strip(), (e.get("CaseNumber") or "").strip()):
        if ref:
            case = await db.svc_cases.find_one(
                {"organization_id": organization_id,
                 "$or": [{"reference": ref}, {"sicon_case_number": ref}]},
                {"_id": 0})
            if case:
                return case
    return None


async def merge_sicon_case(organization_id: str, payload: dict,
                           *, source: str = "sicon_poll") -> dict:
    """Upsert one Sicon ServiceCall into `svc_cases`. Idempotent.

    Returns {"case": <doc>, "created": bool}. Never enqueues outbound
    pushes (anti-echo) — Sicon already has this state.
    """
    e = _entity(payload)
    existing = await _find_existing(organization_id, e)

    status_raw = e.get("StatusID") or e.get("SiSMDocumentStatusName") or ""
    mapped_status = REVERSE_STATUS.get(str(status_raw))
    priority = REVERSE_PRIORITY.get(e.get("PriorityID")) if e.get("PriorityID") is not None else None

    engineer = await resolve_engineer(organization_id, e)

    fields: dict[str, Any] = {
        "updated_at": _now_iso(),
        "last_sicon_sync_at": _now_iso(),
        "sicon_sync_source": source,
    }
    sicon_id = e.get("SiSMCaseId") or e.get("ServiceCallID") or e.get("Id")
    if sicon_id:
        fields["sicon_case_id"] = sicon_id
    if e.get("CaseNumber"):
        fields["sicon_case_number"] = e["CaseNumber"]
    if e.get("Description") or e.get("Summary"):
        fields["title"] = (e.get("Description") or e.get("Summary") or "")[:200]
    if e.get("Notes"):
        fields["description"] = e["Notes"]
    if mapped_status:
        fields["status"] = mapped_status
    if priority:
        fields["priority"] = priority
    if e.get("ScheduledDateTime"):
        fields["scheduled_at"] = e["ScheduledDateTime"]
    if e.get("EstimatedMinutes"):
        fields["estimated_minutes"] = e["EstimatedMinutes"]
    sub_loc = e.get("SubLocation") or {}
    if sub_loc.get("Description"):
        fields["site_name"] = sub_loc["Description"]
    if e.get("ContactName"):
        fields["customer_name"] = e["ContactName"]
    if e.get("ContactEmail"):
        fields["customer_email"] = e["ContactEmail"]
    if e.get("ContactPhone") or e.get("ContactPhoneNumber"):
        fields["customer_phone"] = e.get("ContactPhone") or e.get("ContactPhoneNumber")
    if e.get("EquipmentSerials"):
        fields["equipment_serials"] = e["EquipmentSerials"]
    if e.get("AssignedToSageUserID") or e.get("AssignedToSageUser"):
        fields["sicon_case_admin_id"] = e.get("AssignedToSageUserID")
        fields["sicon_case_admin_name"] = e.get("AssignedToSageUser") or ""

    if engineer:
        fields["assigned_engineer_id"] = engineer["id"]
        fields["assigned_engineer_name"] = engineer.get("full_name") or engineer.get("email") or ""
        # Sicon scheduled it to someone — make sure the case is at least
        # `assigned` so it shows on the engineer's job list immediately.
        effective_status = mapped_status or (existing or {}).get("status") or "new"
        if effective_status in ("new", "triaged"):
            fields["status"] = "assigned"

    created = False
    if existing:
        await db.svc_cases.update_one({"id": existing["id"]}, {"$set": fields})
        case = await db.svc_cases.find_one({"id": existing["id"]}, {"_id": 0})
    else:
        created = True
        from routes.svc.cases import compute_sla_targets, next_reference
        reference = (e.get("CallReference") or "").strip() or await next_reference(organization_id)
        case = {
            "id": (e.get("OurReference") or "").strip() or str(uuid.uuid4()),
            "organization_id": organization_id,
            "reference": reference,
            "title": fields.get("title") or f"Sicon case {reference}",
            "description": fields.get("description") or "",
            "status": fields.get("status") or "new",
            "priority": fields.get("priority") or "p3",
            "source": "sicon",
            "cover_type": e.get("CallTypeID") or "contract",
            "case_type": e.get("JobTypeID") or "repair",
            "created_at": e.get("LoggedDateTime") or _now_iso(),
            "logged_by_name": e.get("LoggedByUserName") or "Sicon Service Desk",
            **{k: v for k, v in fields.items()},
        }
        case.update(await compute_sla_targets(
            organization_id=organization_id,
            priority=case.get("priority", "p3"),
            cover_type=case.get("cover_type") or "",
        ))
        await db.svc_cases.insert_one(dict(case))
        case.pop("_id", None)

    embedded = e.get("Appointments") or e.get("appointments") or []
    if embedded:
        from utils.sicon_appointments import merge_sicon_appointment
        for appt in embedded:
            if isinstance(appt, dict):
                appt.setdefault("SiSMCaseID", sicon_id)
                case = await merge_sicon_appointment(organization_id, appt) or case

    await append_event(
        case_id=case["id"],
        organization_id=organization_id,
        event_type="sicon_sync",
        actor=SICON_ACTOR,
        body=(
            f"Synced from Sicon ({'created' if created else 'updated'})"
            + (f" · assigned to {fields.get('assigned_engineer_name')}" if engineer else "")
            + (f" · status {fields['status']}" if fields.get("status") else "")
        ),
        extra={"source": source, "sicon_case_id": sicon_id},
    )
    return {"case": case, "created": created}


async def _stash_inbox(organization_id: str, payload: dict, *, case_id: str,
                       created: bool, source: str) -> None:
    """Raw audit copy of everything we ingested (powers the health card)."""
    e = _entity(payload)
    key = str(e.get("SiSMCaseId") or e.get("CallReference") or e.get("OurReference") or uuid.uuid4())
    await db[INBOX].update_one(
        {"organization_id": organization_id, "sicon_key": key},
        {"$set": {
            "organization_id": organization_id,
            "sicon_key": key,
            "payload": payload,
            "case_id": case_id,
            "created_case": created,
            "merged": True,
            "source": source,
            "polled_at": datetime.now(timezone.utc),
        },
         "$setOnInsert": {"id": str(uuid.uuid4()), "first_seen_at": _now_iso()},
         "$inc": {"times_seen": 1}},
        upsert=True,
    )


# ─────────────────────────────────────────────────────────────────
# Polling
# ─────────────────────────────────────────────────────────────────

async def poll_org(organization_id: str) -> dict:
    """One inbound poll for a single organisation. Returns counters."""
    counts = {"fetched": 0, "created": 0, "updated": 0, "errors": 0, "skipped_no_config": 0}
    config = await get_sicon_config(organization_id)
    if not config or not config.get("enabled"):
        counts["skipped_no_config"] = 1
        return counts
    client = await get_sicon_client(organization_id)
    if client is None:
        counts["skipped_no_config"] = 1
        return counts

    since = config.get("last_inbound_poll_at") or (
        datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        res = await client.list_cases_updated_since(since)
    except Exception as e:
        logger.warning("sicon inbound poll failed for %s: %s", organization_id, e)
        counts["errors"] += 1
        await log_sicon_event(
            organization_id=organization_id, action="inbound/poll",
            details=f"poll failed: {e}", success=False, user_id="worker")
        return counts

    items = res.get("entities") or res.get("Items") or res.get("items") or []
    if isinstance(res, list):
        items = res
    for item in items:
        counts["fetched"] += 1
        try:
            merged = await merge_sicon_case(organization_id, item, source="sicon_poll")
            counts["created" if merged["created"] else "updated"] += 1
            await _stash_inbox(organization_id, item, case_id=merged["case"]["id"],
                               created=merged["created"], source="sicon_poll")
            await _pull_appointments(client, organization_id, merged["case"])
        except Exception:
            logger.exception("sicon inbound merge failed for %s", organization_id)
            counts["errors"] += 1

    await db.sicon_config.update_one(
        {"organization_id": organization_id},
        {"$set": {"last_inbound_poll_at": _now_iso(), "last_inbound_counts": counts}},
    )
    await log_sicon_event(
        organization_id=organization_id, action="inbound/poll",
        details=f"fetched={counts['fetched']} created={counts['created']} updated={counts['updated']}",
        success=counts["errors"] == 0, user_id="worker")
    return counts


async def _pull_appointments(client, organization_id: str, case: dict) -> None:
    """Read-only: refresh the case's appointments so engineers follow Sicon."""
    sicon_id = case.get("sicon_case_id")
    if not sicon_id:
        return
    from utils.sicon_appointments import merge_sicon_appointment
    try:
        res = await client.get_appointments_for_case(sicon_id)
    except Exception as exc:
        logger.info("sicon appointments pull skipped for case %s: %s", sicon_id, exc)
        return
    rows = res if isinstance(res, list) else (res.get("entities") or res.get("Items") or res.get("items") or [])
    for row in rows:
        r = row.get("entity", row) if isinstance(row, dict) else {}
        case_ref = r.get("SiSMCaseID") or r.get("SiSMCaseId") or r.get("sismcaseid")
        if str(case_ref) == str(sicon_id):
            await merge_sicon_appointment(organization_id, row)


async def tick() -> dict:
    """Poll every organisation with an enabled Sicon config."""
    totals = {"organizations": 0, "fetched": 0, "created": 0, "updated": 0,
              "errors": 0, "skipped_no_config": 0}
    async for cfg in db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1}):
        totals["organizations"] += 1
        counts = await poll_org(cfg["organization_id"])
        for k in ("fetched", "created", "updated", "errors", "skipped_no_config"):
            totals[k] += counts.get(k, 0)
    return totals


async def run_loop(*, interval_seconds: float = 60.0) -> None:
    """Background loop — started from server.py behind SICON_AUTOSTART_WORKER."""
    logger.info("sicon inbound worker loop starting (interval=%ss)", interval_seconds)
    while True:
        try:
            await tick()
        except Exception:
            logger.exception("sicon inbound loop tick failed")
        await asyncio.sleep(interval_seconds)


__all__ = [
    "merge_sicon_case", "resolve_engineer", "poll_org", "tick", "run_loop",
    "REVERSE_STATUS", "REVERSE_PRIORITY",
]
