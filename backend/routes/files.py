from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import Response
from datetime import datetime, timezone
import uuid
import logging
import io
import json

from utils.database import db, APP_NAME, EMERGENT_LLM_KEY, put_object, get_object
from utils.auth import get_current_user, get_organization_filter, verify_token
from utils.ai_access import require_ai_access
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter()


def convert_pdf_to_image(pdf_bytes: bytes) -> tuple:
    """Convert first page of a PDF to a PNG image. Returns (png_bytes, content_type)."""
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=300)
    if not images:
        return None, None
    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue(), "image/png"


@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...), category: str = Query("general"), user: dict = Depends(get_current_user)):
    import hashlib
    from utils.file_validation import validate_upload, MIME_ALL_ATTACHMENTS, MIME_IMAGES, MIME_VIDEOS

    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    data = await file.read()
    original_filename = file.filename
    original_size = len(data)

    # Iter 220ea·33 — engineers' logos are very often SVG (vector exports).
    # SVG is blocked by the validator (can carry inline scripts), so for the
    # branding category we rasterise SVG → PNG up front (cairosvg drops any
    # scripts), which then validates and embeds cleanly in PDFs.
    if category == "branding" and ext.lower() == "svg":
        try:
            import cairosvg
            data = cairosvg.svg2png(bytestring=data, output_width=512)
            ext = "png"
            base = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
            original_filename = f"{base}.png"
        except Exception as e:  # noqa: BLE001
            logger.warning("SVG logo conversion failed: %s", e)
            raise HTTPException(415, "Couldn't process that SVG — please upload a PNG or JPG logo instead.")

    # Iter 216h257 — narrow allow-list per category so engineers can
    # upload videos for case media. Without the override the global
    # `MIME_ALL_ATTACHMENTS` set excluded videos and every video upload
    # silently 415'd, surfacing only as "Upload failed" in the engineer
    # PWA.
    if category in ("videos", "service-videos", "case-videos"):
        allow = MIME_VIDEOS
    elif category in ("photos", "service-photos", "case-photos"):
        allow = MIME_IMAGES
    elif category in ("service-media", "case-media", "engineer-media"):
        # Field engineers capture both photos AND short videos in one flow.
        allow = MIME_IMAGES | MIME_VIDEOS
    else:
        allow = MIME_ALL_ATTACHMENTS

    # Sniff actual bytes — reject polyglots (e.g. HTML disguised as PDF).
    content_type = validate_upload(
        file_bytes=data,
        filename=original_filename,
        allowed=allow,
    )

    # Compress PDFs before storage (PyMuPDF — typically 30-60% smaller
    # with no visible quality loss). Falls back to the original bytes
    # automatically if compression bloats the file.
    if ext.lower() == "pdf":
        from utils.pdf_compress import compress_pdf
        data = compress_pdf(data)

    # Compute content hash for duplicate detection
    content_hash = hashlib.sha256(data).hexdigest()

    # Auto-convert PDF to PNG for floor plans (canvas can't render PDFs)
    if category == "floor-plans" and ext.lower() == "pdf":
        try:
            png_data, png_ct = convert_pdf_to_image(data)
            if png_data:
                data = png_data
                content_type = png_ct
                ext = "png"
                original_filename = file.filename.rsplit(".", 1)[0] + ".png"
                logger.info("Converted PDF floor plan to PNG for canvas rendering")
        except Exception as e:
            logger.error(f"PDF to image conversion failed: {e}")

    path = f"{APP_NAME}/{category}/{user.get('organization_id', user['id'])}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, content_type)

    file_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "category": category,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "original_filename": original_filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "original_size": original_size,
        "compression_ratio": round(1 - (len(data) / original_size), 3) if original_size > 0 and len(data) < original_size else 0,
        "content_hash": content_hash,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.files.insert_one(file_doc)
    file_doc.pop('_id', None)

    # Iter 216bn — auto-trigger AI extraction in the background for
    # indexable document types. Lee removed the user-facing "Index"
    # button + status card per Feb 2026 production feedback; the
    # ingestion still has to happen so DocumentQA + fault-AI-triage
    # have content to draw from. Fire-and-forget — failures are
    # logged inside _run_ai_extraction and don't fail the upload.
    if (ext.lower() in ("pdf", "doc", "docx", "txt") and
            category not in ("floor-plans", "photos")):
        import asyncio as _asyncio
        async def _bg_index(doc):
            try:
                extraction = await _run_ai_extraction(doc)
                await db.files.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "ai_extracted": True,
                        "ai_extraction": extraction,
                        "ai_indexed_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
            except Exception as exc:
                logger.warning("[files] silent auto-index failed for %s: %s", doc.get("id"), exc)
                await db.files.update_one(
                    {"id": doc["id"]},
                    {"$set": {"ai_extracted": False, "ai_extraction_error": str(exc)}},
                )
        _asyncio.create_task(_bg_index(file_doc))

    return file_doc


@router.get("/files/list")
async def list_files(category: str = None, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    query = {**org_filter}
    if category:
        query["category"] = category
    files = await db.files.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"files": files}


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    result = await db.files.delete_one({"id": file_id, **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted"}


_EXTRACTION_SYSTEM_MSG = """You are an expert gym equipment technician and document analyst.
You are analyzing a document related to gym equipment. Extract ALL useful information.
Return ONLY valid JSON:
{
  "document_type": "manual|service_certificate|maintenance_guide|warranty|other",
  "equipment_info": {"equipment_type": "...", "manufacturer": "...", "model": "...", "serial_number_pattern": "..."},
  "key_specifications": ["spec1", "spec2"],
  "common_faults": [{"fault": "...", "symptoms": "...", "fix": "...", "severity": "low|medium|critical"}],
  "maintenance_schedule": [{"task": "...", "frequency": "daily|weekly|monthly|quarterly|annually", "notes": "..."}],
  "safety_warnings": ["warning1", "warning2"],
  "spare_parts": [{"part": "...", "part_number": "...", "notes": "..."}],
  "troubleshooting_tips": ["tip1", "tip2"],
  "summary": "Brief summary of what this document contains"
}"""


def _clean_ai_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from AI output."""
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(cleaned)


async def _run_ai_extraction(file_doc: dict) -> dict:
    """Run AI extraction on a file document and return parsed JSON."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"doc_extract_{file_doc['id']}_{datetime.now().timestamp()}",
        system_message=_EXTRACTION_SYSTEM_MSG,
    ).with_model("openai", "gpt-5.2")

    prompt = (
        f"Analyze this gym equipment document:\n"
        f"Filename: {file_doc.get('original_filename', 'Unknown')}\n"
        f"Category: {file_doc.get('category', 'general')}\n"
        f"Content Type: {file_doc.get('content_type', 'unknown')}\n\n"
        f"Extract all relevant technical information for maintenance staff."
    )
    return _clean_ai_json(await chat.send_message(UserMessage(text=prompt)))


@router.post("/files/{file_id}/extract")
async def extract_file_info(file_id: str, user: dict = Depends(require_ai_access)):
    """AI extracts information from an uploaded document to improve future fault diagnosis."""
    org_filter = get_organization_filter(user)
    file_doc = await db.files.find_one({"id": file_id, **org_filter}, {"_id": 0})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")

    if file_doc.get('ai_extracted'):
        return {"already_extracted": True, "extraction": file_doc.get('ai_extraction', {})}

    try:
        extraction = await _run_ai_extraction(file_doc)

        await db.files.update_one(
            {"id": file_id},
            {"$set": {
                "ai_extracted": True,
                "ai_extraction": extraction,
                "extracted_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        await db.equipment_knowledge.insert_one({
            "id": str(uuid.uuid4()),
            "file_id": file_id,
            "organization_id": user.get('organization_id'),
            "filename": file_doc.get('original_filename'),
            "extraction": extraction,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        return {"success": True, "extraction": extraction}

    except Exception as e:
        logger.error(f"AI extraction failed for {file_id}: {e}")
        await db.files.update_one(
            {"id": file_id},
            {"$set": {"ai_extracted": False, "ai_extraction_error": str(e)}}
        )
        raise HTTPException(status_code=500, detail="AI extraction failed")


@router.get("/files/{file_id}")
async def get_file(file_id: str, user: dict = Depends(get_current_user)):
    # P1.7 — must be scoped to caller's org (or master admin override).
    query = {"id": file_id}
    if not user.get("is_master_admin"):
        query["organization_id"] = user.get("organization_id")
    file_doc = await db.files.find_one(query, {"_id": 0})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(file_doc["storage_path"])
        return Response(content=data, media_type=content_type, headers={"Content-Disposition": f"inline; filename={file_doc['original_filename']}"})
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")


@router.get("/files/{file_id}/view")
async def view_file_inline(file_id: str, token: str = Query(...)):
    """Serve a file for inline viewing (e.g. PDF in iframe) using a token query param."""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    # P1.7 — must be scoped to caller's org (or master admin override).
    viewer = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0})
    if not viewer:
        raise HTTPException(status_code=401, detail="Invalid token")
    query = {"id": file_id}
    if not viewer.get("is_master_admin"):
        query["organization_id"] = viewer.get("organization_id")
    file_doc = await db.files.find_one(query, {"_id": 0})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(file_doc["storage_path"])
        return Response(content=data, media_type=content_type, headers={
            "Content-Disposition": f"inline; filename={file_doc['original_filename']}",
        })
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")



@router.get("/public/files/{file_id}")
async def get_public_file(file_id: str):
    """Public file access — only for branding category files."""
    file_doc = await db.files.find_one({"id": file_id, "category": "branding"}, {"_id": 0})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(file_doc["storage_path"])
        return Response(content=data, media_type=content_type, headers={
            "Content-Disposition": f"inline; filename={file_doc['original_filename']}",
            "Cache-Control": "public, max-age=3600"
        })
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")


from pydantic import BaseModel
from typing import Optional


class DocumentQuestion(BaseModel):
    question: str
    equipment_type: Optional[str] = None
    supplier: Optional[str] = None


def _score_word_matches(q_lower: str, fields: list[str]) -> int:
    """Score how many query words appear in the given text fields."""
    score = 0
    for word in q_lower.split():
        if len(word) > 3 and any(word in f for f in fields):
            score += 3
    return score


def _score_equipment_match(eq_lower: str, eq_type: str) -> int:
    """Score equipment type match."""
    if not eq_lower:
        return 0
    if eq_lower in eq_type or eq_type in eq_lower:
        return 10
    if any(w in eq_type for w in eq_lower.split() if len(w) > 3):
        return 5
    return 0


def _score_supplier_match(sup_lower: str, eq_mfr: str, doc_supplier: str) -> int:
    """Score supplier name match."""
    if not sup_lower:
        return 0
    if sup_lower in eq_mfr or eq_mfr in sup_lower or sup_lower in doc_supplier or doc_supplier in sup_lower:
        return 8
    return 0


def _score_document(kd: dict, q_lower: str, eq_lower: str, sup_lower: str) -> int:
    """Score a knowledge document by relevance to a question."""
    ext = kd.get("extraction", {})
    equip_info = ext.get("equipment_info", {})
    eq_type = (equip_info.get("equipment_type") or "").lower()
    eq_mfr = (equip_info.get("manufacturer") or "").lower()
    eq_model = (equip_info.get("model") or "").lower()
    doc_supplier = (kd.get("supplier_name") or "").lower()
    summary = (ext.get("summary") or "").lower()

    score = _score_word_matches(q_lower, [eq_type, eq_mfr, eq_model, summary, doc_supplier])
    score += _score_equipment_match(eq_lower, eq_type)
    score += _score_supplier_match(sup_lower, eq_mfr, doc_supplier)
    for field in ("common_faults", "troubleshooting_tips", "spare_parts", "maintenance_schedule"):
        if ext.get(field):
            score += 1
    return score


def _build_doc_context(kd: dict) -> tuple[dict, str]:
    """Build a source reference and context text from a knowledge document."""
    ext = kd.get("extraction", {})
    equip_info = ext.get("equipment_info", {})
    source_name = f"{kd.get('supplier_name', '')} {equip_info.get('model', '')}".strip() or kd.get("filename", "Document")

    source = {
        "filename": kd.get("filename", ""),
        "supplier": kd.get("supplier_name", ""),
        "equipment": f"{equip_info.get('manufacturer', '')} {equip_info.get('model', '')}".strip(),
        "type": equip_info.get("equipment_type", ""),
    }

    parts = [f"\n[Source: {source_name}]"]
    parts.append(f"Equipment: {equip_info.get('manufacturer', '')} {equip_info.get('model', '')} ({equip_info.get('equipment_type', '')})")
    if ext.get("summary"):
        parts.append(f"Summary: {ext['summary']}")
    _append_list_section(parts, ext, "common_faults", "Known faults",
        lambda f: f"  - {f.get('fault','')}: {f.get('symptoms','')} -> Fix: {f.get('fix','')} (Severity: {f.get('severity','N/A')})")
    _append_list_section(parts, ext, "troubleshooting_tips", "Troubleshooting", lambda t: f"  - {t}")
    _append_list_section(parts, ext, "spare_parts", "Spare parts",
        lambda p: f"  - {p.get('part','')}: Part# {p.get('part_number','')}")
    _append_list_section(parts, ext, "maintenance_schedule", "Maintenance schedule",
        lambda m: f"  - {m.get('task','')}: {m.get('frequency','')}")
    _append_list_section(parts, ext, "safety_warnings", "Safety warnings", lambda w: f"  - {w}")
    if ext.get("key_specifications"):
        parts.append(f"Key specs: {', '.join(ext['key_specifications'])}")
    return source, "\n".join(parts)


def _append_list_section(parts: list, ext: dict, key: str, header: str, fmt) -> None:
    """Append a formatted list section to context parts if the key exists."""
    items = ext.get(key)
    if items:
        parts.append(f"{header}:")
        for item in items:
            parts.append(fmt(item))


_DOC_QA_SYSTEM_MSG = """You are an expert gym equipment technician answering questions using uploaded equipment documentation.
Always cite your source document when providing information. If the documents don't contain the answer, say so honestly.
Format your answers clearly with bullet points and bold key information. Include part numbers when available."""


async def _search_and_rank_docs(org_id: str | None, question: str, equipment_type: str, supplier: str) -> tuple[list, list]:
    """Search documents, score relevance, return (sources, context_parts)."""
    org_query: dict = {"$or": [{"organization_id": None}]}
    if org_id:
        org_query["$or"].append({"organization_id": org_id})

    all_docs = await db.equipment_knowledge.find(org_query, {"_id": 0}).to_list(100)
    if not all_docs:
        return [], []

    q_lower, eq_lower, sup_lower = question.lower(), (equipment_type or "").lower(), (supplier or "").lower()
    scored = [(s, kd) for kd in all_docs if (s := _score_document(kd, q_lower, eq_lower, sup_lower)) > 0]
    if not scored:
        scored = [(1, kd) for kd in all_docs[:10]]
    scored.sort(key=lambda x: x[0], reverse=True)

    sources, context_parts = [], []
    for _, kd in scored[:6]:
        source, text = _build_doc_context(kd)
        sources.append(source)
        context_parts.append(text)
    return sources, context_parts


@router.post("/documents/ask")
async def ask_documents(body: DocumentQuestion, user: dict = Depends(require_ai_access)):
    """AI-powered Q&A over uploaded equipment documents."""
    sources, context_parts = await _search_and_rank_docs(
        user.get("organization_id"), body.question, body.equipment_type, body.supplier,
    )
    if not sources:
        return {"answer": "No documents have been uploaded yet. Upload equipment manuals to enable document Q&A.", "sources": []}

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"doc_qa_{user['id']}_{datetime.now(timezone.utc).timestamp()}",
            system_message=_DOC_QA_SYSTEM_MSG,
        ).with_model("openai", "gpt-5.2")

        answer = await chat.send_message(UserMessage(text=(
            f"Based on the following equipment documentation, answer this question:\n\n"
            f"QUESTION: {body.question}\n\nDOCUMENTATION:\n{'---'.join(context_parts)}\n\n"
            f"Provide a clear, actionable answer citing the specific source document(s)."
        )))
        return {"answer": answer, "sources": sources, "documents_searched": len(sources)}
    except Exception as e:
        logger.error(f"Document Q&A failed: {e}")
        raise HTTPException(status_code=500, detail="AI query failed")
