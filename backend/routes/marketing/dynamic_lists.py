"""Active Dynamic Lists — auto-refreshing audience segments (Iter 229).

Closes a HubSpot Parity P1 gap: HubSpot ships "active lists" that
auto-refresh as contacts change. Audiences in our existing
`marketing_audiences` collection are static-by-design (size snapshotted
at create time). Dynamic lists are different: they have a TTL (default
1h) and re-evaluate on access if stale, plus optionally on every fresh
write to ``crm_contacts`` (we use a periodic scan, not a watch stream,
so we stay multi-replica safe).

Why this matters for users:
  • Marketing flows can gate steps on "is contact in list X" — without
    auto-refresh, the gate is point-in-time and the journey leaks.
  • A salesperson can save a "Recently engaged" list and the count
    updates without anyone re-running it.

Storage:
  ``marketing_dynamic_lists`` — one row per saved list:
  {id, organization_id, name, description, rules, refresh_interval_minutes,
   member_ids[], member_count, last_evaluated_at, last_evaluation_ms,
   created_by, created_at, updated_at}

Endpoints (all `/api/marketing/dynamic-lists`, marketing-module-gated):
  GET    /                 — list all (auto-refreshes any stale rows)
  POST   /                 — create new list + immediate evaluation
  GET    /{id}             — fetch single
  PUT    /{id}             — update name/rules/refresh_interval
  DELETE /{id}             — hard-delete
  POST   /{id}/refresh     — force re-evaluation NOW
  GET    /{id}/members     — paginated members (page=1, page_size=50)
  GET    /{id}/contains/{contact_id} — boolean membership check (used
    by Journeys to gate steps)
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.audiences import _build_filter
from routes.marketing.helpers import _new_id, _now_iso, _org_id, logger

router = APIRouter()


_DEFAULT_REFRESH_MIN = 60  # 1h
_MIN_REFRESH_MIN = 5
_MAX_REFRESH_MIN = 1440  # 24h
_MAX_MEMBERS_CACHED = 50_000


def _is_stale(row: dict) -> bool:
    last = row.get("last_evaluated_at")
    if not last:
        return True
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    interval = int(row.get("refresh_interval_minutes") or _DEFAULT_REFRESH_MIN)
    age_s = (datetime.now(timezone.utc) - dt).total_seconds()
    return age_s >= interval * 60


async def _evaluate(org_id: str, rules: dict) -> tuple[list[str], int]:
    """Return ``(member_ids, total_count)`` for the rule-tree. We cache up
    to ``_MAX_MEMBERS_CACHED`` ids — after that, the count remains accurate
    but membership-checks fall back to a live count_documents call."""
    base = {"organization_id": org_id, "marketing_consent.email": {"$ne": False}}
    rule_filter = _build_filter(rules or {}) if rules else {}
    full = {**base, **rule_filter} if rule_filter else base
    total = await db.crm_contacts.count_documents(full)
    cur = db.crm_contacts.find(full, {"_id": 0, "id": 1}).limit(_MAX_MEMBERS_CACHED)
    ids = [d["id"] async for d in cur if d.get("id")]
    return ids, total


async def _refresh_row(row: dict) -> dict:
    """Mutate the row in place + persist the new evaluation."""
    started = time.perf_counter()
    member_ids, total = await _evaluate(row["organization_id"], row.get("rules") or {})
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    update = {
        "member_ids": member_ids,
        "member_count": total,
        "last_evaluated_at": _now_iso(),
        "last_evaluation_ms": elapsed_ms,
        "updated_at": _now_iso(),
    }
    await db.marketing_dynamic_lists.update_one({"id": row["id"]}, {"$set": update})
    row.update(update)
    return row


def _public(row: dict) -> dict:
    """Strip the heavy member_ids array for list responses."""
    return {k: v for k, v in row.items() if k not in ("_id", "member_ids")}


def _validate_refresh_interval(value) -> int:
    try:
        interval = int(value or _DEFAULT_REFRESH_MIN)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "refresh_interval_minutes must be an integer") from exc
    if interval < _MIN_REFRESH_MIN or interval > _MAX_REFRESH_MIN:
        raise HTTPException(
            400,
            f"refresh_interval_minutes must be between {_MIN_REFRESH_MIN} and {_MAX_REFRESH_MIN}",
        )
    return interval


@router.get("/marketing/dynamic-lists", dependencies=[Depends(require_module("marketing"))])
async def list_dynamic_lists(
    user: dict = Depends(get_current_user),
    refresh_stale: bool = Query(True, description="Auto-refresh stale rows on read"),
):
    org_id = await _org_id(user)
    rows = await db.marketing_dynamic_lists.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=200)
    refreshed = 0
    if refresh_stale:
        for row in rows:
            if _is_stale(row):
                try:
                    await _refresh_row(row)
                    refreshed += 1
                except Exception as exc:  # pragma: no cover
                    logger.info("[dynamic_lists] refresh failed for %s: %s", row.get("id"), exc)
    return {
        "lists": [_public(r) for r in rows],
        "refreshed_count": refreshed,
    }


@router.post("/marketing/dynamic-lists", dependencies=[Depends(require_module("marketing"))])
async def create_dynamic_list(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    rules = body.get("rules") or {"op": "and", "conditions": []}
    interval = _validate_refresh_interval(body.get("refresh_interval_minutes"))
    doc = {
        "id": _new_id(),
        "organization_id": org_id,
        "created_by": user["id"],
        "name": name,
        "description": (body.get("description") or "").strip(),
        "rules": rules,
        "refresh_interval_minutes": interval,
        "member_ids": [],
        "member_count": 0,
        "last_evaluated_at": None,
        "last_evaluation_ms": 0,
        "tags": body.get("tags") or [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.marketing_dynamic_lists.insert_one(doc)
    await _refresh_row(doc)
    return {"list": _public(doc)}


@router.get("/marketing/dynamic-lists/{list_id}", dependencies=[Depends(require_module("marketing"))])
async def get_dynamic_list(list_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.marketing_dynamic_lists.find_one(
        {"id": list_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "List not found")
    if _is_stale(row):
        await _refresh_row(row)
    return {"list": _public(row)}


@router.put("/marketing/dynamic-lists/{list_id}", dependencies=[Depends(require_module("marketing"))])
async def update_dynamic_list(
    list_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    row = await db.marketing_dynamic_lists.find_one(
        {"id": list_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "List not found")
    update: dict = {"updated_at": _now_iso()}
    rules_changed = False
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Name cannot be empty")
        update["name"] = name
    if "description" in body:
        update["description"] = (body.get("description") or "").strip()
    if "rules" in body:
        update["rules"] = body.get("rules") or {"op": "and", "conditions": []}
        rules_changed = True
    if "refresh_interval_minutes" in body:
        update["refresh_interval_minutes"] = _validate_refresh_interval(
            body.get("refresh_interval_minutes"),
        )
    if "tags" in body:
        update["tags"] = body.get("tags") or []
    await db.marketing_dynamic_lists.update_one({"id": list_id}, {"$set": update})
    row.update(update)
    if rules_changed:
        await _refresh_row(row)
    return {"list": _public(row)}


@router.delete("/marketing/dynamic-lists/{list_id}", dependencies=[Depends(require_module("marketing"))])
async def delete_dynamic_list(list_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    res = await db.marketing_dynamic_lists.delete_one(
        {"id": list_id, "organization_id": org_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "List not found")
    return {"ok": True}


@router.post(
    "/marketing/dynamic-lists/{list_id}/refresh",
    dependencies=[Depends(require_module("marketing"))],
)
async def refresh_dynamic_list(list_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.marketing_dynamic_lists.find_one(
        {"id": list_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "List not found")
    await _refresh_row(row)
    return {"list": _public(row)}


@router.get(
    "/marketing/dynamic-lists/{list_id}/members",
    dependencies=[Depends(require_module("marketing"))],
)
async def list_dynamic_list_members(
    list_id: str,
    user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    org_id = await _org_id(user)
    row = await db.marketing_dynamic_lists.find_one(
        {"id": list_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "List not found")
    if _is_stale(row):
        await _refresh_row(row)
    ids = row.get("member_ids") or []
    total = row.get("member_count") or 0
    start = (page - 1) * page_size
    page_ids = ids[start:start + page_size]
    contacts = []
    if page_ids:
        contacts = await db.crm_contacts.find(
            {"organization_id": org_id, "id": {"$in": page_ids}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "tags": 1, "lifecycle": 1},
        ).to_list(length=page_size)
    return {
        "members": contacts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "cached_total": len(ids),
    }


@router.get(
    "/marketing/dynamic-lists/{list_id}/contains/{contact_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def check_membership(
    list_id: str, contact_id: str, user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    row = await db.marketing_dynamic_lists.find_one(
        {"id": list_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "List not found")
    if _is_stale(row):
        await _refresh_row(row)
    member_ids = row.get("member_ids") or []
    contains = contact_id in member_ids
    return {"list_id": list_id, "contact_id": contact_id, "contains": contains}
