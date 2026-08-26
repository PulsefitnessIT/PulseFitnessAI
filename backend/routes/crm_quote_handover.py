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


async def _customer_portal(quote: dict, user: dict) -> dict:
    """Resolve the deal's customer to their own Pulse portal org (if linked)
    via crm2_companies.tenant_org_id, plus handover progress. A unit only
    counts as handed over while its customer-side copy still exists (so a
    deleted copy becomes re-pushable)."""
    company_id = quote.get("company_id")
    company = await db.crm2_companies.find_one(
        {"id": company_id, **_of(user)}, {"_id": 0, "name": 1, "tenant_org_id": 1},
    ) if company_id else None
    tenant_org_id = (company or {}).get("tenant_org_id") or None
    tenant_name = ""
    if tenant_org_id:
        org = await db.organizations.find_one({"id": tenant_org_id}, {"_id": 0, "name": 1})
        tenant_name = (org or {}).get("name", "")

    seller_rows = await db.equipment.find(
        {"quote_id": quote["id"], **_of(user)}, {"_id": 0, "id": 1, "customer_equipment_id": 1},
    ).to_list(500)
    seller_equipment = len(seller_rows)
    cust_ids = [r["customer_equipment_id"] for r in seller_rows if r.get("customer_equipment_id")]
    existing = set()
    if tenant_org_id and cust_ids:
        rows = await db.equipment.find(
            {"organization_id": tenant_org_id, "id": {"$in": cust_ids}}, {"_id": 0, "id": 1},
        ).to_list(500)
        existing = {r["id"] for r in rows}
    handed = sum(1 for r in seller_rows if r.get("customer_equipment_id") in existing)
    return {
        "linked": bool(tenant_org_id),
        "tenant_org_id": tenant_org_id,
        "tenant_org_name": tenant_name,
        "company_name": (company or {}).get("name", ""),
        "equipment_registered": seller_equipment,
        "equipment_handed_over": handed,
        "pending_handover": max(0, seller_equipment - handed),
    }


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
        "customer_portal": await _customer_portal(quote, user),
    }


@router.post("/{quote_id}/handover/register")
async def register_with_customer(quote_id: str, user=Depends(get_crm_user)):
    """Push this deal's registered equipment into the customer's OWN Pulse
    portal (crm2_companies.tenant_org_id) so they can log faults from day one.
    Idempotent — already handed-over units are skipped."""
    if not _can_manage(user):
        raise HTTPException(403, "Only owners / admins / managers can hand equipment over")
    quote = await _get_quote(quote_id, user)
    portal = await _customer_portal(quote, user)
    if not portal["linked"]:
        raise HTTPException(400, "This customer isn't linked to a Pulse portal yet — link the company to a tenant org first.")
    tenant_org_id = portal["tenant_org_id"]

    # Sensible provenance for the customer-side copy:
    #  • supplier  = the SELLING org (who they bought from), not themselves
    #  • user_id   = a real user in the customer org, else left unset (never
    #                a cross-tenant seller user)
    #  • site_id   = the customer's head-office/only site, else unset
    seller_org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "name": 1},
    )
    seller_name = (seller_org or {}).get("name", "")
    owner = await db.users.find_one({"organization_id": tenant_org_id}, {"_id": 0, "id": 1})
    owner_id = (owner or {}).get("id")
    sites = await db.sites.find(
        {"organization_id": tenant_org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "is_head_office": 1},
    ).to_list(50)
    site_id = None
    if sites:
        hq = next((s for s in sites if s.get("is_head_office")), None)
        site_id = hq["id"] if hq else (sites[0]["id"] if len(sites) == 1 else None)

    # Re-pushable set: not yet handed over, OR the customer copy was deleted.
    seller_rows = await db.equipment.find(
        {"quote_id": quote_id, **_of(user)}, {"_id": 0},
    ).to_list(500)
    cust_ids = [r["customer_equipment_id"] for r in seller_rows if r.get("customer_equipment_id")]
    existing = set()
    if cust_ids:
        rows = await db.equipment.find(
            {"organization_id": tenant_org_id, "id": {"$in": cust_ids}}, {"_id": 0, "id": 1},
        ).to_list(500)
        existing = {r["id"] for r in rows}
    pending = [r for r in seller_rows if r.get("customer_equipment_id") not in existing]

    created = []
    for src in pending:
        new_id = _id()
        copy = {
            "id": new_id,
            "user_id": owner_id,
            "organization_id": tenant_org_id,
            "name": src.get("name"),
            "equipment_type": src.get("equipment_type", "gym_equipment"),
            "manufacturer": src.get("manufacturer", ""),
            "model": src.get("model", ""),
            "serial_number": src.get("serial_number"),
            "purchase_date": src.get("purchase_date"),
            "purchase_cost": src.get("purchase_cost", 0),
            "supplier": seller_name or src.get("supplier", ""),
            "status": "active",
            "site_id": site_id,
            "manuals": [],
            # Warranty sold on the deal (carried to the customer's copy).
            "warranty_tier": src.get("warranty_tier"),
            "warranty_months": src.get("warranty_months"),
            "warranty_start": src.get("warranty_start"),
            "warranty_expiry": src.get("warranty_expiry"),
            # Provenance back to the selling deal.
            "source": "deal_handover",
            "origin_org_id": user.get("organization_id"),
            "origin_equipment_id": src["id"],
            "quote_id": quote_id,
            "quote_number": quote.get("quote_number", ""),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.equipment.insert_one(dict(copy))
        await db.equipment.update_one(
            {"id": src["id"], **_of(user)},
            {"$set": {"handed_over_at": _now(), "customer_org_id": tenant_org_id,
                      "customer_equipment_id": new_id, "updated_at": _now()}},
        )
        created.append({"id": new_id, "name": copy["name"], "serial_number": copy["serial_number"]})

    await _audit(user, quote_id, "customer_handover", {"count": len(created), "tenant_org_id": tenant_org_id})
    return {
        "handed_over": created,
        "customer_portal": await _customer_portal(quote, user),
    }


# ── Branded handover pack PDF ──────────────────────────────────────


async def _fault_instructions(quote: dict, user: dict) -> dict:
    """How the customer logs a fault. If their company is linked to a Pulse
    portal, point them at the portal; always include a service-desk contact
    fallback."""
    portal = await _customer_portal(quote, user)
    out: dict = {"phone": "", "email": ""}
    if portal.get("tenant_org_id"):
        from utils.brand_urls import app_url_for_org
        org = await db.organizations.find_one(
            {"id": portal["tenant_org_id"]}, {"_id": 0, "account_type": 1})
        out["portal_url"] = app_url_for_org(org)
    # Service-desk contact — prefer the selling org's default supplier
    # (Pulse) contact details from the shared doc template.
    from utils.pulse_doc_template import PULSE
    out["phone"] = PULSE.get("phone", "")
    out["email"] = PULSE.get("email", "")
    return out


@router.get("/{quote_id}/handover/pack")
async def handover_pack_pdf(quote_id: str, user=Depends(get_crm_user)):
    """Branded customer Handover Pack PDF — equipment list + serials, the
    warranty sold against each unit, and how to log a fault. Available as
    soon as equipment has been registered on the deal (GRN)."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from routes.crm_v2 import _resolve_crm_brand
    from utils.handover_pack_pdf import build_handover_pack_pdf

    quote = await _get_quote(quote_id, user)
    equipment = await db.equipment.find(
        {"quote_id": quote_id, **_of(user)},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "manufacturer": 1,
         "model": 1, "warranty_tier": 1, "warranty_months": 1,
         "warranty_start": 1, "warranty_expiry": 1, "purchase_date": 1},
    ).sort("created_at", 1).to_list(500)
    if not equipment:
        raise HTTPException(400, "No equipment registered on this deal yet — receive goods (GRN) first.")

    # Backfill warranty for legacy GRN equipment created before tiers existed.
    from utils.warranty import get_tier, compute_expiry
    for e in equipment:
        if not e.get("warranty_expiry"):
            t = get_tier(e.get("warranty_tier"))
            start = e.get("warranty_start") or e.get("purchase_date")
            e["warranty_expiry"] = compute_expiry(start, t["months"])

    brand = await _resolve_crm_brand(user)
    faults = await _fault_instructions(quote, user)
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "mod_force": 1, "account_type": 1})
    is_mod = bool((org or {}).get("mod_force") or (org or {}).get("account_type") == "mod_site")

    pdf = build_handover_pack_pdf(
        brand=brand,
        quote=quote,
        company_name=quote.get("company_name", ""),
        equipment=equipment,
        fault_instructions=faults,
        is_mod=is_mod,
    )
    safe = (quote.get("quote_number") or "handover").replace("/", "-")
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-handover-pack.pdf"'},
    )


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
