"""
Master Admin · org branding / test-flag / account-type sub-router.

Iter 216h185 — Extracted from `routes/master_admin.py` as phase 9 of
the 4,283 LoC → focused-routers decomposition.

Owns three small but mutually-related per-org admin endpoints:

    PUT  /master-admin/organizations/{org_id}/test-flag      — mark/unmark seed-data orgs
    POST /master-admin/organizations/{org_id}/test-email     — send a branded preview email
    PUT  /master-admin/organizations/{org_id}/account-type   — tier + subscription change

Two private helpers travel with the routes:
    _build_preview_comment_email
    _build_preview_engineer_email

Shared helpers (`assert_org_in_pulse_scope`, `log_activity`,
`require_master_admin`) stay on `routes.master_admin`.
"""
import asyncio
import os

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    assert_org_in_pulse_scope,
    log_activity,
    require_master_admin,
)


router = APIRouter()


# ───────────── PUT /test-flag ─────────────

@router.put("/master-admin/organizations/{org_id}/test-flag")
async def toggle_test_flag(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    is_test = body.get("is_test", False)
    await db.organizations.update_one({"id": org_id}, {"$set": {"is_test": is_test}})
    await log_activity("test_flag", f"Set org {org_id} test={is_test}", user["email"], "organization", org_id)
    return {"success": True}


# ───────────── POST /test-email + helpers ─────────────

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
    from_line = f"{site_name} <faults@service.pulsefitness.ai>"
    return html, subject, from_line


def _build_preview_engineer_email(branding: dict, site_name: str,
                                  machine: str, serial: str) -> tuple[str, str, str]:
    """Build a preview of the initial engineer-callout email using the same
    responsive template real engineer emails use — so admins validate the
    exact visual their suppliers will receive."""
    from routes.issue_helpers import _build_engineer_email_html

    platform = branding["platform_name"]
    from_line = f"{site_name} <faults@service.pulsefitness.ai>"
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


@router.post("/master-admin/organizations/{org_id}/test-email")
async def send_test_branded_email(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Send a dummy email of the selected `kind` to `body.to` (default: admin's own)
    using the target org's platform branding (Pulse Fitness vs Pulse Fitness AI). Lets
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
        from_line = f"{site_name} <faults@service.pulsefitness.ai>"
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


# ───────────── PUT /account-type ─────────────

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
