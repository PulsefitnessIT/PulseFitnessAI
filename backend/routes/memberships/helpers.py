"""Shared helpers for the memberships package.

Leaf-level utilities used by every submodule. Importing from `.helpers`
means submodules don't need to depend on each other for plumbing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from passlib.context import CryptContext

from utils.auth import JWT_ALGORITHM, JWT_SECRET, verify_token
from utils.database import db

import jwt as pyjwt

logger = logging.getLogger("memberships")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def _require_operator_org(user: dict) -> str:
    """Return the operator's org_id or raise. Operators = non-member users
    with a gym-operator-style account_type."""
    if not user:
        raise HTTPException(401, "Not authenticated")
    if user.get("account_type") == "member":
        raise HTTPException(403, "Member accounts cannot access operator endpoints")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "No organization context")
    return org_id


def _assert_timetable_write(user: dict) -> None:
    """Block users flagged `timetable_view_only=true` from mutating the
    Group Fitness timetable (create/edit/cancel/archive classes &
    occurrences). Owners and master admins are never restricted."""
    if user.get("is_master_admin") or user.get("role") == "owner":
        return
    if user.get("timetable_view_only"):
        raise HTTPException(
            403,
            "You have view-only access to the Group Fitness timetable. "
            "Ask your manager for edit permissions.",
        )


async def _load_member(member_id: str, org_id: str | None = None) -> dict:
    q = {"id": member_id}
    if org_id:
        q["organization_id"] = org_id
    m = await db.members.find_one(q, {"_id": 0})
    if not m:
        raise HTTPException(404, "Member not found")
    return m


async def _require_current_member(request: Request) -> dict:
    """Resolve the member from the member-auth JWT (separate `m_` prefix
    to distinguish from the operator-side JWTs)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing member token")
    token = auth.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload or payload.get("kind") != "member":
        raise HTTPException(401, "Invalid member token")
    member = await db.members.find_one({"id": payload.get("member_id")}, {"_id": 0})
    if not member:
        raise HTTPException(401, "Member not found")
    if member.get("status") == "cancelled":
        raise HTTPException(403, "Membership cancelled — please contact reception")
    return member


def _member_token(member: dict) -> str:
    """Mint a JWT for the member portal. `kind=member` tells operator
    endpoints to auto-reject; `member_id` is the primary subject."""
    payload = {
        "member_id": member["id"],
        "organization_id": member["organization_id"],
        "kind": "member",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _gen_referral_code(first_name: str) -> str:
    """Short friendly code: FIRST-XXXX (upper, alphanum)."""
    prefix = "".join(ch for ch in (first_name or "").upper() if ch.isalpha())[:5] or "MBR"
    return f"{prefix}-{uuid.uuid4().hex[:4].upper()}"


def _public_member(m: dict) -> dict:
    return {k: v for k, v in m.items() if k not in {"_id", "password"}}
