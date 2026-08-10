from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Form
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import hashlib
import logging
import json
import io

from utils.database import db, APP_NAME, EMERGENT_LLM_KEY, put_object
from utils.auth import get_current_user
# emergentintegrations (litellm) imported lazily inside functions to keep it off the startup import path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/documents", tags=["Admin Documents"])

# Known gym equipment suppliers for matching
KNOWN_SUPPLIERS = [
    "Pulse Fitness", "Technogym", "Life Fitness", "Precor", "Cybex",
    "Matrix Fitness", "Hammer Strength", "Star Trac", "Nautilus", "Body-Solid",
    "Keiser", "Concept2", "Rogue Fitness", "Eleiko", "Jordan Fitness",
    "Watson Gym Equipment", "Peloton", "NordicTrack", "Assault Fitness",
    "Woodway", "TRX", "Wattbike", "StairMaster", "Hoist Fitness", "Octane Fitness",
    "Spirit Fitness", "Gym80", "BH Fitness", "Panatta", "Escape Fitness",
]


def require_admin(user):
    if not user or not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _extract_pdf_text(data: bytes, max_chars: int = 3000) -> str:
    """Extract text from first few pages of a PDF."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = ""
        for page in reader.pages[:3]:
            text += (page.extract_text() or "") + "\n"
            if len(text) > max_chars:
                break
        return text[:max_chars]
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""


async def _ai_detect_supplier(filename: str, text_content: str) -> str:
    """Use AI to detect the supplier/manufacturer from file content."""
    try:
        session_id = f"supplier_detect_{datetime.now().timestamp()}"
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message="You identify gym equipment manufacturers/suppliers from document content. Return ONLY the supplier company name, nothing else. If unsure, return 'Uncategorised'.",
        ).with_model("openai", "gpt-5.2")

        known_list = ", ".join(KNOWN_SUPPLIERS)
        prompt = f"""Identify the equipment manufacturer/supplier from this gym equipment document.

Filename: {filename}

Document text (first pages):
{text_content[:2000] if text_content else '(no text extracted)'}

Common gym suppliers: {known_list}

Return ONLY the supplier company name (e.g. "Technogym" or "Pulse Fitness"). If you cannot determine it, return "Uncategorised"."""

        result = await chat.send_message(UserMessage(text=prompt))
        detected = result.strip().strip('"').strip("'")
        # Validate it's a reasonable name (not a sentence)
        if len(detected) > 50 or "\n" in detected:
            return "Uncategorised"
        return detected if detected else "Uncategorised"
    except Exception as e:
        logger.warning(f"AI supplier detection failed: {e}")
        return "Uncategorised"


def _detect_duplicates(docs):
    """Group documents by content_hash and flag duplicates."""
    hash_groups = {}
    for d in docs:
        h = d.get("content_hash")
        if h:
            hash_groups.setdefault(h, []).append(d["id"])
    duplicate_ids = set()
    for ids in hash_groups.values():
        if len(ids) > 1:
            duplicate_ids.update(ids)
    return hash_groups, duplicate_ids


async def _fetch_org_name_map(docs: list) -> dict:
    """Resolve org_id → org_name for all docs in a single query."""
    org_ids = list({d.get("organization_id") for d in docs if d.get("organization_id")})
    if not org_ids:
        return {}
    orgs: dict = {}
    cursor = db.organizations.find({"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1})
    async for o in cursor:
        orgs[o["id"]] = o["name"]
    return orgs


def _annotate_doc(d: dict, orgs: dict, hash_groups: dict, duplicate_ids: set) -> dict:
    """Add org_name, is_duplicate, duplicate_count fields to a doc."""
    d["org_name"] = orgs.get(d.get("organization_id"), "Global")
    d["is_duplicate"] = d["id"] in duplicate_ids
    h = d.get("content_hash")
    d["duplicate_count"] = (len(hash_groups[h]) - 1) if h and h in hash_groups else 0
    return d


@router.get("")
async def list_global_documents(
    supplier: Optional[str] = None,
    category: Optional[str] = None,
    duplicates_only: bool = False,
    user: dict = Depends(get_current_user),
):
    """List ALL documents across all orgs, grouped by supplier."""
    require_admin(user)

    query = {}
    if supplier:
        query["supplier_name"] = supplier
    if category:
        query["category"] = category

    docs = await db.files.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    orgs = await _fetch_org_name_map(docs)
    hash_groups, duplicate_ids = _detect_duplicates(docs)

    result = [_annotate_doc(d, orgs, hash_groups, duplicate_ids) for d in docs]
    if duplicates_only:
        result = [d for d in result if d["is_duplicate"]]

    suppliers = sorted({d.get("supplier_name", "Uncategorised") for d in result})

    return {
        "files": result,
        "total": len(result),
        "suppliers": suppliers,
        "duplicate_count": len(duplicate_ids),
    }


async def _process_upload_file(file: UploadFile, supplier_name: str, auto_detect: bool, category: str, user_id: str):
    """Process a single file upload: hash, detect supplier, store, create DB record."""
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"

    content_hash = hashlib.sha256(data).hexdigest()
    existing = await db.files.find_one({"content_hash": content_hash}, {"_id": 0, "id": 1, "original_filename": 1})
    is_dup = existing is not None

    file_supplier = supplier_name
    if auto_detect:
        text_content = _extract_pdf_text(data) if ext.lower() == "pdf" else ""
        file_supplier = await _ai_detect_supplier(file.filename, text_content)

    path = f"{APP_NAME}/global/{file_supplier.replace(' ', '_')}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, content_type)

    file_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "organization_id": None,
        "category": category,
        "supplier_name": file_supplier,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "content_hash": content_hash,
        "is_global": True,
        "auto_detected_supplier": auto_detect,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.files.insert_one(file_doc)
    file_doc.pop("_id", None)

    if is_dup:
        file_doc["duplicate_of"] = existing["original_filename"]

    return file_doc, file_supplier, is_dup


@router.post("/upload")
async def global_upload(
    files: List[UploadFile] = File(...),
    supplier_name: str = Form("Uncategorised"),
    category: str = Form("manuals"),
    auto_detect: bool = Form(False),
    user: dict = Depends(get_current_user),
):
    """Mass upload documents to global catalogue with supplier tagging and optional AI auto-detection."""
    require_admin(user)

    uploaded = []
    duplicates_found = []
    detected_suppliers = {}

    for file in files:
        file_doc, detected_supplier, is_dup = await _process_upload_file(file, supplier_name, auto_detect, category, user["id"])
        if auto_detect:
            detected_suppliers[file.filename] = detected_supplier
        if is_dup:
            duplicates_found.append(file_doc)
        uploaded.append(file_doc)

    for doc in uploaded:
        try:
            await _ai_extract(doc["id"], doc["original_filename"], doc.get("supplier_name", ""))
        except Exception as e:
            logger.warning(f"AI extraction failed for {doc['original_filename']}: {e}")

    return {
        "uploaded": len(uploaded),
        "files": uploaded,
        "duplicates_found": len(duplicates_found),
        "duplicate_details": duplicates_found,
        "auto_detected": auto_detect,
        "detected_suppliers": detected_suppliers,
    }


@router.put("/{file_id}/assign-org")
async def assign_document_to_org(
    file_id: str,
    org_id: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Assign a global document to a specific organization."""
    require_admin(user)

    doc = await db.files.find_one({"id": file_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    await db.files.update_one(
        {"id": file_id},
        {"$set": {"organization_id": org_id, "assigned_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": f"Document assigned to {org['name']}"}


@router.put("/{file_id}/supplier")
async def update_document_supplier(
    file_id: str,
    supplier_name: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Update the supplier name on a document."""
    require_admin(user)
    result = await db.files.update_one({"id": file_id}, {"$set": {"supplier_name": supplier_name}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Supplier updated"}


@router.delete("/{file_id}")
async def delete_global_document(file_id: str, user: dict = Depends(get_current_user)):
    """Delete any document globally."""
    require_admin(user)
    result = await db.files.delete_one({"id": file_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}


def _build_doc_summaries(docs: list) -> list:
    """Build compact summaries for AI duplicate comparison."""
    summaries = []
    for d in docs:
        ext = d.get("ai_extraction", {})
        equip = ext.get("equipment_info", {})
        summaries.append({
            "id": d["id"],
            "filename": d.get("original_filename", ""),
            "supplier": d.get("supplier_name", ""),
            "equipment_type": equip.get("equipment_type", ""),
            "manufacturer": equip.get("manufacturer", ""),
            "model": equip.get("model", ""),
            "summary": ext.get("summary", ""),
            "content_hash": d.get("content_hash", ""),
        })
    return summaries


@router.post("/ai-scan-duplicates")
async def ai_scan_duplicates(user: dict = Depends(get_current_user)):
    """AI-powered scan for semantic duplicates across all documents."""
    require_admin(user)

    docs = await db.files.find(
        {"ai_extracted": True},
        {"_id": 0, "id": 1, "original_filename": 1, "supplier_name": 1, "content_hash": 1, "ai_extraction": 1},
    ).to_list(500)

    if len(docs) < 2:
        return {"duplicates": [], "message": "Need at least 2 AI-indexed documents to scan"}

    doc_summaries = _build_doc_summaries(docs)

    try:
        session_id = f"dup_scan_{datetime.now().timestamp()}"
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=session_id,
            system_message="You identify duplicate or near-duplicate gym equipment documents. Return ONLY valid JSON.",
        ).with_model("openai", "gpt-5.2")

        prompt = f"""Analyze these {len(doc_summaries)} documents and find duplicates or near-duplicates.
Two documents are duplicates if they cover the same equipment manual/guide/certificate even if filenames differ slightly.

Documents:
{json.dumps(doc_summaries, indent=2)}

Return JSON array of duplicate groups:
[{{"ids": ["id1", "id2"], "reason": "Both are Technogym Skillmill manuals", "confidence": "high|medium"}}]
Return empty array [] if no duplicates found."""

        raw = await chat.send_message(UserMessage(text=prompt))
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        groups = json.loads(cleaned)
        return {"duplicates": groups, "documents_scanned": len(doc_summaries)}

    except Exception as e:
        logger.error(f"AI duplicate scan failed: {e}")
        return {"duplicates": [], "error": str(e), "documents_scanned": len(doc_summaries)}


_AI_EXTRACT_SYSTEM_MSG = """You are an expert gym equipment technician and document analyst.
Extract ALL useful information from this document. Return ONLY valid JSON:
{
  "document_type": "manual|service_certificate|maintenance_guide|warranty|other",
  "equipment_info": {"equipment_type": "...", "manufacturer": "...", "model": "...", "serial_number_pattern": "..."},
  "key_specifications": ["spec1", "spec2"],
  "common_faults": [{"fault": "...", "symptoms": "...", "fix": "...", "severity": "low|medium|critical"}],
  "maintenance_schedule": [{"task": "...", "frequency": "daily|weekly|monthly|quarterly|annually"}],
  "safety_warnings": ["warning1"],
  "spare_parts": [{"part": "...", "part_number": "..."}],
  "troubleshooting_tips": ["tip1"],
  "summary": "Brief summary"
}"""


def _parse_ai_json_response(raw: str) -> dict:
    """Strip markdown fences and parse AI JSON response."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(cleaned)


async def _ai_extract(file_id: str, filename: str, supplier_name: str):
    """Background AI extraction for a document."""
    try:
        session_id = f"doc_extract_{file_id}_{datetime.now().timestamp()}"
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=_AI_EXTRACT_SYSTEM_MSG,
        ).with_model("openai", "gpt-5.2")

        raw = await chat.send_message(UserMessage(text=(
            f"Analyze this gym equipment document:\nFilename: {filename}\n"
            f"Supplier/Manufacturer: {supplier_name}\n"
            f"Based on the filename and supplier context, extract all relevant technical information."
        )))
        extraction = _parse_ai_json_response(raw)

        await db.files.update_one(
            {"id": file_id},
            {"$set": {"ai_extracted": True, "ai_extraction": extraction, "extracted_at": datetime.now(timezone.utc).isoformat()}},
        )
        await db.equipment_knowledge.insert_one({
            "id": str(uuid.uuid4()), "file_id": file_id, "organization_id": None,
            "filename": filename, "supplier_name": supplier_name,
            "extraction": extraction, "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(f"AI extraction failed for {file_id}: {e}")
        await db.files.update_one({"id": file_id}, {"$set": {"ai_extracted": False, "ai_extraction_error": str(e)}})
