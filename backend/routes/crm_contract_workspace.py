"""Iter 220e5 — CRM → Contracts: workspace-mode adaptation + Engineer
App → CRM contract feedback loop + Contract Review Queue.

Closes the last gap in the operator's enterprise-vs-solo brief:

1. ``GET /crm/v2/contracts/workspace`` — returns the workspace mode
   (``solo`` / ``enterprise``) computed from the org's user count +
   site count + active approval rules. The frontend dashboard and
   wizard read this and hide / show advanced workflows accordingly.

2. ``POST /svc/engineer/jobs/{case_id}/contract-feedback`` —
   engineer-side endpoint that lets an engineer post a contract
   feedback row (asset condition, recommended exclusion, repeated
   fault, CAPEX recommendation, upsell, dispute, etc.) tied to the
   job + the linked contract.

3. ``GET  /crm/v2/contracts/feedback-queue`` — coordinator-side
   Contract Review Queue. Lists open engineer feedback for the org.

4. ``POST /crm/v2/contracts/feedback/{id}/action`` — coordinator
   actions on a feedback row (accept / reject / note / mark
   reviewed). Optionally drops a renewal-task activity.

Storage: a single new collection ``crm2_contract_feedback`` — the
canonical source of truth for the loop. No data is duplicated; the
row references the existing ``svc_cases`` job, the existing
``crm2_contracts`` row and the existing engineer record.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from routes.crm_auth import get_crm_user
from utils.auth import get_current_user
from utils.crm_audit import record_audit
from utils.database import db


router = APIRouter(prefix="/crm/v2", tags=["Contracts · Workspace & Feedback"])

# Iter 220e5 — Engineer router lives alongside the existing
# ``routes/svc/engineer.py`` router and shares the same entitlement
# gate so partner engineers without an active grant get a 402.
try:
    from fastapi import Depends as _Depends
    from routes.partners import require_engineer_app_access
    engineer_router = APIRouter(
        prefix="/svc/engineer",
        tags=["Service Ops · Engineer Mobile"],
        dependencies=[_Depends(require_engineer_app_access)],
    )
except Exception:  # pragma: no cover - safety net for partial imports
    engineer_router = APIRouter(prefix="/svc/engineer", tags=["Service Ops · Engineer Mobile"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org if org else "__none__"}


# Iter 220e5 — Feedback kinds.
#
# Free-form text is allowed in ``body`` but the categorical ``kind``
# powers the Review Queue filters + the engineer dropdown.
ALLOWED_FEEDBACK_KINDS = {
    "asset_condition",       # asset has degraded — note for renewal
    "exclusion_recommended", # asset should be excluded next renewal
    "upgrade_recommended",   # customer should move up a tier
    "renewal_review",        # something about the renewal needs ops attention
    "repeated_fault",        # same fault recurring — service-cost / margin risk
    "capex_replacement",     # asset is end-of-life — recommend replacement
    "upsell_opportunity",    # customer would buy more cover
    "contract_dispute",      # customer disagreed with cover scope
    "chargeable_flag",       # work performed that is chargeable but cover suggests otherwise
    "pricing_review",        # service-cost ratio looks wrong vs annual fee
    "general_note",          # catch-all
}


# ── 1 · Workspace mode ─────────────────────────────────────────


@router.get("/contracts/workspace")
async def workspace_mode(user: dict = Depends(get_crm_user)):
    """Return the workspace mode for the caller's organisation.

    ``solo``:        single CRM user, ≤2 sites, no active approval rule
    ``enterprise``:  anything else (multi-user, multi-site, approvals)

    Also returns a ``capabilities`` map so the frontend can drive
    feature visibility without re-deriving the rules per surface.
    """
    org_match = _of(user)
    user_count = await db.crm2_users.count_documents(org_match)
    if not user_count:
        # Fall back to platform users when the CRM users collection
        # isn't seeded — keeps the heuristic honest for new tenants.
        user_count = await db.users.count_documents(
            {"organization_id": user.get("organization_id")},
        )
    site_count = await db.crm2_sites.count_documents(org_match)
    if not site_count:
        site_count = await db.svc_sites.count_documents(org_match)
    approval_count = 0
    try:
        approval_count = await db.crm2_approval_rules.count_documents(
            {**org_match, "active": True},
        )
    except Exception:
        approval_count = 0

    is_solo = (user_count <= 1) and (site_count <= 2) and (approval_count == 0)
    mode = "solo" if is_solo else "enterprise"

    return {
        "mode": mode,
        "user_count": user_count,
        "site_count": site_count,
        "approval_rules_active": approval_count,
        "capabilities": {
            "show_approval_queue":      not is_solo,
            "show_team_assignment":     not is_solo,
            "show_region_filters":      site_count > 5,
            "show_margin_review":       not is_solo,
            "default_owner_to_self":    True,
            "default_engineer_to_self": is_solo,
            "show_finance_review":      not is_solo,
            "show_review_queue":        True,  # both modes get the feedback queue
            "primary_cta":              "Create Contract" if is_solo else "New (Wizard)",
        },
        "generated_at": _now(),
    }


# ── 2 · Coordinator-side Review Queue ─────────────────────────


def _serialise(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "_id"}


@router.get("/contracts/feedback-queue")
async def feedback_queue(status: str = "open",
                        user: dict = Depends(get_crm_user)):
    """Return engineer contract feedback awaiting review for the
    caller's org. ``status`` filter accepts open / actioned / rejected /
    all. Sorted by newest first."""
    q = {**_of(user)}
    if status and status != "all":
        q["status"] = status
    rows = await db.crm2_contract_feedback.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"feedback": rows, "count": len(rows)}


@router.post("/contracts/feedback/{feedback_id}/action")
async def action_feedback(feedback_id: str, data: dict,
                          user: dict = Depends(get_crm_user)):
    """Coordinator acts on a feedback row.

    Body:
        {
          "action": "accept" | "reject" | "note" | "mark_reviewed",
          "note":   "...optional internal note..."
        }

    On ``accept`` for a ``renewal_review`` / ``upsell_opportunity`` /
    ``exclusion_recommended`` row we also drop a renewal task activity
    pinned to the contract so the renewal coordinator can pick it up
    next time the pipeline view is opened.
    """
    of = _of(user)
    row = await db.crm2_contract_feedback.find_one({"id": feedback_id, **of}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Feedback not found")
    action = (data.get("action") or "").lower()
    if action not in {"accept", "reject", "note", "mark_reviewed"}:
        raise HTTPException(400, "action must be accept / reject / note / mark_reviewed")
    note = (data.get("note") or "").strip()

    status_map = {
        "accept": "actioned",
        "reject": "rejected",
        "mark_reviewed": "reviewed",
        "note": row.get("status", "open"),  # don't change status on note-only
    }
    updates = {
        "status": status_map[action],
        "actioned_by": user.get("full_name", ""),
        "actioned_by_id": user.get("id"),
        "actioned_at": _now(),
        "updated_at": _now(),
    }
    if note:
        history: list[dict] = list(row.get("internal_notes") or [])
        history.append({
            "note": note,
            "by": user.get("full_name", ""),
            "at": _now(),
            "action": action,
        })
        updates["internal_notes"] = history

    await db.crm2_contract_feedback.update_one(
        {"id": feedback_id, **of}, {"$set": updates},
    )

    # On accept for renewal-relevant kinds, drop a renewal task activity.
    if action == "accept" and row.get("kind") in {
        "renewal_review", "upsell_opportunity",
        "exclusion_recommended", "pricing_review", "capex_replacement",
    } and row.get("contract_id"):
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": user.get("organization_id"),
            "type": "contract_renewal",
            "contract_id": row["contract_id"],
            "company_id": row.get("company_id", ""),
            "subject": f"Renewal task from engineer feedback [{row.get('kind')}]",
            "body": (row.get("body") or "")
                    + (f"\n\nCoordinator note: {note}" if note else ""),
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "created_at": _now(),
            "source": "engineer_feedback",
            "feedback_id": feedback_id,
        })

    await record_audit(
        entity_type="contract_feedback", entity_id=feedback_id,
        action=action, user=user, before=row,
        after={**row, **updates},
        summary=f"Feedback {action} by {user.get('full_name', '')}",
    )
    return {"success": True, "status": updates["status"]}


# ── 3 · Engineer-side feedback poster ─────────────────────────
#
# Lives under /svc/engineer so the engineer PWA auth + entitlement
# wall apply automatically. Returns the created feedback row so the
# PWA can display "Saved" confirmation.


async def _resolve_case_and_contract(case_id: str) -> tuple[dict, dict | None]:
    case = await db.svc_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    contract = None
    # Case might already carry a contract_id (linked via check-coverage).
    if case.get("contract_id"):
        contract = await db.crm2_contracts.find_one(
            {"id": case["contract_id"]}, {"_id": 0},
        )
    return case, contract


@engineer_router.post("/jobs/{case_id}/contract-feedback")
async def submit_contract_feedback(case_id: str, data: dict,
                                    user=Depends(get_current_user)):
    """Engineer posts contract feedback from the job detail page.

    Body:
        {
          "kind":      "<one of ALLOWED_FEEDBACK_KINDS>",
          "body":      "Free-text observation",
          "asset_id":  "<optional — links to the asset>",
          "severity":  "low" | "medium" | "high" (optional),
          "evidence_photos": ["url-or-base64", ...] (optional)
        }
    """
    kind = (data.get("kind") or "general_note").lower()
    if kind not in ALLOWED_FEEDBACK_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(ALLOWED_FEEDBACK_KINDS)}")
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "body is required")

    case, contract = await _resolve_case_and_contract(case_id)
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": case.get("organization_id"),
        "case_id": case_id,
        "case_reference": case.get("reference", ""),
        "contract_id": (contract or {}).get("id") or case.get("contract_id"),
        "contract_number": (contract or {}).get("contract_number", ""),
        "company_id": case.get("company_id") or (contract or {}).get("company_id", ""),
        "company_name": case.get("customer_name") or (contract or {}).get("company_name", ""),
        "site_id": case.get("site_id", ""),
        "site_name": case.get("site_name", ""),
        "asset_id": data.get("asset_id", ""),
        "kind": kind,
        "severity": (data.get("severity") or "medium").lower(),
        "body": body,
        "evidence_photos": data.get("evidence_photos") or [],
        "engineer_id": user.get("id"),
        "engineer_name": user.get("full_name", ""),
        "status": "open",
        "internal_notes": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm2_contract_feedback.insert_one(doc)
    # Also drop a lightweight activity so it shows on the CRM Activity
    # feed alongside other contract events.
    if doc["contract_id"]:
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": doc["organization_id"],
            "type": "system",
            "contract_id": doc["contract_id"],
            "company_id": doc.get("company_id", ""),
            "subject": f"Engineer feedback [{kind}]",
            "body": body,
            "owner_id": doc["engineer_id"],
            "owner_name": doc["engineer_name"],
            "created_at": _now(),
            "source": "engineer_feedback",
            "feedback_id": doc["id"],
        })
    return _serialise(doc)


@engineer_router.get("/jobs/{case_id}/contract-feedback")
async def list_my_feedback(case_id: str, user=Depends(get_current_user)):
    """List existing feedback the engineer has posted on this case so
    the PWA can show "previously submitted" without re-querying."""
    rows = await db.crm2_contract_feedback.find(
        {"case_id": case_id, "engineer_id": user.get("id")},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return {"feedback": rows, "count": len(rows)}


# ── 4 · Entitlement panel data ────────────────────────────────


@engineer_router.get("/jobs/{case_id}/contract-entitlement")
async def engineer_entitlement(case_id: str, user=Depends(get_current_user)):
    """Read-only entitlement summary for the engineer App. Combines
    case-level data + the linked contract's structured cover into a
    flat, mobile-friendly shape with plain-English labels.

    Reuses the canonical catalog labels from
    ``crm_contract_templates`` so engineers see the same wording the
    customer sees on the contract PDF.
    """
    case, contract = await _resolve_case_and_contract(case_id)
    if not contract:
        # Iter 220e6 — for solo / contract-less tenants, suppress the
        # panel entirely so it doesn't sit red on every job. Engineer
        # cover signals are still carried by the iter 220e1 cover chip
        # + banner on Summary which always render.
        any_contract = await db.crm2_contracts.find_one(
            {"organization_id": case.get("organization_id")},
            {"_id": 0, "id": 1},
        )
        if not any_contract:
            return {
                "active": False,
                "label": "",
                "tone": "neutral",
                "tenant_has_contracts": False,
                "fields": [],
            }
        # Tenant uses contracts but this case isn't linked to one —
        # surface the chargeable warning as before.
        return {
            "active": False,
            "label": "No contract on file — chargeable visit",
            "tone": "red",
            "tenant_has_contracts": True,
            "fields": [],
        }
    # Resolve labels via the canonical catalog.
    from routes.crm_contract_templates import (
        INCLUSION_GROUPS, EXCLUSION_ITEMS,
    )
    label_lookup: dict[str, str] = {}
    for group in INCLUSION_GROUPS:
        for item in group["items"]:
            label_lookup[item["key"]] = item["label"]
    exclusion_lookup = {e["key"]: e["label"] for e in EXCLUSION_ITEMS}

    inclusions = contract.get("inclusions") or {}
    structured_excl = contract.get("exclusions_structured") or []
    # Engineer-facing fields — plain English yes/no.
    def _has(group: str, key: str) -> bool:
        return key in (inclusions.get(group) or [])

    fields: list[dict[str, Any]] = []
    headline_items = [
        ("maintenance", "callout",              "Callout"),
        ("maintenance", "labour",               "Labour"),
        ("maintenance", "major_parts",          "Major parts"),
        ("maintenance", "wear_tear_parts",      "Wear & tear parts"),
        ("maintenance", "treadmill_belts",      "Treadmill belts"),
        ("maintenance", "treadmill_beds",       "Treadmill decks/beds"),
        ("maintenance", "upholstery",           "Upholstery"),
    ]
    for group_key, item_key, plain in headline_items:
        fields.append({
            "key": item_key,
            "label": plain,
            "covered": _has(group_key, item_key),
        })

    rt = (contract.get("response_times") or {}).get("emergency", {})
    return {
        "active": (contract.get("status") in {"active", "sent"}),
        "contract_id": contract["id"],
        "contract_number": contract.get("contract_number"),
        "tier": contract.get("tier"),
        "end_date": contract.get("end_date"),
        "tone": "green",
        "label": (
            f"Covered by {contract.get('tier', 'service').title()} contract"
            f" until {contract.get('end_date', '')}"
        ),
        "fields": fields,
        "exclusions": [
            {"key": k, "label": exclusion_lookup.get(k, k)} for k in structured_excl
        ],
        "sla_emergency_hours": rt.get("hours"),
        "label_lookup": label_lookup,
    }
