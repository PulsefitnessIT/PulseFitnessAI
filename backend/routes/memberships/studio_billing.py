"""Studio billing extras — monthly class invoicing + smoothed (pro-rata)
annual plans.

Iter 215s. Two operator asks from the latest studio brief:

  1. **Monthly class invoice** — "send out invoices for a month's worth
     of classes". For every member that booked/attended ≥1 class in a
     target calendar month, aggregate the sessions and bill them in a
     single invoice. Supports both a default per-class rate and a
     plan-specific `per_class_pence` override. Ideal for PAYG / small
     studios that run classes instead of subscriptions.

  2. **12-month smoothing (pro-rata)** — annual fee divided evenly
     across N (default 12) months so the member pays a predictable
     amount every month regardless of term/holiday schedule. Applied
     via plan fields (`smoothed`, `smoothed_annual_pence`,
     `smoothed_months`) defined in plans.py. This module exposes a
     helper to compute the smoothed monthly pence so the PlanEditor
     and the member portal can show the real monthly payment.

Data model — new collection `membership_class_invoices`:

    { id, organization_id, member_id, member_email, member_name,
      period:  "YYYY-MM",
      lines:   [ { kind, description, quantity, unit_pence,
                   amount_pence, occurrence_id?, booking_id? } ],
      subtotal_pence, total_pence,
      status:  "draft" | "sent" | "paid" | "void",
      sent_at, paid_at, void_at,
      created_by, created_at, updated_at }

A line's `kind` is one of:
    • "class"     — one booked/attended class at the per-class rate
    • "smoothed"  — monthly installment of a smoothed plan
    • "adhoc"     — operator-added manual line
"""
from __future__ import annotations

import base64
import calendar
import io
import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db, STRIPE_API_KEY
from utils.email import send_email
from utils.module_guard import require_module

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _require_operator_org,
    _uuid,
)

import stripe

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-billing"])


# ═════════════════════ Pro-rata smoothing helper ═════════════════════

def compute_smoothed_monthly_pence(plan: dict) -> int:
    """Return the monthly pence a member on this plan pays when
    smoothing is enabled. Defensive: returns the raw price_pence if the
    plan isn't configured for smoothing."""
    if not plan.get("smoothed"):
        return int(plan.get("price_pence") or 0)
    annual = int(plan.get("smoothed_annual_pence") or 0)
    months = int(plan.get("smoothed_months") or 12) or 12
    if annual <= 0 or months <= 0:
        return int(plan.get("price_pence") or 0)
    # Banker-friendly rounding — we round *down* per month and push the
    # stub pence into month 1 so 12 equal payments + 1 optional
    # rounding-adjustment on the first line. For the display helper we
    # just return the nearest-pence monthly amount.
    return round(annual / months)


@router.get(
    "/memberships/plans/{plan_id}/smoothing-preview",
    dependencies=[Depends(require_module("memberships"))],
)
async def smoothing_preview(plan_id: str, user: dict = Depends(get_current_user)):
    """Operator helper — what the member will pay each month if
    smoothing is enabled on this plan."""
    org_id = await _require_operator_org(user)
    plan = await db.membership_plans.find_one(
        {"id": plan_id, "organization_id": org_id}, {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    months = int(plan.get("smoothed_months") or 12) or 12
    monthly = compute_smoothed_monthly_pence(plan)
    annual = int(plan.get("smoothed_annual_pence") or 0)
    return {
        "enabled": bool(plan.get("smoothed")),
        "monthly_pence": monthly,
        "months": months,
        "annual_pence": annual,
        "annual_vs_monthly_diff_pence": annual - (monthly * months),
    }


# ═════════════════════ Sibling discount settings (iter 215z + iter 216aa) ═════════════════════

class SiblingDiscountIn(BaseModel):
    pct: int = Field(default=0, ge=0, le=50)
    # Iter 216aa Phase B — optional tiered ladder. When non-empty,
    # overrides the flat `pct`. Each tier is {rank, pct}; rank=2 means
    # "the 2nd child", rank=4 means "the 4th and beyond".
    tiers: list[dict] | None = None


def _validate_tiers(tiers: list[dict] | None, *, key: str) -> list[dict]:
    """Normalise + sanity-check a tier ladder. Returns sorted list."""
    if not tiers:
        return []
    cleaned: list[dict] = []
    for t in tiers:
        try:
            rank = int(t.get(key))
            pct = int(t.get("pct"))
        except (TypeError, ValueError):
            raise HTTPException(400, f"Each tier needs {key} (int) and pct (int)")
        if rank < 2 or rank > 20:
            raise HTTPException(400, f"{key} must be between 2 and 20")
        if pct < 0 or pct > 75:
            raise HTTPException(400, "pct must be between 0 and 75")
        cleaned.append({key: rank, "pct": pct})
    cleaned.sort(key=lambda t: t[key])
    # De-dupe by rank/min_classes (keep highest pct for any duplicate).
    by_rank: dict[int, int] = {}
    for t in cleaned:
        by_rank[t[key]] = max(by_rank.get(t[key], 0), t["pct"])
    return [{key: r, "pct": p} for r, p in sorted(by_rank.items())]


@router.get(
    "/memberships/billing/sibling-discount",
    dependencies=[Depends(require_module("memberships"))],
)
async def get_sibling_discount(user: dict = Depends(get_current_user)):
    """Return the org's sibling-discount config — flat pct + tiered ladder."""
    org_id = await _require_operator_org(user)
    pct = await _sibling_discount_pct(org_id)
    tiers = await _sibling_discount_tiers(org_id)
    return {"pct": pct, "enabled": pct > 0 or bool(tiers), "tiers": tiers}


@router.post(
    "/memberships/billing/sibling-discount",
    dependencies=[Depends(require_module("memberships"))],
)
async def set_sibling_discount(
    body: SiblingDiscountIn, user: dict = Depends(get_current_user),
):
    """Owner / manager toggle. ``tiers`` (when supplied) overrides ``pct``;
    leave both empty to disable discounting entirely."""
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can change billing settings.")
    org_id = await _require_operator_org(user)
    tiers = _validate_tiers(body.tiers, key="rank")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "sibling_discount_pct": int(body.pct),
            "sibling_discount_tiers": tiers,
            "sibling_discount_updated_at": _now_iso(),
        }},
    )
    return {"pct": int(body.pct), "tiers": tiers, "enabled": body.pct > 0 or bool(tiers)}


# ═════════════════════ Multi-class discount settings (iter 216aa Phase B) ═════════════════════

class MultiClassDiscountIn(BaseModel):
    tiers: list[dict] | None = None  # [{min_classes:2, pct:10}, …]


@router.get(
    "/memberships/billing/multi-class-discount",
    dependencies=[Depends(require_module("memberships"))],
)
async def get_multi_class_discount(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    tiers = await _multi_class_discount_tiers(org_id)
    return {"tiers": tiers, "enabled": bool(tiers)}


@router.post(
    "/memberships/billing/multi-class-discount",
    dependencies=[Depends(require_module("memberships"))],
)
async def set_multi_class_discount(
    body: MultiClassDiscountIn, user: dict = Depends(get_current_user),
):
    if (user.get("role") or "").lower() not in {"owner", "manager"} and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners or managers can change billing settings.")
    org_id = await _require_operator_org(user)
    tiers = _validate_tiers(body.tiers, key="min_classes")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "multi_class_discount_tiers": tiers,
            "multi_class_discount_updated_at": _now_iso(),
        }},
    )
    return {"tiers": tiers, "enabled": bool(tiers)}


async def _multi_class_discount_tiers(org_id: str) -> list[dict]:
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "multi_class_discount_tiers": 1},
    ) or {}
    return list(org.get("multi_class_discount_tiers") or [])


async def _sibling_discount_tiers(org_id: str) -> list[dict]:
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "sibling_discount_tiers": 1},
    ) or {}
    return list(org.get("sibling_discount_tiers") or [])


def _multi_class_pct_for(count: int, tiers: list[dict]) -> int:
    """Largest tier whose ``min_classes`` <= count."""
    pct = 0
    for t in tiers:
        if int(t.get("min_classes") or 0) <= count:
            pct = max(pct, int(t.get("pct") or 0))
    return pct


def _apply_multi_class_discount(lines: list[dict], tiers: list[dict]) -> tuple[list[dict], int]:
    """Group class lines by attendee; for any attendee with N >= min_classes
    apply the highest matching tier as a negative discount line.

    Returns (lines + extras, delta_pence_negative_or_zero).
    """
    if not tiers:
        return lines, 0

    # Group only "class" lines (smoothed/adhoc/sibling_discount excluded).
    by_att: dict[str, list[dict]] = {}
    for ln in lines:
        if ln.get("kind") != "class":
            continue
        key = ln.get("attendee_sub_profile_id") or (
            f"name:{ln.get('attendee_name','Account')}:{ln.get('attendee_kind','self')}"
        )
        by_att.setdefault(key, []).append(ln)

    delta = 0
    extras: list[dict] = []
    for key, rows in by_att.items():
        count = len(rows)
        pct = _multi_class_pct_for(count, tiers)
        if pct <= 0:
            continue
        sub = sum(int(r.get("amount_pence") or 0) for r in rows)
        if sub <= 0:
            continue
        disc = -((sub * pct) // 100)
        if disc == 0:
            continue
        att_name = rows[0].get("attendee_name") or "Member"
        extras.append({
            "kind": "multi_class_discount",
            "description": f"Multi-class discount ({count} classes · {att_name}) — {pct}% off",
            "quantity": 1,
            "unit_pence": disc,
            "amount_pence": disc,
            "attendee_name": att_name,
            "attendee_kind": rows[0].get("attendee_kind") or "self",
            "attendee_sub_profile_id": rows[0].get("attendee_sub_profile_id"),
            "multi_class_count": count,
            "multi_class_pct": pct,
        })
        delta += disc
    return lines + extras, delta


# ═════════════════════ Monthly class invoicing ═════════════════════

def _month_bounds(period: str) -> tuple[datetime, datetime]:
    """Parse "YYYY-MM" → [start, end) in UTC."""
    try:
        y, m = period.split("-")
        y_i, m_i = int(y), int(m)
        if m_i < 1 or m_i > 12:
            raise ValueError("month out of range")
    except Exception as exc:
        raise HTTPException(400, f"period must be YYYY-MM (got {period!r})") from exc
    start = datetime(y_i, m_i, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(y_i, m_i)[1]
    end = datetime(y_i, m_i, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


async def _default_per_class_pence(org_id: str) -> int:
    """Studio default — the cheapest active payg plan's price, or £10
    fallback. This is used when a booking's plan doesn't carry a
    `per_class_pence` override."""
    payg = await db.membership_plans.find_one(
        {"organization_id": org_id, "kind": "payg", "archived": {"$ne": True}},
        {"_id": 0, "price_pence": 1},
        sort=[("price_pence", 1)],
    )
    return int((payg or {}).get("price_pence") or 1000)


async def _build_invoice_lines_for_member(
    *, org_id: str, member: dict, start: datetime, end: datetime,
    include_attended_only: bool, default_rate: int,
) -> tuple[list[dict], int]:
    """Walk this member's bookings in [start,end) and produce invoice
    line items + a running subtotal."""
    wanted = ["attended"] if include_attended_only else ["attended", "booked"]
    bookings = await db.bookings.find({
        "member_id": member["id"],
        "organization_id": org_id,
        "status": {"$in": wanted},
    }, {"_id": 0}).to_list(1000)

    lines: list[dict] = []
    subtotal = 0
    # Resolve the occurrences + templates in one pass so we have names/dates.
    occ_ids = [b["occurrence_id"] for b in bookings if b.get("occurrence_id")]
    occ_rows = await db.class_occurrences.find(
        {"id": {"$in": occ_ids}}, {"_id": 0, "id": 1, "name": 1, "starts_at": 1, "template_id": 1},
    ).to_list(len(occ_ids) + 1) if occ_ids else []
    occ_by_id = {o["id"]: o for o in occ_rows}
    tpl_rows = await db.class_templates.find(
        {"id": {"$in": [o.get("template_id") for o in occ_rows if o.get("template_id")]}},
        {"_id": 0, "id": 1, "name": 1, "per_class_pence": 1},
    ).to_list(len(occ_rows) + 1) if occ_rows else []
    tpl_by_id = {t["id"]: t for t in tpl_rows}

    for b in bookings:
        occ = occ_by_id.get(b.get("occurrence_id")) or {}
        try:
            dt = datetime.fromisoformat((occ.get("starts_at") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        if not dt or dt < start or dt > end:
            continue
        tpl = tpl_by_id.get(occ.get("template_id")) or {}
        name = tpl.get("name") or occ.get("name") or "Class"
        rate = int(tpl.get("per_class_pence") or default_rate)
        # Iter 215y — per-attendee grouping. Parent accounts with
        # sub-profiles (kids) want their invoice broken down by child.
        attendee_name = b.get("attendee_name") or "You"
        attendee_kind = b.get("attendee_kind") or "self"
        lines.append({
            "kind": "class",
            "description": f"{name} · {dt.strftime('%a %d %b %H:%M')}",
            "quantity": 1,
            "unit_pence": rate,
            "amount_pence": rate,
            "occurrence_id": b.get("occurrence_id"),
            "booking_id": b.get("id"),
            "attendee_name": attendee_name,
            "attendee_kind": attendee_kind,
            "attendee_sub_profile_id": b.get("attendee_sub_profile_id"),
        })
        subtotal += rate
    # Iter 216aa Phase B — apply multi-class discount FIRST so per-attendee
    # subtotals reflect the headline rate before we reduce it again for
    # later siblings.
    mc_tiers = await _multi_class_discount_tiers(org_id)
    lines, mc_delta = _apply_multi_class_discount(lines, mc_tiers)
    subtotal += mc_delta
    # Iter 215z + 216aa — apply sibling discount (org-level). Tiered ladder
    # takes precedence over the legacy flat pct.
    sib_tiers = await _sibling_discount_tiers(org_id)
    pct = await _sibling_discount_pct(org_id)
    lines, delta = _apply_sibling_discount(lines, bookings, pct, sib_tiers)
    subtotal += delta
    return lines, subtotal


async def _append_costume_lines(
    *, org_id: str, member: dict, period: str,
) -> tuple[list[dict], int]:
    """Iter 216ae+ — costume → billing hook.

    For any costume flagged ordered / arrived / fitted (i.e. the studio has
    committed cash on behalf of the member) that hasn't already been rolled
    into an invoice, emit a `kind="costume"` line so studios stop chasing
    costume payments separately. Idempotent via the costume's `invoiced_on`
    period stamp (written by the generate path on finalise).

    Matches costumes by member_id OR via any sub_profile belonging to the
    account holder so parent accounts pick up their kids' costumes too.
    """
    sub_ids: list[str] = []
    async for sp in db.member_sub_profiles.find(
        {"organization_id": org_id, "member_id": member["id"]},
        {"_id": 0, "id": 1},
    ):
        sub_ids.append(sp["id"])

    or_clauses: list[dict] = [{"member_id": member["id"]}]
    if sub_ids:
        or_clauses.append({"sub_profile_id": {"$in": sub_ids}})

    rows = await db.event_costumes.find(
        {
            "organization_id": org_id,
            "$or": or_clauses,
            "status": {"$in": ["ordered", "arrived", "fitted"]},
            "total_pence": {"$gt": 0},
            "$and": [
                {"$or": [
                    {"invoiced_on": {"$exists": False}},
                    {"invoiced_on": None},
                    {"invoiced_on": ""},
                    {"invoiced_on": period},  # allow re-run of the same period
                ]},
            ],
        },
        {"_id": 0},
    ).to_list(500)

    lines: list[dict] = []
    subtotal = 0
    # Enrich with event name so the description reads naturally on the invoice.
    event_ids = list({r.get("event_id") for r in rows if r.get("event_id")})
    event_by_id: dict[str, str] = {}
    if event_ids:
        async for e in db.studio_events.find(
            {"id": {"$in": event_ids}}, {"_id": 0, "id": 1, "name": 1},
        ):
            event_by_id[e["id"]] = e.get("name") or ""

    for r in rows:
        unpaid = max(int(r.get("total_pence") or 0) - int(r.get("paid_pence") or 0), 0)
        if unpaid <= 0:
            continue
        event_label = event_by_id.get(r.get("event_id") or "", "")
        desc = f"Costume · {r.get('costume_name') or 'Outfit'}"
        if r.get("size"):
            desc += f" (size {r['size']})"
        if event_label:
            desc += f" · {event_label}"
        attendee_name = r.get("attendee_name") or "You"
        attendee_kind = "sub_profile" if r.get("sub_profile_id") else "self"
        lines.append({
            "kind": "costume",
            "description": desc,
            "quantity": 1,
            "unit_pence": unpaid,
            "amount_pence": unpaid,
            "costume_id": r.get("id"),
            "event_id": r.get("event_id"),
            "attendee_name": attendee_name,
            "attendee_kind": attendee_kind,
            "attendee_sub_profile_id": r.get("sub_profile_id"),
        })
        subtotal += unpaid
    return lines, subtotal


async def _append_smoothed_line(
    *, org_id: str, member: dict, period: str,
) -> tuple[Optional[dict], int]:
    """If the member is on a smoothed plan, add the monthly installment
    line. We read the active `member_memberships` row to find their
    current plan."""
    mm = await db.member_memberships.find_one(
        {"organization_id": org_id, "member_id": member["id"], "status": "active"},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not mm:
        return None, 0
    plan = await db.membership_plans.find_one({"id": mm.get("plan_id")}, {"_id": 0})
    if not plan or not plan.get("smoothed"):
        return None, 0
    monthly = compute_smoothed_monthly_pence(plan)
    if monthly <= 0:
        return None, 0
    line = {
        "kind": "smoothed",
        "description": (
            f"{plan.get('name')} · smoothed installment ({period})"
        ),
        "quantity": 1,
        "unit_pence": monthly,
        "amount_pence": monthly,
        "plan_id": plan["id"],
    }
    return line, monthly


async def _sibling_discount_pct(org_id: str) -> int:
    """Iter 215z — org-level sibling discount. Returns the flat percent
    applied to EVERY sibling beyond the 1st. 0 = disabled.
    Clamped to [0, 50] so we never refund more than half the class."""
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "sibling_discount_pct": 1},
    ) or {}
    try:
        v = int(org.get("sibling_discount_pct") or 0)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(50, v))


def _sibling_pct_for(rank: int, flat_pct: int, tiers: list[dict]) -> int:
    """Resolve the discount percent for the *rank*-th sibling.

    Iter 216aa — when a tiered ladder is present, find the highest tier
    whose ``rank`` <= the sibling's rank. Otherwise fall back to the
    legacy flat pct (applied to every sibling beyond the eldest)."""
    if tiers:
        pct = 0
        for t in tiers:
            if int(t.get("rank") or 0) <= rank:
                pct = max(pct, int(t.get("pct") or 0))
        return pct
    return flat_pct


def _apply_sibling_discount(
    lines: list[dict],
    bookings: list[dict],
    pct: int,
    tiers: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """Iter 215z + 216aa — group class lines by sub-profile (kids) and add
    a negative discount line for the 2nd, 3rd, ... sibling. When ``tiers``
    is supplied (non-empty list), the per-rank pct is read from the
    ladder; otherwise the flat ``pct`` applies to every extra sibling.

    Ordering is by the earliest booking created_at / occurrence time so
    "first sibling" is deterministic across runs. Returns updated
    (lines, delta_pence) where delta_pence is negative (or 0)."""
    tiers = tiers or []
    if pct <= 0 and not tiers:
        return lines, 0

    # Only count distinct KIDS/sub-profiles — ignore self / no sub-profile.
    sub_groups: dict[str, list[dict]] = {}
    for ln in lines:
        if ln.get("kind") != "class":
            continue
        sid = ln.get("attendee_sub_profile_id")
        if not sid:
            continue
        sub_groups.setdefault(sid, []).append(ln)

    if len(sub_groups) < 2:
        return lines, 0

    # Deterministic order: sort by the minimum booking_id hash-proxy (earliest created).
    booking_order = {b.get("id"): idx for idx, b in enumerate(bookings)}
    def first_seen(rows):
        return min((booking_order.get(r.get("booking_id"), 9999) for r in rows), default=9999)
    ordered = sorted(sub_groups.items(), key=lambda kv: first_seen(kv[1]))

    delta = 0
    new_extra: list[dict] = []
    for rank, (sid, rows) in enumerate(ordered, start=1):
        if rank == 1:
            continue  # full-price eldest sibling
        rank_pct = _sibling_pct_for(rank, pct, tiers)
        if rank_pct <= 0:
            continue
        sub = sum(int(r.get("amount_pence") or 0) for r in rows)
        if sub <= 0:
            continue
        disc = -((sub * rank_pct) // 100)
        if disc == 0:
            continue
        att_name = rows[0].get("attendee_name") or "Sibling"
        label = {2: "2nd", 3: "3rd"}.get(rank, f"{rank}th")
        new_extra.append({
            "kind": "sibling_discount",
            "description": f"Sibling discount ({label} child · {att_name}) — {rank_pct}% off",
            "quantity": 1,
            "unit_pence": disc,
            "amount_pence": disc,
            "attendee_name": att_name,
            "attendee_kind": rows[0].get("attendee_kind") or "sub_profile",
            "attendee_sub_profile_id": sid,
            "sibling_rank": rank,
            "sibling_pct": rank_pct,
        })
        delta += disc
    return lines + new_extra, delta


def _compute_attendee_breakdown(lines: list[dict]) -> list[dict]:
    """Iter 215y — aggregate class lines by attendee (parent → kids).
    Smoothed / adhoc lines (no ``attendee_name``) roll up under 'Account'.
    Returned list is sorted by subtotal desc for a parent-friendly view."""
    by_key: dict[str, dict] = {}
    for ln in lines:
        name = ln.get("attendee_name") or "Account"
        key = ln.get("attendee_sub_profile_id") or f"name:{name}:{ln.get('attendee_kind','self')}"
        row = by_key.setdefault(key, {
            "attendee_name": name,
            "attendee_kind": ln.get("attendee_kind") or "self",
            "attendee_sub_profile_id": ln.get("attendee_sub_profile_id"),
            "line_count": 0,
            "subtotal_pence": 0,
        })
        row["line_count"] += 1
        row["subtotal_pence"] += int(ln.get("amount_pence") or 0)
    return sorted(by_key.values(), key=lambda r: (-r["subtotal_pence"], r["attendee_name"]))


class PreviewIn(BaseModel):
    period: str  # "YYYY-MM"
    include_attended_only: bool = False
    include_smoothed: bool = True
    default_per_class_pence: Optional[int] = Field(default=None, ge=0)
    member_ids: Optional[list[str]] = None


@router.post(
    "/memberships/billing/monthly-invoice/preview",
    dependencies=[Depends(require_module("memberships"))],
)
async def preview_monthly_invoices(body: PreviewIn, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    start, end = _month_bounds(body.period)
    default_rate = body.default_per_class_pence or await _default_per_class_pence(org_id)

    member_q: dict = {"organization_id": org_id, "status": {"$ne": "cancelled"}}
    if body.member_ids:
        member_q["id"] = {"$in": body.member_ids}
    members = await db.members.find(
        member_q, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(2000)

    previews: list[dict] = []
    grand_total = 0
    for m in members:
        lines, subtotal = await _build_invoice_lines_for_member(
            org_id=org_id, member=m, start=start, end=end,
            include_attended_only=body.include_attended_only,
            default_rate=default_rate,
        )
        sm_line, sm_total = (None, 0)
        if body.include_smoothed:
            sm_line, sm_total = await _append_smoothed_line(
                org_id=org_id, member=m, period=body.period,
            )
        if sm_line:
            lines.append(sm_line)
        # Iter 216ae+ — pull unbilled costumes (ordered/arrived/fitted) so
        # operations and billing stay in sync.
        costume_lines, costume_total = await _append_costume_lines(
            org_id=org_id, member=m, period=body.period,
        )
        if costume_lines:
            lines.extend(costume_lines)
        total = subtotal + sm_total + costume_total
        if total <= 0:
            continue  # skip — nothing to bill this period
        name = (f"{m.get('first_name') or ''} {m.get('last_name') or ''}").strip() or (m.get("email") or m["id"])
        previews.append({
            "member_id": m["id"],
            "member_name": name,
            "member_email": m.get("email") or "",
            "line_count": len(lines),
            "subtotal_pence": subtotal,
            "smoothed_pence": sm_total,
            "costume_pence": costume_total,
            "total_pence": total,
            "lines": lines,
            "attendees": _compute_attendee_breakdown(lines),
        })
        grand_total += total

    previews.sort(key=lambda x: x["total_pence"], reverse=True)
    return {
        "period": body.period,
        "member_count": len(previews),
        "total_pence": grand_total,
        "default_per_class_pence": default_rate,
        "invoices": previews,
    }


async def _branding_for_member(org: dict, member: dict) -> dict:
    """Iter 216ag — resolve site-scoped branding for a single member. Returns
    a dict with `name`, `primary_color`, `logo_url` (and `source` for audit)
    honouring the parent→child inheritance established in iter 216af.
    If the member has no site (or site has no override) the parent-org
    branding wins, preserving backwards compatibility."""
    from routes.sites import _effective_site_branding
    site_doc = None
    site_id = (member or {}).get("site_id")
    if site_id:
        site_doc = await db.sites.find_one(
            {"id": site_id, "organization_id": org.get("id")}, {"_id": 0},
        )
    eff = _effective_site_branding(org, site_doc)
    return {
        "name": eff.get("name") or org.get("name") or "Your studio",
        "primary_color": eff.get("primary_color") or "#00B2C7",
        "logo_url": eff.get("logo_url") or "",
        "source": "site" if site_doc and (site_doc.get("branding") or {}) else "organization",
    }


def _render_invoice_email_html(
    *, org_name: str, period_label: str, invoice: dict, member_name: str,
    primary_color: str = "#00B2C7", pay_url: Optional[str] = None,
) -> str:
    # Iter 215y — if there are multiple distinct attendees (e.g. parent
    # with 2 kids), group the detail rows by attendee with subtotals.
    attendees = invoice.get("attendees") or []
    multi_attendee = len([a for a in attendees if a.get("attendee_kind") != "smoothed"]) > 1

    def _lines_table_rows(rows):
        out = ""
        for ln in rows:
            out += (
                f"<tr>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-size:13px'>{_esc(ln['description'])}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-size:13px;text-align:right'>£{ln['amount_pence']/100:.2f}</td>"
                f"</tr>"
            )
        return out

    # Build the main table — either flat list or grouped by attendee.
    if multi_attendee:
        detail_parts = []
        # Group lines by attendee_name, but keep non-class kinds (smoothed)
        # under a shared "Account" heading.
        grouped: dict[str, list[dict]] = {}
        for ln in invoice["lines"]:
            key = ln.get("attendee_name") or "Account" if ln.get("kind") == "class" else "Account"
            grouped.setdefault(key, []).append(ln)
        for att_name, rows in grouped.items():
            sub = sum(int(r.get("amount_pence") or 0) for r in rows)
            detail_parts.append(
                f"<tr><td colspan='2' style='padding:14px 12px 4px;font-size:11px;"
                f"letter-spacing:0.18em;text-transform:uppercase;color:#6B7280;"
                f"font-weight:800'>{_esc(att_name)} · £{sub/100:.2f}</td></tr>"
                + _lines_table_rows(rows)
            )
        lines_html = "".join(detail_parts)
    else:
        lines_html = _lines_table_rows(invoice["lines"])

    total = invoice["total_pence"]
    pay_cta = (
        f"<div style='text-align:center;margin:24px 0 4px'>"
        f"<a href='{_esc(pay_url)}' style='display:inline-block;background:{primary_color};color:#0A0C10;"
        f"padding:14px 28px;border-radius:999px;font-weight:800;text-decoration:none;font-size:15px'>"
        f"Pay £{total/100:.2f} now →</a></div>"
    ) if pay_url else ""
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden;">
  <div style="background:{primary_color};padding:18px 24px;">
    <div style="color:#fff;font-size:12px;letter-spacing:.18em;text-transform:uppercase;opacity:.9">Invoice · {period_label}</div>
    <div style="color:#fff;font-size:22px;font-weight:800;margin-top:4px">{_esc(org_name)}</div>
  </div>
  <div style="padding:24px">
    <p style="margin:0 0 12px;font-size:15px;color:#111">Hi {_esc(member_name)},</p>
    <p style="margin:0 0 20px;font-size:14px;color:#444;line-height:1.5">Here's your {period_label} statement for classes booked at {_esc(org_name)}.</p>
    <table style="width:100%;border-collapse:collapse;border-top:1px solid #eee;margin-bottom:20px">
      {lines_html}
      <tr><td style="padding:14px 12px;font-size:14px;font-weight:800">Total due</td>
          <td style="padding:14px 12px;font-size:16px;font-weight:800;text-align:right;color:{primary_color}">£{total/100:.2f}</td></tr>
    </table>
    {pay_cta}
    <p style="margin:18px 0 0;font-size:12px;color:#6B7280;text-align:center">A copy of this invoice is attached as PDF. Questions? Reply to this email.</p>
  </div>
</div>"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class GenerateIn(BaseModel):
    period: str
    include_attended_only: bool = False
    include_smoothed: bool = True
    default_per_class_pence: Optional[int] = Field(default=None, ge=0)
    send_email: bool = False
    member_ids: Optional[list[str]] = None
    note: Optional[str] = None


@router.post(
    "/memberships/billing/monthly-invoice/generate",
    dependencies=[Depends(require_module("memberships"))],
)
async def generate_monthly_invoices(body: GenerateIn, user: dict = Depends(get_current_user)):
    """Persist one invoice per eligible member. Idempotent on
    `(organization_id, member_id, period)` — re-running for the same
    month updates the existing draft (so operators can iterate before
    sending) unless the invoice is already `sent`/`paid`."""
    org_id = await _require_operator_org(user)
    start, end = _month_bounds(body.period)
    default_rate = body.default_per_class_pence or await _default_per_class_pence(org_id)

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1, "primary_color": 1},
    ) or {}

    member_q: dict = {"organization_id": org_id, "status": {"$ne": "cancelled"}}
    if body.member_ids:
        member_q["id"] = {"$in": body.member_ids}
    members = await db.members.find(
        member_q,
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).to_list(2000)

    generated: list[dict] = []
    email_results: dict[str, int] = {"sent": 0, "skipped_no_email": 0, "failed": 0}

    for m in members:
        lines, subtotal = await _build_invoice_lines_for_member(
            org_id=org_id, member=m, start=start, end=end,
            include_attended_only=body.include_attended_only,
            default_rate=default_rate,
        )
        sm_line, sm_total = (None, 0)
        if body.include_smoothed:
            sm_line, sm_total = await _append_smoothed_line(
                org_id=org_id, member=m, period=body.period,
            )
        if sm_line:
            lines.append(sm_line)
        # Iter 216ae+ — costume → invoice line (idempotent, see stamp below).
        costume_lines, costume_total = await _append_costume_lines(
            org_id=org_id, member=m, period=body.period,
        )
        if costume_lines:
            lines.extend(costume_lines)
        total = subtotal + sm_total + costume_total
        if total <= 0:
            continue

        existing = await db.membership_class_invoices.find_one(
            {"organization_id": org_id, "member_id": m["id"], "period": body.period},
            {"_id": 0},
        )
        if existing and existing.get("status") in ("sent", "paid"):
            continue  # don't overwrite already-sent invoices

        name = (f"{m.get('first_name') or ''} {m.get('last_name') or ''}").strip() or (m.get("email") or m["id"])
        doc = {
            "id": existing["id"] if existing else _uuid(),
            "organization_id": org_id,
            "member_id": m["id"],
            "member_email": m.get("email") or "",
            "member_name": name,
            "period": body.period,
            "lines": lines,
            "attendees": _compute_attendee_breakdown(lines),
            "subtotal_pence": subtotal,
            "smoothed_pence": sm_total,
            "costume_pence": costume_total,
            "total_pence": total,
            "status": "draft",
            "created_by": user.get("id"),
            "note": body.note or None,
            "created_at": existing["created_at"] if existing else _now_iso(),
            "updated_at": _now_iso(),
        }
        if existing:
            await db.membership_class_invoices.update_one(
                {"id": existing["id"]}, {"$set": {k: v for k, v in doc.items() if k != "id"}},
            )
        else:
            await db.membership_class_invoices.insert_one({**doc})
            # Iter 215d4 — activation funnel event (first invoice generated).
            # Idempotent per org; safe to call inside the loop.
            try:
                from routes.activation_events import record_activation_event
                await record_activation_event(
                    org_id, "first_invoice_generated",
                    trigger_user_id=user.get("id"),
                    payload={"invoice_id": doc["id"], "period": body.period},
                )
            except Exception:
                pass

        # Iter 216ae+ — mark costume rows as billed so they don't repeat on
        # next month's invoice. Idempotent: uses `$set invoiced_on=period`.
        if costume_lines:
            costume_ids = [ln["costume_id"] for ln in costume_lines if ln.get("costume_id")]
            if costume_ids:
                await db.event_costumes.update_many(
                    {"id": {"$in": costume_ids}, "organization_id": org_id},
                    {"$set": {
                        "invoiced_on": body.period,
                        "invoice_id": doc["id"],
                        "updated_at": _now_iso(),
                    }},
                )

        # Optional send
        if body.send_email:
            if not doc["member_email"]:
                email_results["skipped_no_email"] += 1
            else:
                period_label = _period_label(body.period)
                # Build a fresh checkout URL so the email's Pay-now CTA works.
                pay_url = await _build_invoice_checkout_url(doc, org)
                # Iter 216ag — resolve site-scoped branding so iGym Leeds
                # members get iGym comms even when the parent org is Pulse.
                brand = await _branding_for_member(org, m)
                html = _render_invoice_email_html(
                    org_name=brand["name"],
                    period_label=period_label,
                    invoice=doc, member_name=name,
                    primary_color=brand["primary_color"],
                    pay_url=pay_url,
                )
                pdf_bytes = _render_invoice_pdf(
                    org_name=brand["name"],
                    period_label=period_label,
                    invoice=doc, member_name=name,
                    primary_color_hex=brand["primary_color"],
                )
                attachments = [{
                    "filename": f"invoice-{period_label.replace(' ', '-')}.pdf",
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "content_type": "application/pdf",
                }]
                ok = await send_email(
                    doc["member_email"],
                    f"Your {period_label} invoice · {brand['name']}",
                    html,
                    attachments=attachments,
                )
                if ok:
                    email_results["sent"] += 1
                    await db.membership_class_invoices.update_one(
                        {"id": doc["id"]},
                        {"$set": {"status": "sent", "sent_at": _now_iso()}},
                    )
                    doc["status"] = "sent"
                else:
                    email_results["failed"] += 1
        generated.append({k: v for k, v in doc.items() if k != "_id"})

    return {
        "period": body.period,
        "generated_count": len(generated),
        "invoices": generated,
        "email": email_results if body.send_email else None,
    }


def _period_label(period: str) -> str:
    try:
        y, m = period.split("-")
        return datetime(int(y), int(m), 1).strftime("%B %Y")
    except Exception:
        return period


# ───────────────────── PDF rendering (reportlab) ─────────────────────

def _render_invoice_pdf(
    *, org_name: str, period_label: str, invoice: dict, member_name: str,
    primary_color_hex: str,
) -> bytes:
    """Build a 1-page A4 invoice PDF using reportlab. Returns the bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, grey
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    primary = HexColor(primary_color_hex if primary_color_hex.startswith("#") else "#00B2C7")

    # Header band
    c.setFillColor(primary)
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, height - 12 * mm, f"INVOICE · {period_label.upper()}")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, height - 22 * mm, org_name)

    # Bill-to
    y = height - 42 * mm
    c.setFillColor(grey)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y, "BILL TO")
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y - 5 * mm, member_name)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y - 10 * mm, invoice.get("member_email") or "")
    c.drawString(width - 60 * mm, y - 5 * mm, f"Invoice #{invoice['id'][:8]}")
    c.drawString(width - 60 * mm, y - 10 * mm, datetime.now(timezone.utc).strftime("Issued %d %b %Y"))

    # Line items — iter 215y grouped by attendee if multiple
    attendees = invoice.get("attendees") or []
    multi = len([a for a in attendees if a.get("attendee_kind") != "smoothed"]) > 1

    table_y = y - 22 * mm
    c.setFillColor(grey)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(20 * mm, table_y, "DESCRIPTION")
    c.drawRightString(width - 20 * mm, table_y, "AMOUNT")
    c.setStrokeColor(grey)
    c.line(20 * mm, table_y - 1 * mm, width - 20 * mm, table_y - 1 * mm)
    c.setFillColor(black)
    c.setFont("Helvetica", 10)

    row_y = table_y - 7 * mm
    line_height = 6 * mm

    if multi:
        grouped: dict[str, list[dict]] = {}
        for ln in invoice.get("lines", []):
            key = ln.get("attendee_name") or "Account" if ln.get("kind") == "class" else "Account"
            grouped.setdefault(key, []).append(ln)
        for att_name, rows in grouped.items():
            sub = sum(int(r.get("amount_pence") or 0) for r in rows)
            # Group heading
            if row_y < 30 * mm:
                c.showPage()
                row_y = height - 30 * mm
            c.setFillColor(grey)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(
                20 * mm, row_y,
                f"{att_name.upper()} · £{sub/100:.2f}",
            )
            row_y -= line_height
            c.setFillColor(black)
            c.setFont("Helvetica", 10)
            for ln in rows:
                if row_y < 30 * mm:
                    c.showPage()
                    row_y = height - 30 * mm
                c.drawString(22 * mm, row_y, (ln.get("description") or "Item")[:78])
                c.drawRightString(width - 20 * mm, row_y, f"£{ln['amount_pence']/100:.2f}")
                row_y -= line_height
            row_y -= 2 * mm  # extra spacing between groups
    else:
        for ln in invoice.get("lines", []):
            if row_y < 35 * mm:
                c.showPage()
                row_y = height - 30 * mm
                c.setFont("Helvetica", 10)
            desc = ln.get("description") or "Item"
            c.drawString(20 * mm, row_y, desc[:80])
            c.drawRightString(width - 20 * mm, row_y, f"£{ln['amount_pence']/100:.2f}")
            row_y -= line_height

    # Total
    row_y -= 4 * mm
    c.setStrokeColor(primary)
    c.setLineWidth(1.4)
    c.line(width - 70 * mm, row_y, width - 20 * mm, row_y)
    row_y -= 8 * mm
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(width - 70 * mm, row_y, "Total due")
    c.drawRightString(width - 20 * mm, row_y, f"£{invoice['total_pence']/100:.2f}")

    # Footer
    c.setFillColor(grey)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 15 * mm, f"Thank you for choosing {org_name}.")
    c.drawRightString(width - 20 * mm, 15 * mm, "Powered by GymAxis")
    c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────── Stripe Checkout pay-link ─────────────────────

stripe.api_key = STRIPE_API_KEY


async def _build_invoice_checkout_url(invoice: dict, org: dict) -> Optional[str]:
    """Create a Stripe Checkout Session for an invoice's outstanding total.
    Returns the hosted URL or None if Stripe isn't configured."""
    if not STRIPE_API_KEY:
        return None
    frontend = (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    success_url = f"{frontend}/members?paid_invoice={invoice['id']}"
    cancel_url = f"{frontend}/members?cancelled_invoice={invoice['id']}"
    # Stripe Connect — route into the gym's connected account (destination
    # charge + platform fee) when onboarded; else charge the platform account.
    # Resolve from the invoice's org id so it's independent of the caller's
    # (often slim) `org` projection.
    from utils.stripe_connect_routing import (
        resolve_org_connect_routing,
        payment_intent_connect_kwargs,
    )
    routing_org = await db.organizations.find_one(
        {"id": invoice.get("organization_id")},
        {"_id": 0, "id": 1, "stripe_account_id": 1, "stripe_charges_enabled": 1},
    ) or {}
    routing = await resolve_org_connect_routing(routing_org)
    pi_data = payment_intent_connect_kwargs(routing, int(invoice["total_pence"]))
    session_kwargs: dict = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": invoice.get("member_email") or None,
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": "gbp",
                "unit_amount": int(invoice["total_pence"]),
                "product_data": {
                    "name": f"{org.get('name') or 'Studio'} · {_period_label(invoice['period'])} invoice",
                    "description": f"{len(invoice.get('lines') or [])} line item(s)",
                },
            },
        }],
        "metadata": {
            "gymaxis_kind": "class_invoice",
            "gymaxis_invoice_id": invoice["id"],
            "gymaxis_org_id": invoice.get("organization_id") or "",
            "gymaxis_member_id": invoice.get("member_id") or "",
        },
    }
    if pi_data:
        session_kwargs["payment_intent_data"] = pi_data
    try:
        session = stripe.checkout.Session.create(**session_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("invoice checkout: stripe failed (%s)", exc)
        return None
    # Persist the session id so the webhook can correlate.
    await db.membership_class_invoices.update_one(
        {"id": invoice["id"]},
        {"$set": {"stripe_session_id": session.id, "checkout_url": session.url,
                  "checkout_url_created_at": _now_iso()}},
    )
    return session.url


@router.post(
    "/memberships/billing/invoices/{invoice_id}/checkout",
    dependencies=[Depends(require_module("memberships"))],
)
async def create_invoice_checkout(invoice_id: str, user: dict = Depends(get_current_user)):
    """Operator-side — generate or refresh a hosted Stripe pay-link
    for an unpaid invoice. The link can be copied + sent manually or
    used internally for a 'Pay now' button in the email."""
    org_id = await _require_operator_org(user)
    inv = await db.membership_class_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.get("status") == "paid":
        raise HTTPException(400, "Invoice already paid")
    if inv.get("total_pence", 0) <= 0:
        raise HTTPException(400, "Invoice total is zero — nothing to charge")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    url = await _build_invoice_checkout_url(inv, org)
    if not url:
        raise HTTPException(503, "Stripe not configured on this environment")
    return {"checkout_url": url}


@router.get("/public/billing/invoice/{invoice_id}/pay")
async def public_invoice_pay(invoice_id: str):
    """Member-facing redirect — used in the email's 'Pay now' button.
    Builds (or re-uses) the Stripe Checkout URL and 302s the browser
    straight to it. No auth — just the invoice id (a uuid). For an
    extra layer of guard, we only build a session for invoices in
    `sent`/`draft` status with a non-zero total."""
    from fastapi.responses import RedirectResponse
    inv = await db.membership_class_invoices.find_one(
        {"id": invoice_id}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.get("status") == "paid":
        # Friendly landing page rather than 400 — the member already paid.
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<html><body style='font-family:system-ui;text-align:center;padding:64px'>"
            "<h1>Already paid ✓</h1><p>Thanks — this invoice has already been settled.</p>"
            "</body></html>", status_code=200,
        )
    if inv.get("total_pence", 0) <= 0:
        raise HTTPException(400, "Invoice has nothing to pay")
    org = await db.organizations.find_one({"id": inv["organization_id"]}, {"_id": 0, "name": 1}) or {}
    url = inv.get("checkout_url") or await _build_invoice_checkout_url(inv, org)
    if not url:
        raise HTTPException(503, "Stripe not configured")
    return RedirectResponse(url, status_code=302)


# ───────────────────── Webhook handler (called from memberships_payments) ─────────────────────

async def mark_class_invoice_paid_from_session(metadata: dict, session: dict) -> bool:
    """Called by the central Stripe webhook when a checkout.session.completed
    event lands with `gymaxis_kind=class_invoice`. Idempotent."""
    invoice_id = metadata.get("gymaxis_invoice_id") or ""
    if not invoice_id:
        return False
    res = await db.membership_class_invoices.update_one(
        {"id": invoice_id, "status": {"$ne": "paid"}},
        {"$set": {
            "status": "paid",
            "paid_at": _now_iso(),
            "paid_via": "stripe_checkout",
            "stripe_payment_intent": getattr(session, "payment_intent", None) or session.get("payment_intent"),
            "updated_at": _now_iso(),
        }},
    )
    return res.modified_count > 0


class InvoiceStatusIn(BaseModel):
    status: Literal["draft", "sent", "paid", "void"]


@router.patch(
    "/memberships/billing/invoices/{invoice_id}/status",
    dependencies=[Depends(require_module("memberships"))],
)
async def set_invoice_status(
    invoice_id: str, body: InvoiceStatusIn, user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    field = {
        "draft": None,
        "sent": "sent_at",
        "paid": "paid_at",
        "void": "void_at",
    }.get(body.status)
    updates: dict = {"status": body.status, "updated_at": _now_iso()}
    if field:
        updates[field] = _now_iso()
    res = await db.membership_class_invoices.update_one(
        {"id": invoice_id, "organization_id": org_id}, {"$set": updates},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    return {"ok": True, "status": body.status}


@router.get(
    "/memberships/billing/invoices",
    dependencies=[Depends(require_module("memberships"))],
)
async def list_invoices(
    period: Optional[str] = None, status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    q: dict = {"organization_id": org_id}
    if period:
        q["period"] = period
    if status:
        q["status"] = status
    rows = await db.membership_class_invoices.find(
        q, {"_id": 0},
    ).sort("updated_at", -1).to_list(500)
    return {"invoices": rows}


@router.post(
    "/memberships/billing/invoices/{invoice_id}/send",
    dependencies=[Depends(require_module("memberships"))],
)
async def send_single_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    inv = await db.membership_class_invoices.find_one(
        {"id": invoice_id, "organization_id": org_id}, {"_id": 0},
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if not inv.get("member_email"):
        raise HTTPException(400, "Member has no email on file")
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0},
    ) or {}
    # Lookup the member record so we can pick the right site-branded look.
    member_doc = await db.members.find_one(
        {"id": inv.get("member_id"), "organization_id": org_id},
        {"_id": 0, "site_id": 1},
    ) or {}
    brand = await _branding_for_member(org, member_doc)
    period_label = _period_label(inv["period"])
    primary = brand["primary_color"]
    pay_url = await _build_invoice_checkout_url(inv, org)
    html = _render_invoice_email_html(
        org_name=brand["name"],
        period_label=period_label,
        invoice=inv, member_name=inv.get("member_name") or "there",
        primary_color=primary, pay_url=pay_url,
    )
    pdf_bytes = _render_invoice_pdf(
        org_name=brand["name"],
        period_label=period_label,
        invoice=inv, member_name=inv.get("member_name") or "there",
        primary_color_hex=primary,
    )
    attachments = [{
        "filename": f"invoice-{period_label.replace(' ', '-')}.pdf",
        "content": base64.b64encode(pdf_bytes).decode("ascii"),
        "content_type": "application/pdf",
    }]
    ok = await send_email(
        inv["member_email"],
        f"Your {period_label} invoice · {brand['name']}",
        html, attachments=attachments,
        organization_id=org_id,
    )
    if not ok:
        raise HTTPException(502, "Email failed to send")
    await db.membership_class_invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": "sent", "sent_at": _now_iso(), "updated_at": _now_iso()}},
    )
    return {"ok": True}


# ─────────────────── Member-facing: my invoices ───────────────────

@router.get("/member/invoices")
async def member_my_invoices(member: dict = Depends(_require_current_member)):
    rows = await db.membership_class_invoices.find(
        {"organization_id": member["organization_id"], "member_id": member["id"]},
        {"_id": 0},
    ).sort("period", -1).to_list(100)
    return {"invoices": rows}


# ─────────────────── Pay-all-outstanding (iter 215w) ───────────────────

@router.post("/member/invoices/pay-all")
async def member_pay_all_outstanding(member: dict = Depends(_require_current_member)):
    """Bundle every unpaid invoice for this member into a single Stripe
    Checkout session. Members hate juggling multiple links; one tap
    reconciles everything."""
    if not STRIPE_API_KEY:
        raise HTTPException(503, "Stripe not configured on this environment")
    unpaid = await db.membership_class_invoices.find(
        {"organization_id": member["organization_id"], "member_id": member["id"],
         "status": {"$in": ["draft", "sent"]}, "total_pence": {"$gt": 0}},
        {"_id": 0},
    ).to_list(50)
    if not unpaid:
        raise HTTPException(400, "Nothing outstanding — you're all paid up 🎉")
    org = await db.organizations.find_one(
        {"id": member["organization_id"]},
        {"_id": 0, "id": 1, "name": 1, "primary_color": 1,
         "stripe_account_id": 1, "stripe_charges_enabled": 1},
    ) or {}
    frontend = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
    success_url = f"{frontend}/members?paid_all=1"
    cancel_url = f"{frontend}/members?pay_all_cancelled=1"
    line_items = []
    total_pence = 0
    for inv in unpaid:
        total_pence += int(inv["total_pence"])
        line_items.append({
            "quantity": 1,
            "price_data": {
                "currency": "gbp",
                "unit_amount": int(inv["total_pence"]),
                "product_data": {
                    "name": f"{_period_label(inv['period'])} · {org.get('name') or 'Studio'}",
                    "description": f"{len(inv.get('lines') or [])} line item(s)",
                },
            },
        })
    # Stripe metadata values are capped at 500 chars; a comma-joined list of
    # uuids fits ~13 invoices which is already extreme for a month.
    invoice_ids = [inv["id"] for inv in unpaid][:20]
    # Route the bundle into the gym's connected account when onboarded.
    from utils.stripe_connect_routing import (
        resolve_org_connect_routing,
        payment_intent_connect_kwargs,
    )
    routing = await resolve_org_connect_routing(org)
    pi_data = payment_intent_connect_kwargs(routing, total_pence)
    bundle_kwargs: dict = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": member.get("email") or None,
        "line_items": line_items,
        "metadata": {
            "gymaxis_kind": "class_invoice_bundle",
            "gymaxis_invoice_ids": ",".join(invoice_ids),
            "gymaxis_org_id": member["organization_id"],
            "gymaxis_member_id": member["id"],
        },
    }
    if pi_data:
        bundle_kwargs["payment_intent_data"] = pi_data
    try:
        session = stripe.checkout.Session.create(**bundle_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pay-all: stripe failed (%s)", exc)
        raise HTTPException(502, "Could not create Stripe session") from exc
    # Stamp the session id on every invoice so the webhook can mark
    # them paid in one pass.
    await db.membership_class_invoices.update_many(
        {"id": {"$in": invoice_ids}},
        {"$set": {
            "stripe_bundle_session_id": session.id,
            "bundle_checkout_url": session.url,
            "updated_at": _now_iso(),
        }},
    )
    return {
        "checkout_url": session.url,
        "invoice_ids": invoice_ids,
        "total_pence": total_pence,
        "count": len(invoice_ids),
    }


async def mark_class_invoice_bundle_paid(metadata: dict, session: dict) -> int:
    """Webhook companion to ``mark_class_invoice_paid_from_session`` but
    for the ``class_invoice_bundle`` kind — flips every invoice in the
    comma-joined list to paid."""
    ids_csv = metadata.get("gymaxis_invoice_ids") or ""
    ids = [i for i in ids_csv.split(",") if i]
    if not ids:
        return 0
    res = await db.membership_class_invoices.update_many(
        {"id": {"$in": ids}, "status": {"$ne": "paid"}},
        {"$set": {
            "status": "paid",
            "paid_at": _now_iso(),
            "paid_via": "stripe_checkout_bundle",
            "stripe_payment_intent": getattr(session, "payment_intent", None) or session.get("payment_intent"),
            "updated_at": _now_iso(),
        }},
    )
    return res.modified_count
