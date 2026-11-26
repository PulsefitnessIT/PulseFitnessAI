"""Approval-first renewals.

``prepare_renewals`` identifies genuine upcoming renewals, verifies the data
and prepares ONE renewal draft per contract (status ``renewal_pending_approval``)
plus one Action Centre item. Nothing is emailed. ``approve_and_send_renewal``
is the explicit coordinator step that sends it to the customer.
"""
from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.cm_actions import raise_action, resolve_action, _customer_email

RENEWAL_WINDOW_DAYS = 90
LIVE = ("active", "signed", "expiring")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date(v):
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except (TypeError, ValueError):
        return None


def _add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def next_term(end_iso: str):
    """Calendar-aware: new term starts the day after expiry, runs 12 months."""
    end = _date(end_iso)
    if not end:
        return None, None
    start = end + timedelta(days=1)
    return start.isoformat(), (_add_years(start, 1) - timedelta(days=1)).isoformat()


async def _approved_uplift(org_id: str, contract: dict):
    """Approved RPI review for this contract → (percent, basis) else None."""
    r = await db.crm2_afs_rpi_reviews.find_one(
        {"organization_id": org_id, "contract_id": contract["id"], "status": "approved"},
        {"_id": 0}, sort=[("approved_at", -1)])
    if r and r.get("previous_value"):
        pct = round((float(r["proposed_value"]) / float(r["previous_value"]) - 1) * 100, 2)
        return pct, f"Approved RPI review ({r.get('approved_by') or 'approver'})"
    return None


async def _existing_renewal(org_id: str, contract: dict):
    rid = contract.get("renewal_contract_id")
    q = {"organization_id": org_id, "previous_contract_id": contract["id"],
         "status": {"$nin": ["cancelled", "declined", "rejected"]}}
    if rid:
        q = {"$or": [{"id": rid, "status": {"$nin": ["cancelled", "declined", "rejected"]}}, q]}
    return await db.crm2_contracts.find_one(q, {"_id": 0, "id": 1, "status": 1, "contract_number": 1})


async def check_renewal(org_id: str, contract: dict) -> list[str]:
    problems = []
    if not _date(contract.get("start_date")):
        problems.append("verified start date")
    if not _date(contract.get("end_date")):
        problems.append("verified expiry date")
    if not float(contract.get("annual_value") or 0):
        problems.append("current contract value")
    if not await _customer_email(org_id, contract):
        problems.append("customer contact email")
    return problems


async def prepare_renewals(org_id: str, *, actor: str, dry_run: bool = False) -> dict:
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=RENEWAL_WINDOW_DAYS)).isoformat()
    prepared, blocked, skipped, would = [], [], [], []
    async for c in db.crm2_contracts.find(
            {"organization_id": org_id, "status": {"$in": list(LIVE)},
             "end_date": {"$gte": today.isoformat(), "$lte": horizon}}, {"_id": 0}):
        ex = await _existing_renewal(org_id, c)
        if ex:
            skipped.append({"contract_id": c["id"], "reason": "renewal_already_in_progress", "renewal_id": ex["id"]})
            continue
        problems = await check_renewal(org_id, c)
        if problems:
            blocked.append({"contract_id": c["id"], "missing": problems})
            if not dry_run:
                await raise_action(
                    org_id, f"cm:renewal-blocked:{c['id']}:{c.get('end_date')}", type_="renewal_blocked",
                    subject=f"Renewal needs information: {c.get('contract_number')}",
                    body=f"{c.get('company_name') or 'Customer'} expires {c.get('end_date')} — add the {', '.join(problems)} so the renewal can be prepared.",
                    contract=c, extra={"missing_fields": problems})
            continue
        appr = await _approved_uplift(org_id, c)
        new_start, new_end = next_term(c["end_date"])
        item = {"contract_id": c["id"], "contract_number": c.get("contract_number"),
                "company_name": c.get("company_name"), "new_start": new_start, "new_end": new_end,
                "current_value": float(c.get("annual_value") or 0),
                "uplift_percent": appr[0] if appr else 0.0,
                "uplift_status": "approved" if appr else "needs_approval",
                "uplift_basis": appr[1] if appr else "No approved price increase — coordinator to confirm"}
        item["new_value"] = round(item["current_value"] * (1 + item["uplift_percent"] / 100), 2)
        if dry_run:
            would.append(item)
            continue
        rid = await _create_draft(org_id, c, item, actor)
        await resolve_action(org_id, f"cm:renewal-blocked:{c['id']}:{c.get('end_date')}", "Renewal draft prepared.")
        await raise_action(
            org_id, f"cm:renewal-approval:{rid}", type_="renewal_approval",
            subject=f"Renewal ready for approval: {c.get('contract_number')}",
            body=(f"{c.get('company_name') or 'Customer'} — new term {new_start} to {new_end} at "
                  f"£{item['new_value']:,.2f}/yr ({item['uplift_basis']}). Review and send."),
            contract=c, extra={"renewal_contract_id": rid, "uplift_status": item["uplift_status"]})
        prepared.append({**item, "renewal_contract_id": rid})
    return {"dry_run": dry_run, "prepared": prepared, "would_prepare": would, "blocked": blocked, "skipped": skipped,
            "totals": {"prepared": len(prepared), "would_prepare": len(would), "blocked": len(blocked), "skipped": len(skipped)}}


async def _create_draft(org_id: str, c: dict, item: dict, actor: str) -> str:
    new_id = str(uuid.uuid4())
    pricing = {**(c.get("pricing") or {}), "annual_value": item["new_value"], "monthly_value": round(item["new_value"] / 12, 2)}
    doc = {
        **{k: v for k, v in c.items() if k not in (
            "id", "_id", "created_at", "status", "signature", "signed_by", "signed_at", "version",
            "accept_token", "auto_renewal_sent_at", "renewal_contract_id", "sicon_contract_id",
            "sage_reference", "sicon_sync_status", "sage_sync_status", "finance_sync_status",
            "mm_record_key", "mm_baseline", "mm_conflicts", "mm_source", "sicon_sync", "revision", "historical_import")},
        "renewed_from_mm_record_key": c.get("mm_record_key"),
        "id": new_id, "contract_number": f"{c.get('contract_number', 'CTR')}/R{(c.get('version') or 1) + 1}",
        "status": "renewal_pending_approval", "previous_contract_id": c["id"],
        "start_date": item["new_start"], "end_date": item["new_end"],
        "annual_value": item["new_value"], "total_value": item["new_value"], "pricing": pricing,
        "renewal_uplift_percent": item["uplift_percent"], "renewal_uplift_status": item["uplift_status"],
        "renewal_uplift_basis": item["uplift_basis"], "version": (c.get("version") or 1) + 1,
        "created_by": actor, "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_contracts.insert_one(dict(doc))
    assets = await db.crm2_contract_assets.find({"contract_id": c["id"], "organization_id": org_id}, {"_id": 0}).to_list(2000)
    for a in assets:
        await db.crm2_contract_assets.insert_one({**{k: v for k, v in a.items() if k not in ("id", "contract_id")},
                                                 "id": str(uuid.uuid4()), "contract_id": new_id, "created_at": _now()})
    await db.crm2_contracts.update_one({"id": c["id"]}, {"$set": {"renewal_contract_id": new_id, "updated_at": _now()}})
    return new_id


def renewal_email_live() -> bool:
    """Customer renewal emails only leave the system when CM_RENEWAL_EMAIL_LIVE=true (preview/tests: off)."""
    return os.environ.get("CM_RENEWAL_EMAIL_LIVE", "").lower() == "true"


# renewal_email_state: awaiting_dispatch → sending → sent | failed ; awaiting_dispatch/failed → cancelled
COMMS_LABELS = {
    "awaiting_dispatch": "Approved — awaiting issue (email queued; live renewal emails are off)",
    "email_cancelled": "Approved — customer email cancelled, not issued",
    "issued_manually": "Issued manually (recorded by a manager)",
    "pending_approval": "Prepared — awaiting approval",
    "awaiting_price_approval": "Price increase awaiting manager approval",
    "approved_not_delivered": "Approved — email NOT delivered",
    "delivered": "Delivered — awaiting customer response",
    "accepted": "Accepted", "declined": "Declined", "expired": "Expired",
}


def comms_status(r: dict, prev_end: str | None = None) -> str:
    st = r.get("status")
    if st == "renewal_pending_approval":
        return "awaiting_price_approval" if r.get("renewal_price_request") else "pending_approval"
    if st in ("active", "signed"):
        return "accepted"
    if st in ("declined", "rejected"):
        return "declined"
    today = datetime.now(timezone.utc).date().isoformat()
    if st == "sent" and (prev_end or "9999") < today:
        return "expired"
    if r.get("renewal_email_state") == "awaiting_dispatch":
        return "awaiting_dispatch"
    if st == "sent" and r.get("renewal_issued_via") == "manual":
        return "issued_manually"
    if r.get("renewal_email_state") == "cancelled":
        return "email_cancelled"
    return "delivered" if r.get("renewal_email_delivered") else "approved_not_delivered"


async def standard_uplift(org_id: str, renewal: dict) -> float:
    prev = {"id": renewal.get("previous_contract_id")}
    appr = await _approved_uplift(org_id, prev) if prev["id"] else None
    return appr[0] if appr else 0.0


async def _send_renewal_email(org_id: str, r: dict) -> tuple[bool, str, str]:
    """Returns (delivered, accept_link, to). Delivery is only True when the
    email provider accepted the message."""
    of = {"organization_id": org_id}
    to_email = await _customer_email(org_id, r)
    if not to_email:
        raise ValueError("No customer contact email on this contract.")
    from routes.crm_contract_send import _build_catalog, _ensure_accept_token
    from utils.crm_contract_pdf import build_contract_pdf
    from utils.brand_urls import app_url_for_org
    token = await _ensure_accept_token(r["id"], of)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    pdf = b""
    try:
        from utils.document_branding import resolve_company_if_configured
        company = await resolve_company_if_configured(db, {"id": org_id, "name": org.get("name")})
        pdf = build_contract_pdf(r, org, _build_catalog(), company=company)
    except Exception:
        pdf = b""
    link = f"{app_url_for_org(org)}/contracts/accept/{token}"
    try:
        from utils.email import send_email
        delivered = bool(await send_email(
            to=to_email, subject=f"Your maintenance renewal is ready — {r['contract_number']}",
            html=(f"<p>Hello,</p><p>Your maintenance agreement is due for renewal. The new term runs "
                  f"{r.get('start_date')} to {r.get('end_date')} at <strong>£{float(r['annual_value']):,.2f} per year</strong>.</p>"
                  f"<p>Review and accept online: <a href=\"{link}\">{link}</a></p>"
                  f"<p>Kind regards,<br/>{org.get('name') or 'Pulse Fitness'}</p>"),
            attachments=[{"filename": f"renewal_{r['contract_number']}.pdf",
                          "content": base64.b64encode(pdf).decode("ascii")}] if pdf else None,
            organization_id=org_id, kind="crm_contract_renewal"))
    except Exception:
        delivered = False
    return delivered, link, to_email


async def request_price_approval(renewal_id: str, user: dict, uplift_percent: float, reason: str) -> dict:
    org_id = user.get("organization_id")
    r = await db.crm2_contracts.find_one({"id": renewal_id, "organization_id": org_id, "status": "renewal_pending_approval"}, {"_id": 0})
    if not r:
        return {"ok": False, "error": "This renewal is not awaiting approval."}
    req = {"uplift_percent": round(float(uplift_percent), 2), "reason": reason or "", "by": user.get("email"), "at": _now()}
    await db.crm2_contracts.update_one({"id": renewal_id}, {
        "$set": {"renewal_price_request": req, "updated_at": _now()},
        "$push": {"approval_evidence": {"action": "price_increase_requested", **req,
                                        "role": user.get("crm_workspace_role")}}})
    await resolve_action(org_id, f"cm:renewal-approval:{renewal_id}", "Submitted for manager price approval.")
    await raise_action(
        org_id, f"cm:renewal-price:{renewal_id}:{req['uplift_percent']}", type_="renewal_price_approval",
        subject=f"Approve renewal increase: {r.get('contract_number')}",
        body=f"{r.get('company_name') or 'Customer'} — {req['uplift_percent']}% requested by {user.get('email')}. {reason or ''}".strip(),
        contract={"id": r.get("previous_contract_id"), "company_id": None, "contract_number": r.get("contract_number")},
        extra={"renewal_contract_id": renewal_id, "requested_uplift_percent": req["uplift_percent"],
               "company_id": r.get("company_id"), "owner_id": "system", "owner_name": "Managers"})
    return {"ok": True, "request": req}


async def approve_and_send_renewal(renewal_id: str, user: dict, uplift_percent=None) -> dict:
    """Approve + issue. Coordinators may issue STANDARD renewals (0% or the
    approved RPI figure); any other increase needs ``renewals.approve``.
    Every decision is recorded as approval evidence."""
    org_id = user.get("organization_id")
    of = {"organization_id": org_id}
    perms = user.get("crm_permissions") or []
    draft = await db.crm2_contracts.find_one({"id": renewal_id, **of, "status": "renewal_pending_approval"}, {"_id": 0})
    if not draft:
        return {"ok": False, "error": "This renewal is not awaiting approval (already sent or not found)."}
    std = await standard_uplift(org_id, draft)
    pct = round(float(uplift_percent), 2) if uplift_percent is not None else round(float(draft.get("renewal_uplift_percent") or 0), 2)
    standard = abs(pct - std) < 0.001
    if not standard and "renewals.approve" not in perms:
        return {"ok": False, "code": "approval_required",
                "error": f"A {pct}% increase differs from the standard {std}% — submit it for manager approval."}
    r = await db.crm2_contracts.find_one_and_update(
        {"id": renewal_id, **of, "status": "renewal_pending_approval"},
        {"$set": {"status": "renewal_sending", "updated_at": _now()}}, projection={"_id": 0})
    if not r:
        return {"ok": False, "error": "This renewal is already being sent."}
    prev = await db.crm2_contracts.find_one({"id": r.get("previous_contract_id"), **of}, {"_id": 0}) or {}
    try:
        base = float(prev.get("annual_value") or r.get("annual_value") or 0)
        r["annual_value"] = r["total_value"] = round(base * (1 + pct / 100), 2)
        live = renewal_email_live()
        if live:
            delivered, link, to_email = await _send_renewal_email(org_id, r)
        else:
            from routes.crm_contract_send import _ensure_accept_token
            from utils.brand_urls import app_url_for_org
            to_email = await _customer_email(org_id, r)
            if not to_email:
                raise ValueError("No customer contact email on this contract.")
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
            link = f"{app_url_for_org(org)}/contracts/accept/{await _ensure_accept_token(r['id'], of)}"
            delivered = False
        evidence = {"action": "approved_and_issued", "by": user.get("email"), "role": user.get("crm_workspace_role"),
                    "uplift_percent": pct, "standard_percent": std,
                    "basis": "standard (approved RPI / no increase)" if standard else "manager-approved increase",
                    "price_request": r.get("renewal_price_request"), "at": _now()}
        status = "delivered" if delivered else ("approved_not_delivered" if live else "awaiting_dispatch")
        # Commercial approval ≠ issue: the renewal is only "sent" (issued) once the email really went
        # (or a manager records a manual issue). Queued or failed emails leave it approved / awaiting issue.
        issued = bool(delivered)
        evidence["action"] = "approved_and_issued" if issued else "approved_awaiting_issue"
        await db.crm2_contracts.update_one({"id": renewal_id}, {
            "$set": {"status": "sent" if issued else "renewal_approved", **({"renewal_issued_at": _now()} if issued else {}),
                     "annual_value": r["annual_value"], "total_value": r["total_value"],
                     "renewal_uplift_percent": pct, "renewal_uplift_status": "approved",
                     "renewal_uplift_basis": evidence["basis"], "renewal_approved_by": user.get("email"),
                     "renewal_approved_at": _now(), "renewal_sent_to": to_email, "renewal_email_delivered": delivered,
                     "renewal_accept_link": link, "renewal_comms_status": status,
                     "renewal_email_state": "sent" if delivered else ("failed" if live else "awaiting_dispatch"),
                     "updated_at": _now()},
            "$push": {"approval_evidence": evidence}})
        if issued:
            await db.crm2_contracts.update_one({"id": prev.get("id")}, {"$set": {"auto_renewal_sent_at": _now(), "updated_at": _now()}})
        await resolve_action(org_id, f"cm:renewal-approval:{renewal_id}",
                             f"Approved{' and issued' if issued else ' — awaiting issue'} by {user.get('email')}.")
        async for a in db.crm2_activities.find({**of, "type": "renewal_price_approval", "renewal_contract_id": renewal_id, "status": "open"}, {"_id": 0, "dedupe_key": 1}):
            await resolve_action(org_id, a["dedupe_key"], f"Approved by {user.get('email')}.")
        if not delivered and live:
            await raise_action(org_id, f"cm:renewal-undelivered:{renewal_id}", type_="renewal_undelivered",
                               subject=f"Renewal email not delivered: {r['contract_number']}",
                               body=f"Share the accept link with {to_email} or resend: {link}",
                               contract={"id": prev.get("id"), "company_id": r.get("company_id"), "contract_number": r["contract_number"]},
                               extra={"renewal_contract_id": renewal_id, "accept_link": link})
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org_id, "type": "contract_renewal",
            "contract_id": prev.get("id"), "company_id": r.get("company_id"),
            "subject": f"Renewal {'issued' if issued else 'approved — awaiting issue'}: {r['contract_number']}",
            "body": f"Approved by {user.get('email')} at {pct}% — {COMMS_LABELS[status]} ({to_email})",
            "owner_id": user.get("id"), "owner_name": user.get("full_name", ""), "created_at": _now()})
        return {"ok": True, "renewal_contract_id": renewal_id, "to": to_email, "email_delivered": delivered,
                "comms_status": status, "accept_link": link, "annual_value": r["annual_value"]}
    except Exception as e:
        await db.crm2_contracts.update_one({"id": renewal_id, "status": "renewal_sending"},
                                           {"$set": {"status": "renewal_pending_approval"}})
        return {"ok": False, "error": str(e)}


async def resend_renewal(renewal_id: str, user: dict) -> dict:
    org_id = user.get("organization_id")
    if not renewal_email_live():
        return {"ok": False, "error": "Live renewal emails are switched off — the email stays queued until they are switched on."}
    r = await db.crm2_contracts.find_one({"id": renewal_id, "organization_id": org_id, "status": "sent"}, {"_id": 0})
    if not r:
        return {"ok": False, "error": "Only an issued renewal awaiting the customer can be resent."}
    try:
        delivered, link, to_email = await _send_renewal_email(org_id, r)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    await db.crm2_contracts.update_one({"id": renewal_id}, {"$set": {
        "renewal_email_delivered": delivered or r.get("renewal_email_delivered", False), "renewal_accept_link": link,
        "renewal_comms_status": "delivered" if (delivered or r.get("renewal_email_delivered")) else "approved_not_delivered",
        "updated_at": _now()}, "$push": {"approval_evidence": {"action": "resent", "by": user.get("email"),
                                                               "delivered": delivered, "at": _now()}}})
    if delivered:
        await resolve_action(org_id, f"cm:renewal-undelivered:{renewal_id}", "Email delivered on resend.")
    return {"ok": True, "email_delivered": delivered, "accept_link": link, "to": to_email}


async def record_outcome(renewal_id: str, user: dict, outcome: str, note: str = "") -> dict:
    org_id = user.get("organization_id")
    r = await db.crm2_contracts.find_one_and_update(
        {"id": renewal_id, "organization_id": org_id, "status": "sent"},
        {"$set": {"status": "declined", "renewal_comms_status": "declined", "updated_at": _now()},
         "$push": {"approval_evidence": {"action": "customer_declined", "by": user.get("email"), "note": note, "at": _now()}}},
        projection={"_id": 0, "id": 1})
    if not r:
        return {"ok": False, "error": "Only an issued renewal can be marked declined."}
    await resolve_action(org_id, f"cm:renewal-undelivered:{renewal_id}", "Customer declined.")
    return {"ok": True}


async def list_renewals(org_id: str) -> list:
    out = []
    async for r in db.crm2_contracts.find(
            {"organization_id": org_id, "previous_contract_id": {"$nin": [None, ""]},
             "status": {"$in": ["renewal_pending_approval", "renewal_sending", "renewal_approved", "sent", "active", "signed", "declined", "rejected"]}},
            {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "status": 1, "start_date": 1, "end_date": 1,
             "annual_value": 1, "renewal_uplift_percent": 1, "renewal_price_request": 1, "renewal_email_delivered": 1, "renewal_email_state": 1, "renewal_issued_via": 1, "renewal_issued_at": 1,
             "renewal_accept_link": 1, "renewal_sent_to": 1, "renewal_approved_by": 1, "approval_evidence": 1,
             "previous_contract_id": 1}).sort("updated_at", -1).limit(300):
        prev = await db.crm2_contracts.find_one({"id": r["previous_contract_id"]}, {"_id": 0, "end_date": 1}) or {}
        cs = comms_status(r, prev.get("end_date"))
        out.append({**r, "comms_status": cs, "comms_label": COMMS_LABELS[cs]})
    return out


async def dispatch_queued_renewals(org_id: str | None = None) -> dict:
    """Send queued renewal emails once live sending is switched on. Atomic claim → no double sends."""
    if not renewal_email_live():
        return {"live": False, "sent": 0, "failed": 0}
    sent = failed = 0
    q = {"status": "renewal_approved", "renewal_email_state": {"$in": ["awaiting_dispatch"]}, **({"organization_id": org_id} if org_id else {})}
    while True:
        r = await db.crm2_contracts.find_one_and_update(q, {"$set": {"renewal_email_state": "sending", "updated_at": _now()}},
                                                        projection={"_id": 0})
        if not r:
            break
        try:
            delivered, link, to_email = await _send_renewal_email(r["organization_id"], r)
        except Exception:  # noqa: BLE001
            delivered, link, to_email = False, r.get("renewal_accept_link"), r.get("renewal_sent_to")
        if delivered:
            await _record_issue(r, "email")
        await db.crm2_contracts.update_one({"id": r["id"]}, {"$set": {
            "renewal_email_state": "sent" if delivered else "failed", "renewal_email_delivered": delivered,
            "renewal_comms_status": "delivered" if delivered else "approved_not_delivered", "renewal_accept_link": link,
            "updated_at": _now()}, "$push": {"approval_evidence": {"action": "queued_email_dispatched", "delivered": delivered,
                                                                  "to": to_email, "at": _now()}}})
        sent, failed = sent + bool(delivered), failed + (not delivered)
    return {"live": True, "sent": sent, "failed": failed}


async def cancel_queued_renewal_email(renewal_id: str, user: dict, reason: str) -> dict:
    res = await db.crm2_contracts.update_one(
        {"id": renewal_id, "organization_id": user.get("organization_id"), "renewal_email_state": {"$in": ["awaiting_dispatch", "failed"]}},
        {"$set": {"renewal_email_state": "cancelled", "renewal_comms_status": "email_cancelled", "updated_at": _now()},
         "$push": {"approval_evidence": {"action": "customer_email_cancelled", "by": user.get("email"), "reason": reason, "at": _now()}}})
    return {"ok": bool(res.modified_count), **({} if res.modified_count else {"error": "There is no queued email to cancel."})}


async def _record_issue(r: dict, how: str, user: dict | None = None, evidence: str = "") -> None:
    """The single place a renewal becomes 'issued' (status sent) — email delivered or a recorded manual issue."""
    await db.crm2_contracts.update_one({"id": r["id"], "status": "renewal_approved"}, {"$set": {
        "status": "sent", "renewal_issued_at": _now(), "renewal_issued_via": how, "updated_at": _now()},
        "$push": {"approval_evidence": {"action": f"issued_{how}", "by": (user or {}).get("email"), "evidence": evidence, "at": _now()}}})
    if r.get("previous_contract_id"):
        await db.crm2_contracts.update_one({"id": r["previous_contract_id"]}, {"$set": {"auto_renewal_sent_at": _now(), "updated_at": _now()}})


async def mark_renewal_issued_manually(renewal_id: str, user: dict, evidence: str) -> dict:
    """Manager records that the approved renewal reached the customer another way (e.g. handed over, own email)."""
    r = await db.crm2_contracts.find_one({"id": renewal_id, "organization_id": user.get("organization_id"), "status": "renewal_approved"}, {"_id": 0})
    if not r:
        return {"ok": False, "error": "Only an approved renewal that has not been issued can be marked issued."}
    await _record_issue(r, "manual", user, evidence)
    await db.crm2_contracts.update_one({"id": renewal_id, "renewal_email_state": {"$in": ["awaiting_dispatch", "failed"]}},
                                       {"$set": {"renewal_email_state": "cancelled", "renewal_comms_status": "email_cancelled"}})
    return {"ok": True}
