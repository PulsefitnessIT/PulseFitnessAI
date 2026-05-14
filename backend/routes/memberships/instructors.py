"""Memberships — Instructor profile roster + public pages.

Iter 215v. Introduces a first-class Instructor entity so studios can
show off their teachers, sell their classes, and share bio pages
anywhere on social.

New collection: ``membership_instructors``

  { id, organization_id,
    name, email, phone,
    slug,            — url-safe, unique within org
    headline,        — short 1-liner e.g. "RYT-500 · Vinyasa & Pre-natal"
    bio,             — long-form body
    photo_url,       — avatar (square) — data URL or external
    hero_photo_url,  — wide (≥1200×630 ideal)
    specialties,     — list[str]
    qualifications,  — list[str]
    years_experience,— int
    social,          — { instagram, tiktok, linkedin, website }
    user_id,         — optional link to a user login for /instructor/*
    is_published,    — hides the public page when false
    archived,
    created_at, updated_at, created_by }

Routes:
  Operator:
    GET    /memberships/instructors                  — list
    POST   /memberships/instructors                  — create
    GET    /memberships/instructors/{id}             — detail
    PATCH  /memberships/instructors/{id}             — edit
    POST   /memberships/instructors/{id}/photo       — set photo (data url)
    POST   /memberships/instructors/{id}/hero        — set hero photo
    DELETE /memberships/instructors/{id}             — archive
  Public:
    GET /public/studios/{slug}/instructors              — roster JSON
    GET /public/studios/{slug}/instructors/{slug}       — profile JSON
    GET /m/{slug}/i/{instructor_slug}/share             — social HTML
    GET /m/{slug}/i/{instructor_slug}/og.png            — OG preview
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db, get_object, put_object
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_operator_org,
    _uuid,
)
from routes.memberships.studio_extras import _hex_to_rgb, _pick_font

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-instructors"])


# ═══════════════════════════════ Schema ═══════════════════════════════

class Social(BaseModel):
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    linkedin: Optional[str] = None
    website: Optional[str] = None


class InstructorIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = None
    headline: Optional[str] = Field(default=None, max_length=140)
    bio: Optional[str] = Field(default=None, max_length=4000)
    photo_url: Optional[str] = None
    hero_photo_url: Optional[str] = None
    specialties: list[str] = []
    qualifications: list[str] = []
    years_experience: Optional[int] = Field(default=None, ge=0, le=80)
    social: Social = Social()
    user_id: Optional[str] = None
    is_published: bool = True
    # Iter 215bl — extended profile fields so the operator-facing
    # instructor drawer captures the same record shape as members.
    dob: Optional[str] = None
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=120)
    postcode: Optional[str] = Field(default=None, max_length=24)
    country: Optional[str] = Field(default=None, max_length=80)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=120)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=4000)
    tags: list[str] = []
    # Iter 216ae — Phase F safeguarding & payroll fields.
    dbs_reference: Optional[str] = Field(default=None, max_length=40)
    dbs_issued_on: Optional[str] = None      # YYYY-MM-DD
    dbs_expires_on: Optional[str] = None     # YYYY-MM-DD
    safeguarding_completed_on: Optional[str] = None
    safeguarding_expires_on: Optional[str] = None
    first_aid_completed_on: Optional[str] = None
    first_aid_expires_on: Optional[str] = None
    hourly_rate_pence: Optional[int] = Field(default=None, ge=0, le=100_000)
    substitute_available: bool = True


class InstructorPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    hero_photo_url: Optional[str] = None
    specialties: Optional[list[str]] = None
    qualifications: Optional[list[str]] = None
    years_experience: Optional[int] = None
    social: Optional[Social] = None
    user_id: Optional[str] = None
    is_published: Optional[bool] = None
    # Iter 215bl — extended profile fields (same set as members).
    dob: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    # Iter 216ae — Phase F safeguarding & payroll fields (patch variant).
    dbs_reference: Optional[str] = None
    dbs_issued_on: Optional[str] = None
    dbs_expires_on: Optional[str] = None
    safeguarding_completed_on: Optional[str] = None
    safeguarding_expires_on: Optional[str] = None
    first_aid_completed_on: Optional[str] = None
    first_aid_expires_on: Optional[str] = None
    hourly_rate_pence: Optional[int] = None
    substitute_available: Optional[bool] = None


# ═══════════════════════════════ Helpers ═══════════════════════════════

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _SLUG_RE.sub("-", (s or "").lower()).strip("-")[:60] or "instructor"


async def _unique_slug(org_id: str, base: str, exclude_id: str | None = None) -> str:
    """Return ``base`` if free within the org, else append -2, -3, etc."""
    slug = base
    n = 1
    while True:
        q: dict = {"organization_id": org_id, "slug": slug}
        if exclude_id:
            q["id"] = {"$ne": exclude_id}
        existing = await db.membership_instructors.find_one(q, {"_id": 0, "id": 1})
        if not existing:
            return slug
        n += 1
        slug = f"{base}-{n}"


def _public_view(doc: dict) -> dict:
    """Pare down to the fields we're willing to show on the public profile."""
    social = doc.get("social") or {}
    return {
        "id": doc["id"],
        "slug": doc.get("slug"),
        "name": doc.get("name"),
        "headline": doc.get("headline"),
        "bio": doc.get("bio"),
        "photo_url": doc.get("photo_url"),
        "hero_photo_url": doc.get("hero_photo_url"),
        "specialties": doc.get("specialties") or [],
        "qualifications": doc.get("qualifications") or [],
        "years_experience": doc.get("years_experience"),
        "social": {
            "instagram": social.get("instagram"),
            "tiktok": social.get("tiktok"),
            "linkedin": social.get("linkedin"),
            "website": social.get("website"),
        },
    }


# ═════════════════════════ Operator CRUD ═════════════════════════

@router.get(
    "/memberships/instructors",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_instructors(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rows = await db.membership_instructors.find(
        {"organization_id": org_id, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    return {"instructors": rows}


# ═════════════════════ Phase F: compliance / payroll / substitutes ═════════════════════
# IMPORTANT: declared before the `/{instructor_id}` dynamic routes so FastAPI
# matches the static paths first.


def _compliance_status(inst: dict) -> dict:
    """Traffic-light status for DBS / safeguarding / first-aid.
    Returns: { status: 'green'|'amber'|'red'|'missing', earliest_expiry, items: [...] }.
    Amber = expires within 60 days. Red = already expired."""
    today = datetime.now(timezone.utc).date()
    soon_days = 60
    items: list[dict] = []
    statuses: list[str] = []
    earliest: str | None = None
    for label, key in [
        ("DBS", "dbs_expires_on"),
        ("Safeguarding", "safeguarding_expires_on"),
        ("First aid", "first_aid_expires_on"),
    ]:
        val = inst.get(key)
        if not val:
            items.append({"label": label, "expires_on": None, "status": "missing"})
            statuses.append("missing")
            continue
        try:
            d = datetime.fromisoformat(str(val)[:10]).date()
        except (ValueError, TypeError):
            items.append({"label": label, "expires_on": val, "status": "missing"})
            statuses.append("missing")
            continue
        delta = (d - today).days
        s = "red" if delta < 0 else ("amber" if delta <= soon_days else "green")
        items.append({"label": label, "expires_on": val, "status": s, "days": delta})
        statuses.append(s)
        if earliest is None or str(val) < earliest:
            earliest = str(val)
    order = {"red": 3, "missing": 2, "amber": 1, "green": 0}
    overall = max(statuses, key=lambda x: order[x]) if statuses else "missing"
    return {"status": overall, "earliest_expiry": earliest, "items": items}


@router.get(
    "/memberships/instructors/substitutes",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_substitutes(
    discipline: Optional[str] = None,
    specialty: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Substitute pool — instructors flagged as available for cover,
    filtered by optional discipline/specialty. Annotates each row with
    compliance traffic-light so dispatchers can skip red/expired subs."""
    org_id = await _require_operator_org(user)
    rows = await db.membership_instructors.find(
        {"organization_id": org_id,
         "archived": {"$ne": True},
         "substitute_available": {"$ne": False}},
        {"_id": 0},
    ).sort("name", 1).to_list(500)
    needle = (discipline or specialty or "").strip().lower()
    out: list[dict] = []
    for r in rows:
        if needle:
            specs = [s.lower() for s in (r.get("specialties") or [])]
            quals = [s.lower() for s in (r.get("qualifications") or [])]
            if needle not in specs and needle not in quals:
                continue
        r["compliance"] = _compliance_status(r)
        out.append(r)
    order = {"green": 0, "amber": 1, "missing": 2, "red": 3}
    out.sort(key=lambda x: (order.get(x["compliance"]["status"], 4), x.get("name") or ""))
    return {"substitutes": out, "count": len(out)}


@router.get(
    "/memberships/instructors/compliance",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_instructor_compliance(user: dict = Depends(get_current_user)):
    """Compliance overview for all instructors — used by the roster badges
    and by an operator KPI strip."""
    org_id = await _require_operator_org(user)
    rows = await db.membership_instructors.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "dbs_expires_on": 1,
         "safeguarding_expires_on": 1, "first_aid_expires_on": 1,
         "substitute_available": 1},
    ).to_list(500)
    summary = {"green": 0, "amber": 0, "red": 0, "missing": 0, "total": len(rows)}
    out: list[dict] = []
    for r in rows:
        c = _compliance_status(r)
        summary[c["status"]] = summary.get(c["status"], 0) + 1
        out.append({
            "id": r["id"], "name": r.get("name"),
            "substitute_available": r.get("substitute_available", True),
            "compliance": c,
        })
    return {"compliance": out, "summary": summary}


@router.get(
    "/memberships/instructors/payroll.csv",
    dependencies=[Depends(require_module("memberships"))],
)
async def payroll_csv(
    date_from: str,
    date_to: str,
    user: dict = Depends(get_current_user),
):
    """Payroll CSV: aggregates completed class occurrences in the window
    and computes pay per instructor. Resolution order for rate:
      1. class_templates.instructor_rate_pence (flat per class)
      2. membership_instructors.hourly_rate_pence × (duration_min / 60)
      3. users.instructor_rate_pence (flat per class, legacy)
    Headers: Instructor, Email, Classes completed, Minutes taught, Hourly rate (GBP), Pay (GBP)."""
    import csv
    from io import StringIO

    org_id = await _require_operator_org(user)
    try:
        df = datetime.fromisoformat(f"{date_from[:10]}T00:00:00+00:00")
        dt = datetime.fromisoformat(f"{date_to[:10]}T23:59:59+00:00")
    except ValueError:
        raise HTTPException(400, "date_from and date_to must be YYYY-MM-DD")

    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": df.isoformat(), "$lte": dt.isoformat()},
         "status": "completed",
         "instructor_user_id": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "instructor_user_id": 1, "instructor_name": 1,
         "template_id": 1, "starts_at": 1, "ends_at": 1, "duration_min": 1},
    ).to_list(5000)

    tpl_ids = list({o.get("template_id") for o in occs if o.get("template_id")})
    tpl_rates: dict[str, int] = {}
    tpl_durations: dict[str, int] = {}
    if tpl_ids:
        async for t in db.class_templates.find(
            {"id": {"$in": tpl_ids}},
            {"_id": 0, "id": 1, "instructor_rate_pence": 1, "duration_min": 1},
        ):
            if t.get("instructor_rate_pence"):
                tpl_rates[t["id"]] = int(t["instructor_rate_pence"])
            if t.get("duration_min"):
                tpl_durations[t["id"]] = int(t["duration_min"])

    user_ids = list({o["instructor_user_id"] for o in occs if o.get("instructor_user_id")})
    insts: dict[str, dict] = {}
    user_rates: dict[str, int] = {}
    user_emails: dict[str, str] = {}
    user_names: dict[str, str] = {}
    if user_ids:
        async for inst in db.membership_instructors.find(
            {"organization_id": org_id, "user_id": {"$in": user_ids}, "archived": {"$ne": True}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "hourly_rate_pence": 1},
        ):
            insts[inst["user_id"]] = inst
        async for u in db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1,
             "email": 1, "instructor_rate_pence": 1},
        ):
            user_rates[u["id"]] = int(u.get("instructor_rate_pence") or 0)
            user_emails[u["id"]] = u.get("email") or ""
            user_names[u["id"]] = (
                (u.get("first_name") or "") + " " + (u.get("last_name") or "")
            ).strip()

    def _duration_min(o: dict) -> int:
        if o.get("duration_min"):
            return int(o["duration_min"])
        if o.get("template_id") and tpl_durations.get(o["template_id"]):
            return tpl_durations[o["template_id"]]
        try:
            start = datetime.fromisoformat(o["starts_at"])
            end = datetime.fromisoformat(o["ends_at"])
            return max(int((end - start).total_seconds() // 60), 0)
        except (KeyError, ValueError, TypeError):
            return 60

    agg: dict[str, dict] = {}
    for o in occs:
        uid = o["instructor_user_id"]
        a = agg.setdefault(uid, {
            "name": (insts.get(uid, {}).get("name")
                     or user_names.get(uid)
                     or o.get("instructor_name") or "Instructor"),
            "email": (insts.get(uid, {}).get("email")
                      or user_emails.get(uid) or ""),
            "hourly_rate_pence": insts.get(uid, {}).get("hourly_rate_pence"),
            "classes": 0,
            "minutes": 0,
            "pay_pence": 0,
        })
        a["classes"] += 1
        mins = _duration_min(o)
        a["minutes"] += mins
        flat = tpl_rates.get(o.get("template_id") or "")
        if flat:
            a["pay_pence"] += int(flat)
        elif a.get("hourly_rate_pence"):
            a["pay_pence"] += int(round(a["hourly_rate_pence"] * mins / 60.0))
        elif user_rates.get(uid):
            a["pay_pence"] += int(user_rates[uid])

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Instructor", "Email", "Classes completed", "Minutes taught",
        "Hourly rate (GBP)", "Pay (GBP)",
    ])
    rows_sorted = sorted(agg.values(), key=lambda r: -r["pay_pence"])
    total_pay = 0
    total_classes = 0
    total_minutes = 0
    for r in rows_sorted:
        hr = f"{(r['hourly_rate_pence'] or 0) / 100:.2f}" if r.get("hourly_rate_pence") else ""
        w.writerow([
            r["name"], r["email"], r["classes"], r["minutes"],
            hr, f"{r['pay_pence'] / 100:.2f}",
        ])
        total_pay += r["pay_pence"]
        total_classes += r["classes"]
        total_minutes += r["minutes"]
    w.writerow(["TOTAL", "", total_classes, total_minutes, "", f"{total_pay / 100:.2f}"])

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    filename = (
        f"payroll-{(org.get('name') or 'studio').lower().replace(' ', '-')}-"
        f"{date_from[:10]}-to-{date_to[:10]}.csv"
    )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/memberships/instructors",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_instructor(body: InstructorIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    base = _slugify(body.name)
    slug = await _unique_slug(org_id, base)
    doc = {
        "id": _uuid(),
        "organization_id": org_id,
        "slug": slug,
        **body.model_dump(),
        "created_by": user.get("id"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.membership_instructors.insert_one({**doc})
    return {"instructor": {k: v for k, v in doc.items() if k != "_id"}}


@router.get(
    "/memberships/instructors/{instructor_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def get_instructor(instructor_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    inst = await db.membership_instructors.find_one(
        {"id": instructor_id, "organization_id": org_id}, {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "Instructor not found")
    return {"instructor": inst}


@router.patch(
    "/memberships/instructors/{instructor_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def patch_instructor(
    instructor_id: str, body: InstructorPatch, user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    inst = await db.membership_instructors.find_one(
        {"id": instructor_id, "organization_id": org_id}, {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "Instructor not found")
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "social" in updates and isinstance(updates["social"], dict):
        # Pydantic has already validated the sub-model shape.
        pass
    if updates.get("name") and updates["name"] != inst.get("name"):
        updates["slug"] = await _unique_slug(
            org_id, _slugify(updates["name"]), exclude_id=instructor_id,
        )
    updates["updated_at"] = _now_iso()
    await db.membership_instructors.update_one(
        {"id": instructor_id}, {"$set": updates},
    )
    # Invalidate any cached OG image — fingerprint will differ anyway.
    await db.membership_instructors.update_one(
        {"id": instructor_id}, {"$unset": {"cached_og": ""}},
    )
    fresh = await db.membership_instructors.find_one(
        {"id": instructor_id}, {"_id": 0},
    )
    return {"instructor": fresh}


class PhotoIn(BaseModel):
    photo_url: str = Field(min_length=6, max_length=2_000_000)
    """A data: URL (data:image/jpeg;base64,...) OR a plain https:// URL."""


@router.post(
    "/memberships/instructors/{instructor_id}/photo",
    dependencies=[Depends(require_module("memberships"))],
)
async def set_photo(instructor_id: str, body: PhotoIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.membership_instructors.update_one(
        {"id": instructor_id, "organization_id": org_id},
        {"$set": {"photo_url": body.photo_url, "updated_at": _now_iso()},
         "$unset": {"cached_og": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Instructor not found")
    return {"ok": True}


@router.post(
    "/memberships/instructors/{instructor_id}/hero",
    dependencies=[Depends(require_module("memberships"))],
)
async def set_hero(instructor_id: str, body: PhotoIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.membership_instructors.update_one(
        {"id": instructor_id, "organization_id": org_id},
        {"$set": {"hero_photo_url": body.photo_url, "updated_at": _now_iso()},
         "$unset": {"cached_og": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Instructor not found")
    return {"ok": True}


@router.delete(
    "/memberships/instructors/{instructor_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def archive_instructor(instructor_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    res = await db.membership_instructors.update_one(
        {"id": instructor_id, "organization_id": org_id},
        {"$set": {"archived": True, "is_published": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Instructor not found")
    return {"ok": True}


# ═════════════════════ Invite login + self-edit (iter 215w) ═════════════════════

@router.post(
    "/memberships/instructors/{instructor_id}/invite-login",
    dependencies=[Depends(require_module("memberships"))],
)
async def invite_instructor_login(instructor_id: str, user: dict = Depends(get_current_user)):
    """Operator-triggered — creates a linked user account so the
    instructor can sign in at /instructor. If the instructor already has
    ``user_id``, we just return that. Otherwise we create a user with a
    random password + magic link email (no password sent over wire).
    """
    import os as _os
    import secrets
    from utils.auth import hash_password
    from utils.email import send_email as _send

    org_id = await _require_operator_org(user)
    inst = await db.membership_instructors.find_one(
        {"id": instructor_id, "organization_id": org_id}, {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "Instructor not found")
    if not inst.get("email"):
        raise HTTPException(400, "Add an email on the instructor before inviting them")

    if inst.get("user_id"):
        existing = await db.users.find_one(
            {"id": inst["user_id"]}, {"_id": 0, "id": 1, "email": 1},
        )
        if existing:
            return {"ok": True, "user_id": existing["id"], "already_linked": True}

    # Someone with this email might already be on another org — refuse to
    # collide; operator should change the email or link manually.
    email = inst["email"].strip().lower()
    dupe = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "organization_id": 1})
    if dupe:
        if dupe.get("organization_id") == org_id:
            await db.membership_instructors.update_one(
                {"id": instructor_id}, {"$set": {"user_id": dupe["id"], "updated_at": _now_iso()}},
            )
            return {"ok": True, "user_id": dupe["id"], "linked_existing": True}
        raise HTTPException(409, "Email already in use on another organisation")

    tmp_password = secrets.token_urlsafe(16)
    new_user = {
        "id": _uuid(),
        "email": email,
        "full_name": inst["name"],
        "password": hash_password(tmp_password),
        "organization_id": org_id,
        "account_type": "instructor",
        "is_instructor": True,
        "created_at": _now_iso(),
    }
    await db.users.insert_one({**new_user})
    await db.membership_instructors.update_one(
        {"id": instructor_id}, {"$set": {"user_id": new_user["id"], "updated_at": _now_iso()}},
    )

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "primary_color": 1}) or {}
    primary = org.get("primary_color") or "#00B2C7"
    frontend = (
        _os.environ.get("FRONTEND_URL")
        or _os.environ.get("REACT_APP_BACKEND_URL")
        or "https://gymaxisai.com"
    ).rstrip("/")
    html = (
        f"<div style='font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto'>"
        f"<div style='background:{primary};padding:18px 24px;border-radius:12px 12px 0 0'>"
        f"<h1 style='color:#0A0C10;margin:0;font-size:22px'>You're invited · {org.get('name') or 'Your studio'}</h1></div>"
        f"<div style='padding:24px;background:#0A0C10;color:#fff;border-radius:0 0 12px 12px'>"
        f"<p>Hi {inst['name']},</p>"
        f"<p>Your studio has set up an instructor account for you. Sign in to keep your bio, photo, and availability up to date.</p>"
        f"<p><strong>Email:</strong> {email}<br>"
        f"<strong>Temporary password:</strong> <code style='background:rgba(255,255,255,0.08);padding:4px 8px;border-radius:4px'>{tmp_password}</code></p>"
        f"<p><a href='{frontend}/instructor' style='display:inline-block;background:{primary};color:#0A0C10;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:800'>Sign in to your profile →</a></p>"
        f"<p style='opacity:0.6;font-size:12px'>Please change your password after signing in.</p></div></div>"
    )
    await _send(email, f"You're invited to {org.get('name') or 'your studio'}", html)
    return {"ok": True, "user_id": new_user["id"], "created_user": True}


@router.get("/instructor/profile")
async def instructor_get_own_profile(user: dict = Depends(get_current_user)):
    """Instructor self-serve: fetch my profile doc (linked by user_id)."""
    inst = await db.membership_instructors.find_one(
        {"user_id": user["id"]}, {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "No instructor profile linked to your account. Ask your studio to connect it.")
    return {"instructor": inst}


@router.patch("/instructor/profile")
async def instructor_update_own_profile(
    body: InstructorPatch, user: dict = Depends(get_current_user),
):
    """Instructor self-serve: update my own profile. Only fields safe
    for self-service are honoured — is_published, user_id, email,
    phone, specialties rarely need instructor-driven edits but harmless
    to allow. ``name`` is not allowed because slug churn would break
    shared links; instructors who've married/etc ask their operator."""
    inst = await db.membership_instructors.find_one(
        {"user_id": user["id"]}, {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "No instructor profile linked to your account.")
    updates = {
        k: v for k, v in body.model_dump(exclude_none=True).items()
        if k in {"headline", "bio", "photo_url", "hero_photo_url",
                 "specialties", "qualifications", "years_experience", "social"}
    }
    if not updates:
        return {"instructor": inst}
    updates["updated_at"] = _now_iso()
    await db.membership_instructors.update_one(
        {"id": inst["id"]},
        {"$set": updates, "$unset": {"cached_og": ""}},
    )
    fresh = await db.membership_instructors.find_one({"id": inst["id"]}, {"_id": 0})
    return {"instructor": fresh}


# ═════════════════════════ Public endpoints ═════════════════════════

async def _resolve_org_and_instructor(slug: str, instructor_slug: str) -> tuple[dict, dict]:
    org = await db.organizations.find_one(
        {"$or": [{"membership_app_slug": slug}, {"slug": slug}]}, {"_id": 0},
    )
    if not org or not (org.get("modules") or {}).get("memberships"):
        raise HTTPException(404, "Studio not found")
    inst = await db.membership_instructors.find_one(
        {
            "organization_id": org["id"],
            "slug": instructor_slug,
            "archived": {"$ne": True},
            "is_published": True,
        },
        {"_id": 0},
    )
    if not inst:
        raise HTTPException(404, "Instructor not found")
    return org, inst


@router.get("/public/studios/{slug}/instructors")
async def public_list_instructors(slug: str):
    org = await db.organizations.find_one(
        {"$or": [{"membership_app_slug": slug}, {"slug": slug}]}, {"_id": 0, "id": 1, "name": 1, "primary_color": 1},
    )
    if not org:
        raise HTTPException(404, "Studio not found")
    rows = await db.membership_instructors.find(
        {"organization_id": org["id"], "archived": {"$ne": True}, "is_published": True},
        {"_id": 0},
    ).sort("name", 1).to_list(200)
    return {"studio": org, "instructors": [_public_view(r) for r in rows]}


async def _upcoming_for_instructor(org_id: str, instructor_id: str) -> list[dict]:
    """Return the next 10 scheduled occurrences taught by this instructor."""
    now = _now_iso()
    # Instructors link either via class_templates.instructor_id or
    # occurrence.instructor_id (legacy) or occurrence.instructor_user_id.
    tpl_ids = await db.class_templates.distinct(
        "id", {"organization_id": org_id, "instructor_id": instructor_id},
    )
    q: dict = {
        "organization_id": org_id,
        "starts_at": {"$gte": now},
        "status": "scheduled",
        "$or": [
            {"instructor_id": instructor_id},
            {"template_id": {"$in": tpl_ids}} if tpl_ids else {"_placeholder": True},
        ],
    }
    # Clean up the $or list — drop the placeholder when empty.
    q["$or"] = [c for c in q["$or"] if "_placeholder" not in c]
    if not q["$or"]:
        q.pop("$or")
    occs = await db.class_occurrences.find(
        q, {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "ends_at": 1,
            "capacity": 1, "bookings_count": 1, "room_name": 1, "template_id": 1},
    ).sort("starts_at", 1).limit(10).to_list(10)
    # Fill any missing name from template.
    need_names = [o["template_id"] for o in occs if not o.get("name") and o.get("template_id")]
    if need_names:
        tpls = await db.class_templates.find(
            {"id": {"$in": need_names}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(need_names))
        name_by = {t["id"]: t["name"] for t in tpls}
        for o in occs:
            if not o.get("name"):
                o["name"] = name_by.get(o.get("template_id"), "Class")
    return occs


@router.get("/public/studios/{slug}/instructors/{instructor_slug}")
async def public_instructor_profile(slug: str, instructor_slug: str):
    org, inst = await _resolve_org_and_instructor(slug, instructor_slug)
    upcoming = await _upcoming_for_instructor(org["id"], inst["id"])
    return {
        "studio": {
            "id": org["id"],
            "name": org.get("name"),
            "slug": org.get("membership_app_slug") or org.get("slug"),
            "primary_color": org.get("primary_color") or "#00B2C7",
        },
        "instructor": _public_view(inst),
        "upcoming": upcoming,
    }


# ═════════════════════════ OG image + share HTML ═════════════════════════

def _instructor_og_cache_key(org: dict, inst: dict) -> str:
    parts = (
        str(inst.get("id") or ""),
        str(inst.get("name") or ""),
        str(inst.get("headline") or ""),
        str(inst.get("photo_url") or "")[:64],
        str(org.get("primary_color") or ""),
        str(org.get("name") or ""),
        "v1",
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _instructor_og_storage_path(org_id: str, inst_id: str, key: str) -> str:
    return f"instructor-og/{org_id}/{inst_id}/{key}.png"


def _render_instructor_og(org: dict, inst: dict) -> bytes:
    """1200×630 PNG: photo circle on the left, name + headline + studio
    branding on the right. Pure Pillow; safe in a thread."""
    W, H = 1200, 630
    primary = _hex_to_rgb(org.get("primary_color") or "#00B2C7")
    img = Image.new("RGB", (W, H), (10, 12, 16))
    d = ImageDraw.Draw(img)

    # Soft gradient drift toward the brand colour.
    for i in range(H):
        t = i / H
        r = int(10 + (primary[0] - 10) * t * 0.22)
        g = int(12 + (primary[1] - 12) * t * 0.22)
        b = int(16 + (primary[2] - 16) * t * 0.22)
        d.line([(0, i), (W, i)], fill=(r, g, b))
    d.rectangle([0, 0, W, 8], fill=primary)

    # Photo circle (avatar) — 320×320 on the left.
    photo_box = (80, 155, 400, 475)
    placed = False
    photo_src = inst.get("photo_url") or ""
    try:
        if photo_src.startswith("data:image"):
            import base64 as _b64
            _, b64 = photo_src.split(",", 1)
            photo = Image.open(io.BytesIO(_b64.b64decode(b64))).convert("RGB")
            photo = photo.resize((320, 320))
            mask = Image.new("L", (320, 320), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 320, 320), fill=255)
            img.paste(photo, (photo_box[0], photo_box[1]), mask)
            placed = True
    except Exception as exc:  # noqa: BLE001
        logger.info("instructor og: photo render failed (%s)", exc)

    if not placed:
        # Initials fallback — draw a primary-tinted circle with initials.
        d.ellipse(photo_box, fill=primary, outline=(255, 255, 255), width=3)
        initials = "".join(w[0] for w in (inst.get("name") or "?").split()[:2]).upper() or "?"
        font = _pick_font(140)
        tw = d.textlength(initials, font=font)
        d.text(
            (photo_box[0] + (320 - tw) / 2, photo_box[1] + 60),
            initials, fill=(10, 12, 16), font=font,
        )

    # Right-hand copy.
    font_small = _pick_font(24)
    font_name = _pick_font(74)
    font_headline = _pick_font(32)
    font_footer = _pick_font(22)

    d.text((450, 170), (org.get("name") or "").upper(), fill=(255, 255, 255, 220), font=font_small)
    name = inst.get("name") or "Instructor"
    if len(name) > 18:
        # Wrap to two lines around the midpoint space.
        words = name.split()
        mid = len(words) // 2 or 1
        l1 = " ".join(words[:mid])
        l2 = " ".join(words[mid:])
        d.text((450, 215), l1, fill=(255, 255, 255), font=font_name)
        d.text((450, 305), l2, fill=(255, 255, 255), font=font_name)
    else:
        d.text((450, 230), name, fill=(255, 255, 255), font=font_name)

    headline = (inst.get("headline") or "").strip()
    if headline:
        if len(headline) > 44:
            headline = headline[:43] + "…"
        d.text((450, 400), headline, fill=primary, font=font_headline)

    d.text((450, 560), "Book a class · powered by GymAxis", fill=(255, 255, 255, 160), font=font_footer)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def _get_or_render_instructor_og(org: dict, inst: dict) -> tuple[bytes, str]:
    key = _instructor_og_cache_key(org, inst)
    cache_meta = inst.get("cached_og") or {}
    path = cache_meta.get("path") or _instructor_og_storage_path(org["id"], inst["id"], key)
    if cache_meta.get("hash") == key:
        try:
            data, _ct = await asyncio.to_thread(get_object, path)
            if data:
                return data, "cache"
        except Exception as exc:  # noqa: BLE001
            logger.warning("instructor og_cache: get failed %s — regenerating (%s)", path, exc)
    data = await asyncio.to_thread(_render_instructor_og, org, inst)
    try:
        fresh_path = _instructor_og_storage_path(org["id"], inst["id"], key)
        await asyncio.to_thread(put_object, fresh_path, data, "image/png")
        await db.membership_instructors.update_one(
            {"id": inst["id"]},
            {"$set": {"cached_og": {
                "hash": key, "path": fresh_path, "bytes": len(data),
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("instructor og_cache: put failed — serving fresh (%s)", exc)
    return data, "fresh"


@router.get("/m/{slug}/i/{instructor_slug}/og.png")
async def instructor_og_image(slug: str, instructor_slug: str):
    org, inst = await _resolve_org_and_instructor(slug, instructor_slug)
    data, source = await _get_or_render_instructor_og(org, inst)
    return Response(
        content=data, media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=600",
            "X-GymAxis-OG-Cache": source,
        },
    )


@router.get("/m/{slug}/i/{instructor_slug}/share", response_class=HTMLResponse)
async def instructor_share_html(slug: str, instructor_slug: str, request: Request):
    org, inst = await _resolve_org_and_instructor(slug, instructor_slug)
    base = str(request.base_url).rstrip("/")
    og_image = f"{base}/api/m/{slug}/i/{instructor_slug}/og.png"
    spa_url = f"{base}/m/{slug}/i/{instructor_slug}"
    org_name = org.get("name") or "Studio"
    name = inst.get("name") or "Instructor"
    headline = inst.get("headline") or ""
    title = f"{name} · {org_name}"
    description = (headline or (inst.get("bio") or "")[:140] or f"Meet {name} at {org_name}")
    primary = org.get("primary_color") or "#00B2C7"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="profile">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{og_image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="{spa_url}">
  <meta property="og:site_name" content="{org_name}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{og_image}">
  <meta http-equiv="refresh" content="0; url={spa_url}">
  <link rel="canonical" href="{spa_url}">
  <style>
    body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0A0C10; color:#fff; min-height:100vh; display:grid; place-items:center; padding:24px; }}
    a {{ color:{primary}; font-weight:700; }}
  </style>
</head>
<body>
  <div style="max-width:560px; text-align:center">
    <p style="opacity:.6; font-size:11px; letter-spacing:.22em; text-transform:uppercase; margin:0">{org_name}</p>
    <h1 style="font-size:40px; margin:12px 0">{name}</h1>
    <p style="opacity:.8; font-size:18px">{headline}</p>
    <p style="margin-top:32px"><a href="{spa_url}">Open profile →</a></p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})
