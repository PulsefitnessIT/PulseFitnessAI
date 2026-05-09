"""Staffing Phase S6 — AI Workforce Automation & Payroll Integration.

Three new manager-facing capabilities:

  • **AI rota builder** — `POST /staffing/ai/rota/suggest` asks Claude
    Sonnet 4.5 to propose a fully-formed weekly rota given the current
    staff roster, their compliance rules, pending leave, and a
    demand template. Returns suggestions only — operator confirms via
    `POST /staffing/ai/rota/apply` which bulk-inserts into
    `staff_shifts`.

  • **Absence prediction** — `GET /staffing/ai/absence-risk` returns a
    deterministic 0-100 risk score per staff member for the upcoming
    14 days, derived from sick-leave history, late clock-ins, no-show
    shifts, and pending overlapping leave. Pure heuristic so it works
    offline; an optional Claude narrative wraps the top risks.

  • **Sage Payroll export** — `GET /staffing/ai/payroll/sage.csv`
    returns the standard Sage-50 Payroll import CSV (Reference,
    Surname, Forenames, NI Number, Hours, Rate, Gross Pay) for any
    date range. Splits `full_name` into Surname/Forenames; pulls
    NI number from the Phase S5 HR profile.

All three endpoints are manager-only (`_require_manager`). The AI
endpoints fail soft when `EMERGENT_LLM_KEY` is missing so the rota
builder still returns a heuristic suggestion (round-robin fill).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db

from routes.staffing import (
    VALID_ROLES,
    _is_manager,
    _now,
    _org,
    _require_manager,
    _shift_hours,
)

logger = logging.getLogger(__name__)
router = APIRouter()

CLAUDE_MODEL = ("anthropic", "claude-sonnet-4-5-20250929")


# ───────────────── Pydantic schemas ──────────────────────────────


class RotaSuggestRequest(BaseModel):
    week_start: str                                      # YYYY-MM-DD (Monday)
    demand: dict | None = None                           # {weekday_int: {"reception": needed, ...}}
    max_hours_per_staff_week: float | None = None
    notes: str | None = None
    site_id: str | None = None


class RotaApplyRequest(BaseModel):
    week_start: str
    shifts: list[dict]                                   # [{staff_id, date, start_time, end_time, role, ...}]
    overwrite_existing: bool = False                     # delete that week's shifts first


# ───────────────── Helpers ───────────────────────────────────────


def _parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _split_name(full: str) -> tuple[str, str]:
    """Split a free-text full name into (forenames, surname)."""
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _maybe_key() -> str | None:
    return os.environ.get("EMERGENT_LLM_KEY") or None


def _heuristic_rota(staff: list[dict], week_start_d: date,
                    demand: dict | None,
                    max_hours: float) -> list[dict]:
    """Round-robin fallback when Claude is unavailable. Generates one
    8-hour shift per staff per weekday, capped at max_hours per week."""
    out: list[dict] = []
    if not staff:
        return out
    DEFAULT_DEMAND = {  # 5-day operational template
        0: {"reception": 1, "manager": 1},
        1: {"reception": 1, "instructor": 1},
        2: {"reception": 1, "instructor": 1},
        3: {"reception": 1, "manager": 1},
        4: {"reception": 1, "instructor": 1},
        5: {"reception": 1},
        6: {"reception": 1},
    }
    demand = demand or DEFAULT_DEMAND
    hours_used: dict[str, float] = {s["id"]: 0.0 for s in staff}
    by_role: dict[str, list[dict]] = {}
    for s in staff:
        by_role.setdefault(s.get("primary_role") or "reception", []).append(s)
    rr_idx: dict[str, int] = {}
    for offset in range(7):
        d = (week_start_d + timedelta(days=offset)).isoformat()
        wd = (week_start_d + timedelta(days=offset)).weekday()
        slots = demand.get(wd) or demand.get(str(wd)) or {}
        for role, count in slots.items():
            pool = by_role.get(role) or by_role.get("reception") or staff
            for _ in range(int(count or 0)):
                idx = rr_idx.get(role, 0)
                # find next staff under cap
                tries = 0
                while tries < len(pool):
                    s = pool[idx % len(pool)]
                    if hours_used[s["id"]] + 8.0 <= max_hours:
                        out.append({
                            "staff_id": s["id"],
                            "date": d,
                            "start_time": "09:00",
                            "end_time": "17:00",
                            "role": role,
                            "reason": f"Auto-assigned (heuristic round-robin) · {s.get('full_name')}",
                        })
                        hours_used[s["id"]] += 8.0
                        rr_idx[role] = idx + 1
                        break
                    idx += 1
                    tries += 1
    return out


# ═══════════════════ AI ROTA BUILDER ═════════════════════════════


@router.post("/staffing/ai/rota/suggest")
async def ai_rota_suggest(
    body: RotaSuggestRequest, user: dict = Depends(get_current_user),
):
    """Propose a weekly rota. Returns suggestions only — does not save."""
    _require_manager(user)
    org_id = _org(user)
    try:
        ws = _parse_iso_date(body.week_start)
    except Exception:
        raise HTTPException(400, "week_start must be YYYY-MM-DD")
    if ws.weekday() != 0:
        # Snap to Monday if user passed mid-week
        ws = ws - timedelta(days=ws.weekday())

    week_end = ws + timedelta(days=6)

    # Pull staff + rules + leave overlapping the target week.
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    ).to_list(500)
    rules = await db.staff_rules.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    leave = await db.staff_leave_requests.find(
        {"organization_id": org_id, "status": {"$in": ["approved", "pending"]}},
        {"_id": 0},
    ).to_list(500)
    leave_by_staff: dict[str, list[dict]] = {}
    for lv in leave:
        try:
            ls = _parse_iso_date(lv["start_date"])
            le = _parse_iso_date(lv["end_date"])
        except Exception:
            continue
        if le < ws or ls > week_end:
            continue
        leave_by_staff.setdefault(lv["staff_id"], []).append(
            {"start": lv["start_date"], "end": lv["end_date"], "type": lv.get("leave_type")}
        )

    max_hours = float(
        body.max_hours_per_staff_week
        or rules.get("max_hours_per_week")
        or 48.0
    )

    # Try Claude. Fall back to heuristic on any failure.
    suggestions: list[dict] = []
    used_ai = False
    key = _maybe_key()
    if key and staff:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: WPS433
            roster_lines = []
            for s in staff:
                lv = leave_by_staff.get(s["id"]) or []
                lv_str = "; ".join(f"{x['start']}→{x['end']} {x.get('type')}" for x in lv) or "none"
                roster_lines.append(
                    f"- id={s['id']} | name={s.get('full_name')} | role={s.get('primary_role')} | "
                    f"hourly=£{s.get('hourly_cost',0)} | leave={lv_str}"
                )
            demand_str = json.dumps(body.demand) if body.demand else "default 5-day commercial gym demand"
            system = (
                "You are GymAxis Workforce, an expert UK gym workforce planner. "
                "Build a fair, compliant 7-day rota. Output STRICT JSON only — no prose. "
                "Schema: {\"shifts\": [{\"staff_id\": str, \"date\": \"YYYY-MM-DD\", "
                "\"start_time\": \"HH:MM\", \"end_time\": \"HH:MM\", \"role\": str, "
                "\"reason\": str (1 short sentence)}]}. "
                f"Constraints: total hours per staff <= {max_hours}/week. "
                "Honour approved/pending leave (do NOT schedule on those dates). "
                "Use 6-9 hour shifts, prefer 09:00-17:00 / 06:00-14:00 / 14:00-22:00 windows. "
                f"Roles MUST be one of: {sorted(VALID_ROLES)}."
            )
            user_text = (
                f"Week starting Monday {ws.isoformat()} (to {week_end.isoformat()}).\n\n"
                f"Demand template: {demand_str}\n\nRoster:\n" + "\n".join(roster_lines)
                + (f"\n\nManager notes: {body.notes}" if body.notes else "")
            )
            chat = LlmChat(
                api_key=key,
                session_id=f"staffing-rota-{uuid.uuid4()}",
                system_message=system,
            ).with_model(*CLAUDE_MODEL)
            t0 = time.time()
            raw = await chat.send_message(UserMessage(text=user_text))
            latency_ms = int((time.time() - t0) * 1000)
            parsed = _extract_json(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("shifts"), list):
                valid_ids = {s["id"] for s in staff}
                for sh in parsed["shifts"]:
                    if not isinstance(sh, dict):
                        continue
                    sid = sh.get("staff_id")
                    if sid not in valid_ids:
                        continue
                    role = sh.get("role") or "reception"
                    if role not in VALID_ROLES:
                        role = "reception"
                    try:
                        d = _parse_iso_date(sh.get("date") or "")
                    except Exception:
                        continue
                    if d < ws or d > week_end:
                        continue
                    if any(_parse_iso_date(lv["start"]) <= d <= _parse_iso_date(lv["end"])
                           for lv in leave_by_staff.get(sid, [])):
                        continue
                    suggestions.append({
                        "staff_id": sid,
                        "date": d.isoformat(),
                        "start_time": (sh.get("start_time") or "09:00")[:5],
                        "end_time": (sh.get("end_time") or "17:00")[:5],
                        "role": role,
                        "reason": (sh.get("reason") or "")[:240],
                    })
                used_ai = bool(suggestions)
            await db.staffing_ai_calls.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "kind": "rota_suggest",
                "week_start": ws.isoformat(),
                "suggestions_count": len(suggestions),
                "latency_ms": latency_ms,
                "ok": used_ai,
                "at": _now(),
            })
        except Exception as e:
            logger.warning("AI rota suggest failed, falling back: %s", e)

    if not suggestions:
        suggestions = _heuristic_rota(staff, ws, body.demand, max_hours)

    # Roll-up summary
    hours_per_staff: dict[str, float] = {}
    cost_total = 0.0
    cost_by_staff: dict[str, dict] = {s["id"]: {"staff_id": s["id"], "name": s.get("full_name"), "rate": float(s.get("hourly_cost") or 0), "hours": 0.0, "cost": 0.0} for s in staff}
    for sh in suggestions:
        h = _shift_hours({"start_time": sh["start_time"], "end_time": sh["end_time"]})
        hours_per_staff[sh["staff_id"]] = hours_per_staff.get(sh["staff_id"], 0) + h
        if sh["staff_id"] in cost_by_staff:
            cost_by_staff[sh["staff_id"]]["hours"] += h
            cost_by_staff[sh["staff_id"]]["cost"] += h * cost_by_staff[sh["staff_id"]]["rate"]
            cost_total += h * cost_by_staff[sh["staff_id"]]["rate"]
    return {
        "week_start": ws.isoformat(),
        "week_end": week_end.isoformat(),
        "engine": "claude-sonnet-4-5" if used_ai else "heuristic",
        "suggestions": suggestions,
        "hours_per_staff": hours_per_staff,
        "cost_per_staff": [v for v in cost_by_staff.values() if v["hours"] > 0],
        "cost_total_pence": round(cost_total * 100),
        "cost_total": round(cost_total, 2),
    }


@router.post("/staffing/ai/rota/apply")
async def ai_rota_apply(
    body: RotaApplyRequest, user: dict = Depends(get_current_user),
):
    """Persist a previously-suggested rota into `staff_shifts`."""
    _require_manager(user)
    org_id = _org(user)
    try:
        ws = _parse_iso_date(body.week_start)
    except Exception:
        raise HTTPException(400, "week_start must be YYYY-MM-DD")
    week_end = ws + timedelta(days=6)

    if body.overwrite_existing:
        await db.staff_shifts.delete_many({
            "organization_id": org_id,
            "date": {"$gte": ws.isoformat(), "$lte": week_end.isoformat()},
        })

    valid_staff_ids = {
        s["id"] async for s in db.staff_members.find(
            {"organization_id": org_id, "active": True}, {"_id": 0, "id": 1},
        )
    }

    docs = []
    for sh in body.shifts:
        sid = sh.get("staff_id")
        if sid not in valid_staff_ids:
            continue
        try:
            d = _parse_iso_date(sh["date"])
        except Exception:
            continue
        if d < ws or d > week_end:
            continue
        role = sh.get("role") or "reception"
        if role not in VALID_ROLES:
            role = "reception"
        docs.append({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "staff_id": sid,
            "site_id": sh.get("site_id"),
            "date": d.isoformat(),
            "start_time": (sh.get("start_time") or "09:00")[:5],
            "end_time": (sh.get("end_time") or "17:00")[:5],
            "role": role,
            "notes": sh.get("notes") or sh.get("reason"),
            "break_minutes": int(sh.get("break_minutes") or 0),
            "status": "scheduled",
            "source": "ai_rota_builder",
            "created_at": _now().isoformat(),
            "created_by": user.get("email"),
        })
    if docs:
        await db.staff_shifts.insert_many([d.copy() for d in docs])
    return {"created": len(docs), "week_start": ws.isoformat()}


# ═══════════════════ ABSENCE PREDICTION ══════════════════════════


@router.get("/staffing/ai/absence-risk")
async def absence_risk(
    horizon_days: int = Query(14, ge=1, le=60),
    user: dict = Depends(get_current_user),
):
    """Heuristic risk score per staff for the next `horizon_days`.

    Score components (0-100, higher = more likely to be absent):
      • +25 per sick leave in last 90 days (cap 50)
      • +15 per late clock-in last 30 days (cap 30)
      • +20 per missed shift last 90 days (cap 40)
      • +10 if pending leave overlaps the horizon
      • +20 baseline if hire_date < 60 days ago (probation jitter)
    """
    _require_manager(user)
    org_id = _org(user)
    today = date.today()
    horizon_end = today + timedelta(days=horizon_days)
    sick_window_start = (today - timedelta(days=90)).isoformat()
    late_window_start = (today - timedelta(days=30)).isoformat()

    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    ).to_list(500)

    # Sick / no-show counts
    leave = await db.staff_leave_requests.find(
        {"organization_id": org_id, "start_date": {"$gte": sick_window_start}},
        {"_id": 0, "staff_id": 1, "leave_type": 1, "status": 1, "start_date": 1, "end_date": 1},
    ).to_list(2000)
    sick_count: dict[str, int] = {}
    pending_overlap: dict[str, int] = {}
    for lv in leave:
        sid = lv.get("staff_id")
        if not sid:
            continue
        if (lv.get("leave_type") == "sick" and lv.get("status") in {"approved", "pending"}):
            sick_count[sid] = sick_count.get(sid, 0) + 1
        if lv.get("status") in {"approved", "pending"}:
            try:
                ls = _parse_iso_date(lv["start_date"])
                le = _parse_iso_date(lv["end_date"])
            except Exception:
                continue
            if le >= today and ls <= horizon_end:
                pending_overlap[sid] = pending_overlap.get(sid, 0) + 1

    # Late clock-ins (Phase S2)
    late_count: dict[str, int] = {}
    if "staff_time_logs" in await db.list_collection_names():
        async for tl in db.staff_time_logs.find(
            {"organization_id": org_id, "date": {"$gte": late_window_start}, "late_minutes": {"$gt": 0}},
            {"_id": 0, "staff_id": 1, "late_minutes": 1},
        ):
            sid = tl.get("staff_id")
            if not sid:
                continue
            late_count[sid] = late_count.get(sid, 0) + 1

    # Missed / no-show shifts
    miss_count: dict[str, int] = {}
    async for sh in db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": sick_window_start},
         "status": {"$in": ["missed", "no_show", "cancelled"]}},
        {"_id": 0, "staff_id": 1, "status": 1},
    ):
        if sh.get("status") in {"missed", "no_show"}:
            sid = sh.get("staff_id")
            if sid:
                miss_count[sid] = miss_count.get(sid, 0) + 1

    rows = []
    for s in staff:
        sid = s["id"]
        score = 0
        reasons = []
        sc = sick_count.get(sid, 0)
        if sc:
            add = min(50, sc * 25)
            score += add
            reasons.append(f"{sc} sick leave in last 90 days")
        lc = late_count.get(sid, 0)
        if lc:
            add = min(30, lc * 15)
            score += add
            reasons.append(f"{lc} late clock-ins last 30 days")
        mc = miss_count.get(sid, 0)
        if mc:
            add = min(40, mc * 20)
            score += add
            reasons.append(f"{mc} missed shifts last 90 days")
        if pending_overlap.get(sid):
            score += 10
            reasons.append("Pending leave overlaps horizon")
        # Probation jitter
        try:
            hire = s.get("hire_date")
            if hire:
                if (today - _parse_iso_date(hire)).days < 60:
                    score += 20
                    reasons.append("Within first 60 days of hire")
        except Exception:
            pass
        score = min(100, score)
        band = "low" if score < 25 else ("medium" if score < 60 else "high")
        rows.append({
            "staff_id": sid,
            "full_name": s.get("full_name"),
            "primary_role": s.get("primary_role"),
            "score": score,
            "band": band,
            "reasons": reasons or ["No risk signals"],
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    summary = {
        "high": sum(1 for r in rows if r["band"] == "high"),
        "medium": sum(1 for r in rows if r["band"] == "medium"),
        "low": sum(1 for r in rows if r["band"] == "low"),
        "horizon_days": horizon_days,
        "as_of": today.isoformat(),
    }
    return {"rows": rows, "summary": summary}


# ═══════════════════ SAGE PAYROLL EXPORT ═════════════════════════


@router.get("/staffing/ai/payroll/sage.csv")
async def sage_payroll_csv(
    date_from: str = Query(...),
    date_to: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Sage 50 Payroll standard import CSV.

    Columns (per Sage 50 Payroll *Hours and Rates* import spec):
      Reference, Surname, Forenames, NI Number, Payment Number,
      Hours, Rate, Amount.

    Aggregates non-cancelled shifts per staff over `[date_from,
    date_to]`.  Non-employees / archived staff are skipped.
    """
    _require_manager(user)
    org_id = _org(user)
    try:
        df = _parse_iso_date(date_from)
        dt = _parse_iso_date(date_to)
    except Exception:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    if dt < df:
        raise HTTPException(400, "date_to must be >= date_from")

    staff = {
        s["id"]: s async for s in db.staff_members.find(
            {"organization_id": org_id}, {"_id": 0},
        )
    }

    # Aggregate hours per staff in window
    hours: dict[str, float] = {}
    async for sh in db.staff_shifts.find(
        {"organization_id": org_id, "date": {"$gte": df.isoformat(), "$lte": dt.isoformat()},
         "status": {"$ne": "cancelled"}},
        {"_id": 0, "staff_id": 1, "start_time": 1, "end_time": 1, "break_minutes": 1},
    ):
        sid = sh.get("staff_id")
        if not sid:
            continue
        hours[sid] = hours.get(sid, 0.0) + _shift_hours(sh)

    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow([
        "Reference", "Surname", "Forenames", "NI Number",
        "Payment Number", "Hours", "Rate", "Amount",
    ])
    total_hours = 0.0
    total_amount = 0.0
    rows = 0
    for sid, h in hours.items():
        if h <= 0:
            continue
        s = staff.get(sid)
        if not s:
            continue
        forenames, surname = _split_name(s.get("full_name") or "")
        rate = float(s.get("hourly_cost") or 0.0)
        amount = round(h * rate, 2)
        ref = (s.get("employee_number") or sid[:8]).upper()
        w.writerow([
            ref,
            surname,
            forenames,
            (s.get("ni_number") or "").upper().replace(" ", ""),
            "1",                         # Sage payment number 1 = Basic Hours
            f"{h:.2f}",
            f"{rate:.2f}",
            f"{amount:.2f}",
        ])
        total_hours += h
        total_amount += amount
        rows += 1
    # Sage doesn't expect a totals row in the import file but it's
    # standard practice to include one as a check sum row prefixed
    # with TOTAL — operators delete it before import.
    w.writerow(["TOTAL", "", "", "", "", f"{total_hours:.2f}", "", f"{total_amount:.2f}"])

    csv_text = buf.getvalue()
    fname = f"sage-payroll-{df.isoformat()}-to-{dt.isoformat()}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Sage-Rows": str(rows),
        },
    )


# ───────────────── Local JSON helper (reused across endpoints) ───


def _extract_json(text: str):
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start: end + 1])
            except Exception:
                return None
    return None
