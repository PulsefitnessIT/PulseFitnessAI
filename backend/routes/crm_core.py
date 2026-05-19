from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timezone
import uuid
import csv
import io

from utils.database import db
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

    # Deals by stage
    pipeline = await db.crm_pipelines.find_one({"is_default": True}, {"_id": 0})
    stages_summary = []
    if pipeline:
        for stage in pipeline.get("stages", []):
            count = await db.crm_deals.count_documents({"stage": stage["id"]})
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
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"company_name": {"$regex": search, "$options": "i"}},
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
    contact = await db.crm_contacts.find_one({"id": contact_id}, {"_id": 0})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    # Get activities
    activities = await db.crm_activities.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    # Get deals
    deals = await db.crm_deals.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {**contact, "activities": activities, "deals": deals}


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm_contacts.find_one({"id": contact_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.crm_contacts.update_one({"id": contact_id}, {"$set": updates})
    await log_audit(user, "contact", contact_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user=Depends(get_crm_user)):
    result = await db.crm_contacts.delete_one({"id": contact_id})
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
            {"name": {"$regex": search, "$options": "i"}},
            {"industry": {"$regex": search, "$options": "i"}},
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
    company = await db.crm_companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    contacts = await db.crm_contacts.find({"company_id": company_id}, {"_id": 0}).to_list(100)
    deals = await db.crm_deals.find({"company_id": company_id}, {"_id": 0}).to_list(100)
    return {**company, "contacts": contacts, "deals": deals}


@router.put("/companies/{company_id}")
async def update_company(company_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.crm_companies.update_one({"id": company_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    await log_audit(user, "company", company_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, user=Depends(get_crm_user)):
    result = await db.crm_companies.delete_one({"id": company_id})
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
        default_pipeline = await db.crm_pipelines.find_one({"is_default": True}, {"_id": 0})
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
    existing = await db.crm_deals.find_one({"id": deal_id}, {"_id": 0})
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

    await db.crm_deals.update_one({"id": deal_id}, {"$set": updates})
    await log_audit(user, "deal", deal_id, "updated", updates)
    return {"status": "updated"}


@router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, user=Depends(get_crm_user)):
    result = await db.crm_deals.delete_one({"id": deal_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Deal not found")
    await log_audit(user, "deal", deal_id, "deleted")
    return {"status": "deleted"}


# ==================== PIPELINE ====================
@router.get("/pipelines")
async def list_pipelines(user=Depends(get_crm_user)):
    pipelines = await db.crm_pipelines.find({}, {"_id": 0}).to_list(20)
    return {"pipelines": pipelines}


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k not in ("id",)}
    result = await db.crm_pipelines.update_one({"id": pipeline_id}, {"$set": updates})
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


# ==================== CRM USERS LIST ====================
@router.get("/users")
async def list_crm_users(user=Depends(get_crm_user)):
    org_id = user.get("organization_id")
    query = {"organization_id": org_id} if org_id else {}
    users = await db.crm_users.find(query, {"_id": 0, "password": 0}).to_list(100)
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
