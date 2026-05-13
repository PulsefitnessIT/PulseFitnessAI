"""Marketing Starter Pack — iter 216h71 + 216h74 launch wiring.

When the operator applies their brand auto-discovery draft to the
brand kit, we offer to auto-draft a starter content pack: 3 emails
(welcome / win-back / promo) + 3 social posts (Instagram caption /
Facebook post / X tweet) baked with their tone-of-voice + audience
segments + current campaigns. Result: blank Marketing module → ready
content in <60 s.

Iter 216h74 — Send/Launch wiring. Each generated email now has 3
one-click actions:
  • Send a real test email to the operator (Resend, co-branded)
  • Create a Campaign draft pre-loaded with the subject + body
  • Bundle all 3 emails into a Welcome Journey (send → wait 3d →
    send → wait 7d → send)

Endpoints:
    POST   /api/marketing/starter-pack/generate                                →  generate & persist 6 drafts
    GET    /api/marketing/starter-pack                                         →  retrieve last pack + launch state
    DELETE /api/marketing/starter-pack                                         →  clear
    POST   /api/marketing/starter-pack/emails/{email_id}/test-send             →  send test email to operator
    POST   /api/marketing/starter-pack/emails/{email_id}/create-campaign       →  create Campaign draft
    POST   /api/marketing/starter-pack/create-journey                          →  create Welcome Journey

All endpoints are module-gated. Generation uses Claude Haiku 4.5 via
Emergent LLM key (one call, ~$0.02 total).
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from routes.marketing.helpers import _new_id, _now_iso, _org_id
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter()


SYSTEM_PROMPT = """You are a fitness-industry marketing copywriter generating a
*starter pack* for a gym operator. Reply with JSON ONLY (no markdown fences),
matching this exact schema:

{
  "emails": [
    {"id": "welcome",   "subject": "...", "preview": "...", "body": "... (180-260 words, plain text, use \\n for paragraph breaks)"},
    {"id": "win_back",  "subject": "...", "preview": "...", "body": "..."},
    {"id": "promo",     "subject": "...", "preview": "...", "body": "..."}
  ],
  "social": [
    {"id": "instagram", "platform": "instagram", "body": "180-300 chars with 3-6 relevant hashtags"},
    {"id": "facebook",  "platform": "facebook",  "body": "1-3 short paragraphs"},
    {"id": "x",         "platform": "x",         "body": "<=270 chars"}
  ]
}

Rules:
- Match the operator's tone_of_voice exactly. If the tone says 'sophisticated and motivational', do NOT write peppy. If it says 'warm and inclusive', do not write austere.
- Speak to the listed audiences specifically — mention them or their goals.
- Reference current_campaigns when relevant (e.g. the promo email).
- Keep copy specific to fitness/wellness — never generic.
- No fluff, no clichés like 'unlock your potential'.
- Emails: subject ≤ 50 chars, preview ≤ 90 chars.
- Output JSON ONLY. Do not wrap in markdown fences."""


async def _generate(brand_kit: dict, intel: dict) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI starter pack unavailable — LLM key not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

    tone = (brand_kit.get("voice") or intel.get("tone_of_voice") or "warm, energetic, professional")
    audiences = intel.get("audiences") or []
    campaigns = intel.get("current_campaigns") or []
    keywords = intel.get("keywords") or []
    business_name = brand_kit.get("business_name") or "the gym"

    user_msg = (
        f"Business: {business_name}\n"
        f"Tone of voice: {tone}\n"
        f"Target audiences: {', '.join(audiences) if audiences else '(general fitness members)'}\n"
        f"Current campaigns / promos to weave in where relevant: "
        f"{'; '.join(campaigns) if campaigns else '(none — write evergreen drafts)'}\n"
        f"Brand keywords / services: {', '.join(keywords) if keywords else '(general fitness)'}\n"
        f"Generate the starter pack now."
    )

    chat = LlmChat(
        api_key=api_key,
        session_id=f"starter-pack-{datetime.now(timezone.utc).timestamp()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("anthropic", "claude-haiku-4-5-20251001")
    answer = await chat.send_message(UserMessage(text=user_msg))

    clean = (answer or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.warning("[starter-pack] claude returned non-JSON: %s", exc)
        raise HTTPException(502, "AI returned malformed JSON — please retry")


@router.post("/marketing/starter-pack/generate", dependencies=[Depends(require_module("marketing"))])
async def generate_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    kit = await db.marketing_brand_kit.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    disc = await db.marketing_brand_discovery.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    intel = (disc.get("draft") or {}).get("intelligence") or {}

    if not (kit.get("voice") or intel.get("tone_of_voice")):
        raise HTTPException(
            400,
            "Brand kit is too sparse — set a voice/tone in Brand Kit or run brand auto-discovery first.",
        )

    pack = await _generate(kit, intel)
    # Validate basic shape so the frontend never renders garbage.
    if not isinstance(pack, dict) or "emails" not in pack or "social" not in pack:
        raise HTTPException(502, "AI returned an unexpected shape — please retry")

    doc = {
        "organization_id": org_id,
        "generated_at": _now_iso(),
        "generated_by": user.get("id"),
        "pack": pack,
        "based_on": {
            "voice": kit.get("voice"),
            "audiences": intel.get("audiences"),
            "campaigns": intel.get("current_campaigns"),
        },
    }
    await db.marketing_starter_pack.update_one(
        {"organization_id": org_id}, {"$set": doc}, upsert=True,
    )
    return {"ok": True, "pack": pack, "generated_at": doc["generated_at"]}


@router.get("/marketing/starter-pack", dependencies=[Depends(require_module("marketing"))])
async def get_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    doc = await db.marketing_starter_pack.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return doc


@router.delete("/marketing/starter-pack", dependencies=[Depends(require_module("marketing"))])
async def delete_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    await db.marketing_starter_pack.delete_one({"organization_id": org_id})
    return {"ok": True}


# ───────────────────────── iter 216h74 — Send / Launch wiring ─────────────────────────

_EMAIL_IDS = {"welcome", "win_back", "promo"}


def _plain_to_html(plain: str) -> str:
    """Convert Claude's plain-text body (with \\n paragraph breaks)
    into a simple, email-client-safe HTML block. Idempotent — if the
    text already contains ``<p>`` / ``<br>`` we trust it."""
    body = (plain or "").strip()
    if not body:
        return ""
    if "<p" in body.lower() or "<br" in body.lower() or "<div" in body.lower():
        return body
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    wrapped = []
    for para in paragraphs:
        # Preserve single newlines inside a paragraph as <br>.
        safe = html_lib.escape(para).replace("\n", "<br>")
        wrapped.append(
            f'<p style="margin:0 0 16px 0;line-height:1.55;color:#1f2937;font-size:15px;">{safe}</p>'
        )
    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;padding:8px 4px;">'
        + "\n".join(wrapped)
        + "</div>"
    )


def _find_email(pack: dict, email_id: str) -> dict:
    if email_id not in _EMAIL_IDS:
        raise HTTPException(400, f"Unknown email id '{email_id}'. Expected one of: {sorted(_EMAIL_IDS)}")
    for em in pack.get("emails") or []:
        if em.get("id") == email_id:
            return em
    raise HTTPException(404, f"Email '{email_id}' is not in the current starter pack — regenerate first.")


async def _load_pack_doc(org_id: str) -> dict:
    doc = await db.marketing_starter_pack.find_one(
        {"organization_id": org_id}, {"_id": 0}
    )
    if not doc or not doc.get("pack"):
        raise HTTPException(
            404,
            "No starter pack on file yet — click 'Draft my starter pack' first.",
        )
    return doc


@router.post(
    "/marketing/starter-pack/emails/{email_id}/test-send",
    dependencies=[Depends(require_module("marketing"))],
)
async def test_send_email(
    email_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Send the draft email to the operator (or a chosen address) RIGHT
    NOW via Resend. Co-brand wrapper + Subject prefixed with ``[Test]``
    so it's clearly a preview send."""
    org_id = await _org_id(user)
    pack_doc = await _load_pack_doc(org_id)
    em = _find_email(pack_doc["pack"], email_id)

    to = (body.get("to") or user.get("email") or "").strip()
    if not to or "@" not in to:
        raise HTTPException(400, "No valid email address — pass {'to': 'someone@example.com'} or set your own email.")

    try:
        from utils.email import send_email  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(503, "Email sender unavailable") from exc

    subject = f"[Test] {(em.get('subject') or 'Starter pack preview').strip()}"
    html = _plain_to_html(em.get("body") or "")
    ok = await send_email(to=to, subject=subject, html=html, organization_id=org_id)
    if not ok:
        raise HTTPException(
            502,
            "Test send failed — check the platform's RESEND_API_KEY and sender domain.",
        )
    await db.marketing_starter_pack.update_one(
        {"organization_id": org_id},
        {"$set": {f"launches.emails.{email_id}.test_sent_at": _now_iso(),
                  f"launches.emails.{email_id}.test_sent_to": to}},
    )
    return {"ok": True, "to": to, "subject": subject}


@router.post(
    "/marketing/starter-pack/emails/{email_id}/create-campaign",
    dependencies=[Depends(require_module("marketing"))],
)
async def create_campaign_from_email(
    email_id: str,
    user: dict = Depends(get_current_user),
):
    """Spin a Marketing Campaign draft pre-loaded with this email's
    subject + body. The operator opens Campaigns to pick an audience
    and press Send."""
    org_id = await _org_id(user)
    pack_doc = await _load_pack_doc(org_id)
    em = _find_email(pack_doc["pack"], email_id)

    # If a campaign already exists for this slot, return the existing
    # one rather than creating duplicates.
    existing_id = (((pack_doc.get("launches") or {}).get("emails") or {}).get(email_id) or {}).get("campaign_id")
    if existing_id:
        existing = await db.marketing_campaigns.find_one(
            {"id": existing_id, "organization_id": org_id}, {"_id": 0},
        )
        if existing:
            return {"ok": True, "campaign_id": existing_id, "already_exists": True, "campaign": existing}

    subject = (em.get("subject") or "Untitled").strip()
    body_html = _plain_to_html(em.get("body") or "")
    label_map = {"welcome": "Welcome", "win_back": "Win-back", "promo": "Promo"}
    name = f"Starter pack · {label_map.get(email_id, email_id.title())}"

    doc = {
        "id": _new_id(),
        "organization_id": org_id,
        "created_by": user["id"],
        "name": name,
        "status": "draft",
        "channel": "email",
        "audience_id": None,
        "audience_inline": None,
        "dynamic_list_id": None,
        "content": {"subject": subject, "body_html": body_html, "preview": em.get("preview") or ""},
        "variants": [{
            "id": "default",
            "name": "Default",
            "subject": subject,
            "body_html": body_html,
            "weight": 1,
        }],
        "ab_test": {"enabled": False},
        "winner_variant_id": None,
        "winner_decided_at": None,
        "pending_recipients": [],
        "schedule": {},
        "tracking": {"utm_source": "gymaxis_marketing", "utm_campaign": f"starter-pack-{email_id}"},
        "metrics": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0,
                    "converted": 0, "revenue_gbp": 0},
        "metrics_by_variant": {"default": {"sent": 0, "opened": 0, "clicked": 0, "bounced": 0}},
        "source": {"kind": "starter_pack", "email_id": email_id},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "sent_at": None,
    }
    await db.marketing_campaigns.insert_one(doc)
    await db.marketing_starter_pack.update_one(
        {"organization_id": org_id},
        {"$set": {f"launches.emails.{email_id}.campaign_id": doc["id"],
                  f"launches.emails.{email_id}.campaign_created_at": _now_iso()}},
    )
    return {"ok": True, "campaign_id": doc["id"], "campaign": {k: v for k, v in doc.items() if k != "_id"}}


@router.post(
    "/marketing/starter-pack/create-journey",
    dependencies=[Depends(require_module("marketing"))],
)
async def create_journey_from_pack(user: dict = Depends(get_current_user)):
    """Build a 3-step Welcome Journey from the starter pack emails:

        send(welcome)  →  wait 3d  →  send(win_back)  →  wait 7d  →  send(promo)

    The journey is created in DRAFT state. The operator wires the
    trigger (e.g. ``member_signed_up``) and clicks Publish in Journeys.
    """
    org_id = await _org_id(user)
    pack_doc = await _load_pack_doc(org_id)
    pack = pack_doc["pack"]
    emails = {em.get("id"): em for em in (pack.get("emails") or [])}
    missing = [eid for eid in ("welcome", "win_back", "promo") if eid not in emails]
    if missing:
        raise HTTPException(
            400, f"Starter pack is missing emails: {', '.join(missing)} — regenerate first.",
        )

    # If a journey already exists, return the existing one.
    existing_id = (pack_doc.get("launches") or {}).get("journey_id")
    if existing_id:
        existing = await db.marketing_journeys.find_one(
            {"id": existing_id, "organization_id": org_id}, {"_id": 0},
        )
        if existing:
            return {"ok": True, "journey_id": existing_id, "already_exists": True, "journey": existing}

    def _send_email_node(em: dict, label: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "type": "send_email",
            "label": label,
            "config": {
                "subject": (em.get("subject") or "").strip(),
                "body_html": _plain_to_html(em.get("body") or ""),
                "preview": em.get("preview") or "",
            },
        }

    def _wait_node(days: int) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "type": "wait",
            "label": f"Wait {days} days",
            "config": {"duration_minutes": days * 24 * 60},
        }

    welcome_node = _send_email_node(emails["welcome"], "Welcome email")
    wait_3d = _wait_node(3)
    win_back_node = _send_email_node(emails["win_back"], "Win-back email")
    wait_7d = _wait_node(7)
    promo_node = _send_email_node(emails["promo"], "Promo email")
    nodes = [welcome_node, wait_3d, win_back_node, wait_7d, promo_node]
    edges = [
        {"id": str(uuid.uuid4()), "source": welcome_node["id"], "target": wait_3d["id"]},
        {"id": str(uuid.uuid4()), "source": wait_3d["id"], "target": win_back_node["id"]},
        {"id": str(uuid.uuid4()), "source": win_back_node["id"], "target": wait_7d["id"]},
        {"id": str(uuid.uuid4()), "source": wait_7d["id"], "target": promo_node["id"]},
    ]

    journey_id = _new_id()
    journey_doc = {
        "id": journey_id,
        "organization_id": org_id,
        "name": "Welcome series (starter pack)",
        "status": "draft",
        "trigger": {"event": "member_signed_up"},
        "nodes": nodes,
        "edges": edges,
        "ai_optimisation": {},
        "metrics": {"entered": 0, "completed": 0, "converted": 0, "revenue_gbp": 0},
        "source": {"kind": "starter_pack"},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.marketing_journeys.insert_one(journey_doc)
    await db.marketing_starter_pack.update_one(
        {"organization_id": org_id},
        {"$set": {"launches.journey_id": journey_id,
                  "launches.journey_created_at": _now_iso()}},
    )
    return {"ok": True, "journey_id": journey_id, "journey": {k: v for k, v in journey_doc.items() if k != "_id"}}
