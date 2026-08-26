"""CRM · Handover & close for CPQ v2 quotes (Equipment Sales Phase 4).

Extends the existing quote + service-jobs (``issues``) processes — no new
module:
  • Turn a won deal into linked install / service (PPM) jobs on the existing
    Operations job board, each stamped with ``quote_id`` and the sold
    equipment so the service team has full visibility.
  • "Complete Deal" — closes the deal once everything is delivered (goods
    received → equipment registered) and invoiced. Managers can force with
    a reason.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_quote_invoicing import _build_view as invoicing_view
from routes.crm_quote_fulfilment import _build_view as fulfilment_view

router = APIRouter(prefix="/crm/v2/quotes", tags=["CRM Quote Handover"])

JOB_TYPES = ("install", "ppm", "repair")
_CCY_SYMBOL = {"GBP": "£", "USD": "$", "EUR": "€"}


def _money(amount: float, ccy: str) -> str:
    sym = _CCY_SYMBOL.get(ccy or "")
    return f"{sym}{amount:,.2f}" if sym else f"{amount:,.2f} {ccy}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _can_manage(user: dict) -> bool:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    return (user.get("role") or "").lower() in ("owner", "admin", "manager")


async def _audit(user: dict, quote_id: str, action: str, meta: dict | None = None) -> None:
    try:
        from routes.crm_core import log_audit
        await log_audit(user, "quote_handover", quote_id, action, meta or {})
    except Exception:
        pass


async def _get_quote(quote_id: str, user: dict) -> dict:
    quote = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    return quote


async def _linked_jobs(quote_id: str, user: dict) -> list[dict]:
    jobs = await db.issues.find(
        {"quote_id": quote_id, **_of(user)},
        {"_id": 0, "id": 1, "machine_type": 1, "case_type": 1, "status": 1,
         "severity": 1, "asset_id": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(100)
    return jobs


_OPEN_JOB = {"new", "open", "assigned", "in_progress", "escalated", "dispatched", None}


async def _completion(quote: dict, user: dict, inv: dict | None = None, ful: dict | None = None) -> dict:
    if inv is None:
        inv = await invoicing_view(quote, user)
    if ful is None:
        ful = await fulfilment_view(quote, user)
    jobs = await _linked_jobs(quote["id"], user)

    invoiced_ok = inv["summary"]["remaining_to_invoice"] <= 0.01 and inv["summary"]["invoiced_gross"] > 0
    units_expected = ful["summary"]["equipment_units_expected"]
    delivered_ok = units_expected == 0 or ful["summary"]["equipment_created"] >= units_expected
    open_jobs = [j for j in jobs if (j.get("status") in _OPEN_JOB)]
    jobs_ok = len(open_jobs) == 0

    reasons = []
    if not invoiced_ok:
        reasons.append(f"Not fully invoiced — {_money(inv['summary']['remaining_to_invoice'], inv['currency'])} still to invoice")
    if not delivered_ok:
        reasons.append(f"Not fully delivered — {ful['summary']['equipment_created']}/{units_expected} equipment units registered")

    return {
        "deal_status": quote.get("deal_status", "open"),
        "completed_at": quote.get("deal_completed_at"),
        "completed_by": quote.get("deal_completed_by"),
        "invoiced_ok": invoiced_ok,
        "delivered_ok": delivered_ok,
        "jobs_ok": jobs_ok,
        "open_job_count": len(open_jobs),
        "ready": invoiced_ok and delivered_ok,
        "reasons": reasons,
        "invoicing_summary": inv["summary"],
        "fulfilment_summary": ful["summary"],
    }


def _job_suggestions(quote: dict, ful: dict) -> list[dict]:
    """Suggest install jobs — one per registered equipment unit if any are
    delivered, otherwise one per equipment line on the quote."""
    out = []
    for e in ful.get("equipment", []):
        out.append({
            "case_type": "install",
            "title": f"Install & commission — {e.get('name')}",
            "equipment_id": e.get("id"),
            "serial_number": e.get("serial_number") or "",
        })
    if not out:
        for p in ful.get("procurable_lines", []):
            if p.get("is_equipment"):
                out.append({
                    "case_type": "install",
                    "title": f"Install & commission — {p.get('description')}",
                    "equipment_id": None,
                    "serial_number": "",
                    "quantity": int(p.get("quantity", 1)),
                })
    return out


# ── Read ───────────────────────────────────────────────────────────


@router.get("/{quote_id}/handover")
async def get_handover(quote_id: str, user=Depends(get_crm_user)):
    quote = await _get_quote(quote_id, user)
    ful = await fulfilment_view(quote, user)
    return {
        "quote_id": quote_id,
        "quote_number": quote.get("quote_number", ""),
        "jobs": await _linked_jobs(quote_id, user),
        "suggestions": _job_suggestions(quote, ful),
        "completion": await _completion(quote, user, ful=ful),
    }


# ── Create linked jobs ─────────────────────────────────────────────


async def _create_job(quote: dict, spec: dict, user: dict) -> dict:
    from models.schemas import IssueCreate
    from routes.issues import _build_issue_doc

    case_type = (spec.get("case_type") or "install").lower()
    if case_type not in JOB_TYPES:
        case_type = "install"
    equipment_id = spec.get("equipment_id")
    serial = (spec.get("serial_number") or "").strip()
    site_id = spec.get("site_id")
    if equipment_id:
        eq = await db.equipment.find_one({"id": equipment_id, **_of(user)}, {"_id": 0, "serial_number": 1, "site_id": 1, "name": 1})
        if eq:
            serial = serial or (eq.get("serial_number") or "")
            site_id = site_id or eq.get("site_id")
    title = (spec.get("title") or "Deal handover job").strip()
    default_desc = {
        "install": "Delivery, installation & commissioning from equipment sale.",
        "ppm": "Planned maintenance / service visit from equipment sale.",
        "repair": "Follow-up work from equipment sale.",
    }[case_type]

    ic = IssueCreate(
        serial_number=serial or "",
        machine_type=title,
        issue_description=(spec.get("description") or default_desc),
        severity=(spec.get("severity") or "medium"),
        case_type=case_type,
        serial_unknown=not bool(serial),
    )
    doc = _build_issue_doc(ic, user)
    doc.update({
        "site_id": site_id or doc.get("site_id") or "",
        "asset_id": equipment_id or "",
        "equipment_ids": [equipment_id] if equipment_id else [],
        # Deal traceability.
        "source": "deal_handover",
        "quote_id": quote["id"],
        "quote_number": quote.get("quote_number", ""),
        "company_id": quote.get("company_id"),
        "company_name": quote.get("company_name", ""),
    })
    await db.issues.insert_one(doc)
    doc.pop("_id", None)
    # Handover jobs land directly on the Operations job board (db.issues).
    # Service-Desk mirroring is intentionally NOT done here — that path is
    # reserved for faults escalated to an engineer (resolution_type ==
    # 'engineer'), which these install/PPM jobs are not.
    return {"id": doc["id"], "machine_type": doc.get("machine_type"), "case_type": case_type, "status": doc.get("status")}


@router.post("/{quote_id}/handover/jobs")
async def create_handover_jobs(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Create linked install/service jobs. Body: {jobs:[{case_type,title,...}]}
    or {auto:true} to generate an install job per registered equipment unit."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can create handover jobs")
    quote = await _get_quote(quote_id, user)
    specs = data.get("jobs") or []
    if data.get("auto") and not specs:
        ful = await fulfilment_view(quote, user)
        specs = _job_suggestions(quote, ful)
        # Expand line-based suggestions by quantity when nothing delivered yet.
        expanded = []
        for s in specs:
            qty = int(s.get("quantity", 1) or 1) if not s.get("equipment_id") else 1
            for _ in range(max(1, qty)):
                expanded.append(dict(s))  # copy so specs don't share references
        specs = expanded
    if not specs:
        raise HTTPException(400, "No jobs to create — pass jobs[] or auto:true (needs equipment lines).")

    created = [await _create_job(quote, s, user) for s in specs]
    ids = [c["id"] for c in created]
    await db.crm2_quotes.update_one(
        {"id": quote_id, **_of(user)},
        {"$addToSet": {"handover_job_ids": {"$each": ids}}, "$set": {"updated_at": _now()}},
    )
    await _audit(user, quote_id, "jobs_created", {"count": len(created)})
    return {"created": created, "jobs": await _linked_jobs(quote_id, user), "completion": await _completion(quote, user)}


# ── Complete / reopen ──────────────────────────────────────────────


@router.post("/{quote_id}/complete")
async def complete_deal(quote_id: str, data: dict = None, user=Depends(get_crm_user)):
    """Mark the deal complete once delivered + invoiced. Managers may force
    with {force:true, reason:'...'}."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can complete a deal")
    data = data or {}
    quote = await _get_quote(quote_id, user)
    if quote.get("deal_status") == "completed":
        raise HTTPException(400, "Deal is already completed")
    comp = await _completion(quote, user)
    forced = bool(data.get("force"))
    if not comp["ready"] and not forced:
        raise HTTPException(400, "; ".join(comp["reasons"]) or "Deal is not ready to complete")
    await db.crm2_quotes.update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {
            "deal_status": "completed",
            "deal_completed_at": _now(),
            "deal_completed_by": user.get("full_name", ""),
            "deal_completed_forced": forced,
            "deal_completed_reason": (data.get("reason") or "").strip() if forced else None,
            "updated_at": _now(),
        }},
    )
    await _audit(user, quote_id, "deal_completed", {"forced": forced, "reason": data.get("reason")})
    quote = await _get_quote(quote_id, user)
    return {"completion": await _completion(quote, user)}


@router.post("/{quote_id}/reopen")
async def reopen_deal(quote_id: str, user=Depends(get_crm_user)):
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can reopen a deal")
    quote = await _get_quote(quote_id, user)
    if quote.get("deal_status") != "completed":
        raise HTTPException(400, "Deal is not completed")
    await db.crm2_quotes.update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {"deal_status": "open", "updated_at": _now()},
         "$unset": {"deal_completed_at": "", "deal_completed_by": "",
                    "deal_completed_forced": "", "deal_completed_reason": ""}},
    )
    await _audit(user, quote_id, "deal_reopened", {})
    quote = await _get_quote(quote_id, user)
    return {"completion": await _completion(quote, user)}
