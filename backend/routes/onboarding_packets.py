"""
Customer Onboarding Packets
Master Admin creates a shareable packet → customer fills it at a token URL →
Master Admin reviews & atomically provisions org + sites + users + equipment + suppliers + contracts.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from utils.auth import get_current_user, hash_password
from utils.database import db
from utils.email import send_password_reset_email, send_onboarding_invite_email

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────

EMPTY_ORG = {
    "legal_name": "", "trading_name": "", "vat_number": "", "company_number": "",
    "billing_address_line1": "", "billing_address_line2": "",
    "billing_city": "", "billing_postcode": "", "billing_country": "United Kingdom",
    "primary_contact_name": "", "primary_contact_email": "", "primary_contact_phone": "",
    "website": "", "notes": "",
}

VALID_STEPS = ["organisation", "sites", "staff", "equipment", "suppliers", "contracts", "review"]
VALID_TIERS = ["starter", "pro", "enterprise"]
VALID_ROLES = ["owner", "manager", "maintenance", "viewer"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_master_admin(user: dict) -> None:
    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
    if user.get("email") != master_email and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin access required")


def _safe_packet_public(packet: Dict) -> Dict:
    """Remove internal fields before exposing to public form."""
    return {
        k: v for k, v in packet.items()
        if k not in ("_id", "created_by", "created_by_name", "provisioned_organization_id")
    }


# ── CRM Prefill ───────────────────────────────────────────────────

def _prefill_org_from_crm(company: Dict) -> Dict:
    """Organisation block prefilled from a CRM company."""
    addr = company.get("address", {}) or {}
    return {
        **EMPTY_ORG,
        "legal_name": company.get("legal_name") or company.get("name", ""),
        "trading_name": company.get("name", ""),
        "vat_number": company.get("vat_number", ""),
        "company_number": company.get("registration_number", ""),
        "billing_address_line1": addr.get("line1", "") or company.get("address_line1", ""),
        "billing_address_line2": addr.get("line2", "") or company.get("address_line2", ""),
        "billing_city": addr.get("city", "") or company.get("city", ""),
        "billing_postcode": addr.get("postcode", "") or company.get("postcode", ""),
        "billing_country": addr.get("country", "") or company.get("country", "United Kingdom"),
        "primary_contact_email": company.get("email", ""),
        "primary_contact_phone": company.get("phone", ""),
        "website": company.get("website", ""),
    }


async def _prefill_staff_from_crm(company: Dict, company_id: str) -> List[Dict]:
    """Staff list prefilled from CRM contacts (+ primary company contact)."""
    contacts = await db.crm_contacts.find({"company_id": company_id}, {"_id": 0}).to_list(50)
    staff: List[Dict] = []
    for c in contacts:
        email = (c.get("email") or "").strip().lower()
        if not email:
            continue
        staff.append({
            "full_name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "email": email, "phone": c.get("phone", ""),
            "role": "manager", "default_site_index": 0,
        })
    if company.get("email") and not any(s["email"] == company["email"].lower() for s in staff):
        staff.insert(0, {
            "full_name": company.get("contact_name", "") or "Primary Contact",
            "email": company["email"].lower(),
            "phone": company.get("phone", ""),
            "role": "owner", "default_site_index": 0,
        })
    return staff


async def _prefill_sites_from_crm(company_id: str) -> List[Dict]:
    """Sites prefilled from CRM sites."""
    sites_cur = await db.crm_sites.find({"company_id": company_id}, {"_id": 0}).to_list(50)
    return [{
        "name": s.get("name", ""),
        "address_line1": s.get("address_line1", ""), "address_line2": s.get("address_line2", ""),
        "city": s.get("city", ""), "postcode": s.get("postcode", ""),
        "square_footage": s.get("square_footage", 0),
        "operating_hours": s.get("operating_hours", ""),
        "on_site_contact_name": s.get("contact_name", ""),
        "on_site_contact_phone": s.get("contact_phone", ""),
    } for s in sites_cur]


async def _prefill_from_crm(company_id: str) -> Dict[str, Any]:
    """Build initial packet data from an existing CRM company + related contacts/sites."""
    company = await db.crm_companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        return {}
    return {
        "organisation": _prefill_org_from_crm(company),
        "sites": await _prefill_sites_from_crm(company_id),
        "staff": await _prefill_staff_from_crm(company, company_id),
        "equipment": [], "suppliers": [], "contracts": [],
        "crm_company_id": company_id,
        "crm_company_name": company.get("name", ""),
    }


# ── Master Admin Endpoints ────────────────────────────────────────

def _validate_create_packet_body(body: Dict) -> tuple[str, bool, int]:
    """Extract + validate the tier/trial fields; raise 400 on invalid."""
    target_tier = (body.get("target_tier") or "pro").lower()
    if target_tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"target_tier must be one of {VALID_TIERS}")
    is_trial = bool(body.get("is_trial", False))
    trial_duration_days = int(body.get("trial_duration_days", 14))
    if is_trial and (trial_duration_days < 1 or trial_duration_days > 90):
        raise HTTPException(status_code=400, detail="trial_duration_days must be between 1 and 90")
    return target_tier, is_trial, trial_duration_days


def _build_empty_packet(packet_id: str, user: dict, target_tier: str, is_trial: bool,
                         trial_duration_days: int, prefill: Dict, body: Dict) -> Dict:
    """Assemble the draft packet document from validated input + prefill data."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    return {
        "id": packet_id, "token": token, "status": "draft",
        "target_tier": target_tier, "is_trial": is_trial,
        "trial_duration_days": trial_duration_days if is_trial else None,
        "customer_display_name": body.get("customer_display_name", "") or prefill.get("crm_company_name", ""),
        "created_by": user["id"],
        "created_by_name": user.get("full_name", user.get("email", "Master Admin")),
        "created_at": _now(), "updated_at": _now(),
        "submitted_at": None, "provisioned_at": None, "expires_at": expires_at,
        "current_step": "organisation",
        "organisation": prefill.get("organisation", dict(EMPTY_ORG)),
        "sites": prefill.get("sites", []), "staff": prefill.get("staff", []),
        "equipment": prefill.get("equipment", []), "suppliers": prefill.get("suppliers", []),
        "contracts": prefill.get("contracts", []),
        "crm_company_id": prefill.get("crm_company_id"),
        "crm_company_name": prefill.get("crm_company_name"),
        "provisioned_organization_id": None, "review_notes": "",
    }


@router.post("/onboarding-packets")
async def create_packet(body: Dict[str, Any], user: dict = Depends(get_current_user)) -> Dict:
    """Create a new packet. Optionally prefill from CRM company."""
    _require_master_admin(user)
    target_tier, is_trial, trial_duration_days = _validate_create_packet_body(body)

    crm_company_id = body.get("crm_company_id") or None
    prefill = await _prefill_from_crm(crm_company_id) if crm_company_id else {}
    packet_id = str(uuid.uuid4())
    packet = _build_empty_packet(packet_id, user, target_tier, is_trial,
                                 trial_duration_days, prefill, body)
    await db.onboarding_packets.insert_one(packet)

    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    share_url = f"{frontend_url}/onboarding/{packet['token']}" if frontend_url else f"/onboarding/{packet['token']}"
    result = _safe_packet_public(packet)
    result["share_url"] = share_url
    return result


@router.get("/onboarding-packets")
async def list_packets(user: dict = Depends(get_current_user),
                       status: Optional[str] = None) -> Dict:
    _require_master_admin(user)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    packets = await db.onboarding_packets.find(
        query, {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    for p in packets:
        p["share_url"] = f"{frontend_url}/onboarding/{p['token']}" if frontend_url else f"/onboarding/{p['token']}"
        p["counts"] = {
            "sites": len(p.get("sites", [])),
            "staff": len(p.get("staff", [])),
            "equipment": len(p.get("equipment", [])),
            "suppliers": len(p.get("suppliers", [])),
            "contracts": len(p.get("contracts", [])),
        }
    return {"packets": packets, "count": len(packets)}


def _parse_iso(value: str | None, fallback: datetime | None = None) -> datetime | None:
    """Parse an ISO-8601 timestamp; return fallback (or None) on failure."""
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return fallback


def _collect_provision_times(packets: List[dict]) -> tuple[List[float], List[float]]:
    """For 'provisioned' packets only, return (created→provisioned hours, submitted→provisioned hours)."""
    provision_times: List[float] = []
    time_in_submitted: List[float] = []
    for p in packets:
        if p.get("status") != "provisioned" or not p.get("provisioned_at"):
            continue
        created = _parse_iso(p.get("created_at"))
        provisioned = _parse_iso(p.get("provisioned_at"))
        if created and provisioned:
            provision_times.append((provisioned - created).total_seconds() / 3600.0)
        submitted = _parse_iso(p.get("submitted_at"))
        if submitted and provisioned:
            time_in_submitted.append((provisioned - submitted).total_seconds() / 3600.0)
    return provision_times, time_in_submitted


def _find_oldest_unprovisioned(packets: List[dict], now: datetime) -> dict | None:
    """Pick the single oldest draft/submitted packet, return its summary dict."""
    oldest = None
    for p in packets:
        status = p.get("status", "draft")
        if status not in ("draft", "submitted"):
            continue
        created = _parse_iso(p.get("created_at"), now)
        age_hours = (now - created).total_seconds() / 3600.0
        if oldest is None or age_hours > oldest["age_hours"]:
            oldest = {
                "id": p.get("id"),
                "customer_display_name": p.get("customer_display_name") or (p.get("organisation") or {}).get("legal_name", ""),
                "status": status,
                "age_hours": round(age_hours, 1),
                "created_at": p.get("created_at"),
            }
    return oldest


def _recent_counts(packets: List[dict], now: datetime) -> tuple[int, int, int]:
    """Return (created_7d, created_30d, provisioned_7d) window counts."""
    seven = now - timedelta(days=7)
    thirty = now - timedelta(days=30)
    created_7d = created_30d = provisioned_7d = 0
    for p in packets:
        c = _parse_iso(p.get("created_at"))
        if c:
            if c >= thirty:
                created_30d += 1
            if c >= seven:
                created_7d += 1
        if p.get("status") == "provisioned":
            pt = _parse_iso(p.get("provisioned_at"))
            if pt and pt >= seven:
                provisioned_7d += 1
    return created_7d, created_30d, provisioned_7d


@router.get("/onboarding-packets/analytics/summary")
async def onboarding_analytics(user: dict = Depends(get_current_user)) -> Dict:
    """Return onboarding funnel metrics for the Master Admin Overview."""
    _require_master_admin(user)

    packets = await db.onboarding_packets.find({}, {"_id": 0}).to_list(2000)
    now = datetime.now(timezone.utc)

    by_status: Dict[str, int] = {}
    for p in packets:
        by_status[p.get("status", "draft")] = by_status.get(p.get("status", "draft"), 0) + 1

    provision_times, time_in_submitted = _collect_provision_times(packets)
    oldest_unprovisioned = _find_oldest_unprovisioned(packets, now)
    created_7d, created_30d, provisioned_7d = _recent_counts(packets, now)

    avg_provision_hours = round(sum(provision_times) / len(provision_times), 1) if provision_times else 0
    avg_review_hours = round(sum(time_in_submitted) / len(time_in_submitted), 1) if time_in_submitted else 0

    return {
        "total": len(packets),
        "by_status": by_status,
        "draft": by_status.get("draft", 0),
        "submitted": by_status.get("submitted", 0),
        "provisioned": by_status.get("provisioned", 0),
        "rejected": by_status.get("rejected", 0),
        "avg_provision_hours": avg_provision_hours,
        "avg_review_hours": avg_review_hours,
        "created_7d": created_7d,
        "created_30d": created_30d,
        "provisioned_7d": provisioned_7d,
        "oldest_unprovisioned": oldest_unprovisioned,
    }


@router.get("/onboarding-packets/{packet_id}")
async def get_packet(packet_id: str, user: dict = Depends(get_current_user)) -> Dict:
    _require_master_admin(user)
    packet = await db.onboarding_packets.find_one({"id": packet_id}, {"_id": 0})
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found")
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    packet["share_url"] = f"{frontend_url}/onboarding/{packet['token']}" if frontend_url else f"/onboarding/{packet['token']}"
    return packet


@router.put("/onboarding-packets/{packet_id}")
async def edit_packet(packet_id: str, body: Dict[str, Any], user: dict = Depends(get_current_user)) -> Dict:
    """Master admin can inline-edit any packet field prior to provisioning."""
    _require_master_admin(user)
    allowed = {"organisation", "sites", "staff", "equipment", "suppliers",
               "contracts", "target_tier", "customer_display_name", "review_notes"}
    update = {k: v for k, v in body.items() if k in allowed}
    update["updated_at"] = _now()
    res = await db.onboarding_packets.update_one({"id": packet_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Packet not found")
    return await get_packet(packet_id, user)


@router.delete("/onboarding-packets/{packet_id}")
async def delete_packet(packet_id: str, user: dict = Depends(get_current_user)) -> Dict:
    _require_master_admin(user)
    packet = await db.onboarding_packets.find_one({"id": packet_id}, {"_id": 0, "status": 1})
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found")
    if packet.get("status") == "provisioned":
        raise HTTPException(status_code=400, detail="Cannot delete a provisioned packet")
    await db.onboarding_packets.delete_one({"id": packet_id})
    return {"success": True}


# ── Public (customer-facing) Endpoints ────────────────────────────

async def _get_packet_by_token(token: str) -> Dict:
    packet = await db.onboarding_packets.find_one({"token": token}, {"_id": 0})
    if not packet:
        raise HTTPException(status_code=404, detail="Onboarding link not found or expired")
    # Expiry check
    try:
        exp = datetime.fromisoformat(packet["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(status_code=410, detail="Onboarding link has expired")
    except HTTPException:
        raise
    except Exception:
        pass
    if packet.get("status") == "provisioned":
        raise HTTPException(status_code=410, detail="This onboarding has already been completed")
    return packet


@router.get("/onboarding/public/{token}")
async def public_get(token: str, request: Request) -> Dict:
    # IP-scoped rate limit — prevents token-guessing brute force.
    from utils.security_plus import rate_limit_async
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"onboarding_token_ip:{ip}", max_requests=60, window_seconds=300)
    packet = await _get_packet_by_token(token)
    return _safe_packet_public(packet)


@router.put("/onboarding/public/{token}")
async def public_save(token: str, body: Dict[str, Any]) -> Dict:
    """Auto-save draft content from the customer's browser."""
    packet = await _get_packet_by_token(token)
    if packet.get("status") not in ("draft", "submitted"):
        raise HTTPException(status_code=400, detail="Packet is no longer editable")

    allowed = {"organisation", "sites", "staff", "equipment", "suppliers", "contracts", "current_step"}
    update = {k: v for k, v in body.items() if k in allowed}
    update["updated_at"] = _now()
    await db.onboarding_packets.update_one({"token": token}, {"$set": update})
    refreshed = await db.onboarding_packets.find_one({"token": token}, {"_id": 0})
    return _safe_packet_public(refreshed)


@router.post("/onboarding/public/{token}/submit")
async def public_submit(token: str) -> Dict:
    packet = await _get_packet_by_token(token)
    if packet.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Packet already submitted")

    errors = _validate_packet(packet)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    await db.onboarding_packets.update_one(
        {"token": token},
        {"$set": {"status": "submitted", "submitted_at": _now(), "updated_at": _now()}}
    )
    return {"success": True, "message": "Submitted for review. Your account manager will be in touch."}


def _validate_org_block(packet: Dict) -> List[str]:
    """Core organization-level required fields."""
    errors: List[str] = []
    org = packet.get("organisation", {}) or {}
    if not org.get("legal_name"):
        errors.append("Organisation: legal name is required")
    if not org.get("billing_postcode"):
        errors.append("Organisation: billing postcode is required")
    if not org.get("primary_contact_email"):
        errors.append("Organisation: primary contact email is required")
    return errors


def _validate_sites_block(packet: Dict) -> List[str]:
    """At-least-one-site + per-site name/postcode."""
    errors: List[str] = []
    sites = packet.get("sites", []) or []
    if not sites:
        errors.append("At least one site is required")
    for i, s in enumerate(sites):
        if not s.get("name"):
            errors.append(f"Site #{i+1}: name is required")
        if not s.get("postcode"):
            errors.append(f"Site #{i+1}: postcode is required")
    return errors


def _validate_staff_member(i: int, member: Dict, emails_seen: set[str]) -> List[str]:
    """Validate a single staff entry; append discovered email to emails_seen."""
    errs: List[str] = []
    email = (member.get("email") or "").strip().lower()
    if not email or "@" not in email:
        errs.append(f"Staff #{i+1}: valid email is required")
    elif email in emails_seen:
        errs.append(f"Staff #{i+1}: duplicate email '{email}'")
    else:
        emails_seen.add(email)
    if not member.get("full_name"):
        errs.append(f"Staff #{i+1}: full name is required")
    return errs


def _validate_staff_block(packet: Dict) -> List[str]:
    """At-least-one-staff + at-least-one-owner + unique emails + name check."""
    errors: List[str] = []
    staff = packet.get("staff", []) or []
    if not staff:
        errors.append("At least one staff member is required")
    if not any((m.get("role") or "").lower() == "owner" for m in staff):
        errors.append("At least one staff member must have the 'owner' role")

    emails_seen: set[str] = set()
    for i, m in enumerate(staff):
        errors.extend(_validate_staff_member(i, m, emails_seen))
    return errors


def _validate_packet(packet: Dict) -> List[str]:
    """Run all three hard-validation blocks; return aggregated errors."""
    return _validate_org_block(packet) + _validate_sites_block(packet) + _validate_staff_block(packet)


# ── Provisioning ──────────────────────────────────────────────────

def _build_trial_fields(is_trial: bool, trial_days: int, now_dt: datetime) -> Dict[str, Any]:
    """Construct the trial-tracking fields for a newly-provisioned org."""
    if not is_trial:
        return {}
    trial_ends_at = now_dt + timedelta(days=trial_days)
    trial_suspends_at = trial_ends_at + timedelta(days=30)  # 30-day grace
    return {
        "is_trial": True,
        "trial_status": "active",
        "trial_started_at": now_dt.isoformat(),
        "trial_ends_at": trial_ends_at.isoformat(),
        "trial_suspends_at": trial_suspends_at.isoformat(),
        "trial_duration_days": trial_days,
        "trial_reminders_sent": [],
        "trial_extended_by_days": 0,
    }


async def _create_organization(packet: Dict, packet_id: str) -> str:
    """Insert the top-level organization record; return its id."""
    org_id = str(uuid.uuid4())
    org = packet["organisation"]
    is_trial = bool(packet.get("is_trial"))
    trial_days = int(packet.get("trial_duration_days") or 14) if is_trial else 0
    now_dt = datetime.now(timezone.utc)
    await db.organizations.insert_one({
        "id": org_id,
        "name": org.get("trading_name") or org.get("legal_name"),
        "legal_name": org.get("legal_name"),
        "account_type": "gymaxis",
        "subscription_tier": packet.get("target_tier", "pro"),
        "vat_number": org.get("vat_number", ""),
        "company_number": org.get("company_number", ""),
        "billing_address": {
            "line1": org.get("billing_address_line1", ""), "line2": org.get("billing_address_line2", ""),
            "city": org.get("billing_city", ""), "postcode": org.get("billing_postcode", ""),
            "country": org.get("billing_country", "United Kingdom"),
        },
        "primary_contact": {
            "name": org.get("primary_contact_name", ""), "email": org.get("primary_contact_email", ""),
            "phone": org.get("primary_contact_phone", ""),
        },
        "website": org.get("website", ""),
        "status": "active",
        "onboarded_via_packet": packet_id,
        "created_at": _now(),
        **_build_trial_fields(is_trial, trial_days, now_dt),
    })
    return org_id


async def _link_or_create_crm_company(packet: Dict, org_id: str, packet_id: str) -> None:
    """Auto-create a CRM company and link it to the new org, or link an existing one."""
    crm_company_id = packet.get("crm_company_id")
    org = packet["organisation"]
    is_trial = bool(packet.get("is_trial"))
    if crm_company_id:
        await db.crm_companies.update_one(
            {"id": crm_company_id},
            {"$set": {"linked_organization_id": org_id, "status": "trial" if is_trial else "customer"}}
        )
        return
    crm_company_id = str(uuid.uuid4())
    await db.crm_companies.insert_one({
        "id": crm_company_id,
        "name": org.get("trading_name") or org.get("legal_name"),
        "legal_name": org.get("legal_name"),
        "vat_number": org.get("vat_number", ""),
        "registration_number": org.get("company_number", ""),
        "email": org.get("primary_contact_email", ""),
        "phone": org.get("primary_contact_phone", ""),
        "website": org.get("website", ""),
        "address": {
            "line1": org.get("billing_address_line1", ""), "line2": org.get("billing_address_line2", ""),
            "city": org.get("billing_city", ""), "postcode": org.get("billing_postcode", ""),
            "country": org.get("billing_country", "United Kingdom"),
        },
        "linked_organization_id": org_id,
        "source": "onboarding_packet_trial" if is_trial else "onboarding_packet",
        "status": "trial" if is_trial else "customer",
        "created_at": _now(),
        "created_from_packet": packet_id,
    })
    logger.info(f"[Provision] Auto-created CRM company {crm_company_id} for org {org_id}")


async def _create_sites(packet: Dict, org_id: str, created: Dict[str, List[str]]) -> Dict[int, str]:
    """Insert site records and populate the created.site_ids list. Returns index→id map."""
    site_ids_by_index: Dict[int, str] = {}
    for i, s in enumerate(packet.get("sites", [])):
        site_id = str(uuid.uuid4())
        await db.sites.insert_one({
            "id": site_id, "organization_id": org_id,
            "name": s.get("name"),
            "address_line1": s.get("address_line1", ""), "address_line2": s.get("address_line2", ""),
            "city": s.get("city", ""), "postcode": s.get("postcode", ""),
            "square_footage": s.get("square_footage", 0),
            "operating_hours": s.get("operating_hours", ""),
            "contact_name": s.get("on_site_contact_name", ""),
            "contact_phone": s.get("on_site_contact_phone", ""),
            "created_at": _now(),
        })
        site_ids_by_index[i] = site_id
        created["site_ids"].append(site_id)
    return site_ids_by_index


async def _send_staff_magic_link(email: str, full_name: str, user_id: str) -> None:
    """Create a 14-day password-setup token and email the magic link."""
    reset_token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": reset_token, "user_id": user_id, "email": email,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "used": False, "created_at": _now(), "purpose": "onboarding_setup",
    })
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    setup_url = f"{frontend_url}/reset-password?token={reset_token}"
    try:
        await send_password_reset_email(email, full_name, setup_url)
    except Exception as e:
        logger.warning(f"[Provision] Welcome email to {email} failed: {e}")


async def _create_staff(packet: Dict, org_id: str, packet_id: str,
                        site_ids_by_index: Dict[int, str], created: Dict[str, List[str]]) -> None:
    """Insert user records for new staff and send onboarding magic-link emails."""
    for m in packet.get("staff", []):
        email = (m.get("email") or "").strip().lower()
        if not email:
            continue
        if await db.users.find_one({"email": email}, {"_id": 0, "id": 1}):
            logger.info(f"[Provision] User {email} already exists — skipping create")
            continue
        user_id = str(uuid.uuid4())
        temp_pwd = secrets.token_urlsafe(24)
        role = (m.get("role") or "manager").lower()
        if role not in VALID_ROLES:
            role = "manager"
        await db.users.insert_one({
            "id": user_id, "email": email,
            "full_name": m.get("full_name", email), "phone": m.get("phone", ""),
            "password": hash_password(temp_pwd), "role": role,
            "organization_id": org_id,
            "default_site_id": site_ids_by_index.get(m.get("default_site_index", 0)),
            "created_at": _now(), "onboarded_via_packet": packet_id,
        })
        created["user_ids"].append(user_id)
        await _send_staff_magic_link(email, m.get("full_name", ""), user_id)


async def _create_equipment(packet: Dict, org_id: str, site_ids_by_index: Dict[int, str],
                            created: Dict[str, List[str]]) -> None:
    for e in packet.get("equipment", []):
        eq_id = str(uuid.uuid4())
        await db.equipment.insert_one({
            "id": eq_id, "organization_id": org_id,
            "site_id": site_ids_by_index.get(e.get("site_index", 0)),
            "name": e.get("name") or f"{e.get('brand', '')} {e.get('model', '')}".strip(),
            "equipment_type": e.get("equipment_type", ""),
            "manufacturer": e.get("brand", ""), "model": e.get("model", ""),
            "serial_number": e.get("serial_number", ""),
            "install_date": e.get("install_date", ""), "warranty_expiry": e.get("warranty_expiry", ""),
            "supplier": e.get("supplier", ""),
            "status": "operational", "created_at": _now(),
        })
        created["equipment_ids"].append(eq_id)


async def _create_suppliers(packet: Dict, org_id: str, created: Dict[str, List[str]]) -> None:
    # Lazy import to avoid circular dep with routes.supplier_portal (which
    # imports from utils that back-reference onboarding in tests).
    from routes.supplier_portal import send_supplier_welcome_email

    org_doc = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1},
    ) or {}
    org_name = org_doc.get("name")

    for s in packet.get("suppliers", []):
        sup_id = str(uuid.uuid4())
        # Normalise to `email` (the CRUD schema) while keeping `contact_email`
        # around so legacy readers / packet review UI keep working.
        contact_email = (s.get("contact_email") or s.get("email") or "").strip()
        contact_person = s.get("contact_person") or s.get("name")
        supplier_doc = {
            "id": sup_id, "organization_id": org_id,
            "name": s.get("name"),
            "email": contact_email,
            "contact_email": contact_email,
            "contact_person": contact_person,
            "phone": s.get("phone", ""),
            "categories": s.get("categories", []),
            "notes": s.get("notes", ""),
            "created_at": _now(),
        }
        await db.suppliers.insert_one(supplier_doc)
        supplier_doc.pop("_id", None)
        created["supplier_ids"].append(sup_id)

        # Fire-and-forget welcome email. `send_supplier_welcome_email` itself
        # skips Pulse Lite and missing-email cases, so onboarding stays safe.
        if contact_email:
            sent = await send_supplier_welcome_email(supplier_doc, org_id, org_name)
            if sent:
                await db.suppliers.update_one(
                    {"id": sup_id},
                    {"$set": {"welcome_email_sent_at": _now()}},
                )


async def _create_contracts(packet: Dict, org_id: str, packet_id: str, created: Dict[str, List[str]]) -> None:
    for c in packet.get("contracts", []):
        ct_id = str(uuid.uuid4())
        await db.crm_contracts.insert_one({
            "id": ct_id, "organization_id": org_id, "company_id": packet.get("crm_company_id"),
            "contract_number": c.get("contract_number"), "provider": c.get("provider"),
            "tier": c.get("tier", "standard"),
            "start_date": c.get("start_date"), "end_date": c.get("end_date"),
            "annual_value": c.get("annual_value", 0),
            "sla": {"response_hours": c.get("sla_response_hours", 24),
                    "resolution_hours": c.get("sla_resolution_hours", 72)},
            "status": "active",
            "imported_from_packet": packet_id,
            "created_at": _now(),
        })
        created["contract_ids"].append(ct_id)


async def _rollback_provisioning(created: Dict[str, List[str]]) -> None:
    """Best-effort cascade delete of whatever _was_ provisioned before a failure."""
    deletions = [
        (db.organizations, created["organization_ids"], None),
        (db.sites, created["site_ids"], None),
        (db.users, created["user_ids"], None),
        (db.password_reset_tokens, created["user_ids"], "user_id"),
        (db.equipment, created["equipment_ids"], None),
        (db.suppliers, created["supplier_ids"], None),
        (db.crm_contracts, created["contract_ids"], None),
    ]
    for coll, ids, key in deletions:
        if ids:
            await coll.delete_many({(key or "id"): {"$in": ids}})


@router.post("/onboarding-packets/{packet_id}/provision")
async def provision_packet(packet_id: str, user: dict = Depends(get_current_user), request: Request = None) -> Dict:
    """Atomically create org + sites + users + equipment + suppliers + contracts."""
    _require_master_admin(user)
    packet = await db.onboarding_packets.find_one({"id": packet_id}, {"_id": 0})
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found")
    if packet.get("status") == "provisioned":
        raise HTTPException(status_code=400, detail="Packet already provisioned")

    errors = _validate_packet(packet)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    created: Dict[str, List[str]] = {
        "organization_ids": [], "site_ids": [], "user_ids": [],
        "equipment_ids": [], "supplier_ids": [], "contract_ids": [],
    }

    try:
        org_id = await _create_organization(packet, packet_id)
        created["organization_ids"].append(org_id)
        await _link_or_create_crm_company(packet, org_id, packet_id)

        site_ids_by_index = await _create_sites(packet, org_id, created)
        await _create_staff(packet, org_id, packet_id, site_ids_by_index, created)
        await _create_equipment(packet, org_id, site_ids_by_index, created)
        await _create_suppliers(packet, org_id, created)
        await _create_contracts(packet, org_id, packet_id, created)

        await db.onboarding_packets.update_one(
            {"id": packet_id},
            {"$set": {
                "status": "provisioned", "provisioned_at": _now(),
                "provisioned_organization_id": org_id, "provisioned_by": user["id"],
                "provision_summary": {k: len(v) for k, v in created.items()},
                "updated_at": _now(),
            }}
        )
        logger.info(f"[Provision] Packet {packet_id} → org {org_id} " +
                    ", ".join(f"{k}={len(v)}" for k, v in created.items()))
        # P2.15 fail-closed audit — packet provisioning is a high-value write.
        from utils.security_plus import audit_required
        await audit_required("security_audit_log", {
            "event": "onboarding.packet.provisioned",
            "actor_id": user["id"], "actor_email": user.get("email"),
            "packet_id": packet_id, "org_id": org_id,
            "summary": {k: len(v) for k, v in created.items()},
        })
        return {"success": True, "organization_id": org_id,
                "summary": {k: len(v) for k, v in created.items()}}

    except Exception as e:
        logger.error(f"[Provision] Failed for packet {packet_id}: {e}")
        await _rollback_provisioning(created)
        raise HTTPException(status_code=500, detail=f"Provisioning failed and was rolled back: {str(e)[:200]}")


# ── Reject ────────────────────────────────────────────────────────

@router.post("/onboarding-packets/{packet_id}/reject")
async def reject_packet(packet_id: str, body: Dict[str, Any], user: dict = Depends(get_current_user)) -> Dict:
    _require_master_admin(user)
    reason = body.get("reason", "")
    res = await db.onboarding_packets.update_one(
        {"id": packet_id},
        {"$set": {"status": "rejected", "review_notes": reason, "updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Packet not found")
    return {"success": True}



# ── Ready-to-Go Preview ───────────────────────────────────────────

def _warn_org(org: Dict) -> List[Dict[str, str]]:
    """Soft org-level warnings (missing optional metadata)."""
    w: List[Dict[str, str]] = []
    if not org.get("trading_name"):
        w.append({"field": "organisation", "message": "No trading name — will use legal name as display name"})
    if not org.get("vat_number"):
        w.append({"field": "organisation", "message": "VAT number missing — you can add this later from settings"})
    if not org.get("primary_contact_phone"):
        w.append({"field": "organisation", "message": "No primary contact phone — recommended for urgent outreach"})
    return w


def _warn_sites(sites: List[Dict]) -> List[Dict[str, str]]:
    """Site-level warnings (street address / on-site contact)."""
    w: List[Dict[str, str]] = []
    for i, s in enumerate(sites):
        label = s.get("name") or i + 1
        if not s.get("address_line1"):
            w.append({"field": f"site_{i}", "message": f"Site '{label}' has no street address"})
        if not s.get("on_site_contact_name"):
            w.append({"field": f"site_{i}", "message": f"Site '{label}' has no on-site contact"})
    return w


def _warn_staff(staff: List[Dict]) -> List[Dict[str, str]]:
    """Staff-level warnings (default site + phone)."""
    w: List[Dict[str, str]] = []
    for i, m in enumerate(staff):
        role = (m.get("role") or "").lower()
        if role in ("manager", "maintenance") and m.get("default_site_index") is None:
            w.append({"field": f"staff_{i}", "message": f"{m.get('full_name')} has no default site assigned"})
        if not m.get("phone"):
            w.append({"field": f"staff_{i}", "message": f"{m.get('full_name')} has no phone number"})
    return w


def _warn_equipment(equipment: List[Dict]) -> List[Dict[str, str]]:
    """Equipment coverage warnings."""
    w: List[Dict[str, str]] = []
    eq_no_serial = sum(1 for e in equipment if not (e.get("serial_number") or "").strip())
    if eq_no_serial:
        w.append({"field": "equipment", "message": f"{eq_no_serial} of {len(equipment)} equipment items missing serial numbers"})
    if len(equipment) == 0:
        w.append({"field": "equipment", "message": "No equipment added — you can import these later, but it means no fault tracking at day one"})
    return w


def _validate_packet_warnings(packet: Dict) -> List[Dict[str, str]]:
    """Soft warnings — nice-to-fix but won't block provisioning."""
    warnings = (
        _warn_org(packet.get("organisation", {}) or {})
        + _warn_sites(packet.get("sites", []) or [])
        + _warn_staff(packet.get("staff", []) or [])
        + _warn_equipment(packet.get("equipment", []) or [])
    )
    if len(packet.get("suppliers", []) or []) == 0:
        warnings.append({"field": "suppliers", "message": "No suppliers added — faster engineer dispatch requires at least one supplier"})
    return warnings


async def _check_duplicate_emails_in_system(emails: List[str]) -> List[str]:
    """Check which staff emails already exist in the users collection."""
    if not emails:
        return []
    existing = await db.users.find(
        {"email": {"$in": emails}},
        {"_id": 0, "email": 1}
    ).to_list(100)
    return [u["email"] for u in existing]


def _role_breakdown(staff: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for m in staff:
        role = (m.get("role") or "manager").lower()
        counts[role] = counts.get(role, 0) + 1
    return counts


def _equipment_per_site(equipment: List[Dict]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for e in equipment:
        idx = e.get("site_index", 0)
        counts[idx] = counts.get(idx, 0) + 1
    return counts


def _provision_plan_org_block(packet: Dict, org: Dict) -> Dict:
    """Organization summary for the preview plan."""
    return {
        "name": org.get("trading_name") or org.get("legal_name") or "(unnamed)",
        "legal_name": org.get("legal_name", ""),
        "postcode": org.get("billing_postcode", ""),
        "primary_contact": org.get("primary_contact_email", ""),
        "tier": packet.get("target_tier"),
        "is_trial": bool(packet.get("is_trial")),
        "trial_duration_days": packet.get("trial_duration_days"),
    }


def _sites_breakdown(sites: list, equipment: list) -> list:
    """Build per-site summary rows (name, postcode, equipment count)."""
    eq_by_site = _equipment_per_site(equipment)
    return [{
        "name": s.get("name") or f"Site #{i+1}",
        "postcode": s.get("postcode", ""),
        "equipment_count": eq_by_site.get(i, 0),
    } for i, s in enumerate(sites)]


def _provision_counts(packet: Dict) -> Dict[str, int]:
    """Count sizes for each provisioning bucket."""
    return {
        "sites": len(packet.get("sites") or []),
        "staff": len(packet.get("staff") or []),
        "equipment": len(packet.get("equipment") or []),
        "suppliers": len(packet.get("suppliers") or []),
        "contracts": len(packet.get("contracts") or []),
    }


def _provision_plan_summary(packet: Dict) -> Dict[str, Any]:
    """Structured summary of what provisioning will create."""
    org = packet.get("organisation", {}) or {}
    sites = packet.get("sites", []) or []
    staff = packet.get("staff", []) or []
    equipment = packet.get("equipment", []) or []

    return {
        "organization": _provision_plan_org_block(packet, org),
        "counts": _provision_counts(packet),
        "role_breakdown": _role_breakdown(staff),
        "sites_breakdown": _sites_breakdown(sites, equipment),
        "will_send_magic_links_to": [m.get("email") for m in staff if m.get("email")],
        "crm_action": "link" if packet.get("crm_company_id") else "auto_create",
    }


@router.get("/onboarding-packets/{packet_id}/preview")
async def preview_packet(packet_id: str, user: dict = Depends(get_current_user)) -> Dict:
    """
    Pre-provision preview: shows exactly what will be created, plus any
    validation errors (blocking) and warnings (advisory).
    """
    _require_master_admin(user)
    packet = await db.onboarding_packets.find_one({"id": packet_id}, {"_id": 0})
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found")

    errors = _validate_packet(packet)
    warnings = _validate_packet_warnings(packet)
    plan = _provision_plan_summary(packet)

    # Check for email collisions with existing users
    staff_emails = [
        (m.get("email") or "").strip().lower()
        for m in (packet.get("staff") or [])
        if m.get("email")
    ]
    conflicts = await _check_duplicate_emails_in_system(staff_emails)
    if conflicts:
        warnings.append({
            "field": "staff_emails",
            "message": f"{len(conflicts)} staff email{'s' if len(conflicts) != 1 else ''} already exist in the system — they will be skipped during provisioning: {', '.join(conflicts[:5])}{'…' if len(conflicts) > 5 else ''}"
        })

    return {
        "ready": len(errors) == 0 and packet.get("status") != "provisioned",
        "already_provisioned": packet.get("status") == "provisioned",
        "errors": errors,
        "warnings": warnings,
        "plan": plan,
        "conflicts": conflicts,
    }


# ── Send invitation email ─────────────────────────────────────────

def _resolve_invite_recipient(packet: Dict, body: Dict) -> tuple[str, str]:
    """Pick the recipient email + name from the request body, falling back to packet contact."""
    override_email = (body.get("email") or "").strip().lower()
    org_block = packet.get("organisation") or {}
    recipient = override_email or (org_block.get("primary_contact_email") or "").strip().lower()
    if not recipient or "@" not in recipient:
        raise HTTPException(status_code=400,
                            detail="No recipient email — provide one or set the packet's primary contact email")
    recipient_name = body.get("recipient_name") or org_block.get("primary_contact_name") or ""
    return recipient, recipient_name


def _compute_invite_deadline_days(packet: Dict) -> int:
    """Days until the packet's share token expires (min 1, default 14)."""
    try:
        exp = datetime.fromisoformat(packet["expires_at"].replace("Z", "+00:00"))
        return max(1, (exp - datetime.now(timezone.utc)).days)
    except Exception:
        return 14


def _invite_share_url(packet: Dict) -> str:
    """Build the customer-facing share URL for the packet invite."""
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    token = packet["token"]
    return f"{frontend_url}/onboarding/{token}" if frontend_url else f"/onboarding/{token}"


def _invite_customer_name(packet: Dict) -> str:
    """Display name for the customer in the invite email."""
    return (packet.get("customer_display_name")
            or (packet.get("organisation") or {}).get("legal_name")
            or "")


async def _record_invite_send(packet_id: str, packet: Dict, recipient: str,
                              user: dict, sender_name: str) -> int:
    """Append a send record to the packet and return the new send count."""
    sends = (packet.get("email_sends") or []) + [{
        "sent_at": _now(), "sent_to": recipient,
        "sent_by": user["id"], "sent_by_name": sender_name,
    }]
    await db.onboarding_packets.update_one(
        {"id": packet_id},
        {"$set": {"last_sent_at": _now(), "last_sent_to": recipient,
                  "email_sends": sends, "updated_at": _now()}}
    )
    return len(sends)


@router.post("/onboarding-packets/{packet_id}/send-email")
async def send_packet_invite(packet_id: str, body: Dict[str, Any], user: dict = Depends(get_current_user)) -> Dict:
    """Send a branded onboarding invite email to the customer's primary contact."""
    _require_master_admin(user)
    packet = await db.onboarding_packets.find_one({"id": packet_id}, {"_id": 0})
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found")
    if packet.get("status") == "provisioned":
        raise HTTPException(status_code=400, detail="Packet already provisioned")

    recipient, recipient_name = _resolve_invite_recipient(packet, body)
    sender_name = user.get("full_name") or user.get("email") or "Your GymAxis account manager"

    sent = await send_onboarding_invite_email(
        email=recipient, recipient_name=recipient_name,
        customer_name=_invite_customer_name(packet),
        share_url=_invite_share_url(packet),
        sender_name=sender_name,
        deadline_days=_compute_invite_deadline_days(packet),
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Email delivery failed — check Resend config")

    send_count = await _record_invite_send(packet_id, packet, recipient, user, sender_name)
    return {"success": True, "sent_to": recipient, "send_count": send_count}


# ── CRM Companies helper (for packet creation dropdown) ───────────

@router.get("/onboarding-packets/crm/companies")
async def list_crm_companies_for_prefill(user: dict = Depends(get_current_user)) -> Dict:
    """Lightweight company list for Master Admin packet-creation autocomplete."""
    _require_master_admin(user)
    companies = await db.crm_companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, "email": 1, "legal_name": 1}
    ).sort("name", 1).to_list(500)
    return {"companies": companies}
