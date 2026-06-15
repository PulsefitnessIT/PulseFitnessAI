"""Org Chart AI assistant (Phase 2).

Single-turn, structured (JSON) LLM helpers powered by the Emergent LLM
key. The AI never mutates the chart directly — it returns proposals the
manager reviews and applies via the normal import / edit endpoints.

  POST /staffing/orgchart/charts/{cid}/ai/generate   — parse a pasted staff list → rows
  POST /staffing/orgchart/charts/{cid}/ai/analyze    — gaps / circular lines / overload
  POST /staffing/orgchart/charts/{cid}/ai/draft-jd   — draft a job description for a role
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db, EMERGENT_LLM_KEY
from utils.ai_guardrails import sanitize_prompt
from routes.staffing import _org, _require_manager

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_PROVIDER, MODEL_NAME = "anthropic", "claude-sonnet-4-6"


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
    system = (
        "You convert a free-text staff list into a structured org chart. "
        "Return ONLY valid JSON, no markdown. Schema: a JSON array of objects with keys: "
        "full_name (string), job_title (string|null), department (string|null), "
        "manager_name (string|null, must exactly match another row's full_name), "
        "email (string|null), vacancy (\"yes\"|\"no\"). Infer reporting lines and departments "
        "sensibly for a fitness business. Mark clearly-empty/open roles as vacancy=yes."
    )
    prompt = f"Build the org-chart rows from this staff list:\n\n{text}"
    data = await _ask_json(system, prompt)
    rows = data if isinstance(data, list) else data.get("rows", [])
    clean = []
    for r in rows[:300]:
        if not isinstance(r, dict) or not (r.get("full_name") or "").strip():
            continue
        clean.append({
            "full_name": str(r.get("full_name")).strip(),
            "job_title": r.get("job_title"),
            "department": r.get("department"),
            "manager_name": r.get("manager_name"),
            "email": r.get("email"),
            "vacancy": "yes" if str(r.get("vacancy")).lower() in ("yes", "true", "1") else "no",
        })
    return {"rows": clean, "count": len(clean)}


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
