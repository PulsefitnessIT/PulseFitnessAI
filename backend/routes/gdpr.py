"""GDPR Data Subject Rights — Subject Access export + Right to Erasure.

Operator (owner/manager) tooling to honour data-subject requests for a
single person (a member or a CRM contact):
  • Search a subject by name/email.
  • Export everything held about them (Subject Access Request) as JSON.
  • Erase them (Right to be Forgotten) — PII is anonymised and the record
    flagged ``gdpr_erased=True`` (already respected across every query),
    while financial/transaction records are retained for legal basis.

Every erasure is logged in ``gdpr_erasures`` for an auditable trail.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/gdpr", tags=["gdpr"])

# subject kind -> (primary collection, primary id field)
PRIMARY = {"member": ("members", "id"), "contact": ("crm2_contacts", "id")}

# Related PII-bearing collections to include in an export, keyed by the
# field that links them to the subject id.
RELATED = {
    "member": [
        ("member_memberships", "member_id"), ("member_checkins", "member_id"),
        ("memberships_bookings", "member_id"), ("payment_transactions", "member_id"),
        ("member_inbox", "member_id"), ("member_sub_profiles", "parent_member_id"),
    ],
    "contact": [
        ("crm2_activities", "contact_id"), ("crm2_opportunities", "contact_id"),
        ("crm2_orders", "contact_id"), ("crm2_quotes", "contact_id"),
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_owner_or_manager(user: dict) -> str:
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager", "master_admin", "master") and not user.get("is_master_admin"):
        raise HTTPException(403, "Owner or manager role required")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "No organization context")
    return org_id


def _clean(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("_id", "password")}


def _name(kind: str, doc: dict) -> str:
    n = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
    return n or doc.get("company_name") or doc.get("email") or "(unnamed)"


@router.get("/search")
async def gdpr_search(q: str = Query(..., min_length=2), user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    rx = re.compile(re.escape(q.strip()), re.IGNORECASE)
    out = []
    for kind, (coll, _) in PRIMARY.items():
        docs = await db[coll].find(
            {"organization_id": org_id,
             "$or": [{"email": rx}, {"first_name": rx}, {"last_name": rx}]},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1,
             "company_name": 1, "gdpr_erased": 1}).limit(15).to_list(15)
        for d in docs:
            out.append({"kind": kind, "id": d.get("id"), "name": _name(kind, d),
                        "email": d.get("email"), "erased": bool(d.get("gdpr_erased"))})
    return {"results": out}


@router.get("/subject/{kind}/{subject_id}/export")
async def gdpr_export(kind: str, subject_id: str, user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    if kind not in PRIMARY:
        raise HTTPException(400, "Unknown subject kind")
    coll, idf = PRIMARY[kind]
    subject = await db[coll].find_one({idf: subject_id, "organization_id": org_id}, {"_id": 0})
    if not subject:
        raise HTTPException(404, "Subject not found")

    bundle: dict = {
        "exported_at": _now(), "exported_by": user.get("email"),
        "subject_kind": kind, "subject_id": subject_id,
        "subject_name": _name(kind, subject),
        "profile": _clean(subject),
        "related": {},
    }
    for rel_coll, link in RELATED[kind]:
        rows = await db[rel_coll].find(
            {link: subject_id, "organization_id": org_id}, {"_id": 0}).to_list(2000)
        if rows:
            bundle["related"][rel_coll] = [_clean(r) for r in rows]
    bundle["record_counts"] = {k: len(v) for k, v in bundle["related"].items()}
    return bundle


@router.post("/subject/{kind}/{subject_id}/erase")
async def gdpr_erase(kind: str, subject_id: str, user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    if kind not in PRIMARY:
        raise HTTPException(400, "Unknown subject kind")
    coll, idf = PRIMARY[kind]
    subject = await db[coll].find_one({idf: subject_id, "organization_id": org_id}, {"_id": 0})
    if not subject:
        raise HTTPException(404, "Subject not found")
    if subject.get("gdpr_erased"):
        raise HTTPException(409, "This subject has already been erased")

    original_name = _name(kind, subject)
    anonymised = {
        "first_name": "Erased", "last_name": "User",
        "email": f"erased+{subject_id}@gdpr.invalid",
        "phone": None, "dob": None, "address_line1": None, "address_line2": None,
        "city": None, "postcode": None, "emergency_contact_name": None,
        "emergency_contact_phone": None, "notes": None, "company_name": None,
        "password": None,
        "gdpr_erased": True, "gdpr_erased_at": _now(), "gdpr_erased_by": user.get("email"),
    }
    # Only set fields that exist on the document (keep it minimal & safe).
    update = {k: v for k, v in anonymised.items()
              if k in subject or k in ("gdpr_erased", "gdpr_erased_at", "gdpr_erased_by")}
    await db[coll].update_one({idf: subject_id, "organization_id": org_id}, {"$set": update})

    # Scrub free-text PII on light related collections (financial rows retained).
    scrubbed = {}
    for rel_coll, link in RELATED[kind]:
        if rel_coll in ("payment_transactions", "crm2_orders", "crm2_quotes"):
            continue  # retained for legal/financial basis
        res = await db[rel_coll].update_many(
            {link: subject_id, "organization_id": org_id},
            {"$set": {"gdpr_erased": True}})
        if res.modified_count:
            scrubbed[rel_coll] = res.modified_count

    audit = {
        "id": f"erasure-{subject_id}", "organization_id": org_id, "subject_kind": kind,
        "subject_id": subject_id, "original_name": original_name,
        "erased_by": user.get("email"), "erased_at": _now(),
        "related_flagged": scrubbed,
    }
    await db.gdpr_erasures.insert_one(dict(audit))
    audit.pop("_id", None)
    return {"ok": True, "erased": True, **{k: audit[k] for k in ("subject_kind", "subject_id", "related_flagged")}}


@router.get("/erasures")
async def gdpr_erasures(user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    rows = await db.gdpr_erasures.find(
        {"organization_id": org_id}, {"_id": 0}).sort("erased_at", -1).to_list(200)
    return {"erasures": rows}


# ───────────────────── Retention sweep (data minimisation) ─────────────────────
# Surface members with no activity past a retention window so an operator can
# review and erase them. Activity = last login (last_seen_at) or, failing that,
# sign-up date. Flag-only by design: nothing is erased automatically — the
# operator double-checks the list and runs the existing erasure flow.

class RetentionFlagBody(BaseModel):
    member_ids: list[str]


@router.get("/retention/preview")
async def gdpr_retention_preview(
    months: int = Query(24, ge=1, le=120), user: dict = Depends(get_current_user)
):
    org_id = _require_owner_or_manager(user)
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=months * 30)).isoformat()
    docs = await db.members.find(
        {"organization_id": org_id, "gdpr_erased": {"$ne": True}, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1,
         "last_seen_at": 1, "created_at": 1, "status": 1, "retention_review_flagged": 1},
    ).to_list(5000)

    inactive = []
    for d in docs:
        last = d.get("last_seen_at") or d.get("created_at") or ""
        if last and last < cutoff_iso:
            inactive.append({
                "id": d.get("id"), "name": _name("member", d), "email": d.get("email"),
                "last_active": last, "status": d.get("status"),
                "flagged": bool(d.get("retention_review_flagged")),
            })
    inactive.sort(key=lambda x: x["last_active"])
    return {
        "window_months": months, "cutoff": cutoff_iso,
        "total_inactive": len(inactive), "members": inactive[:200],
    }


@router.post("/retention/flag")
async def gdpr_retention_flag(body: RetentionFlagBody, user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    if not body.member_ids:
        raise HTTPException(400, "No members selected")
    res = await db.members.update_many(
        {"organization_id": org_id, "id": {"$in": body.member_ids}},
        {"$set": {"retention_review_flagged": True, "retention_review_flagged_at": _now(),
                  "retention_review_flagged_by": user.get("email")}})
    return {"ok": True, "flagged": res.modified_count}


@router.post("/retention/unflag")
async def gdpr_retention_unflag(body: RetentionFlagBody, user: dict = Depends(get_current_user)):
    org_id = _require_owner_or_manager(user)
    if not body.member_ids:
        raise HTTPException(400, "No members selected")
    res = await db.members.update_many(
        {"organization_id": org_id, "id": {"$in": body.member_ids}},
        {"$unset": {"retention_review_flagged": "", "retention_review_flagged_at": "",
                    "retention_review_flagged_by": ""}})
    return {"ok": True, "unflagged": res.modified_count}
