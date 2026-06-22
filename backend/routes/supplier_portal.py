from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, Response
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import uuid
import logging
import asyncio
import base64
import csv
import io
import os
import re

from utils.database import db, put_object
from utils.auth import get_current_user, get_organization_filter

logger = logging.getLogger(__name__)
router = APIRouter()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "support@service.pulsefitness.ai")
FRONTEND_URL = os.environ.get("FRONTEND_URL", os.environ.get("REACT_APP_BACKEND_URL", ""))

try:
    import resend
except ImportError:
    resend = None


# ── Platform branding (Pulse Fitness vs Pulse Fitness AI) ──────────────

def _is_pulse_account_type(account_type: str | None) -> bool:
    return account_type in ("pulse_pro", "lite")


async def _resolve_platform_branding(organization_id: str | None) -> dict:
    """Return platform-level branding based on the org's account_type.

    For Pulse customers (pulse_pro / lite) all outbound comms should appear to
    originate from 'Pulse Fitness' rather than 'Pulse Fitness AI'.
    """
    org = None
    if organization_id:
        org = await db.organizations.find_one(
            {"id": organization_id},
            {"_id": 0, "account_type": 1, "name": 1},
        )
    is_pulse = _is_pulse_account_type((org or {}).get("account_type"))
    if is_pulse:
        return {
            "platform_name": "Pulse Fitness",
            "platform_footer": "Sent via Pulse Fitness — Equipment Maintenance Platform",
            "via_label": "via Pulse Fitness",
            "is_pulse": True,
        }
    return {
        "platform_name": "Pulse Fitness AI",
        "platform_footer": "Sent via Pulse Fitness AI — Equipment Management Platform",
        "via_label": "via Pulse Fitness AI",
        "is_pulse": False,
    }


# ── Supplier welcome / onboarding email ─────────────────────────

def _build_supplier_welcome_html(
    supplier: dict, org_name: str, branding: dict,
) -> str:
    """Onboarding HTML email explaining how faults will flow to the supplier."""
    contact = supplier.get("contact_person") or supplier.get("name") or "Service Team"
    platform = branding["platform_name"]
    return f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#0A0A0A 0%, #1e3a8a 100%);padding:28px 32px;">
    <h1 style="color:#fff;font-size:20px;margin:0;line-height:1.3;">Welcome to {platform}</h1>
    <p style="color:#cbd5e1;font-size:13px;margin:6px 0 0;">{org_name} has added you as a service supplier</p>
  </div>

  <div style="padding:28px 32px;">
    <p style="color:#111;font-size:14px;line-height:1.6;margin:0 0 16px;">
      Hi {contact},
    </p>
    <p style="color:#111;font-size:14px;line-height:1.6;margin:0 0 20px;">
      <strong>{org_name}</strong> has added your business to {platform} as a service supplier.
      From now on, any faults they report on equipment linked to you will arrive as a branded
      email with everything you need to get the job done — photos, serial numbers, severity,
      and a one-click link to reply or schedule a visit.
    </p>

    <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:10px;padding:20px;margin:20px 0;">
      <h3 style="margin:0 0 14px;font-size:14px;color:#111;">What you&rsquo;ll see when a fault is reported</h3>

      <div style="margin:0 0 12px;padding:12px 14px;background:#fff;border:1px solid #E5E7EB;border-radius:8px;">
        <p style="margin:0;font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;">Fault Details</p>
        <p style="margin:6px 0 0;font-size:13px;color:#111;">Equipment name, serial, severity (Safety Critical &rarr; Minor), description, reporting staff member, AI triage notes (where available).</p>
      </div>

      <div style="margin:0 0 12px;padding:12px 14px;background:#fff;border:1px solid #E5E7EB;border-radius:8px;">
        <p style="margin:0;font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;">Schedule a Visit</p>
        <p style="margin:6px 0 0;font-size:13px;color:#111;">Pick a date and name the engineer attending &mdash; the gym is auto-notified.</p>
      </div>

      <div style="margin:0 0 12px;padding:12px 14px;background:#fff;border:1px solid #E5E7EB;border-radius:8px;">
        <p style="margin:0;font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;">Two-way Chat</p>
        <p style="margin:6px 0 0;font-size:13px;color:#111;">Send questions and photos, see the gym&rsquo;s replies in the same thread. Every message is emailed to both sides.</p>
      </div>

      <div style="margin:0 0 12px;padding:12px 14px;background:#fff;border:1px solid #E5E7EB;border-radius:8px;">
        <p style="margin:0;font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;">Status Tracker</p>
        <p style="margin:6px 0 0;font-size:13px;color:#111;">Pending &rarr; Acknowledged &rarr; Engineer Scheduled &rarr; In Progress &rarr; Parts Ordered &rarr; Completed. Gym and you see the same status in real time.</p>
      </div>

      <div style="margin:0;padding:12px 14px;background:#fff;border:1px solid #E5E7EB;border-radius:8px;">
        <p style="margin:0;font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:0.04em;font-weight:700;">Satisfaction Rating</p>
        <p style="margin:6px 0 0;font-size:13px;color:#111;">Once the job is done, the gym rates your response 1&ndash;5 stars with feedback. Builds your track record.</p>
      </div>
    </div>

    <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:16px 20px;margin:20px 0;">
      <h3 style="margin:0 0 10px;font-size:14px;color:#1e3a8a;">Why this is better for you</h3>
      <ul style="margin:0;padding:0 0 0 18px;color:#111;font-size:13px;line-height:1.7;">
        <li><strong>No logins required.</strong> Every email has a secure one-click link straight to the job.</li>
        <li><strong>Photos and context up front.</strong> No more "which treadmill, which fault?" phone tag.</li>
        <li><strong>Single thread per fault.</strong> Everything about the job lives in one place, searchable by job reference (<code>JOB-XXXXXXXX</code>).</li>
        <li><strong>Equipment history.</strong> Repeat faults on the same machine are visible to both sides.</li>
        <li><strong>Faster quoting.</strong> Serial + make/model arrive automatically, so parts pricing is straightforward.</li>
      </ul>
    </div>

    <p style="color:#111;font-size:14px;line-height:1.6;margin:24px 0 0;">
      No action is needed right now &mdash; the next email you get from us will be a live fault report.
      If you&rsquo;d like to update your contact details or preferred engineers, just reply to this email and {org_name} will sort it.
    </p>

    <p style="color:#111;font-size:14px;line-height:1.6;margin:16px 0 0;">
      Thanks,<br>
      <strong>{org_name}</strong><br>
      <span style="color:#6B7280;font-size:12px;">via {platform}</span>
    </p>
  </div>

  <div style="padding:16px 32px;background:#F9FAFB;border-top:1px solid #E5E7EB;">
    <p style="margin:0;font-size:11px;color:#6B7280;">{branding["platform_footer"]}</p>
    <p style="margin:4px 0 0;font-size:11px;color:#9CA3AF;">This is an informational email &mdash; no reply is required.</p>
  </div>
</div>'''


def _build_equipment_csv(equipment: list[dict]) -> str:
    """Turn a list of equipment docs into a CSV body for the welcome email.
    Includes enrichment columns (`_open_faults`, `_total_faults`,
    `_warranty_label`) when present, so suppliers get useful context.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    has_enrichment = any("_open_faults" in e for e in equipment)
    headers = [
        "Name", "Equipment Type", "Manufacturer", "Model", "Serial Number",
        "Location", "Install Date", "Warranty Expiry",
    ]
    if has_enrichment:
        headers += ["Open Faults", "Total Faults", "Warranty Status"]
    w.writerow(headers)
    for e in equipment:
        row = [
            e.get("name", ""),
            e.get("equipment_type", ""),
            e.get("manufacturer", ""),
            e.get("model", ""),
            e.get("serial_number", ""),
            e.get("location", ""),
            (e.get("install_date") or "")[:10],
            (e.get("warranty_expiry") or "")[:10],
        ]
        if has_enrichment:
            row += [
                e.get("_open_faults", 0),
                e.get("_total_faults", 0),
                e.get("_warranty_label", ""),
            ]
        w.writerow(row)
    return buf.getvalue()


def _summarise_equipment(equipment: list[dict]) -> str:
    """Build a short HTML block summarising the assigned machines for the welcome email."""
    if not equipment:
        return ""
    # Group by equipment_type → count
    counts: dict[str, int] = {}
    for e in equipment:
        kind = (e.get("equipment_type") or "Equipment").title()
        counts[kind] = counts.get(kind, 0) + 1
    parts = [f"{n}&nbsp;{k}" for k, n in sorted(counts.items(), key=lambda x: -x[1])]
    total = len(equipment)
    summary = ", ".join(parts[:6])
    if len(parts) > 6:
        summary += ", &hellip;"

    # Surface open-faults so the supplier knows if anything is already in flight.
    total_open = sum(e.get("_open_faults", 0) for e in equipment)
    open_line = ""
    if total_open:
        open_line = (
            f'<p style="margin:6px 0 0;font-size:12px;color:#991B1B;font-weight:600;">'
            f'⚠ {total_open} open fault{"" if total_open == 1 else "s"} already logged — see attached CSV.'
            f'</p>'
        )

    return f'''
    <div style="margin:16px 0;padding:14px 18px;background:#ECFDF5;border:1px solid #A7F3D0;border-radius:10px;">
      <p style="margin:0;font-size:13px;color:#065F46;font-weight:600;">
        {total} machine{'' if total == 1 else 's'} assigned to you
      </p>
      <p style="margin:6px 0 0;font-size:12px;color:#047857;">{summary}</p>
      {open_line}
      <p style="margin:8px 0 0;font-size:11px;color:#059669;">Full list attached as <strong>equipment.csv</strong>.</p>
    </div>'''


async def send_supplier_welcome_email(
    supplier: dict, organization_id: str, sender_org_name: str | None = None,
    include_equipment: bool = True,
) -> bool:
    """Send the onboarding email to a newly-added supplier.

    Skipped when:
      - No supplier email, or
      - Resend is not configured, or
      - The org is on Pulse Lite (welcome emails are a Pro / Full feature).

    When `include_equipment` is True and equipment is assigned to this supplier,
    the email includes a summary section and an `equipment.csv` attachment.

    Returns True if an email was dispatched, False otherwise.
    """
    email = (supplier.get("email") or "").strip()
    if not email or not RESEND_API_KEY or not resend:
        return False

    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "account_type": 1, "name": 1},
    ) or {}
    account_type = org.get("account_type")
    if account_type not in ("full", "pulse_pro", None):
        return False

    branding = await _resolve_platform_branding(organization_id)
    org_name = sender_org_name or org.get("name") or "Your Gym"

    # Gather assigned equipment (exact-match on supplier name within the same org)
    equipment: list[dict] = []
    if include_equipment and supplier.get("name"):
        equipment = await db.equipment.find(
            {"organization_id": organization_id, "supplier": supplier["name"]},
            {"_id": 0},
        ).to_list(length=500)
        equipment = await _enrich_equipment_for_email(equipment, organization_id)

    summary_html = _summarise_equipment(equipment)
    base_html = _build_supplier_welcome_html(supplier, org_name, branding)
    # Inject the summary just before the "Why this is better for you" block.
    html = base_html.replace(
        '<div style="background:#EFF6FF;border:1px solid #BFDBFE;',
        f'{summary_html}<div style="background:#EFF6FF;border:1px solid #BFDBFE;',
        1,
    )

    subject = f"Welcome to {branding['platform_name']} — how faults will reach you from {org_name}"
    payload = {
        "from": f"{org_name} <faults@service.pulsefitness.ai>",
        "to": [email],
        "subject": subject,
        "html": html,
    }
    if equipment:
        csv_body = _build_equipment_csv(equipment)
        payload["attachments"] = [{
            "filename": "equipment.csv",
            "content": base64.b64encode(csv_body.encode("utf-8")).decode("ascii"),
        }]

    resend.api_key = RESEND_API_KEY
    try:
        await asyncio.to_thread(resend.Emails.send, payload)
        logger.info(
            "Supplier welcome email sent to %s (%s, %d machines)",
            email, branding["platform_name"], len(equipment),
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send supplier welcome email: {e}")
        return False


# ── Equipment reassignment notification ─────────────────────────

async def _enrich_equipment_for_email(
    equipment: list[dict], organization_id: str,
) -> list[dict]:
    """Attach open/total fault counts and warranty status to each equipment
    doc so supplier emails arrive briefed instead of blind.

    Runs two batched queries (one issues fetch, one equipment-side parse) so
    performance stays flat regardless of list length.
    """
    if not equipment:
        return equipment

    ids = [e.get("id") for e in equipment if e.get("id")]
    counts: dict[str, dict] = {}
    if ids:
        async for issue in db.issues.find(
            {"organization_id": organization_id, "equipment_id": {"$in": ids}},
            {"_id": 0, "equipment_id": 1, "status": 1},
        ):
            eid = issue.get("equipment_id")
            bucket = counts.setdefault(eid, {"total": 0, "open": 0})
            bucket["total"] += 1
            if issue.get("status") in ("open", "escalated", "in_progress"):
                bucket["open"] += 1

    now = datetime.now(timezone.utc)
    enriched: list[dict] = []
    for e in equipment:
        bucket = counts.get(e.get("id"), {"total": 0, "open": 0})
        warranty_label = _warranty_label(e.get("warranty_expiry"), now)
        enriched.append({
            **e,
            "_open_faults": bucket["open"],
            "_total_faults": bucket["total"],
            "_warranty_label": warranty_label,
        })
    return enriched


def _warranty_label(expiry: str | None, now: datetime) -> str:
    """Human-readable warranty line for supplier emails (e.g. '14 months left',
    'Expired', or empty when unknown)."""
    if not expiry:
        return ""
    try:
        dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (dt - now).days
    except (ValueError, TypeError):
        return ""
    if days <= 0:
        return "Expired"
    months = round(days / 30.44, 1)
    if months >= 1:
        return f"{months} months left"
    return f"{days} days left"


def _build_reassignment_email_html(
    supplier: dict, org_name: str, equipment: list[dict], branding: dict,
) -> str:
    """HTML body telling a supplier that one or more machines have just been
    assigned to them (previous supplier overwritten or fresh assignment).
    Expects each entry to optionally carry `_open_faults`, `_total_faults`,
    `_warranty_label` from _enrich_equipment_for_email.
    """
    contact = supplier.get("contact_person") or supplier.get("name") or "Service Team"
    platform = branding["platform_name"]

    def _fault_badge(open_ct: int, total_ct: int) -> str:
        if open_ct:
            return (
                f'<span style="display:inline-block;padding:2px 6px;background:#FEE2E2;color:#991B1B;'
                f'border-radius:999px;font-size:11px;font-weight:600;">{open_ct} open</span>'
                f'<span style="color:#6B7280;font-size:11px;margin-left:6px;">of {total_ct}</span>'
            )
        if total_ct:
            return f'<span style="color:#6B7280;font-size:11px;">{total_ct} historic</span>'
        return '<span style="color:#9CA3AF;font-size:11px;">none</span>'

    def _warranty_badge(label: str) -> str:
        if not label:
            return '<span style="color:#9CA3AF;font-size:11px;">—</span>'
        if label == "Expired":
            return '<span style="display:inline-block;padding:2px 6px;background:#FEE2E2;color:#991B1B;border-radius:999px;font-size:11px;font-weight:600;">Expired</span>'
        return f'<span style="color:#065F46;font-size:11px;">{label}</span>'

    rows = "".join(f'''
      <tr>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;font-size:13px;">
          <div style="color:#111;font-weight:500;">{e.get("name","")}</div>
          <div style="color:#6B7280;font-size:11px;">{e.get("equipment_type","")}{(" · " + e.get("serial_number","")) if e.get("serial_number") else ""}</div>
        </td>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;font-size:12px;color:#374151;">{e.get("location","")}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;font-size:12px;white-space:nowrap;">{_fault_badge(e.get("_open_faults", 0), e.get("_total_faults", 0))}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;font-size:12px;white-space:nowrap;">{_warranty_badge(e.get("_warranty_label", ""))}</td>
      </tr>''' for e in equipment[:20])
    extra_note = ""
    if len(equipment) > 20:
        extra_note = f'<p style="margin:8px 0 0;font-size:11px;color:#666;">…and {len(equipment) - 20} more (see attached CSV).</p>'

    total_open = sum(e.get("_open_faults", 0) for e in equipment)
    ack_note = (
        f'<div style="margin:14px 0;padding:12px 14px;background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;">'
        f'<p style="margin:0;font-size:12px;color:#991B1B;font-weight:600;">'
        f'⚠ {total_open} open fault{"" if total_open == 1 else "s"} already logged across these machines — please review as priority.'
        f'</p></div>'
    ) if total_open else ""

    return f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden;">
  <div style="background:#0A0A0A;padding:22px 28px;">
    <h1 style="color:#fff;font-size:18px;margin:0;">Machines assigned to you</h1>
    <p style="color:#cbd5e1;font-size:12px;margin:4px 0 0;">{org_name} has updated their supplier records</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#111;font-size:14px;line-height:1.6;margin:0 0 12px;">Hi {contact},</p>
    <p style="color:#111;font-size:14px;line-height:1.6;margin:0 0 16px;">
      <strong>{org_name}</strong> has assigned
      <strong>{len(equipment)} machine{'' if len(equipment) == 1 else 's'}</strong>
      to you on {platform}. Any faults reported against these machines will now
      come directly to you. The table below includes <strong>current open faults</strong>
      and <strong>warranty status</strong> per machine so you can plan your first visit.
    </p>
    {ack_note}
    <div style="border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;margin:12px 0;">
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="background:#F9FAFB;">
            <th style="text-align:left;padding:8px 10px;font-size:11px;color:#374151;text-transform:uppercase;letter-spacing:0.04em;">Machine</th>
            <th style="text-align:left;padding:8px 10px;font-size:11px;color:#374151;text-transform:uppercase;letter-spacing:0.04em;">Location</th>
            <th style="text-align:left;padding:8px 10px;font-size:11px;color:#374151;text-transform:uppercase;letter-spacing:0.04em;">Faults</th>
            <th style="text-align:left;padding:8px 10px;font-size:11px;color:#374151;text-transform:uppercase;letter-spacing:0.04em;">Warranty</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    {extra_note}
    <p style="color:#111;font-size:13px;line-height:1.6;margin:16px 0 0;">
      Full list attached as <strong>equipment.csv</strong>. No action needed right now —
      the next email you receive for any of these machines will be a live fault report.
    </p>
  </div>
  <div style="padding:14px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;">
    <p style="margin:0;font-size:11px;color:#6B7280;">{branding["platform_footer"]}</p>
  </div>
</div>'''


async def send_supplier_reassignment_email(
    supplier: dict, organization_id: str, equipment: list[dict],
    sender_org_name: str | None = None,
) -> bool:
    """Notify a supplier that `equipment` has just been assigned to them.

    Pulse Lite customers are still excluded from outbound platform emails —
    same tier-gate as the welcome email.
    """
    email = (supplier.get("email") or "").strip()
    if not email or not equipment or not RESEND_API_KEY or not resend:
        return False

    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "account_type": 1, "name": 1},
    ) or {}
    if org.get("account_type") not in ("full", "pulse_pro", None):
        return False

    branding = await _resolve_platform_branding(organization_id)
    org_name = sender_org_name or org.get("name") or "Your Gym"
    enriched = await _enrich_equipment_for_email(equipment, organization_id)
    html = _build_reassignment_email_html(supplier, org_name, enriched, branding)
    subject = (
        f"{len(equipment)} machine{'' if len(equipment) == 1 else 's'} assigned "
        f"to you by {org_name} — via {branding['platform_name']}"
    )
    payload = {
        "from": f"{org_name} <faults@service.pulsefitness.ai>",
        "to": [email],
        "subject": subject,
        "html": html,
        "attachments": [{
            "filename": "equipment.csv",
            "content": base64.b64encode(
                _build_equipment_csv(equipment).encode("utf-8"),
            ).decode("ascii"),
        }],
    }

    resend.api_key = RESEND_API_KEY
    try:
        await asyncio.to_thread(resend.Emails.send, payload)
        logger.info(
            "Reassignment email sent to %s (%s, %d machines)",
            email, branding["platform_name"], len(equipment),
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send reassignment email: {e}")
        return False


def _enrich_case(case: dict, issue: dict) -> tuple[dict, float | None]:
    """Enrich a supplier case with issue details. Returns (enriched_case, response_hours_or_None)."""
    first_response = None
    response_hours = None
    hist = case.get("status_history") or []
    if hist:
        first_response = hist[0].get("updated_at")
        if first_response and case.get("created_at"):
            try:
                created = datetime.fromisoformat(case["created_at"].replace("Z", "+00:00"))
                responded = datetime.fromisoformat(first_response.replace("Z", "+00:00"))
                response_hours = (responded - created).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

    return {
        "case_id": case["id"], "supplier_name": case.get("supplier_name", "Unknown"),
        "supplier_email": case.get("supplier_email", ""), "current_status": case.get("current_status", "pending"),
        "created_at": case.get("created_at"), "updated_at": case.get("updated_at"),
        "first_response_at": first_response, "status_history": hist,
        "issue": {
            "id": issue.get("id"), "machine_type": issue.get("machine_type"),
            "serial_number": issue.get("serial_number"),
            "issue_description": issue.get("issue_description", "")[:120],
            "severity": issue.get("severity"), "status": issue.get("status"),
        },
    }, response_hours


def _match_faults_to_suppliers(issues: list, equipment: list) -> dict[str, list]:
    """Match fault issues to equipment manufacturers. Returns {supplier_name: [fault_dicts]}.

    Iter 216h121 — also match by equipment_id (canonical FK on the
    fault record). The legacy serial_number/name match misses demo-
    seeded faults that only reference equipment_id, which surfaced as
    "no faults" on the MOD supplier league table for every supplier
    bar Wattbike (the one supplier with manual ARMY-TEST-001 faults).
    """
    serial_to_eq = {}
    id_to_eq: dict[str, dict] = {}
    for eq in equipment:
        sn = eq.get("serial_number", "")
        if sn:
            serial_to_eq[sn] = eq
        name = eq.get("name", "")
        if name:
            serial_to_eq[name] = eq
        eid = eq.get("id")
        if eid:
            id_to_eq[eid] = eq

    faults_by_supplier: dict[str, list] = {}
    for issue in issues:
        # Prefer the explicit FK; fall back to serial / name match.
        eq_id = issue.get("equipment_id")
        matched = id_to_eq.get(eq_id) if eq_id else None
        if not matched:
            matched = serial_to_eq.get(issue.get("serial_number", ""))
        if not matched:
            continue
        sup = matched.get("supplier_name") or matched.get("manufacturer") or ""
        if not sup:
            continue
        faults_by_supplier.setdefault(sup, []).append({
            "id": issue.get("id"), "machine_type": issue.get("machine_type") or matched.get("equipment_type"),
            "serial_number": issue.get("serial_number") or matched.get("serial_number"),
            "description": (issue.get("issue_description") or "")[:120],
            "severity": issue.get("severity"), "status": issue.get("status"),
            "created_at": issue.get("created_at"),
            # Iter 216h126 — also surface resolved_at so TTF calculation works.
            "resolved_at": issue.get("resolved_at"),
            "updated_at": issue.get("updated_at"),
        })
    return faults_by_supplier


def _build_supplier_map(equipment: list) -> dict[str, dict]:
    """Build a supplier → {name, equipment_count, types, machine_breakdown} map.

    Iter 216h126 — `machine_breakdown` is a dict keyed by equipment_type
    with `{count, model_breakdown}` so Jack can drill into "Life Fitness
    → Treadmill 7, Upright bike 4". The model_breakdown sub-dict counts
    each distinct model/name within that type.
    """
    supplier_map: dict[str, dict] = {}
    for eq in equipment:
        sup = eq.get("supplier_name") or eq.get("manufacturer") or ""
        if not sup:
            continue
        if sup not in supplier_map:
            supplier_map[sup] = {
                "name": sup, "equipment_count": 0,
                "types": set(),
                "type_counts": {},          # {Treadmill: 7, Bike: 4, ...}
                "model_counts": {},         # {"Treadmill": {"Integrity X": 5, ...}}
            }
        bucket = supplier_map[sup]
        bucket["equipment_count"] += 1
        etype = eq.get("equipment_type") or "Unknown"
        bucket["types"].add(etype)
        bucket["type_counts"][etype] = bucket["type_counts"].get(etype, 0) + 1
        bucket["model_counts"].setdefault(etype, {})
        model_key = eq.get("model") or eq.get("name") or "Unspecified"
        bucket["model_counts"][etype][model_key] = bucket["model_counts"][etype].get(model_key, 0) + 1
    return supplier_map


def _build_eq_suppliers(supplier_map: dict, faults_by_supplier: dict) -> list:
    """Build the final equipment_suppliers list with fault data + drill-down breakdown."""
    eq_suppliers = []
    for s in supplier_map.values():
        faults = faults_by_supplier.get(s["name"], [])
        # ── Compute average Time-to-Fix (TTF) across resolved faults ──
        # Iter 216h126 (Jack's #6): Reports → Suppliers wants a TTF KPI.
        # Hours from `created_at` to `resolved_at`.
        ttf_hours: list[float] = []
        for f in faults:
            if f.get("status") != "resolved":
                continue
            try:
                ca = datetime.fromisoformat(str(f.get("created_at")).replace("Z", "+00:00"))
                ra = datetime.fromisoformat(str(f.get("resolved_at") or f.get("updated_at") or "").replace("Z", "+00:00"))
                if ra > ca:
                    ttf_hours.append((ra - ca).total_seconds() / 3600)
            except (ValueError, TypeError):
                continue
        avg_ttf = round(sum(ttf_hours) / len(ttf_hours), 1) if ttf_hours else None

        eq_suppliers.append({
            "name": s["name"], "equipment_count": s["equipment_count"],
            "equipment_types": sorted(s["types"]),
            "type_counts": s.get("type_counts", {}),
            "model_counts": s.get("model_counts", {}),
            "faults": faults,
            "open_faults": sum(1 for f in faults if f["status"] not in ("resolved", "closed")),
            "avg_time_to_fix_hours": avg_ttf,
            "resolved_faults": sum(1 for f in faults if f.get("status") == "resolved"),
            # Iter 220n — decorate with the db.suppliers metadata so the
            # frontend can render the "Auto-added from referral" badge,
            # the auto-dispatch toggle, and the primary-supplier crown.
            "id": s.get("id"),
            "email": s.get("email"),
            "auto_dispatch": s.get("auto_dispatch", False),
            "is_primary_supplier": s.get("is_primary_supplier", False),
            "auto_created_from_referral": s.get("auto_created_from_referral", False),
            "partner_engineer_id": s.get("partner_engineer_id"),
        })
    eq_suppliers.sort(key=lambda x: -x["equipment_count"])
    return eq_suppliers


def _supplier_performance_index(supplier_records: list[dict], cases_by_supplier: dict) -> list[dict]:
    """Iter 216h121 — compute a 0-100 performance score per supplier so
    the Suppliers tab can render a league table.

    Inputs:
      supplier_records  — output of `_build_eq_suppliers`
      cases_by_supplier — dict[supplier_name → list[supplier_case dict]]
                          (case docs straight from db.supplier_cases)

    Score breakdown (lower = worse, higher = better):
      • Resolution rate     (40 pts)  closed/total faults
      • Average rating      (30 pts)  cases.rating  (1-5 scale → 0-30)
      • Response speed      (20 pts)  20pts ≤ 24h · 10pts ≤ 48h · 0 ≥ 96h
      • Open-fault penalty  (10 pts)  -2 per open fault, capped to 10

    A supplier with no cases at all gets a "neutral" 70 + (mini bonus
    for healthy install base) — they're a known supplier we've not
    yet had to call.
    """
    ranked = []
    for sup in supplier_records:
        name = sup["name"]
        faults = sup.get("faults", [])
        total_faults = len(faults)
        closed_faults = sum(1 for f in faults if f.get("status") in ("resolved", "closed"))
        open_faults = sup.get("open_faults", 0)

        cases = cases_by_supplier.get(name, [])
        ratings = [c.get("rating") for c in cases if isinstance(c.get("rating"), (int, float))]
        avg_rating = (sum(ratings) / len(ratings)) if ratings else None

        # Response speed across all cases that have a status_history entry.
        resp_hours: list[float] = []
        for c in cases:
            hist = c.get("status_history") or []
            if not hist or not c.get("created_at"):
                continue
            first = hist[0].get("updated_at")
            if not first:
                continue
            try:
                created = datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00"))
                responded = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
                resp_hours.append((responded - created).total_seconds() / 3600)
            except (ValueError, TypeError):
                continue
        avg_response_h = (sum(resp_hours) / len(resp_hours)) if resp_hours else None

        # ── score ──
        if total_faults == 0 and not cases:
            # Neutral starting score for unblooded suppliers, plus a
            # small bonus for breadth of install (capped 10).
            score = 70 + min(10, sup["equipment_count"])
            resolution_rate = None
        else:
            resolution_rate = (closed_faults / total_faults) if total_faults else 1.0
            score = 0.0
            score += round(resolution_rate * 40, 1)
            if avg_rating is not None:
                score += round((avg_rating / 5.0) * 30, 1)
            else:
                # No ratings yet — neutral 18 pts.
                score += 18
            if avg_response_h is None:
                score += 12
            elif avg_response_h <= 24:
                score += 20
            elif avg_response_h <= 48:
                score += 10
            elif avg_response_h <= 96:
                score += 5
            score -= min(10, open_faults * 2)
            score = max(0, min(100, score))

        # League "grade" — A (>=85) · B · C · D · F (<40).
        grade = (
            "A" if score >= 85 else
            "B" if score >= 70 else
            "C" if score >= 55 else
            "D" if score >= 40 else "F"
        )

        ranked.append({
            **sup,
            "score": round(score, 1),
            "grade": grade,
            "resolution_rate": (round(resolution_rate, 2) if resolution_rate is not None else None),
            "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
            "avg_response_hours": round(avg_response_h, 1) if avg_response_h is not None else None,
            "cases_count": len(cases),
        })
    ranked.sort(key=lambda x: (-x["score"], -x["equipment_count"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


@router.get("/supplier-dashboard")
async def get_supplier_dashboard(
    user: dict = Depends(get_current_user),
    site_id: str | None = None,
):
    """Get all supplier cases + equipment supplier league table for the
    organization (or one MOD child site when `site_id` is supplied).

    Iter 216h121 — adds the league-table scoring + MOD HQ rollup. HQ
    users with no `site_id` see the whole estate's suppliers; passing
    a site_id drills into that base only.
    """
    # MOD-aware: lets HQ users roll up or drill into child orgs.
    from utils.mod_scope import resolve_mod_query_filter
    org_filter = await resolve_mod_query_filter(user, site_id)

    issues = await db.issues.find({**org_filter}, {"_id": 0}).to_list(5000)
    issue_map = {i["id"]: i for i in issues}
    cases = await db.supplier_cases.find(
        {"issue_id": {"$in": list(issue_map)}}, {"_id": 0},
    ).sort("created_at", -1).to_list(2000)

    enriched, total_hours, responded = [], 0.0, 0
    cases_by_supplier: dict[str, list] = {}
    for case in cases:
        ec, hours = _enrich_case(case, issue_map.get(case.get("issue_id"), {}))
        enriched.append(ec)
        if hours is not None:
            total_hours += hours
            responded += 1
        sup_name = (case.get("supplier_name") or "").strip()
        if sup_name:
            cases_by_supplier.setdefault(sup_name, []).append(case)

    status_counts: dict[str, int] = {}
    for c in enriched:
        status_counts[c["current_status"]] = status_counts.get(c["current_status"], 0) + 1

    eq_fields = {"_id": 0, "id": 1, "supplier_name": 1, "manufacturer": 1, "equipment_type": 1, "name": 1, "serial_number": 1}
    equipment = await db.equipment.find(org_filter, eq_fields).to_list(5000)
    supplier_map = _build_supplier_map(equipment)
    # Iter 220n — surface explicit `db.suppliers` rows too so a freshly
    # auto-added Partner Engineer (no equipment bound yet) still appears
    # on the dashboard with the "Auto-added from referral" badge. Also
    # decorates every supplier (even those with equipment) with the
    # auto_dispatch + auto_created_from_referral + partner_engineer_id
    # flags so the UI can render the badge + the routing toggle.
    supplier_rows = await db.suppliers.find(
        {**org_filter},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "auto_dispatch": 1,
         "is_primary_supplier": 1, "auto_created_from_referral": 1,
         "partner_engineer_id": 1, "supplier_types": 1, "created_at": 1},
    ).to_list(500)
    for row in supplier_rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if name not in supplier_map:
            # Fresh referral with no equipment yet — show as ready-to-route.
            supplier_map[name] = {
                "name": name, "equipment_count": 0,
                "types": set(), "type_counts": {}, "model_counts": {},
            }
        # Decorate (works for both fresh + already-engaged suppliers).
        supplier_map[name].update({
            "id": row.get("id"),
            "email": row.get("email"),
            "auto_dispatch": bool(row.get("auto_dispatch")),
            "is_primary_supplier": bool(row.get("is_primary_supplier")),
            "auto_created_from_referral": bool(row.get("auto_created_from_referral")),
            "partner_engineer_id": row.get("partner_engineer_id"),
        })
    faults_by_supplier = _match_faults_to_suppliers(issues, equipment)
    eq_suppliers = _build_eq_suppliers(supplier_map, faults_by_supplier)
    # Iter 216h121 — league table scoring (computed after building the
    # base supplier list so we re-use the fault counts already collected).
    eq_suppliers = _supplier_performance_index(eq_suppliers, cases_by_supplier)

    return {
        "cases": enriched,
        "equipment_suppliers": eq_suppliers,
        "metrics": {
            "total_cases": len(enriched), "status_breakdown": status_counts,
            "avg_response_hours": round(total_hours / responded, 1) if responded else None,
            "responded_count": responded, "pending_count": status_counts.get("pending", 0),
            "suppliers_total": len(eq_suppliers),
            "scope": "site" if site_id else "estate",
        },
    }


def _build_equipment_summary(equipment: dict | None) -> dict | None:
    """Extract relevant equipment fields for supplier view."""
    if not equipment:
        return None
    return {k: equipment.get(k) for k in ("name", "equipment_type", "manufacturer", "model", "serial_number", "location", "sla_response_time", "sla_contract_ref")}


async def _resolve_reporter_contact(issue: dict) -> dict:
    """Best-effort lookup of the person who reported the issue: name, phone, email."""
    reporter_id = issue.get("reported_by") or issue.get("user_id")
    contact = {
        "name": issue.get("reported_by_name") or issue.get("reporter_name")
                or issue.get("created_by_name") or "",
        "email": issue.get("reported_by_email") or issue.get("reporter_email")
                 or issue.get("created_by_email") or "",
        "phone": issue.get("reported_by_phone") or issue.get("reporter_phone")
                 or issue.get("created_by_mobile") or "",
        "role": "",
    }
    # Faults logged via the shared gym-floor login carry an explicit role label
    # so suppliers know they came from a shift worker (not a manager / admin).
    if issue.get("created_via") == "gym_floor":
        contact["role"] = "Gym Floor"
    if reporter_id and not str(reporter_id).startswith("gym-floor:"):
        user = await db.users.find_one(
            {"id": reporter_id},
            {"_id": 0, "full_name": 1, "email": 1, "phone": 1, "role": 1},
        )
        if user:
            contact["name"] = contact["name"] or user.get("full_name", "")
            contact["email"] = contact["email"] or user.get("email", "")
            contact["phone"] = contact["phone"] or user.get("phone", "")
            contact["role"] = contact["role"] or (user.get("role", "") or "").replace("_", " ").title()
    return contact


async def _resolve_site_details(organization_id: str | None) -> dict:
    """Return the gym's postal address, main phone and support email for the fault card."""
    if not organization_id:
        return {}
    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "name": 1, "address": 1, "city": 1, "postcode": 1, "country": 1,
         "phone": 1, "primary_contact_phone": 1, "primary_contact_email": 1,
         "primary_contact_name": 1, "website": 1},
    ) or {}
    addr_parts = [org.get("address"), org.get("city"), org.get("postcode"), org.get("country")]
    postal = ", ".join([p for p in addr_parts if p])
    return {
        "gym_name": org.get("name", ""),
        "address": postal,
        "address_lines": [p for p in addr_parts if p],
        "phone": org.get("phone") or org.get("primary_contact_phone") or "",
        "email": org.get("primary_contact_email") or "",
        "primary_contact_name": org.get("primary_contact_name", ""),
        "website": org.get("website", ""),
    }


def _case_summary_header(case: dict, issue: dict, job_ref: str) -> list[str]:
    return [
        f"Job: {job_ref}",
        f"Status: {(case.get('current_status') or issue.get('status') or 'pending').replace('_', ' ').title()}",
        f"Severity: {(issue.get('severity') or '').title() or 'Unspecified'}",
        f"Reported: {(issue.get('created_at') or '')[:16].replace('T', ' ')}",
    ]


def _case_summary_site(site: dict) -> list[str]:
    lines = ["", "-- GYM / SITE --", f"Site: {site.get('gym_name', '')}"]
    if site.get("address"):
        lines.append(f"Address: {site['address']}")
    if site.get("phone"):
        lines.append(f"Site Phone: {site['phone']}")
    if site.get("website"):
        lines.append(f"Website: {site['website']}")
    return lines


def _case_summary_reporter(reporter: dict) -> list[str]:
    lines = ["", "-- REPORTER --", f"Name: {reporter.get('name', '') or 'Unknown'}"]
    for key, label in (("role", "Role"), ("email", "Email"), ("phone", "Phone")):
        val = reporter.get(key)
        if val:
            lines.append(f"{label}: {val}")
    return lines


def _case_summary_fault(issue: dict) -> list[str]:
    lines = [
        "",
        "-- EQUIPMENT --",
        f"Type: {issue.get('machine_type', '') or 'Unspecified'}",
    ]
    if issue.get("serial_number"):
        lines.append(f"Serial: {issue['serial_number']}")
    lines += [
        "",
        "-- FAULT --",
        f"{issue.get('issue_description', '') or '(no description)'}",
    ]
    triage = issue.get("ai_triage") or {}
    if triage.get("likely_cause"):
        lines += ["", "-- AI TRIAGE --", f"Likely cause: {triage['likely_cause']}"]
        if triage.get("recommended_action"):
            lines.append(f"Suggested action: {triage['recommended_action']}")
    return lines


@router.get("/supplier/case/{token}/summary.txt")
async def export_case_summary(token: str):
    """Return a plain-text, key:value summary of the case that suppliers can
    paste into their own ticketing system (ServiceM8, Freshdesk, Zendesk, etc).
    """
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    issue = await db.issues.find_one({"id": case["issue_id"]}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    reporter = await _resolve_reporter_contact(issue)
    site = await _resolve_site_details(issue.get("organization_id"))
    job_ref = _short_case_ref(case, issue)
    branding = await _resolve_platform_branding(issue.get("organization_id"))
    from utils.brand_urls import app_url_for

    lines = (
        _case_summary_header(case, issue, job_ref)
        + _case_summary_site(site)
        + _case_summary_reporter(reporter)
        + _case_summary_fault(issue)
        + [
            "",
            "-- LINK --",
            f"Live case: {app_url_for(case.get('organization_account_type'))}/supplier/case/{token}",
            "",
            f"(Delivered via {branding['platform_name']})",
        ]
    )
    text = "\n".join(lines)
    filename = f"Job_{job_ref}.txt"
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pulse Fitness-Job": job_ref,
            "X-Pulse Fitness-Site": site.get("gym_name", ""),
        },
    )


@router.get("/supplier/case/{token}/contact.vcf")
async def export_site_vcard(token: str):
    """Return a vCard for the gym so the supplier can one-click add them to
    their address book. Works in iOS, Android, Outlook, Google Contacts."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0, "issue_id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    issue = await db.issues.find_one({"id": case["issue_id"]}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    site = await _resolve_site_details(issue.get("organization_id"))
    reporter = await _resolve_reporter_contact(issue)

    name = reporter.get("name") or site.get("primary_contact_name") or site.get("gym_name") or "Gym Contact"
    gym = site.get("gym_name", "")
    # Reporter > site phone/email (reporter is the person the supplier actually needs to reach)
    phone = (reporter.get("phone") or "").strip() or (site.get("phone") or "").strip()
    email = (reporter.get("email") or "").strip() or (site.get("email") or "").strip()
    addr = ";;" + ";".join([
        site.get("address_lines", [""])[0] if site.get("address_lines") else "",
        site.get("address_lines", ["", ""])[1] if len(site.get("address_lines", [])) > 1 else "",
        "",
        site.get("address_lines", ["", "", ""])[-1] if site.get("address_lines") else "",
        "",
    ])
    vcard = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"FN:{name}\r\n"
        f"ORG:{gym}\r\n"
        + (f"TITLE:{reporter.get('role', '')}\r\n" if reporter.get("role") else "")
        + (f"TEL;TYPE=WORK,VOICE:{phone}\r\n" if phone else "")
        + (f"EMAIL;TYPE=WORK:{email}\r\n" if email else "")
        + (f"ADR;TYPE=WORK:{addr}\r\n" if site.get("address") else "")
        + (f"URL:{site.get('website','')}\r\n" if site.get("website") else "")
        + "END:VCARD\r\n"
    )
    return Response(
        content=vcard,
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{(gym or "site").replace(" ", "_")}.vcf"'},
    )


async def _mark_gym_comments_read_by_supplier(case_id: str) -> None:
    """Stamp `read_at_supplier` on unread gym-authored comments for this case.

    Called when a supplier opens the public case page (token-based, no auth) —
    lets the gym see a "Seen" indicator on their own messages. Idempotent:
    already-read comments are skipped via the `read_at_supplier: None` filter.
    """
    try:
        await db.supplier_case_comments.update_many(
            {
                "case_id": case_id,
                "author_role": "gym",
                "$or": [
                    {"read_at_supplier": {"$exists": False}},
                    {"read_at_supplier": None},
                ],
            },
            {"$set": {"read_at_supplier": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning(f"read-receipt stamp failed for case {case_id}: {e}")


async def mark_supplier_comments_read_by_gym(case_id: str) -> None:
    """Stamp `read_at_gym` on unread supplier-authored comments for this case.

    Called when a gym user opens the issue detail page — lets the supplier
    see a "Seen" indicator on their own replies via the public case page.
    Idempotent; non-blocking on failure.
    """
    try:
        await db.supplier_case_comments.update_many(
            {
                "case_id": case_id,
                "author_role": "supplier",
                "$or": [
                    {"read_at_gym": {"$exists": False}},
                    {"read_at_gym": None},
                ],
            },
            {"$set": {"read_at_gym": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as e:  # pragma: no cover — non-blocking
        logger.warning(f"gym read-receipt stamp failed for case {case_id}: {e}")


@router.get("/supplier/case/{token}")
async def get_supplier_case(token: str, request: Request):
    """Public endpoint - supplier accesses case via secure token from email link."""
    # IP-scoped rate limit — prevents token-guessing brute force attacks.
    from utils.security_plus import rate_limit_async, validate_supplier_token
    from utils.auth import try_get_current_user
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"supplier_case_ip:{ip}", max_requests=60, window_seconds=300)
    # P1+.13 — validate token + enforce TTL
    case = await validate_supplier_token(token)

    # Read-receipts: if the viewer is NOT an authenticated gym user, treat
    # this as a supplier visit and mark gym-authored messages as seen.
    gym_user = await try_get_current_user(request)
    if not gym_user or gym_user.get("is_supplier"):
        await _mark_gym_comments_read_by_supplier(case["id"])

    issue = await db.issues.find_one({"id": case["issue_id"]}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    equipment = None
    if issue.get("serial_number"):
        equipment = await db.equipment.find_one(
            {"$or": [{"serial_number": issue["serial_number"]}, {"name": issue["serial_number"]}]}, {"_id": 0},
        )

    media = [a for a in issue.get("attachments", []) if a.get("content_type", "").startswith(("image/", "video/"))]

    reporter = await _resolve_reporter_contact(issue)
    site = await _resolve_site_details(issue.get("organization_id"))
    job_ref = _short_case_ref(case, issue)

    # White-label: Pulse customers never see "Pulse Fitness AI"
    org = await db.organizations.find_one(
        {"id": issue.get("organization_id")},
        {"_id": 0, "account_type": 1, "name": 1, "brand_color": 1, "branding": 1, "logo_url": 1},
    ) or {}
    account_type = org.get("account_type") or ""
    is_pulse = account_type in ("pulse_pro", "lite")
    platform_name = "Pulse Fitness" if is_pulse else "Pulse Fitness AI"
    platform_tagline = "Service Portal" if is_pulse else "Service Case"
    # Brand colour priority: explicit brand_color → branding.primary_color → default
    branding = org.get("branding") or {}
    brand_color = (org.get("brand_color") or branding.get("primary_color")
                   or ("#0055FF" if is_pulse else "#0055FF"))
    logo_url = org.get("logo_url") or branding.get("logo_url") or None

    return {
        "case_id": case["id"], "po_number": case.get("po_number"),
        "job_ref": job_ref,
        "platform_name": platform_name,
        "platform_tagline": platform_tagline,
        "is_pulse_branded": is_pulse,
        "brand_color": brand_color,
        "logo_url": logo_url,
        "issue": {
            "id": issue["id"], "machine_type": issue.get("machine_type"), "serial_number": issue.get("serial_number"),
            "issue_description": issue.get("issue_description"), "severity": issue.get("severity"),
            "status": issue.get("status"), "ai_triage": issue.get("ai_triage"),
            "can_fix_onsite": issue.get("can_fix_onsite"), "created_at": issue.get("created_at"),
            # Job Card snapshot — supplier needs these to match their own systems
            "sicon_case_id": issue.get("sicon_case_id"),
            "sicon_case_number": issue.get("sicon_case_number"),
            "sicon_status": issue.get("sicon_status"),
            "sicon_priority": issue.get("sicon_priority"),
            "sicon_assigned_to": issue.get("sicon_assigned_to"),
            "sicon_sub_location_description": issue.get("sicon_sub_location_description"),
            "sicon_sub_location_comment": issue.get("sicon_sub_location_comment"),
            "sicon_appointments": [
                {
                    "scheduled_start": a.get("scheduled_start"),
                    "appointment_complete": a.get("appointment_complete", False),
                    "appointment_type": a.get("appointment_type"),
                    "employee_ids": a.get("employee_ids", []),
                }
                for a in (issue.get("sicon_appointments") or [])
            ],
        },
        "reporter": reporter,
        "site": site,
        "equipment": _build_equipment_summary(equipment), "media": media,
        "supplier_name": case.get("supplier_name"),
        "organization_name": case.get("organization_name") or org.get("name") or "",
        "supplier_email": case.get("supplier_email", ""),
        "site_contact_email": case.get("site_contact_email", ""),
        "status_history": case.get("status_history", []), "current_status": case.get("current_status", "pending"),
        "scheduled_date": case.get("scheduled_date"),
        "engineer_name": case.get("engineer_name"),
        "rating": case.get("rating"),
        "rating_feedback": case.get("rating_feedback"),
        "comments": await db.supplier_case_comments.find({"case_id": case["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500),
    }


@router.post("/supplier/case/{token}/update")
async def update_supplier_case(token: str, data: Dict[str, Any]):
    """Supplier updates case status - no login required, token auth only."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or link expired")

    new_status = data.get("status")
    valid_statuses = ["acknowledged", "engineer_scheduled", "in_progress", "parts_ordered", "completed"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    update_entry = {
        "status": new_status,
        "notes": data.get("notes", ""),
        "engineer_name": data.get("engineer_name"),
        "estimated_arrival": data.get("estimated_arrival"),
        "parts_required": data.get("parts_required"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.supplier_cases.update_one(
        {"token": token},
        {
            "$set": {"current_status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()},
            "$push": {"status_history": update_entry}
        }
    )

    issue_status_map = {
        "acknowledged": "in_progress",
        "engineer_scheduled": "in_progress",
        "in_progress": "in_progress",
        "parts_ordered": "in_progress",
        "completed": "resolved",
    }
    issue_status = issue_status_map.get(new_status, "in_progress")
    await db.issues.update_one(
        {"id": case["issue_id"]},
        {"$set": {
            "status": issue_status,
            "supplier_status": new_status,
            "supplier_notes": data.get("notes", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **({"resolved_at": datetime.now(timezone.utc).isoformat()} if new_status == "completed" else {})
        }}
    )

    await _sicon_note_after_supplier_update(case, new_status, data)

    return {"success": True, "new_status": new_status}


async def _sicon_note_after_supplier_update(case: dict, new_status: str, data: Dict[str, Any]) -> None:
    """Post a tracking note to Sicon describing a supplier-side status change."""
    try:
        from utils.sicon_sync import on_supplier_scheduled_visit, on_supplier_responded
        supplier_name = case.get("supplier_name", "Supplier")
        if new_status == "engineer_scheduled" and data.get("estimated_arrival"):
            await on_supplier_scheduled_visit(case["issue_id"], supplier_name, data["estimated_arrival"])
        else:
            msg = f"Status = {new_status}. {data.get('notes', '') or ''}".strip()
            await on_supplier_responded(case["issue_id"], supplier_name, msg)
    except Exception as e:
        logger.warning(f"Sicon supplier update note failed (non-blocking): {e}")


async def create_supplier_case(issue_id: str, supplier_name: str, supplier_email: str, organization_name: str, base_url: str):
    """Called internally when an issue is escalated to supplier. Returns case token."""
    # Resolve the org's account_type (gymaxis / pulse) so brand-aware
    # email links can pick the right public domain on every send.
    org_id = None
    org_account_type = None
    try:
        issue = await db.issues.find_one({"id": issue_id}, {"_id": 0, "organization_id": 1})
        org_id = (issue or {}).get("organization_id")
        if org_id:
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "account_type": 1})
            org_account_type = (org or {}).get("account_type")
    except Exception:
        pass

    token = str(uuid.uuid4())
    case_doc = {
        "id": str(uuid.uuid4()),
        "token": token,
        "issue_id": issue_id,
        "supplier_name": supplier_name,
        "supplier_email": supplier_email,
        "organization_id": org_id,
        "organization_name": organization_name,
        "organization_account_type": org_account_type,
        "current_status": "pending",
        "status_history": [],
        "token_expires_at": (datetime.now(timezone.utc) + timedelta(
            days=int(os.environ.get("SUPPLIER_TOKEN_TTL_DAYS", "30"))
        )).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.supplier_cases.insert_one(case_doc)
    # P2.15 — fail-closed audit trail for every supplier link issued.
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "supplier.token.issued",
        "case_id": case_doc["id"],
        "issue_id": issue_id,
        "supplier_email": supplier_email,
        "token_expires_at": case_doc["token_expires_at"],
    })
    # Always emit the brand-correct URL — ignore the legacy ``base_url``
    # passed by callers (it was hardcoded to ``FRONTEND_URL``).
    from utils.brand_urls import app_url_for
    supplier_url = f"{app_url_for(org_account_type)}/supplier/case/{token}"
    return {"token": token, "url": supplier_url, "case_id": case_doc["id"]}


# ── COMMENTS (two-way conversation) ──────────────────────────────

def _build_comment_email_params(case: dict, comment: dict, to_supplier: bool, machine: str, branding: dict) -> dict:
    """Build email parameters (to, from, subject, intro) for a comment notification."""
    org_name = case.get("organization_name", "Site")
    supplier_name = case.get("supplier_name", "Supplier")
    if to_supplier:
        return {
            "to_email": case.get("supplier_email", ""),
            "from_line": f"{org_name} <faults@service.pulsefitness.ai>",
            "subject": f"New message from {org_name} — {machine}",
            "intro": f"{org_name} has posted a new comment on the fault report for <strong>{machine}</strong>.",
        }
    return {
        "to_email": case.get("site_contact_email", ""),
        "from_line": f"{supplier_name} {branding['via_label']} <faults@service.pulsefitness.ai>",
        "subject": f"Supplier update from {supplier_name} — {machine}",
        "intro": f"{supplier_name} has posted a new comment on the fault report for <strong>{machine}</strong>.",
    }


def _short_case_ref(case: dict, issue: dict | None) -> str:
    """Return a short, human-readable case / job reference for the email subject & body."""
    fault_ref = (issue or {}).get("fault_report_ref") or (issue or {}).get("ticket_number")
    if fault_ref:
        return str(fault_ref)
    case_id = case.get("id") or ""
    return f"JOB-{case_id[:8].upper()}" if case_id else "JOB"


def _build_reporter_block(reporter: dict) -> str:
    """Render a 'Reported by' contact block for the supplier email body.

    Phone & email are click-to-call / click-to-email so an engineer can reach
    out from their inbox in one tap. Returns an empty string if we don't have
    at least a name or email — no point showing a card with nothing in it.
    """
    if not reporter:
        return ""
    name = (reporter.get("name") or "").strip()
    email = (reporter.get("email") or "").strip()
    phone = (reporter.get("phone") or "").strip()
    role = (reporter.get("role") or "").strip()
    if not (name or email or phone):
        return ""

    # Subtle role chip — only renders if we know the role (e.g. "Gym Floor").
    role_chip = (
        f'<span style="display:inline-block;margin-left:8px;padding:2px 8px;'
        f'background:#E0F2FE;color:#0369A1;font-size:10px;font-weight:700;'
        f'border-radius:999px;text-transform:uppercase;letter-spacing:0.04em;">'
        f'{role}</span>'
    ) if role else ""

    name_html = f'<p style="margin:0;font-size:14px;color:#111;font-weight:600;">{name or "Reporter"}{role_chip}</p>'

    contact_lines: list[str] = []
    if email:
        contact_lines.append(
            f'<a href="mailto:{email}" style="color:#0055FF;text-decoration:none;font-weight:500;">{email}</a>'
        )
    if phone:
        # Strip non-dial characters for the tel: href so iOS/Android dialers
        # parse cleanly even if the stored number has spaces or dashes.
        tel = re.sub(r"[^\d+]", "", phone)
        contact_lines.append(
            f'<a href="tel:{tel}" style="color:#0055FF;text-decoration:none;font-weight:500;">{phone}</a>'
        )
    contact_html = (
        '<p style="margin:6px 0 0;font-size:13px;color:#374151;">'
        + " · ".join(contact_lines) + "</p>"
        if contact_lines else ""
    )

    return f'''
    <div style="margin:16px 0;padding:14px 16px;background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;">
      <p style="margin:0 0 4px;font-size:11px;color:#0369A1;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;">Reported by</p>
      {name_html}
      {contact_html}
    </div>'''


def _build_comment_email_html(case: dict, comment: dict, intro: str, branding: dict,
                              issue: dict | None, case_ref: str,
                              reporter: dict | None = None) -> str:
    """Build HTML body for a comment notification email."""
    from utils.brand_urls import app_url_for
    org_name = case.get("organization_name", "Site")
    # Use the brand-correct domain (www.pulsefitness.ai / pulsefitness.ai) so
    # suppliers never see preview.emergentagent.com in real emails.
    base_url = app_url_for(case.get("organization_account_type"))
    case_url = f"{base_url}/supplier/case/{case.get('token', '')}"
    attachments = comment.get("attachments", [])
    attachment_note = f'<p style="color:#666;font-size:12px;margin-top:8px;">Includes {len(attachments)} attachment(s)</p>' if attachments else ""
    fault_desc = (issue or {}).get("issue_description", "") or ""
    machine_type = (issue or {}).get("machine_type", "Equipment")
    serial = (issue or {}).get("serial_number", "")

    fault_block = f'''
    <div style="margin:16px 0;padding:12px 16px;background:#FFFBEA;border:1px solid #FDE68A;border-radius:8px;">
      <p style="margin:0;font-size:11px;color:#92400E;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;">Job {case_ref} · {machine_type}{f" · {serial}" if serial else ""}</p>
      <p style="margin:6px 0 0;font-size:13px;color:#111;line-height:1.5;"><strong>Fault:</strong> {fault_desc[:500]}</p>
    </div>''' if fault_desc else f'''
    <div style="margin:16px 0;padding:12px 16px;background:#FFFBEA;border:1px solid #FDE68A;border-radius:8px;">
      <p style="margin:0;font-size:11px;color:#92400E;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;">Job {case_ref} · {machine_type}{f" · {serial}" if serial else ""}</p>
    </div>'''

    reporter_block = _build_reporter_block(reporter or {})

    return f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;">
  <div style="background:#0A0A0A;padding:20px 28px;">
    <h1 style="color:#fff;font-size:16px;margin:0;">{org_name} — Fault Communication</h1>
    <p style="color:#888;font-size:12px;margin:4px 0 0;">{branding["via_label"]}</p>
  </div>
  <div style="padding:28px;">
    <p style="color:#111;font-size:14px;line-height:1.5;">{intro}</p>
    {fault_block}
    {reporter_block}
    <div style="margin:16px 0;padding:16px;background:#F9FAFB;border-radius:8px;border-left:4px solid #007AFF;">
      <p style="margin:0;font-size:12px;color:#666;font-weight:600;">{comment.get("author_name", "Unknown")} — {comment.get("author_role", "").replace("_", " ").title()}</p>
      <p style="margin:8px 0 0;color:#111;font-size:14px;line-height:1.5;">{comment.get("message", "")}</p>
      {attachment_note}
    </div>
    <a href="{case_url}" style="display:inline-block;margin-top:12px;padding:10px 24px;background:#007AFF;color:#fff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;">View & Reply</a>
  </div>
  <div style="padding:14px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;">
    <p style="margin:0;font-size:11px;color:#999;">{branding["platform_footer"]}</p>
    <p style="margin:4px 0 0;font-size:11px;color:#c00;">Do not reply to this email — use the View & Reply button above to respond.</p>
  </div>
</div>'''


async def _send_comment_notification(case: dict, comment: dict, to_supplier: bool):
    """Send email notification when a new comment is posted."""
    if not RESEND_API_KEY or not resend:
        return
    resend.api_key = RESEND_API_KEY

    issue = await db.issues.find_one({"id": case.get("issue_id")}, {"_id": 0})
    machine = issue.get("machine_type", "Equipment") if issue else "Equipment"
    branding = await _resolve_platform_branding((issue or {}).get("organization_id"))
    case_ref = _short_case_ref(case, issue)

    params = _build_comment_email_params(case, comment, to_supplier, machine, branding)
    if not params["to_email"]:
        return
    # Prefix subject with job ref so supplier inbox threads stay sane.
    params["subject"] = f"[{case_ref}] {params['subject']}"

    # Surface the reporter contact prominently — but only when the email is
    # going to the supplier. The gym side already knows who logged the fault.
    reporter = await _resolve_reporter_contact(issue or {}) if to_supplier else None
    html = _build_comment_email_html(case, comment, params["intro"], branding, issue, case_ref, reporter)

    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": params["from_line"],
            "to": [params["to_email"]],
            "subject": params["subject"],
            "html": html,
        })
        logger.info(f"Comment notification sent to {params['to_email']}")
    except Exception as e:
        logger.warning(f"Failed to send comment notification: {e}")


@router.post("/supplier/case/{token}/update-email")
async def update_supplier_email(token: str, data: Dict[str, Any]):
    """Update the supplier email on a case (for when it wasn't provided initially)."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    supplier_email = (data.get("supplier_email") or "").strip().lower()
    if not supplier_email or "@" not in supplier_email:
        raise HTTPException(400, "Valid email required")
    await db.supplier_cases.update_one({"token": token}, {"$set": {"supplier_email": supplier_email}})
    return {"success": True}


@router.get("/supplier/case/{token}/comments")
async def get_case_comments(token: str, request: Request):
    """Get all comments for a supplier case — public endpoint."""
    from utils.auth import try_get_current_user
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    # Read-receipts: mark gym comments as seen by supplier if the viewer
    # isn't an authenticated gym user (i.e. the supplier is polling the
    # public endpoint).
    gym_user = await try_get_current_user(request)
    if not gym_user or gym_user.get("is_supplier"):
        await _mark_gym_comments_read_by_supplier(case["id"])
    comments = await db.supplier_case_comments.find(
        {"case_id": case["id"]}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return {"comments": comments}


async def _build_upload_attachment(case_id: str, file: UploadFile) -> dict:
    """Upload the attachment and return its metadata."""
    data = await file.read()
    path = f"supplier_comments/{case_id}/{uuid.uuid4()}/{file.filename}"
    result = put_object(path, data, file.content_type or "application/octet-stream")
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "download_url": result.get("url", result.get("download_url", "")),
    }


async def _forward_supplier_comment_to_sicon(case: dict, message: str) -> None:
    """Forward a supplier comment as a Sicon tracking note (non-blocking)."""
    try:
        from utils.sicon_sync import on_supplier_responded
        await on_supplier_responded(case["issue_id"], case.get("supplier_name", "Supplier"), message)
    except Exception as e:
        logger.warning(f"Sicon supplier-comment note failed (non-blocking): {e}")


@router.post("/supplier/case/{token}/comments")
async def add_supplier_comment(
    token: str,
    request: Request,
    message: str = Form(""),
    author_name: str = Form(""),
    author_role: str = Form("supplier"),
    file: Optional[UploadFile] = File(None),
):
    """Supplier adds a comment (with optional attachment) — no login required.

    Defence-in-depth: if the caller happens to be authenticated as a gym
    user (e.g. they clicked the "Supplier Card" link in their dashboard
    and posted from there), we override `author_role` to "gym" so the
    message shows up on the correct side of the conversation. Suppliers
    reach this endpoint via their unauthenticated email-link flow, so
    they won't trigger this branch.
    """
    from utils.captcha import verify_captcha
    from utils.auth import try_get_current_user
    await verify_captcha(request.headers.get("x-captcha-token"), action="supplier_comment")
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")

    msg = message.strip()
    if not msg and not file:
        raise HTTPException(400, "Message or attachment required")

    attachments = [await _build_upload_attachment(case["id"], file)] if file else []

    # If the request carries a valid gym-user JWT, force the attribution
    # regardless of what the client submitted. This eliminates an entire
    # class of "my message showed up as supplier" reports.
    gym_user = await try_get_current_user(request)
    if gym_user and not gym_user.get("is_supplier"):
        author_role = "gym"
        author_name = gym_user.get("full_name") or author_name or "Site Staff"
        notify_supplier = True
    else:
        notify_supplier = False  # matches original behaviour for supplier POSTs

    comment = {
        "id": str(uuid.uuid4()),
        "case_id": case["id"],
        "author_name": author_name or case.get("supplier_name", "Supplier"),
        "author_role": author_role,
        "message": msg,
        "attachments": attachments,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.supplier_case_comments.insert_one(comment)

    # Notify the other party. Gym comments notify the supplier; supplier
    # comments notify the gym (preserved from pre-fix behaviour).
    await _send_comment_notification(case, comment, to_supplier=notify_supplier)

    if author_role == "supplier" and msg:
        await _forward_supplier_comment_to_sicon(case, msg)

    return {k: v for k, v in comment.items() if k != "_id"}


@router.post("/supplier/case/{token}/comments/gym")
async def add_gym_comment(
    token: str,
    message: str = Form(""),
    author_name: str = Form(""),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
):
    """Gym staff adds a comment (authenticated) — notifies supplier."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")

    if not message.strip() and not file:
        raise HTTPException(400, "Message or attachment required")

    attachments = []
    if file:
        data = await file.read()
        path = f"supplier_comments/{case['id']}/{uuid.uuid4()}/{file.filename}"
        result = put_object(path, data, file.content_type or "application/octet-stream")
        attachments.append({
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(data),
            "download_url": result.get("url", result.get("download_url", "")),
        })

    comment = {
        "id": str(uuid.uuid4()),
        "case_id": case["id"],
        "author_name": author_name or user.get("full_name", "Site Staff"),
        "author_role": "gym",
        "message": message.strip(),
        "attachments": attachments,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.supplier_case_comments.insert_one(comment)

    # Notify the supplier about the gym's comment
    await _send_comment_notification(case, comment, to_supplier=True)

    return {k: v for k, v in comment.items() if k != "_id"}


async def _update_case_schedule(token: str, case_id: str, issue_id: str,
                               scheduled_date: str, engineer_name: str, notes: str):
    """Update case and issue records for an engineer visit."""
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.supplier_cases.update_one({"token": token}, {
        "$set": {
            "current_status": "engineer_scheduled",
            "scheduled_date": scheduled_date,
            "engineer_name": engineer_name,
            "updated_at": now_iso,
        },
        "$push": {"status_history": {
            "status": "engineer_scheduled",
            "scheduled_date": scheduled_date,
            "engineer_name": engineer_name,
            "notes": notes,
            "updated_at": now_iso,
        }},
    })
    await db.issues.update_one({"id": issue_id}, {"$set": {
        "status": "in_progress",
        "supplier_status": "engineer_scheduled",
        "scheduled_date": scheduled_date,
        "updated_at": now_iso,
    }})


def _build_schedule_comment(case: dict, scheduled_date: str, engineer_name: str, notes: str) -> dict:
    """Build a system comment announcing a scheduled visit."""
    msg = f"Engineer visit scheduled for {scheduled_date}."
    if engineer_name:
        msg += f" Engineer: {engineer_name}."
    if notes:
        msg += f" {notes}"
    return {
        "id": str(uuid.uuid4()),
        "case_id": case["id"],
        "author_name": engineer_name or case.get("supplier_name", "Supplier"),
        "author_role": "supplier",
        "message": msg,
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/supplier/case/{token}/schedule")
async def schedule_visit(token: str, data: Dict[str, Any]):
    """Supplier schedules an engineer visit date."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")

    scheduled_date = data.get("scheduled_date", "")
    engineer_name = data.get("engineer_name", "")
    notes = data.get("notes", "")

    await _update_case_schedule(token, case["id"], case["issue_id"], scheduled_date, engineer_name, notes)

    comment = _build_schedule_comment(case, scheduled_date, engineer_name, notes)
    await db.supplier_case_comments.insert_one(comment)
    await _send_comment_notification(case, comment, to_supplier=False)

    return {"success": True, "scheduled_date": scheduled_date}


@router.post("/supplier/case/{token}/rate")
async def rate_supplier(token: str, data: Dict[str, Any]):
    """Site rates the supplier after case completion."""
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")

    rating = int(data.get("rating", 0))
    feedback = data.get("feedback", "")
    if rating < 1 or rating > 5:
        raise HTTPException(400, "Rating must be 1-5")

    await db.supplier_cases.update_one({"token": token}, {"$set": {
        "rating": rating,
        "rating_feedback": feedback,
        "rated_at": datetime.now(timezone.utc).isoformat(),
    }})

    return {"success": True}
