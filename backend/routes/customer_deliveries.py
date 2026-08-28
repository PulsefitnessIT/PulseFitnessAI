"""
Customer-facing DELIVERIES & INSTALLATIONS view.

Surfaced inside the operator's own Pulse dashboard (Lite/Pro/Full) — NOT a separate
portal. When a dealer/Pulse-team member links a distribution customer (crm2_companies)
to that customer's Pulse organisation, the customer sees their upcoming installs,
status, warranty and Installation Certificate right in their normal dashboard.

Read-only and customer-safe: no internal H&S risks, drawings, logistics notes or
margins. Scoping is strict — a customer only ever sees installs for companies whose
`linked_operator_org_id` equals their own organisation_id.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from utils.auth import get_current_user
from utils.database import db, get_object

router = APIRouter(prefix="/customer", tags=["Customer · Deliveries & Installations"])
logger = logging.getLogger(__name__)

_CUSTOMER_STATUSES = ["awaiting_installation", "installation_in_progress", "active"]


async def _linked_company_ids(org_id: str) -> list[str]:
    rows = await db.crm2_companies.find(
        {"linked_operator_org_id": org_id}, {"_id": 0, "id": 1}).to_list(500)
    return [r["id"] for r in rows]


@router.get("/deliveries")
async def my_deliveries(user=Depends(get_current_user)):
    """Deliveries/installs for the signed-in operator's linked customer records."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"has_deliveries": False, "deliveries": []}
    company_ids = await _linked_company_ids(org_id)
    if not company_ids:
        return {"has_deliveries": False, "deliveries": []}
    allocs = await db.dealer_customer_allocations.find(
        {"customer_company_id": {"$in": company_ids}, "status": {"$in": _CUSTOMER_STATUSES}},
        {"_id": 0},
    ).sort("planned_install_date", 1).limit(500).to_list(500)

    out = []
    for a in allocs:
        completed = a.get("status") == "active"
        warranty = None
        certificate = False
        if completed:
            w = await db.warranty_activation_events.find_one(
                {"unit_id": a.get("unit_id")}, {"_id": 0, "warranty_start": 1, "warranty_end": 1})
            warranty = w or None
            rec = await db.installation_commissioning_records.find_one(
                {"allocation_id": a.get("id")}, {"_id": 0, "certificate_storage_path": 1})
            certificate = bool(rec and rec.get("certificate_storage_path"))
        out.append({
            "id": a.get("id"),
            "reference": a.get("reference"),
            "model": a.get("model") or a.get("product_code"),
            "product_code": a.get("product_code"),
            "serial_number": a.get("serial_number"),
            "site": a.get("customer_site"),
            "planned_install_date": a.get("planned_install_date"),
            "install_window": a.get("install_window"),
            "status": a.get("status"),
            "installed_at": a.get("installed_at"),
            "warranty": warranty,
            "certificate": certificate,
            "certificate_url": (f"/api/customer/deliveries/{a.get('id')}/certificate" if certificate else None),
        })
    return {"has_deliveries": len(out) > 0, "count": len(out), "deliveries": out}


@router.get("/deliveries/summary")
async def my_deliveries_summary(user=Depends(get_current_user)):
    """Lightweight flag used to show/hide the Deliveries nav item."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"has_deliveries": False, "count": 0}
    company_ids = await _linked_company_ids(org_id)
    if not company_ids:
        return {"has_deliveries": False, "count": 0}
    count = await db.dealer_customer_allocations.count_documents(
        {"customer_company_id": {"$in": company_ids}, "status": {"$in": _CUSTOMER_STATUSES}})
    return {"has_deliveries": count > 0, "count": count}


@router.get("/deliveries/{alloc_id}/certificate")
async def my_delivery_certificate(alloc_id: str, user=Depends(get_current_user)):
    """Stream the Installation Certificate for one of the customer's linked installs."""
    company_ids = await _linked_company_ids(user.get("organization_id"))
    a = await db.dealer_customer_allocations.find_one(
        {"id": alloc_id, "customer_company_id": {"$in": company_ids}}, {"_id": 0, "id": 1})
    if not a:
        raise HTTPException(404, "Delivery not found")
    rec = await db.installation_commissioning_records.find_one(
        {"allocation_id": alloc_id}, {"_id": 0, "certificate_storage_path": 1, "certificate_filename": 1})
    if not rec or not rec.get("certificate_storage_path"):
        raise HTTPException(404, "No certificate available yet")
    data, _ct = await run_in_threadpool(get_object, rec["certificate_storage_path"])
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{rec.get("certificate_filename", "installation-certificate.pdf")}"'})


# ── Warranty register (customer-facing) ─────────────────────────────
#
# Shows the signed-in customer their live equipment warranties + cover-until
# dates, right in their own Pulse dashboard. Reads their org's own
# ``equipment`` records (warranty stamped on the deal handover / GRN), so it
# is strictly org-scoped and read-only.

_EXPIRING_DAYS = 60


def _warranty_row(e: dict) -> dict | None:
    """Shape one equipment doc into a warranty-register row with computed
    status. Returns None if the item carries no warranty information."""
    from datetime import datetime, timezone
    from utils.warranty import get_tier, compute_expiry

    tier_code = e.get("warranty_tier")
    expiry = e.get("warranty_expiry")
    if not expiry and (tier_code or e.get("warranty_start")):
        months = e.get("warranty_months") or get_tier(tier_code)["months"]
        expiry = compute_expiry(e.get("warranty_start") or e.get("purchase_date"), int(months))
    if not expiry and not tier_code:
        return None  # no warranty data → not shown

    tier = get_tier(tier_code) if tier_code else None
    days_remaining = None
    status = "unknown"
    if expiry:
        try:
            end = datetime.strptime(str(expiry)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_remaining = (end - datetime.now(timezone.utc)).days
            status = "expired" if days_remaining < 0 else ("expiring" if days_remaining <= _EXPIRING_DAYS else "active")
        except Exception:
            pass
    return {
        "id": e.get("id"),
        "name": e.get("name") or "Equipment",
        "manufacturer": e.get("manufacturer") or "",
        "model": e.get("model") or "",
        "serial_number": e.get("serial_number") or "",
        "warranty_tier": tier_code or "",
        "warranty_label": (tier or {}).get("label") or "Manufacturer warranty",
        "warranty_summary": (tier or {}).get("summary") or "",
        "warranty_start": e.get("warranty_start") or e.get("purchase_date"),
        "warranty_expiry": expiry,
        "days_remaining": days_remaining,
        "status": status,
    }


@router.get("/warranties")
async def my_warranties(user=Depends(get_current_user)):
    """The signed-in customer's equipment warranties with live cover status."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"has_warranties": False, "warranties": [], "counts": {}}
    rows = await db.equipment.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1,
         "serial_number": 1, "warranty_tier": 1, "warranty_months": 1,
         "warranty_start": 1, "warranty_expiry": 1, "purchase_date": 1},
    ).limit(1000).to_list(1000)
    out = [w for w in (_warranty_row(e) for e in rows) if w]
    # Sort: expiring/expired first (soonest cover-end), then active.
    out.sort(key=lambda w: (w["days_remaining"] is None, w["days_remaining"] if w["days_remaining"] is not None else 1e9))
    counts = {
        "total": len(out),
        "active": sum(1 for w in out if w["status"] == "active"),
        "expiring": sum(1 for w in out if w["status"] == "expiring"),
        "expired": sum(1 for w in out if w["status"] == "expired"),
    }
    # Is there already an open aftersales enquiry for this customer? (last 30 days)
    enquiry_open = False
    if counts["expiring"] or counts["expired"]:
        from datetime import datetime, timezone, timedelta
        company = await _linked_company(org_id)
        if company:
            since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            hit = await db.crm2_contracts.find_one({
                "organization_id": company.get("organization_id"),
                "company_id": company.get("id"),
                "source": "customer_warranty_enquiry", "status": "draft",
                "created_at": {"$gte": since},
            }, {"_id": 1})
            enquiry_open = bool(hit)
    return {"has_warranties": len(out) > 0, "warranties": out, "counts": counts, "renewal_enquiry_open": enquiry_open}


@router.get("/warranties/summary")
async def my_warranties_summary(user=Depends(get_current_user)):
    """Lightweight flag + counts to show/hide the Warranties nav item."""
    res = await my_warranties(user)
    return {"has_warranties": res["has_warranties"], "counts": res["counts"]}


# ── Service & Calibration Certificates (customer-facing) ────────────
#
# Shows the signed-in customer the completed Blue Light Service & Calibration
# certificates for their stations, with the next service-due date. Read-only
# and strictly scoped to the CRM companies linked to the customer's org.
# Reuses the existing crm2_certificates store (no duplicate document system).

_CUSTOMER_CERT_STATUSES = ("sent", "generated")


async def _customer_contract_map(org_id: str) -> dict:
    """{contract_id: {number, title}} for Blue Light contracts of the linked companies."""
    company_ids = await _linked_company_ids(org_id)
    if not company_ids:
        return {}
    rows = await db.crm2_contracts.find(
        {"company_id": {"$in": company_ids}, "is_blue_light": True},
        {"_id": 0, "id": 1, "contract_number": 1, "title": 1}).to_list(500)
    return {r["id"]: {"contract_number": r.get("contract_number"), "title": r.get("title")} for r in rows}


@router.get("/certificates")
async def my_certificates(search: str = "", contract_id: str = "",
                          date_from: str = "", date_to: str = "",
                          user=Depends(get_current_user)):
    """The customer's completed station Service & Calibration certificates."""
    org_id = user.get("organization_id")
    cmap = await _customer_contract_map(org_id)
    if not cmap:
        return {"has_certificates": False, "certificates": [], "count": 0, "next_service_due": ""}
    q = {"contract_id": {"$in": list(cmap.keys())}, "status": {"$in": list(_CUSTOMER_CERT_STATUSES)}}
    if contract_id:
        q["contract_id"] = contract_id
    certs = await db.crm2_certificates.find(q, {"_id": 0}).sort("generated_at", -1).to_list(2000)
    visit_ids = [c["visit_id"] for c in certs if c.get("visit_id")]
    visits = {}
    if visit_ids:
        async for v in db.crm2_station_visits.find(
                {"id": {"$in": visit_ids}}, {"_id": 0, "id": 1, "completed_at": 1, "next_service_due": 1}):
            visits[v["id"]] = v
    out = []
    for c in certs:
        v = visits.get(c.get("visit_id"), {})
        service_date = (v.get("completed_at") or c.get("generated_at") or "")[:10]
        row = {
            "id": c["id"], "station_name": c.get("station_name", ""),
            "filename": c.get("filename", ""),
            "contract_number": cmap.get(c["contract_id"], {}).get("contract_number", ""),
            "service_date": service_date,
            "next_service_due": v.get("next_service_due", ""),
            "status": c.get("status"),
        }
        if search and search.lower() not in (row["station_name"] or "").lower():
            continue
        if date_from and service_date and service_date < date_from:
            continue
        if date_to and service_date and service_date > date_to:
            continue
        out.append(row)
    future = sorted([r["next_service_due"] for r in out if r["next_service_due"]])
    return {"has_certificates": len(out) > 0, "certificates": out, "count": len(out),
            "next_service_due": future[0] if future else "",
            "contracts": [{"id": k, **v} for k, v in cmap.items()]}


@router.get("/certificates/summary")
async def my_certificates_summary(user=Depends(get_current_user)):
    """Lightweight flag + count to show/hide the Certificates nav item."""
    org_id = user.get("organization_id")
    cmap = await _customer_contract_map(org_id)
    if not cmap:
        return {"has_certificates": False, "count": 0}
    n = await db.crm2_certificates.count_documents(
        {"contract_id": {"$in": list(cmap.keys())}, "status": {"$in": list(_CUSTOMER_CERT_STATUSES)}})
    return {"has_certificates": n > 0, "count": n}


@router.get("/certificates/{cert_id}/download")
async def my_certificate_download(cert_id: str, user=Depends(get_current_user)):
    """Stream one of the customer's station certificates (scope-checked)."""
    import base64
    org_id = user.get("organization_id")
    cmap = await _customer_contract_map(org_id)
    cert = await db.crm2_certificates.find_one({"id": cert_id}, {"_id": 0})
    if not cert or cert.get("contract_id") not in cmap or cert.get("status") not in _CUSTOMER_CERT_STATUSES:
        raise HTTPException(404, "Certificate not found")
    f = await db.crm2_certificate_files.find_one({"cert_id": cert_id}, {"_id": 0, "pdf_b64": 1})
    if not f:
        raise HTTPException(404, "Certificate file not available")
    return Response(content=base64.b64decode(f["pdf_b64"]), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{cert.get("filename", "certificate.pdf")}"'})



async def _linked_company(org_id: str) -> dict | None:
    """The single CRM company (seller-side record) linked to this customer org."""
    if not org_id:
        return None
    return await db.crm2_companies.find_one(
        {"$or": [{"linked_operator_org_id": org_id}, {"tenant_org_id": org_id}]}, {"_id": 0})


@router.post("/warranties/enquire")
async def enquire_aftersales(data: dict = None, user=Depends(get_current_user)):
    """Customer-raised aftersales / warranty-renewal enquiry. Creates a DRAFT
    aftersales contract on the seller's side (ties into the existing contracts
    system) + a follow-up task for the account owner, and emails the owner a
    heads-up. De-duplicated within 24h per customer."""
    import uuid
    from datetime import datetime, timezone, timedelta
    data = data or {}
    org_id = user.get("organization_id")
    company = await _linked_company(org_id)
    if not company:
        raise HTTPException(400, "Your account isn't linked to a supplier yet — please contact Pulse Fitness directly.")

    seller_org = company.get("organization_id")
    company_id = company.get("id")
    company_name = company.get("name") or "Customer"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Resolve the equipment referenced (must belong to the customer's org).
    eq_ids = [e for e in (data.get("equipment_ids") or []) if isinstance(e, str)]
    eq_query = {"organization_id": org_id}
    if eq_ids:
        eq_query["id"] = {"$in": eq_ids}
    equipment = await db.equipment.find(
        eq_query, {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "warranty_expiry": 1},
    ).limit(100).to_list(100)
    eq_lines = "; ".join(
        f"{e.get('name', 'Equipment')}"
        + (f" (S/N {e['serial_number']})" if e.get("serial_number") else "")
        + (f", cover until {e['warranty_expiry']}" if e.get("warranty_expiry") else "")
        for e in equipment
    ) or "All equipment on account"
    note = (data.get("message") or "").strip()
    # Customer-selectable cover level (team finalises). Default Bronze.
    _ALLOWED_TIERS = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold"}
    tier = (data.get("preferred_tier") or "bronze").strip().lower()
    if tier not in _ALLOWED_TIERS:
        tier = "bronze"
    tier_label = _ALLOWED_TIERS[tier]

    # De-dupe: reuse an open enquiry contract raised in the last 24h.
    since = (now - timedelta(hours=24)).isoformat()
    existing = await db.crm2_contracts.find_one({
        "organization_id": seller_org, "company_id": company_id,
        "source": "customer_warranty_enquiry", "status": "draft",
        "created_at": {"$gte": since},
    }, {"_id": 0, "id": 1})
    if existing:
        return {"ok": True, "status": "already_requested", "contract_id": existing["id"]}

    owner_id = company.get("owner_id") or ""
    owner = await db.users.find_one({"id": owner_id}, {"_id": 0, "full_name": 1, "email": 1}) if owner_id else None
    if not owner:
        owner = await db.users.find_one({"organization_id": seller_org, "role": "owner"}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})
        owner_id = (owner or {}).get("id") or owner_id
    owner_name = (owner or {}).get("full_name") or ""

    # 1) Draft aftersales contract (Bronze) — team prices & sends.
    contract_id = str(uuid.uuid4())
    contract = {
        "id": contract_id, "organization_id": seller_org,
        "contract_number": f"CTR-{str(uuid.uuid4())[:6].upper()}",
        "title": f"Aftersales cover — {company_name} (warranty renewal)",
        "type": "service", "tier": tier, "status": "draft",
        "company_id": company_id, "company_name": company_name,
        "contact_id": "", "contact_name": user.get("full_name", ""),
        "annual_value": 0.0, "total_value": 0.0,
        "billing_frequency": "annual", "auto_renew": False, "renewal_notice_days": 90,
        "sla": {"response_hours": 8, "resolution_hours": 48, "parts_included": False,
                "labour_included": True, "preventive_maintenance": False},
        "coverage_notes": f"Raised from a customer warranty-renewal enquiry via their Pulse portal.\n"
                          f"Preferred cover level: {tier_label}.\nEquipment: {eq_lines}."
                          + (f"\nCustomer note: {note}" if note else ""),
        "source": "customer_warranty_enquiry",
        "enquiry_equipment_ids": [e["id"] for e in equipment],
        "version": 1,
        "created_by": f"{company_name} (customer portal)",
        "owner_id": owner_id, "owner_name": owner_name,
        "created_at": now_iso, "updated_at": now_iso,
    }
    await db.crm2_contracts.insert_one({**contract})

    # 2) Follow-up task for the account owner.
    task_body = (f"{company_name} has enquired about aftersales / warranty-renewal cover via their Pulse portal.\n"
                 f"Preferred cover level: {tier_label}.\nEquipment: {eq_lines}." + (f"\nCustomer note: {note}" if note else "")
                 + f"\nA draft contract ({contract['contract_number']}) has been created — price & send.")
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": seller_org,
        "type": "task", "subject": f"Aftersales cover enquiry — {company_name}",
        "body": task_body, "company_id": company_id, "contract_id": contract_id,
        "owner_id": owner_id, "owner_name": owner_name, "assigned_to": owner_id,
        "status": "open", "priority": "high",
        "due_date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
        "source": "customer_warranty_enquiry",
        "created_at": now_iso, "updated_at": now_iso,
    })

    # 3) Best-effort email heads-up to the account owner.
    if (owner or {}).get("email"):
        try:
            from utils.email import send_email, wrap_branded
            html = await wrap_branded(
                f"<p>Hi {owner_name.split(' ')[0] if owner_name else 'there'},</p>"
                f"<p><b>{company_name}</b> has asked about aftersales / warranty-renewal cover "
                f"through their Pulse portal.</p>"
                f"<p><b>Preferred cover level:</b> {tier_label}</p>"
                f"<p><b>Equipment:</b> {eq_lines}</p>"
                + (f"<p><b>Their note:</b> {note}</p>" if note else "")
                + f"<p>A draft contract <b>{contract['contract_number']}</b> is ready in the CRM to price and send.</p>",
                seller_org)
            await send_email(to=owner["email"],
                             subject=f"Aftersales cover enquiry — {company_name}",
                             html=html, kind="ops_notification")
        except Exception:
            logger.warning("aftersales enquiry heads-up email failed", exc_info=True)

    return {"ok": True, "status": "requested", "contract_id": contract_id}


@router.get("/warranties/certificate")
async def warranty_certificate_pdf(user=Depends(get_current_user)):
    """One consolidated, branded warranty certificate for the customer's whole
    kit list — grouped by warranty level with serials + cover-until dates."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from utils.warranty_certificate_pdf import build_warranty_certificate_pdf

    org_id = user.get("organization_id")
    rows = await db.equipment.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1,
         "serial_number": 1, "warranty_tier": 1, "warranty_months": 1,
         "warranty_start": 1, "warranty_expiry": 1, "purchase_date": 1},
    ).limit(1000).to_list(1000)
    equipment = [w for w in (_warranty_row(e) for e in rows) if w]
    if not equipment:
        raise HTTPException(400, "No warranties on record to certify yet.")
    equipment.sort(key=lambda w: (w["days_remaining"] is None, w["days_remaining"] if w["days_remaining"] is not None else 1e9))

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    customer_name = (org or {}).get("name") or user.get("full_name") or "Customer"
    pdf = build_warranty_certificate_pdf(customer_name=customer_name, equipment=equipment)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in customer_name)[:40] or "warranty"
    return StreamingResponse(
        BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-warranty-certificate.pdf"'},
    )
