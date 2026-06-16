"""Master Admin — Reset platform to a fresh test state.

Keeps:
  - Master admin user (email == admin@pulsefitness.ai)
  - Tottenham Green Leisure Centre org + ALL users belonging to it
  - Master admin's own org doc

Wipes everything else: orgs, users, equipment, issues, faults, memberships,
bookings, marketing campaigns, supplier cases, invitations, demo accounts,
audit/event logs, etc.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Body, Depends, HTTPException
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["master-admin-wipe"])

# Collections we leave untouched (config / global registries)
_KEEP_COLLECTIONS = {
    "marketing_plans",          # Plan tier pricing config
    "fail2ban",                 # rate-limit infra
    "ui_error_events",          # telemetry
    "trust_events",             # platform reliability
    "self_heal_log",
}

# Collections that key off `id` instead of `organization_id` — handled separately
_NON_ORG_SCOPED = {
    "organizations",
    "users",
    "members",
}


_PLATFORM_RESET_PHRASE = "RESET PLATFORM"


class _Counter:
    """Accumulator for delete sweeps — keeps the main handlers flat."""

    __slots__ = ("summary", "total")

    def __init__(self) -> None:
        self.summary: dict[str, int] = {}
        self.total: int = 0

    def add(self, key: str, n: int) -> None:
        if not n:
            return
        self.summary[key] = self.summary.get(key, 0) + n
        self.total += n


async def _delete(coll_name: str, query: dict, counter: _Counter, key: str | None = None) -> None:
    """Delete matching docs and record the count under ``key`` (defaults to
    the collection name)."""
    try:
        n = (await db[coll_name].delete_many(query)).deleted_count
        counter.add(key or coll_name, n)
    except Exception as exc:  # pragma: no cover — per-collection sweep safety
        logger.info("[wipe] %s skipped: %s", coll_name, exc)


async def _sweep_org_scoped(counter: _Counter, *, keep_org_ids: set[str] | None = None,
                            only_org_id: str | None = None, extra_skip: set[str] = frozenset()) -> None:
    """Iterate every non-system, non-kept collection and issue a single
    delete_many for the target scope.

    - ``keep_org_ids`` — reset-to-tottenham mode: delete docs whose
      ``organization_id`` is NOT in this set.
    - ``only_org_id`` — clear-one-org mode: delete docs whose
      ``organization_id`` equals this id.
    """
    if keep_org_ids is not None:
        query: dict = {"organization_id": {"$exists": True, "$nin": list(keep_org_ids)}}
    elif only_org_id is not None:
        query = {"organization_id": only_org_id}
    else:
        return
    skip = set(_KEEP_COLLECTIONS) | extra_skip
    for col_name in await db.list_collection_names():
        if col_name in skip or col_name.startswith("system."):
            continue
        await _delete(col_name, query, counter)


async def _resolve_platform_reset_survivors() -> tuple[set[str], set[str]]:
    """Look up Tottenham + master admin. Returns (keep_org_ids, keep_user_ids)."""
    tottenham = await db.organizations.find_one(
        {"name": {"$regex": "Tottenham", "$options": "i"}}, {"_id": 0, "id": 1},
    )
    if not tottenham:
        raise HTTPException(404, "Tottenham Green org not found — cannot reset safely")
    keep_org_ids = {tottenham["id"]}

    master = await db.users.find_one(
        {"email": "admin@pulsefitness.ai"}, {"_id": 0, "id": 1, "organization_id": 1},
    )
    if not master:
        raise HTTPException(404, "Master admin user not found — cannot reset safely")
    if master.get("organization_id"):
        keep_org_ids.add(master["organization_id"])

    keep_user_ids = {master["id"]}
    async for u in db.users.find(
        {"organization_id": {"$in": list(keep_org_ids)}}, {"_id": 0, "id": 1},
    ):
        keep_user_ids.add(u["id"])
    return keep_org_ids, keep_user_ids


@router.post("/master-admin/data-wipe/reset-to-tottenham")
async def reset_to_tottenham(body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """DESTRUCTIVE — purge every tenant except Tottenham Green + master admin.

    Body: {confirm_phrase: "RESET PLATFORM"} — required guard against accidents.
    """
    from routes.master_admin import require_gymaxis_master_only
    require_gymaxis_master_only(user)
    if body.get("confirm_phrase") != _PLATFORM_RESET_PHRASE:
        raise HTTPException(
            400,
            f"Confirmation phrase missing — body must include "
            f"{{confirm_phrase: '{_PLATFORM_RESET_PHRASE}'}}.",
        )

    keep_org_ids, keep_user_ids = await _resolve_platform_reset_survivors()
    counter = _Counter()

    # 1) Drop everything tied to a non-survivor org.
    await _sweep_org_scoped(counter, keep_org_ids=keep_org_ids, extra_skip=_NON_ORG_SCOPED)

    # 2–4) Identity + drills + assistant session noise.
    for col, q, key in (
        ("organizations", {"id": {"$nin": list(keep_org_ids)}}, "organizations"),
        ("users", {"id": {"$nin": list(keep_user_ids)}}, "users"),
        ("members", {"organization_id": {"$nin": list(keep_org_ids)}}, "members"),
        ("issues", {"is_drill": True}, "issues_drills"),
        ("assistant_action_log", {}, "assistant_action_log"),
        ("assistant_chats", {}, "assistant_chats"),
        ("onboarding_packets",
         {"organization_id": {"$nin": list(keep_org_ids) + [None]}},
         "onboarding_packets_other"),
    ):
        await _delete(col, q, counter, key)

    logger.warning(
        "[wipe] master_admin=%s reset platform — kept orgs=%s, removed=%s docs",
        user.get("email"), keep_org_ids, counter.total,
    )

    return {
        "ok": True,
        "kept_org_ids": list(keep_org_ids),
        "kept_user_ids_count": len(keep_user_ids),
        "documents_removed": counter.total,
        "by_collection": dict(sorted(counter.summary.items(), key=lambda kv: -kv[1])),
    }


async def _resolve_clear_org_survivors(
    org_id: str, body: dict,
) -> tuple[dict, list[dict]]:
    """For clear_org_data: pick the user to preserve (owner or explicit
    override email) and snapshot all sites belonging to the org."""
    keep_email = (body.get("keep_user_email") or "").strip().lower()
    if keep_email:
        keep_user_doc = await db.users.find_one(
            {"organization_id": org_id, "email": keep_email}, {"_id": 0},
        )
    else:
        keep_user_doc = await db.users.find_one(
            {"organization_id": org_id, "role": "owner"}, {"_id": 0},
        )
    if not keep_user_doc:
        raise HTTPException(404, "No owner / matching user to keep")
    keep_sites = await db.sites.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
    return keep_user_doc, keep_sites


def _check_confirm_phrase(phrase: str | None, expected: str) -> None:
    if (phrase or "").strip().lower() != expected.strip().lower():
        raise HTTPException(
            400,
            f"Confirmation phrase mismatch — body must include "
            f"{{confirm_phrase: '{expected}'}}.",
        )


@router.post("/master-admin/data-wipe/clear-org-data/{org_id}")
async def clear_org_data(org_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """DEEP-WIPE everything inside one org while preserving:
      - the organisation document itself (with branding, modules, account_type)
      - the *owner* user (or a single user picked via body.keep_user_email)
      - sites belonging to the org (so site_id stays stable for re-imports)

    Wipes equipment, issues, faults, check sheets, PPM, purchase orders,
    supplier cases, suppliers (per user request), members, memberships,
    classes, bookings, marketing campaigns/segments, gym-floor diary,
    risk assessments, gym layouts, capex, fault timelines, AI chats and
    action log entries scoped to this org, etc.

    Body: {
      confirm_phrase: "WIPE <org name>",  # case-insensitive substring match
      keep_user_email: "lee.somers@..."   # optional override; defaults to owner
    }
    """
    from routes.master_admin import require_gymaxis_master_only
    require_gymaxis_master_only(user)

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisation not found")

    org_name = org.get("name") or ""
    _check_confirm_phrase(body.get("confirm_phrase"), f"WIPE {org_name}")

    keep_user_doc, keep_site_docs = await _resolve_clear_org_survivors(org_id, body)
    counter = _Counter()

    # Sweep every org-scoped collection (skip the org doc itself).
    await _sweep_org_scoped(counter, only_org_id=org_id, extra_skip={"organizations"})

    # Restore survivors.
    await db.users.insert_one(keep_user_doc)
    if keep_site_docs:
        await db.sites.insert_many(list(keep_site_docs))

    # Global artefacts tied to this org.
    await _delete("issues", {"is_drill": True}, counter, "issues_drills")
    await _delete("assistant_chats", {"organization_id": org_id}, counter)
    await _delete("assistant_action_log", {"organization_id": org_id}, counter)

    logger.warning(
        "[clear-org] master_admin=%s cleared org=%s (%s) — kept user=%s sites=%d, removed=%d docs",
        user.get("email"), org_id, org_name,
        keep_user_doc.get("email"), len(keep_site_docs), counter.total,
    )

    return {
        "ok": True,
        "kept": {
            "org_id": org_id,
            "org_name": org_name,
            "user_email": keep_user_doc.get("email"),
            "site_ids": [s["id"] for s in keep_site_docs],
        },
        "documents_removed": counter.total,
        "by_collection": dict(sorted(counter.summary.items(), key=lambda kv: -kv[1])),
    }



__all__ = ["router"]
