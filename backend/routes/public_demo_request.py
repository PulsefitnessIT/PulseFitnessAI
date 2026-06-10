"""Public Demo Request — Iter 220ak / Phase A.3.

Captures inbound demo requests from the GymAxis public marketing site
(``/demo-request`` landing page) directly into the master-admin CRM
pipeline. This is the lower edge of the inbound funnel that the SEO
Autopilot (Iter 220ad-aj) feeds into.

Flow on submit:

  1. **Honeypot**: silently drop if the hidden ``website`` field has
     any value (bot signal).
  2. **Rate limit**: 5 requests per IP per hour. Bots that bypass the
     honeypot still hit this ceiling.
  3. Insert a ``crm_contacts`` row (so the rep sees the human) and a
     ``crm_deals`` row in stage ``lead`` (so the rep sees the deal),
     both scoped to the master-admin org. The contact and deal cross-
     reference each other via ``contact_id`` / ``company_name``.
  4. Insert a ``crm_activities`` row tagging the source so the rep can
     trace where it came from.
  5. Insert a ``growth_alerts`` row — the Growth Hub renders these in
     a small "New inbound" feed at the top.
  6. Auto-enrol the contact into the ``cold-to-demo`` B2B journey
     (Iter 220ah).
  7. Best-effort email notification to the sales inbox.
  8. Return a stable receipt id the SPA can hand the visitor.

Endpoint surface (single):

    POST /api/public/demo-request

This module is intentionally public (no auth). Every Mongo write is
scoped to the master-admin org — visitors can never touch tenant data.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.database import db
from utils.security import rate_limit, _client_ip
from utils.email import send_email
from routes.master_admin_growth_hub import _master_admin_org_id


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public-demo-request"])


# Defaults — overridable so the same endpoint can be tested with looser
# limits in CI without loosening prod.
_DEMO_RATE_MAX = int(os.environ.get("DEMO_REQUEST_RATE_MAX", "5"))
_DEMO_RATE_WINDOW_S = int(os.environ.get("DEMO_REQUEST_RATE_WINDOW_S", "3600"))
_DEMO_NOTIFY_INBOX = (
    os.environ.get("DEMO_REQUEST_NOTIFY_EMAIL", "sales@gymaxisai.com")
    .strip()
)


_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z\-'.\s]{1,79}$")


class DemoRequestPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    company: str = Field(..., min_length=2, max_length=120)
    site_count: int = Field(..., ge=1, le=999)
    message: str = Field("", max_length=2000)
    # Honeypot — must be empty. Visible to bots that auto-fill every
    # field; invisible to humans (the form hides it via CSS).
    website: Optional[str] = Field(None, max_length=200)
    # UTM passthrough — useful for attribution but never required.
    utm_source: Optional[str] = Field(None, max_length=64)
    utm_medium: Optional[str] = Field(None, max_length=64)
    utm_campaign: Optional[str] = Field(None, max_length=64)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> tuple[str, str]:
    """Split a single ``name`` field into first/last on the first
    space. Falls back to (value, '') for single-word entries."""
    parts = (value or "").strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


async def _enrol_into_cold_journey(*, contact_id: str, deal_id: str,
                                    org_id: str, contact_email: str) -> None:
    """Best-effort enrolment into the ``cold-to-demo`` B2B journey. We
    don't want a journey error to roll back the lead capture, so any
    failure is logged but swallowed."""
    try:
        journey = await db.marketing_journeys.find_one(
            {"organization_id": org_id, "template_id": "cold-to-demo",
             "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1},
        )
        if not journey:
            logger.info("[demo-request] cold-to-demo journey not yet launched; skipping enrolment")
            return
        await db.marketing_journey_enrolments.insert_one({
            "id": str(uuid.uuid4()),
            "journey_id": journey["id"],
            "organization_id": org_id,
            "contact_id": contact_id,
            "contact_email": contact_email,
            "deal_id": deal_id,
            "source": "demo-request-form",
            "status": "active",
            "current_step_index": 0,
            "created_at": _now_iso(),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[demo-request] enrolment failed: %s", exc)


async def _notify_sales_inbox(*, name: str, email: str, company: str,
                              site_count: int, message: str,
                              deal_id: str) -> None:
    if not _DEMO_NOTIFY_INBOX:
        return
    subject = f"New demo request: {company} ({site_count} sites)"
    html = (
        f"<p><strong>{name}</strong> from <strong>{company}</strong> "
        f"({site_count} site{'s' if site_count != 1 else ''}) requested a demo.</p>"
        f"<p><strong>Email:</strong> <a href=\"mailto:{email}\">{email}</a></p>"
        f"<p><strong>Message:</strong><br>{(message or '—').replace(chr(10), '<br>')}</p>"
        f"<hr><p>Deal id: <code>{deal_id}</code> · "
        f"<a href=\"https://gymaxisai.com/master-admin\">Open in Master Admin</a></p>"
    )
    try:
        await send_email(to=_DEMO_NOTIFY_INBOX, subject=subject, html=html)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[demo-request] sales notification email failed: %s", exc)


@router.post("/demo-request")
async def submit_demo_request(payload: DemoRequestPayload, request: Request):
    """Accept a demo request from the public marketing site, drop it
    into the master-admin CRM pipeline, fire the cold-to-demo journey
    and notify the sales inbox. Returns a stable receipt id."""

    # Honeypot — bots that auto-fill every field will populate
    # ``website``. We return 200 with a fake receipt so they don't
    # detect the failure and adapt.
    if payload.website and payload.website.strip():
        logger.info("[demo-request] honeypot tripped from %s", request.client.host if request.client else "unknown")
        return {"ok": True, "receipt_id": str(uuid.uuid4()), "queued": True}

    # Rate-limit by client IP. ``rate_limit`` raises 429. Use a
    # dedicated key so this counter is isolated from the global
    # per-IP buckets used elsewhere on the platform.
    rate_limit(
        f"demo-request:{_client_ip(request)}",
        max_requests=_DEMO_RATE_MAX, window_seconds=_DEMO_RATE_WINDOW_S,
    )

    # Sanity check on the name — Pydantic's min/max guards length but
    # we want to reject all-numeric or symbol-only entries that
    # otherwise pass.
    if not _NAME_RE.match(payload.name.strip()):
        raise HTTPException(status_code=422, detail="Please enter your full name.")

    org_id = await _master_admin_org_id()
    first, last = _safe_name(payload.name)
    contact_id = str(uuid.uuid4())
    deal_id = str(uuid.uuid4())
    now = _now_iso()

    # Default pipeline lookup — keep the deal in whatever the master-
    # admin org calls "default", so the rep sees it on the canonical
    # pipeline view.
    pipeline = await db.crm_pipelines.find_one(
        {"organization_id": org_id, "is_default": True},
        {"_id": 0, "id": 1},
    )
    pipeline_id = pipeline["id"] if pipeline else None

    # 1. Contact
    contact = {
        "id": contact_id,
        "organization_id": org_id,
        "first_name": first, "last_name": last,
        "email": str(payload.email),
        "phone": "",
        "company_id": None,
        "company_name": payload.company,
        "title": "",
        "tags": ["inbound-demo-request"],
        "source": "demo-request-form",
        "lead_score": 50,  # inbound = warm-ish by default
        "owner_id": None,  # rep picks up
        "notes": payload.message or "",
        "linkedin_url": "",
        "address": "",
        "created_by": "system:demo-request",
        "created_at": now,
        "updated_at": now,
        "utm": {
            "source": payload.utm_source or None,
            "medium": payload.utm_medium or None,
            "campaign": payload.utm_campaign or None,
        },
    }
    await db.crm_contacts.insert_one(contact)

    # 2. Deal in stage=lead
    deal = {
        "id": deal_id,
        "organization_id": org_id,
        "title": f"Demo · {payload.company} ({payload.site_count} sites)",
        "value": 0.0,
        "stage": "lead",
        "pipeline_id": pipeline_id,
        "contact_id": contact_id,
        "contact_name": payload.name,
        "company_id": None,
        "company_name": payload.company,
        "owner_id": None,
        "owner_name": "",
        "probability": 10,
        "expected_close": None,
        "notes": payload.message or "",
        "source": "demo-request-form",
        "site_count": payload.site_count,
        "created_by": "system:demo-request",
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
    }
    await db.crm_deals.insert_one(deal)

    # 3. Activity stamp on the contact
    await db.crm_activities.insert_one({
        "id": str(uuid.uuid4()),
        "type": "demo_requested",
        "contact_id": contact_id,
        "deal_id": deal_id,
        "company_id": None,
        "description": f"Demo requested via the public site ({payload.site_count} sites).",
        "created_by": "system:demo-request",
        "created_by_name": "Demo Request Form",
        "created_at": now,
    })

    # 4. Growth Hub alert — the Hub renders these in a "New inbound" feed.
    await db.growth_alerts.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "type": "demo_request",
        "title": f"New demo request · {payload.company}",
        "summary": (
            f"{payload.name} ({payload.site_count} site"
            f"{'s' if payload.site_count != 1 else ''})"
        ),
        "deal_id": deal_id,
        "contact_id": contact_id,
        "read": False,
        "created_at": now,
    })

    # 5. Enrol into the cold-to-demo journey (best-effort).
    await _enrol_into_cold_journey(
        contact_id=contact_id, deal_id=deal_id, org_id=org_id,
        contact_email=str(payload.email),
    )

    # 6. Notify sales inbox (best-effort).
    await _notify_sales_inbox(
        name=payload.name, email=str(payload.email), company=payload.company,
        site_count=payload.site_count, message=payload.message,
        deal_id=deal_id,
    )

    return {
        "ok": True,
        "receipt_id": deal_id,
        "queued": False,
    }


__all__ = ["router"]
