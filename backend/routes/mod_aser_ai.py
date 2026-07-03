"""ASER AI assistance (MOD-only).

Generates review-ready summaries for a single ASER entry and drafts
CAPEX / replacement-evidence wording for an asset (aggregating its ASER +
fault history). Uses the app's existing LLM (Emergent LLM key, openai
gpt-5.2). Guardrails: never closes entries, never makes clinical judgements,
never identifies patients, never guarantees funding — output is always
labelled "AI-generated for review".
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db, EMERGENT_LLM_KEY
from routes.mod_aser import (
    _require_mod, _sites_in_scope, _load_settings, REMOVAL_FLAG_STATUSES, EVENT_TYPES,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["MOD ASER AI"])

_EVENT_LABELS = {k: v for k, v in EVENT_TYPES}

_SYSTEM = (
    "You are an equipment-safety analyst for MOD (Ministry of Defence) rehabilitation "
    "and physical-training facilities. You summarise ASER (Activity Safety Events Register) "
    "data about fitness / PTE equipment and its impact on rehab and activity delivery. "
    "Rules: be concise, factual and professional; use British English; NEVER identify or infer "
    "patients or clinical details; NEVER make clinical judgements; NEVER guarantee funding or "
    "replacement approval; base statements only on the data provided. Write for a site manager "
    "or account manager audience."
)


async def _ensure_ai_enabled(user: dict):
    org = await _require_mod(user)
    settings = await _load_settings()
    if not settings.get("ai_summaries", True):
        raise HTTPException(403, "AI summaries are disabled by the platform administrator")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI is not configured")
    return org


async def _run_llm(session_id: str, prompt: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=_SYSTEM).with_model("openai", "gpt-5.2")
    resp = await chat.send_message(UserMessage(text=prompt))
    return (resp or "").strip()


@router.post("/mod/aser/{entry_id}/ai-summary")
async def ai_entry_summary(entry_id: str, user: dict = Depends(get_current_user)):
    await _ensure_ai_enabled(user)
    site_ids = await _sites_in_scope(user, await _require_mod(user))
    e = await db.aser_entries.find_one({"id": entry_id, "site_id": {"$in": site_ids}}, {"_id": 0})
    if not e:
        raise HTTPException(404, "ASER entry not found")

    ai = e.get("activity_impact") or {}
    si = e.get("safety_impact") or {}
    r = e.get("risk") or {}
    snap = e.get("equipment_snapshot") or {}
    rep = e.get("repeated_issue") or {}
    prompt = (
        "Summarise this ASER entry in 3-4 sentences for a manager review, then give one line "
        "'Suggested next step'. Do not invent facts.\n\n"
        f"Equipment: {snap.get('name')} ({snap.get('equipment_type')}), serial {snap.get('serial_number')}.\n"
        f"Event type: {_EVENT_LABELS.get(e.get('event_type'))}.\n"
        f"Title: {e.get('title')}.\n"
        f"Description: {e.get('description')}.\n"
        f"Immediate action: {e.get('immediate_action') or 'none recorded'}.\n"
        f"Risk: rating={r.get('rating')}, potential severity={r.get('potential_severity')}, likelihood={r.get('likelihood')}.\n"
        f"Rehab impact: rehab={ai.get('impacted_rehab')}, group programme={ai.get('impacted_group')}, "
        f"individual programme={ai.get('impacted_individual')}, sessions affected={ai.get('sessions_affected')}, "
        f"patients affected={ai.get('patients_affected')}.\n"
        f"Safety: injured={si.get('anyone_injured')}, near miss={si.get('near_miss')}, removed from use={si.get('equipment_removed')}.\n"
        f"Equipment status: {e.get('equipment_status')}. Repeated-issue assessment: {rep.get('label')} "
        f"({rep.get('aser_90d', 0)} ASER in 90 days, {rep.get('faults_180d', 0)} faults in 6 months).\n"
    )
    try:
        summary = await _run_llm(f"aser_entry_{entry_id}", prompt)
    except Exception as ex:
        logger.warning("ASER AI entry summary failed: %s", ex)
        raise HTTPException(502, "AI summary could not be generated right now")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.aser_entries.update_one(
        {"id": entry_id}, {"$set": {"ai_summary": summary, "ai_summary_at": now_iso}})
    return {"summary": summary, "generated_at": now_iso, "disclaimer": "AI-generated summary for review."}


@router.post("/mod/aser/ai/asset-evidence/{equipment_id}")
async def ai_asset_evidence(equipment_id: str, user: dict = Depends(get_current_user)):
    """Draft CAPEX / replacement-evidence wording for an asset. Stores the
    result on the equipment record so it can be embedded in the Replacement
    Evidence Report PDF and email."""
    await _ensure_ai_enabled(user)
    site_ids = await _sites_in_scope(user, await _require_mod(user))
    equipment = await db.equipment.find_one(
        {"id": equipment_id, "organization_id": {"$in": site_ids}}, {"_id": 0})
    if not equipment:
        raise HTTPException(404, "Equipment not found in your permitted scope")

    entries = await db.aser_entries.find({"equipment_id": equipment_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    total_faults = await db.issues.count_documents({"equipment_id": equipment_id, "is_drill": {"$ne": True}})
    high = sum(1 for e in entries if (e.get("risk") or {}).get("rating") in ("high", "critical"))
    removed = sum(1 for e in entries if e.get("equipment_status") in REMOVAL_FLAG_STATUSES)
    near_miss = sum(1 for e in entries if (e.get("safety_impact") or {}).get("near_miss"))
    sessions = sum((e.get("activity_impact") or {}).get("sessions_affected", 0) or 0 for e in entries)
    groups = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_group"))
    individuals = sum(1 for e in entries if (e.get("activity_impact") or {}).get("impacted_individual"))
    install = equipment.get("install_date") or equipment.get("installed_at") or equipment.get("created_at")
    age = "unknown"
    try:
        if install:
            d = datetime.fromisoformat(str(install).replace("Z", "+00:00"))
            age = f"{(datetime.now(timezone.utc) - d).days // 365} years"
    except Exception:
        pass

    prompt = (
        "Write a short executive summary (4-6 sentences) supporting a CAPEX / replacement review "
        "for this equipment, based ONLY on the data below. State the evidence plainly (failures, "
        "safety events, delivery impact) and end with a clear recommendation. Do not guarantee funding.\n\n"
        f"Equipment: {equipment.get('name')} ({equipment.get('machine_type') or equipment.get('category')}), "
        f"serial {equipment.get('serial_number')}, age {age}.\n"
        f"Total ASER events: {len(entries)}. High/critical events: {high}. Times removed from use: {removed}. "
        f"Near-misses: {near_miss}. Total faults logged: {total_faults}.\n"
        f"Rehab sessions impacted: {sessions}. Group programmes impacted: {groups}. "
        f"Individual programmes impacted: {individuals}.\n"
        f"Recent event titles: {'; '.join((e.get('title') or '') for e in entries[:6]) or 'none'}.\n"
    )
    try:
        summary = await _run_llm(f"aser_asset_{equipment_id}", prompt)
    except Exception as ex:
        logger.warning("ASER AI asset evidence failed: %s", ex)
        raise HTTPException(502, "AI evidence could not be generated right now")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.equipment.update_one(
        {"id": equipment_id},
        {"$set": {"aser_ai_summary": summary, "aser_ai_summary_at": now_iso, "aser_ai_summary_by": user.get("email")}})
    return {"summary": summary, "generated_at": now_iso,
            "disclaimer": "AI-generated summary for review.",
            "stats": {"aser_events": len(entries), "high_critical": high, "removed": removed,
                      "faults": total_faults, "sessions_impacted": sessions}}
