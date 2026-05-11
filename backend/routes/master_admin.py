"""
Master Admin Routes — Full platform control centre.
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import asyncio
import logging
import os
import secrets
import uuid

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_onboard_date(date_str: str) -> str:
    """Convert dd/mm/yyyy to ISO format for storage."""
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return date_str


# ─────────────────────────────────────────────────────────────────
# Iter 215en — Structured address helpers (Address 1*, Address 2,
# Address 3, City, County, Post code, Country). Everything that
# accepts the legacy single-line `address` continues to work; when
# only the structured fields are supplied we compose the legacy
# field from them so downstream Sage / Sicon outbox payloads keep
# working unchanged.
# ─────────────────────────────────────────────────────────────────

ADDRESS_FIELDS = (
    "address_line1", "address_line2", "address_line3",
    "city", "county", "postcode", "country",
)


def compose_legacy_address(payload: dict) -> str:
    """Compose a single-line address from the structured shape.

    Used to populate the legacy `address` field on org / site rows so
    Sage / Sicon outbox payloads keep working without code changes.
    Returns the existing `address` if no structured fields are present.
    """
    parts = [str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    return str(payload.get("address") or "").strip()


def merge_address(payload: dict) -> dict:
    """Pluck the structured address fields from `payload`, ensure the
    legacy `address` is in sync, and return a dict ready to merge into
    a Mongo document. The caller is responsible for picking out the
    keys they actually want to persist."""
    out = {k: str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS}
    if not out["country"]:
        out["country"] = "United Kingdom"
    legacy_explicit = str(payload.get("address") or "").strip()
    composed = compose_legacy_address(payload)
    out["address"] = legacy_explicit or composed
    return out


MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")

# Account types a Pulse Master Admin is allowed to see.
# Mirrors `routes.pulse_master_admin.PULSE_VISIBLE_ACCOUNT_TYPES` — kept inline
# to avoid a circular import.
PULSE_VISIBLE_ACCOUNT_TYPES = ["pulse_pro", "lite", "mod", "full"]


def is_pulse_only(user: dict) -> bool:
    """True when the caller is a Pulse Master Admin (delegated) but NOT the
    GymAxis platform Master Admin. Used to decide whether to scope list /
    edit endpoints to Pulse-visible orgs."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return False
    return bool(user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin")


def require_master_admin(user: dict):
    """Either the GymAxis Master Admin OR a delegated Pulse Master Admin is
    allowed past this gate. Endpoints that need to lock out Pulse admins
    explicitly should call ``require_gymaxis_master_only(user)`` instead.
    """
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


def require_gymaxis_master_only(user: dict):
    """Strict gate — only the GymAxis platform Master Admin (not Pulse admins)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    raise HTTPException(status_code=403, detail="GymAxis master admin access required")


async def assert_org_in_pulse_scope(user: dict, org_id: str) -> dict:
    """If caller is Pulse-only, 404 unless the target org is Pulse-visible.

    Returns the org doc (sans `_id`) so callers can avoid a redundant fetch.
    GymAxis master admins skip the scope check.
    """
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if is_pulse_only(user) and org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def assert_user_in_pulse_scope(user: dict, target_user_id: str) -> None:
    """Pulse-only callers can only mutate users belonging to a Pulse-visible org."""
    if not is_pulse_only(user):
        return
    target = (
        await db.users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
        or await db.crm_users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
    )
    if not target or not target.get("organization_id"):
        raise HTTPException(status_code=404, detail="User not found")
    org = await db.organizations.find_one(
        {"id": target["organization_id"]}, {"_id": 0, "account_type": 1},
    )
    if not org or org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="User not found")


async def log_activity(action: str, details: str, admin_email: str, target_type: str = "", target_id: str = ""):
    await db.admin_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "action": action,
        "details": details,
        "admin_email": admin_email,
        "target_type": target_type,
        "target_id": target_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _get_platform_counts(org_ids: Optional[list[str]] = None) -> dict:
    """Fetch core platform entity counts.

    When ``org_ids`` is provided (Pulse-scoped admins), every count is filtered
    by ``organization_id ∈ org_ids``. ``None`` means platform-wide (GymAxis
    master view).
    """
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    return {
        "total_users": await db.users.count_documents(scoped_q),
        "total_organizations": await db.organizations.count_documents(org_q),
        "active_orgs": await db.organizations.count_documents({**org_q, "status": {"$in": ["active", None]}}),
        "trial_orgs": await db.organizations.count_documents({**org_q, "status": "trial"}),
        "suspended_orgs": await db.organizations.count_documents({**org_q, "status": "suspended"}),
        "cancelled_orgs": await db.organizations.count_documents({**org_q, "status": "cancelled"}),
        "total_equipment": await db.equipment.count_documents(scoped_q),
        "total_issues": await db.issues.count_documents(scoped_q),
        "open_issues": await db.issues.count_documents({**scoped_q, "status": "open"}),
        "resolved_issues": await db.issues.count_documents({**scoped_q, "status": {"$in": ["resolved", "closed"]}}),
        "total_files": await db.files.count_documents(scoped_q),
        "total_purchase_orders": await db.purchase_orders.count_documents(scoped_q),
        "total_supplier_cases": await db.supplier_cases.count_documents(scoped_q),
    }


async def _get_subscription_stats(org_ids: Optional[list[str]] = None) -> tuple[dict, int]:
    """Fetch subscription breakdown and MRR (excluding test accounts).

    Same scoping semantics as ``_get_platform_counts``.
    """
    non_test = {"is_test": {"$ne": True}}
    if org_ids is not None:
        non_test["id"] = {"$in": org_ids}
    subs = {
        "free": await db.organizations.count_documents({**non_test, "subscription_tier": {"$in": ["free", None, ""]}}),
        "pro": await db.organizations.count_documents({**non_test, "subscription_tier": "pro"}),
        "premium": await db.organizations.count_documents({**non_test, "subscription_tier": "premium"}),
        "enterprise": await db.organizations.count_documents({**non_test, "subscription_tier": "enterprise"}),
    }
    mrr = (subs["pro"] * 49) + (subs["premium"] * 99) + (subs["enterprise"] * 199)
    return subs, mrr


async def _get_growth_data(mrr: int, org_ids: Optional[list[str]] = None) -> list:
    """Build 6-month growth timeline (org_id-scoped when ``org_ids`` is set)."""
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    data = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=30 * i)
        month_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = (month_start + timedelta(days=32)).replace(day=1) if i > 0 else datetime.now(timezone.utc)
        data.append({
            "month": month_start.strftime("%b %Y"),
            "users": await db.users.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "organizations": await db.organizations.count_documents({**org_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "issues": await db.issues.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "mrr": mrr,
        })
    return data


async def _resolve_pulse_scope_org_ids(user: dict) -> Optional[list[str]]:
    """Return org-id list when caller is Pulse-only, else ``None``.

    ``None`` signals platform-wide queries.
    """
    if not is_pulse_only(user):
        return None
    pulse_orgs = await db.organizations.find(
        {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    return [o["id"] for o in pulse_orgs]


@router.get("/master-admin/stats")
async def get_master_stats(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    org_ids = await _resolve_pulse_scope_org_ids(user)
    counts = await _get_platform_counts(org_ids)
    subs, mrr = await _get_subscription_stats(org_ids)
    issue_q: dict = {"ai_triage": {"$exists": True, "$ne": None}}
    audit_q: dict = {}
    payment_succ_q: dict = {"status": "succeeded"}
    payment_fail_q: dict = {"status": "failed"}
    if org_ids is not None:
        issue_q["organization_id"] = {"$in": org_ids}
        audit_q["organization_id"] = {"$in": org_ids}
        payment_succ_q["organization_id"] = {"$in": org_ids}
        payment_fail_q["organization_id"] = {"$in": org_ids}
    ai_calls = await db.issues.count_documents(issue_q)
    ai_audits = await db.audits.count_documents(audit_q)

    return {
        **counts,
        "mrr": mrr,
        "subscriptions": subs,
        "ai_usage": {"triage_calls": ai_calls, "audit_reports": ai_audits, "total": ai_calls + ai_audits},
        "payments": {
            "total": await db.payment_transactions.count_documents(payment_succ_q),
            "failed": await db.payment_transactions.count_documents(payment_fail_q),
        },
        "growth_data": await _get_growth_data(mrr, org_ids),
        "scoped": org_ids is not None,
    }


@router.get("/master-admin/organizations/search")
async def search_organizations(
    q: str = "",
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """Iter 215en — Head-Office autocomplete lookup.

    Used by the Head Office Onboarding Wizard so the master admin can
    pull an existing org's billing details forward (e.g. when adding more
    sites under the same corporate parent later) instead of retyping
    company name, number, VAT and registered address. Returns up to
    `limit` orgs whose name / company number / VAT contain `q` (case-
    insensitive). Empty `q` returns the most recent 10 orgs so the picker
    feels populated from the first keystroke.
    """
    require_master_admin(user)
    qs = (q or "").strip()
    org_filter: dict = {}
    if is_pulse_only(user):
        org_filter["account_type"] = {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}
    if qs:
        # Escape regex metachars so a postcode like "N15 4QT" or a name
        # with parentheses doesn't blow up the query.
        import re as _re
        rx = _re.compile(_re.escape(qs), _re.IGNORECASE)
        org_filter["$or"] = [
            {"name": rx},
            {"company_number": rx},
            {"vat_number": rx},
            {"postcode": rx},
            {"company_code": rx},
        ]

    cursor = db.organizations.find(org_filter, {"_id": 0}).sort("created_at", -1).limit(max(1, min(int(limit or 10), 50)))
    results = []
    async for o in cursor:
        results.append({
            "id": o.get("id"),
            "name": o.get("name", ""),
            "company_code": o.get("company_code", ""),
            "company_number": o.get("company_number", ""),
            "vat_number": o.get("vat_number", ""),
            "account_type": o.get("account_type", "full"),
            "is_multi_site": bool(o.get("is_multi_site")),
            "site_count": int(o.get("site_count") or 0),
            # Structured address (falls back to legacy on un-migrated rows).
            "address_line1": o.get("address_line1") or o.get("address", ""),
            "address_line2": o.get("address_line2", ""),
            "address_line3": o.get("address_line3", ""),
            "city": o.get("city", ""),
            "county": o.get("county", ""),
            "postcode": o.get("postcode", ""),
            "country": o.get("country") or "United Kingdom",
            "phone": o.get("phone", ""),
        })
    return {"organizations": results, "query": qs}


@router.get("/master-admin/organizations")
async def get_all_organizations(
    user: dict = Depends(get_current_user),
    brand: str = "all",
):
    require_master_admin(user)
    org_filter: dict = {}
    if is_pulse_only(user):
        org_filter["account_type"] = {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}
    # Iter 216h18 — Master Admin brand context filter. Applies after
    # the pulse-only guard so a Pulse Master Admin who flips the
    # picker to "GymAxis" still sees nothing (their permission gate
    # always wins).
    from utils.brand_filter import merge_brand_filter
    org_filter = merge_brand_filter(org_filter, brand, collection="organizations")
    orgs = await db.organizations.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(500)
    if not orgs:
        return {"organizations": []}

    org_ids = [o["id"] for o in orgs]

    # Tier-3.5 N+1 fix (Apr 2026): was 1 + 8×N queries on the master-admin
    # dashboard (≈4000 round-trips for 500 orgs). Now 1 + 8 batched aggregates
    # regardless of org count — the MongoDB planner uses the
    # `organization_id` index on each collection, so this is a 10-100×
    # wall-clock improvement for the admin who sees this page first thing.
    import asyncio

    async def _group(coll, match=None):
        """Return {org_id: count} for a $group-by-organization_id pipeline."""
        pipe = []
        if match:
            pipe.append({"$match": match})
        pipe.append({"$match": {"organization_id": {"$in": org_ids}}})
        pipe.append({"$group": {"_id": "$organization_id", "c": {"$sum": 1}}})
        return {d["_id"]: d["c"] for d in await coll.aggregate(pipe).to_list(length=None)}

    async def _owners():
        pipe = [
            {"$match": {"organization_id": {"$in": org_ids}, "role": "owner"}},
            {"$group": {
                "_id": "$organization_id",
                "email": {"$first": "$email"},
                "full_name": {"$first": "$full_name"},
            }},
        ]
        return {d["_id"]: d async for d in db.users.aggregate(pipe)}

    (
        sp_user_map, crm_user_map, equip_map, issue_map, open_issue_map,
        file_map, ai_map, owner_map,
    ) = await asyncio.gather(
        _group(db.users),
        _group(db.crm_users),
        _group(db.equipment),
        _group(db.issues),
        _group(db.issues, {"status": "open"}),
        _group(db.files),
        _group(db.issues, {"ai_triage": {"$exists": True, "$ne": None}}),
        _owners(),
    )

    enriched = []
    for org in orgs:
        oid = org["id"]
        owner = owner_map.get(oid) or {}
        enriched.append({
            **org,
            "status": org.get("status", "active"),
            "user_count": sp_user_map.get(oid, 0) + crm_user_map.get(oid, 0),
            "equipment_count": equip_map.get(oid, 0),
            "issue_count": issue_map.get(oid, 0),
            "open_issues": open_issue_map.get(oid, 0),
            "file_count": file_map.get(oid, 0),
            "ai_calls": ai_map.get(oid, 0),
            "owner_email": owner.get("email", ""),
            "owner_name": owner.get("full_name", ""),
            "features": org.get("features", {}),
            "is_test": org.get("is_test", False),
            "account_type": org.get("account_type", "full"),
            "portal_type": org.get("portal_type", "service_portal"),
            "enabled_modules": org.get("enabled_modules") or _modules_from_portal_type(org.get("portal_type", "service_portal")),
            "industry": org.get("industry", ""),
            "employee_count": org.get("employee_count", ""),
            "website": org.get("website", ""),
            "phone": org.get("phone", ""),
            "address": org.get("address", ""),
            # Iter 215en — structured 8-field address (Address 1*, Address 2,
            # Address 3, City, County, Post code, Country). Falls back to the
            # legacy single-line `address` for line1 on records that haven't
            # been migrated yet.
            "address_line1": org.get("address_line1") or org.get("address", ""),
            "address_line2": org.get("address_line2", ""),
            "address_line3": org.get("address_line3", ""),
            "city": org.get("city", ""),
            "county": org.get("county", ""),
            "postcode": org.get("postcode", ""),
            "country": org.get("country", "United Kingdom"),
            "primary_contact_name": org.get("primary_contact_name", ""),
            "primary_contact_email": org.get("primary_contact_email", ""),
            "primary_contact_phone": org.get("primary_contact_phone", ""),
            "primary_contact_user_id": org.get("primary_contact_user_id") or None,
            "notes": org.get("notes", ""),
        })

    return {"organizations": enriched}


@router.put("/master-admin/organizations/{org_id}/status")
async def update_org_status(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    status = body.get("status")
    if status not in ["active", "trial", "suspended", "cancelled", "archived"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {"status": status, "status_updated_at": now_iso}
    # Stamp archived_at on entering archive; clear it on leaving (for restore UX)
    if status == "archived":
        update["archived_at"] = now_iso
        update["archived_by"] = user["email"]
        update["archive_warning_sent_at"] = None  # reset warning so we don't reuse an old one
    else:
        update["archived_at"] = None
        update["archived_by"] = None
        update["archive_warning_sent_at"] = None

    result = await db.organizations.update_one({"id": org_id}, {"$set": update})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Organization not found")

    await log_activity("org_status_change", f"Changed org {org_id} status to {status}", user["email"], "organization", org_id)
    return {"success": True, "status": status}


_PULSE_TIER_TO_ACCOUNT_TYPE = {"lite": "lite", "pulse_pro": "pulse_pro"}
_GYMAXIS_TIERS = {"free", "pro", "premium", "enterprise", "starter", "professional"}


@router.put("/master-admin/organizations/{org_id}/subscription")
async def update_org_subscription(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update org subscription. Accepts both GymAxis tiers (`free`/`pro`/`premium`/
    `enterprise`/`starter`/`professional`) and Pulse tiers (`lite`/`pulse_pro`).

    For Pulse tiers we also flip `account_type` so feature gating picks up the new
    plan immediately — otherwise a Lite→Pro upgrade only changes the label, not the
    feature set the user actually gets.
    """
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    tier = body.get("tier")
    updates: dict = {"subscription_tier": tier}

    if tier in _PULSE_TIER_TO_ACCOUNT_TYPE:
        updates["account_type"] = _PULSE_TIER_TO_ACCOUNT_TYPE[tier]
    elif tier not in _GYMAXIS_TIERS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    result = await db.organizations.update_one({"id": org_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await log_activity("subscription_change", f"Changed org {org_id} to {tier}", user["email"], "organization", org_id)
    return {"success": True, "tier": tier, "account_type": updates.get("account_type")}


@router.put("/master-admin/organizations/{org_id}/features")
async def update_org_features(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1, "modules": 1})
    old_features = (org or {}).get("features") or {}
    old_modules = (org or {}).get("modules") or {}

    set_doc: dict = {}
    unset_doc: dict = {"features_preset": ""}
    changes: dict = {}

    # Per-feature toggles (existing behaviour)
    if "features" in body and isinstance(body["features"], dict):
        features = body["features"]
        set_doc["features"] = features
        for k, v in features.items():
            if old_features.get(k) != v:
                changes[f"feat:{k}"] = {"from": old_features.get(k), "to": v}

    # Module-level enable + tier matrix (new). Each entry must look like
    # {"enabled": bool, "tier": "lite"|"pro"|"enterprise"}.
    if "modules" in body and isinstance(body["modules"], dict):
        merged: dict = {**old_modules}
        for m_key, cfg in body["modules"].items():
            if m_key not in {"operations", "memberships", "marketing", "crm"}:
                continue
            if not isinstance(cfg, dict):
                continue
            tier = cfg.get("tier") if cfg.get("tier") in {"lite", "pro", "enterprise"} else (old_modules.get(m_key) or {}).get("tier", "pro")
            entry = {"enabled": bool(cfg.get("enabled", False)), "tier": tier}
            # Preserve any legacy/extension keys (e.g. business_enabled)
            existing = old_modules.get(m_key) or {}
            for k, v in existing.items():
                if k not in entry:
                    entry[k] = v
            merged[m_key] = entry
            if old_modules.get(m_key) != entry:
                changes[f"module:{m_key}"] = {"from": old_modules.get(m_key), "to": entry}

        # Iter 215c — Bundle Leisure CRM with Memberships. Whenever
        # Memberships is enabled, the org automatically gets CRM access
        # (leisure mode). Disabling Memberships does NOT auto-disable
        # CRM — Business CRM may be paid-for separately.
        memberships_entry = merged.get("memberships")
        if memberships_entry and memberships_entry.get("enabled"):
            crm_entry = dict(merged.get("crm") or {})
            if not crm_entry.get("enabled"):
                crm_entry["enabled"] = True
                crm_entry.setdefault("tier", memberships_entry.get("tier", "pro"))
                merged["crm"] = crm_entry
                changes["module:crm:auto_bundle"] = {"reason": "memberships_enabled"}
        set_doc["modules"] = merged

    if not set_doc:
        raise HTTPException(400, "Nothing to update — pass {features:{…}} or {modules:{…}}")

    await db.organizations.update_one({"id": org_id}, {"$set": set_doc, "$unset": unset_doc})
    if changes:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "by": user.get("email", "?"),
            "changes": changes,
            "preset": None,
        }
        await db.organizations.update_one(
            {"id": org_id},
            {"$push": {"features_audit": {"$each": [entry], "$slice": -50}}},
        )
    await log_activity("feature_toggle", f"Updated features for org {org_id}", user["email"], "organization", org_id)
    return {"success": True}


@router.put("/master-admin/organizations/{org_id}/test-flag")
async def toggle_test_flag(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    is_test = body.get("is_test", False)
    await db.organizations.update_one({"id": org_id}, {"$set": {"is_test": is_test}})
    await log_activity("test_flag", f"Set org {org_id} test={is_test}", user["email"], "organization", org_id)
    return {"success": True}


@router.post("/master-admin/organizations/{org_id}/test-email")
async def send_test_branded_email(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Send a dummy email of the selected `kind` to `body.to` (default: admin's own)
    using the target org's platform branding (Pulse Fitness vs GymAxis AI). Lets
    master admins validate every outbound template end-to-end without logging a
    real fault. Supported kinds: `comment`, `engineer_callout`, `supplier_welcome`.
    """
    require_master_admin(user)

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        raise HTTPException(status_code=503, detail="Resend is not configured in this environment")

    from routes.supplier_portal import (
        _resolve_platform_branding,
        _build_comment_email_html,
        _build_supplier_welcome_html,
        _short_case_ref,
    )
    import resend as _resend
    _resend.api_key = resend_key

    branding = await _resolve_platform_branding(org_id)
    to_email = (body.get("to") or user.get("email") or "").strip()
    if not to_email:
        raise HTTPException(status_code=400, detail="No recipient email resolved")

    kind = (body.get("kind") or "comment").strip()
    site_name = org.get("name", "Your Gym")
    machine, serial = "Treadmill", "TEST-0001"

    if kind == "supplier_welcome":
        sample_supplier = {
            "name": "Sample Supplier Ltd",
            "contact_person": "Service Team",
            "email": to_email,
        }
        html = _build_supplier_welcome_html(sample_supplier, site_name, branding)
        subject = f"[PREVIEW] Welcome to {branding['platform_name']} — how faults will reach you from {site_name}"
        from_line = f"{site_name} <faults@service.gymaxisai.com>"
    elif kind == "engineer_callout":
        html, subject, from_line = _build_preview_engineer_email(
            branding, site_name, machine, serial,
        )
    else:  # 'comment'
        html, subject, from_line = _build_preview_comment_email(
            branding, site_name, machine, serial,
            _build_comment_email_html, _short_case_ref,
        )

    try:
        await asyncio.to_thread(_resend.Emails.send, {
            "from": from_line,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send preview email: {e}")

    await log_activity(
        "email_preview",
        f"Sent {kind} preview for org {org_id} ({branding['platform_name']}) to {to_email}",
        user["email"], "organization", org_id,
    )
    return {
        "success": True,
        "sent_to": to_email,
        "kind": kind,
        "platform_name": branding["platform_name"],
        "is_pulse": branding["is_pulse"],
    }


def _build_preview_comment_email(branding: dict, site_name: str, machine: str, serial: str,
                                 build_html, build_ref) -> tuple[str, str, str]:
    case = {"id": "preview-case-0000", "token": "preview", "organization_name": site_name}
    issue = {
        "id": "preview-issue", "machine_type": machine, "serial_number": serial,
        "issue_description": "Console intermittently resetting — preview email (no real fault)",
    }
    comment = {
        "author_name": site_name, "author_role": "site_manager",
        "message": (
            "This is a preview of the 2-way conversation email your customers and "
            "suppliers will see. No real fault has been reported."
        ),
    }
    ref = build_ref(case, issue)
    intro = f"{site_name} has posted a new comment on the fault report for <strong>{machine}</strong>."
    html = build_html(case, comment, intro, branding, issue, ref)
    subject = f"[PREVIEW][{ref}] Sample message from {site_name} — {machine}"
    from_line = f"{site_name} <faults@service.gymaxisai.com>"
    return html, subject, from_line


def _build_preview_engineer_email(branding: dict, site_name: str,
                                  machine: str, serial: str) -> tuple[str, str, str]:
    """Build a preview of the initial engineer-callout email using the same
    responsive template real engineer emails use — so admins validate the
    exact visual their suppliers will receive."""
    from routes.issue_helpers import _build_engineer_email_html

    platform = branding["platform_name"]
    from_line = f"{site_name} <faults@service.gymaxisai.com>"
    subject = f"[PREVIEW][JOB-PRVW0001] Engineer Required — {machine} ({serial}) — {site_name}"

    class _PreviewIssue:  # minimal duck-type for the email builder
        machine_type = machine
        serial_number = serial
        severity = "out_of_order"
        issue_description = (
            "Console intermittently resets when Start is pressed. Reproduces 3/5 times. "
            "User report: no display, then reboots after 10 seconds. (Preview — no real fault logged.)"
        )
        ai_triage = "Likely cause: loose power harness or failing PSU. Suggested action: inspect main PSU connector + replace if oxidised."

    user_stub = {"full_name": "Preview Reporter", "email": "preview.reporter@example.com"}
    case_result = {"case_id": "prvw0001-0000-0000-0000-000000000000", "url": "#preview"}
    org_ctx = {
        "brand_color": "#0055FF",
        "company_name": site_name,
        "supplier_contact": "Service Team",
        "supplier_email": "supplier@example.com",
        "test_mode": False,
        "platform_name": platform,
        "is_pulse": branding.get("is_pulse", False),
        "reporter": {"name": "Preview Reporter", "email": "preview.reporter@example.com", "role": "Owner"},
        "site": {"gym_name": site_name, "address": "1 Example Street, London, E1 1AA, UK", "phone": "020 7123 4567"},
        "job_ref": "",
    }
    html = _build_engineer_email_html(_PreviewIssue(), user_stub, case_result, org_ctx)
    return html, subject, from_line


@router.put("/master-admin/organizations/{org_id}/account-type")
async def update_account_type(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    account_type = body.get("account_type")
    if account_type not in ["lite", "full", "pulse_pro"]:
        raise HTTPException(status_code=400, detail="Invalid account type. Must be 'lite', 'full', or 'pulse_pro'")

    # Derive subscription_tier to keep in sync
    tier_map = {"lite": "lite", "pulse_pro": "pro", "full": "premium"}
    tier = tier_map.get(account_type, "free")

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"account_type": account_type, "subscription_tier": tier}},
    )
    # Also update all users in this org so their token reflects the new type
    await db.users.update_many({"organization_id": org_id}, {"$set": {"account_type": account_type}})
    await log_activity("account_type_change", f"Changed org {org_id} to {account_type}", user["email"], "organization", org_id)
    return {"success": True, "account_type": account_type}


# ── Iter 215ar — Modules + Primary-contact auto-provisioning ───────

# Canonical module ids exposed to the master-admin UI (checkbox grid).
ALL_MODULE_IDS = ["operations", "crm", "memberships", "marketing", "staffing", "reporting"]


def _normalize_modules(raw, legacy_portal_type: Optional[str]) -> List[str]:
    """Coerce the inbound `enabled_modules` list to a clean, deduped subset
    of ALL_MODULE_IDS. Falls back to deriving from a legacy portal_type
    string so older callers keep working unchanged."""
    if isinstance(raw, list) and raw:
        cleaned = [m for m in raw if isinstance(m, str) and m in ALL_MODULE_IDS]
        if cleaned:
            # Stable order — match the UI grid for predictability.
            return [m for m in ALL_MODULE_IDS if m in cleaned]
    return _modules_from_portal_type(legacy_portal_type or "service_portal")


def _modules_from_portal_type(portal_type: str) -> List[str]:
    """Map a legacy portal_type string back onto the modules list."""
    if portal_type == "crm":
        return ["crm"]
    if portal_type == "both":
        return ["operations", "crm"]
    return ["operations"]  # service_portal default


def _derive_portal_type(modules: List[str]) -> str:
    """Reduce a modules list to the legacy portal_type for callers that
    still gate on it (collection routing, feature flags)."""
    has_crm = "crm" in modules
    has_ops = any(m in modules for m in ("operations", "memberships", "marketing", "staffing", "reporting"))
    if has_crm and has_ops:
        return "both"
    if has_crm:
        return "crm"
    return "service_portal"


def _generate_initial_password(length: int = 14) -> str:
    """Generate a friendly, copy-able initial password: 4 lowercase + 4 digits + 4 lowercase + 2 symbols.
    Avoids ambiguous characters (no l/1/O/0)."""
    import secrets
    alphabet = "abcdefghijkmnpqrstuvwxyz"
    digits   = "23456789"
    symbols  = "!@#%&*"

    def pick(src: str, n: int) -> str:
        return "".join(secrets.choice(src) for _ in range(n))

    return f"{pick(alphabet, 4)}{pick(digits, 3)}{pick(alphabet, 3)}{pick(symbols, 2)}"


async def _mint_invite_link(user_id: str, email: str, issued_by_email: str = "system") -> dict:
    """Iter 216h26 — Mint a 72 h reset-link invite for a user.

    Extracted from POST /master-admin/users/{user_id}/invite-link so
    that org create + customer onboarding can return a self-serve
    invite URL alongside (or instead of) the legacy reveal-password
    handover. Lets every Master Admin creation surface stay consistent
    with the iter-216h15 reset-link flow.
    """
    import secrets as _secrets
    from datetime import timedelta as _td
    token = _secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email,
        "expires_at": expires_at,
        "used": False,
        "kind": "invite",
        "issued_by": issued_by_email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return {
        "invite_url": f"{frontend_url}/reset-password?token={token}",
        "expires_at": expires_at,
    }


async def _ensure_primary_contact_user(org: dict, actor: dict) -> Optional[str]:
    """If `primary_contact_email` is set on `org` and no user exists for that
    email, auto-provision an admin user in the right collection(s) and
    persist the generated initial password on the org doc. Returns the
    generated password if a new user was created, else None.

    The plaintext is intentionally retained on the org until the user
    changes their password — so master-admin can hand it over during
    onboarding via the Reveal Password button. Cleared by the auth layer
    when the user changes password (see `password_reset.py`)."""
    email = (org.get("primary_contact_email") or "").strip().lower()
    if not email:
        return None
    # Skip if a user already exists in either collection — never overwrite.
    if await db.users.find_one({"email": email}) or await db.crm_users.find_one({"email": email}):
        return None

    full_name = (org.get("primary_contact_name") or email.split("@")[0]).strip() or email
    password  = _generate_initial_password()
    user_id   = str(uuid.uuid4())
    try:
        await _create_org_user(org, email, full_name, password, role="admin", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        # Don't blow up org creation if user creation fails — log + continue.
        logger.warning("Failed to auto-create primary contact user for org %s: %s", org.get("id"), exc)
        return None

    # Persist the plaintext password so master-admin can reveal it.
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "primary_contact_initial_password": password,
            "primary_contact_user_id": user_id,
            "primary_contact_password_changed": False,
            "primary_contact_provisioned_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_activity(
        "primary_contact_provisioned",
        f"Auto-created user {email} as primary contact for {org.get('name')}",
        actor.get("email", "system"), "user", user_id,
    )
    return password


@router.post("/master-admin/organizations")
async def create_organization(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create a new organisation (Service Portal, CRM, or both)."""
    require_master_admin(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organisation name is required")

    # Iter 215ar — `enabled_modules` is the new source of truth for
    # which modules an org has access to. The legacy `portal_type`
    # ("service_portal" | "crm" | "both") is derived from it for
    # backwards-compatibility with existing callers / DB queries.
    raw_modules = body.get("enabled_modules") or body.get("modules")
    enabled_modules = _normalize_modules(raw_modules, body.get("portal_type"))
    portal_type = _derive_portal_type(enabled_modules)

    # Pulse-only admins can only create Pulse-visible orgs.
    requested_account_type = body.get("account_type", "full")
    if is_pulse_only(user) and requested_account_type not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Pulse admins can only create Pulse-visible account types: {PULSE_VISIBLE_ACCOUNT_TYPES}",
        )

    org_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    org_doc = {
        "id": org_id, "name": name,
        "portal_type": portal_type,
        "enabled_modules": enabled_modules,
        "subscription_tier": body.get("subscription_tier", "free"),
        "account_type": requested_account_type,
        "status": "active", "created_at": now,
        "company_code": str(uuid.uuid4())[:8].upper(),
        "industry": body.get("industry", ""),
        "employee_count": body.get("employee_count", ""),
        "website": body.get("website", ""),
        "phone": body.get("phone", ""),
        # Iter 215en — accept structured 8-field address. Legacy `address`
        # is retained for downstream Sage / Sicon outboxes; we auto-compose
        # it from the structured shape when only the structured fields are
        # supplied.
        **merge_address(body),
        "primary_contact_name": body.get("primary_contact_name", ""),
        "primary_contact_email": body.get("primary_contact_email", ""),
        "primary_contact_phone": body.get("primary_contact_phone", ""),
        "notes": body.get("notes", ""),
        "features": body.get("features", {}),
    }
    await db.organizations.insert_one(org_doc)

    # Iter 215ar — auto-provision a user account for the primary contact
    # so the org owner can sign in immediately. Master admin can reveal the
    # initial password from the org panel until the user changes it.
    await _ensure_primary_contact_user(org_doc, user)

    # Iter 216h26 — also mint a 72 h invite link so the operator can
    # send a self-serve "set your own password" URL instead of relying
    # on the credentials-reveal handover. Both paths remain valid;
    # operators can pick whichever fits the customer.
    invite_payload = None
    try:
        org_after = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        owner_id = (org_after or {}).get("primary_contact_user_id")
        owner_email = (org_after or {}).get("primary_contact_email")
        if owner_id and owner_email:
            invite_payload = await _mint_invite_link(owner_id, owner_email, user.get("email", "system"))
    except Exception:  # noqa: BLE001 — never fail org creation on invite mint
        invite_payload = None

    await log_activity("org_created", f"Created organisation: {name} ({portal_type})", user["email"], "organization", org_id)
    fresh = await db.organizations.find_one({"id": org_id}, {"_id": 0, "primary_contact_initial_password": 0})
    response: dict = {**(fresh or org_doc), "user_count": 0}
    if invite_payload:
        response["owner"] = {
            "email": fresh.get("primary_contact_email"),
            "user_id": fresh.get("primary_contact_user_id"),
            "invite_url": invite_payload["invite_url"],
            "invite_expires_at": invite_payload["expires_at"],
        }
        # Convenience top-level keys so older callers keep working.
        response["invite_url"] = invite_payload["invite_url"]
        response["invite_expires_at"] = invite_payload["expires_at"]
    return response



@router.put("/master-admin/organizations/{org_id}/details")
async def update_org_details(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update organization profile details."""
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    allowed = {
        "name", "industry", "employee_count", "website", "phone",
        # Iter 215en — structured 8-field address alongside the legacy
        # single-line `address` (kept for Sage / Sicon outbox payloads).
        "address", "address_line1", "address_line2", "address_line3",
        "city", "county", "postcode", "country",
        "primary_contact_name", "primary_contact_email", "primary_contact_phone",
        "notes", "portal_type", "enabled_modules",
        "customer_account_number", "sage_customer_number", "sicon_customer_number",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid fields to update")

    # Iter 215en — when any structured-address field is being updated, also
    # re-compose the legacy single-line `address` so Sage / Sicon outbox
    # payloads stay in sync.
    if any(k in updates for k in ADDRESS_FIELDS) and "address" not in body:
        merged = merge_address({**body, **updates})
        updates["address"] = merged["address"]

    # Iter 215ar — keep portal_type and enabled_modules in sync. If the
    # caller supplies modules we derive portal_type from them; if they
    # supply portal_type we derive modules.
    if "enabled_modules" in updates:
        normalised = _normalize_modules(updates["enabled_modules"], updates.get("portal_type"))
        updates["enabled_modules"] = normalised
        updates["portal_type"] = _derive_portal_type(normalised)
    elif "portal_type" in updates and updates["portal_type"] not in ("service_portal", "crm", "both"):
        raise HTTPException(status_code=400, detail="portal_type must be service_portal, crm, or both")

    if "primary_contact_email" in updates:
        updates["primary_contact_email"] = (updates["primary_contact_email"] or "").strip().lower()

    result = await db.organizations.update_one({"id": org_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Organisation not found")

    # If the primary contact email is set + the org doesn't already have an
    # auto-provisioned user for it, create one and persist the initial
    # password so master-admin can hand it over during onboarding.
    if "primary_contact_email" in updates and updates["primary_contact_email"]:
        org_after = await db.organizations.find_one({"id": org_id})
        if org_after:
            await _ensure_primary_contact_user(org_after, user)

    await log_activity("org_details_updated", f"Updated details for org {org_id}", user["email"], "organization", org_id)
    return {"success": True}


@router.get("/master-admin/organizations/{org_id}/primary-contact-credentials")
async def get_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Reveal the auto-generated initial password for the org's primary
    contact user. Audited every time it is accessed. Cleared once the
    contact changes their own password (see password reset flow)."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        return {"email": None, "initial_password": None, "password_changed": False, "available": False}
    await log_activity(
        "primary_contact_password_revealed",
        f"Revealed initial password for {email}",
        user["email"], "organization", org_id,
    )
    return {
        "email": email,
        "initial_password": initial if (initial and not changed) else None,
        "password_changed": changed,
        "available": bool(initial and not changed),
    }


@router.post("/master-admin/organizations/{org_id}/send-primary-contact-credentials")
async def send_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 215at — email the auto-generated initial credentials to the
    primary contact via Resend, then clear the plaintext from the org doc
    so it can no longer be revealed in the panel.

    Audited. Returns 400 if no credentials are available to send."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email   = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        raise HTTPException(400, "No primary contact email set on this organisation")
    if not initial or changed:
        raise HTTPException(400, "No initial password is available to send (already used or rotated)")

    # Late import — avoid the helper module loading at startup if email
    # is misconfigured. send_email is best-effort and audited internally.
    from utils.email import send_email

    org_name  = org.get("name", "your GymAxis account")
    contact   = org.get("primary_contact_name") or email.split("@")[0]
    subject   = f"Welcome to {org_name} on GymAxis"

    # Plain HTML — no inline images, no tracking pixels, deliverability-friendly.
    html = f"""
    <div style="font-family:Inter,system-ui,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a">
      <h1 style="font-size:20px;font-weight:800;letter-spacing:-0.4px;margin:0 0 8px">Welcome to GymAxis, {contact}.</h1>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Your account for <strong>{org_name}</strong> is ready. Use the credentials below to sign in for the first time.
      </p>
      <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;background:#f8fafc;margin-bottom:20px">
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Email</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0 0 14px;color:#0f172a">{email}</p>
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Temporary password</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0;color:#0f172a">{initial}</p>
      </div>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Please change your password the first time you sign in — go to your profile menu and select
        <em>Change password</em>. The temporary password above will stop working once you do.
      </p>
      <a href="https://gymaxisai.com/login" style="display:inline-block;background:linear-gradient(135deg,#2563EB,#9D4CDD);color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:999px;font-size:14px">Sign in to GymAxis</a>
      <p style="font-size:11px;color:#94a3b8;margin-top:32px">
        If you weren't expecting this email, please contact us at security@gymaxisai.com.
      </p>
    </div>
    """

    ok = await send_email(email, subject, html)
    if not ok:
        raise HTTPException(502, "Email could not be delivered. Please try again or copy the password manually.")

    # Clear the plaintext from the org doc immediately on successful send —
    # we no longer need to keep it; if the user loses the email they can
    # reset via the standard /auth/forgot-password flow.
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"primary_contact_credentials_sent_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"primary_contact_initial_password": ""}},
    )
    await log_activity(
        "primary_contact_credentials_emailed",
        f"Emailed initial credentials to {email}",
        user["email"], "organization", org_id,
    )
    return {"sent": True, "email": email}


# ── Verify tenant identifier mappings ────────────────────────────


async def _check_code_collision(code: str, fields: list[str], exclude_org_id: str) -> Optional[dict]:
    """Return ``{org_id, name}`` for any OTHER org in our DB sharing this code
    on any of ``fields``. Empty/whitespace codes are skipped."""
    if not (code and code.strip()):
        return None
    norm = code.strip()
    other = await db.organizations.find_one(
        {
            "id": {"$ne": exclude_org_id},
            "$or": [{f: norm} for f in fields],
        },
        {"_id": 0, "id": 1, "name": 1},
    )
    return other if other else None


async def _integration_status(integration_id: str) -> dict:
    """Return ``{status: "configured"|"not_configured", configured: bool}`` for
    the platform-level Sicon / Orbit 4 integration row."""
    cfg = await db.integration_configs.find_one(
        {"id": integration_id}, {"_id": 0, "configured": 1, "connection_status": 1, "last_verified_at": 1},
    )
    if not cfg or not cfg.get("configured"):
        return {"status": "not_configured", "configured": False}
    return {
        "status": "configured",
        "configured": True,
        "connection_status": cfg.get("connection_status", "unknown"),
        "last_verified_at": cfg.get("last_verified_at"),
    }


@router.post("/master-admin/organizations/{org_id}/verify-mappings")
async def verify_org_mappings(
    org_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Sanity-check the tenant identifier codes (`customer_account_number`,
    `sage_customer_number`, `sicon_customer_number`) for an org.

    Returns one block per field with:
      • ``format_ok`` — non-empty, alphanumeric-ish (not pure whitespace)
      • ``collision`` — pointer to another org already using this code
      • ``auto_route_preview`` — count of rows that would be matched by Bulk
        Imports running with this code (useful sanity check)
    Also returns a ``sicon`` / ``orbit4`` block describing whether the
    integration is configured at the platform level. Pulse-only callers
    are scoped via the existing org-in-scope check.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Use the body codes when provided, else fall back to whatever's stored
    # on the org doc — lets the UI verify draft edits before saving.
    payload = body or {}
    candidates = {
        "customer_account_number": (payload.get("customer_account_number") or org.get("customer_account_number") or "").strip(),
        "sage_customer_number": (payload.get("sage_customer_number") or org.get("sage_customer_number") or "").strip(),
        "sicon_customer_number": (payload.get("sicon_customer_number") or org.get("sicon_customer_number") or "").strip(),
    }

    fields_for_collision = list(candidates.keys())
    field_results: dict = {}
    for field, value in candidates.items():
        if not value:
            field_results[field] = {
                "value": "",
                "format_ok": False,
                "collision": None,
                "note": "empty — set this code to enable Bulk Imports auto-routing for this tenant",
            }
            continue

        # Format check: at least 2 chars, no whitespace, only alnum + - _ . / allowed
        format_ok = (
            len(value) >= 2
            and all(ch.isalnum() or ch in "-_./" for ch in value)
        )
        collision = await _check_code_collision(value, fields_for_collision, org_id)
        # Auto-route preview — how many EQUIPMENT rows referencing this org
        # the Bulk Imports auto-routing would already match. Pure read.
        equipment_count = await db.equipment.count_documents({"organization_id": org_id})
        contact_count = await db.crm_contacts.count_documents({"organization_id": org_id})
        field_results[field] = {
            "value": value,
            "format_ok": format_ok,
            "collision": collision,
            "auto_route_preview": {
                "existing_equipment_in_tenant": equipment_count,
                "existing_contacts_in_tenant": contact_count,
            },
        }

    sicon = await _integration_status("sicon")
    orbit4 = await _integration_status("orbit4")

    # Top-level convenience flag — "all green" iff every populated code
    # has format_ok and zero collisions. Empty fields don't fail; they're
    # informational only.
    all_green = all(
        (r["format_ok"] and not r["collision"])
        for r in field_results.values()
        if r["value"]
    ) and any(r["value"] for r in field_results.values())

    return {
        "ok": True,
        "all_green": all_green,
        "fields": field_results,
        "integrations": {"sicon": sicon, "orbit4": orbit4},
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }




async def _create_org_user(org: dict, email: str, full_name: str, password: str, role: str, user_id: str):
    """Create a user in the appropriate collection(s) based on org portal type.

    Iter 215ev — when portal_type == 'both' we write to both collections
    with the SAME `id` so downstream listings can dedupe into one row
    per person (with portal badges), instead of showing the same human
    as two separate user rows. Was a real pain-point (see user bug
    report "Rob Yates doubled up").
    """
    now = datetime.now(timezone.utc).isoformat()
    portal_type = org.get("portal_type", "service_portal")
    is_crm = portal_type in ("crm", "both")
    is_sp = portal_type in ("service_portal", "both")

    if is_crm:
        from routes.crm_auth import crm_hash_password
        await db.crm_users.insert_one({
            "id": user_id, "email": email, "full_name": full_name,
            "password": crm_hash_password(password),
            "organization_id": org["id"], "role": role,
            "avatar_url": None, "created_at": now,
        })

    if is_sp:
        from utils.auth import hash_password
        await db.users.insert_one({
            "id": user_id,  # Iter 215ev — SAME id across both collections so listings dedupe cleanly.
            "email": email, "full_name": full_name,
            "password": hash_password(password),
            "organization_id": org["id"], "role": role,
            "account_type": org.get("account_type", "full"),
            "created_at": now,
        })

    return "CRM" if is_crm else "Service Portal"


@router.get("/master-admin/organizations/{org_id}/integration-health")
async def org_integration_health(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 216h21 — per-org integration health snapshot for the
    Organisations drawer's new Integrations tab (P4 redesign).

    READ-ONLY. Surfaces the connection state of every third-party
    integration that touches a single organisation:
      • stripe_connect — Stripe Express onboarding + platform fee
      • sicon          — Sicon Service (Sage 200 ledger) account ref
      • orbit4         — Orbit 4 stock / equipment master
      • sage200        — Sage 200 customer ledger

    The canonical editors for these connections live on the global
    Integrations pages — this endpoint just returns the per-org slice
    so operators don't have to bounce around the console.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Stripe Connect — pull whatever's persisted on the org doc plus
    # the platform-fee setting from `app_config` if available.
    stripe_account_id = org.get("stripe_connect_account_id") or org.get("stripe_account_id") or ""
    stripe_charges_enabled = bool(org.get("stripe_charges_enabled", False))
    stripe_payouts_enabled = bool(org.get("stripe_payouts_enabled", False))
    platform_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    platform_fee_pct = platform_cfg.get("platform_fee_pct")

    # Sicon — configured iff the org has a customer account ref AND
    # the platform-level Sicon integration is in `configured` state.
    sicon_platform = await _integration_status("sicon")
    sicon_account = org.get("sicon_customer_account_number") or org.get("sicon_customer_number") or ""
    sicon_auto_post = bool(org.get("sicon_auto_post", False))

    # Orbit 4 — same pattern.
    orbit_platform = await _integration_status("orbit4")
    orbit_customer = org.get("orbit4_customer_id") or ""

    # Sage 200 — currently lives via the customer number on the org
    # doc + the same Sicon bridge for posting. Treated as a separate
    # row in the UI because operators think of them separately.
    sage_account = org.get("sage_customer_number") or ""

    return {
        "org_id": org_id,
        "stripe_connect": {
            "connected": bool(stripe_account_id),
            "account_id": stripe_account_id,
            "charges_enabled": stripe_charges_enabled,
            "payouts_enabled": stripe_payouts_enabled,
            "platform_fee_pct": platform_fee_pct,
        },
        "sicon": {
            "configured": bool(sicon_account) and bool(sicon_platform.get("configured")),
            "platform_configured": bool(sicon_platform.get("configured")),
            "account_ref": sicon_account,
            "auto_post": sicon_auto_post,
        },
        "orbit4": {
            "configured": bool(orbit_customer) and bool(orbit_platform.get("configured")),
            "platform_configured": bool(orbit_platform.get("configured")),
            "customer_id": orbit_customer,
        },
        "sage200": {
            "configured": bool(sage_account),
            "account_ref": sage_account,
        },
    }

@router.get("/master-admin/integrations-hub")
async def integrations_hub(user: dict = Depends(get_current_user)):
    """Iter 216h22 — single round-trip status summary for the new
    Integrations Hub page (P5 redesign).

    READ-ONLY aggregate of the 4 third-party connections Master Admins
    care about most:
      • stripe_connect — platform-level Stripe Express OAuth, plus a
        count of orgs that have completed onboarding.
      • sicon          — Sicon Service (Sage 200 ledger) — config doc
        in `db.integrations` + per-org Sicon customer-number coverage.
      • orbit4         — Orbit 4 stock master — same shape as Sicon.
      • sage200        — Per-org Sage customer numbers (Sage is wired
        via the Sicon bridge — no separate platform creds).

    Per-row fields:
      • enabled             — platform-level toggle
      • status              — "connected" | "degraded" | "not_configured" | "down"
      • last_event_at       — most recent integration_logs timestamp
      • events_24h          — count of integration_logs in the last 24 h
      • errors_24h          — count where success=False in last 24 h
      • orgs_configured     — number of orgs that have the per-org ref
      • orgs_total          — total org count (for the brand currently filtered)
      • brand               — "all" | "pulse" | "gymaxis" — applied
                              to the orgs_configured/total counts.
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause
    brand = "all"
    # Pulse-only callers are pinned to the Pulse brand server-side too.
    if is_pulse_only(user):
        brand = "pulse"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()

    async def _row(integration_id: str, ref_field: str, label: str):
        """Build a per-integration row using the `integrations` and
        `integration_logs` collections plus per-org ref coverage."""
        cfg = await db.integrations.find_one({"integration_id": integration_id}, {"_id": 0}) or {}
        enabled = bool(cfg.get("enabled", False))
        events_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso},
        })
        errors_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso}, "success": False,
        })
        # Most recent event (any). For the "Last sync" pill.
        last_doc = await db.integration_logs.find_one(
            {"integration_id": integration_id},
            {"_id": 0, "timestamp": 1, "success": 1},
            sort=[("timestamp", -1)],
        )

        # Per-org ref coverage. Scope to the brand filter when present.
        org_query: dict = {}
        if brand == "pulse":
            org_query = brand_filter_clause("pulse")
        elif brand == "gymaxis":
            org_query = brand_filter_clause("gymaxis")

        orgs_total = await db.organizations.count_documents(org_query)
        ref_query = {**org_query, ref_field: {"$exists": True, "$ne": ""}}
        orgs_configured = await db.organizations.count_documents(ref_query) if ref_field else 0

        if not enabled and not orgs_configured:
            status = "not_configured"
        elif errors_24h > 0 and errors_24h >= max(1, events_24h // 5):
            status = "degraded"
        elif enabled:
            status = "connected"
        else:
            status = "not_configured"

        return {
            "key": integration_id,
            "label": label,
            "enabled": enabled,
            "status": status,
            "last_event_at": (last_doc or {}).get("timestamp"),
            "last_event_success": (last_doc or {}).get("success"),
            "events_24h": events_24h,
            "errors_24h": errors_24h,
            "orgs_configured": orgs_configured,
            "orgs_total": orgs_total,
            "ref_field": ref_field,
        }

    sicon_row  = await _row("sicon",  "sicon_customer_account_number", "Sicon Service (Sage 200 ledger)")
    orbit_row  = await _row("orbit4", "orbit4_customer_id",             "Orbit 4 (stock master)")

    # Stripe Connect is platform-level + per-org onboarding state.
    stripe_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    stripe_enabled = bool(stripe_cfg.get("enabled", True))  # Stripe is on unless explicitly off
    stripe_org_query: dict = {"stripe_connect_account_id": {"$exists": True, "$ne": ""}}
    if brand == "pulse":
        stripe_org_query = {**brand_filter_clause("pulse"), **stripe_org_query}
    elif brand == "gymaxis":
        stripe_org_query = {**brand_filter_clause("gymaxis"), **stripe_org_query}
    stripe_orgs_configured = await db.organizations.count_documents(stripe_org_query)
    stripe_orgs_total = await db.organizations.count_documents(
        brand_filter_clause(brand) if brand != "all" else {},
    )
    stripe_status = "connected" if stripe_orgs_configured > 0 else ("not_configured" if not stripe_enabled else "degraded")
    stripe_row = {
        "key": "stripe_connect",
        "label": "Stripe Connect",
        "enabled": stripe_enabled,
        "status": stripe_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": stripe_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "platform_fee_pct": stripe_cfg.get("platform_fee_pct"),
        "ref_field": "stripe_connect_account_id",
    }

    # Sage 200 is sub-integration: customer numbers stored on the org
    # doc, posts ride the Sicon bridge.
    sage_org_query = {**(brand_filter_clause(brand) if brand != "all" else {}), "sage_customer_number": {"$exists": True, "$ne": ""}}
    sage_orgs_configured = await db.organizations.count_documents(sage_org_query)
    sage_status = "connected" if sage_orgs_configured > 0 else "not_configured"
    sage_row = {
        "key": "sage200",
        "label": "Sage 200 (customer ledger)",
        "enabled": sage_orgs_configured > 0,
        "status": sage_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": sage_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "ref_field": "sage_customer_number",
    }

    summary = {
        "connected":      sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "connected"),
        "degraded":       sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "degraded"),
        "not_configured": sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "not_configured"),
        "total":          4,
    }

    return {
        "brand": brand,
        "integrations": [stripe_row, sicon_row, orbit_row, sage_row],
        "summary": summary,
    }







@router.post("/master-admin/users/{user_id}/invite-link")
async def issue_user_invite_link(user_id: str, user: dict = Depends(get_current_user)):
    """Iter 215ev — issue a signed set-password link for a user.

    Returns a URL the master admin can COPY and send manually (WhatsApp,
    their own email, Slack) while Resend DNS verification is pending —
    or use alongside automatic Resend delivery. 72h expiry. The user
    sets their own password on the linked page; master admin never
    sees the plaintext. Same mechanism is reused for "forgot password"
    resets (see /auth/forgot-password).
    """
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)

    target = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if not target:
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    import secrets as _secrets
    from datetime import timedelta as _td
    token = _secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": target["id"],
        "email": target.get("email", ""),
        "expires_at": expires_at,
        "used": False,
        "kind": "invite",  # distinguishes "set initial password" from "forgot password"
        "issued_by": user.get("email", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    invite_url = f"{frontend_url}/reset-password?token={token}"
    await log_activity("user_invite_link_issued", f"Invite link issued for {target.get('email')}", user["email"], "user", target["id"])
    return {
        "invite_url": invite_url,
        "expires_at": expires_at,
        "email": target.get("email", ""),
        "full_name": target.get("full_name", ""),
    }


@router.post("/master-admin/organizations/{org_id}/users")
async def add_user_to_organization(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Add a user to an existing organisation. Routes to correct collection based on portal_type."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    email = (body.get("email") or "").strip().lower()
    full_name = (body.get("full_name") or "").strip()
    password = body.get("password", "")
    role = body.get("role", "staff")
    # Iter 215ev — when no password is supplied we issue the user an
    # invite-link instead. They set their own password on first visit.
    # Master admin never handles the plaintext. See also
    # /master-admin/users/{user_id}/invite-link for re-issuing.
    invite_mode = not password
    if not email or not full_name:
        raise HTTPException(status_code=400, detail="email and full_name are required")

    # Iter 216h25 — return existing user_id + collection in the 409
    # payload so the frontend toast can render a "Jump to this user"
    # link directly into People → Directory drawer.
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1})
    collection = "users"
    if not existing:
        existing = await db.crm_users.find_one({"email": email}, {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1})
        collection = "crm_users"
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "user_exists",
                "message": f"User {email} already exists",
                "user_id": existing.get("id"),
                "full_name": existing.get("full_name"),
                "organization_id": existing.get("organization_id"),
                "collection": collection,
                "email": email,
            },
        )

    user_id = str(uuid.uuid4())
    # In invite mode we store a random high-entropy placeholder so the
    # row is valid; the user will overwrite it via the /auth/reset-password
    # endpoint when they follow the invite link.
    effective_password = password or secrets.token_urlsafe(32)
    # Iter 216k — `master_admin` role grants platform-wide access. The
    # user still belongs to the org doc (so they appear in its Users
    # tab and can switch context to it) but is_master_admin=True
    # elevates them in every guard. We persist the role as 'owner' on
    # the org-scoped fields so existing queries that look at role keep
    # working, and stamp is_master_admin separately.
    storage_role = "owner" if role == "master_admin" else role
    collection = await _create_org_user(org, email, full_name, effective_password, storage_role, user_id)
    if role == "master_admin":
        # _create_org_user returns "Service Portal" or "CRM", not collection names
        target_coll = db.users if collection == "Service Portal" else db.crm_users
        await target_coll.update_one(
            {"id": user_id},
            {"$set": {"is_master_admin": True, "role": "owner"}},
        )

    invite_url = None
    invite_expires_at = None
    if invite_mode:
        # Mint a 72h invite token so the UI can surface a copy-able link
        # straight back (for WhatsApp / manual email until Resend DNS
        # verification is done).
        from datetime import timedelta as _td
        token = secrets.token_urlsafe(32)
        invite_expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user_id, "email": email,
            "expires_at": invite_expires_at, "used": False, "kind": "invite",
            "issued_by": user.get("email", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
        invite_url = f"{frontend_url}/reset-password?token={token}"

    await log_activity("user_added_to_org", f"Added {email} to {org['name']} ({collection}){' [invite]' if invite_mode else ''}", user["email"], "user", user_id)
    return {
        "id": user_id, "email": email, "full_name": full_name,
        "role": role, "portal": collection,
        "invite_mode": invite_mode,
        "invite_url": invite_url,
        "invite_expires_at": invite_expires_at,
    }



@router.get("/master-admin/users")
async def get_all_users(user: dict = Depends(get_current_user), brand: str = "all"):
    require_master_admin(user)

    # Pulse-only admins see users belonging to Pulse-visible orgs only.
    pulse_org_ids: Optional[set] = None
    if is_pulse_only(user):
        pulse_org_docs = await db.organizations.find(
            {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
            {"_id": 0, "id": 1},
        ).to_list(length=None)
        pulse_org_ids = {o["id"] for o in pulse_org_docs}
        user_filter = {"organization_id": {"$in": list(pulse_org_ids)}}
    else:
        user_filter = {}

    # Iter 216h18 — Master Admin brand context filter.
    from utils.brand_filter import merge_brand_filter, normalise_brand
    canonical_brand = normalise_brand(brand)
    if canonical_brand != "all":
        # If a specific brand is requested, scope by org account_type
        # so that even legacy users whose own `account_type` is null
        # follow their parent org's brand (the org is authoritative).
        org_brand_filter = merge_brand_filter({}, brand, collection="organizations")
        if org_brand_filter:
            brand_org_docs = await db.organizations.find(
                org_brand_filter, {"_id": 0, "id": 1},
            ).to_list(length=None)
            brand_org_ids = {o["id"] for o in brand_org_docs}
            # Intersect with the pulse-only set if applicable.
            if pulse_org_ids is not None:
                brand_org_ids &= pulse_org_ids
            user_filter["organization_id"] = {"$in": list(brand_org_ids) or [""]}

    sp_users = await db.users.find(user_filter, {"_id": 0, "password": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    crm_list = await db.crm_users.find(user_filter, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(1000)

    # Iter 215ev — dedupe by email so a single human that exists in both
    # `users` (Service Portal) and `crm_users` (CRM) renders as ONE row
    # in the UI. We merge with a `portals` array so the frontend can
    # show badges for each system the user can access. Service Portal
    # row is treated as the "primary" (it owns disabled/archived state).
    merged_by_email: dict[str, dict] = {}
    for u in sp_users:
        k = (u.get("email") or "").lower()
        u = dict(u)
        u["portals"] = ["service_portal"]
        u["user_type"] = "service_portal"  # legacy field retained for older callers
        merged_by_email[k] = u
    for u in crm_list:
        k = (u.get("email") or "").lower()
        if k in merged_by_email:
            existing = merged_by_email[k]
            if "crm" not in existing.get("portals", []):
                existing["portals"].append("crm")
            # Copy avatar if SP row didn't have one.
            if not existing.get("avatar_url") and u.get("avatar_url"):
                existing["avatar_url"] = u["avatar_url"]
        else:
            u = dict(u)
            u["portals"] = ["crm"]
            u["user_type"] = "crm"
            merged_by_email[k] = u
    all_users = list(merged_by_email.values())

    # Iter 216g — Pulse Platform Admins can be ATTACHED to one or more orgs
    # via `organization_memberships`. They keep their cross-org platform
    # role but should also surface inside each attached org's user list.
    # We fan a virtual row per (admin × org_membership) so the existing
    # `users.filter(u => u.organization_id === orgId)` UI logic works
    # without changes.
    pulse_with_membership = await db.users.find(
        {"role": "pulse_master_admin", "organization_memberships": {"$exists": True, "$ne": []}},
        {"_id": 0, "password": 0, "password_hash": 0},
    ).to_list(500)
    seen_keys: set[tuple[str, str]] = {
        ((u.get("email") or "").lower(), u.get("organization_id") or "")
        for u in all_users
    }
    for admin in pulse_with_membership:
        email = (admin.get("email") or "").lower()
        for oid in admin.get("organization_memberships") or []:
            if (email, oid) in seen_keys:
                continue
            row = dict(admin)
            row["organization_id"] = oid
            row["portals"] = list(set((row.get("portals") or []) + ["service_portal", "crm"]))
            row["user_type"] = "pulse_master_admin"
            row["is_pulse_master_admin"] = True
            row["display_role"] = "Pulse Platform Admin"
            all_users.append(row)
            seen_keys.add((email, oid))

    # Tier-3.5 N+1 fix: was `find_one` per user (2000 round-trips for 2000
    # users). Now: one batched fetch of all referenced orgs.
    org_ids = {u.get("organization_id") for u in all_users if u.get("organization_id")}
    orgs = await db.organizations.find(
        {"id": {"$in": list(org_ids)}},
        {"_id": 0, "id": 1, "name": 1, "status": 1},
    ).to_list(length=None)
    org_map = {o["id"]: o for o in orgs}

    for u in all_users:
        org = org_map.get(u.get("organization_id"))
        u["organization_name"] = org.get("name", "") if org else "N/A"
        u["org_status"] = org.get("status", "active") if org else "N/A"

    # Iter 216h3 — Role-mismatch detection. Fetch the most-recent accepted
    # invite per (email, org_id) and stamp `invited_role` on the user doc
    # ONLY when it differs from their current role. The frontend renders a
    # small warning badge so operators can spot users whose invited role
    # was changed (legitimately or otherwise) after they joined.
    pairs = [(u.get("email"), u.get("organization_id")) for u in all_users if u.get("email") and u.get("organization_id")]
    if pairs:
        emails = list({p[0] for p in pairs})
        org_ids_for_invites = list({p[1] for p in pairs})
        invites = await db.invites.find(
            {
                "email": {"$in": emails},
                "organization_id": {"$in": org_ids_for_invites},
                "status": "accepted",
            },
            {"_id": 0, "email": 1, "organization_id": 1, "role": 1, "accepted_at": 1, "created_at": 1},
        ).to_list(length=None)
        # Keep the most-recent accepted invite per (email, org_id).
        invite_lookup: dict[tuple[str, str], dict] = {}
        for inv in invites:
            key = ((inv.get("email") or "").lower(), inv.get("organization_id") or "")
            existing = invite_lookup.get(key)
            ts = inv.get("accepted_at") or inv.get("created_at") or ""
            existing_ts = (existing or {}).get("_ts", "")
            if not existing or ts > existing_ts:
                invite_lookup[key] = {**inv, "_ts": ts}
        for u in all_users:
            key = ((u.get("email") or "").lower(), u.get("organization_id") or "")
            inv = invite_lookup.get(key)
            if inv and inv.get("role") and inv["role"] != u.get("role"):
                u["invited_role"] = inv["role"]

    return {"users": all_users}


@router.put("/master-admin/users/{user_id}/edit")
async def admin_edit_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Master admin edits user details: name, email, role, job_title, module_overrides."""
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    allowed = {"full_name", "email", "role", "job_title", "phone", "module_overrides", "allowed_site_ids"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "email" in updates:
        updates["email"] = updates["email"].lower().strip()

    # Iter 216bk — site-locking. allowed_site_ids is a list of site UUIDs
    # the user may see; empty list = unrestricted (the legacy default).
    # Owners/master admins always bypass this in the read path
    # (see routes/sites.py::get_my_sites), but we still persist it so a
    # later role downgrade keeps the assignment intact.
    if "allowed_site_ids" in updates:
        raw = updates["allowed_site_ids"] or []
        if not isinstance(raw, list):
            raise HTTPException(400, "allowed_site_ids must be an array")
        updates["allowed_site_ids"] = [str(x) for x in raw if x]
        # Iter 216bm — stamp a "permissions changed" timestamp so the
        # locked-staff audit panel can show when each restriction last
        # moved. Mirrors what update_staff_permissions does.
        updates["permissions_updated_at"] = datetime.now(timezone.utc).isoformat()

    # Iter 216a — per-user feature editor.
    # `module_overrides` is a {module: bool} dict that REVOKES org-level
    # access for this user. It cannot grant access the org doesn't have
    # (see utils/module_access.py:resolve_module_access). Owners and
    # master admins ignore overrides entirely. We coerce the payload to
    # only valid module keys + bool values to keep the doc clean.
    if "module_overrides" in updates:
        from utils.module_access import MODULE_KEYS as _MK
        raw = updates["module_overrides"] or {}
        if not isinstance(raw, dict):
            raise HTTPException(400, "module_overrides must be an object")
        updates["module_overrides"] = {k: bool(v) for k, v in raw.items() if k in _MK}

    if not updates:
        raise HTTPException(400, "No valid fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Iter 216k — promoting a user to Master Admin via the role field.
    # We translate role=master_admin into is_master_admin=True + role=owner
    # so that downstream guards (which check is_master_admin) light up
    # without breaking org-level role-based queries that expect one of
    # owner/manager/staff.
    if updates.get("role") == "master_admin":
        updates["role"] = "owner"
        updates["is_master_admin"] = True

    result = await db.users.update_one({"id": user_id}, {"$set": updates})
    if result.modified_count == 0:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": updates})
    if result.modified_count == 0:
        raise HTTPException(404, "User not found")
    await log_activity("user_edited", f"Edited user {user_id}: {list(updates.keys())}", user["email"], "user", user_id)
    return {"success": True}


@router.put("/master-admin/users/{user_id}/disable")
async def disable_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    disabled = body.get("disabled", True)
    result = await db.users.update_one({"id": user_id}, {"$set": {"disabled": disabled}})
    if result.modified_count == 0:
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"disabled": disabled}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await log_activity("user_disable" if disabled else "user_enable", f"{'Disabled' if disabled else 'Enabled'} user {user_id}", user["email"], "user", user_id)
    return {"success": True}


@router.put("/master-admin/users/{user_id}/archive")
async def archive_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    archived = body.get("archived", True)
    result = await db.users.update_one({"id": user_id}, {"$set": {"archived": archived}})
    if result.modified_count == 0:
        # Try CRM users collection
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"archived": archived}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    action = "user_archived" if archived else "user_unarchived"
    await log_activity(action, f"{'Archived' if archived else 'Unarchived'} user {user_id}", user["email"], "user", user_id)
    return {"success": True}


@router.delete("/master-admin/users/{user_id}")
async def hard_delete_user(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Permanently delete an archived user and cascade their personal data.

    Strict rules:
      • Caller must be master admin OR an owner/manager of the user's org.
      • Target must already be `archived=True` (force a soft-delete first).
      • Master admins cannot be hard-deleted (avoids platform lockout).
      • The sole owner of an org cannot be hard-deleted (avoids orphan org).
      • The dedicated `admin@gymaxisai.com` is never deletable.
      • Caller must echo back the target's email in `confirm_email`.

    Cascade scope (best-effort, never blocks the delete on a single failure):
      issues (raised_by/user_id), audit_logs (target_id), files (uploaded_by),
      activity_log (target_id), notifications (user_id), invites (email),
      members (user_id) where applicable, password_reset_tokens (user_id),
      ui_error_events (user_id), security_events (target_id),
      crm_audits (user_id), notes (created_by/user_id),
      member_documents (uploaded_by), trust_events (user_id),
      api_keys (user_id), mfa_secrets (user_id), refresh_tokens (user_id).
    """
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        # Try CRM users collection
        target = await db.crm_users.find_one({"id": user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        is_crm = True
    else:
        is_crm = False

    # ── Authorization — master admin OR owner/manager of same org ────
    is_admin = bool(user.get("is_master_admin"))
    if not is_admin:
        same_org = (
            user.get("organization_id")
            and user.get("organization_id") == target.get("organization_id")
        )
        if not same_org or user.get("role") not in ("owner", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Only master admin, or an owner/manager in the same organisation, can hard-delete users.",
            )

    # ── Hard guards ──────────────────────────────────────────────────
    if not target.get("archived"):
        raise HTTPException(
            status_code=400,
            detail="User must be archived first. Archive then delete.",
        )
    if target.get("is_master_admin"):
        raise HTTPException(
            status_code=400,
            detail="Master admin accounts cannot be hard-deleted.",
        )
    if (target.get("email") or "").lower() == "admin@gymaxisai.com":
        raise HTTPException(
            status_code=400,
            detail="The default platform admin account cannot be deleted.",
        )

    # If they're the only owner of the org, refuse — would orphan the org.
    if not is_crm and target.get("role") == "owner" and target.get("organization_id"):
        siblings = await db.users.count_documents({
            "organization_id": target["organization_id"],
            "role": "owner",
            "id": {"$ne": user_id},
            "archived": {"$ne": True},
        })
        if siblings == 0:
            raise HTTPException(
                status_code=400,
                detail="This is the only owner of the organisation. Promote another user before deleting.",
            )

    # ── Confirmation — caller must echo back the email ──────────────
    confirm_email = (body.get("confirm_email") or "").strip().lower()
    if confirm_email != (target.get("email") or "").lower():
        raise HTTPException(
            status_code=400,
            detail="Confirmation email does not match the target user's email.",
        )

    # ── Cascade delete personal data (best-effort) ──────────────────
    cascade_summary: dict[str, int] = {}
    target_email = (target.get("email") or "").lower()

    async def _safe_delete(coll_name: str, query: dict):
        try:
            res = await getattr(db, coll_name).delete_many(query)
            if res.deleted_count:
                cascade_summary[coll_name] = cascade_summary.get(coll_name, 0) + res.deleted_count
        except Exception as exc:
            logger.warning("Cascade delete on %s failed: %s", coll_name, exc)

    cascade_specs = [
        ("issues",                {"$or": [{"user_id": user_id}, {"raised_by": user_id}]}),
        ("notes",                 {"$or": [{"user_id": user_id}, {"created_by": user_id}]}),
        ("files",                 {"uploaded_by": user_id}),
        ("audit_logs",            {"$or": [{"user_id": user_id}, {"target_id": user_id}]}),
        ("activity_log",          {"$or": [{"user_id": user_id}, {"target_id": user_id}]}),
        ("notifications",         {"user_id": user_id}),
        ("invites",               {"email": target_email}),
        ("password_reset_tokens", {"user_id": user_id}),
        ("ui_error_events",       {"user_id": user_id}),
        ("security_audit_log",    {"$or": [{"actor_id": user_id}, {"target_id": user_id}]}),
        ("crm_audits",            {"user_id": user_id}),
        ("member_documents",      {"uploaded_by": user_id}),
        ("trust_events",          {"user_id": user_id}),
        ("api_keys",              {"user_id": user_id}),
        ("mfa_secrets",           {"user_id": user_id}),
        ("refresh_tokens",        {"user_id": user_id}),
        ("user_sessions",         {"user_id": user_id}),
    ]
    for coll, query in cascade_specs:
        await _safe_delete(coll, query)

    # ── Finally, delete the user document itself ────────────────────
    coll = db.crm_users if is_crm else db.users
    res = await coll.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User no longer exists")

    # ── Audit + activity trail ──────────────────────────────────────
    try:
        await log_activity(
            "user_hard_deleted",
            f"Permanently deleted user {target_email} ({user_id}). Cascade: {cascade_summary}",
            user["email"],
            "user",
            user_id,
        )
    except Exception:
        pass
    logger.warning(
        "[hard-delete] user_id=%s email=%s by=%s cascade=%s",
        user_id, target_email, user.get("email"), cascade_summary,
    )

    return {
        "success": True,
        "deleted_user_id": user_id,
        "email": target_email,
        "cascade": cascade_summary,
    }



@router.put("/master-admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    import bcrypt
    import secrets as _secrets
    # P0.5 — generate a one-time cryptographic password for every reset.
    # Never reuse a shared default; the admin must communicate this via a
    # secure channel and the user is forced to change it at next login.
    temp_password = _secrets.token_urlsafe(16)
    hashed = bcrypt.hashpw(temp_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Try service portal users first
    result = await db.users.update_one({"id": user_id}, {"$set": {"password": hashed, "password_reset_required": True}})
    target_email = None
    if result.modified_count > 0:
        target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1})
        target_email = (target or {}).get("email")
    else:
        # Try CRM users
        result = await db.crm_users.update_one({"id": user_id}, {"$set": {"password": hashed, "password_reset_required": True}})
        if result.modified_count > 0:
            target = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "email": 1})
            target_email = (target or {}).get("email")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Iter 215bh — keep the org's "Primary contact login" reveal panel in
    # sync. If the user we just reset is the org's primary contact, write
    # the fresh temp_password back into the org doc so the Master Admin can
    # see (and copy) it from the reveal panel after the toast is gone.
    if target_email:
        await db.organizations.update_many(
            {"primary_contact_email": target_email.strip().lower()},
            {"$set": {
                "primary_contact_initial_password": temp_password,
                "primary_contact_password_changed": False,
            }},
        )

    await log_activity("password_reset", f"Reset password for user {user_id}", user["email"], "user", user_id)
    return {"success": True, "temp_password": temp_password, "user_email": target_email}


@router.get("/master-admin/activity-log")
async def get_activity_log(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    # Admin actions
    admin_logs = await db.admin_activity_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(200)

    # Recent user logins (from users collection last_login field)
    recent_users = await db.users.find({"last_login": {"$exists": True}}, {"_id": 0, "email": 1, "full_name": 1, "last_login": 1, "organization_id": 1}).sort("last_login", -1).to_list(50)
    login_logs = [{"action": "user_login", "details": f"{u.get('full_name', u['email'])} logged in", "admin_email": u["email"], "timestamp": u["last_login"], "target_type": "user"} for u in recent_users if u.get("last_login")]

    all_logs = admin_logs + login_logs
    all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"logs": all_logs[:200]}


@router.get("/master-admin/ai-usage")
async def get_ai_usage(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    if not orgs:
        return {"usage": [], "total_calls": 0}

    # Tier-3.5 N+1 fix: was 3×N count_documents (1500 round-trips for 500
    # orgs). Now: 3 batched $group aggregates running in parallel.
    import asyncio

    org_ids = [o["id"] for o in orgs]

    async def _group(coll, match=None):
        pipe = [{"$match": {"organization_id": {"$in": org_ids}}}]
        if match:
            pipe.append({"$match": match})
        pipe.append({"$group": {"_id": "$organization_id", "c": {"$sum": 1}}})
        return {d["_id"]: d["c"] for d in await coll.aggregate(pipe).to_list(length=None)}

    triage_map, audit_map, ra_map = await asyncio.gather(
        _group(db.issues, {"ai_triage": {"$exists": True, "$ne": None}}),
        _group(db.audits),
        _group(db.risk_assessments),
    )

    usage = []
    for org in orgs:
        oid = org["id"]
        triage = triage_map.get(oid, 0)
        audits = audit_map.get(oid, 0)
        ra = ra_map.get(oid, 0)
        total = triage + audits + ra
        if total > 0:
            usage.append({
                "org_id": oid,
                "org_name": org["name"],
                "triage_calls": triage,
                "audit_reports": audits,
                "risk_assessments": ra,
                "total_calls": total,
                "estimated_cost": round(total * 0.03, 2),
            })
    usage.sort(key=lambda x: x["total_calls"], reverse=True)
    return {"usage": usage, "total_calls": sum(u["total_calls"] for u in usage)}


@router.get("/master-admin/emails")
async def get_email_log(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    # Pull from supplier cases which track email sends
    cases = await db.supplier_cases.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    emails = []
    for c in cases:
        emails.append({
            "id": c.get("id", ""),
            "type": "supplier_case",
            "to": c.get("supplier_email", ""),
            "subject": f"Fault Report — {c.get('serial_number', '')}",
            "status": c.get("status", "sent"),
            "org_id": c.get("organization_id", ""),
            "created_at": c.get("created_at", ""),
        })

    # PO emails
    pos = await db.purchase_orders.find({"emailed": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for po in pos:
        emails.append({
            "id": po.get("id", ""),
            "type": "purchase_order",
            "to": po.get("supplier_email", ""),
            "subject": f"Purchase Order — {po.get('po_number', '')}",
            "status": "sent",
            "org_id": po.get("organization_id", ""),
            "created_at": po.get("created_at", ""),
        })

    emails.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"emails": emails}


@router.post("/master-admin/impersonate/{user_id}")
async def impersonate_user(user_id: str, user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_user_in_pulse_scope(user, user_id)
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    import jwt
    from utils.database import JWT_SECRET as _JWT_SECRET, JWT_ALGORITHM as _JWT_ALGO
    from utils.security_plus import new_jti
    token = jwt.encode({
        "user_id": target["id"],
        "email": target["email"],
        "organization_id": target.get("organization_id", ""),
        "role": target.get("role", "member"),
        "impersonated_by": user["email"],
        "jti": new_jti(),
        "exp": datetime.now(timezone.utc) + timedelta(hours=2),
    }, _JWT_SECRET, algorithm=_JWT_ALGO)

    await log_activity("impersonate", f"Impersonated user {target['email']}", user["email"], "user", user_id)
    return {"token": token, "user": target}


async def _collect_org_site_stats(org: dict) -> dict:
    """Collect stats for a single Pulse organization."""
    org_id = org["id"]
    user_count = await db.users.count_documents({"organization_id": org_id})
    equip_count = await db.equipment.count_documents({"organization_id": org_id})
    issue_count = await db.issues.count_documents({"organization_id": org_id})
    open_count = await db.issues.count_documents({"organization_id": org_id, "status": "open"})
    resolved_count = await db.issues.count_documents({"organization_id": org_id, "status": {"$in": ["resolved", "closed"]}})
    file_count = await db.files.count_documents({"organization_id": org_id})
    owner = await db.users.find_one({"organization_id": org_id, "role": "owner"}, {"_id": 0, "email": 1, "full_name": 1, "last_login": 1})
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent_faults = await db.issues.count_documents({"organization_id": org_id, "created_at": {"$gte": thirty_days_ago}})
    price = 79 if org.get("account_type") == "pulse_pro" else 29

    return {
        "id": org_id, "name": org["name"], "account_type": org.get("account_type", "lite"),
        "status": org.get("status", "active"), "subscription_tier": org.get("subscription_tier", "free"),
        "user_count": user_count, "equipment_count": equip_count,
        "total_faults": issue_count, "open_faults": open_count, "resolved_faults": resolved_count,
        "recent_faults_30d": recent_faults, "file_count": file_count, "monthly_cost": price,
        "owner_email": (owner or {}).get("email", ""), "owner_name": (owner or {}).get("full_name", ""),
        "last_owner_login": (owner or {}).get("last_login", ""), "created_at": org.get("created_at", ""),
    }


def _aggregate_pulse_totals(sites: list) -> dict:
    """Sum the 5 counter fields across all site dicts."""
    keys = ("user_count", "equipment_count", "total_faults", "open_faults", "file_count")
    return {k: sum(s.get(k, 0) for s in sites) for k in keys}


@router.get("/master-admin/pulse-stats")
async def get_pulse_stats(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    pulse_orgs = await db.organizations.find({"account_type": {"$in": ["lite", "pulse_pro"]}}, {"_id": 0}).to_list(500)

    sites = [await _collect_org_site_stats(org) for org in pulse_orgs]
    lite_count = sum(1 for s in sites if s["account_type"] == "lite")
    pro_count = sum(1 for s in sites if s["account_type"] == "pulse_pro")
    totals = _aggregate_pulse_totals(sites)

    return {
        "total_sites": len(sites), "lite_sites": lite_count, "pro_sites": pro_count,
        "total_users": totals["user_count"],
        "total_equipment": totals["equipment_count"],
        "total_faults": totals["total_faults"],
        "open_faults": totals["open_faults"],
        "total_files": totals["file_count"],
        "mrr": (lite_count * 29) + (pro_count * 79),
        "sites": sites,
    }



# ─── Pulse Fitness Standard Equipment Kits ───
PULSE_EQUIPMENT_KITS = {
    "cardio_starter": {
        "name": "Cardio Starter Kit",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 3},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 3},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
        ],
    },
    "cardio_full": {
        "name": "Cardio Full Kit",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 8},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Spin Bike", "equipment_type": "Spin Bike", "manufacturer": "Pulse Fitness", "quantity": 6},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Stairclimber", "equipment_type": "Stairclimber", "manufacturer": "Pulse Fitness", "quantity": 2},
        ],
    },
    "strength_starter": {
        "name": "Strength Starter Kit",
        "items": [
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 3},
        ],
    },
    "strength_full": {
        "name": "Strength Full Kit",
        "items": [
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Shoulder Press", "equipment_type": "Shoulder Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Functional Trainer", "equipment_type": "Functional Trainer", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Power Rack", "equipment_type": "Power Rack", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 6},
        ],
    },
    "complete_gym": {
        "name": "Complete Gym Package",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 8},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Spin Bike", "equipment_type": "Spin Bike", "manufacturer": "Pulse Fitness", "quantity": 6},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Stairclimber", "equipment_type": "Stairclimber", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Shoulder Press", "equipment_type": "Shoulder Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Functional Trainer", "equipment_type": "Functional Trainer", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Power Rack", "equipment_type": "Power Rack", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 6},
        ],
    },
}


@router.get("/master-admin/pulse-equipment-kits")
async def get_pulse_equipment_kits(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    kits = {}
    for kit_id, kit in PULSE_EQUIPMENT_KITS.items():
        total = sum(i["quantity"] for i in kit["items"])
        kits[kit_id] = {"name": kit["name"], "total_items": total, "items": kit["items"]}
    return {"kits": kits}


from utils.auth import hash_password as _hash_password


async def _create_onboard_users(data: dict, config: dict) -> list[dict]:
    """Create owner + additional users for the onboarded site.
    config keys: org_id, owner_id, owner_email, owner_name, owner_password, now, account_type
    """
    org_id = config["org_id"]
    owner_doc = {
        "id": config["owner_id"], "email": config["owner_email"],
        "password": _hash_password(config["owner_password"]), "full_name": config["owner_name"],
        "organization_id": org_id, "role": "owner", "account_type": config["account_type"],
        "created_at": config["now"],
    }
    await db.users.insert_one(owner_doc)
    created = [{"id": config["owner_id"], "email": config["owner_email"], "name": config["owner_name"], "role": "owner"}]

    for u in data.get("users", []):
        u_email = u.get("email", "").strip().lower()
        u_name = u.get("name", "").strip()
        u_password = u.get("password", "").strip()
        if not u_email or not u_name or not u_password:
            continue
        if await db.users.find_one({"email": u_email}, {"_id": 0, "id": 1}):
            continue
        u_id = str(uuid.uuid4())
        u_role = u.get("role", "staff")
        user_doc = {
            "id": u_id, "email": u_email,
            "password": _hash_password(u_password), "full_name": u_name,
            "organization_id": org_id,
            "role": u_role if u_role in ("manager", "staff") else "staff",
            "account_type": config["account_type"], "created_at": config["now"],
        }
        await db.users.insert_one(user_doc)
        created.append({"id": u_id, "email": u_email, "name": u_name, "role": user_doc["role"]})
    return created


async def _create_kit_equipment(kit: dict, org_id: str, owner_id: str, location: str, now: str) -> int:
    """Create equipment from a predefined kit. Returns count created."""
    count = 0
    for item in kit["items"]:
        for i in range(item["quantity"]):
            equip_doc = {
                "id": str(uuid.uuid4()), "user_id": owner_id, "organization_id": org_id,
                "name": f"{item['name']} {i+1}" if item["quantity"] > 1 else item["name"],
                "equipment_type": item["equipment_type"],
                "manufacturer": item.get("manufacturer", "Pulse Fitness"),
                "model": item.get("model"), "serial_number": None,
                "location": location,
                "manuals": [], "photos": [], "created_at": now, "updated_at": now,
            }
            await db.equipment.insert_one(equip_doc)
            count += 1
    return count


async def _create_manual_equipment(eq_list: list, org_id: str, owner_id: str, default_location: str, now: str) -> int:
    """Create equipment from a manual list. Returns count created."""
    count = 0
    for eq in eq_list:
        eq_name = eq.get("name", "").strip()
        eq_type = eq.get("equipment_type", "").strip()
        if not eq_name or not eq_type:
            continue
        equip_doc = {
            "id": str(uuid.uuid4()), "user_id": owner_id, "organization_id": org_id,
            "name": eq_name, "equipment_type": eq_type,
            "manufacturer": eq.get("manufacturer", "Pulse Fitness"), "model": eq.get("model"),
            "serial_number": eq.get("serial_number"),
            "location": eq.get("location", default_location),
            "purchase_date": _parse_onboard_date(eq.get("install_date") or eq.get("purchase_date") or ""),
            "purchase_price": eq.get("unit_price", 0),
            "warranty_expiry": _parse_onboard_date(eq.get("warranty_expiry", "")),
            "warranty_code": eq.get("warranty_code", ""),
            "sla_level": eq.get("sla_name", "") or eq.get("sla_level", ""),
            "status": "operational", "condition": "excellent",
            "manuals": [], "photos": [], "created_at": now, "updated_at": now,
        }
        await db.equipment.insert_one(equip_doc)
        count += 1
    return count


async def _create_onboard_equipment(data: dict, org_id: str, owner_id: str, now: str) -> int:
    """Create equipment from kit and/or manual list. Returns count created."""
    count = 0
    default_location = data.get("default_location", "Main Floor")
    equipment_kit = data.get("equipment_kit")
    if equipment_kit and equipment_kit in PULSE_EQUIPMENT_KITS:
        count += await _create_kit_equipment(PULSE_EQUIPMENT_KITS[equipment_kit], org_id, owner_id, default_location, now)
    count += await _create_manual_equipment(data.get("equipment", []), org_id, owner_id, default_location, now)
    return count


async def _validate_onboard_data(data: dict) -> tuple[str, str, str, str, str]:
    """Validate and extract onboarding data. Returns (site_name, tier, email, name, password)."""
    site_name = data.get("site_name", "").strip()
    tier = data.get("tier", "lite")
    if tier not in ("lite", "pro"):
        raise HTTPException(status_code=400, detail="Tier must be 'lite' or 'pro'")
    if not site_name:
        raise HTTPException(status_code=400, detail="Site name is required")
    email = data.get("owner_email", "").strip().lower()
    name = data.get("owner_name", "").strip()
    password = data.get("owner_password", "").strip()
    if not email or not name or not password:
        raise HTTPException(status_code=400, detail="Owner email, name, and password are required")
    if await db.users.find_one({"email": email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {email} already in use")
    return site_name, tier, email, name, password


@router.post("/master-admin/onboard-pulse-site")
async def onboard_pulse_site(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Full Pulse Fitness site onboarding."""
    require_master_admin(user)
    site_name, tier, owner_email, owner_name, owner_password = await _validate_onboard_data(data)

    org_id, owner_id = str(uuid.uuid4()), str(uuid.uuid4())
    company_code = str(uuid.uuid4())[:8].upper()
    account_type = f"pulse_{tier}"
    now = datetime.now(timezone.utc).isoformat()

    # Iter 215en — accept the structured 8-field address alongside the
    # legacy single-line `address`. We auto-compose the legacy field so
    # downstream Sage / Sicon outboxes keep working unchanged.
    org_addr = merge_address(data)
    site_addr = merge_address({**data, "address": data.get("site_address") or data.get("address", "")})

    await db.organizations.insert_one({
        "id": org_id, "name": site_name, "company_code": company_code, "owner_id": owner_id,
        "created_at": now, "subscription_tier": tier, "account_type": account_type,
        "address": org_addr["address"],
        "address_line1": org_addr["address_line1"],
        "address_line2": org_addr["address_line2"],
        "address_line3": org_addr["address_line3"],
        "city": org_addr["city"],
        "county": org_addr["county"],
        "postcode": org_addr["postcode"],
        "country": org_addr["country"],
        "contact_person": owner_name, "email": owner_email,
        "phone": data.get("phone", ""), "branding": {"primary_color": "#66ccff", "company_name": "Pulse Fitness"},
    })

    site_id = str(uuid.uuid4())
    await db.sites.insert_one({
        "id": site_id, "organization_id": org_id,
        "name": data.get("site_address_name", site_name),
        "address": site_addr["address"],
        "address_line1": site_addr["address_line1"],
        "address_line2": site_addr["address_line2"],
        "address_line3": site_addr["address_line3"],
        "city": site_addr["city"],
        "county": site_addr["county"],
        "postcode": site_addr["postcode"],
        "country": site_addr["country"],
        "created_at": now,
    })

    created_users = await _create_onboard_users(data, {
        "org_id": org_id, "owner_id": owner_id, "owner_email": owner_email,
        "owner_name": owner_name, "owner_password": owner_password,
        "now": now, "account_type": account_type,
    })
    created_equipment = await _create_onboard_equipment(data, org_id, owner_id, now)

    await log_activity("pulse_site_onboarded", f"Onboarded Pulse {tier.upper()} site: {site_name}", user.get("email", ""), "organization", org_id)
    return {
        "success": True,
        "organization": {"id": org_id, "name": site_name, "company_code": company_code, "tier": tier, "account_type": account_type},
        "site": {"id": site_id, "name": data.get("site_address_name", site_name)},
        "users": created_users, "equipment_count": created_equipment,
    }


# ─────────────────────────────────────────────────────────────────
# Iter 216d — Master-admin per-org site CRUD.
# Lets master admins add or bulk-add sites to an existing org without
# impersonating the owner. The owner-scoped endpoints in routes/sites.py
# require role=owner|manager, which master admins are NOT (they have a
# separate is_master_admin flag).
# ─────────────────────────────────────────────────────────────────

@router.post("/master-admin/organizations/{org_id}/sites")
async def admin_create_site(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create a single site under any org (master-admin only)."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Site name is required")

    site_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": name,
        "address": (body.get("address") or "").strip(),
        "address_line1": (body.get("address_line1") or "").strip(),
        "address_line2": (body.get("address_line2") or "").strip(),
        "address_line3": (body.get("address_line3") or "").strip(),
        "city": (body.get("city") or "").strip(),
        "county": (body.get("county") or "").strip(),
        "postcode": (body.get("postcode") or "").strip(),
        "country": (body.get("country") or "United Kingdom").strip(),
        "phone": (body.get("phone") or "").strip(),
        "email": (body.get("email") or "").strip(),
        "site_manager_name": (body.get("site_manager_name") or "").strip(),
        "site_manager_email": (body.get("site_manager_email") or "").strip(),
        "is_head_office": bool(body.get("is_head_office")),
        "default_location": (body.get("default_location") or "Main Floor").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if site_doc["is_head_office"]:
        await db.sites.update_many(
            {"organization_id": org_id, "is_head_office": True},
            {"$set": {"is_head_office": False}},
        )

    await db.sites.insert_one(site_doc)
    site_doc.pop("_id", None)
    await log_activity(
        "site_created", f"Site '{name}' added to org {org_id}",
        user["email"], "site", site_doc["id"],
    )
    return {**site_doc, "equipment_count": 0, "issue_count": 0}


@router.post("/master-admin/organizations/{org_id}/sites/bulk")
async def admin_bulk_create_sites(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Bulk-create sites from a list of normalised site dicts (output of
    the sites_import preview-csv endpoint). Skips rows missing a name."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    sites = body.get("sites") or []
    if not isinstance(sites, list) or not sites:
        raise HTTPException(status_code=400, detail="`sites` must be a non-empty list")

    created: list[dict] = []
    skipped: list[dict] = []
    head_office_set = await db.sites.count_documents({"organization_id": org_id, "is_head_office": True}) > 0

    for row in sites:
        name = (row.get("name") or "").strip()
        if not name:
            skipped.append({"row": row, "reason": "Missing name"})
            continue
        is_hq = bool(row.get("is_head_office")) and not head_office_set
        if is_hq:
            head_office_set = True
        site_doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "name": name,
            "address": (row.get("address_line1") or "").strip(),
            "address_line1": (row.get("address_line1") or "").strip(),
            "address_line2": (row.get("address_line2") or "").strip(),
            "address_line3": (row.get("address_line3") or "").strip(),
            "city": (row.get("city") or "").strip(),
            "county": (row.get("county") or "").strip(),
            "postcode": (row.get("postcode") or "").strip(),
            "country": (row.get("country") or "United Kingdom").strip(),
            "phone": (row.get("phone") or "").strip(),
            "email": (row.get("email") or "").strip(),
            "site_manager_name": (row.get("site_manager_name") or "").strip(),
            "site_manager_email": (row.get("site_manager_email") or "").strip(),
            "is_head_office": is_hq,
            "default_location": (row.get("default_location") or "Main Floor").strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.sites.insert_one(site_doc)
        site_doc.pop("_id", None)
        created.append(site_doc)

    await log_activity(
        "sites_bulk_created", f"{len(created)} sites added to org {org_id}",
        user["email"], "organization", org_id,
    )
    return {"created": created, "created_count": len(created), "skipped": skipped, "skipped_count": len(skipped)}




# ─────────────────────────────────────────────────────────────────
# Iter 215el — Head Office onboarding (multi-site customer in one pass)
# ─────────────────────────────────────────────────────────────────

async def _validate_head_office_payload(data: dict) -> dict:
    """Validate the head-office onboarding payload.

    Returns a normalised dict ready for the create flow. Raises
    HTTPException on the first failure so the wizard surfaces a clear
    field-specific error.
    """
    org_name = (data.get("org_name") or "").strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="Head office name is required")

    # Iter 216d — duplicate-org guard. A common onboarding mistake is to
    # create the same Head Office twice (once via the wizard, once via
    # an "Add organisation" shortcut). Block early with a clear message
    # so the operator can re-use the existing record. Two checks:
    #   • Exact match on company_number (canonical, unambiguous).
    #   • Case-insensitive match on org name (catches typos / casing
    #     drift like "PULSE FITNESS LIMITED" vs "Pulse Fitness Limited").
    # Caller can pass `allow_duplicate: true` to override (e.g. franchise
    # subsidiaries that share a name across regions).
    company_number = (data.get("company_number") or "").strip()
    allow_duplicate = bool(data.get("allow_duplicate"))
    if not allow_duplicate:
        if company_number:
            existing = await db.organizations.find_one(
                {"company_number": company_number}, {"_id": 0, "id": 1, "name": 1}
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"An organisation with company number {company_number} already exists ({existing.get('name')}). Open it from the org list, or pass allow_duplicate=true to create anyway.",
                )
        # Case-insensitive name match. We intentionally compare on the
        # trimmed lowercase form so "Pulse Fitness Limited" == "PULSE
        # FITNESS LIMITED" == "  pulse fitness limited  ".
        existing_by_name = await db.organizations.find_one(
            {"$expr": {"$eq": [{"$toLower": {"$trim": {"input": "$name"}}}, org_name.lower()]}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if existing_by_name:
            raise HTTPException(
                status_code=409,
                detail=f"An organisation named '{existing_by_name.get('name')}' already exists. Open it from the org list, or pass allow_duplicate=true to create anyway.",
            )

    tier = data.get("tier") or "lite"
    if tier not in ("lite", "pro", "starter", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Tier must be one of lite/pro/starter/professional/enterprise")
    # Account type is derived from tier for backwards compatibility with
    # existing role-gating logic.
    account_type = (
        "lite" if tier == "lite"
        else "pulse_pro" if tier == "pro"
        else "full"
    )

    owner_email = (data.get("owner_email") or "").strip().lower()
    owner_name = (data.get("owner_name") or "").strip()
    owner_password = (data.get("owner_password") or "").strip()
    # Iter 216f — password is now optional. If `send_invite=true` (or the
    # password is blank) we create the user with NO password and generate
    # a one-time invite token instead. Caller surfaces the URL on success.
    send_invite = bool(data.get("send_invite")) or not owner_password
    if not owner_email or not owner_name:
        raise HTTPException(status_code=400, detail="Owner email and name are required")
    if not send_invite and len(owner_password) < 8:
        raise HTTPException(status_code=400, detail="Owner password must be at least 8 characters")
    if await db.users.find_one({"email": owner_email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {owner_email} already in use")

    sites = data.get("sites") or []
    if not isinstance(sites, list) or len(sites) < 1:
        raise HTTPException(status_code=400, detail="At least one site is required")
    if len(sites) > 50:
        raise HTTPException(status_code=400, detail="Up to 50 sites per onboarding pass; split into batches if needed")

    cleaned_sites: list[dict] = []
    head_office_count = 0
    for i, s in enumerate(sites):
        if not isinstance(s, dict):
            raise HTTPException(status_code=400, detail=f"Site #{i+1} is malformed")
        s_name = (s.get("name") or "").strip()
        if not s_name:
            raise HTTPException(status_code=400, detail=f"Site #{i+1}: name is required")
        is_hq = bool(s.get("is_head_office"))
        if is_hq:
            head_office_count += 1
        # Iter 215en — accept either the structured 8-field address or the
        # legacy single-line `address` (for backwards-compat with the
        # original wizard payload). `merge_address` returns both shapes
        # auto-composed and ready to persist.
        addr = merge_address(s)
        cleaned_sites.append({
            "name": s_name,
            **addr,
            "phone": (s.get("phone") or "").strip(),
            "email": (s.get("email") or "").strip().lower(),
            "default_location": (s.get("default_location") or "Main Floor").strip(),
            "is_head_office": is_hq,
            # Iter 216e — optional per-site equipment list captured inline
            # in the wizard or via AI invoice import. We persist each
            # machine as an Equipment doc linked to this site at onboard
            # time so the tenant can start scanning QRs immediately.
            "equipment": s.get("equipment") or [],
        })
    # Iter 216e — respect operator's choice: zero HQ is fine (registered
    # office from step 1 is the "head office"; no physical gym is the HQ).
    # We still reject multiple HQs (invariant: ≤1 HQ per org).
    if head_office_count > 1:
        raise HTTPException(status_code=400, detail="Only one site can be flagged as Head Office")

    return {
        "org_name": org_name,
        "tier": tier,
        "account_type": account_type,
        "owner_email": owner_email,
        "owner_name": owner_name,
        "owner_password": owner_password,
        "send_invite": send_invite,
        "sites": cleaned_sites,
        # Iter 215en — accept structured billing address. We pass the
        # whole `data` dict through merge_address so callers can supply
        # either the legacy `billing_address` string or the new
        # structured fields prefixed `billing_*`.
        "billing": merge_address({
            "address": data.get("billing_address", ""),
            "address_line1": data.get("billing_address_line1", ""),
            "address_line2": data.get("billing_address_line2", ""),
            "address_line3": data.get("billing_address_line3", ""),
            "city": data.get("billing_city", ""),
            "county": data.get("billing_county", ""),
            "postcode": data.get("billing_postcode", ""),
            "country": data.get("billing_country", ""),
        }),
        "billing_phone": (data.get("billing_phone") or "").strip(),
        "company_number": (data.get("company_number") or "").strip(),
        "vat_number": (data.get("vat_number") or "").strip(),
    }


@router.post("/master-admin/onboard-head-office")
async def onboard_head_office(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Iter 215el — Create a Head Office customer with N sites in one pass.

    Architecture (Option A — confirmed by user):
      • One `organizations` row = the customer (Head Office)
      • N `sites` rows = the locations under that HQ
      • Exactly one site flagged `is_head_office=true` (corporate HQ
        location); others are operational branches.
      • All downstream collections (members, equipment, contracts,
        svc_cases, crm2_*) are scoped by `organization_id` (the HQ org)
        and optionally by `site_id` for site-level operations.

    Sage / Sicon mapping:
      • Org → SLCustomerAccount / Sicon Customer
      • Each site → SLDeliveryAddress / Sicon SubLocation
    """
    require_master_admin(user)
    payload = await _validate_head_office_payload(data)
    now = datetime.now(timezone.utc).isoformat()

    org_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    company_code = str(uuid.uuid4())[:8].upper()

    # Org row — represents the customer (the Head Office).
    is_pulse = payload["account_type"] in ("lite", "pulse_pro")
    branding = (
        {"primary_color": "#66ccff", "company_name": "Pulse Fitness"}
        if is_pulse else {"primary_color": "#5b8cff", "company_name": payload["org_name"]}
    )
    await db.organizations.insert_one({
        "id": org_id,
        "name": payload["org_name"],
        "company_code": company_code,
        "owner_id": owner_id,
        "created_at": now,
        "subscription_tier": payload["tier"],
        "account_type": payload["account_type"],
        # Iter 215en — structured billing address persisted alongside the
        # legacy single-line `address`. Sage / Sicon outboxes consume the
        # legacy field; reports / UI can pull the structured shape.
        "address": payload["billing"]["address"],
        "address_line1": payload["billing"]["address_line1"],
        "address_line2": payload["billing"]["address_line2"],
        "address_line3": payload["billing"]["address_line3"],
        "city": payload["billing"]["city"],
        "county": payload["billing"]["county"],
        "postcode": payload["billing"]["postcode"],
        "country": payload["billing"]["country"],
        "contact_person": payload["owner_name"],
        "email": payload["owner_email"],
        "phone": payload["billing_phone"],
        "company_number": payload["company_number"],
        "vat_number": payload["vat_number"],
        "branding": branding,
        # Iter 215el — explicit org-level marker so the master-admin org
        # list can render the "X sites" affordance and dashboards know
        # to roll up across children.
        "is_multi_site": True,
        "site_count": len(payload["sites"]),
    })

    # Sites rows — one per location.
    site_ids: list[dict] = []
    total_equipment_created = 0
    for s in payload["sites"]:
        site_id = str(uuid.uuid4())
        await db.sites.insert_one({
            "id": site_id,
            "organization_id": org_id,
            "name": s["name"],
            "address": s["address"],
            "postcode": s["postcode"],
            "phone": s["phone"],
            "email": s["email"],
            "default_location": s["default_location"],
            "is_head_office": s["is_head_office"],
            "created_at": now,
            "updated_at": now,
        })
        # Iter 216e — persist per-site equipment captured in the wizard.
        # Each machine becomes an Equipment doc scoped to this org and
        # site. We silently skip rows missing a minimum viable set of
        # fields (need at least a name or make/model); UI surfaces the
        # ones that were created.
        for eq in (s.get("equipment") or []):
            name = (eq.get("name") or eq.get("model") or eq.get("make") or "").strip()
            if not name:
                continue
            await db.equipment.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "site_id": site_id,
                "name": name,
                "make": (eq.get("make") or eq.get("manufacturer") or "").strip(),
                "manufacturer": (eq.get("manufacturer") or eq.get("make") or "").strip(),
                "model": (eq.get("model") or "").strip(),
                "serial_number": (eq.get("serial_number") or eq.get("serial") or "").strip(),
                "equipment_type": (eq.get("equipment_type") or eq.get("type") or "").strip(),
                "location": (eq.get("location") or s["default_location"] or "Main Floor").strip(),
                "warranty_code": (eq.get("warranty_code") or "").strip(),
                "warranty_expiry": eq.get("warranty_expiry") or None,
                "install_date": eq.get("install_date") or None,
                "purchase_date": eq.get("purchase_date") or eq.get("install_date") or None,
                "status": "active",
                "condition": (eq.get("condition") or "good").strip(),
                "created_at": now,
                "updated_at": now,
            })
            total_equipment_created += 1
        site_ids.append({
            "id": site_id, "name": s["name"], "is_head_office": s["is_head_office"],
            "equipment_count": len(s.get("equipment") or []),
        })

    # Owner user — scoped to the HQ org.
    # Iter 216f — when send_invite=True, persist with NO password and
    # mint a password_reset_token; the wizard surfaces the URL.
    owner_doc = {
        "id": owner_id,
        "email": payload["owner_email"],
        "full_name": payload["owner_name"],
        "organization_id": org_id,
        "role": "owner",
        "account_type": payload["account_type"],
        "created_at": now,
    }
    invite_url: str | None = None
    if payload.get("send_invite"):
        # Persist user with no password — sign-in is blocked until they
        # complete the invite flow.
        owner_doc["password"] = None
        owner_doc["password_pending"] = True
        await db.users.insert_one(owner_doc)
        # Mint invite token (72h) — same shape used by the user-edit
        # invite-link endpoint so the existing /reset-password route can
        # consume it without modification.
        import secrets
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": owner_id, "email": payload["owner_email"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
            "used": False, "kind": "invite",
            "issued_by": user.get("email", ""),
            "created_at": now,
        })
        # Resolve the public-facing host the same way QR codes do.
        try:
            from routes.qr_codes import resolve_frontend_url
            base = resolve_frontend_url(None)
        except Exception:
            base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
        invite_url = f"{base}/reset-password?token={token}"
    else:
        owner_doc["password"] = _hash_password(payload["owner_password"])
        await db.users.insert_one(owner_doc)

    await log_activity(
        "head_office_onboarded",
        f"Onboarded Head Office '{payload['org_name']}' with {len(site_ids)} site(s)",
        user.get("email", ""), "organization", org_id,
    )

    hq = next((s for s in site_ids if s["is_head_office"]), site_ids[0])
    return {
        "success": True,
        "organization": {
            "id": org_id,
            "name": payload["org_name"],
            "company_code": company_code,
            "tier": payload["tier"],
            "account_type": payload["account_type"],
            "site_count": len(site_ids),
        },
        "head_office_site": hq,
        "sites": site_ids,
        "owner": {"id": owner_id, "email": payload["owner_email"], "name": payload["owner_name"]},
        "invite_url": invite_url,
        "equipment_created": total_equipment_created,
    }



async def _aggregate_cursor_values(cursor, field: str) -> int:
    """Sum a numeric field across all documents in an async cursor."""
    total = 0
    async for doc in cursor:
        total += doc.get(field, 0)
    return total


async def _count_by_field_cursor(cursor, field: str) -> dict[str, int]:
    """Group-count documents by a field from an async cursor."""
    counts: dict[str, int] = {}
    async for doc in cursor:
        key = doc.get(field, "unknown") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _get_pipeline_stages() -> list[dict]:
    """Fetch default pipeline stages with deal counts and values."""
    pipeline = await db.crm_pipelines.find_one({"is_default": True}, {"_id": 0})
    if not pipeline:
        return []
    stages = []
    for stage in pipeline.get("stages", []):
        count = await db.crm_deals.count_documents({"stage": stage["id"]})
        total_value = await _aggregate_cursor_values(
            db.crm_deals.find({"stage": stage["id"]}, {"_id": 0, "value": 1}), "value",
        )
        stages.append({
            "id": stage["id"], "name": stage["name"],
            "color": stage.get("color", "#007AFF"), "count": count, "value": total_value,
        })
    return stages


async def _get_lead_score_distribution() -> dict[str, int]:
    """Classify contacts into hot/warm/cold/unscored buckets."""
    ranges: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0, "unscored": 0}
    async for c in db.crm_contacts.find({}, {"_id": 0, "lead_score": 1}):
        score = c.get("lead_score")
        if score is None:
            ranges["unscored"] += 1
        elif score >= 70:
            ranges["hot"] += 1
        elif score >= 40:
            ranges["warm"] += 1
        else:
            ranges["cold"] += 1
    return ranges


async def _get_crm_overview() -> dict:
    """Core CRM entity counts."""
    return {
        "total_contacts": await db.crm_contacts.count_documents({}),
        "total_companies": await db.crm_companies.count_documents({}),
        "total_deals": await db.crm_deals.count_documents({}),
        "total_users": await db.crm_users.count_documents({}),
        "total_conversations": await db.crm_conversations.count_documents({}),
        "total_workflows": await db.crm_workflows.count_documents({}),
        "active_workflows": await db.crm_workflows.count_documents({"active": True}),
        "total_quotes": await db.crm_quotes.count_documents({}),
        "total_meetings": await db.crm_meetings.count_documents({}),
        "total_activities": await db.crm_activities.count_documents({}),
    }


async def _get_crm_growth() -> dict:
    """CRM growth metrics for 7d and 30d windows."""
    thirty = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    seven = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {
        "new_contacts_30d": await db.crm_contacts.count_documents({"created_at": {"$gte": thirty}}),
        "new_deals_30d": await db.crm_deals.count_documents({"created_at": {"$gte": thirty}}),
        "new_contacts_7d": await db.crm_contacts.count_documents({"created_at": {"$gte": seven}}),
        "recent_activities_30d": await db.crm_activities.count_documents({"created_at": {"$gte": thirty}}),
    }


async def _get_sage_status() -> dict:
    """Check Sage 200 integration status."""
    sage_config = await db.crm_integrations.find_one({"type": "sage200"}, {"_id": 0})
    if not sage_config:
        return {"status": "not_configured", "last_sync": None}
    status = "connected" if sage_config.get("access_token") else "configured"
    return {"status": status, "last_sync": sage_config.get("last_sync")}


async def _crm_pipeline_analytics() -> dict:
    """Fetch pipeline metrics for master admin analytics."""
    active_opps = await db.crm2_opportunities.find(
        {"stage": {"$nin": ["closed_won", "closed_lost"]}}, {"_id": 0, "value": 1, "weighted_value": 1, "stage": 1}
    ).to_list(500)
    won_opps = await db.crm2_opportunities.find({"stage": "closed_won"}, {"_id": 0, "value": 1}).to_list(500)
    lost_count = await db.crm2_opportunities.count_documents({"stage": "closed_lost"})
    won_count = len(won_opps)
    total_closed = won_count + lost_count
    stage_counts = {}
    for o in active_opps:
        s = o.get("stage", "lead")
        stage_counts[s] = stage_counts.get(s, 0) + 1
    return {
        "stages": [{"stage": k, "count": v} for k, v in stage_counts.items()],
        "won_deals": won_count, "lost_deals": lost_count,
        "total_won_value": sum(o.get("value", 0) for o in won_opps),
        "win_rate": round((won_count / max(total_closed, 1)) * 100, 1),
        "_active_opps": active_opps,
    }


async def _crm_entity_counts() -> dict:
    """Fetch entity counts for master admin analytics."""
    return {
        "total_contacts": await db.crm2_contacts.count_documents({}),
        "total_companies": await db.crm2_companies.count_documents({}),
        "total_activities": await db.crm2_activities.count_documents({}),
        "open_cases": await db.crm2_cases.count_documents({"status": {"$nin": ["closed", "resolved"]}}),
        "total_assets": await db.crm2_assets.count_documents({}),
        "tasks_due": await db.crm2_activities.count_documents({"type": "task", "completed_at": None}),
    }


async def _crm_quote_analytics() -> dict:
    """Fetch quote metrics for master admin analytics."""
    accepted_q = await db.crm2_quotes.find({"status": "accepted"}, {"_id": 0, "total": 1}).to_list(500)
    return {
        "draft": await db.crm2_quotes.count_documents({"status": "draft"}),
        "sent": await db.crm2_quotes.count_documents({"status": "sent"}),
        "accepted": len(accepted_q),
        "total_value": sum(q.get("total", 0) for q in accepted_q),
    }


async def _crm_workflow_stats() -> dict:
    """Get workflow and tender statistics."""
    return {
        "wf_total": await db.crm2_workflows.count_documents({}),
        "wf_active": await db.crm2_workflows.count_documents({"active": True}),
        "wf_runs": await db.crm2_workflow_runs.count_documents({}),
        "total_tenders": await db.crm2_tenders.count_documents({}),
        "active_tenders": await db.crm2_tenders.count_documents({"status": {"$in": ["draft", "in_progress", "review"]}}),
    }


async def _crm_user_and_activity_stats() -> dict:
    """Get CRM user role distribution and activity type breakdown."""
    crm_users = await db.crm_users.find({}, {"_id": 0, "role": 1}).to_list(200)
    users_by_role = {}
    for u in crm_users:
        r = u.get("role", "user")
        users_by_role[r] = users_by_role.get(r, 0) + 1

    activity_types = {}
    for a in await db.crm2_activities.find({}, {"_id": 0, "type": 1}).to_list(1000):
        t = a.get("type", "other")
        activity_types[t] = activity_types.get(t, 0) + 1

    return {"users_by_role": users_by_role, "user_count": len(crm_users), "activity_types": activity_types}


async def _crm_top_deals_at_risk(limit: int = 5) -> list[dict]:
    """Iter 215br — Top deals at risk for Master Admin CRM tab.

    A deal is "at risk" when any of:
      • probability < 50 AND value > 0 (low-confidence pipeline)
      • close_date is in the past but stage is still open
      • last updated >14 days ago and stage is open
    Sorted by value desc and capped at `limit`.
    """
    today_iso = datetime.now(timezone.utc).date().isoformat()
    stale_threshold = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    open_filter = {"stage": {"$nin": ["closed_won", "closed_lost"]}}

    rows = await db.crm2_opportunities.find(
        {**open_filter, "$or": [
            {"probability": {"$lt": 50}, "value": {"$gt": 0}},
            {"close_date": {"$lt": today_iso, "$ne": ""}},
            {"updated_at": {"$lt": stale_threshold}},
        ]},
        {"_id": 0, "id": 1, "title": 1, "value": 1, "stage": 1, "probability": 1,
         "company_name": 1, "close_date": 1, "updated_at": 1, "owner_name": 1},
    ).sort("value", -1).limit(limit).to_list(limit)

    out = []
    for r in rows:
        reasons = []
        if (r.get("probability") or 0) < 50 and (r.get("value") or 0) > 0:
            reasons.append("low_probability")
        cd = r.get("close_date") or ""
        if cd and cd < today_iso:
            reasons.append("close_date_past")
        if (r.get("updated_at") or "") < stale_threshold:
            reasons.append("stale_14d")
        r["risk_reasons"] = reasons
        out.append(r)
    return out


async def _crm_renewals_due(window_days: int = 30) -> dict:
    """Iter 215br — Upcoming renewals/closes inside `window_days`. Returns
    a list of the closest ones plus a count and total weighted value."""
    today = datetime.now(timezone.utc).date()
    cutoff = (today + timedelta(days=window_days)).isoformat()
    rows = await db.crm2_opportunities.find(
        {
            "stage": {"$nin": ["closed_won", "closed_lost"]},
            "close_date": {"$gte": today.isoformat(), "$lte": cutoff, "$ne": ""},
        },
        {"_id": 0, "id": 1, "title": 1, "value": 1, "weighted_value": 1, "stage": 1,
         "probability": 1, "company_name": 1, "close_date": 1, "owner_name": 1},
    ).sort("close_date", 1).to_list(50)
    return {
        "window_days": window_days,
        "count": len(rows),
        "total_value": sum(r.get("value") or 0 for r in rows),
        "weighted_value": sum(r.get("weighted_value") or 0 for r in rows),
        "items": rows[:8],
    }


async def _crm_ai_usage_block() -> dict:
    """Iter 215br — Lightweight CRM AI usage panel for Master Admin.

    Counts data we actually persist today: tender questions auto-drafted
    by the AI assistant, opportunities with AI-coached next-best-action,
    and copilot/help sessions logged through `help_sessions` (if present).
    Anything not yet wired returns 0 — purposely no fake numbers.
    """
    autopilot_drafts = await db.crm2_tender_questions.count_documents({
        "ai_draft": {"$exists": True, "$nin": ["", None]},
    })
    win_intel_hits = await db.crm2_activities.count_documents({
        "type": {"$in": ["ai_insight", "win_intel", "ai_summary"]},
    })
    # Copilot sessions — opportunistic; collection may not exist yet.
    copilot_sessions = 0
    try:
        copilot_sessions = await db.crm_copilot_sessions.count_documents({})
    except Exception:
        copilot_sessions = 0
    if not copilot_sessions:
        # Fall back to help-centre AI sessions which the in-app copilot uses.
        try:
            copilot_sessions = await db.help_sessions.count_documents({"source": {"$in": ["copilot", "crm_copilot"]}})
        except Exception:
            copilot_sessions = 0
    return {
        "autopilot_drafts": autopilot_drafts,
        "win_intel_hits": win_intel_hits,
        "copilot_sessions": copilot_sessions,
        "total": autopilot_drafts + win_intel_hits + copilot_sessions,
    }


@router.get("/master-admin/crm-analytics")
async def get_crm_analytics(user: dict = Depends(get_current_user)) -> dict:
    """Comprehensive CRM analytics for master admin — uses v2 collections."""
    require_master_admin(user)

    pipeline = await _crm_pipeline_analytics()
    counts = await _crm_entity_counts()
    quotes = await _crm_quote_analytics()
    wf = await _crm_workflow_stats()
    ua = await _crm_user_and_activity_stats()

    active_opps = pipeline.pop("_active_opps")
    pipeline_value = sum(o.get("value", 0) for o in active_opps)
    weighted_forecast = sum(o.get("weighted_value", 0) for o in active_opps)

    recent_deals = await db.crm2_opportunities.find(
        {}, {"_id": 0, "title": 1, "value": 1, "stage": 1, "company_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    recent_activities = await db.crm2_activities.find(
        {}, {"_id": 0, "type": 1, "subject": 1, "owner_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Iter 215br — v2 growth windows for the KPI sub-labels.
    thirty = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    growth = {
        "new_contacts_30d": await db.crm2_contacts.count_documents({"created_at": {"$gte": thirty}}),
        "new_deals_30d": await db.crm2_opportunities.count_documents({"created_at": {"$gte": thirty}}),
        "recent_activities_30d": await db.crm2_activities.count_documents({"created_at": {"$gte": thirty}}),
    }

    # Iter 215br — enriched panels for the Master Admin CRM tab.
    deals_at_risk = await _crm_top_deals_at_risk(5)
    renewals_due = await _crm_renewals_due(30)
    ai_usage = await _crm_ai_usage_block()

    return {
        "overview": {
            **counts, "active_opportunities": len(active_opps),
            "pipeline_value": pipeline_value, "weighted_forecast": weighted_forecast,
            "total_tenders": wf["total_tenders"], "active_tenders": wf["active_tenders"],
        },
        "growth": growth,
        "pipeline": pipeline,
        "quotes": quotes,
        "contacts": {"source_breakdown": {}, "lead_scores": {}},
        "inbox": {"open_conversations": 0, "high_priority": 0},
        "users": {"by_role": ua["users_by_role"], "total": ua["user_count"]},
        "workflows": {"total": wf["wf_total"], "active": wf["wf_active"], "total_executions": wf["wf_runs"]},
        "integrations": {"sage200": {"status": "not_configured"}},
        "activity_types": ua["activity_types"],
        "recent_deals": recent_deals,
        "recent_activities": recent_activities,
        # New panels (iter 215br)
        "deals_at_risk": deals_at_risk,
        "renewals_due": renewals_due,
        "ai_usage": ai_usage,
    }


# ─── CRM User Management (Master Admin) ───

@router.get("/master-admin/crm-users")
async def get_crm_users(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    users = await db.crm_users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(200)
    return {"users": users}


@router.post("/master-admin/crm-users")
async def create_crm_user(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    from routes.crm_auth import crm_hash_password
    email = (data.get("email") or "").strip().lower()
    if not email or not data.get("password"):
        raise HTTPException(status_code=400, detail="Email and password required")
    if await db.crm_users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail=f"CRM user {email} already exists")
    doc = {
        "id": str(uuid.uuid4()), "email": email,
        "full_name": (data.get("full_name") or "").strip(),
        "password": crm_hash_password(data["password"]),
        "role": data.get("role", "user"),
        "avatar_url": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password", None)
    return doc


@router.patch("/master-admin/crm-users/{crm_user_id}")
async def update_crm_user(crm_user_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    existing = await db.crm_users.find_one({"id": crm_user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="CRM user not found")
    updates = {}
    for field in ("full_name", "role"):
        if field in data:
            updates[field] = (data[field] or "").strip()
    if "password" in data and data["password"]:
        from routes.crm_auth import crm_hash_password
        updates["password"] = crm_hash_password(data["password"])
    if updates:
        await db.crm_users.update_one({"id": crm_user_id}, {"$set": updates})
    updated = await db.crm_users.find_one({"id": crm_user_id}, {"_id": 0, "password": 0})
    return updated or {}


@router.delete("/master-admin/crm-users/{crm_user_id}")
async def delete_crm_user(crm_user_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    result = await db.crm_users.delete_one({"id": crm_user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="CRM user not found")
    return {"success": True}



# ── Sicon Integration Health ──────────────────────────────────────

async def _sicon_health_counts(org_id: str) -> dict:
    """Fetch queue + issue counts for one org."""
    pending_q = await db.sicon_sync_queue.count_documents({
        "organization_id": org_id, "resolved_at": None, "retryable": True,
    })
    failed_q = await db.sicon_sync_queue.count_documents({
        "organization_id": org_id, "resolved_at": {"$ne": None},
        "resolution": "retries_exhausted",
    })
    synced = await db.issues.count_documents({
        "organization_id": org_id, "sicon_case_id": {"$exists": True, "$ne": None},
    })
    failed = await db.issues.count_documents({
        "organization_id": org_id, "sicon_sync_status": "failed",
    })
    return {"pending_queue": pending_q, "failed_queue": failed_q,
            "synced_issues": synced, "failed_issues": failed}


def _sicon_health_row(org_id: str, org_name: str, cfg: Optional[dict], counts: dict) -> dict:
    """Build one row of the per-org health response."""
    cfg = cfg or {}
    return {
        "organization_id": org_id, "organization_name": org_name,
        "configured": bool(cfg), "enabled": bool(cfg.get("enabled")),
        "base_url": cfg.get("base_url", ""),
        "connection_status": cfg.get("connection_status", "unknown"),
        "last_tested_at": cfg.get("last_tested_at"),
        "last_poll_at": cfg.get("last_poll_at"),
        "last_poll_counts": cfg.get("last_poll_counts", {}),
        "last_sync_at": cfg.get("last_sync_at"),
        "last_error": cfg.get("last_error", ""),
        **counts,
    }


def _sicon_row_sort_key(r: dict) -> tuple:
    name = r["organization_name"].lower()
    if r["enabled"] and r["connection_status"] == "connected":
        return (0, name)
    if r["enabled"]:
        return (1, name)
    if r["configured"]:
        return (2, name)
    return (3, name)


_SICON_HEALTH_SUMS = {
    "total_pending_queue": "pending_queue",
    "total_failed_queue": "failed_queue",
    "total_synced_issues": "synced_issues",
    "total_failed_issues": "failed_issues",
}


def _sicon_health_totals(rows: list) -> dict:
    totals = {
        "total_orgs": len(rows),
        "configured": sum(1 for r in rows if r["configured"]),
        "enabled": sum(1 for r in rows if r["enabled"]),
        "connected": sum(1 for r in rows if r["connection_status"] == "connected"),
    }
    for out_key, src_key in _SICON_HEALTH_SUMS.items():
        totals[out_key] = sum(r[src_key] for r in rows)
    return totals


@router.get("/master-admin/sicon/health")
async def sicon_health_overview(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate Sicon health across every organization."""
    require_master_admin(user)

    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    configs = await db.sicon_config.find({}, {"_id": 0}).to_list(1000)
    cfg_by_org = {c["organization_id"]: c for c in configs}

    rows = []
    for o in orgs:
        org_id = o["id"]
        cfg = cfg_by_org.get(org_id)
        counts = await _sicon_health_counts(org_id) if cfg else {
            "pending_queue": 0, "failed_queue": 0, "synced_issues": 0, "failed_issues": 0,
        }
        rows.append(_sicon_health_row(org_id, o.get("name", "Unnamed"), cfg, counts))

    rows.sort(key=_sicon_row_sort_key)
    return {"organizations": rows, "totals": _sicon_health_totals(rows)}



@router.post("/master-admin/sicon/test-all")
async def sicon_test_all_connections(user: dict = Depends(get_current_user)) -> dict:
    """Fire a connection test against every Sicon-enabled organization."""
    require_master_admin(user)
    from utils.sicon_common import get_sicon_client

    results = []
    cursor = db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1})
    async for cfg in cursor:
        org_id = cfg.get("organization_id")
        if not org_id:
            continue
        client = await get_sicon_client(org_id)
        if not client:
            continue
        try:
            is_up = await client.ping()
            status = "connected" if is_up else "unreachable"
            await db.sicon_config.update_one(
                {"organization_id": org_id},
                {"$set": {"connection_status": status,
                          "last_tested_at": datetime.now(timezone.utc).isoformat()}}
            )
            results.append({"organization_id": org_id, "connected": is_up, "status": status})
        except Exception as e:
            await db.sicon_config.update_one(
                {"organization_id": org_id},
                {"$set": {"connection_status": "error", "last_error": str(e)[:500]}}
            )
            results.append({"organization_id": org_id, "connected": False, "error": str(e)[:200]})

    return {"tested": len(results), "results": results}


@router.post("/master-admin/sicon/poll-all")
async def sicon_poll_all_orgs(user: dict = Depends(get_current_user)) -> dict:
    """Run an immediate inbound poll across every Sicon-enabled organization."""
    require_master_admin(user)
    from utils.sicon_sync import poll_sicon_updates_for_org, retry_queue_for_org

    results = []
    cursor = db.sicon_config.find({"enabled": True}, {"_id": 0, "organization_id": 1})
    async for cfg in cursor:
        org_id = cfg.get("organization_id")
        if not org_id:
            continue
        try:
            poll = await poll_sicon_updates_for_org(org_id)
            retry = await retry_queue_for_org(org_id)
            results.append({"organization_id": org_id, "poll": poll, "retry": retry})
        except Exception as e:
            results.append({"organization_id": org_id, "error": str(e)[:200]})

    return {"polled": len(results), "results": results}


# ── Trial Management ──────────────────────────────────────────────

@router.get("/master-admin/trials")
async def list_trials(user: dict = Depends(get_current_user)) -> dict:
    """List all trial organizations with status and time remaining."""
    require_master_admin(user)
    from utils.trial_lifecycle import compute_trial_state

    orgs = await db.organizations.find(
        {"is_trial": True}, {"_id": 0}
    ).sort("trial_ends_at", 1).to_list(500)

    result = []
    for o in orgs:
        state = compute_trial_state(o)
        primary = o.get("primary_contact", {}) or {}
        # Count users on this org
        user_count = await db.users.count_documents({"organization_id": o["id"]})
        result.append({
            "id": o["id"],
            "name": o.get("name"),
            "legal_name": o.get("legal_name"),
            "tier": o.get("subscription_tier"),
            "primary_contact": {
                "name": primary.get("name", ""),
                "email": primary.get("email", ""),
            },
            "user_count": user_count,
            "trial_started_at": o.get("trial_started_at"),
            "trial_ends_at": o.get("trial_ends_at"),
            "trial_suspends_at": o.get("trial_suspends_at"),
            "trial_duration_days": o.get("trial_duration_days", 14),
            "trial_status": state.get("status"),
            "days_left": state.get("days_left", 0),
            "read_only": state.get("read_only", False),
            "locked_out": state.get("locked_out", False),
            "extended_by_days": o.get("trial_extended_by_days", 0),
            "reminders_sent": o.get("trial_reminders_sent", []),
            "converted_at": o.get("converted_at"),
        })
    return {"trials": result, "count": len(result)}


def _record_convert_time(o: dict, convert_times: list) -> None:
    """Append the days-to-convert for a converted org to convert_times."""
    try:
        started = datetime.fromisoformat(
            (o.get("trial_started_at") or o.get("created_at", "")).replace("Z", "+00:00")
        )
        converted = datetime.fromisoformat(o.get("converted_at", "").replace("Z", "+00:00"))
        convert_times.append((converted - started).total_seconds() / 86400.0)
    except Exception:
        pass


def _is_expiring_this_week(o: dict, now: datetime, week_out: datetime) -> bool:
    try:
        ends_at = datetime.fromisoformat(o.get("trial_ends_at", "").replace("Z", "+00:00"))
        return now <= ends_at <= week_out
    except Exception:
        return False


async def _classify_org_source(org_id: str) -> str:
    """Return 'crm_linked' or 'direct' based on the CRM source for this org."""
    crm_row = await db.crm_companies.find_one(
        {"linked_organization_id": org_id},
        {"_id": 0, "source": 1}
    )
    if crm_row and crm_row.get("source") and crm_row["source"] != "onboarding_packet_trial":
        return "crm_linked"
    return "direct"


async def _aggregate_trial_counts(orgs: list, now: datetime, week_out: datetime) -> tuple:
    """Walk the trial org list; return (by_status, by_source, convert_times, expiring_this_week)."""
    from utils.trial_lifecycle import compute_trial_state

    by_status = {"active": 0, "expiring_soon": 0, "expired": 0, "suspended": 0, "converted": 0}
    by_source = {"crm_linked": 0, "direct": 0}
    convert_times: list = []
    expiring_this_week = 0

    for o in orgs:
        if o.get("trial_status") == "converted":
            by_status["converted"] += 1
            _record_convert_time(o, convert_times)
        elif o.get("is_trial"):
            status = compute_trial_state(o).get("status", "active")
            by_status[status] = by_status.get(status, 0) + 1
            if _is_expiring_this_week(o, now, week_out):
                expiring_this_week += 1
        by_source[await _classify_org_source(o["id"])] += 1

    return by_status, by_source, convert_times, expiring_this_week


async def _compute_conversion_metrics(cutoff_30d: datetime, now: datetime, convert_times: list) -> tuple:
    """Compute (converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert)."""
    converted_30d = await db.organizations.count_documents({
        "trial_status": "converted",
        "converted_at": {"$gte": cutoff_30d.isoformat()}
    })
    ended_30d = await db.organizations.count_documents({
        "$or": [
            {"trial_status": "converted", "converted_at": {"$gte": cutoff_30d.isoformat()}},
            {"is_trial": True, "trial_ends_at": {"$lte": now.isoformat(), "$gte": cutoff_30d.isoformat()}},
        ]
    })
    conversion_rate_30d = round((converted_30d / ended_30d * 100), 1) if ended_30d > 0 else 0
    avg_days_to_convert = round(sum(convert_times) / len(convert_times), 1) if convert_times else 0
    return converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert


@router.get("/master-admin/trials/summary")
async def trials_summary(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate trial metrics for Master Admin dashboard widget."""
    require_master_admin(user)

    orgs = await db.organizations.find(
        {"$or": [{"is_trial": True}, {"trial_status": "converted"}]},
        {"_id": 0}
    ).to_list(2000)

    now = datetime.now(timezone.utc)
    week_out = now + timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    by_status, by_source, convert_times, expiring_this_week = await _aggregate_trial_counts(orgs, now, week_out)
    converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert = await _compute_conversion_metrics(
        cutoff_30d, now, convert_times
    )

    return {
        "total": by_status["active"] + by_status["expiring_soon"] + by_status["expired"] + by_status["suspended"],
        "by_status": by_status,
        "converted_30d": converted_30d,
        "ended_30d": ended_30d,
        "conversion_rate_30d": conversion_rate_30d,
        "avg_days_to_convert": avg_days_to_convert,
        "expiring_this_week": expiring_this_week,
        "by_source": by_source,
    }


@router.post("/master-admin/trials/{org_id}/extend")
async def extend_trial(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Extend a trial by N days. Resets reminder flags so the customer gets another nudge."""
    require_master_admin(user)
    days = int(body.get("days", 7))
    if days < 1 or days > 30:
        raise HTTPException(status_code=400, detail="days must be between 1 and 30")
    reason = (body.get("reason") or "").strip()

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or not org.get("is_trial"):
        raise HTTPException(status_code=404, detail="Trial org not found")

    current_end = org.get("trial_ends_at")
    try:
        end_dt = datetime.fromisoformat(current_end.replace("Z", "+00:00"))
    except Exception:
        end_dt = datetime.now(timezone.utc)

    new_end = end_dt + timedelta(days=days)
    new_suspend = new_end + timedelta(days=30)

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "trial_ends_at": new_end.isoformat(),
            "trial_suspends_at": new_suspend.isoformat(),
            "trial_status": "active",
            "status": "active",
            "trial_extended_by_days": (org.get("trial_extended_by_days", 0) + days),
            "trial_reminders_sent": [],  # allow new reminders for the new window
        }}
    )
    await log_activity(
        "trial_extended",
        f"Extended by {days} days. Reason: {reason or '—'}",
        user.get("email", ""), "organization", org_id,
    )
    return {"success": True, "new_end": new_end.isoformat(), "days_added": days}


def _resolve_stripe_price_id(target_tier: str) -> str:
    """Map a tier name to the configured Stripe price ID. Raises 400 if unconfigured."""
    from utils.database import STRIPE_PRICE_PRO, STRIPE_PRICE_STARTER, STRIPE_PRICE_ENTERPRISE
    price_map = {"starter": STRIPE_PRICE_STARTER, "pro": STRIPE_PRICE_PRO, "enterprise": STRIPE_PRICE_ENTERPRISE}
    price_id = price_map.get(target_tier)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"No Stripe price configured for tier {target_tier}")
    return price_id


def _build_trial_convert_session(org: dict, org_id: str, target_tier: str, origin_url: str):
    """Create a Stripe Checkout session for a trial → paid conversion."""
    import stripe
    from utils.database import STRIPE_API_KEY
    stripe.api_key = STRIPE_API_KEY
    price_id = _resolve_stripe_price_id(target_tier)
    primary_email = (org.get("primary_contact", {}) or {}).get("email", "")
    return stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{origin_url.rstrip('/')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}&trial_convert={org_id}",
        cancel_url=f"{origin_url.rstrip('/')}/dashboard",
        customer_email=primary_email or None,
        metadata={"trial_org_id": org_id, "trial_convert": "true", "tier": target_tier},
    )


@router.post("/master-admin/trials/{org_id}/convert")
async def convert_trial_to_paid(org_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Generate a Stripe Checkout session so the owner can upgrade to paid.
    Returns checkout_url — master admin can share it or we surface it to the owner.
    """
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or not org.get("is_trial"):
        raise HTTPException(status_code=404, detail="Trial org not found")

    target_tier = body.get("tier") or org.get("subscription_tier") or "pro"
    origin_url = body.get("origin_url", "") or os.environ.get("FRONTEND_URL", "")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    try:
        session = _build_trial_convert_session(org, org_id, target_tier, origin_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stripe checkout creation failed for org {org_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)[:200]}")

    await log_activity(
        "trial_convert_initiated",
        f"Stripe checkout created for tier {target_tier}",
        user.get("email", ""), "organization", org_id,
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/master-admin/trials/{org_id}/mark-converted")
async def mark_converted(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Manually mark a trial as converted (for cases where Stripe webhook didn't fire or payment was manual)."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "trial_status": "converted",
            "status": "active",
            "converted_at": datetime.now(timezone.utc).isoformat(),
            "is_trial": False,  # remove trial flag, full customer now
        }}
    )
    await log_activity("trial_marked_converted", "", user.get("email", ""), "organization", org_id)
    return {"success": True}




# ─── Test Data Purge ────────────────────────────────────────────────
@router.post("/master-admin/test-data/purge")
async def purge_test_data(
    user: dict = Depends(get_current_user),
    payload: dict = Body(default={}),
):
    """
    Wipe seeded/demo/test data so the platform reflects real activity only.
    Master-admin only. Purges by default:
      - revenue_distributions + reserve_transactions (so Monthly Revenue resets)
      - demo faults, demo equipment, demo jobs, demo contracts
      - any record with {is_test: true} or {seed: true}
    Pass {"collections": [...]} to override the default list.
    """
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    # Default collections that accumulate platform-activity test data
    default_collections = [
        "revenue_distributions",
        "reserve_transactions",
        "llm_top_up_log",
        "financial_alerts",
    ]
    collections = payload.get("collections", default_collections)

    # Protected — never wipe these even if passed
    PROTECTED = {"users", "organizations", "stripe_webhook_events", "audit_log", "master_admin_activity_log"}
    results = {}

    for coll_name in collections:
        if coll_name in PROTECTED:
            results[coll_name] = {"skipped": True, "reason": "protected"}
            continue
        try:
            res = await db[coll_name].delete_many({})
            results[coll_name] = {"deleted": res.deleted_count}
        except Exception as e:
            results[coll_name] = {"error": str(e)}

    # Also clear any document flagged as test/seed across the whole database
    flagged_total = 0
    for coll_name in ["faults", "equipment", "jobs", "contracts", "job_cards", "ppm_sheets", "check_sheets"]:
        try:
            res = await db[coll_name].delete_many({"$or": [{"is_test": True}, {"seed": True}, {"demo": True}]})
            if res.deleted_count:
                results[f"{coll_name}_flagged"] = {"deleted": res.deleted_count}
                flagged_total += res.deleted_count
        except Exception:
            pass

    await log_activity(
        "test_data_purged",
        f"Purged: {sum(r.get('deleted',0) for r in results.values() if isinstance(r, dict))} docs, flagged: {flagged_total}",
        user.get("email", ""),
        "platform",
        "",
    )
    return {"success": True, "flagged_total": flagged_total, "results": results}



@router.get("/master-admin/all-sites")
async def all_sites_across_orgs(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    site_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 500,
):
    """Iter 216h23 — Cross-organisation physical-sites list.

    Lives at `Master Admin → Organisations → All sites` sub-tab. Solves
    the "where are all my Pulse sites?" question without breaking the
    SSoT principle (a Site still belongs to exactly one Organisation —
    this is just a flat power-view across all orgs).

    Per-row enrichments:
      • org_name / org_brand  — joined from `organizations`.
      • equipment_count       — `equipment` docs scoped to (org_id, site_id).
      • members_count         — `members` (or `crm_users`) scoped likewise.
      • is_head_office        — direct from the site doc.
      • last_activity         — most recent of any audit_logs / issues
                                / check_sheet_instances touching the site.

    Brand scope: Pulse-only admins receive only Pulse-brand sites.
    Query filters: `org_id`, `site_type`, free-text `q` (matches name).
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause

    # Org scope (Pulse-only admins are pinned to Pulse-brand orgs).
    pulse_only = is_pulse_only(user)
    org_filter: dict = {}
    if pulse_only:
        org_filter = brand_filter_clause("pulse")
    if org_id:
        org_filter = {**org_filter, "id": org_id}

    orgs = await db.organizations.find(
        org_filter, {"_id": 0, "id": 1, "name": 1, "brand": 1},
    ).to_list(2000)
    org_index = {o["id"]: o for o in orgs}
    if not org_index:
        return {"sites": [], "totals": {"sites": 0, "head_offices": 0, "branches": 0, "equipment": 0}}

    site_query: dict = {"organization_id": {"$in": list(org_index.keys())}}
    if site_type == "head_office":
        site_query["is_head_office"] = True
    elif site_type == "branch":
        site_query["is_head_office"] = {"$ne": True}
    if q:
        site_query["name"] = {"$regex": q, "$options": "i"}

    sites = await db.sites.find(site_query, {"_id": 0}).sort([("organization_id", 1), ("name", 1)]).to_list(limit)

    # Bulk equipment counts per (org, site).
    eq_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    eq_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.equipment.aggregate(eq_pipeline)}

    # Bulk member counts per site (best-effort — schema varies by tenant).
    mem_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    mem_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.members.aggregate(mem_pipeline)}

    enriched = []
    head_office_count = 0
    branch_count = 0
    total_equipment = 0
    for s in sites:
        org = org_index.get(s.get("organization_id"), {})
        is_hq = bool(s.get("is_head_office"))
        head_office_count += 1 if is_hq else 0
        branch_count += 0 if is_hq else 1
        eq = eq_counts.get((s.get("organization_id"), s.get("id")), 0)
        total_equipment += eq
        enriched.append({
            "id":              s.get("id"),
            "name":            s.get("name"),
            "organization_id": s.get("organization_id"),
            "org_name":        org.get("name") or "—",
            "org_brand":       org.get("brand") or "gymaxis",
            "is_head_office":  is_hq,
            "site_type":       s.get("site_type") or ("head_office" if is_hq else "branch"),
            "city":            s.get("city") or s.get("address", {}).get("city") if isinstance(s.get("address"), dict) else s.get("city"),
            "postcode":        s.get("postcode") or (s.get("address") or {}).get("postcode") if isinstance(s.get("address"), dict) else s.get("postcode"),
            "active":          s.get("active", True),
            "equipment_count": eq,
            "members_count":   mem_counts.get((s.get("organization_id"), s.get("id")), 0),
            "created_at":      s.get("created_at"),
        })

    return {
        "sites": enriched,
        "totals": {
            "sites":         len(enriched),
            "head_offices":  head_office_count,
            "branches":      branch_count,
            "equipment":     total_equipment,
        },
        "brand": "pulse" if pulse_only else "all",
    }



# ──────────────────────────────────────────────────────────────────────
# Iter 216bm — Locked-staff audit view
# ──────────────────────────────────────────────────────────────────────
@router.get("/master-admin/users/locked-sites")
async def locked_staff_audit(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    limit: int = 200,
):
    """List users with non-empty `allowed_site_ids` for compliance audit.

    Returned for every locked staff member: org name, full name, email,
    role, the names of the sites they're locked to, and the timestamp
    of the last permission change. Master-admin only.

    Query params:
      • `org_id` — narrow to a single organisation (optional)
      • `limit`  — max rows (default 200, hard-capped to 1000)
    """
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(status_code=403, detail="Master admin only")

    capped_limit = max(1, min(int(limit or 200), 1000))

    user_filter: dict = {
        "allowed_site_ids": {"$exists": True, "$ne": []},
    }
    if org_id:
        user_filter["organization_id"] = org_id

    user_docs = await db.users.find(
        user_filter,
        {
            "_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1,
            "organization_id": 1, "allowed_site_ids": 1,
            "permissions_updated_at": 1, "is_master_admin": 1,
        },
    ).limit(capped_limit).to_list(capped_limit)

    if not user_docs:
        return {"locked_staff": [], "total": 0}

    # Resolve org names + site names in one round-trip each. The lock
    # field is small enough that an explicit join is fine.
    org_ids = list({u["organization_id"] for u in user_docs if u.get("organization_id")})
    org_lookup = {
        o["id"]: o["name"]
        for o in await db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(org_ids))
    }

    all_site_ids: set = set()
    for u in user_docs:
        for sid in (u.get("allowed_site_ids") or []):
            all_site_ids.add(sid)
    site_lookup = {
        s["id"]: {"name": s.get("name", "(unnamed)"), "is_head_office": bool(s.get("is_head_office"))}
        for s in await db.sites.find(
            {"id": {"$in": list(all_site_ids)}}, {"_id": 0, "id": 1, "name": 1, "is_head_office": 1}
        ).to_list(len(all_site_ids) or 1)
    }

    rows = []
    for u in user_docs:
        site_ids = u.get("allowed_site_ids") or []
        sites = [
            {"id": sid, "name": site_lookup.get(sid, {}).get("name", "(deleted site)"), "is_head_office": site_lookup.get(sid, {}).get("is_head_office", False)}
            for sid in site_ids
        ]
        rows.append({
            "user_id": u.get("id"),
            "full_name": u.get("full_name") or "(no name)",
            "email": u.get("email") or "",
            "role": u.get("role") or "staff",
            "is_master_admin": bool(u.get("is_master_admin")),
            "organization_id": u.get("organization_id"),
            "organization_name": org_lookup.get(u.get("organization_id", ""), "(unknown org)"),
            "site_count": len(sites),
            "sites": sites,
            "permissions_updated_at": u.get("permissions_updated_at"),
        })

    rows.sort(key=lambda r: r.get("permissions_updated_at") or "", reverse=True)
    return {"locked_staff": rows, "total": len(rows)}



# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Pulse Fitness supplier backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-pulse-supplier")
async def backfill_pulse_supplier(
    user: dict = Depends(get_current_user),
    dry_run: bool = False,
):
    """Set every piece of equipment in every Pulse Fitness Lite / Pro
    organisation's default supplier to "Pulse Fitness" with the
    service.dept@pulsefitness.com email. Master-admin only.

    `?dry_run=true` returns counts without writing.
    """
    require_master_admin(user)
    org_cursor = db.organizations.find(
        {"account_type": {"$in": ["lite", "pulse_pro"]}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    )
    pulse_orgs = [o async for o in org_cursor]
    if not pulse_orgs:
        return {"orgs": 0, "equipment_updated": 0, "dry_run": dry_run}

    org_ids = [o["id"] for o in pulse_orgs]
    if dry_run:
        cnt = await db.equipment.count_documents({"organization_id": {"$in": org_ids}})
        return {"orgs": len(pulse_orgs), "equipment_to_update": cnt, "dry_run": True}

    result = await db.equipment.update_many(
        {"organization_id": {"$in": org_ids}},
        {"$set": {
            "supplier": "Pulse Fitness",
            "supplier_email": "service.dept@pulsefitness.com",
            "supplier_backfilled_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "orgs": len(pulse_orgs),
        "equipment_updated": int(result.modified_count or 0),
        "dry_run": False,
    }


# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Spec-sheet attach backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-spec-sheets")
async def backfill_spec_sheets(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    dry_run: bool = False,
):
    """Re-run the spec-sheet auto-match across existing equipment so
    rows uploaded before iter 216bn pick up matching catalogue entries.
    Master-admin only. `?org_id=` narrows to one organisation.
    """
    require_master_admin(user)
    from routes.spec_sheets import auto_match_equipment_to_specs

    eq_filter: dict = {
        "$or": [
            {"spec_sheet_id": {"$exists": False}},
            {"spec_sheet_id": ""},
            {"spec_sheet_id": None},
        ],
    }
    if org_id:
        eq_filter["organization_id"] = org_id

    cursor = db.equipment.find(eq_filter, {"_id": 0})
    eq_docs = await cursor.to_list(2000)

    matched = 0
    if dry_run:
        for eq in eq_docs:
            m = await auto_match_equipment_to_specs(eq)
            if m:
                matched += 1
        return {"considered": len(eq_docs), "matched": matched, "dry_run": True}

    for eq in eq_docs:
        m = await auto_match_equipment_to_specs(eq)
        if m:
            await db.equipment.update_one(
                {"id": eq["id"]},
                {"$set": {**m, "spec_sheet_attached_at": datetime.now(timezone.utc).isoformat()}},
            )
            matched += 1
    return {"considered": len(eq_docs), "matched": matched, "dry_run": False}
