"""GymAxis Memberships — Weekly Autopilot Digest.

Once per UTC-Monday, per organisation, we build a PDF executive brief +
a concise HTML summary (headline + top-5 at-risk members) and email it to
every operator user in the org. The dispatcher is idempotent: a run-tag
`digest_date=YYYY-MM-DD` is written on the org doc so repeated poller
cycles within the same day are no-ops.

Triggered from `sicon_poller._run_weekly_digest()`.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

_BRAND_BG = "#05070A"
_BRAND_ACCENT = "#19CDFF"


def _monday_key(dt: datetime) -> str:
    """Return YYYY-MM-DD of the Monday of the week containing dt (UTC)."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.date().isoformat()


def _risk_row(m: dict) -> str:
    name = (m.get("name") or "Member").strip() or "Member"
    reason = m.get("reason") or "Low recent activity"
    score = m.get("risk_score") or 0
    return f"""<tr>
      <td style="padding:8px 4px;border-bottom:1px solid rgba(255,255,255,0.08);">
        <div style="font-weight:700;color:#fff;">{name}</div>
        <div style="color:#9ca3af;font-size:12px;">{reason}</div>
      </td>
      <td style="padding:8px 4px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.08);">
        <span style="display:inline-block;padding:3px 8px;border-radius:4px;background:rgba(244,63,94,0.15);color:#F43F5E;font-size:12px;font-weight:700;">{score}</span>
      </td>
    </tr>"""


def _kpi_row(label: str, value: str) -> str:
    return f"""<tr>
      <td style="padding:6px 4px;color:#9ca3af;font-size:13px;">{label}</td>
      <td style="padding:6px 4px;color:#fff;font-weight:700;text-align:right;font-size:13px;">{value}</td>
    </tr>"""


def _build_html(org: dict, brief: dict, kpis: dict, at_risk: list[dict], app_url: str | None) -> str:
    headline = brief.get("headline") or "Weekly brief"
    narrative = brief.get("narrative") or ""
    actions = brief.get("actions") or []
    top_at_risk = at_risk[:5]
    risk_table = (
        "<table style='width:100%;border-collapse:collapse;margin-top:8px;'>"
        + "".join(_risk_row(m) for m in top_at_risk)
        + "</table>"
    ) if top_at_risk else "<p style='color:#9ca3af;'>No at-risk members flagged this week — nice.</p>"
    kpi_table = (
        "<table style='width:100%;border-collapse:collapse;'>"
        + _kpi_row("MRR",             f"£{kpis.get('mrr_gbp', 0):.0f}")
        + _kpi_row("ARPU",            f"£{kpis.get('arpu_gbp', 0):.2f}")
        + _kpi_row("Active members",  str(kpis.get("active_members", 0)))
        + _kpi_row("Net growth",      f"{'+' if kpis.get('net_growth', 0) >= 0 else ''}{kpis.get('net_growth', 0)}")
        + _kpi_row("Churn %",         f"{kpis.get('churn_pct', 0)}%")
        + _kpi_row("Occupancy",       f"{kpis.get('occupancy_pct', 0)}%")
        + _kpi_row("Revenue (week)",  f"£{kpis.get('revenue_gbp', 0):,.0f}")
        + "</table>"
    )
    actions_html = ""
    if actions:
        items = "".join(f"<li style='margin:6px 0;color:#e5e7eb;'>{a}</li>" for a in actions)
        actions_html = f"""<div style='margin-top:16px;padding:14px 16px;border-left:3px solid {_BRAND_ACCENT};background:rgba(25,205,255,0.06);border-radius:6px;'>
          <div style='color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px;'>Recommended actions</div>
          <ol style='margin:0 0 0 18px;padding:0;'>{items}</ol>
        </div>"""
    app_link_html = f"""<p style='color:#9ca3af;font-size:13px;margin-top:18px;'>
        Jump back into the analytics dashboard: <a href='{app_url}' style='color:{_BRAND_ACCENT};text-decoration:none;font-weight:700;'>{app_url}</a>
      </p>""" if app_url else ""
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:620px;margin:0 auto;background:{_BRAND_BG};color:#fff;border-radius:16px;overflow:hidden;">
      <div style="padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.25);">
        <div style="color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">Weekly brief · {org.get('name', 'Studio')}</div>
        <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{headline}</h1>
      </div>
      <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
        <p style="margin:0 0 18px;color:#d1d5db;">{narrative}</p>
        <div style="color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin:18px 0 6px;">Key metrics</div>
        {kpi_table}
        {actions_html}
        <div style="color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin:22px 0 6px;">Top 5 at-risk members</div>
        {risk_table}
        {app_link_html}
      </div>
      <div style="background:{_BRAND_BG};padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
        <p style="color:#6b7280;font-size:11px;margin:0;">GymAxis Memberships · Autopilot digest · Full PDF attached</p>
      </div>
    </div>"""


async def _build_weekly_pdf(org_id: str) -> bytes | None:
    """Re-use the analytics PDF helper to get a branded brief as bytes."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import mm
        import io
        from utils.memberships_ai_insights import generate_executive_brief

        # Build KPIs by calling the aggregation helper directly (non-HTTP)
        from routes.memberships_analytics import analytics_overview, analytics_operations
        # Fake a user dict with the org_id so the dependency passes
        pseudo_user = {"organization_id": org_id, "id": "digest-bot"}
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        ov = await analytics_overview(
            from_=start.isoformat(), to=now.isoformat(),
            site_id=None, period="weekly", user=pseudo_user,
        )
        ops = await analytics_operations(
            from_=start.isoformat(), to=now.isoformat(), user=pseudo_user,
        )
        brief = await generate_executive_brief({
            "period": "weekly", "kpis": ov["kpis"], "alerts": ops["alerts"],
            "top_classes": [], "underperforming_classes": [],
            "revenue_forecast": ov.get("revenue_forecast", []),
        })

        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        W, H = A4
        c.setFillColorRGB(0.098, 0.804, 1)
        c.rect(0, H - 25 * mm, W, 25 * mm, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(20 * mm, H - 16 * mm, "GymAxis Memberships — Weekly Brief")
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, H - 22 * mm, f"Generated {now.isoformat()[:10]}")

        y = H - 40 * mm
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, brief.get("headline") or "Executive brief")
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        text = c.beginText(20 * mm, y)
        for line in (brief.get("narrative") or "").split("\n"):
            text.textLine(line[:110])
        c.drawText(text)
        y -= 40 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Key metrics")
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        for k, v in ov["kpis"].items():
            c.drawString(20 * mm, y, f"• {k.replace('_', ' ').title()}: {v}")
            y -= 5 * mm
            if y < 20 * mm:
                c.showPage()
                y = H - 20 * mm
        c.showPage()
        c.save()
        return buf.getvalue(), ov, brief
    except Exception:
        logger.exception("[digest] weekly pdf build failed")
        return None, None, None


async def send_weekly_digest_for_org(org: dict, force: bool = False) -> dict:
    """Build + email the weekly brief to all operator users on this org.

    Returns {sent: [...emails], skipped: reason?}. Idempotent via
    `memberships_digest.last_sent_monday` on the org doc.
    """
    org_id = org.get("id")
    if not org_id:
        return {"skipped": "no-org-id"}
    now = datetime.now(timezone.utc)
    monday_tag = _monday_key(now)
    if not force and (org.get("memberships_digest") or {}).get("last_sent_monday") == monday_tag:
        return {"skipped": "already_sent_this_week"}

    # Recipients: users on this org that are not deactivated and have a "member_ops" footprint.
    # We're conservative: email every non-deactivated user in the org.
    users = await db.users.find(
        {"organization_id": org_id, "deactivated": {"$ne": True}, "email": {"$exists": True, "$ne": None}},
        {"_id": 0, "email": 1, "first_name": 1},
    ).to_list(200)
    if not users:
        return {"skipped": "no_operators"}

    # Build PDF + pull KPIs + brief
    pdf_bytes, overview, brief = await _build_weekly_pdf(org_id)
    if not overview:
        return {"skipped": "build_failed"}

    # At-risk top 5 — pull via direct helper to avoid HTTP loopback
    try:
        from routes.memberships_analytics import at_risk_members
        ar = await at_risk_members(limit=5, user={"organization_id": org_id, "id": "digest-bot"})
        at_risk = ar.get("members") or []
    except Exception:
        at_risk = []

    # Find the gym's public URL (if slug is set)
    slug = org.get("slug")
    public_url = None
    if slug:
        # Use the backend SENDER url or fall back to a relative hint
        import os
        origin = os.environ.get("PUBLIC_ORIGIN") or os.environ.get("FRONTEND_ORIGIN")
        public_url = f"{origin}/memberships" if origin else None

    html = _build_html(org, brief or {}, overview.get("kpis", {}), at_risk, public_url)

    attachments = []
    if pdf_bytes:
        attachments.append({
            "filename": "weekly-brief.pdf",
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
        })

    sent: list[str] = []
    for u in users:
        ok = await send_email(
            u["email"],
            f"GymAxis weekly brief · {org.get('name', 'Studio')} · {monday_tag}",
            html,
            attachments=attachments or None,
        )
        if ok:
            sent.append(u["email"])

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"memberships_digest.last_sent_monday": monday_tag,
                  "memberships_digest.last_sent_at": now.isoformat(),
                  "memberships_digest.last_recipients": sent}},
    )
    logger.info(f"[memberships-digest] org={org_id} sent={len(sent)}")
    return {"sent": sent, "monday": monday_tag}


async def run_weekly_digest_dispatcher(force: bool = False) -> dict:
    """Called by the sicon poller. Scans Memberships-enabled orgs and fires
    the weekly digest where due. Uses the `setup_completed` flag as the
    proxy for 'this org is using Memberships'."""
    now = datetime.now(timezone.utc)
    # Only fire on Mondays (UTC) unless forced for manual dispatch
    if not force and now.weekday() != 0:
        return {"skipped": "not_monday", "weekday": now.weekday()}
    totals = {"orgs_scanned": 0, "orgs_sent": 0, "recipients": 0, "errors": 0}
    async for org in db.organizations.find(
        {"setup_completed": True, "slug": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ):
        totals["orgs_scanned"] += 1
        try:
            res = await send_weekly_digest_for_org(org, force=force)
            if res.get("sent"):
                totals["orgs_sent"] += 1
                totals["recipients"] += len(res["sent"])
        except Exception:
            totals["errors"] += 1
            logger.exception("[memberships-digest] org failed: %s", org.get("id"))
    logger.info(f"[memberships-digest] cycle complete {totals}")
    return totals
