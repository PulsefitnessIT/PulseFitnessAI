"""
Migration Import Wizard — Iter 255.

Bulk customer/site + historical-case import for service suppliers
migrating onto the platform (spreadsheets / legacy systems). Org-scoped,
available to any Service Desk user (self-serve providers AND the
Pulse/platform desk).

Flow (all under /api/svc/imports):
    POST /parse           — upload CSV/XLSX (≤10,000 rows, ≤10MB), returns
                            import_id + headers + rule-based suggested
                            column mapping + sample rows
    POST /{id}/ai-map     — AI fallback: Claude recommends mappings for
                            headers the rules couldn't match
    POST /{id}/validate   — apply a mapping, return error/duplicate
                            counts + a preview of normalised records
    POST /{id}/commit     — perform the import (duplicate strategy:
                            skip | update), audit-logged
    GET  /{id}/errors.csv — download errored rows (with reason) to fix
                            and re-upload

Import types:
- customers: rows → `svc_engineer_customers` (reuses the Engineer Lite
  CRM schema via CustomerIn/_to_doc so the two surfaces stay in sync).
  Duplicates matched by email, else name+postcode.
- cases: rows → `svc_cases` as CLOSED historical records with their
  original dates (they never pollute open boards; SLA fields are left
  unset so analytics stays honest). Duplicates matched by reference.
  Engineer names are best-effort matched to `svc_engineers` so imported
  history feeds the utilisation analytics.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db
from utils.service_desk_auth import require_service_desk, log_desk_action
from utils.spreadsheet_import import iter_rows, parse_date_cell

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/svc/imports", tags=["Service Ops · Import Wizard"])

MAX_ROWS = 10_000
MAX_BYTES = 10 * 1024 * 1024  # 10MB


def _of(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────
# Target fields + rule-based header matching
# ─────────────────────────────────────────────────────────────────

CUSTOMER_FIELDS = {
    "name":           {"label": "Customer name", "required": True},
    "email":          {"label": "Email"},
    "phone":          {"label": "Phone"},
    "site_name":      {"label": "Site name"},
    "address_line1":  {"label": "Address line 1"},
    "address_line2":  {"label": "Address line 2"},
    "city":           {"label": "City / town"},
    "county":         {"label": "County"},
    "postcode":       {"label": "Postcode"},
    "country":        {"label": "Country"},
    "company_number": {"label": "Company number"},
    "notes":          {"label": "Notes"},
}

CASE_FIELDS = {
    "reference":      {"label": "Case reference"},
    "title":          {"label": "Title / summary", "required": True},
    "description":    {"label": "Description"},
    "priority":       {"label": "Priority"},
    "customer_name":  {"label": "Customer name"},
    "customer_email": {"label": "Customer email"},
    "site_name":      {"label": "Site name"},
    "site_postcode":  {"label": "Site postcode"},
    "created_at":     {"label": "Opened date", "required": True},
    "closed_at":      {"label": "Closed date"},
    "engineer_name":  {"label": "Engineer"},
    "fault_category": {"label": "Fault category"},
}

# Normalised header → target field. Header normalisation strips
# everything but [a-z0-9] so "Customer E-mail", "customer_email" and
# "CustomerEmail" all hit the same key.
_SYNONYMS = {
    "customers": {
        "name": "name", "customername": "name", "customer": "name", "client": "name",
        "clientname": "name", "company": "name", "companyname": "name", "account": "name",
        "accountname": "name", "business": "name", "businessname": "name",
        "email": "email", "emailaddress": "email", "customeremail": "email",
        "contactemail": "email", "mail": "email",
        "phone": "phone", "phonenumber": "phone", "telephone": "phone", "tel": "phone",
        "mobile": "phone", "contactnumber": "phone", "contactphone": "phone",
        "sitename": "site_name", "site": "site_name", "location": "site_name",
        "locationname": "site_name", "branch": "site_name", "gym": "site_name",
        "address": "address_line1", "addressline1": "address_line1", "address1": "address_line1",
        "street": "address_line1", "streetaddress": "address_line1", "siteaddress": "address_line1",
        "addressline2": "address_line2", "address2": "address_line2",
        "city": "city", "town": "city", "towncity": "city",
        "county": "county", "state": "county", "region": "county",
        "postcode": "postcode", "postalcode": "postcode", "zip": "postcode", "zipcode": "postcode",
        "country": "country",
        "companynumber": "company_number", "companyno": "company_number",
        "companyregistrationnumber": "company_number",
        "notes": "notes", "note": "notes", "comments": "notes", "comment": "notes",
    },
    "cases": {
        "reference": "reference", "ref": "reference", "casereference": "reference",
        "caseref": "reference", "caseno": "reference", "casenumber": "reference",
        "jobno": "reference", "jobnumber": "reference", "jobref": "reference",
        "ticket": "reference", "ticketno": "reference", "ticketnumber": "reference",
        "title": "title", "summary": "title", "subject": "title", "issue": "title",
        "fault": "title", "jobtitle": "title", "casetitle": "title",
        "description": "description", "details": "description", "notes": "description",
        "faultdescription": "description", "workdone": "description",
        "priority": "priority", "severity": "priority", "urgency": "priority",
        "customername": "customer_name", "customer": "customer_name", "client": "customer_name",
        "clientname": "customer_name", "company": "customer_name", "account": "customer_name",
        "customeremail": "customer_email", "email": "customer_email", "clientemail": "customer_email",
        "sitename": "site_name", "site": "site_name", "location": "site_name", "branch": "site_name",
        "sitepostcode": "site_postcode", "postcode": "site_postcode", "zip": "site_postcode",
        "createdat": "created_at", "created": "created_at", "opened": "created_at",
        "openedat": "created_at", "openeddate": "created_at", "dateopened": "created_at",
        "raiseddate": "created_at", "raised": "created_at", "loggeddate": "created_at",
        "logged": "created_at", "date": "created_at", "startdate": "created_at",
        "closedat": "closed_at", "closed": "closed_at", "closeddate": "closed_at",
        "dateclosed": "closed_at", "completed": "closed_at", "completeddate": "closed_at",
        "resolved": "closed_at", "resolveddate": "closed_at", "enddate": "closed_at",
        "engineername": "engineer_name", "engineer": "engineer_name", "technician": "engineer_name",
        "assignedto": "engineer_name", "assignedengineer": "engineer_name",
        "faultcategory": "fault_category", "category": "fault_category", "type": "fault_category",
        "casetype": "fault_category", "jobtype": "fault_category",
    },
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _fields_for(import_type: str) -> dict:
    if import_type == "customers":
        return CUSTOMER_FIELDS
    if import_type == "cases":
        return CASE_FIELDS
    raise HTTPException(400, "import_type must be 'customers' or 'cases'")


def _auto_map(headers: list[str], import_type: str) -> dict[str, str | None]:
    syn = _SYNONYMS[import_type]
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for h in headers:
        field = syn.get(_norm_header(h))
        if field and field not in used:
            mapping[h] = field
            used.add(field)
        else:
            mapping[h] = None
    return mapping


def _norm_priority(v: str | None) -> str:
    s = (v or "").strip().lower()
    if s in ("p1", "p2", "p3", "p4"):
        return s
    if s in ("1", "critical", "urgent", "emergency"):
        return "p1"
    if s in ("2", "high"):
        return "p2"
    if s in ("4", "low", "minor"):
        return "p4"
    return "p3"


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ─────────────────────────────────────────────────────────────────
# 1) Parse upload
# ─────────────────────────────────────────────────────────────────

@router.post("/parse")
async def parse_upload(
    file: UploadFile = File(...),
    import_type: str = Form(...),
    user: dict = Depends(require_service_desk),
) -> dict:
    org_id = _of(user)
    _fields_for(import_type)
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Only .csv and .xlsx files are supported")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(400, "File too large (max 10MB)")

    try:
        rows = list(iter_rows(content, filename))
    except Exception as e:
        logger.warning("[imports] parse failed for %s: %s", filename, e)
        raise HTTPException(400, "Could not read the file — is it a valid CSV or Excel sheet?")
    if not rows:
        raise HTTPException(400, "The file has no data rows")
    if len(rows) > MAX_ROWS:
        raise HTTPException(400, f"Too many rows ({len(rows):,}) — max {MAX_ROWS:,} per file")

    headers = list(rows[0].keys())
    mapping = _auto_map(headers, import_type)
    job_id = str(uuid.uuid4())
    await db.svc_import_jobs.insert_one({
        "id": job_id,
        "organization_id": org_id,
        "import_type": import_type,
        "filename": filename,
        "headers": headers,
        "rows": [{k: ("" if v is None else str(v)) for k, v in r.items()} for r in rows],
        "mapping": mapping,
        "status": "parsed",
        "created_by": user.get("id"),
        "created_at": _now(),
    })
    return {
        "import_id": job_id,
        "row_count": len(rows),
        "headers": headers,
        "suggested_mapping": mapping,
        "unmatched_headers": [h for h, f in mapping.items() if not f],
        "target_fields": _fields_for(import_type),
        "sample_rows": rows[:5],
    }


async def _get_job(job_id: str, org_id: str) -> dict:
    job = await db.svc_import_jobs.find_one({"id": job_id, "organization_id": org_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Import not found")
    return job


# ─────────────────────────────────────────────────────────────────
# 2) AI fallback mapping
# ─────────────────────────────────────────────────────────────────

@router.post("/{job_id}/ai-map")
async def ai_map(job_id: str, body: dict, user: dict = Depends(require_service_desk)) -> dict:
    """Claude recommends target fields for headers the rules couldn't match."""
    org_id = _of(user)
    job = await _get_job(job_id, org_id)
    headers = [h for h in (body.get("headers") or []) if h in job["headers"]][:40]
    if not headers:
        raise HTTPException(400, "No headers to map")
    key = os.environ.get("EMERGENT_LLM_KEY") or ""
    if not key:
        raise HTTPException(503, "AI service not configured (EMERGENT_LLM_KEY missing)")

    fields = _fields_for(job["import_type"])
    # A couple of sample values per header gives the model real signal.
    samples = {h: [r.get(h, "") for r in job["rows"][:3]] for h in headers}
    prompt = (
        "Map each spreadsheet column header to ONE of the allowed target fields, "
        "or null if none fits.\n"
        f"Allowed target fields: {json.dumps({k: v['label'] for k, v in fields.items()})}\n"
        f"Headers with sample values: {json.dumps(samples)}\n"
        'Reply with ONLY a JSON object: {"<header>": "<field-or-null>", ...}. '
        "Never map two headers to the same field — pick the best one."
    )
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    started = time.time()
    ok = True
    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"svc-import-map-{job_id}",
            system_message="You map messy spreadsheet headers onto a fixed CRM schema. JSON only.",
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        ok = False
        logger.warning("[imports] ai-map failed: %s", e)
        raise HTTPException(502, "AI mapping failed — map the remaining columns manually")
    finally:
        try:
            await db.svc_ai_calls.insert_one({
                "id": str(uuid.uuid4()), "organization_id": org_id, "kind": "import_map",
                "prompt_chars": len(prompt), "response_chars": len(raw) if ok else 0,
                "latency_ms": int((time.time() - started) * 1000), "ok": ok, "at": _now(),
            })
        except Exception:
            pass

    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s[:-3] if s.endswith("```") else s
    try:
        parsed = json.loads(s)
    except Exception:
        return {"mapping": {}, "note": "AI returned an unexpected format — map manually"}
    used = {f for f in job["mapping"].values() if f}
    result: dict[str, str | None] = {}
    for h in headers:
        f = parsed.get(h)
        if f in fields and f not in used:
            result[h] = f
            used.add(f)
        else:
            result[h] = None
    return {"mapping": result}


# ─────────────────────────────────────────────────────────────────
# Row normalisation + validation (shared by validate & commit)
# ─────────────────────────────────────────────────────────────────

def _apply_mapping(row: dict, mapping: dict[str, str]) -> dict:
    out: dict = {}
    for header, field in mapping.items():
        if field:
            out[field] = (row.get(header) or "").strip()
    return out


def _validate_rows(job: dict, mapping: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Return (valid_records, errors). Each error: {row, reason, data}."""
    import_type = job["import_type"]
    valid: list[dict] = []
    errors: list[dict] = []
    for i, raw in enumerate(job["rows"]):
        rec = _apply_mapping(raw, mapping)
        n = i + 2  # 1-based + header row → matches what users see in Excel
        if import_type == "customers":
            if not rec.get("name"):
                errors.append({"row": n, "reason": "Missing customer name", "data": raw})
                continue
            if rec.get("email") and not _EMAIL_RE.match(rec["email"]):
                errors.append({"row": n, "reason": f"Invalid email '{rec['email']}'", "data": raw})
                continue
        else:  # cases
            if not rec.get("title"):
                errors.append({"row": n, "reason": "Missing title / summary", "data": raw})
                continue
            opened = parse_date_cell(rec.get("created_at"))
            if not opened:
                errors.append({"row": n, "reason": f"Missing or unreadable opened date '{rec.get('created_at', '')}'", "data": raw})
                continue
            rec["created_at"] = opened
            closed = parse_date_cell(rec.get("closed_at")) if rec.get("closed_at") else ""
            rec["closed_at"] = closed or opened
            if rec["closed_at"] < rec["created_at"]:
                errors.append({"row": n, "reason": "Closed date is before opened date", "data": raw})
                continue
            rec["priority"] = _norm_priority(rec.get("priority"))
        rec["_row"] = n
        valid.append(rec)
    return valid, errors


def _customer_dupe_key(rec: dict) -> str:
    email = (rec.get("email") or "").lower()
    if email:
        return f"e:{email}"
    return f"n:{(rec.get('name') or '').lower()}|{(rec.get('postcode') or '').replace(' ', '').lower()}"


async def _existing_customer_keys(org_id: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    async for c in db.svc_engineer_customers.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "postcode": 1},
    ):
        if c.get("email"):
            keys[f"e:{c['email'].lower()}"] = c["id"]
        keys[f"n:{(c.get('name') or '').lower()}|{(c.get('postcode') or '').replace(' ', '').lower()}"] = c["id"]
    return keys


async def _existing_case_refs(org_id: str) -> set[str]:
    refs: set[str] = set()
    async for c in db.svc_cases.find(
        {"organization_id": org_id, "reference": {"$ne": None}}, {"_id": 0, "reference": 1},
    ):
        if c.get("reference"):
            refs.add(str(c["reference"]).strip().lower())
    return refs


async def _count_duplicates(job: dict, valid: list[dict]) -> int:
    org_id = job["organization_id"]
    if job["import_type"] == "customers":
        existing = await _existing_customer_keys(org_id)
        seen: set[str] = set()
        dupes = 0
        for rec in valid:
            k = _customer_dupe_key(rec)
            if k in existing or k in seen:
                dupes += 1
            seen.add(k)
        return dupes
    existing_refs = await _existing_case_refs(org_id)
    seen_refs: set[str] = set()
    dupes = 0
    for rec in valid:
        ref = (rec.get("reference") or "").strip().lower()
        if ref and (ref in existing_refs or ref in seen_refs):
            dupes += 1
        if ref:
            seen_refs.add(ref)
    return dupes


@router.post("/{job_id}/validate")
async def validate(job_id: str, body: dict, user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    job = await _get_job(job_id, org_id)
    fields = _fields_for(job["import_type"])
    mapping = {h: f for h, f in (body.get("mapping") or {}).items()
               if h in job["headers"] and f in fields}
    required = [k for k, v in fields.items() if v.get("required")]
    missing = [k for k in required if k not in mapping.values()]
    if missing:
        raise HTTPException(400, f"Required column(s) not mapped: {', '.join(fields[m]['label'] for m in missing)}")

    valid, errors = _validate_rows(job, mapping)
    dupes = await _count_duplicates(job, valid)
    await db.svc_import_jobs.update_one(
        {"id": job_id}, {"$set": {"mapping": mapping, "status": "validated"}})
    return {
        "row_count": len(job["rows"]),
        "valid_count": len(valid),
        "error_count": len(errors),
        "duplicate_count": dupes,
        "errors": errors[:50],
        "preview": [{k: v for k, v in r.items() if k != "_row"} for r in valid[:10]],
    }


# ─────────────────────────────────────────────────────────────────
# 4) Commit
# ─────────────────────────────────────────────────────────────────

async def _engineer_name_index(org_id: str) -> dict[str, str]:
    idx: dict[str, str] = {}
    async for e in db.svc_engineers.find({"organization_id": org_id}, {"_id": 0, "id": 1, "full_name": 1}):
        if e.get("full_name"):
            idx[e["full_name"].strip().lower()] = e["id"]
    return idx


@router.post("/{job_id}/commit")
async def commit(job_id: str, body: dict, user: dict = Depends(require_service_desk)) -> dict:
    org_id = _of(user)
    job = await _get_job(job_id, org_id)
    if job.get("status") == "committed":
        raise HTTPException(400, "This import has already been committed")
    fields = _fields_for(job["import_type"])
    mapping = {h: f for h, f in (body.get("mapping") or job.get("mapping") or {}).items()
               if h in job["headers"] and f in fields}
    strategy = body.get("duplicate_strategy") or "skip"
    if strategy not in ("skip", "update"):
        raise HTTPException(400, "duplicate_strategy must be 'skip' or 'update'")

    valid, errors = _validate_rows(job, mapping)
    created = updated = skipped = 0
    now = _now()

    if job["import_type"] == "customers":
        from routes.svc.engineer_customers import CustomerIn, _to_doc
        existing = await _existing_customer_keys(org_id)
        seen: set[str] = set()
        for rec in valid:
            key = _customer_dupe_key(rec)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            existing_id = existing.get(key)
            payload_fields = {k: (rec.get(k) or None) for k in CUSTOMER_FIELDS}
            if existing_id:
                if strategy == "skip":
                    skipped += 1
                    continue
                update = {k: v for k, v in payload_fields.items() if v}
                update["updated_at"] = now
                await db.svc_engineer_customers.update_one({"id": existing_id}, {"$set": update})
                updated += 1
            else:
                try:
                    payload = CustomerIn(**payload_fields)
                except Exception as e:
                    errors.append({"row": rec["_row"], "reason": f"Invalid data: {e}", "data": rec})
                    continue
                doc = _to_doc(payload, org_id=org_id, user_id=user.get("id") or "")
                doc["source"] = "import"
                await db.svc_engineer_customers.insert_one(doc)
                created += 1
    else:  # cases
        existing_refs = await _existing_case_refs(org_id)
        seen_refs: set[str] = set()
        eng_idx = await _engineer_name_index(org_id)
        batch_tag = job_id[:8]
        batch: list[dict] = []
        for n, rec in enumerate(valid):
            ref = (rec.get("reference") or "").strip()
            ref_key = ref.lower()
            if ref_key and (ref_key in existing_refs or ref_key in seen_refs):
                # Historical records are immutable — update would rewrite
                # closed history, so duplicates are always skipped here.
                skipped += 1
                continue
            if ref_key:
                seen_refs.add(ref_key)
            eng_name = (rec.get("engineer_name") or "").strip()
            batch.append({
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "reference": ref or f"IMP-{batch_tag}-{n + 1:05d}",
                "title": rec["title"][:300],
                "description": (rec.get("description") or "")[:8000],
                "status": "closed",
                "priority": rec["priority"],
                "customer_name": rec.get("customer_name") or None,
                "customer_email": (rec.get("customer_email") or "").lower() or None,
                "site_name": rec.get("site_name") or None,
                "site_postcode": rec.get("site_postcode") or None,
                "fault_category": rec.get("fault_category") or None,
                "assigned_engineer_name": eng_name or None,
                "assigned_engineer_id": eng_idx.get(eng_name.lower()) if eng_name else None,
                "created_at": f"{rec['created_at']}T00:00:00+00:00",
                "closed_at": f"{rec['closed_at']}T00:00:00+00:00",
                "updated_at": now,
                "source": "import",
                "source_meta": {"import_id": job_id, "filename": job["filename"]},
                "tags": ["imported"],
                "logged_by_id": user.get("id"),
                "logged_by_name": user.get("full_name") or user.get("email"),
            })
            created += 1
        if batch:
            await db.svc_cases.insert_many(batch)

    await db.svc_import_jobs.update_one({"id": job_id}, {"$set": {
        "status": "committed", "committed_at": now,
        "summary": {"created": created, "updated": updated, "skipped": skipped, "errored": len(errors)},
        "error_rows": errors,
        "rows": [],  # staging payload no longer needed — keep the job light
    }})
    await log_desk_action(
        actor=user, action="import.commit", target_type="import", target_id=job_id,
        summary=f"Imported {job['import_type']} from {job['filename']}: "
                f"{created} created, {updated} updated, {skipped} skipped, {len(errors)} errored",
        details={"import_type": job["import_type"], "filename": job["filename"],
                 "created": created, "updated": updated, "skipped": skipped, "errored": len(errors)},
    )
    return {"created": created, "updated": updated, "skipped": skipped,
            "errored": len(errors), "errors": errors[:50]}


# ─────────────────────────────────────────────────────────────────
# 5) Error rows download
# ─────────────────────────────────────────────────────────────────

@router.get("/{job_id}/errors.csv")
async def errors_csv(job_id: str, user: dict = Depends(require_service_desk)) -> StreamingResponse:
    org_id = _of(user)
    job = await _get_job(job_id, org_id)
    rows = job.get("error_rows") or []
    buf = io.StringIO()
    headers = job.get("headers") or []
    writer = csv.writer(buf)
    writer.writerow(["row", "reason", *headers])
    for e in rows:
        data = e.get("data") or {}
        writer.writerow([e.get("row"), e.get("reason"), *[data.get(h, "") for h in headers]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-errors-{job_id[:8]}.csv"'},
    )


__all__ = ["router"]
