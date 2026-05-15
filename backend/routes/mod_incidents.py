"""MOD Personal-Incident (RIDDOR) workflow.

Iter 216h117 — P1 #3. Equipment faults and personal injuries are
fundamentally different beasts:

  * Faults route to engineering / supplier (broken kit).
  * Personal incidents route to the base H&S Officer (a person was
    hurt). They have legal reporting obligations under RIDDOR.

This module captures incidents in a dedicated ``mod_incidents``
collection, emails the H&S officer, schedules a 7-day RIDDOR follow-up
nudge and offers a structured closure questionnaire.

Schema (db.mod_incidents):
  id                   str uuid
  site_id              str organization_id
  incident_ref         str MOD-INC-YYYY-NNNNN
  occurred_at          str ISO timestamp
  category             str slip · trip · impact · electric · cardiac ·
                            equipment · other
  description          str  classified-scanned
  injured_party_name   str (may be redacted on export)
  injured_party_type   str service · civilian · contractor · public
  injury_severity      str none · first_aid · medical · hospitalised ·
                            life_changing · fatal
  riddor_reportable    bool
  riddor_followup_at   str?  +7 day reminder timestamp
  reporter_name        str
  reporter_email       str
  reporter_phone       str
  classification_flags list[dict]   reuses utils/mod_classification
  status               str   open · investigating · closed
  closure_questionnaire dict?  (root_cause, contributing_factors,
                                corrective_action, completed_at, by)
  created_at           str
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MOD Incidents"])

SEVERITY_ORDER = {
    "none": 0, "first_aid": 1, "medical": 2,
    "hospitalised": 3, "life_changing": 4, "fatal": 5,
}

SEVERITY_LABELS = {
    "none": "No injury", "first_aid": "First aid only",
    "medical": "Medical attention", "hospitalised": "Hospitalised",
    "life_changing": "Life-changing", "fatal": "Fatal",
}

CATEGORY_LABELS = {
    "slip": "Slip", "trip": "Trip", "impact": "Impact",
    "electric": "Electric shock", "cardiac": "Cardiac event",
    "equipment": "Equipment-related", "other": "Other",
}


async def _require_mod_site(user: dict) -> dict:
    """Caller must belong to a mod_site organisation."""
    org_id = user.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or org.get("account_type") != "mod_site":
        raise HTTPException(403, "MOD site access required")
    return org


def _next_incident_ref() -> str:
    now = datetime.now(timezone.utc)
    return f"MOD-INC-{now.year}-{str(uuid.uuid4().int)[:5].zfill(5)}"


def _suggest_riddor(category: str, severity: str) -> bool:
    """Conservative auto-suggestion of RIDDOR reportability.

    Real RIDDOR rules are nuanced — we err on the side of suggesting
    reportable so HQ takes a second look. The user remains the
    decision-maker via the ``riddor_reportable`` field on the payload.
    """
    if severity in ("life_changing", "fatal", "hospitalised"):
        return True
    if severity == "medical" and category in ("electric", "cardiac"):
        return True
    return False


class IncidentPayload(BaseModel):
    occurred_at: Optional[str] = None  # ISO; defaults to now
    category: str = Field(..., max_length=40)
    description: str = Field(..., min_length=20, max_length=4000)
    injured_party_name: str = Field(..., min_length=2, max_length=200)
    injured_party_type: str = Field(default="service", max_length=20)
    injury_severity: str = Field(..., max_length=20)
    riddor_reportable: Optional[bool] = None  # caller may force
    reporter_name: str = Field(..., min_length=2, max_length=200)
    reporter_email: EmailStr
    reporter_phone: Optional[str] = Field(default=None, max_length=40)
    equipment_id: Optional[str] = None  # for category=equipment


@router.post("/mod/site/incidents")
async def submit_incident(
    payload: IncidentPayload,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """A PTI raises a personal-incident record. Always routes to the
    base H&S officer (if configured) and the on-call mailbox."""
    org = await _require_mod_site(user)
    if payload.category not in CATEGORY_LABELS:
        raise HTTPException(400, f"category must be one of {list(CATEGORY_LABELS)}")
    if payload.injury_severity not in SEVERITY_LABELS:
        raise HTTPException(400, f"injury_severity must be one of {list(SEVERITY_LABELS)}")

    # Reuse the classification scanner — incidents typically include
    # personal data that's at minimum OFFICIAL-SENSITIVE so the same
    # warning surface applies.
    from utils.mod_classification import scan_many
    classification_flags = scan_many([
        payload.description, payload.injured_party_name, payload.reporter_name,
    ])

    riddor = (
        payload.riddor_reportable
        if payload.riddor_reportable is not None
        else _suggest_riddor(payload.category, payload.injury_severity)
    )

    now = datetime.now(timezone.utc)
    occurred = now
    if payload.occurred_at:
        try:
            occurred = datetime.fromisoformat(payload.occurred_at)
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(400, "occurred_at must be ISO format")
    incident_id = str(uuid.uuid4())
    ref = _next_incident_ref()
    riddor_followup = (occurred + timedelta(days=7)).isoformat() if riddor else None

    doc = {
        "id": incident_id,
        "site_id": org["id"],
        "incident_ref": ref,
        "occurred_at": occurred.isoformat(),
        "category": payload.category,
        "description": payload.description.strip(),
        "injured_party_name": payload.injured_party_name.strip(),
        "injured_party_type": payload.injured_party_type,
        "injury_severity": payload.injury_severity,
        "riddor_reportable": bool(riddor),
        "riddor_followup_at": riddor_followup,
        "riddor_followup_sent": False,
        "reporter_name": payload.reporter_name.strip(),
        "reporter_email": payload.reporter_email,
        "reporter_phone": payload.reporter_phone,
        "equipment_id": payload.equipment_id,
        "classification_flags": classification_flags,
        "classification_flagged": bool(classification_flags),
        "status": "open",
        "closure_questionnaire": None,
        "created_at": now.isoformat(),
        "created_by_user_id": user.get("id"),
    }
    await db.mod_incidents.insert_one(doc)

    # Email the configured base H&S officer + on-call.
    site = await db.organizations.find_one(
        {"id": org["id"]},
        {"_id": 0, "name": 1, "hs_officer_email": 1, "hs_officer_name": 1,
         "dio_contact_email": 1},
    ) or {}
    recipients: list[str] = []
    if site.get("hs_officer_email"):
        recipients.append(site["hs_officer_email"])
    oncall = os.environ.get("MOD_ONCALL_EMAIL") or os.environ.get("TRIAL_SIGNUP_NOTIFY_EMAIL")
    if oncall:
        recipients.append(oncall)
    if riddor and site.get("dio_contact_email"):
        recipients.append(site["dio_contact_email"])

    if recipients:
        try:
            html = _incident_email_html(site, doc, riddor=riddor)
            subject = f"[MOD Incident{' · RIDDOR' if riddor else ''}] {ref} — {site.get('name')}"
            import asyncio as _asyncio
            for rcpt in sorted(set(recipients)):
                _asyncio.create_task(send_email(rcpt, subject, html))
        except Exception as exc:  # pragma: no cover
            logger.warning("Incident email dispatch failed: %s", exc)

    # Audit (chained).
    try:
        from utils.mod_audit import audit_event
        await audit_event(
            site_id=org["id"], action="compliance.event",
            user=user, target_type="incident", target_id=incident_id,
            payload={
                "kind": "incident.create",
                "category": payload.category,
                "severity": payload.injury_severity,
                "riddor_reportable": riddor,
                "incident_ref": ref,
            },
            ip=(request.client.host if request.client else None),
        )
    except Exception:  # pragma: no cover
        pass

    return {
        "ok": True,
        "incident_id": incident_id,
        "incident_ref": ref,
        "riddor_reportable": riddor,
        "riddor_followup_at": riddor_followup,
        "classification_flags": classification_flags,
        "recipients": sorted(set(recipients)),
    }


@router.get("/mod/site/incidents")
async def list_incidents(user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    rows = await db.mod_incidents.find(
        {"site_id": org["id"]}, {"_id": 0},
    ).sort("created_at", -1).limit(100).to_list(100)
    return {"incidents": rows}


@router.get("/mod/site/incidents/{incident_id}")
async def incident_detail(incident_id: str, user: dict = Depends(get_current_user)):
    org = await _require_mod_site(user)
    doc = await db.mod_incidents.find_one(
        {"id": incident_id, "site_id": org["id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Incident not found")
    return doc


class ClosureBody(BaseModel):
    root_cause: str = Field(..., min_length=20, max_length=2000)
    contributing_factors: str = Field(..., min_length=10, max_length=2000)
    corrective_action: str = Field(..., min_length=20, max_length=2000)
    riddor_submission_ref: Optional[str] = Field(default=None, max_length=120)


@router.post("/mod/site/incidents/{incident_id}/closure")
async def close_incident(
    incident_id: str,
    body: ClosureBody,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Senior PTI / manager completes the post-incident questionnaire,
    flipping the record to ``status=closed``."""
    org = await _require_mod_site(user)
    if user.get("role") not in ("owner", "manager", "master_admin"):
        raise HTTPException(403, "Only owners / managers can close an incident")
    incident = await db.mod_incidents.find_one(
        {"id": incident_id, "site_id": org["id"]}, {"_id": 0},
    )
    if not incident:
        raise HTTPException(404, "Incident not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    questionnaire = {
        "root_cause": body.root_cause.strip(),
        "contributing_factors": body.contributing_factors.strip(),
        "corrective_action": body.corrective_action.strip(),
        "riddor_submission_ref": (body.riddor_submission_ref or "").strip() or None,
        "completed_at": now_iso,
        "completed_by_id": user.get("id"),
        "completed_by_email": user.get("email"),
    }
    await db.mod_incidents.update_one(
        {"id": incident_id},
        {"$set": {
            "status": "closed",
            "closure_questionnaire": questionnaire,
            "closed_at": now_iso,
        }},
    )
    try:
        from utils.mod_audit import audit_event
        await audit_event(
            site_id=org["id"], action="compliance.event",
            user=user, target_type="incident", target_id=incident_id,
            payload={
                "kind": "incident.close",
                "incident_ref": incident.get("incident_ref"),
                "riddor_submission_ref": questionnaire["riddor_submission_ref"],
            },
            ip=(request.client.host if request.client else None),
        )
    except Exception:
        pass
    return {"ok": True, "incident_id": incident_id, "questionnaire": questionnaire}


@router.put("/mod/pro/sites/{site_id}/hs-officer")
async def hq_set_hs_officer(
    site_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """HQ owner/manager records the base H&S officer for a child site
    so incidents auto-route correctly."""
    # Defer to mod_portal scoping helpers via local import to avoid a
    # circular dependency.
    from routes.mod_portal import _require_mod_pro
    hq_org = await _require_mod_pro(user)
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"},
        {"_id": 0, "mod_root_id": 1, "mod_branch": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != hq_org.get("mod_root_id"):
        raise HTTPException(403, "Outside MOD scope")
    if hq_org.get("account_type") == "mod_branch" and site.get("mod_branch") != hq_org.get("mod_branch"):
        raise HTTPException(403, "Outside branch scope")
    updates = {
        k: (body.get(k) or "").strip() or None
        for k in ("hs_officer_email", "hs_officer_name", "hs_officer_phone")
    }
    updates["hs_officer_updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.organizations.update_one({"id": site_id}, {"$set": updates})
    return {"ok": True, **updates}


# ─── Reminder sweeper ───
async def sweep_riddor_followups() -> dict:
    """Email a 7-day RIDDOR follow-up for any reportable incident still
    open and past its ``riddor_followup_at``. Idempotent — sets
    ``riddor_followup_sent=True`` after first send."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = db.mod_incidents.find(
        {
            "riddor_reportable": True,
            "riddor_followup_sent": {"$ne": True},
            "riddor_followup_at": {"$lte": now_iso},
            "status": {"$ne": "closed"},
        },
        {"_id": 0},
    )
    sent = 0
    async for incident in cursor:
        try:
            site = await db.organizations.find_one(
                {"id": incident["site_id"]},
                {"_id": 0, "name": 1, "hs_officer_email": 1,
                 "dio_contact_email": 1},
            ) or {}
            recipients: list[str] = []
            if site.get("hs_officer_email"):
                recipients.append(site["hs_officer_email"])
            if site.get("dio_contact_email"):
                recipients.append(site["dio_contact_email"])
            oncall = os.environ.get("MOD_ONCALL_EMAIL")
            if oncall:
                recipients.append(oncall)
            if recipients:
                html = _riddor_followup_html(site, incident)
                subject = (
                    f"[RIDDOR 7-day follow-up] {incident['incident_ref']} — {site.get('name','')}"
                )
                for rcpt in sorted(set(recipients)):
                    try:
                        await send_email(rcpt, subject, html)
                    except Exception as exc:  # pragma: no cover
                        logger.warning("RIDDOR follow-up email failed for %s: %s", rcpt, exc)
            await db.mod_incidents.update_one(
                {"id": incident["id"]},
                {"$set": {"riddor_followup_sent": True,
                          "riddor_followup_sent_at": now_iso}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("RIDDOR sweep failed for %s: %s", incident.get("id"), exc)
    if sent:
        logger.info("[riddor] sent %s follow-up reminders", sent)
    return {"reminders_sent": sent}


def _incident_email_html(site: dict, doc: dict, riddor: bool) -> str:
    banner_tone = "#dc2626" if riddor else "#19CDFF"
    riddor_block = (
        "<p style='margin:14px 0;padding:10px 14px;background:#fee2e2;border-left:3px solid #dc2626;color:#991b1b;'><strong>RIDDOR-reportable</strong> — 7-day follow-up reminder will fire automatically.</p>"
        if riddor else ""
    )
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid {banner_tone};">
    <div style="color:{banner_tone};font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · Personal incident</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{doc['incident_ref']} — {site.get('name','')}</h1>
  </div>
  <div style="padding:22px 28px;">
    {riddor_block}
    <table style="width:100%;font-size:13px;margin-top:6px;">
      <tr><td style='padding:6px 0;color:#6E7476;width:160px;'>Occurred</td><td style='font-weight:700;'>{doc.get('occurred_at','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Category</td><td>{CATEGORY_LABELS.get(doc.get('category'), doc.get('category'))}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Severity</td><td style='font-weight:700;'>{SEVERITY_LABELS.get(doc.get('injury_severity'), doc.get('injury_severity'))}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;vertical-align:top;'>Description</td><td>{doc.get('description','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Injured party</td><td>{doc.get('injured_party_name','')} · {doc.get('injured_party_type','')}</td></tr>
      <tr><td style='padding:6px 0;color:#6E7476;'>Reporter</td><td>{doc.get('reporter_name','')} · <a href='mailto:{doc.get('reporter_email','')}' style='color:#19CDFF;'>{doc.get('reporter_email','')}</a> · {doc.get('reporter_phone','')}</td></tr>
    </table>
  </div>
</div>"""


def _riddor_followup_html(site: dict, doc: dict) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#dc2626;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#fee2e2;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service · RIDDOR · 7-DAY follow-up</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{doc.get('incident_ref','')} — {site.get('name','')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>This incident remains <strong>open</strong> seven days after occurrence. Please confirm:</p>
    <ul>
      <li>Has the RIDDOR submission been filed to the HSE F2508 portal?</li>
      <li>If so, capture the submission reference in the closure questionnaire.</li>
      <li>If not, raise immediately or document the reason it is not reportable.</li>
    </ul>
    <p style="color:#6E7476;font-size:13px;">Severity: <strong style="color:#1B1D1D;">{SEVERITY_LABELS.get(doc.get('injury_severity'), doc.get('injury_severity'))}</strong> · Category: {CATEGORY_LABELS.get(doc.get('category'), doc.get('category'))}</p>
  </div>
</div>"""
