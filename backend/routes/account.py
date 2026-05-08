"""
Account Settings — self-service endpoints used by the in-app
AccountSettingsModal (Owner / Manager / Staff). Master Admins use
the dedicated Master Admin console.

Surface:
    POST   /account/avatar              upload + compress avatar
    DELETE /account/avatar              clear avatar
    PATCH  /account/profile             update full_name, phone
    POST   /account/change-password     in-app password change
    GET    /account/team                list teammates in same org
    POST   /account/team/invite         invite teammate
    PATCH  /account/team/{user_id}      update teammate role/status
    DELETE /account/team/{user_id}      remove teammate
"""
from __future__ import annotations

import base64
import io
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image

from utils.auth import get_current_user, hash_password, verify_password
from utils.database import APP_NAME, db, put_object
from utils.security import validate_password_strength

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────

ALLOWED_ROLES = {"owner", "manager", "staff"}


def _require_team_admin(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners or managers can manage the team")


def _public_user(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "email": u.get("email"),
        "full_name": u.get("full_name"),
        "role": u.get("role", "staff"),
        "status": u.get("status", "active"),
        "avatar_url": u.get("avatar_url"),
        "phone": u.get("phone"),
        "last_login": u.get("last_login"),
        "created_at": u.get("created_at"),
    }


# ── Avatar upload ────────────────────────────────────────────────

@router.post("/account/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Compress to a 256×256 JPEG (≤ ~80 KB) and persist via object storage."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Avatar must be 8 MB or smaller")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse image")
    # Centre-crop to a square then resize to 256×256.
    img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    compressed = buf.getvalue()

    path = f"{APP_NAME}/avatars/{user['id']}/{uuid.uuid4()}.jpg"
    try:
        result = put_object(path, compressed, "image/jpeg")
        avatar_url = result.get("url", result.get("path") or path)
    except Exception as exc:
        # Object-store outage: fall back to inline data URI so the avatar still
        # round-trips. Compressed JPEG fits comfortably in the user document.
        logger.warning(f"[account] avatar object-store put failed, embedding inline: {exc}")
        avatar_url = "data:image/jpeg;base64," + base64.b64encode(compressed).decode("ascii")

    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": avatar_url}})
    return {"avatar_url": avatar_url}


@router.delete("/account/avatar")
async def delete_avatar(user: dict = Depends(get_current_user)) -> dict:
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": None}})
    return {"avatar_url": None}


# ── Profile ──────────────────────────────────────────────────────

@router.patch("/account/profile")
async def update_profile(body: dict, user: dict = Depends(get_current_user)) -> dict:
    allowed = {"full_name", "phone", "job_title"}
    updates = {k: (v.strip() if isinstance(v, str) else v)
               for k, v in (body or {}).items() if k in allowed}
    if "full_name" in updates and not updates["full_name"]:
        raise HTTPException(status_code=400, detail="Full name cannot be empty")
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return _public_user(fresh or user)


# ── Password change ──────────────────────────────────────────────

@router.post("/account/change-password")
async def change_password(body: dict, user: dict = Depends(get_current_user)) -> dict:
    current = (body or {}).get("current_password", "")
    new_password = (body or {}).get("new_password", "")
    if not current or not new_password:
        raise HTTPException(status_code=400, detail="Current and new password are required")
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not full or not verify_password(current, full.get("password", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if current == new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current one")
    validate_password_strength(new_password)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password": hash_password(new_password),
            "password_updated_at": datetime.now(timezone.utc).isoformat(),
            "must_change_password": False,
        }},
    )
    return {"success": True}


# ── Team & Roles ─────────────────────────────────────────────────

@router.get("/account/team")
async def list_team(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        return {"members": []}
    cursor = db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "password": 0},
    ).sort("created_at", 1)
    members = [_public_user(u) async for u in cursor]
    return {"members": members}


@router.post("/account/team/invite")
async def invite_team_member(body: dict, user: dict = Depends(get_current_user)) -> dict:
    _require_team_admin(user)
    email = (body or {}).get("email", "").strip().lower()
    full_name = (body or {}).get("full_name", "").strip()
    role = ((body or {}).get("role") or "staff").lower()
    if not email or not full_name:
        raise HTTPException(status_code=400, detail="Email and full name are required")
    if role not in ALLOWED_ROLES or role == "owner":
        role = "staff"
    if (user.get("role") or "").lower() == "manager" and role != "staff":
        raise HTTPException(status_code=403, detail="Managers can only invite staff")

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    temp_password = f"Welcome{secrets.token_hex(3)}!"
    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    new_user = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "password": hash_password(temp_password),
        "role": role,
        "status": "active",
        "avatar_url": None,
        "organization_id": user.get("organization_id"),
        "invited_by": user["id"],
        "must_change_password": True,
        "created_at": now_iso,
    }
    await db.users.insert_one(new_user)
    return {
        "id": user_id, "email": email, "full_name": full_name, "role": role,
        "temp_password": temp_password,
    }


@router.patch("/account/team/{user_id}")
async def update_team_member(user_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    _require_team_admin(user)
    target = await db.users.find_one(
        {"id": user_id, "organization_id": user.get("organization_id")},
        {"_id": 0},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if target.get("role") == "owner" and (body or {}).get("role") not in (None, "owner"):
        raise HTTPException(status_code=403, detail="Cannot change the Owner's role")
    updates: dict = {}
    if "role" in (body or {}):
        new_role = (body["role"] or "staff").lower()
        if new_role not in ALLOWED_ROLES or new_role == "owner":
            new_role = "staff"
        if (user.get("role") or "").lower() == "manager" and new_role != "staff":
            raise HTTPException(status_code=403, detail="Managers can only assign the staff role")
        updates["role"] = new_role
    if "status" in (body or {}):
        new_status = (body["status"] or "active").lower()
        if new_status not in ("active", "disabled"):
            new_status = "active"
        updates["status"] = new_status
    if "full_name" in (body or {}):
        updates["full_name"] = (body["full_name"] or "").strip() or target.get("full_name")
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": user_id}, {"$set": updates})
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return _public_user(fresh or target)


@router.delete("/account/team/{user_id}")
async def remove_team_member(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_team_admin(user)
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    target = await db.users.find_one(
        {"id": user_id, "organization_id": user.get("organization_id")},
        {"_id": 0, "role": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Cannot remove the Owner")
    await db.users.delete_one({"id": user_id})
    return {"success": True}
