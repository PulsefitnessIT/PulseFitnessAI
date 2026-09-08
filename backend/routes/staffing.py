"""Pulse Fitness Staffing — workforce intelligence backend.

Covers all 12 canonical staffing modules (Smart Rota, Profiles & Skills,
Availability & Leave, Shift Marketplace, Performance, Payroll, Live
Floor, Multi-Site, AI Optimisation, Compliance Rules, Comms). Time
tracking / clock-in is intentionally stubbed — user asked to park it.

Role gating
-----------
- `owner` / `manager` / `master_admin` → full management surface.
- `staff` → ONLY their own shifts, leave, open-shift marketplace, and
  announcements (read-only unless noted).
- `gym_floor` kiosk accounts have no direct staffing API access — the
  kiosk view reuses `/api/gym-floor/*` endpoints for roster + handover.

Data model
----------
- `staff_members`      — canonical staff record (certs, hourly_cost, site_ids)
- `staff_shifts`        — single shift (staff_id, site_id, start, end, role)
- `staff_leave_requests`— time-off request (holiday, sick, unpaid, training)
- `staff_open_shifts`   — unassigned shifts waiting to be claimed
- `staff_swap_requests` — shift swap between two staff members
- `staff_announcements` — manager → staff broadcasts
- `staff_rules`         — per-org compliance rules (max hours, break minutes)

Every endpoint writes only to the caller's organization_id and returns
role-filtered rows.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from utils.security_plus import safe_regex_exact
from pydantic import BaseModel, Field

from utils.dual_auth import get_current_user_or_crm as get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── Helpers ─────────────────────────

def _role(user: dict) -> str:
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return "master_admin"
    r = (user.get("role") or "").lower()
    return r if r in {"owner", "manager", "staff", "gym_floor"} else "staff"


def _is_manager(user: dict) -> bool:
    return _role(user) in {"owner", "manager", "master_admin"}


def _require_manager(user: dict) -> None:
    if not _is_manager(user):
        raise HTTPException(403, "Managers and owners only")


def _org(user: dict) -> str:
    oid = user.get("organization_id")
    if not oid:
        raise HTTPException(400, "No organization context")
    return oid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(doc: dict) -> dict:
    """Strip MongoDB _id + ObjectId sentinels before returning."""
    if not isinstance(doc, dict):
        return doc
    d = {k: v for k, v in doc.items() if k != "_id"}
    # Normalise datetimes to ISO strings so FastAPI's default JSON encoder
    # and downstream clients agree on format.
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.astimezone(timezone.utc).isoformat() if v.tzinfo else v.replace(tzinfo=timezone.utc).isoformat()
    return d


def _my_staff_id(user: dict, org_id: str) -> str | None:
    """Resolve the staff_members.id that matches the logged-in user.

    Staff records are linked to users by `user_id` (same UUID as
    `users.id`) OR by email match if user_id wasn't provided at create
    time. Returns None if no staff record exists — in which case a
    staff user won't be able to see any personal data yet.
    """
    u_id = user.get("id")
    email = (user.get("email") or "").lower()
    query = {"organization_id": org_id, "$or": [
        {"user_id": u_id} if u_id else {"user_id": "__never__"},
        {"email": email} if email else {"email": "__never__"},
    ]}
    doc = db.staff_members.find_one(query, {"_id": 0, "id": 1})
    if hasattr(doc, "__await__"):
        # Async Motor returns a coroutine.
        import asyncio  # noqa: WPS433 — lazy import
        doc = asyncio.get_event_loop().run_until_complete(doc)  # pragma: no cover
    return (doc or {}).get("id")


async def _my_staff_id_async(user: dict, org_id: str) -> str | None:
    """Async variant used by handlers — avoids the sync shim above."""
    u_id = user.get("id")
    email = (user.get("email") or "").lower()
    or_clauses = []
    if u_id:
        or_clauses.append({"user_id": u_id})
    if email:
        or_clauses.append({"email": email})
    if not or_clauses:
        return None
    doc = await db.staff_members.find_one(
        {"organization_id": org_id, "$or": or_clauses},
        {"_id": 0, "id": 1},
    )
    return (doc or {}).get("id")


# ───────────────────────── Models ─────────────────────────

VALID_ROLES = {"instructor", "pt", "manager", "reception", "cleaner", "maintenance", "lifeguard", "duty_manager", "other"}

# Iter 279c — neutral, business-wide default job roles. The platform now
# serves any company (not just gyms), so the suggested catalogue is generic;
# gyms can still add their own (e.g. "Instructor", "Lifeguard") via the Job
# Roles manager. The legacy gym roles stay VALID so existing staff records
# keep their label and never fail validation.
BUSINESS_DEFAULT_ROLES = [
    "manager", "engineer", "technician", "sales_manager",
    "administrator", "receptionist", "supervisor", "director", "other",
]
_LEGACY_GYM_ROLES = {
    "instructor", "pt", "reception", "cleaner",
    "maintenance", "lifeguard", "duty_manager",
}
# Validation superset — anything in here is an accepted primary_role.
VALID_ROLES = set(BUSINESS_DEFAULT_ROLES) | _LEGACY_GYM_ROLES


def _staff_role_from_platform_role(role, allowed: set) -> str:
    """Map a platform user role (set in Master Admin) to a staffing
    ``primary_role`` so a person's job role pulls through to Operations.

    Iter 279c — ``engineer`` / ``sales_manager`` / ``technician`` etc. now
    flow straight through; the historical owner/manager/staff buckets keep
    their meaning. Unrecognised roles fall back to "other"."""
    r = (role or "").strip().lower()
    explicit = {"owner": "manager", "manager": "manager", "staff": "other"}
    if r in explicit:
        return explicit[r]
    allowed_lc = {str(x).lower() for x in (allowed or set())}
    if r and r in allowed_lc:
        return r
    return "other"


def _platform_role_from_staff_role(primary_role) -> str:
    """Reverse of _staff_role_from_platform_role: map a Staffing job role to a
    platform login role (platform set = owner/manager/staff/engineer). Owner is
    never auto-assigned. Makes an 'Engineer' in Staffing become an 'engineer'
    login (Engineer App access) instead of a generic 'staff'/sales role."""
    r = (primary_role or "").strip().lower()
    if r in {"engineer", "technician", "maintenance"}:
        return "engineer"
    # People-management roles → platform "manager". NOTE: "administrator" is an
    # office/admin job (not a people-manager) so it maps to "staff", not manager.
    if r in {"manager", "supervisor", "director", "duty_manager", "sales_manager"}:
        return "manager"
    return "staff"


async def _propagate_role_to_login(org_id: str, staff: dict) -> bool:
    """Keep a staff member's linked platform login role in sync with their
    Staffing job role. Never downgrades an owner / master admin. Returns True
    if a login role was changed."""
    target = _platform_role_from_staff_role(staff.get("primary_role"))
    q = None
    if staff.get("user_id"):
        q = {"id": staff["user_id"]}
    elif (staff.get("email") or "").strip():
        q = {"email": staff["email"].strip().lower()}
    if not q:
        return False
    u = await db.users.find_one(q, {"_id": 0, "id": 1, "role": 1})
    if not u:
        return False
    cur = (u.get("role") or "").lower()
    if cur in {"owner", "master_admin", "pulse_master_admin"}:
        return False  # elevated — managed only in Master Admin
    if cur == target:
        return False
    await db.users.update_one({"id": u["id"]},
                              {"$set": {"role": target, "updated_at": _now().isoformat()}})
    return True


VALID_SHIFT_STATUS = {"scheduled", "confirmed", "completed", "cancelled", "open"}
VALID_LEAVE_TYPE = {"holiday", "sick", "unpaid", "training", "other"}
VALID_LEAVE_STATUS = {"pending", "approved", "rejected", "cancelled"}
VALID_SWAP_STATUS = {"pending", "accepted", "rejected", "cancelled"}


# Iter 216h243 — custom staff roles per organization. Tenants asked
# for the ability to add roles beyond the platform defaults
# (e.g. "swim coach", "first aider", "spa therapist"). Stored on
# ``organizations.custom_staff_roles[]`` as plain string list and
# blended into ``VALID_ROLES`` on every validation call.
async def _allowed_roles_for(org_id: str | None) -> set[str]:
    """Union of platform defaults and the org's custom_staff_roles."""
    if not org_id:
        return set(VALID_ROLES)
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "custom_staff_roles": 1},
    )
    custom = (org or {}).get("custom_staff_roles") or []
    return set(VALID_ROLES) | {r.strip() for r in custom if isinstance(r, str) and r.strip()}


class StaffCreate(BaseModel):
    full_name: str
    email: str | None = None
    user_id: str | None = None
    primary_role: str = "reception"
    secondary_roles: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    site_ids: list[str] = Field(default_factory=list)
    contract_type: str | None = "part_time"  # part_time|full_time|casual|contractor
    weekly_hours: float | None = None
    # Iter 216h241 — canonical contracted-hours field. ``weekly_hours``
    # is kept above for backward compat with legacy callers; the HR
    # profile (see ``routes/staffing_hr.PROFILE_FIELDS``) writes to
    # ``hours_per_week``, so accept it here too and mirror across both
    # keys on persist so the staff list + HR profile stay consistent.
    hours_per_week: float | None = None
    hourly_cost: float = 0.0
    phone: str | None = None
    active: bool = True
    notes: str | None = None


class StaffUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    primary_role: str | None = None
    secondary_roles: list[str] | None = None
    certifications: list[str] | None = None
    site_ids: list[str] | None = None
    contract_type: str | None = None
    weekly_hours: float | None = None
    # Iter 216h241 — see StaffCreate. Accepted here for the same reason.
    hours_per_week: float | None = None
    hourly_cost: float | None = None
    phone: str | None = None
    active: bool | None = None
    notes: str | None = None


class ShiftCreate(BaseModel):
    staff_id: str | None = None           # optional → creates an Open Shift
    site_id: str | None = None
    date: str                              # YYYY-MM-DD (local gym time)
    start_time: str                        # HH:MM
    end_time: str                          # HH:MM
    role: str = "reception"
    notes: str | None = None
    break_minutes: int = 0
    status: str = "scheduled"


class ShiftUpdate(BaseModel):
    staff_id: str | None = None
    site_id: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    role: str | None = None
    notes: str | None = None
    break_minutes: int | None = None
    status: str | None = None


class LeaveRequestCreate(BaseModel):
    start_date: str                   # YYYY-MM-DD
    end_date: str                     # YYYY-MM-DD (inclusive)
    leave_type: str = "holiday"
    reason: str | None = None


class SwapRequestCreate(BaseModel):
    offered_shift_id: str
    recipient_staff_id: str | None = None   # None → post to marketplace
    requested_shift_id: str | None = None   # None → drop / claim


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    audience: str = "all"                  # all | site:<id> | role:<role>
    pinned: bool = False


class RulesUpdate(BaseModel):
    max_hours_per_week: float | None = None
    min_rest_hours_between_shifts: float | None = None
    min_break_minutes_per_shift: float | None = None
    max_days_consecutive: int | None = None
    require_manager_approval_for_overtime: bool | None = None


def _shift_hours(s: dict) -> float:
    """Compute paid hours for a shift (start→end minus break)."""
    try:
        sh, sm = [int(x) for x in s["start_time"].split(":")]
        eh, em = [int(x) for x in s["end_time"].split(":")]
        mins = (eh * 60 + em) - (sh * 60 + sm) - int(s.get("break_minutes") or 0)
        return max(0.0, mins / 60.0)
    except Exception:
        return 0.0


# ───────────────────────── Staff profiles ─────────────────────────

@router.get("/staffing/staff")
async def list_staff(include_inactive: bool = Query(False), user: dict = Depends(get_current_user)):
    """Managers see all staff. Staff see their own profile only.

    Iter 216h49 — Auto-backfill: any platform user (db.users) on this org
    that doesn't already have a matching staff_members row is added on the
    fly with sensible defaults. Lee reported that staff added via Master
    Admin → People had to be re-added inside Staffing, causing duplicates
    and easy-to-miss "ghost" staff. This union pattern keeps the two
    collections in sync without changing every user-creation code path.
    """
    org_id = _org(user)
    # ── Auto-backfill missing staff_members rows for managers ──────
    if _is_manager(user):
        await _ensure_staff_for_org_users(org_id)
    q: dict = {"organization_id": org_id}
    if not include_inactive:
        q["active"] = True
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["id"] = sid or "__none__"
    rows = await db.staff_members.find(q, {"_id": 0}).sort("full_name", 1).to_list(1000)
    return {"staff": rows, "role": _role(user)}


async def _ensure_staff_for_org_users(org_id: str) -> int:
    """Iter 216h49 — Ensure every db.users row on this org has a matching
    db.staff_members row. Returns the number of rows inserted.

    Match priority (so we don't double-insert):
      1. staff_members.user_id == users.id
      2. staff_members.email == users.email (case-insensitive)
    Roles map: gym 'owner'/'manager'/'staff' → staffing 'manager'/'manager'/'reception'.
    The owner is included so they appear in the rota; rate defaults to 0.
    """
    users = await db.users.find(
        {"organization_id": org_id, "disabled": {"$ne": True}},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1},
    ).to_list(2000)
    # Iter 288 — also union in db.crm_users. `_create_org_user` routes a new
    # user to `users` and/or `crm_users` based on the org's portal_type /
    # enabled modules, so staff added via Master Admin to a CRM-primary org
    # (e.g. Pulse Fitness Ltd) land ONLY in crm_users and were invisible in
    # Operations → Staff → HR. Pulling both collections guarantees every
    # internal team member shows up regardless of which one they were
    # written to. Dedup below (by user_id + email) prevents double-inserts.
    crm_people = await db.crm_users.find(
        {"organization_id": org_id, "disabled": {"$ne": True}},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1},
    ).to_list(2000)
    _seen_ids = {u.get("id") for u in users}
    users = users + [c for c in crm_people if c.get("id") not in _seen_ids]
    if not users:
        return 0
    existing_staff = await db.staff_members.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "primary_role": 1,
         "primary_role_source": 1, "auto_synced_from_users": 1},
    ).to_list(5000)
    by_user_id = {s.get("user_id"): s for s in existing_staff if s.get("user_id")}
    seen_user_ids = set(by_user_id.keys())
    seen_emails = {(s.get("email") or "").strip().lower() for s in existing_staff if s.get("email")}

    allowed = await _allowed_roles_for(org_id)
    inserted = 0
    now_iso = _now().isoformat()
    for u in users:
        mapped_role = _staff_role_from_platform_role(u.get("role"), allowed)
        if u["id"] in seen_user_ids:
            # Iter 279c — reconcile: keep an auto-synced staff member's
            # primary_role aligned with the platform role set in Master
            # Admin, UNLESS a manager has manually overridden it in HR
            # (primary_role_source == "manual"). This is what makes
            # "Ryan = Engineer in Master Admin" show as Engineer in Ops.
            s = by_user_id.get(u["id"])
            if (s and s.get("auto_synced_from_users")
                    and s.get("primary_role_source") != "manual"
                    and mapped_role and s.get("primary_role") != mapped_role):
                await db.staff_members.update_one(
                    {"id": s["id"], "organization_id": org_id},
                    {"$set": {"primary_role": mapped_role,
                              "primary_role_source": "platform",
                              "updated_at": now_iso}},
                )
            continue
        em = (u.get("email") or "").strip().lower()
        if em and em in seen_emails:
            # Match by email — bind the user_id so future lookups are
            # O(1) and self-healing.
            await db.staff_members.update_one(
                {"organization_id": org_id, "email": safe_regex_exact(em), "user_id": {"$exists": False}},
                {"$set": {"user_id": u["id"], "updated_at": now_iso}},
            )
            continue
        doc = {
            "id": str(uuid4()),
            "organization_id": org_id,
            "user_id": u["id"],
            "email": u.get("email"),
            "full_name": u.get("full_name") or (u.get("email") or "").split("@")[0] or "Unnamed",
            "primary_role": mapped_role,
            "primary_role_source": "platform",
            "secondary_roles": [],
            "certifications": [],
            "site_ids": [],
            "contract_type": "part_time",
            "hourly_cost": 0.0,
            "active": True,
            "created_at": now_iso,
            "auto_synced_from_users": True,
        }
        await db.staff_members.insert_one(doc.copy())
        inserted += 1
        if em:
            seen_emails.add(em)
        seen_user_ids.add(u["id"])
    return inserted


@router.post("/staffing/staff")
async def create_staff(body: StaffCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    allowed = await _allowed_roles_for(org_id)
    if body.primary_role not in allowed:
        raise HTTPException(400, f"primary_role must be one of {sorted(allowed)}")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        **body.dict(),
    }
    # Iter 216h241 — mirror the contracted-hours value across both keys
    # (``hours_per_week`` ↔ ``weekly_hours``) so the staff list and the
    # HR profile read the same number regardless of which write path
    # the caller used. Whichever value is non-null wins; ties are fine
    # because they're identical.
    h = doc.get("hours_per_week") or doc.get("weekly_hours")
    if h is not None:
        doc["hours_per_week"] = h
        doc["weekly_hours"] = h
    await db.staff_members.insert_one(doc.copy())
    return _clean(doc)


@router.patch("/staffing/staff/{staff_id}")
async def update_staff(staff_id: str, body: StaffUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "primary_role" in patch:
        allowed = await _allowed_roles_for(org_id)
        if patch["primary_role"] not in allowed:
            raise HTTPException(400, "invalid primary_role")
        # Iter 279c — a manager-set role wins over the Master Admin sync;
        # mark it so the auto-reconcile never clobbers their choice.
        patch["primary_role_source"] = "manual"
    # Iter 216h241 — see create_staff: keep both contracted-hours keys
    # in lock-step so the HR profile and the staff list never disagree.
    if "hours_per_week" in patch and "weekly_hours" not in patch:
        patch["weekly_hours"] = patch["hours_per_week"]
    elif "weekly_hours" in patch and "hours_per_week" not in patch:
        patch["hours_per_week"] = patch["weekly_hours"]
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_members.update_one({"id": staff_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "staff not found")
    doc = await db.staff_members.find_one({"id": staff_id}, {"_id": 0})
    # Iter (Aug 2026) — a job-role change flows through to the person's platform
    # login so Master Admin never disagrees with Staffing.
    if "primary_role" in patch and doc:
        try:
            await _propagate_role_to_login(org_id, doc)
        except Exception:
            pass
    return doc


@router.delete("/staffing/staff/{staff_id}")
async def archive_staff(staff_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_members.update_one({"id": staff_id, "organization_id": org_id}, {"$set": {"active": False, "archived_at": _now().isoformat()}})
    if res.matched_count == 0:
        raise HTTPException(404, "staff not found")
    return {"ok": True}


# ───────────────────────── Iter 216h264 — Staff portal credentials ──
#
# Today `create_staff` only inserts a row into `staff_members`. That
# row is enough for the rota / payroll / KPI side of the platform but
# it does NOT give the person a login to the Pulse staff portal.
#
# Managers can now issue (or reset) a staff member's portal login from
# the Staff tab. The endpoint:
#
#   1. Locates the staff_members row in the caller's org.
#   2. Upserts the matching `users` doc with role="staff" (creates if
#      absent, refreshes the password if present).
#   3. Generates a 10-character urlsafe temporary password and bcrypts
#      it before persisting. The plaintext value is returned ONCE in
#      the response so the manager can hand it to the staff member.
#   4. (Best-effort) sends an email with the credentials + portal URL
#      via the existing utils.email pipeline. Failure to send doesn't
#      fail the request — managers can always copy the password from
#      the response.

from pydantic import EmailStr


class StaffCredentialsRequest(BaseModel):
    email: EmailStr | None = None  # falls back to staff_member.email
    send_email: bool = True
    delivery: str = "temp_password"  # "temp_password" | "reset_link"


@router.post("/staffing/staff/{staff_id}/issue-credentials")
async def issue_staff_credentials(
    staff_id: str,
    body: StaffCredentialsRequest | None = None,
    user: dict = Depends(get_current_user),
):
    import secrets
    from utils.auth import hash_password

    _require_manager(user)
    org_id = _org(user)
    body = body or StaffCredentialsRequest()

    staff = await db.staff_members.find_one(
        {"id": staff_id, "organization_id": org_id}, {"_id": 0}
    )
    if not staff:
        raise HTTPException(404, "staff not found")

    email = (body.email or staff.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            400,
            "Staff member has no email on file. Save an email on their "
            "profile (or pass one in the body) before issuing credentials.",
        )

    now_iso = _now().isoformat()
    # The login's platform role is DERIVED from the staff member's job role,
    # so an Engineer in Staffing becomes an 'engineer' login (not generic staff).
    mapped_role = _platform_role_from_staff_role(staff.get("primary_role"))
    use_link = (body.delivery or "").lower() == "reset_link"

    # Generate a friendly temp password — 10 url-safe chars, easy to
    # type without ambiguous glyphs. (Unused text is fine when using a link.)
    temp_password = secrets.token_urlsafe(8).replace("_", "x").replace("-", "y")[:10]

    user_doc_seed = {
        "id": str(uuid4()),
        "email": email,
        "full_name": staff.get("full_name") or email,
        "organization_id": org_id,
        "role": mapped_role,
        "staff_member_id": staff_id,
        "must_change_password": True,
        "created_at": now_iso,
    }
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        # Reset rather than fail — managers often re-issue when staff
        # lose their password. Never downgrade an elevated role.
        keep_elevated = existing.get("role") in {"owner", "manager", "master_admin", "pulse_master_admin"}
        update = {
            "must_change_password": True,
            "staff_member_id": staff_id,
            "organization_id": existing.get("organization_id") or org_id,
            "role": existing.get("role") if keep_elevated else mapped_role,
        }
        if not use_link:
            update["password"] = hash_password(temp_password)
            update["password_updated_at"] = now_iso
        await db.users.update_one({"email": email}, {"$set": update})
        user_id = existing["id"]
        created = False
    else:
        if use_link:
            # Placeholder password so the account is disabled until the
            # invitee sets one via the link.
            user_doc_seed["password"] = hash_password(secrets.token_urlsafe(16))
        else:
            user_doc_seed["password"] = hash_password(temp_password)
        user_doc_seed["password_updated_at"] = now_iso
        await db.users.insert_one(user_doc_seed.copy())
        user_id = user_doc_seed["id"]
        created = True

    # Link the staff record to its login so Master Admin + role-sync agree.
    await db.staff_members.update_one(
        {"id": staff_id, "organization_id": org_id},
        {"$set": {"email": email, "user_id": user_id, "portal_role": mapped_role,
                  "portal_credentials_issued_at": now_iso}},
    )

    # Best-effort engineer app provisioning when the role warrants it.
    if mapped_role == "engineer":
        try:
            from routes.account import _sync_engineer_provisioning
            await _sync_engineer_provisioning({
                "id": user_id, "role": "engineer", "organization_id": org_id,
                "email": email, "full_name": staff.get("full_name") or email,
            })
        except Exception:
            logger.exception("[staff-credentials] engineer provisioning failed")

    invite_url = None
    if use_link:
        try:
            from routes.account import _issue_reset_token
            tok = await _issue_reset_token({"id": user_id, "email": email}, user.get("email", ""))
            invite_url = tok.get("invite_url")
        except Exception:
            logger.exception("[staff-credentials] invite link mint failed")

    sent = False
    if body.send_email:
        try:
            from utils.email import send_email  # generic helper
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
            site_url = (
                os.environ.get("APP_PUBLIC_URL")
                or "https://pulsefitness.ai"
            ).rstrip("/")
            org_name = org.get("name") or "your team"
            subject = f"Your {org_name} staff portal login"
            if use_link and invite_url:
                html = (
                    f"<p>Hi {staff.get('full_name') or 'there'},</p>"
                    f"<p>{user.get('full_name') or 'Your manager'} has invited you to the "
                    f"<b>{org_name}</b> staff portal.</p>"
                    f"<p>Set your password to get started:</p>"
                    f"<p><a href=\"{invite_url}\">{invite_url}</a></p>"
                    f"<p>This link expires in 72 hours.</p>"
                )
            else:
                html = (
                    f"<p>Hi {staff.get('full_name') or 'there'},</p>"
                    f"<p>{user.get('full_name') or 'Your manager'} has created a "
                    f"staff portal account for you on <b>{org_name}</b>.</p>"
                    f"<p><b>Email:</b> {email}<br>"
                    f"<b>Temporary password:</b> <code>{temp_password}</code></p>"
                    f"<p>Log in here: <a href=\"{site_url}/login\">{site_url}/login</a></p>"
                    f"<p>You&rsquo;ll be asked to change your password on first login.</p>"
                )
            await send_email(to=email, subject=subject, html=html)
            sent = True
        except Exception:
            logger.exception("[staff-credentials] welcome email failed")

    return {
        "ok": True,
        "email": email,
        "role": mapped_role,
        "delivery": "reset_link" if use_link else "temp_password",
        "temp_password": None if use_link else temp_password,
        "invite_url": invite_url,
        "created": created,
        "email_sent": sent,
    }


@router.post("/staffing/reconcile-roles")
async def reconcile_staff_login_roles(user: dict = Depends(get_current_user)):
    """One-off reconcile: align every staff member's linked platform login role
    with their Staffing job role (fixes historic mismatches like an Engineer
    showing as sales_rep/staff in Master Admin). Never downgrades an elevated
    role. Returns how many logins were changed."""
    _require_manager(user)
    org_id = _org(user)
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0}
    ).to_list(2000)
    checked = 0
    updated = 0
    changes = []
    for s in staff:
        if not (s.get("user_id") or (s.get("email") or "").strip()):
            continue
        checked += 1
        if await _propagate_role_to_login(org_id, s):
            updated += 1
            changes.append({"staff_id": s["id"], "name": s.get("full_name"),
                            "role": _platform_role_from_staff_role(s.get("primary_role"))})
    return {"ok": True, "checked": checked, "updated": updated, "changes": changes}


# ───────────────────────── Rota / shifts ─────────────────────────

@router.get("/staffing/shifts")
async def list_shifts(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    site_id: str | None = Query(None),
    staff_id: str | None = Query(None),
    status: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Manager view: every shift. Staff view: only their own."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if date_from:
        q["date"] = {**q.get("date", {}), "$gte": date_from}
    if date_to:
        q["date"] = {**q.get("date", {}), "$lte": date_to}
    if site_id:
        q["site_id"] = site_id
    if status:
        q["status"] = status
    if staff_id and _is_manager(user):
        q["staff_id"] = staff_id
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["staff_id"] = sid or "__none__"
    rows = await db.staff_shifts.find(q, {"_id": 0}).sort([("date", 1), ("start_time", 1)]).to_list(1000)
    # Enrich with staff name + labour cost (computed) — useful for the rota grid.
    if rows:
        staff_ids = list({r.get("staff_id") for r in rows if r.get("staff_id")})
        staff = {s["id"]: s async for s in db.staff_members.find({"id": {"$in": staff_ids}}, {"_id": 0, "id": 1, "full_name": 1, "hourly_cost": 1, "primary_role": 1})}
        for r in rows:
            s = staff.get(r.get("staff_id") or "", {})
            r["staff_name"] = s.get("full_name") or ("OPEN SHIFT" if r.get("status") == "open" else "—")
            r["hours"] = _shift_hours(r)
            r["labour_cost"] = round(r["hours"] * float(s.get("hourly_cost") or 0.0), 2) if _is_manager(user) else None
    return {"shifts": rows, "role": _role(user)}


@router.post("/staffing/shifts")
async def create_shift(body: ShiftCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    if body.status not in VALID_SHIFT_STATUS:
        raise HTTPException(400, "invalid status")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        **body.dict(),
    }
    # No staff → open shift that managers can publish or staff can claim.
    if not doc.get("staff_id"):
        doc["status"] = "open"
    await db.staff_shifts.insert_one(doc.copy())
    # Compliance check: soft warn on breaches (doesn't block).
    warnings = await _check_compliance(org_id, doc)
    return {"shift": _clean(doc), "warnings": warnings}


@router.patch("/staffing/shifts/{shift_id}")
async def update_shift(shift_id: str, body: ShiftUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "status" in patch and patch["status"] not in VALID_SHIFT_STATUS:
        raise HTTPException(400, "invalid status")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_shifts.update_one({"id": shift_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "shift not found")
    doc = await db.staff_shifts.find_one({"id": shift_id}, {"_id": 0})
    warnings = await _check_compliance(org_id, doc) if doc else []
    return {"shift": doc, "warnings": warnings}


@router.delete("/staffing/shifts/{shift_id}")
async def delete_shift(shift_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_shifts.delete_one({"id": shift_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "shift not found")
    return {"ok": True}


@router.post("/staffing/shifts/bulk")
async def bulk_create_shifts(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Copy-week helper: accepts {source_start, target_start, site_id?} and
    clones all shifts from the source week to the target week.
    """
    _require_manager(user)
    org_id = _org(user)
    src = body.get("source_start")
    tgt = body.get("target_start")
    if not src or not tgt:
        raise HTTPException(400, "source_start and target_start required (YYYY-MM-DD)")
    delta_days = (datetime.fromisoformat(tgt).date() - datetime.fromisoformat(src).date()).days
    q = {"organization_id": org_id, "date": {"$gte": src, "$lt": (datetime.fromisoformat(src).date() + timedelta(days=7)).isoformat()}}
    if body.get("site_id"):
        q["site_id"] = body["site_id"]
    src_rows = await db.staff_shifts.find(q, {"_id": 0}).to_list(10_000)
    created = []
    for r in src_rows:
        new_date = (datetime.fromisoformat(r["date"]).date() + timedelta(days=delta_days)).isoformat()
        clone = {**r, "id": str(uuid4()), "date": new_date, "created_at": _now().isoformat(), "created_by": user.get("email"), "status": "scheduled"}
        clone.pop("updated_at", None)
        await db.staff_shifts.insert_one(clone.copy())
        created.append(clone.get("id"))
    return {"created_count": len(created), "created_ids": created}


# ───────────────────────── Availability & leave ─────────────────────────

@router.get("/staffing/leave")
async def list_leave(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["staff_id"] = sid or "__none__"
    rows = await db.staff_leave_requests.find(q, {"_id": 0}).sort("start_date", -1).to_list(500)
    return {"leave": rows, "role": _role(user)}


@router.post("/staffing/leave")
async def create_leave(body: LeaveRequestCreate, user: dict = Depends(get_current_user)):
    """Any authenticated staff member can submit. Managers submit on
    behalf of themselves or use PATCH-approve for others."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account — ask a manager to add you.")
    if body.leave_type not in VALID_LEAVE_TYPE:
        raise HTTPException(400, "invalid leave_type")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "staff_id": sid,
        "status": "pending",
        "created_at": _now().isoformat(),
        **body.dict(),
    }
    await db.staff_leave_requests.insert_one(doc.copy())
    return _clean(doc)


@router.patch("/staffing/leave/{leave_id}")
async def decide_leave(leave_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Managers only — approve / reject with optional notes."""
    _require_manager(user)
    org_id = _org(user)
    decision = (body.get("status") or "").lower()
    if decision not in {"approved", "rejected", "cancelled"}:
        raise HTTPException(400, "status must be approved|rejected|cancelled")
    patch = {"status": decision, "decided_at": _now().isoformat(), "decided_by": user.get("email")}
    if body.get("manager_notes"):
        patch["manager_notes"] = body["manager_notes"]
    res = await db.staff_leave_requests.update_one({"id": leave_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "leave request not found")
    doc = await db.staff_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    # Attendance Spine — one approved leave event fans out to every daily
    # record it covers (§3/§80). Revoking recomputes those days back to the
    # working pattern. Best-effort so the decision itself never fails.
    try:
        from routes.attendance import apply_leave_to_daily
        await apply_leave_to_daily(org_id, doc)
    except Exception as e:
        logging.getLogger(__name__).warning(
            "attendance spine fan-out failed for leave %s (staff %s): %s",
            leave_id, (doc or {}).get("staff_id"), e,
        )
    return doc


# ───────────────────────── Shift marketplace ─────────────────────────

@router.get("/staffing/marketplace/open")
async def list_open_shifts(user: dict = Depends(get_current_user)):
    """All logged-in staff can see open shifts to claim. Managers see
    the same list for oversight."""
    org_id = _org(user)
    rows = await db.staff_shifts.find({"organization_id": org_id, "status": "open"}, {"_id": 0}).sort("date", 1).to_list(500)
    for r in rows:
        r["hours"] = _shift_hours(r)
    return {"open_shifts": rows}


@router.post("/staffing/marketplace/open/{shift_id}/claim")
async def claim_open_shift(shift_id: str, user: dict = Depends(get_current_user)):
    """Any staff member (or manager) can claim an open shift. Request is
    queued for manager approval before the shift is assigned."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account.")
    shift = await db.staff_shifts.find_one({"id": shift_id, "organization_id": org_id, "status": "open"}, {"_id": 0})
    if not shift:
        raise HTTPException(404, "open shift not found")
    # Insert a swap request that represents the claim. Manager approves.
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": "claim",
        "offered_shift_id": shift_id,
        "requesting_staff_id": sid,
        "status": "pending",
        "created_at": _now().isoformat(),
    }
    await db.staff_swap_requests.insert_one(doc.copy())
    return _clean(doc)


@router.post("/staffing/marketplace/swap")
async def request_swap(body: SwapRequestCreate, user: dict = Depends(get_current_user)):
    """Staff requests a shift swap. Sent to recipient (or marketplace)
    pending manager approval.
    """
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        raise HTTPException(400, "No staff record linked to your account.")
    shift = await db.staff_shifts.find_one({"id": body.offered_shift_id, "organization_id": org_id}, {"_id": 0})
    if not shift or (shift.get("staff_id") != sid and not _is_manager(user)):
        raise HTTPException(400, "Offered shift isn't yours or doesn't exist.")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": "swap" if body.requested_shift_id else "drop",
        "offered_shift_id": body.offered_shift_id,
        "requested_shift_id": body.requested_shift_id,
        "requesting_staff_id": sid,
        "recipient_staff_id": body.recipient_staff_id,
        "status": "pending",
        "created_at": _now().isoformat(),
    }
    await db.staff_swap_requests.insert_one(doc.copy())
    return _clean(doc)


@router.get("/staffing/marketplace/requests")
async def list_swap_requests(user: dict = Depends(get_current_user)):
    """Managers see every request. Staff see requests they originated
    OR were addressed to."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id}
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        if not sid:
            return {"requests": []}
        q["$or"] = [{"requesting_staff_id": sid}, {"recipient_staff_id": sid}]
    rows = await db.staff_swap_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"requests": rows}


@router.patch("/staffing/marketplace/requests/{req_id}")
async def decide_swap(req_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Managers approve/reject. On approve, we apply the effect:
    - kind=claim    → assign the offered_shift_id to requesting_staff.
    - kind=drop     → mark the offered shift as `open`.
    - kind=swap     → swap staff_ids between offered and requested shifts.
    """
    _require_manager(user)
    org_id = _org(user)
    decision = (body.get("status") or "").lower()
    if decision not in {"approved", "rejected", "cancelled"}:
        raise HTTPException(400, "status must be approved|rejected|cancelled")
    req = await db.staff_swap_requests.find_one({"id": req_id, "organization_id": org_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "request not found")
    patch = {"status": decision, "decided_at": _now().isoformat(), "decided_by": user.get("email")}
    if decision == "approved":
        kind = req.get("kind")
        if kind == "claim":
            await db.staff_shifts.update_one(
                {"id": req["offered_shift_id"], "organization_id": org_id},
                {"$set": {"staff_id": req["requesting_staff_id"], "status": "scheduled"}},
            )
        elif kind == "drop":
            await db.staff_shifts.update_one(
                {"id": req["offered_shift_id"], "organization_id": org_id},
                {"$set": {"status": "open", "staff_id": None}},
            )
        elif kind == "swap" and req.get("requested_shift_id"):
            a = await db.staff_shifts.find_one({"id": req["offered_shift_id"]}, {"_id": 0})
            b = await db.staff_shifts.find_one({"id": req["requested_shift_id"]}, {"_id": 0})
            if a and b:
                await db.staff_shifts.update_one({"id": a["id"]}, {"$set": {"staff_id": b.get("staff_id")}})
                await db.staff_shifts.update_one({"id": b["id"]}, {"$set": {"staff_id": a.get("staff_id")}})
    await db.staff_swap_requests.update_one({"id": req_id}, {"$set": patch})
    return {**req, **patch}


# ───────────────────────── Performance & Payroll ─────────────────────────

@router.get("/staffing/performance")
async def performance_summary(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Managers-only cross-staff analytics. Links staff → classes and
    revenue where possible (uses memberships_classes + bookings)."""
    _require_manager(user)
    org_id = _org(user)
    # Default to last 30 days.
    dt_to = datetime.fromisoformat(date_to) if date_to else _now()
    dt_from = datetime.fromisoformat(date_from) if date_from else (dt_to - timedelta(days=30))
    staff = await db.staff_members.find({"organization_id": org_id, "active": True}, {"_id": 0}).to_list(1000)
    if not staff:
        return {"window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()}, "staff": []}

    staff_ids = [s["id"] for s in staff]
    user_ids = [s.get("user_id") for s in staff if s.get("user_id")]
    names = [s.get("full_name") for s in staff if s.get("full_name")]

    # Batch — one query per collection instead of 3 per staff.
    # Iter 216h170 — was 3*N round-trips, now 3 total.
    shifts_q = {
        "organization_id": org_id,
        "staff_id": {"$in": staff_ids},
        "date": {"$gte": dt_from.date().isoformat(), "$lte": dt_to.date().isoformat()},
    }
    shifts = await db.staff_shifts.find(
        shifts_q,
        {"_id": 0, "staff_id": 1, "start_time": 1, "end_time": 1, "break_minutes": 1},
    ).to_list(50_000)
    shifts_by_staff: dict = {}
    for sh in shifts:
        shifts_by_staff.setdefault(sh["staff_id"], []).append(sh)

    # Aggregated counts for classes + attendees by instructor.
    classes_by_user_id: dict = {}
    classes_by_name: dict = {}
    attendees_by_name: dict = {}
    try:
        # Classes by instructor_id
        cur = db.memberships_classes.aggregate([
            {"$match": {"organization_id": org_id, "instructor_id": {"$in": user_ids}}},
            {"$group": {"_id": "$instructor_id", "n": {"$sum": 1}}},
        ])
        classes_by_user_id = {r["_id"]: r["n"] async for r in cur}
        # Classes by instructor_name (covers staff without user_id link)
        cur2 = db.memberships_classes.aggregate([
            {"$match": {"organization_id": org_id, "instructor_name": {"$in": names}}},
            {"$group": {"_id": "$instructor_name", "n": {"$sum": 1}}},
        ])
        classes_by_name = {r["_id"]: r["n"] async for r in cur2}
        # Attended bookings by instructor_name
        cur3 = db.memberships_bookings.aggregate([
            {"$match": {
                "organization_id": org_id,
                "instructor_name": {"$in": names},
                "status": "attended",
            }},
            {"$group": {"_id": "$instructor_name", "n": {"$sum": 1}}},
        ])
        attendees_by_name = {r["_id"]: r["n"] async for r in cur3}
    except Exception:
        # Collections may not exist on fresh orgs — keep empty defaults.
        pass

    summary = []
    for s in staff:
        sid = s["id"]
        linked_name = s.get("full_name")
        hours = sum(_shift_hours(x) for x in shifts_by_staff.get(sid, []))
        classes_count = (
            classes_by_user_id.get(s.get("user_id"), 0)
            + classes_by_name.get(linked_name, 0)
        )
        attendance_count = attendees_by_name.get(linked_name, 0)
        summary.append({
            "staff_id": sid,
            "full_name": linked_name,
            "primary_role": s.get("primary_role"),
            "hours_scheduled": round(hours, 2),
            "labour_cost": round(hours * float(s.get("hourly_cost") or 0.0), 2),
            "classes_delivered": classes_count,
            "attendees": attendance_count,
        })
    summary.sort(key=lambda x: x["hours_scheduled"], reverse=True)
    return {"window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()}, "staff": summary}


@router.get("/staffing/payroll/export")
async def payroll_csv(
    date_from: str,
    date_to: str,
    user: dict = Depends(get_current_user),
):
    """Managers export CSV of hours + labour cost per staff for a date
    window. Ready to import into Sage or any common payroll tool."""
    _require_manager(user)
    org_id = _org(user)
    shifts = await db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": date_from, "$lte": date_to}, "status": {"$ne": "cancelled"}},
        {"_id": 0},
    ).to_list(50_000)
    staff = {s["id"]: s async for s in db.staff_members.find({"organization_id": org_id}, {"_id": 0})}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Staff ID", "Name", "Role", "Hours", "Hourly Cost", "Total Cost"])
    totals: dict[str, dict] = {}
    for sh in shifts:
        sid = sh.get("staff_id") or ""
        s = staff.get(sid) or {}
        hrs = _shift_hours(sh)
        t = totals.setdefault(sid, {"name": s.get("full_name") or "OPEN SHIFT", "role": s.get("primary_role") or "", "hours": 0.0, "rate": float(s.get("hourly_cost") or 0)})
        t["hours"] += hrs
    for sid, t in totals.items():
        w.writerow([sid, t["name"], t["role"], round(t["hours"], 2), t["rate"], round(t["hours"] * t["rate"], 2)])
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payroll-{date_from}-to-{date_to}.csv"},
    )


# ───────────────────────── Live Gym Floor view ─────────────────────────

@router.get("/staffing/live-floor")
async def live_floor(site_id: str | None = Query(None), user: dict = Depends(get_current_user)):
    """Who's scheduled right now, per site. Available to everyone in the
    org so gym floor staff can see their own crew."""
    org_id = _org(user)
    now = _now()
    today = now.date().isoformat()
    now_hm = now.strftime("%H:%M")
    q = {"organization_id": org_id, "date": today, "status": {"$ne": "cancelled"}}
    if site_id:
        q["site_id"] = site_id
    shifts = await db.staff_shifts.find(q, {"_id": 0}).to_list(500)
    staff = {s["id"]: s async for s in db.staff_members.find({"organization_id": org_id, "active": True}, {"_id": 0})}
    on_now, upcoming, finished = [], [], []
    for sh in shifts:
        sid = sh.get("staff_id")
        nm = staff.get(sid or "", {}).get("full_name") or ("OPEN" if sh.get("status") == "open" else "—")
        sh_out = {**sh, "staff_name": nm}
        if sh["start_time"] <= now_hm <= sh["end_time"]:
            on_now.append(sh_out)
        elif sh["start_time"] > now_hm:
            upcoming.append(sh_out)
        else:
            finished.append(sh_out)
    on_now.sort(key=lambda x: x.get("start_time", ""))
    upcoming.sort(key=lambda x: x.get("start_time", ""))
    coverage = {"on_now": len(on_now), "open_shifts_today": sum(1 for sh in shifts if sh.get("status") == "open")}
    return {"as_of": now.isoformat(), "on_now": on_now, "upcoming": upcoming, "finished": finished, "coverage": coverage}


# ───────────────────────── Compliance rules ─────────────────────────

DEFAULT_RULES = {
    "max_hours_per_week": 48.0,            # UK WTD default
    "min_rest_hours_between_shifts": 11.0, # UK WTD daily rest
    "min_break_minutes_per_shift": 20.0,   # UK WTD when shift > 6h
    "max_days_consecutive": 6,
    "require_manager_approval_for_overtime": True,
}


@router.get("/staffing/rules")
async def get_rules(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return {**DEFAULT_RULES, **doc}


@router.put("/staffing/rules")
async def put_rules(body: RulesUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    patch["organization_id"] = org_id
    patch["updated_at"] = _now().isoformat()
    patch["updated_by"] = user.get("email")
    await db.staff_rules.update_one({"organization_id": org_id}, {"$set": patch}, upsert=True)
    doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return {**DEFAULT_RULES, **doc}


async def _check_compliance(org_id: str, shift: dict) -> list[str]:
    """Fast heuristic checks against the org rules. Runs on shift
    create/update and returns warning strings (does not block)."""
    warnings: list[str] = []
    rules_doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    rules = {**DEFAULT_RULES, **rules_doc}
    hrs = _shift_hours(shift)
    if hrs > 12:
        warnings.append(f"Shift is {hrs:.1f}h — unusually long.")
    if rules.get("min_break_minutes_per_shift") and hrs > 6 and int(shift.get("break_minutes") or 0) < rules["min_break_minutes_per_shift"]:
        warnings.append(f"Shift >6h should include at least {int(rules['min_break_minutes_per_shift'])} min break.")
    # Weekly hours check — uses existing shifts for the same staff this week.
    if shift.get("staff_id"):
        try:
            d = datetime.fromisoformat(shift["date"]).date()
            week_start = (d - timedelta(days=d.weekday())).isoformat()
            week_end = (d - timedelta(days=d.weekday()) + timedelta(days=7)).isoformat()
            same = await db.staff_shifts.find(
                {"organization_id": org_id, "staff_id": shift["staff_id"], "date": {"$gte": week_start, "$lt": week_end}, "status": {"$ne": "cancelled"}},
                {"_id": 0, "start_time": 1, "end_time": 1, "break_minutes": 1, "id": 1},
            ).to_list(200)
            total = sum(_shift_hours(x) for x in same if x["id"] != shift.get("id"))
            total += hrs
            if rules.get("max_hours_per_week") and total > rules["max_hours_per_week"]:
                warnings.append(f"Weekly total {total:.1f}h exceeds rule {rules['max_hours_per_week']:.0f}h.")
        except Exception:  # defensive — don't fail the request over a warning
            pass
    return warnings


# ───────────────────────── Announcements ─────────────────────────

@router.get("/staffing/announcements")
async def list_announcements(user: dict = Depends(get_current_user)):
    org_id = _org(user)
    rows = await db.staff_announcements.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {"announcements": rows}


@router.post("/staffing/announcements")
async def create_announcement(body: AnnouncementCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        "author_name": user.get("full_name") or user.get("email"),
        **body.dict(),
    }
    await db.staff_announcements.insert_one(doc.copy())
    return _clean(doc)


@router.delete("/staffing/announcements/{ann_id}")
async def delete_announcement(ann_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_announcements.delete_one({"id": ann_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "announcement not found")
    return {"ok": True}


# ───────────────────────── AI Workforce Optimisation ─────────────────────────

@router.get("/staffing/ai/insights")
async def ai_insights(user: dict = Depends(get_current_user)):
    """Managers only. Fast heuristic + optional Claude narrative.

    Heuristic: bucket last-30-days class attendance by weekday+hour.
    Match against scheduled shifts. Flag over/under staffed slots.
    """
    _require_manager(user)
    org_id = _org(user)
    dt_to = _now()
    dt_from = dt_to - timedelta(days=30)
    # Bucket actual demand from bookings.
    demand: dict[tuple[int, int], int] = {}
    try:
        bookings = await db.memberships_bookings.find(
            {"organization_id": org_id, "status": "attended", "class_date": {"$gte": dt_from.date().isoformat()}},
            {"_id": 0, "class_date": 1, "class_time": 1},
        ).to_list(20_000)
        for b in bookings:
            try:
                d = datetime.fromisoformat(b["class_date"]).date()
                hr = int((b.get("class_time") or "00:00").split(":")[0])
                demand[(d.weekday(), hr)] = demand.get((d.weekday(), hr), 0) + 1
            except Exception:
                continue
    except Exception:
        demand = {}
    # Bucket supply from shifts.
    supply: dict[tuple[int, int], int] = {}
    shifts = await db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": dt_from.date().isoformat()}, "status": {"$in": ["scheduled", "confirmed", "completed"]}},
        {"_id": 0, "date": 1, "start_time": 1, "end_time": 1},
    ).to_list(50_000)
    for sh in shifts:
        try:
            d = datetime.fromisoformat(sh["date"]).date()
            sh_start = int(sh["start_time"].split(":")[0])
            sh_end = int(sh["end_time"].split(":")[0])
            for h in range(sh_start, max(sh_start + 1, sh_end)):
                supply[(d.weekday(), h)] = supply.get((d.weekday(), h), 0) + 1
        except Exception:
            continue
    # Score slots. Threshold = 10 attendees per staff as a rough "good" ratio.
    flags = []
    for (wd, hr), attendees in demand.items():
        staff_on = supply.get((wd, hr), 0)
        ratio = attendees / max(1, staff_on)
        if staff_on == 0 and attendees >= 3 or ratio > 15:
            flags.append({"weekday": wd, "hour": hr, "kind": "understaffed", "demand": attendees, "supply": staff_on, "ratio": ratio})
    # Overstaffed: supply but zero demand in last 30 days.
    for (wd, hr), staff_on in supply.items():
        if staff_on >= 3 and demand.get((wd, hr), 0) == 0:
            flags.append({"weekday": wd, "hour": hr, "kind": "overstaffed", "demand": 0, "supply": staff_on, "ratio": 0})
    flags.sort(key=lambda f: (-f["ratio"] if f["kind"] == "understaffed" else f["supply"]))
    flags = flags[:10]

    # Optional Claude narrative — falls back to plain summary if no key.
    narrative = ""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if api_key and flags:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
            wd_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            flags_text = "\n".join(f"- {wd_names[f['weekday']]} {f['hour']:02d}:00 → {f['kind']} (demand={f['demand']}, supply={f['supply']})" for f in flags)
            chat = LlmChat(
                api_key=api_key,
                session_id=f"staffing-ai-{org_id}",
                system_message=(
                    "You are a gym workforce optimisation consultant. Given the flagged time "
                    "slots, write a 3-sentence, UK-English, plain-text summary of the top "
                    "staffing opportunities. No bullet points. Focus on cost savings and "
                    "member-experience risk. Do not invent numbers."
                ),
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            resp = await chat.send_message(UserMessage(text=f"Here are the flagged slots:\n{flags_text}"))
            narrative = (resp or "").strip()
        except Exception as exc:
            logger.info("[staffing] ai narrative failed: %s", exc)
            narrative = ""

    if not narrative:
        narrative = f"Flagged {len(flags)} staffing imbalances over the last 30 days — review understaffed peaks first to protect member experience, then rebalance overstaffed slots for cost savings."
    return {"flags": flags, "narrative": narrative}


# ═════════════════════════════════════════════════════════════════
# PHASE S1 — Rota engine upgrade + Workforce Dashboard
# ═════════════════════════════════════════════════════════════════
#
# Extends the existing staffing surface with four operator multipliers
# requested in the Dec 2026 workforce overhaul:
#
#   1. Shift templates — reusable slot definitions that managers can
#      "stamp" across a date range to build a week/month rota in one
#      click (instead of adding 40 shifts by hand).
#   2. Drag/drop reassign — a focused `/move` endpoint that re-parents
#      a shift to a new staff + date in one write so the optimistic UI
#      stays snappy.
#   3. Conflict detection — a bulk `/conflicts` endpoint that returns
#      every warning across a date range in one round-trip, so the
#      frontend can render red borders without firing one request per
#      shift.
#   4. Workforce Dashboard — a single, pre-aggregated endpoint feeding
#      the Control Centre tab: live on-now / late / absent counters,
#      today's coverage, week labour cost, open-shift backlog, a 7×24
#      coverage heatmap, and compliance hot-spots.
#
# All endpoints respect the same org_id scoping + role gating already
# baked into the legacy routes. Nothing above this line was modified
# — the Phase S1 layer is purely additive.


# ── Shift templates ────────────────────────────────────────────────

class ShiftTemplateCreate(BaseModel):
    name: str
    role: str = "reception"
    default_staff_id: str | None = None
    site_id: str | None = None
    start_time: str                        # HH:MM
    end_time: str                          # HH:MM
    break_minutes: int = 0
    colour: str | None = None              # #hex — rota tile tint
    weekdays: list[int] = Field(default_factory=list)  # 0=Mon … 6=Sun
    notes: str | None = None


class ShiftTemplateUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    default_staff_id: str | None = None
    site_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    break_minutes: int | None = None
    colour: str | None = None
    weekdays: list[int] | None = None
    notes: str | None = None
    archived: bool | None = None


@router.get("/staffing/shift-templates")
async def list_shift_templates(user: dict = Depends(get_current_user)):
    """Managers see every template in the org; staff see the ones they
    personally appear on as `default_staff_id` (read-only)."""
    org_id = _org(user)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if not _is_manager(user):
        sid = await _my_staff_id_async(user, org_id)
        q["default_staff_id"] = sid or "__none__"
    rows = await db.staff_shift_templates.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    return {"templates": rows, "role": _role(user)}


@router.post("/staffing/shift-templates")
async def create_shift_template(
    body: ShiftTemplateCreate, user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"role must be one of {sorted(VALID_ROLES)}")
    if not body.weekdays or not all(0 <= d <= 6 for d in body.weekdays):
        raise HTTPException(400, "weekdays must be a non-empty list of 0..6")
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "created_at": _now().isoformat(),
        "created_by": user.get("email"),
        "archived": False,
        **body.dict(),
    }
    await db.staff_shift_templates.insert_one(doc.copy())
    return _clean(doc)


@router.patch("/staffing/shift-templates/{tpl_id}")
async def update_shift_template(
    tpl_id: str,
    body: ShiftTemplateUpdate,
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "role" in patch and patch["role"] not in VALID_ROLES:
        raise HTTPException(400, "invalid role")
    if "weekdays" in patch:
        wd = patch["weekdays"] or []
        if not all(0 <= d <= 6 for d in wd):
            raise HTTPException(400, "weekdays must be 0..6")
    patch["updated_at"] = _now().isoformat()
    res = await db.staff_shift_templates.update_one(
        {"id": tpl_id, "organization_id": org_id},
        {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "template not found")
    doc = await db.staff_shift_templates.find_one({"id": tpl_id}, {"_id": 0})
    return doc


@router.delete("/staffing/shift-templates/{tpl_id}")
async def delete_shift_template(tpl_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.staff_shift_templates.update_one(
        {"id": tpl_id, "organization_id": org_id},
        {"$set": {"archived": True, "archived_at": _now().isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "template not found")
    return {"ok": True}


@router.post("/staffing/shift-templates/{tpl_id}/apply")
async def apply_shift_template(
    tpl_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Materialise a template across a date range. Body:
      {start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD",
       staff_id?: "<override>", skip_existing?: true}

    Creates one shift per weekday-matching date in the range. Returns
    {created, skipped, created_ids} so the UI can show a concise toast.
    Respects the template's `default_staff_id` unless an override is
    supplied; when neither is set, the generated shifts are created
    open (unassigned) so managers can claim or publish them later.
    """
    _require_manager(user)
    org_id = _org(user)
    tpl = await db.staff_shift_templates.find_one(
        {"id": tpl_id, "organization_id": org_id}, {"_id": 0},
    )
    if not tpl:
        raise HTTPException(404, "template not found")
    start_raw = body.get("start_date")
    end_raw = body.get("end_date")
    if not start_raw or not end_raw:
        raise HTTPException(400, "start_date and end_date are required")
    try:
        start_d = datetime.fromisoformat(start_raw).date()
        end_d = datetime.fromisoformat(end_raw).date()
    except ValueError as err:
        raise HTTPException(400, "dates must be YYYY-MM-DD") from err
    if end_d < start_d:
        raise HTTPException(400, "end_date must be ≥ start_date")
    if (end_d - start_d).days > 90:
        raise HTTPException(400, "Max 90-day apply window")

    staff_id = body.get("staff_id") or tpl.get("default_staff_id")
    skip_existing = bool(body.get("skip_existing", True))
    weekdays = set(int(d) for d in (tpl.get("weekdays") or []))

    created = 0
    skipped = 0
    created_ids: list[str] = []
    cur = start_d
    one = timedelta(days=1)
    while cur <= end_d:
        if cur.weekday() in weekdays:
            date_iso = cur.isoformat()
            if skip_existing and staff_id:
                exists = await db.staff_shifts.find_one(
                    {
                        "organization_id": org_id,
                        "staff_id": staff_id,
                        "date": date_iso,
                        "start_time": tpl["start_time"],
                        "status": {"$ne": "cancelled"},
                    },
                    {"_id": 0, "id": 1},
                )
                if exists:
                    skipped += 1
                    cur += one
                    continue
            sid = str(uuid4())
            doc = {
                "id": sid,
                "organization_id": org_id,
                "created_at": _now().isoformat(),
                "created_by": user.get("email"),
                "staff_id": staff_id,
                "site_id": tpl.get("site_id"),
                "date": date_iso,
                "start_time": tpl["start_time"],
                "end_time": tpl["end_time"],
                "role": tpl.get("role") or "reception",
                "break_minutes": int(tpl.get("break_minutes") or 0),
                "status": "scheduled" if staff_id else "open",
                "notes": tpl.get("notes"),
                "template_id": tpl_id,
            }
            await db.staff_shifts.insert_one(doc.copy())
            created += 1
            created_ids.append(sid)
        cur += one
    return {
        "created": created,
        "skipped": skipped,
        "created_ids": created_ids,
        "template_id": tpl_id,
    }


# ── Drag/drop move ────────────────────────────────────────────────

@router.post("/staffing/shifts/{shift_id}/move")
async def move_shift(
    shift_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Re-parent a shift to a new staff + date in one write. Used by
    the drag-drop rota grid so an optimistic UI only needs one round-
    trip instead of a full PATCH with every field."""
    _require_manager(user)
    org_id = _org(user)
    patch: dict = {"updated_at": _now().isoformat()}
    if "staff_id" in body:
        new_sid = body.get("staff_id") or None
        patch["staff_id"] = new_sid
        # Flip to open/scheduled consistent with the new assignment.
        patch["status"] = "open" if not new_sid else "scheduled"
    if "date" in body:
        if not body.get("date"):
            raise HTTPException(400, "date cannot be blank")
        patch["date"] = body["date"]
    if not patch or set(patch.keys()) == {"updated_at"}:
        raise HTTPException(400, "nothing to move — send staff_id and/or date")
    res = await db.staff_shifts.update_one(
        {"id": shift_id, "organization_id": org_id},
        {"$set": patch},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "shift not found")
    doc = await db.staff_shifts.find_one({"id": shift_id}, {"_id": 0})
    warnings = await _check_compliance(org_id, doc) if doc else []
    return {"shift": doc, "warnings": warnings}


# ── Conflict detection (bulk) ─────────────────────────────────────

async def _conflicts_for_range(org_id: str, start: str, end: str) -> list[dict]:
    """Scan all shifts in [start, end] and return overlap/rest-gap/
    weekly-max warnings as a flat list of {shift_id, staff_id, reason,
    severity} records. Used by the rota grid AND the dashboard."""
    shifts = await db.staff_shifts.find(
        {
            "organization_id": org_id,
            "date": {"$gte": start, "$lte": end},
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0},
    ).sort([("staff_id", 1), ("date", 1), ("start_time", 1)]).to_list(5000)
    rules_doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    rules = {**DEFAULT_RULES, **rules_doc}
    findings: list[dict] = []
    by_staff: dict[str, list[dict]] = {}
    for sh in shifts:
        sid = sh.get("staff_id")
        if not sid:
            continue
        by_staff.setdefault(sid, []).append(sh)
    for sid, rows in by_staff.items():
        rows.sort(key=lambda x: (x.get("date", ""), x.get("start_time", "")))
        # Overlap + rest-gap
        for i, cur in enumerate(rows):
            for j in range(i + 1, len(rows)):
                nxt = rows[j]
                if cur["date"] != nxt["date"]:
                    # Rest-gap check across midnight
                    try:
                        cur_end = datetime.fromisoformat(f"{cur['date']}T{cur['end_time']}:00+00:00")
                        nxt_start = datetime.fromisoformat(f"{nxt['date']}T{nxt['start_time']}:00+00:00")
                        gap_h = (nxt_start - cur_end).total_seconds() / 3600.0
                        min_rest = float(rules.get("min_rest_hours_between_shifts") or 0)
                        if 0 < gap_h < min_rest:
                            findings.append({
                                "shift_id": nxt["id"],
                                "staff_id": sid,
                                "severity": "warning",
                                "reason": f"Only {gap_h:.1f}h rest since previous shift (min {min_rest:.0f}h).",
                            })
                    except Exception:
                        pass
                    break  # next shift is on a different day — stop overlap scan
                # Same-date overlap
                if cur["end_time"] > nxt["start_time"]:
                    findings.append({
                        "shift_id": nxt["id"],
                        "staff_id": sid,
                        "severity": "error",
                        "reason": f"Overlaps shift {cur['start_time']}–{cur['end_time']}.",
                    })
        # Weekly max
        by_week: dict[str, float] = {}
        for sh in rows:
            try:
                d = datetime.fromisoformat(sh["date"]).date()
                wk = (d - timedelta(days=d.weekday())).isoformat()
                by_week[wk] = by_week.get(wk, 0.0) + _shift_hours(sh)
            except Exception:
                pass
        max_h = float(rules.get("max_hours_per_week") or 0)
        if max_h:
            for wk, total in by_week.items():
                if total > max_h:
                    # Attach to the last shift in that week
                    last = next(
                        (sh for sh in reversed(rows)
                         if sh.get("date", "").startswith(wk[:7]) and wk <= sh["date"] < (
                             datetime.fromisoformat(wk).date() + timedelta(days=7)
                         ).isoformat()),
                        None,
                    )
                    if last:
                        findings.append({
                            "shift_id": last["id"],
                            "staff_id": sid,
                            "severity": "warning",
                            "reason": f"Week of {wk}: {total:.1f}h exceeds {max_h:.0f}h cap.",
                        })
    return findings


@router.get("/staffing/conflicts")
async def conflicts(
    start_date: str = Query(...),
    end_date: str = Query(...),
    user: dict = Depends(get_current_user),
):
    _require_manager(user)
    org_id = _org(user)
    findings = await _conflicts_for_range(org_id, start_date, end_date)
    return {"conflicts": findings, "count": len(findings)}


# ── Workforce Dashboard ───────────────────────────────────────────

@router.get("/staffing/workforce-dashboard")
async def workforce_dashboard(user: dict = Depends(get_current_user)):
    """One pre-aggregated payload for the Control Centre tab.

    Returns:
      kpis             — on_now, late, absent, open_today, coverage_pct
      week             — labour_cost, hours, overtime_hours, avg_hourly
      heatmap          — 7×24 grid of staff-on-duty counts (Mon→Sun)
      open_shifts      — up to 20 unassigned shifts, next 14 days
      compliance       — top 10 active conflicts
      on_now           — live on-shift roster
      upcoming         — next-to-start today (sorted)
    Everything scoped to the operator's org.
    """
    _require_manager(user)
    org_id = _org(user)
    now = _now()
    today = now.date().isoformat()
    now_hm = now.strftime("%H:%M")

    # Week window (Monday → Sunday, inclusive)
    wk_start = (now.date() - timedelta(days=now.weekday())).isoformat()
    wk_end = (now.date() - timedelta(days=now.weekday()) + timedelta(days=6)).isoformat()

    active_staff = await db.staff_members.count_documents(
        {"organization_id": org_id, "active": True},
    )

    # Load all shifts for this week in one go; we'll slice for each KPI.
    week_shifts = await db.staff_shifts.find(
        {
            "organization_id": org_id,
            "date": {"$gte": wk_start, "$lte": wk_end},
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0},
    ).to_list(5000)

    staff_docs = {s["id"]: s async for s in db.staff_members.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "full_name": 1, "hourly_cost": 1, "primary_role": 1},
    )}

    # Live state
    on_now: list[dict] = []
    upcoming: list[dict] = []
    late_count = 0
    absent_count = 0
    today_shifts_total = 0
    open_today = 0
    for sh in week_shifts:
        if sh.get("date") != today:
            continue
        today_shifts_total += 1
        if sh.get("status") == "open":
            open_today += 1
            continue
        sid = sh.get("staff_id")
        s = staff_docs.get(sid or "", {})
        nm = s.get("full_name") or "—"
        row = {
            **sh,
            "staff_name": nm,
            "primary_role": s.get("primary_role"),
            "hours": _shift_hours(sh),
        }
        if sh["start_time"] <= now_hm <= sh["end_time"]:
            on_now.append(row)
            # "Late" heuristic — scheduled start was >10 min ago and
            # no clock-in recorded. (Time-clock lands in Phase S2;
            # until then, this is a soft count based on the schedule.)
            try:
                sh_start = datetime.fromisoformat(f"{sh['date']}T{sh['start_time']}:00+00:00")
                if (now - sh_start).total_seconds() / 60.0 > 10 and not sh.get("clocked_in_at"):
                    late_count += 1
            except Exception:
                pass
        elif sh["start_time"] > now_hm:
            upcoming.append(row)
        else:
            # Shift ended without any attendance capture → soft absent.
            if not sh.get("clocked_in_at") and sh.get("status") == "scheduled":
                absent_count += 1

    on_now.sort(key=lambda x: x.get("start_time", ""))
    upcoming.sort(key=lambda x: x.get("start_time", ""))

    # Week labour totals (manager view — never NULL)
    week_hours = 0.0
    week_cost = 0.0
    overtime_hours = 0.0
    rules_doc = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    max_weekly = float({**DEFAULT_RULES, **rules_doc}.get("max_hours_per_week") or 0)
    by_staff_hours: dict[str, float] = {}
    for sh in week_shifts:
        h = _shift_hours(sh)
        week_hours += h
        rate = float(staff_docs.get(sh.get("staff_id") or "", {}).get("hourly_cost") or 0)
        week_cost += h * rate
        if sh.get("staff_id"):
            by_staff_hours[sh["staff_id"]] = by_staff_hours.get(sh["staff_id"], 0.0) + h
    if max_weekly:
        for _sid, total in by_staff_hours.items():
            if total > max_weekly:
                overtime_hours += total - max_weekly

    avg_hourly = round(week_cost / week_hours, 2) if week_hours else 0.0

    # Heatmap — 7 rows (Mon→Sun) × 24 cols (0..23h) of staff-on-duty counts.
    # Each covered hour adds 1 per staff member. Partial hours count 0.5
    # where the shift only touches the bucket for part of an hour.
    heatmap = [[0.0] * 24 for _ in range(7)]
    for sh in week_shifts:
        if sh.get("status") == "open":
            continue
        try:
            d = datetime.fromisoformat(sh["date"]).date()
            row = d.weekday()
            sh_h, sm = [int(x) for x in sh["start_time"].split(":")]
            eh_h, em = [int(x) for x in sh["end_time"].split(":")]
            start_m = sh_h * 60 + sm
            end_m = eh_h * 60 + em
            for h in range(24):
                h_start = h * 60
                h_end = h_start + 60
                overlap = max(0, min(end_m, h_end) - max(start_m, h_start))
                if overlap > 0:
                    heatmap[row][h] += round(overlap / 60.0, 2)
        except Exception:
            pass
    # Round for JSON cleanliness
    heatmap = [[round(v, 1) for v in row] for row in heatmap]
    peak = max((max(row) for row in heatmap), default=0)

    # Open shifts (next 14 days)
    horizon = (now.date() + timedelta(days=14)).isoformat()
    open_shifts = await db.staff_shifts.find(
        {
            "organization_id": org_id,
            "status": "open",
            "date": {"$gte": today, "$lte": horizon},
        },
        {"_id": 0},
    ).sort([("date", 1), ("start_time", 1)]).limit(20).to_list(20)

    # Compliance: this week's conflicts, top 10
    conflicts_list = await _conflicts_for_range(org_id, wk_start, wk_end)
    # Decorate with staff name + shift info for the UI
    shift_by_id = {sh["id"]: sh for sh in week_shifts}
    top_conflicts: list[dict] = []
    for c in conflicts_list[:10]:
        sh = shift_by_id.get(c.get("shift_id")) or {}
        top_conflicts.append({
            **c,
            "staff_name": staff_docs.get(c.get("staff_id") or "", {}).get("full_name"),
            "date": sh.get("date"),
            "start_time": sh.get("start_time"),
            "end_time": sh.get("end_time"),
        })

    coverage_pct = 0
    if today_shifts_total > 0:
        filled = today_shifts_total - open_today
        coverage_pct = int(round((filled / today_shifts_total) * 100))
    else:
        coverage_pct = 100  # nothing scheduled → no gap

    return {
        "as_of": now.isoformat(),
        "week_start": wk_start,
        "week_end": wk_end,
        "kpis": {
            "active_staff": active_staff,
            "on_now": len(on_now),
            "late": late_count,
            "absent": absent_count,
            "open_today": open_today,
            "coverage_pct": coverage_pct,
        },
        "week": {
            "hours": round(week_hours, 1),
            "labour_cost": round(week_cost, 2),
            "overtime_hours": round(overtime_hours, 1),
            "avg_hourly": avg_hourly,
        },
        "heatmap": {"grid": heatmap, "peak": peak},
        "on_now": on_now,
        "upcoming": upcoming[:12],
        "open_shifts": open_shifts,
        "compliance": {"count": len(conflicts_list), "top": top_conflicts},
    }



# ╔════════════════════════════════════════════════════════════════╗
# ║  Iter 216h243 — Custom staff roles                             ║
# ║                                                                ║
# ║  Org-scoped extensions to the platform default ``VALID_ROLES`` ║
# ║  set. Backed by ``organizations.custom_staff_roles[]``.        ║
# ╚════════════════════════════════════════════════════════════════╝

@router.get("/staffing/roles")
async def list_staff_roles(user: dict = Depends(get_current_user)):
    """Return the org's job-role catalogue.

    Iter 279c — ``platform_defaults`` is now the neutral, business-wide set
    (Manager, Engineer, Technician, Sales Manager…) rather than the old
    gym-only list. ``all`` is the catalogue the dropdowns should show:
    business defaults + the org's custom roles (legacy gym roles stay
    *valid* for back-compat but are no longer suggested). Frontends append
    a staff member's current role if it isn't already in the list.
    """
    org_id = _org(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "custom_staff_roles": 1})
    custom = sorted({r.strip() for r in ((org or {}).get("custom_staff_roles") or [])
                     if isinstance(r, str) and r.strip()})
    catalogue = [*BUSINESS_DEFAULT_ROLES, *[c for c in custom if c.lower() not in
                 {d.lower() for d in BUSINESS_DEFAULT_ROLES}]]
    return {
        "platform_defaults": list(BUSINESS_DEFAULT_ROLES),
        "custom": custom,
        "all": catalogue,
        # Full validation set (incl. legacy) — exposed for completeness.
        "valid": sorted(await _allowed_roles_for(org_id)),
    }


class StaffRoleAdd(BaseModel):
    role: str


@router.post("/staffing/roles")
async def add_staff_role(body: StaffRoleAdd, user: dict = Depends(get_current_user)):
    """Add a custom staff role to the current org.

    Manager / admin only. Normalises whitespace and rejects duplicates
    of platform defaults (case-insensitive).
    """
    _require_manager(user)
    org_id = _org(user)
    if not org_id:
        raise HTTPException(400, "organization scope required")
    name = (body.role or "").strip()
    if not name:
        raise HTTPException(400, "role name required")
    if len(name) > 60:
        raise HTTPException(400, "role name too long (max 60)")
    # Reject collision with platform defaults (case-insensitive).
    if name.lower() in {r.lower() for r in VALID_ROLES}:
        raise HTTPException(409, f"'{name}' is already a platform default")
    # Read current list, dedupe, persist.
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "custom_staff_roles": 1})
    existing = (org or {}).get("custom_staff_roles") or []
    if any((r or "").lower() == name.lower() for r in existing):
        raise HTTPException(409, f"'{name}' already exists")
    new_list = [*existing, name]
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"custom_staff_roles": new_list, "updated_at": _now().isoformat()}},
    )
    return {"role": name, "custom": sorted(set(new_list))}


@router.delete("/staffing/roles/{role}")
async def delete_staff_role(role: str, user: dict = Depends(get_current_user)):
    """Remove a custom staff role. Platform defaults can't be removed.

    Note: existing ``staff_members`` rows that carry the deleted role
    are left untouched — they keep the historical label so payroll and
    HR records stay correct. Only the dropdown stops offering it.
    """
    _require_manager(user)
    org_id = _org(user)
    if role.lower() in {r.lower() for r in VALID_ROLES}:
        raise HTTPException(400, "cannot delete a platform default role")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "custom_staff_roles": 1})
    existing = (org or {}).get("custom_staff_roles") or []
    new_list = [r for r in existing if (r or "").lower() != role.lower()]
    if len(new_list) == len(existing):
        raise HTTPException(404, "role not found")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"custom_staff_roles": new_list, "updated_at": _now().isoformat()}},
    )
    return {"removed": role, "custom": sorted(set(new_list))}



class StaffRoleRename(BaseModel):
    new_name: str


@router.put("/staffing/roles/{role}")
async def rename_staff_role(role: str, body: StaffRoleRename, user: dict = Depends(get_current_user)):
    """Rename a custom job role and migrate every staff member who carries
    it to the new label. Platform defaults can't be renamed.

    Manager / admin only. The new name must not collide with a platform
    default or another existing custom role (case-insensitive).
    """
    _require_manager(user)
    org_id = _org(user)
    if not org_id:
        raise HTTPException(400, "organization scope required")
    new_name = (body.new_name or "").strip()
    if not new_name:
        raise HTTPException(400, "new role name required")
    if len(new_name) > 60:
        raise HTTPException(400, "role name too long (max 60)")
    if role.lower() in {r.lower() for r in VALID_ROLES}:
        raise HTTPException(400, "cannot rename a platform default role")
    if new_name.lower() in {r.lower() for r in VALID_ROLES}:
        raise HTTPException(409, f"'{new_name}' is already a platform default")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "custom_staff_roles": 1})
    existing = (org or {}).get("custom_staff_roles") or []
    if not any((r or "").lower() == role.lower() for r in existing):
        raise HTTPException(404, "role not found")
    if any((r or "").lower() == new_name.lower() for r in existing if (r or "").lower() != role.lower()):
        raise HTTPException(409, f"'{new_name}' already exists")

    new_list = [new_name if (r or "").lower() == role.lower() else r for r in existing]
    now_iso = _now().isoformat()
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"custom_staff_roles": new_list, "updated_at": now_iso}},
    )
    # Migrate staff members carrying the old label so their role stays valid.
    await db.staff_members.update_many(
        {"organization_id": org_id, "primary_role": role},
        {"$set": {"primary_role": new_name, "updated_at": now_iso}},
    )
    return {"renamed": role, "to": new_name, "custom": sorted(set(new_list))}
