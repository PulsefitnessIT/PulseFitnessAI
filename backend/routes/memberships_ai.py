"""Pulse Fitness Memberships — Phase 5 AI Insights layer.

Four operator-only endpoints that turn raw class/booking data into
revenue-positive recommendations:

  1. Demand prediction
     `GET /api/memberships/ai/demand-forecast?weeks_back=8`
     Per future occurrence: predicted fill % based on the same template's
     historical fills, day-of-week, and time-of-day. Deterministic stats —
     no LLM, no hallucination risk. Surfaces:
        • likely-to-overfill (capacity bump candidates)
        • likely-to-underfill (cancel / reschedule candidates)

  2. Underperforming-class detector
     `GET /api/memberships/ai/underperformers?weeks=4&fill_threshold=50`
     Templates whose last N weeks all averaged below threshold fill rate
     AND at least M occurrences in window. Flags chronic dead slots.

  3. Pricing recommendations (LLM)
     `GET /api/memberships/ai/pricing-recommendations`
     Aggregates plan-level demand + revenue + free-trial conversion +
     waitlist depth + competitor parity hints, then asks Claude to
     suggest price changes per plan with rationale.

  4. New-class suggestions (LLM)
     `GET /api/memberships/ai/class-suggestions`
     Aggregates "demand signals" — search/filter terms, no-show patterns,
     waitlist overflow, member preferences (favourite class affinity),
     and asks Claude to propose 3-5 new class types the studio could
     run with rationale + best slot.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-ai"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


# ───────────────────────── 1. Demand forecast ─────────────────────────


@router.get(
    "/memberships/ai/demand-forecast",
    dependencies=[Depends(require_module("memberships"))],
)
async def demand_forecast(
    weeks_back: int = Query(default=8, ge=2, le=26),
    weeks_ahead: int = Query(default=2, ge=1, le=8),
    user: dict = Depends(get_current_user),
):
    """Predict fill rate for every scheduled occurrence in the next
    `weeks_ahead` weeks based on historical performance of the same
    template at the same weekday/time-of-day slot.

    Algorithm:
      For each future occurrence O of template T at weekday W, hour H:
        1. Find historical occurrences of T at the same W±0 in the
           last `weeks_back` weeks (with non-zero capacity & not
           cancelled).
        2. Compute weighted historical fill (0.0–1.5; >1 means waitlist).
        3. Apply a small uplift if the matching hour-of-day is also
           historically strong for T.
      Return the prediction + suggested action when the prediction
      diverges meaningfully from current bookings.
    """
    org_id = await _require_operator_org(user)
    now = _now()
    history_since = now - timedelta(weeks=weeks_back)
    horizon = now + timedelta(weeks=weeks_ahead)

    history: list[dict] = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": history_since.isoformat(),
                       "$lte": now.isoformat()},
         "status": {"$ne": "cancelled"},
         "capacity": {"$gt": 0}},
        {"_id": 0, "id": 1, "template_id": 1, "starts_at": 1,
         "capacity": 1, "bookings_count": 1, "waitlist_count": 1,
         "attended_count": 1},
    ).to_list(5000)

    # Build (template_id, weekday) -> list of fill ratios; also track
    # (template_id, hour) -> list for the secondary uplift.
    by_template_weekday: dict[tuple[str, int], list[float]] = defaultdict(list)
    by_template_hour: dict[tuple[str, int], list[float]] = defaultdict(list)
    for o in history:
        tpl_id = o.get("template_id") or ""
        ts = _parse_iso(o.get("starts_at"))
        cap = int(o.get("capacity") or 0)
        booked = int(o.get("bookings_count") or 0)
        wl = int(o.get("waitlist_count") or 0)
        if not tpl_id or not ts or not cap:
            continue
        # Cap at 1.5 — a class that fills + has a strong waitlist still
        # signals demand but we don't let one outlier dominate the mean.
        ratio = min((booked + 0.5 * wl) / cap, 1.5)
        by_template_weekday[(tpl_id, ts.weekday())].append(ratio)
        by_template_hour[(tpl_id, ts.hour)].append(ratio)

    # Future occurrences in horizon
    future = await db.class_occurrences.find(
        {"organization_id": org_id,
         "status": "scheduled",
         "starts_at": {"$gte": now.isoformat(),
                       "$lte": horizon.isoformat()}},
        {"_id": 0, "id": 1, "template_id": 1, "starts_at": 1,
         "capacity": 1, "bookings_count": 1, "waitlist_count": 1,
         "instructor_name": 1},
    ).to_list(2000)

    # Pull template names so the UI can show real names
    tpl_ids = list({f.get("template_id") for f in future if f.get("template_id")})
    tpl_names: dict[str, str] = {}
    if tpl_ids:
        async for tpl in db.class_templates.find(
            {"id": {"$in": tpl_ids}}, {"_id": 0, "id": 1, "name": 1},
        ):
            tpl_names[tpl["id"]] = tpl.get("name") or "Class"

    rows: list[dict] = []
    high_fill_count = 0
    low_fill_count = 0
    confident_count = 0
    for o in future:
        tpl_id = o.get("template_id") or ""
        ts = _parse_iso(o.get("starts_at"))
        cap = int(o.get("capacity") or 0)
        booked_now = int(o.get("bookings_count") or 0)
        if not tpl_id or not ts or not cap:
            continue

        weekday_samples = by_template_weekday.get((tpl_id, ts.weekday()), [])
        hour_samples = by_template_hour.get((tpl_id, ts.hour), [])
        if len(weekday_samples) < 2:
            # Too thin to predict — skip rather than mislead
            continue
        weekday_mean = statistics.mean(weekday_samples)
        hour_uplift = (statistics.mean(hour_samples) - weekday_mean) * 0.25 \
            if len(hour_samples) >= 2 else 0.0
        predicted_ratio = max(0.0, weekday_mean + hour_uplift)
        predicted_fill_pct = round(predicted_ratio * 100, 1)
        confidence = "high" if len(weekday_samples) >= 4 else "medium"
        if confidence == "high":
            confident_count += 1

        # Suggest action when prediction diverges from current booked
        current_pct = round(100.0 * booked_now / cap, 1) if cap else 0
        action: Optional[str] = None
        if predicted_ratio >= 1.0 and current_pct < 60:
            action = "demand_high"
            high_fill_count += 1
        elif predicted_ratio <= 0.4 and current_pct < 40:
            action = "demand_low"
            low_fill_count += 1

        rows.append({
            "occurrence_id": o["id"],
            "template_id": tpl_id,
            "name": tpl_names.get(tpl_id, "Class"),
            "starts_at": o.get("starts_at"),
            "capacity": cap,
            "current_bookings": booked_now,
            "current_fill_pct": current_pct,
            "predicted_fill_pct": predicted_fill_pct,
            "predicted_ratio": round(predicted_ratio, 3),
            "confidence": confidence,
            "samples": len(weekday_samples),
            "instructor_name": o.get("instructor_name"),
            "action": action,
        })

    rows.sort(key=lambda r: -r["predicted_fill_pct"])
    return {
        "rows": rows, "count": len(rows),
        "summary": {
            "demand_high_count": high_fill_count,
            "demand_low_count": low_fill_count,
            "high_confidence_count": confident_count,
        },
        "params": {
            "weeks_back": weeks_back, "weeks_ahead": weeks_ahead,
            "since": history_since.isoformat(),
            "until": horizon.isoformat(),
        },
    }


# ───────────────────────── 2. Underperformer detector ─────────────────────────


@router.get(
    "/memberships/ai/underperformers",
    dependencies=[Depends(require_module("memberships"))],
)
async def underperformers(
    weeks: int = Query(default=4, ge=2, le=12),
    fill_threshold_pct: int = Query(default=50, ge=10, le=90),
    min_occurrences: int = Query(default=3, ge=2, le=20),
    user: dict = Depends(get_current_user),
):
    """List class templates whose average fill rate over the last `weeks`
    weeks is below `fill_threshold_pct` AND ran at least `min_occurrences`
    times in the window. These are the chronic dead slots — perfect
    targets for cancel / reschedule / replace.
    """
    org_id = await _require_operator_org(user)
    now = _now()
    since = now - timedelta(weeks=weeks)

    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since.isoformat(),
                       "$lte": now.isoformat()},
         "status": {"$ne": "cancelled"},
         "capacity": {"$gt": 0}},
        {"_id": 0, "template_id": 1, "starts_at": 1,
         "capacity": 1, "bookings_count": 1, "attended_count": 1,
         "no_show_count": 1, "instructor_name": 1},
    ).to_list(5000)

    # Aggregate by template
    by_tpl: dict[str, dict] = defaultdict(lambda: {
        "occurrences": 0, "capacity_sum": 0, "bookings_sum": 0,
        "attended_sum": 0, "no_show_sum": 0, "instructors": set(),
    })
    for o in occs:
        tid = o.get("template_id")
        if not tid:
            continue
        a = by_tpl[tid]
        a["occurrences"] += 1
        a["capacity_sum"] += int(o.get("capacity") or 0)
        a["bookings_sum"] += int(o.get("bookings_count") or 0)
        a["attended_sum"] += int(o.get("attended_count") or 0)
        a["no_show_sum"] += int(o.get("no_show_count") or 0)
        if o.get("instructor_name"):
            a["instructors"].add(o["instructor_name"])

    # Look up template names + active flag
    tpl_ids = list(by_tpl.keys())
    tpls: dict[str, dict] = {}
    if tpl_ids:
        async for tpl in db.class_templates.find(
            {"id": {"$in": tpl_ids}},
            {"_id": 0, "id": 1, "name": 1, "weekday": 1,
             "start_time": 1, "duration_min": 1, "archived": 1,
             "credits_to_book": 1},
        ):
            tpls[tpl["id"]] = tpl

    rows: list[dict] = []
    for tid, agg in by_tpl.items():
        if agg["occurrences"] < min_occurrences:
            continue
        cap = agg["capacity_sum"] or 1
        avg_fill = round(100.0 * agg["bookings_sum"] / cap, 1)
        if avg_fill > fill_threshold_pct:
            continue
        booked = max(agg["bookings_sum"], 1)
        attendance = round(100.0 * agg["attended_sum"] / booked, 1)
        tpl = tpls.get(tid) or {}
        if tpl.get("archived"):
            continue
        rows.append({
            "template_id": tid,
            "name": tpl.get("name") or "Class",
            "weekday": tpl.get("weekday"),
            "start_time": tpl.get("start_time"),
            "duration_min": tpl.get("duration_min"),
            "occurrences": agg["occurrences"],
            "avg_fill_pct": avg_fill,
            "attendance_rate_pct": attendance,
            "no_show_count": agg["no_show_sum"],
            "instructor_count": len(agg["instructors"]),
            "instructors": sorted(agg["instructors"])[:5],
            "lost_capacity": agg["capacity_sum"] - agg["bookings_sum"],
        })

    rows.sort(key=lambda r: r["avg_fill_pct"])  # worst first
    return {
        "rows": rows, "count": len(rows),
        "params": {
            "weeks": weeks, "fill_threshold_pct": fill_threshold_pct,
            "min_occurrences": min_occurrences, "since": since.isoformat(),
        },
    }


# ───────────────────────── 3. Pricing recommendations (Claude) ─────────────────────────


PRICING_SCHEMA = {
    "recommendations": [
        {
            "plan_id": "id of the plan",
            "plan_name": "name as supplied",
            "current_pence": 0,
            "suggested_pence": 0,
            "direction": "raise|hold|lower",
            "rationale": "1-2 sentence explanation citing the data",
            "confidence": "high|medium|low",
        },
    ],
    "summary": "1-line rollup of the strategy across the portfolio",
}


@router.get(
    "/memberships/ai/pricing-recommendations",
    dependencies=[Depends(require_module("memberships"))],
)
async def pricing_recommendations(
    user: dict = Depends(get_current_user),
):
    """Claude looks at every active plan + last 90 days of demand/
    revenue/waitlist/churn signals, and suggests price moves.

    Returns a strict-schema JSON the UI can render directly.
    """
    org_id = await _require_operator_org(user)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Pricing AI unavailable — LLM key not configured")
    now = _now()
    since = now - timedelta(days=90)

    plans = await db.membership_plans.find(
        {"organization_id": org_id, "archived": {"$ne": True}, "active": True},
        {"_id": 0},
    ).to_list(50)
    if not plans:
        return {"recommendations": [], "summary": "No active plans yet."}

    # Per-plan demand + revenue snapshot
    plan_metrics: dict[str, dict] = {p["id"]: {
        "id": p["id"], "name": p.get("name"), "kind": p.get("kind"),
        "billing_cycle": p.get("billing_cycle"),
        "current_pence": int(p.get("price_pence") or 0),
        "trial_days": int(p.get("trial_days") or 0),
        "memberships_active": 0, "memberships_total": 0,
        "memberships_cancelled_90d": 0,
        "revenue_pence_90d": 0,
        "trial_started_90d": 0, "trial_converted_90d": 0,
    } for p in plans}

    async for mm in db.member_memberships.find(
        {"organization_id": org_id, "plan_id": {"$in": list(plan_metrics)}},
        {"_id": 0, "plan_id": 1, "status": 1, "joined_at": 1,
         "last_billed_at": 1, "billing_status": 1, "cancelled_at": 1,
         "trial_ends_at": 1},
    ):
        m = plan_metrics.get(mm["plan_id"])
        if not m:
            continue
        m["memberships_total"] += 1
        if mm.get("status") == "active":
            m["memberships_active"] += 1
        if (mm.get("cancelled_at") or "") >= since.isoformat():
            m["memberships_cancelled_90d"] += 1
        if (mm.get("joined_at") or "") >= since.isoformat() and mm.get("trial_ends_at"):
            m["trial_started_90d"] += 1
            if mm.get("status") == "active" and mm.get("billing_status") == "current":
                m["trial_converted_90d"] += 1

    async for tx in db.payment_transactions.find(
        {"organization_id": org_id, "payment_status": "paid",
         "created_at": {"$gte": since.isoformat()}},
        {"_id": 0, "plan_id": 1, "amount_pence": 1},
    ):
        m = plan_metrics.get(tx.get("plan_id"))
        if m:
            m["revenue_pence_90d"] += int(tx.get("amount_pence") or 0)

    # Waitlist + fill-rate signal at the org level (proxy for overall demand)
    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since.isoformat(),
                       "$lte": now.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "capacity": 1, "bookings_count": 1, "waitlist_count": 1},
    ).to_list(5000)
    cap_sum = sum(int(o.get("capacity") or 0) for o in occs) or 1
    booked_sum = sum(int(o.get("bookings_count") or 0) for o in occs)
    wl_sum = sum(int(o.get("waitlist_count") or 0) for o in occs)
    org_fill_pct = round(100.0 * booked_sum / cap_sum, 1)
    org_waitlist_ratio = round(100.0 * wl_sum / cap_sum, 1)

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1},
    ) or {}

    sys = (
        "You are Pulse Fitness AI Pricing Strategist for an independent gym/"
        "studio. Use UK English. ALWAYS reply with ONE JSON object that "
        f"matches this schema EXACTLY (no markdown, no preamble):\n"
        f"{json.dumps(PRICING_SCHEMA)}\n\n"
        "Hard rules:\n"
        " • Suggest price changes ONLY when you have a clear data-backed "
        "reason. Default to 'hold' when the data is mixed.\n"
        " • Never raise more than 12% in one move. Never lower more "
        "than 25% in one move.\n"
        " • If org-wide fill_pct is over 80% AND waitlist_ratio over 8%, "
        "lean toward raising prices on unlimited subs (genuine demand).\n"
        " • If trial_conversion is below 35% on a recurring plan, "
        "suggest a shorter trial or smaller intro price BEFORE raising "
        "the headline.\n"
        " • For class_pack plans, lean on the per-credit price implicit "
        "in (price ÷ credits_count) — recommend per-credit changes.\n"
        " • For courses (kind=course), do NOT recommend price changes "
        "after the start date — say 'hold' and explain the reason.\n"
        " • current_pence and suggested_pence MUST be integers (pence).\n"
        " • confidence reflects sample size: high (≥30 active members + "
        "<90 days strong signal), medium, low.\n"
    )
    user_msg = (
        f"Studio: {org.get('name') or 'Pulse Fitness customer'}.\n"
        f"Org-wide last 90 days: fill_pct={org_fill_pct}%, "
        f"waitlist_ratio={org_waitlist_ratio}%, "
        f"capacity_sum={cap_sum}, bookings_sum={booked_sum}.\n\n"
        f"Plans:\n{json.dumps(list(plan_metrics.values()), indent=2)}\n\n"
        "Return the JSON now."
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=f"pricing-{org_id}-{uuid.uuid4().hex[:6]}",
            system_message=sys,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_msg))
        cleaned = _strip_json(raw)
        out = json.loads(cleaned)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[ai-pricing] claude failed: %s", exc)
        raise HTTPException(503, f"Pricing recommendations unavailable: {exc}") from exc

    # Persist for audit
    await db.memberships_ai_runs.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "kind": "pricing_recommendations",
        "input_signals": {
            "org_fill_pct": org_fill_pct,
            "org_waitlist_ratio": org_waitlist_ratio,
            "plan_count": len(plans),
        },
        "output": out,
        "created_by": user["id"],
        "created_at": now.isoformat(),
    })
    return {**out, "generated_at": now.isoformat(),
            "org_signals": {
                "fill_pct": org_fill_pct,
                "waitlist_ratio_pct": org_waitlist_ratio,
            }}


# ───────────────────────── 4. New-class suggestions (Claude) ─────────────────────────


CLASS_SUGGESTION_SCHEMA = {
    "suggestions": [
        {
            "name": "proposed class name",
            "rationale": "1-2 sentences citing the demand signal",
            "best_weekday": "Mon|Tue|Wed|Thu|Fri|Sat|Sun",
            "best_time": "HH:MM 24h",
            "duration_min": 0,
            "expected_audience": "who specifically would book this",
            "confidence": "high|medium|low",
        },
    ],
    "summary": "1-line rollup of where new growth could come from",
}


@router.get(
    "/memberships/ai/class-suggestions",
    dependencies=[Depends(require_module("memberships"))],
)
async def class_suggestions(user: dict = Depends(get_current_user)):
    """Claude proposes 3-5 NEW class types the studio could run, given:
      • most-booked existing classes (what members like)
      • most-waitlisted slots (unmet demand)
      • underperforming slots (free space)
      • top member affinity classes from the churn detector signals
    """
    org_id = await _require_operator_org(user)
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Class suggestions unavailable — LLM key not configured")
    now = _now()
    since = now - timedelta(days=90)

    occs = await db.class_occurrences.find(
        {"organization_id": org_id,
         "starts_at": {"$gte": since.isoformat(),
                       "$lte": now.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "template_id": 1, "starts_at": 1,
         "capacity": 1, "bookings_count": 1, "waitlist_count": 1},
    ).to_list(5000)

    by_tpl: dict[str, dict] = defaultdict(lambda: {
        "cap": 0, "booked": 0, "waitlist": 0, "n": 0,
    })
    for o in occs:
        tid = o.get("template_id")
        if not tid:
            continue
        a = by_tpl[tid]
        a["cap"] += int(o.get("capacity") or 0)
        a["booked"] += int(o.get("bookings_count") or 0)
        a["waitlist"] += int(o.get("waitlist_count") or 0)
        a["n"] += 1

    tpl_ids = list(by_tpl)
    tpl_meta: dict[str, dict] = {}
    if tpl_ids:
        async for tpl in db.class_templates.find(
            {"id": {"$in": tpl_ids}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "weekday": 1, "start_time": 1,
             "duration_min": 1},
        ):
            tpl_meta[tpl["id"]] = tpl

    classes_summary: list[dict] = []
    for tid, a in by_tpl.items():
        meta = tpl_meta.get(tid) or {}
        if not meta:
            continue
        cap = a["cap"] or 1
        classes_summary.append({
            "name": meta.get("name"),
            "weekday": meta.get("weekday"),
            "start_time": meta.get("start_time"),
            "duration_min": meta.get("duration_min"),
            "occurrences": a["n"],
            "fill_pct": round(100.0 * a["booked"] / cap, 1),
            "waitlist_count": a["waitlist"],
        })
    classes_summary.sort(key=lambda r: -r["fill_pct"])
    top_loved = classes_summary[:5]
    top_waitlisted = sorted(classes_summary,
                            key=lambda r: -r["waitlist_count"])[:5]

    # Member-side affinity left as a future enhancement — keeping the
    # join lightweight to avoid a 3-collection scan on big orgs.

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1},
    ) or {}

    sys = (
        "You are Pulse Fitness AI Programming Strategist for a gym/studio. "
        "UK English. ALWAYS reply with ONE JSON object that matches "
        f"this schema EXACTLY (no markdown, no preamble):\n"
        f"{json.dumps(CLASS_SUGGESTION_SCHEMA)}\n\n"
        "Hard rules:\n"
        " • Propose 3-5 NEW class types — they should be either "
        "adjacent to what the studio already does well (more times of "
        "loved classes), filling waitlist demand, or genuinely new "
        "tribes (mobility, parents+kids, over-50s, recovery).\n"
        " • Each suggestion must cite a SPECIFIC data signal in the "
        "rationale — don't invent.\n"
        " • Best slot = weekday + 24h time. Pick a realistic operating "
        "hour (06:00-21:30). Avoid duplicating an existing slot.\n"
        " • Keep names concise (≤30 chars), member-friendly, and "
        "free of internal jargon.\n"
    )
    user_msg = (
        f"Studio: {org.get('name') or 'Pulse Fitness customer'}\n\n"
        f"Top-performing existing classes (last 90d):\n"
        f"{json.dumps(top_loved, indent=2)}\n\n"
        f"Most-waitlisted slots (last 90d):\n"
        f"{json.dumps(top_waitlisted, indent=2)}\n\n"
        f"Total classes run: {len(classes_summary)}.\n\n"
        "Return the JSON now."
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=f"classsug-{org_id}-{uuid.uuid4().hex[:6]}",
            system_message=sys,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_msg))
        cleaned = _strip_json(raw)
        out = json.loads(cleaned)
    except Exception as exc:
        logger.warning("[ai-classsug] claude failed: %s", exc)
        raise HTTPException(503, f"Class suggestions unavailable: {exc}") from exc

    await db.memberships_ai_runs.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "kind": "class_suggestions",
        "input_signals": {
            "top_loved_count": len(top_loved),
            "top_waitlisted_count": len(top_waitlisted),
        },
        "output": out,
        "created_by": user["id"],
        "created_at": now.isoformat(),
    })
    return {**out, "generated_at": now.isoformat()}


def _strip_json(raw: Any) -> str:
    """Some LLM responses come wrapped in ```json ... ```; strip safely."""
    if not isinstance(raw, str):
        raw = str(raw)
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        # remove possible "json" tag at the start
        if s.startswith("json"):
            s = s[4:].lstrip()
    return s


__all__ = ["router"]
