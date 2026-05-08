"""Campaign templates library + instantiate.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations


from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _new_id,
    _now_iso,
    _org_id,
)
from routes.marketing.audiences import _evaluate_audience

router = APIRouter()


# ───────────────────────── Campaign Templates ─────────────────────────

CAMPAIGN_TEMPLATES = [
    {
        "id": "welcome_new_member", "name": "Welcome new member",
        "description": "First-impression email for fresh signups — sets expectations and books their first class.",
        "icon": "user-plus", "tone": "friendly",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "signup_at", "op": ">=", "value": "30d_ago"},
        ]},
        "subject": "Welcome to {{gym_name}} — your first session is on us",
        "body_html": ("<h1>Hi {{first_name}}, welcome aboard!</h1>"
                       "<p>You're officially in the family. To make your first week count, we've reserved a free intro session for you.</p>"
                       "<p><a href=\"{{book_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Book your first session</a></p>"
                       "<p>Train hard. Recover well. Win.</p>"),
        "creative_brief": "Welcoming, energetic gym lobby photo with morning sunlight, clean modern equipment in background",
    },
    {
        "id": "winback", "name": "Win back inactive members",
        "description": "Reactivate members who haven't trained in 21 days with a personalised offer.",
        "icon": "trending-down", "tone": "supportive",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "last_attended_at", "op": "<=", "value": "21d_ago"},
            {"field": "churn_risk_score", "op": ">=", "value": 50},
        ]},
        "subject": "We miss you, {{first_name}} — here's 20% off your next month",
        "body_html": ("<h1>Get back to it, {{first_name}}</h1>"
                       "<p>Life happens. But your health doesn't pause. Here's a token to make it easier to get back.</p>"
                       "<p><strong>20% off your next month</strong> — applied automatically to your next renewal.</p>"
                       "<p><a href=\"{{book_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Book a class this week</a></p>"),
        "creative_brief": "Empowering, motivational gym scene — kettlebells, soft morning light, no faces visible (privacy-safe)",
    },
    {
        "id": "class_promo", "name": "Promote a class",
        "description": "Fill an under-booked session — targets members who attend that class type.",
        "icon": "calendar", "tone": "energetic",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "class_preference", "op": "==", "value": "spin"},
            {"field": "last_attended_at", "op": ">=", "value": "60d_ago"},
        ]},
        "subject": "🚴 Saturday spin — your bike is waiting, {{first_name}}",
        "body_html": ("<h1>Saturday morning spin — book now</h1>"
                       "<p>Your favourite class is on this Saturday at 09:00. We've reserved a bike with your name on it.</p>"
                       "<p><a href=\"{{book_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Reserve my spot</a></p>"
                       "<p>30 min. Full energy. No regrets.</p>"),
        "creative_brief": "High-energy spin class with neon studio lighting, riders mid-effort, dramatic shadow play",
    },
    {
        "id": "pt_upsell", "name": "PT package upsell",
        "description": "Upsell personal training to engaged members who haven't booked PT yet.",
        "icon": "user-check", "tone": "premium",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "attendance_30d", "op": ">=", "value": 8},
            {"field": "pt_sessions_used_30d", "op": "==", "value": 0},
        ]},
        "subject": "Ready to level up, {{first_name}}? Try a free PT session",
        "body_html": ("<h1>You're showing up. Time to level up.</h1>"
                       "<p>You've trained 8+ times this month — you're committed. A 1-on-1 PT session can shave weeks off your goals.</p>"
                       "<p><strong>Your first session is on us.</strong> Pick a coach below.</p>"
                       "<p><a href=\"{{pt_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Choose a coach</a></p>"),
        "creative_brief": "Premium 1-on-1 PT session, athlete and coach, gym studio, deliberate lighting",
    },
    {
        "id": "failed_payment_recovery", "name": "Failed payment recovery",
        "description": "Recover members whose direct debit failed — friendly reminder to update card.",
        "icon": "credit-card", "tone": "professional",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "payment_status", "op": "==", "value": "failed"},
        ]},
        "subject": "Quick action needed — update your payment, {{first_name}}",
        "body_html": ("<h1>Hi {{first_name}}</h1>"
                       "<p>Heads up — your last payment didn't go through. It's a 30-second fix.</p>"
                       "<p><a href=\"{{billing_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Update payment method</a></p>"
                       "<p>Once sorted, your access stays uninterrupted. Any questions, reply to this email.</p>"),
        "creative_brief": "Clean professional banking/security iconography, no gym imagery — keep it clinical",
    },
    {
        "id": "referral_push", "name": "Referral push",
        "description": "Drive referrals from your most loyal high-spending members.",
        "icon": "share-2", "tone": "celebratory",
        "audience_rules": {"op": "and", "conditions": [
            {"field": "lifetime_value_gbp", "op": ">=", "value": 500},
            {"field": "attendance_30d", "op": ">=", "value": 6},
        ]},
        "subject": "{{first_name}}, refer a friend — get a free month for both of you",
        "body_html": ("<h1>Train better together</h1>"
                       "<p>You're one of our top members. Bring a friend, and both of you get <strong>one free month</strong>.</p>"
                       "<p><a href=\"{{referral_url}}\" style=\"background:#0055FF;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none\">Get your referral link</a></p>"),
        "creative_brief": "Two friends high-fiving post-workout, authentic energy, natural light",
    },
]


@router.get("/marketing/templates", dependencies=[Depends(require_module("marketing"))])
async def list_templates(user: dict = Depends(get_current_user)):
    """Quick-start campaign templates — pre-built audience rules + subject +
    body + creative brief. Returns:
      • stock platform templates (with per-org overrides applied)
      • org-created custom templates (`source: "custom"`)
      • org-deleted stock template ids (`hidden_stock_ids`) so the UI can
        hide them.
    """
    org_id = await _org_id(user)
    overrides = await db.marketing_template_overrides.find(
        {"organization_id": org_id}, {"_id": 0},
    ).to_list(50)
    by_id = {o["template_id"]: o for o in overrides}
    hidden_stock_ids = [o["template_id"] for o in overrides if o.get("deleted")]

    out: list[dict] = []
    for stock in CAMPAIGN_TEMPLATES:
        if stock["id"] in hidden_stock_ids:
            continue
        ov = by_id.get(stock["id"])
        if ov and not ov.get("deleted"):
            out.append({**stock, **{k: v for k, v in ov.items() if k in
                                     ("name", "subject", "body_html",
                                      "creative_brief", "audience_rules")},
                        "source": "stock_overridden"})
        else:
            out.append({**stock, "source": "stock"})

    custom = await db.marketing_custom_templates.find(
        {"organization_id": org_id}, {"_id": 0, "organization_id": 0},
    ).sort("created_at", -1).to_list(100)
    for c in custom:
        out.append({**c, "source": "custom"})

    return {"templates": out, "hidden_stock_ids": hidden_stock_ids}


class TemplatePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    subject: Optional[str] = Field(default=None, max_length=200)
    body_html: Optional[str] = Field(default=None, max_length=20000)
    creative_brief: Optional[str] = Field(default=None, max_length=500)
    audience_rules: Optional[dict] = None


class TemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    subject: str = Field(min_length=2, max_length=200)
    body_html: str = Field(min_length=1, max_length=20000)
    creative_brief: Optional[str] = Field(default="", max_length=500)
    audience_rules: dict = Field(default_factory=dict)


@router.post(
    "/marketing/templates",
    dependencies=[Depends(require_module("marketing"))],
)
async def create_template(body: TemplateCreate, user: dict = Depends(get_current_user)):
    """Create a new custom org-template (stock library is platform-managed
    and not editable here; use PUT/DELETE on the stock id for an override)."""
    org_id = await _org_id(user)
    doc = {
        "id": _new_id(), "organization_id": org_id,
        "name": body.name, "subject": body.subject,
        "body_html": body.body_html, "creative_brief": body.creative_brief or "",
        "audience_rules": body.audience_rules,
        "created_by": user["id"], "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.marketing_custom_templates.insert_one(doc)
    return {"ok": True, "template": {**{k: v for k, v in doc.items() if k not in {"_id", "organization_id"}}, "source": "custom"}}


@router.put(
    "/marketing/templates/{template_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def update_template(
    template_id: str, body: TemplatePatch,
    user: dict = Depends(get_current_user),
):
    """Update either:
      • a custom org template (in marketing_custom_templates), or
      • a stock template — stored as an override doc keyed by template_id
        in marketing_template_overrides. Stock library is never mutated."""
    org_id = await _org_id(user)
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
    patch["updated_at"] = _now_iso()
    patch["updated_by"] = user["id"]

    # Stock?
    if any(t["id"] == template_id for t in CAMPAIGN_TEMPLATES):
        await db.marketing_template_overrides.update_one(
            {"organization_id": org_id, "template_id": template_id},
            {"$set": {**patch, "organization_id": org_id,
                       "template_id": template_id, "deleted": False}},
            upsert=True,
        )
        return {"ok": True, "template_id": template_id, "kind": "stock_override"}

    # Custom
    res = await db.marketing_custom_templates.update_one(
        {"id": template_id, "organization_id": org_id},
        {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True, "template_id": template_id, "kind": "custom"}


@router.delete(
    "/marketing/templates/{template_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def delete_template(template_id: str, user: dict = Depends(get_current_user)):
    """Delete behaviour:
      • Custom org template → hard-deleted from marketing_custom_templates.
      • Stock template → marked hidden via override doc (so this org no
        longer sees it). Reset by POSTing /reset on the stock id."""
    org_id = await _org_id(user)
    if any(t["id"] == template_id for t in CAMPAIGN_TEMPLATES):
        await db.marketing_template_overrides.update_one(
            {"organization_id": org_id, "template_id": template_id},
            {"$set": {"organization_id": org_id,
                       "template_id": template_id, "deleted": True,
                       "updated_at": _now_iso(),
                       "updated_by": user["id"]}},
            upsert=True,
        )
        return {"ok": True, "template_id": template_id, "kind": "stock_hidden"}
    res = await db.marketing_custom_templates.delete_one(
        {"id": template_id, "organization_id": org_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True, "template_id": template_id, "kind": "custom_deleted"}


@router.post(
    "/marketing/templates/{template_id}/reset",
    dependencies=[Depends(require_module("marketing"))],
)
async def reset_stock_template(
    template_id: str, user: dict = Depends(get_current_user),
):
    """Drop any per-org override on a stock template — restoring the
    platform default."""
    org_id = await _org_id(user)
    if not any(t["id"] == template_id for t in CAMPAIGN_TEMPLATES):
        raise HTTPException(400, "Reset only applies to stock templates")
    await db.marketing_template_overrides.delete_one(
        {"organization_id": org_id, "template_id": template_id},
    )
    return {"ok": True, "template_id": template_id}


@router.post("/marketing/templates/{template_id}/instantiate", dependencies=[Depends(require_module("marketing"))])
async def instantiate_template(template_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """Materialise a template into a draft Campaign + matching Audience.
    Returns both ids so the UI can deep-link the user straight to edit/send.

    Optional ``body.gym_name`` substitutes into subject/body placeholders.
    """
    org_id = await _org_id(user)
    template = next((t for t in CAMPAIGN_TEMPLATES if t["id"] == template_id), None)
    if not template:
        # Custom org template?
        template = await db.marketing_custom_templates.find_one(
            {"id": template_id, "organization_id": org_id},
            {"_id": 0, "organization_id": 0},
        )
    if not template:
        raise HTTPException(404, "Template not found")

    # Apply per-org override (if any) on a stock template
    override = await db.marketing_template_overrides.find_one(
        {"organization_id": org_id, "template_id": template_id, "deleted": {"$ne": True}},
        {"_id": 0},
    )
    if override:
        for k in ("name", "subject", "body_html", "creative_brief", "audience_rules"):
            if k in override:
                template[k] = override[k]

    # Substitute simple placeholders.
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym_name = (body or {}).get("gym_name") or org.get("name") or "your gym"
    subject = template["subject"].replace("{{gym_name}}", gym_name)
    body_html = template["body_html"].replace("{{gym_name}}", gym_name)

    # Save audience.
    aud_count, _ = await _evaluate_audience(org_id, template["audience_rules"])
    audience_doc = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": f"{template['name']} — auto", "type": "dynamic",
        "rules": template["audience_rules"], "estimated_size": aud_count,
        "computed_at": _now_iso(), "tags": ["template", template_id],
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db.marketing_audiences.insert_one(audience_doc)

    # Save campaign draft.
    campaign_doc = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": template["name"], "status": "draft", "channel": "email",
        "audience_id": audience_doc["id"], "audience_inline": None,
        "content": {"subject": subject, "body_html": body_html, "creative_brief": template["creative_brief"]},
        "schedule": {}, "tracking": {"utm_source": "gymaxis_marketing", "utm_campaign": template_id},
        "metrics": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0,
                    "converted": 0, "revenue_gbp": 0},
        "template_id": template_id,
        "created_at": _now_iso(), "updated_at": _now_iso(), "sent_at": None,
    }
    await db.marketing_campaigns.insert_one(campaign_doc)

    return {
        "audience_id": audience_doc["id"],
        "campaign_id": campaign_doc["id"],
        "audience_size": aud_count,
        "subject": subject,
    }
