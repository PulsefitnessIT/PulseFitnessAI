"""Calendar-aware contract date helpers (no 30/365-day approximations)."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional

PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "biannual": 6, "semiannual": 6, "annual": 12, "annually": 12}


def parse_date(v) -> Optional[date]:
    try:
        return datetime.strptime(str(v or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def add_months(d: date, months: int, *, month_end: bool = False) -> date:
    """Add calendar months, clamping to month end (31 Jan + 1m = 28/29 Feb).
    ``month_end`` keeps an end-of-month anchor on the last day every month."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, last if month_end else min(d.day, last))


def term_end(start: date, years: int = 1) -> date:
    return add_months(start, 12 * max(1, years)) - timedelta(days=1)


def term_months(start: date, end: Optional[date], term_years: int) -> int:
    """Whole months from start to the day after end, to the nearest month."""
    if not end:
        return 12 * max(1, term_years)
    e = end + timedelta(days=1)
    months = (e.year - start.year) * 12 + (e.month - start.month)
    if e.day - start.day > 15:  # genuine partial month; anniversary ±a few days is a whole term
        months += 1
    return max(1, months)


def billing_schedule(annual: float, frequency: str, start_iso, end_iso=None, term_years: int = 1) -> list:
    """Billing rows from the contract value; [] when the start date is missing."""
    sd = parse_date(start_iso)
    if not sd:
        return []
    freq = (frequency or "").lower()
    months = term_months(sd, parse_date(end_iso), term_years)
    anchor_end = sd.day == calendar.monthrange(sd.year, sd.month)[1]
    if freq == "lump_sum":
        return [{"due_date": sd.isoformat(), "amount": round(annual * months / 12, 2), "status": "scheduled"}]
    step = PERIOD_MONTHS.get(freq)
    if not step:
        return []
    amt = round(annual * step / 12, 2)
    return [{"due_date": add_months(sd, k, month_end=anchor_end).isoformat(), "amount": amt, "status": "scheduled",
             "period": i + 1} for i, k in enumerate(range(0, months, step))]


def service_schedule(start_iso, visits_per_year, end_iso=None, term_years: int = 1) -> list:
    """Contractual PPM obligations (planned, NOT booked visits); [] without a start.
    Pulse policy: no visit at commencement — visits are spaced through each contract
    year so the last visit of the year falls on the anniversary (1/yr → anniversary),
    kept within cover (an anniversary at expiry uses the final day of cover)."""
    sd = parse_date(start_iso)
    if not sd:
        return []
    visits = max(1, int(visits_per_year or 1))
    ed = parse_date(end_iso)
    months = term_months(sd, ed, term_years)
    last_day = ed or term_end(sd, max(1, term_years))
    rows = []
    for y in range((months + 11) // 12):
        for v in range(visits):
            off = 12 * y + (12 * (v + 1)) // visits
            if off > months:
                break
            d = min(add_months(sd, off), last_day)
            rows.append({"planned_date": d.isoformat(), "status": "planned", "visit_no": v + 1, "year": y + 1})
    return rows
