"""Master Admin → Import Centre → Sage Customer Accounts / Sicon Customer Contacts.

Upload → identify format → validate → review relationships → approve → import (server-side batches) → reconcile.
The approved rows are held server-side; the client only sends row decisions. Imports never create logins, send
emails or activate paid products: every new customer organisation gets Pulse Fitness LITE only and stays
"pending activation" until an administrator invites named people separately.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from routes.pulse_master_admin import MASTER_ADMIN_EMAIL, PULSE_ROLE
from utils.auth import get_current_user
from utils.database import db
from utils import sage_sicon_import as S

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/customer-import", tags=["customer-import"])

LITE_MODULES = ["operations"]
BATCH = 200
_TASKS: set = set()
_PAID_TIERS_FREE = {"", "free", "lite", None}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_admin(user: dict) -> None:
    """Customer account data includes confidential Sage finance fields — Pulse admins only (not Service Desk)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin") or user.get("role") == PULSE_ROLE \
            or user.get("is_pulse_admin"):
        return
    raise HTTPException(403, "Pulse Fitness administrator access required")


_INDEXES_READY = False


async def _ensure_indexes():
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    await db.customer_account_refs.create_index([("system", 1), ("company", 1), ("ref", 1)], unique=True)
    await db.customer_account_refs.create_index("org_id")
    await db.customer_import_rows.create_index([("job_id", 1), ("row", 1)], unique=True)
    await db.customer_account_internal.create_index([("org_id", 1), ("account_ref", 1)], unique=True)
    await db.customer_contact_staging.create_index([("account_ref", 1), ("fingerprint", 1)], unique=True)
    await db.customer_proposed_sites.create_index([("org_id", 1), ("account_ref", 1)], unique=True)
    await db.crm2_contacts.create_index("linked_organization_id")
    await db.customer_import_undo.create_index("job_id")
    _INDEXES_READY = True


async def _operator_org() -> dict:
    op = await db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1, "name": 1})
    if not op:
        raise HTTPException(409, "The Pulse Fitness operator company is not configured — contacts cannot be linked to the internal CRM")
    return op


# ---------------------------------------------------------------- account-reference lookup
async def _orgs_for_ref(ref: str, company: str) -> list[str]:
    ids = {d["org_id"] async for d in db.customer_account_refs.find({"system": "sage", "company": company, "ref": ref}, {"org_id": 1})}
    q = {"$or": [{"customer_account_number": ref}, {"sage_customer_number": ref}, {"sicon_customer_number": ref},
                 {"sage_account_refs": ref}]}
    async for o in db.organizations.find(q, {"_id": 0, "id": 1, "sage_company": 1}):
        if (o.get("sage_company") or "") == company:
            ids.add(o["id"])
    async for s in db.sites.find({"$or": [{"invoice_customer_ref": ref}, {"sicon_customer_ref": ref}]}, {"_id": 0, "organization_id": 1}):
        if s.get("organization_id"):
            ids.add(s["organization_id"])
    return sorted(ids)


async def _ref_index(refs: set, company: str) -> dict:
    """Bulk version of _orgs_for_ref for previews: {ref: sorted org ids}."""
    out: dict[str, set] = {x: set() for x in refs}
    refs_l = list(refs)
    for i in range(0, len(refs_l), 5000):
        chunk = refs_l[i:i + 5000]
        async for d in db.customer_account_refs.find({"system": "sage", "company": company, "ref": {"$in": chunk}}, {"_id": 0}):
            out[d["ref"]].add(d["org_id"])
        q = {"$or": [{f: {"$in": chunk}} for f in ("customer_account_number", "sage_customer_number", "sicon_customer_number",
                                                     "sage_account_refs")]}
        async for o in db.organizations.find(q, {"_id": 0, "id": 1, "sage_company": 1, "customer_account_number": 1,
                                                  "sage_customer_number": 1, "sicon_customer_number": 1, "sage_account_refs": 1}):
            if (o.get("sage_company") or "") != company:
                continue
            for ref in {o.get("customer_account_number"), o.get("sage_customer_number"), o.get("sicon_customer_number"),
                        *(o.get("sage_account_refs") or [])} & set(chunk):
                out[ref].add(o["id"])
        async for st in db.sites.find({"$or": [{"invoice_customer_ref": {"$in": chunk}}, {"sicon_customer_ref": {"$in": chunk}}]},
                                      {"_id": 0, "organization_id": 1, "invoice_customer_ref": 1, "sicon_customer_ref": 1}):
            for ref in {st.get("invoice_customer_ref"), st.get("sicon_customer_ref")} & set(chunk):
                if st.get("organization_id"):
                    out[ref].add(st["organization_id"])
    return {k: sorted(v) for k, v in out.items()}


# ---------------------------------------------------------------- analyse (upload)
async def _file_bytes(user: dict, file: Optional[UploadFile], file_id: Optional[str]) -> tuple[bytes, str]:
    if file_id:
        fdoc = await db.files.find_one({"id": file_id, "organization_id": user.get("organization_id")}, {"_id": 0})
        if not fdoc:
            raise HTTPException(404, "Uploaded file not found")
        from utils.database import get_object
        data, _ = get_object(fdoc["storage_path"])
        return data, fdoc.get("original_filename") or "upload"
    if file is None:
        raise HTTPException(400, "Provide a file or file_id")
    return await file.read(), file.filename or "upload"


@router.post("/analyze")
async def analyze(file: UploadFile = File(None), file_id: Optional[str] = Form(None),
                  expected: Optional[str] = Form(None), worksheet: Optional[str] = Form(None),
                  header_row: Optional[int] = Form(None), source_company: str = Form(""),
                  user: dict = Depends(get_current_user)):
    _require_admin(user)
    await _ensure_indexes()
    raw, filename = await _file_bytes(user, file, file_id)
    try:
        ftype, sheets = S.read_sheets(raw, filename)
        det = S.detect(sheets, worksheet or None, (header_row - 1) if header_row else None)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if det["format"] == "unknown":
        raise HTTPException(422, "This file is not a recognised Sage Customer Accounts or Sicon Customer Contacts export "
                                 "(no AccountNumber/AccountName or CustomerCode/FirstName header found).")
    if expected and expected != det["format"]:
        label = {"sage_accounts": "Sage Customer Accounts", "sicon_contacts": "Sicon Customer Contacts"}
        raise HTTPException(422, f"This file looks like a {label[det['format']]} file, not {label.get(expected, expected)}.")
    await _operator_org()
    job_id = str(uuid.uuid4())
    build = S.build_sage_record if det["format"] == "sage_accounts" else S.build_sicon_record
    docs = []
    for r in det["records"]:
        rec = build(r["values"]) if r["role"] != "metadata" else None
        docs.append({"job_id": job_id, "row": r["row"], "role": r["role"], "record": rec,
                     "decision": {}, "commit_status": "pending"})
    if docs:
        await db.customer_import_rows.insert_many(docs)
    job = {"id": job_id, "kind": det["format"], "status": "analysed", "filename": filename, "file_type": ftype,
           "file_id": file_id, "checksum": S.checksum(raw), "size": len(raw), "source_company": source_company.strip().upper(),
           "detection": {k: v for k, v in det.items() if k != "records"},
           "created_by": user.get("email"), "created_at": _now()}
    prior = await db.customer_import_jobs.find_one({"checksum": job["checksum"], "kind": job["kind"], "status": {"$in": ["completed", "completed_with_errors"]}},
                                                   {"_id": 0, "id": 1, "finished_at": 1})
    job["previously_imported"] = prior
    job["status"] = "analysing"
    await db.customer_import_jobs.insert_one(dict(job))
    t = asyncio.create_task(_evaluate_bg(job_id, "analysed"))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return await _job_view(job_id)


async def _evaluate_bg(job_id: str, then: str) -> None:
    try:
        await _evaluate(job_id)
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": then}})
    except Exception as e:  # noqa: BLE001
        logger.exception("customer import evaluation %s failed", job_id)
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "analysis_failed", "error": str(e)[:300]}})


# ---------------------------------------------------------------- evaluation (preview)
def _included(r: dict) -> bool:
    d, rec = r.get("decision") or {}, r.get("record") or {}
    if r["role"] in ("metadata", "example") or not rec or rec.get("errors"):
        return False
    if "include" in d:
        return bool(d["include"])
    if r["role"] in ("uncertain", "suspected_example"):
        return False
    return not (rec.get("status") or {}).get("hidden")


_ORG_FILL = ("short_name", "currency", "website", "address_line1", "address_line2", "address_line3", "address_line4",
             "city", "county", "postcode")


def _org_changes(existing: dict, org: dict) -> tuple[dict, dict]:
    fills, conflicts = {}, {}
    for k in _ORG_FILL:
        new = (org.get(k) or "").strip()
        cur = (existing.get(k) or "").strip()
        if not new:
            continue  # blank source values never overwrite
        if not cur:
            fills[k] = new
        elif cur.lower() != new.lower():
            conflicts[k] = {"current": cur, "proposed": new}
    if (org.get("phone") or {}).get("display") and not existing.get("phone"):
        fills["phone"] = org["phone"]["display"]
    return fills, conflicts


async def _evaluate(job_id: str) -> None:
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
    rows = await db.customer_import_rows.find({"job_id": job_id}, {"_id": 0}).sort("row", 1).to_list(None)
    if job["kind"] == "sage_accounts":
        await _evaluate_sage(job, rows)
    else:
        await _evaluate_sicon(job, rows)


async def _evaluate_sage(job: dict, rows: list[dict]) -> None:
    company = job.get("source_company") or ""
    by_ref: dict[str, list[dict]] = {}
    for r in rows:
        if _included(r):
            by_ref.setdefault(r["record"]["account_ref"], []).append(r)
    all_refs = set(by_ref) | {rs[0]["record"]["head_office_ref"] for rs in by_ref.values() if rs[0]["record"]["head_office_ref"]}
    idx = await _ref_index(all_refs, company)
    names: dict[str, int] = {}
    async for o in db.organizations.find({}, {"_id": 0, "name": 1}):
        k = (o.get("name") or "").strip().lower()
        names[k] = names.get(k, 0) + 1
    ho_of = {ref: rs[0]["record"]["head_office_ref"] for ref, rs in by_ref.items()
             if rs[0]["record"]["office_type"] == "branch" and rs[0]["record"]["head_office_ref"]}
    outcomes = {}
    for r in rows:
        rec, d = r.get("record"), r.get("decision") or {}
        o = {"category": "", "warnings": list((rec or {}).get("warnings") or []), "org_id": None, "action": ""}
        if r["role"] == "metadata":
            o["category"] = "template_metadata"
        elif r["role"] == "example":
            o["category"] = "excluded_example"
        elif rec and rec.get("errors"):
            o.update(category="invalid", action="Correct the record in Sage and re-import this file")
        elif not _included(r):
            o["category"] = ("hidden_sage_account" if (rec["status"] or {}).get("hidden") and "include" not in d else
                             "excluded_suspected_example" if r["role"] == "suspected_example" and "include" not in d else
                             "uncertain_range" if r["role"] == "uncertain" and "include" not in d else "excluded_by_admin")
            if o["category"] == "uncertain_range":
                o["action"] = "Confirm whether this row is genuine customer data"
            if o["category"] == "excluded_suspected_example":
                o["action"] = "Matches a Sage sample record — include only if it is a genuine customer"
        else:
            ref = rec["account_ref"]
            dupes = by_ref[ref]
            if len(dupes) > 1 and dupes[0]["row"] != r["row"]:
                same = dupes[0]["record"]["fingerprint"] == rec["fingerprint"]
                o.update(category="duplicate_source_row" if same else "conflicting_duplicate",
                         action="" if same else f"Account {ref} appears more than once with different details — exclude one row")
                outcomes[r["row"]] = o
                continue
            if len(dupes) > 1 and any(x["record"]["fingerprint"] != rec["fingerprint"] for x in dupes):
                o.update(category="conflicting_duplicate", action=f"Account {ref} appears more than once with different details — exclude one row")
                outcomes[r["row"]] = o
                continue
            ids = idx.get(ref, [])
            if rec["status"]["on_hold"]:
                o["warnings"].append("Sage account is on hold — imported, but must not be invited without approval")
            if len(ids) > 1:
                o.update(category="ambiguous_organisation", action=f"Account {ref} is linked to {len(ids)} organisations — resolve before importing")
                outcomes[r["row"]] = o
                continue
            rel = _relationship(rec, ref, by_ref, ho_of, idx, d)
            o["relationship"] = rel
            if rel.get("blocking"):
                o.update(category=rel["blocking"], action=rel["message"])
                outcomes[r["row"]] = o
                continue
            if rel.get("message"):
                o["warnings"].append(rel["message"])
            if ids:
                ex = await db.organizations.find_one({"id": ids[0]}, {"_id": 0})
                fills, conflicts = _org_changes(ex, rec["org"])
                o.update(org_id=ids[0], org_name=ex.get("name"), fills=fills, conflicts=conflicts,
                         paid_preserved=ex.get("subscription_tier") not in _PAID_TIERS_FREE or
                         any(m != "operations" for m in (ex.get("enabled_modules") or [])))
                if ex.get("name", "").strip().lower() != rec["org"]["name"].strip().lower():
                    o["conflicts"]["name"] = {"current": ex.get("name"), "proposed": rec["org"]["name"]}
                o["category"] = "existing_update_proposed" if (fills or o["conflicts"]) else "existing_unchanged"
                if o["conflicts"]:
                    o["action"] = "Review changed values — tick 'apply changes' to overwrite"
            elif rel.get("mode") == "merge":
                o.update(category="branch_merged_into_head_office", org_id=rel.get("head_office_org_id"))
            else:
                o["category"] = "new_customer_organisation"
                name_twins = names.get(rec["org"]["name"].strip().lower(), 0)
                if name_twins:
                    o["warnings"].append(f"{name_twins} existing organisation(s) share this name but not this account number — not merged")
            o["contact"] = "new_or_matched" if rec.get("contact") else "no_contact_details"
            o["proposed_site"] = bool(rec["org"].get("address_line1") or rec["org"].get("postcode"))
        outcomes[r["row"]] = o
    await _save_outcomes(job["id"], outcomes)


def _re_escape(s: str) -> str:
    import re
    return re.escape(s or "")


def _relationship(rec, ref, by_ref, ho_of, idx, d) -> dict:
    if rec["office_type"] != "branch":
        return {"type": rec["office_type"]}
    ho = rec["head_office_ref"]
    if not ho:
        return {"type": "branch", "message": "Branch account has no head office reference — imported as a separate customer"}
    if ho == ref:
        return {"type": "branch", "blocking": "invalid_relationship", "message": "Account lists itself as its own head office"}
    seen, cur = {ref}, ho
    while cur in ho_of:
        if cur in seen:
            return {"type": "branch", "blocking": "circular_relationship",
                    "message": f"Circular head office chain via {cur} — correct in Sage or choose 'separate'"}
        seen.add(cur)
        cur = ho_of[cur]
    if cur in seen:
        return {"type": "branch", "blocking": "circular_relationship", "message": f"Circular head office chain via {cur}"}
    in_file = ho in by_ref
    ho_ids = idx.get(ho, [])
    if not in_file and not ho_ids:
        return {"type": "branch", "head_office_ref": ho, "mode": "separate",
                "message": f"Head office account {ho} is not in this file or the platform — imported as a separate customer for now"}
    if len(ho_ids) > 1:
        return {"type": "branch", "blocking": "ambiguous_organisation", "message": f"Head office {ho} matches several organisations"}
    mode = d.get("relationship") or "merge"
    own = idx.get(ref, [])
    if own and (not ho_ids or own[0] != ho_ids[0]):
        return {"type": "branch", "head_office_ref": ho, "mode": "separate",
                "message": f"Already a separate customer on the platform — head office link to {ho} recorded for review, not merged"}
    return {"type": "branch", "head_office_ref": ho, "mode": mode, "head_office_org_id": ho_ids[0] if ho_ids else None}


async def _save_outcomes(job_id: str, outcomes: dict) -> None:
    from pymongo import UpdateOne
    ops = [UpdateOne({"job_id": job_id, "row": row}, {"$set": {"outcome": o}}) for row, o in outcomes.items()]
    for i in range(0, len(ops), 1000):
        await db.customer_import_rows.bulk_write(ops[i:i + 1000], ordered=False)
    cats: dict[str, int] = {}
    for o in outcomes.values():
        cats[o["category"]] = cats.get(o["category"], 0) + 1
    await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"preview": cats, "evaluated_at": _now()}})


async def _org_contacts(org_id: str) -> list[dict]:
    return await db.crm2_contacts.find({"linked_organization_id": org_id, "gdpr_erased": {"$ne": True}},
                                       {"_id": 0, "id": 1, "identity": 1, "source_fingerprints": 1, "first_name": 1,
                                        "last_name": 1, "email": 1}).to_list(5000)


async def _evaluate_sicon(job: dict, rows: list[dict]) -> None:
    company = job.get("source_company") or ""
    outcomes, seen_fp, pending = {}, set(), {}
    idx = await _ref_index({r["record"]["account_ref"] for r in rows if r.get("record") and r["record"].get("account_ref")}, company)
    for r in rows:
        rec = r.get("record")
        o = {"category": "", "warnings": list((rec or {}).get("warnings") or []), "org_id": None, "action": ""}
        if r["role"] == "metadata":
            o["category"] = "template_metadata"
        elif r["role"] == "example":
            o["category"] = "excluded_example"
        elif rec.get("errors"):
            o.update(category="invalid", action="; ".join(rec["errors"]))
        elif not _included(r):
            o["category"] = "excluded_by_admin"
        elif rec["fingerprint"] in seen_fp:
            o["category"] = "duplicate_source_row"
        else:
            seen_fp.add(rec["fingerprint"])
            ids = idx.get(rec["account_ref"], [])
            if len(ids) > 1:
                o.update(category="ambiguous_organisation", action=f"Customer code {rec['account_ref']} matches several organisations")
            elif not ids:
                o.update(category="unresolved_contact", action="Staged until the matching Sage account is imported")
            else:
                pool = pending.setdefault(ids[0], await _org_contacts(ids[0]))
                verdict, hit = S.match_contact(rec["contact"], pool)
                o["org_id"] = ids[0]
                o["category"] = {"new": "new_business_contact", "same": "existing_contact_unchanged",
                                 "update": "existing_contact_update_proposed", "ambiguous": "ambiguous_contact"}[verdict]
                if hit:
                    o["matched_contact_id"] = hit.get("id")
                if verdict == "ambiguous":
                    o["action"] = "Possible match with an existing contact — choose 'create new' or exclude"
                if (r.get("decision") or {}).get("contact_mode") == "new" and verdict == "ambiguous":
                    o["category"] = "new_business_contact"
                    o["action"] = ""
                if verdict == "new" or o["category"] == "new_business_contact":
                    pool.append({"id": f"pending-{r['row']}", "identity": S.contact_identity(rec["contact"]),
                                 "source_fingerprints": [S.contact_fp(rec["contact"])]})
        outcomes[r["row"]] = o
    await _save_outcomes(job["id"], outcomes)


# ---------------------------------------------------------------- views
_BLOCKING = {"ambiguous_organisation", "conflicting_duplicate", "circular_relationship", "invalid_relationship",
             "ambiguous_contact"}
_WRITES = {"new_customer_organisation", "existing_update_proposed", "existing_unchanged", "branch_merged_into_head_office",
           "new_business_contact", "existing_contact_update_proposed", "existing_contact_unchanged", "unresolved_contact"}


async def _job_view(job_id: str) -> dict:
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Import not found")
    p = job.get("preview") or {}
    job["summary"] = {
        "new_lite_organisations": p.get("new_customer_organisation", 0),
        "existing_organisations": p.get("existing_update_proposed", 0) + p.get("existing_unchanged", 0),
        "existing_paid_preserved": await db.customer_import_rows.count_documents({"job_id": job_id, "outcome.paid_preserved": True}),
        "branches_merged": p.get("branch_merged_into_head_office", 0),
        "contacts_to_create": p.get("new_business_contact", 0) + (await db.customer_import_rows.count_documents(
            {"job_id": job_id, "outcome.contact": "new_or_matched"}) if job["kind"] == "sage_accounts" else 0),
        "contacts_to_update": p.get("existing_contact_update_proposed", 0),
        "unresolved": sum(p.get(k, 0) for k in _BLOCKING | {"unresolved_contact", "uncertain_range", "invalid"}),
        "blocking": sum(p.get(k, 0) for k in _BLOCKING) + (p.get("uncertain_range", 0)),
        "paid_subscriptions_to_activate": 0,
        "login_invitations_to_send": 0,
        "users_to_create": 0,
    }
    return job


@router.get("/jobs")
async def list_jobs(kind: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_admin(user)
    q = {"kind": kind} if kind else {}
    return {"jobs": await db.customer_import_jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    return await _job_view(job_id)


@router.get("/jobs/{job_id}/rows")
async def job_rows(job_id: str, category: Optional[str] = None, search: str = "", skip: int = 0,
                   limit: int = Query(100, le=500), user: dict = Depends(get_current_user)):
    _require_admin(user)
    q: dict = {"job_id": job_id}
    if category:
        q["outcome.category"] = category
    if search:
        rx = {"$regex": _re_escape(search), "$options": "i"}
        q["$or"] = [{"record.account_ref": rx}, {"record.org.name": rx}, {"record.contact.last_name": rx}]
    total = await db.customer_import_rows.count_documents(q)
    rows = await db.customer_import_rows.find(q, {"_id": 0, "record.internal": 0, "record.analysis": 0}).sort("row", 1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "rows": rows}


class Decision(BaseModel):
    row: int
    include: Optional[bool] = None
    relationship: Optional[Literal["merge", "separate"]] = None
    apply_changes: Optional[bool] = None
    contact_mode: Optional[Literal["new"]] = None


class DecisionsIn(BaseModel):
    decisions: list[Decision]


@router.post("/jobs/{job_id}/decisions")
async def set_decisions(job_id: str, body: DecisionsIn, user: dict = Depends(get_current_user)):
    _require_admin(user)
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0, "status": 1})
    if not job:
        raise HTTPException(404, "Import not found")
    if job["status"] not in ("analysed", "approved"):
        raise HTTPException(409, "This import is being checked or has already started — wait a moment and try again"
                            if job["status"] == "analysing" else "This import has already started — decisions can no longer change")
    for d in body.decisions:
        upd = {f"decision.{k}": v for k, v in d.model_dump(exclude={"row"}).items() if v is not None}
        if upd:
            await db.customer_import_rows.update_one({"job_id": job_id, "row": d.row}, {"$set": upd})
    # Any change after approval withdraws the approval — the admin must re-approve the new snapshot.
    await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "analysing"}, "$unset": {"approval": ""}})
    t = asyncio.create_task(_evaluate_bg(job_id, "analysed"))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return await _job_view(job_id)


async def _snapshot_hash(job_id: str) -> str:
    rows = await db.customer_import_rows.find({"job_id": job_id}, {"_id": 0, "row": 1, "record.fingerprint": 1, "decision": 1,
                                                                    "outcome.category": 1}).sort("row", 1).to_list(None)
    return S.fingerprint(rows)


@router.post("/jobs/{job_id}/approve")
async def approve(job_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    cur = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0, "status": 1})
    if not cur:
        raise HTTPException(404, "Import not found")
    if cur["status"] not in ("analysed", "approved"):
        raise HTTPException(409, f"Import is {cur['status']}")
    await _evaluate(job_id)  # revalidate against the live database before approval
    job = await _job_view(job_id)
    if job["status"] not in ("analysed", "approved"):
        raise HTTPException(409, f"Import is {job['status']}")
    if job["summary"]["blocking"]:
        raise HTTPException(409, f"{job['summary']['blocking']} record(s) need a decision before this import can be approved")
    approval = {"by": user.get("email"), "at": _now(), "snapshot": await _snapshot_hash(job_id)}
    await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "approved", "approval": approval}})
    return await _job_view(job_id)


@router.post("/jobs/{job_id}/commit")
async def commit(job_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Import not found")
    if job["status"] in ("committing",):
        return await _job_view(job_id)
    if job["status"] not in ("approved", "completed_with_errors", "interrupted"):
        raise HTTPException(409, "Approve the import first")
    if job["status"] == "approved" and (job.get("approval") or {}).get("snapshot") != await _snapshot_hash(job_id):
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "analysed"}, "$unset": {"approval": ""}})
        raise HTTPException(409, "The import changed after approval — review and approve it again")
    claimed = await db.customer_import_jobs.find_one_and_update(
        {"id": job_id, "status": job["status"]},
        {"$set": {"status": "committing", "started_at": _now(), "heartbeat_at": _now(), "committed_by": user.get("email")}})
    if not claimed:
        raise HTTPException(409, "This import is already running")
    t = asyncio.create_task(_run_commit(job_id, user))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return await _job_view(job_id)


# ---------------------------------------------------------------- commit workers
async def _run_commit(job_id: str, user: dict) -> None:
    try:
        job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
        op = await _operator_org()
        await _ensure_indexes()
        q = {"job_id": job_id, "commit_status": {"$ne": "done"}, "outcome.category": {"$in": list(_WRITES)}}
        rows = await db.customer_import_rows.find(q, {"_id": 0}).sort("row", 1).to_list(None)
        if job["kind"] == "sage_accounts":
            rows.sort(key=lambda r: r["outcome"]["category"] == "branch_merged_into_head_office")  # pass 2: branches
        done = 0
        for i in range(0, len(rows), BATCH):
            for r in rows[i:i + BATCH]:
                try:
                    res = await (_commit_sage_row if job["kind"] == "sage_accounts" else _commit_sicon_row)(job, r, op, user)
                    await db.customer_import_rows.update_one({"job_id": job_id, "row": r["row"]},
                                                             {"$set": {"commit_status": "done", "result": res, "committed_at": _now()}})
                except Exception as e:  # noqa: BLE001 — recorded per row; the batch continues
                    logger.exception("customer import row %s failed", r["row"])
                    await db.customer_import_rows.update_one({"job_id": job_id, "row": r["row"]},
                                                             {"$set": {"commit_status": "failed", "error": str(e)[:300]}})
                done += 1
            await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"progress": {"done": done, "total": len(rows)},
                                                                               "heartbeat_at": _now()}})
        failed = await db.customer_import_rows.count_documents({"job_id": job_id, "commit_status": "failed"})
        results = await _result_counts(job_id)
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {
            "status": "completed_with_errors" if failed else "completed", "finished_at": _now(), "results": results}})
        await db.onboarding_audit_events.insert_one({"id": str(uuid.uuid4()), "action": f"{job['kind']}_import_committed",
                                                     "detail": {"job_id": job_id, "results": results}, "actor_email": user.get("email"),
                                                     "at": _now()})
    except Exception as e:  # noqa: BLE001
        logger.exception("customer import %s failed", job_id)
        await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "interrupted", "error": str(e)[:300]}})


async def _result_counts(job_id: str) -> dict:
    out: dict[str, int] = {}
    async for r in db.customer_import_rows.find({"job_id": job_id, "commit_status": {"$in": ["done", "failed"]}},
                                                 {"_id": 0, "result": 1, "commit_status": 1}):
        if r["commit_status"] == "failed":
            out["failed"] = out.get("failed", 0) + 1
            continue
        for k, v in (r.get("result") or {}).items():
            if isinstance(v, bool) and v:
                out[k] = out.get(k, 0) + 1
            elif isinstance(v, str) and k.endswith("_outcome"):
                key = f"{k[:-8]}_{v}"
                out[key] = out.get(key, 0) + 1
    out["paid_subscriptions_activated"] = 0
    out["users_created"] = 0
    out["invitations_sent"] = 0
    return out


async def _claim_ref(ref: str, company: str, org_id: str, job_id: str) -> str:
    """Bind an account reference to one organisation (unique). Returns the org that owns it."""
    try:
        await db.customer_account_refs.insert_one({"system": "sage", "company": company, "ref": ref, "org_id": org_id,
                                                   "job_id": job_id, "created_at": _now()})
        return org_id
    except DuplicateKeyError:
        d = await db.customer_account_refs.find_one({"system": "sage", "company": company, "ref": ref}, {"_id": 0, "org_id": 1})
        return d["org_id"]


async def _log(job_id: str, org_id: str, coll: str, key: dict, *, delete=False, before: Optional[dict] = None,
               pull: Optional[dict] = None) -> None:
    """Undo log: every change an import makes is recorded so the import can be rolled back exactly."""
    await db.customer_import_undo.insert_one({"job_id": job_id, "org_id": org_id, "coll": coll, "key": key, "delete": delete,
                                              "before": before, "pull": pull, "at": datetime.now(timezone.utc)})


async def _add_ref(job_id: str, org_id: str, coll: str, key: dict, field: str, ref: str) -> None:
    if not await db[coll].find_one({**key, field: ref}, {"_id": 1}):
        await db[coll].update_one(key, {"$addToSet": {field: ref}})
        await _log(job_id, org_id, coll, key, pull={field: ref})


async def _before(coll: str, key: dict, fields) -> Optional[dict]:
    cur = await db[coll].find_one(key, {"_id": 0})
    if cur is None:
        return None
    return {f: cur.get(f) for f in fields}


def _lite_org_doc(org_id: str, rec: dict, job: dict) -> dict:
    o = rec["org"]
    return {
        "id": org_id, "name": o["name"], "short_name": o["short_name"],
        "portal_type": "operations",
        "enabled_modules": list(LITE_MODULES),
        "modules": {"operations": {"enabled": True, "tier": "lite", "source": "sage_import"}},
        "subscription_tier": "free", "account_type": "lite",
        "status": "active",  # organisation record is live internally; nobody can sign in until invited
        "onboarding_status": "pending_activation", "portal_access": "not_activated",
        "provisioning_state": "importing",
        "company_code": str(uuid.uuid4())[:8].upper(),
        "customer_account_number": rec["account_ref"], "sage_customer_number": rec["account_ref"],
        "sage_account_refs": [rec["account_ref"]], "sage_company": job.get("source_company") or "",
        "currency": o["currency"], "sage_country_code": o["sage_country_code"],
        "website": o["website"], "phone": (o["phone"] or {}).get("display") or "",
        "phone_parts": o["phone"] or {}, "fax_parts": o["fax"] or {},
        "address_line1": o["address_line1"], "address_line2": o["address_line2"], "address_line3": o["address_line3"],
        "address_line4": o["address_line4"], "city": o["city"], "county": o["county"], "postcode": o["postcode"],
        "country": o["address_country_code"], "address_country_code": o["address_country_code"],
        "address": ", ".join(x for x in (o["address_line1"], o["address_line2"], o["address_line3"], o["address_line4"],
                                         o["city"], o["county"], o["postcode"]) if x),
        "sage_office_type": rec["office_type"], "sage_head_office_ref": rec["head_office_ref"],
        "features": {}, "notes": "",
        "created_via": "sage_customer_import", "created_via_job_id": job["id"], "created_at": _now(),
    }


async def _commit_sage_row(job: dict, r: dict, op: dict, user: dict) -> dict:
    rec, out, d = r["record"], r["outcome"], r.get("decision") or {}
    company, ref = job.get("source_company") or "", rec["account_ref"]
    res: dict = {}
    rel = out.get("relationship") or {}
    if out["category"] == "branch_merged_into_head_office":
        ho_ids = await _orgs_for_ref(rel["head_office_ref"], company)
        if len(ho_ids) != 1:
            raise ValueError(f"Head office {rel['head_office_ref']} could not be resolved at import time")
        org_id = await _claim_ref(ref, company, ho_ids[0], job["id"])
        if org_id != ho_ids[0]:
            raise ValueError(f"Account {ref} was linked to a different organisation by another import")
        for f in ("sage_account_refs", "sage_branch_refs"):
            await _add_ref(job["id"], org_id, "organizations", {"id": org_id}, f, ref)
        res["org_outcome"] = "branch_merged"
    else:
        ids = await _orgs_for_ref(ref, company)  # revalidate at commit time
        if len(ids) > 1:
            raise ValueError(f"Account {ref} now matches several organisations — held")
        if ids:
            org_id = await _claim_ref(ref, company, ids[0], job["id"])
            ex = await db.organizations.find_one({"id": org_id}, {"_id": 0})
            fills, conflicts = _org_changes(ex, rec["org"])
            upd = dict(fills)
            if d.get("apply_changes"):
                upd.update({k: v["proposed"] for k, v in conflicts.items()})
                if (out.get("conflicts") or {}).get("name"):
                    upd["name"] = rec["org"]["name"]
            if upd:
                await db.customer_import_preimages.insert_one({"job_id": job["id"], "org_id": org_id, "row": r["row"],
                                                               "before": {k: ex.get(k) for k in upd}, "at": _now()})
                await db.organizations.update_one({"id": org_id}, {"$set": upd})
            await _add_ref(job["id"], org_id, "organizations", {"id": org_id}, "sage_account_refs", ref)
            res["org_outcome"] = "updated" if upd else "unchanged"
        else:
            new_id = str(uuid.uuid4())
            org_id = await _claim_ref(ref, company, new_id, job["id"])
            if org_id == new_id:
                await db.organizations.insert_one(_lite_org_doc(new_id, rec, job))
                res["org_outcome"] = "created_lite"
            else:
                res["org_outcome"] = "unchanged"  # another run created it first — idempotent
            if rel.get("head_office_ref"):
                await db.organizations.update_one({"id": org_id}, {"$set": {"sage_head_office_ref": rel["head_office_ref"],
                                                                            "head_office_link_status": "proposed"}})
    res["org_id"] = org_id
    ikey = {"org_id": org_id, "account_ref": ref}
    prev = await db.customer_account_internal.find_one(ikey, {"_id": 0})
    await _log(job["id"], org_id, "customer_account_internal", ikey, delete=prev is None,
               before=None if prev is None else {k: prev.get(k) for k in ("fields", "analysis", "sage_status", "office_type",
                                                                           "head_office_ref", "sage_company", "source_job_id")})
    await db.customer_account_internal.update_one(
        ikey,
        {"$set": {"fields": rec["internal"], "analysis": rec["analysis"], "sage_status": rec["status"],
                  "office_type": rec["office_type"], "head_office_ref": rec["head_office_ref"], "sage_company": company,
                  "source_job_id": job["id"], "updated_at": _now()}}, upsert=True)
    company_id = await _crm_company(op, org_id, ref, user, job)
    if rec.get("contact"):
        res["contact_outcome"] = await _upsert_contact(op, org_id, company_id, ref, rec["contact"], "sage", job, user)
    if out.get("proposed_site"):
        o = rec["org"]
        if not await db.customer_proposed_sites.find_one({"org_id": org_id, "account_ref": ref}, {"_id": 1}):
            await _log(job["id"], org_id, "customer_proposed_sites", {"org_id": org_id, "account_ref": ref}, delete=True)
        await db.customer_proposed_sites.update_one(
            {"org_id": org_id, "account_ref": ref},
            {"$setOnInsert": {"id": str(uuid.uuid4()), "status": "proposed", "created_at": _now(), "source_job_id": job["id"],
                              "name": o["name"], **{k: o[k] for k in ("address_line1", "address_line2", "address_line3",
                                                                       "address_line4", "city", "county", "postcode")},
                              "country": o["address_country_code"],
                              "note": "Sage account address — not verified as a gym location"}}, upsert=True)
        res["proposed_site"] = True
    await db.organizations.update_one({"id": org_id, "provisioning_state": "importing"}, {"$set": {"provisioning_state": "complete"}})
    res["staged_contacts_linked"] = await _reconcile_staged(op, org_id, company_id, ref, job, user)
    return res


async def _crm_company(op: dict, org_id: str, ref: str, user: dict, job: dict) -> str:
    """Internal Pulse CRM company for this customer — matched by link or account number, never by name."""
    c = await db.crm2_companies.find_one({"organization_id": op["id"], "linked_organization_id": org_id}, {"_id": 0, "id": 1})
    if not c:
        c = await db.crm2_companies.find_one({"organization_id": op["id"], "account_number": ref,
                                              "linked_organization_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1})
        if c:
            await _log(job["id"], org_id, "crm2_companies", {"id": c["id"]}, before={"linked_organization_id": None, "linked_at": None})
            await db.crm2_companies.update_one({"id": c["id"]}, {"$set": {"linked_organization_id": org_id, "linked_at": _now()}})
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if c:
        await _add_ref(job["id"], org_id, "crm2_companies", {"id": c["id"]}, "sage_account_refs", ref)
        return c["id"]
    cid = str(uuid.uuid4())
    await db.crm2_companies.insert_one({
        "id": cid, "organization_id": op["id"], "site_id": "", "name": org.get("name"), "status": "active", "type": "customer",
        "linked_organization_id": org_id, "linked_at": _now(), "account_number": ref, "sage_account_refs": [ref],
        "website": org.get("website", ""), "phone": org.get("phone", ""), "email": "",
        "address": org.get("address", ""), "address_line1": org.get("address_line1", ""), "city": org.get("city", ""),
        "postcode": org.get("postcode", ""), "sector": "", "company_number": "",
        "account_owner_id": user.get("id"), "account_owner_name": user.get("full_name", ""), "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""), "tags": ["sage-import"], "directors": [], "notes": "",
        "imported_via": "sage_customer_import", "created_via_job_id": job["id"], "created_at": _now(), "updated_at": _now()})
    await _log(job["id"], org_id, "crm2_companies", {"id": cid}, delete=True)
    return cid


async def _upsert_contact(op: dict, org_id: str, company_id: str, ref: str, c: dict, source: str, job: dict, user: dict,
                          force_new: bool = False) -> str:
    from routes.master_admin_bulk_import import _crm2_contact_doc
    pool = await _org_contacts(org_id)
    verdict, hit = ("new", None) if force_new else S.match_contact(c, pool)
    fp, ident = S.contact_fp(c), S.contact_identity(c)
    if verdict == "ambiguous":
        raise ValueError("Contact matches an existing contact ambiguously — held for review")
    if verdict == "same":
        return "unchanged"
    phone = (c.get("telephone") or {}).get("display") or (c.get("telephone") or {}).get("number", "")
    mobile = (c.get("mobile") or {}).get("display") or (c.get("mobile") or {}).get("number", "")
    if verdict == "update":
        cur = await db.crm2_contacts.find_one({"id": hit["id"]}, {"_id": 0})
        fills = {k: v for k, v in {"first_name": c.get("first_name"), "last_name": c.get("last_name"), "email": c.get("email"),
                                   "phone": phone, "mobile": mobile, "salutation": c.get("salutation"),
                                   "middle_name": c.get("middle_name"), "website": c.get("website"),
                                   "job_title": c.get("role") if source == "sicon" else None}.items() if v and not cur.get(k)}
        for k in ("telephone", "mobile", "fax"):
            if c.get(k) and not (cur.get("phones") or {}).get(k):
                fills[f"phones.{k}"] = c[k]
        if source == "sicon":
            fills["sicon_preferences"] = c.get("preferences") or {}
            fills["sicon_default_contact"] = bool(c.get("is_default"))
        fills["identity"] = {**(cur.get("identity") or {}), **{k: v for k, v in ident.items() if v}}
        fills["updated_at"] = _now()
        key = {"id": hit["id"]}
        await _log(job["id"], org_id, "crm2_contacts", key, before=await _before("crm2_contacts", key, fills.keys()))
        await db.crm2_contacts.update_one(key, {"$set": fills})
        for f, v in (("source_fingerprints", fp), ("sources", source), ("customer_account_refs", ref), ("import_job_ids", job["id"])):
            await _add_ref(job["id"], org_id, "crm2_contacts", key, f, v)
        return "updated"
    doc = _crm2_contact_doc(op["id"], company_id, None, {"first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""),
                                                         "email": c.get("email", ""), "phone": phone,
                                                         "title": c.get("role", "")}, user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    doc.update({"company_name": org.get("name"), "mobile": mobile, "salutation": c.get("salutation", ""),
                "middle_name": c.get("middle_name", ""), "website": c.get("website", ""),
                "phones": {k: c[k] for k in ("telephone", "mobile", "fax") if c.get(k)},
                "linked_organization_id": org_id, "customer_account_refs": [ref], "identity": ident,
                "source_fingerprints": [fp], "sources": [source], "import_job_ids": [job["id"]],
                "source": f"{source}_customer_import", "tags": ["imported", f"{source}-import"],
                "country": "", "is_business_contact": True, "portal_user_id": None,
                # Import never implies consent: marketing permission must be obtained separately.
                "marketing_permission": "not_obtained", "gdpr_consent": False,
                "sicon_preferences": c.get("preferences") or {}, "sicon_default_contact": bool(c.get("is_default"))})
    doc["created_via_job_id"] = job["id"]
    await db.crm2_contacts.insert_one(doc)
    await _log(job["id"], org_id, "crm2_contacts", {"id": doc["id"]}, delete=True)
    return "created"


async def _reconcile_staged(op: dict, org_id: str, company_id: str, ref: str, job: dict, user: dict) -> int:
    n = 0
    async for s in db.customer_contact_staging.find({"account_ref": ref, "status": "awaiting_account"}, {"_id": 0}):
        try:
            out = await _upsert_contact(op, org_id, company_id, ref, s["contact"], "sicon", job, user)
            await _log(job["id"], org_id, "customer_contact_staging", {"account_ref": ref, "fingerprint": s["fingerprint"]},
                       before={"status": "awaiting_account", "org_id": None, "linked_at": None, "contact_outcome": None})
            await db.customer_contact_staging.update_one({"account_ref": ref, "fingerprint": s["fingerprint"]},
                                                         {"$set": {"status": "linked", "org_id": org_id, "linked_at": _now(),
                                                                   "contact_outcome": out}})
            n += 1
        except ValueError as e:
            await db.customer_contact_staging.update_one({"account_ref": ref, "fingerprint": s["fingerprint"]},
                                                         {"$set": {"status": "needs_review", "org_id": org_id, "note": str(e)}})
    return n


async def _commit_sicon_row(job: dict, r: dict, op: dict, user: dict) -> dict:
    rec, out = r["record"], r["outcome"]
    ref = rec["account_ref"]
    ids = await _orgs_for_ref(ref, job.get("source_company") or "")
    if len(ids) > 1:
        raise ValueError(f"Customer code {ref} now matches several organisations — held")
    if not ids:
        skey = {"account_ref": ref, "fingerprint": rec["fingerprint"]}
        if not await db.customer_contact_staging.find_one(skey, {"_id": 1}):
            await _log(job["id"], "", "customer_contact_staging", skey, delete=True)
        await db.customer_contact_staging.update_one(
            {"account_ref": ref, "fingerprint": rec["fingerprint"]},
            {"$setOnInsert": {"contact": rec["contact"], "status": "awaiting_account", "source_job_id": job["id"],
                              "source_row": r["row"], "created_at": _now()}}, upsert=True)
        return {"contact_outcome": "staged"}
    company_id = await _crm_company(op, ids[0], ref, user, job)
    force = (r.get("decision") or {}).get("contact_mode") == "new"
    return {"org_id": ids[0], "contact_outcome": await _upsert_contact(op, ids[0], company_id, ref, rec["contact"], "sicon", job,
                                                                     user, force_new=force and out["category"] == "new_business_contact")}


# ---------------------------------------------------------------- reconciliation report / recovery
@router.get("/jobs/{job_id}/report.csv")
async def report(job_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Import not found")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Source file", "Worksheet", "Row", "Row type", "Account reference", "Customer / contact name",
                "Matched organisation id", "Import outcome", "Contact outcome", "Relationship", "Subscription outcome",
                "Onboarding status", "Commit status", "Warnings", "Errors", "Administrator action"])
    async for r in db.customer_import_rows.find({"job_id": job_id}, {"_id": 0, "record.internal": 0}).sort("row", 1):
        rec, o, res = r.get("record") or {}, r.get("outcome") or {}, r.get("result") or {}
        c = rec.get("contact") or {}
        name = (rec.get("org") or {}).get("name") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x)
        rel = o.get("relationship") or {}
        sub = ("LITE (new)" if res.get("org_outcome") == "created_lite" else
               "Existing plan preserved" if res.get("org_outcome") in ("updated", "unchanged", "branch_merged") else "")
        w.writerow([job["filename"], job["detection"].get("worksheet"), r["row"], r["role"], rec.get("account_ref", ""), name,
                    res.get("org_id") or o.get("org_id") or "", res.get("org_outcome") or o.get("category", ""),
                    res.get("contact_outcome") or o.get("contact", ""),
                    f"{rel.get('type', '')} {rel.get('head_office_ref', '')} {rel.get('mode', '')}".strip(), sub,
                    "pending_activation" if res.get("org_outcome") == "created_lite" else "",
                    r.get("commit_status"), " | ".join(o.get("warnings") or []),
                    " | ".join((rec.get("errors") or []) + ([r["error"]] if r.get("error") else [])), o.get("action", "")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="import-reconciliation-{job_id[:8]}.csv"'})


@router.post("/jobs/{job_id}/rollback")
async def rollback(job_id: str, user: dict = Depends(get_current_user)):
    """Undo an import exactly, using its undo log. Organisations it created are removed only while nobody has
    been given access and no paid product is active; such organisations (and their records) are kept."""
    _require_admin(user)
    job = await db.customer_import_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job or job["status"] not in ("completed", "completed_with_errors", "interrupted"):
        raise HTTPException(409, "Only finished imports can be rolled back")
    kept: set = set()
    removable = []
    async for o in db.organizations.find({"created_via_job_id": job_id}, {"_id": 0, "id": 1, "subscription_tier": 1, "enabled_modules": 1}):
        users = await db.users.count_documents({"organization_id": o["id"]}) + await db.crm_users.count_documents({"organization_id": o["id"]})
        if users or o.get("subscription_tier") not in _PAID_TIERS_FREE or (o.get("enabled_modules") or []) != LITE_MODULES:
            kept.add(o["id"])
        else:
            removable.append(o["id"])
    reverted = 0
    entries = await db.customer_import_undo.find({"job_id": job_id}).sort("_id", -1).to_list(None)
    for e in entries:
        if e.get("org_id") in kept:
            continue
        coll, key = db[e["coll"]], e["key"]
        if e.get("delete"):
            doc = await coll.find_one(key, {"_id": 0})
            if doc:
                await db.customer_import_rollback_archive.insert_one({"job_id": job_id, "coll": e["coll"], "doc": doc, "at": _now()})
                await coll.delete_one(key)
        elif e.get("pull"):
            await coll.update_one(key, {"$pull": e["pull"]})
        elif e.get("before") is not None:
            sets = {k: v for k, v in e["before"].items() if v is not None}
            unsets = {k: "" for k, v in e["before"].items() if v is None}
            await coll.update_one(key, {k: v for k, v in (("$set", sets), ("$unset", unsets)) if v})
        reverted += 1
    async for p in db.customer_import_preimages.find({"job_id": job_id}, {"_id": 0}).sort("at", -1):
        if p["org_id"] not in kept:
            await db.organizations.update_one({"id": p["org_id"]}, {"$set": p["before"]})
    await db.customer_account_refs.delete_many({"job_id": job_id, "org_id": {"$nin": list(kept)}})
    for oid in removable:
        full = await db.organizations.find_one({"id": oid}, {"_id": 0})
        await db.customer_import_rollback_archive.insert_one({"job_id": job_id, "coll": "organizations", "doc": full, "at": _now()})
        async for st in db.sites.find({"organization_id": oid, "created_via": "sage_proposed_site"}, {"_id": 0}):
            await db.customer_import_rollback_archive.insert_one({"job_id": job_id, "coll": "sites", "doc": st, "at": _now()})
        await db.sites.delete_many({"organization_id": oid, "created_via": "sage_proposed_site"})
        await db.organizations.delete_one({"id": oid})
    await db.customer_import_jobs.update_one({"id": job_id}, {"$set": {"status": "rolled_back", "rolled_back_at": _now(),
                                                                       "rolled_back_by": user.get("email"),
                                                                       "rollback": {"removed": len(removable), "kept": len(kept),
                                                                                    "changes_reverted": reverted}}})
    return {"removed": len(removable), "kept_in_use": len(kept), "restored": reverted}


@router.get("/staged-contacts")
async def staged_contacts(user: dict = Depends(get_current_user)):
    _require_admin(user)
    groups: dict[str, list] = {}
    async for s in db.customer_contact_staging.find({"status": {"$in": ["awaiting_account", "needs_review"]}}, {"_id": 0}).limit(5000):
        groups.setdefault(s["account_ref"], []).append(s)
    return {"groups": [{"account_ref": k, "contacts": v} for k, v in sorted(groups.items())]}


@router.get("/proposed-sites")
async def proposed_sites(user: dict = Depends(get_current_user)):
    _require_admin(user)
    return {"sites": await db.customer_proposed_sites.find({"status": "proposed"}, {"_id": 0}).to_list(2000)}


@router.post("/proposed-sites/{site_id}/{decision}")
async def decide_site(site_id: str, decision: Literal["confirm", "reject"], user: dict = Depends(get_current_user)):
    """Confirm turns the Sage address into a real customer site (no gym-floor access is created)."""
    _require_admin(user)
    p = await db.customer_proposed_sites.find_one({"id": site_id, "status": "proposed"}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Proposed site not found")
    if decision == "reject":
        await db.customer_proposed_sites.update_one({"id": site_id}, {"$set": {"status": "rejected", "decided_by": user.get("email")}})
        return {"status": "rejected"}
    sid = str(uuid.uuid4())
    await db.sites.insert_one({"id": sid, "organization_id": p["org_id"], "name": p["name"],
                               **{k: p.get(k, "") for k in ("address_line1", "address_line2", "address_line3", "city", "county",
                                                            "postcode", "country")},
                               "invoice_customer_ref": p["account_ref"], "status": "active", "created_via": "sage_proposed_site",
                               "created_at": _now()})
    await db.customer_proposed_sites.update_one({"id": site_id}, {"$set": {"status": "confirmed", "site_id": sid,
                                                                          "decided_by": user.get("email")}})
    return {"status": "confirmed", "site_id": sid}


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    _require_admin(user)
    sage_q = {"sage_account_refs.0": {"$exists": True}}
    return {
        "customer_organisations": await db.organizations.count_documents(sage_q),
        "sage_account_references": await db.customer_account_refs.count_documents({}),
        "awaiting_activation": await db.organizations.count_documents({**sage_q, "onboarding_status": "pending_activation"}),
        "lite_only": await db.organizations.count_documents({**sage_q, "subscription_tier": {"$in": ["free", "lite"]}}),
        "imported_contacts": await db.crm2_contacts.count_documents({"is_business_contact": True}),
        "unmatched_contacts": await db.customer_contact_staging.count_documents({"status": {"$in": ["awaiting_account", "needs_review"]}}),
        "hidden_sage_accounts": await db.customer_account_internal.count_documents({"sage_status.hidden": True}),
        "accounts_on_hold": await db.customer_account_internal.count_documents({"sage_status.on_hold": True}),
        "proposed_sites": await db.customer_proposed_sites.count_documents({"status": "proposed"}),
    }


@router.post("/security/initial-passwords")
async def purge_initial_passwords(apply: bool = False, user: dict = Depends(get_current_user)):
    """Remove stored plaintext first-login passwords. Users' real (hashed) passwords are unaffected;
    hand-over uses the secure set-password link instead."""
    _require_admin(user)
    q = {"primary_contact_initial_password": {"$exists": True}}
    n = await db.organizations.count_documents(q)
    if apply and n:
        await db.organizations.update_many(q, {"$unset": {"primary_contact_initial_password": ""},
                                               "$set": {"initial_password_purged_at": _now()}})
        await db.onboarding_audit_events.insert_one({"id": str(uuid.uuid4()), "action": "initial_passwords_purged",
                                                     "detail": {"count": n}, "actor_email": user.get("email"), "at": _now()})
    return {"organisations_with_stored_password": n, "purged": n if apply else 0}
