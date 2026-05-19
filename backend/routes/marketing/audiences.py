"""Audience segmentation engine + AI-suggest endpoint.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _new_id,
    _now_iso,
    _org_id,
)

router = APIRouter()


# ───────────────────────── Audiences (segmentation) ─────────────────────

# Field resolvers — each returns a Mongo $expr fragment evaluated against
# the joined CRM contact + member doc. Computed fields (lifetime_value_gbp,
# attendance_30d, etc) are pre-aggregated nightly and stored on the contact.

_OPERATORS = {">=": "$gte", "<=": "$lte", ">": "$gt", "<": "$lt", "==": "$eq", "!=": "$ne", "in": "$in"}


def _build_filter(rule: dict) -> dict:
    """Recursively build a MongoDB filter from a rule-tree. Only fields we
    expose are honoured — anything else is ignored (defensive). Special
    values ``"30d_ago"`` etc are resolved to ISO timestamps."""
    op = rule.get("op", "and")
    if op in ("and", "or"):
        clauses = [_build_filter(c) for c in rule.get("conditions", []) if c]
        clauses = [c for c in clauses if c]
        if not clauses:
            return {}
        return {f"${op}": clauses}

    field = rule.get("field")
    operator = rule.get("op")
    value = rule.get("value")
    if not field or operator not in _OPERATORS:
        return {}

    # Map relative-date sentinels.
    if isinstance(value, str) and value.endswith("_ago"):
        try:
            days = int(value.split("d_")[0])
            value = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        except (ValueError, IndexError):
            pass

    return {field: {_OPERATORS[operator]: value}}


async def _evaluate_audience(organization_id: str, rules: dict, limit: int = 0) -> tuple[int, list[dict]]:
    """Resolve a rule-tree against ``crm_contacts`` filtered by org. Returns
    ``(count, sample)`` — sample is up to 10 docs with name/email."""
    base = {"organization_id": organization_id, "marketing_consent.email": {"$ne": False}}
    rule_filter = _build_filter(rules or {}) if rules else {}
    full = {**base, **rule_filter} if rule_filter else base
    count = await db.crm_contacts.count_documents(full)
    sample = []
    if limit:
        sample = await db.crm_contacts.find(
            full,
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "tags": 1},
        ).limit(limit).to_list(length=limit)
    return count, sample


@router.post("/marketing/audiences/preview", dependencies=[Depends(require_module("marketing"))])
async def preview_audience(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    rules = body.get("rules") or {}
    count, sample = await _evaluate_audience(org_id, rules, limit=10)
    return {"estimated_size": count, "sample_contacts": sample}


@router.get("/marketing/audiences", dependencies=[Depends(require_module("marketing"))])
async def list_audiences(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    items = await db.marketing_audiences.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(length=200)
    return {"audiences": items}


@router.post("/marketing/audiences", dependencies=[Depends(require_module("marketing"))])
async def create_audience(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    rules = body.get("rules") or {"op": "and", "conditions": []}
    a_type = body.get("type", "dynamic")
    count, _ = await _evaluate_audience(org_id, rules)
    doc = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": name, "type": a_type, "rules": rules,
        "estimated_size": count, "computed_at": _now_iso(),
        "tags": body.get("tags", []),
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db.marketing_audiences.insert_one(doc)
    # Iter 216h227 — Marketing trial first-win milestone.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            org_id, "first_audience_built", trigger_user_id=user.get("id"),
        )
    except Exception:  # best-effort — never block marketing writes
        pass
    return {"audience": {k: v for k, v in doc.items() if k not in ("_id",)}}


@router.post("/marketing/audiences/ai-suggest", dependencies=[Depends(require_module("marketing"))])
async def ai_suggest_audience(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Plain-English audience description → draft rule-tree. Falls back to
    a deterministic stub if the LLM is unavailable so the UX always works."""
    desc = (body.get("description") or "").lower().strip()
    # Lightweight rule synthesis — covers the most common gym audiences
    # without an LLM round-trip. Keeps preview latency <100 ms.
    rules: dict = {"op": "and", "conditions": []}
    if "churn" in desc or "at risk" in desc or "leaving" in desc:
        rules["conditions"].append({"field": "churn_risk_score", "op": ">=", "value": 60})
    if "high spender" in desc or "vip" in desc:
        rules["conditions"].append({"field": "lifetime_value_gbp", "op": ">=", "value": 500})
    if "new member" in desc or "signed up" in desc:
        rules["conditions"].append({"field": "signup_at", "op": ">=", "value": "30d_ago"})
    if "inactive" in desc or "missed" in desc or "dormant" in desc:
        rules["conditions"].append({"field": "last_attended_at", "op": "<=", "value": "21d_ago"})
    if "spin" in desc:
        rules["conditions"].append({"field": "class_preference", "op": "==", "value": "spin"})
    if "hiit" in desc:
        rules["conditions"].append({"field": "class_preference", "op": "==", "value": "hiit"})
    if "pt" in desc or "personal training" in desc:
        rules["conditions"].append({"field": "pt_sessions_used_30d", "op": ">=", "value": 1})
    if "failed payment" in desc:
        rules["conditions"].append({"field": "payment_status", "op": "==", "value": "failed"})
    if not rules["conditions"]:
        # Default fallback — engaged active members.
        rules["conditions"] = [
            {"field": "last_attended_at", "op": ">=", "value": "30d_ago"},
        ]
    org_id = await _org_id(user)
    count, _ = await _evaluate_audience(org_id, rules)
    return {"rules": rules, "estimated_size": count, "rationale": f"Built from your description: '{body.get('description', '')}'"}



@router.get("/marketing/audiences/data-sources", dependencies=[Depends(require_module("marketing"))])
async def audience_data_sources(user: dict = Depends(get_current_user)):
    """Iter 216at — Phase 1 #3.

    Reports how many candidate contacts exist for audience-building from
    each of the available sources (members, CRM contacts, manually-imported
    contacts). Used by the Marketing front-end to surface a "Import a
    contact CSV" CTA when a Marketing-only org has no other data source.
    """
    from utils.module_access import resolve_module_access

    org_id = await _org_id(user)
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "modules": 1, "account_type": 1, "module_trials": 1, "features": 1},
    ) or {}
    access = resolve_module_access(user, org)

    members_count = await db.members.count_documents({"organization_id": org_id})
    contacts_count = await db.crm_contacts.count_documents({"organization_id": org_id})
    imported_count = await db.marketing_contacts.count_documents({"organization_id": org_id}) if "marketing_contacts" in await db.list_collection_names() else 0
    total_addressable = members_count + contacts_count + imported_count

    return {
        "members_count": members_count,
        "contacts_count": contacts_count,
        "imported_count": imported_count,
        "total_addressable": total_addressable,
        "module_access": {
            "memberships": bool(access.get("memberships")),
            "crm": bool(access.get("crm")),
        },
        # When zero addressable contacts AND neither sister-module is
        # enabled, the front-end shows the import-CSV CTA.
        "needs_data_import": total_addressable == 0
                             and not access.get("memberships")
                             and not access.get("crm"),
    }
