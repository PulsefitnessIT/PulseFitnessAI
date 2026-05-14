"""
Account Settings — self-service endpoints used by the in-app
AccountSettingsModal (Owner / Manager / Staff). Master Admins use
the dedicated Master Admin console.

Surface:
    POST   /account/avatar                       upload + compress avatar
    DELETE /account/avatar                       clear avatar
    PATCH  /account/profile                      update full_name, phone
    POST   /account/change-password              in-app password change
    GET    /account/team                         list teammates in same org
    POST   /account/team/invite                  invite teammate
    PATCH  /account/team/{user_id}               update teammate role/status
    DELETE /account/team/{user_id}               remove teammate
    GET    /account/organisation                 org address + contact details
    PATCH  /account/organisation                 update org address (owner)
    GET    /account/onboarding                   live setup checklist
    GET    /account/billing/{payment_id}/invoice.pdf  download PDF (hybrid)
"""
from __future__ import annotations

import base64
import io
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta as _td, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse
from PIL import Image

from utils.auth import get_current_user, hash_password, verify_password
from utils.database import APP_NAME, db, put_object, get_object
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
        # Iter 216h15 — site allocation + reset audit trail
        "allowed_site_ids": u.get("allowed_site_ids") or [],
        "password_reset_sent_at": u.get("password_reset_sent_at"),
        "password_reset_sent_by": u.get("password_reset_sent_by"),
    }


async def _issue_reset_token(target_user: dict, issued_by_email: str) -> dict:
    """Mint a 72-hour `password_reset_token` for the target user. Returns
    a dict with `invite_url` + `expires_at`. Mirrors the master-admin
    invite-link endpoint so the owner-side flow is identical."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": target_user["id"],
        "email": target_user.get("email", ""),
        "expires_at": expires_at,
        "used": False,
        "kind": "invite",
        "issued_by": issued_by_email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return {
        "invite_url": f"{frontend_url}/reset-password?token={token}",
        "expires_at": expires_at,
        "email": target_user.get("email", ""),
    }


# ── Avatar upload ────────────────────────────────────────────────

@router.post("/account/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Compress to a 256×256 JPEG (≤ ~80 KB) and persist via object storage.

    Iter 216h57 — previously stored the raw object-store *path* in
    `avatar_url` (e.g. ``gymaxis-ai/avatars/{uid}/{u}.jpg``) which the
    browser couldn't load (no host, no auth) — the `<img>` would 404
    and show the alt text 'Avatar'. The fix stores the path internally
    as ``avatar_path`` and exposes ``/api/account/avatar/{user_id}``
    as a public streaming proxy so the URL just works.
    """
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
    avatar_path: str | None = None
    try:
        put_object(path, compressed, "image/jpeg")
        avatar_path = path
        # Cache-buster query string so the new image displaces the old one
        # immediately in the browser cache.
        avatar_url = f"/api/account/avatar/{user['id']}?v={uuid.uuid4().hex[:8]}"
    except Exception as exc:
        # Object-store outage: fall back to inline data URI so the avatar still
        # round-trips. Compressed JPEG fits comfortably in the user document.
        logger.warning(f"[account] avatar object-store put failed, embedding inline: {exc}")
        avatar_url = "data:image/jpeg;base64," + base64.b64encode(compressed).decode("ascii")

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"avatar_url": avatar_url, "avatar_path": avatar_path}},
    )
    return {"avatar_url": avatar_url}


@router.get("/account/avatar/{user_id}")
async def serve_avatar(user_id: str) -> Response:
    """Public proxy that streams the user's avatar bytes from object
    storage (iter 216h57). Public on purpose — avatars are non-sensitive
    and the URL is embedded in <img> tags throughout the app."""
    rec = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "avatar_path": 1, "avatar_url": 1},
    )
    if not rec:
        raise HTTPException(status_code=404, detail="User not found")
    path = rec.get("avatar_path")
    if not path:
        # Legacy: avatar_url stored as raw object-store path.
        legacy = rec.get("avatar_url") or ""
        if legacy and not legacy.startswith("http") and not legacy.startswith("data:") and "/" in legacy:
            path = legacy
    if not path:
        raise HTTPException(status_code=404, detail="No avatar")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        logger.warning(f"Failed to load avatar for {user_id}: {exc}")
        raise HTTPException(status_code=404, detail="Avatar not available") from exc
    return Response(
        content=data,
        media_type=content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=600"},
    )


@router.delete("/account/avatar")
async def delete_avatar(user: dict = Depends(get_current_user)) -> dict:
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"avatar_url": None, "avatar_path": None}},
    )
    return {"avatar_url": None}


# ── Organisation Logo (iter 216h57) ──────────────────────────────
# Same proxy pattern as avatars so the Account Settings "Upload logo"
# CTA works inline rather than navigating away and closing the modal.

@router.post("/account/logo")
async def upload_logo(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload an org logo (PNG/JPEG). Only owners/managers can update.

    Iter 216h58 — also extracts a 5-colour brand palette via Pillow's
    adaptive quantisation so the operator can one-click apply a
    sensible primary brand colour without firing up a colour picker.
    The palette is sorted by frequency, skipping near-white / pure-
    black pixels (logos typically sit on transparent or white
    backgrounds and almost-black stroke pixels aren't useful brand
    colours).
    """
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners or managers can update the logo")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation linked to this account")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo must be 8 MB or smaller")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse image")

    # Preserve transparency for PNGs; fit within a 512px bounding box.
    is_png = (img.format or "").upper() == "PNG"
    img.thumbnail((512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    if is_png:
        img.save(buf, format="PNG", optimize=True)
        content_type, ext = "image/png", "png"
    else:
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=88, optimize=True)
        content_type, ext = "image/jpeg", "jpg"
    compressed = buf.getvalue()

    # ── Palette extraction (iter 216h58) ──
    palette = _extract_brand_palette(img)

    path = f"{APP_NAME}/logos/{org_id}/{uuid.uuid4()}.{ext}"
    logo_path: str | None = None
    try:
        put_object(path, compressed, content_type)
        logo_path = path
        logo_url = f"/api/account/logo/{org_id}?v={uuid.uuid4().hex[:8]}"
    except Exception as exc:
        logger.warning(f"[account] logo object-store put failed, embedding inline: {exc}")
        logo_url = f"data:{content_type};base64," + base64.b64encode(compressed).decode("ascii")

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "logo_url": logo_url, "logo_path": logo_path,
            "logo_content_type": content_type,
            "brand_palette": palette,
        }},
    )
    return {"logo_url": logo_url, "brand_palette": palette}


def _extract_brand_palette(img: "Image.Image", n: int = 5) -> list[str]:
    """Pick the `n` most dominant non-trivial colours from an image.

    Uses Pillow's adaptive quantisation (no sklearn dependency).
    Filters out near-white, near-black, and near-transparent pixels
    since logos sit on neutral backgrounds and the actual brand
    colour is what we want to surface.
    """
    try:
        # Handle transparency by compositing on white before quantising.
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            src = bg
        else:
            src = img.convert("RGB")
        # 32 candidate colours is plenty for a typical logo.
        q = src.quantize(colors=32, method=Image.MEDIANCUT)
        palette = q.getpalette() or []
        counts = sorted(q.getcolors() or [], key=lambda c: -c[0])
        out: list[str] = []
        for count, idx in counts:
            if idx * 3 + 2 >= len(palette):
                continue
            r, g, b = palette[idx*3], palette[idx*3+1], palette[idx*3+2]
            # Skip near-white (background) and near-black (outline)
            mn, mx = min(r, g, b), max(r, g, b)
            if mx >= 245 and mn >= 235:
                continue
            if mx <= 25:
                continue
            hex_color = f"#{r:02x}{g:02x}{b:02x}".upper()
            if hex_color not in out:
                out.append(hex_color)
            if len(out) >= n:
                break
        return out or ["#19CDFF"]  # GymAxis default fallback
    except Exception as exc:
        logger.warning(f"[account] palette extraction failed: {exc}")
        return []


@router.delete("/account/logo")
async def delete_logo(user: dict = Depends(get_current_user)) -> dict:
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners or managers can update the logo")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation linked to this account")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"logo_url": None, "logo_path": None}},
    )
    return {"logo_url": None}


@router.get("/account/logo/{org_id}")
async def serve_logo(org_id: str) -> Response:
    """Public proxy for the org logo (iter 216h57)."""
    rec = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "logo_path": 1, "logo_url": 1, "logo_content_type": 1},
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Organisation not found")
    path = rec.get("logo_path")
    if not path:
        legacy = rec.get("logo_url") or ""
        if legacy and not legacy.startswith("http") and not legacy.startswith("data:") and "/" in legacy:
            path = legacy
    if not path:
        raise HTTPException(status_code=404, detail="No logo")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        logger.warning(f"Failed to load logo for {org_id}: {exc}")
        raise HTTPException(status_code=404, detail="Logo not available") from exc
    return Response(
        content=data,
        media_type=rec.get("logo_content_type") or content_type or "image/png",
        headers={"Cache-Control": "public, max-age=600"},
    )


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
async def list_team(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """List org team members.

    Iter 216h63 (h) — `site_id` query param filters the roster to only
    staff allocated to that site (i.e. `allowed_site_ids` contains the
    site_id). Owners + Managers — who have no `allowed_site_ids`
    restriction (empty list == access to every site) — are ALWAYS
    visible regardless of which site is being viewed so the Staffing
    tab still shows leadership. Omitting `site_id` returns the whole
    roster (used by SiteSwitcher → All Operations Sites).
    """
    org_id = user.get("organization_id")
    if not org_id:
        return {"members": []}
    base_filter = {"organization_id": org_id}
    if site_id:
        # Match users either:
        #   • whose allowed_site_ids array contains the requested site,
        #   • OR who have no `allowed_site_ids` at all (owners/managers
        #     with org-wide access), since they're effectively assigned
        #     to every site.
        base_filter = {
            "organization_id": org_id,
            "$or": [
                {"allowed_site_ids": site_id},
                {"allowed_site_ids": {"$exists": False}},
                {"allowed_site_ids": {"$size": 0}},
                {"role": {"$in": ["owner", "manager"]}},
            ],
        }
    cursor = db.users.find(
        base_filter,
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
    # Iter 216h15 — owners can now choose between (a) issuing a temp
    # password they share inline OR (b) emailing the user a self-serve
    # password reset link (matching Master Admin's existing UX).
    delivery = ((body or {}).get("delivery") or "temp_password").lower()
    if delivery not in {"temp_password", "reset_link"}:
        delivery = "temp_password"
    # Iter 216h15 — optional per-site allocation at invite time.
    allowed_site_ids = list((body or {}).get("allowed_site_ids") or [])
    if not isinstance(allowed_site_ids, list):
        allowed_site_ids = []
    allowed_site_ids = [str(s) for s in allowed_site_ids if s]

    if not email or not full_name:
        raise HTTPException(status_code=400, detail="Email and full name are required")
    if role not in ALLOWED_ROLES or role == "owner":
        role = "staff"
    if (user.get("role") or "").lower() == "manager" and role != "staff":
        raise HTTPException(status_code=403, detail="Managers can only invite staff")

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    # When delivery=reset_link, we still seed a random password so the
    # account row is valid — the user will overwrite it via the reset
    # link before they can log in. We never disclose this seed.
    seed_password = f"Welcome{secrets.token_hex(3)}!"
    new_user = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "password": hash_password(seed_password),
        "role": role,
        "status": "active",
        "avatar_url": None,
        "organization_id": user.get("organization_id"),
        "invited_by": user["id"],
        "must_change_password": True,
        "allowed_site_ids": allowed_site_ids,
        "created_at": now_iso,
    }
    await db.users.insert_one(new_user)

    response: dict = {
        "id": user_id, "email": email, "full_name": full_name, "role": role,
        "allowed_site_ids": allowed_site_ids,
        "delivery": delivery,
    }
    if delivery == "reset_link":
        link = await _issue_reset_token(new_user, user.get("email", ""))
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "password_reset_sent_at": now_iso,
                "password_reset_sent_by": user.get("email", ""),
            }},
        )
        response.update({
            "invite_url": link["invite_url"],
            "expires_at": link["expires_at"],
        })
    else:
        response["temp_password"] = seed_password
    return response


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


# ── Iter 216h15 — Per-user site allocation + send reset link ──────

@router.patch("/account/team/{user_id}/site-access")
async def update_team_member_site_access(user_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Owner/manager assigns the set of sites a teammate can see.

    Empty list = unrestricted (legacy default — staff sees every site
    in the org). Non-empty list = whitelist; `/sites` filters by it
    for non-privileged roles.

    Body: `{"allowed_site_ids": ["site-1", "site-2"]}`
    """
    _require_team_admin(user)
    target = await db.users.find_one(
        {"id": user_id, "organization_id": user.get("organization_id")},
        {"_id": 0, "id": 1, "role": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Owners always see every site")
    raw = (body or {}).get("allowed_site_ids")
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="allowed_site_ids must be a list of site ids")
    cleaned = [str(s) for s in raw if isinstance(s, (str, int)) and str(s).strip()]
    # Verify each id belongs to the caller's org so we can't pin staff
    # to sites outside their tenant.
    if cleaned:
        valid_ids = {
            s["id"] async for s in db.sites.find(
                {"organization_id": user.get("organization_id"), "id": {"$in": cleaned}},
                {"_id": 0, "id": 1},
            )
        }
        cleaned = [s for s in cleaned if s in valid_ids]
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "allowed_site_ids": cleaned,
            "site_access_updated_at": datetime.now(timezone.utc).isoformat(),
            "site_access_updated_by": user.get("email", ""),
        }},
    )
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return _public_user(fresh or target)


@router.post("/account/team/{user_id}/send-reset-link")
async def send_reset_link_to_team_member(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Issue a fresh 72-hour password-reset link for a teammate. The
    owner can copy the URL OR (when Resend is wired) email it directly.
    Stamps the user row with `password_reset_sent_at` / `_by` so the
    Team & Roles list shows an at-a-glance audit trail."""
    _require_team_admin(user)
    target = await db.users.find_one(
        {"id": user_id, "organization_id": user.get("organization_id")},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if target.get("role") == "owner" and user.get("id") != target.get("id"):
        raise HTTPException(status_code=403, detail="Cannot send a reset link to the Owner")
    link = await _issue_reset_token(target, user.get("email", ""))
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_reset_sent_at": now_iso,
            "password_reset_sent_by": user.get("email", ""),
        }},
    )
    return {
        "invite_url": link["invite_url"],
        "expires_at": link["expires_at"],
        "email": target.get("email", ""),
        "sent_at": now_iso,
        "sent_by": user.get("email", ""),
    }



# ── Organisation address & contact details ────────────────────────

ORG_ALLOWED_FIELDS = {
    "address_line1", "address_line2", "address_line3", "city",
    "postcode", "country", "phone", "primary_contact_email",
    "primary_contact_phone", "website",
}


@router.get("/account/organisation")
async def get_organisation(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organisation linked to this account")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "password": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    payload = {k: org.get(k, "") for k in ORG_ALLOWED_FIELDS}
    payload["id"] = org.get("id", "")
    payload["name"] = org.get("name", "")
    payload["company_code"] = org.get("company_code", "")
    payload["logo_url"] = org.get("logo_url", "")
    # Iter 216h58 — palette + active primary brand colour for the UI.
    payload["brand_palette"] = org.get("brand_palette", []) or []
    payload["primary_color"] = (
        (org.get("branding") or {}).get("primary_color")
        or org.get("primary_brand_colour")
        or org.get("brand_color")
        or ""
    )
    return payload


@router.patch("/account/organisation")
async def update_organisation(body: dict, user: dict = Depends(get_current_user)) -> dict:
    if (user.get("role") or "").lower() != "owner" and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only the owner can update organisation details")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organisation linked to this account")
    updates = {k: (v.strip() if isinstance(v, str) else v)
               for k, v in (body or {}).items() if k in ORG_ALLOWED_FIELDS}
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.organizations.update_one({"id": org_id}, {"$set": updates})
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    payload = {k: (org or {}).get(k, "") for k in ORG_ALLOWED_FIELDS}
    payload["id"] = (org or {}).get("id", "")
    payload["name"] = (org or {}).get("name", "")
    payload["company_code"] = (org or {}).get("company_code", "")
    payload["logo_url"] = (org or {}).get("logo_url", "")
    payload["brand_palette"] = (org or {}).get("brand_palette", []) or []
    payload["primary_color"] = (
        ((org or {}).get("branding") or {}).get("primary_color")
        or (org or {}).get("primary_brand_colour")
        or (org or {}).get("brand_color")
        or ""
    )
    return payload


# ── Brand palette apply (iter 216h58) ────────────────────────────

_HEX_RE = __import__("re").compile(r"^#[0-9A-Fa-f]{6}$")


@router.post("/account/branding/apply")
async def apply_brand_color(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """One-click apply a colour from the extracted logo palette.

    Writes the same hex to all three brand-colour fields the rest of
    the codebase reads (`branding.primary_color`, `primary_brand_colour`,
    `brand_color`) so member-facing emails, supplier cases, and the
    member portal pick up the new colour without further plumbing.
    """
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only owners or managers can update brand colours")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation linked to this account")
    primary = (body or {}).get("primary_color") or ""
    if not _HEX_RE.match(primary):
        raise HTTPException(status_code=400, detail="primary_color must be a #RRGGBB hex string")
    primary = primary.upper()

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "branding": 1})
    branding = dict((org or {}).get("branding") or {})
    branding["primary_color"] = primary

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "branding": branding,
            "primary_brand_colour": primary,
            "brand_color": primary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"primary_color": primary}


# ── Onboarding checklist (live derivation) ────────────────────────

ONBOARDING_STEPS = [
    {"id": "site_details", "label": "Enter site details",
     "description": "Add your primary site name, address, and operating hours.",
     "cta_label": "Open sites", "cta_route": "/sites"},
    {"id": "extra_sites", "label": "Add extra site(s)",
     "description": "Multi-site operators add each branch so reporting and rotas split correctly.",
     "cta_label": "Manage sites", "cta_route": "/sites"},
    {"id": "invite_staff", "label": "Invite staff to sites",
     "description": "Invite teammates via the Team & Roles tab so they can sign in and contribute.",
     "cta_label": "Invite teammates", "cta_section": "team"},
    {"id": "set_roles", "label": "Set roles",
     "description": "Promote site leads to Manager and keep day-to-day staff on Staff.",
     "cta_label": "Open Team & Roles", "cta_section": "team"},
    {"id": "upload_logo", "label": "Upload logo",
     "description": "Your logo brands every invoice, member-facing email, and case page.",
     "cta_label": "Upload logo", "cta_section": "organisation"},
    {"id": "import_machines", "label": "Import machines to site(s)",
     "description": "Pull equipment from a supplier invoice (PDF), CSV, or Excel spreadsheet — uses the same template across the platform.",
     "cta_label": "Import equipment", "cta_inline": "equipment_import"},
    {"id": "print_qr_codes", "label": "Print QR codes",
     "description": "Generate and bulk-print QR labels for every machine — members scan them to log a fault.",
     "cta_label": "Print QR codes", "cta_inline": "qr_print"},
    {"id": "connect_stripe", "label": "Connect Stripe",
     "description": "Take memberships, classes, and product payments online.",
     "cta_label": "Connect Stripe", "cta_route": "/pricing"},
    {"id": "complete_profile", "label": "Complete profile",
     "description": "Add your photo and phone so teammates and members recognise you.",
     "cta_label": "Open Profile", "cta_section": "profile"},
]


@router.get("/account/onboarding")
async def onboarding_status(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    if not org_id:
        return {"steps": [{**s, "completed": False} for s in ONBOARDING_STEPS], "percent": 0}

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    sites_count = await db.sites.count_documents({"organization_id": org_id})
    primary_site = await db.sites.find_one({"organization_id": org_id}, {"_id": 0, "address": 1, "address_line1": 1, "name": 1})
    teammate_count = await db.users.count_documents({
        "organization_id": org_id, "id": {"$ne": user["id"]},
    })
    role_assigned = await db.users.count_documents({
        "organization_id": org_id, "id": {"$ne": user["id"]},
        "role": {"$in": ["manager", "staff"]},
    })
    equipment_count = await db.equipment.count_documents({"organization_id": org_id})
    paid_payment = await db.payment_transactions.find_one(
        {"user_email": user.get("email"), "payment_status": "paid"}, {"_id": 0, "id": 1},
    )
    has_stripe = bool(paid_payment) or (org.get("subscription_tier") and org.get("subscription_tier") != "none")

    has_avatar_or_phone = bool(user.get("avatar_url") or user.get("phone"))

    # Derived completion flags.
    flags = {
        "site_details": bool(primary_site and (primary_site.get("name") or primary_site.get("address") or primary_site.get("address_line1"))),
        "extra_sites": sites_count >= 2,
        "invite_staff": teammate_count >= 1,
        "set_roles": role_assigned >= 1,
        "upload_logo": bool(org.get("logo_url")),
        "import_machines": equipment_count >= 1,
        "print_qr_codes": equipment_count >= 1,  # 216h108 — co-completes with import
        "connect_stripe": bool(has_stripe),
        "complete_profile": has_avatar_or_phone,
    }
    steps = [{**s, "completed": flags.get(s["id"], False)} for s in ONBOARDING_STEPS]
    # Iter 216h113h — MOD tenants don't onboard Stripe (procurement
    # handled centrally by DIO / DEFCON), so the step is removed
    # from the wizard entirely rather than shown as "incomplete".
    at = (user.get("account_type") or "").lower()
    if at.startswith("mod_"):
        steps = [s for s in steps if s["id"] != "connect_stripe"]
    completed_count = sum(1 for s in steps if s["completed"])
    return {
        "steps": steps,
        "completed_count": completed_count,
        "total": len(steps),
        "percent": int(round((completed_count / len(steps)) * 100)) if steps else 0,
    }


# ── Invoice PDF (hybrid: Stripe-hosted → fallback reportlab) ──────

def _generate_invoice_pdf(payment: dict, org: dict) -> bytes:
    """Generate a simple branded GymAxis invoice PDF in-memory."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=22, leading=26, textColor=colors.HexColor("#0055FF"))
    body = styles["BodyText"]
    muted = ParagraphStyle("muted", parent=body, textColor=colors.HexColor("#52525B"), fontSize=9)

    story = [
        Paragraph("GymAxis", h1),
        Paragraph("Invoice", styles["Heading2"]),
        Spacer(1, 6 * mm),
    ]

    org_lines = [
        org.get("name", ""),
        " ".join(filter(None, [org.get("address_line1", ""), org.get("address_line2", ""), org.get("address_line3", "")])),
        " ".join(filter(None, [org.get("city", ""), org.get("postcode", "")])),
        org.get("country", ""),
    ]
    story.append(Paragraph("<b>Billed to</b><br/>" + "<br/>".join(filter(None, org_lines)), body))
    story.append(Spacer(1, 6 * mm))

    created = payment.get("created_at", "")
    if created and "T" in created:
        created = created.split("T")[0]
    meta_table = Table([
        ["Invoice #", payment.get("session_id", payment.get("id", ""))[:24]],
        ["Date", created],
        ["Plan", (payment.get("package_name") or payment.get("package_id") or "Charge")],
        ["Status", (payment.get("payment_status") or "pending").upper()],
    ], colWidths=[40 * mm, 110 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#52525B")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [meta_table, Spacer(1, 8 * mm)]

    amount = float(payment.get("amount") or 0)
    currency = (payment.get("currency") or "gbp").upper()
    sym = "£" if currency == "GBP" else "$" if currency == "USD" else (currency + " ")
    items_table = Table([
        ["Description", "Amount"],
        [payment.get("package_name") or payment.get("package_id") or "Subscription charge",
         f"{sym}{amount:.2f}"],
        ["", ""],
        ["Total", f"{sym}{amount:.2f}"],
    ], colWidths=[120 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F7")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#C4C4CC")),
        ("LINEBELOW", (0, -2), (-1, -2), 0.5, colors.HexColor("#C4C4CC")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        "Thank you for choosing GymAxis. If you have any questions about this invoice, "
        "reply to this email or contact billing@gymaxisai.com.", muted,
    ))

    doc.build(story)
    return buf.getvalue()


@router.get("/account/billing/{payment_id}/invoice.pdf")
async def download_invoice_pdf(payment_id: str, user: dict = Depends(get_current_user)):
    """Hybrid: redirect to Stripe-hosted PDF when available, else generate one locally."""
    payment = await db.payment_transactions.find_one(
        {"$or": [{"id": payment_id}, {"session_id": payment_id}]}, {"_id": 0},
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Authorise: the payer themselves OR a teammate of the same org.
    paying_email = (payment.get("user_email") or "").lower()
    own = paying_email == (user.get("email") or "").lower()
    if not own and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="You cannot view this invoice")

    # Try to surface a Stripe-hosted PDF first.
    session_id = payment.get("stripe_session_id") or payment.get("session_id")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if session_id and stripe_key:
        try:
            import stripe
            stripe.api_key = stripe_key
            sess = stripe.checkout.Session.retrieve(session_id, expand=["invoice"])
            invoice = getattr(sess, "invoice", None)
            invoice_pdf = getattr(invoice, "invoice_pdf", None) if invoice else None
            if invoice_pdf:
                return RedirectResponse(invoice_pdf, status_code=302)
        except Exception as exc:
            logger.info(f"[account/invoice] Stripe lookup failed for {session_id}: {exc}")

    # Fallback: generate locally.
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0}) or {}
    pdf_bytes = _generate_invoice_pdf(payment, org)
    filename = f"invoice-{(payment.get('id') or session_id or payment_id)[:12]}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
