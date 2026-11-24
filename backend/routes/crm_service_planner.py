"""Contract Management Service Planner — contractual obligations linked to the
existing Service Desk (bookings, engineers, completions). No second planner:
bookings are ordinary Service Desk PPM cases carrying ``contract_obligation_id``."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.crm_auth import get_crm_user
from routes.crm_workspace import require_crm_perm
from utils.cm_service_link import (CANCELLED_CASE, _brief, _hist, candidate_cases, link_case, obligation_bucket,
                                   sync_all, sync_contract)
from utils.crm_audit import record_audit
from utils.database import db

router = APIRouter(prefix="/crm/v2/aftersales", tags=["Contract Service Planner"])
BUCKETS = ("due", "booked", "completed", "overdue", "review", "planned")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _org(user) -> str:
    return user.get("organization_id")


async def _contract(user, cid: str) -> dict:
    c = await db.crm2_contracts.find_one({"id": cid, "organization_id": _org(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    return c


async def _visit(user, cid: str, oid: str) -> tuple[dict, dict]:
    sched = await db.crm2_afs_service_schedules.find_one({"contract_id": cid, "organization_id": _org(user)}, {"_id": 0})
    v = next((x for x in (sched or {}).get("visits") or [] if x.get("obligation_id") == oid), None)
    if not v:
        raise HTTPException(404, "Service obligation not found")
    return sched, v


async def _save_visit(user, cid: str, oid: str, v: dict) -> None:
    await db.crm2_afs_service_schedules.update_one(
        {"contract_id": cid, "organization_id": _org(user), "visits.obligation_id": oid},
        {"$set": {"visits.$": v, "updated_at": _now()}, "$inc": {"rev": 1}})


@router.get("/service-planner")
async def service_planner(bucket: str = "", q: str = "", user=Depends(require_crm_perm("service.read"))):
    org = _org(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows, totals, sites = [], {b: 0 for b in BUCKETS}, {}
    open_actions = {}
    async for a in db.crm2_activities.find({"organization_id": org, "status": "open", "obligation_id": {"$exists": True}},
                                           {"_id": 0, "obligation_id": 1, "subject": 1, "owner_name": 1}):
        open_actions.setdefault(a["obligation_id"], a)
    async for c in db.crm2_contracts.find({"organization_id": org, "status": "active"}, {"_id": 0}):
        if not await db.crm2_afs_service_schedules.count_documents({"contract_id": c["id"], "organization_id": org}, limit=1):
            continue
        visits = (await sync_contract(org, c, today=today))["visits"]
        last_done = {}
        for v in visits:
            d = (v.get("completion") or {}).get("completed_date")
            if d and d > last_done.get(v.get("site_id"), ""):
                last_done[v.get("site_id")] = d
        for v in visits:
            b = obligation_bucket(v, today)
            if b == "excluded":
                continue
            totals[b] += 1
            sid = v.get("site_id")
            if sid and sid not in sites:
                s = await db.sites.find_one({"id": sid}, {"_id": 0, "name": 1, "postcode": 1}) or {}
                sites[sid] = " · ".join(x for x in (s.get("name"), s.get("postcode")) if x)
            act = open_actions.get(v["obligation_id"])
            rows.append({
                "obligation_id": v["obligation_id"], "contract_id": c["id"], "contract_number": c.get("contract_number"),
                "company_id": c.get("company_id"), "customer": c.get("company_name") or c.get("title"),
                "site_id": sid, "site": sites.get(sid) or ("Contract-wide" if v.get("scope") == "contract" else "—"),
                "scope": v.get("scope"), "machines": len(v.get("equipment_ids") or []),
                "due_date": v.get("planned_date"), "year": v.get("year"), "visit_no": v.get("visit_no"),
                "status": v.get("status") or "planned", "bucket": b,
                "booking_date": v.get("booked_for"), "engineer": v.get("engineer_name") or "",
                "case_id": v.get("case_id"), "case_reference": v.get("case_reference"),
                "completed_date": (v.get("completion") or {}).get("completed_date"),
                "last_completed": last_done.get(sid), "review_reason": v.get("review_reason") or (
                    "scope" if v.get("scope_review") else None),
                "review_candidates": v.get("review_candidates") or [],
                "cancelled_without_replacement": bool(v.get("cancelled_without_replacement")),
                "action": (act or {}).get("subject"), "action_owner": (act or {}).get("owner_name"),
            })
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in " ".join(str(r.get(k) or "") for k in
                                                   ("customer", "site", "contract_number", "case_reference", "engineer")).lower()]
    if bucket:
        rows = [r for r in rows if r["bucket"] == bucket]
    rows.sort(key=lambda r: (r["due_date"] or "9999", r["customer"] or ""))
    return {"rows": rows[:500], "count": len(rows), "totals": totals, "today": today}


@router.post("/service-planner/sync")
async def service_planner_sync(user=Depends(require_crm_perm("service.read"))):
    return await sync_all(_org(user))


@router.get("/service-planner/engineers")
async def planner_engineers(user=Depends(require_crm_perm("service.read"))):
    rows = await db.svc_engineers.find({"organization_id": _org(user), "status": {"$nin": ["archived", "inactive"]}},
                                       {"_id": 0, "id": 1, "full_name": 1}).sort("full_name", 1).to_list(500)
    return {"engineers": [r for r in rows if r.get("full_name")]}


class BookIn(BaseModel):
    scheduled_date: str
    engineer_id: Optional[str] = None


@router.post("/contracts/{contract_id}/obligations/{obligation_id}/book")
async def book_obligation(contract_id: str, obligation_id: str, body: BookIn,
                          user=Depends(require_crm_perm("contracts.manage"))):
    """Raise the Service Desk PPM job for one obligation — once, even if clicked twice."""
    from utils.cm_dates import parse_date
    if not parse_date(body.scheduled_date):
        raise HTTPException(400, "scheduled_date must be YYYY-MM-DD")
    org, contract = _org(user), await _contract(user, contract_id)
    sched, v = await _visit(user, contract_id, obligation_id)
    if v.get("status") in ("completed", "verified", "cancelled", "excluded"):
        raise HTTPException(400, f"This visit is already {v['status']}.")
    if v.get("case_id"):
        live = await db.svc_cases.find_one({"id": v["case_id"], "status": {"$nin": list(CANCELLED_CASE)}}, {"_id": 0})
        if live:
            return {"case_id": live["id"], "reference": live.get("reference"), "existing": True}
    canon = await db.svc_cases.find_one({"contract_obligation_id": obligation_id,
                                         "status": {"$nin": list(CANCELLED_CASE)}}, {"_id": 0})
    if canon:  # booked meanwhile in Service Desk — link, don't duplicate
        await link_case(org, contract, v, canon, "contract_obligation_reference", user.get("email") or "coordinator")
        v.update({"status": "booked", "booked_for": str(canon.get("scheduled_at") or "")[:10] or None,
                  "engineer_name": canon.get("assigned_engineer_name") or ""})
        await _save_visit(user, contract_id, obligation_id, v)
        return {"case_id": canon["id"], "reference": canon.get("reference"), "existing": True}
    lock = await db.crm2_afs_service_schedules.update_one(
        {"contract_id": contract_id, "organization_id": org,
         "visits": {"$elemMatch": {"obligation_id": obligation_id, "case_id": {"$in": [None, ""]}, "booking_lock": None}}},
        {"$set": {"visits.$.booking_lock": _now()}, "$inc": {"rev": 1}})
    if not lock.modified_count:
        _, again = await _visit(user, contract_id, obligation_id)
        if again.get("case_id"):
            return {"case_id": again["case_id"], "reference": again.get("case_reference"), "existing": True}
        raise HTTPException(409, "This visit is being booked by someone else — refresh in a moment.")
    try:
        eng = None
        if body.engineer_id:
            eng = await db.svc_engineers.find_one({"organization_id": org, "id": body.engineer_id}, {"_id": 0, "id": 1, "full_name": 1})
            if not eng:
                raise HTTPException(400, "Engineer not found")
        site = await db.sites.find_one({"id": v.get("site_id")}, {"_id": 0, "name": 1, "postcode": 1}) or {}
        from routes.svc.intake import _create_case
        case = await _create_case(payload={
            "title": f"Contract PPM · {site.get('name') or contract.get('company_name') or 'Site'}",
            "description": f"Contractual planned maintenance {contract.get('contract_number') or ''} — "
                           f"year {v.get('year')} visit {v.get('visit_no')}, due {v.get('planned_date')}.",
            "case_type": "ppm", "priority": "p3", "cover_type": "contract",
            "equipment_ids": v.get("equipment_ids") or [], "customer_name": contract.get("company_name") or "",
            "site_id": v.get("site_id") or "", "site_name": site.get("name") or "",
            "site_postcode": site.get("postcode") or "", "contract_id": contract_id, "estimated_minutes": 90,
        }, source="ppm", user=user)
        upd = {"scheduled_at": f"{body.scheduled_date}T09:00:00+00:00", "contract_obligation_id": obligation_id,
               "contract_number": contract.get("contract_number"), "service_type": "Contract PPM",
               "ppm_customer_org_id": sched.get("linked_organization_id"), "updated_at": _now()}
        if eng:
            upd.update({"assigned_engineer_ids": [eng["id"]], "assigned_engineer_id": eng["id"],
                        "assigned_engineer_name": eng["full_name"], "assigned_engineer_names": [eng["full_name"]],
                        "status": "assigned", "assigned_at": _now()})
        await db.svc_cases.update_one({"id": case["id"]}, {"$set": upd})
        v.update({"case_id": case["id"], "case_reference": case.get("reference"), "status": "booked",
                  "booked_for": body.scheduled_date, "engineer_name": (eng or {}).get("full_name") or "",
                  "engineer_id": (eng or {}).get("id") or "", "link_basis": "booked_from_contract",
                  "cancelled_without_replacement": False, "booking_lock": None})
        _hist(v, "booked", case_id=case["id"], by=user.get("email"), date=body.scheduled_date)
        await _save_visit(user, contract_id, obligation_id, v)
    except Exception:
        await db.crm2_afs_service_schedules.update_one(
            {"contract_id": contract_id, "organization_id": org, "visits.obligation_id": obligation_id},
            {"$set": {"visits.$.booking_lock": None}})
        raise
    await record_audit(entity_type="afs_service_obligation", entity_id=obligation_id, action="book", user=user,
                       extra={"contract_id": contract_id, "case_id": case["id"]})
    await sync_contract(org, contract)
    return {"case_id": case["id"], "reference": case.get("reference"), "existing": False}


class ReviewIn(BaseModel):
    action: str                 # link | not_match | accept_scope | exclude
    case_id: Optional[str] = None
    note: str = ""


@router.post("/contracts/{contract_id}/obligations/{obligation_id}/review")
async def review_obligation(contract_id: str, obligation_id: str, body: ReviewIn,
                            user=Depends(require_crm_perm("exceptions.approve"))):
    """Authorised decision on an uncertain match / scope / exclusion — audited."""
    org, contract = _org(user), await _contract(user, contract_id)
    _, v = await _visit(user, contract_id, obligation_id)
    who = user.get("email") or "manager"
    if body.action == "link":
        case = await db.svc_cases.find_one({"id": body.case_id or ""}, {"_id": 0})
        if not case or case.get("site_id") != v.get("site_id"):
            raise HTTPException(400, "Choose a Service Desk case at this obligation's site.")
        if (case.get("status") or "") in CANCELLED_CASE:
            raise HTTPException(400, "That case was cancelled.")
        if not await link_case(org, contract, v, case, "authorised_review", who):
            raise HTTPException(409, "That case is already linked to another contractual obligation.")
    elif body.action == "not_match":
        if not body.case_id:
            raise HTTPException(400, "case_id required")
        v.setdefault("rejected_cases", []).append(body.case_id)
        v.update({"review_reason": None, "review_candidates": None})
        _hist(v, "candidate_rejected", case_id=body.case_id, by=who, note=body.note)
    elif body.action == "accept_scope":
        v["scope_review"] = None
        _hist(v, "scope_confirmed", by=who, note=body.note)
    elif body.action == "exclude":
        if not body.note.strip():
            raise HTTPException(400, "Give the reason for the approved exclusion.")
        v.update({"status": "excluded", "excluded_reason": body.note, "excluded_by": who, "review_reason": None})
        _hist(v, "excluded", by=who, note=body.note)
    else:
        raise HTTPException(400, "Unknown review action")
    await _save_visit(user, contract_id, obligation_id, v)
    await record_audit(entity_type="afs_service_obligation", entity_id=obligation_id, action=f"review_{body.action}",
                       user=user, extra={"contract_id": contract_id, "case_id": body.case_id, "note": body.note})
    res = await sync_contract(org, contract)
    return {"visit": next((x for x in res["visits"] if x["obligation_id"] == obligation_id), v)}


@router.get("/contracts/{contract_id}/service-reconciliation")
async def service_reconciliation(contract_id: str, user=Depends(require_crm_perm("service.read"))):
    """Preview only — nothing is linked or changed."""
    contract = await _contract(user, contract_id)
    return (await sync_contract(_org(user), contract, dry_run=True))["report"]


@router.get("/contracts/{contract_id}/obligations/{obligation_id}/candidates")
async def obligation_candidates(contract_id: str, obligation_id: str, user=Depends(require_crm_perm("service.read"))):
    sched, v = await _visit(user, contract_id, obligation_id)
    linked = {x["case_id"] for x in sched["visits"] if x.get("case_id")}
    c = await candidate_cases(v, contract_id, int(sched.get("visits_per_year") or 1), linked)
    return {"strong": [_brief(x) for x in c["strong"]], "weak": [_brief(x) for x in c["weak"]]}
