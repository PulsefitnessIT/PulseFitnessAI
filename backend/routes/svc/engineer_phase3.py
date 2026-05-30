"""Iter 216h133 — Engineer App Phase 3: Job workflow surfaces.

Composes existing primitives in `routes/svc/engineer.py` and
`routes/svc/parts.py` and adds the three things the Phase 3 frontend
needs that we didn't yet have endpoints for:

  1. POST /api/svc/engineer/jobs/{case_id}/mileage
     Manual mileage entry for a travel leg with auto rate × distance.
     Persists to `svc_engineer_mileage` and emits a case event.

  2. POST /api/svc/engineer/jobs/{case_id}/parts/{allocation_id}/consume
     Mark a previously-allocated part as actually used. Records a
     `consume` movement so Sicon ledgers reconcile and the case
     `allocated_parts[].fulfilled` flips true.

  3. POST /api/svc/engineer/jobs/{case_id}/parts/use
     Skip-allocation flow — "I used N×SKU on this job right now".
     If van stock exists for the engineer it is decremented; otherwise
     a free-form record is captured so the operator can replenish later.

  4. POST /api/svc/engineer/jobs/{case_id}/generate-invoice-draft
     Build a draft engineer invoice from:
       • all on_site time entries (chargeable=true) × labour rate
       • all mileage entries for the job
       • all consumed parts × list_price
     Then **returns** the new invoice (the engineer can review/edit
     before sending). The case is flagged `invoice_drafted=true` to
     stop accidental double-drafts; engineers can override.

The engineer's labour rate falls back to `partner_engineers.payout
.labour_rate_gbp` (settable later) and the mileage rate to a sane
HMRC-aligned default of £0.45/mile.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db
from utils.svc_state import append_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Job Workflow"],
    dependencies=[Depends(require_engineer_app_access)],
)


DEFAULT_LABOUR_RATE_GBP = 65.0
DEFAULT_MILEAGE_RATE_GBP = 0.45  # HMRC standard
DEFAULT_VAT_PCT = 20.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if isinstance(doc, dict):
        doc.pop("_id", None)
    return doc


async def _case_for_engineer(case_id: str, user: dict) -> dict:
    """Load a case, ensuring the caller is the assigned engineer
    (or an admin)."""
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Job not found")
    assigned = case.get("assigned_engineer_id")
    is_admin = bool(user.get("is_master_admin") or user.get("is_pulse_admin"))
    if assigned and assigned != user["id"] and not is_admin:
        # Iter 220az · F-29 / F-33 — 404 (not 403) on cross-engineer.
        raise HTTPException(404, "Job not found")
    return case


# ───────────────────────── Mileage ─────────────────────────────────


class MileageIn(BaseModel):
    miles: float = Field(..., gt=0, lt=10000, description="Distance in miles")
    rate_gbp_per_mile: float | None = Field(None, ge=0, le=10)
    from_postcode: str | None = ""
    to_postcode: str | None = ""
    notes: str | None = ""
    chargeable: bool = True


@router.post("/jobs/{case_id}/mileage", status_code=201)
async def add_mileage(
    case_id: str,
    body: MileageIn,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Capture a single mileage leg against a job."""
    of = _of(user)
    case = await _case_for_engineer(case_id, user)

    if idempotency_key:
        prev = await db.svc_engineer_mileage.find_one(
            {"idempotency_key": idempotency_key}, {"_id": 0},
        )
        if prev:
            return prev

    rate = float(body.rate_gbp_per_mile or DEFAULT_MILEAGE_RATE_GBP)
    amount = round(body.miles * rate, 2)
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "miles": round(float(body.miles), 2),
        "rate_gbp_per_mile": rate,
        "amount_gbp": amount,
        "from_postcode": (body.from_postcode or "").strip().upper(),
        "to_postcode": (body.to_postcode or "").strip().upper(),
        "notes": (body.notes or "").strip(),
        "chargeable": bool(body.chargeable),
        "logged_at": _now(),
        "idempotency_key": idempotency_key,
    }
    await db.svc_engineer_mileage.insert_one(doc)
    doc.pop("_id", None)
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Mileage logged: {doc['miles']} mi × £{rate:.2f} = £{amount:.2f}",
        extra={"kind": "mileage", "mileage_id": doc["id"], "amount_gbp": amount},
    )
    return doc


@router.get("/jobs/{case_id}/mileage")
async def list_mileage(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    await _case_for_engineer(case_id, user)
    rows = await db.svc_engineer_mileage.find(
        {"case_id": case_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    ).sort("logged_at", -1).to_list(200)
    total_miles = round(sum(r.get("miles", 0) for r in rows), 2)
    total_amount = round(sum(r.get("amount_gbp", 0) for r in rows), 2)
    return {"items": rows, "total_miles": total_miles, "total_amount_gbp": total_amount}


@router.delete("/jobs/{case_id}/mileage/{mileage_id}")
async def delete_mileage(case_id: str, mileage_id: str, user=Depends(get_current_user)):
    of = _of(user)
    await _case_for_engineer(case_id, user)
    res = await db.svc_engineer_mileage.delete_one(
        {"id": mileage_id, "case_id": case_id, **of, "engineer_id": user["id"]},
    )
    if not res.deleted_count:
        raise HTTPException(404, "Mileage entry not found")
    return {"ok": True}


# ─────────────────── Parts: consume + ad-hoc use ───────────────────


@router.post("/jobs/{case_id}/parts/{allocation_id}/consume")
async def consume_allocation(case_id: str, allocation_id: str,
                              user=Depends(get_current_user)):
    """Flip an allocated part to fulfilled and record a consume movement."""
    of = _of(user)
    case = await _case_for_engineer(case_id, user)
    allocations = case.get("allocated_parts") or []
    alloc = next((a for a in allocations if a.get("id") == allocation_id), None)
    if not alloc:
        raise HTTPException(404, "Allocation not on this case")
    if alloc.get("fulfilled"):
        return {"ok": True, "already_consumed": True, "allocation": alloc}

    await db.svc_cases.update_one(
        {"id": case_id, **of, "allocated_parts.id": allocation_id},
        {"$set": {
            "allocated_parts.$.fulfilled": True,
            "allocated_parts.$.fulfilled_at": _now(),
            "allocated_parts.$.fulfilled_by_id": user["id"],
            "updated_at": _now(),
        }},
    )
    await db.svc_part_movements.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "allocation_id": allocation_id,
        "part_sku": alloc.get("part_sku"),
        "part_name": alloc.get("part_name"),
        "qty": alloc.get("qty"),
        "movement_type": "consume",
        "source": "case",
        "engineer_id": user["id"],
        "actor_id": user["id"],
        "actor_name": user.get("full_name") or user.get("email") or "",
        "at": _now(),
        "notes": "Consumed on job by engineer",
    })
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Used {alloc.get('qty')} × {alloc.get('part_sku')} ({alloc.get('part_name','')})",
        extra={"kind": "parts_consume", "allocation_id": allocation_id},
    )
    return {"ok": True, "allocation_id": allocation_id, "fulfilled": True}


class PartUseIn(BaseModel):
    part_sku: str = Field(..., min_length=1)
    qty: int = Field(..., gt=0, le=999)
    notes: str | None = ""
    # Iter 220do — engineers can now tag a used part to the specific
    # machine it went into so the customer report shows
    # "Belt £45 → Treadmill #14" rather than a flat parts list.
    machine_id: str | None = None
    machine_name: str | None = None


@router.post("/jobs/{case_id}/parts/use", status_code=201)
async def use_part_ad_hoc(
    case_id: str, body: PartUseIn,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Engineer reports a part used on the job without a prior allocation.

    Behaviour:
      • If the SKU exists in the catalogue and the engineer has van
        stock, decrement van stock and create an allocation already
        marked `fulfilled=true`.
      • If no van stock (or SKU not in catalogue), still create an
        allocation marked fulfilled — the operator can replenish/
        backfill later. The amount goes onto the invoice draft using
        the part's `list_price` if known, else £0.
    """
    of = _of(user)
    case = await _case_for_engineer(case_id, user)

    if idempotency_key:
        prev_case = await db.svc_cases.find_one(
            {"allocated_parts.idempotency_key": idempotency_key, **of}, {"_id": 0},
        )
        if prev_case:
            for a in prev_case.get("allocated_parts") or []:
                if a.get("idempotency_key") == idempotency_key:
                    return a

    sku = body.part_sku.strip().upper()
    part = await db.svc_parts.find_one({**of, "sku": sku}, {"_id": 0})
    list_price = float((part or {}).get("list_price") or 0)
    part_name = (part or {}).get("name") or sku

    van = await db.svc_van_stock.find_one(
        {**of, "engineer_id": user["id"], "part_sku": sku},
    )
    decremented = False
    if van and (van.get("qty") or 0) >= body.qty:
        await db.svc_van_stock.update_one(
            {"_id": van["_id"]},
            {"$inc": {"qty": -body.qty}, "$set": {"updated_at": _now()}},
        )
        decremented = True

    allocation = {
        "id": str(uuid.uuid4()),
        "organization_id": of["organization_id"],
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "part_sku": sku,
        "part_name": part_name,
        "qty": body.qty,
        "list_price_gbp": list_price,
        "source": "van" if decremented else "adhoc",
        "engineer_id": user["id"],
        "fulfilled": True,
        "fulfilled_at": _now(),
        "allocated_by_id": user["id"],
        "allocated_by_name": user.get("full_name") or user.get("email") or "",
        "allocated_at": _now(),
        "notes": (body.notes or "").strip(),
        "machine_id": (body.machine_id or None),
        "machine_name": (body.machine_name or None),
        "idempotency_key": idempotency_key,
    }
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$push": {"allocated_parts": allocation}, "$set": {"updated_at": _now()}},
    )
    await db.svc_part_movements.insert_one({
        **{k: v for k, v in allocation.items() if k != "_id"},
        "id": str(uuid.uuid4()),
        "allocation_id": allocation["id"],
        "movement_type": "consume",
        "from_location": "van" if decremented else "adhoc",
        "to_location": "case",
        "actor_id": user["id"],
        "actor_name": user.get("full_name") or user.get("email") or "",
        "at": _now(),
    })
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Used {body.qty} × {sku} ({part_name})",
        extra={"kind": "parts_use", "allocation_id": allocation["id"],
               "from_van": decremented},
    )
    return allocation


# ─────────────────── Invoice draft from job context ────────────────


@router.post("/jobs/{case_id}/generate-invoice-draft", status_code=201)
async def generate_invoice_draft(
    case_id: str,
    body: dict | None = None,
    user=Depends(get_current_user),
):
    """Compose an engineer invoice draft from time + mileage + parts."""
    of = _of(user)
    case = await _case_for_engineer(case_id, user)
    body = body or {}

    # Engineer rate lookup
    partner = await db.partner_engineers.find_one(
        {"user_id": user["id"]}, {"_id": 0, "payout": 1, "trading_name": 1, "full_name": 1},
    ) or {}
    labour_rate = float(
        ((partner.get("payout") or {}).get("labour_rate_gbp"))
        or body.get("labour_rate_gbp")
        or DEFAULT_LABOUR_RATE_GBP
    )

    # Collect billable on_site time entries
    entries = await db.svc_time_entries.find(
        {"case_id": case_id, **of, "engineer_id": user["id"]}, {"_id": 0},
    ).to_list(500)
    on_site_minutes = sum(
        int(e.get("duration_minutes") or 0)
        for e in entries
        if e.get("category") == "on_site" and e.get("end_at")
    )
    on_site_hours = round(on_site_minutes / 60.0, 2)

    # Collect mileage
    mileage_rows = await db.svc_engineer_mileage.find(
        {"case_id": case_id, **of, "engineer_id": user["id"], "chargeable": True},
        {"_id": 0},
    ).to_list(200)
    total_miles = round(sum(r.get("miles", 0) for r in mileage_rows), 2)
    mileage_amount = round(sum(r.get("amount_gbp", 0) for r in mileage_rows), 2)

    # Collect consumed parts
    consumed = [a for a in (case.get("allocated_parts") or []) if a.get("fulfilled")]

    lines: list[dict] = []
    if on_site_hours > 0:
        lines.append({
            "kind": "labour",
            "description": f"Engineer labour ({on_site_hours}h on site)",
            "quantity": on_site_hours,
            "unit_price": labour_rate,
        })
    if total_miles > 0:
        # Use the avg rate for the description but pass amount via qty/rate
        avg_rate = round(mileage_amount / total_miles, 2) if total_miles else 0
        lines.append({
            "kind": "travel",
            "description": f"Mileage ({total_miles} mi @ £{avg_rate:.2f}/mi)",
            "quantity": total_miles,
            "unit_price": avg_rate,
        })
    for alloc in consumed:
        qty = float(alloc.get("qty") or 0)
        price = float(alloc.get("list_price_gbp") or 0)
        # Fall back to catalogue list price if not embedded
        if price <= 0 and alloc.get("part_sku"):
            part = await db.svc_parts.find_one(
                {**of, "sku": alloc["part_sku"]}, {"_id": 0, "list_price": 1},
            )
            price = float((part or {}).get("list_price") or 0)
        lines.append({
            "kind": "part",
            "description": f"{alloc.get('part_sku')} — {alloc.get('part_name','')}",
            "quantity": qty,
            "unit_price": price,
        })

    if not lines:
        raise HTTPException(
            400, "Nothing chargeable yet — log time, mileage or parts first.",
        )

    # Compose draft invoice payload mirroring engineer_invoices.create
    payload = {
        "case_id": case_id,
        "case_reference": case.get("reference"),
        "linked_quote_id": None,
        "linked_quote_number": None,
        "customer_name": case.get("customer_name") or "",
        "customer_email": case.get("customer_email") or "",
        "customer_phone": case.get("customer_phone") or "",
        "site_name": case.get("site_name") or "",
        "site_address": case.get("site_address") or "",
        "asset_name": case.get("asset_name") or "",
        "asset_serial": case.get("asset_serial") or "",
        "description_of_work": (case.get("title") or "")
                                + ((" — " + case.get("resolution_notes")) if case.get("resolution_notes") else ""),
        "lines": lines,
        "vat_rate": float(body.get("vat_rate") or DEFAULT_VAT_PCT),
        "discount_pct": float(body.get("discount_pct") or 0),
        "payment_terms_days": int(body.get("payment_terms_days") or 14),
        "payment_method": body.get("payment_method") or "BACS",
        "notes": body.get("notes") or "",
        "terms": body.get("terms") or "",
    }
    # Delegate to the existing invoice creator so totals, numbering,
    # status_history and SOURCE-OF-TRUTH stay identical.
    from routes.svc.engineer_invoices import create_invoice, InvoiceCreate
    invoice = await create_invoice(InvoiceCreate(**payload), user=user)

    # Tag the case so the UI can show "Invoice draft EI-...-XXXX"
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {
            "invoice_drafted": True,
            "invoice_draft_id": invoice["id"],
            "invoice_draft_number": invoice.get("invoice_number"),
            "updated_at": _now(),
        }},
    )
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Invoice draft {invoice.get('invoice_number')} created from job",
        extra={"kind": "invoice_drafted", "invoice_id": invoice["id"]},
    )
    return invoice


# Iter 220cz — Engineer-to-engineer handoff notes.
# When a job is reassigned (admin or auto-route), the leaving engineer
# can leave a freeform note that surfaces on the NEW engineer's
# JobAtAGlance card. This was the #1 dispatch-friction win from the
# process-analyst review.
@router.post("/jobs/{case_id}/handoff-note")
async def add_handoff_note(
    case_id: str,
    body: dict,
    user=Depends(get_current_user),
):
    """Body: `{note: str}`. Appends a handoff note to `case.handoff_notes`."""
    of = _of(user)
    note = (body.get("note") or "").strip()
    if not note:
        raise HTTPException(400, "Empty handoff note")
    if len(note) > 2000:
        note = note[:2000]
    case = await db.svc_cases.find_one(
        {"id": case_id, **of}, {"_id": 0, "id": 1, "reference": 1},
    )
    if not case:
        raise HTTPException(404, "Case not found")
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": str(uuid.uuid4()),
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "note": note,
        "at": now_iso,
    }
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {
            "$push": {"handoff_notes": entry},
            "$set":  {"updated_at": now_iso},
        },
    )
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="note", actor=user,
        body=f"Handoff note left: {note[:80]}{'…' if len(note) > 80 else ''}",
        extra={"kind": "handoff_note", "handoff_note_id": entry["id"]},
    )
    return {"ok": True, "entry": entry}


# ─── Iter 220dp · Return-to-fix ──────────────────────────────────
#
# When the engineer can't complete the repair on this visit (parts
# on order, time ran out, asset needs spec work etc), the Complete
# tab now offers an explicit **"Did you fix it on this visit?"**
# question. Picking *No* pushes a single call that:
#
#   • Stamps the case with a `return_to_fix` block (date, reason,
#     follow-up note) so the customer-facing report and admin
#     dashboard can render the truthful "needs second visit" badge.
#   • Re-schedules the case for the chosen ISO datetime.
#   • Sets status back to ``scheduled`` so it re-enters the diary
#     workflow instead of being closed prematurely.
#   • (Optional) emits a customer ETA notification — re-uses the
#     existing engineer→customer ETA push helper so the customer
#     sees the same branded copy as a first-visit ETA, just with
#     the "second visit" framing.
#
# Surgical fields only — the existing diary/handoff/SLA machinery
# does the rest.

class ReturnToFixIn(BaseModel):
    return_at: str = Field(..., min_length=10,
                           description="ISO datetime for the follow-up visit")
    reason: str = Field("", max_length=400,
                        description="Why a second visit is needed")
    notify_customer: bool = True


@router.post("/jobs/{case_id}/return-to-fix")
async def return_to_fix(
    case_id: str, body: ReturnToFixIn,
    user=Depends(get_current_user),
):
    """Engineer flags the job as 'needs a return visit' and optionally
    notifies the customer.

    Idempotent on the same ``return_at`` — re-firing the same payload
    just refreshes the stamp."""
    of = _of(user)
    case = await _case_for_engineer(case_id, user)
    try:
        datetime.fromisoformat(body.return_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "return_at must be ISO datetime")

    now_iso = _now()
    rtf = {
        "id": str(uuid.uuid4()),
        "engineer_id": user["id"],
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "reason": (body.reason or "").strip(),
        "return_at": body.return_at,
        "created_at": now_iso,
    }
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {
            "$set": {
                "return_to_fix": rtf,
                "scheduled_at": body.return_at,
                "status": "scheduled",
                "updated_at": now_iso,
            },
        },
    )
    await append_event(
        case_id=case_id, organization_id=of["organization_id"],
        event_type="return_to_fix", actor=user,
        body=(f"Return-to-fix scheduled for {body.return_at}"
              + (f": {body.reason}" if body.reason else "")),
        extra={"kind": "return_to_fix", "return_at": body.return_at,
               "reason": body.reason, "rtf_id": rtf["id"]},
    )

    notified = False
    if body.notify_customer and case.get("customer_email"):
        try:
            from routes.svc.notifications import create_notification
            ref = case.get("reference") or case_id[:8]
            site = case.get("site_name") or "your site"
            try:
                when_str = datetime.fromisoformat(
                    body.return_at.replace("Z", "+00:00"),
                ).strftime("%a %d %b · %H:%M")
            except Exception:
                when_str = body.return_at
            await create_notification(
                user_id=case.get("customer_user_id") or "",
                organization_id=of["organization_id"],
                kind="job_rescheduled",
                title=f"Return visit booked · {ref}",
                body=f"{site} — back on {when_str}"
                     + (f" ({body.reason})" if body.reason else ""),
                link=case.get("public_track_url"),
                source_type="case",
                source_id=case_id,
            )
            notified = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("return-to-fix notify failed for case=%s: %s",
                           case_id, exc)
    return {"ok": True, "return_to_fix": rtf, "customer_notified": notified}


__all__ = ["router"]
