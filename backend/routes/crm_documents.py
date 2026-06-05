from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from utils.security_plus import safe_regex
from datetime import datetime, timezone

import uuid
import hashlib

from utils.database import db, APP_NAME, put_object
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/documents", tags=["CRM Documents"])


@router.get("")
async def list_documents(
    search: str = "",
    category: str = "",
    linked_to: str = "",
    skip: int = 0,
    limit: int = 100,
    user=Depends(get_crm_user),
):
    """List CRM documents with optional filters."""
    query = {"organization_id": user.get("organization_id")}
    if search:
        query["$or"] = [
            {"original_filename": safe_regex(search)},
            {"notes": safe_regex(search)},
        ]
    if category:
        query["category"] = category
    if linked_to:
        query["$or"] = query.get("$or", []) + [
            {"linked_contact_id": linked_to},
            {"linked_deal_id": linked_to},
            {"linked_company_id": linked_to},
        ]

    docs = await db.crm_documents.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_documents.count_documents(query)
    return {"documents": docs, "total": total}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Query("general"),
    notes: str = Query(""),
    linked_contact_id: str = Query(""),
    linked_deal_id: str = Query(""),
    linked_company_id: str = Query(""),
    user=Depends(get_crm_user),
):
    """Upload a document to CRM."""
    from utils.file_validation import validate_upload, MIME_ALL_ATTACHMENTS
    data = await file.read()
    content_type = validate_upload(
        file_bytes=data, filename=file.filename,
        allowed=MIME_ALL_ATTACHMENTS, max_size=25 * 1024 * 1024,
    )
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    content_hash = hashlib.sha256(data).hexdigest()

    path = f"{APP_NAME}/crm-docs/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, content_type)

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "original_filename": file.filename,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "content_hash": content_hash,
        "category": category,
        "notes": notes,
        "linked_contact_id": linked_contact_id or None,
        "linked_deal_id": linked_deal_id or None,
        "linked_company_id": linked_company_id or None,
        "uploaded_by": user["id"],
        "uploaded_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(get_crm_user)):
    """Get document metadata."""
    doc = await db.crm_documents.find_one({"id": doc_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_crm_user)):
    """Delete a document."""
    result = await db.crm_documents.delete_one({"id": doc_id, "organization_id": user.get("organization_id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}
