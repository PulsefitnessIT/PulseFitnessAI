"""
Master Admin Trust Dashboard routes.

Serves the Trust & Reliability Engine (Layer 1) — the internal, admin-facing
surface. Powered by the `trust_events` collection.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body

from utils.auth import get_current_user
from utils.database import db
from utils.trust_events import _now_iso

from routes.master_admin import require_master_admin, log_activity

router = APIRouter(prefix="/master-admin/trust", tags=["trust"])


# ------------------------------- helpers --------------------------------------

async def _count_by_state(state: str) -> int:
    return await db.trust_events.count_documents({"state": state})


async def _count_by_severity_open(severity: str) -> int:
    return await db.trust_events.count_documents({"state": "open", "severity": severity})


async def _recent_resolved(hours: int = 24) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return await db.trust_events.count_documents({
        "state": {"$in": ["resolved", "auto_resolved"]},
        "resolved_at": {"$gte": cutoff},
    })


async def _reliability_snapshot(hours: int = 24) -> dict:
    """Rough reliability % = 1 - (critical+high open events / max event count, clamped).
    Lightweight proxy until we wire a proper uptime probe; gives the dashboard
    a meaningful headline number on day one.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    total_new = await db.trust_events.count_documents({"created_at": {"$gte": cutoff}})
    bad = await db.trust_events.count_documents({
        "created_at": {"$gte": cutoff},
        "severity": {"$in": ["high", "critical"]},
    })
    if total_new == 0:
        return {"reliability_pct": 100.0, "events_24h": 0, "bad_events_24h": 0}
    return {
        "reliability_pct": round(max(0.0, 1.0 - bad / max(total_new, 1)) * 100, 2),
        "events_24h": total_new,
        "bad_events_24h": bad,
    }


async def _integration_status() -> list[dict]:
    """Snapshot of each tracked integration's state. Pulls the most recent
    open event per integration type if any exists, else reports 'live'."""
    integrations = [
        ("Sicon Service", "sicon"),
        ("Sage 200", "sage"),
        ("Resend", "email"),
        ("Database", "db"),
        ("API", "api"),
    ]
    rows = []
    for label, prefix in integrations:
        latest = await db.trust_events.find_one(
            {"type": {"$regex": f"^{prefix}\\."}, "state": {"$in": ["open", "acknowledged"]}},
            sort=[("severity", -1), ("created_at", -1)],
            projection={"_id": 0, "severity": 1, "type": 1, "summary": 1, "last_seen_at": 1},
        )
        rows.append({
            "label": label,
            "prefix": prefix,
            "state": "degraded" if latest else "live",
            "latest": latest,
        })
    return rows


# ------------------------------- endpoints ------------------------------------

@router.get("/overview")
async def trust_overview(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)

    summary = {
        "open": await _count_by_state("open"),
        "acknowledged": await _count_by_state("acknowledged"),
        "resolved_24h": await _recent_resolved(24),
        "critical_open": await _count_by_severity_open("critical"),
        "high_open": await _count_by_severity_open("high"),
    }
    reliability = await _reliability_snapshot(24)
    integrations = await _integration_status()

    open_events = await db.trust_events.find(
        {"state": {"$in": ["open", "acknowledged"]}},
        {"_id": 0},
    ).sort([("severity", -1), ("created_at", -1)]).limit(25).to_list(length=25)

    # self-heal log = auto_resolved events in last 24h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    self_heal = await db.trust_events.find(
        {"state": "auto_resolved", "resolved_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("resolved_at", -1).limit(25).to_list(length=25)

    return {
        "summary": summary,
        "reliability": reliability,
        "integrations": integrations,
        "open_events": open_events,
        "self_heal_log": self_heal,
        "generated_at": _now_iso(),
    }


@router.get("/events")
async def list_trust_events(
    state: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(100, le=500),
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    query: dict = {}
    if state:
        query["state"] = state
    if severity:
        query["severity"] = severity
    if event_type:
        query["type"] = {"$regex": f"^{event_type}"}
    events = await db.trust_events.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"events": events, "total": len(events)}


@router.post("/events/{event_id}/ack")
async def ack_trust_event(event_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    res = await db.trust_events.update_one(
        {"id": event_id, "state": "open"},
        {"$set": {"state": "acknowledged", "acknowledged_at": _now_iso(), "acknowledged_by": user["email"]}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Open event not found")
    await log_activity("trust_ack", f"Acknowledged trust event {event_id}", user["email"], "trust_event", event_id)
    return {"success": True, "state": "acknowledged"}


@router.post("/events/{event_id}/resolve")
async def resolve_trust_event(
    event_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    note = (body or {}).get("note", "")
    res = await db.trust_events.update_one(
        {"id": event_id, "state": {"$in": ["open", "acknowledged"]}},
        {"$set": {
            "state": "resolved",
            "resolved_at": _now_iso(),
            "resolved_by": user["email"],
            "resolution_note": note,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Active event not found")
    await log_activity("trust_resolve", f"Resolved trust event {event_id}: {note}", user["email"], "trust_event", event_id)
    return {"success": True, "state": "resolved"}


@router.post("/events/seed-demo")
async def seed_demo_events(user: dict = Depends(get_current_user)) -> dict:
    """Insert a handful of demo events so the dashboard is populated on first
    open. Idempotent via dedupe keys."""
    require_master_admin(user)
    from utils.trust_events import record_trust_event
    seeds = [
        dict(type="api.latency", severity="low", summary="API p95 latency 1.4s (target ≤1.0s)",
             dedupe_key="demo.api.latency",
             payload={"p95_ms": 1420, "endpoint": "/api/issues"}),
        dict(type="sicon.queue.depth", severity="med",
             summary="Sicon sync queue has 14 pending jobs — monitoring",
             dedupe_key="demo.sicon.queue",
             payload={"queue_depth": 14, "oldest_age_minutes": 12}),
        dict(type="email.bounce.rate", severity="low",
             summary="Resend bounce rate 3.1% (threshold 5%)",
             dedupe_key="demo.email.bounce",
             payload={"bounce_pct": 3.1, "window_hours": 24}),
    ]
    for s in seeds:
        await record_trust_event(**s)
    return {"success": True, "seeded": len(seeds)}


# ---------- AI Diagnosis (optional micro-feature) -----------------------------

_DIAGNOSE_SYSTEM = """You are a senior DevSecOps engineer reviewing a platform trust event.
You will receive:
- The triggering event (type, severity, summary, payload)
- Up to 20 related recent events (same type or dedupe_key, last 7 days)

Return ONLY valid JSON (no markdown fences, no commentary) matching:
{
  "probable_cause":      "1–2 sentence root-cause hypothesis",
  "recommended_action":  "1–3 concrete next steps the admin should take",
  "customer_safe_message": "Short plain-English line a customer could see if this needed surfacing to them, or null if internal only",
  "confidence":          "low" | "medium" | "high"
}
Rules:
- Base reasoning on the payload numbers and related-event pattern; don't invent facts.
- Flag "confidence": "low" when evidence is thin — better to admit uncertainty than hallucinate.
- Keep recommended_action short and actionable — no generic advice."""


async def _collect_related_events(event: dict, limit: int = 20) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    query = {"created_at": {"$gte": cutoff}, "id": {"$ne": event["id"]}}
    if event.get("dedupe_key"):
        query["$or"] = [{"dedupe_key": event["dedupe_key"]}, {"type": event["type"]}]
    else:
        query["type"] = event["type"]
    return await db.trust_events.find(
        query, {"_id": 0, "severity": 1, "summary": 1, "payload": 1, "created_at": 1, "state": 1}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)


def _build_diagnose_prompt(event: dict, related: list[dict]) -> str:
    import json as _json
    parts = [
        "TRIGGERING EVENT:",
        f"  type: {event.get('type')}",
        f"  severity: {event.get('severity')}",
        f"  state: {event.get('state')}",
        f"  summary: {event.get('summary', '')}",
        f"  occurrences: {event.get('occurrences', 1)}",
        f"  first_seen: {event.get('created_at')}",
        f"  last_seen: {event.get('last_seen_at') or event.get('created_at')}",
        f"  payload: {_json.dumps(event.get('payload') or {})}",
        "",
        f"RELATED EVENTS (last 7 days, {len(related)} shown):",
    ]
    for i, r in enumerate(related[:20], 1):
        parts.append(f"  [{i}] {r.get('created_at', '')[:19]} · {r.get('severity')} · state={r.get('state','?')} · {r.get('summary','')[:140]}")
    if not related:
        parts.append("  (none)")
    return "\n".join(parts)


@router.post("/events/{event_id}/diagnose")
async def diagnose_trust_event(event_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Ask GPT-5.2 to triage this trust event. Writes {ai_summary, probable_cause,
    recommended_action, customer_safe_message, confidence, diagnosed_at, diagnosed_model}
    back onto the event doc and returns the updated event.

    Does NOT take any remediation action — output is advisory only. Admin still
    decides whether to Acknowledge or Resolve.
    """
    require_master_admin(user)
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from utils.database import EMERGENT_LLM_KEY
    from routes.issue_helpers import call_ai_with_retry, parse_ai_json
    import uuid as _uuid

    event = await db.trust_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="Emergent LLM key not configured")

    related = await _collect_related_events(event)
    prompt = _build_diagnose_prompt(event, related)
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"trust-diagnose-{event_id}-{_uuid.uuid4().hex[:8]}",
        system_message=_DIAGNOSE_SYSTEM,
    ).with_model("openai", "gpt-5.2")

    try:
        raw = await call_ai_with_retry(chat, UserMessage(text=prompt), max_retries=2)
        parsed = parse_ai_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI diagnosis failed: {exc}")

    ai_fields = {
        "probable_cause": (parsed.get("probable_cause") or "").strip(),
        "recommended_action": (parsed.get("recommended_action") or "").strip(),
        "customer_safe_message": parsed.get("customer_safe_message"),
        "confidence": parsed.get("confidence") if parsed.get("confidence") in ("low", "medium", "high") else "low",
        "diagnosed_at": _now_iso(),
        "diagnosed_by": user["email"],
        "diagnosed_model": "openai/gpt-5.2",
    }
    await db.trust_events.update_one(
        {"id": event_id},
        {"$set": {f"ai.{k}": v for k, v in ai_fields.items()}},
    )
    await log_activity("trust_diagnose", f"AI-diagnosed trust event {event_id} ({ai_fields['confidence']} conf)",
                       user["email"], "trust_event", event_id)

    refreshed = await db.trust_events.find_one({"id": event_id}, {"_id": 0})
    return {"success": True, "event": refreshed, "ai": ai_fields}
