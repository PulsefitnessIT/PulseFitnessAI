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
