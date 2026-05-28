"""Unified GymAxis AI Assistant — single endpoint, mode-aware grounded chat.

The same floating orb appears on /marketing, /pulse, and /memberships. Behind
the scenes each route picks a `mode` and we build a tailored system prompt +
context block from that module's MongoDB collections so Claude answers with
the user's real, live data and only on platform topics.

Endpoints
---------
* POST /api/assistant/chat               — chat turn
* GET  /api/assistant/chat/{session_id}  — replay history
* POST /api/assistant/execute-action     — run a Claude-recommended one-click action

Allowed modes: marketing | operations | memberships
"""
from __future__ import annotations

import logging
import os
import re
import json as _json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.ai_guardrails import (
    detect_injection,
    enforce_token_budget,
    record_ai_action,
    record_token_usage,
    sanitize_prompt,
    wrap_user_input,
)
from routes.help_data import search_guides as _search_help_guides

logger = logging.getLogger(__name__)


# ── Page-context + help-grounding helpers (Iter 215l) ──────────

def _format_page_context(ctx: dict) -> str:
    """Compress the frontend's page-context dict into a few prompt-ready
    bullet points. Keeps token cost predictable; ignores anything we
    don't recognise."""
    if not ctx:
        return ""
    pathname = (ctx.get("pathname") or "").strip()
    tab = (ctx.get("tab") or "").strip()
    section = (ctx.get("active_section") or "").strip()
    query = ctx.get("query") or {}
    recent = ctx.get("recent_actions") or []

    lines = []
    if pathname:
        lines.append(f"- Route: `{pathname}`")
    if tab:
        lines.append(f"- Active tab: `{tab}`")
    if section:
        lines.append(f"- Active section: `{section}`")
    if isinstance(query, dict) and query:
        # Only surface short, safe params.
        compact = ", ".join(f"{k}={v}" for k, v in list(query.items())[:6] if isinstance(v, (str, int, bool)) and len(str(v)) < 40)
        if compact:
            lines.append(f"- URL params: {compact}")
    if isinstance(recent, list) and recent:
        # Last 5 recorded actions only, truncated for safety.
        last = [str(a)[:60] for a in recent[-5:]]
        lines.append("- Recent user actions: " + " → ".join(last))
    if not lines:
        return ""
    lines.append('- When the user says "this", "here", "this screen", they mean the route + tab above.')
    return "\n".join(lines)


async def _format_help_grounding(message: str, mode: str, page_ctx: dict) -> str:
    """Return up to 3 relevant help guides as a markdown block the assistant
    can cite. Combines the user's message with active-tab keywords for
    better recall.

    Note: we pass role="master_admin" so the assistant can ground its
    answer against the FULL corpus. The customer-facing reply is what's
    actually shown to the user — guide visibility filtering already
    happens at the Help Centre UI level.
    """
    if not message:
        return ""
    query = message
    tab = (page_ctx or {}).get("tab")
    if tab:
        query += f" {tab}"
    try:
        hits = _search_help_guides(query, role="master_admin")
    except Exception:  # noqa: BLE001
        return ""
    if not hits:
        return ""
    out_lines = []
    for h in hits[:3]:
        title = h.get("title") or h.get("id")
        desc = (h.get("description") or "").replace("\n", " ").strip()[:160]
        out_lines.append(f"- **{title}** — {desc}")
    return "\n".join(out_lines)


router = APIRouter(tags=["assistant"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


async def _org_id(user: dict) -> str:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "Organisation context required")
    return org_id


# ════════════════════════════════════════════════════════════════════════
# Context builders — one per mode
# ════════════════════════════════════════════════════════════════════════

async def _ctx_marketing(org_id: str) -> str:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym = org.get("name") or "the gym"
    camps = await db.marketing_campaigns.find(
        {"organization_id": org_id}, {"_id": 0, "name": 1, "status": 1, "metrics": 1, "created_at": 1},
    ).sort([("created_at", -1)]).limit(5).to_list(5)
    lines = []
    for c in camps:
        m = c.get("metrics") or {}
        sent = m.get("sent", 0) or 0
        opens = m.get("opened", 0) or 0
        rate = round((opens / sent) * 100, 1) if sent else 0
        lines.append(f"- {c.get('name','(unnamed)')} [{c.get('status','draft')}] · sent={sent} · opens={rate}%")
    auds = await db.marketing_audiences.find(
        {"organization_id": org_id}, {"_id": 0, "name": 1, "estimated_size": 1},
    ).sort([("estimated_size", -1)]).limit(5).to_list(5)
    al = [f"- {a.get('name')} · {a.get('estimated_size', 0)} contacts" for a in auds]
    rev = await db.marketing_attributions.aggregate([
        {"$match": {"organization_id": org_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_gbp"}}},
    ]).to_list(1)
    revenue = (rev[0] if rev else {}).get("total") or 0
    return (
        f"# Live data for {gym}\n\n## Recent campaigns ({len(camps)}):\n"
        + ("\n".join(lines) if lines else "- No campaigns yet")
        + "\n\n## Top audiences:\n" + ("\n".join(al) if al else "- No audiences yet")
        + f"\n\n## Attributed revenue (all-time): £{revenue:,.2f}\n"
    )


async def _ctx_operations(org_id: str) -> str:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym = org.get("name") or "the gym"
    # Operations faults live in the `issues` collection (NOT `faults`).
    open_q = {"organization_id": org_id, "status": {"$in": ["open", "in_progress"]}}
    open_faults = await db.issues.count_documents(open_q)
    high_open = await db.issues.count_documents({**open_q, "severity": "high"})
    eq_total = await db.equipment.count_documents({"organization_id": org_id})
    eq_down = await db.equipment.count_documents({"organization_id": org_id, "status": "out_of_service"})
    recent = await db.issues.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "machine_type": 1, "issue_description": 1,
         "status": 1, "severity": 1, "created_at": 1, "serial_number": 1},
    ).sort([("created_at", -1)]).limit(5).to_list(5)
    rf_lines = [
        f"- \"{(f.get('issue_description') or '(no description)')[:60]}\" "
        f"[{f.get('severity','medium')}/{f.get('status','open')}] on "
        f"{f.get('machine_type','?')} ({f.get('serial_number','-')}) · id={f.get('id','')}"
        for f in recent
    ]
    return (
        f"# Live operations for {gym}\n\n"
        f"- Open faults: **{open_faults}** ({high_open} high severity)\n"
        f"- Equipment fleet: {eq_total} units · {eq_down} out of service\n\n"
        f"## Recent faults ({len(recent)}):\n"
        + ("\n".join(rf_lines) if rf_lines else "- No recent faults")
        + "\n\nAvailable actions for a specific fault:\n"
        "- Open it: `{\"type\": \"open_fault\", \"label\": \"Open fault\", \"params\": {\"fault_id\": \"<id>\"}}`\n"
        "- Mark resolved (DESTRUCTIVE — only when the user clearly says resolve/close/fix): "
        "`{\"type\": \"resolve_issue\", \"label\": \"Resolve fault\", \"params\": {\"fault_id\": \"<id>\"}}`"
    )


async def _ctx_memberships(org_id: str) -> str:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym = org.get("name") or "the gym"
    # Membership data lives in `members`, `membership_plans`, `member_memberships`,
    # `class_occurrences` (NOT the `memberships_*` namespaced names).
    active = await db.members.count_documents({"organization_id": org_id, "status": "active"})
    paused = await db.member_memberships.count_documents({"organization_id": org_id, "status": "frozen"})
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cancelled_today = await db.member_memberships.count_documents({
        "organization_id": org_id, "status": "cancelled",
        "cancel_effective_date": {"$gte": today_iso},
    })
    plans = await db.membership_plans.find(
        {"organization_id": org_id, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "monthly_price_pence": 1, "kind": 1},
    ).limit(5).to_list(5)
    plan_lines = []
    for p in plans:
        price_pence = p.get("monthly_price_pence") or 0
        price_str = f"£{(price_pence / 100):.2f}/mo" if p.get("kind") == "recurring" else (p.get("kind") or "plan")
        count = await db.member_memberships.count_documents(
            {"organization_id": org_id, "plan_id": p.get("id"), "status": "active"}
        )
        plan_lines.append(f"- {p.get('name')} · {price_str} · {count} members · id={p.get('id','')}")
    classes_today = await db.class_occurrences.count_documents({
        "organization_id": org_id,
        "starts_at": {"$gte": today_iso, "$lt": today_iso + "T23:59:59"},
    })
    # Top 3 highest-LTV active members for the AI to reference by name.
    top_members = await db.members.find(
        {"organization_id": org_id, "status": "active"},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "lifetime_value_pence": 1, "last_visit_at": 1},
    ).sort([("lifetime_value_pence", -1)]).limit(3).to_list(3)
    member_lines = [
        f"- {(m.get('first_name') or '').strip()} {(m.get('last_name') or '').strip()}".rstrip()
        + f" · LTV £{((m.get('lifetime_value_pence') or 0) / 100):.0f}"
        + f" · last visit {m.get('last_visit_at') or 'never'} · id={m.get('id','')}"
        for m in top_members
    ]
    return (
        f"# Live memberships for {gym}\n\n"
        f"- Active members: **{active}** · Frozen: {paused} · Cancelled (today): {cancelled_today}\n"
        f"- Class occurrences today: {classes_today}\n\n"
        f"## Active plans:\n" + ("\n".join(plan_lines) if plan_lines else "- No plans configured")
        + ("\n\n## Top members by LTV:\n" + "\n".join(member_lines) if member_lines else "")
        + "\n\nAvailable actions for a specific member or plan:\n"
        "- Open member: `{\"type\": \"open_member\", \"params\": {\"member_id\": \"<id>\"}}`\n"
        "- Open plan: `{\"type\": \"open_plan\", \"params\": {\"plan_id\": \"<id>\"}}`\n"
        "- Freeze membership (DESTRUCTIVE — only when user clearly asks to freeze/pause): "
        "`{\"type\": \"freeze_membership\", \"label\": \"Freeze membership\", \"params\": {\"member_id\": \"<id>\", \"days\": 30}}`\n"
        "- Cancel membership (DESTRUCTIVE — only when user clearly asks to cancel/end): "
        "`{\"type\": \"cancel_membership\", \"label\": \"Cancel membership\", \"params\": {\"member_id\": \"<id>\", \"immediate\": false, \"reason\": \"member_request\"}}`"
    )


# Map mode → context builder + system prompt header + action allowlist
MODE_REGISTRY: dict[str, dict] = {
    "marketing": {
        "label": "Marketing",
        "context_fn": _ctx_marketing,
        "scope_topics": (
            "campaigns, audiences, segmentation, email/SMS, creatives, journeys, "
            "performance, attribution, A/B tests, deliverability, social media"
        ),
        "tabs": ("insights", "audiences", "campaigns", "creative", "journeys", "social", "performance"),
        "actions": {
            "navigate_tab": ["insights", "audiences", "campaigns", "creative", "journeys", "social", "performance"],
            "instantiate_template": ["welcome_new_member", "winback", "class_promo", "pt_upsell", "failed_payment_recovery", "referral_push"],
        },
    },
    "operations": {
        "label": "Operations",
        "context_fn": _ctx_operations,
        "scope_topics": (
            "equipment, faults, maintenance, suppliers, parts, service tickets, "
            "sites, technicians, downtime, SLAs, work orders"
        ),
        "tabs": ("dashboard", "faults", "equipment", "schedule", "service-desk", "settings"),
        "actions": {
            "navigate": ["faults", "equipment", "schedule", "service-desk"],
            "open_fault": True,        # validated by uuid presence
            "open_equipment": True,
            "resolve_issue": True,     # destructive — sets status=resolved
        },
    },
    "memberships": {
        "label": "Memberships",
        "context_fn": _ctx_memberships,
        "scope_topics": (
            "members, plans, sign-ups, retention, churn, lifetime value, "
            "classes, bookings, waitlists, ads, cancellations, pauses"
        ),
        "tabs": ("dashboard", "members", "plans", "classes", "ads", "analytics"),
        "actions": {
            "navigate_tab": ["dashboard", "members", "plans", "classes", "ads", "analytics"],
            "open_member": True,
            "open_plan": True,
            "freeze_membership": True,   # destructive — pauses billing
            "cancel_membership": True,   # destructive — ends membership
        },
    },
    # Iter 215q — lightweight guidance modes for Master Admin and CRM so
    # the AI Orb can mount on those pages and cite Help Centre guides.
    # No destructive actions; just grounded Q&A.
    "admin": {
        "label": "Admin",
        "context_fn": None,
        "scope_topics": (
            "organisations, billing, invoices, subscriptions, integrations, "
            "users, permissions, security, onboarding, data wipe, password reset"
        ),
        "tabs": ("overview", "tasks", "onboarding", "finance", "security", "roles"),
        "actions": {},
    },
    "crm": {
        "label": "CRM",
        "context_fn": None,
        "scope_topics": (
            "contacts, companies, deals, pipelines, stages, quotes, contracts, "
            "activities, custom properties, leisure mode, business mode, bulk import"
        ),
        "tabs": ("dashboard", "contacts", "companies", "pipeline", "activity-feed", "calendar", "workflows", "quotes"),
        "actions": {},
    },
}


def _build_system_prompt(mode: str, context_block: str) -> str:
    cfg = MODE_REGISTRY[mode]
    other_modes = ", ".join(k.title() for k in MODE_REGISTRY if k != mode)
    return (
        f"You are GymAxis {cfg['label']} Copilot — an AI assistant embedded in "
        f"the {cfg['label']} module of a platform built for fitness operators "
        f"(Pulse Pro and GymAxis). You give concise, actionable answers grounded "
        f"in the user's real, live data (provided below).\n\n"
        f"## SCOPE GUARDRAIL — CRITICAL\n"
        f"You ONLY answer questions related to topics within this platform:\n"
        f"- {cfg['label']} (your specialty): {cfg['scope_topics']}\n"
        f"- Adjacent modules ({other_modes}) — answer briefly if relevant, then point them to that module.\n"
        f"- Business: revenue, growth, billing, integrations (Sage, Sicon, Orbit 4, Stripe, Resend, Meta), "
        f"gym industry benchmarks.\n\n"
        f"For anything OUTSIDE these topics — general knowledge, coding, recipes, "
        f"weather, news, jokes, geography, personal advice — politely decline in "
        f"ONE short sentence and redirect them to a relevant {cfg['label'].lower()} topic.\n\n"
        f"## TONE & FORMAT\n"
        f"Friendly, expert, never patronising. British English. Under 150 words "
        f"unless asked for detail. Refer to the actual numbers below when answering "
        f"performance questions. Tell users which tab to open by name. Never invent "
        f"metrics.\n\n"
        f"## ACTION PROTOCOL\n"
        f"When recommending a concrete in-app step, append a single JSON action block "
        f"at the very end on its own line, fenced like this:\n"
        f'```action\n{{"type": "<TYPE>", "label": "<button label, max 32 chars>", "params": {{...}}}}\n```\n'
        f"The platform renders this as a one-click button. ONE action max per "
        f"response. Allowed types for this mode: {', '.join(cfg['actions'].keys())}. "
        f"Don't include actions for purely informational answers.\n\n"
        f"## DESTRUCTIVE ACTIONS — EXTRA CARE\n"
        f"Types prefixed `resolve_`, `freeze_`, `cancel_` mutate real data. ONLY emit "
        f"them when the user has clearly asked for that mutation (e.g. \"resolve fault X\", "
        f"\"freeze Emma's membership for 4 weeks\", \"cancel John's plan\"). If the user "
        f"is just asking for information, do NOT emit a destructive action — recommend "
        f"opening the record instead. The frontend always asks the operator to confirm "
        f"before executing, so you can be helpful and offer the action when intent is clear.\n\n"
        f"{context_block}"
    )


# ════════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════════


async def _call_chat_llm(*, session_id: str, system_message: str, message: str, mode: str) -> str:
    """Invoke the Claude chat backend. Returns a friendly fallback string
    if the LLM service is unreachable so the UX never silently breaks."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI assistant unavailable — LLM key not configured")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(api_key=api_key, session_id=session_id, system_message=system_message) \
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        return await chat.send_message(UserMessage(text=message))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.warning("[assistant] claude chat failed mode=%s err=%s", mode, exc)
        return (
            "I'm having trouble reaching the AI service right now — please try "
            "again in a moment."
        )


def _extract_action_block(answer: str, mode: str) -> tuple[str, dict | None]:
    """Pull a ```action {...}``` block out of the LLM response. Returns
    `(answer_without_block, action_or_None)`. Malformed blocks are
    treated as plain text — the chat must always come back."""
    try:
        m = re.search(r"```action\s*(\{.+?\})\s*```", answer, flags=re.DOTALL)
    except Exception:  # pragma: no cover
        return answer, None
    if not m:
        return answer, None
    try:
        payload = _json.loads(m.group(1))
    except Exception as exc:  # pragma: no cover
        logger.info("[assistant] action parse failed: %s", exc)
        return answer, None
    allowed_types = set(MODE_REGISTRY[mode]["actions"].keys())
    action: dict | None = None
    if isinstance(payload, dict) and payload.get("type") in allowed_types:
        action = {
            "type": payload["type"],
            "label": (payload.get("label") or "Do it")[:48],
            "params": payload.get("params") or {},
        }
    return (answer[: m.start()] + answer[m.end():]).strip(), action


@router.post("/assistant/chat")
async def assistant_chat(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Mode-aware chat turn. Body: {mode, session_id, message, page_context?}.

    `page_context` (optional) is an opaque dict the frontend pushes describing
    where the user is right now — current tab, active modal, query params,
    last-clicked element. Wired into the system prompt so a question like
    "how do I do this?" resolves to *this screen*, not the whole module.
    Falls back gracefully when omitted (legacy clients).
    """
    mode = (body.get("mode") or "").strip().lower()
    if mode not in MODE_REGISTRY:
        raise HTTPException(400, f"Unsupported mode: {mode!r}. Allowed: {list(MODE_REGISTRY)}")
    session_id = (body.get("session_id") or "").strip() or _new_id()
    message_raw = (body.get("message") or "").strip()
    if not message_raw:
        raise HTTPException(400, "Message is required")

    # ── F-11 / LLM01 — prompt-injection guardrails (Iter 220at) ──
    # Strip control chars + clamp to 8k chars, score the input
    # against a known-bad-pattern list, reject obvious jailbreaks.
    message = sanitize_prompt(message_raw)
    risk = detect_injection(message)
    if risk["score"] >= 80:
        logger.warning(
            "[assistant] prompt rejected — injection flags=%s user=%s mode=%s",
            risk["flags"], user.get("email"), mode,
        )
        await record_ai_action(
            user, action=f"assistant.chat.{mode}.rejected",
            payload={"flags": risk["flags"], "score": risk["score"]},
            risk_score=risk["score"],
        )
        raise HTTPException(
            400,
            "That request looks like a prompt-injection attempt and was blocked. "
            "Please rephrase the question without instructing the AI to ignore its "
            "system prompt or reveal hidden data.",
        )

    org_id = await _org_id(user)
    # ── F-16 / LLM10 — per-tenant daily token budget ─────────────
    # Conservative estimate: a typical chat turn ≈ 2k tokens combined
    # (system+context+message+answer). Surfaces a 429 long before any
    # tenant blows the per-org budget.
    await enforce_token_budget(org_id, est_tokens=2000)
    ctx_fn = MODE_REGISTRY[mode].get("context_fn")
    context = await ctx_fn(org_id) if ctx_fn else ""

    # Iter 215l — Page context awareness. Frontend supplies {pathname, tab,
    # query, active_section, recent_actions} so the assistant knows *where*
    # in the module the user is stuck.
    page_ctx = body.get("page_context") or {}
    page_block = _format_page_context(page_ctx) if isinstance(page_ctx, dict) else ""

    # Help-guide grounding — pull in any guides relevant to the user's
    # message + current page so the assistant can cite documentation.
    help_block = await _format_help_grounding(message, mode, page_ctx)

    system_message = _build_system_prompt(mode, context)
    if page_block:
        system_message += f"\n\n## CURRENT SCREEN CONTEXT\n{page_block}"
    if help_block:
        system_message += f"\n\n## RELEVANT HELP GUIDES (cite by title when applicable)\n{help_block}"

    history = await db.assistant_chats.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0},
    ) or {"session_id": session_id, "user_id": user["id"], "organization_id": org_id, "mode": mode, "turns": []}

    answer = await _call_chat_llm(
        session_id=session_id, system_message=system_message,
        message=wrap_user_input(message), mode=mode,
    )
    answer_clean, action = _extract_action_block(answer, mode)

    # Track token spend (rough estimate — 1 token ≈ 4 chars). Cheap
    # write, used by ``enforce_token_budget`` on subsequent turns.
    await record_token_usage(
        org_id,
        tokens=(len(message) + len(system_message) + len(answer)) // 4,
        surface=f"assistant.{mode}",
    )
    await record_ai_action(
        user, action=f"assistant.chat.{mode}",
        payload={"action_emitted": (action or {}).get("type")},
        risk_score=risk["score"],
    )

    now = _now()
    history.setdefault("turns", []).extend([
        {"role": "user", "content": message, "at": now},
        {"role": "assistant", "content": answer_clean, "action": action, "at": now},
    ])
    history["updated_at"] = now
    history["mode"] = mode
    await db.assistant_chats.update_one(
        {"session_id": session_id, "user_id": user["id"]}, {"$set": history}, upsert=True,
    )
    if len(history["turns"]) > 40:
        await db.assistant_chats.update_one(
            {"session_id": session_id, "user_id": user["id"]},
            {"$set": {"turns": history["turns"][-40:]}},
        )

    return {"session_id": session_id, "answer": answer_clean, "action": action, "mode": mode, "model": "claude-sonnet-4-5-20250929"}


@router.get("/assistant/chat/{session_id}")
async def assistant_chat_history(session_id: str, user: dict = Depends(get_current_user)):
    record = await db.assistant_chats.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0},
    )
    return {"turns": (record or {}).get("turns", []), "mode": (record or {}).get("mode")}


_DESTRUCTIVE_TYPES = {"resolve_issue", "freeze_membership", "cancel_membership"}


async def _log_destructive_action(*, user: dict, mode: str, action_type: str,
                                   params: dict, target_kind: str, target_id: str,
                                   target_label: str, before_status: str | None,
                                   after_status: str | None, result: dict | None,
                                   already_done: bool = False) -> None:
    """Persist an audit row for every destructive AI mutation. Best-effort —
    logging failures must not break the action itself."""
    try:
        org_id = user.get("organization_id")
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
        await db.assistant_action_log.insert_one({
            "id": _new_id(),
            "executed_at": _now(),
            "mode": mode,
            "action_type": action_type,
            "user_id": user.get("id"),
            "user_name": user.get("full_name") or user.get("email"),
            "user_email": user.get("email"),
            "organization_id": org_id,
            "organization_name": org.get("name"),
            "target_kind": target_kind,
            "target_id": target_id,
            "target_label": target_label,
            "params": {k: params.get(k) for k in ("days", "immediate", "reason") if k in params},
            "before_status": before_status,
            "after_status": after_status,
            "already_done": already_done,
            "result_summary": (result or {}).get("effective") or (result or {}).get("frozen_until"),
        })
    except Exception as exc:  # pragma: no cover
        logger.warning("[assistant] action log failed type=%s err=%s", action_type, exc)


@router.post("/assistant/execute-action")
async def assistant_execute_action(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Run a one-click action recommended by the AI Assistant.

    Thin dispatcher — each `(mode, action_type)` is delegated to a small
    handler. This keeps the entry-point cyclomatic complexity low and
    makes individual actions easy to test/extend.
    """
    mode = (body.get("mode") or "").strip().lower()
    if mode not in MODE_REGISTRY:
        raise HTTPException(400, f"Unsupported mode: {mode!r}")
    action_type = (body.get("type") or "").strip()
    params = body.get("params") or {}
    allowlist = MODE_REGISTRY[mode]["actions"]
    if action_type not in allowlist:
        raise HTTPException(400, f"Action {action_type!r} not allowed in mode {mode!r}")

    org_id = await _org_id(user)
    ctx = {"user": user, "mode": mode, "action_type": action_type,
           "params": params, "allowlist": allowlist, "org_id": org_id}

    handler = _ACTION_HANDLERS.get((mode, action_type)) or _ACTION_HANDLERS.get((None, action_type))
    if not handler:
        raise HTTPException(400, f"Unsupported action: {action_type}")
    return await handler(ctx)


# ── Per-action handlers ───────────────────────────────────────────────


async def _act_navigate_tab(ctx: dict) -> dict:
    tab = (ctx["params"].get("tab") or "").strip()
    if tab not in ctx["allowlist"][ctx["action_type"]]:
        raise HTTPException(400, f"Tab {tab!r} not allowed in {ctx['mode']}")
    return {"executed": True, "navigate_to_tab": tab}


async def _act_navigate(ctx: dict) -> dict:
    target = (ctx["params"].get("target") or "").strip()
    if target not in ctx["allowlist"][ctx["action_type"]]:
        raise HTTPException(400, f"Target {target!r} not allowed in {ctx['mode']}")
    return {"executed": True, "navigate_to": target}


async def _act_open_fault(ctx: dict) -> dict:
    fault_id = (ctx["params"].get("fault_id") or "").strip()
    fault = await db.issues.find_one(
        {"id": fault_id, "organization_id": ctx["org_id"]},
        {"_id": 0, "machine_type": 1, "issue_description": 1},
    )
    if not fault:
        raise HTTPException(404, "Fault not found in your organisation")
    label = (fault.get("machine_type") or fault.get("issue_description") or "Fault")[:40]
    return {"executed": True, "navigate_to_tab": "faults",
            "deep_link": {"kind": "fault", "id": fault_id, "label": label}}


async def _act_open_equipment(ctx: dict) -> dict:
    eq_id = (ctx["params"].get("equipment_id") or "").strip()
    eq = await db.equipment.find_one(
        {"id": eq_id, "organization_id": ctx["org_id"]}, {"_id": 0, "name": 1},
    )
    if not eq:
        raise HTTPException(404, "Equipment not found in your organisation")
    return {"executed": True, "navigate_to_tab": "equipment",
            "deep_link": {"kind": "equipment", "id": eq_id, "label": eq.get("name", "")}}


async def _act_open_member(ctx: dict) -> dict:
    member_id = (ctx["params"].get("member_id") or "").strip()
    m = await db.members.find_one(
        {"id": member_id, "organization_id": ctx["org_id"]},
        {"_id": 0, "first_name": 1, "last_name": 1},
    )
    if not m:
        raise HTTPException(404, "Member not found in your organisation")
    label = f"{(m.get('first_name') or '').strip()} {(m.get('last_name') or '').strip()}".strip() or "Member"
    return {"executed": True, "navigate_to_tab": "members",
            "deep_link": {"kind": "member", "id": member_id, "label": label}}


async def _act_open_plan(ctx: dict) -> dict:
    plan_id = (ctx["params"].get("plan_id") or "").strip()
    p = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": ctx["org_id"]}, {"_id": 0, "name": 1},
    )
    if not p:
        raise HTTPException(404, "Plan not found in your organisation")
    return {"executed": True, "navigate_to_tab": "plans",
            "deep_link": {"kind": "plan", "id": plan_id, "label": p.get("name", "Plan")}}


async def _act_instantiate_template(ctx: dict) -> dict:
    template_id = (ctx["params"].get("template_id") or "").strip()
    if template_id not in ctx["allowlist"][ctx["action_type"]]:
        raise HTTPException(400, f"Template {template_id!r} not allowed")
    from routes.marketing import instantiate_template
    return await instantiate_template(template_id=template_id, user=ctx["user"])


async def _act_resolve_issue(ctx: dict) -> dict:
    fault_id = (ctx["params"].get("fault_id") or "").strip()
    issue = await db.issues.find_one(
        {"id": fault_id, "organization_id": ctx["org_id"]},
        {"_id": 0, "status": 1, "machine_type": 1, "issue_description": 1},
    )
    if not issue:
        raise HTTPException(404, "Fault not found in your organisation")
    before_status = issue.get("status")
    target_label = (issue.get("machine_type") or issue.get("issue_description") or "Fault")[:60]
    user = ctx["user"]
    if before_status in ("resolved", "closed"):
        await _log_destructive_action(user=user, mode=ctx["mode"], action_type=ctx["action_type"],
            params=ctx["params"], target_kind="fault", target_id=fault_id, target_label=target_label,
            before_status=before_status, after_status=before_status, result=None, already_done=True)
        return {"executed": True, "already_done": True, "navigate_to_tab": "faults",
                "deep_link": {"kind": "fault", "id": fault_id, "label": "(already resolved)"}}
    now = _now()
    await db.issues.update_one(
        {"id": fault_id, "organization_id": ctx["org_id"]},
        {"$set": {"status": "resolved", "resolved_at": now, "updated_at": now,
                  "resolution_type": "ai_assistant",
                  "resolved_by": user.get("full_name") or user.get("id")},
         "$push": {"timeline": {"event": "status_changed_to_resolved",
                                 "timestamp": now,
                                 "by": user.get("full_name", "AI Assistant")}}},
    )
    await _log_destructive_action(user=user, mode=ctx["mode"], action_type=ctx["action_type"],
        params=ctx["params"], target_kind="fault", target_id=fault_id, target_label=target_label,
        before_status=before_status, after_status="resolved", result=None)
    return {"executed": True, "navigate_to_tab": "faults",
            "deep_link": {"kind": "fault", "id": fault_id, "label": "Resolved"}}


async def _act_freeze_membership(ctx: dict) -> dict:
    member_id = (ctx["params"].get("member_id") or "").strip()
    days_raw = ctx["params"].get("days", 30)
    try:
        days = int(days_raw)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 180))
    member = await db.members.find_one(
        {"id": member_id, "organization_id": ctx["org_id"]},
        {"_id": 0, "first_name": 1, "last_name": 1, "status": 1},
    )
    if not member:
        raise HTTPException(404, "Member not found in your organisation")
    target_label = f"{(member.get('first_name') or '').strip()} {(member.get('last_name') or '').strip()}".strip() or "Member"
    before_status = member.get("status")
    from routes.memberships import members_freeze  # type: ignore
    result = await members_freeze(member_id=member_id, body={"days": days}, user=ctx["user"])
    await _log_destructive_action(user=ctx["user"], mode=ctx["mode"], action_type=ctx["action_type"],
        params={**ctx["params"], "days": days}, target_kind="member", target_id=member_id,
        target_label=target_label, before_status=before_status, after_status="frozen",
        result=result)
    return {"executed": True, "navigate_to_tab": "members",
            "deep_link": {"kind": "member", "id": member_id, "label": f"Frozen {days}d"},
            "result": result}


async def _act_cancel_membership(ctx: dict) -> dict:
    member_id = (ctx["params"].get("member_id") or "").strip()
    immediate = bool(ctx["params"].get("immediate", False))
    reason = (ctx["params"].get("reason") or "member_request").strip() or "member_request"
    member = await db.members.find_one(
        {"id": member_id, "organization_id": ctx["org_id"]},
        {"_id": 0, "first_name": 1, "last_name": 1, "status": 1},
    )
    if not member:
        raise HTTPException(404, "Member not found in your organisation")
    target_label = f"{(member.get('first_name') or '').strip()} {(member.get('last_name') or '').strip()}".strip() or "Member"
    before_status = member.get("status")
    from routes.memberships import members_cancel  # type: ignore
    result = await members_cancel(member_id=member_id,
                                   body={"immediate": immediate, "reason": reason}, user=ctx["user"])
    await _log_destructive_action(user=ctx["user"], mode=ctx["mode"], action_type=ctx["action_type"],
        params={**ctx["params"], "immediate": immediate, "reason": reason},
        target_kind="member", target_id=member_id, target_label=target_label,
        before_status=before_status,
        after_status=("cancelled" if immediate else "cancel_pending"), result=result)
    return {"executed": True, "navigate_to_tab": "members",
            "deep_link": {"kind": "member", "id": member_id,
                          "label": "Cancelled" if immediate else "Cancel pending"},
            "result": result}


# Dispatch table — `(mode, action_type)`. `None` mode = action available
# in any allowlisted mode (e.g. navigate_tab, navigate).
_ACTION_HANDLERS = {
    (None, "navigate_tab"): _act_navigate_tab,
    (None, "navigate"): _act_navigate,
    ("operations", "open_fault"): _act_open_fault,
    ("operations", "open_equipment"): _act_open_equipment,
    ("operations", "resolve_issue"): _act_resolve_issue,
    ("memberships", "open_member"): _act_open_member,
    ("memberships", "open_plan"): _act_open_plan,
    ("memberships", "freeze_membership"): _act_freeze_membership,
    ("memberships", "cancel_membership"): _act_cancel_membership,
    ("marketing", "instantiate_template"): _act_instantiate_template,
}


# ════════════════════════════════════════════════════════════════════════
# Master Admin — AI Action Log
# ════════════════════════════════════════════════════════════════════════

_UNDO_WINDOW_SECONDS = 300  # 5 minutes


@router.get("/master-admin/assistant-actions")
async def assistant_action_log(
    days: int = 7,
    limit: int = 100,
    mode: str | None = None,
    action_type: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Return the audit trail of every Claude-initiated destructive action.
    Master Admin (and Pulse Master Admin, scoped) only."""
    from routes.master_admin import require_master_admin, _resolve_pulse_scope_org_ids
    require_master_admin(user)

    days = max(1, min(int(days or 7), 90))
    limit = max(1, min(int(limit or 100), 500))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    q: dict = {"executed_at": {"$gte": cutoff_iso}}
    if mode and mode in MODE_REGISTRY:
        q["mode"] = mode
    if action_type and action_type in _DESTRUCTIVE_TYPES:
        q["action_type"] = action_type

    pulse_org_ids = await _resolve_pulse_scope_org_ids(user)
    if pulse_org_ids is not None:
        q["organization_id"] = {"$in": pulse_org_ids}

    rows = await db.assistant_action_log.find(q, {"_id": 0}).sort([("executed_at", -1)]).limit(limit).to_list(limit)

    # Per-type rollup for the dashboard headline tiles.
    by_type: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    distinct_users: set[str] = set()
    distinct_orgs: set[str] = set()
    for r in rows:
        by_type[r.get("action_type", "?")] = by_type.get(r.get("action_type", "?"), 0) + 1
        by_mode[r.get("mode", "?")] = by_mode.get(r.get("mode", "?"), 0) + 1
        if r.get("user_id"):
            distinct_users.add(r["user_id"])
        if r.get("organization_id"):
            distinct_orgs.add(r["organization_id"])

    return {
        "rows": rows,
        "totals": {
            "events": len(rows),
            "by_type": by_type,
            "by_mode": by_mode,
            "distinct_users": len(distinct_users),
            "distinct_orgs": len(distinct_orgs),
        },
        "scoped": pulse_org_ids is not None,
        "window_days": days,
        "undo_window_seconds": _UNDO_WINDOW_SECONDS,
    }


# ── Undo handlers ─────────────────────────────────────────────────────


async def _undo_resolve_issue(*, target_id: str, org_id: str, before_status: str, now: str, user: dict) -> None:
    result = await db.issues.update_one(
        {"id": target_id, "organization_id": org_id, "status": "resolved"},
        {"$set": {"status": before_status, "resolved_at": None,
                  "resolved_by": None, "resolution_type": None,
                  "updated_at": now},
         "$push": {"timeline": {"event": f"undo_resolve_to_{before_status}",
                                 "timestamp": now,
                                 "by": user.get("full_name", "Master Admin")}}},
    )
    if result.modified_count == 0:
        raise HTTPException(409, "Fault state has changed since the action — manual review required")


async def _undo_freeze_membership(*, target_id: str, org_id: str, now: str, user: dict, **_) -> None:
    mm = await db.member_memberships.find_one(
        {"member_id": target_id, "organization_id": org_id, "status": "frozen"},
        {"_id": 0, "id": 1},
    )
    if not mm:
        raise HTTPException(409, "Membership is no longer frozen — manual review required")
    await db.member_memberships.update_one(
        {"id": mm["id"]},
        {"$set": {"status": "active", "frozen_from": None, "frozen_until": None},
         "$push": {"audit_log": {"at": now, "actor_id": user.get("id"),
                                   "action": "freeze_undone",
                                   "via": "ai_action_undo"}}},
    )


async def _undo_cancel_membership(*, target_id: str, org_id: str, before_status: str,
                                   now: str, user: dict, row: dict) -> None:
    immediate = bool((row.get("params") or {}).get("immediate"))
    mm = await db.member_memberships.find_one(
        {"member_id": target_id, "organization_id": org_id},
        {"_id": 0, "id": 1, "status": 1},
    )
    if not mm:
        raise HTTPException(409, "Membership not found — manual review required")
    if immediate:
        await db.member_memberships.update_one(
            {"id": mm["id"]},
            {"$set": {"status": "active", "cancel_effective_date": None,
                      "cancel_reason": None},
             "$push": {"audit_log": {"at": now, "actor_id": user.get("id"),
                                       "action": "cancel_undone_immediate",
                                       "via": "ai_action_undo"}}},
        )
        await db.members.update_one(
            {"id": target_id, "organization_id": org_id},
            {"$set": {"status": before_status or "active"}},
        )
    else:
        await db.member_memberships.update_one(
            {"id": mm["id"]},
            {"$set": {"billing_status": None, "cancel_effective_date": None,
                      "cancel_reason": None},
             "$push": {"audit_log": {"at": now, "actor_id": user.get("id"),
                                       "action": "cancel_undone_notice",
                                       "via": "ai_action_undo"}}},
        )


_UNDO_HANDLERS = {
    "resolve_issue": _undo_resolve_issue,
    "freeze_membership": _undo_freeze_membership,
    "cancel_membership": _undo_cancel_membership,
}


def _ensure_undoable(row: dict) -> datetime:
    """Validate the action row is within the undo window. Returns the
    parsed `executed_at` timestamp."""
    if row.get("undone_at"):
        raise HTTPException(400, "Action has already been undone")
    if row.get("already_done"):
        raise HTTPException(400, "Original action was a no-op — nothing to undo")
    try:
        executed_at = datetime.fromisoformat(row["executed_at"].replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(400, "Action timestamp is malformed") from exc
    age_s = (datetime.now(timezone.utc) - executed_at).total_seconds()
    if age_s > _UNDO_WINDOW_SECONDS:
        raise HTTPException(400, f"Undo window expired ({_UNDO_WINDOW_SECONDS}s)")
    if age_s < 0:
        raise HTTPException(400, "Action is in the future — clock skew?")
    return executed_at


@router.post("/master-admin/assistant-actions/{action_id}/undo")
async def assistant_action_undo(action_id: str, user: dict = Depends(get_current_user)):
    """Reverse a destructive AI action within the configured undo window."""
    from routes.master_admin import require_master_admin, _resolve_pulse_scope_org_ids
    require_master_admin(user)

    row = await db.assistant_action_log.find_one({"id": action_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Action not found")

    pulse_org_ids = await _resolve_pulse_scope_org_ids(user)
    if pulse_org_ids is not None and row.get("organization_id") not in pulse_org_ids:
        raise HTTPException(404, "Action not found")

    _ensure_undoable(row)

    action_type = row.get("action_type")
    handler = _UNDO_HANDLERS.get(action_type)
    if not handler:
        raise HTTPException(400, f"Cannot undo action_type {action_type!r}")

    now = _now()
    await handler(
        target_id=row.get("target_id"),
        org_id=row.get("organization_id"),
        before_status=row.get("before_status") or "open",
        now=now,
        user=user,
        row=row,
    )

    await db.assistant_action_log.update_one(
        {"id": action_id},
        {"$set": {"undone_at": now,
                  "undone_by_user_id": user.get("id"),
                  "undone_by_user_name": user.get("full_name") or user.get("email")}},
    )
    return {"ok": True, "undone_at": now, "action_type": action_type, "target_id": row.get("target_id")}


__all__ = ["router"]
