"""Org Chart AI assistant (Phase 2).

Single-turn, structured (JSON) LLM helpers powered by the Emergent LLM
key. The AI never mutates the chart directly — it returns proposals the
manager reviews and applies via the normal import / edit endpoints.

  POST /staffing/orgchart/charts/{cid}/ai/generate   — parse a pasted staff list → rows
  POST /staffing/orgchart/charts/{cid}/ai/analyze    — gaps / circular lines / overload
  POST /staffing/orgchart/charts/{cid}/ai/draft-jd   — draft a job description for a role
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db, EMERGENT_LLM_KEY
from utils.ai_guardrails import sanitize_prompt
from routes.staffing import _org, _require_manager

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_PROVIDER, MODEL_NAME = "anthropic", "claude-sonnet-4-6"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ask_json(system: str, prompt: str) -> dict | list:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI is not configured")
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=str(uuid.uuid4()),
        system_message=system,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)
    raw = (await llm.send_message(UserMessage(text=prompt))).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
        if m:
            return json.loads(m.group(1))
        raise HTTPException(502, "AI returned an unparseable response")


async def _chart_or_404(cid: str, org_id: str):
    c = await db.org_charts.find_one({"id": cid, "organization_id": org_id}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(404, "Org chart not found")


# ───────────────────────── generate from text ─────────────────────────

class GenerateRequest(BaseModel):
    text: str


@router.post("/staffing/orgchart/charts/{cid}/ai/generate")
async def ai_generate(cid: str, body: GenerateRequest, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _chart_or_404(cid, org_id)
    text = sanitize_prompt(body.text, max_chars=12000)
    if not text.strip():
        raise HTTPException(400, "Paste a staff list to generate from")
    rows = await _rows_from_text(text)
    return {"rows": rows, "count": len(rows)}


_ROWS_SYSTEM = (
    "You convert a free-text staff list into a structured org chart. "
    "Return ONLY valid JSON, no markdown. Schema: a JSON array of objects with keys: "
    "full_name (string), job_title (string|null), department (string|null), "
    "manager_name (string|null, must exactly match another row's full_name), "
    "email (string|null), vacancy (\"yes\"|\"no\"). Infer reporting lines and departments "
    "sensibly for a fitness business. Mark clearly-empty/open roles as vacancy=yes."
)


def _clean_rows(data) -> list[dict]:
    rows = data if isinstance(data, list) else (data.get("rows") if isinstance(data, dict) else [])
    out = []
    for r in (rows or [])[:600]:
        if not isinstance(r, dict) or not (r.get("full_name") or "").strip():
            continue
        out.append({
            "full_name": str(r.get("full_name")).strip()[:120],
            "job_title": (r.get("job_title") or None),
            "department": (r.get("department") or None),
            "manager_name": (r.get("manager_name") or None),
            "email": (r.get("email") or None),
            "vacancy": "yes" if str(r.get("vacancy")).lower() in ("yes", "true", "1") else "no",
        })
    return out


async def _rows_from_text(text: str) -> list[dict]:
    data = await _ask_json(_ROWS_SYSTEM, f"Build the org-chart rows from this staff list:\n\n{text}")
    return _clean_rows(data)


# ───────────────────────── analyse structure ─────────────────────────

@router.post("/staffing/orgchart/charts/{cid}/ai/analyze")
async def ai_analyze(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _chart_or_404(cid, org_id)
    nodes = await db.org_chart_nodes.find({"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    if not nodes:
        raise HTTPException(400, "Add some cards before running analysis")
    by_id = {n["id"]: n for n in nodes}
    compact = [{
        "name": n.get("full_name"), "title": n.get("job_title"),
        "department": n.get("department"), "type": n.get("type"),
        "manager": (by_id.get(n.get("manager_node_id")) or {}).get("full_name"),
    } for n in nodes]
    system = (
        "You are an org-design advisor for a fitness business. Analyse the structure and "
        "return ONLY valid JSON, no markdown. Schema: {\"summary\": string (2-3 sentences), "
        "\"issues\": [{\"type\": one of [\"gap\",\"circular\",\"overload\",\"orphan\",\"duplicate\"], "
        "\"severity\": one of [\"low\",\"medium\",\"high\"], \"detail\": string}], "
        "\"suggestions\": [string]}. Flag people with no manager, managers with too many reports (>8), "
        "departments without a clear lead, likely duplicates, and any circular reporting."
    )
    prompt = "Analyse this org chart:\n\n" + json.dumps(compact, ensure_ascii=False)
    data = await _ask_json(system, prompt)
    return {
        "summary": data.get("summary", "") if isinstance(data, dict) else "",
        "issues": (data.get("issues") or [])[:30] if isinstance(data, dict) else [],
        "suggestions": (data.get("suggestions") or [])[:15] if isinstance(data, dict) else [],
    }


# ───────────────────────── draft a job description ─────────────────────────

class DraftJDRequest(BaseModel):
    node_id: str | None = None
    title: str | None = None
    department: str | None = None


@router.post("/staffing/orgchart/charts/{cid}/ai/draft-jd")
async def ai_draft_jd(cid: str, body: DraftJDRequest, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _chart_or_404(cid, org_id)
    title, dept = body.title, body.department
    if body.node_id:
        node = await db.org_chart_nodes.find_one({"id": body.node_id, "chart_id": cid, "organization_id": org_id}, {"_id": 0})
        if node:
            title = title or node.get("job_title") or node.get("full_name")
            dept = dept or node.get("department")
    if not (title or "").strip():
        raise HTTPException(400, "A role title is required")
    system = (
        "You are an HR specialist for a fitness business. Draft a concise, professional job "
        "description. Return ONLY valid JSON, no markdown. Schema: {\"title\": string, "
        "\"summary\": string, \"responsibilities\": [string], \"requirements\": [string], "
        "\"nice_to_have\": [string]}."
    )
    prompt = f"Draft a job description for the role: {sanitize_prompt(title, max_chars=200)}"
    if dept:
        prompt += f" in the {sanitize_prompt(dept, max_chars=120)} department"
    data = await _ask_json(system, prompt)
    if not isinstance(data, dict):
        raise HTTPException(502, "AI returned an unexpected response")
    return data


# ───────────────────────── import an existing org chart (PDF / image) ─────────────────────────

_VISION_SYSTEM = (
    "You read an ORGANISATION CHART from image(s) and convert it into structured data. "
    "Return ONLY valid JSON, no markdown — a JSON array of objects with keys: "
    "full_name (the person's name in the box; if the box only shows a job title and no name, "
    "use the job title as full_name), job_title (string|null), department (string|null — infer "
    "from section headers or colour groupings if shown), manager_name (string|null — the EXACT "
    "full_name of the box directly connected ABOVE this one in the hierarchy), vacancy "
    "(\"yes\" if the box is clearly an empty/open/TBC/vacant role, else \"no\"). "
    "Work top-to-bottom, follow the connecting lines carefully to set manager_name, and include "
    "EVERY box you can read. If two boxes share a title, keep them as separate rows."
)

_PDF_TEXT_MIN = 140          # below this we treat the PDF as image-only and use vision
_MAX_FILE_BYTES = 25 * 1024 * 1024


def _pdf_text(data: bytes) -> str:
    import fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        parts = [p.get_text("text") for p in doc]
        doc.close()
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _pdf_to_images(data: bytes, dpi: int = 200, max_pages: int = 6) -> list[str]:
    import base64 as _b64
    import fitz
    out = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for page in doc:
            if len(out) >= max_pages:
                break
            pix = page.get_pixmap(matrix=mat, alpha=False)
            out.append(_b64.b64encode(pix.tobytes("png")).decode("ascii"))
        doc.close()
    except Exception as e:
        raise HTTPException(400, f"Could not read the PDF: {e}")
    return out


@router.post("/staffing/orgchart/charts/{cid}/import/document")
async def import_document(
    cid: str,
    file: UploadFile | None = File(None),
    file_url: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """Kick off conversion of an EXISTING org chart (PDF / PNG / JPG) into
    reviewable rows. Vision OCR can take >60s on dense charts, which exceeds
    the ingress timeout — so we run it as a background job and the client
    polls :func:`import_document_status`.
    """
    _require_manager(user)
    org_id = _org(user)
    await _chart_or_404(cid, org_id)

    data, filename = None, "upload"
    if file is not None:
        data = await file.read()
        filename = file.filename or "upload"
    elif file_url:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(file_url)
            if r.status_code != 200:
                raise HTTPException(400, "Could not download that file")
            data = r.content
            filename = file_url.split("?")[0].rsplit("/", 1)[-1] or "upload"
    if not data:
        raise HTTPException(400, "Upload a file or provide file_url")
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(400, "File too large (max 25MB)")

    job_id = str(uuid.uuid4())
    await db.org_chart_import_jobs.insert_one({
        "id": job_id, "chart_id": cid, "organization_id": org_id,
        "status": "processing", "filename": filename, "rows": [], "count": 0,
        "source": None, "error": None,
        "created_at": _now_iso(), "updated_at": _now_iso(),
    })
    asyncio.create_task(_process_import_job(job_id, cid, org_id, data, filename))
    return {"job_id": job_id, "status": "processing", "filename": filename}


@router.get("/staffing/orgchart/charts/{cid}/import/document/{job_id}")
async def import_document_status(cid: str, job_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    job = await db.org_chart_import_jobs.find_one(
        {"id": job_id, "chart_id": cid, "organization_id": org_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Import job not found")
    return job


async def _process_import_job(job_id: str, cid: str, org_id: str, data: bytes, filename: str):
    # Run the whole extraction (fitz + the blocking litellm.completion call) in a
    # worker thread so the event loop stays free — this lets the POST response
    # flush immediately and keeps the poll endpoint responsive. Only Mongo
    # writes (motor, bound to the main loop) happen back here.
    try:
        rows, source = await asyncio.to_thread(_extract_rows_sync, data, filename)
        await db.org_chart_import_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "done", "rows": rows, "count": len(rows),
                      "source": source, "updated_at": _now_iso()}})
    except Exception as e:  # noqa: BLE001
        logger.exception("orgchart import job failed")
        detail = e.detail if isinstance(e, HTTPException) else "Could not read that chart"
        await db.org_chart_import_jobs.update_one(
            {"id": job_id}, {"$set": {"status": "error", "error": str(detail), "updated_at": _now_iso()}})


def _llm_json_sync(system_message: str, prompt_text: str, images_b64: list[str] | None = None):
    """Synchronous structured LLM call — safe to run inside ``asyncio.to_thread``.

    ``emergentintegrations`` wraps the *blocking* ``litellm.completion`` inside an
    ``async`` method, so we drive it with a fresh ``asyncio.run`` in this worker
    thread; the blocking call then only stalls this thread, never the main loop.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI is not configured")
    llm = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=str(uuid.uuid4()),
                  system_message=system_message).with_model(MODEL_PROVIDER, MODEL_NAME)
    fc = [ImageContent(image_base64=b) for b in (images_b64 or [])[:6]]
    msg = UserMessage(text=prompt_text, file_contents=fc) if fc else UserMessage(text=prompt_text)
    raw = asyncio.run(llm.send_message(msg)).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        if not m:
            raise HTTPException(502, "Could not read a chart from that file")
        return json.loads(m.group(1))


def _extract_rows_sync(data: bytes, filename: str) -> tuple[list[dict], str]:
    """Fully synchronous extraction pipeline — runs in a worker thread."""
    import base64 as _b64
    is_pdf = filename.lower().endswith(".pdf") or data[:5] == b"%PDF-"
    if is_pdf:
        text = _pdf_text(data)
        if len(text) >= _PDF_TEXT_MIN:
            data_json = _llm_json_sync(_ROWS_SYSTEM, f"Build the org-chart rows from this staff list:\n\n{sanitize_prompt(text, max_chars=16000)}")
            return _clean_rows(data_json), "text"
        images = _pdf_to_images(data)
        return _clean_rows(_llm_json_sync(_VISION_SYSTEM, "Extract the full organisation chart from the attached page image(s) as JSON rows.", images)), "vision"
    b = _b64.b64encode(data).decode("ascii")
    return _clean_rows(_llm_json_sync(_VISION_SYSTEM, "Extract the full organisation chart from the attached image as JSON rows.", [b])), "vision"
