"""
GymAxis Service Operations — AI Assistant Layer.

Iter 215ds (Phase 5).

Four endpoints, all powered by Claude Sonnet 4.5 via the Emergent LLM key:

  POST /api/svc/ai/triage
       body: {description, site_name?, asset_name?, customer_name?}
       returns {priority, fault_code, likely_parts: [{sku, name, reason}],
                rationale, confidence}
       <2s p95.

  POST /api/svc/ai/photo/classify
       body: {photo_id?, image_base64?}
       returns {tags, severity, summary}

  POST /api/svc/ai/summarise/{case_id}
       returns {customer_summary, engineer_summary}

  POST /api/svc/ai/scheduler-tiebreak
       body: {case_id, candidate_engineer_ids: [str]}
       returns {chosen_engineer_id, reasoning}
       Used by the scheduler after the heuristic when 2+ engineers are
       within 10 score points of each other.

Robustness:
  • Every Claude call has a strict JSON schema; if the model deviates we
    return `{ok: false, raw: ...}` with status 200 so the UI can fall
    back to manual operator entry.
  • Every call is logged in `svc_ai_calls` with prompt/response sizes
    and latency for observability.
"""
__integration_fields__ = {
    # AI outputs feed downstream Sicon/Sage payloads but the AI layer
    # itself is GymAxis-internal — Claude calls + observability logs only.
    # svc_ai_calls (observability)
    "ai_calls.id":              "gymaxis_only: local uuid",
    "ai_calls.organization_id": "gymaxis_only: tenant scoping",
    "ai_calls.kind":            "gymaxis_only: triage|photo_classify|summary|tiebreak",
    "ai_calls.prompt_chars":    "gymaxis_only: prompt size for cost telemetry",
    "ai_calls.response_chars":  "gymaxis_only: response size for cost telemetry",
    "ai_calls.latency_ms":      "gymaxis_only: p50/p95 dashboard input",
    "ai_calls.ok":              "gymaxis_only: success rate dashboard input",
    "ai_calls.at":              "gymaxis_only: timestamp",
    # Triage output (consumed by intake.py → forwarded to Sicon)
    "triage.priority":          "sicon: PriorityID (PRIORITY_CROSSWALK) · GymAxis → Sicon (via case)",
    "triage.fault_code":        "sicon: FaultCode · GymAxis → Sicon (via case)",
    "triage.likely_parts":      "sicon: AllocatedParts[] suggestion · gymaxis_only until operator confirms",
    "triage.rationale":         "gymaxis_only: operator UX",
    "triage.confidence":        "gymaxis_only: operator UX",
    # Photo classify output (persisted on svc_engineer_photos.ai)
    "photo.tags":               "sicon: AttachmentTags[] · GymAxis → Sicon (when push_attachment runs)",
    "photo.severity":           "gymaxis_only: operator UX",
    "photo.summary":            "sicon: AttachmentDescription · GymAxis → Sicon",
    # Summarisation output (consumed by comms.py → email body)
    "summary.customer_summary": "gymaxis_only: customer-facing email body",
    "summary.engineer_summary": "sicon: TrackingNote (when written to timeline) · GymAxis → Sicon",
    # Tie-break output (consumed by scheduler.py)
    "tiebreak.chosen_engineer_id": "sicon: AppointmentResourceID · GymAxis → Sicon (via assign)",
    "tiebreak.reasoning":          "gymaxis_only: operator UX",
}

from datetime import datetime, timezone
from typing import Any, Optional
import base64
import json
import logging
import os
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from utils.auth import get_current_user
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/ai", tags=["Service Ops · AI Assistant"])


CLAUDE_MODEL = ("anthropic", "claude-sonnet-4-5-20250929")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def _key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY") or ""
    if not k:
        raise HTTPException(503, "AI service not configured (EMERGENT_LLM_KEY missing)")
    return k


async def _log_call(*, organization_id: str, kind: str, prompt_chars: int,
                    response_chars: int, latency_ms: int, ok: bool,
                    extra: dict | None = None) -> None:
    try:
        await db.svc_ai_calls.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "kind": kind,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "latency_ms": latency_ms,
            "ok": ok,
            "extra": extra or {},
            "at": _now(),
        })
    except Exception as e:
        logger.warning("ai call log failed: %s", e)


async def _chat(*, system: str, user_text: str,
                images: list[ImageContent] | None = None,
                session_id: str | None = None) -> str:
    """Wrap the emergentintegrations chat with our model + key."""
    chat = LlmChat(
        api_key=_key(),
        session_id=session_id or f"svc-ai-{uuid.uuid4()}",
        system_message=system,
    ).with_model(*CLAUDE_MODEL)
    msg = UserMessage(text=user_text, file_contents=images) if images else UserMessage(text=user_text)
    return await chat.send_message(msg)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction — Claude usually returns clean JSON
    when prompted, but occasionally wraps it in ```json fences."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        # Strip first fence + closing fence.
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        # Drop the language tag if present (e.g., "json").
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    try:
        return json.loads(s)
    except Exception:
        # Try to find the first {...} blob.
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start: end + 1])
            except Exception:
                return None
    return None


# ─────────────────────────────────────────────────────────────────
# 1. Intake triage
# ─────────────────────────────────────────────────────────────────

_TRIAGE_SYSTEM = """You are GymAxis Service Ops triage assistant.
You are advising a UK service desk operator who is logging a maintenance
case for commercial gym equipment (treadmills, bikes, ellipticals,
strength kit). Be concise and decisive.

Rules:
- Output STRICT JSON only. No prose, no markdown fences.
- Choose ONE priority: p1 (critical, safety/down site), p2 (high impact,
  same-day fix needed), p3 (standard, within SLA), p4 (cosmetic / can wait).
- fault_code is a short kebab-case slug like "belt-fray", "console-fault",
  "drive-motor-fail". Use a stable taxonomy.
- likely_parts: 1-4 entries; each {sku, name, reason}. If unsure of the
  sku, use a recognisable family code (e.g. "BELT-95TI") plus the name.
- rationale: ≤ 200 chars, plain English.
- confidence: 0.0-1.0.

Schema:
{
  "priority": "p1|p2|p3|p4",
  "fault_code": "string",
  "likely_parts": [{"sku":"string","name":"string","reason":"string"}],
  "rationale": "string",
  "confidence": 0.0
}
"""


@router.post("/triage")
async def triage(data: dict, user=Depends(get_current_user)):
    description = ((data or {}).get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description required")
    of = _of(user)
    context_lines = [f"Fault description: {description}"]
    for k in ("site_name", "asset_name", "customer_name"):
        v = (data or {}).get(k)
        if v:
            context_lines.append(f"{k.replace('_', ' ').title()}: {v}")
    user_text = "\n".join(context_lines)

    # Surface the existing parts catalogue so Claude can pick real SKUs
    # rather than hallucinate. Cap at 60 entries to keep latency low.
    catalogue = await db.svc_parts.find(
        {**of, "active": {"$ne": False}},
        {"_id": 0, "sku": 1, "name": 1, "manufacturer": 1},
    ).limit(60).to_list(60)
    if catalogue:
        user_text += "\n\nKnown parts catalogue (pick from these when matched):\n"
        user_text += "\n".join(f"- {p['sku']}: {p['name']}" for p in catalogue)

    t0 = time.monotonic()
    try:
        raw = await _chat(system=_TRIAGE_SYSTEM, user_text=user_text)
    except Exception as e:
        logger.warning("triage chat failed: %s", e)
        await _log_call(organization_id=of["organization_id"], kind="triage",
                        prompt_chars=len(user_text), response_chars=0,
                        latency_ms=int((time.monotonic() - t0) * 1000), ok=False,
                        extra={"error": str(e)[:200]})
        return {"ok": False, "error": "AI service unavailable"}
    latency = int((time.monotonic() - t0) * 1000)
    parsed = _extract_json(raw)
    ok = isinstance(parsed, dict) and parsed.get("priority") in ("p1", "p2", "p3", "p4")
    await _log_call(organization_id=of["organization_id"], kind="triage",
                    prompt_chars=len(user_text), response_chars=len(raw or ""),
                    latency_ms=latency, ok=ok)
    if not ok:
        return {"ok": False, "raw": raw}
    return {
        "ok": True,
        "priority": parsed.get("priority"),
        "fault_code": parsed.get("fault_code") or "",
        "likely_parts": parsed.get("likely_parts") or [],
        "rationale": parsed.get("rationale") or "",
        "confidence": float(parsed.get("confidence") or 0),
        "latency_ms": latency,
    }


# ─────────────────────────────────────────────────────────────────
# 2. Photo classification
# ─────────────────────────────────────────────────────────────────

_PHOTO_SYSTEM = """You are GymAxis Service Ops vision assistant.
You inspect photos taken by field engineers on commercial gym equipment.
Identify visible issues — wear, damage, leaks, electrical faults, fluid
or rust. Be concise.

Rules:
- Output STRICT JSON. No prose.
- tags: 2-6 short kebab-case strings (e.g. "frayed-belt", "burnt-pcb").
- severity: low|med|high. high = stop using equipment now.
- summary: 1 short sentence.

Schema:
{
  "tags": ["string"],
  "severity": "low|med|high",
  "summary": "string"
}
"""


def _b64_from_data_url(data_url: str) -> tuple[str, str]:
    """Return (b64_payload, mime). Accepts either bare base64 or data URL."""
    if data_url.startswith("data:"):
        header, _, payload = data_url.partition(",")
        mime = header[5:].split(";")[0] or "image/jpeg"
        return payload, mime
    return data_url, "image/jpeg"


@router.post("/photo/classify")
async def photo_classify(data: dict, user=Depends(get_current_user)):
    of = _of(user)
    image_b64 = (data or {}).get("image_base64") or ""
    photo_id = (data or {}).get("photo_id") or ""
    if not image_b64 and photo_id:
        photo = await db.svc_engineer_photos.find_one({**of, "id": photo_id}, {"_id": 0})
        if not photo:
            raise HTTPException(404, "Photo not found")
        url = photo.get("file_url") or ""
        if url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    image_b64 = base64.b64encode(r.content).decode()
            except Exception as e:
                raise HTTPException(502, f"Could not fetch image: {e}") from e
    if not image_b64:
        raise HTTPException(400, "image_base64 or photo_id required")

    payload, _mime = _b64_from_data_url(image_b64)
    image = ImageContent(image_base64=payload)
    t0 = time.monotonic()
    try:
        raw = await _chat(
            system=_PHOTO_SYSTEM,
            user_text="Inspect this photo of gym equipment and produce the JSON.",
            images=[image],
        )
    except Exception as e:
        logger.warning("photo classify chat failed: %s", e)
        await _log_call(organization_id=of["organization_id"], kind="photo_classify",
                        prompt_chars=0, response_chars=0,
                        latency_ms=int((time.monotonic() - t0) * 1000), ok=False,
                        extra={"error": str(e)[:200]})
        return {"ok": False, "error": "AI service unavailable"}
    latency = int((time.monotonic() - t0) * 1000)
    parsed = _extract_json(raw)
    ok = isinstance(parsed, dict) and parsed.get("severity") in ("low", "med", "high")
    await _log_call(organization_id=of["organization_id"], kind="photo_classify",
                    prompt_chars=len(image_b64), response_chars=len(raw or ""),
                    latency_ms=latency, ok=ok, extra={"photo_id": photo_id})
    if not ok:
        return {"ok": False, "raw": raw}
    result = {
        "ok": True,
        "tags": parsed.get("tags") or [],
        "severity": parsed.get("severity"),
        "summary": parsed.get("summary") or "",
        "latency_ms": latency,
    }
    if photo_id:
        # Persist on the photo doc so future reads don't re-pay the AI cost.
        try:
            await db.svc_engineer_photos.update_one(
                {**of, "id": photo_id},
                {"$set": {"ai": {**result, "at": _now()}}},
            )
        except Exception as e:
            logger.warning("photo ai persist failed: %s", e)
    return result


# ─────────────────────────────────────────────────────────────────
# 3. Case summarisation
# ─────────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM = """You are GymAxis Service Ops summariser.
Compress a noisy case timeline into two short summaries that different
audiences can read in 10 seconds.

Rules:
- Output STRICT JSON. No prose.
- customer_summary: ≤3 sentences. Friendly, no internal jargon, no
  engineer names. Mention what's been done and any next step.
- engineer_summary: ≤3 sentences. Tactical hand-off. Include parts
  used, fault code, and the next action.

Schema:
{
  "customer_summary": "string",
  "engineer_summary": "string"
}
"""


@router.post("/summarise/{case_id}")
async def summarise(case_id: str, user=Depends(get_current_user)):
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    events = (
        await db.svc_case_events
        .find({"case_id": case_id, **of}, {"_id": 0})
        .sort("at", 1).to_list(200)
    )
    lines = [f"Case {case.get('reference')} — {case.get('title')}",
             f"Status: {case.get('status')} · Priority: {case.get('priority')} · Site: {case.get('site_name')}"]
    for ev in events:
        t = ev.get("at") or ""
        if ev.get("type") == "state_change":
            lines.append(f"[{t}] {ev.get('from_state')} → {ev.get('to_state')}{(': ' + ev.get('reason')) if ev.get('reason') else ''}")
        elif ev.get("body"):
            lines.append(f"[{t}] {ev.get('type')}: {ev['body']}")
    user_text = "\n".join(lines[-120:])  # cap to last 120 events
    t0 = time.monotonic()
    try:
        raw = await _chat(system=_SUMMARY_SYSTEM, user_text=user_text)
    except Exception as e:
        logger.warning("summary chat failed: %s", e)
        return {"ok": False, "error": "AI service unavailable"}
    latency = int((time.monotonic() - t0) * 1000)
    parsed = _extract_json(raw)
    ok = isinstance(parsed, dict) and parsed.get("customer_summary")
    await _log_call(organization_id=of["organization_id"], kind="summary",
                    prompt_chars=len(user_text), response_chars=len(raw or ""),
                    latency_ms=latency, ok=bool(ok),
                    extra={"case_id": case_id})
    if not ok:
        return {"ok": False, "raw": raw}
    return {
        "ok": True,
        "case_id": case_id,
        "customer_summary": parsed["customer_summary"],
        "engineer_summary": parsed.get("engineer_summary") or "",
        "latency_ms": latency,
    }


# ─────────────────────────────────────────────────────────────────
# 4. Scheduler tie-break
# ─────────────────────────────────────────────────────────────────

_TIEBREAK_SYSTEM = """You are GymAxis Service Ops scheduling tie-break.
The heuristic scorer has produced 2 or 3 candidate engineers within
10 points of each other. Your job is to pick ONE based on intuition
about real-world service work.

Rules:
- Output STRICT JSON. No prose.
- chosen_engineer_id MUST be one of the candidate ids provided.
- reasoning: ≤200 chars, plain English.

Schema:
{
  "chosen_engineer_id": "string",
  "reasoning": "string"
}
"""


@router.post("/scheduler-tiebreak")
async def scheduler_tiebreak(data: dict, user=Depends(get_current_user)):
    of = _of(user)
    case_id = (data or {}).get("case_id")
    candidates = (data or {}).get("candidate_engineer_ids") or []
    if not case_id or not isinstance(candidates, list) or len(candidates) < 2:
        raise HTTPException(400, "case_id and ≥2 candidate_engineer_ids required")
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    engs = await db.svc_engineers.find(
        {**of, "id": {"$in": candidates}}, {"_id": 0},
    ).to_list(len(candidates))
    if not engs:
        raise HTTPException(404, "No candidate engineers found")
    user_text = (
        f"Case: {case.get('reference')} · {case.get('title')}\n"
        f"Priority: {case.get('priority')} · Site: {case.get('site_name')} (postcode {case.get('site_postcode') or 'unknown'})\n"
        f"Required skills: {', '.join(case.get('required_skills') or []) or 'none specified'}\n"
        f"Asset: {case.get('asset_name') or 'unknown'}\n\nCandidates:\n"
    )
    for e in engs:
        user_text += f"- id={e.get('id')} · name={e.get('full_name')} · skills={', '.join(e.get('skills') or []) or 'none'} · home={e.get('home_address', {}).get('postcode') or 'unknown'}\n"
    t0 = time.monotonic()
    try:
        raw = await _chat(system=_TIEBREAK_SYSTEM, user_text=user_text)
    except Exception as e:
        logger.warning("tiebreak chat failed: %s", e)
        return {"ok": False, "error": "AI service unavailable"}
    latency = int((time.monotonic() - t0) * 1000)
    parsed = _extract_json(raw)
    ok = (
        isinstance(parsed, dict)
        and parsed.get("chosen_engineer_id") in candidates
    )
    await _log_call(organization_id=of["organization_id"], kind="tiebreak",
                    prompt_chars=len(user_text), response_chars=len(raw or ""),
                    latency_ms=latency, ok=bool(ok),
                    extra={"case_id": case_id})
    if not ok:
        return {"ok": False, "raw": raw}
    return {
        "ok": True,
        "case_id": case_id,
        "chosen_engineer_id": parsed["chosen_engineer_id"],
        "reasoning": parsed.get("reasoning") or "",
        "latency_ms": latency,
    }


__all__ = ["router"]
