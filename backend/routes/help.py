"""GymAxis Help Centre — API surface.

Endpoints
---------
GET  /api/help/categories          → list of 10 canonical categories
GET  /api/help/guides              → list guide cards (role/category/module filters)
GET  /api/help/guides/{id}         → full guide body
GET  /api/help/search?q=...        → keyword search across the guide corpus
POST /api/help/ask                 → AI assistant (Claude Sonnet, guide-grounded)
GET  /api/help/setup-checklist     → first-login setup checklist with live progress

Design notes
------------
- Role-based visibility is applied in `help_data.visible_to_role`.
- The AI assistant is grounded: Claude only answers from the guide corpus
  (user picked option (a) — "Guide-grounded only, won't hallucinate
  outside GymAxis").
- All endpoints require an authenticated user (no public crawling).
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from utils.auth import get_current_user
from utils.database import db

from routes.help_data import (
    CATEGORIES,
    GUIDES,
    guide_by_id,
    list_guides,
    search_guides,
    visible_to_role,
)


# ── CRM-token fallback (iter 215n) ─────────────────────────────────────────
# CRM users live in `db.crm_users`, not `db.users`, so the standard
# `get_current_user` rejects valid CRM tokens with "User not found".
# Help content is generic platform documentation and is safe for any
# authenticated principal — operator OR CRM. This dependency tries the
# operator path first and falls back to the CRM user table.
async def get_current_principal(request: Request) -> dict:
    """Authenticate either as an operator (db.users) or a CRM user
    (db.crm_users). Help endpoints accept both."""
    from utils.auth import verify_token, AUTH_COOKIE_NAME  # type: ignore
    auth_header = request.headers.get("Authorization") or ""
    bearer = auth_header.split(" ", 1)[1].strip() if auth_header.lower().startswith("bearer ") else ""
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    token = bearer or cookie or ""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user:
        return user
    crm_user = await db.crm_users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if crm_user:
        crm_user.setdefault("role", "manager")
        crm_user["_principal_kind"] = "crm"
        return crm_user
    raise HTTPException(status_code=401, detail="User not found")

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_role(user: dict) -> str:
    """Flatten the few role-ish fields on the user record into one string."""
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return "master_admin"
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager", "staff", "gym_floor"):
        return role
    return "staff"  # safe default


def _user_brand(user: dict) -> dict:
    """Return brand metadata for the current user.

    Pulse Fitness operators (account_type=pulse_pro|lite) must NEVER see
    "GymAxis" branding — they're sold a single product called Pulse
    Fitness, and confusing the two brands is a contractual issue.

    Master admins and standard SaaS customers see the GymAxis branding.
    """
    account_type = (user.get("account_type") or "").lower()
    is_pulse = account_type in ("pulse_pro", "lite")
    if is_pulse:
        return {
            "id": "pulse",
            "name": "Pulse Fitness",
            "assistant_name": "Ask Pulse Fitness",
        }
    return {
        "id": "gymaxis",
        "name": "GymAxis",
        "assistant_name": "Ask GymAxis",
    }


def _whitelabel(text: str | None, brand: dict) -> str | None:
    """Replace any incidental 'GymAxis' mentions in user-facing copy
    with the user's brand name. Cheap, deterministic, idempotent.

    Used at the API boundary so we never have to maintain a separate
    Pulse-branded corpus — guide editorial stays single-source.
    """
    if text is None:
        return None
    if brand.get("id") == "gymaxis":
        return text
    out = text
    for needle in ("GymAxis AI", "GymAxis", "gymaxis"):
        out = out.replace(needle, brand["name"])
    return out


def _whitelabel_guide(guide: dict, brand: dict) -> dict:
    """Walk a guide dict and white-label every string field for the
    user's brand. Returns a new dict — never mutates the source.
    """
    if brand.get("id") == "gymaxis":
        return guide
    new = dict(guide)
    new["title"] = _whitelabel(guide.get("title"), brand)
    new["description"] = _whitelabel(guide.get("description"), brand)
    if isinstance(guide.get("steps"), list):
        new["steps"] = [
            {**s, "title": _whitelabel(s.get("title"), brand), "body": _whitelabel(s.get("body"), brand), "ui_hint": _whitelabel(s.get("ui_hint"), brand)}
            for s in guide["steps"]
        ]
    if isinstance(guide.get("tips"), list):
        new["tips"] = [_whitelabel(t, brand) for t in guide["tips"]]
    if isinstance(guide.get("mistakes"), list):
        new["mistakes"] = [_whitelabel(m, brand) for m in guide["mistakes"]]
    if isinstance(guide.get("walkthrough"), dict):
        wt = dict(guide["walkthrough"])
        if isinstance(wt.get("steps"), list):
            wt["steps"] = [
                {**s, "title": _whitelabel(s.get("title"), brand), "content": _whitelabel(s.get("content"), brand)}
                for s in wt["steps"]
            ]
        new["walkthrough"] = wt
    return new


@router.get("/help/categories")
async def help_categories(user: dict = Depends(get_current_principal)):
    """Return the 10 canonical help categories with per-category counts."""
    role = _user_role(user)
    brand = _user_brand(user)
    counts: dict[str, int] = {c["id"]: 0 for c in CATEGORIES}
    for g in GUIDES:
        if not visible_to_role(g, role):
            continue
        cid = g.get("category")
        if cid in counts:
            counts[cid] += 1
    return {
        "categories": [{**c, "count": counts.get(c["id"], 0)} for c in CATEGORIES],
        "role": role,
        "brand": brand,
    }


@router.get("/help/guides")
async def help_list(
    category: str | None = Query(None),
    module: str | None = Query(None),
    popular: bool = Query(False),
    user: dict = Depends(get_current_principal),
):
    """Return guide cards (summary, no step bodies) filtered by role/category."""
    role = _user_role(user)
    brand = _user_brand(user)
    cards = list_guides(role=role, category=category, module=module, popular_only=popular)
    cards = [
        {**c, "title": _whitelabel(c.get("title"), brand), "description": _whitelabel(c.get("description"), brand)}
        for c in cards
    ]
    return {"guides": cards, "role": role, "brand": brand}


@router.get("/help/guides/{guide_id}")
async def help_detail(guide_id: str, user: dict = Depends(get_current_principal)):
    """Return the full body of a guide if the current user's role can see it."""
    guide = guide_by_id(guide_id)
    if not guide:
        raise HTTPException(404, "Guide not found")
    role = _user_role(user)
    brand = _user_brand(user)
    if not visible_to_role(guide, role):
        raise HTTPException(403, "Not available for your role")
    # Resolve related guide titles so the frontend can render links without a
    # second round-trip per related id.
    related_resolved = []
    for rid in guide.get("related", []) or []:
        rg = guide_by_id(rid)
        if rg and visible_to_role(rg, role):
            related_resolved.append({
                "id": rg["id"],
                "title": _whitelabel(rg["title"], brand),
                "category": rg["category"],
            })
    branded = _whitelabel_guide(guide, brand)
    return {**branded, "related_resolved": related_resolved, "brand": brand}


@router.get("/help/search")
async def help_search(q: str = Query(..., min_length=2), user: dict = Depends(get_current_principal)):
    """Case-insensitive search across the visible-to-role corpus."""
    role = _user_role(user)
    brand = _user_brand(user)
    raw = search_guides(q, role=role)
    out = [
        {**r, "title": _whitelabel(r.get("title"), brand), "description": _whitelabel(r.get("description"), brand)}
        for r in raw
    ]
    # Iter 215c0 — also surface deep-link capability results so the user
    # finds the actual screen, not just the docs page.
    capabilities = []
    try:
        from routes.help_search import search_help as _capability_search
        cap_resp = await _capability_search(q)
        capabilities = cap_resp.get("results", [])[:5]
    except Exception:
        capabilities = []
    # Log misses for the content-roadmap. Telemetry must never block.
    if not out and not capabilities:
        try:
            from utils.database import db
            from datetime import datetime, timezone
            await db.help_search_misses.insert_one({
                "query": q,
                "role": role,
                "user_id": user.get("id"),
                "user_email": user.get("email"),
                "brand_id": (brand or {}).get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
    return {"results": out, "capabilities": capabilities, "query": q, "brand": brand, "miss": (not bool(out) and not capabilities)}


@router.get("/help/search-misses")
async def help_search_misses(user: dict = Depends(get_current_user)) -> dict:
    """Master-admin view of recent help searches that returned 0
    results. Use this as a content roadmap signal."""
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")
    from utils.database import db

    # Top 25 most-frequent missed queries across all time.
    pipeline = [
        {"$group": {
            "_id": {"$toLower": "$query"},
            "count": {"$sum": 1},
            "last_seen": {"$max": "$created_at"},
            "sample_role": {"$first": "$role"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 25},
    ]
    top = await db.help_search_misses.aggregate(pipeline).to_list(length=25)
    top = [
        {"query": r["_id"], "count": r["count"], "last_seen": r.get("last_seen"), "sample_role": r.get("sample_role")}
        for r in top
    ]

    # Last 25 individually so we can see the freshest missing intent.
    recent = await db.help_search_misses.find(
        {}, {"_id": 0, "query": 1, "role": 1, "created_at": 1, "user_email": 1},
    ).sort("created_at", -1).to_list(length=25)
    return {"top_misses": top, "recent": recent, "total_top": len(top)}


# ───────────────────────── AI assistant (guide-grounded) ───────────

def _build_corpus_for_role(role: str, brand: dict) -> str:
    """Concatenate every visible guide into a compact grounding block,
    white-labelled for the user's brand. Kept small (~12KB) so Claude
    can attend to it fully in one turn.
    """
    chunks: list[str] = []
    for g in GUIDES:
        if not visible_to_role(g, role):
            continue
        wg = _whitelabel_guide(g, brand)
        steps = "\n".join(f"- {s.get('title','')}: {s.get('body','')}" for s in wg.get("steps", []))
        tips = "\n".join(f"- {t}" for t in wg.get("tips", []))
        mistakes = "\n".join(f"- {m}" for m in wg.get("mistakes", []))
        chunks.append(
            f"### Guide `{wg['id']}` — {wg['title']} (category: {wg['category']})\n"
            f"{wg.get('description','')}\n\n"
            f"Steps:\n{steps}\n"
            + (f"\nTips:\n{tips}\n" if tips else "")
            + (f"\nCommon mistakes:\n{mistakes}\n" if mistakes else "")
        )
    return "\n\n".join(chunks)


@router.post("/help/ask")
async def help_ask(body: dict = Body(...), request: Request = None, user: dict = Depends(get_current_user)):
    """Answer the user's question using ONLY the Help Centre guides.

    Body::

        {"question": "How do I connect Stripe?", "current_module": "memberships"}

    Returns::

        {"answer": "...", "guide_ids": ["int-stripe-connect", ...], "model": "..."}

    The prompt explicitly tells Claude to refuse out-of-scope questions so
    the assistant won't hallucinate features outside GymAxis. Rate-limited
    per-user to protect the LLM budget (20/min).
    """
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"help_ask:{user['id']}", max_requests=20, window_seconds=60)

    question = (body.get("question") or "").strip()
    current_module = (body.get("current_module") or "").strip().lower() or None
    if len(question) < 3:
        raise HTTPException(400, "Question too short")

    role = _user_role(user)
    brand = _user_brand(user)
    corpus = _build_corpus_for_role(role, brand)
    api_key = os.environ.get("EMERGENT_LLM_KEY")

    if not api_key:
        # Deterministic fallback — keyword search + short answer assembled
        # from the top guide's description.
        hits = search_guides(question, role=role)
        if not hits:
            return {
                "answer": "I couldn't find a guide that matches that question. Try rephrasing, or browse the categories on the left.",
                "guide_ids": [],
                "model": "fallback-keyword",
                "brand": brand,
            }
        top = hits[0]
        full = guide_by_id(top["id"]) or {}
        title = _whitelabel(top["title"], brand)
        desc = _whitelabel(full.get("description", ""), brand)
        return {
            "answer": f"Based on our guides — **{title}**: {desc}",
            "guide_ids": [h["id"] for h in hits[:3]],
            "model": "fallback-keyword",
            "brand": brand,
        }

    system_message = (
        f"You are the {brand['name']} Help Assistant — a friendly, expert "
        f"guide who answers questions about {brand['name']} ONLY from the "
        "provided Help Centre corpus. Respond in UK English, keep answers "
        "under 120 words, use a confident but simple tone, and never "
        "invent features or steps that aren't in the corpus.\n\n"
        "IMPORTANT RULES:\n"
        "1. If the corpus doesn't contain an answer, say so plainly and "
        "recommend the closest guide. Never make up features.\n"
        "2. Always cite the `guide_id` (e.g. `service-log-fault`) of any "
        "guide you used at the END of your answer, on its own line, in "
        "this exact format: `SOURCES: [id1, id2, ...]`. Max 3 sources.\n"
        "3. Write plain text, no markdown lists longer than 3 items.\n"
        "4. Don't repeat the user's question back to them.\n"
        f"5. NEVER mention 'GymAxis' or any other brand name except "
        f"`{brand['name']}` — the user only knows this product as "
        f"{brand['name']}.\n\n"
        f"USER CONTEXT: role={role}, current_module={current_module or 'none'}\n\n"
        "HELP CORPUS (authoritative — do not go beyond this):\n" + corpus
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key,
            session_id=f"help-{user['id']}",
            system_message=system_message,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=question))
    except Exception as exc:
        logger.warning("[help] Claude failed, falling back to keyword: %s", exc)
        hits = search_guides(question, role=role)
        return {
            "answer": (
                "I'm having trouble reaching the AI assistant right now — "
                "but here's the closest guide."
                if hits else
                "I'm having trouble right now. Try again in a moment, or browse the categories."
            ),
            "guide_ids": [h["id"] for h in hits[:3]],
            "model": "fallback-keyword",
            "brand": brand,
        }

    # Parse `SOURCES: [...]` trailer.
    answer_text = (raw or "").strip()
    guide_ids: list[str] = []
    m = re.search(r"SOURCES:\s*\[([^\]]+)\]\s*$", answer_text)
    if m:
        raw_ids = [s.strip().strip('`').strip('"').strip("'") for s in m.group(1).split(",")]
        # Only keep guide_ids that actually exist + are visible.
        for gid in raw_ids:
            g = guide_by_id(gid)
            if g and visible_to_role(g, role):
                guide_ids.append(gid)
        answer_text = answer_text[: m.start()].rstrip()

    return {
        "answer": _whitelabel(answer_text, brand) or answer_text,
        "guide_ids": guide_ids[:3],
        "model": "claude-sonnet-4-5-20250929",
        "brand": brand,
    }


# ───────────────────────── Setup Checklist ─────────────────────────

# Canonical first-login checklist. Each item maps to a real signal we
# can detect from the database, so progress is honest — not just a
# localStorage flag. Items can be filtered to roles that actually own
# the work (e.g. only owners/master_admin can configure billing).
_CHECKLIST_ITEMS: list[dict] = [
    {
        "id": "ck-equipment",
        "label": "Add your first piece of equipment",
        "module": "operations",
        "href": "/pulse?tab=equipment",
        "guide_id": "gs-first-login",
        "roles": ["owner", "manager", "staff", "master_admin"],
    },
    {
        "id": "ck-fault",
        "label": "Log your first fault",
        "module": "operations",
        "href": "/pulse?tab=faults",
        "guide_id": "service-log-fault",
        "roles": [],  # everyone can do this
    },
    {
        "id": "ck-team",
        "label": "Invite a team member",
        "module": "admin",
        "href": "/master-admin",
        "guide_id": "admin-invite-user",
        "roles": ["owner", "manager", "master_admin"],
    },
    {
        "id": "ck-member",
        "label": "Add or import your first member",
        "module": "memberships",
        "href": "/memberships",
        "guide_id": "mbr-onboard-first",
        "roles": ["owner", "manager", "staff", "master_admin"],
    },
    {
        "id": "ck-plan",
        "label": "Create a membership plan",
        "module": "memberships",
        "href": "/memberships?tab=plans",
        "guide_id": "mbr-first-plan",
        "roles": ["owner", "manager", "master_admin"],
    },
    {
        "id": "ck-campaign",
        "label": "Launch your first campaign",
        "module": "marketing",
        "href": "/marketing",
        "guide_id": "mkt-first-campaign",
        "roles": ["owner", "manager", "staff", "master_admin"],
    },
    {
        "id": "ck-stripe",
        "label": "Connect Stripe for member payments",
        "module": "admin",
        "href": "/memberships?tab=settings",
        "guide_id": "int-stripe-connect",
        "roles": ["owner", "master_admin"],
    },
]


async def _checklist_progress(org_filter: dict, user_id: str) -> dict[str, bool]:
    """Lightweight existence checks against the user's org. Each query
    uses a `find_one(... projection={"_id": 1})` style for speed.

    Missing collections are treated as "not done" — no exceptions raised
    so a fresh org sees every item as outstanding.
    """
    async def _exists(collection_name: str, query: dict) -> bool:
        try:
            coll = db[collection_name]
            doc = await coll.find_one({**org_filter, **query}, {"_id": 1})
            return doc is not None
        except Exception:  # collection missing or db error — fail closed
            return False

    # Equipment + faults live in the Operations side.
    has_equipment = await _exists("equipment", {})
    has_fault = await _exists("issues", {})
    # A team is "set up" once at least one user beyond the seeded admin exists.
    try:
        team_count = await db.users.count_documents({**org_filter})
    except Exception:
        team_count = 0
    has_team = team_count > 1
    # Memberships
    has_member = await _exists("memberships_members", {})
    has_plan = await _exists("memberships_plans", {})
    # Marketing
    has_campaign = await _exists("marketing_campaigns", {})
    # Stripe — use the integrations collection, key 'stripe_connect'.
    has_stripe = False
    try:
        rec = await db.integrations.find_one({**org_filter, "key": "stripe_connect"}, {"_id": 1})
        has_stripe = rec is not None
    except Exception:
        has_stripe = False

    return {
        "ck-equipment": has_equipment,
        "ck-fault":     has_fault,
        "ck-team":      has_team,
        "ck-member":    has_member,
        "ck-plan":      has_plan,
        "ck-campaign":  has_campaign,
        "ck-stripe":    has_stripe,
    }


@router.get("/help/setup-checklist")
async def help_setup_checklist(user: dict = Depends(get_current_user)):
    """Return the first-login setup checklist for the current org/user.

    Each item carries `completed: bool` so the frontend can render a
    progress bar and a friendly "X of Y done" copy.
    """
    role = _user_role(user)
    org_id = user.get("organization_id")
    org_filter = {"organization_id": org_id} if org_id else {}

    progress = await _checklist_progress(org_filter, user.get("id", ""))

    items = []
    for it in _CHECKLIST_ITEMS:
        roles = it.get("roles") or []
        if roles and role != "master_admin" and role not in roles:
            continue  # hide items the user can't action
        items.append({
            **it,
            "completed": bool(progress.get(it["id"], False)),
        })

    done_n = sum(1 for x in items if x["completed"])
    total_n = len(items)
    return {
        "items": items,
        "completed_count": done_n,
        "total_count": total_n,
        "percent": round((done_n / total_n) * 100) if total_n else 0,
        "role": role,
    }
