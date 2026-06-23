"""Pulse Fitness AI — Comms Centre / shared Campaign Engine (Phase 1).

ONE shared campaign system backing Marketing → Campaigns,
Memberships → Emails and CRM → Communications. Campaign records live in
the existing ``marketing_campaigns`` collection so there is a single
source of truth — these endpoints add the unified fields
(``campaign_type``, ``related_module``, ``owner``, richer ``status`` and
``approval``) plus a drag-and-drop email-block content model and a
branded test-send, without duplicating records.

Access is granted to any org with Marketing OR Memberships OR CRM, so the
same engine powers all three contextual views.
"""
from __future__ import annotations

import html as _htmllib
import re
import base64
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import _new_id, _now_iso, _org_id, logger

router = APIRouter(prefix="/comms")

_ANY_COMMS_MODULE = require_module(("marketing", "memberships", "crm"))

# ───────────────────────── Catalogues (meta) ─────────────────────────

# module → category used for the verified Resend sending sub-domain.
_MODULE_EMAIL_CATEGORY = {
    "marketing": "support",
    "memberships": "memberships",
    "crm": "support",
}

CAMPAIGN_TYPES = [
    # id, label, module (primary context), group
    {"id": "regular", "label": "Regular email", "module": "marketing", "group": "Email"},
    {"id": "plain_text", "label": "Plain-text email", "module": "marketing", "group": "Email"},
    {"id": "newsletter", "label": "Newsletter", "module": "marketing", "group": "Email"},
    {"id": "promotion", "label": "Promotional campaign", "module": "marketing", "group": "Email"},
    {"id": "member_announcement", "label": "Member announcement", "module": "memberships", "group": "Members"},
    {"id": "class_update", "label": "Class / timetable update", "module": "memberships", "group": "Members"},
    {"id": "birthday", "label": "Birthday campaign", "module": "memberships", "group": "Occasions"},
    {"id": "holiday", "label": "Christmas / holiday", "module": "memberships", "group": "Occasions"},
    {"id": "renewal", "label": "Membership renewal", "module": "memberships", "group": "Members"},
    {"id": "failed_payment", "label": "Failed payment", "module": "memberships", "group": "Members"},
    {"id": "reactivation", "label": "Inactive member reactivation", "module": "memberships", "group": "Members"},
    {"id": "trial_followup", "label": "Trial follow-up", "module": "memberships", "group": "Members"},
    {"id": "lead_nurture", "label": "Lead nurture", "module": "crm", "group": "B2B"},
    {"id": "b2b_lead_nurture", "label": "B2B lead nurture", "module": "crm", "group": "B2B"},
    {"id": "sales_followup", "label": "Sales follow-up", "module": "crm", "group": "B2B"},
    {"id": "quote_followup", "label": "Quote follow-up", "module": "crm", "group": "B2B"},
    {"id": "proposal_followup", "label": "Proposal follow-up", "module": "crm", "group": "B2B"},
    {"id": "tender_followup", "label": "Tender follow-up", "module": "crm", "group": "B2B"},
    {"id": "supplier_update", "label": "Supplier update", "module": "crm", "group": "B2B"},
    {"id": "partner_update", "label": "Partner update", "module": "crm", "group": "B2B"},
    {"id": "account_management", "label": "Account management", "module": "crm", "group": "B2B"},
    {"id": "event_invite", "label": "Event invitation", "module": "marketing", "group": "Email"},
    {"id": "service_update", "label": "Service update", "module": "crm", "group": "Service"},
    {"id": "survey", "label": "Survey campaign", "module": "marketing", "group": "Feedback"},
    {"id": "review_request", "label": "Feedback / review request", "module": "marketing", "group": "Feedback"},
    {"id": "transactional", "label": "Transactional email", "module": "marketing", "group": "System"},
    {"id": "automated_journey", "label": "Automated journey", "module": "marketing", "group": "Automation"},
]
_CAMPAIGN_TYPE_IDS = {t["id"] for t in CAMPAIGN_TYPES}
_CAMPAIGN_TYPE_MODULE = {t["id"]: t["module"] for t in CAMPAIGN_TYPES}

# status → list of allowed next statuses (approval workflow)
CAMPAIGN_STATUSES = [
    "draft", "in_review", "changes_requested", "approved",
    "scheduled", "sending", "sent", "paused", "cancelled", "archived",
]
_STATUS_TRANSITIONS = {
    "draft": {"in_review", "approved", "scheduled", "cancelled", "archived"},
    "in_review": {"changes_requested", "approved", "draft", "cancelled"},
    "changes_requested": {"draft", "in_review", "cancelled"},
    "approved": {"scheduled", "draft", "cancelled"},
    "scheduled": {"sending", "paused", "cancelled", "draft"},
    "sending": {"sent", "paused"},
    "sent": {"archived"},
    "paused": {"scheduled", "cancelled", "archived"},
    "cancelled": {"draft", "archived"},
    "archived": {"draft"},
}

BLOCK_TYPES = [
    {"id": "logo", "label": "Logo", "icon": "image"},
    {"id": "heading", "label": "Heading", "icon": "heading"},
    {"id": "text", "label": "Paragraph", "icon": "text"},
    {"id": "image", "label": "Image", "icon": "image"},
    {"id": "button", "label": "Button", "icon": "mouse-pointer"},
    {"id": "divider", "label": "Divider", "icon": "minus"},
    {"id": "spacer", "label": "Spacer", "icon": "move-vertical"},
    {"id": "social", "label": "Social links", "icon": "share-2"},
    {"id": "video", "label": "Video link", "icon": "video"},
    {"id": "html", "label": "HTML / code", "icon": "code"},
    {"id": "footer", "label": "Footer", "icon": "layout"},
]

MERGE_TAGS = {
    "member": [
        "{{first_name}}", "{{last_name}}", "{{full_name}}", "{{membership_type}}",
        "{{membership_expiry_date}}", "{{site_name}}", "{{class_name}}",
        "{{instructor_name}}", "{{birthday}}", "{{joined_date}}", "{{renewal_link}}",
        "{{payment_link}}", "{{booking_link}}", "{{customer_portal_link}}",
    ],
    "b2b": [
        "{{contact_first_name}}", "{{contact_last_name}}", "{{company_name}}",
        "{{company_website}}", "{{account_owner}}", "{{sales_owner}}",
        "{{pipeline_stage}}", "{{opportunity_name}}", "{{quote_number}}",
        "{{quote_link}}", "{{proposal_link}}", "{{contract_name}}",
        "{{contract_renewal_date}}", "{{invoice_number}}", "{{invoice_link}}",
        "{{supplier_name}}", "{{partner_name}}",
    ],
    "system": [
        "{{unsubscribe_link}}", "{{preferences_link}}",
        "{{view_in_browser_link}}", "{{forward_to_friend_link}}",
    ],
}
_KNOWN_TAGS = {t for grp in MERGE_TAGS.values() for t in grp}
# sample values used purely for previews / test sends
_TAG_SAMPLES = {
    "{{first_name}}": "Alex", "{{last_name}}": "Taylor", "{{full_name}}": "Alex Taylor",
    "{{contact_first_name}}": "Alex", "{{contact_last_name}}": "Taylor",
    "{{membership_type}}": "Premium", "{{membership_expiry_date}}": "31 Dec 2026",
    "{{site_name}}": "Pulse Fitness — City Centre", "{{class_name}}": "Open Flow Yoga",
    "{{instructor_name}}": "Jamie Rowe", "{{birthday}}": "14 March",
    "{{joined_date}}": "2 Jan 2024", "{{company_name}}": "Acme Leisure Ltd",
    "{{company_website}}": "acme-leisure.co.uk", "{{account_owner}}": "Sam Price",
    "{{sales_owner}}": "Sam Price", "{{pipeline_stage}}": "Proposal",
    "{{opportunity_name}}": "Gym refurbishment", "{{quote_number}}": "Q-1042",
    "{{contract_name}}": "Service contract 2026", "{{contract_renewal_date}}": "1 Apr 2026",
    "{{invoice_number}}": "INV-2051", "{{supplier_name}}": "TechnoServe",
    "{{partner_name}}": "FitFix Engineering",
}
_LINK_TAGS = {
    "{{renewal_link}}", "{{payment_link}}", "{{booking_link}}", "{{customer_portal_link}}",
    "{{quote_link}}", "{{proposal_link}}", "{{invoice_link}}", "{{unsubscribe_link}}",
    "{{preferences_link}}", "{{view_in_browser_link}}", "{{forward_to_friend_link}}",
}

_CYAN = "#19CDFF"


# ───────────────────────── Block renderer ─────────────────────────

def _esc(v) -> str:
    return _htmllib.escape(str(v or ""))


def _render_block(b: dict) -> str:
    t = b.get("type")
    p = b.get("props") or {}
    if t == "logo":
        src = p.get("src") or "/brand/pulse-mark.svg"
        return (
            f'<tr><td style="padding:24px 24px 8px;text-align:{p.get("align","center")}">'
            f'<img src="{_esc(src)}" alt="Pulse Fitness AI" height="40" style="height:40px"></td></tr>'
        )
    if t == "heading":
        return (
            f'<tr><td style="padding:8px 24px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:{p.get("size",24)}px;font-weight:800;color:{_esc(p.get("color","#0B1220"))};'
            f'text-align:{p.get("align","left")}">{_esc(p.get("text","Heading"))}</td></tr>'
        )
    if t == "text":
        return (
            f'<tr><td style="padding:8px 24px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:15px;line-height:1.6;color:#374151;text-align:{p.get("align","left")}">'
            f'{p.get("text","Your text here.")}</td></tr>'
        )
    if t == "image":
        src = p.get("src") or "https://via.placeholder.com/560x240?text=Image"
        alt = _esc(p.get("alt", ""))
        return (
            f'<tr><td style="padding:12px 24px;text-align:center">'
            f'<img src="{_esc(src)}" alt="{alt}" width="100%" style="max-width:560px;border-radius:10px"></td></tr>'
        )
    if t == "button":
        return (
            f'<tr><td style="padding:16px 24px;text-align:{p.get("align","center")}">'
            f'<a href="{_esc(p.get("url","#"))}" style="background:{_esc(p.get("color",_CYAN))};'
            f'color:#03212b;text-decoration:none;font-weight:700;font-family:Arial,Helvetica,sans-serif;'
            f'padding:13px 26px;border-radius:999px;display:inline-block;font-size:15px">'
            f'{_esc(p.get("text","Click here"))}</a></td></tr>'
        )
    if t == "divider":
        return '<tr><td style="padding:8px 24px"><hr style="border:none;border-top:1px solid #E5E7EB;margin:0"></td></tr>'
    if t == "spacer":
        return f'<tr><td style="height:{int(p.get("height",24))}px;line-height:1px">&nbsp;</td></tr>'
    if t == "social":
        links = p.get("links") or [{"label": "Instagram", "url": "#"}, {"label": "Facebook", "url": "#"}]
        cells = "".join(
            f'<a href="{_esc(l.get("url","#"))}" style="color:{_CYAN};text-decoration:none;'
            f'font-weight:700;margin:0 8px;font-family:Arial,Helvetica,sans-serif;font-size:13px">'
            f'{_esc(l.get("label",""))}</a>'
            for l in links
        )
        return f'<tr><td style="padding:12px 24px;text-align:center">{cells}</td></tr>'
    if t == "video":
        thumb = p.get("thumbnail") or "https://via.placeholder.com/560x300?text=Watch+video"
        return (
            f'<tr><td style="padding:12px 24px;text-align:center">'
            f'<a href="{_esc(p.get("url","#"))}"><img src="{_esc(thumb)}" alt="Watch video" '
            f'width="100%" style="max-width:560px;border-radius:10px"></a></td></tr>'
        )
    if t == "html":
        return f'<tr><td style="padding:8px 24px">{p.get("html","")}</td></tr>'
    if t == "footer":
        return (
            f'<tr><td style="padding:20px 24px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:12px;line-height:1.6;color:#9CA3AF;text-align:center;border-top:1px solid #F1F5F9">'
            f'{p.get("text","You are receiving this email from Pulse Fitness AI.")}<br>'
            f'<a href="{{{{unsubscribe_link}}}}" style="color:#9CA3AF">Unsubscribe</a> · '
            f'<a href="{{{{preferences_link}}}}" style="color:#9CA3AF">Update preferences</a> · '
            f'<a href="{{{{view_in_browser_link}}}}" style="color:#9CA3AF">View in browser</a>'
            f'</td></tr>'
        )
    return ""


def render_blocks_to_html(blocks: list[dict]) -> str:
    """Render the drag-and-drop block model into email-safe table HTML."""
    rows = "".join(_render_block(b) for b in (blocks or []))
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F3F4F6;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border-radius:14px;overflow:hidden;max-width:600px;width:100%">'
        f'{rows}'
        '</table></td></tr></table>'
    )


def _apply_samples(html_str: str) -> str:
    out = html_str
    for tag, sample in _TAG_SAMPLES.items():
        out = out.replace(tag, sample)
    for tag in _LINK_TAGS:
        out = out.replace(tag, "#")
    # any remaining unknown {{tags}} → blank to avoid raw tokens in preview
    return out


def _find_tags(text: str) -> set[str]:
    return set(re.findall(r"\{\{[^}]+\}\}", text or ""))


def _quality_checks(campaign: dict) -> list[dict]:
    """Pre-send accessibility / quality / merge-tag warnings."""
    warnings: list[dict] = []
    content = campaign.get("content") or {}
    subject = (content.get("subject") or "").strip()
    blocks = content.get("blocks") or []
    body = render_blocks_to_html(blocks) if blocks else (content.get("body_html") or "")

    if not subject:
        warnings.append({"level": "error", "code": "no_subject", "message": "Subject line is missing."})
    elif len(subject) > 90:
        warnings.append({"level": "warn", "code": "long_subject", "message": "Subject line is over 90 characters."})

    used = _find_tags(subject) | _find_tags(body)
    unknown = [t for t in used if t not in _KNOWN_TAGS]
    if unknown:
        warnings.append({"level": "error", "code": "broken_merge_tag",
                         "message": f"Unknown merge tag(s): {', '.join(sorted(unknown))}"})

    if "{{unsubscribe_link}}" not in body and campaign.get("campaign_type") != "transactional":
        warnings.append({"level": "warn", "code": "no_unsubscribe",
                         "message": "No unsubscribe link found. Marketing emails should include one."})

    has_image = any((b.get("type") in ("image", "logo")) for b in blocks)
    missing_alt = any(b.get("type") == "image" and not (b.get("props") or {}).get("alt") for b in blocks)
    if has_image and missing_alt:
        warnings.append({"level": "warn", "code": "missing_alt",
                         "message": "One or more images are missing alt text (accessibility)."})

    if not blocks and not (content.get("body_html") or "").strip():
        warnings.append({"level": "error", "code": "empty_body", "message": "The email has no content."})
    return warnings


# ───────────────────────── Serialisation ─────────────────────────

def _public_campaign(doc: dict) -> dict:
    """Normalise a stored campaign for the Comms API (back-compat defaults)."""
    ct = doc.get("campaign_type") or "regular"
    doc.pop("_id", None)
    doc["campaign_type"] = ct
    doc["related_module"] = doc.get("related_module") or _CAMPAIGN_TYPE_MODULE.get(ct, "marketing")
    doc.setdefault("owner", doc.get("created_by"))
    doc.setdefault("owner_name", "")
    doc.setdefault("conversion_goal", "")
    doc.setdefault("approval", {"status": "none", "reviewer": None, "notes": ""})
    doc.setdefault("tags", [])
    return doc


async def _get_owned(campaign_id: str, org_id: str) -> dict:
    doc = await db.marketing_campaigns.find_one({"id": campaign_id, "organization_id": org_id})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    return _public_campaign(doc)


# ───────────────────────── Meta ─────────────────────────

@router.get("/meta", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def comms_meta(user: dict = Depends(get_current_user)):
    return {
        "campaign_types": CAMPAIGN_TYPES,
        "statuses": CAMPAIGN_STATUSES,
        "status_transitions": {k: sorted(v) for k, v in _STATUS_TRANSITIONS.items()},
        "blocks": BLOCK_TYPES,
        "merge_tags": MERGE_TAGS,
        "modules": ["marketing", "memberships", "crm"],
    }


# ───────────────────────── Dashboard ─────────────────────────

@router.get("/dashboard", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def comms_dashboard(
    module: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    q: dict = {"organization_id": org_id}
    docs = await db.marketing_campaigns.find(q, {"_id": 0}).sort("created_at", -1).to_list(length=1000)
    docs = [_public_campaign(d) for d in docs]
    if module and module != "all":
        docs = [d for d in docs if d["related_module"] == module]

    by_status: dict[str, int] = {s: 0 for s in CAMPAIGN_STATUSES}
    by_module: dict[str, int] = {"marketing": 0, "memberships": 0, "crm": 0}
    totals = {"sent": 0, "opened": 0, "clicked": 0, "bounced": 0, "converted": 0}
    for d in docs:
        by_status[d.get("status", "draft")] = by_status.get(d.get("status", "draft"), 0) + 1
        by_module[d["related_module"]] = by_module.get(d["related_module"], 0) + 1
        m = d.get("metrics") or {}
        for k in totals:
            totals[k] += int(m.get(k, 0) or 0)
    open_rate = round(totals["opened"] / totals["sent"] * 100, 1) if totals["sent"] else 0.0
    click_rate = round(totals["clicked"] / totals["sent"] * 100, 1) if totals["sent"] else 0.0
    return {
        "total_campaigns": len(docs),
        "by_status": by_status,
        "by_module": by_module,
        "totals": totals,
        "open_rate": open_rate,
        "click_rate": click_rate,
        "recent": docs[:8],
    }


# ───────────────────────── Campaign CRUD ─────────────────────────

@router.get("/campaigns", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def list_comms_campaigns(
    module: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    docs = await db.marketing_campaigns.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).limit(500).to_list(length=500)
    out = [_public_campaign(d) for d in docs]
    if module and module != "all":
        out = [d for d in out if d["related_module"] == module]
    if type:
        out = [d for d in out if d.get("campaign_type") == type]
    if status:
        out = [d for d in out if d.get("status") == status]
    if q:
        ql = q.lower()
        out = [d for d in out if ql in (d.get("name") or "").lower()]
    return {"campaigns": out}


@router.post("/campaigns", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def create_comms_campaign(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    ct = (body.get("campaign_type") or "regular").strip()
    if ct not in _CAMPAIGN_TYPE_IDS:
        raise HTTPException(400, f"Unknown campaign_type '{ct}'")
    related_module = (body.get("related_module") or _CAMPAIGN_TYPE_MODULE.get(ct, "marketing")).strip()
    content = body.get("content") or {}
    if content.get("blocks") and not content.get("body_html"):
        content["body_html"] = render_blocks_to_html(content["blocks"])
    doc = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "owner": user["id"], "owner_name": user.get("name") or user.get("email") or "",
        "name": (body.get("name") or "Untitled campaign").strip()[:160],
        "campaign_type": ct, "related_module": related_module,
        "status": "draft", "channel": body.get("channel", "email"),
        "conversion_goal": (body.get("conversion_goal") or "").strip()[:120],
        "audience_id": body.get("audience_id"),
        "audience_inline": body.get("audience_inline"),
        "dynamic_list_id": body.get("dynamic_list_id"),
        "segment_id": body.get("segment_id"),
        "content": content,
        "variants": [],
        "ab_test": {"enabled": False},
        "approval": {"status": "none", "reviewer": None, "notes": ""},
        "tags": body.get("tags") or [],
        "schedule": body.get("schedule") or {},
        "tracking": body.get("tracking") or {
            "utm_source": "pulsefitnessai", "utm_medium": "email",
        },
        "metrics": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0,
                    "bounced": 0, "converted": 0, "revenue_gbp": 0},
        "created_at": _now_iso(), "updated_at": _now_iso(), "sent_at": None,
    }
    await db.marketing_campaigns.insert_one(doc)
    return {"campaign": _public_campaign(doc)}


@router.get("/campaigns/{campaign_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def get_comms_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    doc = await _get_owned(campaign_id, org_id)
    return {"campaign": doc, "quality": _quality_checks(doc)}


_EDITABLE = {
    "name", "campaign_type", "related_module", "channel", "conversion_goal",
    "audience_id", "audience_inline", "dynamic_list_id", "segment_id", "schedule",
    "tracking", "tags", "content",
}


@router.put("/campaigns/{campaign_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def update_comms_campaign(
    campaign_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    existing = await _get_owned(campaign_id, org_id)
    if existing.get("status") in ("sending", "sent"):
        raise HTTPException(400, "A sent campaign cannot be edited. Duplicate it instead.")
    updates: dict = {"updated_at": _now_iso()}
    for k in _EDITABLE:
        if k in body:
            updates[k] = body[k]
    if "campaign_type" in updates and updates["campaign_type"] not in _CAMPAIGN_TYPE_IDS:
        raise HTTPException(400, "Unknown campaign_type")
    if "content" in updates:
        content = updates["content"] or {}
        if content.get("blocks") is not None:
            content["body_html"] = render_blocks_to_html(content["blocks"])
        updates["content"] = content
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id}, {"$set": updates},
    )
    doc = await _get_owned(campaign_id, org_id)
    return {"campaign": doc, "quality": _quality_checks(doc)}


@router.post("/campaigns/{campaign_id}/duplicate", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def duplicate_comms_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    src = await _get_owned(campaign_id, org_id)
    clone = {**src}
    clone["id"] = _new_id()
    clone["name"] = f"{src.get('name','Campaign')} (copy)"[:160]
    clone["status"] = "draft"
    clone["approval"] = {"status": "none", "reviewer": None, "notes": ""}
    clone["metrics"] = {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0,
                        "bounced": 0, "converted": 0, "revenue_gbp": 0}
    clone["created_at"] = _now_iso()
    clone["updated_at"] = _now_iso()
    clone["sent_at"] = None
    clone["created_by"] = user["id"]
    clone["owner"] = user["id"]
    await db.marketing_campaigns.insert_one(clone)
    return {"campaign": _public_campaign(clone)}


@router.post("/campaigns/{campaign_id}/status", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def set_comms_status(
    campaign_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    existing = await _get_owned(campaign_id, org_id)
    new_status = (body.get("status") or "").strip()
    if new_status not in CAMPAIGN_STATUSES:
        raise HTTPException(400, "Unknown status")
    cur = existing.get("status", "draft")
    if new_status != cur and new_status not in _STATUS_TRANSITIONS.get(cur, set()):
        raise HTTPException(400, f"Cannot move from '{cur}' to '{new_status}'")
    updates: dict = {"status": new_status, "updated_at": _now_iso()}
    approval = existing.get("approval") or {"status": "none", "reviewer": None, "notes": ""}
    if new_status == "in_review":
        approval = {"status": "pending", "reviewer": None, "notes": body.get("notes", "")}
    elif new_status == "approved":
        approval = {"status": "approved", "reviewer": user.get("email"), "notes": body.get("notes", "")}
    elif new_status == "changes_requested":
        approval = {"status": "changes_requested", "reviewer": user.get("email"), "notes": body.get("notes", "")}
    updates["approval"] = approval
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id}, {"$set": updates},
    )
    return {"ok": True, "status": new_status, "approval": approval}


@router.delete("/campaigns/{campaign_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def archive_comms_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    await _get_owned(campaign_id, org_id)
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id},
        {"$set": {"status": "archived", "updated_at": _now_iso()}},
    )
    return {"ok": True}


# ───────────────────────── Test send / preview ─────────────────────────

@router.get("/campaigns/{campaign_id}/preview", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def preview_comms_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    doc = await _get_owned(campaign_id, org_id)
    content = doc.get("content") or {}
    blocks = content.get("blocks") or []
    raw = render_blocks_to_html(blocks) if blocks else (content.get("body_html") or "")
    return {
        "subject": _apply_samples(content.get("subject") or doc.get("name") or ""),
        "html": _apply_samples(raw),
        "quality": _quality_checks(doc),
    }


@router.post("/campaigns/{campaign_id}/test-send", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def test_send_comms_campaign(
    campaign_id: str, body: dict = Body(default_factory=dict), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    doc = await _get_owned(campaign_id, org_id)
    to = (body.get("to") or user.get("email") or "").strip()
    if not to or "@" not in to:
        raise HTTPException(400, "A valid recipient email is required")
    content = doc.get("content") or {}
    blocks = content.get("blocks") or []
    raw = render_blocks_to_html(blocks) if blocks else (content.get("body_html") or "")
    subject = "[TEST] " + _apply_samples(content.get("subject") or doc.get("name") or "Pulse Fitness AI")
    html = _apply_samples(raw)
    category = _MODULE_EMAIL_CATEGORY.get(doc.get("related_module"), "support")
    try:
        from utils.email import send_email
        ok = await send_email(
            to=to, subject=subject, html=html,
            organization_id=org_id, category=category, kind="adhoc",
        )
    except Exception as exc:
        logger.info("[comms] test-send failed: %s", exc)
        ok = False
    return {"ok": bool(ok), "sent_to": to}


# ───────────────────────── Schedule / batch / timezone send ─────────────────────────

@router.post("/campaigns/{campaign_id}/schedule", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def schedule_comms_campaign(
    campaign_id: str, body: dict = Body(...), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    if camp.get("status") in ("sending", "sent"):
        raise HTTPException(400, "Campaign is already sending or sent.")
    content = camp.get("content") or {}
    if not (content.get("blocks") or content.get("body_html")):
        raise HTTPException(400, "Add some email content before scheduling.")
    if not camp.get("segment_id") and not camp.get("audience_inline"):
        raise HTTPException(400, "Choose an audience segment for this campaign first.")

    strategy = body.get("strategy", "scheduled")
    schedule = {
        "strategy": strategy,
        "send_at": body.get("send_at") if strategy == "scheduled" else _now_iso(),
        "batch_size": int(body.get("batch_size") or 0),
        "batch_interval_minutes": int(body.get("batch_interval_minutes") or 0),
        "timezone_mode": body.get("timezone_mode", "fixed"),
        "tz": body.get("tz", "Europe/London"),
        "local_hour": int(body.get("local_hour", 9)),
    }
    if strategy == "scheduled" and not schedule["send_at"]:
        raise HTTPException(400, "Pick a send date/time.")
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id},
        {"$set": {"schedule": schedule, "status": "scheduled", "updated_at": _now_iso()}},
    )
    if strategy == "immediate":
        from utils.comms_dispatch import activate_campaign
        camp["schedule"] = schedule
        count = await activate_campaign(camp)
        return {"ok": True, "status": "sending", "recipients": count}
    return {"ok": True, "status": "scheduled", "send_at": schedule["send_at"]}


@router.post("/campaigns/{campaign_id}/pause-send", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def pause_comms_send(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    if camp.get("status") not in ("sending", "scheduled"):
        raise HTTPException(400, "Campaign is not sending or scheduled.")
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id},
        {"$set": {"status": "paused", "updated_at": _now_iso()}},
    )
    return {"ok": True, "status": "paused"}


@router.post("/campaigns/{campaign_id}/resume-send", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def resume_comms_send(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    if camp.get("status") != "paused":
        raise HTTPException(400, "Campaign is not paused.")
    # if a queue exists it's mid-send → resume to sending; else back to scheduled
    queued = await db.marketing_messages.count_documents({"campaign_id": campaign_id, "status": "queued"})
    new_status = "sending" if queued else "scheduled"
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id},
        {"$set": {"status": new_status, "updated_at": _now_iso()}},
    )
    return {"ok": True, "status": new_status}


@router.get("/campaigns/{campaign_id}/dispatch", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def dispatch_progress(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    queued = await db.marketing_messages.count_documents({"campaign_id": campaign_id, "status": "queued"})
    metrics = camp.get("metrics") or {}
    total = (camp.get("schedule") or {}).get("total", 0) or (queued + int(metrics.get("sent", 0)) + int(metrics.get("bounced", 0)))
    return {
        "status": camp.get("status"), "total": total, "queued": queued,
        "sent": int(metrics.get("sent", 0)), "bounced": int(metrics.get("bounced", 0)),
        "schedule": camp.get("schedule") or {},
    }


# ───────────────────────── Open / click tracking (unauthenticated) ─────────────────────────

_PIXEL = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cb\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@router.get("/t/o/{message_id}")
async def comms_track_open(message_id: str):
    msg = await db.marketing_messages.find_one({"id": message_id}, {"_id": 0, "opened_at": 1, "campaign_id": 1})
    if msg:
        first = not msg.get("opened_at")
        await db.marketing_messages.update_one(
            {"id": message_id},
            {"$set": {"opened_at": _now_iso()}, "$push": {"events": {"type": "open", "at": _now_iso()}}},
        )
        if first:
            await db.marketing_campaigns.update_one(
                {"id": msg.get("campaign_id")}, {"$inc": {"metrics.opened": 1}})
    return Response(content=_PIXEL, media_type="image/png", headers={"Cache-Control": "no-cache, no-store"})


@router.get("/t/c/{message_id}")
async def comms_track_click(message_id: str, u: str = ""):
    try:
        url = base64.urlsafe_b64decode(u.encode()).decode() if u else "https://pulsefitness.ai"
    except Exception:
        url = "https://pulsefitness.ai"
    if not url.startswith(("http://", "https://")):
        url = "https://pulsefitness.ai"
    msg = await db.marketing_messages.find_one(
        {"id": message_id}, {"_id": 0, "opened_at": 1, "clicked_at": 1, "campaign_id": 1})
    if msg:
        inc: dict = {}
        if not msg.get("clicked_at"):
            inc["metrics.clicked"] = 1
        if not msg.get("opened_at"):
            inc["metrics.opened"] = 1  # a click implies an open
        await db.marketing_messages.update_one(
            {"id": message_id},
            {"$set": {"clicked_at": _now_iso(), "opened_at": msg.get("opened_at") or _now_iso()},
             "$push": {"events": {"type": "click", "at": _now_iso(), "url": url}}},
        )
        if inc:
            await db.marketing_campaigns.update_one({"id": msg.get("campaign_id")}, {"$inc": inc})
    return RedirectResponse(url, status_code=302)


@router.post("/conversions", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def log_conversion(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Record a conversion and attribute it to a recent comms campaign."""
    org_id = await _org_id(user)
    from utils.comms_conversions import record_conversion
    ok = await record_conversion(
        org_id, body.get("email", ""), body.get("type", "conversion"),
        value_gbp=float(body.get("value_gbp", 0) or 0), source=body.get("source", "manual"),
        meta=body.get("meta"),
    )
    return {"ok": ok}
