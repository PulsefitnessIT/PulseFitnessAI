"""Notification preferences (iter 215c0).

Granular email/SMS opt-in/out for both operators and members. Mandatory
under UK GDPR + PECR — every transactional system email must respect a
member's `transactional` flag (kept on by default but changeable for
auditing/regulatory obligations) and every marketing email respects
`marketing`.

Storage: `notification_prefs` keyed by (subject_kind, subject_id) where
`subject_kind` is `user` or `member`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from routes.memberships.helpers import _require_current_member
from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db

router = APIRouter(tags=["notifications"])


# Keys are categories the platform can send. Booleans are sane defaults.
DEFAULT_OPERATOR_PREFS: dict[str, bool] = {
    "transactional": True,        # password reset, invoice receipts (cannot be turned off legally for some)
    "product_updates": True,      # what's new emails, security advisories
    "marketing": False,           # third-party promo
    "weekly_digest": True,        # operator weekly summary
    "billing_alerts": True,       # failed payment, low balance, trial expiry
    "feature_tips": True,         # nudges, in-app help (also used by tour)
    "sms": False,                 # opt in to operator SMS alerts
}

DEFAULT_MEMBER_PREFS: dict[str, bool] = {
    "transactional": True,        # booking confirmations, receipts
    "class_reminders": True,      # 24h-before SMS/email
    "marketing": False,           # studio promos, new plans
    "winback": False,             # reactivation campaigns
    "billing_alerts": True,       # payment failed, plan renewal
    "newsletter": False,          # studio newsletter
    "sms": True,                  # required for class reminders
}


async def _load_prefs(subject_kind: str, subject_id: str, defaults: dict[str, bool]) -> dict:
    doc = await db.notification_prefs.find_one(
        {"subject_kind": subject_kind, "subject_id": subject_id},
        {"_id": 0},
    )
    if not doc:
        return {"prefs": dict(defaults), "updated_at": None}
    # Merge over defaults so newly added keys appear in the response.
    merged = dict(defaults)
    for k, v in (doc.get("prefs") or {}).items():
        if k in merged:
            merged[k] = bool(v)
    return {"prefs": merged, "updated_at": doc.get("updated_at")}


async def _save_prefs(subject_kind: str, subject_id: str, prefs_in: dict, defaults: dict[str, bool]) -> dict:
    # Whitelist + coerce — never accept arbitrary keys from the client.
    sanitized = {k: bool(prefs_in.get(k, defaults[k])) for k in defaults}
    now = datetime.now(timezone.utc).isoformat()
    await db.notification_prefs.update_one(
        {"subject_kind": subject_kind, "subject_id": subject_id},
        {"$set": {
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "prefs": sanitized,
            "updated_at": now,
        }},
        upsert=True,
    )
    return {"prefs": sanitized, "updated_at": now}


# ── Operator prefs ────────────────────────────────────────────
@router.get("/me/notification-preferences")
async def get_my_operator_prefs(user: dict = Depends(get_current_user)) -> dict:
    return await _load_prefs("user", user["id"], DEFAULT_OPERATOR_PREFS)


@router.put("/me/notification-preferences")
async def update_my_operator_prefs(
    payload: dict, request: Request, user: dict = Depends(get_current_user),
) -> dict:
    saved = await _save_prefs("user", user["id"], payload.get("prefs") or payload, DEFAULT_OPERATOR_PREFS)
    ip = request.client.host if request.client else ""
    await audit_log(
        "notification_prefs_update", user["id"], user.get("email", ""),
        "user", user["id"], "Updated notification preferences", ip,
    )
    return saved


# ── Member prefs (member-portal token) ────────────────────────
@router.get("/portal/me/notification-preferences")
async def get_my_member_prefs(member: dict = Depends(_require_current_member)) -> dict:
    return await _load_prefs("member", member["id"], DEFAULT_MEMBER_PREFS)


@router.put("/portal/me/notification-preferences")
async def update_my_member_prefs(
    payload: dict, request: Request, member: dict = Depends(_require_current_member),
) -> dict:
    saved = await _save_prefs("member", member["id"], payload.get("prefs") or payload, DEFAULT_MEMBER_PREFS)
    ip = request.client.host if request.client else ""
    await audit_log(
        "notification_prefs_update", member["id"], member.get("email", ""),
        "member", member["id"], "Member updated notification preferences", ip,
    )
    return saved


# Helper for backend code that needs to gate a send.
async def can_send(subject_kind: str, subject_id: str, category: str) -> bool:
    if subject_kind not in ("user", "member"):
        return True
    defaults = DEFAULT_OPERATOR_PREFS if subject_kind == "user" else DEFAULT_MEMBER_PREFS
    if category not in defaults:
        return True  # unknown category falls through (don't accidentally suppress sends)
    res = await _load_prefs(subject_kind, subject_id, defaults)
    return bool(res["prefs"].get(category, defaults[category]))


@router.get("/portal/me/notification-preferences/check")
async def check_send_consent(category: str, member: dict = Depends(_require_current_member)) -> dict:
    """Member-portal probe — useful for the consent page UI to test a category."""
    if category not in DEFAULT_MEMBER_PREFS:
        raise HTTPException(status_code=400, detail="Unknown category")
    return {"category": category, "can_send": await can_send("member", member["id"], category)}
