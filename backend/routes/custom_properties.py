"""Custom Properties — user-facing schema editor (Iter 232).

HubSpot Parity P1 gap: operators and admins can add custom fields to
contacts/companies/deals (text/number/date/select/multi-select/boolean)
without a developer.

Storage:
  • ``custom_properties`` collection holds field definitions:
    {id, organization_id, entity_type, key, label, field_type, options[],
     required, group, sort_order, status, created_by, created_at,
     updated_at}
  • ``crm_contacts`` (and friends) gain a ``custom_fields`` map keyed by
    the property's ``key``. We never mutate the schema globally — each
    record carries only the keys it has.

What the rule builder + form builder pick up automatically:
  • The audiences/dynamic-list rule builder fetches active properties on
    mount and merges them into its FIELDS list. Field paths use Mongo
    dot-notation (``custom_fields.<key>``) so existing
    ``_build_filter`` works without modification.
  • The form builder allows mapping a form field to ``custom.<key>`` —
    the form-submission handler routes those into the contact's
    ``custom_fields`` sub-document.

Endpoints (`/api/custom-properties`):
  GET    /                       — list active props (filterable by entity_type)
  POST   /                       — create
  GET    /{id}                   — single get
  PUT    /{id}                   — update mutable fields (key + field_type frozen)
  DELETE /{id}                   — soft-archive (status=archived)
  GET    /{id}/usage             — count of records using this prop

Auth: master admin OR org owner/manager. Operators can self-serve
without a master admin in the loop.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


VALID_ENTITY_TYPES = {"contact", "company", "deal"}
VALID_FIELD_TYPES = {
    "text", "number", "date", "boolean", "select", "multi_select",
    "url", "email",
}
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
RESERVED_KEYS = {
    # Avoid collisions with first-class fields on crm_contacts.
    "id", "first_name", "last_name", "email", "phone", "company",
    "lifecycle", "owner", "tags", "marketing_consent", "created_at",
    "updated_at", "organization_id",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _require_admin_or_owner(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager"):
        return
    raise HTTPException(403, "Owner / manager / master-admin only")


async def _org_id(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(400, "User has no organization context")
    return org


def _public(prop: dict) -> dict:
    return {k: v for k, v in prop.items() if k != "_id"}


def _validate_immutables(payload: dict) -> dict:
    """Validate the create-only fields: entity_type, field_type, key."""
    entity = (payload.get("entity_type") or "").strip().lower()
    if entity not in VALID_ENTITY_TYPES:
        raise HTTPException(400, f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)}")
    ftype = (payload.get("field_type") or "").strip().lower()
    if ftype not in VALID_FIELD_TYPES:
        raise HTTPException(400, f"field_type must be one of {sorted(VALID_FIELD_TYPES)}")
    key = (payload.get("key") or "").strip().lower()
    if not KEY_PATTERN.match(key):
        raise HTTPException(400, "key must match ^[a-z][a-z0-9_]{1,40}$")
    if key in RESERVED_KEYS:
        raise HTTPException(400, f"'{key}' is reserved — pick another key")
    return {"entity_type": entity, "field_type": ftype, "key": key}


def _validate_label(payload: dict) -> str:
    label = (payload.get("label") or "").strip()
    if not label:
        raise HTTPException(400, "label is required")
    if len(label) > 80:
        raise HTTPException(400, "label too long (max 80 chars)")
    return label


def _validate_options(raw) -> list[dict]:
    if not isinstance(raw, list):
        raise HTTPException(400, "options must be an array")
    cleaned: list[dict] = []
    for o in raw:
        if isinstance(o, str):
            v = o.strip()
            if v:
                cleaned.append({"value": v, "label": v})
        elif isinstance(o, dict):
            v = (o.get("value") or "").strip()
            lbl = (o.get("label") or v).strip()
            if v:
                cleaned.append({"value": v, "label": lbl})
    if len(cleaned) > 50:
        raise HTTPException(400, "Too many options (max 50)")
    return cleaned


def _coerce_sort_order(raw) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "sort_order must be an integer") from exc


_MUTABLE_FIELD_COERCERS = (
    ("label", lambda p: _validate_label(p)),
    ("options", lambda p: _validate_options(p.get("options") or [])),
    ("required", lambda p: bool(p.get("required"))),
    ("group", lambda p: (p.get("group") or "").strip()[:60]),
    ("sort_order", lambda p: _coerce_sort_order(p.get("sort_order"))),
    ("description", lambda p: (p.get("description") or "")[:300]),
)


def _validate_payload(payload: dict, *, on_create: bool) -> dict:
    """Normalise + validate. On update, key/entity_type/field_type are
    untouchable; we just sanity-check the mutable fields."""
    out: dict = {}
    if on_create:
        out.update(_validate_immutables(payload))
    for field, coerce in _MUTABLE_FIELD_COERCERS:
        # `label` is required on create, optional otherwise.
        if field == "label":
            if on_create or "label" in payload:
                out["label"] = coerce(payload)
            continue
        if field in payload:
            out[field] = coerce(payload)
    return out


@router.get("/custom-properties")
async def list_properties(
    user: dict = Depends(get_current_user),
    entity_type: str | None = Query(None),
    include_archived: bool = Query(False),
):
    org_id = await _org_id(user)
    query: dict = {"organization_id": org_id}
    if entity_type:
        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(400, "Unknown entity_type")
        query["entity_type"] = entity_type
    if not include_archived:
        query["status"] = {"$ne": "archived"}
    rows = await db.custom_properties.find(query, {"_id": 0}).sort([
        ("entity_type", 1), ("group", 1), ("sort_order", 1), ("created_at", 1),
    ]).to_list(length=500)
    return {"properties": rows}


@router.post("/custom-properties")
async def create_property(body: dict = Body(...), user: dict = Depends(get_current_user)):
    _require_admin_or_owner(user)
    org_id = await _org_id(user)
    fields = _validate_payload(body, on_create=True)
    # Uniqueness on (org, entity_type, key) — case-insensitive via normalised key.
    existing = await db.custom_properties.find_one({
        "organization_id": org_id,
        "entity_type": fields["entity_type"],
        "key": fields["key"],
        "status": {"$ne": "archived"},
    }, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(409, f"A property with key '{fields['key']}' already exists for {fields['entity_type']}")
    doc = {
        "id": _new_id(),
        "organization_id": org_id,
        "entity_type": fields["entity_type"],
        "key": fields["key"],
        "label": fields["label"],
        "field_type": fields["field_type"],
        "options": fields.get("options", []),
        "required": fields.get("required", False),
        "group": fields.get("group", ""),
        "sort_order": fields.get("sort_order", 0),
        "description": fields.get("description", ""),
        "status": "active",
        "created_by": user["id"],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.custom_properties.insert_one(doc)
    return {"property": _public(doc)}


@router.get("/custom-properties/{prop_id}")
async def get_property(prop_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.custom_properties.find_one(
        {"id": prop_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Property not found")
    return {"property": row}


@router.put("/custom-properties/{prop_id}")
async def update_property(
    prop_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    _require_admin_or_owner(user)
    org_id = await _org_id(user)
    row = await db.custom_properties.find_one(
        {"id": prop_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Property not found")
    if row.get("status") == "archived":
        raise HTTPException(400, "Cannot edit an archived property")

    # Reject attempts to change immutable fields. (`field_type`/`key`/`entity_type`)
    for frozen in ("key", "field_type", "entity_type"):
        if frozen in body and (body[frozen] or "").strip().lower() != row[frozen]:
            raise HTTPException(400, f"'{frozen}' cannot be changed after creation")

    update = _validate_payload(body, on_create=False)
    update["updated_at"] = _now_iso()
    await db.custom_properties.update_one({"id": prop_id}, {"$set": update})
    row.update(update)
    return {"property": _public(row)}


@router.delete("/custom-properties/{prop_id}")
async def archive_property(prop_id: str, user: dict = Depends(get_current_user)):
    _require_admin_or_owner(user)
    org_id = await _org_id(user)
    res = await db.custom_properties.update_one(
        {"id": prop_id, "organization_id": org_id, "status": {"$ne": "archived"}},
        {"$set": {"status": "archived", "archived_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Property not found")
    return {"ok": True}


@router.get("/custom-properties/{prop_id}/usage")
async def property_usage(prop_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    row = await db.custom_properties.find_one(
        {"id": prop_id, "organization_id": org_id}, {"_id": 0},
    )
    if not row:
        raise HTTPException(404, "Property not found")
    coll_paths = {
        "contact": [db.crm_contacts, db.crm2_contacts],
        "company": [db.crm_companies, db.crm2_companies],
        "deal": [db.crm_deals, db.crm2_opportunities],
    }
    colls = coll_paths.get(row["entity_type"]) or []
    if not colls:
        return {"usage": 0}
    field_path = f"custom_fields.{row['key']}"
    total = 0
    for coll in colls:
        try:
            total += await coll.count_documents({
                "organization_id": org_id,
                field_path: {"$exists": True, "$ne": None},
            })
        except Exception:  # collection may not exist in a tenant
            continue
    return {"usage": total, "entity_type": row["entity_type"], "key": row["key"]}
