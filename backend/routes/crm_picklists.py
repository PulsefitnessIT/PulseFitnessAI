"""CRM · Picklists (Iter 216h223).

Centralised, editable picklists for CRM dropdowns that today are either
free-text inputs (`job_title`, `industry`, `lead_source`, `lost_reason`)
or constants buried in module code (`case_type`, `contact_role`,
`opportunity_type`).

Why this module:
  • Free-text → dirty data ("VP", "V.P.", "Vice-President" → 3 rows
    instead of 1). Picklists guide users toward a canonical value
    while still allowing admin-managed additions without code changes.
  • Master Admin owns the *global defaults* so every tenant starts
    with a sensible vocabulary (and reporting comparisons across
    tenants stay clean). Each tenant can then *extend* the global
    list with their own org-specific values.

Data model (single collection `crm_picklists`):
  {
    id: uuid,
    key: "job_title" | "industry" | "lead_source" | ...,
    label: "Sales Executive",
    organization_id: <uuid> | null,    # null = global default
    sort_order: int,
    deprecated: bool,                  # soft-delete: hidden in new
                                       # forms but preserved on
                                       # existing records
    created_at, created_by,
    updated_at,
  }

Read API:
  GET /crm/picklists                            list all keys + counts
  GET /crm/picklists/{key}                      list values for one key
                                                (global + org-specific
                                                merged, deprecated
                                                filtered out)

Write API (master_admin OR crm_admin for their own org):
  POST   /crm/picklists/{key}                  create a value
  PATCH  /crm/picklists/{key}/{value_id}       rename / sort / deprecate
  DELETE /crm/picklists/{key}/{value_id}       hard-delete (only allowed
                                                if the value isn't
                                                referenced anywhere)

Used by:
  • Settings → Picklists admin panel (CRMSettings.js → Picklists tab).
  • Contact create/edit (`job_title`).
  • Company create/edit (`industry`).
  • Opportunity create (`lead_source`, `opportunity_type`).
  • Opportunity lost (`lost_reason`).
  • Case create (`case_type`).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/picklists", tags=["CRM Picklists"])


# ── Supported picklist keys ────────────────────────────────────────
#
# Adding a new key here is the only code change needed to unlock a new
# picklist surface in the UI. Each key declares its UI-friendly label
# and the global defaults seeded on first boot.
PICKLIST_KEYS: dict[str, dict] = {
    "job_title": {
        "label": "Job Title",
        "scope": "contact",
        "defaults": [
            "CEO", "Managing Director", "Operations Director",
            "Sales Director", "Marketing Director", "Finance Director",
            "General Manager", "Operations Manager", "Sales Manager",
            "Marketing Manager", "Facility Manager", "Club Manager",
            "Personal Trainer", "Coach", "Receptionist", "Administrator",
            "Procurement", "Buyer", "Owner", "Other",
        ],
    },
    "industry": {
        "label": "Industry",
        "scope": "company",
        "defaults": [
            "Health & Fitness", "Hotel & Hospitality", "Education",
            "Healthcare", "Corporate Wellness", "Local Authority",
            "Defence & Public Sector", "Sports Club",
            "Residential / Property", "Spa & Wellness", "Other",
        ],
    },
    "lead_source": {
        "label": "Lead Source",
        "scope": "opportunity",
        "defaults": [
            "Inbound Website", "Referral", "LinkedIn", "Outbound Call",
            "Outbound Email", "Trade Show", "Partner", "Existing Customer",
            "Tender", "Inbound Phone", "Other",
        ],
    },
    "opportunity_type": {
        "label": "Opportunity Type",
        "scope": "opportunity",
        "defaults": [
            "New Business", "Renewal", "Upsell", "Cross-sell",
            "Replacement", "Service Contract", "Tender / RFP",
        ],
    },
    "lost_reason": {
        "label": "Lost Reason",
        "scope": "opportunity",
        "defaults": [
            "Price", "Competitor won", "No budget", "Timing",
            "No decision", "Lost to incumbent", "Cancelled project",
            "No fit", "Lost — no response", "Other",
        ],
    },
    "case_type": {
        "label": "Case Type",
        "scope": "case",
        "defaults": [
            "Equipment fault", "Installation issue", "Warranty claim",
            "Service request", "Complaint", "Account query",
            "Sales enquiry", "Other",
        ],
    },
    "contact_role": {
        "label": "Contact Role",
        "scope": "contact",
        "defaults": [
            "Primary contact", "Billing contact", "Operations contact",
            "Technical contact", "Site contact", "Procurement contact",
            "Other",
        ],
    },
    "department": {
        "label": "Department",
        "scope": "contact",
        "defaults": [
            "Executive", "Sales", "Marketing", "Operations",
            "Finance", "IT", "HR", "Procurement", "Facilities", "Other",
        ],
    },
    # Iter 220bs — Tender lifecycle picklists. Replaces the hard-coded
    # TENDER_STATUSES list in crm_v2.py so operators can extend the
    # workflow without a code change.
    "tender_status": {
        "label": "Tender Status",
        "scope": "tender",
        "defaults": [
            "Draft", "Parsing", "In Progress", "Internal Review",
            "Submitted", "Awarded", "Lost", "Withdrawn",
        ],
    },
    "tender_outcome_reason": {
        "label": "Tender Outcome Reason",
        "scope": "tender",
        "defaults": [
            "Best technical answer", "Best commercial answer",
            "Incumbent advantage", "Lost — price", "Lost — technical",
            "Lost — relationship", "Lost — no decision",
            "Withdrew — no fit", "Other",
        ],
    },
}


# ── Helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_master(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("is_pulse_admin"))


def _can_write(user: dict, organization_id: str | None) -> bool:
    """Master admins can write globally (organization_id=null) and to
    any org. Non-master admins can only write their own org's values.
    """
    if _is_master(user):
        return True
    if organization_id is None:
        return False  # only master admin owns global defaults
    return organization_id == user.get("organization_id")


# ── Seed ────────────────────────────────────────────────────────────


async def seed_global_picklists() -> None:
    """Seed the global defaults on every startup. Idempotent: if a
    value already exists for the same (key, label, organization_id=null)
    triple it's left untouched. This keeps the global vocabulary
    sensible even after the codebase ships new keys.
    """
    try:
        for key, meta in PICKLIST_KEYS.items():
            for idx, label in enumerate(meta["defaults"]):
                exists = await db.crm_picklists.find_one({
                    "key": key,
                    "label": label,
                    "organization_id": None,
                })
                if exists:
                    continue
                await db.crm_picklists.insert_one({
                    "id": str(uuid.uuid4()),
                    "key": key,
                    "label": label,
                    "organization_id": None,
                    "sort_order": idx * 10,
                    "deprecated": False,
                    "created_at": _now(),
                    "created_by": "system",
                    "updated_at": _now(),
                })
        # Useful indexes for the merged-list query.
        await db.crm_picklists.create_index([("key", 1), ("organization_id", 1)])
        await db.crm_picklists.create_index([("key", 1), ("label", 1)])
    except Exception:
        logger.exception("seed_global_picklists failed (non-fatal)")


# ── Enforcement helper (Iter 220bs) ─────────────────────────────────


async def get_allowed_values(key: str, organization_id: str | None) -> list[str]:
    """Return the canonical labels for a picklist key, merging global
    defaults + org-specific values, with deprecated rows filtered. Used
    by the strict-validation helper below.
    """
    if key not in PICKLIST_KEYS:
        return []
    rows = await db.crm_picklists.find(
        {
            "key": key,
            "deprecated": False,
            "$or": [{"organization_id": None}, {"organization_id": organization_id}],
        },
        {"_id": 0, "label": 1},
    ).to_list(500)
    return [r["label"] for r in rows if r.get("label")]


async def validate_picklist_value(
    key: str, value: str | None,
    organization_id: str | None,
    *, strict: bool = True,
) -> str | None:
    """Validate a single picklist-typed field.

    * ``None`` / empty values pass through unchanged (picklists are
      optional unless the caller enforces requiredness separately).
    * Match is **case-insensitive** and trims whitespace; the canonical
      label from the picklist row is returned so we normalise storage.
    * ``strict=True`` (default) raises HTTPException(400) listing the
      valid options when no match is found — clean error surface for
      the operator UI.
    * ``strict=False`` returns ``None`` on no-match so legacy callers
      can warn-only and migrate gradually.

    Designed to be cheap to call from every CRUD endpoint — a single
    indexed Mongo query per (key, org) and an O(n) Python compare.
    """
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    allowed = await get_allowed_values(key, organization_id)
    lookup = {a.casefold(): a for a in allowed}
    canonical = lookup.get(cleaned.casefold())
    if canonical is not None:
        return canonical
    if not strict:
        return None
    # Helpful 400 with the valid options listed (capped at 20 for sanity).
    raise HTTPException(
        status_code=400,
        detail={
            "error": "invalid_picklist_value",
            "key": key,
            "field_label": PICKLIST_KEYS.get(key, {}).get("label", key),
            "received": cleaned,
            "valid_examples": allowed[:20],
            "hint": (
                f"Pick one of the values from /api/crm/picklists/{key}. "
                "If you need a new value, add it via the Settings → "
                "Picklists screen first."
            ),
        },
    )


async def validate_picklist_fields(
    payload: dict, fields: dict[str, str],
    organization_id: str | None,
    *, strict: bool = True,
) -> dict:
    """Bulk version — pass ``{payload_field: picklist_key}`` and the
    payload is normalised in-place (returns the same dict for chaining).

    Example::

        await validate_picklist_fields(data, {
            "lead_source": "lead_source",
            "opportunity_type": "opportunity_type",
        }, user.get("organization_id"))
    """
    for payload_field, picklist_key in fields.items():
        if payload_field not in payload:
            continue
        canonical = await validate_picklist_value(
            picklist_key, payload.get(payload_field),
            organization_id, strict=strict,
        )
        # Only overwrite if we got a canonical match — preserves
        # empty/None as-is.
        if canonical is not None:
            payload[payload_field] = canonical
    return payload


# ── Read endpoints ──────────────────────────────────────────────────


@router.get("")
async def list_picklist_keys(user=Depends(get_crm_user)) -> dict:
    """Return every supported picklist key + how many values each has
    (merged: global defaults + org-specific). Powers the Settings
    panel sidebar.
    """
    org_id = user.get("organization_id")
    out = []
    for key, meta in PICKLIST_KEYS.items():
        cnt = await db.crm_picklists.count_documents({
            "key": key,
            "deprecated": False,
            "$or": [{"organization_id": None}, {"organization_id": org_id}],
        })
        out.append({
            "key": key,
            "label": meta["label"],
            "scope": meta["scope"],
            "value_count": cnt,
        })
    return {"keys": out}


@router.get("/{key}")
async def list_picklist_values(key: str, user=Depends(get_crm_user)) -> dict:
    """Return the values for one picklist key. Merges global defaults
    (organization_id=null) with the requesting user's org values, with
    deprecated rows filtered out. Sorted by `sort_order`, ties broken
    by `label`.
    """
    if key not in PICKLIST_KEYS:
        raise HTTPException(404, f"Unknown picklist key: {key}")
    org_id = user.get("organization_id")
    cursor = db.crm_picklists.find(
        {
            "key": key,
            "deprecated": False,
            "$or": [{"organization_id": None}, {"organization_id": org_id}],
        },
        {"_id": 0},
    ).sort([("sort_order", 1), ("label", 1)])
    rows = await cursor.to_list(500)
    return {
        "key": key,
        "label": PICKLIST_KEYS[key]["label"],
        "scope": PICKLIST_KEYS[key]["scope"],
        "values": rows,
    }


# ── Write endpoints ─────────────────────────────────────────────────


@router.post("/{key}")
async def create_picklist_value(key: str, data: dict, user=Depends(get_crm_user)) -> dict:
    """Create a new value. By default the value belongs to the
    requesting user's org. Master admins can set `organization_id=null`
    in the body to create a *global* value visible to every tenant.
    Duplicate labels (case-insensitive) within the same scope are
    rejected so we don't silently re-introduce dupes.
    """
    if key not in PICKLIST_KEYS:
        raise HTTPException(404, f"Unknown picklist key: {key}")
    label = (data.get("label") or "").strip()
    if not label:
        raise HTTPException(400, "label is required")
    target_org = data.get("organization_id", user.get("organization_id"))
    # Master admin explicitly setting organization_id=null → global.
    if "organization_id" in data and data["organization_id"] in (None, ""):
        target_org = None
    if not _can_write(user, target_org):
        raise HTTPException(403, "Cannot write to that scope")

    # Duplicate guard — block (key, label) collision within the same
    # visibility scope (case-insensitive).
    existing = await db.crm_picklists.find_one({
        "key": key,
        "label": {"$regex": f"^{label}$", "$options": "i"},
        "$or": [
            {"organization_id": None},
            {"organization_id": target_org},
        ],
        "deprecated": False,
    })
    if existing:
        raise HTTPException(409, "A value with that label already exists")

    sort_order = data.get("sort_order")
    if sort_order is None:
        # Append at the end.
        last = await db.crm_picklists.find_one(
            {"key": key, "organization_id": target_org},
            sort=[("sort_order", -1)],
        )
        sort_order = ((last or {}).get("sort_order", 0) or 0) + 10

    doc = {
        "id": str(uuid.uuid4()),
        "key": key,
        "label": label,
        "organization_id": target_org,
        "sort_order": int(sort_order),
        "deprecated": False,
        "created_at": _now(),
        "created_by": user.get("id", ""),
        "updated_at": _now(),
    }
    await db.crm_picklists.insert_one(doc)
    await log_audit(user, "picklist", doc["id"], "created", {"key": key, "label": label, "scope": "global" if target_org is None else "org"})
    # Strip Mongo-injected _id before returning (BSON ObjectId is not
    # JSON-serialisable and would 500 the response).
    doc.pop("_id", None)
    return doc


@router.patch("/{key}/{value_id}")
async def update_picklist_value(key: str, value_id: str, data: dict, user=Depends(get_crm_user)) -> dict:
    """Rename / re-sort / soft-deprecate a value."""
    if key not in PICKLIST_KEYS:
        raise HTTPException(404, f"Unknown picklist key: {key}")
    existing = await db.crm_picklists.find_one({"id": value_id, "key": key}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Value not found")
    if not _can_write(user, existing.get("organization_id")):
        raise HTTPException(403, "Cannot edit this value")

    updates: dict = {"updated_at": _now()}
    if "label" in data:
        label = (data["label"] or "").strip()
        if not label:
            raise HTTPException(400, "label cannot be empty")
        updates["label"] = label
    if "sort_order" in data:
        updates["sort_order"] = int(data["sort_order"])
    if "deprecated" in data:
        updates["deprecated"] = bool(data["deprecated"])

    await db.crm_picklists.update_one({"id": value_id}, {"$set": updates})
    await log_audit(user, "picklist", value_id, "updated", updates)
    return {**existing, **updates}


@router.delete("/{key}/{value_id}")
async def delete_picklist_value(key: str, value_id: str, user=Depends(get_crm_user)) -> dict:
    """Hard-delete a value. Refuses if the label is still referenced
    anywhere (contacts.job_title, companies.industry, etc.) so we
    don't silently break the relational integrity. Caller should use
    PATCH with `deprecated: true` for a safe hide-from-new-forms.
    """
    if key not in PICKLIST_KEYS:
        raise HTTPException(404, f"Unknown picklist key: {key}")
    existing = await db.crm_picklists.find_one({"id": value_id, "key": key}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Value not found")
    if not _can_write(user, existing.get("organization_id")):
        raise HTTPException(403, "Cannot delete this value")

    label = existing["label"]
    # Map each picklist key → the (collection, field) it's referenced from.
    ref_map = {
        "job_title": [("crm2_contacts", "job_title")],
        "industry": [("crm2_companies", "industry")],
        "lead_source": [("crm2_opportunities", "source"), ("crm2_opportunities", "lead_source")],
        "opportunity_type": [("crm2_opportunities", "type")],
        "lost_reason": [("crm2_opportunities", "lost_reason")],
        "case_type": [("crm2_cases", "type")],
        "contact_role": [("crm2_contacts", "role")],
        "department": [("crm2_contacts", "department")],
    }
    org_id = existing.get("organization_id") or user.get("organization_id")
    for coll_name, field in ref_map.get(key, []):
        coll = getattr(db, coll_name)
        usage_q = {field: label, "organization_id": org_id}
        usage = await coll.count_documents(usage_q)
        if usage > 0:
            raise HTTPException(
                409,
                f"Cannot delete — '{label}' is still used by {usage} record(s) in {coll_name}.{field}. "
                "Use deprecated=true instead to hide from new forms.",
            )

    await db.crm_picklists.delete_one({"id": value_id})
    await log_audit(user, "picklist", value_id, "deleted", {"key": key, "label": label})
    return {"deleted": True, "id": value_id}
