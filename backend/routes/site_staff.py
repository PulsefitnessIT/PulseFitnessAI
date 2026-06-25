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

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
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
    "require_staff_pin": False,
    "notify_manager": False,
    "notify_staff": False,
    "notify_service_desk": False,
    "notify_supplier": False,
}

GLOBAL_CONFIG_ID = "shared_login_global"
DEFAULT_GLOBAL = {
    "allow_shared_site_logins": True,
    "require_staff_selection": True,
    "allow_other_staff": False,
    "require_staff_pin": False,
    "notify_manager": True,
    "notify_staff": True,
    "notify_service_desk": False,
    "notify_supplier": False,
}


async def get_global_config() -> dict:
    doc = await db.app_config.find_one({"id": GLOBAL_CONFIG_ID}, {"_id": 0})
    return {**DEFAULT_GLOBAL, **((doc or {}).get("settings") or {})}


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
    pin: Optional[str] = Field(default=None, min_length=4, max_length=8)


class StaffUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    job_title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=3, max_length=40)
    department: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)
    receive_job_updates: Optional[bool] = None
    pin: Optional[str] = Field(default=None, max_length=8)  # "" clears the PIN


class GlobalConfigPayload(BaseModel):
    allow_shared_site_logins: Optional[bool] = None
    require_staff_selection: Optional[bool] = None
    allow_other_staff: Optional[bool] = None
    require_staff_pin: Optional[bool] = None
    notify_manager: Optional[bool] = None
    notify_staff: Optional[bool] = None
    notify_service_desk: Optional[bool] = None
    notify_supplier: Optional[bool] = None


class StaffTransfer(BaseModel):
    to_site_id: str


class ProvisionPayload(BaseModel):
    rotate: bool = False


class SharedLoginSettings(BaseModel):
    require_staff_selection: Optional[bool] = None
    allow_other_staff: Optional[bool] = None
    require_staff_pin: Optional[bool] = None
    notify_manager: Optional[bool] = None
    notify_staff: Optional[bool] = None
    notify_service_desk: Optional[bool] = None
    notify_supplier: Optional[bool] = None


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
    out = {k: v for k, v in doc.items() if k not in ("_id", "email_lc", "pin_hash")}
    out["has_pin"] = bool(doc.get("pin_hash"))
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
    ).sort("full_name", 1).to_list(1000)
    return {"staff": [_staff_public(s) for s in items]}


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
         "job_title": 1, "email": 1, "phone": 1, "pin_hash": 1},
    ).sort("full_name", 1).to_list(1000)
    site = await db.sites.find_one({"id": site_id}, {"_id": 0, "shared_login": 1})
    cfg = {**DEFAULT_SETTINGS, **(((site or {}).get("shared_login") or {}).get("settings") or {})}
    staff_out = [{
        "id": s["id"], "full_name": s.get("full_name"), "job_title": s.get("job_title"),
        "email": s.get("email"), "phone": s.get("phone"), "has_pin": bool(s.get("pin_hash")),
    } for s in items]
    return {
        "staff": staff_out,
        "settings": {
            "allow_other_staff": cfg.get("allow_other_staff", False),
            "require_staff_pin": cfg.get("require_staff_pin", False),
        },
    }


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
        "pin_hash": hash_password(payload.pin) if payload.pin else None,
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
    if payload.pin is not None:
        updates["pin_hash"] = hash_password(payload.pin) if payload.pin else None
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
    gcfg = await get_global_config()
    if not gcfg.get("allow_shared_site_logins"):
        raise HTTPException(403, "Shared site logins are disabled platform-wide by the administrator.")

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
    if "settings" not in site_shared:
        site_shared["settings"] = {k: gcfg.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
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
    for field in ("require_staff_selection", "allow_other_staff", "require_staff_pin",
                  "notify_manager", "notify_staff", "notify_service_desk", "notify_supplier"):
        val = getattr(payload, field)
        if val is not None:
            settings[field] = val
    site_shared["settings"] = settings
    await db.sites.update_one({"id": site_id}, {"$set": {"shared_login": site_shared}})
    await _audit("shared_login.settings", user, site_id, request, **settings)
    return {"settings": settings}


# ══════════════════════════════════════════════════════════════════
#              GLOBAL CONFIG — Admin → Portal Settings
# ══════════════════════════════════════════════════════════════════
def _require_master(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Master admin only")


@router.get("/master-admin/shared-login-config")
async def get_shared_login_config(user: dict = Depends(get_current_user)):
    _require_master(user)
    return {"config": await get_global_config()}


@router.put("/master-admin/shared-login-config")
async def update_shared_login_config(payload: GlobalConfigPayload, request: Request, user: dict = Depends(get_current_user)):
    _require_master(user)
    cfg = await get_global_config()
    for field in DEFAULT_GLOBAL:
        val = getattr(payload, field)
        if val is not None:
            cfg[field] = val
    await db.app_config.update_one(
        {"id": GLOBAL_CONFIG_ID},
        {"$set": {"id": GLOBAL_CONFIG_ID, "settings": cfg,
                  "updated_at": datetime.now(timezone.utc).isoformat(),
                  "updated_by": user.get("id")}},
        upsert=True,
    )
    await _audit("shared_login.global_config", user, "", request, **cfg)
    return {"config": cfg}


__all__ = ["router", "is_shared_site_login", "get_global_config"]


# ══════════════════════════════════════════════════════════════════
#              BULK IMPORT SITE STAFF  +  USAGE REPORT
# ══════════════════════════════════════════════════════════════════
STAFF_TEMPLATE_HEADERS = ["first_name", "last_name", "job_title", "email", "phone", "department", "active"]


class StaffImportConfirm(BaseModel):
    site_id: str
    rows: list[dict]


def _pick(row: dict, *names: str) -> str:
    low = {str(k).strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in low and low[n] is not None and str(low[n]).strip():
            return str(low[n]).strip()
    return ""


def _classify_import_row(r: dict, existing: set, seen: set) -> tuple[str, str]:
    em = (r.get("email") or "").lower()
    if not (r["first_name"] and r["last_name"] and r["job_title"] and em and r["phone"]):
        return "invalid", "Missing required field (first name, last name, job title, email, phone)"
    if "@" not in em:
        return "invalid", "Invalid email address"
    if em in existing or em in seen:
        return "duplicate", "Already exists for this site — will be skipped"
    return "new", ""


@router.get("/site-staff/import/template")
async def staff_import_template(user: dict = Depends(get_current_user)):
    _require_manager(user)
    csv = ",".join(STAFF_TEMPLATE_HEADERS) + "\n" + \
        "Sarah,Jones,General Manager,sarah@example.com,07123 456789,Management,yes\n" + \
        "David,Smith,Fitness Instructor,david@example.com,07123 456780,Fitness,yes\n"
    return Response(content=csv, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=site-staff-template.csv"})


@router.post("/site-staff/import/preview")
async def staff_import_preview(site_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Parse + validate + dedupe a staff spreadsheet WITHOUT inserting."""
    _require_manager(user)
    await _get_site(site_id, user)
    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    from utils.spreadsheet_import import iter_rows
    data = await file.read()
    validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    org_id = user.get("organization_id")
    existing_docs = await db.site_staff.find(
        {"organization_id": org_id, "site_id": site_id}, {"_id": 0, "email_lc": 1},
    ).to_list(5000)
    existing = {e["email_lc"] for e in existing_docs if e.get("email_lc")}
    rows: list[dict] = []
    seen: set = set()
    for raw in iter_rows(data, file.filename):
        r = {
            "first_name": _pick(raw, "first_name", "firstname", "first"),
            "last_name": _pick(raw, "last_name", "lastname", "last", "surname"),
            "job_title": _pick(raw, "job_title", "jobtitle", "title", "role"),
            "email": _pick(raw, "email", "email_address", "e-mail").lower(),
            "phone": _pick(raw, "phone", "telephone", "mobile", "contact", "tel"),
            "department": _pick(raw, "department", "dept") or None,
            "active": _pick(raw, "active", "status").lower() not in ("no", "false", "inactive", "0"),
        }
        if not any([r["first_name"], r["last_name"], r["job_title"], r["email"], r["phone"]]):
            continue
        status, reason = _classify_import_row(r, existing, seen)
        if r["email"]:
            seen.add(r["email"])
        rows.append({**r, "status": status, "reason": reason})
    summary = {
        "total": len(rows),
        "new": sum(1 for r in rows if r["status"] == "new"),
        "duplicate": sum(1 for r in rows if r["status"] == "duplicate"),
        "invalid": sum(1 for r in rows if r["status"] == "invalid"),
    }
    return {"rows": rows, "summary": summary}


@router.post("/site-staff/import/confirm")
async def staff_import_confirm(payload: StaffImportConfirm, request: Request, user: dict = Depends(get_current_user)):
    _require_manager(user)
    await _get_site(payload.site_id, user)
    org_id = user.get("organization_id")
    existing_docs = await db.site_staff.find(
        {"organization_id": org_id, "site_id": payload.site_id}, {"_id": 0, "email_lc": 1},
    ).to_list(5000)
    existing = {e["email_lc"] for e in existing_docs if e.get("email_lc")}
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    skipped = 0
    for r in payload.rows:
        em = (r.get("email") or "").lower().strip()
        if not (r.get("first_name") and r.get("last_name") and r.get("job_title") and em and "@" in em and r.get("phone")):
            skipped += 1
            continue
        if em in existing:
            skipped += 1
            continue
        existing.add(em)
        contact = await db.contacts.find_one(
            {"organization_id": org_id, "$or": [{"email": em}, {"email_lc": em}]}, {"_id": 0, "id": 1},
        )
        full_name = f"{r['first_name']} {r['last_name']}".strip()
        await db.site_staff.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org_id, "site_id": payload.site_id,
            "first_name": sanitise_string(r["first_name"]), "last_name": sanitise_string(r["last_name"]),
            "full_name": sanitise_string(full_name), "job_title": sanitise_string(r["job_title"]),
            "email": em, "email_lc": em, "phone": sanitise_string(r["phone"]),
            "department": sanitise_string(r.get("department")) if r.get("department") else None,
            "notes": None, "receive_job_updates": True,
            "contact_id": contact.get("id") if contact else None, "pin_hash": None,
            "is_active": bool(r.get("active", True)), "fault_count": 0, "last_reported_at": None,
            "created_at": now, "created_by": user.get("id"), "updated_at": now,
        })
        created += 1
    await _audit("site_staff.bulk_import", user, payload.site_id, request, created=created, skipped=skipped)
    return {"created": created, "skipped": skipped}


@router.get("/site-staff/reports/usage")
async def staff_usage_report(site_id: str, user: dict = Depends(get_current_user)):
    """Shared-login usage report — faults per staff member, shared-login
    volume, top reporters, and staff with no activity."""
    _require_manager(user)
    await _get_site(site_id, user)
    org_id = user.get("organization_id")
    agg = await db.issues.aggregate([
        {"$match": {"organization_id": org_id, "site_id": site_id}},
        {"$group": {"_id": "$reporter_staff_id", "count": {"$sum": 1},
                    "via_shared": {"$sum": {"$cond": [{"$eq": ["$logged_via_shared_login", True]}, 1, 0]}},
                    "name": {"$first": "$reporter_name"}}},
    ]).to_list(2000)
    agg_map = {a["_id"]: a for a in agg if a.get("_id")}
    staff = await db.site_staff.find(
        {"organization_id": org_id, "site_id": site_id},
        {"_id": 0, "id": 1, "full_name": 1, "job_title": 1, "is_active": 1},
    ).to_list(2000)
    by_staff = []
    for s in staff:
        a = agg_map.get(s["id"], {})
        by_staff.append({
            "staff_id": s["id"], "name": s.get("full_name"), "job_title": s.get("job_title"),
            "is_active": s.get("is_active", True),
            "count": a.get("count", 0), "via_shared": a.get("via_shared", 0),
        })
    by_staff.sort(key=lambda x: -x["count"])
    other = next((a for a in agg if not a.get("_id")), {})
    return {
        "summary": {
            "total_faults": sum(a["count"] for a in agg),
            "via_shared_login": sum(a["via_shared"] for a in agg),
            "staff_count": len(staff),
            "active_reporters": sum(1 for b in by_staff if b["count"] > 0),
            "unattributed": other.get("count", 0),
        },
        "by_staff": by_staff,
        "top_reporters": [b for b in by_staff if b["count"] > 0][:5],
        "no_activity": [b for b in by_staff if b["count"] == 0 and b["is_active"]],
    }
