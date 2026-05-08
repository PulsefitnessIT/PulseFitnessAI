"""
GymAxis Service Operations — Email digest dispatcher.

Iter 216y (Phase 6+).

Sends a daily/weekly summary email to every org with
`svc_digest_enabled = True`. Cadence is checked against
`svc_digest_last_sent_at` so the cron tick is safe to run as often as
the platform poller fires (we'll only actually send when due).

Dispatcher is wired into `utils/sicon_poller.py` so it inherits the
existing daily run cadence and the per-tick log scaffolding.
"""
from datetime import datetime, timezone, timedelta
import logging

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def run_svc_digest_dispatcher() -> dict:
    """Iterate every org with the digest enabled and send if it's due."""
    orgs = await db.organizations.find(
        {"svc_digest_enabled": True},
        {"_id": 0, "id": 1, "name": 1, "svc_digest_cadence": 1,
         "svc_digest_recipients": 1, "svc_digest_last_sent_at": 1},
    ).to_list(2000)
    sent = 0
    skipped = 0
    errors = 0
    now = _now()
    for org in orgs:
        cadence = (org.get("svc_digest_cadence") or "weekly").lower()
        last_iso = org.get("svc_digest_last_sent_at")
        last_dt = None
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
            except Exception:
                last_dt = None
        due = last_dt is None
        if not due:
            window = timedelta(days=1) if cadence == "daily" else timedelta(days=7)
            due = (now - last_dt) >= window
        if not due:
            skipped += 1
            continue
        try:
            n = await send_digest_for_org(org["id"], cadence_override=cadence)
            sent += n
        except Exception:
            errors += 1
            logger.exception("[svc-digest] org=%s send failed", org.get("id"))
    if sent or errors:
        logger.info("[svc-digest] cycle complete sent=%s skipped=%s errors=%s",
                    sent, skipped, errors)
    return {"sent": sent, "skipped": skipped, "errors": errors}


async def send_digest_for_org(
    organization_id: str,
    *,
    force: bool = False,
    cadence_override: str | None = None,
) -> int:
    """Render & send the digest for a single org. Returns the number of
    emails actually dispatched.

    `force=True` ignores the cadence guard (used by the "Send test" button).
    """
    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "id": 1, "name": 1, "svc_digest_enabled": 1,
         "svc_digest_cadence": 1, "svc_digest_recipients": 1},
    )
    if not org:
        return 0
    if not force and not org.get("svc_digest_enabled"):
        return 0
    recipients = [r for r in (org.get("svc_digest_recipients") or [])
                  if r and "@" in r]
    if not recipients:
        return 0
    cadence = cadence_override or org.get("svc_digest_cadence") or "weekly"
    days = 1 if cadence == "daily" else 7
    org_name = org.get("name") or "GymAxis"

    horizon_iso = (_now() - timedelta(days=days)).isoformat()
    now_iso = _now().isoformat()
    of = {"organization_id": organization_id}

    # Counts
    open_cases = await db.svc_cases.count_documents({**of,
        "status": {"$nin": ["closed", "invoiced", "rejected"]}})
    new_in_window = await db.svc_cases.count_documents({**of,
        "created_at": {"$gte": horizon_iso}})
    closed_in_window = await db.svc_cases.count_documents({**of,
        "status": {"$in": ["closed", "invoiced"]},
        "closed_at": {"$gte": horizon_iso}})
    sla_breached = await db.svc_cases.count_documents({**of,
        "status": {"$nin": ["closed", "invoiced", "rejected"]},
        "sla_resolve_at": {"$lte": now_iso}})

    # Top open cases (priority + SLA risk)
    top_open = await db.svc_cases.find(
        {**of, "status": {"$nin": ["closed", "invoiced", "rejected"]}},
        {"_id": 0, "reference": 1, "title": 1, "priority": 1,
         "site_name": 1, "sla_resolve_at": 1, "assigned_engineer_name": 1},
    ).sort("sla_resolve_at", 1).limit(8).to_list(8)

    # Recently closed
    recent_closed = await db.svc_cases.find(
        {**of, "status": {"$in": ["closed", "invoiced"]},
         "closed_at": {"$gte": horizon_iso}},
        {"_id": 0, "reference": 1, "title": 1, "site_name": 1,
         "closed_at": 1, "assigned_engineer_name": 1},
    ).sort("closed_at", -1).limit(8).to_list(8)

    period_label = "yesterday" if cadence == "daily" else "the last 7 days"
    subject = f"GymAxis service digest — {org_name} · {period_label}"

    def _row(c, ts_field):
        ts = c.get(ts_field) or ""
        ts_short = (ts[:16] + "Z") if ts else ""
        ref = c.get("reference") or ""
        title = (c.get("title") or "")[:60]
        site = c.get("site_name") or "—"
        eng = c.get("assigned_engineer_name") or "<i>unassigned</i>"
        prio = (c.get("priority") or "p3").upper()
        return (
            f"<tr><td style='padding:4px 8px;font-family:ui-monospace,monospace'>{ref}</td>"
            f"<td style='padding:4px 8px'>{prio}</td>"
            f"<td style='padding:4px 8px'>{title}</td>"
            f"<td style='padding:4px 8px;color:#64748b'>{site}</td>"
            f"<td style='padding:4px 8px;color:#64748b'>{eng}</td>"
            f"<td style='padding:4px 8px;color:#64748b;font-family:ui-monospace,monospace'>{ts_short}</td></tr>"
        )

    open_rows = "".join(_row(c, "sla_resolve_at") for c in top_open) or \
        "<tr><td colspan='6' style='padding:8px;color:#64748b;font-style:italic'>No open cases.</td></tr>"
    closed_rows = "".join(_row(c, "closed_at") for c in recent_closed) or \
        f"<tr><td colspan='6' style='padding:8px;color:#64748b;font-style:italic'>None closed in {period_label}.</td></tr>"

    body = f"""
<div style='font-family:Inter,system-ui,sans-serif;color:#0f172a;max-width:680px'>
  <h1 style='font-size:18px;margin:0 0 4px'>{org_name} — service operations digest</h1>
  <p style='color:#64748b;margin:0 0 16px;font-size:12px'>Window: {period_label} · Generated {now_iso[:16]}Z</p>

  <table style='width:100%;border-collapse:collapse;margin:0 0 16px'>
    <tr>
      <td style='padding:8px;background:#eef2ff;border-radius:8px;text-align:center'>
        <div style='font-size:11px;color:#1d4ed8;font-weight:700'>OPEN</div>
        <div style='font-size:22px;font-weight:800'>{open_cases}</div>
      </td>
      <td style='padding:8px;background:#ecfdf5;border-radius:8px;text-align:center'>
        <div style='font-size:11px;color:#047857;font-weight:700'>NEW</div>
        <div style='font-size:22px;font-weight:800'>{new_in_window}</div>
      </td>
      <td style='padding:8px;background:#f0fdf4;border-radius:8px;text-align:center'>
        <div style='font-size:11px;color:#15803d;font-weight:700'>CLOSED</div>
        <div style='font-size:22px;font-weight:800'>{closed_in_window}</div>
      </td>
      <td style='padding:8px;background:#fef2f2;border-radius:8px;text-align:center'>
        <div style='font-size:11px;color:#b91c1c;font-weight:700'>SLA BREACHED</div>
        <div style='font-size:22px;font-weight:800'>{sla_breached}</div>
      </td>
    </tr>
  </table>

  <h2 style='font-size:14px;margin:16px 0 8px'>Top open cases (SLA-risk first)</h2>
  <table style='width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden'>
    <thead><tr style='background:#f1f5f9;text-align:left'>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Ref</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Pri</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Title</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Site</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Engineer</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>SLA</th>
    </tr></thead>
    <tbody>{open_rows}</tbody>
  </table>

  <h2 style='font-size:14px;margin:20px 0 8px'>Recently closed</h2>
  <table style='width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden'>
    <thead><tr style='background:#f1f5f9;text-align:left'>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Ref</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Pri</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Title</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Site</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Engineer</th>
      <th style='padding:6px 8px;font-size:10px;text-transform:uppercase'>Closed</th>
    </tr></thead>
    <tbody>{closed_rows}</tbody>
  </table>

  <p style='font-size:11px;color:#64748b;margin-top:24px'>
    You're receiving this because the GymAxis Service Ops digest is enabled for {org_name}.
    Toggle it off in <strong>Service Ops → Reports → Email digest</strong>.
  </p>
</div>
""".strip()

    sent = 0
    for to in recipients:
        try:
            ok = await send_email(to=to, subject=subject, html=body)
            if ok:
                sent += 1
        except Exception:
            logger.exception("[svc-digest] send failed for %s", to)

    await db.organizations.update_one(
        {"id": organization_id},
        {"$set": {
            "svc_digest_last_sent_at": _now().isoformat(),
            "svc_digest_last_sent_count": sent,
        }},
    )
    return sent


__all__ = ["run_svc_digest_dispatcher", "send_digest_for_org"]
