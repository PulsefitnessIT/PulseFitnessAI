"""GDPR compliance endpoints: data export, account deletion, consent, audit logs, data retention."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from datetime import datetime, timezone, timedelta
import json
import logging

from utils.database import db
from utils.auth import get_current_user
from utils.audit import audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance", tags=["GDPR Compliance"])


# ── Data Export (Right of Access — GDPR Art. 15) ─────────────────

@router.get("/my-data")
async def export_my_data(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Export all personal data held for this user (GDPR Art. 15 — Right of Access)."""
    user_id = user["id"]

    # Gather all user data across collections
    user_profile = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    organization = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    equipment = await db.equipment.find({"user_id": user_id}, {"_id": 0}).to_list(500)
    issues = await db.issues.find({"user_id": user_id}, {"_id": 0}).to_list(500)
    files = await db.files.find({"user_id": user_id}, {"_id": 0}).to_list(200)
    imports = await db.equipment_imports.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    audit_entries = await db.audit_logs.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    consent_records = await db.consent_records.find({"user_id": user_id}, {"_id": 0}).to_list(50)

    ip = request.client.host if request.client else ""
    await audit_log("data_export", user_id, user.get("email", ""), "user", user_id, "User requested GDPR data export", ip)

    return {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "data_subject": user.get("email"),
        "profile": user_profile,
        "organization": organization,
        "equipment": equipment,
        "issues_reported": issues,
        "documents": files,
        "imports": imports,
        "audit_trail": audit_entries,
        "consent_records": consent_records,
    }


@router.get("/my-data/download")
async def download_my_data(request: Request, user: dict = Depends(get_current_user)) -> Response:
    """Download personal data as JSON file."""
    data = await export_my_data(request, user)
    json_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=my_data_{user['id'][:8]}.json"},
    )


# ── Account Deletion (Right to Erasure — GDPR Art. 17) ───────────

@router.delete("/delete-account")
async def delete_my_account(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Delete user account and anonymise associated data (GDPR Art. 17)."""
    user_id = user["id"]
    email = user.get("email", "")
    ip = request.client.host if request.client else ""

    # Don't allow master admin to self-delete
    if user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin accounts cannot be self-deleted")

    # Anonymise user data instead of hard delete (preserve audit trail integrity)
    anonymised_email = f"deleted_{user_id[:8]}@anonymised.local"
    await db.users.update_one({"id": user_id}, {"$set": {
        "email": anonymised_email,
        "full_name": "Deleted User",
        "password": "DELETED",
        "phone": "",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "is_deleted": True,
    }})

    # Anonymise in issues
    await db.issues.update_many({"user_id": user_id}, {"$set": {"created_by_name": "Deleted User"}})

    # Log the deletion
    await audit_log("account_deletion", user_id, email, "user", user_id, "GDPR account deletion request fulfilled", ip)

    return {"message": "Account deleted. Your personal data has been anonymised."}


# ── Consent Management (GDPR Art. 7) ─────────────────────────────

CURRENT_TERMS_VERSION = "1.0"
CURRENT_PRIVACY_VERSION = "1.0"


@router.post("/consent")
async def record_consent(body: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Record user consent to terms/privacy policy."""
    consent_type = body.get("type", "terms_and_privacy")
    version = body.get("version", CURRENT_TERMS_VERSION)
    ip = request.client.host if request.client else ""

    consent_doc = {
        "user_id": user["id"],
        "user_email": user.get("email", ""),
        "consent_type": consent_type,
        "version": version,
        "consented": True,
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.consent_records.insert_one(consent_doc)
    await db.users.update_one({"id": user["id"]}, {"$set": {
        f"consent_{consent_type}": version,
        f"consent_{consent_type}_at": datetime.now(timezone.utc).isoformat(),
    }})

    await audit_log("consent_recorded", user["id"], user.get("email", ""), "consent", consent_type, f"Consented to {consent_type} v{version}", ip)
    return {"consented": True, "version": version}


@router.get("/consent/status")
async def get_consent_status(user: dict = Depends(get_current_user)) -> dict:
    """Check if user has consented to current terms version."""
    terms_version = user.get("consent_terms_and_privacy", "")
    needs_consent = terms_version != CURRENT_TERMS_VERSION
    return {
        "needs_consent": needs_consent,
        "current_version": CURRENT_TERMS_VERSION,
        "user_version": terms_version,
    }


# ── Audit Log Viewing (for admins) ───────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(limit: int = 100, user: dict = Depends(get_current_user)) -> dict:
    """View audit logs. Master admin sees all, others see their own."""
    if user.get("is_master_admin"):
        logs = await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))
    else:
        logs = await db.audit_logs.find({"user_id": user["id"]}, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 100))
    return {"logs": logs, "count": len(logs)}


# ── Data Retention (automated cleanup) ────────────────────────────

@router.post("/run-retention")
async def run_data_retention(user: dict = Depends(get_current_user)) -> dict:
    """Run data retention policies. Master admin only."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    now = datetime.now(timezone.utc)
    results = {}

    # 1. Purge expired password reset tokens (older than 24h)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    r = await db.password_reset_tokens.delete_many({"$or": [{"used": True}, {"expires_at": {"$lt": cutoff_24h}}]})
    results["expired_reset_tokens"] = r.deleted_count

    # 2. Archive old audit logs (keep 1 year, archive older)
    cutoff_1y = (now - timedelta(days=365)).isoformat()
    old_logs = await db.audit_logs.find({"timestamp": {"$lt": cutoff_1y}}, {"_id": 0}).to_list(1000)
    if old_logs:
        await db.audit_logs_archive.insert_many(old_logs)
        await db.audit_logs.delete_many({"timestamp": {"$lt": cutoff_1y}})
    results["archived_audit_logs"] = len(old_logs)

    # 3. Purge orphaned import records (pending_review older than 30 days)
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    r = await db.equipment_imports.delete_many({"status": "pending_review", "created_at": {"$lt": cutoff_30d}})
    results["stale_imports"] = r.deleted_count

    await audit_log("data_retention_run", user["id"], user.get("email", ""), "system", "", f"Retention results: {results}")
    return {"results": results}
