"""Approval-first renewals.

``prepare_renewals`` identifies genuine upcoming renewals, verifies the data
and prepares ONE renewal draft per contract (status ``renewal_pending_approval``)
plus one Action Centre item. Nothing is emailed. ``approve_and_send_renewal``
is the explicit coordinator step that sends it to the customer.
"""
from __future__ import annotations

import base64
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
            "sage_reference", "sicon_sync_status", "sage_sync_status", "finance_sync_status")},
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


async def approve_and_send_renewal(renewal_id: str, user: dict, uplift_percent=None) -> dict:
    """Coordinator approval: optionally set the increase, then email the
    customer the accept link. Only valid once per draft."""
    org_id = user.get("organization_id")
    of = {"organization_id": org_id}
    r = await db.crm2_contracts.find_one_and_update(
        {"id": renewal_id, **of, "status": "renewal_pending_approval"},
        {"$set": {"status": "renewal_sending", "updated_at": _now()}}, projection={"_id": 0})
    if not r:
        return {"ok": False, "error": "This renewal is not awaiting approval (already sent or not found)."}
    prev = await db.crm2_contracts.find_one({"id": r.get("previous_contract_id"), **of}, {"_id": 0}) or {}
    try:
        if uplift_percent is not None:
            pct = round(float(uplift_percent), 2)
            base = float(prev.get("annual_value") or r.get("annual_value") or 0)
            new_val = round(base * (1 + pct / 100), 2)
            r.update({"annual_value": new_val, "total_value": new_val, "renewal_uplift_percent": pct,
                      "renewal_uplift_status": "approved", "renewal_uplift_basis": f"Approved by {user.get('email')}"})
        elif r.get("renewal_uplift_status") != "approved":
            r.update({"renewal_uplift_status": "approved", "renewal_uplift_basis": f"Approved by {user.get('email')} at {r.get('renewal_uplift_percent', 0)}%"})
        to_email = await _customer_email(org_id, r)
        if not to_email:
            raise ValueError("No customer contact email on this contract.")
        from routes.crm_contract_send import _build_catalog, _ensure_accept_token
        from utils.crm_contract_pdf import build_contract_pdf
        token = await _ensure_accept_token(renewal_id, of)
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
        pdf = b""
        try:
            from utils.document_branding import resolve_company_if_configured
            company = await resolve_company_if_configured(db, {"id": org_id, "name": org.get("name")})
            pdf = build_contract_pdf(r, org, _build_catalog(), company=company)
        except Exception:
            pdf = b""
        from utils.brand_urls import app_url_for_org
        link = f"{app_url_for_org(org)}/contracts/accept/{token}"
        emailed = False
        try:
            from utils.email import send_email
            emailed = bool(await send_email(
                to=to_email, subject=f"Your maintenance renewal is ready — {r['contract_number']}",
                html=(f"<p>Hello,</p><p>Your maintenance agreement is due for renewal. The new term runs "
                      f"{r.get('start_date')} to {r.get('end_date')} at <strong>£{float(r['annual_value']):,.2f} per year</strong>.</p>"
                      f"<p>Review and accept online: <a href=\"{link}\">{link}</a></p>"
                      f"<p>Kind regards,<br/>{org.get('name') or 'Pulse Fitness'}</p>"),
                attachments=[{"filename": f"renewal_{r['contract_number']}.pdf",
                              "content": base64.b64encode(pdf).decode("ascii")}] if pdf else None,
                organization_id=org_id, kind="crm_contract_renewal"))
        except Exception:
            emailed = False
        await db.crm2_contracts.update_one({"id": renewal_id}, {"$set": {
            "status": "sent", "annual_value": r["annual_value"], "total_value": r.get("total_value", r["annual_value"]),
            "renewal_uplift_percent": r.get("renewal_uplift_percent"), "renewal_uplift_status": "approved",
            "renewal_uplift_basis": r.get("renewal_uplift_basis"), "renewal_approved_by": user.get("email"),
            "renewal_approved_at": _now(), "renewal_sent_to": to_email, "renewal_email_delivered": emailed,
            "updated_at": _now()}})
        await db.crm2_contracts.update_one({"id": prev.get("id")}, {"$set": {"auto_renewal_sent_at": _now(), "updated_at": _now()}})
        await resolve_action(org_id, f"cm:renewal-approval:{renewal_id}", f"Approved and sent by {user.get('email')}.")
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org_id, "type": "contract_renewal",
            "contract_id": prev.get("id"), "company_id": r.get("company_id"),
            "subject": f"Renewal sent: {r['contract_number']}",
            "body": f"Approved by {user.get('email')} and sent to {to_email}" + ("" if emailed else " (email not delivered — share the link manually)"),
            "owner_id": user.get("id"), "owner_name": user.get("full_name", ""), "created_at": _now()})
        return {"ok": True, "renewal_contract_id": renewal_id, "to": to_email, "email_delivered": emailed,
                "accept_link": link, "annual_value": r["annual_value"]}
    except Exception as e:
        await db.crm2_contracts.update_one({"id": renewal_id, "status": "renewal_sending"},
                                           {"$set": {"status": "renewal_pending_approval"}})
        return {"ok": False, "error": str(e)}
