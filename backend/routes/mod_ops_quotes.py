"""MOD Operations → Quotations: the single authoritative MOD quotation workflow.

Draft → Pending approval → Approved → Published → Customer review → Authorisation submitted
→ Accepted → Handed over (plus declined / withdrawn / expired / superseded).
Quote documents live in crm2_quotes (quote_kind="mod_sor") so CRM sees them natively.
"""
from __future__ import annotations

import hashlib
import re
import io
import os
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from routes.bfpo import _require_staff
from routes.crm_auth import get_crm_user
from routes.crm_mod_quote import _ensure_rate_card
from utils.database import db, get_object, put_object
from utils.mod_quote_chase import chase_schedule, run_chases
from utils.mod_quote_engine import (QUOTE_TYPES, TYPE_LABELS, apply_entry, build_quote, diff_against_card,
                                    parse_equipment_file, parse_schedule_b, suggest_coverage,
                                    rate_is_verified, synthetic_rates_allowed, match_card, schedule_label)
from utils.mod_quote_pdf import render_mod_quote_pdf
from utils.mod_sor_data import match_by_mod_code, match_equipment

router = APIRouter(prefix="/mod-ops/quotes", tags=["mod-ops-quotes"])

PERM_SALES, PERM_APPROVE, PERM_PRICING = "sales", "manager", "pricing"
CUSTOMER_VISIBLE = ("published", "customer_review", "authorisation_submitted", "accepted", "handed_over")
DEFAULT_VALIDITY = {"id": "validity", "days": 365, "status": "approved",
                    "note": "Approved by Pulse Fitness 25/11/2026 — Schedule B Year 4 prices are fixed for a year"}
HIDDEN_STATUSES = ("superseded", "staging", "failed_staging")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _need(user: dict, perm: str):
    """MOD Sales = MOD Operations staff; manager/pricing via user.mod_quote_role (or platform admin)."""
    if user.get("is_master_admin") or perm == PERM_SALES:
        return
    role = (user.get("mod_quote_role") or "").lower()
    allowed = {PERM_APPROVE: ("manager", "pricing_admin_manager"), PERM_PRICING: ("pricing_admin", "pricing_admin_manager")}
    if role not in allowed[perm]:
        label = "MOD Sales Manager" if perm == PERM_APPROVE else "Pricing Administrator"
        raise HTTPException(403, f"{label} permission required")


async def require_operator_crm_user(user=Depends(_require_staff)):
    if not user.get("is_master_admin"):
        org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0, "is_operator_company": 1})
        if not (org or {}).get("is_operator_company"):
            raise HTTPException(403, "MOD quotations are restricted to Pulse Fitness staff")
    return user


async def _sales(user=Depends(require_operator_crm_user)):
    return user


async def _event(gid: str, kind: str, user: dict | None, quote_id: str | None = None, version: int | None = None,
                 detail: dict | None = None, actor: str | None = None):
    await db.mod_quote_events.insert_one({
        "id": str(uuid.uuid4()), "group_id": gid, "quote_id": quote_id, "kind": kind, "version": version,
        "user_id": (user or {}).get("id"), "user_name": actor or (user or {}).get("full_name") or (user or {}).get("email"),
        "detail": detail or {}, "at": _now()})


async def _crm_activity(group: dict, subject: str, body: str, user: dict | None):
    if not group.get("crm_company_id"):
        return
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": group["organization_id"], "type": "mod_quote",
        "company_id": group["crm_company_id"], "contact_id": group.get("contact_id"),
        "subject": subject, "body": body, "mod_group_id": group["id"],
        "created_by": (user or {}).get("id"), "created_at": _now()})


async def _card_by_id() -> dict:
    await _ensure_rate_card()
    return {e["id"]: e async for e in db.mod_sor_rate_card.find({}, {"_id": 0})}


async def _next_ref() -> str:
    doc = await db.mod_quote_counters.find_one_and_update(
        {"id": "mod_quote"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return f"PFQ-{int(doc['seq']):06d}"


async def _group(gid: str) -> dict:
    g = await db.mod_quote_groups.find_one({"id": gid}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Quotation group not found")
    return g


async def _quotes(gid: str, current_only=True) -> list[dict]:
    flt = {"mod_group_id": gid}
    if current_only:
        flt["status"] = {"$nin": list(HIDDEN_STATUSES)}
    order = {"A": 0, "B": 1, "AB": 2}
    qs = await db.crm2_quotes.find(flt, {"_id": 0, "esign_token": 0}).to_list(50)
    return sorted(qs, key=lambda q: (q.get("version") or 0, order.get(q.get("mod_quote_type"), 3)))


# ── customers & equipment ──────────────────────────────────────────────
def _address_lines(o: dict) -> list[str]:
    parts = [o.get("address_line1"), o.get("address_line2"), o.get("address_line3"), o.get("city"),
             o.get("county"), o.get("postcode"), o.get("country")]
    lines = [p for p in parts if p]
    if not lines and o.get("address"):
        lines = [p.strip() for p in str(o["address"]).split(",") if p.strip()]
    return lines


@router.get("/customers")
async def search_customers(q: str = "", user=Depends(_sales)):
    flt = {"account_type": {"$in": ["mod_site", "mod_org"]}}
    if q.strip():
        flt["name"] = {"$regex": re.escape(q.strip()[:60]), "$options": "i"}
    out = []
    async for o in db.organizations.find(flt, {"_id": 0}).sort("name", 1).limit(40):
        comp = await db.crm2_companies.find_one({"linked_organization_id": o["id"]}, {"_id": 0, "id": 1, "name": 1, "account_ref": 1, "sage_account_ref": 1})
        out.append({
            "site_id": o["id"], "name": o["name"], "account_type": o.get("account_type"),
            "address_lines": _address_lines(o), "contact_name": o.get("primary_contact_name") or "",
            "contact_email": o.get("primary_contact_email") or "", "contact_phone": o.get("primary_contact_phone") or "",
            "account_ref": (comp or {}).get("sage_account_ref") or (comp or {}).get("account_ref") or o.get("company_code") or "",
            "crm_company_id": (comp or {}).get("id"),
            "equipment_count": await db.equipment.count_documents({"organization_id": o["id"]}),
        })
    return {"customers": out}


def _row_from(eq: dict, card: list[dict], source: str) -> dict:
    m = match_by_mod_code(eq.get("mod_code"), card) if eq.get("mod_code") else None
    if m:
        rid, conf = m["id"], 1.0
    else:
        r = match_equipment({"name": eq.get("description") or eq.get("name"), "equipment_type": eq.get("equipment_type", ""),
                             "model": eq.get("model", ""), "brand": eq.get("brand", "")}, card)
        rid, conf = (r["rate_card_id"] if r["matched"] else None), round(r["confidence"], 2)
    entry = next((c for c in card if c["id"] == rid), None)
    return {"row_id": str(uuid.uuid4()), "description": eq.get("description") or eq.get("name") or "",
            "qty": int(eq.get("qty") or 1), "rate_card_id": rid, "match_confidence": conf,
            "needs_review": rid is None or conf < 0.75, "label": "", "serial": eq.get("serial") or eq.get("serial_number") or "",
            "location": eq.get("location") or "", "mod_code": eq.get("mod_code") or "",
            "coverage": None, "suggested_coverage": suggest_coverage(entry) if entry else None,
            "equipment_id": eq.get("id"), "source": source}


@router.get("/sites/{site_id}/equipment")
async def site_equipment(site_id: str, user=Depends(_sales)):
    card = list((await _card_by_id()).values())
    rows = []
    async for eq in db.equipment.find({"organization_id": site_id, "is_deleted": {"$ne": True}}, {"_id": 0}).sort("name", 1).limit(2000):
        rows.append(_row_from(eq, card, "register"))
    return {"rows": rows}


@router.post("/import-equipment")
async def import_equipment(file: UploadFile = File(...), user=Depends(_sales)):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (10 MB max)")
    if not (file.filename or "").lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload an Excel (.xlsx) or CSV file")
    try:
        parsed = parse_equipment_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    card = list((await _card_by_id()).values())
    return {"rows": [_row_from(p, card, "upload") for p in parsed], "filename": file.filename}


@router.get("/catalogue")
async def catalogue(user=Depends(_sales)):
    card = await _card_by_id()
    return {"entries": sorted(card.values(), key=lambda e: e.get("sort_order", 0))}


# ── preview & groups ───────────────────────────────────────────────────
class Customer(BaseModel):
    site_id: str
    name: str
    address_lines: list[str] = []
    delivery_lines: list[str] = []
    account_ref: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    customer_reference: str = ""
    crm_company_id: str | None = None


class Row(BaseModel):
    row_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    qty: int = Field(1, ge=0, le=100000)
    rate_card_id: str | None = None
    label: str = ""
    coverage: str | None = None
    serial: str = ""
    location: str = ""
    mod_code: str = ""
    equipment_id: str | None = None
    source: str = "manual"


class GroupIn(BaseModel):
    customer: Customer
    rows: list[Row]
    options: list[str] = ["A", "B", "AB"]
    callout_qty: int = Field(1, ge=0, le=50)
    notes: str = ""
    idempotency_key: str | None = None


def _check_options(opts: list[str]) -> list[str]:
    opts = [o.upper() for o in opts]
    if not opts or any(o not in QUOTE_TYPES for o in opts):
        raise HTTPException(400, "Choose at least one of Type A, Type B or Type A/B Mix")
    return [o for o in QUOTE_TYPES if o in opts]


@router.post("/preview")
async def preview(body: GroupIn, user=Depends(_sales)):
    card = await _card_by_id()
    rows = [r.model_dump() for r in body.rows]
    return {"options": {o: build_quote(rows, o, card, body.callout_qty) for o in _check_options(body.options)}}


async def _resolve_site(customer: dict) -> dict:
    """Server-side truth for the MOD establishment and its linked CRM company."""
    site = await db.organizations.find_one({"id": customer["site_id"], "account_type": {"$in": ["mod_site", "mod_org"]}},
                                           {"_id": 0, "id": 1, "name": 1})
    if not site:
        raise HTTPException(422, "Select a valid MOD establishment")
    comp = await db.crm2_companies.find_one({"linked_organization_id": site["id"]}, {"_id": 0, "id": 1})
    return {**customer, "site_id": site["id"], "crm_company_id": (comp or {}).get("id")}


async def _check_equipment_ownership(site_id: str, rows: list[dict]):
    ids = [r["equipment_id"] for r in rows if r.get("equipment_id")]
    if not ids:
        return
    owned = {e["id"] async for e in db.equipment.find({"id": {"$in": ids}, "organization_id": site_id}, {"_id": 0, "id": 1})}
    foreign = [r["description"] for r in rows if r.get("equipment_id") and r["equipment_id"] not in owned]
    if foreign:
        raise HTTPException(422, f"These items are not on this site's equipment register: {', '.join(foreign[:5])}")


async def _make_quotes(group: dict, rows: list[dict], options: list[str], callout_qty: int, user: dict, version: int,
                       batch: str) -> list[str]:
    """Insert one quote per option in 'staging' status; caller promotes the batch once the group is saved."""
    card = await _card_by_id()
    built = {o: build_quote(rows, o, card, callout_qty) for o in options}
    bad = {o: b["issues"] for o, b in built.items() if b["issues"]}
    if bad:
        raise HTTPException(422, {"message": "Resolve these before generating", "issues": bad})
    cust = group["customer"]
    ids = []
    for o, b in built.items():
        qid = str(uuid.uuid4())
        ids.append(qid)
        await db.crm2_quotes.insert_one({"staging_batch": batch, "excluded_rows": b["excluded_rows"],
            "id": qid, "organization_id": group["organization_id"], "quote_kind": "mod_sor", "mod_group_id": group["id"],
            "mod_quote_type": o, "mod_contract_type": "A" if o == "A" else ("B" if o == "B" else "AB"),
            "quote_number": await _next_ref(), "sage_quote_number": None,
            "title": f"{TYPE_LABELS[o]} — {cust['name']}", "company_id": cust.get("crm_company_id"),
            "company_name": cust["name"], "contact_name": cust.get("contact_name"),
            "mod_site_id": cust["site_id"], "mod_site_name": cust["name"], "status": "staging", "version": version,
            "lines": b["lines"], "subtotal": b["net"], "vat_rate": b["vat_rate"], "vat_amount": b["vat"],
            "tax_rate": b["vat_rate"], "tax_amount": b["vat"], "tax_label": "VAT", "total": b["gross"], "currency": "GBP",
            "unverified_rate_lines": b["unverified_lines"], "price_list_version": card.get("sor-2", {}).get("price_list_version"),
            "customer_visible": False, "created_by": user.get("id"), "created_by_name": user.get("full_name") or user.get("email"),
            "created_at": _now(), "updated_at": _now(), "notes": group.get("notes", "")})
    return ids


async def _promote(batch: str, status: str = "draft"):
    await db.crm2_quotes.update_many({"staging_batch": batch, "status": "staging"}, {"$set": {"status": status}})


async def _fail_batch(batch: str):
    await db.crm2_quotes.update_many({"staging_batch": batch, "status": "staging"},
                                     {"$set": {"status": "failed_staging", "customer_visible": False}})


@router.post("/groups")
async def create_group(body: GroupIn, user=Depends(_sales)):
    opts = _check_options(body.options)
    if body.idempotency_key:
        await db.mod_quote_groups.create_index("idempotency_key", unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}})
        prior = await db.mod_quote_groups.find_one({"idempotency_key": body.idempotency_key}, {"_id": 0, "id": 1})
        if prior:
            return await get_group(prior["id"], user)
    customer = await _resolve_site(body.customer.model_dump())
    await _check_equipment_ownership(customer["site_id"], [r.model_dump() for r in body.rows])
    gid = str(uuid.uuid4())
    group = {"id": gid, "organization_id": user.get("organization_id"), "customer": customer,
             "crm_company_id": customer["crm_company_id"], "mod_site_id": customer["site_id"],
             "idempotency_key": body.idempotency_key,
             "rows": [r.model_dump() for r in body.rows], "options": opts, "callout_qty": body.callout_qty,
             "notes": body.notes, "status": "draft", "revision": 1, "created_by": user.get("id"),
             "created_by_name": user.get("full_name") or user.get("email"), "created_at": _now(), "updated_at": _now()}
    batch = str(uuid.uuid4())
    await _make_quotes(group, group["rows"], opts, body.callout_qty, user, 1, batch)
    try:
        await db.mod_quote_groups.insert_one(dict(group))
    except DuplicateKeyError:
        await _fail_batch(batch)
        prior = await db.mod_quote_groups.find_one({"idempotency_key": body.idempotency_key}, {"_id": 0, "id": 1})
        return await get_group(prior["id"], user)
    except Exception:
        await _fail_batch(batch)
        raise
    await _promote(batch)
    await _event(gid, "created", user, version=1, detail={"options": opts})
    await _crm_activity(group, "MOD quotation group created", f"{len(opts)} option(s) drafted in MOD Operations", user)
    return await get_group(gid, user)


@router.get("/groups")
async def list_groups(status: str = "", q: str = "", site_id: str = "", user=Depends(_sales)):
    flt: dict = {}
    if status == "historical":
        flt["status"] = {"$in": ["declined", "withdrawn", "expired", "handed_over"]}
    elif status:
        flt["status"] = status
    if site_id:
        flt["mod_site_id"] = site_id
    if q.strip():
        rx = {"$regex": re.escape(q.strip()[:60]), "$options": "i"}
        ids = [x["mod_group_id"] async for x in db.crm2_quotes.find({"quote_number": rx, "mod_group_id": {"$exists": True}}, {"mod_group_id": 1})]
        flt["$or"] = [{"customer.name": rx}, {"id": {"$in": ids}}]
    groups = await db.mod_quote_groups.find(flt, {"_id": 0, "rows": 0}).sort("updated_at", -1).limit(200).to_list(200)
    for g in groups:
        g["quotes"] = [{k: x.get(k) for k in ("id", "quote_number", "mod_quote_type", "subtotal", "total", "status", "version")}
                       for x in await _quotes(g["id"])]
    counts = {}
    async for c in db.mod_quote_groups.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[c["_id"]] = c["n"]
    return {"groups": groups, "counts": counts}


@router.get("/groups/{gid}")
async def get_group(gid: str, user=Depends(_sales)):
    g = await _group(gid)
    g["quotes"] = await _quotes(gid)
    g["superseded"] = await db.crm2_quotes.find({"mod_group_id": gid, "status": "superseded"},
                                                {"_id": 0, "id": 1, "quote_number": 1, "mod_quote_type": 1, "version": 1, "total": 1}).to_list(100)
    g["events"] = await db.mod_quote_events.find({"group_id": gid}, {"_id": 0}).sort("at", -1).to_list(200)
    g["authorisations"] = await db.mod_quote_authorisations.find({"group_id": gid}, {"_id": 0}).sort("submitted_at", -1).to_list(20)
    return g


@router.put("/groups/{gid}")
async def revise_group(gid: str, body: GroupIn, user=Depends(_sales)):
    g = await _group(gid)
    if g["status"] in ("accepted", "handed_over"):
        raise HTTPException(409, "An accepted quotation cannot be revised")
    opts = _check_options(body.options)
    if body.customer.site_id != g["mod_site_id"]:
        raise HTTPException(409, "A quotation group cannot be moved to a different MOD establishment — create a new quotation for that site")
    customer = await _resolve_site(body.customer.model_dump())
    await _check_equipment_ownership(customer["site_id"], [r.model_dump() for r in body.rows])
    issued = g["status"] not in ("draft", "pending_approval")
    version = g["revision"] + 1 if issued else g["revision"]
    newg = {**g, "customer": customer, "rows": [r.model_dump() for r in body.rows], "options": opts,
            "callout_qty": body.callout_qty, "notes": body.notes, "crm_company_id": customer["crm_company_id"]}
    batch = str(uuid.uuid4())
    seq = g.get("edit_seq") or 0
    await _make_quotes(newg, newg["rows"], opts, body.callout_qty, user, version, batch)
    res = await db.mod_quote_groups.update_one({"id": gid, "revision": g["revision"], "status": g["status"],
                                                "edit_seq": {"$in": [seq] if seq else [None, 0]}, "revising_batch": {"$in": [None]}},
                                               {"$set": {"revising_batch": batch, "edit_seq": seq + 1}})
    if res.modified_count != 1:
        await _fail_batch(batch)
        raise HTTPException(409, "This quotation group was changed by someone else — reload and try again")
    old_ids = [x["id"] for x in await _quotes(gid)]
    try:
        await db.crm2_quotes.update_many({"id": {"$in": old_ids}},
                                         {"$set": {"status": "superseded", "customer_visible": False, "superseded_at": _now()}})
    except Exception:
        await _fail_batch(batch)
        await db.mod_quote_groups.update_one({"id": gid, "revising_batch": batch}, {"$set": {"revising_batch": None}})
        raise
    if issued:
        await _event(gid, "superseded", user, version=g["revision"])
        await db.mod_quote_authorisations.update_many({"group_id": gid, "status": "submitted"},
                                                      {"$set": {"status": "superseded", "reviewed_at": _now()}})
    await db.mod_quote_groups.update_one({"id": gid}, {"$set": {
        "customer": newg["customer"], "rows": newg["rows"], "options": opts, "callout_qty": body.callout_qty,
        "notes": body.notes, "crm_company_id": newg["crm_company_id"], "status": "draft", "revision": version,
        "updated_at": _now(), "approved_by": None, "approved_at": None, "revising_batch": None}})
    await _promote(batch)
    await _event(gid, "revised" if issued else "edited", user, version=version)
    return await get_group(gid, user)


async def _set_status(gid: str, status: str, quote_filter: dict | None = None, extra: dict | None = None):
    await db.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": status, "updated_at": _now(), **(extra or {})}})
    await db.crm2_quotes.update_many({"mod_group_id": gid, "status": {"$nin": list(HIDDEN_STATUSES)}, **(quote_filter or {})},
                                     {"$set": {"status": status, "updated_at": _now()}})


@router.post("/groups/{gid}/submit")
async def submit_for_approval(gid: str, user=Depends(_sales)):
    g = await _group(gid)
    if g["status"] != "draft":
        raise HTTPException(409, f"Only drafts can be submitted (currently {g['status']})")
    await _set_status(gid, "pending_approval")
    await _event(gid, "submitted_for_approval", user, version=g["revision"])
    return {"ok": True}


class CommercialException(BaseModel):
    quote_id: str
    line_no: int
    reason: str = Field(..., min_length=10, max_length=500)
    original_rate: float
    proposed_rate: float
    valid_until: date


class ApproveIn(BaseModel):
    approve: bool = True
    exceptions: list[CommercialException] = []
    notes: str = ""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _exception_gaps(q: dict) -> list[dict]:
    """Unverified priced lines on a quote that lack a valid, matching commercial exception."""
    exc = {e["line_no"]: e for e in (q.get("commercial_exceptions") or [])}
    gaps = []
    for ln in q.get("unverified_rate_lines") or []:
        e = exc.get(ln["line_no"])
        if not e or e["valid_until"] < _today() or float(e["proposed_rate"]) != float(ln["unit_price"]):
            gaps.append({"quote_id": q["id"], "quote_number": q["quote_number"], **ln})
    return gaps


@router.post("/groups/{gid}/approve")
async def approve_group(gid: str, body: ApproveIn, user=Depends(require_operator_crm_user)):
    _need(user, PERM_APPROVE)
    g = await _group(gid)
    if g["status"] != "pending_approval":
        raise HTTPException(409, "Quotation is not awaiting approval")
    if not body.approve:
        await _set_status(gid, "draft")
        await _event(gid, "approval_rejected", user, version=g["revision"], detail={"notes": body.notes})
        return {"ok": True, "status": "draft"}
    qs = await _quotes(gid)
    by_q = {q["id"]: q for q in qs}
    who, when = user.get("full_name") or user.get("email"), _now()
    staged: dict[str, list] = {}
    for e in body.exceptions:
        q = by_q.get(e.quote_id)
        line = next((ln for ln in (q or {}).get("unverified_rate_lines") or [] if ln["line_no"] == e.line_no), None)
        if not line:
            raise HTTPException(422, f"Exception for line {e.line_no} does not match an unverified line on that quotation")
        if float(e.original_rate) != float(line["unit_price"]):
            raise HTTPException(422, f"Line {e.line_no}: original rate must be the quoted £{line['unit_price']:.2f}")
        if float(e.proposed_rate) != float(line["unit_price"]):
            raise HTTPException(422, f"Line {e.line_no}: to quote a different rate, revise the quotation — exceptions approve the quoted rate only")
        if e.valid_until.isoformat() < _today():
            raise HTTPException(422, f"Line {e.line_no}: exception validity has already passed")
        staged.setdefault(e.quote_id, []).append({**e.model_dump(mode="json"), "description": line["description"],
                                                  "item_code": line["item_code"], "authorised_by": who, "authorised_at": when})
    for qid, lst in staged.items():
        await db.crm2_quotes.update_one({"id": qid}, {"$set": {"commercial_exceptions": lst}})
        by_q[qid]["commercial_exceptions"] = lst
    gaps = [gp for q in by_q.values() for gp in _exception_gaps(q)]
    if gaps:
        raise HTTPException(422, {"message": "These priced lines use unverified rates — each needs a structured commercial exception",
                                  "unverified": [f"{gp['quote_number']} line {gp['line_no']}: {gp['description']} £{gp['unit_price']:.2f}" for gp in gaps],
                                  "lines": gaps})
    await _set_status(gid, "approved", extra={"approved_by": who, "approved_at": when})
    await _event(gid, "approved", user, version=g["revision"], detail={"exceptions": sum(len(v) for v in staged.values())})
    return {"ok": True, "status": "approved"}


async def _validity() -> dict:
    doc = await db.mod_quote_settings.find_one({"id": "validity"}, {"_id": 0})
    # An unapproved provisional value never overrides the approved 365-day default.
    return doc if doc and doc.get("status") == "approved" else dict(DEFAULT_VALIDITY)


@router.get("/settings")
async def get_settings(user=Depends(_sales)):
    return {"validity": await _validity()}


class ValidityIn(BaseModel):
    days: int = Field(..., ge=1, le=365)
    approved_commercially: bool = False
    note: str = ""


@router.put("/settings/validity")
async def set_validity(body: ValidityIn, user=Depends(require_operator_crm_user)):
    _need(user, PERM_APPROVE)
    doc = {"id": "validity", "days": body.days, "status": "approved" if body.approved_commercially else "provisional",
           "note": body.note, "updated_by": user.get("full_name") or user.get("email"), "updated_at": _now()}
    await db.mod_quote_settings.update_one({"id": "validity"}, {"$set": doc}, upsert=True)
    return {"validity": doc}


def assert_quote_current(q: dict, g: dict):
    """Server-side guard used by every acceptance path."""
    if not q or q.get("status") in HIDDEN_STATUSES or not q.get("customer_visible") or q.get("version") != g.get("revision"):
        raise HTTPException(409, "This quotation version is no longer current and cannot be accepted")
    if q.get("valid_until") and q["valid_until"] < _today():
        raise HTTPException(409, f"This quotation expired on {q['valid_until']} — please ask Pulse Fitness for a replacement or an extension")


class ExtendIn(BaseModel):
    valid_until: date
    reason: str = Field(..., min_length=10)


@router.post("/groups/{gid}/extend-validity")
async def extend_validity(gid: str, body: ExtendIn, user=Depends(require_operator_crm_user)):
    _need(user, PERM_APPROVE)
    g = await _group(gid)
    if g["status"] in ("accepted", "handed_over", "withdrawn"):
        raise HTTPException(409, f"Quotation is {g['status']}")
    if len(body.reason.strip()) < 10:
        raise HTTPException(422, "Give a reason of at least 10 characters")
    new_until = body.valid_until.isoformat()
    if new_until <= _today():
        raise HTTPException(422, "New validity date must be in the future")
    res = await db.crm2_quotes.update_many({"mod_group_id": gid, "customer_visible": True, "status": {"$nin": list(HIDDEN_STATUSES)}},
                                           {"$set": {"valid_until": new_until}})
    await _event(gid, "validity_extended", user, version=g["revision"], detail={"valid_until": new_until, "reason": body.reason})
    return {"ok": True, "updated": res.modified_count}


def _pdf_payload(q: dict, g: dict) -> dict:
    c = g["customer"]
    return {**q, "quote_number": q.get("sage_quote_number") or q["quote_number"],
            "quote_date": datetime.fromisoformat(q.get("published_at") or q["created_at"]).strftime("%d/%m/%Y"),
            "customer_reference": c.get("customer_reference"), "customer_name": c["name"],
            "address_lines": c.get("address_lines") or [], "delivery_lines": c.get("delivery_lines") or ["As Above"],
            "net": q["subtotal"], "vat": q["vat_amount"], "gross": q["total"]}


def pdf_filename(q: dict, g: dict) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " -" else "" for ch in g["customer"]["name"]).strip().replace(" ", "-")
    t = {"A": "Type-A", "B": "Type-B", "AB": "Type-A-B-Mix"}[q["mod_quote_type"]]
    return f"{q.get('sage_quote_number') or q['quote_number']}_{t}_{safe}_v{q['version']}.pdf"


async def quote_pdf_bytes(q: dict, g: dict) -> bytes:
    if q.get("published_pdf_path"):
        data, _ = get_object(q["published_pdf_path"])
        if q.get("published_pdf_sha256") and hashlib.sha256(data).hexdigest() != q["published_pdf_sha256"]:
            raise HTTPException(500, f"Integrity check failed for published quotation {q['quote_number']}")
        return data
    return render_mod_quote_pdf(_pdf_payload(q, g))


class PublishIn(BaseModel):
    quote_ids: list[str]


async def _put_with_retry(path: str, data: bytes, attempts: int = 3):
    import asyncio
    for i in range(attempts):
        try:
            return put_object(path, data, "application/pdf")
        except Exception:
            if i == attempts - 1:
                raise
            await asyncio.sleep(0.5 * (i + 1))


@router.post("/groups/{gid}/publish")
async def publish(gid: str, body: PublishIn, user=Depends(_sales)):
    g = await db.mod_quote_groups.find_one_and_update({"id": gid, "status": "approved"}, {"$set": {"status": "publishing"}},
                                                      projection={"_id": 0})
    if not g:
        raise HTTPException(409, "Only internally approved quotations can be published")
    try:
        await _resolve_site(g["customer"])
        c = g["customer"]
        missing = [k for k in ("name", "address_lines") if not c.get(k)]
        if missing:
            raise HTTPException(422, f"Customer details incomplete: {', '.join(missing)}")
        qs = [q for q in await _quotes(gid) if q["id"] in body.quote_ids]
        if not qs:
            raise HTTPException(400, "Select at least one quotation to publish")
        gaps = [gp for q in qs for gp in _exception_gaps(q)]
        if gaps:
            raise HTTPException(422, {"message": "Unverified rates without a valid commercial exception cannot be published",
                                      "unverified": [f"{gp['quote_number']} line {gp['line_no']}: {gp['description']}" for gp in gaps]})
        validity = await _validity()
        valid_until = (datetime.now(timezone.utc) + timedelta(days=int(validity["days"]))).date().isoformat()
        rendered = []
        for q in qs:
            if q.get("published_pdf_path"):
                continue
            q["published_at"] = _now()
            pdf = render_mod_quote_pdf(_pdf_payload(q, g))
            path = f"mod_quotes/{gid}/{q['id']}_v{q['version']}.pdf"
            await _put_with_retry(path, pdf)
            rendered.append((q, path, hashlib.sha256(pdf).hexdigest()))
        for q, path, sha in rendered:
            await db.crm2_quotes.update_one({"id": q["id"], "published_pdf_path": {"$exists": False}}, {"$set": {
                "status": "published", "customer_visible": True, "published_at": q["published_at"],
                "published_by": user.get("full_name") or user.get("email"), "published_pdf_path": path,
                "published_pdf_sha256": sha, "valid_until": valid_until,
                "validity_basis": {"days": validity["days"], "status": validity["status"]},
                "pricing_snapshot": {"lines": q["lines"], "net": q["subtotal"], "vat": q["vat_amount"], "gross": q["total"],
                                     "price_list_version": q.get("price_list_version"),
                                     "commercial_exceptions": q.get("commercial_exceptions") or [],
                                     "customer": {k: c.get(k) for k in ("name", "address_lines", "delivery_lines", "customer_reference")}}}})
            await _event(gid, "published", user, q["id"], q["version"], {"option": TYPE_LABELS[q["mod_quote_type"]], "ref": q["quote_number"]})
    except Exception:
        await db.mod_quote_groups.update_one({"id": gid, "status": "publishing"}, {"$set": {"status": "approved"}})
        raise
    await db.crm2_quotes.update_many({"mod_group_id": gid, "status": "approved", "id": {"$nin": body.quote_ids}},
                                     {"$set": {"status": "approved_not_published"}})
    await db.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": "published", "published_at": _now(), "updated_at": _now(),
                                                                "chase_schedule": chase_schedule(datetime.now(timezone.utc).date())}})
    await _crm_activity(g, "MOD quotations published to MODService", ", ".join(q["quote_number"] for q in qs), user)
    return await get_group(gid, user)


def _can(user: dict, perm: str) -> bool:
    try:
        _need(user, perm)
        return True
    except HTTPException:
        return False


@router.get("/followups")
async def list_followups(status: str = "open", everyone: bool = False, user=Depends(_sales)):
    q: dict = {"organization_id": user.get("organization_id")} if not user.get("is_master_admin") else {}
    if status:
        q["status"] = status
    if not (everyone and _can(user, PERM_APPROVE)):
        q["assigned_to"] = user.get("id")
    items = await db.mod_quote_followups.find(q, {"_id": 0}).sort("due", 1).to_list(500)
    return {"items": items}


class FollowupDoneIn(BaseModel):
    outcome: str = Field(..., min_length=3, max_length=500)


@router.post("/followups/{fid}/done")
async def followup_done(fid: str, body: FollowupDoneIn, user=Depends(_sales)):
    f = await db.mod_quote_followups.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Follow-up not found")
    if f["assigned_to"] != user.get("id") and not _can(user, PERM_APPROVE):
        raise HTTPException(403, "Only the quote owner or a MOD Sales Manager can close this follow-up")
    res = await db.mod_quote_followups.update_one({"id": fid, "status": "open"}, {"$set": {
        "status": "done", "outcome": body.outcome.strip(), "done_by": user.get("full_name") or user.get("email"), "done_at": _now()}})
    if not res.modified_count:
        raise HTTPException(409, "This follow-up is already closed")
    await _event(f["group_id"], "follow_up_recorded", user, detail={"chase": f["chase_no"], "outcome": body.outcome.strip()})
    return {"ok": True}


@router.post("/followups/run")
async def followups_run(user=Depends(_sales)):
    _need(user, PERM_APPROVE)
    return await run_chases()


class SageRefIn(BaseModel):
    sage_quote_number: str = Field(..., min_length=3, max_length=30)
    verified: bool


@router.post("/quotes/{qid}/sage-ref")
async def set_sage_ref(qid: str, body: SageRefIn, user=Depends(_sales)):
    """Record a Sage-assigned number. Only used on documents published after it is recorded."""
    if not body.verified:
        raise HTTPException(422, "Confirm the number was assigned by Sage")
    ref = body.sage_quote_number.strip().upper()
    if ref.startswith("PFQ-"):
        raise HTTPException(422, "PFQ references are internal — enter the number Sage assigned")
    q = await db.crm2_quotes.find_one({"id": qid, "mod_group_id": {"$exists": True}}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.get("published_pdf_path"):
        raise HTTPException(409, "This quotation is already published — record the Sage number on a revision")
    await db.crm2_quotes.update_one({"id": qid}, {"$set": {"sage_quote_number": ref, "sage_ref_recorded_by": user.get("full_name") or user.get("email"), "sage_ref_recorded_at": _now()}})
    await _event(q["mod_group_id"], "sage_reference_recorded", user, qid, q["version"], {"sage_quote_number": ref})
    return {"ok": True}


class NotifyIn(BaseModel):
    to: str = ""
    confirm_to: str = ""
    attach_pdfs: bool = True
    resend: bool = False


@router.post("/groups/{gid}/notify")
async def notify_customer(gid: str, body: NotifyIn, user=Depends(_sales)):
    from utils.email import send_email
    g = await _group(gid)
    qs = [q for q in await _quotes(gid) if q.get("customer_visible")]
    if not qs:
        raise HTTPException(409, "Publish at least one quotation first")
    if g.get("notified_revision") == g["revision"] and not body.resend:
        raise HTTPException(409, "The customer has already been notified for this revision")
    to = (body.to or g["customer"].get("contact_email") or "").strip()
    if "@" not in to:
        raise HTTPException(422, "No customer email address held — enter one")
    if body.confirm_to.strip().lower() != to.lower():
        raise HTTPException(422, "Re-type the recipient address to confirm it")
    live = os.environ.get("MOD_QUOTE_NOTIFY_LIVE", "").lower() == "true"
    portal = os.environ.get("MOD_PORTAL_URL", "").rstrip("/")
    rows = "".join(f"<li>{q['quote_number']} — {TYPE_LABELS[q['mod_quote_type']]}: £{q['total']:,.2f} inc. VAT</li>" for q in qs)
    portal_line = (f"<p>If your unit uses MODService you can also compare the options and authorise online at "
                   f"<a href=\"{portal}\">{portal}</a>. Downloading a quotation does not commit you to it.</p>") if portal else ""
    attached = "Copies are attached to this email." if body.attach_pdfs else ""
    html = (f"<p>Dear {g['customer'].get('contact_name') or 'Customer'},</p><p>Please find below your Pulse Fitness "
            f"maintenance quotation(s) for {g['customer']['name']}. {attached}</p><ul>{rows}</ul>{portal_line}"
            f"<p>To proceed, reply with your purchase order or authorisation and tell us which option you would like.</p>"
            f"<p>Pulse Fitness MOD Sales</p>")
    import base64
    atts = [{"filename": pdf_filename(q, g), "content": base64.b64encode(await quote_pdf_bytes(q, g)).decode()} for q in qs] if body.attach_pdfs else []
    if not live:
        await _event(gid, "customer_notification_dry_run", user, version=g["revision"],
                     detail={"to": to, "attachments": len(atts), "reason": "MOD_QUOTE_NOTIFY_LIVE is not enabled"})
        return {"ok": True, "to": to, "sent": False, "dry_run": True}
    await send_email(to, f"Your Pulse Fitness quotations — {g['customer']['name']}", html, atts,
                     organization_id=g["organization_id"], kind="mod_quote_ready")
    await db.mod_quote_groups.update_one({"id": gid}, {"$set": {"notified_revision": g["revision"], "notified_at": _now(), "notified_to": to}})
    await _event(gid, "customer_notified", user, version=g["revision"], detail={"to": to, "attachments": len(atts)})
    return {"ok": True, "to": to, "sent": True}


class StatusIn(BaseModel):
    reason: str = ""


@router.post("/groups/{gid}/withdraw")
async def withdraw(gid: str, body: StatusIn, user=Depends(_sales)):
    g = await _group(gid)
    if g["status"] in ("accepted", "handed_over"):
        raise HTTPException(409, "Accepted quotations cannot be withdrawn")
    await _set_status(gid, "withdrawn")
    await db.crm2_quotes.update_many({"mod_group_id": gid}, {"$set": {"customer_visible": False}})
    await _event(gid, "withdrawn", user, version=g["revision"], detail={"reason": body.reason})
    await _crm_activity(g, "MOD quotation withdrawn", body.reason, user)
    return {"ok": True}


@router.get("/quotes/{qid}/pdf")
async def quote_pdf(qid: str, user=Depends(_sales)):
    q = await db.crm2_quotes.find_one({"id": qid, "quote_kind": "mod_sor"}, {"_id": 0})
    if not q or not q.get("mod_group_id"):
        raise HTTPException(404, "Quote not found")
    g = await _group(q["mod_group_id"])
    return Response(await quote_pdf_bytes(q, g), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{pdf_filename(q, g)}"'})


async def zip_bytes(qs: list[dict], g: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for q in qs:
            z.writestr(pdf_filename(q, g), await quote_pdf_bytes(q, g))
    return buf.getvalue()


@router.get("/groups/{gid}/pdfs.zip")
async def group_zip(gid: str, user=Depends(_sales)):
    g = await _group(gid)
    data = await zip_bytes(await _quotes(gid), g)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="MOD-Quotations-{"".join(ch if ch.isalnum() else "-" for ch in g["customer"]["name"]).strip("-")}-v{g["revision"]}.zip"'})


# ── customer authorisation review & handover ───────────────────────────
@router.get("/authorisations")
async def authorisation_queue(status: str = "submitted", user=Depends(_sales)):
    items = await db.mod_quote_authorisations.find({"status": status} if status else {}, {"_id": 0}).sort("submitted_at", -1).to_list(200)
    return {"items": items}


@router.get("/authorisations/{aid}/evidence")
async def authorisation_evidence(aid: str, user=Depends(_sales)):
    a = await db.mod_quote_authorisations.find_one({"id": aid}, {"_id": 0})
    if not a or not a.get("evidence_path"):
        raise HTTPException(404, "No evidence uploaded")
    data, ctype = get_object(a["evidence_path"])
    return Response(data, media_type=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{a.get("evidence_filename") or "evidence"}"'})


class VerifyIn(BaseModel):
    accept: bool
    notes: str = ""


@router.post("/authorisations/{aid}/verify")
async def verify_authorisation(aid: str, body: VerifyIn, user=Depends(require_operator_crm_user)):
    _need(user, PERM_APPROVE)
    a = await db.mod_quote_authorisations.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Authorisation not found")
    if a["status"] != "submitted":
        raise HTTPException(409, f"Already {a['status']}")
    q = await db.crm2_quotes.find_one({"id": a["quote_id"]}, {"_id": 0})
    g = await _group(a["group_id"])
    if not body.accept:
        await db.mod_quote_authorisations.update_one({"id": aid}, {"$set": {"status": "rejected", "reviewed_by": user.get("full_name"), "reviewed_at": _now(), "review_notes": body.notes}})
        await _set_status(g["id"], "customer_review", {"customer_visible": True})
        await _event(g["id"], "authorisation_rejected", user, q["id"], q["version"], {"notes": body.notes})
        return {"ok": True, "status": "rejected"}
    assert_quote_current(q, g)
    if g["status"] in ("accepted", "handed_over"):
        raise HTTPException(409, "An option in this group has already been accepted")
    res = await db.mod_quote_groups.update_one({"id": g["id"], "status": {"$nin": ["accepted", "handed_over"]}},
                                               {"$set": {"status": "accepted", "accepted_quote_id": q["id"], "accepted_at": _now(),
                                                         "accepted_by": user.get("full_name") or user.get("email"), "updated_at": _now()}})
    if res.modified_count != 1:
        raise HTTPException(409, "Already accepted")
    await db.crm2_quotes.update_one({"id": q["id"]}, {"$set": {"status": "accepted", "accepted_at": _now(),
                                                                "accepted_evidence_id": aid}})
    await db.crm2_quotes.update_many({"mod_group_id": g["id"], "id": {"$ne": q["id"]}, "status": {"$nin": list(HIDDEN_STATUSES)}},
                                     {"$set": {"status": "not_selected", "customer_visible": True}})
    await db.mod_quote_authorisations.update_one({"id": aid}, {"$set": {"status": "verified", "reviewed_by": user.get("full_name") or user.get("email"),
                                                                         "reviewed_at": _now(), "review_notes": body.notes}})
    await _event(g["id"], "accepted", user, q["id"], q["version"], {"authorisation_id": aid, "po": a.get("po_reference")})
    await _crm_activity(g, f"MOD quotation {q['quote_number']} accepted",
                        f"{TYPE_LABELS[q['mod_quote_type']]} — £{q['total']:,.2f} gross. PO {a.get('po_reference') or 'n/a'}", user)
    if g.get("crm_company_id"):
        opp_id = str(uuid.uuid4())
        await db.crm2_opportunities.update_one({"mod_group_id": g["id"]}, {"$setOnInsert": {
            "id": opp_id, "organization_id": g["organization_id"], "company_id": g["crm_company_id"], "mod_group_id": g["id"],
            "name": f"MOD maintenance — {g['customer']['name']}", "value": q["subtotal"], "stage": "won", "status": "won",
            "source": "mod_operations_quote", "quote_id": q["id"], "created_at": _now()}}, upsert=True)
    q["status"] = "accepted"
    handover = await handover_quote(q, g, user)
    return {"ok": True, "status": "accepted", "handover_id": handover["id"]}


async def handover_quote(q: dict, g: dict, user: dict) -> dict:
    """Idempotent: one MOD Service Operations handover per accepted quote. No bookings, invoices or Sicon writes."""
    await db.mod_quote_handovers.create_index("source_quote_id", unique=True)
    existing = await db.mod_quote_handovers.find_one({"source_quote_id": q["id"]}, {"_id": 0})
    if existing:
        return existing
    if q.get("status") not in ("accepted", "handed_over"):
        raise HTTPException(409, "Only an accepted quotation can be handed to Operations")
    eq_lines = [ln for ln in q["lines"] if not ln.get("special") and ln.get("kind") != "call_out"]
    a_lines = [ln for ln in eq_lines if ln["coverage"] == "A"]
    rows = {r["row_id"]: r for r in g["rows"]}
    doc = {"id": str(uuid.uuid4()), "source_quote_id": q["id"], "source_quote_number": q["quote_number"],
           "group_id": g["id"], "mod_site_id": g["mod_site_id"], "mod_site_name": g["customer"]["name"],
           "quote_type": q["mod_quote_type"], "status": "awaiting_operations",
           "annual_type_a_value": round(sum(ln["total"] for ln in a_lines), 2),
           "one_off_type_b_value": round(sum(ln["total"] for ln in q["lines"] if ln.get("coverage") == "B"), 2),
           "annual_ppm_required": bool(a_lines),
           "coverage": [{"coverage": ln["coverage"], "item_code": ln["item_code"], "description": ln["description"],
                         "qty": ln["qty"], "total": ln["total"], "schedule_b_uid": ln.get("schedule_b_uid"),
                         "equipment_id": (rows.get(ln.get("row_id")) or {}).get("equipment_id"),
                         "annual_obligation": ln["coverage"] == "A"} for ln in eq_lines],
           "sicon_sync_state": "not_synchronised", "created_by": user.get("id"), "created_at": _now()}
    try:
        await db.mod_quote_handovers.insert_one(dict(doc))
    except DuplicateKeyError:
        return await db.mod_quote_handovers.find_one({"source_quote_id": q["id"]}, {"_id": 0})
    await db.mod_quote_groups.update_one({"id": g["id"]}, {"$set": {"status": "handed_over", "handover_id": doc["id"]}})
    await db.crm2_quotes.update_one({"id": q["id"]}, {"$set": {"status": "handed_over"}})
    await _event(g["id"], "operations_handover", user, q["id"], q["version"], {"handover_id": doc["id"]})
    return doc


@router.get("/handovers")
async def list_handovers(user=Depends(_sales)):
    return {"items": await db.mod_quote_handovers.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)}


# ── CRM read-side ──────────────────────────────────────────────────────
@router.get("/crm/company/{company_id}")
async def crm_company_quotes(company_id: str, user=Depends(get_crm_user)):
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0, "is_operator_company": 1})
    if not user.get("is_master_admin") and not (org or {}).get("is_operator_company"):
        raise HTTPException(403, "MOD quotations are restricted to Pulse Fitness staff")
    out = []
    async for q in db.crm2_quotes.find({"company_id": company_id, "mod_group_id": {"$exists": True}}, {"_id": 0, "lines": 0, "pricing_snapshot": 0}).sort("created_at", -1):
        g = await db.mod_quote_groups.find_one({"id": q["mod_group_id"]}, {"_id": 0, "status": 1, "accepted_quote_id": 1, "handover_id": 1})
        dl = await db.mod_quote_events.count_documents({"quote_id": q["id"], "kind": "customer_downloaded"})
        out.append({k: q.get(k) for k in ("id", "quote_number", "mod_group_id", "mod_quote_type", "subtotal", "total", "status",
                                          "created_at", "created_by_name", "published_at", "version", "mod_site_name", "sage_quote_number")} |
                   {"group_status": (g or {}).get("status"), "selected": (g or {}).get("accepted_quote_id") == q["id"],
                    "customer_downloads": dl, "handover_id": (g or {}).get("handover_id")})
    return {"quotes": out}


# ── Schedule B pricing administration ──────────────────────────────────
@router.post("/rates/import-preview")
async def rates_import_preview(file: UploadFile = File(...), user=Depends(require_operator_crm_user)):
    _need(user, PERM_PRICING)
    content = await file.read()
    try:
        parsed = parse_schedule_b(content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    card = list((await _card_by_id()).values())
    pid = str(uuid.uuid4())
    await db.mod_sor_price_lists.insert_one({
        "id": pid, "status": "preview", "filename": file.filename, "sha256": hashlib.sha256(content).hexdigest(),
        "entries": parsed["entries"], "issues": parsed["issues"], "uploaded_by": user.get("full_name") or user.get("email"),
        "uploaded_at": _now(), "synthetic": parsed["synthetic"], "price_year": parsed.get("price_year")})
    return {"price_list_id": pid, "rows": diff_against_card(parsed["entries"], card), "issues": parsed["issues"],
            "synthetic": parsed["synthetic"], "price_year": parsed.get("price_year")}


class RatesApproveIn(BaseModel):
    effective_from: date
    expires_on: date | None = None
    confirm: bool = False


@router.post("/rates/{pid}/approve")
async def rates_approve(pid: str, body: RatesApproveIn, user=Depends(require_operator_crm_user)):
    _need(user, PERM_PRICING)
    _need(user, PERM_APPROVE)
    if not body.confirm:
        raise HTTPException(400, "Confirm replacement of the live Schedule of Rates")
    pl = await db.mod_sor_price_lists.find_one({"id": pid}, {"_id": 0})
    if not pl or pl["status"] != "preview":
        raise HTTPException(409, "Price list is not awaiting approval")
    if pl.get("synthetic") and not synthetic_rates_allowed():
        raise HTTPException(409, "This workbook is marked SYNTHETIC TEST DATA and cannot replace the live Schedule of Rates")
    return await approve_price_list(pl, body.effective_from.isoformat(),
                                    body.expires_on.isoformat() if body.expires_on else None, user)


async def approve_price_list(pl: dict, eff: str, exp: str | None, user: dict) -> dict:
    pid = pl["id"]
    card = list((await _card_by_id()).values())
    version = f"SOR-{eff}-{pid[:6]}"
    created: dict[str, dict] = {}
    for e in pl["entries"]:
        hits = match_card(e, card) or ([created[e["item_no"]]] if e["item_no"] in created else [])
        if not hits and e.get("layout") == "pricing_schedule" and e["service_type"] in ("A", "B"):
            new = {"id": str(uuid.uuid4()), "item_no": f"{e['item_no']}-{pid[:4]}", "kind": "service",
                   "label": schedule_label(e),
                   "equipment_type": e["name"], "currency": "GBP", "is_poa": False, "match_keywords": [],
                   "sort_order": 100 + int(e["item_no"]), "created_from_price_list": pid, "created_at": _now()}
            await db.mod_sor_rate_card.insert_one(dict(new))
            created[e["item_no"]] = new
            card.append(new)
            hits = [new]
        for c in hits:
            await _apply_rate(c, e, pl, pid, eff, exp, version, user, keep_label=len(hits) > 1)
    await _finish_approve(pid, eff, version, user)
    return {"ok": True, "version": version, "created_entries": len(created)}


async def _apply_rate(c, e, pl, pid, eff, exp, version, user, keep_label=False):
    await db.mod_sor_rate_card_history.insert_one({"id": str(uuid.uuid4()), "rate_card_id": c["id"], "before": c,
                                                   "price_list_id": pid, "changed_by": user.get("id"), "at": _now()})
    approval = {"source": f"Schedule B import {pl['filename']} (sha256 {pl['sha256'][:12]})", "effective_from": eff,
                "expires_on": exp, "approved_by": user.get("full_name") or user.get("email"),
                "approved_at": _now(), "version": version, "synthetic": bool(pl.get("synthetic"))}
    if approval["synthetic"]:
        approval["source"] = "SYNTHETIC TEST DATA — " + approval["source"]
    upd = apply_entry(c, e, approval)
    if keep_label:
        upd.pop("label", None)
    await db.mod_sor_rate_card.update_one({"id": c["id"]}, {"$set": {**upd, "price_list_version": version, "updated_at": _now()}})


async def _finish_approve(pid, eff, version, user):
    await db.mod_sor_price_lists.update_many({"status": "live"}, {"$set": {"status": "superseded"}})
    await db.mod_sor_price_lists.update_one({"id": pid}, {"$set": {"status": "live", "version": version,
                                                                   "effective_from": eff,
                                                                   "approved_by": user.get("full_name") or user.get("email"), "approved_at": _now()}})


@router.delete("/rates/{pid}")
async def rates_discard(pid: str, user=Depends(require_operator_crm_user)):
    _need(user, PERM_PRICING)
    res = await db.mod_sor_price_lists.update_one({"id": pid, "status": "preview"}, {"$set": {
        "status": "discarded", "discarded_by": user.get("full_name") or user.get("email"), "discarded_at": _now()}})
    if not res.modified_count:
        raise HTTPException(409, "Only an import preview can be discarded")
    return {"ok": True}


@router.get("/rates/price-lists")
async def price_lists(user=Depends(require_operator_crm_user)):
    # Price-list provenance (source files, approvers, versions) is Master Admin only.
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Price list history is available to Master Admin only")
    return {"items": await db.mod_sor_price_lists.find({}, {"_id": 0, "entries": 0}).sort("uploaded_at", -1).to_list(50)}


def _rate_status(entry: dict, key: str, today: str) -> str:
    if entry.get(f"poa_{key}"):
        return "poa"
    if rate_is_verified(entry, key, today):
        return "verified"
    if entry.get(f"rate_{key}_synthetic"):
        return "test_data"
    rate = entry.get(f"rate_{key}") or {}
    if rate.get("status") == "verified" and rate.get("expires_on") and rate["expires_on"] < today:
        return "expired"
    return entry.get(f"price_status_{key}") or "unverified"


@router.get("/rates/current")
async def rates_current(user=Depends(require_operator_crm_user)):
    _need(user, PERM_PRICING)
    today = date.today().isoformat()
    rows = []
    for e in sorted((await _card_by_id()).values(), key=lambda x: x.get("sort_order", 0)):
        row = {"id": e["id"], "item_no": e.get("item_no"), "kind": e.get("kind"), "label": e.get("label"),
               "price_list_version": e.get("price_list_version")}
        for k in ("a", "b"):
            rate = e.get(f"rate_{k}") or {}
            if k == "a" and e.get("kind") == "call_out":
                row[k] = {"code": None, "sage_code": None, "price": None, "status": "n/a", "effective_from": None,
                          "expires_on": None, "source": None, "approved_by": None, "ambiguous": False}
                continue
            row[k] = {"code": e.get(f"schedule_b_uid_{k}") or e.get(f"code_{k}"), "sage_code": e.get(f"sage_code_{k}"),
                      "price": e.get(f"type_{k}_price"), "status": _rate_status(e, k, today),
                      "effective_from": rate.get("effective_from"), "expires_on": rate.get("expires_on"),
                      "source": rate.get("source"), "approved_by": rate.get("approved_by"),
                      "ambiguous": bool(e.get(f"ambiguous_sage_code_{k}"))}
        rows.append(row)
    live = await db.mod_sor_price_lists.find_one({"status": "live"}, {"_id": 0, "entries": 0, "issues": 0})
    summary: dict[str, int] = {}
    for r in rows:
        for k in ("a", "b"):
            if r[k]["price"] is not None or r[k]["status"] == "poa":
                summary[r[k]["status"]] = summary.get(r[k]["status"], 0) + 1
    ready = bool(live) and not live.get("synthetic") and set(summary) <= {"verified", "poa"}
    if not user.get("is_master_admin"):
        # Staff see prices, item codes, status and dates — never where the prices came from.
        for r in rows:
            r.pop("price_list_version", None)
            for k in ("a", "b"):
                for f in ("source", "approved_by", "code"):
                    r[k].pop(f, None)
        live = {"effective_from": live.get("effective_from"), "synthetic": bool(live.get("synthetic"))} if live else None
    return {"rows": rows, "live_price_list": live, "summary": summary, "customer_ready": ready}


@router.get("/me")
async def my_capabilities(user=Depends(_sales)):
    def can(p):
        try:
            _need(user, p)
            return True
        except HTTPException:
            return False
    return {"sales": True, "manager": can(PERM_APPROVE), "pricing": can(PERM_PRICING),
            "master": bool(user.get("is_master_admin")), "name": user.get("full_name") or user.get("email")}


# ── MOD Service Operations handover queue ──────────────────────────────
@router.get("/handovers/{hid}")
async def get_handover(hid: str, user=Depends(_sales)):
    h = await db.mod_quote_handovers.find_one({"id": hid}, {"_id": 0})
    if not h:
        raise HTTPException(404, "Handover not found")
    g = await _group(h["group_id"])
    q = await db.crm2_quotes.find_one({"id": h["source_quote_id"]}, {"_id": 0, "accepted_evidence_id": 1, "valid_until": 1})
    auth = await db.mod_quote_authorisations.find_one({"id": (q or {}).get("accepted_evidence_id")}, {"_id": 0})
    outstanding = []
    if not g["customer"].get("contact_email"):
        outstanding.append("Site contact email")
    if h["annual_ppm_required"] and not h.get("start_date"):
        outstanding.append("Contract commencement date")
    if any(not c.get("equipment_id") for c in h["coverage"]):
        outstanding.append("Some lines are not linked to equipment register records")
    return {**h, "customer": g["customer"], "authorisation": auth, "outstanding": outstanding}


class SetupIn(BaseModel):
    start_date: date
    notes: str = ""


@router.post("/handovers/{hid}/setup")
async def setup_handover(hid: str, body: SetupIn, user=Depends(require_operator_crm_user)):
    """Manager action: create the Type A annual contract and/or Type B one-off record from the accepted scope.
    Idempotent. Proposes (does not confirm) the annual visit; no bookings, invoices or Sicon writes."""
    _need(user, PERM_APPROVE)
    start = body.start_date.isoformat()
    h = await db.mod_quote_handovers.find_one({"id": hid}, {"_id": 0})
    if not h:
        raise HTTPException(404, "Handover not found")
    if h.get("status") == "setup_complete":
        return {"ok": True, "already": True, "records": h.get("service_records", [])}
    await db.mod_service_contracts.create_index([("source_handover_id", 1), ("contract_type", 1)], unique=True,
                                                partialFilterExpression={"source_handover_id": {"$type": "string"}})
    now, who = _now(), user.get("full_name") or user.get("email")
    records = []
    for ct in ("A", "B"):
        cov = [c for c in h["coverage"] if c["coverage"] == ct]
        if not cov:
            continue
        doc = {"id": str(uuid.uuid4()), "organization_id": user.get("organization_id"), "contract_type": ct,
               "source_handover_id": hid, "quote_id": h["source_quote_id"], "quote_number": h["source_quote_number"],
               "mod_site_id": h["mod_site_id"], "mod_site_name": h["mod_site_name"], "currency": "GBP",
               "coverage": cov, "equipment_count": sum(int(c["qty"]) for c in cov), "start_date": start,
               "created_by": user.get("id"), "created_by_name": who, "created_at": now, "updated_at": now,
               "sicon_sync_state": "not_synchronised", "notes": body.notes}
        if ct == "A":
            doc.update({"status": "active", "activated_at": now, "term_months": 12, "annual_value": h["annual_type_a_value"],
                        "annual_visit": {"status": "pending_confirmation", "proposed_date": start, "scheduled_date": None,
                                         "engineer": None, "notes": None, "confirmed_by": None, "confirmed_at": None, "created_at": now}})
        else:
            doc.update({"status": "one_off_awaiting_booking", "one_off_value": h["one_off_type_b_value"], "annual_obligation": False})
        try:
            await db.mod_service_contracts.insert_one(dict(doc))
        except DuplicateKeyError:
            doc = await db.mod_service_contracts.find_one({"source_handover_id": hid, "contract_type": ct}, {"_id": 0})
        records.append({"id": doc["id"], "contract_type": ct, "status": doc["status"]})
    await db.mod_quote_handovers.update_one({"id": hid}, {"$set": {"status": "setup_complete", "start_date": start,
                                                                    "service_records": records, "setup_by": who, "setup_at": now}})
    await _event(h["group_id"], "operations_setup_complete", user, h["source_quote_id"], None, {"records": records})
    return {"ok": True, "records": records}
