"""Weekly MOD Estate Readiness email to HQ.

Every Monday at 09:00 UTC we email the whole-of-MOD go-live readiness
checklist (the same Excel produced by the Master Admin "Readiness
checklist (Excel)" button) to HQ, with an HTML summary table in the body.

Hooked into the existing sicon poller (runs every ~5 min); this dispatcher
gates itself to Monday >= 09:00 UTC and is idempotent per ISO week via a
`system_jobs` lock so it fires at most once a week regardless of cron cadence.
A Master Admin "Send now" endpoint reuses `send_mod_readiness_email(force=True)`.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

DEFAULT_ESTATE_ID = "uk-mod"
JOB_KEY = "mod_readiness_weekly_email"
SEND_HOUR_UTC = int(os.environ.get("MOD_READINESS_SEND_HOUR_UTC", "9"))


def _hq_recipient() -> str:
    return (os.environ.get("MOD_READINESS_HQ_EMAIL")
            or "modservice@pulsefitness.com")


def _iso_week_tag(dt: datetime) -> str:
    """Monday-anchored ISO week key, e.g. 2026-W23."""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _summary_html(data: dict, estate_name: str = "UK Ministry of Defence") -> str:
    t = data.get("totals", {})
    sites = data.get("sites", [])
    total = t.get("sites", 0)
    ready = t.get("fully_ready", 0)
    no_equip = t.get("no_equipment", 0)
    not_ready = total - ready

    step_labels = [
        ("equipment", "Equipment"), ("staff", "Staff"), ("suppliers", "Suppliers"),
        ("documents", "Documents"), ("checks", "Check Sheets"),
    ]

    def _chip(ok: bool, count: int) -> str:
        colour = "#0a7d3a" if ok else "#b42318"
        bg = "#e7f6ec" if ok else "#fdeceb"
        mark = "✓" if ok else "✗"
        return (f'<td style="text-align:center;background:{bg};color:{colour};'
                f'font-weight:600;padding:6px 8px;border:1px solid #eaecf0;">'
                f'{count}&nbsp;{mark}</td>')

    rows = []
    for s in sorted(sites, key=lambda x: (not x.get("fully_ready"), x.get("name") or "")):
        st = s.get("steps", {})
        loc = "Overseas" if s.get("is_overseas") else (s.get("region") or "UK")
        ready_badge = ('<span style="background:#e7f6ec;color:#0a7d3a;border-radius:999px;'
                       'padding:2px 10px;font-size:12px;font-weight:700;">READY</span>'
                       if s.get("fully_ready") else
                       '<span style="background:#fdeceb;color:#b42318;border-radius:999px;'
                       'padding:2px 10px;font-size:12px;font-weight:700;">Not yet</span>')
        cells = "".join(
            _chip(st.get(k, {}).get("ready", False), st.get(k, {}).get("count", 0))
            for k, _ in step_labels
        )
        rows.append(
            f'<tr><td style="padding:6px 8px;border:1px solid #eaecf0;font-weight:600;">'
            f'{s.get("name","")}</td>'
            f'<td style="padding:6px 8px;border:1px solid #eaecf0;color:#475467;">'
            f'{(s.get("force") or "").upper()}</td>'
            f'<td style="padding:6px 8px;border:1px solid #eaecf0;color:#475467;">{loc}</td>'
            f'{cells}'
            f'<td style="text-align:center;padding:6px 8px;border:1px solid #eaecf0;">'
            f'{ready_badge}</td></tr>'
        )
    body_rows = "".join(rows) or (
        '<tr><td colspan="9" style="padding:14px;text-align:center;color:#667085;">'
        'No MOD sites found for this estate.</td></tr>'
    )

    head_cells = "".join(
        f'<th style="padding:8px;background:#19398D;color:#fff;border:1px solid #19398D;'
        f'font-size:12px;text-align:center;">{lbl}</th>' for _, lbl in step_labels
    )

    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#101828;max-width:820px;">
      <h2 style="color:#19398D;margin:0 0 4px;">MOD Estate — Weekly Go-live Readiness</h2>
      <p style="color:#667085;margin:0 0 18px;">{estate_name} · week of
        {datetime.now(timezone.utc).strftime('%d %b %Y')}</p>
      <table style="border-collapse:collapse;margin-bottom:18px;">
        <tr>
          <td style="padding:10px 18px;background:#f2f4f7;border-radius:8px 0 0 8px;">
            <div style="font-size:24px;font-weight:800;">{total}</div>
            <div style="font-size:12px;color:#667085;">Total sites</div></td>
          <td style="padding:10px 18px;background:#e7f6ec;">
            <div style="font-size:24px;font-weight:800;color:#0a7d3a;">{ready}</div>
            <div style="font-size:12px;color:#667085;">Go-live ready</div></td>
          <td style="padding:10px 18px;background:#fef4e6;">
            <div style="font-size:24px;font-weight:800;color:#b54708;">{not_ready}</div>
            <div style="font-size:12px;color:#667085;">Not yet ready</div></td>
          <td style="padding:10px 18px;background:#fdeceb;border-radius:0 8px 8px 0;">
            <div style="font-size:24px;font-weight:800;color:#b42318;">{no_equip}</div>
            <div style="font-size:12px;color:#667085;">Awaiting equipment</div></td>
        </tr>
      </table>
      <table style="border-collapse:collapse;width:100%;font-size:13px;">
        <thead><tr>
          <th style="padding:8px;background:#19398D;color:#fff;border:1px solid #19398D;text-align:left;">Site</th>
          <th style="padding:8px;background:#19398D;color:#fff;border:1px solid #19398D;">Force</th>
          <th style="padding:8px;background:#19398D;color:#fff;border:1px solid #19398D;">Location</th>
          {head_cells}
          <th style="padding:8px;background:#19398D;color:#fff;border:1px solid #19398D;">Go-live</th>
        </tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
      <p style="color:#667085;font-size:12px;margin-top:16px;">
        The full checklist (colour-coded per step, plus a summary sheet) is attached as
        <strong>MOD_Estate_Readiness.xlsx</strong>. Automated every Monday morning.
      </p>
    </div>
    """


async def send_mod_readiness_email(estate_id: str = DEFAULT_ESTATE_ID,
                                    to: str | None = None,
                                    force: bool = False) -> dict:
    """Build the readiness Excel + HTML summary and email HQ.

    `force=True` (manual trigger) bypasses the once-per-week lock.
    Returns a small dict describing what happened.
    """
    from routes.master_admin_mod_estate import (
        _compute_estate_readiness, build_readiness_xlsx_bytes,
        DEFAULT_ESTATE_NAME,
    )

    now = datetime.now(timezone.utc)
    week_tag = _iso_week_tag(now)
    recipient = to or _hq_recipient()

    if not force:
        # Idempotent per ISO week: claim the lock atomically.
        res = await db.system_jobs.update_one(
            {"job": JOB_KEY, "week_tag": {"$ne": week_tag}},
            {"$set": {"job": JOB_KEY, "week_tag": week_tag, "claimed_at": now.isoformat()}},
            upsert=True,
        )
        if res.modified_count == 0 and res.upserted_id is None:
            return {"skipped": "already_sent_this_week", "week_tag": week_tag}

    data = await _compute_estate_readiness(estate_id)
    xlsx = build_readiness_xlsx_bytes(data)
    html = _summary_html(data, DEFAULT_ESTATE_NAME)
    totals = data.get("totals", {})

    subject = (f"MOD Estate readiness — {totals.get('fully_ready', 0)}/"
               f"{totals.get('sites', 0)} sites go-live ready · {now.strftime('%d %b %Y')}")

    ok = await send_email(
        recipient,
        subject,
        html,
        attachments=[{
            "filename": "MOD_Estate_Readiness.xlsx",
            "content": base64.b64encode(xlsx).decode("ascii"),
        }],
        kind="mod_readiness_digest",
        category="service",
    )

    await db.system_jobs.update_one(
        {"job": JOB_KEY},
        {"$set": {"job": JOB_KEY, "week_tag": week_tag,
                  "last_sent_at": now.isoformat(), "last_recipient": recipient,
                  "last_ok": bool(ok), "last_totals": totals}},
        upsert=True,
    )
    logger.info(f"[mod-readiness] emailed HQ={recipient} ok={ok} week={week_tag}")
    return {"sent": bool(ok), "recipient": recipient, "week_tag": week_tag,
            "totals": totals, "sites": len(data.get("sites", []))}


async def run_mod_readiness_weekly() -> dict:
    """Cron entrypoint. Fires only on Monday at/after SEND_HOUR_UTC; the
    per-week system_jobs lock guarantees at most one send per week."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 0 or now.hour < SEND_HOUR_UTC:
        return {"skipped": "not_due", "weekday": now.weekday(), "hour": now.hour}
    return await send_mod_readiness_email()
