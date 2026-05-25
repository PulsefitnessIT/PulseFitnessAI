"""Partner application AI decision helper — iter 219b.

Lightweight wrapper around GPT-4o-mini (Emergent LLM key) that gives
the master admin a one-line decision recommendation for a pending
partner engineer application.

Why this exists:
  Reading 30+ applications a day is slow. Subtle structural signals
  (expired insurance, single-brand engineer in a multi-brand postcode,
  coverage gap, qualifications mismatch) are easy to miss when
  scanning. This helper surfaces them up-front.

Design rules:
  • NEVER blocks the drawer — degrades gracefully on LLM failure.
  • Returns structured JSON so the frontend can render chips/pills
    without parsing free-form text.
  • Deterministic fallback in `_fallback()` when the LLM is offline
    so the UI always shows something useful.
"""
from __future__ import annotations

import json as json_mod
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_MSG = (
    "You are a triage analyst for GymAxis's Partner Engineer network. "
    "Given a pending application + the current partner roster, give a "
    "concise British-English recommendation. You are advisory only — "
    "the human reviewer makes the final call. Be honest about red flags; "
    "do not flatter. Output STRICT JSON only, no markdown."
)

ALLOWED_DECISIONS = {"approve", "reject", "needs_info"}
ALLOWED_LEVELS = {
    "engineer_partner", "verified_partner", "strategic_partner",
}


def _summarise_roster(roster: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact aggregation of existing partners — sent to the LLM so it
    can spot coverage gaps without us paying for the full list."""
    brand_counts: dict[str, int] = {}
    postcode_areas: dict[str, int] = {}
    for p in roster or []:
        for b in (p.get("brands_supported") or []):
            brand_counts[b] = brand_counts.get(b, 0) + 1
        pc = (p.get("service_postcode") or "").strip().upper()
        if pc:
            area = pc.split(" ")[0] if " " in pc else pc[:2]
            postcode_areas[area] = postcode_areas.get(area, 0) + 1
    top_brands = sorted(brand_counts.items(), key=lambda x: -x[1])[:15]
    top_postcodes = sorted(postcode_areas.items(), key=lambda x: -x[1])[:20]
    return {
        "total_active_partners": len(roster or []),
        "brand_coverage": [{"brand": b, "partners": c} for b, c in top_brands],
        "postcode_coverage": [{"area": a, "partners": c} for a, c in top_postcodes],
    }


def _build_prompt(app: dict[str, Any], roster_summary: dict[str, Any]) -> str:
    """Strip the application down to the signal-bearing fields so we
    don't waste tokens on submission timestamps etc."""
    applicant = {
        "full_name": app.get("full_name"),
        "years_experience": app.get("years_experience"),
        "company_name": app.get("company_name"),
        "service_postcode": app.get("service_postcode"),
        "travel_radius_km": app.get("travel_radius_km"),
        "brands_supported": app.get("brands_supported") or [],
        "skills": app.get("skills") or [],
        "qualifications": app.get("qualifications") or [],
        "has_insurance": bool(app.get("has_insurance")),
        "insurance_provider": app.get("insurance_provider"),
        "insurance_expires_at": app.get("insurance_expires_at"),
        "qualifications_expires_at": app.get("qualifications_expires_at"),
        "cover_letter_excerpt": (app.get("cover_letter") or "")[:600],
        "attachments_count": len(app.get("attachments") or []),
    }
    return (
        "Pending Partner Engineer application:\n"
        + json_mod.dumps(applicant, default=str, indent=2)
        + "\n\nCurrent partner roster snapshot (for coverage-gap reasoning):\n"
        + json_mod.dumps(roster_summary, indent=2)
        + "\n\nReturn STRICT JSON with this exact shape:\n"
        + "{\n"
        + '  "decision": "approve" | "reject" | "needs_info",\n'
        + '  "level":    "engineer_partner" | "verified_partner" | "strategic_partner",\n'
        + '  "confidence": 0.0-1.0,\n'
        + '  "headline":   "<one short sentence the admin reads first>",\n'
        + '  "reasons":    ["<3-5 bullet reasons>"],\n'
        + '  "red_flags":  ["<empty list if none, otherwise concrete concerns>"],\n'
        + '  "coverage_value": "<short note: does this applicant fill a brand/postcode gap?>"\n'
        + "}\n\n"
        + "Rules:\n"
        + " • Approve only when insurance is on file, terms accepted, and skills/qualifications look credible.\n"
        + " • Reject when there is no insurance OR core paperwork is missing AND no cover letter.\n"
        + " • Otherwise prefer 'needs_info'.\n"
        + " • Use 'verified_partner' only when the candidate explicitly demonstrates seniority "
        + "(6+ yrs, multi-brand, recognised qualifications like IPAF/IOSH).\n"
        + " • Never invent facts. If a field is null or empty, say so.\n"
    )


def _fallback(app: dict[str, Any]) -> dict[str, Any]:
    """Deterministic decision so the UI is always populated even when
    the LLM is unavailable. Mirrors the prompt's rules above."""
    has_insurance = bool(app.get("has_insurance"))
    attachments = len(app.get("attachments") or [])
    quals = app.get("qualifications") or []
    brands = app.get("brands_supported") or []
    cover_letter = (app.get("cover_letter") or "").strip()
    red_flags: list[str] = []
    if not has_insurance:
        red_flags.append("No insurance recorded — required before approval.")
    if attachments == 0:
        red_flags.append("No paperwork attached (CV / certifications).")
    if not quals:
        red_flags.append("No qualifications listed.")

    if not has_insurance and attachments == 0 and not cover_letter:
        decision = "reject"
        headline = "Auto-suggest reject — missing insurance, paperwork and cover letter."
    elif red_flags:
        decision = "needs_info"
        headline = "Needs more info before approval — see red flags."
    else:
        decision = "approve"
        headline = "Looks complete — paperwork and insurance on file."

    level = "engineer_partner"
    try:
        years = int(str(app.get("years_experience") or "0").strip() or "0")
    except ValueError:
        years = 0
    if years >= 6 and len(brands) >= 2 and any(
        q.upper().startswith(("IPAF", "IOSH", "C&G")) for q in quals
    ):
        level = "verified_partner"

    return {
        "decision": decision,
        "level": level,
        "confidence": 0.45,  # deterministic — not high
        "headline": headline,
        "reasons": [
            f"{len(brands)} brand(s) supported, {len(quals)} qualification(s).",
            f"{attachments} file(s) attached.",
            ("Insurance on file." if has_insurance else "Insurance MISSING."),
        ],
        "red_flags": red_flags,
        "coverage_value": "Coverage-gap analysis unavailable (LLM offline).",
        "model": "deterministic-fallback",
    }


def _coerce(parsed: dict[str, Any]) -> dict[str, Any]:
    """Clamp / normalise the LLM output so the FE never crashes on a
    surprise key or out-of-enum value."""
    decision = str(parsed.get("decision") or "needs_info").lower().strip()
    if decision not in ALLOWED_DECISIONS:
        decision = "needs_info"
    level = str(parsed.get("level") or "engineer_partner").lower().strip()
    if level not in ALLOWED_LEVELS:
        level = "engineer_partner"
    try:
        confidence = float(parsed.get("confidence") or 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return {
        "decision": decision,
        "level": level,
        "confidence": confidence,
        "headline": str(parsed.get("headline") or "").strip()[:240],
        "reasons": [str(x).strip()[:240] for x in (parsed.get("reasons") or []) if x][:6],
        "red_flags": [str(x).strip()[:240] for x in (parsed.get("red_flags") or []) if x][:6],
        "coverage_value": str(parsed.get("coverage_value") or "").strip()[:280],
    }


async def suggest_decision(
    app: dict[str, Any], roster: list[dict[str, Any]],
) -> dict[str, Any]:
    """Main entrypoint. Returns a decision payload — never raises.
    The deterministic fallback is used whenever the LLM is offline,
    times out, returns invalid JSON, or `EMERGENT_LLM_KEY` is unset.
    """
    roster_summary = _summarise_roster(roster)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
        if not api_key:
            raise RuntimeError("EMERGENT_LLM_KEY missing")
        chat = LlmChat(
            api_key=api_key,
            session_id=str(uuid.uuid4()),
            system_message=SYSTEM_MSG,
        ).with_model("openai", "gpt-4o-mini")
        raw = await chat.send_message(UserMessage(text=_build_prompt(app, roster_summary)))
        raw = (raw or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json_mod.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.info("Partner application AI suggestion fell back: %s", exc)
        out = _fallback(app)
        return {**out, "roster_summary": roster_summary}

    out = _coerce(parsed)
    return {**out, "model": "gpt-4o-mini", "roster_summary": roster_summary}
