"""Sites routes — CRUD for multi-site management."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
import uuid

from utils.database import db
from utils.auth import get_current_user

router = APIRouter()


@router.get("/sites")
async def get_my_sites(user: dict = Depends(get_current_user)) -> dict:
    """Return all sites belonging to the current user's organization.

    Iter 216bk — site-locking for non-privileged staff.
    Owner / manager / master-admin always see every site in the org.
    Other roles (`staff`, `crm`, `service_desk`, etc.) are filtered by
    the user document's `allowed_site_ids` list when it's present and
    non-empty. Empty/absent list = unrestricted (the legacy default,
    so existing accounts continue to work without migration).
    """
    org_id = user.get("organization_id")
    if not org_id:
        return {"sites": []}

    # Iter 216h15 / 216h32 — auto-create a real Head Office site when an
    # org has ≥1 site but none is flagged `is_head_office`. Head Office
    # is a PROPER site (sales/marketing/admin staff are assigned to it,
    # even though it usually has no equipment), so it must be persisted
    # in `db.sites` rather than synthesised on read. Idempotent: only
    # runs when there are real sites AND no real HQ already exists.
    #
    # Iter 216h32 — dropped the `is_privileged` gate. Lee's production
    # incident (Pulse Fitness · iGym Carshalton / Congleton, no HQ row)
    # showed that gating auto-create on a narrow role allow-list silently
    # skipped the insert whenever the operator's role wasn't exactly
    # owner/manager (e.g. legacy roles like "admin" or "site_manager").
    # Auto-create is idempotent and harmless for non-privileged callers —
    # they just won't see the HQ themselves until an owner visits.
    role = (user.get("role") or "").lower()
    is_privileged = (
        role in ("owner", "manager", "master_admin", "master")
        or bool(user.get("is_master_admin"))
    )
    existing = await db.sites.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "is_head_office": 1},
    ).to_list(200)
    if existing and not any(bool(s.get("is_head_office")) for s in existing):
        org_doc = await db.organizations.find_one(
            {"id": org_id}, {"_id": 0, "name": 1, "address": 1},
        )
        if org_doc:
            hq_id = str(uuid.uuid4())
            await db.sites.insert_one({
                "id": hq_id,
                "organization_id": org_id,
                "name": f"{org_doc.get('name', 'Head Office')} Head Office",
                "address": org_doc.get("address", ""),
                "is_head_office": True,
                "default_location": "Head Office",
                "auto_created": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Diagnostic — should never happen since the user's
            # organization_id always matches a real org doc, but log it
            # so we can spot mis-linked accounts.
            import logging
            logging.warning(
                "auto_create_hq.skipped: org_doc missing for org_id=%s user=%s",
                org_id, user.get("email"),
            )

    # Iter 216h61 — hide archived sites from the operator UI. The
    # Master Admin org drawer still lists them (with an "Archived"
    # badge) via `admin_list_org_sites`, but operator-facing screens
    # treat archived as deleted-but-recoverable.
    sites = await db.sites.find(
        {"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    allowed = user.get("allowed_site_ids") or []
    if not is_privileged and allowed:
        allowed_set = set(allowed)
        sites = [s for s in sites if s.get("id") in allowed_set]

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
        # Iter 216h15 — sort HQ to the top of the list (so the
        # SiteSwitcher renders "Head Office" first), then real sites
        # in their original creation order.
        enriched.sort(key=lambda s: (not bool(s.get("is_head_office")), 0))
    else:
        enriched = []

    # Iter 216h113j — MOD Head Office rollup. When the caller is at a
    # MOD HQ org (`account_type=mod_org`), expose every `mod_site` org
    # that shares the same `mod_force` as a virtual site so the HQ's
    # SiteSwitcher / reports can drill into individual gyms or roll
    # everything up under "All Operations Sites". Each MOD site is its
    # own organisation row, so we surface them with their org id
    # serving double duty as the site id.
    at = (user.get("account_type") or "").lower()
    if at == "mod_org":
        org_doc = await db.organizations.find_one(
            {"id": org_id}, {"_id": 0, "mod_force": 1, "name": 1},
        )
        force = (org_doc or {}).get("mod_force") if org_doc else None
        if force:
            child_orgs = await db.organizations.find(
                {
                    "account_type": "mod_site",
                    "mod_force": (force or "").lower(),
                    "is_mod": True,
                    "status": {"$ne": "archived"},
                },
                {"_id": 0, "id": 1, "name": 1, "address": 1, "mod_branch": 1, "mod_force": 1},
            ).sort("name", 1).to_list(2000)
            existing_ids = {s.get("id") for s in enriched}
            for c in child_orgs:
                if c["id"] in existing_ids:
                    continue
                eq_count = await db.equipment.count_documents({"site_id": c["id"]})
                issue_count = await db.issues.count_documents({"site_id": c["id"]})
                enriched.append({
                    "id": c["id"],
                    "organization_id": c["id"],
                    "name": c.get("name") or "(unnamed)",
                    "address": c.get("address") or "",
                    "mod_branch": c.get("mod_branch"),
                    "mod_force": c.get("mod_force"),
                    "is_mod_child": True,
                    "is_head_office": False,
                    "equipment_count": eq_count,
                    "issue_count": issue_count,
                })

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
        # Iter 216h50 — Sicon "Invoice Customer Ref" per-site reference.
        # Stored even when blank so the field is always present on read.
        "invoice_customer_ref": (body.get("invoice_customer_ref") or "").strip(),
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
    for field in ("name", "address", "postcode", "invoice_customer_ref"):
        if field in body:
            updates[field] = (body[field] or "").strip()
    # Iter 216h113j — MOD force selector (army/raf/navy). MOD tenants
    # tag each site with one of the three services so HQ rollups can
    # filter correctly. Non-MOD orgs ignore this field entirely.
    if "mod_force" in body:
        v = (body.get("mod_force") or "").strip().lower()
        if v in ("army", "raf", "navy"):
            updates["mod_force"] = v
        elif v in ("", None):
            updates["mod_force"] = None
        else:
            raise HTTPException(400, "mod_force must be one of army | raf | navy")
    # Phase S2 — optional geofence config for staff time-clock.
    # latitude/longitude are floats in decimal degrees; radius is metres.
    for field in ("latitude", "longitude", "geofence_radius_m"):
        if field in body:
            val = body[field]
            if val in (None, ""):
                updates[field] = None
            else:
                try:
                    updates[field] = float(val) if field != "geofence_radius_m" else int(val)
                except (TypeError, ValueError) as err:
                    raise HTTPException(400, f"Invalid {field}") from err
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
    org = await db.organizations.find_one({"id": site.get("organization_id")}, {"_id": 0, "modules": 1, "account_type": 1, "module_trials": 1}) or {}
    org_modules = (org.get("modules") or {})
    site_modules = (site.get("modules") or {})

    from utils.module_access import _org_module_access
    # Iter 216h60 — use the user-agnostic org resolver so master-admin
    # introspection doesn't inflate the effective set.
    org_resolved = _org_module_access({"is_master_admin": False, "account_type": "full"}, org)

    effective = {}
    for k in _VALID_MODULES:
        org_on = bool(org_resolved.get(k, False))
        site_cfg = site_modules.get(k)
        if isinstance(site_cfg, dict) and "enabled" in site_cfg:
            # Iter 216h60 — site override cannot exceed org access.
            # A legacy override saying enabled=true on a module the
            # org now has off should resolve to FALSE so the operator
            # never sees a phantom-enabled module.
            effective[k] = bool(site_cfg["enabled"]) and org_on
        else:
            effective[k] = org_on
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
    # Iter 216h60 — guard: site override cannot ENABLE a module the
    # parent org has disabled. Operator feedback (Lee): "Sites are
    # showing that they have modules switched on however the main
    # feature control is switched off." Sites toggles must be a strict
    # subset of the org-level matrix.
    # We deliberately compute the org's *intrinsic* access (not
    # user-scoped) — passing user=master-admin to resolve_module_access
    # returns all-true and would defeat the guard. The right check is:
    # "is this module enabled at the ORG layer regardless of which
    # user is making the call?"
    site_full = await db.sites.find_one({"id": site_id}, {"_id": 0, "organization_id": 1})
    org_doc = await db.organizations.find_one(
        {"id": (site_full or {}).get("organization_id")}, {"_id": 0, "modules": 1, "account_type": 1, "module_trials": 1},
    ) or {}
    from utils.module_access import _org_module_access
    # Use a synthetic non-master, non-mod user so the resolver applies
    # the actual org matrix + trials + account-type defaults.
    org_resolved = _org_module_access({"is_master_admin": False, "account_type": "full"}, org_doc)
    blocked: list[str] = []
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
            wants_on = bool(cfg["enabled"])
            if wants_on and not org_resolved.get(key, False):
                # Refuse to enable a module the parent org has off.
                blocked.append(key)
                # Also strip any previously-stored override so the UI
                # immediately reflects the org-level state.
                next_modules.pop(key, None)
                continue
            next_modules[key] = {"enabled": wants_on}
            set_keys.append(key)
    await db.sites.update_one({"id": site_id}, {"$set": {"modules": next_modules}})
    if blocked:
        return {
            "ok": False,
            "modules": next_modules, "cleared": cleared, "set": set_keys,
            "blocked": blocked,
            "detail": (
                f"Cannot enable {', '.join(blocked)} at site level — the parent organisation has "
                "that module turned off. Enable it on the org first via Master Admin → Modules."
            ),
        }
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
        # Iter 216h31 — mirror /api/sites: sort HQ to the top so the
        # Master Admin org drawer's Sites tab renders Head Office first.
        enriched.sort(key=lambda s: (not bool(s.get("is_head_office")), 0))
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



@router.get("/master-admin/organizations/{org_id}/sites/{site_id}/equipment")
async def admin_list_site_equipment(
    org_id: str,
    site_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h61 — master-admin equipment listing scoped to a single
    site. Mirrors `/api/equipment?site_id=` but uses the target org_id
    rather than the master-admin's own `user_id` (which is what the
    generic `/equipment` endpoint falls back to for master-admin users
    that don't have an organization_id, returning 0 cross-org results).

    Used by the Master Admin Site Detail drawer → Equipment tab to
    drill into Third Space / Pulse / any-customer machines.
    """
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    items = await db.equipment.find(
        {"organization_id": org_id, "site_id": site_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)
    return {"equipment": items, "count": len(items)}


@router.post("/master-admin/organizations/{org_id}/sites/{site_id}/archive")
async def admin_archive_site(
    org_id: str,
    site_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h61 (f) — soft-archive a site. Keeps the row in the
    sites collection so equipment + issues + audit trail still resolve
    historically, but flips `archived=true` so it disappears from the
    operator-facing UI. Restore by clearing the flag (DELETE returns
    the archive metadata so it can be undone)."""
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site.get("is_head_office"):
        # Refuse to archive HQ until the operator demotes it or moves
        # equipment elsewhere. Prevents accidental data orphaning.
        head_office_count = await db.sites.count_documents(
            {"organization_id": org_id, "is_head_office": True, "archived": {"$ne": True}},
        )
        if head_office_count <= 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot archive the Head Office while it's the only HQ. "
                    "Promote another site to Head Office first, then archive this one."
                ),
            )
    await db.sites.update_one(
        {"id": site_id, "organization_id": org_id},
        {"$set": {
            "archived": True,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": user.get("id"),
        }},
    )
    return {"ok": True, "site_id": site_id, "archived": True}


@router.post("/master-admin/organizations/{org_id}/sites/{site_id}/restore")
async def admin_restore_site(
    org_id: str,
    site_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h61 — undo an archive."""
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    r = await db.sites.update_one(
        {"id": site_id, "organization_id": org_id},
        {"$unset": {"archived": "", "archived_at": "", "archived_by": ""}},
    )
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"ok": True, "site_id": site_id, "archived": False}


@router.delete("/master-admin/organizations/{org_id}/sites/{site_id}")
async def admin_delete_site(
    org_id: str,
    site_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h61 (f) — HARD delete a site. Refused when the site has
    equipment or open issues — operator must move/archive those first
    so no historical data is silently orphaned. The Site Detail drawer
    must explicitly call this after a confirmation dialog.
    """
    from routes.master_admin import require_master_admin, assert_org_in_pulse_scope
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    eq_count = await db.equipment.count_documents({"organization_id": org_id, "site_id": site_id})
    open_issue_count = await db.issues.count_documents(
        {"organization_id": org_id, "site_id": site_id, "status": {"$nin": ["resolved", "closed", "archived"]}},
    )
    if eq_count or open_issue_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete '{site.get('name')}' while it still has "
                f"{eq_count} equipment item(s) and {open_issue_count} open issue(s). "
                "Move the equipment to another site or archive the site instead."
            ),
        )
    await db.sites.delete_one({"id": site_id, "organization_id": org_id})
    return {"ok": True, "site_id": site_id, "deleted": True}


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
    # Iter 216h50 — include invoice_customer_ref so master-admin can update
    # the Sicon per-site reference without impersonating the org owner.
    # Iter 216h61 — extended editable field set (Lee's SiteDetailDrawer
    # form) so the master-admin form actually persists every cell it
    # exposes (city, county, country, phone, email, manager contacts,
    # default location and the line1/2 address breakdown).
    for field in (
        "name", "address", "postcode", "invoice_customer_ref",
        "address_line1", "address_line2", "city", "county", "country",
        "phone", "email", "site_manager_name", "site_manager_email",
        "default_location",
    ):
        if field in body:
            updates[field] = (body[field] or "").strip()
    # Iter 216h113j — MOD force tag. Sites tagged with a force show
    # up in their HQ rollup view.
    if "mod_force" in body:
        v = (body.get("mod_force") or "").strip().lower()
        if v in ("army", "raf", "navy"):
            updates["mod_force"] = v
        elif not v:
            updates["mod_force"] = None
        else:
            raise HTTPException(400, "mod_force must be one of army | raf | navy")
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
