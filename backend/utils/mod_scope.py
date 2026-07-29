"""Iter 216h120 — MOD HQ query scope helper.

MOD child sites are full organisations in their own right
(`account_type=mod_site`), with their own equipment / issues stored
under that child's `organization_id` and **no** `site_id` field. The
HQ tiers (`mod_org`, `mod_branch`) need to:

  • Drill into a single child gym (Helles Barracks Gym) → query that
    child org's data even though the HQ user's JWT carries the
    parent HQ org id.
  • Roll the whole estate up for "All Operations Sites" → query
    every child sharing the HQ's `mod_root_id` (and `mod_branch` for
    branch-tier users).

The legacy `get_organization_filter` + `apply_site_lock` pair only
knows about the user's own `organization_id`, so for any MOD HQ user
both flows returned zero rows. This helper closes that gap.

Usage from a route handler:

    @router.get("/equipment")
    async def list_equipment(user=Depends(get_current_user),
                             site_id: str | None = None):
        org_filter = await resolve_mod_query_filter(user, site_id)
        equipment = await db.equipment.find(org_filter, {"_id": 0})...

For non-MOD users it returns exactly what `get_organization_filter`
would have, with site-lock applied. For MOD HQ users it returns:

  • requested_site_id is a child gym       → {"organization_id": child_id}
  • requested_site_id is the HQ org itself → {"organization_id": hq_id}
                                              (HQ users at HQ scope see
                                              the HQ's own data — usually
                                              empty, but not cross-tenant
                                              data)
  • requested_site_id is None              → {"organization_id":
                                              {"$in": [hq_id, *child_ids]}}
"""
from __future__ import annotations

from fastapi import HTTPException

from utils.auth import get_organization_filter
from utils.site_scope import build_site_filter, get_request_site_scope
from utils.database import db


async def _mod_child_org_ids(user: dict) -> list[str]:
    """Return the org ids of every `mod_site` the caller can see.

    For `mod_site` users this is just their own org. For `mod_branch`
    users it's every site sharing their branch under the same root.
    For `mod_org` users it's every site under their root regardless
    of branch.
    """
    at = (user.get("account_type") or "").lower()
    org_id = user.get("organization_id")
    if at == "mod_site":
        return [org_id] if org_id else []
    if at not in ("mod_org", "mod_branch"):
        return []
    hq = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "mod_force": 1, "mod_branch": 1, "mod_root_id": 1, "id": 1},
    ) or {}
    mod_root_id = hq.get("mod_root_id") or hq.get("id") or org_id
    child_query: dict = {
        "account_type": "mod_site",
        "is_mod": True,
        "status": {"$ne": "archived"},
        "mod_root_id": mod_root_id,
    }
    if at == "mod_branch" and hq.get("mod_branch"):
        child_query["mod_branch"] = hq["mod_branch"]
    cursor = db.organizations.find(child_query, {"_id": 0, "id": 1})
    return [c["id"] async for c in cursor]


def _is_mod_hq(user: dict) -> bool:
    return (user.get("account_type") or "").lower() in ("mod_org", "mod_branch")


async def resolve_mod_query_filter(
    user: dict,
    requested_site_id: str | None = None,
    *,
    extra: dict | None = None,
) -> dict:
    """Return a Mongo filter scoped to what the caller should see.

    MOD-aware: rebinds to the child mod_site org when the caller is
    an HQ user drilling into one site, OR fans out across every child
    when no specific site is requested.

    `extra` — optional dict whose keys are merged into the final
    filter (e.g. {"status": {"$in": [...]}}).
    """
    base = dict(extra or {})

    if not _is_mod_hq(user):
        # ── Non-MOD-HQ path (Pulse Pro, Lite, full, mod_site, etc.) ──
        # Iter 2026-07 — unified onto the ContextVar site-scope engine
        # (utils.site_scope.build_site_filter), the SAME engine used by
        # Memberships/CRM/Marketing. This retires the legacy
        # apply_site_lock for Operations: managers with a non-empty
        # allowed_site_ids are now correctly restricted here too, and a
        # restricted user requesting a disallowed site gets 403
        # site_access_denied. The per-request scope is stamped by
        # utils.auth.get_current_user.
        f = get_organization_filter(user)
        site_filter = build_site_filter(requested_site_id)
        # Guard (2026-07): build_site_filter does NOT verify org-membership for
        # an UNRESTRICTED user — it happily returns {"site_id": X} for any id.
        # If a stale / foreign / cross-org site_id leaks in (e.g. inherited from
        # a master-admin impersonation switch), the query then returns ZERO rows
        # and equipment/faults silently "disappear". Treat a site_id that does
        # NOT belong to the caller's org as "all sites" instead of an empty set.
        # Restricted users are untouched: build_site_filter already 403s them
        # for a disallowed site, and we must never widen their scope here.
        requested = (requested_site_id or "").strip()
        if requested and site_filter.get("site_id") == requested:
            scope = get_request_site_scope()
            org_id = user.get("organization_id")
            if not scope.restricted and org_id:
                belongs = await db.sites.find_one(
                    {"organization_id": org_id, "id": requested},
                    {"_id": 0, "id": 1},
                )
                if not belongs:
                    site_filter = {}
        return {**f, **base, **site_filter}

    # ── MOD HQ path ──
    child_ids = await _mod_child_org_ids(user)
    hq_org_id = user.get("organization_id")

    if requested_site_id:
        # Strictly drill into one site, regardless of whether it's a
        # child gym, the HQ itself, or an unrelated org (in which case
        # we 403 to avoid cross-tenant leak).
        if requested_site_id == hq_org_id:
            return {"organization_id": hq_org_id, **base}
        if requested_site_id in child_ids:
            return {"organization_id": requested_site_id, **base}
        raise HTTPException(
            status_code=403,
            detail="You do not have access to that site",
        )

    # No specific site — return the collective rollup of HQ + all children.
    all_ids = ([hq_org_id] if hq_org_id else []) + child_ids
    if not all_ids:
        # Defensive fallback: never return an unfiltered query.
        return {"organization_id": "__none__", **base}
    return {"organization_id": {"$in": all_ids}, **base}


__all__ = ["resolve_mod_query_filter"]
