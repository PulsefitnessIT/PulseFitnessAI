"""Always-visible AI assistant: ask, chat, execute-action, history.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.auth_guards import assert_role
from utils.database import db
from utils.ai_guardrails import sanitize_prompt, wrap_user_input
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _new_id,
    _now_iso,
    _org_id,
    logger,
)
from routes.marketing.templates import CAMPAIGN_TEMPLATES, instantiate_template

router = APIRouter()


# ───────────────────────── AI Assistant (always-visible) ───────────────

@router.post("/marketing/assistant/ask", dependencies=[Depends(require_module("marketing"))])
async def assistant_ask(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Lightweight context-aware suggester. Takes the current page name and
    a question, returns up to 3 suggested actions. Phase 1 uses deterministic
    rules; Phase 2 wires Claude Sonnet for free-form Q&A (see /chat below)."""
    org_id = await _org_id(user)
    page = (body.get("page") or "").lower()
    question = (body.get("question") or "").lower().strip()

    suggestions: list[dict] = []
    if "audience" in page or "audience" in question:
        suggestions.append({
            "id": "tip-segment",
            "label": "Try plain-English audience builder",
            "body": "Type a description like \"high spenders at risk of churning\" — AI will draft the rules for you.",
            "action": "focus_ai_input",
        })
        suggestions.append({
            "id": "tip-snapshot",
            "label": "Use snapshot audiences for one-off campaigns",
            "body": "Snapshot freezes the contact list — useful when you want to send to exactly 'these people' and not have it auto-update.",
            "action": None,
        })
    if "campaign" in page or "send" in question:
        templates_count = len(CAMPAIGN_TEMPLATES)
        suggestions.append({
            "id": "tip-templates",
            "label": f"Use one of {templates_count} quick-start templates",
            "body": "Pre-built audiences + subject + body + creative brief for welcome / win-back / class promo / PT upsell / failed payment / referral.",
            "action": "open_templates",
        })
    if "creative" in page or "image" in question or "poster" in question:
        suggestions.append({
            "id": "tip-prompt",
            "label": "Describe the energy, not the photo",
            "body": "AI does best with mood prompts — try \"high-energy spin Saturday morning\" instead of \"a poster of bikes\".",
            "action": None,
        })
    if not suggestions:
        # Default tips based on org state.
        last_camp = await db.marketing_campaigns.find_one(
            {"organization_id": org_id, "status": "sent"},
            {"_id": 0, "metrics": 1, "name": 1}, sort=[("sent_at", -1)],
        )
        if last_camp:
            sent = (last_camp.get("metrics") or {}).get("sent", 0) or 1
            opened = (last_camp.get("metrics") or {}).get("opened", 0)
            rate = opened / sent
            if rate < 0.15:
                suggestions.append({
                    "id": "tip-subject-ab",
                    "label": "Try shorter subject lines next time",
                    "body": f"Your last campaign opened at {round(rate*100,1)}%. Subject lines under 40 chars typically lift opens by 8-15%.",
                    "action": None,
                })
        suggestions.append({
            "id": "tip-quick-start",
            "label": "Send your first campaign in 60 seconds",
            "body": "Pick a quick-start template, AI fills in the gym-specific details, hit send.",
            "action": "open_templates",
        })
    return {"suggestions": suggestions[:3]}


# ════════════════════════════════════════════════════════════════════════
# AI Assistant — free-form chat grounded on the org's real metrics
# ════════════════════════════════════════════════════════════════════════
#
# Backed by Claude Sonnet 4.5 via emergentintegrations. We build a fresh
# system message per session that injects the org's live numbers — last
# 5 campaigns + their open/click/conversion rates, top 5 audiences with
# size, journey stats, brand kit colours — so the model can give
# answers grounded in the user's reality rather than generic advice.
#
# Chat history is persisted in `marketing_assistant_chats` so the
# conversation survives page reloads and continues across sessions.


async def _build_assistant_context(org_id: str) -> str:
    """Render the org's recent marketing performance into a compact context
    block for the LLM. Kept under ~2k tokens so we don't blow context."""
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym_name = org.get("name") or "the gym"

    # Last 5 campaigns (any status)
    camps = await db.marketing_campaigns.find(
        {"organization_id": org_id}, {"_id": 0, "name": 1, "status": 1, "channel": 1, "metrics": 1, "sent_at": 1, "created_at": 1},
    ).sort([("created_at", -1)]).limit(5).to_list(5)
    camps_lines = []
    for c in camps:
        m = c.get("metrics") or {}
        sent = m.get("sent", 0) or 0
        opened = m.get("opened", 0) or 0
        clicked = m.get("clicked", 0) or 0
        rate_o = round((opened / sent) * 100, 1) if sent else 0
        rate_c = round((clicked / sent) * 100, 1) if sent else 0
        camps_lines.append(
            f"- {c.get('name','(unnamed)')} [{c.get('status','draft')}] · sent={sent} · opens={rate_o}% · clicks={rate_c}%"
        )

    # Audience snapshot
    auds = await db.marketing_audiences.find(
        {"organization_id": org_id}, {"_id": 0, "name": 1, "estimated_size": 1, "type": 1},
    ).sort([("estimated_size", -1)]).limit(5).to_list(5)
    auds_lines = [f"- {a.get('name')} · {a.get('estimated_size', 0)} contacts ({a.get('type','dynamic')})" for a in auds]

    # Journey stats
    jstats = await db.marketing_journeys.aggregate([
        {"$match": {"organization_id": org_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(10)
    j_summary = ", ".join(f"{j['_id']}={j['count']}" for j in jstats) or "no journeys yet"

    # 30-day attribution
    revenue_30d = await db.marketing_attributions.aggregate([
        {"$match": {"organization_id": org_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_gbp"}}},
    ]).to_list(1)
    rev = (revenue_30d[0] if revenue_30d else {}).get("total") or 0

    return (
        f"# Live data for {gym_name}\n\n"
        f"## Recent campaigns ({len(camps)}):\n"
        + ("\n".join(camps_lines) if camps_lines else "- No campaigns yet")
        + f"\n\n## Top audiences ({len(auds)}):\n"
        + ("\n".join(auds_lines) if auds_lines else "- No audiences yet")
        + f"\n\n## Journeys: {j_summary}"
        + f"\n## Attributed revenue (all-time): £{rev:,.2f}\n"
    )


@router.post("/marketing/assistant/chat")
async def assistant_chat(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Free-form Q&A grounded in the org's real metrics, powered by Claude
    Sonnet 4.5. Conversation history persists per session_id. Rate-limited
    to 15/min per user to protect LLM budget."""
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"mk_chat:{user['id']}", max_requests=15, window_seconds=60)

    org_id = await _org_id(user)
    session_id = (body.get("session_id") or "").strip() or _new_id()
    # Iter 220bo · F-220bo-2 — cap user input length so a 100k-char
    # message cannot burn through the org's LLM budget in one shot.
    raw_message = (body.get("message") or "").strip()
    if len(raw_message) > 4000:
        raise HTTPException(
            400, f"message too long ({len(raw_message):,} chars); max 4,000.",
        )
    message = sanitize_prompt(raw_message, max_chars=4000)
    if not message:
        raise HTTPException(400, "Message is required")

    # Load prior turns (exclude system / context — we always rebuild fresh).
    history = await db.marketing_assistant_chats.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0},
    ) or {"session_id": session_id, "user_id": user["id"], "organization_id": org_id, "turns": []}

    context = await _build_assistant_context(org_id)
    system_message = (
        "You are Pulse Fitness Marketing Copilot — an AI assistant embedded in a "
        "marketing platform built for fitness operators (Pulse Pro and "
        "Pulse Fitness). You give concise, actionable answers grounded in the "
        "user's real, live data (provided below).\n\n"
        "## SCOPE GUARDRAIL — CRITICAL\n"
        "You ONLY answer questions related to topics within the Pulse Fitness / "
        "Pulse Fitness platform:\n"
        "- Marketing: campaigns, audiences, segmentation, email/SMS, "
        "creatives, journeys, performance, attribution, A/B tests, "
        "deliverability, social media\n"
        "- Memberships: members, plans, sign-ups, retention, churn, "
        "lifetime value, classes, bookings, waitlists, ads\n"
        "- Operations: equipment, faults, maintenance, suppliers, parts, "
        "service tickets, sites, technicians, downtime\n"
        "- Business: revenue, growth, billing, integrations (Sage, Sicon, "
        "Orbit 4, Stripe, Resend, Meta), gym industry benchmarks\n\n"
        "If the user asks about anything OUTSIDE these topics — general "
        "knowledge, coding help, recipes, weather, news, geography, "
        "personal life advice, jokes, unrelated software — politely "
        "decline in ONE short sentence and redirect them to a relevant "
        "platform topic. Do NOT engage with the off-topic question even "
        "partially. Example refusal: \"I'm focused on your marketing and "
        "gym operations — happy to help with campaigns, members, or "
        "performance instead. What would you like to look at?\"\n\n"
        "## TONE & FORMAT\n"
        "Tone: friendly, expert, never patronising. Use bullet points "
        "sparingly. Answer in British English. Keep responses under 150 "
        "words unless the user explicitly asks for detail.\n\n"
        "When the user asks about performance, refer to the actual numbers "
        "below. When suggesting an action (e.g. \"create a winback campaign\"), "
        "tell the user which tab to open (Audiences / Campaigns / Creative / "
        "Journeys / Performance). Never invent metrics.\n\n"
        "## ACTION PROTOCOL\n"
        "When you recommend a concrete in-app step the user can take RIGHT "
        "NOW, append a single JSON action block at the very end of your "
        "reply, on its own line, fenced like this:\n"
        "```action\n"
        "{\"type\": \"<TYPE>\", \"label\": \"<button label, max 32 chars>\", "
        "\"params\": { ... }}\n"
        "```\n"
        "The platform will render this as a one-click button. Use AT MOST "
        "ONE action per response. Allowed action types:\n"
        "- `navigate_tab` — switch the active tab. params: {\"tab\": "
        "\"insights|audiences|campaigns|creative|journeys|social|performance\"}\n"
        "- `instantiate_template` — create a campaign from a built-in "
        "template. params: {\"template_id\": "
        "\"welcome_new_member|winback|class_promo|pt_upsell|"
        "failed_payment_recovery|referral_push\"}\n"
        "- `clear_demo_data` — remove tour-seeded demo records. params: {}\n"
        "Don't include actions for purely informational answers.\n\n"
        f"{context}"
    )

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI assistant unavailable — LLM key not configured")

    answer = ""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=system_message,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        # Replay prior turns so Claude has the conversational context.
        # The library auto-tracks history per session_id, but on a fresh
        # process restart we need to seed it manually.
        for turn in history.get("turns", []):
            if turn.get("role") == "user":
                # Re-send each prior user message — library only stores within
                # its own runtime memory, so this hydrates conversation state.
                # We DON'T await responses for these; just send().
                pass  # The library accumulates; we send only the new message.
        # Iter 220bo · F-220bo-5 — wrap user input in a delimited
        # block + injection-guard header so prompt-injection attempts
        # ("ignore previous instructions...") are visibly outside the
        # system-message authority zone.
        answer = await chat.send_message(UserMessage(text=wrap_user_input(message)))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[marketing] claude chat failed: %s", exc)
        # Fallback to a deterministic apology so the UX still works.
        answer = (
            "I'm having trouble reaching the AI service right now — please try "
            "again in a moment. In the meantime, you can use the suggestion "
            "tiles above for quick wins on this tab."
        )

    now = _now_iso()
    # Parse out optional ```action {...}``` block at end of response.
    action = None
    answer_clean = answer
    try:
        import re
        m = re.search(r"```action\s*(\{.+?\})\s*```", answer, flags=re.DOTALL)
        if m:
            import json as _json
            payload = _json.loads(m.group(1))
            allowed_types = {"navigate_tab", "instantiate_template", "clear_demo_data"}
            if isinstance(payload, dict) and payload.get("type") in allowed_types:
                action = {
                    "type": payload["type"],
                    "label": (payload.get("label") or "Do it")[:48],
                    "params": payload.get("params") or {},
                }
            answer_clean = (answer[: m.start()] + answer[m.end():]).strip()
    except Exception as exc:  # pragma: no cover
        logger.info("[marketing] action parse failed: %s", exc)

    history.setdefault("turns", []).extend([
        {"role": "user", "content": message, "at": now},
        {"role": "assistant", "content": answer_clean, "action": action, "at": now},
    ])
    history["updated_at"] = now
    history["organization_id"] = org_id
    await db.marketing_assistant_chats.update_one(
        {"session_id": session_id, "user_id": user["id"]}, {"$set": history}, upsert=True,
    )
    # Trim history to last 40 turns so storage stays bounded.
    if len(history["turns"]) > 40:
        await db.marketing_assistant_chats.update_one(
            {"session_id": session_id, "user_id": user["id"]},
            {"$set": {"turns": history["turns"][-40:]}},
        )

    await db.marketing_subscriptions.update_one(
        {"organization_id": org_id}, {"$inc": {"usage_this_period.ai_generations": 1}},
    )

    return {"session_id": session_id, "answer": answer_clean, "action": action, "model": "claude-sonnet-4-5-20250929"}


@router.post("/marketing/assistant/execute-action")
async def assistant_execute_action(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Run a one-click action recommended by the AI Assistant.
    Returns metadata the frontend uses to navigate / show toasts."""
    # Iter 220bo · F-220bo-1 — operator-only. The chat suggestion
    # surface remains open to all members, but DB-mutating actions
    # (notably ``clear_demo_data``) require an operator/owner/manager
    # role so a prompt-injected suggestion cannot trick a non-operator
    # into deleting demo data. Master / Pulse admins always pass.
    assert_role(user, ["operator", "owner", "manager", "admin", "marketing_admin"])
    org_id = await _org_id(user)
    action_type = (body.get("type") or "").strip()
    params = body.get("params") or {}

    if action_type == "navigate_tab":
        tab = (params.get("tab") or "").strip()
        if tab not in {"insights", "audiences", "campaigns", "creative", "journeys", "social", "performance"}:
            raise HTTPException(400, f"Unsupported tab: {tab}")
        return {"executed": True, "navigate_to_tab": tab}

    if action_type == "instantiate_template":
        template_id = (params.get("template_id") or "").strip()
        valid = {"welcome_new_member", "winback", "class_promo", "pt_upsell",
                 "failed_payment_recovery", "referral_push"}
        if template_id not in valid:
            raise HTTPException(400, f"Unknown template: {template_id}")
        # Reuse the existing instantiate handler logic by calling it directly.
        return await instantiate_template(template_id=template_id, body={}, user=user)

    if action_type == "clear_demo_data":
        res_a = await db.marketing_audiences.delete_many({"organization_id": org_id, "tags": "demo_tour"})
        res_c = await db.marketing_campaigns.delete_many({"organization_id": org_id, "tags": "demo_tour"})
        res_j = await db.marketing_journeys.delete_many({"organization_id": org_id, "tags": "demo_tour"})
        res_cr = await db.marketing_creative_assets.delete_many({"organization_id": org_id, "tags": "demo_tour"})
        return {
            "executed": True,
            "audiences_removed": res_a.deleted_count,
            "campaigns_removed": res_c.deleted_count,
            "journeys_removed": res_j.deleted_count,
            "creatives_removed": res_cr.deleted_count,
        }

    raise HTTPException(400, f"Unsupported action type: {action_type}")


@router.get("/marketing/assistant/chat/{session_id}")
async def assistant_chat_history(session_id: str, user: dict = Depends(get_current_user)):
    """Load saved conversation turns for a session."""
    record = await db.marketing_assistant_chats.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0},
    )
    return {"turns": (record or {}).get("turns", [])}



# ───────────────────────── Campaign Wizard AI Copilot ──────────────────

# Valid wizard steps (mirrors STEP_DEFS in frontend CampaignWizard.js).
_WIZARD_STEPS = {"goal", "audience", "creative", "schedule", "review"}

# Valid goal ids (mirrors GOALS in frontend CampaignWizard.js). The goal
# `custom` is accepted so Claude can still provide tailored copy for a
# user-defined objective.
_WIZARD_GOALS = {
    "fill-classes", "win-back", "promote-class", "upsell-pt", "retention", "custom",
}


def _wizard_fallback(step: str, goal: str | None) -> dict:
    """Deterministic fallback suggestions used when the LLM is unreachable.

    Matches the shape returned by the live endpoint so the frontend renders
    the same UI regardless of whether AI succeeded.
    """
    base = {
        "tip": "",
        "suggestions": [],
        "copy": None,
    }
    if step == "goal":
        base["tip"] = (
            "Pick the outcome you want. Fill empty classes works well mid-week; "
            "Win back inactive members is great if engagement has dipped recently."
        )
        base["suggestions"] = [
            {"label": "Fill empty classes", "detail": "Boost attendance on under-booked slots", "applyId": "fill-classes"},
            {"label": "Win back inactive members", "detail": "Re-engage members dormant 30+ days", "applyId": "win-back"},
            {"label": "Upsell Personal Training", "detail": "Offer 1:1 to consistent attendees", "applyId": "upsell-pt"},
        ]
    elif step == "audience":
        base["tip"] = "Highly targeted lists (50–200 people) beat blasts to everyone — every time."
    elif step == "creative":
        base["tip"] = "Keep subjects under 45 characters. Lead with a benefit, not a discount."
        if goal:
            base["copy"] = _wizard_default_copy(goal)
    elif step == "schedule":
        base["tip"] = "Tuesdays at 7 AM tend to perform best for gym email. Avoid Friday evenings."
        base["suggestions"] = [
            {"label": "Best-time send (Tue 7 AM)", "detail": "Predicted +14% open rate", "applyTiming": "best-time"},
        ]
    else:
        base["tip"] = "Quick pre-flight check — placeholders substituted, no spam triggers."
    return base


def _wizard_default_copy(goal: str) -> dict:
    return {
        "fill-classes":  {"subject": "Your class is waiting — grab your spot",                  "body": "Hey {{first_name}}, your usual 5pm slot has 3 spaces left today — book before it sells out."},
        "win-back":      {"subject": "We miss you — 20% off your comeback week",                "body": "It's been a minute. Here's 20% off any class or day pass to help you bounce back this week."},
        "promote-class": {"subject": "New class alert — {{class_name}} just launched",          "body": "Based on your last 4 bookings, you'll love this one. First session is on the house for early signups."},
        "upsell-pt":     {"subject": "Ready to level up? Try 1:1 with a coach",                  "body": "You've been crushing it. Pair it with a free PT intro to hit the next gear — no pressure, no commitment."},
        "retention":     {"subject": "You've done X classes this quarter — nice.",              "body": "Just wanted to drop in and say well done. Here's a small token of appreciation from all of us."},
        "custom":        {"subject": "",                                                         "body": ""},
    }.get(goal, {"subject": "", "body": ""})


@router.post("/marketing/wizard-copilot", dependencies=[Depends(require_module("marketing"))])
async def wizard_copilot(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Generate Claude-powered AI copilot suggestions for the CampaignWizard.
    Rate-limited to 30/min per user to protect LLM budget.

    Request body::

        {
          "step": "goal" | "audience" | "creative" | "schedule" | "review",
          "goal": "fill-classes" | ... | null,
          "audience": {"id": "...", "label": "...", "approx": "..."} | null,
          "brand_name": "PulseFitness" | null,
          "channel": "email" | "sms" | null
        }

    Response::

        {
          "tip": "<1-2 sentence expert advice>",
          "suggestions": [
            {"label": "...", "detail": "...", "applyId"|"applyTiming": "..."}
          ],
          "copy": {"subject": "...", "body": "..."}   # only for step=creative
        }

    Falls back to a deterministic scaffold if the LLM call fails so the
    wizard stays usable offline / on quota exhaustion.
    """
    step = (body.get("step") or "").strip().lower()
    goal = (body.get("goal") or "").strip().lower() or None
    audience = body.get("audience") or None
    brand_name = (body.get("brand_name") or "").strip() or "your gym"
    channel = (body.get("channel") or "email").strip().lower()

    if step not in _WIZARD_STEPS:
        raise HTTPException(400, f"Unsupported step: {step}")
    if goal and goal not in _WIZARD_GOALS:
        # Permit custom user-typed goals as-is (treated as 'custom').
        goal = "custom"

    # Rate-limit — prevents wizard hammering and LLM-budget blow-outs.
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"wiz_cop:{user['id']}", max_requests=30, window_seconds=60)

    org_id = await _org_id(user)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        # Return a fallback rather than 503 — the wizard stays usable.
        return _wizard_fallback(step, goal)

    # Build per-step prompts so Claude gives focused, short output.
    step_prompt = {
        "goal": (
            "The user is about to pick a campaign GOAL. Recommend the best "
            "goal for a gym right now in 1 short tip (<=30 words) and return "
            "three prioritised goal suggestions."
        ),
        "audience": (
            f"The user picked the goal `{goal}`. Recommend WHO to send to in "
            "1 short tip (<=30 words). Return no suggestion objects."
        ),
        "creative": (
            f"The user picked the goal `{goal}`. Write a compelling "
            f"{channel.upper()} campaign. Include BOTH a short subject line "
            "(<=45 chars, no emojis) AND a body (<=60 words). "
            "Use the placeholders {{first_name}} and {{company_name}} naturally. "
            f"Brand voice: warm, confident, UK English. Brand: {brand_name}."
        ),
        "schedule": (
            "The user is picking a SEND TIME. Recommend the best time slot in "
            "1 short tip (<=25 words). Return suggestion objects with "
            "`applyTiming` set to `best-time`."
        ),
        "review": (
            "The user is about to LAUNCH. Give a 1-line pre-flight reassurance "
            "(<=25 words). No suggestions needed."
        ),
    }[step]

    system_message = (
        "You are Pulse Fitness's Marketing Copilot — an elite gym-industry "
        "growth consultant embedded inside a campaign builder. Respond in UK "
        "English, be punchy and concrete, and never use emojis. "
        "You MUST return STRICTLY VALID JSON — no markdown, no prose, no "
        "code fences. The JSON schema is:\n\n"
        "{\n"
        '  "tip": "<short expert tip, <=30 words>",\n'
        '  "suggestions": [ {"label": "...", "detail": "...", "applyId": "...", "applyTiming": "..."} ],\n'
        '  "copy": {"subject": "<<=45 chars>", "body": "<<=60 words>"} | null\n'
        "}\n\n"
        "Rules:\n"
        "- For step=goal: suggestions[].applyId MUST be one of "
        "fill-classes|win-back|promote-class|upsell-pt|retention. "
        "Include 2–3 suggestions.\n"
        "- For step=schedule: suggestions[].applyTiming MUST be `best-time`. "
        "Include exactly 1 suggestion.\n"
        "- For step=creative: populate the `copy` object; suggestions=[].\n"
        "- For step=audience and step=review: suggestions=[]; copy=null.\n"
        "- Never return null for `tip`."
    )

    audience_line = (
        f"Current audience: {audience.get('label')} ({audience.get('approx')})."
        if audience else "Current audience: (not yet selected)."
    )
    user_prompt = (
        f"Step: {step}\n"
        f"Goal: {goal or '(not yet selected)'}\n"
        f"{audience_line}\n"
        f"Channel: {channel}\n\n"
        f"{step_prompt}\n\n"
        "Respond with JSON only — no commentary."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key,
            session_id=f"mkt-wizard-{org_id}-{step}",
            system_message=system_message,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_prompt))
    except Exception as exc:
        logger.warning("[marketing] wizard copilot LLM failed: %s", exc)
        return _wizard_fallback(step, goal)

    # Parse JSON — tolerate stray ```json fences.
    import json as _json
    import re as _re
    text = (raw or "").strip()
    m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=_re.DOTALL)
    if m:
        text = m.group(1)
    try:
        parsed = _json.loads(text)
    except Exception:
        logger.warning("[marketing] wizard copilot returned invalid JSON: %s", text[:200])
        return _wizard_fallback(step, goal)

    # Clean / validate shape.
    tip = (parsed.get("tip") or "").strip() or _wizard_fallback(step, goal)["tip"]
    suggestions_in = parsed.get("suggestions") or []
    suggestions: list[dict] = []
    if isinstance(suggestions_in, list):
        for s in suggestions_in[:3]:
            if not isinstance(s, dict):
                continue
            item = {
                "label": (s.get("label") or "").strip()[:80],
                "detail": (s.get("detail") or "").strip()[:140],
            }
            if step == "goal" and s.get("applyId") in _WIZARD_GOALS:
                item["applyId"] = s["applyId"]
                suggestions.append(item)
            elif step == "schedule":
                item["applyTiming"] = "best-time"
                suggestions.append(item)
    copy = None
    if step == "creative":
        copy_in = parsed.get("copy") or {}
        if isinstance(copy_in, dict):
            copy = {
                "subject": (copy_in.get("subject") or "").strip()[:120],
                "body": (copy_in.get("body") or "").strip()[:1200],
            }
        if not copy or not copy.get("subject"):
            copy = _wizard_default_copy(goal or "custom")

    # Track AI usage so billing stays accurate.
    try:
        await db.marketing_subscriptions.update_one(
            {"organization_id": org_id},
            {"$inc": {"usage_this_period.ai_generations": 1}},
        )
    except Exception:
        pass

    return {
        "tip": tip,
        "suggestions": suggestions,
        "copy": copy,
        "model": "claude-sonnet-4-5-20250929",
    }
