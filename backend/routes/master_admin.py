"""
Master Admin Routes — Full platform control centre.
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import asyncio
import logging
import os
import secrets
import uuid

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_onboard_date(date_str: str) -> str:
    """Convert dd/mm/yyyy to ISO format for storage."""
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return date_str


# ─────────────────────────────────────────────────────────────────
# Iter 215en — Structured address helpers (Address 1*, Address 2,
# Address 3, City, County, Post code, Country). Everything that
# accepts the legacy single-line `address` continues to work; when
# only the structured fields are supplied we compose the legacy
# field from them so downstream Sage / Sicon outbox payloads keep
# working unchanged.
# ─────────────────────────────────────────────────────────────────

ADDRESS_FIELDS = (
    "address_line1", "address_line2", "address_line3",
    "city", "county", "postcode", "country",
)


def compose_legacy_address(payload: dict) -> str:
    """Compose a single-line address from the structured shape.

    Used to populate the legacy `address` field on org / site rows so
    Sage / Sicon outbox payloads keep working without code changes.
    Returns the existing `address` if no structured fields are present.
    """
    parts = [str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    return str(payload.get("address") or "").strip()


def merge_address(payload: dict) -> dict:
    """Pluck the structured address fields from `payload`, ensure the
    legacy `address` is in sync, and return a dict ready to merge into
    a Mongo document. The caller is responsible for picking out the
    keys they actually want to persist."""
    out = {k: str(payload.get(k) or "").strip() for k in ADDRESS_FIELDS}
    if not out["country"]:
        out["country"] = "United Kingdom"
    legacy_explicit = str(payload.get("address") or "").strip()
    composed = compose_legacy_address(payload)
    out["address"] = legacy_explicit or composed
    return out


MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")

# Account types a Pulse Master Admin is allowed to see.
# Mirrors `routes.pulse_master_admin.PULSE_VISIBLE_ACCOUNT_TYPES` — kept inline
# to avoid a circular import.
PULSE_VISIBLE_ACCOUNT_TYPES = ["pulse_pro", "lite", "mod", "full"]


def is_pulse_only(user: dict) -> bool:
    """True when the caller is a Pulse Master Admin (delegated) but NOT the
    GymAxis platform Master Admin. Used to decide whether to scope list /
    edit endpoints to Pulse-visible orgs."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return False
    return bool(user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin")


def require_master_admin(user: dict):
    """Either the GymAxis Master Admin OR a delegated Pulse Master Admin is
    allowed past this gate. Endpoints that need to lock out Pulse admins
    explicitly should call ``require_gymaxis_master_only(user)`` instead.
    """
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


def require_gymaxis_master_only(user: dict):
    """Strict gate — only the GymAxis platform Master Admin (not Pulse admins)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    raise HTTPException(status_code=403, detail="GymAxis master admin access required")


async def assert_org_in_pulse_scope(user: dict, org_id: str) -> dict:
    """If caller is Pulse-only, 404 unless the target org is Pulse-visible.

    Returns the org doc (sans `_id`) so callers can avoid a redundant fetch.
    GymAxis master admins skip the scope check.
    """
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if is_pulse_only(user) and org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def assert_user_in_pulse_scope(user: dict, target_user_id: str) -> None:
    """Pulse-only callers can only mutate users belonging to a Pulse-visible org."""
    if not is_pulse_only(user):
        return
    target = (
        await db.users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
        or await db.crm_users.find_one({"id": target_user_id}, {"_id": 0, "organization_id": 1})
    )
    if not target or not target.get("organization_id"):
        raise HTTPException(status_code=404, detail="User not found")
    org = await db.organizations.find_one(
        {"id": target["organization_id"]}, {"_id": 0, "account_type": 1},
    )
    if not org or org.get("account_type") not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(status_code=404, detail="User not found")


async def log_activity(action: str, details: str, admin_email: str, target_type: str = "", target_id: str = ""):
    await db.admin_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "action": action,
        "details": details,
        "admin_email": admin_email,
        "target_type": target_type,
        "target_id": target_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _get_platform_counts(org_ids: Optional[list[str]] = None) -> dict:
    """Fetch core platform entity counts.

    When ``org_ids`` is provided (Pulse-scoped admins), every count is filtered
    by ``organization_id ∈ org_ids``. ``None`` means platform-wide (GymAxis
    master view).
    """
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    return {
        "total_users": await db.users.count_documents(scoped_q),
        "total_organizations": await db.organizations.count_documents(org_q),
        "active_orgs": await db.organizations.count_documents({**org_q, "status": {"$in": ["active", None]}}),
        "trial_orgs": await db.organizations.count_documents({**org_q, "status": "trial"}),
        "suspended_orgs": await db.organizations.count_documents({**org_q, "status": "suspended"}),
        "cancelled_orgs": await db.organizations.count_documents({**org_q, "status": "cancelled"}),
        "total_equipment": await db.equipment.count_documents(scoped_q),
        "total_issues": await db.issues.count_documents(scoped_q),
        "open_issues": await db.issues.count_documents({**scoped_q, "status": "open"}),
        "resolved_issues": await db.issues.count_documents({**scoped_q, "status": {"$in": ["resolved", "closed"]}}),
        "total_files": await db.files.count_documents(scoped_q),
        "total_purchase_orders": await db.purchase_orders.count_documents(scoped_q),
        "total_supplier_cases": await db.supplier_cases.count_documents(scoped_q),
    }


async def _get_subscription_stats(org_ids: Optional[list[str]] = None) -> tuple[dict, int]:
    """Fetch subscription breakdown and MRR (excluding test accounts).

    Same scoping semantics as ``_get_platform_counts``.
    """
    non_test = {"is_test": {"$ne": True}}
    if org_ids is not None:
        non_test["id"] = {"$in": org_ids}
    subs = {
        "free": await db.organizations.count_documents({**non_test, "subscription_tier": {"$in": ["free", None, ""]}}),
        "pro": await db.organizations.count_documents({**non_test, "subscription_tier": "pro"}),
        "premium": await db.organizations.count_documents({**non_test, "subscription_tier": "premium"}),
        "enterprise": await db.organizations.count_documents({**non_test, "subscription_tier": "enterprise"}),
    }
    mrr = (subs["pro"] * 49) + (subs["premium"] * 99) + (subs["enterprise"] * 199)
    return subs, mrr


async def _get_growth_data(mrr: int, org_ids: Optional[list[str]] = None) -> list:
    """Build 6-month growth timeline (org_id-scoped when ``org_ids`` is set)."""
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    data = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=30 * i)
        month_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = (month_start + timedelta(days=32)).replace(day=1) if i > 0 else datetime.now(timezone.utc)
        data.append({
            "month": month_start.strftime("%b %Y"),
            "users": await db.users.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "organizations": await db.organizations.count_documents({**org_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "issues": await db.issues.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "mrr": mrr,
        })
    return data


async def _resolve_pulse_scope_org_ids(user: dict) -> Optional[list[str]]:
    """Return org-id list when caller is Pulse-only, else ``None``.

    ``None`` signals platform-wide queries.
    """
    if not is_pulse_only(user):
        return None
    pulse_orgs = await db.organizations.find(
        {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    return [o["id"] for o in pulse_orgs]


@router.get("/master-admin/stats")
async def get_master_stats(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    org_ids = await _resolve_pulse_scope_org_ids(user)
    counts = await _get_platform_counts(org_ids)
    subs, mrr = await _get_subscription_stats(org_ids)
    issue_q: dict = {"ai_triage": {"$exists": True, "$ne": None}}
    audit_q: dict = {}
    payment_succ_q: dict = {"status": "succeeded"}
    payment_fail_q: dict = {"status": "failed"}
    if org_ids is not None:
        issue_q["organization_id"] = {"$in": org_ids}
        audit_q["organization_id"] = {"$in": org_ids}
        payment_succ_q["organization_id"] = {"$in": org_ids}
        payment_fail_q["organization_id"] = {"$in": org_ids}
    ai_calls = await db.issues.count_documents(issue_q)
    ai_audits = await db.audits.count_documents(audit_q)

    return {
        **counts,
        "mrr": mrr,
        "subscriptions": subs,
        "ai_usage": {"triage_calls": ai_calls, "audit_reports": ai_audits, "total": ai_calls + ai_audits},
        "payments": {
            "total": await db.payment_transactions.count_documents(payment_succ_q),
            "failed": await db.payment_transactions.count_documents(payment_fail_q),
        },
        "growth_data": await _get_growth_data(mrr, org_ids),
        "scoped": org_ids is not None,
    }


# ── Audit-log viewer · Iter 216h161 ─────────────────────────────
#
# Compliance surface over the `audit_logs` collection populated by
# `utils.audit.audit_log()`. Filterable + paginated + CSV export so
# enterprise procurement / SOC2 auditors can pull "every action by
# this user in 2026" in one click.

@router.get("/master-admin/audit-logs")
async def list_audit_logs(
    user: dict = Depends(get_current_user),
    q: str = "",
    action: str = "",
    user_id: str = "",
    user_email: str = "",
    resource_type: str = "",
    resource_id: str = "",
    since: str = "",   # ISO date or datetime
    until: str = "",
    skip: int = 0,
    limit: int = 50,
):
    """Paginated audit-log search. Master-admin only."""
    require_master_admin(user)
    limit = max(1, min(limit, 500))
    skip = max(skip, 0)
    query: dict = {}
    if action:
        query["action"] = {"$regex": action, "$options": "i"}
    if user_id:
        query["user_id"] = user_id
    if user_email:
        query["user_email"] = {"$regex": user_email, "$options": "i"}
    if resource_type:
        query["resource_type"] = resource_type
    if resource_id:
        query["resource_id"] = resource_id
    if since or until:
        ts: dict = {}
        if since:
            ts["$gte"] = since
        if until:
            ts["$lte"] = until
        query["timestamp"] = ts
    if q:
        # Free-text — search across action, email, details, resource id.
        query.setdefault("$or", []).extend([
            {"action": {"$regex": q, "$options": "i"}},
            {"user_email": {"$regex": q, "$options": "i"}},
            {"details": {"$regex": q, "$options": "i"}},
            {"resource_id": {"$regex": q, "$options": "i"}},
        ])
    cursor = db.audit_logs.find(
        query, {"_id": 0},
    ).sort([("timestamp", -1)]).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    total = await db.audit_logs.count_documents(query)
    return {"rows": rows, "total": total, "skip": skip, "limit": limit}


@router.get("/master-admin/audit-logs/facets")
async def list_audit_facets(user: dict = Depends(get_current_user)):
    """Distinct actions + resource_types so the UI can render filter
    dropdowns without scanning the full collection."""
    require_master_admin(user)
    actions = await db.audit_logs.distinct("action")
    resource_types = await db.audit_logs.distinct("resource_type")
    return {
        "actions": sorted([a for a in actions if a])[:500],
        "resource_types": sorted([r for r in resource_types if r])[:200],
    }


@router.get("/master-admin/audit-logs/export.csv")
async def export_audit_logs_csv(
    user: dict = Depends(get_current_user),
    q: str = "",
    action: str = "",
    user_email: str = "",
    resource_type: str = "",
    since: str = "",
    until: str = "",
    limit: int = 10000,
):
    """Stream a filtered audit-log slice as CSV. Same query semantics
    as the JSON list endpoint, but capped at 10k rows by default to
    keep response time bounded."""
    require_master_admin(user)
    import csv
    import io
    from fastapi.responses import StreamingResponse

    limit = max(1, min(limit, 50000))
    query: dict = {}
    if action:
        query["action"] = {"$regex": action, "$options": "i"}
    if user_email:
        query["user_email"] = {"$regex": user_email, "$options": "i"}
    if resource_type:
        query["resource_type"] = resource_type
    if since or until:
        ts: dict = {}
        if since:
            ts["$gte"] = since
        if until:
            ts["$lte"] = until
        query["timestamp"] = ts
    if q:
        query.setdefault("$or", []).extend([
            {"action": {"$regex": q, "$options": "i"}},
            {"user_email": {"$regex": q, "$options": "i"}},
            {"details": {"$regex": q, "$options": "i"}},
            {"resource_id": {"$regex": q, "$options": "i"}},
        ])
    rows = await db.audit_logs.find(
        query, {"_id": 0},
    ).sort([("timestamp", -1)]).limit(limit).to_list(limit)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action", "user_email", "user_id",
                     "resource_type", "resource_id", "details", "ip_address"])
    for r in rows:
        writer.writerow([
            r.get("timestamp", ""), r.get("action", ""), r.get("user_email", ""),
            r.get("user_id", ""), r.get("resource_type", ""), r.get("resource_id", ""),
            (r.get("details", "") or "").replace("\n", " ").replace("\r", " "),
            r.get("ip_address", ""),
        ])
    buf.seek(0)
    fname = f"audit-logs-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── /organizations/search — extracted to master_admin_orgs.py (iter 216h178) ──


# ── /organizations (list) — extracted to master_admin_orgs.py (iter 216h178) ──

# ── /organizations/{id}/status — extracted to master_admin_orgs.py (iter 216h178) ──
_PULSE_TIER_TO_ACCOUNT_TYPE = {"lite": "lite", "pulse_pro": "pulse_pro"}
_GYMAXIS_TIERS = {"free", "pro", "premium", "enterprise", "starter", "professional"}


# ── /organizations/{id}/subscription + /features — extracted to master_admin_orgs.py (iter 216h178) ──

@router.put("/master-admin/organizations/{org_id}/test-flag")
async def toggle_test_flag(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    is_test = body.get("is_test", False)
    await db.organizations.update_one({"id": org_id}, {"$set": {"is_test": is_test}})
    await log_activity("test_flag", f"Set org {org_id} test={is_test}", user["email"], "organization", org_id)
    return {"success": True}


@router.post("/master-admin/organizations/{org_id}/test-email")
async def send_test_branded_email(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Send a dummy email of the selected `kind` to `body.to` (default: admin's own)
    using the target org's platform branding (Pulse Fitness vs GymAxis AI). Lets
    master admins validate every outbound template end-to-end without logging a
    real fault. Supported kinds: `comment`, `engineer_callout`, `supplier_welcome`.
    """
    require_master_admin(user)

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        raise HTTPException(status_code=503, detail="Resend is not configured in this environment")

    from routes.supplier_portal import (
        _resolve_platform_branding,
        _build_comment_email_html,
        _build_supplier_welcome_html,
        _short_case_ref,
    )
    import resend as _resend
    _resend.api_key = resend_key

    branding = await _resolve_platform_branding(org_id)
    to_email = (body.get("to") or user.get("email") or "").strip()
    if not to_email:
        raise HTTPException(status_code=400, detail="No recipient email resolved")

    kind = (body.get("kind") or "comment").strip()
    site_name = org.get("name", "Your Gym")
    machine, serial = "Treadmill", "TEST-0001"

    if kind == "supplier_welcome":
        sample_supplier = {
            "name": "Sample Supplier Ltd",
            "contact_person": "Service Team",
            "email": to_email,
        }
        html = _build_supplier_welcome_html(sample_supplier, site_name, branding)
        subject = f"[PREVIEW] Welcome to {branding['platform_name']} — how faults will reach you from {site_name}"
        from_line = f"{site_name} <faults@service.gymaxisai.com>"
    elif kind == "engineer_callout":
        html, subject, from_line = _build_preview_engineer_email(
            branding, site_name, machine, serial,
        )
    else:  # 'comment'
        html, subject, from_line = _build_preview_comment_email(
            branding, site_name, machine, serial,
            _build_comment_email_html, _short_case_ref,
        )

    try:
        await asyncio.to_thread(_resend.Emails.send, {
            "from": from_line,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send preview email: {e}")

    await log_activity(
        "email_preview",
        f"Sent {kind} preview for org {org_id} ({branding['platform_name']}) to {to_email}",
        user["email"], "organization", org_id,
    )
    return {
        "success": True,
        "sent_to": to_email,
        "kind": kind,
        "platform_name": branding["platform_name"],
        "is_pulse": branding["is_pulse"],
    }


def _build_preview_comment_email(branding: dict, site_name: str, machine: str, serial: str,
                                 build_html, build_ref) -> tuple[str, str, str]:
    case = {"id": "preview-case-0000", "token": "preview", "organization_name": site_name}
    issue = {
        "id": "preview-issue", "machine_type": machine, "serial_number": serial,
        "issue_description": "Console intermittently resetting — preview email (no real fault)",
    }
    comment = {
        "author_name": site_name, "author_role": "site_manager",
        "message": (
            "This is a preview of the 2-way conversation email your customers and "
            "suppliers will see. No real fault has been reported."
        ),
    }
    ref = build_ref(case, issue)
    intro = f"{site_name} has posted a new comment on the fault report for <strong>{machine}</strong>."
    html = build_html(case, comment, intro, branding, issue, ref)
    subject = f"[PREVIEW][{ref}] Sample message from {site_name} — {machine}"
    from_line = f"{site_name} <faults@service.gymaxisai.com>"
    return html, subject, from_line


def _build_preview_engineer_email(branding: dict, site_name: str,
                                  machine: str, serial: str) -> tuple[str, str, str]:
    """Build a preview of the initial engineer-callout email using the same
    responsive template real engineer emails use — so admins validate the
    exact visual their suppliers will receive."""
    from routes.issue_helpers import _build_engineer_email_html

    platform = branding["platform_name"]
    from_line = f"{site_name} <faults@service.gymaxisai.com>"
    subject = f"[PREVIEW][JOB-PRVW0001] Engineer Required — {machine} ({serial}) — {site_name}"

    class _PreviewIssue:  # minimal duck-type for the email builder
        machine_type = machine
        serial_number = serial
        severity = "out_of_order"
        issue_description = (
            "Console intermittently resets when Start is pressed. Reproduces 3/5 times. "
            "User report: no display, then reboots after 10 seconds. (Preview — no real fault logged.)"
        )
        ai_triage = "Likely cause: loose power harness or failing PSU. Suggested action: inspect main PSU connector + replace if oxidised."

    user_stub = {"full_name": "Preview Reporter", "email": "preview.reporter@example.com"}
    case_result = {"case_id": "prvw0001-0000-0000-0000-000000000000", "url": "#preview"}
    org_ctx = {
        "brand_color": "#0055FF",
        "company_name": site_name,
        "supplier_contact": "Service Team",
        "supplier_email": "supplier@example.com",
        "test_mode": False,
        "platform_name": platform,
        "is_pulse": branding.get("is_pulse", False),
        "reporter": {"name": "Preview Reporter", "email": "preview.reporter@example.com", "role": "Owner"},
        "site": {"gym_name": site_name, "address": "1 Example Street, London, E1 1AA, UK", "phone": "020 7123 4567"},
        "job_ref": "",
    }
    html = _build_engineer_email_html(_PreviewIssue(), user_stub, case_result, org_ctx)
    return html, subject, from_line


@router.put("/master-admin/organizations/{org_id}/account-type")
async def update_account_type(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    account_type = body.get("account_type")
    if account_type not in ["lite", "full", "pulse_pro"]:
        raise HTTPException(status_code=400, detail="Invalid account type. Must be 'lite', 'full', or 'pulse_pro'")

    # Derive subscription_tier to keep in sync
    tier_map = {"lite": "lite", "pulse_pro": "pro", "full": "premium"}
    tier = tier_map.get(account_type, "free")

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"account_type": account_type, "subscription_tier": tier}},
    )
    # Also update all users in this org so their token reflects the new type
    await db.users.update_many({"organization_id": org_id}, {"$set": {"account_type": account_type}})
    await log_activity("account_type_change", f"Changed org {org_id} to {account_type}", user["email"], "organization", org_id)
    return {"success": True, "account_type": account_type}


# ── Iter 215ar — Modules + Primary-contact auto-provisioning ───────

# Canonical module ids exposed to the master-admin UI (checkbox grid).
ALL_MODULE_IDS = ["operations", "crm", "memberships", "marketing", "staffing", "reporting"]


def _normalize_modules(raw, legacy_portal_type: Optional[str]) -> List[str]:
    """Coerce the inbound `enabled_modules` list to a clean, deduped subset
    of ALL_MODULE_IDS. Falls back to deriving from a legacy portal_type
    string so older callers keep working unchanged."""
    if isinstance(raw, list) and raw:
        cleaned = [m for m in raw if isinstance(m, str) and m in ALL_MODULE_IDS]
        if cleaned:
            # Stable order — match the UI grid for predictability.
            return [m for m in ALL_MODULE_IDS if m in cleaned]
    return _modules_from_portal_type(legacy_portal_type or "service_portal")


def _modules_from_portal_type(portal_type: str) -> List[str]:
    """Map a legacy portal_type string back onto the modules list."""
    if portal_type == "crm":
        return ["crm"]
    if portal_type == "both":
        return ["operations", "crm"]
    return ["operations"]  # service_portal default


def _derive_portal_type(modules: List[str]) -> str:
    """Reduce a modules list to the legacy portal_type for callers that
    still gate on it (collection routing, feature flags)."""
    has_crm = "crm" in modules
    has_ops = any(m in modules for m in ("operations", "memberships", "marketing", "staffing", "reporting"))
    if has_crm and has_ops:
        return "both"
    if has_crm:
        return "crm"
    return "service_portal"


def _generate_initial_password(length: int = 14) -> str:
    """Generate a friendly, copy-able initial password: 4 lowercase + 4 digits + 4 lowercase + 2 symbols.
    Avoids ambiguous characters (no l/1/O/0)."""
    import secrets
    alphabet = "abcdefghijkmnpqrstuvwxyz"
    digits   = "23456789"
    symbols  = "!@#%&*"

    def pick(src: str, n: int) -> str:
        return "".join(secrets.choice(src) for _ in range(n))

    return f"{pick(alphabet, 4)}{pick(digits, 3)}{pick(alphabet, 3)}{pick(symbols, 2)}"


async def _mint_invite_link(user_id: str, email: str, issued_by_email: str = "system") -> dict:
    """Iter 216h26 — Mint a 72 h reset-link invite for a user.

    Extracted from POST /master-admin/users/{user_id}/invite-link so
    that org create + customer onboarding can return a self-serve
    invite URL alongside (or instead of) the legacy reveal-password
    handover. Lets every Master Admin creation surface stay consistent
    with the iter-216h15 reset-link flow.
    """
    import secrets as _secrets
    from datetime import timedelta as _td
    token = _secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + _td(hours=72)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email,
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
    }


async def _ensure_primary_contact_user(org: dict, actor: dict) -> Optional[str]:
    """If `primary_contact_email` is set on `org` and no user exists for that
    email, auto-provision an admin user in the right collection(s) and
    persist the generated initial password on the org doc. Returns the
    generated password if a new user was created, else None.

    The plaintext is intentionally retained on the org until the user
    changes their password — so master-admin can hand it over during
    onboarding via the Reveal Password button. Cleared by the auth layer
    when the user changes password (see `password_reset.py`)."""
    email = (org.get("primary_contact_email") or "").strip().lower()
    if not email:
        return None
    # Skip if a user already exists in either collection — never overwrite.
    if await db.users.find_one({"email": email}) or await db.crm_users.find_one({"email": email}):
        return None

    full_name = (org.get("primary_contact_name") or email.split("@")[0]).strip() or email
    password  = _generate_initial_password()
    user_id   = str(uuid.uuid4())
    try:
        await _create_org_user(org, email, full_name, password, role="admin", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        # Don't blow up org creation if user creation fails — log + continue.
        logger.warning("Failed to auto-create primary contact user for org %s: %s", org.get("id"), exc)
        return None

    # Persist the plaintext password so master-admin can reveal it.
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "primary_contact_initial_password": password,
            "primary_contact_user_id": user_id,
            "primary_contact_password_changed": False,
            "primary_contact_provisioned_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_activity(
        "primary_contact_provisioned",
        f"Auto-created user {email} as primary contact for {org.get('name')}",
        actor.get("email", "system"), "user", user_id,
    )
    return password


@router.post("/master-admin/organizations")
async def create_organization(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create a new organisation (Service Portal, CRM, or both)."""
    require_master_admin(user)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organisation name is required")

    # Iter 215ar — `enabled_modules` is the new source of truth for
    # which modules an org has access to. The legacy `portal_type`
    # ("service_portal" | "crm" | "both") is derived from it for
    # backwards-compatibility with existing callers / DB queries.
    raw_modules = body.get("enabled_modules") or body.get("modules")
    enabled_modules = _normalize_modules(raw_modules, body.get("portal_type"))
    portal_type = _derive_portal_type(enabled_modules)

    # Pulse-only admins can only create Pulse-visible orgs.
    requested_account_type = body.get("account_type", "full")
    if is_pulse_only(user) and requested_account_type not in PULSE_VISIBLE_ACCOUNT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Pulse admins can only create Pulse-visible account types: {PULSE_VISIBLE_ACCOUNT_TYPES}",
        )

    org_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Iter 216h109 — MOD portal fields. `is_mod` flags the org for the
    # MOD module-gating rules (no Memberships/CRM/Marketing/Staffing/
    # Gym Layout). `mod_force` (army|raf|navy) groups sites under the
    # right Command-Centre HQ. `parent_organization_id` chains a site
    # under its service HQ.
    is_mod = bool(body.get("is_mod") or False)
    mod_force = (body.get("mod_force") or "").strip().lower() or None
    if mod_force and mod_force not in {"army", "raf", "navy"}:
        raise HTTPException(status_code=400, detail="mod_force must be army, raf, or navy")
    parent_organization_id = body.get("parent_organization_id") or None
    org_doc = {
        "id": org_id, "name": name,
        "portal_type": portal_type,
        "enabled_modules": enabled_modules,
        "subscription_tier": body.get("subscription_tier", "free"),
        "account_type": requested_account_type,
        "status": "active", "created_at": now,
        "company_code": str(uuid.uuid4())[:8].upper(),
        "industry": body.get("industry", ""),
        "employee_count": body.get("employee_count", ""),
        "website": body.get("website", ""),
        "phone": body.get("phone", ""),
        # MOD portal hierarchy + flagging.
        "is_mod": is_mod,
        "mod_force": mod_force,
        "parent_organization_id": parent_organization_id,
        # Iter 215en — accept structured 8-field address. Legacy `address`
        # is retained for downstream Sage / Sicon outboxes; we auto-compose
        # it from the structured shape when only the structured fields are
        # supplied.
        **merge_address(body),
        "primary_contact_name": body.get("primary_contact_name", ""),
        "primary_contact_email": body.get("primary_contact_email", ""),
        "primary_contact_phone": body.get("primary_contact_phone", ""),
        "notes": body.get("notes", ""),
        "features": body.get("features", {}),
    }
    await db.organizations.insert_one(org_doc)

    # Iter 215ar — auto-provision a user account for the primary contact
    # so the org owner can sign in immediately. Master admin can reveal the
    # initial password from the org panel until the user changes it.
    await _ensure_primary_contact_user(org_doc, user)

    # Iter 216h26 — also mint a 72 h invite link so the operator can
    # send a self-serve "set your own password" URL instead of relying
    # on the credentials-reveal handover. Both paths remain valid;
    # operators can pick whichever fits the customer.
    invite_payload = None
    try:
        org_after = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        owner_id = (org_after or {}).get("primary_contact_user_id")
        owner_email = (org_after or {}).get("primary_contact_email")
        if owner_id and owner_email:
            invite_payload = await _mint_invite_link(owner_id, owner_email, user.get("email", "system"))
    except Exception:  # noqa: BLE001 — never fail org creation on invite mint
        invite_payload = None

    await log_activity("org_created", f"Created organisation: {name} ({portal_type})", user["email"], "organization", org_id)
    fresh = await db.organizations.find_one({"id": org_id}, {"_id": 0, "primary_contact_initial_password": 0})
    response: dict = {**(fresh or org_doc), "user_count": 0}
    if invite_payload:
        response["owner"] = {
            "email": fresh.get("primary_contact_email"),
            "user_id": fresh.get("primary_contact_user_id"),
            "invite_url": invite_payload["invite_url"],
            "invite_expires_at": invite_payload["expires_at"],
        }
        # Convenience top-level keys so older callers keep working.
        response["invite_url"] = invite_payload["invite_url"]
        response["invite_expires_at"] = invite_payload["expires_at"]
    return response



# ── /organizations/{id}/details — extracted to master_admin_orgs.py (iter 216h178) ──

@router.get("/master-admin/organizations/{org_id}/primary-contact-credentials")
async def get_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Reveal the auto-generated initial password for the org's primary
    contact user. Audited every time it is accessed. Cleared once the
    contact changes their own password (see password reset flow)."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        return {"email": None, "initial_password": None, "password_changed": False, "available": False}
    await log_activity(
        "primary_contact_password_revealed",
        f"Revealed initial password for {email}",
        user["email"], "organization", org_id,
    )
    return {
        "email": email,
        "initial_password": initial if (initial and not changed) else None,
        "password_changed": changed,
        "available": bool(initial and not changed),
    }


@router.post("/master-admin/organizations/{org_id}/send-primary-contact-credentials")
async def send_primary_contact_credentials(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 215at — email the auto-generated initial credentials to the
    primary contact via Resend, then clear the plaintext from the org doc
    so it can no longer be revealed in the panel.

    Audited. Returns 400 if no credentials are available to send."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    email   = (org.get("primary_contact_email") or "").strip().lower()
    initial = org.get("primary_contact_initial_password")
    changed = bool(org.get("primary_contact_password_changed"))
    if not email:
        raise HTTPException(400, "No primary contact email set on this organisation")
    if not initial or changed:
        raise HTTPException(400, "No initial password is available to send (already used or rotated)")

    # Late import — avoid the helper module loading at startup if email
    # is misconfigured. send_email is best-effort and audited internally.
    from utils.email import send_email

    org_name  = org.get("name", "your GymAxis account")
    contact   = org.get("primary_contact_name") or email.split("@")[0]
    subject   = f"Welcome to {org_name} on GymAxis"

    # Plain HTML — no inline images, no tracking pixels, deliverability-friendly.
    html = f"""
    <div style="font-family:Inter,system-ui,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a">
      <h1 style="font-size:20px;font-weight:800;letter-spacing:-0.4px;margin:0 0 8px">Welcome to GymAxis, {contact}.</h1>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Your account for <strong>{org_name}</strong> is ready. Use the credentials below to sign in for the first time.
      </p>
      <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;background:#f8fafc;margin-bottom:20px">
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Email</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0 0 14px;color:#0f172a">{email}</p>
        <p style="font-size:12px;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin:0 0 6px;font-weight:700">Temporary password</p>
        <p style="font-family:ui-monospace,monospace;font-size:14px;margin:0;color:#0f172a">{initial}</p>
      </div>
      <p style="font-size:14px;line-height:1.55;color:#475569;margin:0 0 20px">
        Please change your password the first time you sign in — go to your profile menu and select
        <em>Change password</em>. The temporary password above will stop working once you do.
      </p>
      <a href="https://gymaxisai.com/login" style="display:inline-block;background:linear-gradient(135deg,#2563EB,#9D4CDD);color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:999px;font-size:14px">Sign in to GymAxis</a>
      <p style="font-size:11px;color:#94a3b8;margin-top:32px">
        If you weren't expecting this email, please contact us at security@gymaxisai.com.
      </p>
    </div>
    """

    ok = await send_email(email, subject, html)
    if not ok:
        raise HTTPException(502, "Email could not be delivered. Please try again or copy the password manually.")

    # Clear the plaintext from the org doc immediately on successful send —
    # we no longer need to keep it; if the user loses the email they can
    # reset via the standard /auth/forgot-password flow.
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"primary_contact_credentials_sent_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"primary_contact_initial_password": ""}},
    )
    await log_activity(
        "primary_contact_credentials_emailed",
        f"Emailed initial credentials to {email}",
        user["email"], "organization", org_id,
    )
    return {"sent": True, "email": email}


# ── Verify tenant identifier mappings ────────────────────────────


async def _check_code_collision(code: str, fields: list[str], exclude_org_id: str) -> Optional[dict]:
    """Return ``{org_id, name}`` for any OTHER org in our DB sharing this code
    on any of ``fields``. Empty/whitespace codes are skipped."""
    if not (code and code.strip()):
        return None
    norm = code.strip()
    other = await db.organizations.find_one(
        {
            "id": {"$ne": exclude_org_id},
            "$or": [{f: norm} for f in fields],
        },
        {"_id": 0, "id": 1, "name": 1},
    )
    return other if other else None


async def _integration_status(integration_id: str) -> dict:
    """Return ``{status: "configured"|"not_configured", configured: bool}`` for
    the platform-level Sicon / Orbit 4 integration row."""
    cfg = await db.integration_configs.find_one(
        {"id": integration_id}, {"_id": 0, "configured": 1, "connection_status": 1, "last_verified_at": 1},
    )
    if not cfg or not cfg.get("configured"):
        return {"status": "not_configured", "configured": False}
    return {
        "status": "configured",
        "configured": True,
        "connection_status": cfg.get("connection_status", "unknown"),
        "last_verified_at": cfg.get("last_verified_at"),
    }


@router.post("/master-admin/organizations/{org_id}/verify-mappings")
async def verify_org_mappings(
    org_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Sanity-check the tenant identifier codes (`customer_account_number`,
    `sage_customer_number`, `sicon_customer_number`) for an org.

    Returns one block per field with:
      • ``format_ok`` — non-empty, alphanumeric-ish (not pure whitespace)
      • ``collision`` — pointer to another org already using this code
      • ``auto_route_preview`` — count of rows that would be matched by Bulk
        Imports running with this code (useful sanity check)
    Also returns a ``sicon`` / ``orbit4`` block describing whether the
    integration is configured at the platform level. Pulse-only callers
    are scoped via the existing org-in-scope check.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Use the body codes when provided, else fall back to whatever's stored
    # on the org doc — lets the UI verify draft edits before saving.
    payload = body or {}
    candidates = {
        "customer_account_number": (payload.get("customer_account_number") or org.get("customer_account_number") or "").strip(),
        "sage_customer_number": (payload.get("sage_customer_number") or org.get("sage_customer_number") or "").strip(),
        "sicon_customer_number": (payload.get("sicon_customer_number") or org.get("sicon_customer_number") or "").strip(),
    }

    fields_for_collision = list(candidates.keys())
    field_results: dict = {}
    for field, value in candidates.items():
        if not value:
            field_results[field] = {
                "value": "",
                "format_ok": False,
                "collision": None,
                "note": "empty — set this code to enable Bulk Imports auto-routing for this tenant",
            }
            continue

        # Format check: at least 2 chars, no whitespace, only alnum + - _ . / allowed
        format_ok = (
            len(value) >= 2
            and all(ch.isalnum() or ch in "-_./" for ch in value)
        )
        collision = await _check_code_collision(value, fields_for_collision, org_id)
        # Auto-route preview — how many EQUIPMENT rows referencing this org
        # the Bulk Imports auto-routing would already match. Pure read.
        equipment_count = await db.equipment.count_documents({"organization_id": org_id})
        contact_count = await db.crm_contacts.count_documents({"organization_id": org_id})
        field_results[field] = {
            "value": value,
            "format_ok": format_ok,
            "collision": collision,
            "auto_route_preview": {
                "existing_equipment_in_tenant": equipment_count,
                "existing_contacts_in_tenant": contact_count,
            },
        }

    sicon = await _integration_status("sicon")
    orbit4 = await _integration_status("orbit4")

    # Top-level convenience flag — "all green" iff every populated code
    # has format_ok and zero collisions. Empty fields don't fail; they're
    # informational only.
    all_green = all(
        (r["format_ok"] and not r["collision"])
        for r in field_results.values()
        if r["value"]
    ) and any(r["value"] for r in field_results.values())

    return {
        "ok": True,
        "all_green": all_green,
        "fields": field_results,
        "integrations": {"sicon": sicon, "orbit4": orbit4},
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }




async def _create_org_user(org: dict, email: str, full_name: str, password: str, role: str, user_id: str):
    """Create a user in the appropriate collection(s) based on org portal type.

    Iter 215ev — when portal_type == 'both' we write to both collections
    with the SAME `id` so downstream listings can dedupe into one row
    per person (with portal badges), instead of showing the same human
    as two separate user rows. Was a real pain-point (see user bug
    report "Rob Yates doubled up").
    """
    now = datetime.now(timezone.utc).isoformat()
    portal_type = org.get("portal_type", "service_portal")
    is_crm = portal_type in ("crm", "both")
    is_sp = portal_type in ("service_portal", "both")

    if is_crm:
        from routes.crm_auth import crm_hash_password
        await db.crm_users.insert_one({
            "id": user_id, "email": email, "full_name": full_name,
            "password": crm_hash_password(password),
            "organization_id": org["id"], "role": role,
            "avatar_url": None, "created_at": now,
        })

    if is_sp:
        from utils.auth import hash_password
        await db.users.insert_one({
            "id": user_id,  # Iter 215ev — SAME id across both collections so listings dedupe cleanly.
            "email": email, "full_name": full_name,
            "password": hash_password(password),
            "organization_id": org["id"], "role": role,
            "account_type": org.get("account_type", "full"),
            "created_at": now,
        })

    return "CRM" if is_crm else "Service Portal"


@router.get("/master-admin/organizations/{org_id}/integration-health")
async def org_integration_health(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 216h21 — per-org integration health snapshot for the
    Organisations drawer's new Integrations tab (P4 redesign).

    READ-ONLY. Surfaces the connection state of every third-party
    integration that touches a single organisation:
      • stripe_connect — Stripe Express onboarding + platform fee
      • sicon          — Sicon Service (Sage 200 ledger) account ref
      • orbit4         — Orbit 4 stock / equipment master
      • sage200        — Sage 200 customer ledger

    The canonical editors for these connections live on the global
    Integrations pages — this endpoint just returns the per-org slice
    so operators don't have to bounce around the console.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Stripe Connect — pull whatever's persisted on the org doc plus
    # the platform-fee setting from `app_config` if available.
    stripe_account_id = org.get("stripe_connect_account_id") or org.get("stripe_account_id") or ""
    stripe_charges_enabled = bool(org.get("stripe_charges_enabled", False))
    stripe_payouts_enabled = bool(org.get("stripe_payouts_enabled", False))
    platform_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    platform_fee_pct = platform_cfg.get("platform_fee_pct")

    # Sicon — configured iff the org has a customer account ref AND
    # the platform-level Sicon integration is in `configured` state.
    sicon_platform = await _integration_status("sicon")
    sicon_account = org.get("sicon_customer_account_number") or org.get("sicon_customer_number") or ""
    sicon_auto_post = bool(org.get("sicon_auto_post", False))

    # Orbit 4 — same pattern.
    orbit_platform = await _integration_status("orbit4")
    orbit_customer = org.get("orbit4_customer_id") or ""

    # Sage 200 — currently lives via the customer number on the org
    # doc + the same Sicon bridge for posting. Treated as a separate
    # row in the UI because operators think of them separately.
    sage_account = org.get("sage_customer_number") or ""

    return {
        "org_id": org_id,
        "stripe_connect": {
            "connected": bool(stripe_account_id),
            "account_id": stripe_account_id,
            "charges_enabled": stripe_charges_enabled,
            "payouts_enabled": stripe_payouts_enabled,
            "platform_fee_pct": platform_fee_pct,
        },
        "sicon": {
            "configured": bool(sicon_account) and bool(sicon_platform.get("configured")),
            "platform_configured": bool(sicon_platform.get("configured")),
            "account_ref": sicon_account,
            "auto_post": sicon_auto_post,
        },
        "orbit4": {
            "configured": bool(orbit_customer) and bool(orbit_platform.get("configured")),
            "platform_configured": bool(orbit_platform.get("configured")),
            "customer_id": orbit_customer,
        },
        "sage200": {
            "configured": bool(sage_account),
            "account_ref": sage_account,
        },
    }

@router.get("/master-admin/integrations-hub")
async def integrations_hub(user: dict = Depends(get_current_user)):
    """Iter 216h22 — single round-trip status summary for the new
    Integrations Hub page (P5 redesign).

    READ-ONLY aggregate of the 4 third-party connections Master Admins
    care about most:
      • stripe_connect — platform-level Stripe Express OAuth, plus a
        count of orgs that have completed onboarding.
      • sicon          — Sicon Service (Sage 200 ledger) — config doc
        in `db.integrations` + per-org Sicon customer-number coverage.
      • orbit4         — Orbit 4 stock master — same shape as Sicon.
      • sage200        — Per-org Sage customer numbers (Sage is wired
        via the Sicon bridge — no separate platform creds).

    Per-row fields:
      • enabled             — platform-level toggle
      • status              — "connected" | "degraded" | "not_configured" | "down"
      • last_event_at       — most recent integration_logs timestamp
      • events_24h          — count of integration_logs in the last 24 h
      • errors_24h          — count where success=False in last 24 h
      • orgs_configured     — number of orgs that have the per-org ref
      • orgs_total          — total org count (for the brand currently filtered)
      • brand               — "all" | "pulse" | "gymaxis" — applied
                              to the orgs_configured/total counts.
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause
    brand = "all"
    # Pulse-only callers are pinned to the Pulse brand server-side too.
    if is_pulse_only(user):
        brand = "pulse"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()

    async def _row(integration_id: str, ref_field: str, label: str):
        """Build a per-integration row using the `integrations` and
        `integration_logs` collections plus per-org ref coverage."""
        cfg = await db.integrations.find_one({"integration_id": integration_id}, {"_id": 0}) or {}
        enabled = bool(cfg.get("enabled", False))
        events_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso},
        })
        errors_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso}, "success": False,
        })
        # Most recent event (any). For the "Last sync" pill.
        last_doc = await db.integration_logs.find_one(
            {"integration_id": integration_id},
            {"_id": 0, "timestamp": 1, "success": 1},
            sort=[("timestamp", -1)],
        )

        # Per-org ref coverage. Scope to the brand filter when present.
        org_query: dict = {}
        if brand == "pulse":
            org_query = brand_filter_clause("pulse")
        elif brand == "gymaxis":
            org_query = brand_filter_clause("gymaxis")

        orgs_total = await db.organizations.count_documents(org_query)
        ref_query = {**org_query, ref_field: {"$exists": True, "$ne": ""}}
        orgs_configured = await db.organizations.count_documents(ref_query) if ref_field else 0

        if not enabled and not orgs_configured:
            status = "not_configured"
        elif errors_24h > 0 and errors_24h >= max(1, events_24h // 5):
            status = "degraded"
        elif enabled:
            status = "connected"
        else:
            status = "not_configured"

        return {
            "key": integration_id,
            "label": label,
            "enabled": enabled,
            "status": status,
            "last_event_at": (last_doc or {}).get("timestamp"),
            "last_event_success": (last_doc or {}).get("success"),
            "events_24h": events_24h,
            "errors_24h": errors_24h,
            "orgs_configured": orgs_configured,
            "orgs_total": orgs_total,
            "ref_field": ref_field,
        }

    sicon_row  = await _row("sicon",  "sicon_customer_account_number", "Sicon Service (Sage 200 ledger)")
    orbit_row  = await _row("orbit4", "orbit4_customer_id",             "Orbit 4 (stock master)")

    # Stripe Connect is platform-level + per-org onboarding state.
    stripe_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    stripe_enabled = bool(stripe_cfg.get("enabled", True))  # Stripe is on unless explicitly off
    stripe_org_query: dict = {"stripe_connect_account_id": {"$exists": True, "$ne": ""}}
    if brand == "pulse":
        stripe_org_query = {**brand_filter_clause("pulse"), **stripe_org_query}
    elif brand == "gymaxis":
        stripe_org_query = {**brand_filter_clause("gymaxis"), **stripe_org_query}
    stripe_orgs_configured = await db.organizations.count_documents(stripe_org_query)
    stripe_orgs_total = await db.organizations.count_documents(
        brand_filter_clause(brand) if brand != "all" else {},
    )
    stripe_status = "connected" if stripe_orgs_configured > 0 else ("not_configured" if not stripe_enabled else "degraded")
    stripe_row = {
        "key": "stripe_connect",
        "label": "Stripe Connect",
        "enabled": stripe_enabled,
        "status": stripe_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": stripe_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "platform_fee_pct": stripe_cfg.get("platform_fee_pct"),
        "ref_field": "stripe_connect_account_id",
    }

    # Sage 200 is sub-integration: customer numbers stored on the org
    # doc, posts ride the Sicon bridge.
    sage_org_query = {**(brand_filter_clause(brand) if brand != "all" else {}), "sage_customer_number": {"$exists": True, "$ne": ""}}
    sage_orgs_configured = await db.organizations.count_documents(sage_org_query)
    sage_status = "connected" if sage_orgs_configured > 0 else "not_configured"
    sage_row = {
        "key": "sage200",
        "label": "Sage 200 (customer ledger)",
        "enabled": sage_orgs_configured > 0,
        "status": sage_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": sage_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "ref_field": "sage_customer_number",
    }

    summary = {
        "connected":      sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "connected"),
        "degraded":       sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "degraded"),
        "not_configured": sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "not_configured"),
        "total":          4,
    }

    return {
        "brand": brand,
        "integrations": [stripe_row, sicon_row, orbit_row, sage_row],
        "summary": summary,
    }










# ─────────────────────────────────────────────────────────────────
# Iter 216d — Master-admin per-org site CRUD.
# Lets master admins add or bulk-add sites to an existing org without
# impersonating the owner. The owner-scoped endpoints in routes/sites.py
# require role=owner|manager, which master admins are NOT (they have a
# separate is_master_admin flag).
# ─────────────────────────────────────────────────────────────────

# ── /organizations/{id}/sites + /sites/bulk — extracted to master_admin_orgs.py (iter 216h178) ──





# ── CRM Users + Sicon health — extracted to master_admin_integrations.py (iter 216h177) ──

# ── Trial Management — extracted to master_admin_trials.py (iter 216h177) ──



# ─── Test Data Purge ────────────────────────────────────────────────
@router.post("/master-admin/test-data/purge")
async def purge_test_data(
    user: dict = Depends(get_current_user),
    payload: dict = Body(default={}),
):
    """
    Wipe seeded/demo/test data so the platform reflects real activity only.
    Master-admin only. Purges by default:
      - revenue_distributions + reserve_transactions (so Monthly Revenue resets)
      - demo faults, demo equipment, demo jobs, demo contracts
      - any record with {is_test: true} or {seed: true}
    Pass {"collections": [...]} to override the default list.
    """
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    # Default collections that accumulate platform-activity test data
    default_collections = [
        "revenue_distributions",
        "reserve_transactions",
        "llm_top_up_log",
        "financial_alerts",
    ]
    collections = payload.get("collections", default_collections)

    # Protected — never wipe these even if passed
    PROTECTED = {"users", "organizations", "stripe_webhook_events", "audit_log", "master_admin_activity_log"}
    results = {}

    for coll_name in collections:
        if coll_name in PROTECTED:
            results[coll_name] = {"skipped": True, "reason": "protected"}
            continue
        try:
            res = await db[coll_name].delete_many({})
            results[coll_name] = {"deleted": res.deleted_count}
        except Exception as e:
            results[coll_name] = {"error": str(e)}

    # Also clear any document flagged as test/seed across the whole database
    flagged_total = 0
    for coll_name in ["faults", "equipment", "jobs", "contracts", "job_cards", "ppm_sheets", "check_sheets"]:
        try:
            res = await db[coll_name].delete_many({"$or": [{"is_test": True}, {"seed": True}, {"demo": True}]})
            if res.deleted_count:
                results[f"{coll_name}_flagged"] = {"deleted": res.deleted_count}
                flagged_total += res.deleted_count
        except Exception:
            pass

    await log_activity(
        "test_data_purged",
        f"Purged: {sum(r.get('deleted',0) for r in results.values() if isinstance(r, dict))} docs, flagged: {flagged_total}",
        user.get("email", ""),
        "platform",
        "",
    )
    return {"success": True, "flagged_total": flagged_total, "results": results}



@router.get("/master-admin/all-sites")
async def all_sites_across_orgs(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    site_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 500,
):
    """Iter 216h23 — Cross-organisation physical-sites list.

    Lives at `Master Admin → Organisations → All sites` sub-tab. Solves
    the "where are all my Pulse sites?" question without breaking the
    SSoT principle (a Site still belongs to exactly one Organisation —
    this is just a flat power-view across all orgs).

    Per-row enrichments:
      • org_name / org_brand  — joined from `organizations`.
      • equipment_count       — `equipment` docs scoped to (org_id, site_id).
      • members_count         — `members` (or `crm_users`) scoped likewise.
      • is_head_office        — direct from the site doc.
      • last_activity         — most recent of any audit_logs / issues
                                / check_sheet_instances touching the site.

    Brand scope: Pulse-only admins receive only Pulse-brand sites.
    Query filters: `org_id`, `site_type`, free-text `q` (matches name).
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause

    # Org scope (Pulse-only admins are pinned to Pulse-brand orgs).
    pulse_only = is_pulse_only(user)
    org_filter: dict = {}
    if pulse_only:
        org_filter = brand_filter_clause("pulse")
    if org_id:
        org_filter = {**org_filter, "id": org_id}

    orgs = await db.organizations.find(
        org_filter, {"_id": 0, "id": 1, "name": 1, "brand": 1},
    ).to_list(2000)
    org_index = {o["id"]: o for o in orgs}
    if not org_index:
        return {"sites": [], "totals": {"sites": 0, "head_offices": 0, "branches": 0, "equipment": 0}}

    site_query: dict = {"organization_id": {"$in": list(org_index.keys())}}
    if site_type == "head_office":
        site_query["is_head_office"] = True
    elif site_type == "branch":
        site_query["is_head_office"] = {"$ne": True}
    if q:
        site_query["name"] = {"$regex": q, "$options": "i"}

    sites = await db.sites.find(site_query, {"_id": 0}).sort([("organization_id", 1), ("name", 1)]).to_list(limit)

    # Bulk equipment counts per (org, site).
    eq_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    eq_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.equipment.aggregate(eq_pipeline)}

    # Bulk member counts per site (best-effort — schema varies by tenant).
    mem_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    mem_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.members.aggregate(mem_pipeline)}

    enriched = []
    head_office_count = 0
    branch_count = 0
    total_equipment = 0
    for s in sites:
        org = org_index.get(s.get("organization_id"), {})
        is_hq = bool(s.get("is_head_office"))
        head_office_count += 1 if is_hq else 0
        branch_count += 0 if is_hq else 1
        eq = eq_counts.get((s.get("organization_id"), s.get("id")), 0)
        total_equipment += eq
        enriched.append({
            "id":              s.get("id"),
            "name":            s.get("name"),
            "organization_id": s.get("organization_id"),
            "org_name":        org.get("name") or "—",
            "org_brand":       org.get("brand") or "gymaxis",
            "is_head_office":  is_hq,
            "site_type":       s.get("site_type") or ("head_office" if is_hq else "branch"),
            "city":            s.get("city") or s.get("address", {}).get("city") if isinstance(s.get("address"), dict) else s.get("city"),
            "postcode":        s.get("postcode") or (s.get("address") or {}).get("postcode") if isinstance(s.get("address"), dict) else s.get("postcode"),
            "active":          s.get("active", True),
            "equipment_count": eq,
            "members_count":   mem_counts.get((s.get("organization_id"), s.get("id")), 0),
            "created_at":      s.get("created_at"),
        })

    return {
        "sites": enriched,
        "totals": {
            "sites":         len(enriched),
            "head_offices":  head_office_count,
            "branches":      branch_count,
            "equipment":     total_equipment,
        },
        "brand": "pulse" if pulse_only else "all",
    }



# ──────────────────────────────────────────────────────────────────────
# Iter 216bm — Locked-staff audit view
# ──────────────────────────────────────────────────────────────────────
@router.get("/master-admin/users/locked-sites")
async def locked_staff_audit(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    limit: int = 200,
):
    """List users with non-empty `allowed_site_ids` for compliance audit.

    Returned for every locked staff member: org name, full name, email,
    role, the names of the sites they're locked to, and the timestamp
    of the last permission change. Master-admin only.

    Query params:
      • `org_id` — narrow to a single organisation (optional)
      • `limit`  — max rows (default 200, hard-capped to 1000)
    """
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(status_code=403, detail="Master admin only")

    capped_limit = max(1, min(int(limit or 200), 1000))

    user_filter: dict = {
        "allowed_site_ids": {"$exists": True, "$ne": []},
    }
    if org_id:
        user_filter["organization_id"] = org_id

    user_docs = await db.users.find(
        user_filter,
        {
            "_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1,
            "organization_id": 1, "allowed_site_ids": 1,
            "permissions_updated_at": 1, "is_master_admin": 1,
        },
    ).limit(capped_limit).to_list(capped_limit)

    if not user_docs:
        return {"locked_staff": [], "total": 0}

    # Resolve org names + site names in one round-trip each. The lock
    # field is small enough that an explicit join is fine.
    org_ids = list({u["organization_id"] for u in user_docs if u.get("organization_id")})
    org_lookup = {
        o["id"]: o["name"]
        for o in await db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(org_ids))
    }

    all_site_ids: set = set()
    for u in user_docs:
        for sid in (u.get("allowed_site_ids") or []):
            all_site_ids.add(sid)
    site_lookup = {
        s["id"]: {"name": s.get("name", "(unnamed)"), "is_head_office": bool(s.get("is_head_office"))}
        for s in await db.sites.find(
            {"id": {"$in": list(all_site_ids)}}, {"_id": 0, "id": 1, "name": 1, "is_head_office": 1}
        ).to_list(len(all_site_ids) or 1)
    }

    rows = []
    for u in user_docs:
        site_ids = u.get("allowed_site_ids") or []
        sites = [
            {"id": sid, "name": site_lookup.get(sid, {}).get("name", "(deleted site)"), "is_head_office": site_lookup.get(sid, {}).get("is_head_office", False)}
            for sid in site_ids
        ]
        rows.append({
            "user_id": u.get("id"),
            "full_name": u.get("full_name") or "(no name)",
            "email": u.get("email") or "",
            "role": u.get("role") or "staff",
            "is_master_admin": bool(u.get("is_master_admin")),
            "organization_id": u.get("organization_id"),
            "organization_name": org_lookup.get(u.get("organization_id", ""), "(unknown org)"),
            "site_count": len(sites),
            "sites": sites,
            "permissions_updated_at": u.get("permissions_updated_at"),
        })

    rows.sort(key=lambda r: r.get("permissions_updated_at") or "", reverse=True)
    return {"locked_staff": rows, "total": len(rows)}



# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Pulse Fitness supplier backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-pulse-supplier")
async def backfill_pulse_supplier(
    user: dict = Depends(get_current_user),
    dry_run: bool = False,
):
    """Set every piece of equipment in every Pulse Fitness Lite / Pro
    organisation's default supplier to "Pulse Fitness" with the
    service.dept@pulsefitness.com email. Master-admin only.

    `?dry_run=true` returns counts without writing.
    """
    require_master_admin(user)
    org_cursor = db.organizations.find(
        {"account_type": {"$in": ["lite", "pulse_pro"]}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    )
    pulse_orgs = [o async for o in org_cursor]
    if not pulse_orgs:
        return {"orgs": 0, "equipment_updated": 0, "dry_run": dry_run}

    org_ids = [o["id"] for o in pulse_orgs]
    if dry_run:
        cnt = await db.equipment.count_documents({"organization_id": {"$in": org_ids}})
        return {"orgs": len(pulse_orgs), "equipment_to_update": cnt, "dry_run": True}

    result = await db.equipment.update_many(
        {"organization_id": {"$in": org_ids}},
        {"$set": {
            "supplier": "Pulse Fitness",
            "supplier_email": "service.dept@pulsefitness.com",
            "supplier_backfilled_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "orgs": len(pulse_orgs),
        "equipment_updated": int(result.modified_count or 0),
        "dry_run": False,
    }


# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Spec-sheet attach backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-spec-sheets")
async def backfill_spec_sheets(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    dry_run: bool = False,
):
    """Re-run the spec-sheet auto-match across existing equipment so
    rows uploaded before iter 216bn pick up matching catalogue entries.
    Master-admin only. `?org_id=` narrows to one organisation.
    """
    require_master_admin(user)
    from routes.spec_sheets import auto_match_equipment_to_specs

    eq_filter: dict = {
        "$or": [
            {"spec_sheet_id": {"$exists": False}},
            {"spec_sheet_id": ""},
            {"spec_sheet_id": None},
        ],
    }
    if org_id:
        eq_filter["organization_id"] = org_id

    cursor = db.equipment.find(eq_filter, {"_id": 0})
    eq_docs = await cursor.to_list(2000)

    matched = 0
    if dry_run:
        for eq in eq_docs:
            m = await auto_match_equipment_to_specs(eq)
            if m:
                matched += 1
        return {"considered": len(eq_docs), "matched": matched, "dry_run": True}

    for eq in eq_docs:
        m = await auto_match_equipment_to_specs(eq)
        if m:
            await db.equipment.update_one(
                {"id": eq["id"]},
                {"$set": {**m, "spec_sheet_attached_at": datetime.now(timezone.utc).isoformat()}},
            )
            matched += 1
    return {"considered": len(eq_docs), "matched": matched, "dry_run": False}
