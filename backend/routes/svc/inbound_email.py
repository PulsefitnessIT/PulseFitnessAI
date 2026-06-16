"""
Pulse Fitness Service Operations — Inbound email webhook.

Iter 216h146 (Phase 5 follow-on).

Accepts inbound emails forwarded by SendGrid Inbound Parse (multipart
form) or a generic JSON-format provider (CloudMailin / Mailgun / a
local QA simulator), routes them to the engineer whose intake slug
matches the recipient local-part, and drops the request into the
existing `svc_job_requests` collection where the engineer triages it
from `/svc/engineer/inbox` — exactly the same flow as the public
supplier-card form.

Setup (operator):
  1. Pick a subdomain you control, e.g. `in.gymaxis.com`.
  2. Point MX records at SendGrid: `mx.sendgrid.net` priority 10.
  3. In SendGrid → Settings → Inbound Parse, add the hostname pointing
     to:  https://<your-host>/api/inbound/email?secret=<INBOUND_EMAIL_WEBHOOK_SECRET>
  4. Set `INBOUND_EMAIL_WEBHOOK_SECRET` and (optionally)
     `INBOUND_EMAIL_DOMAIN` in backend .env.
  5. Each engineer's inbox address becomes `<intake_slug>@in.gymaxis.com`.

Routes (PUBLIC, secret-gated):
  POST /api/inbound/email           — webhook (multipart OR JSON)
  POST /api/inbound/email/test      — local simulator (returns the parsed payload)

Internal:
  GET  /api/svc/engineer/inbound-address  — engineer's email address (for the UI)
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)

# Iter 216h157 — high-confidence parses skip the triage inbox and
# create the case directly. Tunable via env so ops can dial it back
# during early rollout. Range checked at boot.
try:
    AUTOACCEPT_THRESHOLD = float(os.environ.get("INBOUND_EMAIL_AUTOACCEPT_THRESHOLD") or "0.9")
except (TypeError, ValueError):
    AUTOACCEPT_THRESHOLD = 0.9
AUTOACCEPT_THRESHOLD = min(max(AUTOACCEPT_THRESHOLD, 0.0), 1.0)


# ── public webhook router (no auth — secret-gated) ───────────────
public_router = APIRouter(
    prefix="/inbound",
    tags=["Public · Inbound Email Webhook"],
)
# Address-helper router (engineer-side)
engineer_router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Inbound Address"],
    dependencies=[Depends(require_engineer_app_access)],
)


# ── helpers ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_EMAIL_RE = re.compile(r"<?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})>?", re.I)


def _extract_email(field: Optional[str]) -> Optional[str]:
    """Pull the first email address out of a header like 'John <john@x.com>'."""
    if not field:
        return None
    m = _EMAIL_RE.search(field)
    return m.group(1).lower() if m else None


def _extract_name(field: Optional[str]) -> Optional[str]:
    """Pull display name out of 'John Doe <john@x.com>'."""
    if not field:
        return None
    s = field.strip()
    if "<" in s:
        return s.split("<")[0].strip(' "\'') or None
    return None


def _local_part(addr: str) -> str:
    """Lowercase local-part of an email."""
    return (addr or "").split("@")[0].lower()


def _domain_part(addr: str) -> str:
    return (addr or "").split("@")[-1].lower()


def _verify_secret(secret: Optional[str]) -> None:
    """Reject anything that doesn't carry the configured shared secret."""
    expected = os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET")
    if not expected:
        # Hard-fail to make misconfiguration obvious. The operator must
        # set the secret before the webhook starts accepting traffic.
        raise HTTPException(503, "Inbound email not configured (set INBOUND_EMAIL_WEBHOOK_SECRET)")
    if not secret or secret != expected:
        raise HTTPException(401, "Invalid inbound webhook secret")


def _verify_domain_allowed(to_addr: Optional[str]) -> None:
    """Optional belt-and-braces guard: enforce a known recipient domain."""
    allowed = os.environ.get("INBOUND_EMAIL_DOMAIN")
    if not allowed:
        return
    dom = _domain_part(to_addr or "")
    if dom and dom != allowed.lower():
        raise HTTPException(400, f"Recipient domain '{dom}' not allowed")


async def _resolve_engineer(slug: str) -> dict:
    eng = await db.svc_engineers.find_one(
        {"intake_slug": slug, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1,
         "intake_slug": 1},
    )
    if not eng:
        raise HTTPException(404, "No engineer matches that inbox address")
    return eng


# ── payload normalisation ─────────────────────────────────────────

class NormalisedEmail(BaseModel):
    to: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    subject: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    headers: Optional[str] = None
    spam_score: Optional[float] = None

    class Config:
        populate_by_name = True


async def _normalise_request(request: Request) -> NormalisedEmail:
    """Accept SendGrid Inbound Parse (multipart) OR JSON. The JSON
    format must use the same field names: to/from/subject/text/html."""
    ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ct == "application/json":
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")
        return NormalisedEmail(
            to=body.get("to"),
            **{"from": body.get("from")},
            subject=body.get("subject"),
            text=body.get("text"),
            html=body.get("html"),
            headers=body.get("headers"),
            spam_score=body.get("spam_score"),
        )
    # multipart/form-data (SendGrid Inbound Parse) or url-encoded
    form = await request.form()
    raw_score = form.get("spam_score") or None
    try:
        score_f = float(raw_score) if raw_score not in (None, "") else None
    except (TypeError, ValueError):
        score_f = None
    return NormalisedEmail(
        to=form.get("to"),
        **{"from": form.get("from")},
        subject=form.get("subject"),
        text=form.get("text"),
        html=form.get("html"),
        headers=form.get("headers"),
        spam_score=score_f,
    )


# ── AI extraction (reuse) ─────────────────────────────────────────

async def _ai_extract(text: str, subject: Optional[str]) -> dict:
    """Best-effort GPT-5.2 extraction. Returns empty dict on failure."""
    if not text or not text.strip():
        return {}
    try:
        from routes.svc.independence import PARSE_SYSTEM_PROMPT, _key
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=_key(),
            session_id=f"engineer-inbound-{uuid.uuid4()}",
            system_message=PARSE_SYSTEM_PROMPT,
        ).with_model("openai", "gpt-5.2")
        raw = await chat.send_message(UserMessage(
            text=f"Subject: {subject or '(none)'}\n\n{text.strip()}",
        ))
        cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(),
                          flags=re.MULTILINE).strip()
        return json.loads(cleaned)
    except Exception as e:
        logger.info("inbound AI parse skipped: %s", e)
        return {}


# ── auto-accept · Iter 216h157 ──────────────────────────────────

async def _next_case_reference(organization_id: str) -> str:
    """SVC-YYYY-MM-NNNNN — reuses the convention from cases.py without
    importing the heavyweight `intake.create_case` flow."""
    now = datetime.now(timezone.utc)
    prefix = f"SVC-{now.year}-{now.month:02d}"
    # Count existing cases this month for a stable serial.
    seq = await db.svc_cases.count_documents({
        "organization_id": organization_id,
        "reference": {"$regex": f"^{prefix}-"},
    })
    return f"{prefix}-{seq + 1:05d}"


async def _auto_create_case(
    *, eng: dict, parsed: dict, payload: NormalisedEmail,
    from_addr: str, to_addr: str,
    title: str, description: Optional[str],
    priority: str, confidence: float,
) -> dict:
    """High-confidence parse → skip the triage inbox and create the
    svc_case directly. Mirrors `independence.self_allocate` semantics
    (canonical ASSIGNED state, case_created timeline event, CRM/Sicon/
    audit hooks fired) so downstream behaviour is identical to the
    manual-accept path."""
    from utils.svc_state import ASSIGNED, append_event
    from routes.svc.integrations import sicon_sync

    case_id = str(uuid.uuid4())
    reference = await _next_case_reference(eng["organization_id"])
    actor = {
        "id": eng["id"],
        "email": eng.get("email") or "",
        "full_name": eng.get("full_name") or "",
    }
    case = {
        "id": case_id,
        "organization_id": eng["organization_id"],
        "reference": reference,
        "title": title,
        "description": description,
        "priority": priority,
        "status": ASSIGNED,
        "assigned_engineer_id": eng["id"],
        "assigned_engineer_name": eng.get("full_name"),
        "self_claimed_at": _now(),
        "intake_channel": "inbound_email",
        "intake_subchannel": "auto_accepted",
        "intake_confidence": confidence,
        # Iter 216h158 — slug attribution (every inbound email is
        # routed via the engineer's intake_slug, so it counts as
        # supplier-card traffic for marketing rollups).
        "source_card_slug": eng.get("intake_slug"),
        "source_engineer_id": eng["id"],
        "customer_name": parsed.get("customer_name") or _extract_name(payload.from_) or from_addr,
        "customer_email": parsed.get("customer_email") or from_addr,
        "customer_phone": parsed.get("customer_phone"),
        "site_name": parsed.get("site_name"),
        "site_address": parsed.get("site_address"),
        "site_postcode": parsed.get("site_postcode"),
        "scheduled_at": parsed.get("scheduled_at_hint"),
        "estimated_minutes": 60,
        "source": {
            "type": "email",
            "from": from_addr,
            "to": to_addr,
            "subject": payload.subject,
        },
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_cases.insert_one(case)
    case.pop("_id", None)
    try:
        await append_event(
            case_id=case_id,
            organization_id=eng["organization_id"],
            event_type="case_created",
            actor=actor,
            body=f"Auto-accepted from inbound email (confidence {confidence:.2f})",
            extra={"intake_channel": "inbound_email", "auto_accepted": True,
                   "confidence": confidence, "status": ASSIGNED,
                   "from": from_addr, "subject": payload.subject},
        )
    except Exception as e:
        logger.warning("[inbound→timeline] append_event failed: %s", e)
    # Mirror to Sicon (case + tracking note).
    try:
        await sicon_sync.push_case(case)
        evt = await db.svc_case_events.find_one(
            {"case_id": case_id, "type": "case_created"},
            sort=[("at", -1)], projection={"_id": 0},
        )
        if evt:
            await sicon_sync.push_event(evt, case_reference=reference)
    except Exception as e:
        logger.warning("[inbound→sicon] push failed: %s", e)
    # In-app + Web Push (push gated by engineer prefs in iter 216h156).
    try:
        from routes.svc.notifications import create_notification
        await create_notification(
            user_id=eng["id"],
            organization_id=eng["organization_id"],
            kind="job_assigned",
            title=f"Auto-created: {reference} · {title[:60]}",
            body=(parsed.get("site_name")
                  or parsed.get("customer_name")
                  or "Inbound email")
                + f" · confidence {int(confidence * 100)}%",
            link=f"/svc/engineer/jobs/{case_id}",
            source_type="case",
            source_id=case_id,
        )
    except Exception:
        pass
    # Immutable audit row — compliance posture matches the manual
    # accept path (iter 216h155).
    try:
        await audit_log(
            action="svc.case.auto_accept_email",
            user_id=eng["id"],
            user_email=eng.get("email") or "",
            resource_type="svc_case",
            resource_id=case_id,
            details=f"{reference} · from={from_addr} · "
                    f"confidence={confidence:.2f} · "
                    f"threshold={AUTOACCEPT_THRESHOLD:.2f}",
        )
    except Exception as e:
        logger.warning("[audit] auto_accept_email failed: %s", e)
    return case


# ── core ingest pipeline ─────────────────────────────────────────

async def _ingest(payload: NormalisedEmail,
                  *, parsed_override: Optional[dict] = None) -> dict:
    """Common path used by the live webhook and the simulator.

    `parsed_override` short-circuits the AI extraction step — used by
    the QA simulator (iter 216h157) so tests can pin auto-accept
    behaviour without racing a live model."""
    to_addr = _extract_email(payload.to)
    from_addr = _extract_email(payload.from_)
    if not to_addr:
        raise HTTPException(400, "Missing recipient address")
    if not from_addr:
        raise HTTPException(400, "Missing sender address")
    _verify_domain_allowed(to_addr)

    # Spam check (SendGrid default threshold is 5)
    if (payload.spam_score or 0) >= 5:
        await db.svc_inbound_email_log.insert_one({
            "id": str(uuid.uuid4()),
            "to": to_addr, "from": from_addr,
            "subject": payload.subject, "spam_score": payload.spam_score,
            "outcome": "rejected_spam", "created_at": _now(),
        })
        # Return 200 so SendGrid doesn't retry — we silently drop spam.
        return {"ok": True, "outcome": "rejected_spam"}

    slug = _local_part(to_addr)
    try:
        eng = await _resolve_engineer(slug)
    except HTTPException as e:
        await db.svc_inbound_email_log.insert_one({
            "id": str(uuid.uuid4()),
            "to": to_addr, "from": from_addr, "subject": payload.subject,
            "outcome": "no_engineer", "slug": slug, "created_at": _now(),
        })
        raise e

    # AI extraction (best-effort) — bypassed when the QA simulator
    # passes `parsed_override` (iter 216h157).
    body_text = payload.text or ""
    parsed = parsed_override if isinstance(parsed_override, dict) else await _ai_extract(body_text, payload.subject)

    title = (parsed.get("title") or payload.subject or "Inbound service request")[:160]
    description = (parsed.get("description")
                    or body_text[:4000]
                    or None)
    priority = (parsed.get("priority") or "P3").upper()
    if priority not in ("P1", "P2", "P3", "P4"):
        priority = "P3"

    # Iter 216h157 — compute auto-accept eligibility. We combine the
    # AI's self-reported confidence with a deterministic floor (fields
    # present + non-trivial title) so a hallucinated `confidence: 0.95`
    # alone can never trip the gate. min(ai, deterministic) wins.
    site_known = bool(parsed.get("site_name") or parsed.get("site_postcode"))
    customer_known = bool(parsed.get("customer_name"))
    title_substantial = len(title) >= 12
    deterministic_conf = (
        0.7
        + (0.1 if site_known else 0.0)
        + (0.1 if customer_known else 0.0)
        + (0.1 if title_substantial else 0.0)
    )
    try:
        ai_conf = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        ai_conf = 0.0
    confidence = round(min(ai_conf, deterministic_conf) if parsed else 0.0, 2)
    auto_accept = (
        confidence >= AUTOACCEPT_THRESHOLD
        and customer_known and site_known and title_substantial
    )

    if auto_accept:
        case_doc = await _auto_create_case(
            eng=eng,
            parsed=parsed,
            payload=payload,
            from_addr=from_addr,
            to_addr=to_addr,
            title=title,
            description=description,
            priority=priority,
            confidence=confidence,
        )
        await db.svc_inbound_email_log.insert_one({
            "id": str(uuid.uuid4()),
            "to": to_addr, "from": from_addr,
            "subject": payload.subject,
            "outcome": "case_auto_created",
            "case_id": case_doc["id"],
            "case_reference": case_doc.get("reference"),
            "slug": slug,
            "spam_score": payload.spam_score,
            "ai_used": True,
            "confidence": confidence,
            "ai_confidence": ai_conf,
            "deterministic_confidence": round(deterministic_conf, 2),
            "created_at": _now(),
        })
        return {
            "ok": True,
            "outcome": "case_auto_created",
            "case_id": case_doc["id"],
            "case_reference": case_doc.get("reference"),
            "confidence": confidence,
        }

    req_id = str(uuid.uuid4())
    doc = {
        "id": req_id,
        "engineer_id": eng["id"],
        "engineer_name": eng.get("full_name"),
        "organization_id": eng["organization_id"],
        "intake_slug": slug,
        "intake_channel": "inbound_email",
        "status": "pending",
        "customer_name": parsed.get("customer_name") or _extract_name(payload.from_) or from_addr,
        "customer_email": parsed.get("customer_email") or from_addr,
        "customer_phone": parsed.get("customer_phone"),
        "site_name": parsed.get("site_name"),
        "site_address": parsed.get("site_address"),
        "site_postcode": parsed.get("site_postcode"),
        "title": title,
        "description": description,
        "priority": priority,
        "confidence": confidence,
        "source": {
            "type": "email",
            "from": from_addr,
            "to": to_addr,
            "subject": payload.subject,
        },
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_job_requests.insert_one(doc)

    # Notification + Web Push
    try:
        from routes.svc.notifications import create_notification
        await create_notification(
            user_id=eng["id"],
            organization_id=eng["organization_id"],
            kind="job_request",
            title=f"Email request: {title[:60]}",
            body=f"{from_addr}{' — ' + parsed.get('site_name') if parsed.get('site_name') else ''}",
            link="/svc/engineer/inbox",
            source_type="job_request",
            source_id=req_id,
        )
    except Exception:
        pass

    # Audit log
    await db.svc_inbound_email_log.insert_one({
        "id": str(uuid.uuid4()),
        "to": to_addr, "from": from_addr,
        "subject": payload.subject,
        "outcome": "request_created",
        "request_id": req_id,
        "slug": slug,
        "spam_score": payload.spam_score,
        "ai_used": bool(parsed),
        "created_at": _now(),
    })

    return {"ok": True, "request_id": req_id, "engineer_id": eng["id"],
            "outcome": "request_created"}


# ── public webhook ──────────────────────────────────────────────

@public_router.post("/email")
async def inbound_email_webhook(
    request: Request,
    secret: Optional[str] = Query(None),
):
    _verify_secret(secret)
    payload = await _normalise_request(request)
    return await _ingest(payload)


class SimIn(BaseModel):
    to: str
    from_: str = Field(..., alias="from")
    subject: Optional[str] = None
    text: Optional[str] = None
    spam_score: Optional[float] = None
    # Iter 216h157 — QA-only deterministic override: skip the LLM call
    # and inject this dict as the parsed result. Used by test suites and
    # the support team to reproduce auto-accept decisions without
    # racing a live model. Still behind the webhook secret.
    parsed_override: Optional[dict] = None

    class Config:
        populate_by_name = True


@public_router.post("/email/test")
async def inbound_email_simulate(
    body: SimIn = Body(...),
    secret: Optional[str] = Query(None),
):
    """Plain-JSON simulator for QA. Same flow as the real webhook, so
    you can exercise routing and AI without setting up MX records.
    Still requires the shared secret."""
    _verify_secret(secret)
    payload = NormalisedEmail(
        to=body.to, **{"from": body.from_}, subject=body.subject,
        text=body.text, spam_score=body.spam_score,
    )
    return await _ingest(payload, parsed_override=body.parsed_override)


# ── engineer "what's my inbox address?" helper ──────────────────

@engineer_router.get("/inbound-address")
async def my_inbound_address(user=Depends(get_current_user)):
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    eng = await db.svc_engineers.find_one(
        {"id": user["id"], "organization_id": org},
        {"_id": 0, "intake_slug": 1, "id": 1},
    )
    if not eng or not eng.get("intake_slug"):
        # Lazily mint a slug — same path as supplier-card setup.
        from routes.svc.independence import _ensure_intake_slug
        slug = await _ensure_intake_slug(user)
    else:
        slug = eng["intake_slug"]
    domain = os.environ.get("INBOUND_EMAIL_DOMAIN") or "in.gymaxis.com"
    enabled = bool(os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET"))
    return {
        "email": f"{slug}@{domain}",
        "domain": domain,
        "slug": slug,
        "enabled": enabled,
    }


async def ensure_inbound_email_indexes() -> None:
    try:
        await db.svc_inbound_email_log.create_index(
            [("created_at", -1)],
            expireAfterSeconds=60 * 60 * 24 * 60,  # 60 days
        )
        await db.svc_inbound_email_log.create_index([("id", 1)], unique=True)
    except Exception as e:
        logger.warning("inbound email index warning: %s", e)


__all__ = [
    "public_router", "engineer_router",
    "ensure_inbound_email_indexes",
]
