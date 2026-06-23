"""Member-facing booking, cancel, swap, and waitlist promotion.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query

from utils.database import db
from utils.memberships_emails import (
    send_booking_confirmation,
    send_waitlist_promotion,
)

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _uuid,
)

router = APIRouter(tags=["memberships"])



@router.get("/member/timetable")
async def member_timetable(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    member: dict = Depends(_require_current_member),
):
    frm = from_ or datetime.now(timezone.utc).isoformat()
    toh = to or (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    q = {"organization_id": member["organization_id"], "starts_at": {"$gte": frm, "$lte": toh}, "status": "scheduled"}
    occs = await db.class_occurrences.find(q, {"_id": 0}).sort("starts_at", 1).to_list(500)
    occ_ids = [o["id"] for o in occs]
    # Mark which ones the member is already booked on
    my_booked = {b["occurrence_id"]: b for b in await db.bookings.find(
        {"member_id": member["id"], "occurrence_id": {"$in": occ_ids},
         "status": {"$in": ["booked", "waitlist"]}}, {"_id": 0}
    ).to_list(500)}

    # Iter 215w — stitch instructor profile info onto each occurrence so
    # the member portal can link to `/m/{slug}/i/{instructor_slug}`.
    inst_ids = [o.get("instructor_id") for o in occs if o.get("instructor_id")]
    inst_by_id: dict[str, dict] = {}
    if inst_ids:
        for inst in await db.membership_instructors.find(
            {"id": {"$in": list(set(inst_ids))}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "slug": 1, "photo_url": 1, "is_published": 1},
        ).to_list(len(set(inst_ids))):
            inst_by_id[inst["id"]] = inst

    # Iter 215t — compute waitlist positions for the member's waitlist
    # bookings so the UI can show "#3 of 8 in queue".
    waitlist_positions: dict[str, int] = {}
    for occ_id, my in my_booked.items():
        if my.get("status") != "waitlist":
            continue
        ahead = await db.bookings.count_documents({
            "occurrence_id": occ_id,
            "status": "waitlist",
            "created_at": {"$lt": my.get("created_at") or ""},
        })
        waitlist_positions[occ_id] = ahead + 1

    for o in occs:
        my = my_booked.get(o["id"])
        if my:
            o["my_booking"] = {"id": my["id"], "status": my["status"]}
            if my.get("status") == "waitlist":
                o["my_booking"]["waitlist_position"] = waitlist_positions.get(o["id"])
        o["full"] = (o.get("bookings_count") or 0) >= (o.get("capacity") or 0)
        inst = inst_by_id.get(o.get("instructor_id"))
        if inst and inst.get("is_published"):
            o["instructor"] = {
                "id": inst["id"],
                "name": inst.get("name"),
                "slug": inst.get("slug"),
                "photo_url": inst.get("photo_url"),
            }
    return {"occurrences": occs}


@router.post("/member/bookings")
async def member_book(body: dict = Body(...), background: BackgroundTasks = None, member: dict = Depends(_require_current_member)):
    """Book a class.

    Two modes on the same endpoint, fully back-compat:

    1. Single (legacy):  body = { occurrence_id }
       → books the calling member into the class.

    2. Multi-attendee (Phase 2): body = {
            occurrence_id,
            attendees: [
              { kind: 'self' },
              { kind: 'sub_profile', sub_profile_id: '...' },
              { kind: 'guest', guest_name: '...', guest_email?: '...' },
              ...
           ]
       }
       → books all attendees in one atomic transaction. Capacity check
         sums every attendee. Credits = N × credits_to_book are debited
         from the parent member's pool. Bookings are linked via
         `booking_group_id` so the member portal can show them as one row.

    Returns: { bookings: [...] } in multi-mode, { booking: {...} } in
    legacy single mode.
    """
    occ_id = body.get("occurrence_id")
    occ = await db.class_occurrences.find_one({"id": occ_id, "organization_id": member["organization_id"]}, {"_id": 0})
    if not occ:
        raise HTTPException(404, "Class not found")
    if occ["status"] != "scheduled":
        raise HTTPException(400, "Class is cancelled")
    tpl = await db.class_templates.find_one({"id": occ["template_id"]}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template missing")
    now = datetime.now(timezone.utc)
    starts = datetime.fromisoformat(occ["starts_at"].replace("Z", "+00:00"))
    opens_at = starts - timedelta(hours=int(tpl.get("booking_opens_hours_before", 168)))
    if now < opens_at:
        raise HTTPException(400, f"Booking opens {opens_at.isoformat()}")

    # ── Resolve attendees. Default = single self-booking.
    raw_attendees = body.get("attendees")
    if not raw_attendees:
        raw_attendees = [{"kind": "self"}]
    if len(raw_attendees) > 8:
        raise HTTPException(400, "Maximum 8 attendees per booking")

    from routes.memberships_family import resolve_attendee
    resolved: list[dict] = []
    seen_sub_ids: set[str] = set()
    has_self = False
    for a in raw_attendees:
        kind = (a.get("kind") or "self").lower()
        if kind == "self":
            if has_self:
                raise HTTPException(400, "Cannot book the same member twice")
            has_self = True
        if kind == "sub_profile":
            sp_id = a.get("sub_profile_id")
            if sp_id in seen_sub_ids:
                raise HTTPException(400, "Cannot book the same sub-profile twice")
            seen_sub_ids.add(sp_id)
        info = await resolve_attendee(
            kind=kind, sub_profile_id=a.get("sub_profile_id"),
            guest_name=a.get("guest_name"), guest_email=a.get("guest_email"),
            parent_member=member,
        )
        # Already booked? Block any duplicate
        existing_q: dict = {
            "occurrence_id": occ_id,
            "status": {"$in": ["booked", "waitlist"]},
        }
        if info["attendee_kind"] == "self":
            existing_q["member_id"] = member["id"]
            existing_q["attendee_kind"] = {"$in": ["self", None]}
        elif info["attendee_kind"] == "sub_profile":
            existing_q["attendee_sub_profile_id"] = info["attendee_sub_profile_id"]
        else:
            # Guest dedup by name+email under the same parent
            existing_q["member_id"] = member["id"]
            existing_q["attendee_kind"] = "guest"
            existing_q["attendee_name"] = info["attendee_name"]
        existing = await db.bookings.find_one(existing_q, {"_id": 0, "id": 1, "status": 1})
        if existing:
            raise HTTPException(
                409, f"{info['attendee_name']} is already {existing['status']} for this class",
            )
        resolved.append(info)
    n_attendees = len(resolved)

    # ── Membership / credit check (parent's pool covers everyone)
    now_iso = _now_iso()
    mm = None
    async for cand in db.member_memberships.find(
        {"member_id": member["id"], "organization_id": member["organization_id"],
         "status": "active"},
        {"_id": 0},
    ).sort("joined_at", 1):
        exp = cand.get("credits_expires_at")
        if exp and exp < now_iso and (cand.get("credits_remaining") or 0) > 0:
            await db.member_memberships.update_one(
                {"id": cand["id"]},
                {"$set": {"credits_expired_at": _now_iso()},
                 "$push": {"audit_log": {"at": _now_iso(), "actor_id": "system",
                                          "action": "credits_expired"}}},
            )
            continue
        mm = cand
        break
    plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0}) if mm else None
    credits_per_attendee = int(tpl.get("credits_to_book") or 1)
    credits_needed = credits_per_attendee * n_attendees
    is_unlimited = bool(plan and plan.get("included_classes") == "unlimited")
    if not is_unlimited and (not mm or (mm.get("credits_remaining") or 0) < credits_needed):
        raise HTTPException(402, f"Need {credits_needed} credit{'s' if credits_needed != 1 else ''} — purchase a pack")
    # Access gating via access_plans
    if tpl.get("access_plans") and plan and plan["id"] not in (tpl["access_plans"] or []):
        raise HTTPException(403, "Your membership does not include this class")

    # ── Capacity check sums all N attendees
    capacity = int(occ.get("capacity") or 0)
    booked_now = int(occ.get("bookings_count") or 0)
    free_spots = max(capacity - booked_now, 0)
    going_to_waitlist = max(n_attendees - free_spots, 0)
    if going_to_waitlist > 0 and not tpl.get("waitlist_enabled", True):
        raise HTTPException(400, f"Class has {free_spots} spot{'s' if free_spots != 1 else ''} left — try fewer attendees")
    if going_to_waitlist > 0:
        wl_now = int(occ.get("waitlist_count") or 0)
        wl_max = int(tpl.get("max_waitlist", 10))
        if wl_now + going_to_waitlist > wl_max:
            raise HTTPException(400, "Waitlist is full")

    # ── Insert bookings — booked first, waitlist for the overflow
    booking_group_id = _uuid() if n_attendees > 1 else None
    booked_inserted = 0
    waitlist_inserted = 0
    inserted: list[dict] = []
    for i, info in enumerate(resolved):
        on_waitlist = i >= free_spots
        booking = {
            "id": _uuid(),
            "occurrence_id": occ_id,
            "member_id": member["id"],
            "organization_id": member["organization_id"],
            "site_id": occ.get("site_id"),
            "status": "waitlist" if on_waitlist else "booked",
            "credits_charged": 0 if on_waitlist or is_unlimited else credits_per_attendee,
            "booked_at": _now_iso(),
            "channel": "member_portal",
            **info,  # attendee_kind / attendee_name / attendee_email / attendee_sub_profile_id?
        }
        if booking_group_id:
            booking["booking_group_id"] = booking_group_id
        await db.bookings.insert_one(booking)
        if on_waitlist:
            waitlist_inserted += 1
        else:
            booked_inserted += 1
        inserted.append({k: v for k, v in booking.items() if k != "_id"})

    # Single atomic capacity update
    inc: dict = {}
    if booked_inserted:
        inc["bookings_count"] = booked_inserted
    if waitlist_inserted:
        inc["waitlist_count"] = waitlist_inserted
    if inc:
        await db.class_occurrences.update_one({"id": occ_id}, {"$inc": inc})
    if booked_inserted:
        try:
            from utils.comms_conversions import record_conversion
            await record_conversion(member["organization_id"], member.get("email"), "class_booking",
                                    source="member_portal", meta={"occurrence_id": occ_id})
        except Exception:
            pass
    # Single credit debit (only the booked ones consume credits)
    debit = credits_per_attendee * booked_inserted if not is_unlimited else 0
    if debit and mm:
        await db.member_memberships.update_one(
            {"id": mm["id"]},
            {"$inc": {"credits_remaining": -debit, "credits_used": debit}},
        )
    if booked_inserted and background is not None:
        background.add_task(send_booking_confirmation, member, occ)

    # Iter 215d4 — activation funnel event (first booking taken). Best-effort.
    if booked_inserted:
        try:
            from routes.activation_events import record_activation_event
            await record_activation_event(
                member["organization_id"], "first_booking_taken",
                trigger_user_id=member.get("id"),
                payload={"occurrence_id": occ_id, "count": booked_inserted},
            )
        except Exception:
            pass

    # Legacy single-booking response shape when only one attendee was passed
    if n_attendees == 1 and not body.get("attendees"):
        return {"booking": inserted[0]}
    return {
        "bookings": inserted,
        "booked": booked_inserted,
        "waitlisted": waitlist_inserted,
        "booking_group_id": booking_group_id,
    }


@router.delete("/member/bookings/{booking_id}")
async def member_cancel_booking(booking_id: str, background: BackgroundTasks = None, member: dict = Depends(_require_current_member)):
    b = await db.bookings.find_one({"id": booking_id, "member_id": member["id"]}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Booking not found")
    if b["status"] not in ("booked", "waitlist"):
        raise HTTPException(400, f"Cannot cancel a {b['status']} booking")
    occ = await db.class_occurrences.find_one({"id": b["occurrence_id"]}, {"_id": 0})
    tpl = await db.class_templates.find_one({"id": occ["template_id"]}, {"_id": 0}) if occ else None
    cutoff_hrs = int((tpl or {}).get("cancellation_cutoff_hours_before", 12))
    now = datetime.now(timezone.utc)
    starts = datetime.fromisoformat(occ["starts_at"].replace("Z", "+00:00")) if occ else now
    late = now > starts - timedelta(hours=cutoff_hrs)
    new_status = "late_cancel" if (late and b["status"] == "booked") else "cancelled"
    await db.bookings.update_one({"id": booking_id},
        {"$set": {"status": new_status, "cancelled_at": _now_iso()}})
    # Decrement occurrence counts
    if b["status"] == "booked":
        await db.class_occurrences.update_one({"id": b["occurrence_id"]}, {"$inc": {"bookings_count": -1}})
    else:
        await db.class_occurrences.update_one({"id": b["occurrence_id"]}, {"$inc": {"waitlist_count": -1}})
    # Refund credits if not a late cancel
    if not late and b.get("credits_charged"):
        await db.member_memberships.update_one(
            {"member_id": member["id"], "status": {"$in": ["active", "frozen"]}},
            {"$inc": {"credits_remaining": b["credits_charged"], "credits_used": -b["credits_charged"]}},
        )
    # Promote from waitlist if this was a booked cancel
    if b["status"] == "booked" and not late:
        promoted = await _promote_from_waitlist(b["occurrence_id"])
        occ_full = await db.class_occurrences.find_one({"id": b["occurrence_id"]}, {"_id": 0})
        if background is not None and occ_full:
            for promoted_member in promoted:
                background.add_task(send_waitlist_promotion, promoted_member, occ_full)
            # Phase 4: if the occurrence is still under-capacity AND
            # starts within 24h, fire a drop-in invite to opted-in members.
            try:
                from routes.memberships_phase4 import maybe_send_dropin_invites
                await maybe_send_dropin_invites(occ_full, background)
            except Exception:
                # Never fail a cancel because the invite engine hiccuped
                pass
    if late and b["status"] == "booked":
        await db.members.update_one({"id": member["id"]}, {"$inc": {"no_show_count": 1}})
    return {"ok": True, "status": new_status, "refunded_credits": (0 if late else b.get("credits_charged", 0))}


@router.post("/member/bookings/{booking_id}/swap")
async def member_swap_booking(
    booking_id: str, body: dict = Body(...),
    background: BackgroundTasks = None,
    member: dict = Depends(_require_current_member),
):
    """One-click move a booking from one class occurrence to another.

    Phase 2 win: way better UX than `cancel + rebook` because:
      • single API call,
      • no late-cancel penalty if the swap target is also valid,
      • atomic — if the target is full we don't lose the original spot.

    Body: { target_occurrence_id }

    Validation rules:
      • Original booking must be in 'booked' or 'waitlist' status.
      • Target occurrence must be scheduled, in the same org, and have
        an open spot (or open waitlist slot if waitlist enabled).
      • Booking-window opens-at on the target is honoured.
      • Credits are conserved — the original credit charge transfers to
        the new booking row; no double-debit.
      • Only single bookings (not multi-attendee groups) are swappable
        in v1.
    """
    target_occ_id = body.get("target_occurrence_id")
    if not target_occ_id:
        raise HTTPException(400, "target_occurrence_id is required")

    b = await db.bookings.find_one(
        {"id": booking_id, "member_id": member["id"]}, {"_id": 0},
    )
    if not b:
        raise HTTPException(404, "Booking not found")
    if b["status"] not in ("booked", "waitlist"):
        raise HTTPException(400, f"Cannot swap a {b['status']} booking")
    if b.get("booking_group_id"):
        raise HTTPException(
            400, "Multi-attendee bookings can't be swapped — cancel and rebook",
        )
    if b["occurrence_id"] == target_occ_id:
        raise HTTPException(400, "Already booked on this class")

    target = await db.class_occurrences.find_one(
        {"id": target_occ_id, "organization_id": member["organization_id"]},
        {"_id": 0},
    )
    if not target:
        raise HTTPException(404, "Target class not found")
    if target.get("status") != "scheduled":
        raise HTTPException(400, "Target class is cancelled")
    target_tpl = await db.class_templates.find_one(
        {"id": target["template_id"]}, {"_id": 0},
    )
    if not target_tpl:
        raise HTTPException(404, "Target class template missing")
    now = datetime.now(timezone.utc)
    target_starts = datetime.fromisoformat(
        target["starts_at"].replace("Z", "+00:00"),
    )
    opens_at = target_starts - timedelta(
        hours=int(target_tpl.get("booking_opens_hours_before", 168)),
    )
    if now < opens_at:
        raise HTTPException(400, f"Target booking opens {opens_at.isoformat()}")

    # Ensure no existing booking on the target for this member
    dup = await db.bookings.find_one(
        {"member_id": member["id"], "occurrence_id": target_occ_id,
         "status": {"$in": ["booked", "waitlist"]}},
        {"_id": 0, "status": 1},
    )
    if dup:
        raise HTTPException(409, f"Already {dup['status']} for the target class")

    # Capacity / waitlist on target
    target_capacity = int(target.get("capacity") or 0)
    target_booked = int(target.get("bookings_count") or 0)
    target_full = target_booked >= target_capacity
    if target_full and not target_tpl.get("waitlist_enabled", True):
        raise HTTPException(400, "Target class is full")
    if target_full and (target.get("waitlist_count") or 0) >= int(
        target_tpl.get("max_waitlist", 10),
    ):
        raise HTTPException(400, "Target waitlist is full")
    new_status = "waitlist" if target_full else "booked"

    # Credits — keep what was already charged for this booking (no
    # double-debit, no surprise refund). If credits_to_book differs on
    # the target template, we adjust the delta.
    old_charged = int(b.get("credits_charged") or 0)
    new_charge = (0 if new_status == "waitlist"
                  else int(target_tpl.get("credits_to_book") or 1))
    # If original was waitlist (no charge) and new is booked, we charge
    # the target's credits. Conversely, going booked→waitlist refunds.
    delta = new_charge - old_charged

    if delta > 0:
        # Need extra credits — find an active membership with enough
        mm = await db.member_memberships.find_one(
            {"member_id": member["id"], "status": "active"}, {"_id": 0},
        )
        plan = await db.membership_plans.find_one(
            {"id": (mm or {}).get("plan_id")}, {"_id": 0},
        ) if mm else None
        is_unlimited = bool(plan and plan.get("included_classes") == "unlimited")
        if not is_unlimited:
            if not mm or (mm.get("credits_remaining") or 0) < delta:
                raise HTTPException(
                    402, f"Need {delta} extra credit{'s' if delta > 1 else ''} to swap to this class",
                )
            await db.member_memberships.update_one(
                {"id": mm["id"]},
                {"$inc": {"credits_remaining": -delta, "credits_used": delta}},
            )
    elif delta < 0:
        await db.member_memberships.update_one(
            {"member_id": member["id"], "status": {"$in": ["active", "frozen"]}},
            {"$inc": {"credits_remaining": -delta, "credits_used": delta}},
        )

    # Update the booking row in place — keeps history continuity
    await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {
            "occurrence_id": target_occ_id,
            "site_id": target.get("site_id"),
            "status": new_status,
            "credits_charged": new_charge,
            "swapped_from_occurrence_id": b["occurrence_id"],
            "swapped_at": _now_iso(),
        }},
    )

    # Update occurrence counts on both sides
    if b["status"] == "booked":
        await db.class_occurrences.update_one(
            {"id": b["occurrence_id"]}, {"$inc": {"bookings_count": -1}},
        )
        # Promote waitlist on the source class
        promoted = await _promote_from_waitlist(b["occurrence_id"])
        if background is not None:
            src_occ = await db.class_occurrences.find_one(
                {"id": b["occurrence_id"]}, {"_id": 0},
            )
            for pm in promoted:
                background.add_task(send_waitlist_promotion, pm, src_occ)
    else:  # original was waitlist
        await db.class_occurrences.update_one(
            {"id": b["occurrence_id"]}, {"$inc": {"waitlist_count": -1}},
        )
    target_inc = (
        {"bookings_count": 1} if new_status == "booked"
        else {"waitlist_count": 1}
    )
    await db.class_occurrences.update_one(
        {"id": target_occ_id}, {"$inc": target_inc},
    )

    # Email confirmation if booked
    if new_status == "booked" and background is not None:
        background.add_task(send_booking_confirmation, member, target)

    return {
        "ok": True,
        "booking_id": booking_id,
        "status": new_status,
        "credits_delta": delta,
        "from_occurrence_id": b["occurrence_id"],
        "to_occurrence_id": target_occ_id,
    }


async def _promote_from_waitlist(occ_id: str) -> list[dict]:
    """Promote next waitlisted member(s) to booked using a smart priority
    score (Phase 4): VIP plan bonus, fewer no-shows, then earliest
    booked_at as tiebreaker. Returns the list of members who were
    promoted so the caller can dispatch emails."""
    occ = await db.class_occurrences.find_one({"id": occ_id}, {"_id": 0})
    promoted: list[dict] = []
    if not occ:
        return promoted

    # Pull all waitlisters once + score them, then iterate in priority order.
    wl: list[dict] = await db.bookings.find(
        {"occurrence_id": occ_id, "status": "waitlist"}, {"_id": 0},
    ).sort("booked_at", 1).to_list(500)
    if not wl:
        return promoted

    # Score map: higher = promote first.
    scored: list[tuple[int, str, dict]] = []
    for b in wl:
        mem = await db.members.find_one({"id": b["member_id"]}, {"_id": 0, "no_show_count": 1})
        mm = await db.member_memberships.find_one(
            {"member_id": b["member_id"], "status": {"$in": ["active", "frozen"]}},
            {"_id": 0, "plan_id": 1},
        )
        plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0}) if mm else None
        score = 0
        if plan:
            inc = plan.get("included_classes")
            cycle = plan.get("billing_cycle")
            if inc == "unlimited":
                score += 50
            if cycle == "annual":
                score += 30
        score -= 10 * int((mem or {}).get("no_show_count") or 0)
        scored.append((score, b.get("booked_at") or "", b))

    # Higher score first; on tie, earliest booked_at first.
    scored.sort(key=lambda t: (-t[0], t[1]))

    for _score, _bat, nxt in scored:
        # Re-read live capacity each iteration in case bookings changed.
        occ = await db.class_occurrences.find_one({"id": occ_id}, {"_id": 0})
        if (occ.get("bookings_count") or 0) >= (occ.get("capacity") or 0):
            break
        await db.bookings.update_one(
            {"id": nxt["id"]},
            {"$set": {"status": "booked",
                      "promoted_from_waitlist_at": _now_iso(),
                      "promotion_score": _score}},
        )
        await db.class_occurrences.update_one(
            {"id": occ_id}, {"$inc": {"bookings_count": 1, "waitlist_count": -1}},
        )
        # Charge credits now that they're booked
        tpl = await db.class_templates.find_one({"id": occ["template_id"]}, {"_id": 0})
        credits = int((tpl or {}).get("credits_to_book") or 1)
        mm = await db.member_memberships.find_one(
            {"member_id": nxt["member_id"], "status": "active"}, {"_id": 0},
        )
        plan = await db.membership_plans.find_one({"id": mm["plan_id"]}, {"_id": 0}) if mm else None
        if plan and plan.get("included_classes") != "unlimited" and mm:
            await db.member_memberships.update_one(
                {"id": mm["id"]},
                {"$inc": {"credits_remaining": -credits, "credits_used": credits}},
            )
            await db.bookings.update_one(
                {"id": nxt["id"]}, {"$set": {"credits_charged": credits}},
            )
        mem_doc = await db.members.find_one({"id": nxt["member_id"]}, {"_id": 0, "password": 0})
        if mem_doc:
            promoted.append(mem_doc)
    return promoted


@router.get("/member/bookings")
async def member_list_bookings(member: dict = Depends(_require_current_member)):
    upcoming = await db.bookings.find({"member_id": member["id"], "status": {"$in": ["booked", "waitlist"]}}, {"_id": 0}).sort("booked_at", -1).to_list(100)
    past = await db.bookings.find({"member_id": member["id"], "status": {"$in": ["attended", "no_show", "cancelled", "late_cancel"]}}, {"_id": 0}).sort("booked_at", -1).limit(20).to_list(20)
    for lst in (upcoming, past):
        for b in lst:
            occ = await db.class_occurrences.find_one({"id": b["occurrence_id"]}, {"_id": 0})
            b["occurrence"] = occ
    # Iter 215t — annotate waitlist bookings with their live queue position
    # so the member's "My bookings" tab can show "Waitlist · #3 of 8".
    for b in upcoming:
        if b.get("status") != "waitlist":
            continue
        ahead = await db.bookings.count_documents({
            "occurrence_id": b["occurrence_id"],
            "status": "waitlist",
            "created_at": {"$lt": b.get("created_at") or ""},
        })
        b["waitlist_position"] = ahead + 1
    return {"upcoming": upcoming, "past": past}



# ═════════════ Operator-side booking (Sprint A · G4 · iter 216ah) ═════════════

from utils.auth import get_current_user as _get_current_user_obk  # noqa: E402


def _assert_operator_org(user: dict) -> str:
    """Helper — ensure caller is an operator in an org. Raises 403 otherwise."""
    if not user or not user.get("organization_id"):
        raise HTTPException(status_code=403, detail="Not an operator")
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager", "staff") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Operator role required")
    return user["organization_id"]


@router.post("/memberships/occurrences/{occurrence_id}/bookings")
async def operator_book_member(
    occurrence_id: str,
    body: dict = Body(...),
    user: dict = Depends(_get_current_user_obk),
):
    """Operator-facing: book one or more members into a class occurrence.

    Body:
      {
        "member_ids": ["..."],               # required, 1..10
        "allow_waitlist": true,              # default true
        "bypass_credits": true,              # default true — operator override
        "note": "Booked at the desk by Sarah"
      }

    Unlike POST /member/bookings:
      * Operators can bypass credit / plan / access checks by default
        (they've already confirmed payment at the desk, or are fixing
        a system issue).
      * Capacity is still enforced. Overflow flows to the waitlist when
        `allow_waitlist` AND the template has waitlist_enabled.
      * Double-bookings are silently skipped (returned in
        `skipped_already_booked`) so operators can re-run without 409s.
      * Every booking carries `channel="operator"` + `booked_by_user_id`
        for a clean audit trail.
    """
    org_id = _assert_operator_org(user)
    occ = await db.class_occurrences.find_one(
        {"id": occurrence_id, "organization_id": org_id}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class occurrence not found")
    if occ.get("status") != "scheduled":
        raise HTTPException(400, "Class is cancelled")
    tpl = await db.class_templates.find_one({"id": occ["template_id"]}, {"_id": 0}) or {}

    member_ids = body.get("member_ids") or []
    if isinstance(member_ids, str):
        member_ids = [member_ids]
    if not member_ids:
        raise HTTPException(400, "member_ids is required (list of 1-10 ids)")
    if len(member_ids) > 10:
        raise HTTPException(400, "Maximum 10 members per operator booking")

    allow_waitlist = bool(body.get("allow_waitlist", True))
    bypass_credits = bool(body.get("bypass_credits", True))
    note = (body.get("note") or "").strip() or None

    member_docs: list[dict] = []
    async for m in db.members.find(
        {"organization_id": org_id, "id": {"$in": member_ids}},
        {"_id": 0},
    ):
        member_docs.append(m)
    found_ids = {m["id"] for m in member_docs}
    missing = [mid for mid in member_ids if mid not in found_ids]
    if missing:
        raise HTTPException(404, f"{len(missing)} member(s) not found in this org")

    # Silent-dedupe anyone already booked/waitlisted so retries don't 409.
    already: set[str] = set()
    async for b in db.bookings.find(
        {"occurrence_id": occurrence_id,
         "member_id": {"$in": [m["id"] for m in member_docs]},
         "status": {"$in": ["booked", "waitlist", "attended"]}},
        {"_id": 0, "member_id": 1},
    ):
        already.add(b["member_id"])
    eligible = [m for m in member_docs if m["id"] not in already]

    capacity = int(occ.get("capacity") or 0)
    booked_now = int(occ.get("bookings_count") or 0)
    free_spots = max(capacity - booked_now, 0)

    inserted: list[dict] = []
    booked_inserted = 0
    waitlist_inserted = 0
    for m in eligible:
        on_waitlist = booked_inserted >= free_spots
        if on_waitlist and (not allow_waitlist or not tpl.get("waitlist_enabled", True)):
            break
        doc = {
            "id": _uuid(),
            "occurrence_id": occurrence_id,
            "member_id": m["id"],
            "organization_id": org_id,
            "site_id": occ.get("site_id"),
            "status": "waitlist" if on_waitlist else "booked",
            "credits_charged": 0,  # operator override — never deduct credits
            "booked_at": _now_iso(),
            "created_at": _now_iso(),
            "channel": "operator",
            "booked_by_user_id": user.get("id"),
            "attendee_kind": "self",
            "attendee_name": (
                ((m.get("first_name") or "") + " " + (m.get("last_name") or "")).strip()
                or m.get("email") or "Member"
            ),
            "attendee_email": m.get("email") or "",
            "operator_note": note,
            "bypass_credits": bypass_credits,
        }
        await db.bookings.insert_one(doc)
        if on_waitlist:
            waitlist_inserted += 1
        else:
            booked_inserted += 1
        inserted.append({k: v for k, v in doc.items() if k != "_id"})

    inc: dict = {}
    if booked_inserted:
        inc["bookings_count"] = booked_inserted
    if waitlist_inserted:
        inc["waitlist_count"] = waitlist_inserted
    if inc:
        await db.class_occurrences.update_one({"id": occurrence_id}, {"$inc": inc})

    skipped = len(member_docs) - len(inserted)
    return {
        "ok": True,
        "booked": booked_inserted,
        "waitlisted": waitlist_inserted,
        "skipped": skipped,
        "skipped_already_booked": sorted(already),
        "bookings": inserted,
    }
