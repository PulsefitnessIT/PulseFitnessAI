"""MOD aftersales contracts (CRM) — PTE service contract with the MoD.

Service types per the Pulse Fitness MOD Contract Summary:
  A  UK — 12-month all-inclusive service, repair & maintenance (price per site, annual)
  B  UK — one-off service, repair & maintenance (price per visit)
  C  Overseas — quoted service incl. inspection, staff training, optional quarterly inspections
  repair  — ad-hoc repairs outside A/B (quoted, MoD approval required)
  refurb  — refurbishment (quoted, 24-month warranty)
Stored in crm2_contracts with contract_type="mod"; one line per site location + service type.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from routes.crm_auth import get_crm_user
from utils.database import db

router = APIRouter(prefix="/crm/v2/mod-contracts", tags=["MOD Contracts"])

MOD_SERVICE_TYPES = {
    "A": {"label": "Type A — UK 12-month all-inclusive", "region": "UK", "price_basis": "annual",
          "includes": ["Service, cleaning & calibration", "All repairs for 12 months", "Service certificate & red label"],
          "excludes": ["Upholstery", "Cycle foot straps", "Damage caused by misuse"]},
    "B": {"label": "Type B — UK one-off service", "region": "UK", "price_basis": "per_visit",
          "includes": ["One-off service, repair & maintenance", "Service certificate & red label"],
          "excludes": ["Additional repairs need a quote and MoD approval"]},
    "C": {"label": "Type C — Overseas (quoted)", "region": "Overseas", "price_basis": "quoted",
          "includes": ["Service & inspection", "Staff training", "Optional quarterly inspections"],
          "excludes": ["Items excluded under Types A/B where applicable"]},
    "repair": {"label": "Repairs (quoted)", "region": "Any", "price_basis": "quoted",
               "includes": ["Ad-hoc repairs outside Type A/B"], "excludes": ["Work without MoD approval"]},
    "refurb": {"label": "Refurbishment (quoted)", "region": "Any", "price_basis": "quoted",
               "includes": ["Full refurbishment", "24-month warranty"], "excludes": ["Upholstery refresh unless requested"]},
}
STATUSES = ("draft", "active", "expired", "cancelled")


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id") or "__none__"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_editor(user: dict) -> None:
    if (user.get("role") or "").lower() not in ("owner", "manager", "admin", "master_admin", "super_admin", "sales_manager"):
        raise HTTPException(403, "Only managers can edit MOD contracts")


async def _mod_company(company_id: str, user: dict) -> dict:
    from routes.crm_v2 import ensure_mod_company_link
    c = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Company not found")
    return await ensure_mod_company_link(c)


def _clean_lines(raw: list, locations: dict) -> list:
    lines = []
    for ln in raw or []:
        st = ln.get("service_type")
        if st not in MOD_SERVICE_TYPES:
            raise HTTPException(400, f"Unknown service type: {st}")
        loc_id = ln.get("location_id") or ""
        if loc_id and loc_id not in locations:
            raise HTTPException(400, "Location doesn't belong to this site")
        try:
            price = round(float(ln.get("price") or 0), 2)
        except (TypeError, ValueError):
            raise HTTPException(400, "Price must be a number")
        if price < 0:
            raise HTTPException(400, "Price can't be negative")
        lines.append({
            "id": ln.get("id") or str(uuid.uuid4()), "location_id": loc_id,
            "location_name": locations.get(loc_id, "Whole site") if loc_id else "Whole site",
            "service_type": st, "price": price, "price_basis": MOD_SERVICE_TYPES[st]["price_basis"],
            "quarterly_inspections": bool(ln.get("quarterly_inspections")) if st == "C" else False,
            "notes": (ln.get("notes") or "")[:500],
        })
    return lines


async def _locations(company: dict) -> dict:
    org = company.get("linked_organization_id")
    if not org:
        return {}
    return {s["id"]: s["name"] async for s in db.sites.find(
        {"organization_id": org, "status": {"$ne": "archived"}}, {"_id": 0, "id": 1, "name": 1})}


async def _build(data: dict, company: dict, user: dict, existing: dict | None = None) -> dict:
    lines = _clean_lines(data.get("lines"), await _locations(company))
    status = data.get("status") or (existing or {}).get("status") or "draft"
    if status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    annual = sum(ln["price"] for ln in lines if ln["service_type"] == "A")
    return {
        "reference": (data.get("reference") or "").strip()[:80],
        "title": (data.get("title") or "MOD PTE Service Contract").strip()[:160],
        "authority": (data.get("authority") or "").strip()[:160],
        "start_date": data.get("start_date") or "", "end_date": data.get("end_date") or "",
        "status": status, "notes": (data.get("notes") or "")[:2000], "lines": lines,
        "annual_value": annual, "total_value": round(sum(ln["price"] for ln in lines), 2),
        "service_types": sorted({ln["service_type"] for ln in lines}),
        "updated_at": _now(), "updated_by": user.get("id"),
    }


@router.get("/catalog")
async def mod_catalog(user=Depends(get_crm_user)):
    return {"service_types": [{"key": k, **v} for k, v in MOD_SERVICE_TYPES.items()]}


@router.get("/locations")
async def mod_locations(company_id: str, user=Depends(get_crm_user)):
    company = await _mod_company(company_id, user)
    locs = await _locations(company)
    return {"linked": bool(company.get("linked_organization_id")),
            "locations": [{"id": k, "name": v} for k, v in sorted(locs.items(), key=lambda kv: kv[1].lower())]}


@router.get("")
async def list_mod_contracts(company_id: str = "", user=Depends(get_crm_user)):
    q = {**_of(user), "contract_type": "mod"}
    if company_id:
        q["company_id"] = company_id
    rows = await db.crm2_contracts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"contracts": rows}


@router.post("")
async def create_mod_contract(data: dict, user=Depends(get_crm_user)):
    _require_editor(user)
    company = await _mod_company(data.get("company_id") or "", user)
    doc = {"id": str(uuid.uuid4()), **_of(user), "contract_type": "mod", "type": "service", "is_mod": True,
           "company_id": company["id"], "company_name": company.get("name"),
           "created_at": _now(), "created_by": user.get("id"), **(await _build(data, company, user))}
    await db.crm2_contracts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.put("/{contract_id}")
async def update_mod_contract(contract_id: str, data: dict, user=Depends(get_crm_user)):
    _require_editor(user)
    existing = await db.crm2_contracts.find_one({"id": contract_id, "contract_type": "mod", **_of(user)}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Contract not found")
    company = await _mod_company(existing["company_id"], user)
    sets = await _build({**existing, **data}, company, user, existing)
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": sets})
    return {**existing, **sets}


@router.delete("/{contract_id}")
async def delete_mod_contract(contract_id: str, user=Depends(get_crm_user)):
    _require_editor(user)
    r = await db.crm2_contracts.delete_one({"id": contract_id, "contract_type": "mod", **_of(user)})
    if not r.deleted_count:
        raise HTTPException(404, "Contract not found")
    return {"ok": True}
