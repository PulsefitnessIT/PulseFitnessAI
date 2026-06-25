"""Site Staff + Shared Site Login — commercial customer portals.

Generalises the MOD service-portal pattern (mod_portal.py) for commercial
Pulse Lite / Pulse Pro customer sites:

  • A site can have ONE shared login (username + password) that any number
    of physical site staff use to reach the Operations portal and log faults.
  • Owners / managers / admins maintain a list of authorised **site staff**
    (name, job title, email, phone) per site.
  • When a fault is logged from a shared login, the staff member MUST pick
    their own name first (enforced in routes/issues.py) so suppliers and
    engineers know exactly who to contact.

The shared login is a normal `db.users` record that signs in through the
existing landing-page /auth/login flow by **username** (no @). It is scoped
to one site via `site_id` + `allowed_site_ids` so the existing site-isolation
engine restricts it, and carries a least-privilege `role="site_staff"` flag
so it is blocked from every management endpoint here.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user, hash_password
from utils.database import db
from utils.security import sanitise_string
from utils.audit import audit_log

logger = logging.getLogger(__name__)
router = APIRouter()

# Account types that get the commercial shared-login feature. MOD sites keep
# their own purpose-built portal (mod_portal.py) and are intentionally excluded.
COMMERCIAL_ACCOUNT_TYPES = {"lite", "pulse_pro", "full"}

_MANAGER_ROLES = {"owner", "manager", "admin", "master_admin", "master"}

DEFAULT_SETTINGS = {
    "require_staff_selection": True,
    "allow_other_staff": False,
    "notify_manager": False,
    "notify_staff": False,
}


# ══════════════════════════════════════════════════════════════════
#                            MODELS
# ══════════════════════════════════════════════════════════════════
class StaffCreate(BaseModel):
    site_id: str
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    job_title: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=3, max_length=40)
    department: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)
    receive_job_updates: bool = True


class StaffUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    job_title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=3, max_length=40)
    department: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)
    receive_job_updates: Optional[bool] = None


class StaffTransfer(BaseModel):
    to_site_id: str


class ProvisionPayload(BaseModel):
    rotate: bool = False


class SharedLoginSettings(BaseModel):
    require_staff_selection: Optional[bool] = None
    allow_other_staff: Optional[bool] = None
    notify_manager: Optional[bool] = None
    notify_staff: Optional[bool] = None


# ══════════════════════════════════════════════════════════════════
#                            HELPERS
# ══════════════════════════════════════════════════════════════════
def is_shared_site_login(user: dict) -> bool:
    """True for the shared kiosk account (blocked from management)."""
    return bool(user.get("is_shared_site_login")) or (user.get("role") or "").lower() == "site_staff"


def _is_manager(user: dict) -> bool:
    if user.get("is_master_admin"):
        return True
    if is_shared_site_login(user):
        return False
    return (user.get("role") or "").lower() in _MANAGER_ROLES


def _require_manager(user: dict) -> None:
    if not _is_manager(user):
        raise HTTPException(403, "Only owners, managers or admins can manage site staff.")


async def _get_site(site_id: str, user: dict) -> dict:
    """Load a site and enforce it belongs to the caller's organisation."""
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        raise HTTPException(404, "Site not found")
    if not user.get("is_master_admin") and site.get("organization_id") != user.get("organization_id"):
        raise HTTPException(403, "That site is outside your organisation")
    return site


def _staff_public(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in ("_id", "email_lc")}
    return out


async def _audit(action: str, user: dict, site_id: str, request: Optional[Request] = None, **details) -> None:
    ip = ""
    if request and request.client:
        ip = request.client.host or ""
    detail_str = "; ".join(f"{k}={v}" for k, v in details.items() if v is not None)
    try:
        await db.shared_login_audit.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "organization_id": user.get("organization_id"),
            "site_id": site_id,
            "actor_user_id": user.get("id"),
            "actor_name": user.get("full_name") or user.get("username"),
            "via_shared_login": is_shared_site_login(user),
            "details": details,
            "ip_address": ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:  # pragma: no cover
        logger.warning("shared_login_audit write failed: %s", e)
    await audit_log(action, user.get("id", ""), user.get("email", ""), "site_staff", site_id, detail_str, ip)


def _slugify(value: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in (value or "").lower()).strip("-")
    return base or f"site-{uuid.uuid4().hex[:6]}"


def _mint_password() -> str:
    """A readable but strong site password (word-digits-word style)."""
    import secrets
    words = ["pulse", "atlas", "delta", "orbit", "nova", "vault", "fox", "river", "ridge", "ember"]
    return f"{secrets.choice(words).capitalize()}-{secrets.randbelow(9000) + 1000}-{secrets.choice(words)}"


# ══════════════════════════════════════════════════════════════════
#                       SITE STAFF — CRUD
# ══════════════════════════════════════════════════════════════════
@router.get("/site-staff")
async def list_site_staff(site_id: str, user: dict = Depends(get_current_user)):
    """Managers see all staff (active + inactive) for a site."""
    _require_manager(user)
    await _get_site(site_id, user)
    items = await db.site_staff.find(
        {"organization_id": user.get("organization_id"), "site_id": site_id},
        {"_id": 0, "email_lc": 0},
    ).sort("full_name", 1).to_list(1000)
    return {"staff": items}


@router.get("/site-staff/active")
async def list_active_site_staff(site_id: str, user: dict = Depends(get_current_user)):
    """Active staff for the mandatory "Who is logging this fault?" dropdown.

    Accessible to the shared-login account too — but it may only read its
    OWN site's staff (site-isolation), never another site's list.
    """
    if is_shared_site_login(user):
        allowed = set(user.get("allowed_site_ids") or [])
        if user.get("site_id"):
            allowed.add(user["site_id"])
        if allowed and site_id not in allowed:
            raise HTTPException(403, "You can only view staff for your own site")
    else:
        await _get_site(site_id, user)
    items = await db.site_staff.find(
        {"organization_id": user.get("organization_id"), "site_id": site_id, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "first_name": 1, "last_name": 1,
         "job_title": 1, "email": 1, "phone": 1},
    ).sort("full_name", 1).to_list(1000)
    return {"staff": items}


@router.post("/site-staff")
async def create_site_staff(payload: StaffCreate, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    await _get_site(payload.site_id, user)
    org_id = user.get("organization_id")
    email_lc = payload.email.lower().strip()
    dup = await db.site_staff.find_one(
        {"organization_id": org_id, "site_id": payload.site_id, "email_lc": email_lc, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1},
    )
    if dup:
        raise HTTPException(400, "A staff member with this email already exists for this site")

    # Link to an existing CRM contact rather than duplicating (no auto-create).
    contact = await db.contacts.find_one(
        {"organization_id": org_id, "$or": [{"email": email_lc}, {"email_lc": email_lc}]},
        {"_id": 0, "id": 1},
    )
    full_name = f"{payload.first_name} {payload.last_name}".strip()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "site_id": payload.site_id,
        "first_name": sanitise_string(payload.first_name),
        "last_name": sanitise_string(payload.last_name),
        "full_name": sanitise_string(full_name),
        "job_title": sanitise_string(payload.job_title),
        "email": payload.email,
        "email_lc": email_lc,
        "phone": sanitise_string(payload.phone),
        "department": sanitise_string(payload.department) if payload.department else None,
        "notes": sanitise_string(payload.notes) if payload.notes else None,
        "receive_job_updates": payload.receive_job_updates,
        "contact_id": contact.get("id") if contact else None,
        "is_active": True,
        "fault_count": 0,
        "last_reported_at": None,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
    }
    await db.site_staff.insert_one(doc)
    await _audit("site_staff.create", user, payload.site_id, request, staff_id=doc["id"], email=email_lc)
    return _staff_public(doc)


@router.patch("/site-staff/{staff_id}")
async def update_site_staff(staff_id: str, payload: StaffUpdate, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    existing = await db.site_staff.find_one(
        {"id": staff_id, "organization_id": user.get("organization_id")}, {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Staff not found")
    updates: dict = {}
    for field in ("first_name", "last_name", "job_title", "phone", "department", "notes"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = sanitise_string(val) if val else None
    if payload.email is not None:
        updates["email"] = payload.email
        updates["email_lc"] = payload.email.lower().strip()
    if payload.receive_job_updates is not None:
        updates["receive_job_updates"] = payload.receive_job_updates
    if "first_name" in updates or "last_name" in updates:
        fn = updates.get("first_name", existing.get("first_name", ""))
        ln = updates.get("last_name", existing.get("last_name", ""))
        updates["full_name"] = sanitise_string(f"{fn} {ln}".strip())
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.site_staff.update_one({"id": staff_id}, {"$set": updates})
    await _audit("site_staff.update", user, existing.get("site_id"), request, staff_id=staff_id)
    return {"ok": True}


@router.post("/site-staff/{staff_id}/deactivate")
async def deactivate_site_staff(staff_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    res = await db.site_staff.update_one(
        {"id": staff_id, "organization_id": user.get("organization_id")},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Staff not found")
    await _audit("site_staff.deactivate", user, "", request, staff_id=staff_id)
    return {"ok": True}


@router.post("/site-staff/{staff_id}/reactivate")
async def reactivate_site_staff(staff_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    res = await db.site_staff.update_one(
        {"id": staff_id, "organization_id": user.get("organization_id")},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Staff not found")
    await _audit("site_staff.reactivate", user, "", request, staff_id=staff_id)
    return {"ok": True}


@router.post("/site-staff/{staff_id}/transfer")
async def transfer_site_staff(staff_id: str, payload: StaffTransfer, request: Request, user: dict = Depends(get_current_user)):
    """Move a staff member to another site within the same organisation."""
    _require_manager(user)
    staff = await db.site_staff.find_one(
        {"id": staff_id, "organization_id": user.get("organization_id")}, {"_id": 0},
    )
    if not staff:
        raise HTTPException(404, "Staff not found")
    await _get_site(payload.to_site_id, user)
    if payload.to_site_id == staff.get("site_id"):
        raise HTTPException(400, "Staff member is already at that site")
    await db.site_staff.update_one(
        {"id": staff_id},
        {"$set": {"site_id": payload.to_site_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await _audit("site_staff.transfer", user, payload.to_site_id, request,
                 staff_id=staff_id, from_site=staff.get("site_id"), to_site=payload.to_site_id)
    return {"ok": True, "site_id": payload.to_site_id}


@router.get("/site-staff/{staff_id}/jobs")
async def staff_jobs(staff_id: str, user: dict = Depends(get_current_user)):
    """Faults logged by a given staff member (manager view)."""
    _require_manager(user)
    staff = await db.site_staff.find_one(
        {"id": staff_id, "organization_id": user.get("organization_id")}, {"_id": 0, "site_id": 1},
    )
    if not staff:
        raise HTTPException(404, "Staff not found")
    jobs = await db.issues.find(
        {"organization_id": user.get("organization_id"), "reporter_staff_id": staff_id},
        {"_id": 0, "id": 1, "machine_type": 1, "issue_description": 1, "severity": 1,
         "status": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(500)
    return {"jobs": jobs, "count": len(jobs)}


# ══════════════════════════════════════════════════════════════════
#                   SHARED SITE LOGIN — provisioning
# ══════════════════════════════════════════════════════════════════
async def _find_shared_login(site_id: str) -> Optional[dict]:
    return await db.users.find_one(
        {"site_id": site_id, "is_shared_site_login": True}, {"_id": 0},
    )


@router.get("/sites/{site_id}/shared-login")
async def get_shared_login(site_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    site = await _get_site(site_id, user)
    existing = await _find_shared_login(site_id)
    settings = {**DEFAULT_SETTINGS, **((site.get("shared_login") or {}).get("settings") or {})}
    return {
        "enabled": bool(existing),
        "username": existing.get("username") if existing else None,
        "password_updated_at": existing.get("password_updated_at") if existing else None,
        "settings": settings,
    }


@router.post("/sites/{site_id}/shared-login/provision")
async def provision_shared_login(site_id: str, payload: ProvisionPayload, request: Request, user: dict = Depends(get_current_user)):
    """Create OR rotate a site's shared login. Returns the plaintext
    password exactly once — only the bcrypt hash is stored thereafter."""
    _require_manager(user)
    site = await _get_site(site_id, user)
    org = await db.organizations.find_one({"id": site.get("organization_id")}, {"_id": 0, "account_type": 1, "name": 1})
    account_type = (org or {}).get("account_type")
    if account_type not in COMMERCIAL_ACCOUNT_TYPES:
        raise HTTPException(400, "Shared site login is only available for commercial customer sites")

    existing = await _find_shared_login(site_id)
    new_password = _mint_password()
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        if not payload.rotate:
            raise HTTPException(409, "This site already has a shared login. Use rotate to set a new password.")
        username = existing["username"]
        await db.users.update_one(
            {"id": existing["id"]},
            {"$set": {"password": hash_password(new_password), "password_updated_at": now}},
        )
        await _audit("shared_login.rotate", user, site_id, request, username=username)
    else:
        username = _slugify(site.get("name") or "site")
        if await db.users.find_one({"username": username}, {"_id": 0, "id": 1}):
            username = f"{username}-{uuid.uuid4().hex[:4]}"
        placeholder_email = f"{username}@site.local"
        if await db.users.find_one({"email": placeholder_email}, {"_id": 0, "id": 1}):
            placeholder_email = f"{username}+{uuid.uuid4().hex[:6]}@site.local"
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "username": username,
            "email": placeholder_email,
            "password": hash_password(new_password),
            "full_name": f"{site.get('name') or 'Site'} — Shared Login",
            "role": "site_staff",
            "account_type": account_type,
            "organization_id": site.get("organization_id"),
            "site_id": site_id,
            "allowed_site_ids": [site_id],
            "is_site_account": True,
            "is_shared_site_login": True,
            "login_type": "shared_site",
            "password_updated_at": now,
            "created_at": now,
            "created_by": user.get("id"),
        })
        await _audit("shared_login.provision", user, site_id, request, username=username)

    # Persist the enabled flag + default settings on the site.
    site_shared = site.get("shared_login") or {}
    site_shared["enabled"] = True
    site_shared["username"] = username
    site_shared.setdefault("settings", dict(DEFAULT_SETTINGS))
    await db.sites.update_one({"id": site_id}, {"$set": {"shared_login": site_shared}})

    return {"username": username, "password": new_password, "rotated": bool(existing)}


@router.post("/sites/{site_id}/shared-login/disable")
async def disable_shared_login(site_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    site = await _get_site(site_id, user)
    existing = await _find_shared_login(site_id)
    if existing:
        await db.users.delete_one({"id": existing["id"]})
    site_shared = site.get("shared_login") or {}
    site_shared["enabled"] = False
    await db.sites.update_one({"id": site_id}, {"$set": {"shared_login": site_shared}})
    await _audit("shared_login.disable", user, site_id, request)
    return {"ok": True}


@router.patch("/sites/{site_id}/shared-login/settings")
async def update_shared_login_settings(site_id: str, payload: SharedLoginSettings, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    site = await _get_site(site_id, user)
    site_shared = site.get("shared_login") or {}
    settings = {**DEFAULT_SETTINGS, **(site_shared.get("settings") or {})}
    for field in ("require_staff_selection", "allow_other_staff", "notify_manager", "notify_staff"):
        val = getattr(payload, field)
        if val is not None:
            settings[field] = val
    site_shared["settings"] = settings
    await db.sites.update_one({"id": site_id}, {"$set": {"shared_login": site_shared}})
    await _audit("shared_login.settings", user, site_id, request, **settings)
    return {"settings": settings}


__all__ = ["router", "is_shared_site_login"]
