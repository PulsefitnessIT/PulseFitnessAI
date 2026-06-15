from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from utils.security_plus import safe_regex
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from typing import Optional
import uuid
import csv
import io

from utils.database import db
from utils.crm_pipeline import get_or_create_default_pipeline
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm", tags=["CRM Core"])


def _org_filter(user: dict) -> dict:
    """Return org-scoped filter for CRM queries. Uses impossible match if no org to prevent data leaks."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"organization_id": "__NO_ORG__"}
    return {"organization_id": org_id}


# ==================== AUDIT LOG HELPER ====================
async def log_audit(user, entity_type, entity_id, action, changes=None):
    await db.crm_audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "changes": changes,
        "user_id": user["id"],
        "user_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ==================== DASHBOARD ====================
@router.get("/dashboard")
async def crm_dashboard(user=Depends(get_crm_user)):
    of = _org_filter(user)
    total_contacts = await db.crm_contacts.count_documents(of)
    total_companies = await db.crm_companies.count_documents(of)
    total_deals = await db.crm_deals.count_documents({**of, "stage": {"$nin": ["won", "lost"]}})
    won_deals = await db.crm_deals.count_documents({**of, "stage": "won"})
    lost_deals = await db.crm_deals.count_documents({**of, "stage": "lost"})

    # Pipeline value
    pipeline_cursor = db.crm_deals.find({**of, "stage": {"$nin": ["won", "lost"]}}, {"_id": 0, "value": 1})
    pipeline_value = sum([d.get("value", 0) async for d in pipeline_cursor])

    won_cursor = db.crm_deals.find({**of, "stage": "won"}, {"_id": 0, "value": 1})
    won_value = sum([d.get("value", 0) async for d in won_cursor])

    # Recent activities
    recent = await db.crm_activities.find(of, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

    # Deals by stage — org-scoped pipeline + org-scoped counts
    pipeline = await get_or_create_default_pipeline(user.get("organization_id"))
    stages_summary = []
    if pipeline:
        for stage in pipeline.get("stages", []):
            count = await db.crm_deals.count_documents({**of, "stage": stage["id"]})
            stages_summary.append({"stage_id": stage["id"], "name": stage["name"], "color": stage["color"], "count": count})

    return {
        "total_contacts": total_contacts,
        "total_companies": total_companies,
        "active_deals": total_deals,
        "won_deals": won_deals,
        "lost_deals": lost_deals,
        "pipeline_value": pipeline_value,
        "won_value": won_value,
        "recent_activities": recent,
        "stages_summary": stages_summary,
    }


# ==================== CONTACTS ====================
@router.get("/contacts")
async def list_contacts(
    search: str = "", tag: str = "", source: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user)
):
    of = _org_filter(user)
    query = {**of}
    if search:
        query["$or"] = [
            {"first_name": safe_regex(search)},
            {"last_name": safe_regex(search)},
            {"email": safe_regex(search)},
            {"company_name": safe_regex(search)},
        ]
    if tag:
        query["tags"] = tag
    if source:
        query["source"] = source

    total = await db.crm_contacts.count_documents(query)
    contacts = await db.crm_contacts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"contacts": contacts, "total": total}


@router.post("/contacts")
async def create_contact(data: dict, user=Depends(get_crm_user)):
    contact_id = str(uuid.uuid4())
    contact = {
        "id": contact_id,
        "organization_id": user.get("organization_id"),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        "title": data.get("title", ""),
        "tags": data.get("tags", []),
        "source": data.get("source", "manual"),
        "lead_score": data.get("lead_score", 0),
        "owner_id": data.get("owner_id", user["id"]),
        "notes": data.get("notes", ""),
        "linkedin_url": data.get("linkedin_url", ""),
        "address": data.get("address", ""),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_contacts.insert_one(contact)
    await log_audit(user, "contact", contact_id, "created")
    contact.pop("_id", None)
    return contact


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, user=Depends(get_crm_user)):
    contact = await db.crm_contacts.find_one({"id": contact_id, **_org_filter(user)}, {"_id": 0})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    # Get activities
    activities = await db.crm_activities.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    # Get deals
    deals = await db.crm_deals.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {**contact, "activities": activities, "deals": deals}


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm_contacts.find_one({"id": contact_id, **_org_filter(user)})
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.crm_contacts.update_one({"id": contact_id, **_org_filter(user)}, {"$set": updates})
    await log_audit(user, "contact", contact_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user=Depends(get_crm_user)):
    result = await db.crm_contacts.delete_one({"id": contact_id, **_org_filter(user)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    await log_audit(user, "contact", contact_id, "deleted")
    return {"status": "deleted"}


# ==================== COMPANIES ====================
@router.get("/companies")
async def list_companies(search: str = "", skip: int = 0, limit: int = 50, user=Depends(get_crm_user)):
    of = _org_filter(user)
    query = {**of}
    if search:
        query["$or"] = [
            {"name": safe_regex(search)},
            {"industry": safe_regex(search)},
        ]
    total = await db.crm_companies.count_documents(query)
    companies = await db.crm_companies.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"companies": companies, "total": total}


@router.post("/companies")
async def create_company(data: dict, user=Depends(get_crm_user)):
    company_id = str(uuid.uuid4())
    company = {
        "id": company_id,
        "organization_id": user.get("organization_id"),
        "name": data.get("name", ""),
        "industry": data.get("industry", ""),
        "website": data.get("website", ""),
        "size": data.get("size", ""),
        "revenue": data.get("revenue", ""),
        "address": data.get("address", ""),
        "phone": data.get("phone", ""),
        "notes": data.get("notes", ""),
        # Iter 216h240 — integration round-trip fields. Captured at
        # create-time so spreadsheet migrations from Sage / Sicon can
        # bind the GymAxis row to its upstream natural keys without a
        # second-pass sync. Empty defaults keep the field shape stable
        # for orgs that haven't connected Sage / Sicon yet.
        # See INTEGRATION_FIELD_MAPPING.md §19 + §29.
        "sage_customer_account_id": data.get("sage_customer_account_id", "") or "",
        "sage_customer_reference":  data.get("sage_customer_reference", "")  or "",
        "sicon_company_id":         data.get("sicon_company_id", "")         or "",
        "sicon_company_reference":  data.get("sicon_company_reference", "")  or "",
        "vat_registration":         data.get("vat_registration", "")         or "",
        "currency":                 data.get("currency", "")                 or "",
        "nominal_default":          data.get("nominal_default", "")          or "",
        "payment_terms_days":       data.get("payment_terms_days"),
        "credit_limit":             data.get("credit_limit"),
        "account_status":           data.get("account_status", "")           or "",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_companies.insert_one(company)
    await log_audit(user, "company", company_id, "created")
    # Iter 216h227 — fire the CRM trial first-win milestone so the
    # activation card congratulates the operator on their first lead.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            user.get("organization_id"), "first_lead_added",
            trigger_user_id=user.get("id"),
        )
    except Exception:  # best-effort — never block CRM writes
        pass
    company.pop("_id", None)
    return company


@router.get("/companies/{company_id}")
async def get_company(company_id: str, user=Depends(get_crm_user)):
    company = await db.crm_companies.find_one({"id": company_id, **_org_filter(user)}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    contacts = await db.crm_contacts.find({"company_id": company_id, **_org_filter(user)}, {"_id": 0}).to_list(100)
    deals = await db.crm_deals.find({"company_id": company_id, **_org_filter(user)}, {"_id": 0}).to_list(100)
    return {**company, "contacts": contacts, "deals": deals}


@router.put("/companies/{company_id}")
async def update_company(company_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.crm_companies.update_one({"id": company_id, **_org_filter(user)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    await log_audit(user, "company", company_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, user=Depends(get_crm_user)):
    result = await db.crm_companies.delete_one({"id": company_id, **_org_filter(user)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    await log_audit(user, "company", company_id, "deleted")
    return {"status": "deleted"}


# ==================== DEALS ====================
@router.get("/deals")
async def list_deals(stage: str = "", pipeline_id: str = "", skip: int = 0, limit: int = 100, user=Depends(get_crm_user)):
    of = _org_filter(user)
    query = {**of}
    if stage:
        query["stage"] = stage
    if pipeline_id:
        query["pipeline_id"] = pipeline_id
    deals = await db.crm_deals.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_deals.count_documents(query)
    return {"deals": deals, "total": total}


@router.post("/deals")
async def create_deal(data: dict, user=Depends(get_crm_user)):
    deal_id = str(uuid.uuid4())
    # Get default pipeline if none specified
    pipeline_id = data.get("pipeline_id")
    if not pipeline_id:
        default_pipeline = await get_or_create_default_pipeline(user.get("organization_id"))
        pipeline_id = default_pipeline["id"] if default_pipeline else None

    deal = {
        "id": deal_id,
        "organization_id": user.get("organization_id"),
        "title": data.get("title", ""),
        "value": float(data.get("value", 0)),
        "stage": data.get("stage", "lead"),
        "pipeline_id": pipeline_id,
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        "owner_id": data.get("owner_id", user["id"]),
        "owner_name": user["full_name"],
        "probability": int(data.get("probability", 0)),
        "expected_close": data.get("expected_close"),
        "notes": data.get("notes", ""),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
    }
    await db.crm_deals.insert_one(deal)
    await log_audit(user, "deal", deal_id, "created")

    # Auto-create activity
    await db.crm_activities.insert_one({
        "id": str(uuid.uuid4()),
        "type": "deal_created",
        "contact_id": deal["contact_id"],
        "deal_id": deal_id,
        "company_id": deal["company_id"],
        "description": f"Deal '{deal['title']}' created (£{deal['value']:,.0f})",
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Iter 216h227 — fire the CRM trial first-win milestone for
    # "first deal created" so the activation card congratulates the
    # operator on building their first pipeline opportunity.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            user.get("organization_id"), "first_deal_created",
            trigger_user_id=user.get("id"),
        )
    except Exception:  # best-effort — never block CRM writes
        pass

    deal.pop("_id", None)
    return deal


@router.put("/deals/{deal_id}")
async def update_deal(deal_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm_deals.find_one({"id": deal_id, **_org_filter(user)}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Deal not found")

    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    if "value" in updates:
        updates["value"] = float(updates["value"])
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Check if stage changed
    old_stage = existing.get("stage")
    new_stage = updates.get("stage")
    if new_stage and new_stage != old_stage:
        if new_stage in ("won", "lost"):
            updates["closed_at"] = datetime.now(timezone.utc).isoformat()
        # Log stage change activity
        await db.crm_activities.insert_one({
            "id": str(uuid.uuid4()),
            "type": "stage_change",
            "contact_id": existing.get("contact_id"),
            "deal_id": deal_id,
            "company_id": existing.get("company_id"),
            "description": f"Deal moved from '{old_stage}' to '{new_stage}'",
            "created_by": user["id"],
            "created_by_name": user["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    await db.crm_deals.update_one({"id": deal_id, **_org_filter(user)}, {"$set": updates})
    await log_audit(user, "deal", deal_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, user=Depends(get_crm_user)):
    result = await db.crm_deals.delete_one({"id": deal_id, **_org_filter(user)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Deal not found")
    await log_audit(user, "deal", deal_id, "deleted")
    return {"status": "deleted"}


# ==================== PIPELINE ====================
@router.get("/pipelines")
async def list_pipelines(user=Depends(get_crm_user)):
    org_id = user.get("organization_id")
    await get_or_create_default_pipeline(org_id)  # ensure the org has at least one
    pipelines = await db.crm_pipelines.find({"organization_id": org_id}, {"_id": 0}).to_list(20)
    return {"pipelines": pipelines}


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: str, data: dict, user=Depends(get_crm_user)):
    # Pipelines are org-scoped (SEC-008). Editing is further limited to
    # privileged roles so a low-privilege CRM user (sales_rep/analyst/finance)
    # can't rewrite their org's shared pipeline config.
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")
            or user.get("role") in ("owner", "admin", "manager")):
        raise HTTPException(status_code=403, detail="Insufficient permissions to edit the pipeline")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id")}
    result = await db.crm_pipelines.update_one(
        {"id": pipeline_id, "organization_id": user.get("organization_id")}, {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"status": "updated"}


# ==================== ACTIVITIES ====================
@router.get("/activities")
async def list_activities(
    contact_id: str = "", deal_id: str = "", activity_type: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user)
):
    query = {**_org_filter(user)}
    if contact_id:
        query["contact_id"] = contact_id
    if deal_id:
        query["deal_id"] = deal_id
    if activity_type:
        query["type"] = activity_type
    activities = await db.crm_activities.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_activities.count_documents(query)
    return {"activities": activities, "total": total}


@router.post("/activities")
async def create_activity(data: dict, user=Depends(get_crm_user)):
    activity_id = str(uuid.uuid4())
    activity = {
        "id": activity_id,
        "organization_id": user.get("organization_id"),
        "type": data.get("type", "note"),
        "contact_id": data.get("contact_id"),
        "deal_id": data.get("deal_id"),
        "company_id": data.get("company_id"),
        "description": data.get("description", ""),
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_activities.insert_one(activity)
    activity.pop("_id", None)
    return activity


# ==================== AUDIT LOG ====================
@router.get("/audit-log")
async def list_audit_log(
    entity_type: str = "", entity_id: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user)
):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    query = {}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    logs = await db.crm_audit_log.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_audit_log.count_documents(query)
    return {"logs": logs, "total": total}


# ==================== DATA IMPORT ====================
def _normalize_csv_field(row: dict, *keys) -> str:
    """Get the first non-empty value from multiple possible CSV column names."""
    for key in keys:
        val = (row.get(key) or "").strip()
        if val:
            return val
    return ""


def _parse_csv_row(row: dict, user_id: str) -> dict | None:
    """Parse a single CSV row into a contact dict. Returns None if row is empty."""
    email = _normalize_csv_field(row, "email", "Email").lower()
    first_name = _normalize_csv_field(row, "first_name", "First Name", "FirstName")
    last_name = _normalize_csv_field(row, "last_name", "Last Name", "LastName")

    if not first_name and not last_name and not email:
        return None

    return {
        "id": str(uuid.uuid4()),
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": _normalize_csv_field(row, "phone", "Phone"),
        "company_name": _normalize_csv_field(row, "company", "Company", "company_name"),
        "title": _normalize_csv_field(row, "title", "Title", "job_title"),
        "tags": [t.strip() for t in _normalize_csv_field(row, "tags", "Tags").split(",") if t.strip()],
        "source": "csv_import",
        "lead_score": 0,
        "owner_id": user_id,
        "company_id": None,
        "notes": "",
        "linkedin_url": _normalize_csv_field(row, "linkedin", "LinkedIn"),
        "address": _normalize_csv_field(row, "address", "Address"),
        # Iter 216h240 — Sage round-trip refs. When the CSV carries
        # these, the row binds to the existing Sage SLCustomerAccount
        # at upsert time instead of being treated as a new contact.
        # See INTEGRATION_FIELD_MAPPING.md §29.
        "sage_ref": _normalize_csv_field(row, "sage_ref", "Sage Ref", "sage_reference"),
        "sage_id":  _normalize_csv_field(row, "sage_id",  "Sage ID"),
        "sage_customer_account_id": _normalize_csv_field(row, "sage_customer_account_id", "Sage Customer Account ID"),
        "created_by": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/import/contacts")
async def import_contacts(file: UploadFile = File(...), user=Depends(get_crm_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    content = await file.read()
    validate_upload(file_bytes=content, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped = 0, 0
    errors = []

    for i, row in enumerate(reader):
        try:
            contact = _parse_csv_row(row, user["id"])
            if not contact:
                skipped += 1
                continue

            # Iter 216h240 — dedupe on `sage_ref` first (when present)
            # so re-imports from Sage don't create duplicates. Fall back
            # to email dedupe for the standard case.
            if contact.get("sage_ref"):
                existing = await db.crm_contacts.find_one({"sage_ref": contact["sage_ref"]})
                if existing:
                    skipped += 1
                    continue
            if contact["email"]:
                existing = await db.crm_contacts.find_one({"email": contact["email"]})
                if existing:
                    skipped += 1
                    continue

            await db.crm_contacts.insert_one(contact)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    await log_audit(user, "import", "contacts", "bulk_import", {"imported": imported, "skipped": skipped})
    return {"imported": imported, "skipped": skipped, "errors": errors[:10]}


# ==================== COMPANY CSV IMPORT (Iter 216h240) ====================
# See INTEGRATION_FIELD_MAPPING.md §19 — every column below has a
# documented Sage / Sicon counterpart, so a freshly-imported spreadsheet
# binds cleanly to the existing accounts on the next sync (no duplicates).
_COMPANY_CSV_HEADERS = [
    "name",                        # required
    "industry",
    "website",
    "size",
    "revenue",
    "address",
    "phone",
    "notes",
    # Integration refs — natural keys for Sage / Sicon round-trip.
    "sage_customer_account_id",
    "sage_customer_reference",
    "sicon_company_id",
    "sicon_company_reference",
    "vat_registration",
    "currency",
    "nominal_default",
    "payment_terms_days",
    "credit_limit",
    "account_status",
]


@router.get("/companies-csv-template")
async def download_companies_csv_template(user=Depends(get_crm_user)):
    """Iter 216h240 — canonical company CSV template.

    Pre-filled with one example row so operators can see the expected
    shape of each Sage/Sicon column. Idempotent download.

    Path note: uses ``-`` separator instead of ``/`` to avoid colliding
    with the dynamic ``GET /companies/{company_id}`` route — FastAPI
    resolves routes in registration order, and the dynamic param
    pattern would otherwise swallow ``csv-template`` as a fake id.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_COMPANY_CSV_HEADERS)
    w.writerow([
        "Acme Fitness Ltd", "Health & Fitness", "https://acmefitness.example", "201-500",
        "£8M", "1 Acme Way, London SW1A 1AA", "020 0000 0000",
        "Migrated from Pulse Fitness back-office on 2026-02-19.",
        # Sage refs
        "ACME001", "ACME-LDN", "sicon-acme-1234", "SiconAcme",
        "GB123456789", "GBP", "4000", "30", "50000", "active",
    ])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="gymaxis-companies-template.csv"'},
    )


def _parse_company_csv_row(row: dict, user_id: str, org_id: Optional[str]) -> Optional[dict]:
    """Build a `crm_companies` document from a single CSV row. Returns
    None when the row is missing the required `name` field."""
    name = _normalize_csv_field(row, "name", "Name", "company_name").strip()
    if not name:
        return None

    def _val(*aliases: str) -> str:
        return _normalize_csv_field(row, *aliases).strip()

    def _num_or_none(s: str):
        if not s:
            return None
        try:
            # Accept "30", "30.0", "£50,000" — strip non-numeric where sensible.
            cleaned = "".join(c for c in s if c.isdigit() or c in ".-")
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": name,
        "industry": _val("industry", "Industry"),
        "website": _val("website", "Website"),
        "size":    _val("size", "Size"),
        "revenue": _val("revenue", "Revenue"),
        "address": _val("address", "Address"),
        "phone":   _val("phone", "Phone"),
        "notes":   _val("notes", "Notes"),
        # Integration round-trip fields. Every value preserved as a
        # string so leading zeros / mixed-case account refs survive.
        "sage_customer_account_id": _val("sage_customer_account_id", "Sage Customer Account ID"),
        "sage_customer_reference":  _val("sage_customer_reference",  "Sage Customer Reference", "sage_ref"),
        "sicon_company_id":         _val("sicon_company_id",         "Sicon Company ID"),
        "sicon_company_reference":  _val("sicon_company_reference",  "Sicon Company Reference"),
        "vat_registration":         _val("vat_registration",         "VAT Registration"),
        "currency":                 _val("currency",                 "Currency") or "GBP",
        "nominal_default":          _val("nominal_default",          "Nominal Default"),
        "payment_terms_days":       _num_or_none(_val("payment_terms_days", "Payment Terms Days")),
        "credit_limit":             _num_or_none(_val("credit_limit", "Credit Limit")),
        "account_status":           _val("account_status", "Account Status") or "active",
        "source": "csv_import",
        "created_by": user_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


@router.post("/companies-import-csv")
async def import_companies_csv(file: UploadFile = File(...), user=Depends(get_crm_user)):
    """Iter 216h240 — CRM Companies CSV bulk-import.

    Idempotent dedupe order: ``sage_customer_reference`` (preferred) →
    ``sicon_company_reference`` → ``name`` (case-insensitive). Re-running
    the same CSV is safe; rows with a matching natural key are skipped
    rather than duplicated.

    Manager / admin only — this is a commercial dataset. Path note:
    sibling of ``GET /companies-csv-template``; same reason for the
    ``-`` separator (avoids ``/companies/{company_id}`` collision).
    """
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    content = await file.read()
    validate_upload(file_bytes=content, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is empty or missing a header row")
    headers_lower = [(h or "").strip().lower() for h in reader.fieldnames]
    if "name" not in headers_lower:
        raise HTTPException(
            status_code=400,
            detail="CSV must include a 'name' column. Download the template via GET /api/crm/companies-csv-template.",
        )

    imported, skipped = 0, 0
    errors: list[str] = []
    org_id = user.get("organization_id")
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        try:
            doc = _parse_company_csv_row(row, user["id"], org_id)
            if not doc:
                skipped += 1
                continue

            # Idempotent dedupe — natural-key first, then name fallback.
            dedupe_query = None
            if doc.get("sage_customer_reference"):
                dedupe_query = {"sage_customer_reference": doc["sage_customer_reference"]}
            elif doc.get("sicon_company_reference"):
                dedupe_query = {"sicon_company_reference": doc["sicon_company_reference"]}
            else:
                dedupe_query = {"name": doc["name"]}

            if org_id:
                dedupe_query["organization_id"] = org_id

            existing = await db.crm_companies.find_one(dedupe_query, {"_id": 0, "id": 1})
            if existing:
                skipped += 1
                continue

            await db.crm_companies.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i}: {e!s}")

    await log_audit(user, "import", "companies", "bulk_import", {"imported": imported, "skipped": skipped})
    return {"imported": imported, "skipped": skipped, "errors": errors[:10]}




# ==================== CRM USERS LIST ====================
def _humanize_role(role):
    """lower_snake job-role token → Title Case ("sales_manager" → "Sales Manager")."""
    if not role:
        return None
    return str(role).replace("_", " ").replace("-", " ").title()


@router.get("/users")
async def list_crm_users(user=Depends(get_crm_user)):
    org_id = user.get("organization_id")
    query = {"organization_id": org_id} if org_id else {}
    users = await db.crm_users.find(query, {"_id": 0, "password": 0}).to_list(100)

    # Iter 279e — enrich each CRM team member with their company JOB TITLE
    # (Engineer, Sales Manager …) drawn from the shared staffing catalogue.
    # This is read-only here and kept SEPARATE from the CRM permission role:
    # it pulls through from the linked platform user's staffing primary_role
    # (which itself syncs from the role set in Master Admin — iter 279c).
    emails_lc = [(u.get("email") or "").lower().strip() for u in users if u.get("email")]
    if emails_lc and org_id:
        plat_users = await db.users.find(
            {"organization_id": org_id, "email": {"$in": emails_lc}},
            {"_id": 0, "id": 1, "email": 1, "role": 1},
        ).to_list(500)
        # case-insensitive email match (platform emails may be stored mixed-case)
        if len(plat_users) < len(set(emails_lc)):
            plat_users = await db.users.find(
                {"organization_id": org_id},
                {"_id": 0, "id": 1, "email": 1, "role": 1},
            ).to_list(2000)
        plat_by_email = {(p.get("email") or "").lower().strip(): p for p in plat_users}
        plat_ids = [p["id"] for p in plat_by_email.values() if p.get("id")]
        staff = await db.staff_members.find(
            {"organization_id": org_id,
             "$or": [{"user_id": {"$in": plat_ids}}, {"email": {"$in": emails_lc}}]},
            {"_id": 0, "user_id": 1, "email": 1, "primary_role": 1},
        ).to_list(2000)
        staff_by_uid = {s["user_id"]: s for s in staff if s.get("user_id")}
        staff_by_email = {(s.get("email") or "").lower().strip(): s for s in staff if s.get("email")}
        for u in users:
            em = (u.get("email") or "").lower().strip()
            pu = plat_by_email.get(em)
            role_token = None
            if pu:
                sm = staff_by_uid.get(pu.get("id")) or staff_by_email.get(em)
                role_token = (sm or {}).get("primary_role") or pu.get("role")
            elif em in staff_by_email:
                role_token = staff_by_email[em].get("primary_role")
            u["job_title"] = _humanize_role(role_token)
    else:
        for u in users:
            u["job_title"] = None

    return {"users": users}


# ==================== INVITE / REMOVE / EDIT TEAM MEMBERS ====================

def _require_team_admin(user: dict):
    """Check user has permission to manage team."""
    if user["role"] not in ("admin", "owner", "manager"):
        raise HTTPException(403, "Insufficient permissions to manage team")


@router.post("/users/invite")
async def invite_crm_user(data: dict, user=Depends(get_crm_user)):
    """Invite a new team member to the CRM."""
    _require_team_admin(user)

    email = (data.get("email") or "").lower().strip()
    full_name = (data.get("full_name") or "").strip()
    role = data.get("role", "sales_rep")

    if not email or not full_name:
        raise HTTPException(400, "Email and full name required")
    # Owner can only be set from Master Admin
    if role not in ("admin", "manager", "sales_rep"):
        role = "sales_rep"
    # Managers can only invite sales_rep
    if user["role"] == "manager" and role != "sales_rep":
        raise HTTPException(403, "Managers can only invite Sales Reps")

    existing = await db.crm_users.find_one({"email": email})
    if existing:
        raise HTTPException(409, "A user with this email already exists")

    from routes.crm_auth import crm_hash_password
    temp_password = f"Welcome{uuid.uuid4().hex[:6]}!"
    user_id = str(uuid.uuid4())
    new_user = {
        "id": user_id, "email": email, "full_name": full_name,
        "password": crm_hash_password(temp_password),
        "role": role, "status": "active", "avatar_url": None,
        "organization_id": user.get("organization_id"),
        "invited_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_users.insert_one(new_user)
    await log_audit(user, "user", user_id, "invited", {"email": email, "role": role})
    return {"id": user_id, "email": email, "full_name": full_name, "role": role, "temp_password": temp_password}


def _validate_user_edit_permissions(user: dict, target: dict, data: dict):
    """Validate role-based permissions for editing a team member."""
    if target.get("role") == "owner" and "role" in data and data["role"] != "owner":
        raise HTTPException(403, "Cannot change the Owner's role")
    if user["role"] == "manager" and target.get("role") not in ("sales_rep",):
        raise HTTPException(403, "Managers can only edit Sales Reps")
    if data.get("role") == "owner":
        raise HTTPException(403, "Owner role can only be set from Master Admin")


def _sanitize_user_updates(data: dict) -> dict:
    """Extract and validate allowed fields for user update."""
    allowed = {"full_name", "email", "role", "status", "phone", "job_title"}
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    if "role" in updates and updates["role"] not in ("admin", "manager", "sales_rep"):
        updates["role"] = "sales_rep"
    if "email" in updates:
        updates["email"] = updates["email"].lower().strip()
    return updates


@router.put("/users/{user_id}")
async def update_crm_user(user_id: str, data: dict, user=Depends(get_crm_user)):
    """Edit a team member's name, email, role, or status."""
    _require_team_admin(user)

    target = await db.crm_users.find_one({"id": user_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")

    _validate_user_edit_permissions(user, target, data)
    updates = _sanitize_user_updates(data)

    if "email" in updates:
        dup = await db.crm_users.find_one({"email": updates["email"], "id": {"$ne": user_id}})
        if dup:
            raise HTTPException(409, "Email already in use")

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.crm_users.update_one({"id": user_id}, {"$set": updates})
        await log_audit(user, "user", user_id, "updated", updates)

    return {"success": True}


@router.delete("/users/{user_id}")
async def remove_crm_user(user_id: str, user=Depends(get_crm_user)):
    """Remove a team member."""
    _require_team_admin(user)
    if user_id == user["id"]:
        raise HTTPException(400, "Cannot remove yourself")

    target = await db.crm_users.find_one({"id": user_id, "organization_id": user.get("organization_id")}, {"_id": 0, "email": 1, "role": 1})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("role") == "owner":
        raise HTTPException(403, "Cannot delete the Owner account")

    await db.crm_users.delete_one({"id": user_id})
    await log_audit(user, "user", user_id, "removed", {"email": target.get("email")})
    return {"message": "User removed"}

