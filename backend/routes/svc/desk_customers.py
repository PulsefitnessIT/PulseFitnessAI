"""
Provider-native desk Customers — Iter 256.

The Service Desk "Customers" tab for self-serve providers shows their
FIELD-SERVICE customers (`svc_engineer_customers` — the same book the
Engineer App and the import wizard write to), not platform organisations.

The Engineer App's own customers API (`/svc/engineer/customers`) is gated
by `require_engineer_app_access`, which a desk OWNER (no svc_engineers
row, no partner enrolment) fails with a 402 — hence this thin desk-scoped
surface guarded by `require_service_desk` instead. Reuses the Engineer
Lite CRM schema (CustomerIn/_to_doc) so both surfaces stay in sync.

    GET    /api/service-desk/provider-customers            — list/search
    POST   /api/service-desk/provider-customers            — create
    GET    /api/service-desk/provider-customers/{id}       — detail + recent cases
    PATCH  /api/service-desk/provider-customers/{id}       — update
    DELETE /api/service-desk/provider-customers/{id}       — remove
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.security_plus import safe_regex, safe_regex_exact
from utils.service_desk_auth import require_service_desk, log_desk_action
from routes.svc.engineer_customers import CustomerIn, CustomerPatch, _to_doc

router = APIRouter(prefix="/service-desk/provider-customers",
                   tags=["Service Desk · Provider Customers"])


def _of(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get(org_id: str, customer_id: str) -> dict:
    doc = await db.svc_engineer_customers.find_one(
        {"id": customer_id, "organization_id": org_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Customer not found")
    return doc


@router.get("")
async def list_customers(
    q: str = Query("", max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_service_desk),
) -> dict:
    org_id = _of(user)
    query: dict = {"organization_id": org_id}
    needle = q.strip()
    if needle:
        query["$or"] = [
            {"name": safe_regex(needle)},
            {"email": safe_regex(needle)},
            {"phone": safe_regex(needle)},
            {"site_name": safe_regex(needle)},
            {"postcode": safe_regex(needle)},
        ]
    cur = (db.svc_engineer_customers.find(query, {"_id": 0})
           .sort("updated_at", -1).skip(skip).limit(limit))
    rows = await cur.to_list(limit)
    total = await db.svc_engineer_customers.count_documents(query)
    return {"customers": rows, "total": total}


def _case_match(org_id: str, customer: dict) -> dict:
    ors: list[dict] = []
    if customer.get("email"):
        ors.append({"customer_email": customer["email"]})
    if customer.get("name"):
        ors.append({"customer_name": safe_regex_exact(customer["name"])})
    if not ors:
        return {"organization_id": org_id, "id": "__none__"}
    return {"organization_id": org_id, "$or": ors}


@router.get("/{customer_id}")
async def get_customer(customer_id: str, user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    doc = await _get(org_id, customer_id)
    case_q = _case_match(org_id, doc)
    cases = await (db.svc_cases.find(
        case_q, {"_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1,
                 "priority": 1, "created_at": 1, "closed_at": 1})
        .sort("created_at", -1).limit(10)).to_list(10)
    case_count = await db.svc_cases.count_documents(case_q)
    return {"customer": doc, "recent_cases": cases, "case_count": case_count}


@router.post("", status_code=201)
async def create_customer(payload: CustomerIn, user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    doc = _to_doc(payload, org_id=org_id, user_id=user.get("id") or "")
    doc["source"] = "desk"
    await db.svc_engineer_customers.insert_one(doc)
    doc.pop("_id", None)
    await log_desk_action(
        actor=user, action="provider_customer.create", target_type="customer",
        target_id=doc["id"], summary=f"Added customer {doc['name']}")
    return {"customer": doc}


@router.patch("/{customer_id}")
async def update_customer(customer_id: str, payload: CustomerPatch,
                          user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    await _get(org_id, customer_id)
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = _now()
    await db.svc_engineer_customers.update_one(
        {"id": customer_id, "organization_id": org_id}, {"$set": update})
    doc = await _get(org_id, customer_id)
    await log_desk_action(
        actor=user, action="provider_customer.update", target_type="customer",
        target_id=customer_id, summary=f"Updated customer {doc.get('name', '')}",
        details={"fields": list(update.keys())})
    return {"customer": doc}


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str, user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    doc = await _get(org_id, customer_id)
    await db.svc_engineer_customers.delete_one({"id": customer_id, "organization_id": org_id})
    await log_desk_action(
        actor=user, action="provider_customer.delete", target_type="customer",
        target_id=customer_id, summary=f"Deleted customer {doc.get('name', '')}")
    return {"ok": True}


__all__ = ["router"]
