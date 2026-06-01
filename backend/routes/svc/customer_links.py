"""Iter 220ea·26 (G1) — Canonical customer link between Service Ops and CRM.

The same gym historically lived as up to four unlinked records: the live
v2 CRM company (``crm2_companies``), a v1 Sage shadow (``crm_companies``),
the engineer's saved book (``svc_engineer_customers``) and a free-text
``customer_name`` string on ``svc_cases``. Nothing shared an id, so links
were re-derived from names every time.

This module adds the shared spine:

  * ``GET  /api/svc/customers/crm-search?q=`` — search the org's CRM (v2)
    companies so the Service Desk / engineer app can pick the canonical
    customer to link. Uses the regular service auth (``get_current_user``)
    so it works from both the office portal and the engineer PWA.
  * ``POST /api/svc/admin/customers/backfill-crm-links`` — one-shot (and
    idempotent) backfill that stamps ``company_id`` onto existing
    ``svc_cases`` and ``svc_engineer_customers`` by matching name/email.

New writes auto-link via ``utils.svc_crm_sync.find_company_id`` (wired into
intake + engineer-customer create). Reads expose ``company_id`` already
because the field lives on the stored doc.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.svc_crm_sync import _re_escape, find_company_id, push_customer_to_crm

router = APIRouter(prefix="/svc", tags=["Service Ops · CRM Customer Link"])


def _org(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _can_manage(user: dict) -> bool:
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("account_type") == "gymaxis_admin"
        or (user.get("role") or "") in {"owner", "owner_admin", "manager"}
    )


@router.get("/customers/crm-search")
async def crm_company_search(q: str = "", limit: int = 10, user=Depends(get_current_user)):
    """Search the org's live CRM (v2) companies for the link picker."""
    org = _org(user)
    q = (q or "").strip()
    limit = max(1, min(limit, 25))
    query: dict = {"organization_id": org}
    if q:
        rx = {"$regex": _re_escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"email": rx}, {"postcode": rx}]
    rows = await db.crm2_companies.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "postcode": 1,
         "sage_customer_id": 1},
    ).sort("name", 1).limit(limit).to_list(limit)
    return {"companies": rows}


@router.post("/admin/customers/backfill-crm-links")
async def backfill_crm_links(user=Depends(get_current_user)):
    """Stamp ``company_id`` onto service cases + engineer customers that
    don't have one yet, matching by name/email against the v2 CRM.
    Idempotent — only touches rows where ``company_id`` is missing."""
    if not _can_manage(user):
        raise HTTPException(403, "Owners, managers and admins only")
    org = _org(user)
    of = {"organization_id": org}

    async def _link(collection, name_field, email_field, postcode_field):
        linked = unmatched = 0
        cursor = collection.find(
            {**of, "$or": [{"company_id": {"$exists": False}}, {"company_id": ""},
                           {"company_id": None}]},
            {"_id": 0, "id": 1, name_field: 1, email_field: 1, postcode_field: 1},
        )
        async for row in cursor:
            cid = await find_company_id(
                org,
                name=row.get(name_field) or "",
                email=row.get(email_field) or "",
                postcode=row.get(postcode_field) or "",
            )
            if cid:
                await collection.update_one(
                    {**of, "id": row["id"]}, {"$set": {"company_id": cid}})
                linked += 1
            else:
                unmatched += 1
        return linked, unmatched

    cases_linked, cases_unmatched = await _link(
        db.svc_cases, "customer_name", "customer_email", "site_postcode")
    cust_linked, cust_unmatched = await _link(
        db.svc_engineer_customers, "name", "email", "postcode")

    return {
        "ok": True,
        "cases": {"linked": cases_linked, "unmatched": cases_unmatched},
        "customers": {"linked": cust_linked, "unmatched": cust_unmatched},
    }

@router.post("/customers/{customer_id}/push-to-crm")
async def push_customer(customer_id: str, user=Depends(get_current_user)):
    """Iter 220ea·26 (G4) — reconcile one field-added service customer
    into the CRM: link to an existing CRM company if one matches, else
    create a new CRM company. Idempotent (no-op if already linked)."""
    org = _org(user)
    cust = await db.svc_engineer_customers.find_one(
        {"organization_id": org, "id": customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(404, "Customer not found")
    return await push_customer_to_crm(cust, user=user)


@router.post("/admin/customers/push-unlinked-to-crm")
async def push_unlinked_customers(user=Depends(get_current_user)):
    """Iter 220ea·26 (G4) — bulk reconcile: push every field-added
    customer that isn't yet linked to the CRM. Counterpart to the G1
    backfill (which only links to *existing* CRM companies — this also
    *creates* CRM companies for genuinely new field customers)."""
    if not _can_manage(user):
        raise HTTPException(403, "Owners, managers and admins only")
    org = _org(user)
    created = linked = skipped = 0
    cursor = db.svc_engineer_customers.find(
        {"organization_id": org,
         "$or": [{"company_id": {"$exists": False}}, {"company_id": ""},
                 {"company_id": None}]},
        {"_id": 0},
    )
    async for cust in cursor:
        res = await push_customer_to_crm(cust, user=user)
        if res.get("created"):
            created += 1
        elif res.get("linked"):
            linked += 1
        else:
            skipped += 1
    return {"ok": True, "created": created, "linked": linked, "skipped": skipped}




__all__ = ["router"]
