"""Master Admin → Automatic dunning (overdue invoice reminders).

When an issued invoice goes 7 / 14 / 28 days past its `due_at`, a
reminder email is fired to the same billing contact used by the
"Send invoice to client" flow. Each reminder is recorded on the
invoice as ``reminders: [{stage, days_overdue, sent_at, share_id,
recipient, delivered}]`` so we never double-fire the same stage and
the admin UI can show a "Reminded ×N" pill.

Two entry points are exposed:

* ``POST /api/master-admin/billing/dunning/run`` — batch sweep for
  all overdue invoices (intended to be wired to a daily cron later).
* ``POST /api/master-admin/orgs/{org_id}/billing/invoice/{id}/remind``
  — one-off manual reminder for a single invoice.

Both reuse the share-link plumbing from :mod:`invoice_share` so the
recipient still gets a public download URL alongside the PDF
attachment.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email


router = APIRouter()
logger = logging.getLogger(__name__)

# Stages we remind at (days past due_at). Each invoice can fire each
# stage once.
DUNNING_STAGES = (7, 14, 28)

# Share link TTL for dunning emails — 30 days is plenty for the
# customer to act on a reminder.
DUNNING_TTL_DAYS = 30


def _require_master(user: dict) -> None:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _ccy_symbol(ccy: str) -> str:
    return {"GBP": "£", "EUR": "€", "USD": "$"}.get((ccy or "").upper(), "")


def _format_money(minor: int, ccy: str) -> str:
    return f"{_ccy_symbol(ccy)}{(minor or 0) / 100:,.2f}"


def _public_base() -> str:
    import os as _os
    return (
        _os.environ.get("FRONTEND_URL")
        or _os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")


def _next_stage_for(invoice: dict, days_overdue: int) -> int | None:
    """Return the highest unfired stage we can fire right now, or None.

    A stage fires once `days_overdue >= stage` AND we haven't already
    fired that stage for this invoice.
    """
    fired = {r.get("stage") for r in (invoice.get("reminders") or [])}
    eligible = [s for s in DUNNING_STAGES if days_overdue >= s and s not in fired]
    return max(eligible) if eligible else None


def _render_dunning_email_html(
    org_name: str,
    invoice: dict,
    download_url: str,
    stage: int,
    days_overdue: int,
    expires_at: datetime,
) -> str:
    """Stage-aware email body. Tone escalates 7 → 14 → 28."""
    ccy = invoice.get("currency", "GBP")
    total = _format_money(invoice.get("total", 0), ccy)
    expires_str = expires_at.strftime("%-d %b %Y")
    due_at = (invoice.get("due_at") or "")[:10]

    if stage <= 7:
        headline = "Friendly reminder"
        intro = (
            f"This is a quick reminder that invoice "
            f"<strong>{invoice.get('number','')}</strong> is now "
            f"<strong>{days_overdue} days</strong> past due."
        )
        cta = "Settle invoice"
        footer = "If you've already paid, please ignore this — payments can take a couple of days to land with us."
        accent = "#19CDFF"
    elif stage <= 14:
        headline = "Second reminder — payment overdue"
        intro = (
            f"Invoice <strong>{invoice.get('number','')}</strong> is "
            f"<strong>{days_overdue} days</strong> past due. Please arrange "
            f"payment or get in touch if there's an issue we should know about."
        )
        cta = "Pay this invoice"
        footer = "Continued non-payment may impact service availability."
        accent = "#F59E0B"
    else:
        headline = "Final reminder — action required"
        intro = (
            f"Invoice <strong>{invoice.get('number','')}</strong> is "
            f"<strong>{days_overdue} days</strong> past due. This is a final "
            f"reminder before the account is paused."
        )
        cta = "Settle now"
        footer = "If payment isn't received in the next 7 days the account may be suspended pending review."
        accent = "#DC2626"

    return f"""<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;background:#fff;">
  <div style="background:#0A0C10;padding:28px 30px;text-align:center;">
    <div style="color:{accent};font-size:11px;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px;">{headline}</div>
    <h1 style="color:#fff;margin:0;font-size:22px;letter-spacing:-0.3px;">{org_name or 'GymAxis AI'} — invoice {invoice.get('number','')}</h1>
  </div>
  <div style="padding:32px 30px;color:#1a1a1a;">
    <p style="line-height:1.6;margin:0 0 14px;">Hi,</p>
    <p style="line-height:1.6;margin:0 0 16px;">{intro}</p>
    <table style="width:100%;border-collapse:collapse;margin:14px 0;font-size:14px;">
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Total due</td>
        <td style="padding:8px 0;text-align:right;font-weight:700;">{total}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Invoice date due</td>
        <td style="padding:8px 0;text-align:right;">{due_at}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Days overdue</td>
        <td style="padding:8px 0;text-align:right;color:{accent};font-weight:700;">{days_overdue} days</td>
      </tr>
    </table>
    <div style="text-align:center;margin:28px 0;">
      <a href="{download_url}" style="display:inline-block;background:{accent};color:#0A0C10;padding:14px 32px;
         text-decoration:none;border-radius:8px;font-weight:700;font-size:14px;letter-spacing:0.3px;">
         {cta} →
      </a>
    </div>
    <p style="color:#6b7280;font-size:12px;line-height:1.6;text-align:center;">
      The PDF is also attached. Secure download link expires {expires_str}.
    </p>
    <p style="color:#9ca3af;font-size:12px;line-height:1.6;margin-top:24px;text-align:center;">{footer}</p>
  </div>
  <div style="background:#f5f5f5;padding:16px 30px;text-align:center;">
    <p style="color:#9ca3af;font-size:11px;margin:0;">Sent from {org_name or 'GymAxis AI'} billing</p>
  </div>
</div>"""


async def _fire_reminder(
    invoice: dict,
    org: dict,
    stage: int,
    days_overdue: int,
    actor_id: str | None,
) -> dict:
    """Render PDF, persist a share link, send the reminder email,
    append a `reminders[]` row to the invoice. Returns a small summary."""
    recipient = (
        org.get("primary_contact_email")
        or (org.get("primary_contact") or {}).get("email")
        or ""
    ).strip()
    if "@" not in recipient:
        return {
            "ok": False,
            "skipped": True,
            "reason": "no_recipient",
            "invoice_id": invoice.get("id"),
            "stage": stage,
        }

    from routes.master_admin_billing import _render_invoice_pdf
    pdf_bytes = _render_invoice_pdf(invoice, org)

    expires_at = _now() + timedelta(days=DUNNING_TTL_DAYS)
    token = uuid.uuid4().hex
    share = {
        "id": str(uuid.uuid4()),
        "token": token,
        "organization_id": org.get("id"),
        "invoice_id": invoice.get("id"),
        "recipient_email": recipient,
        "subject": f"Reminder · invoice {invoice.get('number','')} ({days_overdue} days overdue)",
        "message": "",
        "expires_at": expires_at.isoformat(),
        "used_count": 0,
        "last_used_at": None,
        "created_by": actor_id,
        "created_at": _now().isoformat(),
        "revoked": False,
        "kind": "dunning",
        "stage": stage,
    }
    await db.invoice_share_links.insert_one(dict(share))

    base = _public_base()
    download_url = f"{base}/api/public/invoice-share/{token}" if base else f"/api/public/invoice-share/{token}"

    html = _render_dunning_email_html(
        org_name=org.get("name", ""),
        invoice=invoice,
        download_url=download_url,
        stage=stage,
        days_overdue=days_overdue,
        expires_at=expires_at,
    )
    attachments = [{
        "filename": f"{invoice.get('number','invoice')}.pdf",
        "content": base64.b64encode(pdf_bytes).decode(),
    }]
    sent_ok = await send_email(
        recipient,
        share["subject"],
        html,
        attachments=attachments,
        category="billing",
    )

    reminder = {
        "stage": stage,
        "days_overdue": days_overdue,
        "sent_at": _now().isoformat(),
        "share_id": share["id"],
        "recipient": recipient,
        "delivered": bool(sent_ok),
        "sent_by": actor_id,
    }
    await db.org_billing_invoices.update_one(
        {"id": invoice.get("id"), "organization_id": org.get("id")},
        {"$push": {"reminders": reminder}},
    )
    return {
        "ok": True,
        "skipped": False,
        "invoice_id": invoice.get("id"),
        "invoice_number": invoice.get("number"),
        "organization_id": org.get("id"),
        "stage": stage,
        "days_overdue": days_overdue,
        "recipient": recipient,
        "share_url": download_url,
        "delivered": bool(sent_ok),
    }


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/master-admin/billing/dunning/run")
async def run_dunning(
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Sweep every issued, unpaid, non-void invoice and fire the next
    eligible dunning stage (7/14/28 days past due_at).

    Optional payload:
        ``dry_run`` — if true, return what *would* fire without
        sending anything. Useful for the admin UI preview.
    """
    _require_master(user)
    dry_run = bool(payload.get("dry_run"))
    now = _now()

    cursor = db.org_billing_invoices.find(
        {"status": "issued"},
        {"_id": 0},
    ).sort("due_at", 1)
    invoices = await cursor.to_list(length=2000)

    fired: list[dict] = []
    skipped: list[dict] = []
    would_fire: list[dict] = []

    org_cache: dict[str, dict] = {}

    for inv in invoices:
        due = _parse_iso(inv.get("due_at"))
        if not due or due >= now:
            continue
        days_overdue = (now - due).days
        stage = _next_stage_for(inv, days_overdue)
        if stage is None:
            continue

        org_id = inv.get("organization_id")
        if not org_id:
            skipped.append({"invoice_id": inv.get("id"), "reason": "no_org"})
            continue
        org = org_cache.get(org_id)
        if org is None:
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
            org_cache[org_id] = org

        if dry_run:
            would_fire.append({
                "invoice_id": inv.get("id"),
                "invoice_number": inv.get("number"),
                "organization_id": org_id,
                "organization_name": org.get("name"),
                "stage": stage,
                "days_overdue": days_overdue,
                "total": inv.get("total"),
                "currency": inv.get("currency"),
            })
            continue

        result = await _fire_reminder(inv, org, stage, days_overdue, user.get("id"))
        if result.get("ok"):
            fired.append(result)
        else:
            skipped.append({
                "invoice_id": result.get("invoice_id"),
                "reason": result.get("reason"),
                "stage": stage,
            })

    return {
        "as_of": now.isoformat(),
        "scanned": len(invoices),
        "dry_run": dry_run,
        "fired": fired if not dry_run else [],
        "would_fire": would_fire if dry_run else [],
        "skipped": skipped,
        "summary": {
            "candidates": len(would_fire) if dry_run else len(fired) + len(skipped),
            "sent": 0 if dry_run else len(fired),
            "skipped": len(skipped),
        },
    }


@router.post("/master-admin/orgs/{org_id}/billing/invoice/{invoice_id}/remind")
async def remind_one_invoice(
    org_id: str,
    invoice_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Manually fire a dunning reminder for a single invoice. Skips if
    the invoice is paid/void or not yet overdue (unless ``force=true``).
    """
    _require_master(user)
    inv = await db.org_billing_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0}
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.get("status") in ("paid", "void"):
        raise HTTPException(400, f"Invoice is {inv.get('status')} — nothing to chase")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organization not found")

    now = _now()
    due = _parse_iso(inv.get("due_at"))
    days_overdue = (now - due).days if due else 0
    force = bool(payload.get("force"))

    if days_overdue < DUNNING_STAGES[0] and not force:
        raise HTTPException(
            400,
            f"Invoice is not overdue yet ({days_overdue} days past due). Pass force=true to override.",
        )

    # Pick the explicit stage if provided & valid; else next eligible;
    # else (forced override pre-due) use stage 7 as the friendliest copy.
    requested_stage = payload.get("stage")
    if requested_stage in DUNNING_STAGES:
        stage = int(requested_stage)
    else:
        stage = _next_stage_for(inv, days_overdue) or DUNNING_STAGES[0]

    result = await _fire_reminder(inv, org, stage, max(days_overdue, 0), user.get("id"))
    if not result.get("ok"):
        raise HTTPException(400, f"Reminder skipped: {result.get('reason')}")
    return result


@router.get("/master-admin/billing/dunning/preview")
async def preview_dunning(user: dict = Depends(get_current_user)) -> dict:
    """Lightweight `?dry_run=true` wrapper so the admin UI can show a
    "X invoices would be reminded" banner without writing anything."""
    _require_master(user)
    return await run_dunning(payload={"dry_run": True}, user=user)
