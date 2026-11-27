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
