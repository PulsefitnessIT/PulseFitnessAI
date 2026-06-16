"""Iter 220m — Monthly Engineer Reputation Reports.

The 1st of every month, every Partner Engineer who collected at
least one customer rating in the previous calendar month gets a
branded email digest summarising:

  • Avg rating + count for the month.
  • Trend vs previous month (▲/▼/—).
  • Star distribution.
  • A single highlighted comment (highest-rated, longest comment first).
  • A "Share on LinkedIn" button with a pre-filled compose URL.
  • "View all my reviews" CTA → /svc/engineer/ratings.

Idempotency:
  We stamp `reputation_reports.last_sent_period = "YYYY-MM"` on the
  partner record so re-running on the same day is a no-op even if the
  loop crashes / restarts.

Scheduling:
  The loop wakes every 6 hours; it only acts when *today* is the 1st
  AND the partner hasn't been sent the report for the current period
  yet. So even with a same-day restart the email fires exactly once.
"""
from __future__ import annotations

import asyncio
import logging
import urllib.parse
from datetime import date, datetime, timezone
from typing import Optional

from utils.database import db
from utils.email import send_email, PUBLIC_BASE_URL

logger = logging.getLogger(__name__)


def _period_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _month_window(year: int, month: int) -> tuple[str, str]:
    """ISO start (inclusive) and ISO end (exclusive) for the given
    calendar month."""
    start = datetime(year, month, 1, tzinfo=timezone.utc).isoformat()
    if month == 12:
        nxt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        nxt = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    end = nxt.isoformat()
    return start, end


def _previous_period(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return (year - 1, 12)
    return (year, month - 1)


async def build_monthly_report(*, engineer_user_id: str, year: int, month: int) -> Optional[dict]:
    """Aggregate stats for a single engineer + period. Returns None if
    the engineer had zero ratings in the period (caller skips the email)."""
    start, end = _month_window(year, month)
    pipeline = [
        {"$match": {
            "assigned_engineer_id": engineer_user_id,
            "customer_rating": {"$gte": 1},
            "customer_feedback_at": {"$gte": start, "$lt": end},
        }},
        {"$group": {
            "_id": None,
            "avg": {"$avg": "$customer_rating"},
            "count": {"$sum": 1},
        }},
    ]
    summary = await db.svc_cases.aggregate(pipeline).to_list(1)
    if not summary or not summary[0].get("count"):
        return None
    avg = round(float(summary[0]["avg"]), 2)
    count = int(summary[0]["count"])

    # Distribution
    dist_rows = await db.svc_cases.aggregate([
        {"$match": {
            "assigned_engineer_id": engineer_user_id,
            "customer_rating": {"$gte": 1},
            "customer_feedback_at": {"$gte": start, "$lt": end},
        }},
        {"$group": {"_id": "$customer_rating", "n": {"$sum": 1}}},
    ]).to_list(10)
    distribution = {str(i): 0 for i in range(1, 6)}
    for r in dist_rows:
        distribution[str(int(r["_id"]))] = int(r["n"])

    # Previous-month avg for the trend pill
    prev_y, prev_m = _previous_period(year, month)
    p_start, p_end = _month_window(prev_y, prev_m)
    prev = await db.svc_cases.aggregate([
        {"$match": {
            "assigned_engineer_id": engineer_user_id,
            "customer_rating": {"$gte": 1},
            "customer_feedback_at": {"$gte": p_start, "$lt": p_end},
        }},
        {"$group": {"_id": None, "avg": {"$avg": "$customer_rating"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    prev_avg = round(float(prev[0]["avg"]), 2) if prev else None
    prev_count = int(prev[0]["n"]) if prev else 0

    # Pick the single "best" comment: prefer 5★ with a non-empty comment;
    # tie-break on longest comment so we surface something substantive.
    comment_docs = await db.svc_cases.find(
        {
            "assigned_engineer_id": engineer_user_id,
            "customer_rating": {"$gte": 4},
            "customer_rating_comment": {"$exists": True, "$nin": [None, ""]},
            "customer_feedback_at": {"$gte": start, "$lt": end},
        },
        {"_id": 0, "customer_rating": 1, "customer_rating_comment": 1, "customer_name": 1},
    ).to_list(50)
    best_quote: Optional[dict] = None
    for d in comment_docs:
        score = (
            int(d.get("customer_rating") or 0) * 1000
            + len((d.get("customer_rating_comment") or "").strip())
        )
        if best_quote is None or score > best_quote["_score"]:
            best_quote = {
                "_score": score,
                "rating": int(d["customer_rating"]),
                "comment": (d.get("customer_rating_comment") or "").strip(),
                "customer_name": d.get("customer_name") or "A customer",
            }
    if best_quote:
        best_quote.pop("_score", None)

    return {
        "period": _period_label(year, month),
        "period_y": year, "period_m": month,
        "avg": avg, "count": count,
        "distribution": distribution,
        "prev_avg": prev_avg, "prev_count": prev_count,
        "delta": round(avg - prev_avg, 2) if prev_avg is not None else None,
        "best_quote": best_quote,
    }


def _trend_pill_html(delta: Optional[float]) -> str:
    if delta is None:
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
            'background:#f1f5f9;color:#475569;font-size:11px;font-weight:600;">'
            'First month tracked</span>'
        )
    if delta > 0:
        return (
            f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
            f'background:#d1fae5;color:#065f46;font-size:11px;font-weight:700;">'
            f'▲ +{delta:.2f} vs last month</span>'
        )
    if delta < 0:
        return (
            f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
            f'background:#fee2e2;color:#991b1b;font-size:11px;font-weight:700;">'
            f'▼ {delta:.2f} vs last month</span>'
        )
    return (
        '<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        'background:#e0e7ff;color:#3730a3;font-size:11px;font-weight:600;">'
        '— Stable vs last month</span>'
    )


def _linkedin_share_url(report: dict) -> str:
    """Pre-fill a LinkedIn `sharing/share-offsite` URL with a humblebrag-
    style quote about the engineer's month."""
    base = (PUBLIC_BASE_URL or "https://www.pulsefitness.ai").rstrip("/")
    # Land on the public engineer card eventually — for now, the Pulse Fitness
    # homepage is fine as a fallback target.
    text = (
        f"⭐ {report['avg']:.1f} avg from {report['count']} customer "
        f"review{'' if report['count'] == 1 else 's'} this month. "
        f"Proud of the work via @Pulse Fitness — building a healthier fitness "
        f"industry one machine at a time."
    )
    params = {
        "url": base,
        "summary": text,
    }
    return "https://www.linkedin.com/sharing/share-offsite/?" + urllib.parse.urlencode(params)


def render_monthly_report_html(*, engineer: dict, report: dict, ratings_url: str) -> str:
    period_y, period_m = report["period_y"], report["period_m"]
    month_name = date(period_y, period_m, 1).strftime("%B %Y")
    avg = report["avg"]
    count = report["count"]
    full_stars = "★" * int(round(avg))
    empty_stars = "☆" * (5 - int(round(avg)))
    trend = _trend_pill_html(report.get("delta"))
    quote_block = ""
    if report.get("best_quote"):
        bq = report["best_quote"]
        quote_block = f"""
        <div style="margin:18px 0;padding:14px 18px;background:#fefce8;border-left:4px solid #f59e0b;border-radius:6px;">
          <p style="margin:0 0 6px;color:#78350f;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">⭐ Quote of the month</p>
          <p style="margin:0;color:#0f172a;font-size:14px;line-height:1.6;font-style:italic;">"{bq['comment'][:280]}"</p>
          <p style="margin:6px 0 0;color:#64748b;font-size:11px;">— {bq['customer_name']}</p>
        </div>
        """
    dist = report["distribution"]
    max_dist = max(dist.values()) or 1
    dist_rows = ""
    for stars in [5, 4, 3, 2, 1]:
        n = dist[str(stars)]
        pct = int((n / max_dist) * 100)
        dist_rows += f"""
        <tr>
          <td style="font-size:12px;color:#475569;padding:2px 8px 2px 0;width:30px;font-weight:700;">{stars} ★</td>
          <td style="padding:2px 0;">
            <div style="height:8px;background:#f1f5f9;border-radius:999px;overflow:hidden;">
              <div style="width:{pct}%;height:100%;background:#f59e0b;"></div>
            </div>
          </td>
          <td style="font-size:11px;color:#64748b;text-align:right;padding:2px 0 2px 8px;width:24px;">{n}</td>
        </tr>
        """
    li_url = _linkedin_share_url(report)
    first_name = (engineer.get("full_name") or "Engineer").split(" ")[0]
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:600px;margin:0 auto;">
      <h2 style="margin:0 0 6px;font-size:20px;color:#0f172a;">Your {month_name} reputation report</h2>
      <p style="margin:0 0 20px;color:#475569;font-size:14px;">
        Hey {first_name} — here's how customers rated your work this month.
      </p>
      <div style="text-align:center;padding:20px 16px;background:linear-gradient(135deg,#fef3c7 0%,#fde68a 100%);border-radius:12px;margin:0 0 14px;">
        <p style="margin:0;font-size:11px;font-weight:700;color:#78350f;letter-spacing:.12em;text-transform:uppercase;">Average</p>
        <p style="margin:6px 0 4px;font-size:42px;font-weight:900;color:#92400e;line-height:1;">{avg:.1f}</p>
        <p style="margin:0;font-size:18px;color:#f59e0b;letter-spacing:.04em;">{full_stars}<span style="color:#fcd34d;">{empty_stars}</span></p>
        <p style="margin:8px 0 0;font-size:12px;color:#78350f;">From {count} review{'' if count == 1 else 's'} · {trend}</p>
      </div>
      {quote_block}
      <table style="width:100%;border-collapse:collapse;margin:18px 0;">{dist_rows}</table>
      <div style="text-align:center;margin:22px 0 12px;">
        <a href="{ratings_url}"
           style="display:inline-block;padding:10px 22px;background:#1d4ed8;color:white;text-decoration:none;border-radius:8px;font-weight:700;font-size:13px;">
           See every review →
        </a>
        <a href="{li_url}"
           target="_blank" rel="noopener"
           style="display:inline-block;padding:10px 22px;margin-left:8px;background:#0a66c2;color:white;text-decoration:none;border-radius:8px;font-weight:700;font-size:13px;">
           Share on LinkedIn
        </a>
      </div>
      <p style="margin:24px 0 6px;color:#64748b;font-size:11px;line-height:1.5;">
        You're getting this because you're a Pulse Fitness Partner Engineer with at least
        one customer rating last month. Reports fire once on the 1st of each month —
        no daily noise.
      </p>
    </div>
    """


async def send_monthly_report_to(partner: dict, year: int, month: int) -> dict:
    """Build + send a single report. Returns `{sent: bool, reason?: str}`.

    Caller is responsible for the idempotency stamp."""
    user_id = partner.get("user_id")
    if not user_id:
        return {"sent": False, "reason": "no_user_id"}
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "full_name": 1, "organization_id": 1})
    if not user or not user.get("email"):
        return {"sent": False, "reason": "user_or_email_missing"}
    report = await build_monthly_report(engineer_user_id=user_id, year=year, month=month)
    if report is None:
        return {"sent": False, "reason": "no_ratings_in_period"}
    base = (PUBLIC_BASE_URL or "").rstrip("/")
    ratings_url = f"{base}/svc/engineer/ratings" if base else "/svc/engineer/ratings"
    html = render_monthly_report_html(engineer=user, report=report, ratings_url=ratings_url)
    month_name = date(year, month, 1).strftime("%B %Y")
    await send_email(
        to=user["email"],
        subject=f"Your {month_name} reputation report — {report['avg']:.1f} avg from {report['count']} reviews",
        html=html,
        organization_id=user.get("organization_id"),
    )
    return {"sent": True, "report": report}


async def run_monthly_reputation_reports(*, force_period: Optional[str] = None) -> dict:
    """One sweep. Eligible iff:
      • today is the 1st of the month, OR `force_period` is given.
      • partner.reputation_reports.last_sent_period != current period.

    Returns a summary `{checked, sent, skipped}` for log + tests.
    """
    today = datetime.now(timezone.utc).date()
    if force_period:
        try:
            year_s, month_s = force_period.split("-")
            year, month = int(year_s), int(month_s)
        except ValueError:
            return {"checked": 0, "sent": 0, "skipped": 0, "error": "bad_force_period"}
    else:
        if today.day != 1:
            return {"checked": 0, "sent": 0, "skipped": 0, "reason": "not_first_of_month"}
        # On the 1st we send the report for the *previous* month.
        year, month = _previous_period(today.year, today.month)
    period = _period_label(year, month)

    cursor = db.partner_engineers.find(
        {"status": "approved", "user_id": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "user_id": 1, "reputation_reports": 1},
    )
    partners = await cursor.to_list(length=None)
    summary = {"checked": 0, "sent": 0, "skipped": 0, "period": period}
    for p in partners:
        summary["checked"] += 1
        rr = (p.get("reputation_reports") or {})
        if rr.get("last_sent_period") == period and not force_period:
            summary["skipped"] += 1
            continue
        try:
            res = await send_monthly_report_to(p, year, month)
        except Exception as exc:
            logger.exception("[reputation-reports] send failed for partner %s: %s", p.get("id"), exc)
            summary["skipped"] += 1
            continue
        if res.get("sent"):
            await db.partner_engineers.update_one(
                {"id": p["id"]},
                {"$set": {"reputation_reports.last_sent_period": period,
                          "reputation_reports.last_sent_at": datetime.now(timezone.utc).isoformat()}},
            )
            summary["sent"] += 1
        else:
            summary["skipped"] += 1
    return summary


async def run_forever(interval_hours: int = 6) -> None:
    """Background loop. Wakes every `interval_hours` (default 6h); the
    sweep itself is idempotent and a no-op outside the 1st of the
    month."""
    logger.info(f"[reputation-reports] loop started (every {interval_hours}h)")
    while True:
        try:
            summary = await run_monthly_reputation_reports()
            if summary.get("sent") or summary.get("checked"):
                logger.info(f"[reputation-reports] sweep: {summary}")
        except Exception as exc:
            logger.exception("[reputation-reports] sweep crashed: %s", exc)
        await asyncio.sleep(interval_hours * 3600)


__all__ = [
    "build_monthly_report",
    "send_monthly_report_to",
    "run_monthly_reputation_reports",
    "render_monthly_report_html",
    "run_forever",
]
