"""
Iter 337 — Engineer → Gym Operations equipment transfer.

When an engineer has onboarded a gym's equipment into the Engineer App
(stored under the *engineer's* org, tagged with a ``customer_id``) and
that gym later signs up for the Operations portal (a separate org), the
engineer needs to hand the assets — plus their QR stickers and service
history — over to the gym's own Operations portal.

Design (approved):
  * Trigger: engineer-initiated push  OR  gym-initiated pull.
  * Consent: the *receiving* side always approves before anything moves
    (engineer-initiated → gym approves; gym-initiated → engineer approves).
  * What moves: the equipment records are *re-parented* (same ``id`` →
    physical QR stickers keep resolving), the QR value is carried over,
    and a denormalised service-history snapshot is embedded on each
    asset so the gym sees past visits. The engineer's own case/visit
    records are left intact (no billing corruption).
  * Engineer keeps access to the machines after the move via an
    ``engineer_managed_grant`` (the same mechanism as "My Gyms").
  * Idempotent: the executor only moves rows still under the source org,
    so a re-run is a no-op.

Only supports transfer when the gym already has an Operations org.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.svc.notifications import create_notification

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engineer · Equipment transfer (iter 337)"])


# ── helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _eng_org(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _gym_org(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _require_gym_admin(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager") or user.get("is_master_admin") or user.get("is_pulse_admin"):
        return
    raise HTTPException(403, "Owners and managers only")


async def _engineer_partner(user: dict) -> Optional[dict]:
    return await db.partner_engineers.find_one(
        {"$or": [{"user_id": user.get("id")}, {"email": user.get("email")}]},
        {"_id": 0, "id": 1, "business_name": 1, "full_name": 1},
    )


async def _resolve_org_by_email(email: str) -> Optional[dict]:
    """Find an Operations org via the email of one of its admin users."""
    email = (email or "").strip().lower()
    if not email:
        return None
    u = await db.users.find_one(
        {"email": email, "organization_id": {"$ne": None}},
        {"_id": 0, "organization_id": 1},
    )
    if not u:
        return None
    return await db.organizations.find_one(
        {"id": u["organization_id"]}, {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    )


async def _first_site(org_id: str) -> Optional[dict]:
    return await db.sites.find_one(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1},
    )


async def _customer_equipment_ids(eng_org: str, customer_id: str) -> list[str]:
    rows = await db.equipment.find(
        {"organization_id": eng_org, "customer_id": customer_id},
        {"_id": 0, "id": 1},
    ).to_list(2000)
    return [r["id"] for r in rows if r.get("id")]


async def _build_history_snapshot(eq_ids: list[str], source_org: str) -> dict[str, list]:
    """Denormalised per-asset visit history from the engineer's records."""
    if not eq_ids:
        return {}
    machine_rows = await db.svc_work_visit_machines.find(
        {"organization_id": source_org, "asset_id": {"$in": eq_ids}},
        {"_id": 0, "asset_id": 1, "case_id": 1, "serviced": 1, "cleaned": 1,
         "notes": 1, "created_at": 1, "updated_at": 1},
    ).to_list(5000)
    case_ids = list({m["case_id"] for m in machine_rows if m.get("case_id")})
    cases: dict[str, dict] = {}
    if case_ids:
        async for c in db.svc_cases.find(
            {"organization_id": source_org, "id": {"$in": case_ids}},
            {"_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1,
             "assigned_engineer_name": 1, "completed_at": 1, "updated_at": 1,
             "created_at": 1},
        ):
            cases[c["id"]] = c
    snap: dict[str, list] = defaultdict(list)
    for m in machine_rows:
        case = cases.get(m.get("case_id") or "", {})
        visit_date = (
            case.get("completed_at") or case.get("updated_at")
            or m.get("updated_at") or m.get("created_at")
        )
        snap[m["asset_id"]].append({
            "visit_date": visit_date,
            "case_reference": case.get("reference"),
            "case_title": case.get("title"),
            "engineer_name": case.get("assigned_engineer_name"),
            "serviced": bool(m.get("serviced")),
            "cleaned": bool(m.get("cleaned")),
            "notes": m.get("notes"),
        })
    for k in snap:
        snap[k].sort(key=lambda v: v["visit_date"] or "", reverse=True)
    return snap


async def _ensure_engineer_grant(transfer: dict, target_org: str) -> None:
    """Keep the engineer working on the machines after the move via a
    standard active managed-grant (same mechanism as My Gyms)."""
    now = _now()
    key: dict = {"organization_id": target_org}
    if transfer.get("partner_id"):
        key["partner_id"] = transfer["partner_id"]
    else:
        key["engineer_user_id"] = transfer.get("engineer_user_id")
    await db.engineer_managed_grants.update_one(
        key,
        {"$set": {"status": "active", "updated_at": now, "decided_at": now,
                  "scope": "lite_ops", "source": "equipment_transfer"},
         "$setOnInsert": {"id": _new_id(), "created_at": now,
                          "partner_id": transfer.get("partner_id"),
                          "engineer_user_id": transfer.get("engineer_user_id"),
                          "organization_id": target_org}},
        upsert=True,
    )


async def _notify_gym_admins(org_id: str, *, title: str, body: str, link: str) -> None:
    try:
        async for u in db.users.find(
            {"organization_id": org_id,
             "$or": [{"role": {"$in": ["owner", "manager"]}},
                     {"is_master_admin": True}, {"is_pulse_admin": True}]},
            {"_id": 0, "id": 1}).limit(20):
            await create_notification(
                user_id=u["id"], organization_id=org_id, kind="equipment_transfer",
                title=title, body=body, link=link, source_type="equipment_transfer")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[eq-transfer] gym notify failed: %s", exc)


async def _execute_transfer(transfer: dict, *, by_id: str, by_name: str) -> int:
    """Re-parent equipment + embed history + grant engineer access.
    Idempotent — only rows still under the source org are moved."""
    eq_ids = transfer.get("equipment_ids") or []
    source = transfer["source_org_id"]
    target = transfer["target_org_id"]
    site_id = transfer.get("target_site_id")
    snapshots = await _build_history_snapshot(eq_ids, source)
    now = _now()
    moved = 0
    for eid in eq_ids:
        eq = await db.equipment.find_one(
            {"id": eid, "organization_id": source},
            {"_id": 0, "id": 1, "qr_code": 1, "sticker_code": 1},
        )
        if not eq:
            continue  # already moved or gone — idempotent skip
        set_doc = {
            "organization_id": target,
            "site_id": site_id,
            "customer_id": None,
            "transferred_at": now,
            "transferred_from_org": source,
            "transferred_by": by_id,
            "source_customer_id": transfer.get("source_customer_id"),
            "transfer_id": transfer["id"],
            "updated_at": now,
            "qr_code": eq.get("qr_code") or eq.get("sticker_code"),
            "service_history_imported": snapshots.get(eid, [])[:200],
            "service_history_source": "engineer_transfer",
        }
        await db.equipment.update_one(
            {"id": eid, "organization_id": source}, {"$set": set_doc})
        moved += 1
    await _ensure_engineer_grant(transfer, target)
    await db.equipment_transfers.update_one(
        {"id": transfer["id"]},
        {"$set": {"status": "completed", "decided_at": now,
                  "decided_by_id": by_id, "decided_by_name": by_name,
                  "moved_count": moved, "updated_at": now}},
    )
    return moved


def _public(t: dict) -> dict:
    t.pop("_id", None)
    return t


async def _send_invite_email(transfer: dict) -> None:
    """Email the gym admin a signup link; the transfer auto-runs on signup."""
    try:
        from utils.email import send_email, PUBLIC_BASE_URL
        email = transfer["invite_email"]
        link = f"{PUBLIC_BASE_URL}/?invite_transfer=1&invite_email={quote(email)}"
        eng = transfer.get("engineer_name") or "Your engineer"
        company = transfer.get("engineer_company")
        who = f"{eng}{f' ({company})' if company else ''}"
        count = transfer.get("equipment_count", 0)
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#0f172a">
          <h2 style="margin:0 0 12px">Your equipment is ready to import</h2>
          <p>{who} has <strong>{count} machine(s)</strong> on file for you in Pulse Fitness, complete with QR codes and service history.</p>
          <p>Create your free Pulse Fitness Operations portal and these machines &mdash; plus their full history &mdash; will be imported automatically. Nothing changes on the equipment; your existing QR stickers keep working.</p>
          <p style="margin:24px 0">
            <a href="{link}" style="background:#f97316;color:#fff;padding:12px 22px;border-radius:9999px;text-decoration:none;font-weight:700">Set up your portal &amp; import equipment</a>
          </p>
          <p style="font-size:12px;color:#64748b">If you didn't expect this, you can ignore this email &mdash; nothing will be shared until you sign up.</p>
        </div>
        """
        await send_email(to=email, subject="Your gym equipment is ready to import into Pulse Fitness",
                         html=html, kind="equipment_transfer_invite")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[eq-transfer] invite email failed: %s", exc)


async def claim_invited_transfers_for_org(email: str, org_id: str, site_id: Optional[str] = None) -> int:
    """Called on gym signup — auto-runs any equipment transfer an engineer
    invited to this email. Signing up via the invite IS the consent."""
    email = (email or "").strip().lower()
    if not email or not org_id:
        return 0
    invited = await db.equipment_transfers.find(
        {"invite_email": email, "status": "invited"}, {"_id": 0}).to_list(50)
    if not invited:
        return 0
    org_doc = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    site = None
    if site_id:
        site = await db.sites.find_one({"id": site_id, "organization_id": org_id}, {"_id": 0, "id": 1, "name": 1})
    if not site:
        site = await _first_site(org_id)
    claimed = 0
    for t in invited:
        eq_ids = await _customer_equipment_ids(t["source_org_id"], t["source_customer_id"])
        now = _now()
        if not eq_ids:
            await db.equipment_transfers.update_one(
                {"id": t["id"]}, {"$set": {"status": "cancelled", "updated_at": now,
                                           "note": "no equipment at claim time"}})
            continue
        t.update({
            "target_org_id": org_id,
            "target_org_name": (org_doc or {}).get("name"),
            "target_site_id": (site or {}).get("id"),
            "target_site_name": (site or {}).get("name"),
            "equipment_ids": eq_ids,
            "equipment_count": len(eq_ids),
        })
        await db.equipment_transfers.update_one(
            {"id": t["id"]},
            {"$set": {"target_org_id": org_id, "target_org_name": (org_doc or {}).get("name"),
                      "target_site_id": (site or {}).get("id"),
                      "target_site_name": (site or {}).get("name"),
                      "equipment_ids": eq_ids, "equipment_count": len(eq_ids),
                      "updated_at": now}})
        moved = await _execute_transfer(t, by_id="invite-signup", by_name=email)
        claimed += 1
        if t.get("engineer_user_id"):
            await create_notification(
                user_id=t["engineer_user_id"], organization_id=t["source_org_id"],
                kind="equipment_transfer", title="Gym signed up — equipment transferred",
                body=f"{(org_doc or {}).get('name') or 'The gym'} created their Operations portal and {moved} machine(s) were imported automatically. You still have access via My Gyms.",
                link="/svc/engineer/my-gyms", source_type="equipment_transfer", source_id=t["id"])
    return claimed


# ── Engineer-side endpoints ──────────────────────────────────────────

@router.get("/svc/engineer/customers/{customer_id}/transfer-preview")
async def transfer_preview(customer_id: str, user=Depends(get_current_user)):
    eng_org = _eng_org(user)
    customer = await db.svc_engineer_customers.find_one(
        {"id": customer_id, "organization_id": eng_org},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "site_name": 1},
    )
    if not customer:
        raise HTTPException(404, "Customer not found")
    eq_ids = await _customer_equipment_ids(eng_org, customer_id)
    matched = await _resolve_org_by_email(customer.get("email")) if customer.get("email") else None
    if matched and matched["id"] == eng_org:
        matched = None  # never target our own org
    pending = await db.equipment_transfers.find_one(
        {"source_org_id": eng_org, "source_customer_id": customer_id,
         "status": "pending"}, {"_id": 0},
    )
    invited = await db.equipment_transfers.find_one(
        {"source_org_id": eng_org, "source_customer_id": customer_id,
         "status": "invited"}, {"_id": 0},
    )
    return {
        "customer": customer,
        "equipment_count": len(eq_ids),
        "matched_gym": matched,
        "pending_transfer": _public(pending) if pending else None,
        "invited_transfer": _public(invited) if invited else None,
    }


class EngineerTransferBody(BaseModel):
    target_org_id: Optional[str] = Field(default=None, max_length=64)
    target_admin_email: Optional[str] = Field(default=None, max_length=200)
    target_site_id: Optional[str] = Field(default=None, max_length=64)
    equipment_ids: Optional[list[str]] = Field(default=None, max_length=2000)


@router.post("/svc/engineer/customers/{customer_id}/transfer")
async def engineer_initiate_transfer(
    customer_id: str, body: EngineerTransferBody, user=Depends(get_current_user),
):
    eng_org = _eng_org(user)
    customer = await db.svc_engineer_customers.find_one(
        {"id": customer_id, "organization_id": eng_org},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    )
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Resolve the target gym Operations org.
    target = None
    if body.target_org_id:
        target = await db.organizations.find_one(
            {"id": body.target_org_id}, {"_id": 0, "id": 1, "name": 1})
    elif body.target_admin_email or customer.get("email"):
        target = await _resolve_org_by_email(body.target_admin_email or customer.get("email"))
    if not target:
        raise HTTPException(404, "No Operations org found for this gym. The gym must sign up for the Operations portal first.")
    if target["id"] == eng_org:
        raise HTTPException(400, "Target gym resolves to your own org")

    # Resolve equipment set.
    if body.equipment_ids:
        valid = await db.equipment.find(
            {"organization_id": eng_org, "customer_id": customer_id,
             "id": {"$in": body.equipment_ids}}, {"_id": 0, "id": 1}).to_list(2000)
        eq_ids = [r["id"] for r in valid]
    else:
        eq_ids = await _customer_equipment_ids(eng_org, customer_id)
    if not eq_ids:
        raise HTTPException(400, "No equipment to transfer for this customer")

    # Dedupe a live pending transfer for the same customer→org.
    existing = await db.equipment_transfers.find_one(
        {"source_org_id": eng_org, "source_customer_id": customer_id,
         "target_org_id": target["id"], "status": "pending"}, {"_id": 0},
    )
    if existing:
        raise HTTPException(409, "A transfer for this gym is already pending approval")

    site = None
    if body.target_site_id:
        site = await db.sites.find_one(
            {"id": body.target_site_id, "organization_id": target["id"]},
            {"_id": 0, "id": 1, "name": 1})
    if not site:
        site = await _first_site(target["id"])

    partner = await _engineer_partner(user)
    now = _now()
    transfer = {
        "id": _new_id(),
        "status": "pending",
        "awaiting": "gym",
        "initiated_by": "engineer",
        "source_org_id": eng_org,
        "source_customer_id": customer_id,
        "source_customer_name": customer.get("name"),
        "engineer_user_id": user.get("id"),
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "engineer_email": user.get("email") or "",
        "engineer_company": (partner or {}).get("business_name") or "",
        "partner_id": (partner or {}).get("id"),
        "target_org_id": target["id"],
        "target_org_name": target.get("name"),
        "target_site_id": (site or {}).get("id"),
        "target_site_name": (site or {}).get("name"),
        "equipment_ids": eq_ids,
        "equipment_count": len(eq_ids),
        "moved_count": 0,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "decided_by_id": None,
        "decided_by_name": None,
    }
    await db.equipment_transfers.insert_one(transfer)
    await _notify_gym_admins(
        target["id"],
        title="Equipment ready to import",
        body=f"{transfer['engineer_name']} wants to transfer {len(eq_ids)} machine(s) into your Operations portal.",
        link="/dashboard/equipment-transfers",
    )
    return {"ok": True, "transfer": _public(transfer)}


class TransferInviteBody(BaseModel):
    target_admin_email: str = Field(max_length=200)


@router.post("/svc/engineer/customers/{customer_id}/transfer/invite")
async def engineer_invite_transfer(
    customer_id: str, body: TransferInviteBody, user=Depends(get_current_user),
):
    """Gym not on Pulse Fitness yet — email them a signup link. On signup the
    equipment auto-transfers (signing up via the invite = consent)."""
    eng_org = _eng_org(user)
    customer = await db.svc_engineer_customers.find_one(
        {"id": customer_id, "organization_id": eng_org},
        {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not customer:
        raise HTTPException(404, "Customer not found")
    email = (body.target_admin_email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid gym admin email is required")

    existing_org = await _resolve_org_by_email(email)
    if existing_org and existing_org["id"] != eng_org:
        raise HTTPException(409, "This gym already has an Operations portal — use 'Send transfer for approval' instead.")

    eq_ids = await _customer_equipment_ids(eng_org, customer_id)
    if not eq_ids:
        raise HTTPException(400, "No equipment to transfer for this customer")

    existing_inv = await db.equipment_transfers.find_one(
        {"source_org_id": eng_org, "source_customer_id": customer_id,
         "invite_email": email, "status": "invited"}, {"_id": 0, "id": 1})
    if existing_inv:
        raise HTTPException(409, "You've already invited this gym")

    partner = await _engineer_partner(user)
    now = _now()
    transfer = {
        "id": _new_id(),
        "status": "invited",
        "awaiting": "gym_signup",
        "initiated_by": "engineer",
        "invite_email": email,
        "source_org_id": eng_org,
        "source_customer_id": customer_id,
        "source_customer_name": customer.get("name"),
        "engineer_user_id": user.get("id"),
        "engineer_name": user.get("full_name") or user.get("email") or "",
        "engineer_email": user.get("email") or "",
        "engineer_company": (partner or {}).get("business_name") or "",
        "partner_id": (partner or {}).get("id"),
        "target_org_id": None,
        "target_org_name": None,
        "target_site_id": None,
        "target_site_name": None,
        "equipment_ids": eq_ids,
        "equipment_count": len(eq_ids),
        "moved_count": 0,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "decided_by_id": None,
        "decided_by_name": None,
    }
    await db.equipment_transfers.insert_one(dict(transfer))
    await _send_invite_email(transfer)
    return {"ok": True, "transfer": _public(transfer)}
async def list_engineer_transfers(status: str = "all", user=Depends(get_current_user)):
    eng_org = _eng_org(user)
    q: dict = {"source_org_id": eng_org}
    if status and status != "all":
        q["status"] = status
    rows = await db.equipment_transfers.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"transfers": rows}


@router.post("/svc/engineer/transfers/{transfer_id}/cancel")
async def cancel_transfer(transfer_id: str, user=Depends(get_current_user)):
    eng_org = _eng_org(user)
    t = await db.equipment_transfers.find_one(
        {"id": transfer_id, "source_org_id": eng_org}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t["status"] != "pending":
        raise HTTPException(409, f"Transfer already {t['status']}")
    await db.equipment_transfers.update_one(
        {"id": transfer_id}, {"$set": {"status": "cancelled", "updated_at": _now()}})
    return {"ok": True, "status": "cancelled"}


@router.post("/svc/engineer/transfers/{transfer_id}/approve")
async def engineer_approve_pull(transfer_id: str, user=Depends(get_current_user)):
    """Engineer approves a GYM-initiated pull request → executes."""
    eng_org = _eng_org(user)
    t = await db.equipment_transfers.find_one(
        {"id": transfer_id, "source_org_id": eng_org}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t["status"] != "pending" or t.get("awaiting") != "engineer":
        raise HTTPException(409, "This transfer is not awaiting your approval")
    moved = await _execute_transfer(
        t, by_id=user.get("id"), by_name=user.get("full_name") or user.get("email") or "")
    await _notify_gym_admins(
        t["target_org_id"], title="Equipment imported",
        body=f"{moved} machine(s) from {t.get('engineer_name')} are now in your Operations portal.",
        link="/dashboard/equipment")
    return {"ok": True, "status": "completed", "moved_count": moved}


# ── Gym-side (Operations) endpoints ──────────────────────────────────

@router.get("/operations/equipment-transfers")
async def gym_list_transfers(status: str = "pending", user=Depends(get_current_user)):
    org = _gym_org(user)
    q: dict = {"target_org_id": org}
    if status and status != "all":
        q["status"] = status
    rows = await db.equipment_transfers.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"transfers": rows}


@router.post("/operations/equipment-transfers/{transfer_id}/approve")
async def gym_approve_transfer(transfer_id: str, user=Depends(get_current_user)):
    _require_gym_admin(user)
    org = _gym_org(user)
    t = await db.equipment_transfers.find_one(
        {"id": transfer_id, "target_org_id": org}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t["status"] != "pending" or t.get("awaiting") != "gym":
        raise HTTPException(409, "This transfer is not awaiting your approval")
    moved = await _execute_transfer(
        t, by_id=user.get("id"), by_name=user.get("full_name") or user.get("email") or "")
    if t.get("engineer_user_id"):
        await create_notification(
            user_id=t["engineer_user_id"], organization_id=t["source_org_id"],
            kind="equipment_transfer", title="Transfer approved",
            body=f"{t.get('target_org_name') or 'The gym'} imported {moved} machine(s). You still have access via My Gyms.",
            link="/svc/engineer/my-gyms", source_type="equipment_transfer",
            source_id=transfer_id)
    return {"ok": True, "status": "completed", "moved_count": moved}


@router.post("/operations/equipment-transfers/{transfer_id}/decline")
async def gym_decline_transfer(transfer_id: str, user=Depends(get_current_user)):
    _require_gym_admin(user)
    org = _gym_org(user)
    t = await db.equipment_transfers.find_one(
        {"id": transfer_id, "target_org_id": org}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t["status"] != "pending":
        raise HTTPException(409, f"Transfer already {t['status']}")
    await db.equipment_transfers.update_one(
        {"id": transfer_id},
        {"$set": {"status": "declined", "decided_at": _now(),
                  "decided_by_id": user.get("id"),
                  "decided_by_name": user.get("full_name") or user.get("email") or "",
                  "updated_at": _now()}})
    if t.get("engineer_user_id"):
        await create_notification(
            user_id=t["engineer_user_id"], organization_id=t["source_org_id"],
            kind="equipment_transfer", title="Transfer declined",
            body=f"{t.get('target_org_name') or 'The gym'} declined the equipment transfer.",
            link="/svc/engineer/my-gyms", source_type="equipment_transfer",
            source_id=transfer_id)
    return {"ok": True, "status": "declined"}


@router.get("/operations/equipment-transfers/available")
async def gym_available_imports(user=Depends(get_current_user)):
    """Gym discovers engineer-held equipment matching their admin email."""
    org = _gym_org(user)
    email = (user.get("email") or "").strip().lower()
    if not email:
        return {"available": []}
    customers = await db.svc_engineer_customers.find(
        {"email": email}, {"_id": 0, "id": 1, "name": 1, "organization_id": 1},
    ).limit(50).to_list(50)
    out = []
    for c in customers:
        if c.get("organization_id") == org:
            continue
        count = await db.equipment.count_documents(
            {"organization_id": c["organization_id"], "customer_id": c["id"]})
        if count <= 0:
            continue
        eng = await db.organizations.find_one(
            {"id": c["organization_id"]}, {"_id": 0, "name": 1})
        out.append({
            "source_org_id": c["organization_id"],
            "source_customer_id": c["id"],
            "engineer_org_name": (eng or {}).get("name") or "Your engineer",
            "equipment_count": count,
        })
    return {"available": out}


class GymPullBody(BaseModel):
    source_org_id: str = Field(max_length=64)
    source_customer_id: str = Field(max_length=64)
    target_site_id: Optional[str] = Field(default=None, max_length=64)


@router.post("/operations/equipment-transfers/request")
async def gym_request_pull(body: GymPullBody, user=Depends(get_current_user)):
    """Gym-initiated pull → creates a request the engineer approves."""
    _require_gym_admin(user)
    org = _gym_org(user)
    if body.source_org_id == org:
        raise HTTPException(400, "Invalid source org")
    customer = await db.svc_engineer_customers.find_one(
        {"id": body.source_customer_id, "organization_id": body.source_org_id},
        {"_id": 0, "id": 1, "name": 1})
    if not customer:
        raise HTTPException(404, "Engineer customer record not found")
    eq_ids = await _customer_equipment_ids(body.source_org_id, body.source_customer_id)
    if not eq_ids:
        raise HTTPException(400, "No equipment available to import")
    existing = await db.equipment_transfers.find_one(
        {"source_org_id": body.source_org_id, "source_customer_id": body.source_customer_id,
         "target_org_id": org, "status": "pending"}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(409, "A request for this engineer is already pending")

    site = None
    if body.target_site_id:
        site = await db.sites.find_one(
            {"id": body.target_site_id, "organization_id": org}, {"_id": 0, "id": 1, "name": 1})
    if not site:
        site = await _first_site(org)
    org_doc = await db.organizations.find_one({"id": org}, {"_id": 0, "name": 1})
    eng_admin = await db.users.find_one(
        {"organization_id": body.source_org_id}, {"_id": 0, "id": 1})
    now = _now()
    transfer = {
        "id": _new_id(),
        "status": "pending",
        "awaiting": "engineer",
        "initiated_by": "gym",
        "source_org_id": body.source_org_id,
        "source_customer_id": body.source_customer_id,
        "source_customer_name": customer.get("name"),
        "engineer_user_id": (eng_admin or {}).get("id"),
        "engineer_name": "",
        "engineer_company": "",
        "partner_id": None,
        "target_org_id": org,
        "target_org_name": (org_doc or {}).get("name"),
        "target_site_id": (site or {}).get("id"),
        "target_site_name": (site or {}).get("name"),
        "equipment_ids": eq_ids,
        "equipment_count": len(eq_ids),
        "moved_count": 0,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
        "decided_by_id": None,
        "decided_by_name": None,
    }
    await db.equipment_transfers.insert_one(transfer)
    if (eng_admin or {}).get("id"):
        await create_notification(
            user_id=eng_admin["id"], organization_id=body.source_org_id,
            kind="equipment_transfer", title="Gym requested your equipment records",
            body=f"{(org_doc or {}).get('name') or 'A gym'} wants to import {len(eq_ids)} machine(s) you hold. Approve to transfer.",
            link="/svc/engineer/my-gyms", source_type="equipment_transfer",
            source_id=transfer["id"])
    return {"ok": True, "transfer": _public(transfer)}


async def ensure_indexes() -> None:
    try:
        await db.equipment_transfers.create_index([("source_org_id", 1), ("status", 1)])
        await db.equipment_transfers.create_index([("target_org_id", 1), ("status", 1)])
    except Exception:  # noqa: BLE001
        pass


__all__ = ["router", "ensure_indexes"]
