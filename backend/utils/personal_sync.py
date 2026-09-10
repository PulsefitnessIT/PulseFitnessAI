"""Single source of truth for a staff member's personal details.

The canonical store is ``staff_members`` (the HR-profile fields are embedded
there). The New Starter sign-up keeps a parallel copy in the ``new_starter``
form submission so the recruit wizard and the Staff Portal "My Details" tab can
read it. To stop the two drifting, every write path mirrors both ways through
these helpers, and reads overlay the canonical values on top of the form copy.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# (new_starter form key, canonical staff_members field)
PERSONAL_MAP = [
    ("dob", "date_of_birth"),
    ("ni_number", "ni_number"),
    ("home_address", "address_line1"),
    ("emergency_contact_name", "emergency_contact_name"),
    ("emergency_contact_phone", "emergency_contact_phone"),
    ("bank_name", "bank_name"),
    ("sort_code", "bank_sort_code"),
    ("bank_account", "bank_account"),
]

_STAFF_TO_FORM = {s: f for f, s in PERSONAL_MAP}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last4(v) -> str | None:
    s = "".join(ch for ch in str(v or "") if ch.isalnum())
    return s[-4:] if s else None


def form_to_staff_patch(data: dict) -> dict:
    """Canonical ``staff_members`` $set patch derived from new_starter form data."""
    patch: dict = {}
    for fkey, sfield in PERSONAL_MAP:
        if fkey in (data or {}):
            val = data[fkey]
            patch[sfield] = val
            if sfield == "bank_account":
                patch["bank_account_last4"] = _last4(val)
    return patch


def staff_to_form_patch(staff: dict) -> dict:
    """new_starter form-data patch derived from canonical ``staff_members`` fields."""
    patch: dict = {}
    for fkey, sfield in PERSONAL_MAP:
        if (staff or {}).get(sfield) is not None:
            patch[fkey] = staff[sfield]
    return patch


async def sync_from_form(db, org_id: str, staff_id: str, form_data: dict) -> dict:
    """Write personal fields entered on the sign-up form into the canonical
    ``staff_members`` record. Returns the applied patch."""
    patch = form_to_staff_patch(form_data)
    if patch:
        patch["updated_at"] = _now_iso()
        await db.staff_members.update_one(
            {"id": staff_id, "organization_id": org_id}, {"$set": patch})
    return patch


async def sync_from_staff(db, org_id: str, staff_id: str, staff_patch: dict) -> None:
    """Mirror the personal fields of a ``staff_members`` $set patch back into the
    new_starter form data so My Details (which reads the form) stays current."""
    form_patch = {_STAFF_TO_FORM[k]: v for k, v in (staff_patch or {}).items()
                  if k in _STAFF_TO_FORM}
    if not form_patch:
        return
    now = _now_iso()
    existing = await db.staff_form_submissions.find_one(
        {"staff_id": staff_id, "form_key": "new_starter"})
    if existing:
        data = dict(existing.get("data") or {})
        data.update(form_patch)
        await db.staff_form_submissions.update_one(
            {"id": existing["id"]}, {"$set": {"data": data, "updated_at": now}})
    else:
        await db.staff_form_submissions.insert_one({
            "id": str(uuid.uuid4()), "staff_id": staff_id, "organization_id": org_id,
            "onboarding_case_id": None, "form_key": "new_starter", "data": form_patch,
            "created_at": now, "updated_at": now})
