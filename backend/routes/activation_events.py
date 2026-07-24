"""Activation-event capture & funnel reporting.

Why: today we know how many trials we have but not what they DO. A trial
that uploaded 5 pieces of equipment and took its first booking by day 3
converts to paid 4× more than a trial that only logged in. Capturing
explicit activation events gives us:

  • A real conversion funnel per cohort.
  • A "magic moment" threshold to push customers toward.
  • A leading indicator of churn ("this org hasn't fired any activation
    event in 7 days").

Schema (`activation_events`)
==========================
::

    {
        "id":              uuid,
        "organization_id": str,
        "event_type":      "first_login" | "first_equipment_added" |
                           "first_member_added" | "first_booking_taken" |
                           "first_invoice_generated" | "first_staff_invited" |
                           "first_class_scheduled" | "module_activated",
        "occurred_at":     iso datetime,
        "trigger_user_id": str | null,
        "payload":         dict           # tiny, denormalised metadata
    }

Each event_type fires **only once per organisation** — duplicates are
silently ignored to keep the funnel honest.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


EVENT_TYPES = (
    # Universal — fire regardless of module mix.
    "first_login",
    "first_staff_invited",
    "module_activated",
    # Operations module
    "first_equipment_added",
    "first_fault_logged",
    # Memberships module
    "first_member_added",
    "first_booking_taken",
    "first_invoice_generated",
    "first_class_scheduled",
    # CRM module
    "first_lead_added",
    "first_deal_created",
    "first_quote_sent",
    # Marketing module
    "first_brand_discovered",
    "first_audience_built",
    "first_campaign_launched",
)

# Iter 216h216 — Craig's audit: "why do I need to add equipment if I
# chose the Memberships module?" The activation checklist now filters
# by what the org has actually switched on. Each event belongs to a
# module key (or "always" when it's universal across every trial).
#
# Iter 216h227 — Lee follow-up: marketing / CRM trials previously saw
# zero relevant milestones because no events were defined for those
# modules. New event types added below and wired into the matching
# route handlers so every module trial gets a tailored "first wins"
# list out of the box. Engineers / Staffing / Reporting aren't
# first-class module keys (see utils.module_access.MODULE_KEYS) so
# their would-be milestones fold into the four canonical modules.
EVENT_MODULES: dict[str, str] = {
    # Universal
    "first_login":              "always",
    "first_staff_invited":      "always",
    "module_activated":         "always",
    # Operations
    "first_equipment_added":    "operations",
    "first_fault_logged":       "operations",
    # Memberships (invoices today live in memberships)
    "first_member_added":       "memberships",
    "first_booking_taken":      "memberships",
    "first_invoice_generated":  "memberships",
    "first_class_scheduled":    "memberships",
    # CRM
    "first_lead_added":         "crm",
    "first_deal_created":       "crm",
    "first_quote_sent":         "crm",
    # Marketing
    "first_brand_discovered":   "marketing",
    "first_audience_built":     "marketing",
    "first_campaign_launched":  "marketing",
}


def _modules_enabled_for(user_or_org: dict) -> set[str]:
    """Return the set of module keys the org has enabled.

    Accepts either a `users` row (which carries the cached module_access)
    or an `organizations` row (which has the canonical `modules` map).
    Iter 216h227 — also reads list-form `enabled_modules` (trial
    signups stamp this so the activation filter sees the actual unlock
    set, not just the dict-form module_access map).
    """
    enabled: set[str] = set()
    # users row stores it as `module_access` (cached on login)
    mods = user_or_org.get("module_access") or user_or_org.get("modules") or {}
    if isinstance(mods, dict):
        for k, v in mods.items():
            if v:
                enabled.add(k)
    # Trial orgs persist their unlocked module list as a flat array.
    em = user_or_org.get("enabled_modules")
    if isinstance(em, (list, tuple, set)):
        for m in em:
            if m:
                enabled.add(str(m))
    # Full account types (account_type='full' / 'pulse_pro' / 'pro') have
    # everything enabled by default.
    acc = (user_or_org.get("account_type") or "").lower()
    if acc in {"full", "pro", "pulse_pro"}:
        enabled.update({"operations", "memberships", "service_desk", "crm", "marketing"})
    return enabled


def _primary_modules_for(user_or_org: dict) -> set[str]:
    """Modules the operator declared as their PRIMARY intent at signup.

    When set, the activation funnel narrows to JUST those + the
    `always` event types so a Marketing trial doesn't see "Add
    equipment" or "Take first booking" as suggested first wins
    (Lee's Feb 2026 audit). When unset, all enabled modules' events
    are surfaced — preserves behaviour for legacy / pre-existing orgs.
    """
    pm = user_or_org.get("primary_module")
    if isinstance(pm, str) and pm.strip():
        return {pm.strip().lower()}
    if isinstance(pm, (list, tuple, set)):
        return {str(m).strip().lower() for m in pm if m and str(m).strip()}
    return set()

# Friendly labels surfaced in the UI funnel.
EVENT_LABELS: dict[str, str] = {
    "first_login":             "First login",
    "first_staff_invited":     "First staff member invited",
    "module_activated":        "First module switched on",
    "first_equipment_added":   "First piece of equipment added",
    "first_fault_logged":      "First fault logged",
    "first_member_added":      "First member added",
    "first_booking_taken":     "First booking taken",
    "first_invoice_generated": "First invoice generated",
    "first_class_scheduled":   "First class scheduled",
    "first_lead_added":        "First lead added",
    "first_deal_created":      "First deal created",
    "first_quote_sent":        "First quote sent",
    "first_brand_discovered":  "Brand discovery completed",
    "first_audience_built":    "First audience built",
    "first_campaign_launched": "First campaign launched",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Internal helper for in-process callers ──────────────────────────


async def record_activation_event(
    organization_id: str,
    event_type: str,
    *,
    trigger_user_id: str | None = None,
    payload: dict | None = None,
) -> bool:
    """Idempotent per (organization_id, event_type). Returns True if a row
    was inserted, False if the org has already fired this event before.

    Best-effort — never raises. Activation tracking must not gate primary
    workflows like creating equipment.
    """
    if event_type not in EVENT_TYPES:
        return False
    try:
        existing = await db.activation_events.find_one(
            {"organization_id": organization_id, "event_type": event_type},
            {"_id": 1},
        )
        if existing:
            return False
        await db.activation_events.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "event_type": event_type,
            "occurred_at": _iso_now(),
            "trigger_user_id": trigger_user_id,
            "payload": payload or {},
        })
        return True
    except Exception:
        logger.exception("activation_event insert failed for %s/%s", organization_id, event_type)
        return False


# ── Public endpoints ────────────────────────────────────────────────


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


@router.post("/activation/record")
async def record_event_endpoint(
    payload: dict,
    user: dict = Depends(get_current_user),
) -> dict:
    """Authenticated client-side hook. Operators (frontend) call this when
    a milestone happens (e.g. "first_member_added"). Resolves the
    organisation from the calling user.
    """
    org_id = user.get("organization_id")
    if not org_id:
        # Master admin / cross-org users have no single org — no-op.
        return {"recorded": False, "reason": "no_org"}
    event_type = (payload or {}).get("event_type")
    if event_type not in EVENT_TYPES:
        raise HTTPException(400, f"event_type must be one of {EVENT_TYPES}")
    inserted = await record_activation_event(
        org_id, event_type,
        trigger_user_id=user.get("id"),
        payload=(payload or {}).get("payload") or {},
    )
    return {"recorded": inserted}


MOD_MILESTONES_SITE = (
    ("mod_first_login",          "Signed in to the MOD Service Portal"),
    ("mod_equipment_registered", "Equipment register set up"),
    ("mod_first_fault_reported", "Reported your first equipment fault"),
    ("mod_first_incident_logged", "Logged your first incident report"),
    ("mod_staff_added",          "Added a site service contact"),
    ("mod_aser_submitted",       "Submitted an ASER return"),
    ("mod_compliance_scheduled", "Scheduled a compliance check"),
)


async def _mod_activation_timeline(org_id: str, account_type: str) -> dict:
    """Bespoke 'first wins' for MOD Service Portal users. Milestone state is
    derived from real MOD records for the caller's site, so it self-heals for
    existing data and needs no per-endpoint event wiring."""
    async def _exists(coll: str, query: dict) -> bool:
        return await db[coll].count_documents(query, limit=1) > 0

    checks = {
        # First login is implicit — they are authenticated to reach here.
        "mod_first_login": True,
        "mod_equipment_registered": await _exists("equipment", {"organization_id": org_id}),
        "mod_first_fault_reported": await _exists("issues", {"organization_id": org_id}),
        "mod_first_incident_logged": await _exists("mod_incidents", {"site_id": org_id}),
        "mod_staff_added": await _exists("mod_site_staff", {"site_id": org_id}),
        "mod_aser_submitted": await _exists("aser_entries", {"site_id": org_id}),
        "mod_compliance_scheduled": await _exists("mod_compliance_events", {"site_id": org_id}),
    }
    timeline = [
        {"event_type": et, "label": label, "fired": bool(checks.get(et)),
         "occurred_at": None, "module": "mod"}
        for et, label in MOD_MILESTONES_SITE
    ]
    fired_count = sum(1 for m in timeline if m["fired"])
    return {
        "timeline": timeline,
        "fired_count": fired_count,
        "total": len(timeline),
        "modules_enabled": ["mod"],
        "primary_module": "mod",
        "is_mod": True,
        "as_of": _iso_now(),
    }


@router.get("/activation/me")
async def activation_for_me(user: dict = Depends(get_current_user)) -> dict:
    """Operator-facing timeline — returns which milestones the caller's
    organisation has achieved. Master admins without an org return an
    empty timeline (they use `/master-admin/activation/funnel` instead).

    Iter 216h216 — filters the milestones to the modules the org has
    enabled. A Memberships-only org no longer sees "Add equipment" and
    a Operations-only org no longer sees "First class scheduled".
    """
    org_id = user.get("organization_id")
    if not org_id:
        return {"timeline": [], "fired_count": 0, "total": 0, "as_of": _iso_now()}

    # MOD (defence) organisations run the MOD Service Portal, not the gym
    # modules — their "first wins" are a bespoke timeline computed from real
    # MOD records (equipment register, faults, incidents, ASER, compliance).
    account_type = str(user.get("account_type") or "").lower()
    if account_type.startswith("mod_") or user.get("is_mod_user"):
        return await _mod_activation_timeline(org_id, account_type)

    # Resolve enabled modules from the user row first (cheap), fall
    # back to the org doc if missing. Iter 216h227 — also fetch
    # `primary_module` so the funnel can narrow to the intent module
    # the prospect chose at signup.
    enabled = _modules_enabled_for(user)
    primary = _primary_modules_for(user)
    if not enabled or not primary:
        org = await db.organizations.find_one(
            {"id": org_id},
            {"_id": 0, "modules": 1, "enabled_modules": 1,
             "account_type": 1, "primary_module": 1},
        )
        if org:
            if not enabled:
                enabled = _modules_enabled_for(org)
            if not primary:
                primary = _primary_modules_for(org)

    # When the operator declared a primary module at signup, the
    # funnel narrows to JUST that module's events. Otherwise the
    # full enabled set is used.
    focus = primary or enabled

    def _is_relevant(et: str) -> bool:
        mod = EVENT_MODULES.get(et, "always")
        if mod == "always":
            return True
        # Iter 216h227 — when we have NO module info at all (very old
        # orgs from before the modules schema landed), fall back to
        # the historical core set (operations + memberships) rather
        # than leaking every module's events.
        if not focus:
            return mod in {"operations", "memberships"}
        return mod in focus

    relevant = tuple(et for et in EVENT_TYPES if _is_relevant(et))

    rows = await db.activation_events.find(
        {"organization_id": org_id, "event_type": {"$in": list(relevant)}}, {"_id": 0},
    ).sort("occurred_at", 1).to_list(length=50)
    fired_set = {r["event_type"]: r["occurred_at"] for r in rows}
    timeline: list[dict[str, Any]] = []
    for et in relevant:
        timeline.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "fired": et in fired_set,
            "occurred_at": fired_set.get(et),
            "module": EVENT_MODULES.get(et, "always"),
        })
    return {
        "timeline": timeline,
        "fired_count": len(fired_set),
        "total": len(relevant),
        "modules_enabled": sorted(enabled),
        "primary_module": sorted(primary)[0] if len(primary) == 1 else (sorted(primary) or None),
        "as_of": _iso_now(),
    }


@router.get("/master-admin/activation/funnel")
async def activation_funnel(user: dict = Depends(get_current_user)) -> dict:
    """Aggregated funnel for the master admin dashboard.

    Returns one row per event_type with: total firings, % of orgs that
    have hit it, and the median time-from-signup-to-event in days.
    """
    _require_master(user)

    total_orgs = await db.organizations.count_documents({"portal_type": {"$ne": "crm"}})
    if total_orgs == 0:
        return {"steps": [], "total_orgs": 0, "as_of": _iso_now()}

    steps = []
    for et in EVENT_TYPES:
        # How many distinct orgs have ever fired this event?
        cnt = await db.activation_events.count_documents({"event_type": et})
        steps.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "orgs": cnt,
            "pct": round(cnt / total_orgs * 100, 1) if total_orgs else 0,
        })
    return {
        "steps": steps,
        "total_orgs": total_orgs,
        "as_of": _iso_now(),
    }


@router.get("/master-admin/activation/org/{org_id}")
async def activation_for_org(
    org_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Per-org checklist: which events have fired, when. Useful inside
    the org detail panel to spot stalled trials at a glance.
    """
    _require_master(user)
    rows = await db.activation_events.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("occurred_at", 1).to_list(length=50)
    fired_set = {r["event_type"]: r["occurred_at"] for r in rows}
    timeline: list[dict[str, Any]] = []
    for et in EVENT_TYPES:
        timeline.append({
            "event_type": et,
            "label": EVENT_LABELS.get(et, et),
            "fired": et in fired_set,
            "occurred_at": fired_set.get(et),
        })
    return {"timeline": timeline, "as_of": _iso_now()}


# ── Indexes ─────────────────────────────────────────────────────────


async def ensure_activation_indexes() -> None:
    try:
        await db.activation_events.create_index(
            [("organization_id", 1), ("event_type", 1)], unique=True,
        )
        await db.activation_events.create_index([("event_type", 1), ("occurred_at", -1)])
        await db.activation_events.create_index([("occurred_at", -1)])
    except Exception:
        logger.exception("ensure_activation_indexes failed (non-fatal)")
