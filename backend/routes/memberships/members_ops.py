"""Sprint C — Operator Multipliers.

Three operator-side features that compound across the member directory:

  1. Saved views ────────────────────────────────────────────────
     Per-operator filter presets so the front desk doesn't rebuild
     "Trialists ending in 7 days" by hand every morning. Server-side
     presets are hardcoded (always available); custom views are stored
     per-user in `memberships_member_views` and can be renamed/deleted.

  2. Bulk actions ───────────────────────────────────────────────
     Fan-out dispatcher against a list of `member_ids`. Actions:
       • invite_portal  — re-uses the single-member magic-link flow
       • send_reminder  — short email to each member (templated)
       • add_tag        — bulk-tag for future filtering
     Returns per-member ok/error so the UI can show "Invited 18 of 20,
     2 skipped (no email on file)".

  3. Activity timeline ──────────────────────────────────────────
     Merges bookings + payments + invoices + portal-invite events +
     membership audit-log entries into one reverse-chronological feed.
     Powers the new "Activity" tab on the member edit drawer.

Extracted into a separate submodule (not tacked onto members.py) so the
Sprint C surface area stays reviewable and can be deleted/replaced
wholesale later if we ship a heavier analytics engine.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from utils.security_plus import safe_regex

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module
from utils.security import sanitise_string

from routes.memberships.helpers import (
    _load_member,
    _now_iso,
    _require_operator_org,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships"])


# ═════════════════════════════════════════════════════════════════
# 1. Saved views (presets + per-user custom)
# ═════════════════════════════════════════════════════════════════

# Built-in presets exposed to every operator. The `filter` key is a
# small declarative object the list endpoint understands. Keep these
# light — operators compose richer queries via custom views.
PRESET_VIEWS = [
    {
        "id": "preset:trialists_7d",
        "name": "Trialists ending in 7 days",
        "description": "Members on a trial plan whose trial ends within a week.",
        "filter": {"preset": "trialists_7d"},
        "is_preset": True,
        "icon": "clock",
    },
    {
        "id": "preset:no_shows_14d",
        "name": "No-shows (last 14 days)",
        "description": "Members who missed 2+ classes in the last two weeks.",
        "filter": {"preset": "no_shows_14d"},
        "is_preset": True,
        "icon": "alert",
    },
    {
        "id": "preset:uninvited",
        "name": "Not yet on the portal",
        "description": "Members who haven't been sent a portal invite.",
        "filter": {"preset": "uninvited"},
        "is_preset": True,
        "icon": "mail",
    },
    {
        "id": "preset:new_this_week",
        "name": "New this week",
        "description": "Members added in the last 7 days.",
        "filter": {"preset": "new_this_week"},
        "is_preset": True,
        "icon": "sparkles",
    },
]


@router.get(
    "/memberships/saved-views",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_saved_views(user: dict = Depends(get_current_user)):
    """Return built-in presets + this user's custom saved views."""
    org_id = await _require_operator_org(user)
    custom = await db.memberships_member_views.find(
        {"organization_id": org_id, "user_id": user.get("id")},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return {"presets": PRESET_VIEWS, "custom": custom}


@router.post(
    "/memberships/saved-views",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_saved_view(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Create a custom saved view. `filter` is an opaque JSON blob the
    frontend round-trips back to `GET /memberships/members?<params>`."""
    org_id = await _require_operator_org(user)
    name = sanitise_string((body.get("name") or "").strip())[:80]
    if not name:
        raise HTTPException(400, "Name is required")
    raw_filter = body.get("filter")
    if not isinstance(raw_filter, dict):
        raise HTTPException(400, "Filter must be an object")
    # Whitelist keys so we don't persist arbitrary payloads.
    allowed = {"q", "preset", "status", "tag", "has_plan"}
    flt = {k: v for k, v in raw_filter.items() if k in allowed and v not in (None, "")}
    view = {
        "id": _uuid(),
        "organization_id": org_id,
        "user_id": user.get("id"),
        "name": name,
        "filter": flt,
        "is_preset": False,
        "created_at": _now_iso(),
    }
    await db.memberships_member_views.insert_one(view)
    view.pop("_id", None)
    return {"view": view}


@router.delete(
    "/memberships/saved-views/{view_id}",
    dependencies=[Depends(require_module("memberships"))],
)
async def delete_saved_view(view_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    if view_id.startswith("preset:"):
        raise HTTPException(400, "Built-in views can't be deleted")
    res = await db.memberships_member_views.delete_one(
        {"id": view_id, "organization_id": org_id, "user_id": user.get("id")},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "View not found")
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════
# 2. Member list with preset filters
# ═════════════════════════════════════════════════════════════════

async def _apply_preset_filter(org_id: str, preset: str) -> list[str] | None:
    """Return a list of member_ids matching the preset, or None if the
    preset doesn't need an ID-list restriction. Returning [] means
    'match nothing' — caller should short-circuit."""
    now = datetime.now(timezone.utc)

    if preset == "trialists_7d":
        cutoff = (now + timedelta(days=7)).isoformat()
        rows = await db.member_memberships.find(
            {
                "organization_id": org_id,
                "status": "active",
                "end_date": {"$lte": cutoff, "$gte": now.isoformat()},
            },
            {"_id": 0, "member_id": 1},
        ).to_list(500)
        return [r["member_id"] for r in rows if r.get("member_id")]

    if preset == "no_shows_14d":
        since = (now - timedelta(days=14)).isoformat()
        pipeline = [
            {"$match": {"organization_id": org_id, "status": "no_show", "booked_at": {"$gte": since}}},
            {"$group": {"_id": "$member_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gte": 2}}},
        ]
        try:
            rows = await db.bookings.aggregate(pipeline).to_list(500)
            return [r["_id"] for r in rows if r.get("_id")]
        except Exception:
            return []

    if preset == "uninvited":
        rows = await db.members.find(
            {
                "organization_id": org_id,
                "portal_invited_at": {"$in": [None, ""]},
                "email": {"$nin": [None, ""]},
            },
            {"_id": 0, "id": 1},
        ).to_list(500)
        return [r["id"] for r in rows]

    if preset == "new_this_week":
        since = (now - timedelta(days=7)).isoformat()
        rows = await db.members.find(
            {"organization_id": org_id, "created_at": {"$gte": since}},
            {"_id": 0, "id": 1},
        ).to_list(500)
        return [r["id"] for r in rows]

    return None  # unknown preset — treat as no-op


@router.get(
    "/memberships/members-filtered",
    dependencies=[Depends(require_module("memberships"))],
)
async def members_list_filtered(
    q: str | None = None,
    preset: str | None = Query(None),
    status_f: str | None = Query(None, alias="status"),
    tag: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Operator list with Sprint C preset + tag filters applied.

    Mirrors the core `/memberships/members` shape so the frontend can
    swap endpoints when a saved view is active without re-rendering
    the row renderer. Separate path so we don't alter the existing
    endpoint's public contract (defensive: the core endpoint is hit
    from several places including the Unified AI assistant).
    """
    org_id = await _require_operator_org(user)
    query: dict = {"organization_id": org_id}
    if status_f:
        query["status"] = status_f
    if tag:
        query["tags"] = tag
    if q:
        ql = q.lower()
        query["$or"] = [
            {"email": safe_regex(ql)},
            {"first_name": safe_regex(ql)},
            {"last_name": safe_regex(ql)},
            {"phone": safe_regex(ql)},
        ]

    if preset:
        ids = await _apply_preset_filter(org_id, preset)
        if ids is None:
            pass  # unknown preset — ignore
        elif not ids:
            return {"members": [], "preset": preset, "count": 0}
        else:
            query["id"] = {"$in": ids}

    rows = await db.members.find(query, {"_id": 0, "password": 0})\
        .sort("created_at", -1).limit(500).to_list(500)

    # Decorate with active membership (same shape as core endpoint).
    # Iter 216h200 — include pending_payment so the column matches the
    # main /memberships/members endpoint. Prefer active > frozen >
    # pending_payment if multiple rows exist.
    for r in rows:
        mm = None
        for st in ("active", "frozen", "pending_payment"):
            mm = await db.member_memberships.find_one(
                {"member_id": r["id"], "status": st},
                {"_id": 0},
            )
            if mm:
                break
        if mm:
            plan = await db.membership_plans.find_one(
                {"id": mm["plan_id"]},
                {"_id": 0, "name": 1, "kind": 1, "colour": 1},
            )
            r["active_membership"] = {**mm, "plan": plan}
    return {"members": rows, "preset": preset, "count": len(rows)}


# ═════════════════════════════════════════════════════════════════
# 3. Bulk actions
# ═════════════════════════════════════════════════════════════════

_BULK_MAX = 200


async def _bulk_invite_portal(org_id: str, member_ids: list[str], user: dict):
    """Re-invoke the single-member invite logic per id."""
    from routes.memberships.members import invite_member_portal

    results = []
    for mid in member_ids:
        try:
            out = await invite_member_portal(mid, body={}, user=user)
            results.append({"member_id": mid, "ok": True, "email_sent": bool(out.get("email_sent"))})
        except HTTPException as e:
            results.append({"member_id": mid, "ok": False, "error": e.detail})
        except Exception as e:
            logger.exception("bulk invite failed for %s", mid)
            results.append({"member_id": mid, "ok": False, "error": str(e)[:140]})
    return results


async def _bulk_send_reminder(
    org_id: str, member_ids: list[str], user: dict, payload: dict
):
    """Send a short operator-authored email to each member. Subject and
    body come from payload; both are sanitised + size-capped."""
    from utils.email import send_email

    subject = sanitise_string((payload.get("subject") or "").strip())[:120]
    message = sanitise_string((payload.get("message") or "").strip())[:2000]
    if not subject or not message:
        raise HTTPException(400, "Subject and message are required")

    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "name": 1, "primary_color": 1},
    ) or {}
    brand_name = org.get("name") or "Your studio"
    primary = org.get("primary_color") or "#19CDFF"

    results = []
    # Stamp a single audit entry so the activity timeline can show it.
    batch_id = _uuid()
    for mid in member_ids:
        m = await db.members.find_one(
            {"id": mid, "organization_id": org_id},
            {"_id": 0, "email": 1, "first_name": 1},
        )
        if not m:
            results.append({"member_id": mid, "ok": False, "error": "not found"})
            continue
        if not m.get("email"):
            results.append({"member_id": mid, "ok": False, "error": "no email on file"})
            continue
        first = sanitise_string(m.get("first_name") or "there")
        body_lines = message.replace("\n", "<br>")
        html = (
            f"<div style='font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;color:#0A0C10'>"
            f"<div style='background:{primary};padding:22px 26px;border-radius:12px 12px 0 0'>"
            f"<h1 style='margin:0;font-size:22px;color:#0A0C10'>{brand_name}</h1></div>"
            f"<div style='padding:24px;background:#0A0C10;color:#fff;border-radius:0 0 12px 12px'>"
            f"<p>Hi {first},</p>"
            f"<p>{body_lines}</p>"
            f"<p style='margin-top:28px;opacity:0.6;font-size:12px'>— The {brand_name} team</p>"
            f"</div></div>"
        )
        try:
            sent = await send_email(m["email"], subject, html)
            results.append({"member_id": mid, "ok": True, "email_sent": bool(sent)})
            # Log event for activity timeline
            await db.memberships_member_events.insert_one({
                "id": _uuid(),
                "organization_id": org_id,
                "member_id": mid,
                "kind": "reminder_sent",
                "actor_id": user.get("id"),
                "actor_email": user.get("email"),
                "batch_id": batch_id,
                "subject": subject,
                "at": _now_iso(),
            })
        except Exception as e:
            logger.exception("reminder send failed for %s", mid)
            results.append({"member_id": mid, "ok": False, "error": str(e)[:140]})
    return results


async def _bulk_add_tag(org_id: str, member_ids: list[str], user: dict, payload: dict):
    tag = sanitise_string((payload.get("tag") or "").strip())[:40]
    if not tag:
        raise HTTPException(400, "Tag is required")
    results = []
    for mid in member_ids:
        try:
            res = await db.members.update_one(
                {"id": mid, "organization_id": org_id},
                {"$addToSet": {"tags": tag}, "$set": {"updated_at": _now_iso()}},
            )
            if res.matched_count == 0:
                results.append({"member_id": mid, "ok": False, "error": "not found"})
                continue
            await db.memberships_member_events.insert_one({
                "id": _uuid(),
                "organization_id": org_id,
                "member_id": mid,
                "kind": "tag_added",
                "actor_id": user.get("id"),
                "tag": tag,
                "at": _now_iso(),
            })
            results.append({"member_id": mid, "ok": True})
        except Exception as e:
            logger.exception("add tag failed for %s", mid)
            results.append({"member_id": mid, "ok": False, "error": str(e)[:140]})
    return results


@router.post(
    "/memberships/members/bulk-action",
    dependencies=[Depends(require_module("memberships"))],
)
async def members_bulk_action(
    body: dict = Body(...),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """Fan-out dispatcher. Body:
      { "action": "invite_portal"|"send_reminder"|"add_tag",
        "member_ids": [...], "payload": {...} }
    """
    # Iter 220be (F-10) — Centralised bulk-action guard. Enforces the
    # 200-row cap + de-dupe + per-row audit. Cross-tenant ids are
    # silently dropped via `filter_same_tenant_ids` before fan-out so
    # an attacker mixing other-tenant IDs into the payload only sees
    # their own tenant's results — no enumeration via error messages.
    from utils.bulk_action import (
        validate_bulk_ids,
        filter_same_tenant_ids,
        record_bulk_action,
    )

    org_id = await _require_operator_org(user)
    action = (body.get("action") or "").strip().lower()
    member_ids = validate_bulk_ids(
        body.get("member_ids"),
        max_rows=_BULK_MAX,
        field_label="member_ids",
    )
    payload = body.get("payload") or {}

    # Drop any IDs that don't actually belong to this org.
    member_ids = await filter_same_tenant_ids(
        member_ids, collection="members", org_id=org_id,
    )
    if not member_ids:
        raise HTTPException(404, "No members match the supplied ids in this organisation")

    if action == "invite_portal":
        results = await _bulk_invite_portal(org_id, member_ids, user)
    elif action == "send_reminder":
        results = await _bulk_send_reminder(org_id, member_ids, user, payload)
    elif action == "add_tag":
        results = await _bulk_add_tag(org_id, member_ids, user, payload)
    else:
        raise HTTPException(400, f"Unknown action: {action}")

    succeeded = sum(1 for r in results if r.get("ok"))
    failed = len(results) - succeeded

    # Per-row audit: one row per member id so the master-admin audit
    # dashboard can replay exactly who was affected.
    succ_ids = [r.get("member_id") for r in results if r.get("ok") and r.get("member_id")]
    fail_ids = [r.get("member_id") for r in results if not r.get("ok") and r.get("member_id")]
    await record_bulk_action(
        name=f"memberships.bulk.{action}",
        actor=user, org_id=org_id, ids=member_ids,
        succeeded_ids=succ_ids, failed_ids=fail_ids, request=request,
    )
    return {
        "ok": True,
        "action": action,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


# ═════════════════════════════════════════════════════════════════
# 4. Activity timeline
# ═════════════════════════════════════════════════════════════════

@router.get(
    "/memberships/members/{member_id}/activity",
    dependencies=[Depends(require_module("memberships"))],
)
async def member_activity_timeline(
    member_id: str,
    user: dict = Depends(get_current_user),
):
    """Unified reverse-chronological feed for the Activity drawer tab.

    Sources:
      • Bookings            → class attended / booked / no-showed
      • Payments            → money received
      • Invoices            → invoice issued / paid / overdue
      • Member events log   → portal invites, reminders, bulk tag ops
      • Membership changes  → plan assigned / frozen / cancelled
    """
    org_id = await _require_operator_org(user)
    m = await _load_member(member_id, org_id)

    events: list[dict] = []

    # Bookings (last 100) — ordered by booked_at
    bookings = await db.bookings.find(
        {"member_id": member_id},
        {"_id": 0},
    ).sort("booked_at", -1).limit(100).to_list(100)
    for b in bookings:
        occ = await db.class_occurrences.find_one(
            {"id": b.get("occurrence_id")},
            {"_id": 0, "name": 1, "starts_at": 1},
        )
        status = (b.get("status") or "booked").lower()
        title = "Booked a class"
        if status == "attended":
            title = "Attended a class"
        elif status == "no_show":
            title = "No-showed"
        elif status == "cancelled":
            title = "Cancelled booking"
        events.append({
            "id": f"booking:{b.get('id')}",
            "kind": "booking",
            "status": status,
            "title": title,
            "subtitle": (occ or {}).get("name"),
            "at": b.get("attended_at") or b.get("cancelled_at") or b.get("booked_at"),
            "class_at": (occ or {}).get("starts_at"),
        })

    # Payments
    payments = await db.payments.find(
        {"member_id": member_id, "organization_id": org_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(50).to_list(50)
    for p in payments:
        events.append({
            "id": f"payment:{p.get('id')}",
            "kind": "payment",
            "status": (p.get("status") or "").lower(),
            "title": "Payment " + ((p.get("status") or "received").lower()),
            "subtitle": p.get("description") or p.get("method"),
            "amount_pence": p.get("amount_pence"),
            "at": p.get("paid_at") or p.get("created_at"),
        })

    # Invoices
    invoices = await db.invoices.find(
        {"member_id": member_id, "organization_id": org_id},
        {"_id": 0},
    ).sort("issued_at", -1).limit(50).to_list(50)
    for inv in invoices:
        events.append({
            "id": f"invoice:{inv.get('id')}",
            "kind": "invoice",
            "status": (inv.get("status") or "").lower(),
            "title": "Invoice " + ((inv.get("status") or "issued").lower()),
            "subtitle": inv.get("description") or inv.get("reference"),
            "amount_pence": inv.get("amount_pence"),
            "at": inv.get("issued_at") or inv.get("created_at"),
        })

    # Custom event log (portal invites, reminders, tag ops)
    logs = await db.memberships_member_events.find(
        {"member_id": member_id, "organization_id": org_id},
        {"_id": 0},
    ).sort("at", -1).limit(100).to_list(100)
    for ev in logs:
        kind = ev.get("kind") or "event"
        title_map = {
            "reminder_sent": "Reminder sent",
            "tag_added": f"Tagged as '{ev.get('tag')}'",
            "portal_invited": "Portal invite sent",
        }
        events.append({
            "id": f"event:{ev.get('id')}",
            "kind": kind,
            "title": title_map.get(kind, kind.replace("_", " ").capitalize()),
            "subtitle": ev.get("subject") or ev.get("tag") or ev.get("note"),
            "actor_id": ev.get("actor_id"),
            "at": ev.get("at"),
        })

    # Portal invite from members.portal_invited_at (if no matching event log row)
    if m.get("portal_invited_at"):
        already = any(e["kind"] == "portal_invited" for e in events)
        if not already:
            events.append({
                "id": "member:portal_invite",
                "kind": "portal_invited",
                "title": "Portal invite sent",
                "subtitle": None,
                "at": m.get("portal_invited_at"),
            })

    # Membership audit entries.
    # Iter 216h200 — skip rows that were auto-superseded (Craig's
    # screenshot showed 3x "Assigned plan" because the assign endpoint
    # used to spawn duplicate rows; the new endpoint is idempotent but
    # there's already noise in the wild — filter it out of the feed).
    memberships = await db.member_memberships.find(
        {"member_id": member_id, "organization_id": org_id},
        {"_id": 0},
    ).to_list(50)
    SUPERSEDED_REASONS = {"replaced_by_new_plan"}
    for mm in memberships:
        if (mm.get("status") in {"cancelled", "replaced"}
            and mm.get("cancel_reason") in SUPERSEDED_REASONS):
            # Auto-superseded by a subsequent assign — internal tidy-up,
            # not a real customer-facing event.
            continue
        if mm.get("status") == "replaced":
            # `replaced` rows always come from record-payment / assign
            # superseding an earlier pending row; suppress to avoid the
            # ghost-assignment chatter.
            continue
        plan = await db.membership_plans.find_one(
            {"id": mm.get("plan_id")},
            {"_id": 0, "name": 1},
        ) or {}
        plan_name = plan.get("name") or "plan"
        for entry in (mm.get("audit_log") or []):
            action = (entry.get("action") or "").lower()
            title = {
                "assigned": f"Assigned plan '{plan_name}'",
                "frozen": f"Froze plan '{plan_name}'",
                "cancel_requested": f"Cancelled plan '{plan_name}'",
            }.get(action, action.replace("_", " ").capitalize() or "Membership change")
            events.append({
                "id": f"membership:{mm.get('id')}:{action}:{entry.get('at')}",
                "kind": "membership",
                "title": title,
                "subtitle": None,
                "at": entry.get("at"),
            })

    # Joined at
    if m.get("created_at"):
        events.append({
            "id": "member:joined",
            "kind": "joined",
            "title": "Joined the studio",
            "subtitle": None,
            "at": m.get("created_at"),
        })

    # Sort DESC by `at`, missing timestamps sink to the bottom.
    def _k(e):
        return e.get("at") or ""
    events.sort(key=_k, reverse=True)

    return {"member_id": member_id, "events": events[:200], "count": len(events)}
