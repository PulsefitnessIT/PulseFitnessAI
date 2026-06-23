"""Pulse Fitness AI — Comms audience segmentation (Phase 2).

A unified, saved/dynamic segment builder that works across data sources
(marketing/CRM contacts and gym members) using the SAME rule-tree engine
the marketing dynamic-lists already use (``_build_filter``) — no second
rules language. Dynamic segments re-evaluate on read; saved segments keep
their last count. Segments are stored once in ``comms_segments`` and can
be targeted by any campaign in the shared engine.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from routes.marketing.audiences import _build_filter
from routes.marketing.helpers import _new_id, _now_iso, _org_id, logger
from routes.comms import _ANY_COMMS_MODULE

router = APIRouter(prefix="/comms")

# source → (collection, base filter builder, projection for samples)
_SOURCES = {
    "contacts": {
        "label": "CRM / Marketing contacts", "collection": "crm_contacts",
        "base": lambda org: {"organization_id": org, "marketing_consent.email": {"$ne": False}},
        "proj": {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "lifecycle": 1, "tags": 1},
    },
    "members": {
        "label": "Gym members", "collection": "members",
        "base": lambda org: {"organization_id": org},
        "proj": {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "status": 1, "plan_id": 1},
    },
}

# Operators the rule engine supports (mirrors marketing audiences).
_OPERATORS = [
    {"id": "==", "label": "is"}, {"id": "!=", "label": "is not"},
    {"id": ">=", "label": "on/after (or ≥)"}, {"id": "<=", "label": "on/before (or ≤)"},
    {"id": ">", "label": "greater than"}, {"id": "<", "label": "less than"},
    {"id": "in", "label": "is any of"},
]

# Field catalogue per source for the builder UI. `kind` drives the input.
_FIELDS = {
    "contacts": [
        {"field": "lifecycle", "label": "Lifecycle stage", "kind": "select",
         "options": ["lead", "marketing_qualified", "sales_qualified", "customer", "evangelist", "other"]},
        {"field": "tags", "label": "Tag", "kind": "tag"},
        {"field": "country", "label": "Country", "kind": "text"},
        {"field": "company_id", "label": "Company", "kind": "text"},
        {"field": "created_at", "label": "Created date", "kind": "date"},
        {"field": "source", "label": "Source", "kind": "text"},
    ],
    "members": [
        {"field": "status", "label": "Membership status", "kind": "select",
         "options": ["active", "lapsed", "frozen", "cancelled", "pending_invite", "trial"]},
        {"field": "plan_id", "label": "Plan", "kind": "text"},
        {"field": "credits_remaining", "label": "Credits remaining", "kind": "number"},
        {"field": "created_at", "label": "Joined date", "kind": "date"},
        {"field": "country", "label": "Country", "kind": "text"},
    ],
}


async def _evaluate(org_id: str, source: str, rules: dict, sample: int = 5):
    src = _SOURCES.get(source)
    if not src:
        raise HTTPException(400, f"Unknown source '{source}'")
    base = src["base"](org_id)
    rule_filter = _build_filter(rules or {}) if rules else {}
    full = {**base, **rule_filter} if rule_filter else base
    coll = getattr(db, src["collection"])
    count = await coll.count_documents(full)
    docs = []
    if sample:
        docs = await coll.find(full, src["proj"]).limit(sample).to_list(length=sample)
    return count, docs


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "_id"}


@router.get("/segments/fields", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def segment_fields(user: dict = Depends(get_current_user)):
    return {
        "sources": [{"id": k, "label": v["label"]} for k, v in _SOURCES.items()],
        "fields": _FIELDS,
        "operators": _OPERATORS,
        "date_sentinels": ["7d_ago", "30d_ago", "60d_ago", "90d_ago", "180d_ago", "365d_ago"],
    }


@router.post("/segments/preview", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def preview_segment(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    count, docs = await _evaluate(org_id, body.get("source", "contacts"), body.get("rules"), sample=8)
    return {"count": count, "sample": docs}


@router.get("/segments", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def list_segments(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    rows = await db.comms_segments.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(length=300)
    # refresh dynamic counts cheaply
    for r in rows:
        if r.get("type") == "dynamic":
            try:
                r["member_count"], _ = await _evaluate(org_id, r.get("source", "contacts"), r.get("rules"), sample=0)
            except Exception as exc:  # pragma: no cover
                logger.info("[comms-seg] refresh failed %s: %s", r.get("id"), exc)
    return {"segments": rows}


@router.post("/segments", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def create_segment(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Segment name is required")
    source = body.get("source", "contacts")
    if source not in _SOURCES:
        raise HTTPException(400, "Unknown source")
    rules = body.get("rules") or {"op": "and", "conditions": []}
    count, sample = await _evaluate(org_id, source, rules, sample=5)
    doc = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": name[:140], "description": (body.get("description") or "").strip()[:300],
        "source": source, "type": body.get("type", "dynamic"),
        "rules": rules, "member_count": count, "sample": sample,
        "last_evaluated_at": _now_iso(), "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db.comms_segments.insert_one(doc)
    return {"segment": _public(doc)}


@router.get("/segments/{segment_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def get_segment(segment_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.comms_segments.find_one({"id": segment_id, "organization_id": org_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Segment not found")
    if row.get("type") == "dynamic":
        row["member_count"], row["sample"] = await _evaluate(org_id, row.get("source", "contacts"), row.get("rules"), sample=8)
    return {"segment": row}


@router.put("/segments/{segment_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def update_segment(segment_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.comms_segments.find_one({"id": segment_id, "organization_id": org_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Segment not found")
    upd: dict = {"updated_at": _now_iso()}
    for k in ("name", "description", "source", "type", "rules"):
        if k in body:
            upd[k] = body[k]
    source = upd.get("source", row.get("source", "contacts"))
    rules = upd.get("rules", row.get("rules"))
    count, sample = await _evaluate(org_id, source, rules, sample=5)
    upd["member_count"] = count
    upd["sample"] = sample
    upd["last_evaluated_at"] = _now_iso()
    await db.comms_segments.update_one({"id": segment_id, "organization_id": org_id}, {"$set": upd})
    row.update(upd)
    return {"segment": _public(row)}


@router.delete("/segments/{segment_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def delete_segment(segment_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    res = await db.comms_segments.delete_one({"id": segment_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Segment not found")
    return {"ok": True}


@router.post("/segments/ai-suggest", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_suggest_segment(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    desc = (body.get("description") or "").strip()
    if not desc:
        raise HTTPException(400, "Describe the audience you want")
    from utils import comms_ai
    catalogue = {"sources": list(_SOURCES.keys()), "fields": _FIELDS,
                 "operators": [o["id"] for o in _OPERATORS],
                 "date_sentinels": ["7d_ago", "30d_ago", "60d_ago", "90d_ago", "180d_ago", "365d_ago"]}
    sug = await comms_ai.suggest_segment(desc, catalogue)
    if not sug:
        raise HTTPException(503, "AI assistant is unavailable right now. Please try again.")
    source = sug.get("source") if sug.get("source") in _SOURCES else "contacts"
    valid_fields = {f["field"] for f in _FIELDS[source]}
    valid_ops = {o["id"] for o in _OPERATORS}
    conditions = [
        c for c in (sug.get("rules", {}).get("conditions") or [])
        if c.get("field") in valid_fields and c.get("op") in valid_ops and c.get("value") not in (None, "")
    ]
    rules = {"op": sug.get("rules", {}).get("op", "and") if sug.get("rules", {}).get("op") in ("and", "or") else "and",
             "conditions": conditions}
    count, sample = await _evaluate(org_id, source, rules, sample=8)
    return {"name": sug.get("name", "AI segment"), "source": source, "rules": rules,
            "count": count, "sample": sample}
async def segment_members(
    segment_id: str, limit: int = Query(50, ge=1, le=500), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    row = await db.comms_segments.find_one({"id": segment_id, "organization_id": org_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Segment not found")
    count, docs = await _evaluate(org_id, row.get("source", "contacts"), row.get("rules"), sample=limit)
    return {"members": docs, "total": count}
