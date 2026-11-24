"""Contract Management — Maintenance Master bridge (import, reconcile, edit, export,
deferred Sicon). Records live in the existing ``crm2_contracts``/``crm2_companies``."""
from __future__ import annotations

import asyncio
import hashlib
import re
import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from routes.crm_workspace import require_crm_perm
from utils import mm_import as mm
from utils.crm_audit import record_audit
from utils.database import db

router = APIRouter(prefix="/crm/v2/aftersales/maintenance-master", tags=["Maintenance Master"])
log = logging.getLogger(__name__)
CHUNK_MAX = 4 * 1024 * 1024
FILE_MAX = 200 * 1024 * 1024
_TASKS: set = set()


def _spawn(coro):
    t = asyncio.get_event_loop().create_task(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


UNRESOLVED = ("duplicate_overlap", "missing_information", "requires_review")
CLASSES = ("skipped", "matched_unchanged", "matched_differences", "new_contract", "duplicate_overlap",
           "missing_information", "requires_review")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _org(user) -> str:
    return user.get("organization_id")


def _who(user) -> str:
    return user.get("email") or user.get("name") or user.get("id") or "user"


async def _indexes():
    await db.crm2_mm_rows.create_index([("upload_id", 1), ("cls", 1)])
    await db.crm2_mm_rows.create_index([("upload_id", 1), ("sheet", 1), ("row", 1)], unique=True)
    await db.crm2_mm_upload_chunks.create_index([("upload_id", 1), ("n", 1)], unique=True)
    await db.crm2_contracts.create_index([("organization_id", 1), ("mm_record_key", 1)], unique=True,
                                         partialFilterExpression={"mm_record_key": {"$type": "string"}},
                                         name="org_mm_record_key_unique")
    await db.crm2_contract_changes.create_index([("contract_id", 1), ("at", -1)])


async def _upload(user, uid: str) -> dict:
    u = await db.crm2_mm_uploads.find_one({"id": uid, "organization_id": _org(user)}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Upload not found")
    return u


# ───────────────────────────── upload (chunked → GridFS, original kept unchanged)

class UploadIn(BaseModel):
    filename: str
    size: int
    total_chunks: int
    source_version: str = ""


@router.post("/uploads")
async def start_upload(body: UploadIn, user=Depends(require_crm_perm("contracts.manage"))):
    if not body.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload the Maintenance Master as an .xlsx workbook.")
    if body.size > FILE_MAX or body.total_chunks < 1:
        raise HTTPException(400, "File too large (max 200 MB).")
    await _indexes()
    uid = str(uuid.uuid4())
    await db.crm2_mm_uploads.insert_one({
        "id": uid, "organization_id": _org(user), "filename": body.filename, "size": body.size,
        "total_chunks": body.total_chunks, "source_version": body.source_version or body.filename,
        "state": "uploading", "uploaded_by": _who(user), "created_at": _now()})
    return {"upload_id": uid}


@router.put("/uploads/{uid}/chunks/{n}")
async def put_chunk(uid: str, n: int, request: Request, user=Depends(require_crm_perm("contracts.manage"))):
    u = await _upload(user, uid)
    if u["state"] != "uploading" or not 0 <= n < u["total_chunks"]:
        raise HTTPException(400, "Chunk not expected")
    data = await request.body()
    if not data or len(data) > CHUNK_MAX:
        raise HTTPException(400, "Chunk must be 1 byte – 4 MB")
    await db.crm2_mm_upload_chunks.update_one({"upload_id": uid, "n": n}, {"$set": {"data": data}}, upsert=True)
    return {"ok": True, "n": n}


@router.post("/uploads/{uid}/complete")
async def complete_upload(uid: str, user=Depends(require_crm_perm("contracts.manage"))):
    u = await _upload(user, uid)
    if u["state"] != "uploading":
        return {"upload_id": uid, "state": u["state"]}
    chunks = await db.crm2_mm_upload_chunks.find({"upload_id": uid}, {"_id": 0, "n": 1, "data": 1}).sort("n", 1).to_list(1000)
    if [c["n"] for c in chunks] != list(range(u["total_chunks"])):
        raise HTTPException(400, f"Missing chunks — received {len(chunks)} of {u['total_chunks']}.")
    blob = b"".join(c["data"] for c in chunks)
    sha = hashlib.sha256(blob).hexdigest()
    fid = await mm.bucket().upload_from_stream(u["filename"], io.BytesIO(blob), metadata={
        "upload_id": uid, "sha256": sha, "organization_id": _org(user)})
    prior = await db.crm2_mm_uploads.find_one({"organization_id": _org(user), "sha256": sha, "id": {"$ne": uid},
                                               "state": {"$nin": ["failed", "uploading"]}},
                                              {"_id": 0, "id": 1, "created_at": 1})
    await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {
        "state": "parsing", "sha256": sha, "file_id": str(fid), "received_size": len(blob),
        "same_file_as": (prior or {}).get("id"), "uploaded_at": _now()}})
    await db.crm2_mm_upload_chunks.delete_many({"upload_id": uid})
    _spawn(_parse_job(_org(user), uid, blob))
    return {"upload_id": uid, "state": "parsing", "sha256": sha, "same_file_as": (prior or {}).get("id")}


async def _read_file(u: dict) -> bytes:
    from bson import ObjectId
    out = io.BytesIO()
    await mm.bucket().download_to_stream(ObjectId(u["file_id"]), out)
    return out.getvalue()


# ───────────────────────────── staging + reconciliation preview

async def _parse_job(org: str, uid: str, blob: bytes | None = None):
    try:
        u = await db.crm2_mm_uploads.find_one({"id": uid}, {"_id": 0})
        blob = blob or await _read_file(u)
        parsed = await asyncio.to_thread(mm.parse_workbook, blob)
        await db.crm2_mm_rows.delete_many({"upload_id": uid, "state": "staged"})
        docs = []
        for r in parsed["rows"]:
            docs.append({"id": str(uuid.uuid4()), "upload_id": uid, "organization_id": org, **r,
                         "record_key": mm.record_key(r["sheet"], r["mapped"]), "state": "staged"})
        for i in range(0, len(docs), 1000):
            await db.crm2_mm_rows.insert_many(docs[i:i + 1000], ordered=False)
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"sheets": parsed["sheets"], "state": "classifying"}})
        summary = await classify_upload(org, uid)
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"state": "ready", "summary": summary, "parsed_at": _now()}})
    except Exception as e:  # noqa: BLE001
        log.exception("maintenance master parse failed")
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"state": "failed", "error": str(e)[:500]}})


def effective(r: dict) -> dict:
    """Source values with coordinator corrections applied (the raw row is never changed)."""
    return {**r["mapped"], **{k: v["value"] for k, v in (r.get("corrections") or {}).items()}}


async def classify_upload(org: str, uid: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    idx = await mm.company_index(org)
    planner, sicon = {}, {}
    async for r in db.crm2_mm_rows.find({"upload_id": uid, "role": "evidence"}, {"_id": 0, "sheet": 1, "raw": 1, "mapped": 1, "row": 1}):
        raw = r["raw"]
        if r["sheet"] == "Service Planner" and raw.get("Record ID (internal)"):
            planner[str(raw["Record ID (internal)"])] = {
                "latest_service": mm.norm_date(raw.get("Latest service on record"))[0],
                "ppm_completed": mm.norm_date(raw.get("PPM completed - ENTER DATE"))[0],
                "contractual_due": mm.norm_date(raw.get("Contractual service due"))[0],
                "service_status": raw.get("Service status"), "service_booked": mm.norm_date(raw.get("Service booked"))[0],
                "engineer": raw.get("Assigned engineer"), "sicon_case_ref": raw.get("Sicon case reference"),
                "verified_by": raw.get("Completion verified by"), "planner_row": r["row"]}
        elif r["sheet"] == "Sicon Contracts" and r["mapped"].get("contract_number") and raw.get("Sicon contract ID"):
            s = sicon.setdefault(r["mapped"]["contract_number"], {"ids": set(), "lines": set(), "rows": []})
            s["ids"].add(str(raw["Sicon contract ID"]))
            if raw.get("Sicon line ID"):
                s["lines"].add(str(raw["Sicon line ID"]))
            s["rows"].append(r["row"])
    existing = {}
    async for c in db.crm2_contracts.find({"organization_id": org}, {"_id": 0, "id": 1, "mm_record_key": 1, "contract_number": 1,
                                                                    "company_id": 1, "status": 1, "start_date": 1, "end_date": 1,
                                                                    "annual_value": 1, "mm": 1, "mm_baseline": 1, "source": 1,
                                                                    "coordinator_name": 1, "visits_per_year": 1, "payment_frequency": 1,
                                                                    "direct_debit": 1, "sicon_contract_id": 1, "sage_account_ref": 1}):
        if c.get("mm_record_key"):
            existing[("k", c["mm_record_key"])] = c
        if c.get("contract_number"):
            existing.setdefault(("n", str(c["contract_number"])), c)
    live_numbers = {}
    async for r in db.crm2_mm_rows.find({"upload_id": uid, "role": "contract"}, {"_id": 0, "mapped": 1, "corrections": 1, "decision": 1}):
        if (r.get("decision") or {}).get("action") == "skip":
            continue
        m = effective(r)
        if m.get("contract_number") and mm.contract_status(m.get("start_date"), m.get("end_date"), today) in ("active", "future"):
            live_numbers[m["contract_number"]] = live_numbers.get(m["contract_number"], 0) + 1
    counts = {k: 0 for k in CLASSES}
    totals = {}
    ops = []
    async for r in db.crm2_mm_rows.find({"upload_id": uid, "role": {"$in": ["contract", "held"]}}, {"_id": 0}):
        m = effective(r)
        st = mm.contract_status(m.get("start_date"), m.get("end_date"), today)
        t = totals.setdefault(r["sheet"], {"rows": 0, "contract_amount": 0.0, "original_amount": 0.0, "annual_value": 0.0,
                                           "active": 0, "expired": 0, "future": 0, "uncertain": 0})
        t["rows"] += 1
        t[st] += 1
        t["contract_amount"] = round(t["contract_amount"] + (m.get("contract_amount") or 0), 2)
        t["original_amount"] = round(t["original_amount"] + (m.get("original_amount") or 0), 2)
        t["annual_value"] = round(t["annual_value"] + (mm.annual_value(m) or 0), 2)
        if r["role"] == "held":
            ops.append((r["id"], {"cls": "held_mod", "problems": ["MOD row — kept for MOD Operations reconciliation"], "status": st}))
            continue
        ex = existing.get(("k", r["record_key"])) or (existing.get(("n", m["contract_number"])) if m.get("contract_number") else None)
        cust = mm.match_company(idx, m) if not ex else {"status": "matched", "company_id": ex.get("company_id"), "basis": "existing contract"}
        if not ex and cust.get("company_id") and st in ("active", "future") and m.get("start_date") and m.get("end_date"):
            ov = await db.crm2_contracts.find_one({"organization_id": org, "company_id": cust["company_id"], "status": "active",
                                                   "start_date": {"$lte": m["end_date"]}, "end_date": {"$gte": m["start_date"]},
                                                   "contract_number": {"$ne": m.get("contract_number")}},
                                                  {"_id": 0, "contract_number": 1})
            if ov:
                ex = {"_overlap": f"overlaps active CRM contract {ov.get('contract_number')} for this customer"}
        dup = (live_numbers.get(m.get("contract_number"), 0) > 1 and st in ("active", "future")
               and (r.get("decision") or {}).get("action") not in ("skip", "accept_duplicate"))
        cls, problems = mm.classify(m, cust, ex, dup, today)
        if (r.get("decision") or {}).get("action") == "skip":
            cls, problems = "skipped", [f"not imported — {(r.get('decision') or {}).get('note') or 'coordinator decision'}"]
        diff, conflicts, updates = {}, [], []
        if ex and not ex.get("_overlap"):
            diff = mm.diff_fields(ex, m)
            edited = mm.edited_fields(ex)
            conflicts = [f for f in diff if f in edited]
            updates = [f for f in diff if f not in edited] if ex.get("source") == "maintenance_master" else []
        ev = {"service": planner.get(m.get("record_id") or ""), "sicon_contract_id": None, "sicon_line_ids": []}
        s = sicon.get(m.get("contract_number") or "")
        if s and len(s["ids"]) == 1:
            ev.update({"sicon_contract_id": next(iter(s["ids"])), "sicon_line_ids": sorted(s["lines"])})
        elif s:
            problems.append(f"several Sicon contract IDs for this number: {', '.join(sorted(s['ids']))}")
        counts[cls] += 1
        ops.append((r["id"], {"cls": cls, "problems": problems, "status": st, "match": cust, "evidence": ev,
                              "existing_contract_id": (ex or {}).get("id"), "diff": diff, "conflicts": conflicts,
                              "updates": updates}))
    from pymongo import UpdateOne
    for i in range(0, len(ops), 1000):
        await db.crm2_mm_rows.bulk_write([UpdateOne({"id": rid}, {"$set": upd}) for rid, upd in ops[i:i + 1000]], ordered=False)
    corrected = await db.crm2_mm_rows.count_documents({"upload_id": uid, "corrections": {"$exists": True}})
    return {"counts": counts, "totals": totals, "held_mod": sum(1 for _, u in ops if u["cls"] == "held_mod"),
            "corrected_rows": corrected,
            "evidence": {"service_planner_records": len(planner), "sicon_contract_numbers": len(sicon)},
            "conflicts": sum(1 for _, u in ops if u.get("conflicts")), "classified_at": _now()}


@router.get("/uploads")
async def list_uploads(user=Depends(require_crm_perm("contracts.read"))):
    rows = [await _fresh_same(x) for x in await db.crm2_mm_uploads.find(
        {"organization_id": _org(user)}, {"_id": 0, "sheets": 0}).sort("created_at", -1).to_list(50)]
    cut = await db.crm2_mm_cutover.find_one({"organization_id": _org(user)}, {"_id": 0})
    return {"uploads": rows, "cutover": cut, "sicon_writes_enabled": os.environ.get("SICON_ALLOW_WRITES", "false").lower() == "true"}


async def _fresh_same(u: dict) -> dict:
    if u.get("same_file_as") and await db.crm2_mm_uploads.count_documents(
            {"id": u["same_file_as"], "state": {"$in": ["failed", "uploading"]}}, limit=1):
        u["same_file_as"] = None  # an earlier failed upload is not a real duplicate
    return u


@router.get("/uploads/{uid}")
async def get_upload(uid: str, user=Depends(require_crm_perm("contracts.read"))):
    return await _fresh_same(await _upload(user, uid))


@router.get("/uploads/{uid}/rows")
async def upload_rows(uid: str, cls: str = "", q: str = "", page: int = 1, issue: str = "", coordinator: str = "",
                      unresolved: bool = False, user=Depends(require_crm_perm("contracts.read"))):
    import re
    await _upload(user, uid)
    f = {"upload_id": uid, "role": {"$in": ["contract", "held"]}}
    if cls:
        f["cls"] = cls
    if issue:
        f["problems"] = {"$regex": re.escape(issue), "$options": "i"}
    if coordinator:
        f["mapped.coordinator_name"] = {"$regex": f"^{re.escape(coordinator)}", "$options": "i"}
    if unresolved:
        f.update({"state": "staged", "decision.action": {"$ne": "skip"}, "cls": cls if cls else {"$in": list(UNRESOLVED)}})
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"mapped.customer_name": rx}, {"mapped.contract_number": rx}, {"mapped.site_account": rx}]
    n = await db.crm2_mm_rows.count_documents(f)
    rows = await db.crm2_mm_rows.find(f, {"_id": 0, "raw": 0}).sort([("sheet", 1), ("row", 1)]).skip((max(page, 1) - 1) * 50).limit(50).to_list(50)
    return {"rows": [{**r, "effective": effective(r)} for r in rows], "count": n, "page": page}


class DecisionIn(BaseModel):
    action: str                    # link_company | create_customer | skip | reset
    company_id: Optional[str] = None
    note: str = ""


@router.post("/uploads/{uid}/rows/{rid}/decision")
async def row_decision(uid: str, rid: str, body: DecisionIn, user=Depends(require_crm_perm("contracts.manage"))):
    await _upload(user, uid)
    r = await db.crm2_mm_rows.find_one({"id": rid, "upload_id": uid}, {"_id": 0, "state": 1, "match": 1})
    if not r or r["state"] != "staged":
        raise HTTPException(400, "Only staged rows can be decided.")
    if body.action in ("skip", "accept_duplicate") and not body.note.strip():
        raise HTTPException(400, "Record why this decision was made.")
    if body.action == "link_company":
        co = await db.crm2_companies.find_one({"id": body.company_id or "", "organization_id": _org(user)}, {"_id": 0, "id": 1, "name": 1})
        if not co:
            raise HTTPException(400, "Choose an existing CRM customer.")
        dec = {"action": "link_company", "company_id": co["id"], "company_name": co["name"]}
    elif body.action in ("create_customer", "skip", "reset", "accept_duplicate"):
        dec = {"action": body.action}
    else:
        raise HTTPException(400, "Unknown decision")
    entry = {**dec, "by": _who(user), "at": _now(), "note": body.note}
    await db.crm2_mm_rows.update_one({"id": rid}, {"$set": {"decision": None if body.action == "reset" else entry},
                                                   "$push": {"decision_log": entry}})
    if body.action in ("skip", "accept_duplicate", "reset"):
        await _refresh_summary(_org(user), uid)
    return {"ok": True}


async def _refresh_summary(org: str, uid: str):
    summary = await classify_upload(org, uid)
    await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"summary": summary}})
    return summary


@router.get("/uploads/{uid}/rows/{rid}")
async def row_detail(uid: str, rid: str, user=Depends(require_crm_perm("contracts.read"))):
    await _upload(user, uid)
    r = await db.crm2_mm_rows.find_one({"id": rid, "upload_id": uid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Row not found")
    return {**r, "effective": effective(r)}


CORRECTABLE = {"contract_number", "start_date", "end_date", "contract_amount", "payment_frequency", "customer_name",
               "site_account", "invoice_account", "visits_per_year", "coordinator_name"}


class CorrectIn(BaseModel):
    fields: dict
    reason: str


@router.post("/uploads/{uid}/rows/{rid}/correct")
async def correct_row(uid: str, rid: str, body: CorrectIn, user=Depends(require_crm_perm("contracts.manage"))):
    """Confirmed correction of a flagged row before commit — source cells stay untouched."""
    await _upload(user, uid)
    if not body.reason.strip():
        raise HTTPException(400, "Record why the value is being corrected (e.g. checked against the signed agreement).")
    bad = [k for k in body.fields if k not in CORRECTABLE]
    if bad:
        raise HTTPException(400, f"Cannot correct: {', '.join(bad)}")
    r = await db.crm2_mm_rows.find_one({"id": rid, "upload_id": uid}, {"_id": 0, "state": 1})
    if not r or r["state"] != "staged":
        raise HTTPException(400, "Only rows not yet committed can be corrected.")
    sets, entry = {}, {"by": _who(user), "at": _now(), "reason": body.reason.strip()}
    for k, v in body.fields.items():
        if k in ("start_date", "end_date"):
            v = mm.norm_date(v)[0]
            if not v:
                raise HTTPException(400, f"{k} must be a date (YYYY-MM-DD)")
        if k == "contract_amount":
            v = mm.num(v)
            if v is None:
                raise HTTPException(400, "contract_amount must be a number")
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise HTTPException(400, f"{k} cannot be blank — leave it flagged instead")
        sets[f"corrections.{k}"] = {"value": v, **entry}
    await db.crm2_mm_rows.update_one({"id": rid}, {"$set": sets, "$push": {"decision_log": {"action": "correct", "fields": body.fields, **entry}}})
    summary = await _refresh_summary(_org(user), uid)
    row = await db.crm2_mm_rows.find_one({"id": rid}, {"_id": 0, "raw": 0})
    return {"row": row, "counts": summary["counts"]}


@router.get("/customers")
async def search_customers(q: str, user=Depends(require_crm_perm("contracts.read"))):
    import re
    if len(q.strip()) < 2:
        return {"customers": []}
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    rows = await db.crm2_companies.find({"organization_id": _org(user), "archived": {"$ne": True},
                                         "$or": [{"name": rx}, {"legal_name": rx}, {"sage_account": rx}, {"account_number": rx}]},
                                        {"_id": 0, "id": 1, "name": 1, "legal_name": 1, "sage_account": 1, "postcode": 1}).limit(20).to_list(20)
    return {"customers": rows}


# ───────────────────────────── commit (authorised, resumable, idempotent)

class CommitIn(BaseModel):
    create_missing_customers: bool = False
    limit: Optional[int] = None     # process at most N rows (controlled batches / interruption tests)


@router.post("/uploads/{uid}/commit")
async def commit_upload(uid: str, body: CommitIn, user=Depends(require_crm_perm("exceptions.approve"))):
    u = await _upload(user, uid)
    if u["state"] not in ("ready", "committed", "partial", "commit_failed", "committing"):
        raise HTTPException(400, f"Upload is {u['state']} — wait for the preview.")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    lock = await db.crm2_mm_uploads.update_one(
        {"id": uid, "$or": [{"state": {"$ne": "committing"}}, {"commit.heartbeat": {"$lt": stale}}]},
        {"$set": {"state": "committing", "commit.heartbeat": _now(), "commit.approved_by": _who(user),
                  "commit.approved_at": _now(), "commit.create_missing_customers": body.create_missing_customers}})
    if not lock.modified_count:
        raise HTTPException(409, "This import is already being committed.")
    await record_audit(entity_type="maintenance_master_upload", entity_id=uid, action="approve", user=user,
                       extra={"create_missing_customers": body.create_missing_customers, "limit": body.limit})
    if body.limit:
        await _commit_job(_org(user), uid, user, body)  # synchronous controlled batch
    else:
        _spawn(_commit_job(_org(user), uid, user, body))
    return {"upload_id": uid, "state": "committing"}


# Missing-information rows stay in the review queue until corrected — never committed as if valid.
COMMITTABLE = ("new_contract", "matched_unchanged", "matched_differences", "requires_review")


async def _resolve_company(org: str, r: dict, body: CommitIn, made: dict, actor: str):
    dec = r.get("decision") or {}
    if dec.get("action") == "skip":
        return None, "skipped by coordinator"
    if dec.get("action") == "link_company":
        return {"id": dec["company_id"], "name": dec["company_name"]}, None
    match = r.get("match") or {}
    if match.get("status") == "matched" and match.get("company_id"):
        return {"id": match["company_id"], "name": match.get("company_name")}, None
    if match.get("status") in ("ambiguous", "name_only"):
        return None, "customer match needs a coordinator decision"
    if not (body.create_missing_customers or dec.get("action") == "create_customer"):
        return None, "new customer not approved"
    m = r["mapped"]
    refs = match.get("refs") or mm.account_refs(m.get("site_account"), m.get("invoice_account"))
    key = refs[0] if refs else (m.get("customer_name") or "").strip().lower()
    if key in made:
        return made[key], None
    co = {"id": str(uuid.uuid4()), "organization_id": org, "name": m.get("customer_name") or "Unnamed customer",
          "sage_account": refs[0] if refs else None, "account_refs": refs, "county": m.get("county"),
          "sales_region": m.get("sales_region"), "source": "maintenance_master", "created_by": actor, "created_at": _now()}
    await db.crm2_companies.insert_one(dict(co))
    made[key] = co
    return co, None


async def _commit_job(org: str, uid: str, user: dict, body: CommitIn):
    actor = _who(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    u = await db.crm2_mm_uploads.find_one({"id": uid}, {"_id": 0})
    made, stats, n = {}, {"created": 0, "linked": 0, "updated": 0, "held": 0, "failed": 0}, 0
    try:
        async for r in db.crm2_mm_rows.find({"upload_id": uid, "state": "staged", "cls": {"$in": list(COMMITTABLE)}},
                                            {"_id": 0}).sort([("sheet", 1), ("row", 1)]):
            if body.limit and n >= body.limit:
                break
            n += 1
            try:
                res = await _commit_row(org, u, r, body, made, actor, today)
                stats[res] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed"] += 1
                await db.crm2_mm_rows.update_one({"id": r["id"]}, {"$set": {"commit_error": str(e)[:300]}})
            if n % 50 == 0:
                await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"commit.heartbeat": _now(), "commit.progress": stats}})
        left = await db.crm2_mm_rows.count_documents({"upload_id": uid, "state": "staged", "cls": {"$in": list(COMMITTABLE)},
                                                      "hold_reason": {"$exists": False}})
        state = "partial" if left else "committed"
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"state": state, "commit.progress": stats,
                                                                   "commit.finished_at": _now(), "commit.remaining": left}})
    except Exception as e:  # noqa: BLE001
        log.exception("maintenance master commit failed")
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"state": "commit_failed", "error": str(e)[:500]}})


async def _change(contract: dict, field: str, old, new, actor: str, reason: str, approval=None, source="crm_edit", bump=True):
    await db.crm2_contract_changes.insert_one({
        "id": str(uuid.uuid4()), "contract_id": contract["id"], "organization_id": contract["organization_id"],
        "mm_record_key": contract.get("mm_record_key"), "contract_number": contract.get("contract_number"),
        "field": field, "old": old, "new": new, "by": actor, "at": _now(), "reason": reason,
        "approval": approval, "source": source, "revision": (contract.get("revision") or 1) + (1 if bump else 0)})


async def _commit_row(org, u, r, body, made, actor, today) -> str:
    if r.get("existing_contract_id"):
        c = await db.crm2_contracts.find_one({"id": r["existing_contract_id"]}, {"_id": 0})
        link = {"mm_record_key": c.get("mm_record_key") or r["record_key"], "updated_at": _now()}
        if not c.get("mm_source"):
            link["mm_source"] = {"upload_id": u["id"], "sha256": u["sha256"], "filename": u["filename"],
                                 "sheet": r["sheet"], "row": r["row"], "raw": r["raw"]}
            link["mm_differences"] = r.get("diff") or {}  # pre-existing CRM contract: CRM wins, differences kept for review
        sets, done = {}, "linked"
        for f in r.get("updates") or []:
            new = r["diff"][f]["source"]
            old = mm.current(c, f)
            await _change(c, f, old, new, "maintenance_master_reimport", f"Updated from {u['filename']}", source="workbook")
            if f in ("start_date", "end_date", "annual_value", "coordinator_name", "visits_per_year", "payment_frequency",
                     "direct_debit", "sicon_contract_id", "sage_account_ref"):
                sets[f] = new
            else:
                sets[f"mm.{f}"] = new
            sets[f"mm_baseline.{f}"] = new
            done = "updated"
        if r.get("conflicts"):
            link["mm_conflicts"] = {f: r["diff"][f] for f in r["conflicts"]}
        upd = {"$set": {**link, **sets}}
        if sets:
            upd["$inc"] = {"revision": 1}
        await db.crm2_contracts.update_one({"id": c["id"]}, upd)
        await db.crm2_mm_rows.update_one({"id": r["id"]}, {"$set": {"state": "committed", "contract_id": c["id"], "result": done}})
        return done
    company, why = await _resolve_company(org, r, body, made, actor)
    if not company:
        await db.crm2_mm_rows.update_one({"id": r["id"]}, {"$set": {"hold_reason": why}})
        return "held"
    doc = mm.new_contract_doc(org, u, {**r, "mapped": effective(r), "evidence": r.get("evidence")}, company, actor, today)
    if r.get("corrections"):
        doc["mm_corrections"] = r["corrections"]
    doc["mm_exceptions"] = r.get("problems") or []
    if doc["annual_value"] is None:
        doc["mm_exceptions"].append("annual value not stated as annual in the workbook — confirm")
    try:
        await db.crm2_contracts.insert_one(dict(doc))
        cid, res = doc["id"], "created"
    except DuplicateKeyError:  # retried after an interruption — already there
        cid = (await db.crm2_contracts.find_one({"organization_id": org, "mm_record_key": r["record_key"]}, {"_id": 0, "id": 1}))["id"]
        res = "linked"
    await db.crm2_mm_rows.update_one({"id": r["id"]}, {"$set": {"state": "committed", "contract_id": cid, "result": res},
                                                        "$unset": {"hold_reason": ""}})
    return res


# ───────────────────────────── coordinator editing (revisioned, audited)

@router.get("/contracts")
async def mm_contracts(q: str = "", status: str = "", sync: str = "", exceptions: bool = False, page: int = 1,
                       user=Depends(require_crm_perm("contracts.read"))):
    import re
    f = {"organization_id": _org(user), "mm_record_key": {"$type": "string"}}
    if status:
        f["status"] = status
    if sync:
        f["sicon_sync.state"] = sync
    if exceptions:
        f["$or"] = [{"mm_exceptions.0": {"$exists": True}}, {"mm_conflicts": {"$exists": True, "$ne": {}}}]
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        f.setdefault("$and", []).append({"$or": [{"company_name": rx}, {"title": rx}, {"contract_number": rx},
                                                  {"sage_account_ref": rx}, {"coordinator_name": rx}]})
    n = await db.crm2_contracts.count_documents(f)
    rows = await db.crm2_contracts.find(f, {"_id": 0, "mm_source.raw": 0, "mm_baseline": 0}).sort("contract_number", 1) \
        .skip((max(page, 1) - 1) * 50).limit(50).to_list(50)
    return {"contracts": rows, "count": n}


@router.get("/contracts/{cid}")
async def mm_contract(cid: str, user=Depends(require_crm_perm("contracts.read"))):
    c = await db.crm2_contracts.find_one({"id": cid, "organization_id": _org(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    hist = await db.crm2_contract_changes.find({"contract_id": cid}, {"_id": 0}).sort("at", -1).to_list(500)
    return {"contract": c, "changes": hist}


class EditIn(BaseModel):
    revision: int
    changes: dict
    reason: str = ""
    approval_ref: str = ""


@router.patch("/contracts/{cid}")
async def edit_contract(cid: str, body: EditIn, user=Depends(require_crm_perm("contracts.manage"))):
    c = await db.crm2_contracts.find_one({"id": cid, "organization_id": _org(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    bad = [k for k in body.changes if k not in mm.EDITABLE]
    if bad:
        raise HTTPException(400, f"Not editable here: {', '.join(bad)}")
    if "sicon_contract_id" in body.changes and "exceptions.approve" not in (user.get("crm_permissions") or []):
        raise HTTPException(403, "Only a manager can record a verified Sicon contract ID.")
    for k in ("start_date", "end_date", "next_action_date"):
        if body.changes.get(k) and not mm.norm_date(body.changes[k])[0]:
            raise HTTPException(400, f"{k} must be a date (YYYY-MM-DD)")
    if body.changes.get("annual_value") not in (None, "") and mm.num(body.changes["annual_value"]) is None:
        raise HTTPException(400, "annual_value must be a number")
    sets, diffs = {}, []
    for f, new in body.changes.items():
        new = mm.num(new) if f in ("annual_value", "original_amount", "contract_amount") and new not in (None, "") else new
        old = mm.current(c, f)
        if str(old or "") == str(new or ""):
            continue
        diffs.append((f, old, new))
        top = f in ("start_date", "end_date", "annual_value", "coordinator_name", "visits_per_year", "payment_frequency",
                    "direct_debit", "sicon_contract_id", "sage_account_ref")
        sets[f if top else f"mm.{f}"] = new
        if f == "customer_name":
            sets["title"] = new
    if not diffs:
        return {"contract": c, "changed": []}
    sets.update({"updated_at": _now(), "updated_by": _who(user)})
    s = c.get("sicon_sync") or {}
    if s.get("state") == "synced_verified":
        sets["sicon_sync.state"] = "changes_pending"
    res = await db.crm2_contracts.update_one({"id": cid, "revision": body.revision}, {"$set": sets, "$inc": {"revision": 1}})
    if not res.modified_count:
        raise HTTPException(409, "Someone else saved this contract — reload to see their changes before editing.")
    for f, old, new in diffs:
        await _change(c, f, old, new, _who(user), body.reason, approval={"ref": body.approval_ref} if body.approval_ref else None)
    c = await db.crm2_contracts.find_one({"id": cid}, {"_id": 0})
    if s.get("state") != "synced_verified":
        await db.crm2_contracts.update_one({"id": cid}, {"$set": {"sicon_sync.state": mm.sicon_state(c)}})
    await record_audit(entity_type="crm_contract", entity_id=cid, action="update", user=user,
                       extra={"fields": [d[0] for d in diffs], "source": "maintenance_master_edit"})
    return {"contract": await db.crm2_contracts.find_one({"id": cid}, {"_id": 0}), "changed": [d[0] for d in diffs]}


class NoteIn(BaseModel):
    text: str


@router.post("/contracts/{cid}/notes")
async def add_note(cid: str, body: NoteIn, user=Depends(require_crm_perm("contracts.manage"))):
    if not body.text.strip():
        raise HTTPException(400, "Note is empty")
    c = await db.crm2_contracts.find_one({"id": cid, "organization_id": _org(user)}, {"_id": 0, "id": 1, "organization_id": 1,
                                                                                    "mm_record_key": 1, "contract_number": 1, "revision": 1})
    if not c:
        raise HTTPException(404, "Contract not found")
    note = {"id": str(uuid.uuid4()), "text": body.text.strip(), "by": _who(user), "at": _now()}
    await db.crm2_contracts.update_one({"id": cid}, {"$push": {"mm_notes": note}})
    await _change(c, "note", None, note["text"], _who(user), "note added", bump=False)
    return note


# ───────────────────────────── deferred Sicon (no external writes)

@router.post("/contracts/{cid}/sicon-queue")
async def queue_sicon(cid: str, user=Depends(require_crm_perm("exceptions.approve"))):
    c = await db.crm2_contracts.find_one({"id": cid, "organization_id": _org(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    op = "update" if c.get("sicon_contract_id") else "create_or_match"
    key = f"{cid}:r{c.get('revision') or 1}"
    entry = {"id": str(uuid.uuid4()), "key": key, "organization_id": _org(user), "contract_id": cid,
             "contract_number": c.get("contract_number"), "revision": c.get("revision") or 1, "operation": op,
             "endpoints": ["POST /api/Contract/CreateUpdateContract", "POST /api/ContractLine/PostContractLine"],
             "preconditions": ["Sicon API family confirmed", "Sage company + customer account mapped",
                               "existing Sicon contract checked and identity reconciled", "existing lines reconciled",
                               "manager approval of the initial reconciliation"],
             "payload_preview": {"ContractNumber": c.get("contract_number"), "CustomerAccount": c.get("sage_account_ref"),
                                 "StartDate": c.get("start_date"), "EndDate": c.get("end_date"),
                                 "SiconContractId": c.get("sicon_contract_id"), "AnnualValue": c.get("annual_value")},
             "state": "held_writes_disabled" if os.environ.get("SICON_ALLOW_WRITES", "false").lower() != "true"
             else "awaiting_controlled_reconciliation",
             "approved_by": _who(user), "created_at": _now(), "external_write_attempted": False}
    await db.crm2_sicon_contract_queue.create_index("key", unique=True)
    try:
        await db.crm2_sicon_contract_queue.insert_one(dict(entry))
    except DuplicateKeyError:
        entry = await db.crm2_sicon_contract_queue.find_one({"key": key}, {"_id": 0})
    entry.pop("_id", None)
    await db.crm2_contracts.update_one({"id": cid}, {"$set": {
        "sicon_sync.state": "held_for_sicon", "sicon_sync.held_revision": entry["revision"],
        "sicon_sync.previous_approved_revision": (c.get("sicon_sync") or {}).get("held_revision"),
        "sicon_sync.queue_id": entry["id"], "sicon_sync.last_attempt_at": None,
        "sicon_sync.last_result": "held — SICON_ALLOW_WRITES is false; nothing sent"}})
    return entry


@router.get("/sicon-queue")
async def sicon_queue(user=Depends(require_crm_perm("contracts.read"))):
    rows = await db.crm2_sicon_contract_queue.find({"organization_id": _org(user)}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"queue": rows, "sicon_writes_enabled": os.environ.get("SICON_ALLOW_WRITES", "false").lower() == "true"}


class SimMatch(BaseModel):
    contract_number: str
    sicon_contract_id: str
    sicon_line_ids: list[str] = []


class SimIn(BaseModel):
    matches: list[SimMatch]
    apply: bool = False


@router.post("/sicon-reconcile")
async def sicon_reconcile(body: SimIn, user=Depends(require_crm_perm("exceptions.approve"))):
    """Match Sicon contract identities (from a verified Sicon read/export) to CRM contracts.
    Never creates contracts here or in Sicon; ambiguous identities go to review."""
    out = {"matched": [], "already": [], "conflict": [], "not_found": []}
    for mt in body.matches:
        cs = await db.crm2_contracts.find({"organization_id": _org(user), "contract_number": mt.contract_number,
                                           "status": {"$nin": ["cancelled"]}}, {"_id": 0}).to_list(5)
        if not cs:
            out["not_found"].append(mt.contract_number)
            continue
        if len(cs) > 1:
            out["conflict"].append({"contract_number": mt.contract_number, "reason": "several CRM contracts share this number"})
            continue
        c = cs[0]
        other = await db.crm2_contracts.find_one({"organization_id": _org(user), "sicon_contract_id": mt.sicon_contract_id,
                                                  "id": {"$ne": c["id"]}}, {"_id": 0, "contract_number": 1})
        if other or (c.get("sicon_contract_id") and c["sicon_contract_id"] != mt.sicon_contract_id):
            out["conflict"].append({"contract_number": mt.contract_number, "reason": "Sicon ID already used / differs — review"})
            if body.apply:
                await db.crm2_contracts.update_one({"id": c["id"]}, {"$set": {
                    "sicon_sync.state": "conflict", "sicon_sync.conflict": {"offered_sicon_contract_id": mt.sicon_contract_id,
                                                                           "at": _now(), "by": _who(user)}}})
            continue
        if (c.get("sicon_sync") or {}).get("identity_verified"):
            out["already"].append(mt.contract_number)
            continue
        out["matched"].append(mt.contract_number)
        if body.apply:
            await db.crm2_contracts.update_one({"id": c["id"]}, {"$set": {
                "sicon_contract_id": mt.sicon_contract_id, "sicon_sync.sicon_contract_id": mt.sicon_contract_id,
                "sicon_sync.sicon_line_ids": mt.sicon_line_ids, "sicon_sync.identity_verified": True,
                "sicon_sync.state": "ready_for_sync", "sicon_sync.verified_by": _who(user), "sicon_sync.verified_at": _now()}})
            await _change(c, "sicon_contract_id", c.get("sicon_contract_id"), mt.sicon_contract_id, _who(user),
                          "Sicon identity reconciled", source="sicon_reconcile", bump=False)
    return {**out, "applied": body.apply, "external_writes": 0}


# ───────────────────────────── reports / exports / cutover

def _xlsx(sheets: dict) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name[:31])
        for r in rows:
            ws.append([("" if v is None else v if isinstance(v, (int, float)) else str(v)) for v in r])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _send(blob: bytes, name: str):
    return StreamingResponse(io.BytesIO(blob), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/uploads/{uid}/report")
async def upload_report(uid: str, kind: str = "reconciliation", user=Depends(require_crm_perm("contracts.read"))):
    u = await _upload(user, uid)
    f = {"upload_id": uid, "role": {"$in": ["contract", "held"]}}
    if kind == "unresolved":
        f.update({"state": "staged", "decision.action": {"$ne": "skip"}, "cls": {"$in": list(UNRESOLVED)}})
    elif kind == "exceptions":
        f["$or"] = [{"cls": {"$in": ["duplicate_overlap", "missing_information", "requires_review"]}},
                    {"problems.0": {"$exists": True}}, {"conflicts.0": {"$exists": True}}, {"hold_reason": {"$exists": True}}]
    head = ["Sheet", "Row", "Record key", "Customer / site", "Contract number", "Start", "Expiry", "Status",
            "Classification", "Problems", "Customer match", "Differences", "Conflicts (app kept)", "State", "Hold reason", "CRM contract ID"]
    rows = [head]
    async for r in db.crm2_mm_rows.find(f, {"_id": 0, "raw": 0}).sort([("sheet", 1), ("row", 1)]):
        m = r["mapped"]
        rows.append([r["sheet"], r["row"], r["record_key"], m.get("customer_name"), m.get("contract_number"), m.get("start_date"),
                     m.get("end_date"), r.get("status"), r.get("cls"), "; ".join(r.get("problems") or []),
                     (r.get("match") or {}).get("basis"), "; ".join(f"{k}: {v['crm']} → {v['source']}" for k, v in (r.get("diff") or {}).items()),
                     ", ".join(r.get("conflicts") or []), r.get("state"), r.get("hold_reason"), r.get("contract_id")])
    s = u.get("summary") or {}
    summary = [["File", u["filename"]], ["SHA-256", u.get("sha256")], ["Uploaded", u.get("uploaded_at")], ["Uploaded by", u.get("uploaded_by")],
               ["State", u["state"]], [], ["Classification", "Rows"]] + [[k, v] for k, v in (s.get("counts") or {}).items()]
    summary += [[], ["Sheet", "Rows", "Active", "Expired", "Future", "Uncertain", "Contract amount £", "Original amount £", "Stated annual £",
                     "CRM contracts", "CRM annual £"]]
    for sh, t in (s.get("totals") or {}).items():
        keys = [r["record_key"] async for r in db.crm2_mm_rows.find({"upload_id": uid, "sheet": sh, "state": "committed"}, {"record_key": 1})]
        crm = await db.crm2_contracts.find({"organization_id": _org(user), "mm_record_key": {"$in": keys}}, {"annual_value": 1}).to_list(20000)
        summary.append([sh, t["rows"], t["active"], t["expired"], t["future"], t["uncertain"], t["contract_amount"],
                        t["original_amount"], t["annual_value"], len(crm), round(sum(c.get("annual_value") or 0 for c in crm), 2)])
    blob = await asyncio.to_thread(_xlsx, {"Summary": summary, "Rows": rows})
    return _send(blob, f"maintenance-master-{kind}-{u['created_at'][:10]}.xlsx")


@router.get("/export/current")
async def export_current(user=Depends(require_crm_perm("contracts.read"))):
    head = ["CRM contract ID", "Master record", "Contract number", "Customer", "Sage account", "Status", "Start", "Expiry",
            "Annual value £", "Payment frequency", "Direct Debit", "Services / year", "Coordinator", "Revision",
            "Sicon contract ID", "Sicon sync state", "Exceptions", "Source sheet", "Source row"]
    rows = [head]
    async for c in db.crm2_contracts.find({"organization_id": _org(user), "mm_record_key": {"$type": "string"}},
                                          {"_id": 0, "mm_source.raw": 0}).sort("contract_number", 1):
        src = c.get("mm_source") or {}
        rows.append([c["id"], c.get("mm_record_key"), c.get("contract_number"), c.get("company_name"), c.get("sage_account_ref"),
                     c.get("status"), c.get("start_date"), c.get("end_date"), c.get("annual_value"), c.get("payment_frequency"),
                     c.get("direct_debit"), c.get("visits_per_year"), c.get("coordinator_name"), c.get("revision"),
                     c.get("sicon_contract_id"), (c.get("sicon_sync") or {}).get("state"), "; ".join(c.get("mm_exceptions") or []),
                     src.get("sheet"), src.get("row")])
    changes = [["Contract number", "Field", "Old", "New", "By", "At", "Reason", "Source"]]
    async for h in db.crm2_contract_changes.find({"organization_id": _org(user)}, {"_id": 0}).sort("at", 1):
        changes.append([h.get("contract_number"), h["field"], h.get("old"), h.get("new"), h.get("by"), h.get("at"), h.get("reason"), h.get("source")])
    blob = await asyncio.to_thread(_xlsx, {"Contracts": rows, "Change history": changes})
    return _send(blob, f"crm-contracts-{datetime.now(timezone.utc):%Y-%m-%d}.xlsx")


def _rebuild_master(blob: bytes, edits: list, appended: list, changes: list) -> bytes:
    """Original workbook, original layout/formulas — only edited cells changed, new contracts appended."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob))
    cols = {}
    for name in mm.CONTRACT_SHEETS:
        if name in wb.sheetnames:
            ws = wb[name]
            cols[name] = {str(c.value).strip(): c.column for c in ws[1] if c.value}
    for sheet, row, header, value in edits:
        col = cols.get(sheet, {}).get(header)
        if col:
            wb[sheet].cell(row=row, column=col, value=value)
    if appended and "Maintenance Database" in wb.sheetnames:
        ws = wb["Maintenance Database"]
        nxt = max((r for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value), default=1) + 1
        for vals in appended:
            for header, value in vals.items():
                col = cols["Maintenance Database"].get(header)
                if col:
                    ws.cell(row=nxt, column=col, value=value)
            nxt += 1
    ws = wb.create_sheet("Pulse Fitness Pro changes")
    ws.append(["Sheet", "Row", "Contract number", "Field", "Workbook column", "Old", "New", "Changed by", "Changed at", "Reason"])
    for ch in changes:
        ws.append(ch)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@router.get("/export/master")
async def export_master(user=Depends(require_crm_perm("contracts.read"))):
    org = _org(user)
    u = await db.crm2_mm_uploads.find_one({"organization_id": org, "state": {"$in": ["committed", "partial"]}},
                                          {"_id": 0}, sort=[("created_at", -1)])
    if not u:
        raise HTTPException(400, "No committed Maintenance Master yet.")
    rev = {v: k for k, v in mm.FIELDS.items()}
    edits, appended, changes = [], [], []
    heads = {sh["name"]: set(sh.get("headers") or []) for sh in u.get("sheets") or []}
    pos = {r["record_key"]: {"sheet": r["sheet"], "row": r["row"]} async for r in db.crm2_mm_rows.find(
        {"upload_id": u["id"], "role": "contract"}, {"_id": 0, "record_key": 1, "sheet": 1, "row": 1})}
    async for c in db.crm2_contracts.find({"organization_id": org, "mm_record_key": {"$type": "string"}},
                                          {"_id": 0, "mm_source.raw": 0}):
        src = pos.get(c["mm_record_key"])
        if not src:
            continue
        written = set()
        for f in mm.edited_fields(c):
            if f in rev and rev[f] in heads.get(src["sheet"], set()) and mm.current(c, f) not in (None, ""):
                edits.append((src["sheet"], src["row"], rev[f], mm.current(c, f)))
                written.add(f)  # a blank never overwrites a populated workbook cell — it is listed instead
        if mm.edited_fields(c):
            async for h in db.crm2_contract_changes.find({"contract_id": c["id"], "field": {"$ne": "note"}}, {"_id": 0}).sort("at", 1):
                changes.append([src.get("sheet"), src.get("row"), c.get("contract_number"), h["field"],
                                rev.get(h["field"]) if h["field"] in written else "no column in workbook — listed here only",
                                str(h.get("old") if h.get("old") is not None else ""), str(h.get("new") if h.get("new") is not None else ""),
                                h.get("by"), h.get("at"), h.get("reason")])
    async for c in db.crm2_contracts.find({"organization_id": org, "status": "active", "source": {"$ne": "maintenance_master"},
                                           "mm_record_key": {"$exists": False}}, {"_id": 0}).limit(2000):
        appended.append({"Customer / site": c.get("company_name") or c.get("title"), "Contract number": c.get("contract_number"),
                         "Start date": c.get("start_date"), "Expiry date": c.get("end_date"),
                         "Contract amount (£)": c.get("annual_value"), "Payment frequency": c.get("payment_frequency") or "Annually",
                         "Comments": "Added in Pulse Fitness Pro"})
    blob = await asyncio.to_thread(_rebuild_master, await _read_file(u), edits, appended, changes)
    return _send(blob, f"Maintenance Master - from Pulse Fitness Pro {datetime.now(timezone.utc):%d.%m.%Y}.xlsx")


@router.get("/uploads/{uid}/original")
async def download_original(uid: str, user=Depends(require_crm_perm("contracts.read"))):
    u = await _upload(user, uid)
    return _send(await _read_file(u), u["filename"])


class CutoverIn(BaseModel):
    upload_id: str
    note: str = ""


@router.post("/cutover")
async def cutover(body: CutoverIn, user=Depends(require_crm_perm("exceptions.approve"))):
    u = await _upload(user, body.upload_id)
    if u["state"] != "committed":
        raise HTTPException(400, "Commit the whole workbook (no remaining rows) before cutover.")
    doc = {"organization_id": _org(user), "upload_id": u["id"], "sha256": u["sha256"], "filename": u["filename"],
           "approved_by": _who(user), "at": _now(), "note": body.note,
           "statement": "Contract Management is the editable system of record; the workbook is retained as migration evidence."}
    await db.crm2_mm_cutover.update_one({"organization_id": _org(user)}, {"$set": doc}, upsert=True)
    await record_audit(entity_type="maintenance_master_upload", entity_id=u["id"], action="approve", user=user, extra={"cutover": True})
    return doc


@router.post("/uploads/{uid}/reparse")
async def reparse_upload(uid: str, user=Depends(require_crm_perm("contracts.manage"))):
    """Rebuild the preview from the stored original (e.g. after a mapping fix). Committed rows are kept."""
    u = await _upload(user, uid)
    if u["state"] in ("parsing", "classifying", "committing", "uploading"):
        raise HTTPException(409, f"Upload is {u['state']}")
    if await db.crm2_mm_rows.count_documents({"upload_id": uid, "state": "committed"}, limit=1):
        summary = await classify_upload(_org(user), uid)
        await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"summary": summary}})
        return {"upload_id": uid, "state": u["state"], "reclassified": True}
    await db.crm2_mm_uploads.update_one({"id": uid}, {"$set": {"state": "parsing"}})
    _spawn(_parse_job(_org(user), uid))
    return {"upload_id": uid, "state": "parsing"}


# ───────────────────────────── coordinator daily view

@router.get("/daily")
async def daily_view(coordinator: str = "", user=Depends(require_crm_perm("contracts.read"))):
    """Actionable work for the day across contracts, renewals, service, imports, billing and Sicon."""
    import re
    from utils.cm_service_link import obligation_bucket
    org = _org(user)
    today = datetime.now(timezone.utc).date()
    t, soon = today.isoformat(), (today + timedelta(days=90)).isoformat()
    base = {"organization_id": org}
    if coordinator:
        base["coordinator_name"] = {"$regex": f"^{re.escape(coordinator)}", "$options": "i"}
    proj = {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "title": 1, "end_date": 1, "status": 1,
            "coordinator_name": 1, "mm_exceptions": 1, "mm": 1, "annual_value": 1, "payment_frequency": 1}

    async def grab(extra, sort=("end_date", 1)):
        follow = extra.pop("_follow", False)
        f = {**base, **extra}
        n = await db.crm2_contracts.count_documents(f)
        rows = await db.crm2_contracts.find(f, proj).sort(*sort).limit(8).to_list(8)
        return {"count": n, "items": [{"id": r["id"], "contract_number": r.get("contract_number"),
                                       "customer": r.get("company_name") or r.get("title"), "end_date": r.get("end_date"),
                                       "status": r.get("status"),
                                       "detail": (f"{(r.get('mm') or {}).get('next_action') or 'Follow up'} · due {(r.get('mm') or {}).get('next_action_date')}"
                                                  if follow else "; ".join((r.get("mm_exceptions") or [])[:2]) or (r.get("mm") or {}).get("next_action"))}
                          for r in rows]}
    cards = {
        "expiring_soon": await grab({"status": "active", "end_date": {"$gte": t, "$lte": soon}}),
        "renewals": await grab({"status": {"$in": ["renewal_pending_approval", "renewal_draft", "renewal_pending"]}}),
        "missing_information": await grab({"mm_exceptions.0": {"$exists": True}, "status": {"$nin": ["expired", "cancelled"]}}),
        "awaiting_approval": await grab({"status": {"$in": ["draft", "pending_approval"]}}),
        "follow_up": await grab({"_follow": True, "mm.next_action_date": {"$lte": t, "$gte": "2000-01-01"}, "status": {"$nin": ["expired", "cancelled"]}},
                                ("mm.next_action_date", 1)),
        "unverified_billing": await grab({"historical_import": True, "status": "active", "$or": [
            {"annual_value": None}, {"payment_frequency": {"$in": [None, ""]}}]}),
        "sicon_pending": await grab({"mm_record_key": {"$type": "string"}, "status": "active",
                                     "sicon_sync.state": {"$nin": ["ready_for_sync", "synced_verified"]}}),
    }
    svc = {"due": 0, "overdue": 0, "review": 0, "items": []}
    live = {c["id"]: c async for c in db.crm2_contracts.find({**base, "status": "active"},
                                                             {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1})}
    async for sc in db.crm2_afs_service_schedules.find({"organization_id": org, "contract_id": {"$in": list(live)}},
                                                       {"_id": 0, "contract_id": 1, "visits": 1}):
        ct = live[sc["contract_id"]]
        for v in sc.get("visits") or []:
            b = obligation_bucket(v, t)
            if b in ("due", "overdue", "review"):
                svc[b] += 1
                if len(svc["items"]) < 8:
                    svc["items"].append({"id": ct["id"], "contract_number": ct.get("contract_number"), "customer": ct.get("company_name"),
                                         "detail": f"PPM due {v.get('planned_date')} · {b}"})
    cards["service_attention"] = {"count": svc["due"] + svc["overdue"] + svc["review"], **svc}
    latest = await db.crm2_mm_uploads.find_one({"organization_id": org, "state": {"$nin": ["failed", "uploading"]}},
                                               {"_id": 0, "id": 1, "filename": 1}, sort=[("created_at", -1)])
    unresolved = 0
    if latest:
        f = {"upload_id": latest["id"], "state": "staged", "decision.action": {"$ne": "skip"}, "cls": {"$in": list(UNRESOLVED)}}
        if coordinator:
            f["mapped.coordinator_name"] = {"$regex": f"^{re.escape(coordinator)}", "$options": "i"}
        unresolved = await db.crm2_mm_rows.count_documents(f)
    cards["import_exceptions"] = {"count": unresolved, "upload_id": (latest or {}).get("id"), "items": []}
    coords = sorted({c for c in await db.crm2_contracts.distinct("coordinator_name", {"organization_id": org}) if c})
    return {"today": t, "coordinator": coordinator, "coordinators": coords, "cards": cards}


# ───────────────────────────── monthly invoice-run preview (no posting)

LIVE = ("active", "pending_start", "renewal_pending_approval", "renewal_draft")
_FREQ = {"annually": 12, "annual": 12, "yearly": 12, "monthly": 1, "quarterly": 3, "bi-annually": 6, "biannual": 6,
         "six monthly": 6, "half yearly": 6, "semiannual": 6}


async def _vat_pct(org: str):
    s = await db.crm2_afs_settings.find_one({"organization_id": org}, {"_id": 0, "vat_pct": 1}) or {}
    return s.get("vat_pct")


@router.get("/invoice-run")
async def invoice_run(period: str, user=Depends(require_crm_perm("contracts.read"))):
    """Proposed maintenance invoices for one month — preview only, nothing is created or posted."""
    from utils.cm_dates import add_months, parse_date
    if not re.fullmatch(r"\d{4}-\d{2}", period or ""):
        raise HTTPException(400, "period must be YYYY-MM")
    org = _org(user)
    vat = await _vat_pct(org)
    rows, seen = [], {}

    def add(row):
        key = (row["contract_id"], row["billing_date"])
        if key in seen:
            row["warnings"].append("duplicate billing obligation — excluded from total")
            row["duplicate"] = True
        seen[key] = True
        rows.append(row)
    contracts = {c["id"]: c async for c in db.crm2_contracts.find({"organization_id": org}, {"_id": 0, "mm_source": 0, "mm_baseline": 0})}
    orphans = 0
    async for b in db.crm2_afs_billing.find({"organization_id": org}, {"_id": 0}):
        c = contracts.get(b.get("contract_id"))
        if not c or c.get("status") not in LIVE:
            orphans += sum(1 for inv in b.get("invoices") or [] if str(inv.get("due_date") or "").startswith(period))
            continue  # never propose billing for a missing, cancelled or expired contract
        for inv in b.get("invoices") or []:
            if not str(inv.get("due_date") or "").startswith(period):
                continue
            w = []
            done = inv.get("status") in ("raised", "invoiced", "paid", "posted") or inv.get("sage_invoice_ref")
            if done:
                w.append("already invoiced — not proposed again")
            add({"contract_id": b["contract_id"], "contract_number": c.get("contract_number"), "customer": c.get("company_name"),
                 "description": c.get("title") or "Maintenance agreement", "frequency": b.get("frequency"),
                 "billing_date": inv["due_date"], "amount": inv.get("amount"), "amount_basis": "agreed billing schedule",
                 "sage_account": c.get("sage_account_ref") or c.get("sage_reference"), "status": "already_invoiced" if done else "proposed",
                 "direct_debit": c.get("direct_debit") or c.get("payment_method"), "source": "agreement billing schedule", "warnings": w,
                 "duplicate": False, "existing_ref": inv.get("sage_invoice_ref")})
    billed = {r["contract_id"] for r in rows}
    y, mth = int(period[:4]), int(period[5:])
    for c in contracts.values():
        if not c.get("historical_import") or c.get("status") != "active" or c["id"] in billed:
            continue
        sd, ed = parse_date(c.get("start_date")), parse_date(c.get("end_date"))
        step = _FREQ.get((c.get("payment_frequency") or "").strip().lower())
        w = []
        if not sd:
            continue
        if not step:
            w.append(f"billing frequency '{c.get('payment_frequency') or 'missing'}' not recognised")
            step = None
        due = None
        if step:
            k = ((y - sd.year) * 12 + (mth - sd.month))
            if k < 0 or k % step:
                continue
            due = add_months(sd, k)
            if ed and due > ed:
                continue
        elif sd.month != mth:
            continue
        amount, basis = None, ""
        mmv = c.get("mm") or {}
        if step == 12 and c.get("annual_value") is not None:
            amount, basis = c["annual_value"], "annual value"
        elif mmv.get("instalment_amount") not in (None, ""):
            amount, basis = mm.num(mmv["instalment_amount"]), "confirmed instalment amount"
        else:
            w.append("instalment amount not confirmed — workbook contract amount shown for reference only")
        if not c.get("sage_account_ref"):
            w.append("Sage account missing")
        add({"contract_id": c["id"], "contract_number": c.get("contract_number"), "customer": c.get("company_name"),
             "description": mmv.get("contract_type") or "Maintenance contract", "frequency": c.get("payment_frequency"),
             "billing_date": (due or sd).isoformat(), "amount": amount, "amount_basis": basis,
             "reference_amount": mmv.get("contract_amount"), "sage_account": c.get("sage_account_ref"),
             "status": "proposed" if amount is not None and not w else "needs_information",
             "direct_debit": c.get("direct_debit"), "source": "Maintenance Master import", "warnings": w,
             "duplicate": False, "invoice_history": mmv.get("invoice_numbers")})
    ok = [r for r in rows if r["status"] == "proposed" and not r["duplicate"]]
    net = round(sum(r["amount"] or 0 for r in ok), 2)
    rows.sort(key=lambda r: (r["billing_date"], r["customer"] or ""))
    return {"period": period, "rows": rows, "vat_pct": vat, "vat_verified": vat is not None,
            "totals": {"proposed": len(ok), "net": net, "vat": round(net * vat, 2) if vat is not None else None,
                       "gross": round(net * (1 + vat), 2) if vat is not None else None,
                       "needs_information": sum(1 for r in rows if r["status"] == "needs_information"),
                       "already_invoiced": sum(1 for r in rows if r["status"] == "already_invoiced"),
                       "duplicates": sum(1 for r in rows if r["duplicate"]),
                       "excluded_not_live": orphans},
            "preview_only": True, "posting_enabled": False}


@router.get("/invoice-run/export")
async def invoice_run_export(period: str, user=Depends(require_crm_perm("contracts.read"))):
    d = await invoice_run(period, user)
    head = ["Billing date", "Contract", "Customer", "Description", "Frequency", "Amount £", "Basis", "Workbook amount £",
            "Sage account", "Direct Debit", "Status", "Warnings", "Source"]
    rows = [head] + [[r["billing_date"], r["contract_number"], r["customer"], r["description"], r["frequency"], r["amount"],
                      r["amount_basis"], r.get("reference_amount"), r["sage_account"], r["direct_debit"], r["status"],
                      "; ".join(r["warnings"]), r["source"]] for r in d["rows"]]
    t = d["totals"]
    summary = [["Period", period], ["PREVIEW ONLY — nothing has been invoiced or posted"], ["Proposed invoices", t["proposed"]],
               ["Net £", t["net"]], ["VAT rate", d["vat_pct"] if d["vat_verified"] else "not configured — VAT not calculated"],
               ["VAT £", t["vat"]], ["Gross £", t["gross"]], ["Needs information", t["needs_information"]],
               ["Already invoiced", t["already_invoiced"]], ["Duplicates excluded", t["duplicates"]],
               ["Not proposed — contract missing / not live", t["excluded_not_live"]]]
    blob = await asyncio.to_thread(_xlsx, {"Summary": summary, "Invoice run": rows})
    return _send(blob, f"invoice-run-preview-{period}.xlsx")
