"""Release 1 — one set of rules for every staff-administration endpoint (auth.py and account.py)."""
from fastapi import HTTPException

from utils.database import db


def is_disabled(user: dict) -> bool:
    return user.get("active") is False or user.get("is_active") is False or (user.get("status") or "").lower() == "disabled"


async def validate_org_sites(org_id: str, ids) -> list:
    ids = [str(x) for x in (ids or []) if x]
    if ids and await db.sites.count_documents({"id": {"$in": ids}, "organization_id": org_id}) != len(set(ids)):
        raise HTTPException(status_code=400, detail="One or more sites don't belong to your organisation")
    return ids


def assert_can_manage(actor: dict, target: dict) -> None:
    """Owners manage everyone but owners; managers manage only staff/engineers inside their own sites; never yourself."""
    role = (actor.get("role") or "").lower()
    if actor.get("is_master_admin"):
        return
    if target.get("id") == actor.get("id"):
        raise HTTPException(status_code=403, detail="You can't change your own access")
    if target.get("role") == "owner":
        raise HTTPException(status_code=403, detail="The owner's access can only change through an ownership transfer")
    if role == "owner":
        return
    if role != "manager" or target.get("role") == "manager":
        raise HTTPException(status_code=403, detail="Managers can only manage staff")
    mine = set(actor.get("allowed_site_ids") or [])
    theirs = set(target.get("allowed_site_ids") or [])
    if mine and (not theirs or not theirs <= mine):
        raise HTTPException(status_code=403, detail="This person works at sites you don't manage")


def assert_sites_within_scope(actor: dict, ids: list) -> None:
    mine = set(actor.get("allowed_site_ids") or [])
    if (actor.get("role") or "").lower() == "manager" and mine and (not ids or not set(ids) <= mine):
        raise HTTPException(status_code=403, detail="You can only give access to the sites you manage")


# ---- Release 1 sign-off: one authoritative organisation access-state check ----
import time as _time  # noqa: E402

_ORG_CACHE: dict = {}
_ORG_TTL = 10.0  # seconds; a customer set back to "awaiting activation" loses sessions within this window


def org_access_blocked(org: dict) -> bool:
    """Customer access is refused while an organisation is awaiting activation, not activated or still provisioning."""
    if not org or org.get("is_operator_company"):
        return False
    return (org.get("onboarding_status") == "pending_activation"
            or org.get("portal_access") == "not_activated"
            or org.get("provisioning_state") == "importing")


async def org_blocked(org_id) -> bool:
    if not org_id:
        return False
    hit = _ORG_CACHE.get(org_id)
    now = _time.monotonic()
    if hit and now - hit[0] < _ORG_TTL:
        return hit[1]
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "onboarding_status": 1, "portal_access": 1,
                                                           "provisioning_state": 1, "is_operator_company": 1})
    blocked = org_access_blocked(org or {})
    if len(_ORG_CACHE) > 5000:
        _ORG_CACHE.clear()  # bounded
    _ORG_CACHE[org_id] = (now, blocked)
    return blocked


def is_pulse_admin(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("is_pulse_admin"))


async def assert_user_may_access(user: dict) -> None:
    """Disabled account or blocked organisation -> 401/403. Pulse administrators are never blocked by a customer state."""
    if is_disabled(user):
        raise HTTPException(status_code=401, detail="Account disabled")
    if not is_pulse_admin(user) and await org_blocked(user.get("organization_id")):
        raise HTTPException(status_code=403, detail="Your organisation hasn't been activated yet. Use the activation invitation from Pulse Fitness.")
