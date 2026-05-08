"""Journey builder visual canvas (CRUD + dispatch).

Iter 233 — Omni-channel dispatch. The CRUD path is unchanged; we add:
  • POST /journeys/{id}/test-send — synchronously dispatch every leaf
    node (send_email/send_sms/send_push/send_in_app) of a journey to a
    chosen contact. Skips wait/branch nodes; this is deliberately a
    "preview" of how the journey will deliver, not the production
    runtime (which still requires a scheduler).
  • POST /journeys/{id}/enrol — record an enrolment + dispatch the
    eligible leaf nodes for THIS contact, recording a journey_run row.
  • GET  /journeys/{id}/runs — recent enrolments for the journey
    (delivery breakdown by channel).
"""
from __future__ import annotations


from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.omnichannel import dispatch_step

from routes.marketing.helpers import (
    _get_entitlement,
    _new_id,
    _now_iso,
    _org_id,
    _require_feature,
)

router = APIRouter()


_LEAF_NODE_TYPES = {"send_email", "send_sms", "send_push", "send_in_app"}


# ───────────────────────── Journeys (visual canvas) ─────────────────────

@router.get("/marketing/journeys", dependencies=[Depends(require_module("marketing"))])
async def list_journeys(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    items = await db.marketing_journeys.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=100)
    return {"journeys": items}


@router.post("/marketing/journeys", dependencies=[Depends(require_module("marketing"))])
async def upsert_journey(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    entitlement = await _get_entitlement(user)
    _require_feature(entitlement, "journeys")
    j_id = body.get("id") or _new_id()
    doc = {
        "id": j_id, "organization_id": org_id,
        "name": (body.get("name") or "Untitled Journey").strip(),
        "status": body.get("status", "draft"),
        "trigger": body.get("trigger") or {"event": "member_signed_up"},
        "nodes": body.get("nodes") or [],
        "edges": body.get("edges") or [],
        "ai_optimisation": body.get("ai_optimisation") or {},
        "metrics": {"entered": 0, "completed": 0, "converted": 0, "revenue_gbp": 0},
        "updated_at": _now_iso(),
    }
    existing = await db.marketing_journeys.find_one({"id": j_id, "organization_id": org_id}, {"_id": 0, "created_at": 1})
    if existing:
        doc["created_at"] = existing.get("created_at")
        await db.marketing_journeys.update_one({"id": j_id}, {"$set": doc})
    else:
        doc["created_at"] = _now_iso()
        await db.marketing_journeys.insert_one(doc)
    return {"journey": {k: v for k, v in doc.items() if k != "_id"}}


# ───────────────────────── Dispatch ─────────────────────


async def _resolve_contact(org_id: str, contact_id: str) -> dict:
    contact = await db.crm_contacts.find_one(
        {"organization_id": org_id, "id": contact_id},
        {"_id": 0},
    )
    if not contact:
        raise HTTPException(404, f"Contact '{contact_id}' not found in this org")
    return contact


async def _dispatch_leaves(
    *, journey: dict, contact: dict, run_id: str,
) -> list[dict]:
    """Walk the journey nodes in order and dispatch every leaf
    (delivery) node. Wait/branch/tag/notify_staff nodes are recorded as
    skipped so the run row reflects the actual node-traversal."""
    org_id = journey["organization_id"]
    journey_id = journey["id"]
    history: list[dict] = []
    for node in journey.get("nodes") or []:
        ntype = (node.get("type") or "").lower()
        if ntype not in _LEAF_NODE_TYPES:
            history.append({
                "node_id": node.get("id"),
                "type": ntype,
                "status": "skipped_in_test",
                "at": _now_iso(),
            })
            continue
        result = await dispatch_step(
            organization_id=org_id, contact=contact, node=node,
            journey_id=journey_id, journey_run_id=run_id,
        )
        history.append({
            "node_id": node.get("id"),
            "type": ntype,
            "status": "sent" if result.ok else "failed",
            "channel": result.channel,
            "provider": result.provider,
            "message_id": result.message_id,
            "error": result.error,
            "at": _now_iso(),
        })
    return history


@router.post(
    "/marketing/journeys/{journey_id}/test-send",
    dependencies=[Depends(require_module("marketing"))],
)
async def test_send_journey(
    journey_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Dispatch all leaf nodes of a journey to a single contact NOW —
    skipping waits, branches and admin-only nodes. Used by the operator
    to preview omni-channel delivery before going live."""
    org_id = await _org_id(user)
    journey = await db.marketing_journeys.find_one(
        {"id": journey_id, "organization_id": org_id}, {"_id": 0},
    )
    if not journey:
        raise HTTPException(404, "Journey not found")
    contact_id = (body.get("contact_id") or "").strip()
    if not contact_id:
        raise HTTPException(400, "contact_id is required")
    contact = await _resolve_contact(org_id, contact_id)
    run_id = _new_id()
    history = await _dispatch_leaves(
        journey=journey, contact=contact, run_id=run_id,
    )
    await db.marketing_journey_runs.insert_one({
        "id": run_id, "organization_id": org_id, "journey_id": journey_id,
        "contact_id": contact_id, "mode": "test_send",
        "history": history, "started_at": _now_iso(),
        "completed_at": _now_iso(),
        "triggered_by": user["id"],
    })
    sent = sum(1 for h in history if h.get("status") == "sent")
    failed = sum(1 for h in history if h.get("status") == "failed")
    skipped = sum(1 for h in history if h.get("status") == "skipped_in_test")
    return {
        "ok": True, "run_id": run_id, "sent": sent, "failed": failed,
        "skipped": skipped, "history": history,
    }


@router.post(
    "/marketing/journeys/{journey_id}/enrol",
    dependencies=[Depends(require_module("marketing"))],
)
async def enrol_into_journey(
    journey_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Production-mode enrolment. Same dispatcher as test-send — but
    records the run with mode='live' so it shows up in the journey's
    enrolment dashboard. Wait nodes are still skipped at this MVP layer
    pending the scheduler; the run is marked accordingly."""
    org_id = await _org_id(user)
    journey = await db.marketing_journeys.find_one(
        {"id": journey_id, "organization_id": org_id}, {"_id": 0},
    )
    if not journey:
        raise HTTPException(404, "Journey not found")
    contact_id = (body.get("contact_id") or "").strip()
    if not contact_id:
        raise HTTPException(400, "contact_id is required")
    contact = await _resolve_contact(org_id, contact_id)
    run_id = _new_id()
    history = await _dispatch_leaves(
        journey=journey, contact=contact, run_id=run_id,
    )
    await db.marketing_journey_runs.insert_one({
        "id": run_id, "organization_id": org_id, "journey_id": journey_id,
        "contact_id": contact_id, "mode": "live",
        "history": history, "started_at": _now_iso(),
        "completed_at": _now_iso(),
        "triggered_by": user["id"],
    })
    await db.marketing_journeys.update_one(
        {"id": journey_id}, {"$inc": {"metrics.entered": 1}},
    )
    return {"ok": True, "run_id": run_id, "history": history}


@router.get(
    "/marketing/journeys/{journey_id}/runs",
    dependencies=[Depends(require_module("marketing"))],
)
async def list_journey_runs(
    journey_id: str, user: dict = Depends(get_current_user),
):
    """Recent runs + per-channel delivery breakdown."""
    org_id = await _org_id(user)
    journey = await db.marketing_journeys.find_one(
        {"id": journey_id, "organization_id": org_id}, {"_id": 0, "id": 1},
    )
    if not journey:
        raise HTTPException(404, "Journey not found")
    runs = await db.marketing_journey_runs.find(
        {"organization_id": org_id, "journey_id": journey_id}, {"_id": 0},
    ).sort("started_at", -1).limit(50).to_list(length=50)

    # Roll-up per channel
    by_channel: dict[str, dict[str, int]] = {}
    for r in runs:
        for h in r.get("history") or []:
            ch = h.get("channel") or h.get("type") or "unknown"
            bucket = by_channel.setdefault(ch, {"sent": 0, "failed": 0, "skipped": 0})
            status = h.get("status") or ""
            if status in bucket:
                bucket[status] += 1
            elif status.startswith("skipped"):
                bucket["skipped"] += 1
    return {"runs": runs, "by_channel": by_channel}
