"""
Master Admin · Organisations CRUD + sites sub-router.

Iter 216h178 — Extracted from `routes/master_admin.py` as phase 2 of the
4,283 LoC → 5-6 focused routers decomposition.

Owns the organisations dashboard surface (search, list, status,
subscription, features, details) and the per-org sites endpoints
exposed under `/api/master-admin/organizations/{org_id}/*`.

All shared helpers continue to live on the parent `routes.master_admin`
module so the dozen-or-so cross-module imports keep working unchanged.
"""
import asyncio
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.brand_filter import merge_brand_filter
from routes.master_admin import (
    ADDRESS_FIELDS,
    ALL_MODULE_IDS,
    PULSE_VISIBLE_ACCOUNT_TYPES,
    _PULSE_TIER_TO_ACCOUNT_TYPE,
    _GYMAXIS_TIERS,
    _derive_portal_type,
    _ensure_primary_contact_user,
    _modules_from_portal_type,
    _normalize_modules,
    assert_org_in_pulse_scope,
    is_pulse_only,
    log_activity,
    merge_address,
    require_master_admin,
)


router = APIRouter()


# ───────────── /organizations/search — Head-Office autocomplete ─────────────

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


# ───────────── /organizations — list with batched aggregates ─────────────

# Iter 216h174 — Payload-size pass. Exclude heavy detail-only fields
# from the list response. `features_audit` is an append-only history
# of every feature-flag flip on the org (≈3.7-5.3 KB per org, capped
# at 50 entries by /master-admin/organizations/{id}/features audit).
# On a Master Admin with 500 orgs that's ~2.5 MB of audit history
# shipped on every refresh — and the frontend never reads it from
# this list (it's lazy-fetched via the dedicated /features-audit
# endpoint when an admin opens the audit drawer).
_ORG_LIST_EXCLUDE = {"_id": 0, "features_audit": 0}


@router.get("/master-admin/organizations")
async def get_all_organizations(
    user: dict = Depends(get_current_user),
    brand: str = "all",
    q: str = "",
    skip: int = 0,
    limit: int = 2000,
):
    require_master_admin(user)
    org_filter: dict = {}
    if is_pulse_only(user):
        org_filter["account_type"] = {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}
    # Iter 216h18 — Master Admin brand context filter. Applies after
    # the pulse-only guard so a Pulse Master Admin who flips the
    # picker to "Pulse Fitness" still sees nothing (their permission gate
    # always wins).
    org_filter = merge_brand_filter(org_filter, brand, collection="organizations")

    # Iter 216h189 — server-side `q` filter. The Master Admin Orgs page
    # used to fetch ALL orgs (up to 2000) and filter client-side by name
    # + owner_email. With 1000+ orgs this shipped ~3-5 MB on every
    # refresh / keystroke-debounce. We now push the text-match into
    # Mongo when `q` is non-empty — the org index on `name` makes this
    # cheap, and the frontend client-side filter stays as a safety net
    # for the few result rows that come back.
    #
    # Matched fields: `name`, `email`, `primary_contact_email`,
    # `primary_contact_name`, `company_code`. We deliberately do NOT
    # join against `users` to filter by `owner_email` — the latency hit
    # would dwarf the saved payload bytes and the rarer use-case is
    # better served by the dedicated `/users` endpoint anyway.
    qs = (q or "").strip()
    if qs and len(qs) >= 2:
        # Case-insensitive substring search. Anchor to len ≥ 2 so single
        # keystrokes don't trigger a near-table-scan.
        import re
        esc = re.escape(qs)
        q_or = [
            {"name": {"$regex": esc, "$options": "i"}},
            {"email": {"$regex": esc, "$options": "i"}},
            {"primary_contact_email": {"$regex": esc, "$options": "i"}},
            {"primary_contact_name": {"$regex": esc, "$options": "i"}},
            {"company_code": {"$regex": esc, "$options": "i"}},
        ]
        # Iter 216h190 bug-fix — `merge_brand_filter` may have already
        # set `$or` for the brand scope. Naively assigning `$or = q_or`
        # would silently wipe the brand filter (verified live: a Pulse
        # admin searching for "fitness" would otherwise see "full"-tier
        # orgs the brand filter intended to hide). Promote both into
        # `$and` so neither is lost — same pattern as merge_brand_filter.
        if "$or" in org_filter:
            existing_or = org_filter.pop("$or")
            existing_and = list(org_filter.get("$and") or [])
            existing_and.extend([{"$or": existing_or}, {"$or": q_or}])
            org_filter["$and"] = existing_and
        else:
            org_filter["$or"] = q_or

    # Iter 216h190 — server-side pagination. Existing callers that don't
    # pass `skip` keep the old behaviour (one big page up to limit=2000),
    # but new callers can page through the result set with `?skip=N`.
    # We always return `total` so callers can render "X of Y" badges
    # without a second round-trip.
    capped_limit = max(1, min(int(limit or 2000), 2000))
    capped_skip = max(0, int(skip or 0))
    total = await db.organizations.count_documents(org_filter)
    orgs = await (
        db.organizations.find(org_filter, _ORG_LIST_EXCLUDE)
        .sort("created_at", -1)
        .skip(capped_skip)
        .limit(capped_limit)
        .to_list(capped_limit)
    )
    if not orgs:
        return {
            "organizations": [],
            "total": total,
            "skip": capped_skip,
            "limit": capped_limit,
            "has_more": False,
        }

    org_ids = [o["id"] for o in orgs]

    # Tier-3.5 N+1 fix (Apr 2026): was 1 + 8×N queries on the master-admin
    # dashboard (≈4000 round-trips for 500 orgs). Now 1 + 8 batched aggregates
    # regardless of org count — the MongoDB planner uses the
    # `organization_id` index on each collection, so this is a 10-100×
    # wall-clock improvement for the admin who sees this page first thing.

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

    async def _crm_owners():
        # CRM-only orgs keep their owner in `crm_users`, not `users`. Fall
        # back to any CRM user when none is explicitly role=owner so the
        # list still shows a contact.
        pipe = [
            {"$match": {"organization_id": {"$in": org_ids}}},
            {"$sort": {"role": 1}},  # 'owner' sorts before others
            {"$group": {
                "_id": "$organization_id",
                "email": {"$first": "$email"},
                "full_name": {"$first": "$full_name"},
            }},
        ]
        return {d["_id"]: d async for d in db.crm_users.aggregate(pipe)}

    (
        sp_user_map, crm_user_map, equip_map, issue_map, open_issue_map,
        file_map, ai_map, owner_map, crm_owner_map,
    ) = await asyncio.gather(
        _group(db.users),
        _group(db.crm_users),
        _group(db.equipment),
        _group(db.issues),
        _group(db.issues, {"status": "open"}),
        _group(db.files),
        _group(db.issues, {"ai_triage": {"$exists": True, "$ne": None}}),
        _owners(),
        _crm_owners(),
    )

    enriched = []
    for org in orgs:
        oid = org["id"]
        owner = owner_map.get(oid) or {}
        crm_owner = crm_owner_map.get(oid) or {}
        # Iter (Jul 2026) fix — the org row showed "No owner" whenever the
        # org had no `users` doc with role=owner, even though an owner WAS
        # set another way. Fall back through: users-role-owner → org's own
        # owner_email → CRM owner → primary contact → admin_email.
        owner_email = (
            owner.get("email")
            or org.get("owner_email")
            or crm_owner.get("email")
            or org.get("primary_contact_email")
            or org.get("admin_email")
            or ""
        )
        owner_name = (
            owner.get("full_name")
            or org.get("owner_name")
            or crm_owner.get("full_name")
            or org.get("primary_contact_name")
            or ""
        )
        enriched.append({
            **org,
            "status": org.get("status", "active"),
            "user_count": sp_user_map.get(oid, 0) + crm_user_map.get(oid, 0),
            "equipment_count": equip_map.get(oid, 0),
            "issue_count": issue_map.get(oid, 0),
            "open_issues": open_issue_map.get(oid, 0),
            "file_count": file_map.get(oid, 0),
            "ai_calls": ai_map.get(oid, 0),
            "owner_email": owner_email,
            "owner_name": owner_name,
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
            "is_head_office": org.get("is_head_office", False),
        })

    return {
        "organizations": enriched,
        "total": total,
        "skip": capped_skip,
        "limit": capped_limit,
        "has_more": (capped_skip + len(enriched)) < total,
    }


# ───────────── /organizations/{id}/status ─────────────

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


# ───────────── /organizations/{id}/subscription ─────────────

@router.put("/master-admin/organizations/{org_id}/subscription")
async def update_org_subscription(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Update org subscription. Accepts both Pulse Fitness tiers (`free`/`pro`/`premium`/
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

    # Lite = free Operations only. Downgrading to Lite auto-disables every
    # bolt-on module (CRM / Memberships / Marketing / Staffing / Reporting);
    # they become re-enableable only on Pro. (Comms lives inside the bolt-ons.)
    if updates.get("account_type") == "lite":
        org_doc = await db.organizations.find_one({"id": org_id}, {"_id": 0, "modules": 1})
        mods = (org_doc or {}).get("modules") or {}
        new_mods = {}
        for k, v in mods.items():
            if isinstance(v, dict):
                new_mods[k] = {**v, "enabled": (k == "operations")}
            else:
                new_mods[k] = v
        ops = new_mods.get("operations")
        new_mods["operations"] = {**(ops if isinstance(ops, dict) else {}), "enabled": True, "tier": "lite"}
        updates["modules"] = new_mods
        updates["enabled_modules"] = ["operations"]
        updates["portal_type"] = "service_portal"

    result = await db.organizations.update_one({"id": org_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await log_activity("subscription_change", f"Changed org {org_id} to {tier}", user["email"], "organization", org_id)
    # Iter 216h276 — subscription change can flip an org INTO (or OUT
    # of) the Pulse mirror set; reconcile the CRM company now.
    try:
        from utils.tenant_mirror import mirror_single_tenant
        await mirror_single_tenant(org_id)
    except Exception:
        pass
    return {"success": True, "tier": tier, "account_type": updates.get("account_type")}


# ───────────── /organizations/{id}/features ─────────────

@router.put("/master-admin/organizations/{org_id}/features")
async def update_org_features(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1, "modules": 1, "account_type": 1})
    old_features = (org or {}).get("features") or {}
    old_modules = (org or {}).get("modules") or {}
    is_lite = (org or {}).get("account_type") == "lite"
    _BOLT_ON_MODULES = {"crm", "memberships", "marketing", "staffing", "reporting"}

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
            existing = old_modules.get(m_key) or {}
            enabled = bool(cfg.get("enabled", existing.get("enabled", False)))
            # Lite orgs cannot enable bolt-on modules — Pro only.
            if is_lite and m_key in _BOLT_ON_MODULES:
                enabled = False
            entry = {"enabled": enabled, "tier": tier}
            # Preserve any legacy/extension keys (e.g. business_enabled)
            for k, v in existing.items():
                if k not in entry:
                    entry[k] = v
            # Stamp the master-admin as the source so an explicit disable
            # here is distinguishable from "never opted in" — the trial
            # gate uses this to show "contact your administrator" instead
            # of a self-serve trial CTA that would re-enable it.
            entry["source"] = "admin"
            # CRM mode flags — Gym (leisure) and Corporate (business). Accept
            # them from the incoming payload (previously dropped) and treat
            # either mode being on as implying CRM itself is enabled.
            if m_key == "crm":
                if "business_enabled" in cfg:
                    entry["business_enabled"] = bool(cfg["business_enabled"])
                if "leisure_enabled" in cfg:
                    entry["leisure_enabled"] = bool(cfg["leisure_enabled"])
                if entry.get("business_enabled") or entry.get("leisure_enabled"):
                    entry["enabled"] = True
            if is_lite and m_key in _BOLT_ON_MODULES:
                entry["enabled"] = False
            merged[m_key] = entry
            if old_modules.get(m_key) != entry:
                changes[f"module:{m_key}"] = {"from": old_modules.get(m_key), "to": entry}

        # Iter 216h59 — REMOVED Memberships→CRM auto-bundle. Operator
        # feedback (Lee): "Memberships and CRM are supposed to be able
        # to work stand-alone." Modules now toggle independently in the
        # Feature Control Panel; the leisure-CRM gate inside
        # `utils/module_access.crm_modes()` was also flipped to read
        # the `crm` flag directly.
        set_doc["modules"] = merged

        # Iter 216h277 — Keep `enabled_modules` array + `portal_type`
        # legacy field in sync with the per-module dict so the Master
        # Admin "CRM Orgs" filter (and any other consumer of either
        # field) sees a single source of truth. Previously, toggling
        # CRM in the Features tab only wrote to `modules.crm.enabled`
        # — the org never appeared in the CRM tab list because that
        # filter still checked `portal_type`.
        enabled_list = [k for k, v in merged.items() if isinstance(v, dict) and v.get("enabled")]
        # Stable order matching the UI grid + filter to known module ids.
        derived_modules = [m for m in ALL_MODULE_IDS if m in enabled_list]
        # Never let the array go empty — every org has at least Operations
        # by product policy (matches `_modules_from_portal_type` default).
        if not derived_modules:
            derived_modules = ["operations"]
        set_doc["enabled_modules"] = derived_modules
        set_doc["portal_type"] = _derive_portal_type(derived_modules)

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


# ───────────── /organizations/{id}/details ─────────────

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
        # Iter 216h109 — MOD portal flags
        "is_mod", "mod_force", "parent_organization_id",
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
        # Iter 216h277 — also reconcile the per-module `modules` dict
        # so the Features tab "Module access" toggles stay coherent
        # with the Details-tab module picker. Without this an admin
        # could toggle CRM ON via the picker but the Features tab
        # would still show it OFF (different storage shape).
        existing_modules = await db.organizations.find_one({"id": org_id}, {"_id": 0, "modules": 1})
        old_modules = (existing_modules or {}).get("modules") or {}
        synced_modules: dict = dict(old_modules)
        for m_key in ("operations", "memberships", "marketing", "crm"):
            prev = old_modules.get(m_key) or {}
            tier = prev.get("tier") if prev.get("tier") in {"lite", "pro", "enterprise"} else "pro"
            entry = {"enabled": m_key in normalised, "tier": tier}
            for k, v in prev.items():
                if k not in entry:
                    entry[k] = v
            entry["source"] = "admin"
            synced_modules[m_key] = entry
        updates["modules"] = synced_modules
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
    # Iter 216h276 — propagate tenant-side changes into the mirrored
    # CRM company so renames + address updates flow forward without
    # a backend restart.
    try:
        from utils.tenant_mirror import mirror_single_tenant
        await mirror_single_tenant(org_id)
    except Exception:
        pass  # mirror is best-effort; never block the admin write
    return {"success": True}


# ───────────── /organizations/{id}/sites — single + bulk create ─────────────

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
            # Iter 216h53 — Sicon per-site "Invoice Customer Ref" so bulk
            # site imports populate the same field as the wizard path.
            "invoice_customer_ref": (row.get("invoice_customer_ref") or "").strip(),
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


# ───────────── /organizations/{id}/head-office — set/clear org as HQ ─────────────

@router.post("/master-admin/organizations/{org_id}/head-office")
async def admin_set_org_head_office(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Mark (or clear) an ORGANISATION as a Head Office.

    When enabling, ensures the org has a Head Office *site* so equipment can be
    onboarded to it — without the operator hand-creating a duplicate site:
      • promote_site_id given → promote that existing site to HQ;
      • else if the org already has a HQ site → keep it;
      • else auto-create a HQ site from the org's own details (named as the org).
    Disabling just clears the org-level flag; the HQ site + its equipment remain.
    """
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    enabled = bool(body.get("enabled", True))

    if not enabled:
        await db.organizations.update_one({"id": org_id}, {"$set": {"is_head_office": False}})
        await log_activity("org_head_office_cleared", f"Cleared Head Office flag for org {org_id}",
                           user["email"], "organization", org_id)
        return {"is_head_office": False, "head_office_site_id": None}

    await db.organizations.update_one({"id": org_id}, {"$set": {"is_head_office": True}})

    promote_site_id = (body.get("promote_site_id") or "").strip()
    ho_site = None

    if promote_site_id:
        site = await db.sites.find_one({"id": promote_site_id, "organization_id": org_id}, {"_id": 0})
        if not site:
            raise HTTPException(status_code=404, detail="Site to promote not found for this org")
        await db.sites.update_many(
            {"organization_id": org_id, "is_head_office": True},
            {"$set": {"is_head_office": False}},
        )
        await db.sites.update_one({"id": promote_site_id}, {"$set": {"is_head_office": True}})
        ho_site = await db.sites.find_one({"id": promote_site_id}, {"_id": 0})
    else:
        ho_site = await db.sites.find_one(
            {"organization_id": org_id, "is_head_office": True}, {"_id": 0})
        if not ho_site:
            # Auto-create a HQ site from the org's own details (choice 2a: same name as the org).
            ho_site = {
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "name": (org.get("name") or "Head Office").strip(),
                "address": (org.get("address_line1") or org.get("address") or "").strip(),
                "address_line1": (org.get("address_line1") or org.get("address") or "").strip(),
                "address_line2": (org.get("address_line2") or "").strip(),
                "address_line3": (org.get("address_line3") or "").strip(),
                "city": (org.get("city") or "").strip(),
                "county": (org.get("county") or "").strip(),
                "postcode": (org.get("postcode") or "").strip(),
                "country": (org.get("country") or "United Kingdom").strip(),
                "phone": (org.get("phone") or org.get("primary_contact_phone") or "").strip(),
                "email": (org.get("primary_contact_email") or "").strip(),
                "site_manager_name": (org.get("primary_contact_name") or "").strip(),
                "site_manager_email": (org.get("primary_contact_email") or "").strip(),
                "is_head_office": True,
                "default_location": "Main Floor",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.sites.insert_one(ho_site)
            ho_site.pop("_id", None)

    await log_activity("org_head_office_set", f"Set org {org_id} as Head Office",
                       user["email"], "organization", org_id)
    return {"is_head_office": True, "head_office_site_id": ho_site["id"], "head_office_site": ho_site}




# ───────────── /head-offices — onboarding "attach to HQ" picker ─────────────

@router.get("/master-admin/head-offices")
async def list_head_offices(user: dict = Depends(get_current_user)):
    """List Pulse-visible organisations that have a Head Office site, so
    the onboarding wizard can attach a new branch site to an existing HQ.
    Returns one entry per org with its head-office site + branch count."""
    require_master_admin(user)
    hq_sites = await db.sites.find(
        {"is_head_office": True},
        {"_id": 0, "id": 1, "name": 1, "organization_id": 1},
    ).to_list(2000)
    if not hq_sites:
        return {"head_offices": []}

    org_ids = list({s["organization_id"] for s in hq_sites if s.get("organization_id")})
    orgs = await db.organizations.find(
        {"id": {"$in": org_ids}, "account_type": {"$in": list(PULSE_VISIBLE_ACCOUNT_TYPES)}},
        {"_id": 0, "id": 1, "name": 1, "company_code": 1, "account_type": 1},
    ).to_list(2000)
    org_map = {o["id"]: o for o in orgs}

    # Branch counts per org (one aggregate query).
    counts = await db.sites.aggregate([
        {"$match": {"organization_id": {"$in": list(org_map.keys())}}},
        {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
    ]).to_list(2000)
    count_map = {c["_id"]: c["n"] for c in counts}

    out = []
    for s in hq_sites:
        org = org_map.get(s.get("organization_id"))
        if not org:
            continue
        out.append({
            "organization_id": org["id"],
            "organization_name": org.get("name"),
            "company_code": org.get("company_code"),
            "head_office_site_id": s["id"],
            "head_office_name": s.get("name"),
            "site_count": count_map.get(org["id"], 1),
        })
    out.sort(key=lambda x: (x.get("organization_name") or "").lower())
    return {"head_offices": out}
