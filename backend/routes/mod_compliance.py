"""Compliance / inspection calendar (Iter 216h116).

MOD audits gym safety quarterly — typically via DIO. The platform is
now the evidence pack. We model recurring compliance events
(insurance, PAT test, fixed-wiring, weight load-test, …), capture
``due_date`` + ``last_completed`` + an attachment URL, and surface
upcoming expiries with severity colouring.

Collection: ``mod_compliance_events``
  id              str   uuid
  site_id         str   organization_id (mod_site)
  kind            str   insurance · pat · fixed_wiring · load_test ·
                          weights_cert · fire_inspection · other
  title           str   human label
  due_date        str   ISO yyyy-mm-dd
  last_completed  str?  ISO yyyy-mm-dd
  notes           str?
  doc_url         str?  link to evidence pack PDF
  reminded_30     bool  emailed 30-day warning
  reminded_14     bool  emailed 14-day warning
  reminded_7      bool  emailed 7-day warning
  reminded_overdue bool emailed overdue
  created_at      str
  updated_at      str
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from utils.database import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MOD Compliance"])

KIND_LABELS = {
    "insurance": "Insurance renewal",
    "pat": "PAT testing",
    "fixed_wiring": "Fixed wiring inspection",
    "load_test": "Weights load test",
    "weights_cert": "Weights certification",
    "fire_inspection": "Fire-safety inspection",
    "ppm": "PPM service",
    "other": "Other",
}


async def _require_mod_pro(user: dict) -> dict:
    """Shared check — caller must be mod_org or mod_branch."""
    org_id = user.get("organization_id")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or org.get("account_type") not in ("mod_org", "mod_branch"):
        raise HTTPException(403, "MOD HQ access required")
    return org


async def _scope_check(hq_org: dict, site_id: str) -> dict:
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"},
        {"_id": 0, "mod_root_id": 1, "mod_branch": 1, "name": 1},
    )
    if not site:
        raise HTTPException(404, "Site not found")
    if site.get("mod_root_id") != hq_org.get("mod_root_id"):
        raise HTTPException(403, "Site outside MOD organisation scope")
    if hq_org.get("account_type") == "mod_branch" and site.get("mod_branch") != hq_org.get("mod_branch"):
        raise HTTPException(403, "Site outside branch scope")
    return site


class ComplianceEventBody(BaseModel):
    site_id: str
    kind: str = Field(..., max_length=40)
    title: str = Field(..., max_length=200)
    due_date: str  # ISO date
    last_completed: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    doc_url: Optional[str] = Field(default=None, max_length=500)


@router.get("/mod/pro/compliance")
async def list_compliance(site_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """List compliance events scoped to the HQ user's children. Filter
    by ``site_id`` when supplied (after scope check)."""
    hq = await _require_mod_pro(user)
    # Resolve set of site ids in scope.
    child_query = {
        "account_type": "mod_site", "is_mod": True, "status": {"$ne": "archived"},
    }
    if hq.get("account_type") == "mod_branch":
        if hq.get("mod_branch"):
            child_query["mod_branch"] = hq["mod_branch"]
        if hq.get("mod_root_id"):
            child_query["mod_root_id"] = hq["mod_root_id"]
    else:
        if hq.get("mod_root_id"):
            child_query["mod_root_id"] = hq["mod_root_id"]
    children = await db.organizations.find(
        child_query, {"_id": 0, "id": 1, "name": 1},
    ).to_list(2000)
    site_ids = {c["id"] for c in children}
    if site_id:
        if site_id not in site_ids:
            raise HTTPException(403, "Site outside scope")
        site_ids = {site_id}
    rows = await db.mod_compliance_events.find(
        {"site_id": {"$in": list(site_ids)}}, {"_id": 0},
    ).sort("due_date", 1).to_list(2000)
    # Enrich with site name + days_until.
    by_id = {c["id"]: c["name"] for c in children}
    today = date.today()
    enriched = []
    for r in rows:
        try:
            d = datetime.fromisoformat(r["due_date"]).date()
            days_until = (d - today).days
        except Exception:
            days_until = None
        enriched.append({
            **r,
            "site_name": by_id.get(r["site_id"], ""),
            "kind_label": KIND_LABELS.get(r.get("kind"), r.get("kind")),
            "days_until": days_until,
            "status": _bucket(days_until),
        })
    return {"events": enriched, "kinds": KIND_LABELS}


def _bucket(days_until: Optional[int]) -> str:
    if days_until is None:
        return "unknown"
    if days_until < 0:
        return "overdue"
    if days_until <= 7:
        return "critical"
    if days_until <= 14:
        return "warning"
    if days_until <= 30:
        return "soon"
    return "ok"


@router.post("/mod/pro/compliance")
async def create_compliance(body: ComplianceEventBody, request: Request, user: dict = Depends(get_current_user)):
    hq = await _require_mod_pro(user)
    site = await _scope_check(hq, body.site_id)
    try:
        datetime.fromisoformat(body.due_date)
    except Exception:
        raise HTTPException(400, "due_date must be ISO yyyy-mm-dd")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "site_id": body.site_id,
        "kind": body.kind,
        "title": body.title,
        "due_date": body.due_date,
        "last_completed": body.last_completed,
        "notes": (body.notes or "").strip() or None,
        "doc_url": body.doc_url,
        "reminded_30": False,
        "reminded_14": False,
        "reminded_7": False,
        "reminded_overdue": False,
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("id"),
    }
    await db.mod_compliance_events.insert_one(doc)
    doc.pop("_id", None)
    try:
        from utils.mod_audit import audit_event
        await audit_event(
            site_id=body.site_id, action="compliance.event",
            user=user, target_type="compliance", target_id=doc["id"],
            payload={"kind": body.kind, "due_date": body.due_date, "op": "create"},
            ip=(request.client.host if request.client else None),
        )
    except Exception:
        pass
    return {"ok": True, "event": doc, "site_name": site.get("name")}


@router.patch("/mod/pro/compliance/{event_id}")
async def update_compliance(event_id: str, body: ComplianceEventBody, request: Request, user: dict = Depends(get_current_user)):
    hq = await _require_mod_pro(user)
    existing = await db.mod_compliance_events.find_one({"id": event_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Compliance event not found")
    await _scope_check(hq, existing["site_id"])
    updates = body.model_dump(exclude_unset=True)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Reset reminder flags if the due_date moves.
    if updates.get("due_date") and updates["due_date"] != existing.get("due_date"):
        updates["reminded_30"] = False
        updates["reminded_14"] = False
        updates["reminded_7"] = False
        updates["reminded_overdue"] = False
    await db.mod_compliance_events.update_one({"id": event_id}, {"$set": updates})
    try:
        from utils.mod_audit import audit_event
        await audit_event(
            site_id=existing["site_id"], action="compliance.event",
            user=user, target_type="compliance", target_id=event_id,
            payload={"op": "update", "changed_keys": sorted(updates.keys())},
            ip=(request.client.host if request.client else None),
        )
    except Exception:
        pass
    return {"ok": True}


@router.delete("/mod/pro/compliance/{event_id}")
async def delete_compliance(event_id: str, user: dict = Depends(get_current_user)):
    hq = await _require_mod_pro(user)
    existing = await db.mod_compliance_events.find_one({"id": event_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Compliance event not found")
    await _scope_check(hq, existing["site_id"])
    await db.mod_compliance_events.delete_one({"id": event_id})
    return {"ok": True}


# ─── Reminder sweeper ───
async def sweep_compliance_reminders() -> dict:
    """Email 30/14/7-day pre-expiry reminders + overdue alerts.

    Called from the proactive-nudges cycle. Idempotent — flags are
    flipped on the event row so each band only sends once per cycle.
    """
    today = date.today()
    bands = [
        (30, "reminded_30", "30-day"),
        (14, "reminded_14", "14-day"),
        (7,  "reminded_7",  "7-day"),
        (0,  "reminded_overdue", "OVERDUE"),
    ]
    sent_total = 0
    for days, flag, label in bands:
        target = (today.fromordinal(today.toordinal() + days)).isoformat() if days > 0 else today.isoformat()
        # For positive days we want due_date <= today+days AND flag=False
        # AND due_date > today (so we don't re-send for already-overdue).
        if days > 0:
            cursor = db.mod_compliance_events.find({
                "due_date": {"$lte": target, "$gte": today.isoformat()},
                flag: {"$ne": True},
            }, {"_id": 0})
        else:
            cursor = db.mod_compliance_events.find({
                "due_date": {"$lt": today.isoformat()},
                flag: {"$ne": True},
            }, {"_id": 0})
        async for ev in cursor:
            try:
                site = await db.organizations.find_one(
                    {"id": ev["site_id"]},
                    {"_id": 0, "name": 1, "mod_force": 1, "mod_branch": 1},
                )
                hq_q = {
                    "account_type": {"$in": ["mod_branch", "mod_org"]},
                    "mod_force": (site or {}).get("mod_force"),
                }
                if (site or {}).get("mod_branch"):
                    hq_q["$or"] = [
                        {"mod_branch": site["mod_branch"]},
                        {"account_type": "mod_org"},
                    ]
                hq_users = await db.users.find(
                    {**hq_q, "is_active": {"$ne": False}, "email": {"$exists": True, "$ne": None}},
                    {"_id": 0, "email": 1},
                ).to_list(50)
                recipients = sorted({u["email"] for u in hq_users if u.get("email")})
                # Fall back to MOD on-call so a reminder is never lost.
                if not recipients:
                    fallback = os.environ.get("MOD_ONCALL_EMAIL")
                    if fallback:
                        recipients = [fallback]
                if recipients:
                    from utils.email_service import send_email
                    subject = f"[Compliance · {label}] {ev['title']} — {(site or {}).get('name','')}"
                    html = _reminder_html(ev, site, label)
                    for rcpt in recipients:
                        try:
                            await send_email(rcpt, subject, html)
                        except Exception as e:  # pragma: no cover
                            logger.warning("[compliance] email %s failed: %s", rcpt, e)
                await db.mod_compliance_events.update_one(
                    {"id": ev["id"]}, {"$set": {flag: True}},
                )
                sent_total += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("[compliance] reminder failed for %s: %s", ev.get("id"), exc)
    if sent_total:
        logger.info("[compliance] sweep complete — sent %s reminders", sent_total)
    return {"reminders_sent": sent_total}


def _reminder_html(ev: dict, site: Optional[dict], label: str) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Compliance · {label}</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{ev.get('title','')}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p><strong>Site:</strong> {(site or {}).get('name','')}<br>
       <strong>Due:</strong> {ev.get('due_date','')}<br>
       <strong>Type:</strong> {KIND_LABELS.get(ev.get('kind'), ev.get('kind'))}</p>
    {f'<p>{ev.get("notes")}</p>' if ev.get('notes') else ''}
    {f'<p><a href="{ev.get("doc_url")}" style="color:#19CDFF;">Evidence pack →</a></p>' if ev.get('doc_url') else ''}
  </div>
</div>"""
