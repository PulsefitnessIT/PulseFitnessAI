"""
Gym Floor — site-generic login + Handover Diary.

Replaces the per-staff-account pattern for gym-floor shift staff with:

  1. ONE shared site credential (the "Gym Floor login") created by the Manager
     from Pulse Pro onboarding. Staff all share these creds.
  2. A managed staff roster — dropdown of names that gym-floor users pick when
     logging a handover entry, so every note is still attributable.
  3. Customisable topic taxonomy (seeded + manager-editable).
  4. Handover Diary — date/staff/topic/notes timeline visible to all
     gym-floor staff AND the manager. Moderation layer flags offensive or
     inappropriate content via keyword list + optional GPT-4o-mini review.

All endpoints mounted under /api/gym-floor.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gym-floor"])


# ─── Helpers ─────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(raw: str) -> str:
    # Lightweight credential hash — reuses the project's bcrypt helper if
    # available, otherwise a salted sha256. Gym-floor login is a shared
    # credential so we prioritise reliability over peak password security.
    try:
        import bcrypt
        return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    except Exception:
        salt = secrets.token_hex(8)
        return f"sha:{salt}:{hashlib.sha256((salt + raw).encode()).hexdigest()}"


def _verify(raw: str, hashed: str) -> bool:
    try:
        if hashed.startswith("sha:"):
            _, salt, digest = hashed.split(":", 2)
            return hashlib.sha256((salt + raw).encode()).hexdigest() == digest
        import bcrypt
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except Exception:
        return False


def _require_manager(user: dict) -> None:
    role = (user or {}).get("role") or ""
    at = (user or {}).get("account_type") or ""
    if role in ("master_admin", "master") or (user or {}).get("is_master_admin"):
        return
    if role == "owner" or role == "manager":
        return
    # Pulse Pro operators (full or pulse_pro) are managers for their own site
    if at in ("pulse_pro", "full") and role != "member":
        return
    # MOD PRO users (branch / organisation-wide) manage gym-floor across their scope
    if at in ("mod_branch", "mod_org"):
        return
    raise HTTPException(status_code=403, detail="Manager privileges required")


def _org_id_of(user: dict) -> Optional[str]:
    return user.get("organization_id") or user.get("org_id")


# ─── Default topic taxonomy ──────────────────────────────────────

DEFAULT_TOPICS = [
    {"id": "shift_handover",    "label": "Shift handover"},
    {"id": "cleaning",          "label": "Cleaning / housekeeping"},
    {"id": "equipment_issue",   "label": "Equipment issue"},
    {"id": "customer_incident", "label": "Customer incident"},
    {"id": "stock",             "label": "Stock / supplies"},
    {"id": "safety",            "label": "Safety / first aid"},
    {"id": "general",           "label": "General note"},
]

BAD_WORDS = {
    # Deliberately short list — the AI layer catches the rest. These are
    # stop-gap flags for the most common offensive English phrases.
    "fuck", "shit", "bitch", "bastard", "asshole", "cunt", "dickhead",
    "wanker", "retard", "nigger", "faggot", "whore", "slut",
    "stupid cow", "fat pig",
}


async def _moderate(text: str) -> dict:
    """Two-stage: fast keyword scan, then optional GPT-4o-mini review.
    Returns {flagged: bool, reason: str, severity: 'none|low|high'}."""
    t = (text or "").lower()
    for w in BAD_WORDS:
        if w in t:
            return {"flagged": True, "reason": "contains disallowed word", "severity": "high"}
    # AI layer — short, cheap, best-effort
    try:
        from utils.memberships_ai_insights import _chat
        prompt = (
            "You are a content moderator for a gym staff handover diary.\n"
            "Flag text that is offensive, discriminatory, harassing, overly aggressive, or shares "
            "confidential medical/personal member details that a colleague shouldn't post publicly.\n"
            "Respond STRICT JSON: {\"flagged\": bool, \"severity\": \"none|low|high\", \"reason\": \"short\"}\n"
            f"TEXT: {text[:500]}"
        )
        import json
        raw = await _chat(prompt, max_tokens=120)
        m = re.search(r"\{.*\}", raw or "", re.S)
        if m:
            data = json.loads(m.group(0))
            if data.get("flagged"):
                return {"flagged": True, "severity": data.get("severity") or "low", "reason": data.get("reason") or "flagged"}
    except Exception as exc:
        logger.info("AI moderation unavailable (non-fatal): %s", exc)
    return {"flagged": False, "severity": "none", "reason": ""}


# ═════════════════ Setup — Manager creates the shared login ═════════════════

class GymFloorSetup(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=6, max_length=120)
    staff_names: list[str] = Field(default_factory=list)


@router.post("/gym-floor/setup")
async def setup_gym_floor(body: GymFloorSetup, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    if not org_id:
        raise HTTPException(400, "No organization bound to this account")
    doc = {
        "id": org_id,
        "organization_id": org_id,
        "username": body.username.strip().lower(),
        "password_hash": _hash(body.password),
        "created_at": _now_iso(),
        "created_by": user.get("email"),
        "enabled": True,
    }
    await db.gym_floor_credentials.replace_one({"id": org_id}, doc, upsert=True)
    # Seed topics (idempotent)
    existing = await db.gym_floor_topics.count_documents({"organization_id": org_id})
    if existing == 0:
        await db.gym_floor_topics.insert_many([
            {**t, "organization_id": org_id, "_id_override": f"{org_id}:{t['id']}"} for t in DEFAULT_TOPICS
        ])
    # Seed staff roster
    for name in (body.staff_names or []):
        nm = name.strip()
        if not nm:
            continue
        await db.gym_floor_staff.update_one(
            {"organization_id": org_id, "name_lower": nm.lower()},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "name": nm,
                "name_lower": nm.lower(),
                "active": True,
                "created_at": _now_iso(),
            }},
            upsert=True,
        )
    return {"ok": True, "username": doc["username"]}


@router.get("/gym-floor/status")
async def gym_floor_status(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    if not org_id:
        return {"configured": False}
    cred = await db.gym_floor_credentials.find_one({"id": org_id}, {"_id": 0, "password_hash": 0})
    return {"configured": bool(cred), "credential": cred}


# ═════════════════ Shared-credential login ═════════════════

class GymFloorLogin(BaseModel):
    username: str
    password: str


@router.post("/gym-floor/login")
async def gym_floor_login(body: GymFloorLogin):
    cred = await db.gym_floor_credentials.find_one({"username": body.username.strip().lower()}, {"_id": 0})
    if not cred or not cred.get("enabled", True):
        raise HTTPException(401, "Invalid credentials")
    if not _verify(body.password, cred.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")
    # Session token — short-lived, stores org_id and a marker.
    token = f"gfloor-{secrets.token_urlsafe(24)}"
    await db.gym_floor_sessions.insert_one({
        "token": token,
        "organization_id": cred["organization_id"],
        "created_at": _now_iso(),
    })
    return {
        "token": token,
        "organization_id": cred["organization_id"],
    }


async def _resolve_gym_floor_session(x_gym_floor_token: Optional[str]) -> Optional[dict]:
    if not x_gym_floor_token:
        return None
    return await db.gym_floor_sessions.find_one({"token": x_gym_floor_token}, {"_id": 0})


# Combined auth dep — manager (via Bearer) OR gym-floor-token header.
async def _any_viewer(
    x_gym_floor_token: Optional[str] = Header(None, alias="X-Gym-Floor-Token"),
    authorization: Optional[str] = Header(None),
) -> dict:
    # Try the shared-session first
    s = await _resolve_gym_floor_session(x_gym_floor_token)
    if s:
        return {"organization_id": s["organization_id"], "_gym_floor_session": True}
    # Fall back to Bearer — delegate to get_current_user
    if authorization:
        try:
            from utils.auth import verify_token
            payload = verify_token(authorization.split(" ", 1)[1])
            if payload:
                u = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password_hash": 0})
                if u:
                    return u
        except Exception:
            pass
    raise HTTPException(401, "Not authenticated")


# ═════════════════ Staff roster ═════════════════

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    return v if EMAIL_RE.match(v) else None


def _normalise_mobile(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = re.sub(r"[\s\-().]", "", value.strip())
    if not v:
        return None
    # Accept E.164-ish or local digits, length 6-20
    if not re.match(r"^\+?\d{6,20}$", v):
        return None
    return v


class StaffIn(BaseModel):
    name: str
    email: Optional[str] = None
    mobile: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.get("/gym-floor/staff")
async def list_staff(viewer: dict = Depends(_any_viewer)):
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    rows = await db.gym_floor_staff.find(
        {"organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    # Hide email/mobile from the gym-floor session response — those are
    # confidential. Managers (Bearer auth) get the full record.
    if viewer.get("_gym_floor_session"):
        rows = [{k: v for k, v in r.items() if k not in ("email", "mobile")} for r in rows]
    return {"staff": rows}


@router.post("/gym-floor/staff")
async def add_staff(body: StaffIn, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    nm = body.name.strip()
    if not nm:
        raise HTTPException(400, "Name required")
    email = _normalise_email(body.email)
    if not email:
        raise HTTPException(400, "A valid email is required so suppliers can reach this staff member.")
    mobile = _normalise_mobile(body.mobile)  # optional

    # Insert if new, otherwise update the existing row (managers re-adding a name
    # to fill in contact details should not get a duplicate).
    existing = await db.gym_floor_staff.find_one(
        {"organization_id": org_id, "name_lower": nm.lower()}, {"_id": 0, "id": 1},
    )
    if existing:
        await db.gym_floor_staff.update_one(
            {"id": existing["id"]},
            {"$set": {
                "name": nm,
                "email": email,
                "mobile": mobile,
                "active": True,
                "updated_at": _now_iso(),
            }},
        )
    else:
        await db.gym_floor_staff.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "name": nm,
            "name_lower": nm.lower(),
            "email": email,
            "mobile": mobile,
            "active": True,
            "created_at": _now_iso(),
        })
    return {"ok": True}


@router.patch("/gym-floor/staff/{staff_id}")
async def update_staff(staff_id: str, body: StaffUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    update: dict = {}
    if body.name is not None:
        nm = body.name.strip()
        if not nm:
            raise HTTPException(400, "Name cannot be empty")
        update["name"] = nm
        update["name_lower"] = nm.lower()
    if body.email is not None:
        email = _normalise_email(body.email)
        if not email:
            raise HTTPException(400, "Invalid email")
        update["email"] = email
    if body.mobile is not None:
        # Allow clearing mobile by sending empty string
        if body.mobile.strip() == "":
            update["mobile"] = None
        else:
            mobile = _normalise_mobile(body.mobile)
            if not mobile:
                raise HTTPException(400, "Invalid mobile number")
            update["mobile"] = mobile
    if not update:
        return {"ok": True}
    update["updated_at"] = _now_iso()
    r = await db.gym_floor_staff.update_one(
        {"id": staff_id, "organization_id": org_id}, {"$set": update},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Staff member not found")
    return {"ok": True}


@router.delete("/gym-floor/staff/{staff_id}")
async def remove_staff(staff_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    await db.gym_floor_staff.update_one(
        {"id": staff_id, "organization_id": org_id},
        {"$set": {"active": False}},
    )
    return {"ok": True}


# ═════════════════ Topics ═════════════════

class TopicIn(BaseModel):
    label: str
    id: Optional[str] = None


@router.get("/gym-floor/topics")
async def list_topics(viewer: dict = Depends(_any_viewer)):
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    rows = await db.gym_floor_topics.find({"organization_id": org_id}, {"_id": 0, "_id_override": 0}).to_list(200)
    if not rows:
        rows = [{**t, "organization_id": org_id} for t in DEFAULT_TOPICS]
    return {"topics": rows}


@router.post("/gym-floor/topics")
async def add_topic(body: TopicIn, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    tid = (body.id or body.label).strip().lower().replace(" ", "_")[:40]
    await db.gym_floor_topics.update_one(
        {"organization_id": org_id, "id": tid},
        {"$set": {"organization_id": org_id, "id": tid, "label": body.label.strip()[:80]}},
        upsert=True,
    )
    return {"ok": True, "id": tid}


@router.delete("/gym-floor/topics/{topic_id}")
async def delete_topic(topic_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    await db.gym_floor_topics.delete_one({"organization_id": org_id, "id": topic_id})
    return {"ok": True}


# ═════════════════ Handover Diary ═════════════════

class HandoverEntry(BaseModel):
    staff_name: str
    topic_id: str
    notes: str = Field(min_length=1, max_length=4000)
    shift_date: Optional[str] = None  # ISO date


@router.get("/gym-floor/handover")
async def list_handover(limit: int = 100, viewer: dict = Depends(_any_viewer)):
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    limit = max(1, min(limit, 500))
    entries = await db.gym_floor_handover.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"entries": entries}


@router.post("/gym-floor/handover")
async def create_handover(body: HandoverEntry, viewer: dict = Depends(_any_viewer)):
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    if not org_id:
        raise HTTPException(400, "Missing organization context")

    moderation = await _moderate(body.notes)
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "staff_name": body.staff_name.strip(),
        "topic_id": body.topic_id,
        "notes": body.notes.strip(),
        "shift_date": (body.shift_date or _now_iso()[:10]),
        "created_at": _now_iso(),
        "flagged": bool(moderation["flagged"]),
        "moderation": moderation,
        "posted_via": "gym_floor" if viewer.get("_gym_floor_session") else "manager",
    }
    await db.gym_floor_handover.insert_one(doc)
    return {"ok": True, "entry": {k: v for k, v in doc.items() if k != "_id"}}


@router.delete("/gym-floor/handover/{entry_id}")
async def delete_handover(entry_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org_id_of(user)
    r = await db.gym_floor_handover.delete_one({"id": entry_id, "organization_id": org_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Entry not found")
    return {"ok": True}


# ═════════════════ Equipment + Fault logging (gym-floor session) ═════════════════
# Gym-floor staff (signed in via the shared site credential) can log faults
# for any machine on their site. To keep every report attributable, the
# staff member must pick their name from the managed roster — we then auto-
# inject their email/mobile into the fault payload so suppliers can reach
# them directly.

class GymFloorFaultIn(BaseModel):
    staff_id: str
    equipment_id: str
    issue_description: str = Field(min_length=3, max_length=4000)
    severity: str = "operational_minor"
    steps_taken: Optional[str] = ""
    fault_code: Optional[str] = None
    media: Optional[list] = None  # [{url, type, name}, …]


@router.get("/gym-floor/equipment")
async def gym_floor_equipment(viewer: dict = Depends(_any_viewer)):
    """Lightweight equipment list usable from the gym-floor login."""
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    if not org_id:
        raise HTTPException(400, "Missing organization context")
    rows = await db.equipment.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "manufacturer": 1,
         "equipment_type": 1, "location": 1, "supplier": 1},
    ).sort("name", 1).to_list(2000)
    return {"equipment": rows}


@router.post("/gym-floor/fault")
async def gym_floor_create_fault(body: GymFloorFaultIn, viewer: dict = Depends(_any_viewer)):
    """Create an issue from the gym-floor login. Requires a roster staff_id
    so the report carries that staff member's email/mobile to suppliers."""
    org_id = viewer.get("organization_id") or _org_id_of(viewer)
    if not org_id:
        raise HTTPException(400, "Missing organization context")

    staff = await db.gym_floor_staff.find_one(
        {"id": body.staff_id, "organization_id": org_id, "active": {"$ne": False}}, {"_id": 0},
    )
    if not staff:
        raise HTTPException(400, "Please select your name from the staff list before logging a fault.")
    if not staff.get("email"):
        raise HTTPException(400, "Your contact details are incomplete — ask the manager to add your email before logging faults.")

    eq = await db.equipment.find_one(
        {"id": body.equipment_id, "organization_id": org_id}, {"_id": 0},
    )
    if not eq:
        raise HTTPException(400, "Equipment not found on this site.")

    # Sanitise inputs to match the standard /api/issues sanitisation behaviour.
    from utils.security import sanitise_string
    now = _now_iso()
    serial = eq.get("serial_number") or eq.get("name") or ""
    severity = body.severity if body.severity in (
        "operational_minor", "operational_fault", "non_operational", "safety_critical",
    ) else "operational_minor"
    fault_type = "safety_critical" if severity == "safety_critical" else "standard"

    issue_doc = {
        "id": str(uuid.uuid4()),
        "user_id": f"gym-floor:{staff['id']}",  # Reference, not a real user
        "organization_id": org_id,
        "site_id": eq.get("site_id"),
        "created_by_name": staff["name"],
        "created_by_email": staff["email"],
        "created_by_mobile": staff.get("mobile") or "",
        "created_via": "gym_floor",
        "serial_number": serial,
        "machine_type": sanitise_string(eq.get("equipment_type") or eq.get("name") or ""),
        "issue_description": sanitise_string(body.issue_description),
        "severity": severity,
        "fault_type": fault_type,
        "sla_category": "standard",
        "supplier": sanitise_string(eq.get("supplier") or eq.get("manufacturer") or ""),
        "steps_taken": sanitise_string(body.steps_taken or ""),
        "status": "open",
        "resolution_type": None,
        "resolution_note": None,
        "resolved_by": None,
        "ai_triage": None,
        "can_fix_onsite": None,
        "selected_fix_step": None,
        "selected_fix_title": None,
        "fix_method": None,
        "fault_code": body.fault_code,
        "media": body.media or [],
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "engineer_assigned_at": None,
        "engineer_arrived_at": None,
        "work_started_at": None,
        "work_completed_at": None,
        "first_response_at": None,
        "parts_used": [],
        "engineer_notes": None,
        "safety_checks_passed": None,
        "timeline": [{
            "event": "fault_logged",
            "timestamp": now,
            "by": f"{staff['name']} (Gym Floor)",
        }],
    }
    await db.issues.insert_one(issue_doc)
    issue_doc.pop("_id", None)

    # Best-effort integration hub publish — same surface as /api/issues so
    # supplier notifications still fire for gym-floor-logged faults.
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="service_issue_created", source_system="service_portal", target_system="crm",
            entity_type="service_case", entity_id=issue_doc["id"],
            payload={
                "issue_id": issue_doc["id"],
                "title": issue_doc.get("machine_type", "Service Issue"),
                "description": issue_doc.get("issue_description", ""),
                "priority": issue_doc.get("severity", "medium"),
                "equipment_name": issue_doc.get("machine_type", ""),
                "reporter_name": staff["name"],
                "reporter_email": staff["email"],
                "reporter_mobile": staff.get("mobile") or "",
            },
            organization_id=org_id,
            triggered_by=f"{staff['name']} (Gym Floor)",
        )
    except Exception as exc:  # pragma: no cover — non-blocking
        logger.info("integration_hub publish failed (non-fatal): %s", exc)

    return {
        "ok": True,
        "id": issue_doc["id"],
        "ref": f"FLT-{issue_doc['id'][:8].upper()}",
        "reporter": {
            "name": staff["name"],
            "email": staff["email"],
            "mobile": staff.get("mobile") or "",
        },
    }
