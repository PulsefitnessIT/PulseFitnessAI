"""Sites routes — CRUD for multi-site management."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
import uuid

from utils.database import db
from utils.auth import get_current_user

router = APIRouter()


@router.get("/sites")
async def get_my_sites(user: dict = Depends(get_current_user)) -> dict:
    """Return all sites belonging to the current user's organization."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"sites": []}

    sites = await db.sites.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    # Enrich with counts
    enriched = []
    for site in sites:
        eq_count = await db.equipment.count_documents({
            "organization_id": org_id, "site_id": site["id"]
        })
        issue_count = await db.issues.count_documents({
            "organization_id": org_id, "site_id": site["id"]
        })
        enriched.append({**site, "equipment_count": eq_count, "issue_count": issue_count})

    if enriched:
        return {"sites": enriched}

    # Fallback: no sites — return org as default site
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "id": 1, "name": 1, "address": 1}
    )
    if org:
        eq_count = await db.equipment.count_documents({"organization_id": org_id})
        issue_count = await db.issues.count_documents({"organization_id": org_id})
        return {"sites": [{
            "id": org["id"],
            "organization_id": org_id,
            "name": org.get("name", "Main Site"),
            "address": org.get("address", ""),
            "is_default": True,
            "equipment_count": eq_count,
            "issue_count": issue_count,
        }]}

    return {"sites": []}


@router.get("/sites/overview")
async def get_sites_overview(user: dict = Depends(get_current_user)) -> dict:
    """Iter 216i — Multi-site KPI roll-up for owner/manager dashboards.

    Returns per-site KPIs plus a sorted "best-performing-sites" ranking.
    A site is "best-performing" when it has the lowest open-fault count
    relative to its equipment and the highest check-sheet completion rate.

    Scoring formula (0–100, higher is better):
        score = 100
                - min(40, open_faults * 8)            # open fault penalty
                - min(20, overdue_faults * 5)         # overdue penalty
                + min(20, completion_rate * 20)       # check-sheet bonus
        clamped to [0, 100]

    Returns:
        {
          "sites": [
             {site_id, name, equipment_count, open_faults, overdue_faults,
              faults_this_week, score, rank}, ...
          ],
          "totals": {equipment, open_faults, overdue_faults, sites},
          "best_site": {id, name, score} | null,
          "worst_site": {id, name, score} | null
        }
    """
    from datetime import datetime, timedelta, timezone as _tz
    org_id = user.get("organization_id")
    if not org_id:
        return {"sites": [], "totals": {"equipment": 0, "open_faults": 0, "overdue_faults": 0, "sites": 0}, "best_site": None, "worst_site": None}

    sites = await db.sites.find({"organization_id": org_id}, {"_id": 0}).sort("name", 1).to_list(200)
    if not sites:
        # Fall back to org-as-single-site so the overview still renders
        # something meaningful for non-multi-site tenants.
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1})
        if not org:
            return {"sites": [], "totals": {"equipment": 0, "open_faults": 0, "overdue_faults": 0, "sites": 0}, "best_site": None, "worst_site": None}
        sites = [{"id": org["id"], "name": org.get("name", "Main Site"), "is_default": True}]

    week_ago = (datetime.now(_tz.utc) - timedelta(days=7)).isoformat()
    now_iso = datetime.now(_tz.utc).isoformat()

    enriched = []
    total_equipment = 0
    total_open = 0
    total_overdue = 0

    for s in sites:
        site_filter = {"organization_id": org_id, "site_id": s["id"]}
        eq_count = await db.equipment.count_documents(site_filter)
        open_faults = await db.issues.count_documents({**site_filter, "status": {"$in": ["open", "in_progress", "awaiting_parts"]}})
        overdue_faults = await db.issues.count_documents({
            **site_filter,
            "status": {"$in": ["open", "in_progress", "awaiting_parts"]},
            "sla_deadline": {"$lt": now_iso, "$ne": None},
        })
        faults_this_week = await db.issues.count_documents({
            **site_filter, "created_at": {"$gte": week_ago},
        })
        # Check-sheet completion rate over last 7 days (instances with
        # status='completed' / total instances). count_documents on a
        # non-existent collection is safe (returns 0).
        total_checks = await db.check_sheet_instances.count_documents({
            **site_filter, "created_at": {"$gte": week_ago},
        })
        completed_checks = await db.check_sheet_instances.count_documents({
            **site_filter, "status": "completed", "created_at": {"$gte": week_ago},
        })
        completion_rate = (completed_checks / total_checks) if total_checks else 0.0

        # Score (higher = better)
        score = 100 - min(40, open_faults * 8) - min(20, overdue_faults * 5) + int(min(20, completion_rate * 20))
        score = max(0, min(100, score))

        enriched.append({
            "id": s["id"],
            "name": s.get("name") or "Unnamed site",
            "address": s.get("address") or "",
            "postcode": s.get("postcode") or "",
            "is_head_office": bool(s.get("is_head_office")),
            "equipment_count": eq_count,
            "open_faults": open_faults,
            "overdue_faults": overdue_faults,
            "faults_this_week": faults_this_week,
            "completion_rate": round(completion_rate, 2),
            "score": score,
        })
        total_equipment += eq_count
        total_open += open_faults
        total_overdue += overdue_faults

    # Sort by score desc, then by open_faults asc (tiebreak)
    ranked = sorted(enriched, key=lambda x: (-x["score"], x["open_faults"]))
    for i, s in enumerate(ranked, 1):
        s["rank"] = i

    return {
        "sites": ranked,
        "totals": {
            "equipment": total_equipment,
            "open_faults": total_open,
            "overdue_faults": total_overdue,
            "sites": len(enriched),
            "faults_this_week": sum(s["faults_this_week"] for s in enriched),
        },
        "best_site": ranked[0] if ranked else None,
        "worst_site": ranked[-1] if len(ranked) > 1 else None,
    }


@router.post("/sites")
async def create_site(
    body: dict = Body(...), user: dict = Depends(get_current_user)
) -> dict:
    """Create a new site within the user's organization. Owner/manager only."""
    if user.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Only owners/managers can create sites")

    org_id = user.get("organization_id")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Site name is required")

    site_id = str(uuid.uuid4())
    is_head_office = bool(body.get("is_head_office"))
    site_doc = {
        "id": site_id,
        "organization_id": org_id,
        "name": name,
        "address": (body.get("address") or "").strip(),
        "postcode": (body.get("postcode") or "").strip(),
        "is_head_office": is_head_office,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if is_head_office:
        # Iter 215bi — only one site per org can be HQ at a time. If the new
        # site is being created as HQ, demote any existing HQ first.
        await db.sites.update_many(
            {"organization_id": org_id, "is_head_office": True},
            {"$set": {"is_head_office": False}},
        )
    await db.sites.insert_one(site_doc)
    site_doc.pop("_id", None)
    return {**site_doc, "equipment_count": 0, "issue_count": 0}


@router.patch("/sites/{site_id}")
async def update_site(
    site_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)
) -> dict:
    """Update a site's details."""
    if user.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Only owners/managers can edit sites")

    org_id = user.get("organization_id")
    existing = await db.sites.find_one(
        {"id": site_id, "organization_id": org_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found")

    updates = {}
    for field in ("name", "address", "postcode"):
        if field in body:
            updates[field] = (body[field] or "").strip()
    # Iter 215bi — head-office flag (boolean). If set true, demote any
    # other site in the same org so only one HQ exists.
    if "is_head_office" in body:
        new_hq = bool(body.get("is_head_office"))
        updates["is_head_office"] = new_hq
        if new_hq:
            await db.sites.update_many(
                {"organization_id": org_id, "is_head_office": True, "id": {"$ne": site_id}},
                {"$set": {"is_head_office": False}},
            )

    if updates:
        await db.sites.update_one({"id": site_id}, {"$set": updates})

    updated = await db.sites.find_one({"id": site_id}, {"_id": 0})
    return updated or {}


@router.delete("/sites/{site_id}")
async def delete_site(
    site_id: str, user: dict = Depends(get_current_user)
) -> dict:
    """Delete a site. Equipment is unlinked (site_id cleared), not deleted."""
    if user.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Only owners/managers can delete sites")

    org_id = user.get("organization_id")
    result = await db.sites.delete_one({"id": site_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Site not found")

    # Unlink equipment and issues from this site
    await db.equipment.update_many(
        {"organization_id": org_id, "site_id": site_id},
        {"$unset": {"site_id": ""}}
    )
    await db.issues.update_many(
        {"organization_id": org_id, "site_id": site_id},
        {"$unset": {"site_id": ""}}
    )
    return {"success": True}


@router.post("/sites/{site_id}/assign-equipment")
async def assign_equipment_to_site(
    site_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)
) -> dict:
    """Bulk-assign equipment to a site."""
    org_id = user.get("organization_id")
    equipment_ids = body.get("equipment_ids", [])
    if not equipment_ids:
        raise HTTPException(status_code=400, detail="equipment_ids required")

    # Verify site belongs to org
    site = await db.sites.find_one(
        {"id": site_id, "organization_id": org_id}, {"_id": 0, "id": 1}
    )
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    result = await db.equipment.update_many(
        {"organization_id": org_id, "id": {"$in": equipment_ids}},
        {"$set": {"site_id": site_id}}
    )
    return {"success": True, "updated": result.modified_count}


# ────────────────── Per-site module overrides ──────────────────
# A multi-site org can selectively enable/disable modules per site.
# Resolution order at runtime is:
#   site.modules.<key>.enabled (if explicitly set)
#       → org.modules.<key>.enabled (the matrix from FeatureControlPanel)
#       → account_type fallback (utils/module_access.py)
#
# Master admin (or org owner/manager) sets the per-site overrides through
# this endpoint. Listing returns the effective resolution per site.

_VALID_MODULES = {"operations", "memberships", "marketing"}


@router.get("/sites/{site_id}/modules")
async def get_site_modules(site_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Effective module access for a single site. Returns the override doc
    if one exists plus the merged effective {operations,memberships,marketing}."""
    # Master admins can introspect any site; everyone else is scoped to their org.
    if user.get("is_master_admin"):
        site = await db.sites.find_one(
            {"id": site_id}, {"_id": 0, "id": 1, "name": 1, "modules": 1, "organization_id": 1},
        )
    else:
        org_id = user.get("organization_id")
        site = await db.sites.find_one(
            {"id": site_id, "organization_id": org_id}, {"_id": 0, "id": 1, "name": 1, "modules": 1, "organization_id": 1},
        )
    if not site:
        raise HTTPException(404, "Site not found")
    org = await db.organizations.find_one({"id": site.get("organization_id")}, {"_id": 0, "modules": 1, "account_type": 1}) or {}
    org_modules = (org.get("modules") or {})
    site_modules = (site.get("modules") or {})

    from utils.module_access import resolve_module_access
    org_resolved = resolve_module_access(user, org)

    effective = {}
    for k in _VALID_MODULES:
        site_cfg = site_modules.get(k)
        if isinstance(site_cfg, dict) and "enabled" in site_cfg:
            effective[k] = bool(site_cfg["enabled"])
        else:
            effective[k] = org_resolved.get(k, False)
    return {
        "site_id": site["id"], "site_name": site.get("name"),
        "site_overrides": site_modules, "org_modules": org_modules,
        "effective": effective,
    }


@router.put("/sites/{site_id}/modules")
async def set_site_modules(site_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Set per-site module overrides. Body: {modules: {operations:{enabled:bool}, ...}}.
    Pass `null` to clear an override (the site re-inherits the org-level setting).
    Owner/manager/master-admin only."""
    if not user.get("is_master_admin") and user.get("role") not in ("owner", "manager"):
        raise HTTPException(403, "Only owners/managers/master-admin can set site modules")
    if user.get("is_master_admin"):
        site = await db.sites.find_one({"id": site_id}, {"_id": 0, "id": 1, "modules": 1})
    else:
        org_id = user.get("organization_id")
        site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0, "id": 1, "modules": 1})
    if not site:
        raise HTTPException(404, "Site not found")
    incoming = (body.get("modules") or {})
    existing = (site.get("modules") or {})
    next_modules = {**existing}
    cleared: list[str] = []
    set_keys: list[str] = []
    for key, cfg in incoming.items():
        if key not in _VALID_MODULES:
            continue
        if cfg is None or (isinstance(cfg, dict) and cfg.get("enabled") is None and cfg.get("clear")):
            next_modules.pop(key, None)
            cleared.append(key)
        elif isinstance(cfg, dict) and "enabled" in cfg:
            next_modules[key] = {"enabled": bool(cfg["enabled"])}
            set_keys.append(key)
    await db.sites.update_one({"id": site_id}, {"$set": {"modules": next_modules}})
    return {"ok": True, "modules": next_modules, "cleared": cleared, "set": set_keys}



@router.get("/master-admin/organizations/{org_id}/sites")
async def admin_list_org_sites(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Master-admin listing of all sites belonging to a given org, with the
    same default-site fallback the operator-facing /sites endpoint uses.
    Used by the Master Admin org drawer to flip per-site module overrides."""
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    sites = await db.sites.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)

    enriched = []
    for site in sites:
        eq_count = await db.equipment.count_documents({
            "organization_id": org_id, "site_id": site["id"]
        })
        issue_count = await db.issues.count_documents({
            "organization_id": org_id, "site_id": site["id"]
        })
        enriched.append({**site, "equipment_count": eq_count, "issue_count": issue_count})

    if enriched:
        return {"sites": enriched}

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "id": 1, "name": 1, "address": 1}
    )
    if org:
        eq_count = await db.equipment.count_documents({"organization_id": org_id})
        issue_count = await db.issues.count_documents({"organization_id": org_id})
        return {"sites": [{
            "id": org["id"],
            "organization_id": org_id,
            "name": org.get("name", "Main Site"),
            "address": org.get("address", ""),
            "is_default": True,
            "equipment_count": eq_count,
            "issue_count": issue_count,
        }]}
    return {"sites": []}



@router.patch("/master-admin/organizations/{org_id}/sites/{site_id}")
async def admin_patch_org_site(
    org_id: str,
    site_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 215bi — master-admin can update site fields (including the
    head-office flag) for any org within their scope. Mirrors the
    org-owner PATCH /sites/{site_id} but routed through master-admin
    auth so platform admins don't need to impersonate."""
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    existing = await db.sites.find_one(
        {"id": site_id, "organization_id": org_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found")

    updates: dict = {}
    for field in ("name", "address", "postcode"):
        if field in body:
            updates[field] = (body[field] or "").strip()
    if "is_head_office" in body:
        new_hq = bool(body.get("is_head_office"))
        updates["is_head_office"] = new_hq
        if new_hq:
            await db.sites.update_many(
                {"organization_id": org_id, "is_head_office": True, "id": {"$ne": site_id}},
                {"$set": {"is_head_office": False}},
            )
    if updates:
        await db.sites.update_one({"id": site_id}, {"$set": updates})
    updated = await db.sites.find_one({"id": site_id}, {"_id": 0})
    return updated or {}


@router.post("/master-admin/organizations/{org_id}/sites/{site_id}/move")
async def admin_move_site_org(
    org_id: str,
    site_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 215br — Move a site from `org_id` (the current parent) to a new
    parent organisation. All equipment, issues and per-site module
    overrides travel with the site. Used by the Master Admin org drawer
    "Linked sites" tab to roll up multi-site groups under the right HQ.
    """
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    target_org_id = (body.get("target_organization_id") or "").strip()
    if not target_org_id:
        raise HTTPException(status_code=400, detail="target_organization_id required")
    if target_org_id == org_id:
        raise HTTPException(status_code=400, detail="Site is already on this org")
    await assert_org_in_pulse_scope(user, target_org_id)

    target = await db.organizations.find_one(
        {"id": target_org_id}, {"_id": 0, "id": 1, "name": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Target organisation not found")

    site = await db.sites.find_one(
        {"id": site_id, "organization_id": org_id}, {"_id": 0}
    )
    if not site:
        raise HTTPException(status_code=404, detail="Site not found on this org")

    # Move the site itself (always demote head-office on a move so the new
    # parent's existing HQ flag isn't stomped).
    await db.sites.update_one(
        {"id": site_id},
        {"$set": {
            "organization_id": target_org_id,
            "is_head_office": False,
            "moved_at": datetime.now(timezone.utc).isoformat(),
            "moved_by": user.get("id"),
            "moved_from_organization_id": org_id,
        }},
    )

    # Equipment + issues live under the site -> follow it.
    eq_res = await db.equipment.update_many(
        {"organization_id": org_id, "site_id": site_id},
        {"$set": {"organization_id": target_org_id}},
    )
    iss_res = await db.issues.update_many(
        {"organization_id": org_id, "site_id": site_id},
        {"$set": {"organization_id": target_org_id}},
    )

    return {
        "success": True,
        "site_id": site_id,
        "moved_from": org_id,
        "moved_to": target_org_id,
        "target_organization_name": target.get("name"),
        "equipment_moved": eq_res.modified_count,
        "issues_moved": iss_res.modified_count,
    }



# ────────────────── Per-site branding overrides (iter 216af) ──────────────────
# Parent → child inheritance: a site's branding (logo / primary colour /
# name override) overrides its parent organisation's. Resolution order:
#   site.branding.<field> → org.branding.<field> → org.<direct field> → default
# Used by: public /m/{slug}/branding?site=... and any internal email/PDF
# renderer that needs the right look-and-feel for a specific venue.


_BRANDING_ALLOWED = {"name", "logo_url", "primary_color", "secondary_color"}
_DEFAULT_PRIMARY = "#19CDFF"


def _effective_site_branding(org: dict, site: dict | None) -> dict:
    """Merge parent-org branding + site-level override. Site wins where it
    carries a non-empty value. Always returns a fully-populated dict so
    consumers never have to reach into None."""
    org = org or {}
    org_b = (org.get("branding") or {}) if isinstance(org.get("branding"), dict) else {}
    # Parent org fallback chain — the `branding` sub-doc is authoritative
    # when set (that's what auth.py writes), then direct fields we store
    # at the top level for legacy reasons.
    parent = {
        "name":             org_b.get("company_name") or org_b.get("name") or org.get("name") or "",
        "logo_url":         org_b.get("logo_url") or org.get("logo_url") or "",
        "primary_color":    org_b.get("primary_color") or org.get("primary_brand_colour") or org.get("primary_color") or _DEFAULT_PRIMARY,
        "secondary_color":  org_b.get("secondary_color") or org.get("secondary_color") or "",
    }
    site_b = ((site or {}).get("branding") or {})
    out: dict = {}
    for k, default in parent.items():
        v = site_b.get(k)
        out[k] = v if (v is not None and v != "") else default
    # Source metadata so the UI can show "inherited" vs "overridden" badges.
    out["_inherits"] = {k: (site_b.get(k) in (None, "")) for k in parent}
    out["_parent"] = parent
    return out


@router.get("/sites/{site_id}/branding")
async def get_site_branding(site_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Return the effective branding for a site (parent org + site override)."""
    if user.get("is_master_admin"):
        site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    else:
        org_id = user.get("organization_id")
        site = await db.sites.find_one(
            {"id": site_id, "organization_id": org_id}, {"_id": 0},
        )
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    org = await db.organizations.find_one({"id": site.get("organization_id")}, {"_id": 0}) or {}
    effective = _effective_site_branding(org, site)
    return {
        "site_id": site["id"],
        "site_name": site.get("name"),
        "effective": effective,
        "override": site.get("branding") or {},
        "parent": effective["_parent"],
    }


@router.patch("/sites/{site_id}/branding")
async def update_site_branding(
    site_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Owner/manager — write a site-level branding override. Pass any
    subset of `{name, logo_url, primary_color, secondary_color}`. Passing
    an empty string clears that field so it falls back to the parent org's
    value again."""
    if user.get("role") not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners/managers can update site branding")
    org_id = user.get("organization_id")
    q = {"id": site_id}
    if not user.get("is_master_admin"):
        q["organization_id"] = org_id
    site = await db.sites.find_one(q, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    current = (site.get("branding") or {}).copy()
    for k in _BRANDING_ALLOWED:
        if k in body:
            v = body.get(k)
            if v in (None, ""):
                current.pop(k, None)
            else:
                current[k] = str(v).strip()
    await db.sites.update_one(
        {"id": site_id},
        {"$set": {
            "branding": current,
            "branding_updated_at": datetime.now(timezone.utc).isoformat(),
            "branding_updated_by": user.get("id"),
        }},
    )

    # Audit — brand changes are material to member-facing look-and-feel.
    try:
        from utils.security_plus import audit_required
        await audit_required("security_audit_log", {
            "event": "site.branding.updated",
            "actor_id": user.get("id"),
            "actor_email": user.get("email"),
            "org_id": site.get("organization_id"),
            "site_id": site_id,
            "changes": list(body.keys()),
        })
    except Exception:
        pass

    org = await db.organizations.find_one(
        {"id": site.get("organization_id")}, {"_id": 0},
    ) or {}
    fresh = await db.sites.find_one({"id": site_id}, {"_id": 0})
    effective = _effective_site_branding(org, fresh)
    return {
        "site_id": site_id,
        "override": fresh.get("branding") or {},
        "effective": effective,
        "parent": effective["_parent"],
    }


@router.get("/master-admin/module-status")
async def admin_module_status(user: dict = Depends(get_current_user)) -> dict:
    """Roll-up of module entitlements for the Organisations dashboard.
    Returns a map keyed by org_id with:
      • org_disabled        — list of module keys explicitly disabled at org level
      • sites_total         — number of real sites for the org
      • sites_with_overrides — number of sites that carry at least one
                                explicit module override (any value)

    Pulse Master Admins are scoped to their visible orgs; the GymAxis
    master admin sees every org. One aggregation pipeline + one find — no
    N+1 over the org list.
    """
    from routes.master_admin import require_master_admin, _resolve_pulse_scope_org_ids
    require_master_admin(user)

    pulse_org_ids = await _resolve_pulse_scope_org_ids(user)
    org_filter: dict = {}
    if pulse_org_ids is not None:
        org_filter["id"] = {"$in": pulse_org_ids}

    orgs = await db.organizations.find(
        org_filter, {"_id": 0, "id": 1, "modules": 1}
    ).to_list(1000)
    org_ids = [o["id"] for o in orgs]

    org_status: dict[str, dict] = {}
    for o in orgs:
        modules = (o.get("modules") or {})
        disabled = [
            k for k in ("operations", "memberships", "marketing")
            if isinstance(modules.get(k), dict) and modules[k].get("enabled") is False
        ]
        org_status[o["id"]] = {
            "org_disabled": disabled,
            "sites_total": 0,
            "sites_with_overrides": 0,
        }

    if org_ids:
        pipe = [
            {"$match": {"organization_id": {"$in": org_ids}}},
            {"$project": {
                "organization_id": 1,
                "has_override": {
                    "$gt": [
                        {"$size": {"$ifNull": [{"$objectToArray": "$modules"}, []]}},
                        0,
                    ]
                },
            }},
            {"$group": {
                "_id": "$organization_id",
                "sites_total": {"$sum": 1},
                "sites_with_overrides": {"$sum": {"$cond": ["$has_override", 1, 0]}},
            }},
        ]
        async for row in db.sites.aggregate(pipe):
            entry = org_status.get(row["_id"])
            if entry is not None:
                entry["sites_total"] = int(row.get("sites_total") or 0)
                entry["sites_with_overrides"] = int(row.get("sites_with_overrides") or 0)

    return {"data": org_status, "scoped": pulse_org_ids is not None}
