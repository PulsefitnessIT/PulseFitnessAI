"""CRM · Stakeholder Mapping (Iter 216h223 — Miller Heiman extension).

Extends the existing decision-maker model on `crm2_contacts` (which
today only tracks `is_decision_maker` + `is_champion` booleans) with
proper Miller Heiman stakeholder classification.

The contact-level fields stay backward-compatible — the existing
booleans are NOT removed and are derived from the new field where the
contact participates as the matching role.

What's added:
  • `influence_types: []` on contacts — multi-select tags from the
    canonical Miller Heiman set + common B2B influence roles.
  • Per-opportunity stakeholder map (`crm_stakeholder_map`) — lets the
    same contact play different roles in different deals. A
    Procurement contact might be a `Blocker` on one deal and the
    `Economic Buyer` on another.

Canonical roles (`INFLUENCE_TYPES`):
  • Economic Buyer    — controls budget / signs off cost
  • Technical Buyer   — gatekeeps technical fit
  • User Buyer        — will actually use the product day-to-day
  • Coach             — gives us insider info / advocates internally
  • Champion          — actively selling on our behalf
  • Blocker           — opposes the deal
  • Influencer        — sways the buying group
  • Decision Maker    — final-yes authority
  • Procurement       — commercial / contract terms
  • Finance Contact   — invoicing / payment terms
  • Operational Lead  — practical day-1 operator

Endpoints:
  GET    /crm/stakeholders/influence-types         — return canonical list
  PATCH  /crm/contacts/{contact_id}/influence-types — update contact's
                                                       global influence
                                                       tags
  GET    /crm/opportunities/{op_id}/stakeholders   — list stakeholders
                                                       on a deal
  POST   /crm/opportunities/{op_id}/stakeholders   — add contact w/ roles
  PATCH  /crm/opportunities/{op_id}/stakeholders/{contact_id}
                                                   — update roles / notes
  DELETE /crm/opportunities/{op_id}/stakeholders/{contact_id}
                                                   — remove from map
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm", tags=["CRM Stakeholders"])


INFLUENCE_TYPES: list[dict[str, str]] = [
    {"id": "economic_buyer",   "label": "Economic Buyer",   "tone": "violet",  "framework": "miller_heiman", "description": "Controls the budget. Final yes on cost."},
    {"id": "technical_buyer",  "label": "Technical Buyer",  "tone": "blue",    "framework": "miller_heiman", "description": "Gatekeeps technical fit. Veto power on specs."},
    {"id": "user_buyer",       "label": "User Buyer",       "tone": "sky",     "framework": "miller_heiman", "description": "Will use the product day-to-day. Their pain is the trigger."},
    {"id": "coach",            "label": "Coach",            "tone": "emerald", "framework": "miller_heiman", "description": "Provides insider info. Wants us to win but works inside the buying org."},
    {"id": "champion",         "label": "Champion",         "tone": "amber",   "framework": "miller_heiman", "description": "Actively sells on our behalf. Mobilises support internally."},
    {"id": "decision_maker",   "label": "Decision Maker",   "tone": "rose",    "framework": "core",          "description": "Final-yes authority for the purchase."},
    {"id": "influencer",       "label": "Influencer",       "tone": "indigo",  "framework": "core",          "description": "Sways the buying group without owning the decision."},
    {"id": "blocker",          "label": "Blocker",          "tone": "red",     "framework": "core",          "description": "Opposes the deal. Map their objection before close."},
    {"id": "procurement",      "label": "Procurement",      "tone": "zinc",    "framework": "ops",           "description": "Commercial and contractual terms gatekeeper."},
    {"id": "finance_contact",  "label": "Finance Contact",  "tone": "stone",   "framework": "ops",           "description": "Invoicing, payment terms, billing setup."},
    {"id": "operational_lead", "label": "Operational Lead", "tone": "teal",    "framework": "ops",           "description": "Practical day-1 operator. Drives adoption."},
]

VALID_TYPE_IDS = {t["id"] for t in INFLUENCE_TYPES}


# ── Iter 216h270 — Strategic Selling field catalogues ─────────────
# These extend the existing `influence_types[]` tags with the
# canonical Miller Heiman "Blue Sheet" qualitative scoring fields
# every account exec is taught to fill in before a major review:
#   * Buying influence level (Low / Medium / High)
#   * Adoption sentiment (5-point: Strong Anti → Strong Supporter)
#   * Coverage confidence (Stranger / Acquaintance / Trusted Advisor)
#   * Reports-to link (forces the rep to map the org chart)
#   * Personal wins / motivations (free-text)


BUYING_INFLUENCE_LEVELS: list[dict[str, str]] = [
    {"id": "low",    "label": "Low",    "tone": "zinc",   "description": "Limited say on the buying decision."},
    {"id": "medium", "label": "Medium", "tone": "amber",  "description": "Has a meaningful but non-final say."},
    {"id": "high",   "label": "High",   "tone": "rose",   "description": "Materially shapes or controls the decision."},
]


ADOPTION_SENTIMENTS: list[dict[str, str]] = [
    {"id": "strong_anti",       "label": "Strong Anti",       "tone": "red",     "score": -2, "description": "Actively opposes the deal — work the objection or route around."},
    {"id": "anti",              "label": "Anti",              "tone": "orange",  "score": -1, "description": "Sceptical or unconvinced. Needs evidence."},
    {"id": "neutral",           "label": "Neutral",           "tone": "zinc",    "score": 0,  "description": "No strong position — easy to swing either way."},
    {"id": "supporter",         "label": "Supporter",         "tone": "lime",    "score": 1,  "description": "Wants us to win. Needs nurturing into a Champion."},
    {"id": "strong_supporter",  "label": "Strong Supporter",  "tone": "emerald", "score": 2,  "description": "Actively sells on our behalf. Treat as a strategic asset."},
]


COVERAGE_CONFIDENCES: list[dict[str, str]] = [
    {"id": "stranger",         "label": "Stranger",         "tone": "stone",   "description": "Not yet engaged. No relationship — research before contact."},
    {"id": "acquaintance",     "label": "Acquaintance",     "tone": "sky",     "description": "Engaged at least once. Relationship is transactional."},
    {"id": "trusted_advisor",  "label": "Trusted Advisor",  "tone": "emerald", "description": "Will take our call and share candid info. Protect this!"},
]


VALID_BUYING_INFLUENCE = {b["id"] for b in BUYING_INFLUENCE_LEVELS}
VALID_ADOPTION_SENTIMENT = {s["id"] for s in ADOPTION_SENTIMENTS}
VALID_COVERAGE_CONFIDENCE = {c["id"] for c in COVERAGE_CONFIDENCES}


def _validate_miller_heiman(data: dict) -> dict:
    """Coerce + validate the Miller Heiman scoring fields. Empty / None
    values pass through (clearing a field is a legitimate operation),
    unknown values raise 400 so typos don't poison the dataset.
    """
    out: dict[str, Any] = {}
    if "buying_influence_level" in data:
        v = (data.get("buying_influence_level") or "").strip().lower() or None
        if v and v not in VALID_BUYING_INFLUENCE:
            raise HTTPException(400, f"Unknown buying_influence_level: {v}")
        out["buying_influence_level"] = v
    if "adoption_sentiment" in data:
        v = (data.get("adoption_sentiment") or "").strip().lower() or None
        if v and v not in VALID_ADOPTION_SENTIMENT:
            raise HTTPException(400, f"Unknown adoption_sentiment: {v}")
        out["adoption_sentiment"] = v
    if "coverage_confidence" in data:
        v = (data.get("coverage_confidence") or "").strip().lower() or None
        if v and v not in VALID_COVERAGE_CONFIDENCE:
            raise HTTPException(400, f"Unknown coverage_confidence: {v}")
        out["coverage_confidence"] = v
    if "reports_to_id" in data:
        v = (data.get("reports_to_id") or "").strip() or None
        out["reports_to_id"] = v
    if "personal_wins" in data:
        out["personal_wins"] = (data.get("personal_wins") or "").strip()
    return out


# ── Helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _validate_types(types: list[str]) -> list[str]:
    """Strip empties, dedupe, reject unknowns."""
    cleaned = []
    seen: set[str] = set()
    for t in types or []:
        t = (t or "").strip().lower()
        if not t or t in seen:
            continue
        if t not in VALID_TYPE_IDS:
            raise HTTPException(400, f"Unknown influence type: {t}")
        cleaned.append(t)
        seen.add(t)
    return cleaned


def _derive_legacy_booleans(types: list[str]) -> dict[str, bool]:
    """Keep `is_decision_maker` / `is_champion` in sync with the new
    multi-tag field so any code path that still reads the booleans
    stays accurate."""
    return {
        "is_decision_maker": "decision_maker" in (types or []),
        "is_champion": "champion" in (types or []),
    }


# ── Read endpoints ─────────────────────────────────────────────────


@router.get("/stakeholders/influence-types")
async def list_influence_types(user=Depends(get_crm_user)) -> dict:
    """Canonical Miller Heiman + extension role catalogue. Powers the
    multi-select on contact + opportunity surfaces.
    """
    return {"types": INFLUENCE_TYPES}


# ── Iter 216h270 — Miller Heiman scoring catalogues + endpoint ────


@router.get("/stakeholders/miller-heiman-catalogues")
async def list_miller_heiman_catalogues(user=Depends(get_crm_user)) -> dict:
    """Single endpoint that returns every catalogue the Strategic
    Selling panel needs (buying influence, adoption sentiment,
    coverage confidence). One round-trip → render the whole panel.
    """
    return {
        "buying_influence_levels": BUYING_INFLUENCE_LEVELS,
        "adoption_sentiments": ADOPTION_SENTIMENTS,
        "coverage_confidences": COVERAGE_CONFIDENCES,
    }


@router.patch("/contacts/{contact_id}/miller-heiman")
async def update_contact_miller_heiman(
    contact_id: str,
    data: dict,
    user=Depends(get_crm_user),
) -> dict:
    """Update the Strategic Selling fields on a contact. Accepts any
    subset of `buying_influence_level`, `adoption_sentiment`,
    `coverage_confidence`, `reports_to_id`, `personal_wins`. Fields
    not in the payload are left untouched — passing `null`/`""` clears
    the field explicitly.

    `reports_to_id` is validated against the same org so we never
    create a hierarchy pointer that crosses tenants. Self-reference
    is also rejected so the org chart can't loop on itself.
    """
    existing = await db.crm2_contacts.find_one(
        {"id": contact_id, **_of(user)}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Contact not found")

    updates = _validate_miller_heiman(data)

    # Cross-validate reports_to: must be a contact in the same org,
    # and must not be the contact itself.
    if "reports_to_id" in updates and updates["reports_to_id"]:
        rid = updates["reports_to_id"]
        if rid == contact_id:
            raise HTTPException(400, "A contact can't report to themselves")
        target = await db.crm2_contacts.find_one(
            {"id": rid, **_of(user)},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "job_title": 1},
        )
        if not target:
            raise HTTPException(404, f"reports_to_id={rid} not found in this org")

    updates["updated_at"] = _now()
    await db.crm2_contacts.update_one(
        {"id": contact_id, **_of(user)},
        {"$set": updates},
    )
    await log_audit(user, "contact", contact_id, "miller_heiman_updated", updates)
    return {**existing, **updates}


# ── Contact-level influence tags ───────────────────────────────────


@router.patch("/contacts/{contact_id}/influence-types")
async def update_contact_influence_types(
    contact_id: str,
    data: dict,
    user=Depends(get_crm_user),
) -> dict:
    """Replace the contact's global influence tags. Also syncs the
    legacy `is_decision_maker` + `is_champion` booleans so the rest of
    the CRM (lists, pipeline cards, ICP filters) stays consistent
    without a separate migration pass.
    """
    new_types = _validate_types(data.get("influence_types") or [])
    existing = await db.crm2_contacts.find_one(
        {"id": contact_id, **_of(user)}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Contact not found")
    updates: dict[str, Any] = {
        "influence_types": new_types,
        "updated_at": _now(),
        **_derive_legacy_booleans(new_types),
    }
    await db.crm2_contacts.update_one(
        {"id": contact_id, **_of(user)},
        {"$set": updates},
    )
    await log_audit(user, "contact", contact_id, "influence_types_updated", {"influence_types": new_types})
    return {**existing, **updates}


# ── Opportunity-level stakeholder map ──────────────────────────────


@router.get("/opportunities/{op_id}/stakeholders")
async def list_opportunity_stakeholders(op_id: str, user=Depends(get_crm_user)) -> dict:
    """List stakeholders on a deal. Each row is one contact playing
    one or more roles. Returns the joined contact record so the UI
    doesn't need a second round-trip.
    """
    opp = await db.crm2_opportunities.find_one({"id": op_id, **_of(user)}, {"_id": 0})
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    rows = await db.crm_stakeholder_map.find(
        {"opportunity_id": op_id, **_of(user)},
        {"_id": 0},
    ).sort("created_at", 1).to_list(200)

    # Hydrate contact details.
    contact_ids = [r["contact_id"] for r in rows if r.get("contact_id")]
    contacts = {
        c["id"]: c
        for c in await db.crm2_contacts.find(
            {"id": {"$in": contact_ids}, **_of(user)},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "job_title": 1, "company_id": 1, "company_name": 1, "phone": 1},
        ).to_list(200)
    }
    for r in rows:
        r["contact"] = contacts.get(r.get("contact_id"))

    return {"opportunity_id": op_id, "stakeholders": rows}


@router.post("/opportunities/{op_id}/stakeholders")
async def add_opportunity_stakeholder(
    op_id: str,
    data: dict,
    user=Depends(get_crm_user),
) -> dict:
    """Add a contact to the deal's stakeholder map. The same contact
    can have different role(s) on different deals — that's the whole
    point of having a per-opportunity map. Re-adding the same contact
    is rejected (use PATCH instead).
    """
    contact_id = (data.get("contact_id") or "").strip()
    if not contact_id:
        raise HTTPException(400, "contact_id is required")
    types = _validate_types(data.get("influence_types") or [])

    opp = await db.crm2_opportunities.find_one({"id": op_id, **_of(user)}, {"_id": 0, "id": 1})
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    contact = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)}, {"_id": 0, "id": 1})
    if not contact:
        raise HTTPException(404, "Contact not found")

    dup = await db.crm_stakeholder_map.find_one({
        "opportunity_id": op_id, "contact_id": contact_id, **_of(user),
    })
    if dup:
        raise HTTPException(409, "Contact is already on the stakeholder map — use PATCH to update")

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "opportunity_id": op_id,
        "contact_id": contact_id,
        "influence_types": types,
        "support_level": data.get("support_level", "neutral"),  # supporter | neutral | blocker
        "notes": (data.get("notes") or "").strip(),
        "created_at": _now(),
        "created_by": user.get("id", ""),
        "updated_at": _now(),
    }
    await db.crm_stakeholder_map.insert_one(doc)
    await log_audit(user, "opportunity", op_id, "stakeholder_added", {"contact_id": contact_id, "influence_types": types})
    doc.pop("_id", None)
    return doc


@router.patch("/opportunities/{op_id}/stakeholders/{contact_id}")
async def update_opportunity_stakeholder(
    op_id: str,
    contact_id: str,
    data: dict,
    user=Depends(get_crm_user),
) -> dict:
    """Update roles / support level / notes for a stakeholder."""
    existing = await db.crm_stakeholder_map.find_one(
        {"opportunity_id": op_id, "contact_id": contact_id, **_of(user)},
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Stakeholder not found on this opportunity")

    updates: dict[str, Any] = {"updated_at": _now()}
    if "influence_types" in data:
        updates["influence_types"] = _validate_types(data["influence_types"] or [])
    if "support_level" in data:
        lvl = (data["support_level"] or "").strip().lower()
        if lvl not in ("supporter", "neutral", "blocker"):
            raise HTTPException(400, "support_level must be supporter | neutral | blocker")
        updates["support_level"] = lvl
    if "notes" in data:
        updates["notes"] = (data["notes"] or "").strip()

    await db.crm_stakeholder_map.update_one(
        {"opportunity_id": op_id, "contact_id": contact_id, **_of(user)},
        {"$set": updates},
    )
    await log_audit(user, "opportunity", op_id, "stakeholder_updated", {"contact_id": contact_id, **updates})
    return {**existing, **updates}


@router.delete("/opportunities/{op_id}/stakeholders/{contact_id}")
async def remove_opportunity_stakeholder(
    op_id: str,
    contact_id: str,
    user=Depends(get_crm_user),
) -> dict:
    """Remove a contact from the deal's map (doesn't touch the
    contact record itself)."""
    res = await db.crm_stakeholder_map.delete_one(
        {"opportunity_id": op_id, "contact_id": contact_id, **_of(user)},
    )
    if not res.deleted_count:
        raise HTTPException(404, "Stakeholder not found on this opportunity")
    await log_audit(user, "opportunity", op_id, "stakeholder_removed", {"contact_id": contact_id})
    return {"deleted": True}


# ── Index bootstrap (called from startup) ──────────────────────────


async def ensure_stakeholder_indexes() -> None:
    try:
        await db.crm_stakeholder_map.create_index(
            [("opportunity_id", 1), ("contact_id", 1)], unique=True
        )
        await db.crm_stakeholder_map.create_index("organization_id")
    except Exception:
        logger.exception("ensure_stakeholder_indexes failed (non-fatal)")
