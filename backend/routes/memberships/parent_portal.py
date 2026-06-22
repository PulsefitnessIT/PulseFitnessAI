"""Parent / member portal extras — Phase C (iter 216ab).

Bundles four small but high-impact studio-portal capabilities:

  1. Consent forms (operator CRUD + member sign)
  2. Web Push subscriptions (member opt-in / opt-out)
  3. Industry vocabulary lookup (so the UI can swap "member" ↔
     "student" / "athlete" / "swimmer" based on the studio preset)
  4. Public trial-class discovery & booking (anonymous lead capture)

Collections:
  • consent_forms        { id, organization_id, title, body_html, version,
                           required, archived, created_at, updated_at }
  • consent_signatures   { id, organization_id, member_id, sub_profile_id?,
                           form_id, version, signed_at, signature_text,
                           ip_hash }
  • push_subscriptions   { id, organization_id, member_id, endpoint,
                           keys: {p256dh, auth}, user_agent, created_at,
                           last_seen_at }
  • trial_signups        { id, organization_id, occurrence_id, name,
                           email, phone, attendee_age, source,
                           created_at }
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-parent-portal"])

_INDUSTRY_DEFAULT_NOUNS = {
    "member_singular": "member",
    "member_plural":   "members",
    "guardian_noun":   "guardian",
    "label":           "Studio",
}


# ─────────────────────────────────────────────────────────────────
# Vocabulary
# ─────────────────────────────────────────────────────────────────

@router.get("/memberships/studio/vocabulary")
async def get_studio_vocabulary(user=Depends(get_current_user)):
    """Return the active studio's noun preset so the UI can swap copy."""
    org_id = await _require_operator_org(user)
    return await _resolve_vocabulary(org_id)


@router.get("/member/studio/vocabulary")
async def get_member_studio_vocabulary(member: dict = Depends(_require_current_member)):
    """Member-side mirror — used by the parent portal to brand its copy
    in the studio's native vocabulary (e.g. "athlete" for cheer)."""
    return await _resolve_vocabulary(member["organization_id"])


async def _resolve_vocabulary(org_id: str) -> dict:
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "studio_industry": 1, "name": 1},
    ) or {}
    industry = org.get("studio_industry")
    # Lazy-import the preset dictionary from studio.py so we keep one source of truth.
    try:
        from routes.memberships.studio import _INDUSTRY_PRESETS
    except Exception:
        _INDUSTRY_PRESETS = {}
    preset = _INDUSTRY_PRESETS.get(industry) if industry else None
    if not preset:
        return {"industry": industry, "studio_name": org.get("name"),
                **_INDUSTRY_DEFAULT_NOUNS}
    return {
        "industry": industry,
        "studio_name": org.get("name"),
        "label": preset.get("label") or "Studio",
        "member_singular": preset.get("noun_singular") or "member",
        "member_plural":   preset.get("noun_plural") or "members",
        "guardian_noun":   preset.get("guardian_noun") or "guardian",
    }


# ─────────────────────────────────────────────────────────────────
# Consent forms — operator CRUD
# ─────────────────────────────────────────────────────────────────

class ConsentFormIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body_html: str = Field(min_length=10, max_length=20_000)
    required: bool = True


@router.get(
    "/memberships/consent-forms",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_list_forms(user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.consent_forms.find(
        {"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"forms": rows, "count": len(rows)}


@router.post(
    "/memberships/consent-forms",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_create_form(body: ConsentFormIn, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage consent forms.")
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "title": body.title.strip(),
        "body_html": body.body_html,
        "version": 1,
        "required": bool(body.required),
        "archived": False,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "created_by_id": user.get("id"),
    }
    await db.consent_forms.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put(
    "/memberships/consent-forms/{form_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_update_form(
    form_id: str, body: ConsentFormIn = Body(...),
    user=Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage consent forms.")
    # Bumping the body invalidates prior signatures: increment version so members re-sign.
    existing = await db.consent_forms.find_one(
        {"id": form_id, "organization_id": org_id}, {"_id": 0, "version": 1, "body_html": 1},
    )
    if not existing:
        raise HTTPException(404, "Form not found")
    new_version = int(existing.get("version") or 1)
    if body.body_html.strip() != (existing.get("body_html") or "").strip():
        new_version += 1
    await db.consent_forms.update_one(
        {"id": form_id, "organization_id": org_id},
        {"$set": {"title": body.title.strip(), "body_html": body.body_html,
                  "required": bool(body.required), "version": new_version,
                  "updated_at": _now_iso()}},
    )
    return await db.consent_forms.find_one({"id": form_id}, {"_id": 0})


@router.delete(
    "/memberships/consent-forms/{form_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_archive_form(form_id: str, user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can manage consent forms.")
    res = await db.consent_forms.update_one(
        {"id": form_id, "organization_id": org_id},
        {"$set": {"archived": True, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Form not found")
    return {"ok": True, "id": form_id}


# ─────────────────────────────────────────────────────────────────
# Consent forms — member-facing list & sign
# ─────────────────────────────────────────────────────────────────

@router.get("/member/consent-forms")
async def member_list_forms(member: dict = Depends(_require_current_member)):
    """Returns every active form for the member's org along with the
    member's signing state (signed bool, signed version, signed at)."""
    org_id = member["organization_id"]
    forms = await db.consent_forms.find(
        {"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    sigs = await db.consent_signatures.find(
        {"organization_id": org_id, "member_id": member["id"]},
        {"_id": 0, "form_id": 1, "version": 1, "signed_at": 1},
    ).to_list(500)
    sig_by_form: dict[str, dict] = {}
    for s in sigs:
        cur = sig_by_form.get(s["form_id"])
        if not cur or int(s.get("version") or 0) > int(cur.get("version") or 0):
            sig_by_form[s["form_id"]] = s
    rows = []
    for f in forms:
        sig = sig_by_form.get(f["id"])
        rows.append({
            **f,
            "signed": bool(sig and int(sig.get("version") or 0) >= int(f.get("version") or 1)),
            "signed_version": (sig or {}).get("version"),
            "signed_at": (sig or {}).get("signed_at"),
        })
    pending_required = sum(1 for r in rows if r.get("required") and not r["signed"])
    return {"forms": rows, "count": len(rows), "pending_required": pending_required}


class SignIn(BaseModel):
    signature_text: str = Field(min_length=2, max_length=120)
    sub_profile_id: Optional[str] = None


@router.post("/member/consent-forms/{form_id}/sign")
async def member_sign_form(
    form_id: str, body: SignIn = Body(...), request: Request = None,
    member: dict = Depends(_require_current_member),
):
    org_id = member["organization_id"]
    form = await db.consent_forms.find_one(
        {"id": form_id, "organization_id": org_id, "archived": {"$ne": True}},
    )
    if not form:
        raise HTTPException(404, "Form not found")
    ip = (request.client.host if request and request.client else "") or ""
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else ""
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "member_id": member["id"],
        "sub_profile_id": body.sub_profile_id,
        "form_id": form_id,
        "version": int(form.get("version") or 1),
        "signature_text": body.signature_text.strip(),
        "ip_hash": ip_hash,
        "signed_at": _now_iso(),
    }
    await db.consent_signatures.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "signature": doc}


# ─────────────────────────────────────────────────────────────────
# Web Push subscriptions
# ─────────────────────────────────────────────────────────────────

class PushSubIn(BaseModel):
    endpoint: str = Field(min_length=10)
    keys: dict
    user_agent: Optional[str] = None


@router.post("/member/push/subscribe")
async def member_push_subscribe(
    body: PushSubIn, member: dict = Depends(_require_current_member),
):
    org_id = member["organization_id"]
    # Deduplicate by (member, endpoint).
    existing = await db.push_subscriptions.find_one(
        {"organization_id": org_id, "member_id": member["id"], "endpoint": body.endpoint},
        {"_id": 0, "id": 1},
    )
    now = _now_iso()
    if existing:
        await db.push_subscriptions.update_one(
            {"id": existing["id"]},
            {"$set": {"keys": body.keys, "user_agent": body.user_agent or "",
                      "last_seen_at": now}},
        )
        return {"ok": True, "id": existing["id"], "kept": True}
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "member_id": member["id"],
        "endpoint": body.endpoint,
        "keys": body.keys,
        "user_agent": body.user_agent or "",
        "created_at": now,
        "last_seen_at": now,
    }
    await db.push_subscriptions.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "id": doc["id"], "kept": False}


@router.delete("/member/push/subscribe/{sub_id}")
async def member_push_unsubscribe(
    sub_id: str, member: dict = Depends(_require_current_member),
):
    res = await db.push_subscriptions.delete_one(
        {"id": sub_id, "member_id": member["id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Subscription not found")
    return {"ok": True}


@router.get(
    "/operator/push-subscriptions/count",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_push_count(user=Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    n = await db.push_subscriptions.count_documents({"organization_id": org_id})
    return {"count": n}


# ─────────────────────────────────────────────────────────────────
# Public trial-class discovery & booking
# ─────────────────────────────────────────────────────────────────

@router.get("/public/trial-classes")
async def public_trial_classes(
    org_slug: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Anonymous endpoint for the public booking page. Returns upcoming
    occurrences whose template is flagged ``trial_eligible``."""
    org = await db.organizations.find_one(
        {"$or": [{"slug": org_slug}, {"id": org_slug}]},
        {"_id": 0, "id": 1, "name": 1},
    )
    if not org:
        raise HTTPException(404, "Studio not found")
    now = _now_iso()
    tpl_ids = [t["id"] for t in await db.class_templates.find(
        {"organization_id": org["id"], "trial_eligible": True,
         "archived": {"$ne": True}},
        {"_id": 0, "id": 1},
    ).to_list(200)]
    if not tpl_ids:
        return {"studio": org["name"], "occurrences": [], "count": 0}
    occs = await db.class_occurrences.find(
        {"organization_id": org["id"], "template_id": {"$in": tpl_ids},
         "starts_at": {"$gte": now}, "status": "scheduled"},
        {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "ends_at": 1,
         "instructor_name": 1, "room_name": 1, "capacity": 1,
         "bookings_count": 1, "min_age": 1, "max_age": 1, "skill_level": 1,
         "discipline": 1, "colour": 1},
    ).sort("starts_at", 1).limit(limit).to_list(limit)
    return {"studio": org["name"], "occurrences": occs, "count": len(occs)}


class TrialBookingIn(BaseModel):
    org_slug: str
    occurrence_id: str
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    attendee_age: Optional[int] = Field(default=None, ge=0, le=120)
    notes: Optional[str] = Field(default=None, max_length=400)
    source: Optional[str] = Field(default="public_form", max_length=40)


@router.post("/public/trial-bookings")
async def public_trial_booking(body: TrialBookingIn):
    org = await db.organizations.find_one(
        {"$or": [{"slug": body.org_slug}, {"id": body.org_slug}]},
        {"_id": 0, "id": 1, "name": 1, "owner_email": 1},
    )
    if not org:
        raise HTTPException(404, "Studio not found")
    occ = await db.class_occurrences.find_one(
        {"id": body.occurrence_id, "organization_id": org["id"]},
        {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "capacity": 1, "bookings_count": 1},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    if (occ.get("bookings_count") or 0) >= int(occ.get("capacity") or 0):
        raise HTTPException(409, "This class is fully booked")
    doc = {
        "id": _uuid(),
        "organization_id": org["id"],
        "occurrence_id": body.occurrence_id,
        "name": body.name.strip(),
        "email": body.email.lower(),
        "phone": body.phone or "",
        "attendee_age": body.attendee_age,
        "notes": (body.notes or "").strip(),
        "source": body.source or "public_form",
        "created_at": _now_iso(),
    }
    await db.trial_signups.insert_one(doc)
    # Bump capacity counter so the slot fills as expected.
    await db.class_occurrences.update_one(
        {"id": body.occurrence_id},
        {"$inc": {"bookings_count": 1}},
    )
    # Notify the studio (best-effort; never block the response).
    try:
        owner_email = (org.get("owner_email") or "").strip()
        if owner_email and "@" in owner_email:
            await send_email(
                to=owner_email,
                subject=f"New trial signup — {body.name} for {occ.get('name')}",
                html=(
                    f"<p>{body.name} ({body.email}) booked a trial class for "
                    f"<strong>{occ.get('name')}</strong> on "
                    f"<strong>{(occ.get('starts_at') or '')[:16]}</strong>.</p>"
                    f"<p>Phone: {body.phone or '—'} · Age: {body.attendee_age or '—'}</p>"
                    f"<p>Notes: {body.notes or '—'}</p>"
                ),
                category="bookings",
            )
        # Confirmation to the lead.
        if body.email:
            await send_email(
                to=body.email,
                subject=f"You're booked in — {occ.get('name')}",
                html=(
                    f"<p>Hi {body.name.split()[0] if body.name else 'there'},</p>"
                    f"<p>You're confirmed for <strong>{occ.get('name')}</strong> "
                    f"on <strong>{(occ.get('starts_at') or '')[:16]}</strong> at "
                    f"<strong>{org.get('name')}</strong>.</p>"
                    f"<p>We can't wait to meet you!</p>"
                ),
                category="bookings",
            )
    except Exception:
        logger.warning("trial signup notify failed", exc_info=True)
    doc.pop("_id", None)
    return {"ok": True, "trial_id": doc["id"]}


__all__ = ["router"]
