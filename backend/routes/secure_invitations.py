"""Release C — secure invitations: public accept flow + Pulse customer activation (owner verification)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils import secure_invites as SI
from utils.security import rate_limit, _client_ip

router = APIRouter(tags=["secure-invitations"])


def _limit(request: Request, key: str, n: int) -> None:
    import os
    bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "").strip()
    if bypass and request.headers.get("x-ratelimit-bypass", "") == bypass:
        return
    rate_limit(f"{key}:{_client_ip(request)}", max_requests=n, window_seconds=600)


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AcceptIn(TokenIn):
    email: str
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


@router.post("/invitations/inspect")
async def inspect_invitation(body: TokenIn, request: Request):
    _limit(request, "invite-inspect", 30)
    return await SI.inspect(body.token)


@router.post("/invitations/accept")
async def accept_invitation(body: AcceptIn, request: Request):
    _limit(request, "invite-accept", 10)
    return await SI.accept(body.token, full_name=body.full_name, password=body.password, email_confirm=body.email)


# ---------------------------------------------------------------- Pulse: customer activation
async def _pulse(user: dict, perm: str) -> None:
    from routes.customer_account_import import _require_admin
    await _require_admin(user, perm)


class OwnerInviteIn(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=120)
    contact_id: str | None = None
    verification_method: str
    verification_note: str = Field(min_length=5, max_length=1000)
    accounts_confirmed: bool = False


@router.get("/master-admin/customer-activation/{org_id}")
async def activation_detail(org_id: str, user: dict = Depends(get_current_user)):
    await _pulse(user, "activation.view")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1, "customer_account_number": 1,
                                                          "onboarding_status": 1, "portal_access": 1, "account_type": 1})
    if not org:
        raise HTTPException(404, "Customer not found")
    contacts = await db.crm2_contacts.find(
        {"linked_organization_id": org_id, "email": {"$nin": ["", None]}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "full_name": 1, "email": 1, "job_title": 1, "phone": 1},
    ).limit(50).to_list(50)
    invites = await db.secure_invitations.find({"organization_id": org_id}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(20)
    st = await db.customer_account_internal.find_one({"org_id": org_id}, {"_id": 0, "sage_status": 1}) or {}
    return {"organization": org, "contacts": contacts, "invitations": [SI.public_view(i) for i in invites],
            "sage_hold": bool((st.get("sage_status") or {}).get("on_hold") or (st.get("sage_status") or {}).get("hidden")),
            "verification_methods": SI.VERIFICATION_METHODS, "emails_live": SI.emails_live(),
            "users": await db.users.count_documents({"organization_id": org_id})}


@router.post("/master-admin/customer-activation/{org_id}/owner-invite")
async def invite_owner(org_id: str, body: OwnerInviteIn, user: dict = Depends(get_current_user)):
    await _pulse(user, "activation.invite")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Customer not found")
    if org.get("onboarding_status") != "pending_activation" and org.get("portal_access") != "not_activated":
        raise HTTPException(409, "This customer is already activated. Their owner invites staff from Settings.")
    if org.get("provisioning_state") == "importing":
        raise HTTPException(409, "This customer is still being imported. Try again when the import finishes.")
    if body.verification_method not in SI.VERIFICATION_METHODS:
        raise HTTPException(400, "Choose how the owner was verified")
    st = await db.customer_account_internal.find_one({"org_id": org_id}, {"_id": 0, "sage_status": 1}) or {}
    held = (st.get("sage_status") or {})
    if (held.get("on_hold") or held.get("hidden")) and not body.accounts_confirmed:
        raise HTTPException(409, "This Sage account is on hold or hidden. Confirm with Accounts before inviting.")
    email = body.email.strip().lower()
    contact = None
    if body.contact_id:
        contact = await db.crm2_contacts.find_one({"id": body.contact_id, "linked_organization_id": org_id},
                                                  {"_id": 0, "id": 1, "email": 1})
        if not contact:
            raise HTTPException(400, "That contact doesn't belong to this customer")
    verification = {"method": body.verification_method, "note": body.verification_note.strip(),
                    "contact_id": (contact or {}).get("id"),
                    "email_matches_contact": bool(contact and (contact.get("email") or "").strip().lower() == email),
                    "verified_by": user.get("id"), "verified_by_email": user.get("email"),
                    "verified_at": datetime.now(timezone.utc).isoformat()}
    return await SI.create_invitation(kind="owner_activation", org=org, email=email, full_name=body.full_name,
                                      role="owner", actor=user, require_mfa=True, verification=verification)


@router.post("/master-admin/customer-activation/invitations/{inv_id}/revoke")
async def revoke_owner_invite(inv_id: str, user: dict = Depends(get_current_user)):
    await _pulse(user, "activation.invite")
    return await SI.revoke(inv_id, user, kind="owner_activation")


@router.post("/master-admin/customer-activation/invitations/{inv_id}/reissue")
async def reissue_owner_invite(inv_id: str, user: dict = Depends(get_current_user)):
    await _pulse(user, "activation.invite")
    return await SI.reissue(inv_id, user, kind="owner_activation")


class MigrateIn(BaseModel):
    apply: bool = False


@router.post("/master-admin/legacy-invites/migrate")
async def migrate_legacy(body: MigrateIn, user: dict = Depends(get_current_user)):
    from routes.customer_account_import import _is_full_admin
    if not _is_full_admin(user):
        raise HTTPException(403, "Pulse Fitness administrator access required")
    return await SI.migrate_legacy_invites(apply=body.apply, actor=user)
