"""Unified Import Centre engine.

ONE consistent import pipeline for every data type:
  template → upload → auto-map → validate → dedupe → preview → commit → report

Each type is declared once in TYPE_REGISTRY (fields, aliases for auto-mapping,
dedupe keys, target collection, row→doc transform defaults). Adding a new type
is config, not new code. Writes go into the EXISTING platform collections
(crm_contacts / members / suppliers …) — no new silos, no duplicate records
(dedupe is enforced on commit).

The proven sites / equipment / customers importers keep their dedicated
endpoints; this engine fills the gaps and gives every type the same UX.
"""
import csv
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.pulse_master_admin import _require_pulse_or_master

logger = logging.getLogger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_ROWS = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Type registry ────────────────────────────────────────────────────────

def F(key, label, *, required=False, aliases=None, kind="text"):
    return {"key": key, "label": label, "required": required,
            "aliases": [a.lower() for a in (aliases or [])] + [key.lower(), label.lower()], "kind": kind}


TYPE_REGISTRY = {
    "contacts": {
        "label": "Contacts",
        "collection": "crm_contacts",
        "dedupe_keys": ["email"],
        "fields": [
            F("email", "Email", required=True, aliases=["email address", "e-mail", "mail"], kind="email"),
            F("first_name", "First name", aliases=["firstname", "forename", "given name"]),
            F("last_name", "Last name", aliases=["lastname", "surname", "family name"]),
            F("phone", "Phone", aliases=["telephone", "mobile", "tel"], kind="phone"),
            F("company", "Company", aliases=["organisation", "organization", "account", "customer name"]),
            F("title", "Job title", aliases=["role", "position"]),
            F("linkedin", "LinkedIn", aliases=["linked in", "linkedin url"]),
            F("address", "Address", aliases=["location"]),
        ],
        "defaults": {"lifecycle": "Lead", "source": "import_centre"},
    },
    "members": {
        "label": "Members",
        "collection": "members",
        "dedupe_keys": ["email"],
        "fields": [
            F("email", "Email", required=True, aliases=["email address", "e-mail"], kind="email"),
            F("first_name", "First name", required=True, aliases=["firstname", "forename"]),
            F("last_name", "Last name", aliases=["lastname", "surname"]),
            F("phone", "Phone", aliases=["mobile", "telephone"], kind="phone"),
            F("membership_type", "Membership type", aliases=["membership", "plan", "tier"]),
            F("joined_at", "Join date", aliases=["join date", "start date", "joined"], kind="date"),
        ],
        "defaults": {"active": True, "source": "import_centre"},
    },
    "suppliers": {
        "label": "Suppliers",
        "collection": "suppliers",
        "dedupe_keys": ["name", "email"],
        "fields": [
            F("name", "Supplier name", required=True, aliases=["supplier", "company", "vendor"]),
            F("email", "Email", aliases=["email address", "service email"], kind="email"),
            F("phone", "Phone", aliases=["telephone", "tel"], kind="phone"),
            F("contact_person", "Contact person", aliases=["contact", "contact name"]),
            F("address", "Address", aliases=["location"]),
            F("supplier_type", "Supplier type", aliases=["type", "category"]),
            F("notes", "Notes", aliases=["comment", "comments"]),
        ],
        "defaults": {},
    },
}


def _type_or_404(t: str) -> dict:
    spec = TYPE_REGISTRY.get(t)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Unknown import type '{t}'")
    return spec


# ── Reference + template ───────────────────────────────────────────────────

@router.get("/onboarding/import/types")
async def import_types(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    return {"types": [
        {"id": t, "label": s["label"], "dedupe_keys": s["dedupe_keys"],
         "fields": [{"key": f["key"], "label": f["label"], "required": f["required"], "kind": f["kind"]} for f in s["fields"]]}
        for t, s in TYPE_REGISTRY.items()
    ]}


@router.get("/onboarding/import/template/{import_type}")
async def import_template(import_type: str, user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    spec = _type_or_404(import_type)
    headers = [f["key"] for f in spec["fields"]]
    example = {
        "email": "jane@example.com", "first_name": "Jane", "last_name": "Smith",
        "phone": "+44 20 1234 5678", "company": "Acme Ltd", "title": "Manager",
        "name": "Acme Service Co", "membership_type": "Monthly", "joined_at": "2026-01-15",
        "supplier_type": "Maintenance", "address": "1 High St, London", "notes": "",
        "contact_person": "John Doe", "linkedin": "",
    }
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerow([example.get(h, "") for h in headers])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{import_type}-template.csv"'},
    )


# ── Auto-map helper ──────────────────────────────────────────────────────

def _auto_map(columns: list, spec: dict) -> dict:
    """Suggest {field_key: column_name} from CSV headers via alias matching."""
    mapping = {}
    used = set()
    norm = {c: c.strip().lower() for c in columns}
    for f in spec["fields"]:
        for col, n in norm.items():
            if col in used:
                continue
            if n in f["aliases"] or n.replace("_", " ") in f["aliases"] or n.replace(" ", "_") in f["aliases"]:
                mapping[f["key"]] = col
                used.add(col)
                break
    return mapping


@router.post("/onboarding/import/analyze")
async def analyze(import_type: str = Form(...), file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    spec = _type_or_404(import_type)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    rows = []
    for i, r in enumerate(reader):
        if i >= _MAX_ROWS:
            break
        rows.append({k: (v or "").strip() for k, v in r.items() if k})
    return {
        "import_type": import_type,
        "columns": columns,
        "suggested_mapping": _auto_map(columns, spec),
        "fields": [{"key": f["key"], "label": f["label"], "required": f["required"], "kind": f["kind"]} for f in spec["fields"]],
        "dedupe_keys": spec["dedupe_keys"],
        "sample_rows": rows[:5],
        "rows": rows,
        "row_count": len(rows),
    }


# ── Validate + dedupe ──────────────────────────────────────────────────────

class ValidateBody(BaseModel):
    import_type: str
    mapping: dict                       # {field_key: column_name}
    rows: list                          # list of {column: value}
    organization_id: Optional[str] = None


def _build_doc(row: dict, mapping: dict, spec: dict) -> dict:
    doc = {}
    for f in spec["fields"]:
        col = mapping.get(f["key"])
        if col:
            doc[f["key"]] = (row.get(col) or "").strip()
    return doc


def _validate_doc(doc: dict, spec: dict) -> list:
    errs = []
    for f in spec["fields"]:
        val = doc.get(f["key"], "")
        if f["required"] and not val:
            errs.append(f"Missing required: {f['label']}")
        if val and f["kind"] == "email" and not _EMAIL_RE.match(val):
            errs.append(f"Invalid email: {val}")
        if val and f["kind"] == "phone" and len(re.sub(r"[^0-9]", "", val)) < 7:
            errs.append(f"Suspicious phone: {val}")
    return errs


async def _existing_dupe_keys(spec: dict, org_id: Optional[str], docs: list) -> set:
    """Return the set of dedupe-key signatures already present in the DB."""
    if not org_id:
        return set()
    coll = db[spec["collection"]]
    sig_present = set()
    for dk in spec["dedupe_keys"]:
        vals = [d.get(dk, "").lower() for d in docs if d.get(dk)]
        if not vals:
            continue
        # case-insensitive match via $in on lowercase is approximate; fetch and compare
        existing = await coll.find({"organization_id": org_id}, {"_id": 0, dk: 1}).to_list(20000)
        present = {(e.get(dk) or "").strip().lower() for e in existing if e.get(dk)}
        for v in vals:
            if v in present:
                sig_present.add(f"{dk}:{v}")
    return sig_present


@router.post("/onboarding/import/validate")
async def validate(body: ValidateBody, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    spec = _type_or_404(body.import_type)
    docs = [_build_doc(r, body.mapping, spec) for r in body.rows]
    existing_sig = await _existing_dupe_keys(spec, body.organization_id, docs)

    seen_in_file = {}
    rows_out = []
    counts = {"valid": 0, "errors": 0, "warnings": 0, "dupes_existing": 0, "dupes_in_file": 0}
    for idx, doc in enumerate(docs):
        errs = _validate_doc(doc, spec)
        flags = []
        # in-file duplicate
        sigs = [f"{dk}:{doc.get(dk, '').strip().lower()}" for dk in spec["dedupe_keys"] if doc.get(dk)]
        dup_in_file = any(s in seen_in_file for s in sigs)
        for s in sigs:
            seen_in_file[s] = idx
        dup_existing = any(s in existing_sig for s in sigs)
        if dup_in_file:
            flags.append("duplicate_in_file")
            counts["dupes_in_file"] += 1
        if dup_existing:
            flags.append("duplicate_existing")
            counts["dupes_existing"] += 1
        if errs:
            counts["errors"] += 1
        elif not flags:
            counts["valid"] += 1
        rows_out.append({"row": idx + 1, "doc": doc, "errors": errs, "flags": flags})
    return {
        "import_type": body.import_type,
        "total": len(docs),
        "counts": counts,
        "rows": rows_out,
    }


# ── Commit ──────────────────────────────────────────────────────────────────

class CommitBody(BaseModel):
    import_type: str
    mapping: dict
    rows: list
    organization_id: str
    dedupe_action: str = "skip"         # skip | update | create
    project_id: Optional[str] = None
    project_step_key: Optional[str] = None


@router.post("/onboarding/import/commit")
async def commit(body: CommitBody, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    spec = _type_or_404(body.import_type)
    if body.dedupe_action not in {"skip", "update", "create"}:
        raise HTTPException(status_code=400, detail="Invalid dedupe_action")
    org = await db.organizations.find_one({"id": body.organization_id}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Target organisation not found")

    coll = db[spec["collection"]]
    report = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    seen_in_file = set()

    for idx, row in enumerate(body.rows):
        doc = _build_doc(row, body.mapping, spec)
        errs = _validate_doc(doc, spec)
        if errs:
            report["failed"] += 1
            report["errors"].append({"row": idx + 1, "errors": errs})
            continue
        # in-file dedupe (always skip later dup rows)
        sigs = [f"{dk}:{doc.get(dk, '').strip().lower()}" for dk in spec["dedupe_keys"] if doc.get(dk)]
        if any(s in seen_in_file for s in sigs):
            report["skipped"] += 1
            continue
        for s in sigs:
            seen_in_file.add(s)

        # existing-record dedupe
        existing = None
        for dk in spec["dedupe_keys"]:
            v = doc.get(dk, "").strip()
            if not v:
                continue
            existing = await coll.find_one(
                {"organization_id": body.organization_id, dk: {"$regex": f"^{re.escape(v)}$", "$options": "i"}},
                {"_id": 0, "id": 1},
            )
            if existing:
                break
        try:
            if existing:
                if body.dedupe_action == "skip":
                    report["skipped"] += 1
                    continue
                if body.dedupe_action == "update":
                    await coll.update_one(
                        {"id": existing["id"]},
                        {"$set": {**{k: v for k, v in doc.items() if v}, "updated_at": _now()}},
                    )
                    report["updated"] += 1
                    continue
                # create → fall through to insert a new record
            new_doc = {
                "id": str(uuid.uuid4()),
                "organization_id": body.organization_id,
                **spec.get("defaults", {}),
                **doc,
                "created_at": _now(),
                "created_by": user.get("email"),
            }
            if spec["collection"] == "members":
                fn = doc.get("first_name", ""); ln = doc.get("last_name", "")
                new_doc["full_name"] = (fn + " " + ln).strip()
            if spec["collection"] == "suppliers" and doc.get("supplier_type"):
                new_doc["supplier_types"] = [doc["supplier_type"]]
            await coll.insert_one(new_doc)
            report["created"] += 1
        except Exception as e:
            report["failed"] += 1
            report["errors"].append({"row": idx + 1, "errors": [str(e)]})

    # Audit
    try:
        await db.onboarding_audit_events.insert_one({
            "id": str(uuid.uuid4()),
            "project_id": body.project_id,
            "action": "import_committed",
            "detail": {"type": body.import_type, "org": body.organization_id, "report": report},
            "actor_email": user.get("email"), "at": _now(),
        })
    except Exception:
        logger.exception("import audit failed")

    # Auto-advance the linked onboarding checklist step
    if body.project_id and body.project_step_key and report["created"] + report["updated"] > 0:
        try:
            proj = await db.onboarding_projects.find_one({"id": body.project_id})
            if proj:
                checklist = proj.get("checklist", [])
                for s in checklist:
                    if s.get("key") == body.project_step_key:
                        s["status"] = "complete"
                await db.onboarding_projects.update_one(
                    {"id": body.project_id}, {"$set": {"checklist": checklist, "updated_at": _now()}}
                )
        except Exception:
            logger.exception("checklist auto-advance failed")

    return {"report": report}


# ── Saved mappings ───────────────────────────────────────────────────────────

class MappingSave(BaseModel):
    import_type: str
    name: str
    mapping: dict


@router.get("/onboarding/import/mappings")
async def list_mappings(import_type: Optional[str] = None, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    q = {"import_type": import_type} if import_type else {}
    rows = await db.onboarding_import_mappings.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"mappings": rows}


@router.post("/onboarding/import/mappings")
async def save_mapping(body: MappingSave, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    _type_or_404(body.import_type)
    doc = {
        "id": str(uuid.uuid4()), "import_type": body.import_type, "name": body.name.strip(),
        "mapping": body.mapping, "created_at": _now(), "created_by": user.get("email"),
    }
    await db.onboarding_import_mappings.insert_one(dict(doc))
    return doc
