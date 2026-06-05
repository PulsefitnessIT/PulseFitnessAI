from fastapi import APIRouter, HTTPException, Depends
from utils.security_plus import safe_regex
from datetime import datetime, timezone
import uuid
import logging
import os

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_date(date_str: str):
    """Parse date from ISO or DD/MM/YYYY format."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    # Try DD/MM/YYYY
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _classify_urgency(days_left: int) -> str:
    """Classify urgency based on days remaining."""
    if days_left <= 7:
        return "critical"
    return "warning" if days_left <= 30 else "info"


def _make_alert(equip: dict, coverage_type: str, expiry: datetime, days_left: int) -> dict:
    """Build a single expiry alert dict."""
    alert = {
        "equipment_id": equip["id"],
        "equipment_name": equip.get("name", ""),
        "equipment_type": equip.get("equipment_type", ""),
        "serial_number": equip.get("serial_number", ""),
        "manufacturer": equip.get("manufacturer", ""),
        "coverage_type": coverage_type,
        "expiry_date": expiry.isoformat(),
        "days_remaining": days_left,
        "urgency": _classify_urgency(days_left),
        "organization_id": equip.get("organization_id"),
    }
    if coverage_type == "contract":
        alert["sla_contract_ref"] = equip.get("sla_contract_ref", "")
    return alert


def _check_expiry(equip: dict, field: str, ctype: str, now) -> dict | None:
    """Check a single expiry field and return an alert or None."""
    raw = equip.get(field)
    if not raw:
        return None
    expiry = _parse_date(raw)
    if not expiry:
        return None
    days_left = (expiry - now).days
    if 0 < days_left <= 90:
        return _make_alert(equip, ctype, expiry, days_left)
    return None


async def _build_expiry_alerts(org_filter: dict) -> list:
    """Scan all equipment for upcoming warranty/contract expiries."""
    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(500)
    now = datetime.now(timezone.utc)
    alerts = []
    for equip in equipment_list:
        for field, ctype in (("warranty_expiry", "warranty"), ("sla_expiry", "contract")):
            alert = _check_expiry(equip, field, ctype, now)
            if alert:
                alerts.append(alert)
    alerts.sort(key=lambda a: a["days_remaining"])
    return alerts


def _build_sent_map(sent_notifications: list) -> dict:
    """Index sent notifications by equipment+coverage (keep latest)."""
    sent_map = {}
    for n in sent_notifications:
        key = f"{n['equipment_id']}_{n['coverage_type']}"
        if key not in sent_map:
            sent_map[key] = n
    return sent_map


def _annotate_alerts_with_history(alerts: list, sent_map: dict) -> None:
    """Attach last-notified metadata to each alert (mutates alerts in place)."""
    for alert in alerts:
        key = f"{alert['equipment_id']}_{alert['coverage_type']}"
        notification = sent_map.get(key)
        if not notification:
            continue
        alert["last_notified"] = notification.get("sent_at")
        alert["notification_id"] = notification.get("id")
        alert["notified_admin"] = notification.get("admin_email")
        alert["notified_supplier"] = notification.get("supplier_email")


@router.get("/expiry-alerts")
async def get_expiry_alerts(user: dict = Depends(get_current_user)):
    """Get all upcoming warranty/contract expiry alerts for the organisation."""
    org_filter = get_organization_filter(user)
    alerts = await _build_expiry_alerts(org_filter)

    sent_notifications = await db.expiry_notifications.find(
        {**org_filter}, {"_id": 0}
    ).sort("sent_at", -1).to_list(200)

    _annotate_alerts_with_history(alerts, _build_sent_map(sent_notifications))

    # Iter 216h126 — surface the org's digest preference so the UI can
    # render the current cadence + a switch.
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "expiry_digest_frequency": 1, "expiry_digest_last_sent_at": 1},
    ) or {}

    return {
        "alerts": alerts,
        "critical_count": len([a for a in alerts if a["urgency"] == "critical"]),
        "warning_count": len([a for a in alerts if a["urgency"] == "warning"]),
        "info_count": len([a for a in alerts if a["urgency"] == "info"]),
        "total": len(alerts),
        "digest_frequency": org.get("expiry_digest_frequency", "off"),
        "digest_last_sent_at": org.get("expiry_digest_last_sent_at"),
    }


@router.put("/expiry-alerts/digest-frequency")
async def set_expiry_digest_frequency(
    body: dict, user: dict = Depends(get_current_user),
) -> dict:
    """Set the org's expiry-digest cadence — off / weekly / monthly
    (Jack request #4)."""
    freq = (body or {}).get("frequency", "off")
    if freq not in {"off", "weekly", "monthly"}:
        raise HTTPException(400, "frequency must be off / weekly / monthly")
    if not user.get("organization_id"):
        raise HTTPException(400, "User has no organisation")
    await db.organizations.update_one(
        {"id": user["organization_id"]},
        {"$set": {
            "expiry_digest_frequency": freq,
            "expiry_digest_updated_at": datetime.now(timezone.utc).isoformat(),
            "expiry_digest_updated_by": user.get("id"),
        }},
    )
    return {"ok": True, "frequency": freq}


def _build_email_row(alert: dict) -> str:
    """Build a single HTML table row for an expiry alert."""
    days = alert["days_remaining"]
    urgency_color = "#DC2626" if days <= 7 else "#F59E0B"
    coverage_label = "Warranty" if alert["coverage_type"] == "warranty" else "Contract"
    return (
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold;">{alert["equipment_name"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert["equipment_type"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert.get("serial_number","N/A")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert.get("manufacturer","N/A")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{coverage_label}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert["expiry_date"][:10]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold;color:{urgency_color};">'
        f'{days} day{"s" if days != 1 else ""}</td>'
        f'</tr>'
    )


def _build_supplier_row(alert: dict) -> str:
    """Build a single HTML table row for a supplier expiry email."""
    days = alert["days_remaining"]
    urgency_color = "#DC2626" if days <= 7 else "#F59E0B"
    coverage_label = "Warranty" if alert["coverage_type"] == "warranty" else "Contract"
    return (
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold;">{alert["equipment_name"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert["equipment_type"]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert.get("serial_number","N/A")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{coverage_label}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{alert["expiry_date"][:10]}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:bold;color:{urgency_color};">'
        f'{days} day{"s" if days != 1 else ""}</td>'
        f'</tr>'
    )


async def _filter_unsent_alerts(urgent_alerts: list, today: str) -> list:
    """Return only alerts that haven't been notified today."""
    unsent = []
    for alert in urgent_alerts:
        already_sent = await db.expiry_notifications.find_one({
            "equipment_id": alert["equipment_id"],
            "coverage_type": alert["coverage_type"],
            "sent_date": today,
        })
        if not already_sent:
            unsent.append(alert)
    return unsent


async def _build_supplier_groups(unsent_alerts: list, org_filter: dict) -> dict:
    """Group alerts by supplier email for consolidated supplier emails."""
    groups: dict = {}
    for alert in unsent_alerts:
        manufacturer = alert.get("manufacturer", "")
        if not manufacturer:
            continue
        supplier_doc = await db.suppliers.find_one(
            {"name": safe_regex(manufacturer), **org_filter}, {"_id": 0},
        )
        if supplier_doc and supplier_doc.get("email"):
            key = supplier_doc["email"]
            if key not in groups:
                groups[key] = {"name": supplier_doc.get("name", manufacturer), "email": key, "alerts": []}
            groups[key]["alerts"].append(alert)
    return groups


async def _record_sent_notifications(
    unsent_alerts: list, supplier_groups: dict, admin_recipient: str, user: dict, today: str,
) -> None:
    """Record a notification document per alert."""
    supplier_alert_map: dict[str, str] = {}
    for group in supplier_groups.values():
        for ga in group["alerts"]:
            key = f"{ga['equipment_id']}_{ga['coverage_type']}"
            supplier_alert_map[key] = group["email"]

    for alert in unsent_alerts:
        key = f"{alert['equipment_id']}_{alert['coverage_type']}"
        notification_doc = {
            "id": str(uuid.uuid4()),
            "equipment_id": alert["equipment_id"],
            "equipment_name": alert["equipment_name"],
            "coverage_type": alert["coverage_type"],
            "days_remaining": alert["days_remaining"],
            "expiry_date": alert["expiry_date"],
            "admin_email": admin_recipient,
            "supplier_email": supplier_alert_map.get(key, "none found"),
            "supplier_notified": key in supplier_alert_map,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "sent_date": today,
            "organization_id": user.get("organization_id"),
            "bundled": True,
        }
        await db.expiry_notifications.insert_one(notification_doc)


_TABLE_HEADER_STYLE = (
    'style="padding:8px 12px;text-align:left;font-size:12px;color:#666;border-bottom:2px solid #ddd;"'
)


async def _load_reminder_context(user: dict) -> dict:
    """Load org, branding, and email config for sending reminders."""
    org = (
        await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
        if user.get("organization_id") else None
    )
    org_name = org.get("name", "GymAxis AI") if org else "GymAxis AI"
    branding = (org or {}).get("branding", {}) or {}
    test_mode = "resend.dev" in (os.environ.get("SENDER_EMAIL", "") or "")
    return {
        "org_name": org_name,
        "brand_color": branding.get("primary_color", "#0055FF"),
        "company_name": branding.get("company_name") or org_name,
        "admin_email": user["email"],
        "admin_name": user.get("full_name", "Admin"),
        "test_mode": test_mode,
        "test_recipient": os.environ.get("TEST_RECIPIENT_EMAIL", ""),
    }


async def _send_admin_reminder(unsent_alerts: list, ctx: dict) -> str:
    """Send the admin summary email and return the recipient address."""
    equipment_rows = "".join(_build_email_row(a) for a in unsent_alerts)
    critical_count = len([a for a in unsent_alerts if a["days_remaining"] <= 7])
    admin_html = _render_admin_email(equipment_rows, critical_count, len(unsent_alerts), ctx["brand_color"], ctx["company_name"], ctx["test_mode"])
    admin_recipient = (ctx["test_recipient"] or ctx["admin_email"]) if ctx["test_mode"] else ctx["admin_email"]
    n = len(unsent_alerts)
    await send_email(admin_recipient, f"Expiry Alert — {n} machine{'s' if n != 1 else ''} expiring within 30 days", admin_html)
    return admin_recipient


async def _send_supplier_reminders(unsent_alerts: list, org_filter: dict, ctx: dict) -> dict:
    """Send per-supplier reminder emails. Returns supplier_groups dict."""
    supplier_groups = await _build_supplier_groups(unsent_alerts, org_filter)
    email_ctx = {k: ctx[k] for k in ("brand_color", "company_name", "admin_name", "admin_email", "test_mode")}
    for group in supplier_groups.values():
        supplier_rows = "".join(_build_supplier_row(a) for a in group["alerts"])
        html = _render_supplier_email(supplier_rows, group["name"], group["email"], len(group["alerts"]), email_ctx)
        recipient = (ctx["test_recipient"] or ctx["admin_email"]) if ctx["test_mode"] else group["email"]
        n = len(group["alerts"])
        await send_email(recipient, f"Coverage Expiry Reminder — {n} machine{'s' if n != 1 else ''} at {ctx['company_name']}", html)
    return supplier_groups


@router.post("/expiry-alerts/send-reminders")
async def send_expiry_reminders(user: dict = Depends(get_current_user)) -> dict:
    """Send consolidated expiry reminder emails."""
    org_filter = get_organization_filter(user)
    alerts = await _build_expiry_alerts(org_filter)
    urgent_alerts = [a for a in alerts if a["days_remaining"] <= 30]
    if not urgent_alerts:
        return {"sent": 0, "message": "No equipment expiring within 30 days"}

    ctx = await _load_reminder_context(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    unsent_alerts = await _filter_unsent_alerts(urgent_alerts, today)
    if not unsent_alerts:
        return {"sent": 0, "message": "All reminders already sent today"}

    admin_recipient = await _send_admin_reminder(unsent_alerts, ctx)
    supplier_groups = await _send_supplier_reminders(unsent_alerts, org_filter, ctx)
    await _record_sent_notifications(unsent_alerts, supplier_groups, admin_recipient, user, today)

    emails_sent = 1 + len(supplier_groups)
    n = len(unsent_alerts)
    return {
        "sent": n, "emails_sent": emails_sent, "alerts_checked": len(urgent_alerts),
        "message": f"Sent {emails_sent} email{'s' if emails_sent != 1 else ''} covering {n} machine{'s' if n != 1 else ''} ({1} admin + {len(supplier_groups)} supplier{'s' if len(supplier_groups) != 1 else ''})",
    }


def _render_admin_email(
    equipment_rows: str, critical_count: int, total: int,
    brand_color: str, company_name: str, test_mode: bool,
) -> str:
    """Build the full admin HTML email body."""
    test_banner = (
        '<div style="background:#FFF3CD;border:1px solid #FFC107;padding:12px;margin-bottom:16px;'
        'border-radius:6px;font-size:13px;"><strong>Test Mode:</strong> In production, suppliers '
        'would also receive their own bundled reminder.</div>'
    ) if test_mode else ""

    critical_block = (
        f'<div style="background:#DC262615;border:2px solid #DC2626;border-radius:8px;'
        f'padding:12px 16px;flex:1;text-align:center;">'
        f'<p style="color:#DC2626;font-size:24px;font-weight:bold;margin:0;">{critical_count}</p>'
        f'<p style="color:#DC2626;font-size:12px;margin:4px 0 0;">Critical (7 days)</p></div>'
    ) if critical_count else ""

    return (
        f'<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden;">'
        f'<div style="background:{brand_color};padding:24px;"><h2 style="color:white;margin:0;">{company_name}</h2>'
        f'<p style="color:rgba(255,255,255,0.8);margin:4px 0 0;">Warranty & Contract Expiry Summary</p></div>'
        f'<div style="padding:24px;">{test_banner}'
        f'<div style="display:flex;gap:12px;margin-bottom:20px;">{critical_block}'
        f'<div style="background:#F59E0B15;border:2px solid #F59E0B;border-radius:8px;padding:12px 16px;flex:1;text-align:center;">'
        f'<p style="color:#F59E0B;font-size:24px;font-weight:bold;margin:0;">{total}</p>'
        f'<p style="color:#F59E0B;font-size:12px;margin:4px 0 0;">Expiring within 30 days</p></div></div>'
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px;"><thead><tr style="background:#f5f5f5;">'
        f'<th {_TABLE_HEADER_STYLE}>Equipment</th><th {_TABLE_HEADER_STYLE}>Type</th>'
        f'<th {_TABLE_HEADER_STYLE}>Serial</th><th {_TABLE_HEADER_STYLE}>Manufacturer</th>'
        f'<th {_TABLE_HEADER_STYLE}>Coverage</th><th {_TABLE_HEADER_STYLE}>Expiry</th>'
        f'<th {_TABLE_HEADER_STYLE}>Remaining</th></tr></thead><tbody>{equipment_rows}</tbody></table>'
        f'<p style="color:#333;"><strong>Recommended actions:</strong></p>'
        f'<ul style="color:#555;"><li>Contact the relevant manufacturers/suppliers to discuss renewal options</li>'
        f'<li>Review equipment condition and repair history before renewing</li>'
        f'<li>Consider extended warranties or service contracts for high-value equipment</li></ul></div>'
        f'<div style="background:#f5f5f5;padding:16px;text-align:center;font-size:12px;color:#999;">'
        f'Powered by {company_name} via GymAxis AI</div></div>'
    )


def _render_supplier_email(
    supplier_rows: str, supplier_name: str, supplier_email_address: str,
    alert_count: int, ctx: dict,
) -> str:
    """Build the full supplier HTML email body.
    ctx keys: brand_color, company_name, admin_name, admin_email, test_mode
    """
    brand_color = ctx["brand_color"]
    company_name = ctx["company_name"]
    admin_name = ctx["admin_name"]
    admin_email = ctx["admin_email"]
    test_mode = ctx["test_mode"]
    test_banner = (
        f'<div style="background:#FFF3CD;border:1px solid #FFC107;padding:12px;margin-bottom:16px;'
        f'border-radius:6px;font-size:13px;"><strong>Test Mode:</strong> This would be sent to '
        f'<strong>{supplier_email_address}</strong> ({supplier_name}) in production.</div>'
    ) if test_mode else ""

    plural = "s" if alert_count != 1 else ""
    is_are = "are" if alert_count != 1 else "is"
    its_their = "their" if alert_count != 1 else "its"
    this_these = "these machines" if alert_count != 1 else "this equipment"

    return (
        f'<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden;">'
        f'<div style="background:{brand_color};padding:24px;"><h2 style="color:white;margin:0;">{company_name}</h2>'
        f'<p style="color:rgba(255,255,255,0.8);margin:4px 0 0;">Coverage Expiry Reminder</p></div>'
        f'<div style="padding:24px;">{test_banner}'
        f'<p>Dear {supplier_name} Service Team,</p>'
        f'<p>This is an automated reminder that the warranty/contract for the following '
        f'<strong>{alert_count} machine{plural}</strong> at <strong>{company_name}</strong> '
        f'{is_are} approaching {its_their} expiry date:</p>'
        f'<table style="width:100%;border-collapse:collapse;margin:16px 0;"><thead><tr style="background:#f5f5f5;">'
        f'<th {_TABLE_HEADER_STYLE}>Equipment</th><th {_TABLE_HEADER_STYLE}>Type</th>'
        f'<th {_TABLE_HEADER_STYLE}>Serial</th><th {_TABLE_HEADER_STYLE}>Coverage</th>'
        f'<th {_TABLE_HEADER_STYLE}>Expiry</th><th {_TABLE_HEADER_STYLE}>Remaining</th>'
        f'</tr></thead><tbody>{supplier_rows}</tbody></table>'
        f'<p>We would appreciate it if you could contact us regarding renewal options or new coverage for {this_these}.</p>'
        f'<p>Please direct any queries to <strong>{admin_name}</strong> at <a href="mailto:{admin_email}">{admin_email}</a>.</p>'
        f'<p>Kind regards,<br/>{admin_name}<br/>{company_name}</p></div>'
        f'<div style="background:#f5f5f5;padding:16px;text-align:center;font-size:12px;color:#999;">'
        f'Powered by {company_name} via GymAxis AI</div></div>'
    )


@router.post("/expiry-alerts/{alert_equipment_id}/send-reminder")
async def send_single_reminder(alert_equipment_id: str, data: dict = None, user: dict = Depends(get_current_user)):
    """Manually send a reminder for a specific equipment's expiry."""
    if data is None:
        data = {}
    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one({"id": alert_equipment_id, **org_filter}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    coverage_type = data.get("coverage_type", "warranty")

    # Build a single-item alert and re-use the bulk sender logic
    alerts = await _build_expiry_alerts(org_filter)
    target = [a for a in alerts if a["equipment_id"] == alert_equipment_id and a["coverage_type"] == coverage_type]
    if not target:
        raise HTTPException(status_code=400, detail="No upcoming expiry found for this equipment")

    # Clear today's sent record so the reminder goes through
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.expiry_notifications.delete_many({
        "equipment_id": alert_equipment_id,
        "coverage_type": coverage_type,
        "sent_date": today,
    })

    # Temporarily override the org filter to just this equipment
    result = await send_expiry_reminders(user)
    return result
