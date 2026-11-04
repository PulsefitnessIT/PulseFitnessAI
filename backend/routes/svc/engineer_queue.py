"""
Pulse Fitness Service Operations — Engineer Self-Allocation Queue.

Iter 216h147 (Phase 5 follow-on).
Iter 216h150 — "Nearest to me" haversine sort (Feb 2026).

Lets a field engineer see all unassigned org-wide jobs and atomically
self-claim one without a dispatcher. Race-safe via Mongo
`find_one_and_update` with `assigned_engineer_id == null` precondition,
so two engineers can never grab the same job.

Endpoints (gated by `require_engineer_app_access`):
  GET  /api/svc/engineer/queue/unassigned       — list jobs needing an engineer
  GET  /api/svc/engineer/queue/stats            — quick stat strip (open / risk / today)
  POST /api/svc/engineer/queue/{case_id}/claim  — atomically assign to caller
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access, require_engineer_compliance_to_claim
from routes.svc.integrations import sicon_sync
from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db
from utils.esp_engineer import BFPO_ORG_ID, esp_site_ids, is_external_engineer
from utils.postcodes_client import lookup as postcode_lookup, normalise_postcode
from utils.svc_state import (
    ASSIGNED, OPEN_STATES, TERMINAL_STATES, NEW, TRIAGED, append_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer/queue",
    tags=["Service Ops · Engineer Queue"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _unassigned_query(org_id: str) -> dict:
    """An 'unassigned' job is one that's still open (per the canonical
    state machine — see `utils.svc_state.OPEN_STATES`) and has no
    engineer assigned. Iter 216h151 — uses real state names instead of
    the previous literal `["closed", "invoiced", "cancelled", "void"]`
    which referenced states that don't exist in this state machine and
    would let `rejected` cases leak into the queue."""
    return {
        "organization_id": org_id,
        "status": {"$in": list(OPEN_STATES)},
        "$or": [
            {"assigned_engineer_id": {"$in": [None, ""]}},
            {"assigned_engineer_id": {"$exists": False}},
        ],
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points, in kilometres."""
    R = 6371.0088  # mean Earth radius (km)
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Field-service mixed-route average for UK engineers (motorway + town
# centre, depot stops, parking). Conservative on purpose — engineers
# under-promise & over-deliver. Round ETA to 5-min increments so the
# UI doesn't pretend to a precision haversine can't justify.
ETA_AVG_KMH = 50.0


def _eta_minutes_from_km(km: float | None) -> int | None:
    if km is None:
        return None
    raw = (km / ETA_AVG_KMH) * 60.0
    rounded = max(5, int(round(raw / 5.0)) * 5)  # never show < 5 min
    return rounded


async def _resolve_postcode_coords(postcode: str) -> tuple[float, float] | None:
    """postcodes.io → (lat, lon), or None. Cached upstream for 24h."""
    norm = normalise_postcode(postcode)
    if not norm:
        return None
    result = await postcode_lookup(norm)
    if not result:
        return None
    lat = result.get("latitude")
    lon = result.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


async def _job_coords(job: dict) -> tuple[float, float] | None:
    """Best-effort coords for a case: prefer cached lat/lon on the doc,
    else resolve from `site_postcode` via postcodes.io."""
    lat = job.get("site_latitude")
    lon = job.get("site_longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            pass
    pc = job.get("site_postcode")
    if pc:
        return await _resolve_postcode_coords(pc)
    return None


async def _esp_site_jobs(user: dict, priority: Optional[str], limit: int, *, unassigned_only: bool) -> dict:
    """ESP engineers: open MOD faults on the sites their provider services."""
    sites = await esp_site_ids(user)
    if not sites:
        return {"jobs": [], "count": 0, "territories": []}
    q: dict = {"organization_id": {"$in": [BFPO_ORG_ID, *sites]}, "status": {"$in": list(OPEN_STATES)},
               "$or": [{"site_id": {"$in": sites}}, {"organization_id": {"$in": sites}}]}
    if unassigned_only:
        q["assigned_engineer_id"] = {"$in": [None, ""]}
    else:
        q["assigned_engineer_id"] = {"$in": [None, "", user["id"]]}
    if priority:
        q["priority"] = priority.lower()
    rows = await db.svc_cases.find(q, {
        "_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1, "status": 1, "site_name": 1,
        "site_postcode": 1, "customer_name": 1, "scheduled_at": 1, "sla_resolve_at": 1, "estimated_minutes": 1,
        "intake_channel": 1, "description": 1, "created_at": 1, "assigned_engineer_id": 1,
        "assigned_engineer_name": 1}).sort([("priority", 1), ("created_at", -1)]).limit(limit).to_list(limit)
    names = {o["id"]: o.get("name") async for o in db.organizations.find({"id": {"$in": sites}}, {"_id": 0, "id": 1, "name": 1})}
    return {"jobs": rows, "count": len(rows), "sort": "default", "origin_source": None,
            "territories": [{"id": s, "name": names.get(s) or "MOD site"} for s in sites]}


@router.get("/unassigned")
async def list_unassigned(
    priority: Optional[str] = Query(None, description="P1|P2|P3|P4 — optional filter"),
    limit: int = Query(100, ge=1, le=500),
    sort: Optional[str] = Query(
        None, description="If 'nearest', sort by haversine distance "
                          "(requires lat+lon or postcode).",
    ),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    postcode: Optional[str] = Query(None, max_length=16,
                                    description="Fallback UK postcode for distance origin"),
    user=Depends(get_current_user),
):
    of = _of(user)
    if is_external_engineer(user):
        return await _esp_site_jobs(user, priority, limit, unassigned_only=True)
    q = _unassigned_query(of["organization_id"])
    if priority:
        q["priority"] = priority.upper()
    rows = await db.svc_cases.find(
        q,
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
         "status": 1, "site_name": 1, "site_postcode": 1,
         "site_latitude": 1, "site_longitude": 1, "customer_name": 1,
         "scheduled_at": 1, "sla_resolve_at": 1, "estimated_minutes": 1,
         "intake_channel": 1, "description": 1, "created_at": 1},
    ).sort([("priority", 1), ("sla_resolve_at", 1), ("created_at", -1)]) \
     .limit(limit).to_list(limit)

    origin: tuple[float, float] | None = None
    origin_source: Optional[str] = None
    if sort == "nearest":
        if lat is not None and lon is not None:
            origin = (float(lat), float(lon))
            origin_source = "geolocation"
        elif postcode:
            origin = await _resolve_postcode_coords(postcode)
            if origin:
                origin_source = "postcode"

    if origin:
        ox, oy = origin
        for r in rows:
            coords = await _job_coords(r)
            if coords:
                d = _haversine_km(ox, oy, coords[0], coords[1])
                # round to 1 decimal — engineers don't care about 50m precision
                r["distance_km"] = round(d, 1)
                r["eta_minutes"] = _eta_minutes_from_km(d)
            else:
                r["distance_km"] = None
                r["eta_minutes"] = None
        # Sort by distance asc; jobs without coords go last while preserving
        # the original priority/SLA tiebreak.
        rows.sort(key=lambda j: (j.get("distance_km") is None,
                                 j.get("distance_km") if j.get("distance_km") is not None else 0))

    return {
        "jobs": rows,
        "count": len(rows),
        "sort": "nearest" if origin else "default",
        "origin_source": origin_source,
    }


@router.get("/territory")
async def list_territory(
    priority: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    user=Depends(get_current_user),
):
    """All open cases logged in the engineer's AREA — i.e. cases whose linked
    CRM company sits in a territory the engineer is an assigned rep on. Unlike
    ``/unassigned`` this returns everything in the patch (assigned or not), so
    the engineer sees their territory's full workload. CRM territories are
    Pulse-only, so this naturally returns nothing for non-Pulse tenants."""
    of = _of(user)
    org_id = of["organization_id"]
    if is_external_engineer(user):
        return await _esp_site_jobs(user, priority, limit, unassigned_only=False)

    candidate_ids: set[str] = set()
    if user.get("id"):
        candidate_ids.add(user["id"])
    email = (user.get("email") or "").strip().lower()
    if email:
        async for cu in db.crm_users.find(
            {"organization_id": org_id, "email": email}, {"_id": 0, "id": 1},
        ):
            candidate_ids.add(cu["id"])
    if not candidate_ids:
        return {"jobs": [], "count": 0, "territories": []}

    terrs = await db.crm_territories.find(
        {"organization_id": org_id,
         "assigned_rep_ids": {"$in": list(candidate_ids)},
         "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "postcode_prefixes": 1},
    ).to_list(200)
    terr_list = [{"id": t["id"], "name": t.get("name") or "Territory"} for t in terrs]
    terr_ids = [t["id"] for t in terrs]
    if not terr_ids:
        return {"jobs": [], "count": 0, "territories": []}

    company_ids = [
        c["id"] async for c in db.crm2_companies.find(
            {"organization_id": org_id, "territory_id": {"$in": terr_ids}},
            {"_id": 0, "id": 1})
    ]

    proj = {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
            "status": 1, "site_name": 1, "site_postcode": 1,
            "customer_name": 1, "scheduled_at": 1, "sla_resolve_at": 1,
            "estimated_minutes": 1, "intake_channel": 1, "description": 1,
            "created_at": 1, "assigned_engineer_id": 1, "assigned_engineer_name": 1}

    rows: list[dict] = []
    if company_ids:
        q = {
            "organization_id": org_id,
            "company_id": {"$in": company_ids},
            "status": {"$in": list(OPEN_STATES)},
        }
        if priority:
            q["priority"] = priority.upper()
        rows = await db.svc_cases.find(q, proj).sort(
            [("priority", 1), ("sla_resolve_at", 1), ("created_at", -1)]
        ).limit(limit).to_list(limit)

    # Fallback — open cases in the engineer's postcode AREA that aren't linked
    # to an in-territory CRM company yet (e.g. a job just logged in the app).
    # Matched by the case's site_postcode outward code against the engineer's
    # territory postcode prefixes.
    prefixes = {p.upper().strip() for t in terrs for p in (t.get("postcode_prefixes") or []) if p}
    if prefixes and len(rows) < limit:
        from routes.crm_territories import _postcode_prefix
        seen = {r["id"] for r in rows}
        cand = await db.svc_cases.find(
            {"organization_id": org_id,
             "status": {"$in": list(OPEN_STATES)},
             "site_postcode": {"$nin": [None, ""]},
             "id": {"$nin": list(seen)}},
            proj,
        ).sort([("priority", 1), ("sla_resolve_at", 1), ("created_at", -1)]).limit(400).to_list(400)
        for c in cand:
            pc = _postcode_prefix(c.get("site_postcode") or "")
            if pc and any(pc.startswith(p) for p in prefixes):
                c["unlinked_area"] = True
                rows.append(c)
                if len(rows) >= limit:
                    break

    return {"jobs": rows, "count": len(rows), "territories": terr_list}


# ─────────────────────────────────────────────────────────────────
# Iter 220dc — "Nearest of MY jobs today" for the engineer home
# screen. Different from /unassigned (which is up-for-grabs) — this
# is the engineer's OWN open assignments sorted by distance from
# where they actually are right now.
# ─────────────────────────────────────────────────────────────────
@router.get("/my-nearest")
async def my_nearest_jobs(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    postcode: Optional[str] = Query(None, max_length=16),
    limit: int = Query(5, ge=1, le=20),
    user=Depends(get_current_user),
):
    """Return the engineer's open jobs sorted by distance from
    ``(lat, lon)`` (or ``postcode``). Falls back to scheduled-time
    order when neither origin is provided.

    Response: ``{nearest, jobs[], origin_source}``. ``jobs[]`` is the
    full list (cap = ``limit``); ``nearest`` is the top result for
    one-tap navigation from the home strip.
    """
    of = _of(user)
    # Engineer's open assignments — today and any in-flight scheduled
    # work. We pull a small superset (limit*3, capped at 30) and re-sort.
    rows = await db.svc_cases.find(
        {
            **of,
            "assigned_engineer_id": user["id"],
            "status": {"$in": list(OPEN_STATES)},
        },
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
            "status": 1, "site_name": 1, "site_address": 1,
            "site_postcode": 1, "site_latitude": 1, "site_longitude": 1,
            "customer_name": 1, "scheduled_at": 1, "estimated_minutes": 1,
        },
    ).sort([("scheduled_at", 1)]).limit(min(30, limit * 3)).to_list(30)

    origin: tuple[float, float] | None = None
    origin_source: Optional[str] = None
    if lat is not None and lon is not None:
        origin = (float(lat), float(lon))
        origin_source = "geolocation"
    elif postcode:
        origin = await _resolve_postcode_coords(postcode)
        if origin:
            origin_source = "postcode"

    if origin:
        ox, oy = origin
        for r in rows:
            coords = await _job_coords(r)
            if coords:
                d = _haversine_km(ox, oy, coords[0], coords[1])
                r["distance_km"] = round(d, 1)
                r["eta_minutes"] = _eta_minutes_from_km(d)
            else:
                r["distance_km"] = None
                r["eta_minutes"] = None
        rows.sort(key=lambda j: (
            j.get("distance_km") is None,
            j.get("distance_km") if j.get("distance_km") is not None else 0,
        ))

    rows = rows[:limit]
    return {
        "nearest": rows[0] if rows else None,
        "jobs": rows,
        "count": len(rows),
        "origin_source": origin_source,
        "sort": "nearest" if origin else "scheduled",
    }


@router.get("/stats")
async def queue_stats(user=Depends(get_current_user)):
    of = _of(user)
    base = _unassigned_query(of["organization_id"])
    total = await db.svc_cases.count_documents(base)
    today = datetime.now(timezone.utc).date().isoformat()
    risk_cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    risk_cutoff_iso = risk_cutoff.isoformat()
    risk = await db.svc_cases.count_documents({
        **base, "sla_resolve_at": {"$lt": risk_cutoff_iso},
    })
    p1 = await db.svc_cases.count_documents({**base, "priority": "P1"})
    return {"total": total, "p1": p1, "sla_breached_or_due": risk, "date": today}


class ClaimIn(BaseModel):
    scheduled_at: Optional[str] = Field(
        None, description="Optional ISO datetime — when you plan to start"
    )
    estimated_minutes: Optional[int] = Field(None, ge=15, le=600)


@router.get("/my-gyms")
async def my_gyms_queue(user=Depends(get_current_user)):
    """Iter 220p — "My gyms" queue for Partner Engineers.

    Returns open supplier_cases the engineer has been dispatched to —
    i.e. faults from the gyms they referred (auto-attached as primary
    supplier on signup, iter 220n) plus any gym that has explicitly
    added them as a supplier afterwards.

    Joins:
      * `partner_engineers` (via user_id) → partner_engineer.id
      * `suppliers`   (partner_engineer_id == partner.id) → list of
        gyms where this engineer is the dispatched supplier
      * `supplier_cases` (issue_id linked, supplier_email match) →
        the actual jobs

    Distinct from the org-wide `/queue/unassigned` flow — those are
    cases the engineer has an authenticated org-membership for. My-gyms
    cases come in via the public supplier-portal token flow (the
    engineer isn't actually a user of the gym's org).

    Response shape mirrors `/queue/unassigned` `jobs[]` as closely as
    possible so the same row component can render both lists.
    """
    # 1. Resolve this engineer's partner record. If they're not a
    #    Partner Engineer, return an empty list — non-fatal.
    partner = await db.partner_engineers.find_one(
        {"user_id": user["id"]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1},
    )
    if not partner:
        return {"jobs": [], "total": 0, "is_partner_engineer": False}

    # 2. Find every gym this engineer is the auto-dispatch supplier for.
    supplier_rows = await db.suppliers.find(
        {"partner_engineer_id": partner["id"]},
        {"_id": 0, "id": 1, "organization_id": 1, "name": 1, "email": 1,
         "is_primary_supplier": 1, "auto_created_from_referral": 1},
    ).to_list(500)
    if not supplier_rows:
        return {"jobs": [], "total": 0, "is_partner_engineer": True,
                "no_gyms_yet": True}

    org_ids = sorted({r["organization_id"] for r in supplier_rows if r.get("organization_id")})
    supplier_org_by_name = {r["name"]: r["organization_id"] for r in supplier_rows if r.get("name")}

    # 3. Query the engineer's open supplier_cases. Filter:
    #    - supplier_email == engineer.email (covers cases dispatched
    #      before the partner_engineer_id link was stable too), AND
    #    - status open (not closed/resolved).
    open_statuses = ["new", "in_progress", "awaiting_parts", "scheduled",
                     "awaiting_customer", "viewed"]
    sc_filter = {
        "supplier_email": partner.get("email"),
        "status": {"$in": open_statuses},
    }
    supplier_cases = await db.supplier_cases.find(
        sc_filter,
        {"_id": 0, "id": 1, "token": 1, "issue_id": 1, "supplier_email": 1,
         "organization_name": 1, "status": 1, "created_at": 1,
         "title": 1, "priority": 1, "machine_name": 1, "equipment_name": 1,
         "sla_resolve_at": 1, "site_id": 1, "site_name": 1},
        sort=[("created_at", -1)],
    ).to_list(500)

    # 4. Decorate each row with provenance flags so the UI can render
    #    the "Auto-referred gym" badge on the row.
    jobs = []
    for sc in supplier_cases:
        org_name = sc.get("organization_name") or ""
        sup_row = next((r for r in supplier_rows
                        if (r.get("name") or "") == org_name
                        or r.get("organization_id") == supplier_org_by_name.get(org_name)),
                       None) or {}
        jobs.append({
            "id": sc.get("id"),
            "supplier_case_token": sc.get("token"),
            "issue_id": sc.get("issue_id"),
            "title": sc.get("title") or sc.get("equipment_name") or "Service request",
            "priority": sc.get("priority") or "P3",
            "status": sc.get("status"),
            "created_at": sc.get("created_at"),
            "sla_resolve_at": sc.get("sla_resolve_at"),
            "organization_name": org_name,
            "site_name": sc.get("site_name"),
            "machine_name": sc.get("machine_name") or sc.get("equipment_name"),
            "from_referred_gym": bool(sup_row.get("auto_created_from_referral")),
            "is_primary_supplier": bool(sup_row.get("is_primary_supplier")),
        })

    return {
        "jobs": jobs,
        "total": len(jobs),
        "gyms_count": len(org_ids),
        "is_partner_engineer": True,
    }


# Iter 220cj — Preview an unassigned job before claiming it.
# Returns the case fields the engineer cares about + related site
# equipment + any existing quote value so they can decide.


def _unassigned_filter(org_id: str) -> dict:
    return _unassigned_query(org_id)


@router.get("/{case_id}/preview")
async def preview_unassigned_case(case_id: str, user=Depends(get_current_user)):
    """Read-only preview of an *unassigned* job in the engineer's org.

    Surfaces enough context for the engineer to decide whether to claim:
    site name + address, asset summary, fault description, SLA timer,
    photo/attachment count, related site-equipment lines, and the
    potential value (open quote total) when one is on file.

    Hardening: only returns cases that match ``_unassigned_query`` — an
    already-claimed case 404s so engineers can't preview each other's
    work via this endpoint.
    """
    of = _of(user)
    # Re-use the same precondition as the queue list so the access
    # surface is identical: org scope + assigned_engineer_id is null +
    # status in OPEN_STATES.
    flt = {**_unassigned_filter(of["organization_id"]), "id": case_id}
    case = await db.svc_cases.find_one(
        flt,
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
            "status": 1, "description": 1,
            "site_id": 1, "site_name": 1, "site_address": 1,
            "site_postcode": 1, "site_latitude": 1, "site_longitude": 1,
            "customer_id": 1, "customer_name": 1, "customer_email": 1,
            "customer_phone": 1, "asset_id": 1, "asset_name": 1,
            "asset_serial": 1, "fault_code": 1,
            "scheduled_at": 1, "sla_resolve_at": 1, "estimated_minutes": 1,
            "intake_channel": 1, "created_at": 1, "tags": 1,
        },
    )
    if not case:
        raise HTTPException(404, "Job not found")

    # ── Related equipment for the case's site (or asset_id fallback) ──
    eq_filter: dict = {"organization_id": of["organization_id"]}
    if case.get("site_id"):
        eq_filter["site_id"] = case["site_id"]
    elif case.get("asset_id"):
        eq_filter["id"] = case["asset_id"]
    site_equipment: list[dict] = []
    if "site_id" in eq_filter or "id" in eq_filter:
        site_equipment = (
            await db.equipment.find(
                eq_filter,
                {
                    "_id": 0, "id": 1, "name": 1, "equipment_type": 1,
                    "manufacturer": 1, "model": 1, "serial_number": 1,
                    "location": 1, "status": 1,
                },
            )
            .sort([("equipment_type", 1), ("name", 1)])
            .limit(50)
            .to_list(50)
        )

    # ── Potential value: latest open quote on this case ──
    potential_value: Optional[dict] = None
    try:
        quote = await db.engineer_quotes.find_one(
            {
                **of, "case_id": case_id,
                "status": {"$in": ["draft", "sent", "accepted"]},
            },
            {"_id": 0, "id": 1, "status": 1, "total": 1, "currency": 1},
            sort=[("created_at", -1)],
        )
        if quote and quote.get("total") is not None:
            potential_value = {
                "total": float(quote.get("total") or 0),
                "currency": quote.get("currency") or "GBP",
                "quote_status": quote.get("status"),
                "quote_id": quote.get("id"),
            }
    except Exception:  # noqa: BLE001 — analytics-only, never break preview
        potential_value = None

    # ── Attachment + photo counters ──
    photos_count = await db.svc_engineer_photos.count_documents(
        {**of, "case_id": case_id},
    )
    events_count = await db.svc_case_events.count_documents(
        {**of, "case_id": case_id},
    )

    return {
        "case": case,
        "site_equipment": site_equipment,
        "site_equipment_count": len(site_equipment),
        "photos_count": photos_count,
        "events_count": events_count,
        "potential_value": potential_value,
    }


@router.post("/{case_id}/claim", dependencies=[Depends(require_engineer_compliance_to_claim)])
async def claim_case(
    case_id: str,
    body: ClaimIn = Body(default_factory=ClaimIn),
    user=Depends(get_current_user),
):
    of = _of(user)
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], **of}, {"_id": 0, "id": 1, "full_name": 1},
    )
    if not eng:
        raise HTTPException(403, "Engineer profile required to claim jobs")
    if is_external_engineer(user):
        sites = await esp_site_ids(user)
        if not await db.svc_cases.count_documents(
                {"id": case_id, "$or": [{"site_id": {"$in": sites}}, {"organization_id": {"$in": sites}}]}):
            raise HTTPException(404, "Job not found")
    if body.scheduled_at:
        try:
            datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "scheduled_at must be ISO datetime")

    upd = {
        "assigned_engineer_id": user["id"],
        "assigned_engineer_name": eng.get("full_name"),
        "self_claimed_at": _now(),
        "updated_at": _now(),
    }
    if body.scheduled_at:
        upd["scheduled_at"] = body.scheduled_at
    if body.estimated_minutes:
        upd["estimated_minutes"] = body.estimated_minutes

    # Race-safe: only assign if still unassigned **and** in an open state.
    # Iter 216h151 — uses canonical OPEN_STATES + a Mongo aggregation
    # pipeline update so we can transition status → ASSIGNED in the same
    # atomic operation. NEW/TRIAGED → ASSIGNED; already-ASSIGNED stays
    # ASSIGNED (state machine permits ASSIGNED→ASSIGNED for re-claim).
    result = await db.svc_cases.find_one_and_update(
        {
            "id": case_id, **of,
            "status": {"$in": list(OPEN_STATES)},
            "$or": [
                {"assigned_engineer_id": {"$in": [None, ""]}},
                {"assigned_engineer_id": {"$exists": False}},
            ],
        },
        [
            {"$set": {
                **upd,
                "prev_status": "$status",
                "status": {
                    "$cond": [
                        {"$in": ["$status", [NEW, TRIAGED]]},
                        ASSIGNED,
                        "$status",
                    ],
                },
            }},
        ],
        projection={"_id": 0, "id": 1, "reference": 1, "title": 1,
                    "site_name": 1, "scheduled_at": 1, "priority": 1,
                    "status": 1, "prev_status": 1},
        return_document=True,  # equivalent of pymongo ReturnDocument.AFTER → True
    )
    if not result:
        # Could be: not found, already claimed, or closed.
        existing = await db.svc_cases.find_one(
            {"id": case_id, **of},
            {"_id": 0, "assigned_engineer_id": 1, "status": 1, "reference": 1,
             "assigned_engineer_name": 1},
        )
        if not existing:
            raise HTTPException(404, "Job not found")
        if existing.get("status") in TERMINAL_STATES:
            raise HTTPException(409, {"code": "closed",
                                      "detail": f"Job is {existing['status']}"})
        raise HTTPException(409, {
            "code": "already_claimed",
            "detail": f"Already claimed by {existing.get('assigned_engineer_name') or 'another engineer'}",
            "reference": existing.get("reference"),
        })

    # Strip the temporary `prev_status` field from the persisted doc and
    # record a timeline event if we actually moved state. We unset
    # `prev_status` *after* the read so the caller can see what happened.
    prev = result.pop("prev_status", None)
    if prev and prev != result.get("status"):
        await db.svc_cases.update_one(
            {"id": case_id, **of}, {"$unset": {"prev_status": ""}},
        )
        try:
            await append_event(
                case_id=case_id,
                organization_id=of["organization_id"],
                event_type="state_change",
                actor=user,
                body=f"Self-claimed by {eng.get('full_name') or user.get('email')}",
                extra={"from_state": prev, "to_state": result.get("status"),
                       "via": "self_claim"},
            )
        except Exception:
            pass
    else:
        # Status was already ASSIGNED — still record the claim itself for audit.
        await db.svc_cases.update_one(
            {"id": case_id, **of}, {"$unset": {"prev_status": ""}},
        )
        try:
            await append_event(
                case_id=case_id,
                organization_id=of["organization_id"],
                event_type="self_claim",
                actor=user,
                body=f"Re-claimed by {eng.get('full_name') or user.get('email')}",
                extra={"via": "self_claim"},
            )
        except Exception:
            pass

    # Fire an in-app notification to the claimer themselves so it
    # surfaces in the bell badge ("you took job X"). Best-effort.
    try:
        from routes.svc.notifications import create_notification
        await create_notification(
            user_id=user["id"],
            organization_id=of["organization_id"],
            kind="job_self_claimed",
            title=f"Claimed: {result.get('reference')} · {result.get('title') or ''}",
            body=(result.get("site_name") or "Site TBC") +
                 (f" — scheduled {result['scheduled_at'][:16]}" if result.get("scheduled_at") else ""),
            link=f"/svc/engineer/jobs/{case_id}",
            source_type="case",
            source_id=case_id,
            fire_push=False,  # no need to push to the engineer's own device — they just tapped it
        )
    except Exception:
        pass

    # Iter 216h153 — Sicon outbox push so the upstream service-call
    # record reflects the new engineer + status. Re-read the full doc
    # so the payload mapper has every field (the `result` projection
    # is intentionally lean for the API response).
    try:
        full_case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
        if full_case:
            await sicon_sync.push_case(full_case)
            if prev and prev != result.get("status"):
                last_evt = await db.svc_case_events.find_one(
                    {"case_id": case_id, "type": "state_change"},
                    sort=[("at", -1)], projection={"_id": 0},
                )
                if last_evt:
                    await sicon_sync.push_event(
                        last_evt, case_reference=full_case.get("reference"),
                    )
    except Exception as e:
        logger.warning("[svc→sicon] self-claim push failed: %s", e)

    # Iter 216h155 — compliance audit for self-claim.
    try:
        await audit_log(
            action="svc.case.self_claim",
            user_id=user.get("id", ""),
            user_email=user.get("email", ""),
            resource_type="svc_case",
            resource_id=case_id,
            details=f"{result.get('reference', '')} claimed"
                    + (f" (status {prev}→{result.get('status')})"
                       if prev and prev != result.get("status") else ""),
        )
    except Exception as e:
        logger.warning("[audit] self_claim failed: %s", e)

    return {"ok": True, "case_id": case_id, "reference": result.get("reference"),
            "scheduled_at": result.get("scheduled_at")}


__all__ = ["router"]
