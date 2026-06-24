"""AI onboarding assistant (GPT-4o via Emergent universal key).

ADVISORY ONLY — every endpoint returns *suggestions*. The assistant never
imports, maps, overwrites, merges or deletes anything itself; the human
applies suggestions through the existing approval-gated flows.
"""
import json
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db
from routes.pulse_master_admin import _require_pulse_or_master
from routes.onboarding_import import TYPE_REGISTRY

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

_MODEL = "gpt-4o"


def _key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise HTTPException(status_code=503, detail="AI assistant is not configured (missing key).")
    return k


async def _ask_json(system: str, prompt: str) -> dict:
    """One-shot GPT-4o call that must return a JSON object."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=_key(), session_id=f"onb-ai-{uuid.uuid4()}", system_message=system).with_model("openai", _MODEL)
    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("onboarding AI call failed")
        raise HTTPException(status_code=502, detail=f"AI request failed: {e}")
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().strip("`").strip()
    try:
        return json.loads(text)
    except Exception:
        # best-effort: extract first {...}
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        raise HTTPException(status_code=502, detail="AI returned an unparseable response.")


# ── Analyse a spreadsheet ────────────────────────────────────────────────

class AiAnalyzeBody(BaseModel):
    columns: list
    sample_rows: list           # list of {column: value}


@router.post("/onboarding/import/ai-analyze")
async def ai_analyze(body: AiAnalyzeBody, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    catalog = {
        t: {"label": s["label"], "fields": [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in s["fields"]]}
        for t, s in TYPE_REGISTRY.items()
    }
    system = (
        "You are an onboarding data-import assistant. You analyse a CSV's columns and sample rows "
        "and recommend (1) which import type it is, (2) how to map columns to that type's fields, and "
        "(3) data-quality issues. You ONLY advise — you never import data. Respond with STRICT JSON only."
    )
    prompt = (
        f"Available import types and their fields (JSON):\n{json.dumps(catalog)}\n\n"
        f"CSV columns: {json.dumps(body.columns)}\n"
        f"Sample rows (up to 5): {json.dumps(body.sample_rows[:5])}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "suggested_type": "<one of the type ids or empty>",\n'
        '  "confidence": "high|medium|low",\n'
        '  "mapping": {"<field_key>": "<csv column name>"},\n'
        '  "issues": [{"severity": "error|warning", "message": "..."}],\n'
        '  "cleanup_suggestions": ["..."],\n'
        '  "notes": "one short sentence"\n'
        "}\n"
        "Only map fields you are confident about. Flag missing required fields, malformed emails/phones, "
        "and likely duplicates in the sample."
    )
    result = await _ask_json(system, prompt)
    # guard: only allow known types/fields through
    st = result.get("suggested_type")
    if st and st not in TYPE_REGISTRY:
        result["suggested_type"] = ""
    if st in TYPE_REGISTRY and isinstance(result.get("mapping"), dict):
        valid_fields = {f["key"] for f in TYPE_REGISTRY[st]["fields"]}
        valid_cols = set(body.columns)
        result["mapping"] = {k: v for k, v in result["mapping"].items() if k in valid_fields and v in valid_cols}
    result["advisory"] = True
    return result


# ── Summarise project progress ───────────────────────────────────────────

@router.post("/onboarding/projects/{project_id}/ai-summary")
async def ai_summary(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    proj = await db.onboarding_projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    checklist = [{"label": s["label"], "status": s["status"], "optional": s.get("optional"), "group": s.get("group")} for s in proj.get("checklist", [])]
    snapshot = {
        "customer_name": proj.get("customer_name"),
        "customer_type": proj.get("customer_type"),
        "modules": proj.get("modules"),
        "go_live_target": proj.get("go_live_target"),
        "checklist": checklist,
        "profile_filled": [k for k, v in (proj.get("profile") or {}).items() if v],
    }
    system = (
        "You are an onboarding success manager. Given a customer's onboarding state, write a concise, "
        "practical status. You ONLY advise. Respond with STRICT JSON only."
    )
    prompt = (
        f"Onboarding snapshot (JSON):\n{json.dumps(snapshot)}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "summary": "2-3 sentence plain-English status",\n'
        '  "risks": ["..."],\n'
        '  "next_best_actions": ["specific next step", "..."],\n'
        '  "missing_info": ["..."],\n'
        '  "go_live_ready": true|false\n'
        "}\n"
    )
    result = await _ask_json(system, prompt)
    result["advisory"] = True
    return result
