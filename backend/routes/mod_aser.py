"""ASER — Activity Safety Events Register (MOD-exclusive).

Lets MOD rehab / medical / gym / PTI teams document equipment-related
safety events, near-misses, repeated failures and incidents that impact
rehab / activity delivery. Reuses existing platform records (equipment,
issues/faults, CAPEX scoring, sites, users, audit) — NEVER duplicates
core records.

Access is MOD-only and site-scoped:
  * mod_site users create + view ASER entries for their OWN site.
  * mod_branch / mod_org (PRO) users read across their permitted sites.
  * commercial customers have no access.

Schema (db.aser_entries):
  id, aser_ref (ASER-YYYY-NNNNN), site_id, equipment_id, equipment_snapshot,
  event_type, title, description, what_happened, immediate_action,
  activity_impact{...}, safety_impact{...}, risk{actual_harm, potential_severity,
  likelihood, rating}, equipment_status, follow_up{...}, attachment_urls[],
  linked_fault_id, capex_flagged, status, repeated_issue{...}, actions[],
  created_by_*, created_at, status_history[]
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.security import sanitise_string

logger = logging.getLogger(__name__)
router = APIRouter(tags=["MOD ASER"])

MOD_ACCOUNT_TYPES = {"mod_site", "mod_branch", "mod_org"}

# ── Config enums (also surfaced via GET /mod/aser/config) ─────────────
EVENT_TYPES = [
    ("equipment_failure_rehab", "Equipment Failure Impacting Rehab Delivery"),
    ("equipment_failure_group", "Equipment Failure Impacting Group Programme"),
    ("equipment_failure_individual", "Equipment Failure Impacting Individual Programme"),
    ("equipment_unavailable_clinical", "Equipment Unavailable for Clinical/Rehab Use"),
    ("equipment_safety_concern", "Equipment Safety Concern"),
    ("near_miss", "Near Miss"),
    ("incident", "Incident"),
    ("repeated_fault", "Repeated Fault"),
    ("unsafe_condition", "Unsafe Condition"),
    ("removed_from_use", "Equipment Removed from Use"),
    ("breakdown_during_activity", "Equipment Breakdown During Activity"),
    ("old_rundown", "Old/Rundown Equipment Affecting Delivery"),
    ("hygiene", "Hygiene/Infection Control Concern"),
    ("accessibility", "Accessibility Concern"),
    ("environmental", "Environmental Concern"),
    ("other", "Other"),
]
EVENT_TYPE_KEYS = {k for k, _ in EVENT_TYPES}

ACTUAL_HARM = ["no_harm", "low_harm", "moderate_harm", "severe_harm", "fatality", "not_applicable"]
POTENTIAL_SEVERITY = ["low", "medium", "high", "critical"]
LIKELIHOOD = ["rare", "unlikely", "possible", "likely", "almost_certain"]
RISK_RATING = ["low", "medium", "high", "critical"]

EQUIPMENT_STATUSES = [
    "operational", "operational_with_monitoring", "restricted_use",
    "removed_from_use", "awaiting_engineer", "awaiting_parts",
    "awaiting_replacement", "replacement_recommended", "resolved", "closed",
]
# Statuses that mean the machine should be highlighted red (flagged for removal)
REMOVAL_FLAG_STATUSES = {"removed_from_use", "awaiting_replacement", "replacement_recommended"}

ENTRY_STATUSES = [
    "draft", "submitted", "under_review", "linked_to_fault", "awaiting_action",
    "awaiting_engineer", "awaiting_parts", "monitoring", "escalated",
    "capex_review", "replacement_recommended", "resolved", "closed",
]


# ══════════════════════════════════════════════════════════════════
#                     SCOPE HELPERS
# ══════════════════════════════════════════════════════════════════
async def _org_of(user: dict) -> dict:
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org


# ── Settings (singleton, Master Admin controlled) ─────────────────────
DEFAULT_SETTINGS = {
    "id": "global",
    "enabled": True,
    "restrict_to_mod": True,
    "require_equipment_selection": True,
    "allow_without_equipment": False,
    "enable_capex_linking": True,
    "enable_fault_linking": True,
    "require_manager_review_high_critical": True,
    "repeated_issue_threshold": 2,
    "patient_pii_warning": True,
    "ai_summaries": True,
    "notifications": {
        "site_manager": {"on_new": True, "on_high_critical": True, "on_removed": True,
                         "on_repeated": True, "on_capex": True},
        "service_desk": {"enabled": False, "email": "", "on_high_critical": True,
                         "on_fault_link": True, "on_repeated": True},
        "account_manager": {"enabled": False, "email": "", "on_repeated": True, "on_capex": True},
    },
}


def _merge_settings(doc: Optional[dict]) -> dict:
    out = {**DEFAULT_SETTINGS}
    if doc:
        for k, v in doc.items():
            if k == "notifications" and isinstance(v, dict):
                merged = {grp: {**DEFAULT_SETTINGS["notifications"][grp], **(v.get(grp) or {})}
                          for grp in DEFAULT_SETTINGS["notifications"]}
                out["notifications"] = merged
            else:
                out[k] = v
    return out


async def _load_settings() -> dict:
    doc = await db.aser_settings.find_one({"id": "global"}, {"_id": 0})
    return _merge_settings(doc)



async def _require_mod(user: dict) -> dict:
    """Caller must belong to a MOD organisation (site or PRO)."""
    org = await _org_of(user)
    if org.get("account_type") not in MOD_ACCOUNT_TYPES and not user.get("is_master_admin"):
        raise HTTPException(403, "ASER is available to MOD organisations only")
    if not user.get("is_master_admin"):
        settings = await _load_settings()
        if not settings.get("enabled", True):
            raise HTTPException(403, "ASER is currently disabled by the platform administrator")
    return org


async def _sites_in_scope(user: dict, org: dict) -> list[str]:
    """Return the list of mod_site org IDs this user can see ASER for."""
    at = org.get("account_type")
    if at == "mod_site":
        return [org["id"]]
    if at in {"mod_branch", "mod_org"}:
        q = {"account_type": "mod_site", "mod_root_id": org.get("mod_root_id")}
        if at == "mod_branch" and org.get("mod_branch"):
            q["mod_branch"] = org["mod_branch"]
        sites = await db.organizations.find(q, {"_id": 0, "id": 1}).to_list(2000)
        return [s["id"] for s in sites]
    if user.get("is_master_admin"):
        sites = await db.organizations.find(
            {"account_type": "mod_site"}, {"_id": 0, "id": 1},
        ).to_list(5000)
        return [s["id"] for s in sites]
    return [org["id"]]


def _is_manager(user: dict) -> bool:
    return user.get("role") in ("owner", "manager") or bool(user.get("is_master_admin"))


def _next_ref() -> str:
    now = datetime.now(timezone.utc)
    return f"ASER-{now.year}-{str(uuid.uuid4().int)[:5].zfill(5)}"


async def _equipment_in_site(equipment_id: str, site_ids: list[str]) -> Optional[dict]:
    return await db.equipment.find_one(
        {"id": equipment_id, "organization_id": {"$in": site_ids}}, {"_id": 0},
    )


async def _repeated_issue_for(equipment_id: str, site_id: str) -> dict:
    """Compute repeated-issue counters + label for an equipment asset."""
    now = datetime.now(timezone.utc)
    since_90 = (now - timedelta(days=90)).isoformat()
    since_180 = (now - timedelta(days=180)).isoformat()

    aser_90 = await db.aser_entries.count_documents(
        {"equipment_id": equipment_id, "created_at": {"$gte": since_90}},
    )
    aser_total = await db.aser_entries.count_documents({"equipment_id": equipment_id})
    faults_180 = await db.issues.count_documents(
        {"equipment_id": equipment_id, "created_at": {"$gte": since_180}, "is_drill": {"$ne": True}},
    )
    removed_count = await db.aser_entries.count_documents(
        {"equipment_id": equipment_id, "equipment_status": {"$in": list(REMOVAL_FLAG_STATUSES)}},
    )
    capex_flagged = await db.aser_entries.count_documents(
        {"equipment_id": equipment_id, "capex_flagged": True},
    )

    label = "monitor"
    if capex_flagged or removed_count > 1 or aser_90 >= 3:
        label = "replacement_strongly_recommended"
    elif aser_90 >= 2 or faults_180 >= 3:
        label = "replacement_evidence_building"
    elif removed_count >= 1:
        label = "escalation_recommended"
    elif aser_total >= 1:
        label = "repeated_issue"

    triggers = []
    if aser_90 >= 2:
        triggers.append("2+ ASER entries in 90 days")
    if faults_180 >= 3:
        triggers.append("3+ faults in 6 months")
    if removed_count > 1:
        triggers.append("Removed from use more than once")
    if capex_flagged:
        triggers.append("CAPEX replacement flagged")

    return {
        "aser_90d": aser_90,
        "aser_total": aser_total,
        "faults_180d": faults_180,
        "removed_count": removed_count,
        "capex_flagged_count": capex_flagged,
        "label": label,
        "triggers": triggers,
    }


# ══════════════════════════════════════════════════════════════════
#                     CONFIG + EQUIPMENT
# ══════════════════════════════════════════════════════════════════
@router.get("/mod/aser/config")
async def aser_config(user: dict = Depends(get_current_user)):
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    settings = await _load_settings()
    sites = await db.organizations.find(
        {"id": {"$in": site_ids}}, {"_id": 0, "id": 1, "name": 1, "site_code": 1, "mod_branch": 1},
    ).sort("name", 1).to_list(2000)
    return {
        "event_types": [{"key": k, "label": v} for k, v in EVENT_TYPES],
        "actual_harm": ACTUAL_HARM,
        "potential_severity": POTENTIAL_SEVERITY,
        "likelihood": LIKELIHOOD,
        "risk_rating": RISK_RATING,
        "equipment_statuses": EQUIPMENT_STATUSES,
        "entry_statuses": ENTRY_STATUSES,
        "sites": sites,
        "is_manager": _is_manager(user),
        "ai_summaries": bool(settings.get("ai_summaries", True)),
        "account_type": org.get("account_type"),
    }


@router.get("/mod/aser/equipment")
async def aser_equipment(
    site_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=120),
    user: dict = Depends(get_current_user),
):
    """Equipment picker — only equipment at the caller's permitted site(s),
    enriched with fault + ASER history so the user picks the right asset."""
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    if site_id:
        if site_id not in site_ids:
            raise HTTPException(403, "Site outside your permitted scope")
        query_sites = [site_id]
    else:
        query_sites = site_ids

    query: dict = {"organization_id": {"$in": query_sites}}
    if q:
        import re as _re
        rx = {"$regex": _re.escape(q.strip()), "$options": "i"}
        query["$or"] = [
            {"name": rx}, {"serial_number": rx}, {"asset_number": rx},
            {"model": rx}, {"machine_type": rx}, {"category": rx},
        ]
    items = await db.equipment.find(query, {"_id": 0}).sort("name", 1).limit(500).to_list(500)

    out = []
    for e in items:
        eid = e["id"]
        open_faults = await db.issues.count_documents(
            {"equipment_id": eid, "status": {"$ne": "resolved"}},
        )
        prev_aser = await db.aser_entries.count_documents({"equipment_id": eid})
        out.append({
            "id": eid,
            "name": e.get("name"),
            "asset_number": e.get("asset_number") or e.get("asset_tag"),
            "serial_number": e.get("serial_number"),
            "model": e.get("model") or e.get("model_number"),
            "equipment_type": e.get("machine_type") or e.get("category") or e.get("equipment_type"),
            "location": e.get("location"),
            "status": e.get("status"),
            "install_date": e.get("install_date") or e.get("installed_at") or e.get("created_at"),
            "warranty_expiry": e.get("warranty_expiry"),
            "sla_expiry": e.get("sla_expiry"),
            "organization_id": e.get("organization_id"),
            "open_faults": open_faults,
            "previous_aser_count": prev_aser,
            "aser_removed_from_use": bool(e.get("aser_removed_from_use")),
            "aser_flag_status": e.get("aser_flag_status"),
            "aser_disposed": bool(e.get("aser_disposed")),
        })
    return {"equipment": out}


# ══════════════════════════════════════════════════════════════════
#                     CREATE + LIST + DETAIL
# ══════════════════════════════════════════════════════════════════
class ActivityImpact(BaseModel):
    impacted_rehab: bool = False
    impacted_group: bool = False
    impacted_individual: bool = False
    impacted_clinic_output: bool = False
    activity_affected: Optional[str] = Field(default=None, max_length=300)
    sessions_affected: int = 0
    patients_affected: int = 0
    programme_cancelled: bool = False
    programme_delayed: bool = False
    programme_modified: bool = False
    alternative_equipment_used: bool = False
    impact_summary: Optional[str] = Field(default=None, max_length=2000)


class SafetyImpact(BaseModel):
    anyone_injured: bool = False
    near_miss: bool = False
    equipment_removed: bool = False
    area_isolated: bool = False
    warning_signage: bool = False
    concern_description: Optional[str] = Field(default=None, max_length=2000)


class Risk(BaseModel):
    actual_harm: str = "no_harm"
    potential_severity: str = "low"
    likelihood: str = "possible"
    rating: str = "low"


class ASERCreate(BaseModel):
    site_id: str
    equipment_id: str
    event_type: str
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=4000)
    what_happened: Optional[str] = Field(default=None, max_length=4000)
    immediate_action: Optional[str] = Field(default=None, max_length=2000)
    activity_impact: ActivityImpact = Field(default_factory=ActivityImpact)
    safety_impact: SafetyImpact = Field(default_factory=SafetyImpact)
    risk: Risk = Field(default_factory=Risk)
    equipment_status: str = "operational"
    follow_up_actions: Optional[str] = Field(default=None, max_length=2000)
    action_owner: Optional[str] = Field(default=None, max_length=200)
    due_date: Optional[str] = None
    attachment_urls: list[str] = Field(default_factory=list, max_length=12)
    linked_fault_id: Optional[str] = None
    capex_flagged: bool = False
    submit: bool = True  # False → save as draft


async def _apply_equipment_removal_flag(equipment_id: str, status: str, aser_ref: str, reason: str):
    """When ASER marks an asset for removal/replacement, flag the real
    equipment record so it is highlighted RED across the app. Managers
    can later dispose of it. Does NOT delete or duplicate the record."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if status in REMOVAL_FLAG_STATUSES:
        await db.equipment.update_one(
            {"id": equipment_id},
            {"$set": {
                "aser_removed_from_use": True,
                "aser_flag_status": status,
                "aser_flag_reason": reason[:300],
                "aser_flag_ref": aser_ref,
                "aser_flag_at": now_iso,
                **({"status": "out_of_service"} if status == "removed_from_use" else {}),
            }},
        )


@router.post("/mod/aser")
async def aser_create(payload: ASERCreate, request: Request, user: dict = Depends(get_current_user)):
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    if payload.site_id not in site_ids:
        raise HTTPException(403, "Site outside your permitted scope")
    if payload.event_type not in EVENT_TYPE_KEYS:
        raise HTTPException(400, "Invalid event_type")
    if payload.equipment_status not in EQUIPMENT_STATUSES:
        raise HTTPException(400, "Invalid equipment_status")
    if payload.risk.rating not in RISK_RATING:
        raise HTTPException(400, "Invalid risk rating")

    equipment = await _equipment_in_site(payload.equipment_id, [payload.site_id])
    if not equipment:
        raise HTTPException(404, "Equipment not found at this site")

    # Validate linked fault belongs to the same site.
    if payload.linked_fault_id:
        fault = await db.issues.find_one(
            {"id": payload.linked_fault_id, "organization_id": payload.site_id}, {"_id": 0, "id": 1},
        )
        if not fault:
            raise HTTPException(400, "Linked fault not found at this site")

    now = datetime.now(timezone.utc)
    ref = _next_ref()
    entry_id = str(uuid.uuid4())
    settings = await _load_settings()

    # High/critical risk requires review — set status accordingly (gated by settings).
    status = "draft" if not payload.submit else "submitted"
    if payload.submit and payload.risk.rating in ("high", "critical") and settings.get("require_manager_review_high_critical", True):
        status = "under_review"
    if payload.linked_fault_id and payload.submit:
        status = "linked_to_fault"
    if payload.capex_flagged and payload.submit:
        status = "capex_review"

    repeated = await _repeated_issue_for(payload.equipment_id, payload.site_id)

    doc = {
        "id": entry_id,
        "aser_ref": ref,
        "site_id": payload.site_id,
        "site_name": (await db.organizations.find_one({"id": payload.site_id}, {"_id": 0, "name": 1}) or {}).get("name"),
        "equipment_id": payload.equipment_id,
        "equipment_snapshot": {
            "name": equipment.get("name"),
            "asset_number": equipment.get("asset_number") or equipment.get("asset_tag"),
            "serial_number": equipment.get("serial_number"),
            "model": equipment.get("model") or equipment.get("model_number"),
            "equipment_type": equipment.get("machine_type") or equipment.get("category"),
            "location": equipment.get("location"),
            "install_date": equipment.get("install_date") or equipment.get("installed_at") or equipment.get("created_at"),
            "warranty_expiry": equipment.get("warranty_expiry"),
        },
        "event_type": payload.event_type,
        "title": sanitise_string(payload.title),
        "description": payload.description.strip(),
        "what_happened": (payload.what_happened or "").strip() or None,
        "immediate_action": (payload.immediate_action or "").strip() or None,
        "activity_impact": payload.activity_impact.model_dump(),
        "safety_impact": payload.safety_impact.model_dump(),
        "risk": payload.risk.model_dump(),
        "equipment_status": payload.equipment_status,
        "follow_up": {
            "actions": (payload.follow_up_actions or "").strip() or None,
            "action_owner": (payload.action_owner or "").strip() or None,
            "due_date": payload.due_date,
        },
        "attachment_urls": payload.attachment_urls,
        "linked_fault_id": payload.linked_fault_id,
        "capex_flagged": bool(payload.capex_flagged),
        "repeated_issue": repeated,
        "status": status,
        "created_by_user_id": user.get("id"),
        "created_by_name": user.get("full_name") or user.get("email"),
        "created_by_email": user.get("email"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "status_history": [{"status": status, "at": now.isoformat(), "by": user.get("email")}],
    }
    await db.aser_entries.insert_one(doc)

    # Flag equipment for removal (red highlight) if applicable.
    await _apply_equipment_removal_flag(payload.equipment_id, payload.equipment_status, ref, payload.title)

    # Flag equipment for CAPEX evidence (does not duplicate CAPEX engine).
    if payload.capex_flagged:
        await db.equipment.update_one(
            {"id": payload.equipment_id},
            {"$set": {
                "capex_manual_flag": True,
                "capex_flag_source": "aser",
                "capex_flag_ref": ref,
                "capex_flag_at": now.isoformat(),
            }},
        )

    await _audit(payload.site_id, user, "aser.create", target_id=entry_id, request=request,
                 aser_ref=ref, event_type=payload.event_type, risk=payload.risk.rating,
                 equipment_status=payload.equipment_status, capex_flagged=payload.capex_flagged)

    doc.pop("_id", None)
    if payload.submit:
        await _notify_aser_created(doc, settings)
    return {"ok": True, "aser_ref": ref, "entry": doc}


@router.get("/mod/aser")
async def aser_list(
    site_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    risk: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    capex: Optional[bool] = Query(None),
    removed: Optional[bool] = Query(None),
    repeated: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, max_length=120),
    user: dict = Depends(get_current_user),
):
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    query: dict = {"site_id": {"$in": site_ids}}
    if site_id and site_id in site_ids:
        query["site_id"] = site_id
    if event_type:
        query["event_type"] = event_type
    if risk:
        query["risk.rating"] = risk
    if status:
        query["status"] = status
    if capex is not None:
        query["capex_flagged"] = capex
    if removed:
        query["equipment_status"] = {"$in": list(REMOVAL_FLAG_STATUSES)}
    if repeated:
        query["repeated_issue.label"] = {"$in": [
            "repeated_issue", "escalation_recommended",
            "replacement_evidence_building", "replacement_strongly_recommended",
        ]}
    if q:
        import re as _re
        rx = {"$regex": _re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"aser_ref": rx}, {"title": rx}, {"equipment_snapshot.name": rx},
                        {"equipment_snapshot.serial_number": rx}]
    rows = await db.aser_entries.find(query, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"entries": rows, "count": len(rows)}


@router.get("/mod/aser/dashboard")
async def aser_dashboard(user: dict = Depends(get_current_user)):
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    base = {"site_id": {"$in": site_ids}}
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    entries = await db.aser_entries.find(base, {"_id": 0}).to_list(5000)
    open_statuses = {"draft", "submitted", "under_review", "awaiting_action",
                     "awaiting_engineer", "awaiting_parts", "monitoring",
                     "escalated", "capex_review", "linked_to_fault"}

    sessions_impacted = sum((e.get("activity_impact") or {}).get("sessions_affected", 0) or 0 for e in entries)
    group_impacted = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_group"))
    individual_impacted = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_individual"))

    # by-type / by-risk / by-site aggregations
    def _count_by(field_fn):
        acc: dict = {}
        for e in entries:
            k = field_fn(e)
            if k:
                acc[k] = acc.get(k, 0) + 1
        return acc

    removed_equipment = len({e["equipment_id"] for e in entries
                             if e.get("equipment_status") in REMOVAL_FLAG_STATUSES})
    repeated_equipment = len({e["equipment_id"] for e in entries
                              if (e.get("repeated_issue") or {}).get("label") in {
                                  "repeated_issue", "escalation_recommended",
                                  "replacement_evidence_building", "replacement_strongly_recommended"}})

    return {
        "cards": {
            "entries_this_month": sum(1 for e in entries if e.get("created_at", "") >= month_start),
            "open_entries": sum(1 for e in entries if e.get("status") in open_statuses),
            "high_risk_entries": sum(1 for e in entries if (e.get("risk") or {}).get("rating") in ("high", "critical")),
            "removed_from_use": removed_equipment,
            "repeated_issue_equipment": repeated_equipment,
            "sessions_impacted": sessions_impacted,
            "group_programmes_impacted": group_impacted,
            "individual_programmes_impacted": individual_impacted,
            "capex_evidence_flags": sum(1 for e in entries if e.get("capex_flagged")),
            "total_entries": len(entries),
        },
        "by_event_type": _count_by(lambda e: e.get("event_type")),
        "by_risk": _count_by(lambda e: (e.get("risk") or {}).get("rating")),
        "by_site": _count_by(lambda e: e.get("site_name")),
        "scope_sites": len(site_ids),
    }


@router.get("/mod/aser/analytics")
async def aser_analytics(
    months: int = Query(12, ge=3, le=24),
    user: dict = Depends(get_current_user),
):
    """Trend + breakdown analytics for the ASER register (site-scoped)."""
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    entries = await db.aser_entries.find({"site_id": {"$in": site_ids}}, {"_id": 0}).to_list(10000)

    now = datetime.now(timezone.utc)
    # Build the last `months` month buckets (YYYY-MM), oldest → newest.
    buckets: list[str] = []
    y, m = now.year, now.month
    for _ in range(months):
        buckets.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    buckets.reverse()
    bset = set(buckets)

    trend = {b: {"month": b, "entries": 0, "high_risk": 0, "sessions_impacted": 0,
                 "removed_from_use": 0, "rehab_impacted": 0} for b in buckets}
    repeated_labels = {
        "repeated_issue", "escalation_recommended",
        "replacement_evidence_building", "replacement_strongly_recommended",
    }

    def acc(d: dict, k):
        if k:
            d[k] = d.get(k, 0) + 1

    by_event_type: dict = {}
    by_risk: dict = {}
    by_site: dict = {}
    by_equipment_type: dict = {}
    asset_counts: dict = {}

    for e in entries:
        mkey = (e.get("created_at") or "")[:7]
        if mkey in bset:
            t = trend[mkey]
            t["entries"] += 1
            rating = (e.get("risk") or {}).get("rating")
            if rating in ("high", "critical"):
                t["high_risk"] += 1
            ai = e.get("activity_impact") or {}
            t["sessions_impacted"] += ai.get("sessions_affected", 0) or 0
            if ai.get("impacted_rehab"):
                t["rehab_impacted"] += 1
            if e.get("equipment_status") in REMOVAL_FLAG_STATUSES:
                t["removed_from_use"] += 1
        acc(by_event_type, e.get("event_type"))
        acc(by_risk, (e.get("risk") or {}).get("rating"))
        acc(by_site, e.get("site_name"))
        acc(by_equipment_type, (e.get("equipment_snapshot") or {}).get("equipment_type"))
        eid = e.get("equipment_id")
        if eid:
            snap = e.get("equipment_snapshot") or {}
            a = asset_counts.setdefault(eid, {
                "equipment_id": eid,
                "name": snap.get("name"),
                "serial_number": snap.get("serial_number"),
                "equipment_type": snap.get("equipment_type"),
                "aser_count": 0, "high_risk": 0, "removed": 0, "capex": 0,
                "label": (e.get("repeated_issue") or {}).get("label"),
            })
            a["aser_count"] += 1
            if (e.get("risk") or {}).get("rating") in ("high", "critical"):
                a["high_risk"] += 1
            if e.get("equipment_status") in REMOVAL_FLAG_STATUSES:
                a["removed"] += 1
            if e.get("capex_flagged"):
                a["capex"] += 1
            lbl = (e.get("repeated_issue") or {}).get("label")
            if lbl:
                a["label"] = lbl

    top_assets = sorted(asset_counts.values(), key=lambda x: x["aser_count"], reverse=True)[:10]
    repeated_assets = [a for a in top_assets if a.get("label") in repeated_labels]

    def to_list(d):
        return [{"name": k, "value": v} for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)]

    return {
        "trend": [trend[b] for b in buckets],
        "by_event_type": to_list(by_event_type),
        "by_risk": to_list(by_risk),
        "by_site": to_list(by_site),
        "by_equipment_type": to_list(by_equipment_type),
        "top_assets": top_assets,
        "repeated_assets": repeated_assets,
        "total_entries": len(entries),
        "scope_sites": len(site_ids),
    }



@router.get("/mod/aser/{entry_id}")
async def aser_detail(entry_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    doc = await db.aser_entries.find_one(
        {"id": entry_id, "site_id": {"$in": site_ids}}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "ASER entry not found")
    return doc


# ══════════════════════════════════════════════════════════════════
#                 UPDATE / STATUS / FAULT / CAPEX / DISPOSE
# ══════════════════════════════════════════════════════════════════
async def _load_scoped(entry_id: str, user: dict) -> tuple[dict, dict, list[str]]:
    org = await _require_mod(user)
    site_ids = await _sites_in_scope(user, org)
    doc = await db.aser_entries.find_one({"id": entry_id, "site_id": {"$in": site_ids}}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "ASER entry not found")
    return org, doc, site_ids


@router.patch("/mod/aser/{entry_id}")
async def aser_update(entry_id: str, body: dict = Body(...), request: Request = None,
                      user: dict = Depends(get_current_user)):
    _org, doc, _sites = await _load_scoped(entry_id, user)
    now_iso = datetime.now(timezone.utc).isoformat()
    updates: dict = {"updated_at": now_iso}

    if "status" in body:
        new_status = body["status"]
        if new_status not in ENTRY_STATUSES:
            raise HTTPException(400, "Invalid status")
        updates["status"] = new_status
    if "equipment_status" in body:
        es = body["equipment_status"]
        if es not in EQUIPMENT_STATUSES:
            raise HTTPException(400, "Invalid equipment_status")
        updates["equipment_status"] = es
        await _apply_equipment_removal_flag(doc["equipment_id"], es, doc["aser_ref"], doc.get("title", ""))
    if "follow_up" in body and isinstance(body["follow_up"], dict):
        updates["follow_up"] = {**(doc.get("follow_up") or {}), **body["follow_up"]}
    if "risk" in body and isinstance(body["risk"], dict):
        updates["risk"] = {**(doc.get("risk") or {}), **body["risk"]}

    push = {}
    if "status" in updates:
        push["status_history"] = {"status": updates["status"], "at": now_iso, "by": user.get("email")}

    op: dict = {"$set": updates}
    if push:
        op["$push"] = push
    await db.aser_entries.update_one({"id": entry_id}, op)
    await _audit(doc["site_id"], user, "aser.update", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], changes=list(updates.keys()))
    return {"ok": True}


class LinkFaultBody(BaseModel):
    fault_id: str


@router.post("/mod/aser/{entry_id}/link-fault")
async def aser_link_fault(entry_id: str, body: LinkFaultBody, request: Request = None,
                          user: dict = Depends(get_current_user)):
    _org, doc, _sites = await _load_scoped(entry_id, user)
    fault = await db.issues.find_one({"id": body.fault_id, "organization_id": doc["site_id"]}, {"_id": 0, "id": 1})
    if not fault:
        raise HTTPException(404, "Fault not found at this site")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.aser_entries.update_one(
        {"id": entry_id},
        {"$set": {"linked_fault_id": body.fault_id, "status": "linked_to_fault", "updated_at": now_iso},
         "$push": {"status_history": {"status": "linked_to_fault", "at": now_iso, "by": user.get("email")}}},
    )
    await _audit(doc["site_id"], user, "aser.link_fault", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], fault_id=body.fault_id)
    return {"ok": True, "linked_fault_id": body.fault_id}


@router.post("/mod/aser/{entry_id}/create-fault")
async def aser_create_fault(entry_id: str, request: Request = None, user: dict = Depends(get_current_user)):
    """Create a fault (issues record) pre-filled from the ASER entry and
    link it back. Reuses the existing faults collection — no duplicate."""
    _org, doc, _sites = await _load_scoped(entry_id, user)
    if doc.get("linked_fault_id"):
        raise HTTPException(400, "This ASER entry is already linked to a fault")
    equipment = await db.equipment.find_one({"id": doc["equipment_id"]}, {"_id": 0})
    now = datetime.now(timezone.utc)
    ticket_ref = f"MOD-{now.year}-{str(uuid.uuid4().int)[:5].zfill(5)}"
    issue_id = str(uuid.uuid4())
    safety = (doc.get("safety_impact") or {})
    is_safety = bool(safety.get("anyone_injured") or safety.get("near_miss")
                     or doc.get("event_type") in {"equipment_safety_concern", "unsafe_condition", "incident"})
    priority = "urgent" if (doc.get("risk") or {}).get("rating") == "critical" or is_safety else (
        "high" if (doc.get("risk") or {}).get("rating") == "high" else "medium")
    issue = {
        "id": issue_id,
        "organization_id": doc["site_id"],
        "user_id": user.get("id"),
        "equipment_id": doc["equipment_id"],
        "machine_type": (equipment or {}).get("machine_type") or (equipment or {}).get("category"),
        "serial_number": (equipment or {}).get("serial_number"),
        "issue_description": f"[ASER {doc['aser_ref']}] {doc.get('title')}\n\n{doc.get('description')}",
        "severity": priority,
        "priority": priority,
        "status": "open",
        "mod_site_id": doc["site_id"],
        "mod_ticket_ref": ticket_ref,
        "fault_type_mod": "safety" if is_safety else "other",
        "aser_entry_id": entry_id,
        "aser_ref": doc["aser_ref"],
        "attachment_urls": doc.get("attachment_urls", []),
        "reporter_name": doc.get("created_by_name"),
        "reporter_email": doc.get("created_by_email"),
        "created_at": now.isoformat(),
    }
    await db.issues.insert_one(issue)
    now_iso = now.isoformat()
    await db.aser_entries.update_one(
        {"id": entry_id},
        {"$set": {"linked_fault_id": issue_id, "linked_fault_ref": ticket_ref,
                  "status": "linked_to_fault", "updated_at": now_iso},
         "$push": {"status_history": {"status": "linked_to_fault", "at": now_iso, "by": user.get("email")}}},
    )
    await _audit(doc["site_id"], user, "aser.create_fault", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], fault_id=issue_id, ticket_ref=ticket_ref)
    return {"ok": True, "fault_id": issue_id, "ticket_ref": ticket_ref}


@router.post("/mod/aser/{entry_id}/flag-capex")
async def aser_flag_capex(entry_id: str, request: Request = None, user: dict = Depends(get_current_user)):
    _org, doc, _sites = await _load_scoped(entry_id, user)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.aser_entries.update_one(
        {"id": entry_id},
        {"$set": {"capex_flagged": True, "status": "capex_review", "updated_at": now_iso},
         "$push": {"status_history": {"status": "capex_review", "at": now_iso, "by": user.get("email")}}},
    )
    await db.equipment.update_one(
        {"id": doc["equipment_id"]},
        {"$set": {"capex_manual_flag": True, "capex_flag_source": "aser",
                  "capex_flag_ref": doc["aser_ref"], "capex_flag_at": now_iso}},
    )
    await _audit(doc["site_id"], user, "aser.flag_capex", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], equipment_id=doc["equipment_id"])
    return {"ok": True}


class CloseBody(BaseModel):
    manager_override: bool = False
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/mod/aser/{entry_id}/close")
async def aser_close(entry_id: str, body: CloseBody, request: Request = None,
                     user: dict = Depends(get_current_user)):
    _org, doc, _sites = await _load_scoped(entry_id, user)
    if not _is_manager(user):
        raise HTTPException(403, "Only owners / managers can close an ASER entry")
    # High/critical risk needs review before closure unless override recorded.
    rating = (doc.get("risk") or {}).get("rating")
    fu = doc.get("follow_up") or {}
    incomplete = bool(fu.get("actions")) and not body.manager_override and doc.get("status") in {"awaiting_action"}
    if rating in ("high", "critical") and doc.get("status") == "submitted" and not body.manager_override:
        raise HTTPException(400, "High/critical entries require review before closure (or a manager override)")
    if incomplete:
        raise HTTPException(400, "Follow-up actions are incomplete — record a manager override to close")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.aser_entries.update_one(
        {"id": entry_id},
        {"$set": {"status": "closed", "closed_at": now_iso, "closed_by": user.get("email"),
                  "close_note": (body.note or "").strip() or None,
                  "manager_override": bool(body.manager_override), "updated_at": now_iso},
         "$push": {"status_history": {"status": "closed", "at": now_iso, "by": user.get("email")}}},
    )
    await _audit(doc["site_id"], user, "aser.close", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], manager_override=body.manager_override)
    return {"ok": True}


@router.post("/mod/aser/{entry_id}/dispose")
async def aser_dispose(entry_id: str, request: Request = None, user: dict = Depends(get_current_user)):
    """Manager disposes of a machine that ASER flagged for removal. Marks
    the real equipment record disposed (soft — never hard-deleted) and
    resolves the ASER entry."""
    _org, doc, _sites = await _load_scoped(entry_id, user)
    if not _is_manager(user):
        raise HTTPException(403, "Only owners / managers can dispose of equipment")
    equipment = await db.equipment.find_one({"id": doc["equipment_id"]}, {"_id": 0, "aser_removed_from_use": 1})
    if not equipment or not equipment.get("aser_removed_from_use"):
        raise HTTPException(400, "Equipment is not flagged for removal — set status to 'Removed from Use' first")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.equipment.update_one(
        {"id": doc["equipment_id"]},
        {"$set": {"aser_disposed": True, "aser_disposed_at": now_iso,
                  "aser_disposed_by": user.get("email"), "status": "disposed", "is_disposed": True}},
    )
    await db.aser_entries.update_one(
        {"id": entry_id},
        {"$set": {"status": "resolved", "equipment_status": "removed_from_use",
                  "disposed": True, "updated_at": now_iso},
         "$push": {"status_history": {"status": "resolved", "at": now_iso, "by": user.get("email"), "note": "Equipment disposed"}}},
    )
    await _audit(doc["site_id"], user, "aser.dispose", target_id=entry_id, request=request,
                 aser_ref=doc["aser_ref"], equipment_id=doc["equipment_id"])
    return {"ok": True, "equipment_id": doc["equipment_id"]}


# ── Audit helper (delegates to tamper-evident MOD audit) ──────────────
async def _audit(site_id: str, user: dict, action: str, *, target_id: Optional[str] = None,
                 request: Optional[Request] = None, **payload) -> None:
    try:
        from utils.mod_audit import audit_event
        ip = None
        ua = None
        if request is not None:
            try:
                ip = request.client.host if request.client else None
                ua = request.headers.get("user-agent")
            except Exception:
                pass
        await audit_event(site_id=site_id, action=action, user=user,
                          target_type="aser", target_id=target_id, payload=payload, ip=ip, user_agent=ua)
    except Exception as e:  # pragma: no cover
        logger.warning("ASER audit failed: %s", e)


# ══════════════════════════════════════════════════════════════════
#                 NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════
async def _site_manager_emails(site_id: str) -> list[str]:
    users = await db.users.find(
        {"organization_id": site_id, "role": {"$in": ["owner", "manager"]}, "active": {"$ne": False}},
        {"_id": 0, "email": 1},
    ).to_list(50)
    emails = [u["email"] for u in users if u.get("email")]
    org = await db.organizations.find_one({"id": site_id}, {"_id": 0, "owner_email": 1})
    if org and org.get("owner_email"):
        emails.append(org["owner_email"])
    return emails


async def _notify_aser_created(entry: dict, settings: dict) -> None:
    """Fire configurable email notifications for a new ASER entry. Never
    blocks the request — failures are swallowed and logged."""
    try:
        from utils.email import send_email
        notif = settings.get("notifications") or {}
        sm = notif.get("site_manager") or {}
        sd = notif.get("service_desk") or {}
        am = notif.get("account_manager") or {}

        rating = (entry.get("risk") or {}).get("rating")
        is_high = rating in ("high", "critical")
        is_removed = entry.get("equipment_status") in REMOVAL_FLAG_STATUSES
        rep = (entry.get("repeated_issue") or {}).get("label") in {
            "repeated_issue", "escalation_recommended",
            "replacement_evidence_building", "replacement_strongly_recommended"}
        aser_90 = (entry.get("repeated_issue") or {}).get("aser_90d", 0) or 0
        is_repeated = rep and aser_90 >= (settings.get("repeated_issue_threshold", 2) or 2)
        is_capex = bool(entry.get("capex_flagged"))

        recipients: set[str] = set()
        # Site managers
        if sm.get("on_new") or (is_high and sm.get("on_high_critical")) or \
           (is_removed and sm.get("on_removed")) or (is_repeated and sm.get("on_repeated")) or \
           (is_capex and sm.get("on_capex")):
            for e in await _site_manager_emails(entry["site_id"]):
                recipients.add(e)
        # Service desk
        if sd.get("enabled") and sd.get("email") and (
                (is_high and sd.get("on_high_critical")) or (is_repeated and sd.get("on_repeated"))):
            recipients.add(sd["email"])
        # Account manager
        if am.get("enabled") and am.get("email") and (
                (is_repeated and am.get("on_repeated")) or (is_capex and am.get("on_capex"))):
            recipients.add(am["email"])

        if not recipients:
            return

        snap = entry.get("equipment_snapshot") or {}
        ai = entry.get("activity_impact") or {}
        flags = []
        if is_high:
            flags.append(f"<b>{rating.title()} risk</b>")
        if is_removed:
            flags.append("<b style='color:#b91c1c'>Equipment flagged for removal</b>")
        if is_repeated:
            flags.append("<b>Repeated issue</b>")
        if is_capex:
            flags.append("CAPEX evidence flagged")
        subject = f"[ASER {entry['aser_ref']}] {entry.get('title')}" + (" — HIGH RISK" if is_high else "")
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px">
          <h2 style="color:#0F1419;margin:0 0 4px">ASER — Activity Safety Event</h2>
          <p style="color:#6b7280;font-size:13px;margin:0 0 12px">{entry.get('site_name')} · {entry['aser_ref']}</p>
          <table style="font-size:13px;border-collapse:collapse;width:100%">
            <tr><td style="padding:4px 8px;color:#6b7280">Equipment</td><td style="padding:4px 8px"><b>{snap.get('name') or '-'}</b> ({snap.get('serial_number') or '-'})</td></tr>
            <tr><td style="padding:4px 8px;color:#6b7280">Event</td><td style="padding:4px 8px">{(entry.get('event_type') or '').replace('_',' ').title()}</td></tr>
            <tr><td style="padding:4px 8px;color:#6b7280">Risk</td><td style="padding:4px 8px">{(rating or '').title()}</td></tr>
            <tr><td style="padding:4px 8px;color:#6b7280">Rehab sessions impacted</td><td style="padding:4px 8px">{ai.get('sessions_affected', 0)}</td></tr>
            <tr><td style="padding:4px 8px;color:#6b7280">Equipment status</td><td style="padding:4px 8px">{(entry.get('equipment_status') or '').replace('_',' ').title()}</td></tr>
          </table>
          <p style="font-size:13px;color:#111827;margin:12px 0">{entry.get('description','')}</p>
          {('<p style="font-size:13px">' + ' · '.join(flags) + '</p>') if flags else ''}
          <p style="font-size:11px;color:#9ca3af;margin-top:16px">MOD Service Portal · ASER register. Do not reply — manage this entry in the portal.</p>
        </div>"""
        for rcpt in sorted(recipients):
            try:
                await send_email(rcpt, subject, html, kind="mod_aser_alert",
                                 organization_id=entry.get("site_id"))
            except Exception as e:
                logger.warning("ASER notify send failed for %s: %s", rcpt, e)
    except Exception as e:  # pragma: no cover
        logger.warning("ASER notify failed: %s", e)


# ══════════════════════════════════════════════════════════════════
#                 MASTER ADMIN — SETTINGS
# ══════════════════════════════════════════════════════════════════
def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Master admin only")


@router.get("/master-admin/aser/settings")
async def aser_get_settings(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    return await _load_settings()


@router.put("/master-admin/aser/settings")
async def aser_put_settings(body: dict = Body(...), user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    merged = _merge_settings(body)
    merged["id"] = "global"
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()
    merged["updated_by"] = user.get("email")
    await db.aser_settings.update_one({"id": "global"}, {"$set": merged}, upsert=True)
    return {"ok": True, "settings": merged}
