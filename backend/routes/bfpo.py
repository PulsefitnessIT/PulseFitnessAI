"""
Pulse Fitness — MOD / BFPO Engineer Portal API.

A role-scoped experience layered on top of the shared service-case engine
(`db.svc_cases` + `utils.svc_state`). It does NOT create a duplicate job
store: BFPO jobs ARE svc_cases, tagged with territory/site/country and a
`bfpo=True` marker, worked by engineers and tracked by MOD staff.

Roles (stored on the user doc as `bfpo_role`):
  • engineer  — sees only their territory's sites & jobs; does the work.
  • lead      — everything an engineer can do + territory-wide visibility.
  • staff     — UK MOD service staff; global oversight + allocation.

Server-side scoping is enforced on every read/write so an engineer can
never reach another territory's job by changing an id.
"""
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import os
import uuid
import secrets
import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response

from utils.database import db
from utils.auth import get_current_user, hash_password
from utils.svc_state import (
    transition as state_transition,
    append_event,
    OPEN_STATES, ASSIGNED, ON_SITE, PAUSED_PARTS, AWAITING_SIGN_OFF, CLOSED, NEW,
)
from routes.svc.cases import next_reference, compute_sla_targets

logger = logging.getLogger(__name__)

BFPO_ORG_ID = "bfpo-mod-org"

# Two-way directory sync: engineers invited from the MOD Operations portal are
# linked to this auto "in-house" provider so they also surface in Master Admin →
# External Service Providers (mirrors provider-provisioned engineers).
MOD_ESTATE_ID = "uk-mod"
INHOUSE_SUPPLIER_ID = "pulse-inhouse-mod"
INHOUSE_PROVIDER_NAME = "Pulse Fitness (in-house)"

router = APIRouter(prefix="/bfpo", tags=["MOD · BFPO Engineer Portal"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_inhouse_supplier() -> str:
    """Get-or-create the in-house provider company in the external-provider
    directory so MOD-Operations-invited engineers appear in Master Admin."""
    existing = await db.mod_estate_suppliers.find_one({"id": INHOUSE_SUPPLIER_ID}, {"_id": 0, "id": 1})
    if not existing:
        await db.mod_estate_suppliers.insert_one({
            "id": INHOUSE_SUPPLIER_ID, "mod_estate_id": MOD_ESTATE_ID,
            "name": INHOUSE_PROVIDER_NAME, "contact_name": "", "email": "", "phone": "",
            "countries": [], "regions": [], "manufacturer_keywords": [],
            "notes": "Pulse Fitness in-house MOD/BFPO engineers (invited from MOD Operations).",
            "is_inhouse": True, "created_at": _now(),
        })
    return INHOUSE_SUPPLIER_ID


def _today() -> str:
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────
# Identity + scoping
# ─────────────────────────────────────────────────────────────────

def _role(user: dict) -> str:
    r = (user.get("bfpo_role") or "").lower()
    if r in ("engineer", "lead", "staff"):
        return r
    # Pulse Fitness staff granted the MOD Operations module (platform admins
    # always qualify) get the staff operations view even without a bfpo_role.
    from utils.module_access import has_mod_operations
    if has_mod_operations(user):
        return "staff"
    return ""


async def _require_bfpo(user=Depends(get_current_user)) -> dict:
    role = _role(user)
    if not role:
        raise HTTPException(403, "Not a MOD / BFPO portal user")
    return user


async def _require_staff(user=Depends(_require_bfpo)) -> dict:
    if _role(user) != "staff":
        raise HTTPException(403, "MOD service staff access required")
    from utils.module_access import has_mod_operations
    if not has_mod_operations(user):
        raise HTTPException(403, "Requires the Pulse Fitness MOD Operations module")
    return user


def _of() -> dict:
    return {"organization_id": BFPO_ORG_ID, "bfpo": True}


async def _engineer_scope(user: dict) -> dict:
    """Return {'territory_ids', 'active_site_ids', 'all_site_ids'} the caller
    may see. Leads/staff see everything (empty => unrestricted)."""
    role = _role(user)
    if role in ("lead", "staff"):
        return {"unrestricted": True, "territory_ids": list(user.get("bfpo_territory_ids") or []),
                "active_site_ids": [], "all_site_ids": []}
    terr = list(user.get("bfpo_territory_ids") or [])
    # Permanently-allocated sites (set by staff when the engineer is set up)
    # are always in scope, distinct from the time-boxed visiting-access grants.
    assigned = list(user.get("bfpo_site_ids") or [])
    active_sites: set[str] = set(assigned)
    all_sites: set[str] = set(assigned)
    today = _today()
    async for g in db.bfpo_visiting_access.find(
        {"organization_id": BFPO_ORG_ID, "engineer_id": user["id"]}, {"_id": 0},
    ):
        sid = g.get("site_id")
        if sid:
            all_sites.add(sid)
            if (g.get("from_date") or "") <= today <= (g.get("to_date") or "9999"):
                active_sites.add(sid)
    return {"unrestricted": False, "territory_ids": terr,
            "active_site_ids": list(active_sites), "all_site_ids": list(all_sites)}


MOD_ORG_TYPES = ("mod_site", "mod_branch", "mod_org")
_MOD_IDS_CACHE: dict = {"at": 0.0, "ids": []}


async def _mod_org_ids() -> list:
    """Ids of every MOD tenant org (sites/branches/root) — cached 60s."""
    import time
    if time.time() - _MOD_IDS_CACHE["at"] > 60:
        _MOD_IDS_CACHE["ids"] = [o["id"] async for o in db.organizations.find(
            {"account_type": {"$in": list(MOD_ORG_TYPES)}}, {"_id": 0, "id": 1})]
        _MOD_IDS_CACHE["at"] = time.time()
    return _MOD_IDS_CACHE["ids"]


async def _ops_org_filter() -> dict:
    """Cases MOD Operations sees: BFPO jobs + every MOD tenant's own service-desk cases."""
    return {"organization_id": {"$in": [BFPO_ORG_ID, *(await _mod_org_ids())]}}


async def _case_org(case_id: str) -> str:
    c = await db.svc_cases.find_one({"id": case_id}, {"_id": 0, "organization_id": 1})
    return (c or {}).get("organization_id") or BFPO_ORG_ID


async def _scoped_case_query(user: dict, *, read: bool = True) -> dict:
    """Base Mongo query restricting cases to what the caller may see."""
    q = await _ops_org_filter()
    scope = await _engineer_scope(user)
    if scope["unrestricted"]:
        return q
    ors = [{"assigned_engineer_id": user["id"]}]
    if scope["territory_ids"]:
        ors.append({"territory_id": {"$in": scope["territory_ids"]}})
    site_ids = scope["all_site_ids"] if read else scope["active_site_ids"]
    if site_ids:
        ors.append({"site_id": {"$in": site_ids}})
        ors.append({"organization_id": {"$in": site_ids}})  # MOD site orgs
    q["$or"] = ors
    return q


async def _get_scoped_case(user: dict, case_id: str, *, read: bool = True) -> dict:
    q = await _scoped_case_query(user, read=read)
    q["id"] = case_id
    case = await db.svc_cases.find_one(q, {"_id": 0})
    if not case:
        raise HTTPException(404, "Job not found")
    return case


# ─────────────────────────────────────────────────────────────────
# Engineer — home + jobs
# ─────────────────────────────────────────────────────────────────

_TERMINAL = ["closed", "invoiced", "repaired", "awaiting_sign_off", "rejected"]


async def _kpis(base_q: dict) -> dict:
    open_q = {**base_q, "status": {"$in": list(OPEN_STATES)}}
    today = _today()
    urgent = {**open_q, "$and": [{"$or": [{"priority": "p1"}, {"safety_critical": True}]}]}
    return {
        "open": await db.svc_cases.count_documents(open_q),
        "urgent": await db.svc_cases.count_documents(urgent),
        "waiting_parts": await db.svc_cases.count_documents({**base_q, "status": PAUSED_PARTS}),
        "return_visit": await db.svc_cases.count_documents({**base_q, "return_visit": True, "status": {"$in": list(OPEN_STATES)}}),
        "overdue": await db.svc_cases.count_documents({
            **open_q, "sla_resolve_at": {"$lt": _now(), "$ne": None},
        }),
    }


@router.get("/me")
async def bfpo_me(user=Depends(_require_bfpo)):
    role = _role(user)
    base_q = await _scoped_case_query(user)
    terr_ids = list(user.get("bfpo_territory_ids") or [])
    territories = []
    if terr_ids:
        territories = await db.bfpo_territories.find(
            {"organization_id": BFPO_ORG_ID, "id": {"$in": terr_ids}}, {"_id": 0},
        ).to_list(50)
    return {
        "user": {"id": user["id"], "name": user.get("full_name") or user.get("email"),
                 "email": user.get("email"), "role": role},
        "territories": territories,
        "kpis": await _kpis(base_q),
    }


_MOD_PRIORITY_MAP = {"urgent": "p1", "high": "p2", "medium": "p3", "low": "p4"}


async def _bridge_mod_fault_to_bfpo(issue: dict) -> Optional[str]:
    """Mirror a MOD fault (db.issues) into a BFPO job (svc_cases under
    BFPO_ORG_ID) so it surfaces in the MOD Operations dashboard AND to the
    site's engineers (unassigned). Idempotent — returns the linked case id."""
    if not issue:
        return None
    if issue.get("bfpo_case_id"):
        return issue["bfpo_case_id"]
    case_id = str(uuid.uuid4())
    claimed = await db.issues.find_one_and_update(
        {"id": issue["id"], "$or": [{"bfpo_case_id": {"$exists": False}}, {"bfpo_case_id": None}, {"bfpo_case_id": ""}]},
        {"$set": {"bfpo_case_id": case_id}})
    if not claimed:  # another request bridged it first
        return (await db.issues.find_one({"id": issue["id"]}, {"_id": 0, "bfpo_case_id": 1}) or {}).get("bfpo_case_id")
    site_id = issue.get("mod_site_id") or issue.get("organization_id")
    org = await db.organizations.find_one(
        {"id": site_id},
        {"_id": 0, "name": 1, "country": 1, "mod_branch": 1,
         "territory_id": 1, "territory_name": 1}) or {}
    equip = {}
    if issue.get("equipment_id"):
        equip = await db.equipment.find_one(
            {"id": issue["equipment_id"]},
            {"_id": 0, "name": 1, "equipment_type": 1, "serial_number": 1}) or {}
    pr = str(issue.get("priority") or issue.get("severity") or "medium").lower()
    priority = _MOD_PRIORITY_MAP.get(pr, "p3")
    safety = pr in ("urgent", "high") or issue.get("safe_in_service") is False
    branch = (org.get("mod_branch") or "").upper()
    now = datetime.now(timezone.utc).isoformat()
    case = {
        "id": case_id, "organization_id": BFPO_ORG_ID,
        "reference": issue.get("mod_ticket_ref") or f"MOD-{case_id[:6].upper()}",
        "title": f"{(issue.get('fault_type_mod') or 'Fault').replace('_', ' ').title()} — "
                 f"{equip.get('name') or issue.get('machine_type') or 'Equipment'}",
        "description": issue.get("issue_description") or "",
        "status": _ISSUE_TO_CASE_STATUS.get(issue.get("status") or "open", NEW),
        "case_type": "fault", "priority": priority, "bfpo": True,
        "asset_id": issue.get("equipment_id"),
        "reporter_name": issue.get("reporter_name") or issue.get("reported_by_name") or issue.get("reported_by"),
        "reporter_email": issue.get("reporter_email"), "reporter_phone": issue.get("reporter_phone"),
        "classification_flags": issue.get("classification_flags") or [],
        "photos_count": len(issue.get("attachment_urls") or issue.get("attachments") or issue.get("photos") or []),
        "safety_critical": bool(safety),
        "site_id": site_id, "site_name": org.get("name") or "MOD Site",
        "country": org.get("country") or "United Kingdom",
        "territory_id": org.get("territory_id"),
        "territory_name": org.get("territory_name") or branch or "MOD",
        "asset_name": equip.get("name") or issue.get("machine_type") or "",
        "asset_serial": equip.get("serial_number") or issue.get("serial_number") or "",
        "fault_code": issue.get("fault_type_mod") or "",
        "customer_name": org.get("name") or "MOD Site",
        "source": "mod_fault", "mod_issue_id": issue.get("id"),
        "mod_ticket_ref": issue.get("mod_ticket_ref"),
        "assigned_engineer_id": None,
        "created_at": issue.get("created_at") or now, "updated_at": now,
    }
    if case["status"] == CLOSED:
        case["closed_at"] = issue.get("resolved_at") or issue.get("closed_at") or now
        case["resolution_notes"] = issue.get("resolution_notes") or "Resolved at site level"
    try:
        await db.svc_cases.insert_one(case)
    except Exception:
        await db.issues.update_one({"id": issue["id"]}, {"$set": {"bfpo_case_id": None}})
        raise
    reporter = case.get("reporter_name") or "the site"
    await append_event(case_id=case_id, organization_id=BFPO_ORG_ID, event_type="intake",
                       actor={"id": "", "full_name": reporter},
                       body=f"Fault logged by {reporter} at {case['site_name']}")
    if case["status"] != CLOSED:
        from utils.esp_engineer import auto_allocate_sole_engineer
        try:
            await auto_allocate_sole_engineer(case)
        except Exception as exc:  # noqa: BLE001 — never block fault intake
            logger.warning("ESP auto-allocate failed for %s: %s", case_id, exc)
    return case_id


_ISSUE_TO_CASE_STATUS = {"open": NEW, "in_progress": "triaged", "resolved": CLOSED, "closed": CLOSED}


async def _ensure_mod_faults_bridged(limit: int = 2000) -> int:
    """Idempotently mirror every MOD site fault (any intake path — MOD wizard,
    Log-a-fault, QR, ASER…) into MOD Operations, and close unworked Ops jobs
    the site has since resolved."""
    mod_ids = await _mod_org_ids()
    own_desk = set(await db.svc_cases.distinct(
        "source_meta.issue_id", {"organization_id": {"$in": mod_ids}, "source_meta.issue_id": {"$nin": [None, ""]}}))
    n = 0
    cursor = db.issues.find(
        {"$and": [
            {"$or": [{"mod_site_id": {"$nin": [None, ""]}}, {"organization_id": {"$in": mod_ids}}]},
            {"$or": [{"bfpo_case_id": {"$exists": False}}, {"bfpo_case_id": None}, {"bfpo_case_id": ""}]},
            # already worked by that MOD org's own service desk → visible via _ops_org_filter
            {"$or": [{"linked_case_id": {"$exists": False}}, {"linked_case_id": None}, {"linked_case_id": ""}]},
        ]},
        {"_id": 0}).limit(limit)
    async for issue in cursor:
        if issue["id"] in own_desk:
            continue
        if await _bridge_mod_fault_to_bfpo(issue):
            n += 1
    # Site resolved it before anyone picked it up → close the Ops job.
    async for issue in db.issues.find(
            {"bfpo_case_id": {"$nin": [None, ""]}, "status": {"$in": ["resolved", "closed"]},
             "bfpo_closed_synced": {"$ne": True}}, {"_id": 0, "id": 1, "bfpo_case_id": 1, "resolved_at": 1}):
        res = await db.svc_cases.update_one(
            {"id": issue["bfpo_case_id"], "status": {"$in": [NEW, "triaged"]}, "assigned_engineer_id": None},
            {"$set": {"status": CLOSED, "closed_at": issue.get("resolved_at") or _now(),
                      "resolution_notes": "Resolved by the site", "updated_at": _now()}})
        if res.modified_count:
            await append_event(case_id=issue["bfpo_case_id"], organization_id=BFPO_ORG_ID,
                               event_type="note", actor={"id": "", "full_name": "MOD site"},
                               body="Closed — the site marked this fault resolved before an engineer was allocated")
        await db.issues.update_one({"id": issue["id"]}, {"$set": {"bfpo_closed_synced": True}})
    return n


_BRIDGE_STATE: dict = {"at": 0.0}
_BRIDGE_LOCK = asyncio.Lock()


async def _safe_bridge() -> None:
    """Bridge on read, throttled to once every 30s per process."""
    import time
    if time.time() - _BRIDGE_STATE["at"] < 30 or _BRIDGE_LOCK.locked():
        return
    async with _BRIDGE_LOCK:
        _BRIDGE_STATE["at"] = time.time()
        try:
            await _ensure_mod_faults_bridged()
        except Exception as e:
            logger.warning("MOD fault bridge failed: %s", e)


async def backfill_mod_bridge() -> int:
    """Startup: flag older bridged jobs so engineers can see them, then bridge."""
    await db.svc_cases.update_many({"source": "mod_fault", "bfpo": {"$ne": True}}, {"$set": {"bfpo": True}})
    async for a in db.bfpo_alert_acks.find({"user_key": {"$exists": False}}, {"_id": 1, "user_id": 1}):
        u = await db.users.find_one({"id": a.get("user_id")}, {"_id": 0, "email": 1})
        await db.bfpo_alert_acks.update_one({"_id": a["_id"]}, {"$set": {"user_key": ((u or {}).get("email") or "").lower() or a.get("user_id")}})
    try:
        await db.svc_cases.create_index(
            "mod_issue_id", unique=True, name="uniq_mod_issue_id",
            partialFilterExpression={"mod_issue_id": {"$type": "string"}})
    except Exception as e:
        logger.warning("mod_issue_id unique index not created: %s", e)
    return await _ensure_mod_faults_bridged(limit=10000)



_FILTER_MAP = {
    "all_open": {"status": {"$in": list(OPEN_STATES)}},
    "new": {"status": {"$in": [NEW, "triaged", ASSIGNED]}},
    "in_progress": {"status": {"$in": ["en_route", ON_SITE]}},
    "waiting_parts": {"status": PAUSED_PARTS},
    "return_visit": {"return_visit": True, "status": {"$in": list(OPEN_STATES)}},
    "completed": {"status": {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]}},
}

_JOB_PROJECTION = {
    "_id": 0, "id": 1, "reference": 1, "title": 1, "description": 1, "priority": 1,
    "status": 1, "safety_critical": 1, "site_name": 1, "site_id": 1, "territory_name": 1,
    "country": 1, "asset_name": 1, "fault_code": 1, "scheduled_at": 1, "sla_resolve_at": 1,
    "assigned_engineer_id": 1, "assigned_engineer_name": 1, "return_visit": 1,
    "waiting_reason": 1, "created_at": 1, "closed_at": 1, "customer_name": 1,
    "source": 1, "organization_id": 1, "reporter_name": 1, "classification_flags": 1,
}


@router.get("/jobs")
async def bfpo_jobs(when: str = Query("all_open"), user=Depends(_require_bfpo)):
    await _safe_bridge()
    base_q = await _scoped_case_query(user)
    q = {**base_q, **_FILTER_MAP.get(when, _FILTER_MAP["all_open"])}
    sort = [("closed_at", -1)] if when == "completed" else [("safety_critical", -1), ("priority", 1), ("sla_resolve_at", 1)]
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort(sort).to_list(200)
    return {"jobs": rows, "count": len(rows)}


@router.post("/faults/sync")
async def bfpo_sync_mod_faults(user=Depends(_require_bfpo)):
    """One-tap backfill: bridge any open MOD faults into BFPO jobs so they
    appear in the MOD Operations dashboard and engineer lists."""
    n = await _ensure_mod_faults_bridged()
    return {"success": True, "bridged": n}


@router.get("/jobs/{case_id}")
async def bfpo_job_detail(case_id: str, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    events = await db.svc_case_events.find(
        {"case_id": case_id}, {"_id": 0},
    ).sort("at", -1).limit(80).to_list(80)
    photos = await db.svc_engineer_photos.find(
        {"case_id": case_id}, {"_id": 0},
    ).sort("taken_at", -1).limit(40).to_list(40)
    site = None
    if case.get("site_id"):
        site = await db.sites.find_one(
            {"id": case["site_id"], "organization_id": BFPO_ORG_ID}, {"_id": 0},
        ) or await db.organizations.find_one(
            {"id": case["site_id"], "account_type": {"$in": list(MOD_ORG_TYPES)}},
            {"_id": 0, "id": 1, "name": 1, "country": 1, "mod_branch": 1, "address": 1,
             "city": 1, "postcode": 1, "contact_email": 1, "contact_phone": 1},
        )
    equipment = []
    eq_ids = list(case.get("equipment_ids") or [])
    if case.get("asset_id"):
        eq_ids.append(case["asset_id"])
    if eq_ids:
        equipment = await db.equipment.find(
            {"id": {"$in": eq_ids}}, {"_id": 0},
        ).to_list(50)
    # asset history — prior closed jobs on the same asset
    asset_history = []
    if case.get("asset_id"):
        asset_history = await db.svc_cases.find(
            {"organization_id": case.get("organization_id") or BFPO_ORG_ID, "asset_id": case["asset_id"],
             "id": {"$ne": case_id}, "status": {"$in": ["closed", "invoiced", "repaired"]}},
            {"_id": 0, "id": 1, "reference": 1, "title": 1, "closed_at": 1, "resolution_notes": 1},
        ).sort("closed_at", -1).limit(5).to_list(5)
    signature = await db.svc_signatures.find_one(
        {"case_id": case_id}, {"_id": 0}, sort=[("signed_at", -1)],
    )
    mod_issue = None
    if case.get("mod_issue_id"):
        mod_issue = await db.issues.find_one(
            {"id": case["mod_issue_id"]},
            {"_id": 0, "id": 1, "status": 1, "issue_description": 1, "reporter_name": 1,
             "reporter_email": 1, "reporter_phone": 1, "reported_by_name": 1, "classification_flags": 1,
             "safe_in_service": 1, "photos": 1, "images": 1, "created_at": 1, "mod_ticket_ref": 1,
             "comments": 1, "updates": 1})
    return {**case, "events": events, "photos": photos, "site": site,
            "equipment": equipment, "asset_history": asset_history,
            "signature": signature, "viewer_role": _role(user), "mod_issue": mod_issue}


# ─────────────────────────────────────────────────────────────────
# Engineer — guided workflow
# ─────────────────────────────────────────────────────────────────

async def _op_update(case: dict, user: dict, update_type: str, body: str, extra: dict | None = None):
    await append_event(
        case_id=case["id"], organization_id=case.get("organization_id") or BFPO_ORG_ID,
        event_type="operational_update", actor=user, body=body,
        extra={"update_type": update_type, **(extra or {})},
    )


@router.post("/jobs/{case_id}/accept")
async def bfpo_accept(case_id: str, data: dict = Body(default={}), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    await db.svc_cases.update_one(
        {"id": case_id},
        {"$set": {"assigned_engineer_id": user["id"],
                  "assigned_engineer_name": user.get("full_name") or user.get("email"),
                  "updated_at": _now()}},
    )
    if case.get("status") in (NEW, "triaged"):
        try:
            await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                                   target_state=ASSIGNED, actor=user, reason="engineer accepted job")
        except ValueError:
            pass
    await _op_update(case, user, "acknowledged", "Engineer accepted the job")
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/arrive")
async def bfpo_arrive(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    safe = bool(data.get("safe"))
    notes = (data.get("notes") or "").strip()
    updates = {"safety_confirmed": safe, "safety_notes": notes, "arrived_at": _now(), "updated_at": _now()}
    if not safe:
        updates["safety_critical"] = True
    try:
        await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                               target_state=ON_SITE, actor=user, reason="engineer arrived on site")
    except ValueError:
        if case.get("status") != ON_SITE:
            raise HTTPException(409, "Accept the job before marking yourself on site")
    if case.get("status") == ON_SITE and case.get("arrived_at"):
        return await bfpo_job_detail(case_id, user)  # already on site (e.g. offline replay) — no duplicate entry
    await db.svc_cases.update_one({"id": case_id}, {"$set": updates})
    await _op_update(case, user, "arrived",
                     "Engineer arrived on site — " + ("safe to work" if safe else "SAFETY CONCERN raised"),
                     {"safe": safe, "notes": notes})
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/diagnosis")
async def bfpo_diagnosis(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    text = (data.get("diagnosis") or "").strip()
    if not text:
        raise HTTPException(400, "diagnosis required")
    await db.svc_cases.update_one({"id": case_id},
                                  {"$set": {"diagnosis": text, "updated_at": _now()}})
    await append_event(case_id=case_id, organization_id=await _case_org(case_id), event_type="note",
                       actor=user, body=text, extra={"kind": "diagnosis", "visibility": "internal"})
    return {"ok": True}


@router.post("/jobs/{case_id}/parts")
async def bfpo_parts(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Log a part needed — never requires a Pulse part number.
    Body: {name, description?, part_number?, photo_url?, equipment_id?}"""
    case = await _get_scoped_case(user, case_id, read=False)
    name = (data.get("name") or data.get("description") or "").strip()
    if not name and not data.get("photo_url"):
        raise HTTPException(400, "Describe the part or attach a photo")
    part = {
        "id": str(uuid.uuid4()), "organization_id": case.get("organization_id") or BFPO_ORG_ID, "case_id": case_id,
        "case_reference": case.get("reference"), "engineer_id": user["id"],
        "name": name or "Part (see photo)", "description": (data.get("description") or "").strip(),
        "part_number": (data.get("part_number") or "").strip(),
        "photo_url": data.get("photo_url") or "", "equipment_id": data.get("equipment_id") or "",
        "status": "pending", "created_at": _now(),
    }
    await db.bfpo_parts_requests.insert_one(part)
    await db.svc_cases.update_one({"id": case_id},
                                  {"$set": {"waiting_reason": "Parts required", "updated_at": _now()}})
    try:
        await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                               target_state=PAUSED_PARTS, actor=user, reason="parts required")
    except ValueError:
        pass
    await _op_update(case, user, "parts_required", f"Parts required: {part['name']}",
                     {"part_id": part["id"], "part_name": part["name"]})
    part.pop("_id", None)
    return {"ok": True, "part": part}


@router.post("/jobs/{case_id}/outcome")
async def bfpo_outcome(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Record a non-repair outcome that keeps the job open.
    Body: {outcome: return_visit|unable_access|equipment_unsafe, reason, details?}"""
    case = await _get_scoped_case(user, case_id, read=False)
    outcome = (data.get("outcome") or "").lower()
    reason = (data.get("reason") or "").strip()
    details = (data.get("details") or "").strip()
    label = {"return_visit": "Return visit needed", "unable_access": "Unable to access",
             "equipment_unsafe": "Equipment unsafe"}.get(outcome)
    if not label:
        raise HTTPException(400, "outcome must be return_visit | unable_access | equipment_unsafe")
    updates = {"return_visit": True, "waiting_reason": label,
               "return_reason": reason or label, "updated_at": _now()}
    if outcome == "equipment_unsafe":
        updates["safety_critical"] = True
    await db.svc_cases.update_one({"id": case_id}, {"$set": updates})
    await _op_update(case, user, outcome, f"{label}: {reason or details or '—'}", {"details": details})
    return await bfpo_job_detail(case_id, user)


@router.post("/jobs/{case_id}/report-fault")
async def bfpo_report_fault(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Report an ADDITIONAL fault during a visit → creates a linked case.
    Body: {title, description, equipment_id?, safety_critical?, priority?}"""
    parent = await _get_scoped_case(user, case_id, read=False)
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title required")
    equipment_id = data.get("equipment_id") or ""
    warning = None
    if equipment_id:
        dup = await db.svc_cases.find_one({
            "organization_id": BFPO_ORG_ID, "asset_id": equipment_id,
            "status": {"$in": list(OPEN_STATES)},
        }, {"_id": 0, "id": 1, "reference": 1})
        if dup:
            warning = f"That equipment already has an open job ({dup.get('reference')})"
    priority = (data.get("priority") or "p3").lower()
    if priority not in ("p1", "p2", "p3", "p4"):
        priority = "p3"
    sla = await compute_sla_targets(organization_id=BFPO_ORG_ID, priority=priority)
    reference = await next_reference(BFPO_ORG_ID)
    asset_name = ""
    if equipment_id:
        eq = await db.equipment.find_one({"id": equipment_id, "organization_id": BFPO_ORG_ID},
                                         {"_id": 0, "name": 1, "model": 1, "manufacturer": 1})
        if eq:
            asset_name = f"{eq.get('manufacturer') or ''} {eq.get('model') or eq.get('name') or ''}".strip()
    new_case = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "bfpo": True,
        "reference": reference, "status": NEW, "priority": priority, "case_type": "repair",
        "title": title, "description": (data.get("description") or "").strip(),
        "safety_critical": bool(data.get("safety_critical")),
        "territory_id": parent.get("territory_id"), "territory_name": parent.get("territory_name"),
        "country": parent.get("country"), "site_id": parent.get("site_id"),
        "site_name": parent.get("site_name"), "site_timezone": parent.get("site_timezone"),
        "customer_name": parent.get("customer_name"), "asset_id": equipment_id,
        "asset_name": asset_name, "equipment_ids": [equipment_id] if equipment_id else [],
        "linked_from_case_id": case_id, "linked_from_reference": parent.get("reference"),
        "assigned_engineer_id": "", "assigned_engineer_name": "", "scheduled_at": None,
        "sla_response_at": sla["sla_response_at"], "sla_resolve_at": sla["sla_resolve_at"],
        "source": "engineer_report", "logged_by_id": user["id"],
        "logged_by_name": user.get("full_name") or user.get("email"),
        "closed_at": None, "created_at": _now(), "updated_at": _now(),
    }
    await db.svc_cases.insert_one(new_case)
    await append_event(case_id=new_case["id"], organization_id=BFPO_ORG_ID, event_type="intake",
                       actor=user, body=f"Additional fault reported during visit to {parent.get('reference')}",
                       extra={"linked_from": case_id})
    await _op_update(parent, user, "additional_fault",
                     f"Additional fault logged: {title} ({reference})", {"new_case_id": new_case["id"]})
    new_case.pop("_id", None)
    return {"ok": True, "case": new_case, "warning": warning}


@router.post("/jobs/{case_id}/photos")
async def bfpo_add_photo(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    file_url = data.get("file_url")
    if not file_url:
        raise HTTPException(400, "file_url required")
    photo = {
        "id": str(uuid.uuid4()), "organization_id": case.get("organization_id") or BFPO_ORG_ID, "case_id": case_id,
        "case_reference": case.get("reference"), "file_url": file_url,
        "mime_type": data.get("mime_type") or "image/jpeg", "kind": "photo",
        "caption": (data.get("caption") or "").strip(), "taken_at": _now(),
        "taken_by_id": user["id"], "taken_by_name": user.get("full_name") or user.get("email"),
        "created_at": _now(),
    }
    await db.svc_engineer_photos.insert_one(photo)
    await append_event(case_id=case_id, organization_id=await _case_org(case_id), event_type="photo",
                       actor=user, body=photo["caption"] or "Photo attached", extra={"file_url": file_url})
    photo.pop("_id", None)
    return {"ok": True, "photo": photo}


@router.post("/jobs/{case_id}/signature")
async def bfpo_signature(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Body: {signed_by_name, signed_by_email?, image_data} OR {unavailable: true, reason}"""
    from utils.customer_signoff import build_signoff
    case = await _get_scoped_case(user, case_id, read=False)
    sig = build_signoff(data, case_id=case_id, organization_id=case.get("organization_id") or BFPO_ORG_ID,
                        reference=case.get("reference"), user=user)
    await db.svc_signatures.insert_one(sig)
    await append_event(case_id=case_id, organization_id=await _case_org(case_id), event_type="signature",
                       actor=user, body=("Signature unavailable" if sig.get("unavailable")
                                         else f"Signed by {sig['signed_by_name']}"))
    sig.pop("_id", None)
    return {"ok": True, "signature": sig}


@router.post("/jobs/{case_id}/complete")
async def bfpo_complete(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    """Body: {summary, parts_used?, safe_and_working: bool, photo_urls?[]}"""
    from utils.customer_signoff import require_signoff
    case = await _get_scoped_case(user, case_id, read=False)
    summary = (data.get("summary") or "").strip()
    if not summary:
        raise HTTPException(400, "summary required")
    await require_signoff(case_id=case_id)
    safe_working = bool(data.get("safe_and_working"))
    updates = {
        "resolution_notes": summary, "parts_used": data.get("parts_used") or "",
        "safe_and_working": safe_working, "return_visit": False,
        "waiting_reason": "", "completed_at": _now(), "updated_at": _now(),
    }
    if safe_working:
        updates["safety_critical"] = False
    await db.svc_cases.update_one({"id": case_id}, {"$set": updates})
    # walk state → on_site → closed
    if case.get("status") in (ASSIGNED, "en_route", "triaged", NEW, PAUSED_PARTS):
        try:
            await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                                   target_state=ON_SITE, actor=user, reason="auto: completing job")
        except ValueError:
            pass
    for tgt in (AWAITING_SIGN_OFF, CLOSED):
        try:
            await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                                   target_state=tgt, actor=user, reason=summary[:200])
        except ValueError:
            continue
    await _op_update(case, user, "job_completed", f"Job completed: {summary[:120]}",
                     {"safe_and_working": safe_working})
    updated = await db.svc_cases.find_one({"id": case_id}, {"_id": 0})
    if updated and updated.get("status") in (AWAITING_SIGN_OFF, CLOSED):
        from utils.customer_signoff import spawn
        spawn(_email_signed_job_sheet(case_id))
    return {"ok": True, "case": updated,
            "job_sheet_url": f"/api/bfpo/jobs/{case_id}/job-sheet.pdf"}


async def _email_signed_job_sheet(case_id: str) -> str:
    from utils.customer_signoff import email_signed_pdf, latest_signoff, resolve_site_contact
    try:
        case = await db.svc_cases.find_one({"id": case_id}, {"_id": 0}) or {}
        sig = await latest_signoff(case_id=case_id)
        pdf = await build_mod_service_report(case)
        sent = await email_signed_pdf(
            sig=sig, contact=await resolve_site_contact(case), pdf=pdf,
            filename=f"Service Report - {case.get('reference')}.pdf",
            subject=f"Signed service report · {case.get('reference')} — {case.get('site_name') or 'MOD service'}",
            intro=f"Job <b>{case.get('reference')}</b> has been completed.", organization_id=case.get("organization_id"))
        if sent:
            await db.svc_cases.update_one({"id": case_id}, {"$set": {"service_report_sent_at": _now(), "service_report_sent_to": sent}})
        return sent
    except Exception:
        logger.exception("BFPO signed job sheet email failed")
        return ""


@router.get("/jobs/{case_id}/signoff")
async def bfpo_signoff_info(case_id: str, user=Depends(_require_bfpo)):
    from utils.customer_signoff import latest_signoff, resolve_site_contact
    case = await _get_scoped_case(user, case_id)
    sig = await latest_signoff(case_id=case_id, current_only=True)
    if sig:
        sig.pop("image_data", None)
    return {"site_contact": await resolve_site_contact(case), "signoff": sig, "reopened_at": case.get("reopened_at")}


@router.post("/jobs/{case_id}/update")
async def bfpo_operational_update(case_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id, read=False)
    update_type = (data.get("update_type") or "general").lower()
    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    await _op_update(case, user, update_type, message)
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Engineer — sites, equipment, history
# ─────────────────────────────────────────────────────────────────

async def _visible_site_ids(user: dict) -> Optional[list]:
    scope = await _engineer_scope(user)
    if scope["unrestricted"]:
        return None  # all
    ids = set(scope["all_site_ids"])
    if scope["territory_ids"]:
        async for s in db.sites.find(
            {"organization_id": BFPO_ORG_ID, "territory_id": {"$in": scope["territory_ids"]}},
            {"_id": 0, "id": 1},
        ):
            ids.add(s["id"])
    return list(ids)


@router.get("/sites")
async def bfpo_sites(user=Depends(_require_bfpo)):
    q = {"organization_id": BFPO_ORG_ID}
    ids = await _visible_site_ids(user)
    if ids is not None:
        q["id"] = {"$in": ids}
    sites = await db.sites.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    if ids is not None:
        sites += await db.organizations.find({"account_type": "mod_site", "id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "country": 1, "city": 1, "address": 1, "postcode": 1}).sort("name", 1).to_list(500)
    can_sensitive = _role(user) in ("lead", "staff")
    for s in sites:
        if not can_sensitive:
            s.pop("access_instructions", None)
            s.pop("security_notes", None)
    return {"sites": sites, "count": len(sites)}


@router.get("/sites/{site_id}")
async def bfpo_site_detail(site_id: str, user=Depends(_require_bfpo)):
    ids = await _visible_site_ids(user)
    if ids is not None and site_id not in ids:
        raise HTTPException(404, "Site not found")
    site = await db.sites.find_one({"id": site_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    mod_org = False
    if not site:
        site = await db.organizations.find_one(
            {"id": site_id, "account_type": "mod_site"},
            {"_id": 0, "id": 1, "name": 1, "country": 1, "mod_branch": 1, "address": 1,
             "city": 1, "postcode": 1, "contact_email": 1, "contact_phone": 1})
        mod_org = bool(site)
    if not site:
        raise HTTPException(404, "Site not found")
    eq_q = {"organization_id": site_id} if mod_org else {"organization_id": BFPO_ORG_ID, "site_id": site_id}
    equipment = await db.equipment.find(eq_q, {"_id": 0}).sort("name", 1).to_list(500)
    open_jobs = len(await _open_cases_for_site(site_id, mod_org=mod_org))
    return {"site": site, "equipment": equipment, "open_jobs": open_jobs,
            "sensitive_visible": _role(user) in ("lead", "staff")}


@router.get("/equipment")
async def bfpo_equipment(search: str = Query(""), user=Depends(_require_bfpo)):
    q = {"organization_id": BFPO_ORG_ID}
    ids = await _visible_site_ids(user)
    if ids is not None:
        q = {"$or": [{"organization_id": BFPO_ORG_ID, "site_id": {"$in": ids}}, {"organization_id": {"$in": ids}}]}
    else:
        mod_sites = [o["id"] async for o in db.organizations.find({"account_type": "mod_site"}, {"_id": 0, "id": 1})]
        q = {"organization_id": {"$in": [BFPO_ORG_ID, *mod_sites]}}
    if search:
        from utils.security_plus import safe_regex
        q = {"$and": [q, {"$or": [{"serial_number": safe_regex(search)}, {"model": safe_regex(search)},
                                  {"name": safe_regex(search)}, {"manufacturer": safe_regex(search)}]}]}
    rows = await db.equipment.find(q, {"_id": 0}).sort("name", 1).limit(300).to_list(300)
    return {"equipment": rows, "count": len(rows)}


@router.get("/equipment/{equipment_id}")
async def bfpo_equipment_detail(equipment_id: str, user=Depends(_require_bfpo)):
    ids = await _visible_site_ids(user)
    orgs = [BFPO_ORG_ID, *(await _mod_org_ids())]
    eq = await db.equipment.find_one({"id": equipment_id, "organization_id": {"$in": orgs}}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    if ids is not None and eq.get("site_id") not in ids and eq.get("organization_id") not in ids:
        raise HTTPException(404, "Equipment not found")
    history = await db.svc_cases.find(
        {**(await _ops_org_filter()), "asset_id": equipment_id}, {"_id": 0,
         "id": 1, "reference": 1, "title": 1, "status": 1, "closed_at": 1, "created_at": 1,
         "resolution_notes": 1},
    ).sort("created_at", -1).limit(30).to_list(30)
    return {"equipment": eq, "history": history}


@router.get("/history")
async def bfpo_history(user=Depends(_require_bfpo)):
    q = await _scoped_case_query(user)
    q["status"] = {"$in": ["closed", "invoiced", "repaired", "awaiting_sign_off"]}
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort("closed_at", -1).limit(200).to_list(200)
    return {"jobs": rows, "count": len(rows)}


# ─────────────────────────────────────────────────────────────────
# MOD staff — global oversight
# ─────────────────────────────────────────────────────────────────

def _site_health(stats: dict) -> str:
    if stats.get("unsafe") or stats.get("overdue_urgent"):
        return "critical"
    if stats.get("machines_down", 0) >= 2 or stats.get("waiting_parts") or stats.get("access_problem") or stats.get("overdue"):
        return "attention"
    return "normal"


@router.get("/staff/dashboard")
async def staff_dashboard(user=Depends(_require_staff)):
    await _safe_bridge()
    base = await _ops_org_filter()
    open_q = {**base, "status": {"$in": list(OPEN_STATES)}}
    kpis = {
        "open": await db.svc_cases.count_documents(open_q),
        "urgent": await db.svc_cases.count_documents(
            {**open_q, "$or": [{"priority": "p1"}, {"safety_critical": True}]}),
        "waiting_parts": await db.svc_cases.count_documents({**base, "status": PAUSED_PARTS}),
        "overdue": await db.svc_cases.count_documents(
            {**open_q, "sla_resolve_at": {"$lt": _now(), "$ne": None}}),
    }
    # sites requiring attention
    site_health = await _compute_site_health()
    kpis["sites_attention"] = sum(1 for s in site_health if s["health"] != "normal")
    urgent_list = await db.svc_cases.find(
        {**open_q, "$or": [{"priority": "p1"}, {"safety_critical": True}]}, _JOB_PROJECTION,
    ).sort("sla_resolve_at", 1).limit(20).to_list(20)
    return {"kpis": kpis, "urgent_jobs": urgent_list,
            "attention_sites": [s for s in site_health if s["health"] != "normal"]}


async def _compute_site_health() -> list:
    sites = await db.sites.find({"organization_id": BFPO_ORG_ID}, {"_id": 0}).to_list(1000)
    now = _now()
    out = []
    for s in sites:
        open_cases = await _open_cases_for_site(s["id"])
        stats = {"machines_down": len(open_cases),
                 "unsafe": any(c.get("safety_critical") for c in open_cases),
                 "waiting_parts": any(c.get("status") == PAUSED_PARTS for c in open_cases),
                 "access_problem": any((c.get("waiting_reason") or "").lower().startswith("unable") for c in open_cases),
                 "overdue": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now for c in open_cases),
                 "overdue_urgent": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now
                                       and (c.get("priority") == "p1" or c.get("safety_critical")) for c in open_cases)}
        out.append({"site_id": s["id"], "site_name": s.get("name"),
                    "country": s.get("country"), "territory_id": s.get("territory_id"),
                    "territory_name": s.get("territory_name"),
                    "open_jobs": len(open_cases), "health": _site_health(stats)})

    # Imported MOD estate sites live as their own tenant orgs
    # (db.organizations, account_type='mod_site'), not in db.sites — surface
    # them here grouped by country then service branch (ARMY / RAF / NAVY).
    mod_orgs = await db.organizations.find(
        {"account_type": "mod_site"},
        {"_id": 0, "id": 1, "name": 1, "country": 1, "mod_branch": 1},
    ).to_list(5000)
    for o in mod_orgs:
        open_cases = await _open_cases_for_site(o["id"], mod_org=True)
        branch = (o.get("mod_branch") or "").upper() or "MOD"
        out.append({"site_id": o["id"], "site_name": o.get("name") or "MOD Site",
                    "country": o.get("country") or "United Kingdom",
                    "territory_id": None, "territory_name": branch,
                    "open_jobs": len(open_cases), "health": _site_health(_case_stats(open_cases))})
    return out


async def _open_cases_for_site(site_id: str, *, mod_org: bool = False) -> list:
    """Open jobs for a site — BFPO jobs keyed by site_id, plus (for a MOD tenant
    org) that org's own service-desk cases."""
    ors = [{"organization_id": BFPO_ORG_ID, "site_id": site_id}]
    if mod_org:
        ors.append({"organization_id": site_id})
    return await db.svc_cases.find(
        {"$or": ors, "status": {"$in": list(OPEN_STATES)}},
        {"_id": 0, "priority": 1, "safety_critical": 1, "sla_resolve_at": 1, "status": 1, "waiting_reason": 1},
    ).to_list(500)


def _case_stats(open_cases: list) -> dict:
    now = _now()
    return {"machines_down": len(open_cases),
            "unsafe": any(c.get("safety_critical") for c in open_cases),
            "waiting_parts": any(c.get("status") == PAUSED_PARTS for c in open_cases),
            "access_problem": any((c.get("waiting_reason") or "").lower().startswith("unable") for c in open_cases),
            "overdue": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now for c in open_cases),
            "overdue_urgent": any(c.get("sla_resolve_at") and c["sla_resolve_at"] < now
                                  and (c.get("priority") == "p1" or c.get("safety_critical")) for c in open_cases)}


@router.get("/staff/sites")
async def staff_sites(user=Depends(_require_staff)):
    await _safe_bridge()
    health = await _compute_site_health()
    grouped: dict = {}
    for s in health:
        country = s.get("country") or "Other"
        terr = s.get("territory_name") or "Unassigned"
        grouped.setdefault(country, {}).setdefault(terr, []).append(s)
    tree = [{"country": c,
             "territories": [{"territory_name": t, "sites": sites,
                              "health": ("critical" if any(x["health"] == "critical" for x in sites)
                                         else "attention" if any(x["health"] == "attention" for x in sites)
                                         else "normal")}
                             for t, sites in terrs.items()]}
            for c, terrs in sorted(grouped.items())]
    return {"tree": tree}


@router.get("/staff/jobs")
async def staff_jobs(
    territory: str = Query(""), site: str = Query(""), engineer: str = Query(""),
    status: str = Query(""), priority: str = Query(""), safety: str = Query(""),
    overdue: str = Query(""), user=Depends(_require_staff),
):
    await _safe_bridge()
    q = await _ops_org_filter()
    if territory:
        q["territory_id"] = territory
    if site:
        q["site_id"] = site
    if engineer:
        q["assigned_engineer_id"] = engineer
    if status == "open":
        q["status"] = {"$in": list(OPEN_STATES)}
    elif status:
        q["status"] = status
    if priority:
        q["priority"] = priority
    if safety == "true":
        q["safety_critical"] = True
    if overdue == "true":
        q["sla_resolve_at"] = {"$lt": _now(), "$ne": None}
        q.setdefault("status", {"$in": list(OPEN_STATES)})
    rows = await db.svc_cases.find(q, _JOB_PROJECTION).sort([("priority", 1), ("sla_resolve_at", 1)]).limit(300).to_list(300)
    return {"jobs": rows, "count": len(rows)}


@router.get("/staff/jobs/{case_id}")
async def staff_job_detail(case_id: str, user=Depends(_require_staff)):
    return await bfpo_job_detail(case_id, user)


@router.get("/staff/engineers")
async def staff_engineers(user=Depends(_require_staff)):
    rows = await db.users.find(
        {"organization_id": BFPO_ORG_ID, "bfpo_role": {"$in": ["engineer", "lead"]}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "bfpo_role": 1, "bfpo_territory_ids": 1},
    ).to_list(200)
    return {"engineers": rows}


@router.post("/staff/jobs/{case_id}/allocate")
async def staff_allocate(case_id: str, data: dict = Body(...), user=Depends(_require_staff)):
    case = await db.svc_cases.find_one({"id": case_id, **(await _ops_org_filter())}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Job not found")
    eng_id = data.get("engineer_id")
    eng = await db.users.find_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eng:
        raise HTTPException(404, "Engineer not found")
    handover = (data.get("handover") or "").strip()
    previous = case.get("assigned_engineer_name")
    await db.svc_cases.update_one(
        {"id": case_id},
        {"$set": {"assigned_engineer_id": eng_id,
                  "assigned_engineer_name": eng.get("full_name") or eng.get("email"),
                  "updated_at": _now()}},
    )
    if case.get("status") in (NEW, "triaged"):
        try:
            await state_transition(case_id=case_id, organization_id=await _case_org(case_id),
                                   target_state=ASSIGNED, actor=user, reason="allocated by MOD staff")
        except ValueError:
            pass
    body = f"Allocated to {eng.get('full_name') or eng.get('email')}"
    if previous:
        body = f"Reallocated from {previous} to {eng.get('full_name') or eng.get('email')}"
    await append_event(case_id=case_id, organization_id=await _case_org(case_id), event_type="allocation",
                       actor=user, body=body, extra={"engineer_id": eng_id, "handover": handover})
    if handover:
        await append_event(case_id=case_id, organization_id=await _case_org(case_id), event_type="note",
                           actor=user, body=handover, extra={"kind": "handover"})
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# MOD staff — temporary visiting-engineer access
# ─────────────────────────────────────────────────────────────────

@router.get("/staff/visiting-access")
async def list_visiting_access(user=Depends(_require_staff)):
    rows = await db.bfpo_visiting_access.find({"organization_id": BFPO_ORG_ID}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"grants": rows}


@router.post("/staff/visiting-access")
async def grant_visiting_access(data: dict = Body(...), user=Depends(_require_staff)):
    eng = await db.users.find_one({"id": data.get("engineer_id"), "organization_id": BFPO_ORG_ID}, {"_id": 0})
    site = await db.sites.find_one({"id": data.get("site_id"), "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eng or not site:
        raise HTTPException(404, "Engineer or site not found")
    grant = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID,
        "engineer_id": eng["id"], "engineer_name": eng.get("full_name") or eng.get("email"),
        "site_id": site["id"], "site_name": site.get("name"),
        "territory_id": site.get("territory_id"), "territory_name": site.get("territory_name"),
        "from_date": data.get("from_date") or _today(), "to_date": data.get("to_date") or _today(),
        "granted_by": user.get("full_name") or user.get("email"), "created_at": _now(),
    }
    await db.bfpo_visiting_access.insert_one(grant)
    grant.pop("_id", None)
    return {"ok": True, "grant": grant}


@router.delete("/staff/visiting-access/{grant_id}")
async def revoke_visiting_access(grant_id: str, user=Depends(_require_staff)):
    res = await db.bfpo_visiting_access.delete_one({"id": grant_id, "organization_id": BFPO_ORG_ID})
    if not res.deleted_count:
        raise HTTPException(404, "Grant not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Branded job sheet PDF
# ─────────────────────────────────────────────────────────────────

async def build_mod_service_report(case: dict) -> bytes:
    """MOD jobs use the standard Pulse Service Report (MOD badge in header)."""
    from routes.svc.service_report import _build_report
    pdf, _ = await _build_report(case["id"], {"organization_id": case["organization_id"],
                                              "is_master_admin": True, "id": "system"})
    return pdf


@router.get("/jobs/{case_id}/job-sheet.pdf")
async def bfpo_job_sheet(case_id: str, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    pdf = await build_mod_service_report(case)
    fname = f"Service Report - {case.get('reference')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ─────────────────────────────────────────────────────────────────
# Engineer setup & invitations (staff / master-admin only)
# ─────────────────────────────────────────────────────────────────

def _frontend_url() -> str:
    return (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


def _public_member(u: dict) -> dict:
    return {
        "id": u.get("id"), "full_name": u.get("full_name"), "email": u.get("email"),
        "phone": u.get("phone", ""), "bfpo_role": u.get("bfpo_role"),
        "bfpo_territory_ids": list(u.get("bfpo_territory_ids") or []),
        "bfpo_site_ids": list(u.get("bfpo_site_ids") or []),
        "is_active": u.get("is_active", True),
        "invite_pending": bool(u.get("invite_pending")),
        "must_change_password": bool(u.get("must_change_password")),
        "created_at": u.get("created_at"),
    }


def _gen_temp_password() -> str:
    # Human-typeable temporary password, still hard to guess.
    return "Pulse-" + secrets.token_urlsafe(6)


async def _issue_invite(user_doc: dict) -> str:
    """Create a single-use invite token, email the set-password link, and
    return the absolute URL (so staff can copy it even if email is offline)."""
    token = secrets.token_urlsafe(32)
    await db.bfpo_invites.delete_many({"user_id": user_doc["id"]})
    await db.bfpo_invites.insert_one({
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID,
        "user_id": user_doc["id"], "email": user_doc["email"], "token": token,
        "status": "sent", "created_at": _now(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    })
    url = f"{(os.environ.get('MOD_PORTAL_URL') or _frontend_url()).rstrip('/')}/bfpo/invite/{token}"
    name = user_doc.get("full_name") or "there"
    html = (
        f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto'>"
        f"<h2 style='color:#111'>Set up your Pulse Fitness MOD account</h2>"
        f"<p>Hi {name},</p>"
        f"<p>You've been set up on the Pulse Fitness MOD / BFPO Engineer Portal. "
        f"Click below to choose a password and activate your account.</p>"
        f"<p style='margin:28px 0'><a href='{url}' "
        f"style='background:#0891b2;color:#fff;padding:12px 22px;border-radius:10px;"
        f"text-decoration:none;font-weight:bold'>Set my password</a></p>"
        f"<p style='color:#666;font-size:13px'>This link expires in 7 days. If the button "
        f"doesn't work, paste this into your browser:<br>{url}</p></div>"
    )
    try:
        from utils.email import send_email
        await send_email(to=user_doc["email"],
                         subject="Set up your Pulse Fitness MOD engineer account",
                         html=html, organization_id=BFPO_ORG_ID,
                         kind="bfpo_invite", category="mod")
    except Exception as e:
        logger.warning("BFPO invite email failed for %s: %s", user_doc["email"], e)
    return url


@router.get("/staff/territories")
async def staff_territories(user=Depends(_require_staff)):
    rows = await db.bfpo_territories.find(
        {"organization_id": BFPO_ORG_ID},
        {"_id": 0, "id": 1, "name": 1, "country": 1},
    ).to_list(200)
    return {"territories": rows}


@router.get("/staff/team")
async def staff_team(user=Depends(_require_staff)):
    """Full management list of every BFPO portal member (engineer/lead/staff)."""
    rows = await db.users.find(
        {"organization_id": BFPO_ORG_ID, "bfpo_role": {"$in": ["engineer", "lead", "staff"]}},
        {"_id": 0},
    ).to_list(500)
    rows.sort(key=lambda r: (r.get("bfpo_role") != "staff", (r.get("full_name") or "").lower()))
    return {"members": [_public_member(r) for r in rows]}


@router.post("/staff/engineers")
async def create_engineer(data: dict = Body(...), user=Depends(_require_staff)):
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    role = (data.get("bfpo_role") or "engineer").lower()
    if role not in ("engineer", "lead", "staff"):
        role = "engineer"
    if not full_name:
        raise HTTPException(400, "Full name is required")
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email address is required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "A user with this email address already exists")

    mode = (data.get("password_mode") or "invite").lower()
    if mode not in ("invite", "temp"):
        mode = "invite"
    territory_ids = [t for t in (data.get("bfpo_territory_ids") or []) if t]
    site_ids = [s for s in (data.get("bfpo_site_ids") or []) if s]
    phone = (data.get("phone") or "").strip()
    uid = str(uuid.uuid4())

    doc = {
        "id": uid, "organization_id": BFPO_ORG_ID, "email": email, "username": email,
        "full_name": full_name, "phone": phone,
        "role": "engineer" if role in ("engineer", "lead") else "staff",
        "bfpo_role": role, "bfpo_territory_ids": territory_ids, "bfpo_site_ids": site_ids,
        "module_overrides": ({"mod_operations": True} if role == "staff" else {}),
        "account_type": "mod_site", "is_mod_user": True, "is_active": True,
        "must_change_password": False, "created_at": _now(),
        "created_by": user.get("id"),
    }

    temp_password = None
    invite_url = None
    if mode == "temp":
        temp_password = (data.get("temp_password") or "").strip() or _gen_temp_password()
        if len(temp_password) < 8:
            raise HTTPException(400, "Temporary password must be at least 8 characters")
        doc["password"] = hash_password(temp_password)
        doc["must_change_password"] = True
    else:
        # Unusable placeholder hash until the invitee sets their own password.
        doc["password"] = hash_password(secrets.token_urlsafe(24))
        doc["invite_pending"] = True

    if role in ("engineer", "lead"):
        # Show the one-time welcome kit on their first sign-in.
        doc["bfpo_welcome_pending"] = True
        # Two-way sync — surface this engineer in Master Admin → External
        # Service Providers, grouped under the auto in-house provider.
        doc["mod_estate_supplier_id"] = await _ensure_inhouse_supplier()
        doc["provider_name"] = INHOUSE_PROVIDER_NAME
        doc["is_mod_bfpo"] = True
    await db.users.insert_one(doc)
    if role in ("engineer", "lead"):
        await db.svc_engineers.update_one(
            {"id": uid, "organization_id": BFPO_ORG_ID},
            {"$set": {"id": uid, "organization_id": BFPO_ORG_ID, "full_name": full_name,
                      "email": email, "active": True, "created_at": _now()}}, upsert=True)

    if mode == "invite":
        invite_url = await _issue_invite(doc)

    return {"member": _public_member(doc), "temp_password": temp_password, "invite_url": invite_url}


@router.patch("/staff/engineers/{eng_id}")
async def update_engineer(eng_id: str, data: dict = Body(...), user=Depends(_require_staff)):
    u = await db.users.find_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Engineer not found")
    updates: dict = {"updated_at": _now()}
    if "full_name" in data:
        fn = (data.get("full_name") or "").strip()
        if not fn:
            raise HTTPException(400, "Full name cannot be empty")
        updates["full_name"] = fn
    if "phone" in data:
        updates["phone"] = (data.get("phone") or "").strip()
    if "bfpo_territory_ids" in data:
        updates["bfpo_territory_ids"] = [t for t in (data.get("bfpo_territory_ids") or []) if t]
    if "bfpo_site_ids" in data:
        updates["bfpo_site_ids"] = [s for s in (data.get("bfpo_site_ids") or []) if s]
    if "bfpo_role" in data:
        role = (data.get("bfpo_role") or "").lower()
        if role not in ("engineer", "lead", "staff"):
            raise HTTPException(400, "Invalid role")
        updates["bfpo_role"] = role
        updates["role"] = "engineer" if role in ("engineer", "lead") else "staff"
        mo = dict(u.get("module_overrides") or {})
        if role == "staff":
            mo["mod_operations"] = True
        else:
            mo.pop("mod_operations", None)
        updates["module_overrides"] = mo
    await db.users.update_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    if updates.get("full_name") and (u.get("bfpo_role") in ("engineer", "lead")):
        await db.svc_engineers.update_one(
            {"id": eng_id, "organization_id": BFPO_ORG_ID}, {"$set": {"full_name": updates["full_name"]}})
    merged = {**u, **updates}
    return {"member": _public_member(merged)}


@router.post("/staff/engineers/{eng_id}/resend-invite")
async def resend_invite(eng_id: str, user=Depends(_require_staff)):
    u = await db.users.find_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Engineer not found")
    await db.users.update_one({"id": eng_id, "organization_id": BFPO_ORG_ID},
                              {"$set": {"invite_pending": True, "is_active": True}})
    u["invite_pending"] = True
    invite_url = await _issue_invite(u)
    return {"success": True, "invite_url": invite_url}


@router.post("/staff/engineers/{eng_id}/status")
async def set_engineer_status(eng_id: str, data: dict = Body(...), user=Depends(_require_staff)):
    active = bool(data.get("active"))
    u = await db.users.find_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Engineer not found")
    updates = {"is_active": active, "updated_at": _now()}
    if not active:
        # Kill any live sessions for a deactivated engineer.
        updates["tokens_revoked_before"] = int(datetime.now(timezone.utc).timestamp())
    await db.users.update_one({"id": eng_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    if u.get("bfpo_role") in ("engineer", "lead"):
        await db.svc_engineers.update_one(
            {"id": eng_id, "organization_id": BFPO_ORG_ID}, {"$set": {"active": active}})
    return {"success": True, "is_active": active}


# ── Public invite acceptance (no session required) ───────────────

@router.get("/invite/{token}")
async def invite_status(token: str):
    inv = await db.bfpo_invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        return {"valid": False, "reason": "not_found"}
    if inv.get("status") == "accepted":
        return {"valid": False, "reason": "used"}
    if (inv.get("expires_at") or "") < _now():
        return {"valid": False, "reason": "expired"}
    u = await db.users.find_one({"id": inv["user_id"]}, {"_id": 0, "full_name": 1})
    return {"valid": True, "email": inv["email"], "full_name": (u or {}).get("full_name", "")}


@router.post("/invite/{token}/accept")
async def invite_accept(token: str, data: dict = Body(...)):
    inv = await db.bfpo_invites.find_one({"token": token}, {"_id": 0})
    if not inv or inv.get("status") == "accepted" or (inv.get("expires_at") or "") < _now():
        raise HTTPException(400, "This invite link is invalid or has expired")
    password = data.get("password") or ""
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    await db.users.update_one({"id": inv["user_id"]}, {"$set": {
        "password": hash_password(password), "invite_pending": False, "is_active": True,
        "must_change_password": False, "password_updated_at": _now()}})
    await db.bfpo_invites.update_one({"token": token},
                                     {"$set": {"status": "accepted", "accepted_at": _now()}})
    return {"success": True}


# ── Engineer welcome kit (one-time, first sign-in) ───────────────

@router.get("/me/welcome")
async def my_welcome(user=Depends(_require_bfpo)):
    role = _role(user)
    show = bool(user.get("bfpo_welcome_pending")) and role in ("engineer", "lead")
    terr_ids = list(user.get("bfpo_territory_ids") or [])
    territories = []
    if terr_ids:
        territories = await db.bfpo_territories.find(
            {"organization_id": BFPO_ORG_ID, "id": {"$in": terr_ids}},
            {"_id": 0, "id": 1, "name": 1, "country": 1},
        ).to_list(50)
    scope = await _engineer_scope(user)
    site_ids = set(user.get("bfpo_site_ids") or []) | set(scope.get("all_site_ids") or [])
    site_or = []
    if terr_ids:
        site_or.append({"territory_id": {"$in": terr_ids}})
    if site_ids:
        site_or.append({"id": {"$in": list(site_ids)}})
    sites = []
    if site_or:
        sites = await db.sites.find(
            {"organization_id": BFPO_ORG_ID, "$or": site_or},
            {"_id": 0, "id": 1, "name": 1, "country": 1, "territory_name": 1},
        ).to_list(200)
    q = await _scoped_case_query(user, read=True)
    q["status"] = {"$in": list(OPEN_STATES)}
    jobs = await db.svc_cases.find(
        q, {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1, "site_name": 1, "status": 1},
    ).sort("created_at", -1).to_list(200)
    return {
        "show": show, "full_name": user.get("full_name"), "role": role,
        "territories": territories, "sites": sites,
        "open_jobs": {"count": len(jobs), "items": jobs[:6]},
    }


@router.post("/me/welcome/dismiss")
async def dismiss_welcome(user=Depends(_require_bfpo)):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"bfpo_welcome_pending": False, "bfpo_welcomed_at": _now()}},
    )
    return {"success": True}


__all__ = ["router"]

# ─────────────────────────────────────────────────────────────────
# Urgent-fault alerts (in-app banner) + site fault photos
# ─────────────────────────────────────────────────────────────────

_ALERT_PROJECTION = {"_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1, "priority": 1,
                     "safety_critical": 1, "created_at": 1, "status": 1, "reporter_name": 1}


@router.get("/alerts")
async def bfpo_alerts(user=Depends(_require_bfpo)):
    """Open P1 / safety-critical jobs the caller can see and hasn't acknowledged.
    Staff see every MOD job; engineers see their territory / sites / assigned jobs."""
    await _safe_bridge()
    q = await _scoped_case_query(user)
    acked = await db.bfpo_alert_acks.distinct("case_id", {"user_key": _ack_key(user)})
    q = {"$and": [q, {"status": {"$in": [NEW, "triaged", ASSIGNED]}},
                  {"$or": [{"priority": "p1"}, {"safety_critical": True}]},
                  {"id": {"$nin": acked}}]}
    count = await db.svc_cases.count_documents(q)
    rows = await db.svc_cases.find(q, _ALERT_PROJECTION).sort("created_at", -1).limit(20).to_list(20)
    return {"alerts": rows, "count": count}


def _ack_key(user: dict) -> str:
    # Email is stable across sessions (some admin sessions mint a fresh id each login).
    return (user.get("email") or "").lower() or user["id"]


@router.post("/alerts/{case_id}/ack")
async def bfpo_alert_ack(case_id: str, user=Depends(_require_bfpo)):
    await _get_scoped_case(user, case_id)
    key = _ack_key(user)
    await db.bfpo_alert_acks.update_one(
        {"user_key": key, "case_id": case_id},
        {"$set": {"user_key": key, "user_id": user["id"], "case_id": case_id, "at": _now()}}, upsert=True)
    return {"ok": True}


def _issue_photo_paths(issue: dict) -> list[str]:
    paths = [p for p in (issue.get("attachment_urls") or []) if isinstance(p, str)]
    for a in issue.get("attachments") or []:
        if isinstance(a, dict) and a.get("storage_path") and a.get("kind") != "quote":
            paths.append(a["storage_path"])
    for p in (issue.get("photos") or []) + (issue.get("images") or []):
        if isinstance(p, str):
            paths.append(p)
        elif isinstance(p, dict) and (p.get("storage_path") or p.get("path")):
            paths.append(p.get("storage_path") or p.get("path"))
    from utils.database import APP_NAME
    # Only MOD fault attachments / issue photos — never arbitrary storage paths.
    site = issue.get("mod_site_id") or issue.get("organization_id") or "-"
    allowed = (f"{APP_NAME}/mod-attachments/{site}/", f"{APP_NAME}/issues/{issue.get('id') or '-'}/")
    return [p for p in paths if p and ".." not in p and p.startswith(allowed)]


async def _case_issue(case: dict) -> dict:
    iid = case.get("mod_issue_id") or (case.get("source_meta") or {}).get("issue_id")
    return (await db.issues.find_one({"id": iid}, {"_id": 0}) or {}) if iid else {}


@router.get("/jobs/{case_id}/site-photos")
async def bfpo_site_photos(case_id: str, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    paths = _issue_photo_paths(await _case_issue(case))
    return {"photos": [{"index": i, "kind": "video" if p.lower().endswith((".mp4", ".mov", ".webm")) else "image"}
                       for i, p in enumerate(paths)]}


@router.get("/jobs/{case_id}/site-photos/{index}")
async def bfpo_site_photo(case_id: str, index: int, user=Depends(_require_bfpo)):
    case = await _get_scoped_case(user, case_id)
    paths = _issue_photo_paths(await _case_issue(case))
    if index < 0 or index >= len(paths):
        raise HTTPException(404, "Photo not found")
    from utils.database import get_object
    try:
        data, ct = await asyncio.to_thread(get_object, paths[index])
    except Exception:
        raise HTTPException(404, "Photo not available")
    return Response(content=data, media_type=ct or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# ─────────────────────────────────────────────────────────────────
# Engineer — capture missing asset details (Sicon essentials) on site
# ─────────────────────────────────────────────────────────────────

async def _site_equipment_query(site_id: str) -> dict:
    mod_org = await db.organizations.find_one({"id": site_id, "account_type": {"$in": list(MOD_ORG_TYPES)}}, {"_id": 0, "id": 1})
    return {"organization_id": site_id} if mod_org else {"organization_id": BFPO_ORG_ID, "site_id": site_id}


@router.get("/jobs/{case_id}/equipment-gaps")
async def bfpo_job_equipment_gaps(case_id: str, user=Depends(_require_bfpo)):
    from utils.sicon_equipment import ENGINEER_EDITABLE_FIELDS, missing_essentials
    case = await _get_scoped_case(user, case_id)
    if not case.get("site_id"):
        return {"items": [], "count": 0, "total": 0}
    q = await _site_equipment_query(case["site_id"])
    proj = {"_id": 0, "id": 1, "equipment_type": 1, "sicon_customer_ref": 1, **{f: 1 for f in ENGINEER_EDITABLE_FIELDS}}
    docs = await db.equipment.find(q, proj).sort([("location", 1), ("name", 1)]).to_list(1000)
    items = []
    for d in docs:
        # Customer Ref is office data — the engineer is only asked for what they can see on site.
        miss = [f for f in missing_essentials(d, customer_ref="-") if f != "sicon_customer_ref"]
        if not d.get("install_date"):
            miss.append("install_date")
        if miss:
            items.append({**d, "missing": miss})
    return {"items": items, "count": len(items), "total": len(docs), "fields": list(ENGINEER_EDITABLE_FIELDS)}


@router.post("/jobs/{case_id}/equipment/{equipment_id}/details")
async def bfpo_capture_equipment_details(case_id: str, equipment_id: str, body: dict = Body(...), user=Depends(_require_bfpo)):
    from utils.sicon_equipment import ENGINEER_EDITABLE_FIELDS
    from routes.equipment_gaps import _PROJECTION, apply_detail_patch
    case = await _get_scoped_case(user, case_id)
    if not case.get("site_id"):
        raise HTTPException(404, "Equipment not found")
    q = await _site_equipment_query(case["site_id"])
    eq = await db.equipment.find_one({**q, "id": equipment_id}, _PROJECTION)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    fields = {k: v for k, v in (body or {}).items() if v not in (None, "")}
    item = await apply_detail_patch(eq, fields, ENGINEER_EDITABLE_FIELDS, user, "engineer_app")
    item["missing"] = [f for f in item["missing"] if f not in ("sicon_customer_ref", "mod_code")]
    await _op_update(case, user, "asset_details", f"Captured asset details for {item.get('name') or 'equipment'}: {', '.join(sorted(fields))}",
                     {"equipment_id": equipment_id})
    return {"success": True, "item": item}
