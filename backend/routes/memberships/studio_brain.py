"""Studio Brain — Phase E (iter 216ad).

Four high-leverage AI/analytics endpoints that complement the existing
``memberships_ai.py`` (demand forecast, pricing, underperformers):

  GET /api/memberships/studio/retention-risk
      → Per-attendee (member or sub-profile) attendance trend with a
        risk score, churn band, and the "why" (reasons array). Pure
        heuristic — fast & explainable; no LLM needed.

  GET /api/memberships/studio/occupancy-heatmap?weeks=4
      → 7-day × time-bucket grid of average capacity utilisation,
        ready for a frontend heat-map render.

  GET /api/memberships/studio/timetable-suggestions
      → AI-drafted timetable optimisation suggestions (add a slot,
        drop a slot, retime a slot) using Claude Haiku via
        emergentintegrations. Heuristic seed → LLM expansion → JSON.

  GET /api/memberships/studio/boardroom
      → One-call boardroom dashboard composing: 30-day revenue,
        retention summary, occupancy summary, top opportunities and
        the headline AI advice for the next 30 days.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.memberships.helpers import _require_operator_org

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-studio-brain"])


# ─────────────────────────────────────────────────────────────────
# Retention risk
# ─────────────────────────────────────────────────────────────────

def _band_for_risk(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


@router.get(
    "/memberships/studio/retention-risk",
    dependencies=[Depends(require_module("memberships"))],
)
async def retention_risk(
    weeks: int = Query(8, ge=2, le=26),
    limit: int = Query(50, ge=1, le=500),
    user=Depends(get_current_user),
):
    """Per-attendee retention-risk leaderboard.

    Signals (weighted):
      • Days since last attended (× 1.5, capped 45)
      • Attendance drop ratio = (recent_half / earlier_half) — < 0.6 → 25 pts
      • Streak of cancelled bookings last 14d (× 8 each, capped 24)
    """
    org_id = await _require_operator_org(user)
    now = datetime.now(timezone.utc)
    horizon_start = (now - timedelta(weeks=weeks)).isoformat()
    half_pivot = (now - timedelta(weeks=weeks // 2)).isoformat()

    bookings = await db.class_bookings.find(
        {"organization_id": org_id, "created_at": {"$gte": horizon_start}},
        {"_id": 0, "attendee_name": 1, "attendee_sub_profile_id": 1,
         "member_id": 1, "occurrence_id": 1, "status": 1, "created_at": 1,
         "attended_at": 1, "cancelled_at": 1},
    ).to_list(20000)

    occs = await db.class_occurrences.find(
        {"organization_id": org_id, "starts_at": {"$gte": horizon_start}},
        {"_id": 0, "id": 1, "starts_at": 1, "name": 1, "template_id": 1},
    ).to_list(20000)
    occ_by_id = {o["id"]: o for o in occs}

    # Group by (member_id, sub_profile_id, attendee_name).
    by_attendee: dict[tuple, dict] = {}
    for b in bookings:
        key = (b.get("member_id") or "", b.get("attendee_sub_profile_id") or "",
               b.get("attendee_name") or "")
        bucket = by_attendee.setdefault(key, {
            "member_id": b.get("member_id"),
            "sub_profile_id": b.get("attendee_sub_profile_id"),
            "attendee_name": b.get("attendee_name") or "Member",
            "early_count": 0, "late_count": 0,
            "last_attended_at": None,
            "cancelled_14d": 0,
            "total": 0,
        })
        bucket["total"] += 1
        occ = occ_by_id.get(b.get("occurrence_id"))
        ts = (b.get("attended_at") or b.get("created_at")
              or (occ or {}).get("starts_at"))
        if not ts:
            continue
        if ts < half_pivot:
            bucket["early_count"] += 1
        else:
            bucket["late_count"] += 1
        if b.get("attended_at"):
            cur = bucket["last_attended_at"]
            if cur is None or ts > cur:
                bucket["last_attended_at"] = ts
        # Recent cancellations
        if b.get("status") == "cancelled" and (b.get("cancelled_at") or "") >= (
            (now - timedelta(days=14)).isoformat()
        ):
            bucket["cancelled_14d"] += 1

    rows: list[dict[str, Any]] = []
    for bucket in by_attendee.values():
        if bucket["total"] < 2:
            continue  # too few datapoints for a trend
        score = 0.0
        reasons: list[str] = []

        # Days since last attended.
        days_since = None
        if bucket["last_attended_at"]:
            try:
                last_dt = datetime.fromisoformat(
                    bucket["last_attended_at"].replace("Z", "+00:00"),
                )
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_since = max(0, (now - last_dt).days)
            except Exception:
                pass
        if days_since is not None:
            score += min(45, days_since * 1.5)
            if days_since >= 21:
                reasons.append(f"Hasn't attended in {days_since} days")

        # Attendance drop in second half.
        if bucket["early_count"] > 0:
            recent_ratio = bucket["late_count"] / max(1, bucket["early_count"])
            if recent_ratio < 0.6:
                score += 25
                reasons.append(
                    f"Attendance dropped {round((1 - recent_ratio) * 100)}% "
                    f"vs first half of the {weeks}-week window"
                )
            elif recent_ratio > 1.4:
                # Engagement up — give them credit.
                score -= 8

        # Cancellation streak.
        if bucket["cancelled_14d"] >= 2:
            bump = min(24, bucket["cancelled_14d"] * 8)
            score += bump
            reasons.append(
                f"{bucket['cancelled_14d']} cancellations in last 14 days"
            )

        score_int = max(0, min(100, int(round(score))))
        if score_int < 10 and not reasons:
            continue  # skip "obviously fine" attendees
        rows.append({
            **bucket,
            "score": score_int,
            "band": _band_for_risk(score_int),
            "reasons": reasons,
            "days_since_last_attended": days_since,
            "weeks_window": weeks,
        })

    rows.sort(key=lambda r: -r["score"])
    rows = rows[:limit]
    summary = {
        "high":   sum(1 for r in rows if r["band"] == "high"),
        "medium": sum(1 for r in rows if r["band"] == "medium"),
        "low":    sum(1 for r in rows if r["band"] == "low"),
        "scored_attendees": len(rows),
        "weeks_window": weeks,
    }
    return {"rows": rows, "summary": summary,
            "scored_at": now.isoformat()}


# ─────────────────────────────────────────────────────────────────
# Occupancy heatmap
# ─────────────────────────────────────────────────────────────────

_HEATMAP_BUCKETS = [
    ("06:00", 6, 9),
    ("09:00", 9, 12),
    ("12:00", 12, 15),
    ("15:00", 15, 18),
    ("18:00", 18, 21),
    ("21:00", 21, 24),
]


@router.get(
    "/memberships/studio/occupancy-heatmap",
    dependencies=[Depends(require_module("memberships"))],
)
async def occupancy_heatmap(
    weeks: int = Query(4, ge=1, le=12),
    user=Depends(get_current_user),
):
    """Average capacity utilisation per day-of-week × time-bucket."""
    org_id = await _require_operator_org(user)
    now = datetime.now(timezone.utc)
    horizon = (now - timedelta(weeks=weeks)).isoformat()
    occs = await db.class_occurrences.find(
        {"organization_id": org_id, "starts_at": {"$gte": horizon},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "starts_at": 1, "capacity": 1, "bookings_count": 1, "name": 1},
    ).to_list(20000)

    grid: dict[str, dict[str, dict]] = {}
    for o in occs:
        try:
            dt = datetime.fromisoformat(o["starts_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        dow = dt.strftime("%a")  # Mon, Tue, …
        hour = dt.hour
        bucket_label = next(
            (lbl for lbl, lo, hi in _HEATMAP_BUCKETS if lo <= hour < hi),
            None,
        )
        if not bucket_label:
            continue
        cap = max(1, int(o.get("capacity") or 0))
        booked = int(o.get("bookings_count") or 0)
        cell = grid.setdefault(dow, {}).setdefault(bucket_label, {
            "occurrences": 0, "capacity": 0, "booked": 0,
        })
        cell["occurrences"] += 1
        cell["capacity"] += cap
        cell["booked"] += booked

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cells = []
    hottest = None
    coldest = None
    for d in days:
        for lbl, _lo, _hi in _HEATMAP_BUCKETS:
            cell = (grid.get(d) or {}).get(lbl) or {}
            occ = cell.get("occurrences", 0)
            cap_total = cell.get("capacity", 0)
            booked = cell.get("booked", 0)
            pct = round(booked / cap_total * 100) if cap_total else 0
            row = {
                "day": d, "bucket": lbl, "occurrences": occ,
                "capacity_total": cap_total, "booked": booked,
                "utilisation_pct": pct,
            }
            cells.append(row)
            if occ > 0:
                if hottest is None or pct > hottest["utilisation_pct"]:
                    hottest = row
                if coldest is None or pct < coldest["utilisation_pct"]:
                    coldest = row

    return {
        "cells": cells, "days": days,
        "buckets": [b[0] for b in _HEATMAP_BUCKETS],
        "weeks_window": weeks,
        "hottest": hottest, "coldest": coldest,
    }


# ─────────────────────────────────────────────────────────────────
# AI timetable optimisation suggestions
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/memberships/studio/timetable-suggestions",
    dependencies=[Depends(require_module("memberships"))],
)
async def timetable_suggestions(user=Depends(get_current_user)):
    """Heuristic seed → Claude Haiku (if key present) → structured array."""
    org_id = await _require_operator_org(user)
    heatmap = await occupancy_heatmap(weeks=4, user=user)
    cells = heatmap["cells"]
    busy = sorted(
        [c for c in cells if c["occurrences"] > 0 and c["utilisation_pct"] >= 80],
        key=lambda c: -c["utilisation_pct"],
    )[:5]
    quiet = sorted(
        [c for c in cells if c["occurrences"] > 0 and c["utilisation_pct"] < 40],
        key=lambda c: c["utilisation_pct"],
    )[:5]

    seed_suggestions: list[dict] = []
    for b in busy:
        seed_suggestions.append({
            "kind": "open_extra_slot",
            "day": b["day"], "bucket": b["bucket"],
            "rationale": f"{b['utilisation_pct']}% capacity over the last 4 weeks "
                         f"({b['booked']}/{b['capacity_total']}). Open another slot.",
            "impact": "Capture rejected bookings & waitlist demand.",
        })
    for q in quiet:
        seed_suggestions.append({
            "kind": "consolidate_or_drop",
            "day": q["day"], "bucket": q["bucket"],
            "rationale": f"Only {q['utilisation_pct']}% utilisation "
                         f"({q['booked']}/{q['capacity_total']}). "
                         f"Consider merging with a busier slot or dropping it.",
            "impact": "Free instructor hours for higher-value classes.",
        })

    # Try LLM for a richer narrative; fall back gracefully.
    import os
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
    if not api_key or not seed_suggestions:
        return {"suggestions": seed_suggestions, "model": "heuristic_only",
                "generated_at": datetime.now(timezone.utc).isoformat()}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        prompt = (
            "You're a studio operations advisor. Given these heuristic seed "
            "suggestions about timetable optimisation, return a JSON array "
            "with objects of shape {day, bucket, kind, rationale, impact, "
            "confidence: 'low'|'med'|'high'}. Keep rationales under 200 chars, "
            "merge duplicates, and add 0-2 *new* ideas if the data clearly "
            "supports them. Output ONLY a JSON array, no commentary.\n\n"
            f"Seeds:\n{json.dumps(seed_suggestions, indent=2)}"
        )
        chat = LlmChat(
            api_key=api_key,
            session_id=f"timetable-{org_id}",
            system_message="You output JSON arrays only.",
        ).with_model("anthropic", "claude-haiku-4-5")
        raw = await chat.send_message(UserMessage(text=prompt))
        # Strip code-fences if present.
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.strip("`")
            if clean.lower().startswith("json"):
                clean = clean[4:].lstrip()
        suggestions = json.loads(clean)
        if not isinstance(suggestions, list):
            raise ValueError("LLM returned non-list payload")
    except Exception:
        logger.warning("LLM timetable suggestion failed, returning heuristic", exc_info=True)
        suggestions = seed_suggestions
        return {"suggestions": suggestions, "model": "heuristic_fallback",
                "generated_at": datetime.now(timezone.utc).isoformat()}

    return {"suggestions": suggestions, "model": "claude_haiku_4_5",
            "generated_at": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────
# Boardroom dashboard
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/memberships/studio/boardroom",
    dependencies=[Depends(require_module("memberships"))],
)
async def boardroom(user=Depends(get_current_user)):
    """Single-call exec summary for studio owners."""
    org_id = await _require_operator_org(user)
    now = datetime.now(timezone.utc)
    horizon_30 = (now - timedelta(days=30)).isoformat()
    horizon_60 = (now - timedelta(days=60)).isoformat()

    # Member growth.
    members_total = await db.members.count_documents(
        {"organization_id": org_id, "status": {"$ne": "cancelled"}},
    )
    new_30d = await db.members.count_documents(
        {"organization_id": org_id, "created_at": {"$gte": horizon_30}},
    )
    new_30_to_60d = await db.members.count_documents(
        {"organization_id": org_id, "created_at": {"$gte": horizon_60, "$lt": horizon_30}},
    )
    growth_pct = None
    if new_30_to_60d > 0:
        growth_pct = round(((new_30d - new_30_to_60d) / new_30_to_60d) * 100, 1)

    # Revenue (paid invoices, last 30 days).
    paid = await db.member_invoices.find(
        {"organization_id": org_id, "status": "paid",
         "paid_at": {"$gte": horizon_30}},
        {"_id": 0, "amount_pence": 1},
    ).to_list(20000)
    revenue_30d_pence = sum(int(i.get("amount_pence") or 0) for i in paid)

    # Active class bookings last 30d.
    bookings_30d = await db.class_bookings.count_documents(
        {"organization_id": org_id, "created_at": {"$gte": horizon_30}},
    )

    # Reuse the other endpoints to avoid duplication.
    risk = await retention_risk(weeks=8, limit=10, user=user)
    heatmap = await occupancy_heatmap(weeks=4, user=user)
    advice = await timetable_suggestions(user=user)

    # Headline (one-liner) — picks the most actionable bullet.
    headline = "Steady operations — keep monitoring class fill-rates."
    if (risk.get("summary") or {}).get("high", 0) > 0:
        n = risk["summary"]["high"]
        headline = (
            f"{n} {'student is' if n == 1 else 'students are'} flagged HIGH retention-risk — "
            "reach out this week."
        )
    elif heatmap.get("hottest") and heatmap["hottest"]["utilisation_pct"] >= 90:
        h = heatmap["hottest"]
        headline = (
            f"{h['day']} {h['bucket']} is {h['utilisation_pct']}% full — "
            "open another slot to capture demand."
        )
    elif (advice.get("suggestions") or []):
        headline = advice["suggestions"][0].get("rationale") or headline

    return {
        "headline": headline,
        "kpis": {
            "members_total": members_total,
            "members_new_30d": new_30d,
            "members_new_30_to_60d": new_30_to_60d,
            "growth_pct": growth_pct,
            "revenue_30d_pence": revenue_30d_pence,
            "bookings_30d": bookings_30d,
        },
        "retention_summary": risk.get("summary") or {},
        "top_at_risk": (risk.get("rows") or [])[:5],
        "heatmap_hottest": heatmap.get("hottest"),
        "heatmap_coldest": heatmap.get("coldest"),
        "ai_suggestions": (advice.get("suggestions") or [])[:5],
        "generated_at": now.isoformat(),
    }


__all__ = ["router"]
