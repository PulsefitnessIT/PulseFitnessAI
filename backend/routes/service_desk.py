"""Service Desk operational endpoints — customer management, audit, impersonation.

All mutating endpoints write a row to `service_desk_audit_log` via `log_desk_action`.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from utils.security_plus import safe_regex
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from utils.auth import create_token
from utils.database import db
from utils.service_desk_auth import (
    require_service_desk, log_desk_action,
    desk_scope_org_ids, assert_org_in_desk_scope, desk_provider_org_id,
)

router = APIRouter(prefix="/service-desk", tags=["Service Desk"])


# ── Dashboard / summary ──────────────────────────────────────────

@router.get("/summary")
async def desk_summary(user: dict = Depends(require_service_desk)) -> dict:
    """Top-level counters shown on the Service Desk landing page."""
    since_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    # Iter 253 — self-serve providers get THEIR desk's numbers (cases,
    # engineers, customers), never the platform customer-org estate.
    provider_org = await desk_provider_org_id(user)
    if provider_org:
        from utils.svc_state import OPEN_STATES
        return {
            "desk_kind": "provider",
            "provider": {
                "open_cases": await db.svc_cases.count_documents(
                    {"organization_id": provider_org, "status": {"$in": list(OPEN_STATES)}}),
                "total_cases": await db.svc_cases.count_documents(
                    {"organization_id": provider_org}),
                "engineers": await db.svc_engineers.count_documents(
                    {"organization_id": provider_org, "active": True}),
                "customers": await db.svc_engineer_customers.count_documents(
                    {"organization_id": provider_org}),
            },
            "recent_actions_7d": await db.service_desk_audit_log.count_documents(
                {"actor_org_id": provider_org, "timestamp": {"$gte": since_7d}}),
            "scoped_to_pulse": False,
        }
    scope = await desk_scope_org_ids(user)
    base: dict = {"id": {"$in": scope}} if scope is not None else {}
    orgs_total = await db.organizations.count_documents(base)
    orgs_active = await db.organizations.count_documents({**base, "status": {"$ne": "archived"}})
    orgs_pending = await db.organizations.count_documents({**base, "status": "pending_invite"})
    orgs_archived = await db.organizations.count_documents({**base, "status": "archived"})
    recent_actions = await db.service_desk_audit_log.count_documents({
        "timestamp": {"$gte": since_7d},
    })
    return {
        "desk_kind": "platform",
        "organizations": {
            "total": orgs_total, "active": orgs_active,
            "pending_invite": orgs_pending, "archived": orgs_archived,
        },
        "recent_actions_7d": recent_actions,
        "scoped_to_pulse": scope is not None,
    }


# ── Customer list ────────────────────────────────────────────────

def _build_customer_query(q: str, account_type: str, status: str) -> dict:
    query: dict = {}
    if q:
        query["$or"] = [
            {"name": safe_regex(q)},
            {"sicon_customer_ref": safe_regex(q)},
            {"head_office_ref": safe_regex(q)},
        ]
    if account_type:
        query["account_type"] = account_type
    if status:
        query["status"] = status
    return query


@router.get("/customers")
async def list_customers(
    q: str = "",
    account_type: str = "",
    status: str = "",
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Search + filter customer organisations. Billing/cost fields excluded."""
    query = _build_customer_query(q, account_type, status)
    # Iter 245 — pulse-brand agents see only Pulse-visible customer orgs.
    scope = await desk_scope_org_ids(user)
    if scope is not None:
        query["id"] = {"$in": scope}
    projection = {
        "_id": 0, "id": 1, "name": 1, "account_type": 1, "status": 1,
        "sicon_customer_ref": 1, "head_office_ref": 1, "is_multi_site": 1,
        "subscription_tier": 1, "primary_contact_email": 1,
        "onboarding_variant": 1, "created_at": 1, "last_activity_at": 1,
    }
    cursor = db.organizations.find(query, projection).sort("created_at", -1).skip(skip).limit(limit)
    orgs = await cursor.to_list(limit)
    total = await db.organizations.count_documents(query)
    return {"organizations": orgs, "total": total, "scoped_to_pulse": scope is not None}


# ── Global equipment search (Iter 216h49) ────────────────────────
#
# Pulse Fitness currently uses Sicon Service to look up "what's that
# treadmill in Carshalton" by serial number from a single search box.
# Service Desk gets feature parity here — one search across every org's
# equipment with org + site context surfaced inline.

@router.get("/equipment")
async def search_equipment_global(
    q: str = "",
    org_id: str = "",
    site_id: str = "",
    equipment_type: str = "",
    manufacturer: str = "",
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Global equipment search across every customer organisation.

    Service Desk feature-parity with Sicon Service. Filters all use AND.
    Returns equipment rows enriched with their parent org name + site name
    so the desk operator never has to drill into a customer to identify
    "which gym is this kit at".

    Args:
        q: free-text — matches name, model, manufacturer, serial number
        org_id: scope to one organisation
        site_id: scope to one site (org_id optional, but site is unique
                 per-org so usually paired)
        equipment_type / manufacturer: exact-match filters
        skip / limit: pagination
    """
    query: Dict[str, Any] = {}
    # Iter 245 — pulse-brand agents search only Pulse-visible orgs' kit.
    scope = await desk_scope_org_ids(user)
    if org_id:
        if scope is not None and org_id not in scope:
            raise HTTPException(status_code=404, detail="Organisation not found")
        query["organization_id"] = org_id
    elif scope is not None:
        query["organization_id"] = {"$in": scope}
    if site_id:
        query["site_id"] = site_id
    if equipment_type:
        query["equipment_type"] = equipment_type
    if manufacturer:
        query["manufacturer"] = manufacturer
    if q:
        # Mongo $or with case-insensitive regex. Anchored to be cheap on
        # short queries; Pulse has fewer than 100k equipment rows so a
        # collection scan is acceptable until a text index is justified.
        import re
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"name": rx}, {"model": rx}, {"manufacturer": rx},
            {"serial_number": rx}, {"equipment_type": rx},
        ]

    projection = {
        "_id": 0, "id": 1, "name": 1, "equipment_type": 1, "manufacturer": 1,
        "model": 1, "serial_number": 1, "location": 1, "site_id": 1,
        "organization_id": 1, "purchase_date": 1, "warranty_expiry": 1,
        "supplier": 1, "created_at": 1,
    }
    cursor = (
        db.equipment.find(query, projection)
        .sort("created_at", -1)
        .skip(max(0, int(skip)))
        .limit(min(200, max(1, int(limit))))
    )
    rows = await cursor.to_list(limit)
    total = await db.equipment.count_documents(query)

    # Hydrate org + site names in a single pass each to avoid N+1.
    org_ids = list({r.get("organization_id") for r in rows if r.get("organization_id")})
    site_ids = list({r.get("site_id") for r in rows if r.get("site_id")})
    orgs = {
        o["id"]: o.get("name", "")
        for o in await db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(org_ids) or 1)
    } if org_ids else {}
    sites = {
        s["id"]: s.get("name", "")
        for s in await db.sites.find(
            {"id": {"$in": site_ids}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(site_ids) or 1)
    } if site_ids else {}

    for r in rows:
        r["organization_name"] = orgs.get(r.get("organization_id"), "")
        r["site_name"] = sites.get(r.get("site_id"), "")

    await log_desk_action(
        user, "equipment.search", "equipment", "global",
        f"Equipment search: q={q!r}, results={len(rows)}",
        details={"q": q, "org_id": org_id, "site_id": site_id, "count": len(rows)},
    )

    return {"equipment": rows, "total": total}


# ── Cross-customer Supplier Health (Iter 216h52) ─────────────────
#
# GymAxis ops want a top-down view of how their supplier ecosystem
# is performing across every gym customer — which suppliers are
# servicing the most kit, who has open faults stacking up, who's
# blowing through SLAs. This drives renewal negotiations and lets
# GymAxis chase under-performing suppliers on behalf of customers
# rather than each gym chasing individually.
#
# Suppliers are grouped by normalised name (lower-cased, suffix-
# stripped) so a customer entering "Pulse Fitness Limited" and
# another entering "Pulse Fitness" roll up into the same supplier.

import re as _re_mod
_SUFFIX_RE = _re_mod.compile(r"\s*(limited|ltd\.?|plc|inc\.?|llc)\s*$", _re_mod.I)


def _normalise_supplier_name(name: str) -> str:
    """Strip common company suffixes + lowercase + collapse whitespace.
    Mirrors the resolver in master_admin_bulk_import.py so the rollup
    here joins seamlessly with the equipment-import resolution."""
    if not name:
        return ""
    base = _SUFFIX_RE.sub("", name).strip().lower()
    return _re_mod.sub(r"\s+", " ", base)


@router.get("/suppliers/health")
async def supplier_health_global(
    days: int = 30,
    sort: str = "open_issues",  # open_issues | equipment | sla_breaches | name
    user: dict = Depends(require_service_desk),
) -> dict:
    """Aggregate supplier health metrics across every customer org.

    For each unique (normalised) supplier name returns:
      - customer_org_count : how many customer orgs use this supplier
      - equipment_count : total equipment linked
      - open_issues_count : issues with status != resolved on linked kit
      - resolved_issues_window : resolved in the last `days`
      - sla_breaches_window : (resolved_at − created_at) > equipment.sla_response_time
      - avg_response_hours : mean (first_response_at − created_at)
      - avg_resolution_hours : mean (resolved_at − created_at)
      - aliases : list of every literal supplier name that collapsed into this row
      - orgs : [{id, name, equipment_count, open_issues_count}] for drill-down
    """
    days = max(1, min(365, int(days)))
    window_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Iter 245 — pulse-brand agents roll up only Pulse-visible orgs.
    scope = await desk_scope_org_ids(user)
    scope_q: Dict[str, Any] = {"organization_id": {"$in": scope}} if scope is not None else {}

    # 1) Pull every supplier from every org. Then group by normalised name.
    all_suppliers = await db.suppliers.find(
        scope_q, {"_id": 0, "id": 1, "name": 1, "organization_id": 1, "email": 1, "service_email": 1, "phone": 1, "supplier_types": 1},
    ).to_list(5000)

    # name_norm → {names: set, supplier_ids: set, org_ids: set, contact: {...}}
    groups: Dict[str, Dict[str, Any]] = {}
    for s in all_suppliers:
        n = _normalise_supplier_name(s.get("name", ""))
        if not n:
            continue
        g = groups.setdefault(n, {
            "name": s.get("name") or n.title(),
            "aliases": set(),
            "supplier_ids": set(),
            "org_ids": set(),
            "email": s.get("email") or s.get("service_email"),
            "phone": s.get("phone"),
            "supplier_types": set(),
        })
        g["aliases"].add(s.get("name") or "")
        g["supplier_ids"].add(s["id"])
        if s.get("organization_id"):
            g["org_ids"].add(s["organization_id"])
        for st in s.get("supplier_types") or []:
            if st:
                g["supplier_types"].add(st)

    # 2) Pull equipment in one shot, group by normalised supplier name.
    all_equipment = await db.equipment.find(
        scope_q, {"_id": 0, "id": 1, "organization_id": 1, "supplier": 1, "supplier_id": 1, "sla_response_time": 1},
    ).to_list(50000)
    eq_by_norm: Dict[str, list] = {}
    for e in all_equipment:
        n = _normalise_supplier_name(e.get("supplier", ""))
        if not n:
            continue
        eq_by_norm.setdefault(n, []).append(e)
        # Ensure equipment surfaces a supplier even if no supplier doc was created.
        if n not in groups:
            groups[n] = {
                "name": (e.get("supplier") or n.title()),
                "aliases": {e.get("supplier") or ""},
                "supplier_ids": set(),
                "org_ids": {e.get("organization_id")} if e.get("organization_id") else set(),
                "email": None, "phone": None, "supplier_types": set(),
            }
        groups[n]["org_ids"].add(e.get("organization_id"))

    # 3) Pull recent issues in one shot.
    all_issues = await db.issues.find(
        scope_q,
        {"_id": 0, "id": 1, "organization_id": 1, "equipment_id": 1, "asset_id": 1,
         "status": 1, "created_at": 1, "resolved_at": 1, "first_response_at": 1},
    ).to_list(50000)
    # Quick eq_id → norm map.
    eq_id_to_norm: Dict[str, str] = {}
    eq_id_to_sla: Dict[str, Optional[int]] = {}
    eq_id_to_org: Dict[str, str] = {}
    for e in all_equipment:
        norm = _normalise_supplier_name(e.get("supplier", ""))
        if norm:
            eq_id_to_norm[e["id"]] = norm
        eq_id_to_sla[e["id"]] = e.get("sla_response_time")
        eq_id_to_org[e["id"]] = e.get("organization_id", "")

    # 4) Tally per-group metrics.
    org_names: Dict[str, str] = {}
    org_ids_needed: set = set()
    for g in groups.values():
        org_ids_needed.update(g["org_ids"])
    if org_ids_needed:
        async for o in db.organizations.find(
            {"id": {"$in": list(org_ids_needed)}}, {"_id": 0, "id": 1, "name": 1},
        ):
            org_names[o["id"]] = o.get("name", "")

    metrics: Dict[str, Dict[str, Any]] = {n: {
        "open_issues_count": 0, "resolved_issues_window": 0, "sla_breaches_window": 0,
        "response_secs": [], "resolution_secs": [],
        "per_org": {},  # org_id → {equipment_count, open_issues_count}
    } for n in groups}

    # Equipment counts per (norm, org).
    for e in all_equipment:
        norm = _normalise_supplier_name(e.get("supplier", ""))
        if not norm or norm not in metrics:
            continue
        org_id = e.get("organization_id") or ""
        po = metrics[norm]["per_org"].setdefault(org_id, {"equipment_count": 0, "open_issues_count": 0})
        po["equipment_count"] += 1

    # Issue rollups.
    for iss in all_issues:
        eq_id = iss.get("equipment_id") or iss.get("asset_id")
        if not eq_id:
            continue
        norm = eq_id_to_norm.get(eq_id)
        if not norm or norm not in metrics:
            continue
        m = metrics[norm]
        org_id = iss.get("organization_id") or eq_id_to_org.get(eq_id, "")
        po = m["per_org"].setdefault(org_id, {"equipment_count": 0, "open_issues_count": 0})
        status = (iss.get("status") or "open").lower()
        if status != "resolved":
            m["open_issues_count"] += 1
            po["open_issues_count"] += 1
            continue
        # Resolved — windowed metrics
        if (iss.get("resolved_at") or "") < window_iso:
            continue
        m["resolved_issues_window"] += 1
        try:
            created = datetime.fromisoformat((iss.get("created_at") or "").replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(iss["resolved_at"].replace("Z", "+00:00"))
            resp_secs = (resolved - created).total_seconds()
            m["resolution_secs"].append(resp_secs)
            sla_h = eq_id_to_sla.get(eq_id)
            if sla_h and resp_secs > sla_h * 3600:
                m["sla_breaches_window"] += 1
        except (ValueError, KeyError, TypeError):
            pass
        if iss.get("first_response_at"):
            try:
                created = datetime.fromisoformat((iss.get("created_at") or "").replace("Z", "+00:00"))
                first = datetime.fromisoformat(iss["first_response_at"].replace("Z", "+00:00"))
                m["response_secs"].append((first - created).total_seconds())
            except (ValueError, KeyError, TypeError):
                pass

    # 5) Build the response array.
    out = []
    for norm, g in groups.items():
        m = metrics[norm]
        equipment_count = sum(po["equipment_count"] for po in m["per_org"].values())
        avg_response = (sum(m["response_secs"]) / len(m["response_secs"]) / 3600) if m["response_secs"] else None
        avg_resolution = (sum(m["resolution_secs"]) / len(m["resolution_secs"]) / 3600) if m["resolution_secs"] else None
        out.append({
            "name": g["name"],
            "normalised_name": norm,
            "aliases": sorted(a for a in g["aliases"] if a and a != g["name"]),
            "customer_org_count": len([oid for oid in m["per_org"] if oid]),
            "equipment_count": equipment_count,
            "open_issues_count": m["open_issues_count"],
            "resolved_issues_window": m["resolved_issues_window"],
            "sla_breaches_window": m["sla_breaches_window"],
            "avg_response_hours": round(avg_response, 1) if avg_response is not None else None,
            "avg_resolution_hours": round(avg_resolution, 1) if avg_resolution is not None else None,
            "email": g["email"],
            "phone": g["phone"],
            "supplier_types": sorted(g["supplier_types"]),
            "orgs": [
                {
                    "id": oid,
                    "name": org_names.get(oid, "Unknown org"),
                    "equipment_count": po["equipment_count"],
                    "open_issues_count": po["open_issues_count"],
                }
                for oid, po in m["per_org"].items() if oid
            ],
        })

    # Sort
    if sort == "equipment":
        out.sort(key=lambda r: r["equipment_count"], reverse=True)
    elif sort == "sla_breaches":
        out.sort(key=lambda r: (r["sla_breaches_window"], r["open_issues_count"]), reverse=True)
    elif sort == "name":
        out.sort(key=lambda r: r["name"].lower())
    else:  # default open_issues
        out.sort(key=lambda r: (r["open_issues_count"], r["sla_breaches_window"]), reverse=True)

    # Top-level rollup for the page summary card.
    totals = {
        "supplier_count": len(out),
        "equipment_total": sum(r["equipment_count"] for r in out),
        "open_issues_total": sum(r["open_issues_count"] for r in out),
        "sla_breaches_total": sum(r["sla_breaches_window"] for r in out),
        "window_days": days,
    }

    await log_desk_action(
        user, "suppliers.health", "supplier", "global",
        f"Supplier health rollup: {len(out)} suppliers, {totals['open_issues_total']} open issues",
        details={"window_days": days, "sort": sort},
    )

    return {"suppliers": out, "totals": totals, "scoped_to_pulse": scope is not None}


# ── Customer detail / edit ───────────────────────────────────────

async def _org_or_404(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.get("/customers/{org_id}")
async def get_customer(
    org_id: str,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Full customer record including sites, staff, supplier, onboarding state."""
    await assert_org_in_desk_scope(user, org_id)
    org = await _org_or_404(org_id)
    sites = await db.sites.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
    staff = await db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "disabled": 1, "last_login_at": 1},
    ).to_list(500)
    suppliers = await db.suppliers.find({"organization_id": org_id}, {"_id": 0}).to_list(50)
    equipment_count = await db.equipment.count_documents({"organization_id": org_id})

    return {
        "organization": org, "sites": sites, "staff": staff,
        "suppliers": suppliers, "equipment_count": equipment_count,
    }


_EDITABLE_ORG_FIELDS = {
    "name", "primary_contact_email", "primary_contact_name",
    "primary_contact_phone", "head_office_ref", "notes",
}


@router.patch("/customers/{org_id}")
async def update_customer(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(require_service_desk),
) -> dict:
    """Patch whitelisted customer fields. Billing / tier / feature-flag edits
    stay in Master Admin only — they are intentionally absent from the allow-list."""
    await assert_org_in_desk_scope(user, org_id)
    org = await _org_or_404(org_id)
    updates = {k: v for k, v in body.items() if k in _EDITABLE_ORG_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields supplied")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.organizations.update_one({"id": org_id}, {"$set": updates})
    await log_desk_action(
        user, "org.update", "organization", org_id,
        f"Updated {org.get('name', org_id)} — fields: {', '.join(updates.keys())}",
        details={"before": {k: org.get(k) for k in updates}, "after": updates},
    )
    return {"success": True, "updated_fields": list(updates.keys())}


# ── Site management ──────────────────────────────────────────────

@router.patch("/customers/{org_id}/sites/{site_id}")
async def update_site(
    org_id: str,
    site_id: str,
    body: dict = Body(...),
    user: dict = Depends(require_service_desk),
) -> dict:
    """Edit a site's address / contact fields on behalf of the customer."""
    await assert_org_in_desk_scope(user, org_id)
    site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    allowed = {"name", "address_line1", "address_line2", "city", "county",
               "postcode", "phone", "contact_name", "contact_email"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sites.update_one({"id": site_id}, {"$set": updates})
    await log_desk_action(
        user, "site.update", "site", site_id,
        f"Updated site '{site.get('name')}' for org {org_id}",
        details={"fields": list(updates.keys())},
    )
    return {"success": True, "updated_fields": list(updates.keys())}


# ── Impersonation ────────────────────────────────────────────────

async def _resolve_impersonation_target(org_id: str) -> dict:
    org = await _org_or_404(org_id)
    target = await db.users.find_one(
        {"organization_id": org_id, "role": "owner", "disabled": {"$ne": True}},
        {"_id": 0},
    )
    if not target:
        raise HTTPException(
            status_code=400,
            detail=f"No active owner user for org '{org.get('name')}'",
        )
    return target


@router.post("/customers/{org_id}/impersonate")
async def impersonate_customer(
    org_id: str,
    request: Request,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Issue a short-lived token scoped to the customer org's owner user.

    The returned token has `impersonation=True` in its payload so the frontend
    can show a red banner and audit every action taken during the session.
    Session expires in 1 hour; every refresh requires a fresh impersonation call.
    """
    await assert_org_in_desk_scope(user, org_id)
    target = await _resolve_impersonation_target(org_id)
    token = create_token(target["id"], expires_hours=1)
    await log_desk_action(
        user, "org.impersonate", "organization", org_id,
        f"Impersonation session started for {target.get('email')}",
        impersonating_org_id=org_id,
    )
    # Iter 220ax · F-28 — dedicated impersonation audit row.
    from utils.audit_log import record_impersonation_event
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    await record_impersonation_event(
        actor=user, target_user_id=target["id"],
        target_email=target.get("email"),
        target_organization_id=org_id,
        token_jti=None,
        expires_at=_dt.now(_tz.utc) + _td(hours=1),
        request=request, reason="service_desk_impersonate",
    )
    return {
        "token": token,
        "expires_in_seconds": 3600,
        "impersonating": {
            "user_id": target["id"],
            "user_email": target.get("email"),
            "org_id": org_id,
        },
    }


# ── Audit log ────────────────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    actor_id: str = Query(""),
    target_type: str = Query(""),
    target_id: str = Query(""),
    action: str = Query(""),
    skip: int = 0,
    limit: int = 200,
    user: dict = Depends(require_service_desk),
) -> dict:
    """Immutable feed of Service Desk actions. Any Service Desk agent can read;
    nobody (including Master Admin) can delete or edit rows."""
    # Iter 220as — clamp client-supplied limit to MAX_LIMIT.
    from utils.pagination import safe_limit, safe_skip
    limit = safe_limit(limit, default=200, hard_max=500)
    skip = safe_skip(skip)
    query: dict = {}
    # Iter 253 — provider desks only see audit actions from their own tenant.
    provider_org = await desk_provider_org_id(user)
    if provider_org:
        query["actor_org_id"] = provider_org
    for field, value in (
        ("actor_id", actor_id), ("target_type", target_type),
        ("target_id", target_id), ("action", action),
    ):
        if value:
            query[field] = value
    cursor = db.service_desk_audit_log.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    total = await db.service_desk_audit_log.count_documents(query)
    return {"rows": rows, "total": total}
