"""Secure, single-use invitations (Release C).

One service for owner activation (imported customers) and staff invitations.
- Tokens are random 32-byte values; only a SHA-256 hash is stored.
- The link carries the token in the URL fragment (#token=...), so mail scanners
  that fetch the link never send it to the server. Nothing happens on GET:
  inspection and acceptance are explicit POSTs from the page.
- Single use: acceptance claims the invitation atomically (pending -> accepting).
- Emails are HELD (not sent) unless INVITATION_EMAILS_LIVE=true.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from utils.database import db

logger = logging.getLogger(__name__)

OWNER_TTL_HOURS = 72
STAFF_TTL_HOURS = 72
VERIFICATION_METHODS = {
    "sage_contact": "Matches the contact on the Sage / Sicon account",
    "phone_callback": "Phoned back on the number held on the account",
    "known_contact": "Known to the account manager",
    "written_confirmation": "Written confirmation from the customer",
}
_IDX = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def emails_live() -> bool:
    return os.environ.get("INVITATION_EMAILS_LIVE", "").strip().lower() == "true"


def _frontend_url() -> str:
    return (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


def invite_link(token: str) -> str:
    return f"{_frontend_url()}/accept-invite#token={token}"


def mask_email(email: str) -> str:
    name, _, dom = (email or "").partition("@")
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{dom}" if dom else email


def public_view(inv: dict) -> dict:
    return {k: inv.get(k) for k in (
        "id", "kind", "organization_id", "organization_name", "email", "full_name", "role", "allowed_site_ids",
        "require_mfa", "status", "expires_at", "created_at", "created_by_email", "accepted_at", "revoked_at",
        "verification", "delivery")}


async def ensure_indexes() -> None:
    global _IDX
    if _IDX:
        return
    await db.secure_invitations.create_index("token_hash", unique=True)
    await db.secure_invitations.create_index([("organization_id", 1), ("email", 1), ("status", 1)])
    await db.secure_invitations.create_index(
        [("organization_id", 1), ("email", 1)], unique=True, name="one_pending_invite",
        partialFilterExpression={"status": "pending"})
    _IDX = True


def org_awaiting_activation(org: Optional[dict]) -> bool:
    return bool(org) and (org.get("onboarding_status") == "pending_activation" or org.get("portal_access") == "not_activated")


def _expired(inv: dict) -> bool:
    try:
        return datetime.fromisoformat(inv["expires_at"]) <= _now()
    except Exception:
        return True


async def _audit(event: str, inv: dict, actor: Optional[dict] = None, **extra) -> None:
    await db.onboarding_audit_events.insert_one({
        "id": str(uuid.uuid4()), "event": event, "invitation_id": inv.get("id"), "kind": inv.get("kind"),
        "org_id": inv.get("organization_id"), "email": inv.get("email"), "role": inv.get("role"),
        "actor_id": (actor or {}).get("id"), "actor_email": (actor or {}).get("email"),
        "at": _now().isoformat(), **extra})


async def _deliver(inv: dict, token: str, inviter_name: str) -> dict:
    link = invite_link(token)
    if not emails_live():
        return {"mode": "held", "at": _now().isoformat(),
                "note": "Email held: invitation emails are switched off (INVITATION_EMAILS_LIVE)."}
    from utils.email import send_activation_invite_email
    ok = await send_activation_invite_email(inv, link, inviter_name)
    return {"mode": "sent" if ok else "failed", "at": _now().isoformat()}


async def create_invitation(*, kind: str, org: dict, email: str, full_name: str, role: str, actor: dict,
                            allowed_site_ids: Optional[list] = None, require_mfa: bool = False,
                            verification: Optional[dict] = None) -> dict:
    """Create (and supersede any pending) invitation. Returns {invitation, delivery, link?}."""
    await ensure_indexes()
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email address is required")
    existing = await db.users.find_one({"email": email}, {"_id": 0, "organization_id": 1})
    if existing:
        if existing.get("organization_id") == org["id"]:
            raise HTTPException(409, "This person already has a login in this organisation")
        # One person = one identity. Until multi-organisation access exists, flag for review instead of duplicating.
        await db.organizations.update_one({"id": org["id"]}, {"$set": {"activation_review_required": {
            "reason": "person_has_login_in_another_organisation", "email": email, "kind": kind,
            "flagged_by": actor.get("id"), "at": _now().isoformat()}}})
        raise HTTPException(409, "This person already has a Pulse Fitness login with another organisation. "
                                 "The customer has been flagged for activation review until multi-organisation access is available.")
    now = _now()
    # One owner invitation per organisation (any email); otherwise one per person.
    sup = {"organization_id": org["id"], "status": "pending"}
    sup.update({"kind": "owner_activation"} if kind == "owner_activation" else {"email": email})
    await db.secure_invitations.update_many(sup, {"$set": {"status": "superseded", "superseded_at": now.isoformat()}})
    token = secrets.token_urlsafe(32)
    ttl = OWNER_TTL_HOURS if kind == "owner_activation" else STAFF_TTL_HOURS
    inv = {
        "id": str(uuid.uuid4()), "kind": kind, "organization_id": org["id"], "organization_name": org.get("name", ""),
        "email": email, "full_name": (full_name or "").strip()[:120], "role": role,
        "allowed_site_ids": [str(s) for s in (allowed_site_ids or []) if s], "require_mfa": bool(require_mfa),
        "token_hash": token_hash(token), "expires_at": (now + timedelta(hours=ttl)).isoformat(),
        "status": "pending", "created_by": actor.get("id"), "created_by_email": actor.get("email"),
        "created_at": now.isoformat(), "verification": verification, "failed_attempts": 0,
    }
    try:
        await db.secure_invitations.insert_one(dict(inv))
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise HTTPException(409, "Another invitation for this person was created at the same moment. Refresh and try again.")
        raise
    delivery = await _deliver(inv, token, actor.get("full_name") or "Pulse Fitness")
    await db.secure_invitations.update_one({"id": inv["id"]}, {"$set": {"delivery": delivery}})
    inv["delivery"] = delivery
    await _audit("invitation.created", inv, actor, delivery=delivery["mode"])
    out = {"invitation": public_view(inv), "delivery": delivery}
    if delivery["mode"] == "held":
        # Test mode only: the one-time link is shown once to the person who created it, never stored.
        out["link"] = invite_link(token)
    return out


async def revoke(inv_id: str, actor: dict, org_id: Optional[str] = None, kind: Optional[str] = None) -> dict:
    q = {"id": inv_id, "status": "pending"}
    if org_id:
        q["organization_id"] = org_id
    if kind:
        q["kind"] = kind
    inv = await db.secure_invitations.find_one_and_update(
        q, {"$set": {"status": "revoked", "revoked_at": _now().isoformat(), "revoked_by": actor.get("id")}},
        projection={"_id": 0})
    if not inv:
        raise HTTPException(404, "No pending invitation found")
    await _audit("invitation.revoked", inv, actor)
    return public_view({**inv, "status": "revoked"})


async def reissue(inv_id: str, actor: dict, org_id: Optional[str] = None, kind: Optional[str] = None) -> dict:
    q = {"id": inv_id, "status": {"$in": ["pending", "expired"]}}
    if org_id:
        q["organization_id"] = org_id
    if kind:
        q["kind"] = kind
    inv = await db.secure_invitations.find_one(q, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Only a pending or expired invitation can be re-sent")
    org = await db.organizations.find_one({"id": inv["organization_id"]}, {"_id": 0})
    if inv["kind"] == "owner_activation" and not org_awaiting_activation(org):
        raise HTTPException(409, "This customer is already activated. Their owner invites staff from Settings.")
    return await create_invitation(kind=inv["kind"], org=org, email=inv["email"], full_name=inv.get("full_name", ""),
                                   role=inv["role"], actor=actor, allowed_site_ids=inv.get("allowed_site_ids"),
                                   require_mfa=inv.get("require_mfa", False), verification=inv.get("verification"))


async def _find(token: str) -> Optional[dict]:
    if not token or len(token) < 20:
        return None
    return await db.secure_invitations.find_one({"token_hash": token_hash(token)}, {"_id": 0})


def _state(inv: Optional[dict]) -> str:
    if not inv:
        return "invalid"
    if inv["status"] == "accepting" and inv.get("accepting_at", "") < (_now() - timedelta(minutes=5)).isoformat():
        return "valid" if not _expired(inv) else "expired"  # interrupted acceptance can be retried
    if inv["status"] == "pending" and _expired(inv):
        return "expired"
    return {"pending": "valid", "accepted": "used", "accepting": "used"}.get(inv["status"], "revoked")


async def inspect(token: str) -> dict:
    inv = await _find(token)
    state = _state(inv)
    if state == "invalid":
        return {"state": "invalid"}
    return {"state": state, "kind": inv["kind"], "organization_name": inv.get("organization_name"),
            "email_hint": mask_email(inv["email"]), "full_name": inv.get("full_name"), "role": inv["role"],
            "require_mfa": inv.get("require_mfa", False), "expires_at": inv["expires_at"]}


_STATE_MSG = {"invalid": "This invitation link is not valid.",
              "expired": "This invitation has expired. Ask for a new one.",
              "used": "This invitation has already been used. Sign in instead.",
              "revoked": "This invitation was cancelled. Ask for a new one."}


async def accept(token: str, *, full_name: str, password: str, email_confirm: str) -> dict:
    from utils.auth import hash_password
    from utils.security import validate_password_strength, assert_password_not_breached
    inv = await _find(token)
    state = _state(inv)
    if state != "valid":
        raise HTTPException(410 if state != "invalid" else 400, _STATE_MSG[state])
    if (email_confirm or "").strip().lower() != inv["email"]:
        after = await db.secure_invitations.find_one_and_update(
            {"id": inv["id"]}, {"$inc": {"failed_attempts": 1}}, projection={"_id": 0, "failed_attempts": 1},
            return_document=True)
        if (after or {}).get("failed_attempts", 0) >= 5:
            await db.secure_invitations.update_one({"id": inv["id"], "status": "pending"},
                                                   {"$set": {"status": "revoked", "revoked_at": _now().isoformat(),
                                                             "revoked_reason": "too_many_attempts"}})
            await _audit("invitation.locked", inv)
        raise HTTPException(400, "That email address doesn't match this invitation")
    validate_password_strength(password)
    await assert_password_not_breached(password)
    stale = (_now() - timedelta(minutes=5)).isoformat()
    claimed = await db.secure_invitations.find_one_and_update(
        {"id": inv["id"], "expires_at": {"$gt": _now().isoformat()},
         "$or": [{"status": "pending"}, {"status": "accepting", "accepting_at": {"$lt": stale}}]},
        {"$set": {"status": "accepting", "accepting_at": _now().isoformat()}}, projection={"_id": 0})
    if not claimed:
        raise HTTPException(410, _STATE_MSG["used"])
    if claimed["kind"] == "owner_activation" and not org_awaiting_activation(
            await db.organizations.find_one({"id": claimed["organization_id"]}, {"_id": 0})):
        await db.secure_invitations.update_one({"id": inv["id"]}, {"$set": {
            "status": "revoked", "revoked_at": _now().isoformat(), "revoked_reason": "organisation_already_activated"}})
        raise HTTPException(410, "This organisation has already been activated. Ask its owner to invite you.")
    try:
        # Recovery: an interrupted earlier attempt may already have created this person's login.
        user = await db.users.find_one({"invited_via": claimed["id"]}, {"_id": 0})
        if user:
            await db.users.update_one({"id": user["id"]}, {"$set": {"password": hash_password(password)}})
        else:
            user = await _create_user(claimed, full_name, hash_password(password))
    except Exception:
        await db.secure_invitations.update_one({"id": inv["id"], "status": "accepting"}, {"$set": {"status": "pending"}})
        raise
    now = _now().isoformat()
    await db.secure_invitations.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now,
                                                                        "accepted_user_id": user["id"]}})
    if claimed["kind"] == "owner_activation":
        await _activate_org(claimed, user)
    await _audit("invitation.accepted", claimed, user)
    return {"ok": True, "email": user["email"], "requires_mfa_setup": bool(claimed.get("require_mfa")),
            "kind": claimed["kind"]}


async def _create_user(inv: dict, full_name: str, pw_hash: str) -> dict:
    from utils.security import sanitise_string
    org = await db.organizations.find_one({"id": inv["organization_id"]}, {"_id": 0, "id": 1})
    if not org:
        raise HTTPException(410, "This organisation no longer exists")
    if await db.users.find_one({"email": inv["email"]}, {"_id": 1}):
        raise HTTPException(409, "This email already has a login. Sign in instead.")
    now = _now().isoformat()
    user = {
        "id": str(uuid.uuid4()), "email": inv["email"], "password": pw_hash,
        "full_name": sanitise_string(full_name or inv.get("full_name") or inv["email"])[:120],
        "organization_id": inv["organization_id"], "role": inv["role"], "created_at": now, "password_updated_at": now,
        "allowed_site_ids": inv.get("allowed_site_ids") or [], "invited_via": inv["id"],
        "email_verified": (inv.get("delivery") or {}).get("mode") == "sent",
        "mfa_required": bool(inv.get("require_mfa")), "mfa_enrolment_required": bool(inv.get("require_mfa")),
    }
    await db.users.insert_one(dict(user))
    if user["role"] == "engineer":
        from routes.account import _sync_engineer_provisioning
        await _sync_engineer_provisioning(user)
    return user


async def _activate_org(inv: dict, user: dict) -> None:
    """Owner accepted: the customer becomes active. Entitlements are NOT changed (LITE stays LITE)."""
    now = _now().isoformat()
    await db.secure_invitations.update_many(
        {"organization_id": inv["organization_id"], "kind": "owner_activation", "status": "pending"},
        {"$set": {"status": "superseded", "superseded_at": now}})
    org = await db.organizations.find_one({"id": inv["organization_id"]}, {"_id": 0, "owner_id": 1})
    s = {"onboarding_status": "active", "portal_access": "activated", "activated_at": now,
         "activated_via_invitation": inv["id"], "activated_owner_user_id": user["id"],
         "primary_contact_user_id": user["id"], "primary_contact_email": user["email"]}
    if not (org or {}).get("owner_id"):
        s["owner_id"] = user["id"]
    await db.organizations.update_one({"id": inv["organization_id"]}, {"$set": s})


async def migrate_legacy_invites(*, apply: bool, actor: dict, organization_id: Optional[str] = None) -> dict:
    """Reissue pending legacy `invites` (company-code era) through this service. Dry run by default.
    Role is capped at manager/staff; no site scope is invented (owners can narrow it when re-sending).
    Legacy rows are marked `migrated`, never deleted."""
    rows = await db.invites.find({"status": "pending", **({"organization_id": organization_id} if organization_id else {})},
                                 {"_id": 0}).to_list(5000)
    plan = []
    for r in rows:
        org = await db.organizations.find_one({"id": r.get("organization_id")}, {"_id": 0})
        email = (r.get("email") or "").strip().lower()
        reason = None
        if not org:
            reason = "organisation_missing"
        elif not email or "@" not in email:
            reason = "invalid_email"
        elif await db.users.find_one({"email": email}, {"_id": 1}):
            reason = "already_has_login"
        elif org_awaiting_activation(org):
            reason = "organisation_awaiting_activation"  # owners of imported customers come only via owner activation
        plan.append({"legacy_id": r.get("id"), "organization_id": r.get("organization_id"), "email": email,
                     "role": r.get("role") if r.get("role") in ("manager", "staff") else "staff",
                     "action": "skip" if reason else "reissue", "reason": reason})
    done = 0
    if apply:
        for p in plan:
            if p["action"] != "reissue":
                await db.invites.update_one({"id": p["legacy_id"], "status": "pending"},
                                            {"$set": {"status": "retired", "retired_reason": p["reason"], "retired_at": _now().isoformat()}})
                continue
            legacy = next(r for r in rows if r.get("id") == p["legacy_id"])
            inviter = await db.users.find_one({"id": legacy.get("invited_by")}, {"_id": 0}) or actor
            org = await db.organizations.find_one({"id": p["organization_id"]}, {"_id": 0})
            try:
                out = await create_invitation(kind="staff", org=org, email=p["email"], full_name=legacy.get("full_name") or "",
                                              role=p["role"], actor=inviter, require_mfa=p["role"] == "manager")
            except HTTPException as exc:
                p["action"], p["reason"] = "error", str(exc.detail)
                continue
            await db.invites.update_one({"id": p["legacy_id"]}, {"$set": {
                "status": "migrated", "migrated_to": out["invitation"]["id"], "migrated_at": _now().isoformat(),
                "migrated_by": actor.get("id")}})
            done += 1
    return {"apply": apply, "pending_legacy": len(rows), "reissued": done, "plan": plan}
