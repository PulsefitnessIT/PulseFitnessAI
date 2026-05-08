"""GymAxis Memberships — Launch Kit bundle.

When a gym finishes the Setup Wizard we send them a single email packed
with everything they need to launch publicly:

  • A4 poster PDF (print shop)
  • Instagram square PNG (feed post)
  • Instagram story PNG (9:16)
  • Ready-to-paste WhatsApp + Instagram caption
  • Email template for their existing member list
  • Link to the live member app + brag card + share URL

Idempotent: `organization.launch_kit_sent_at` stamp prevents double-fires.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone

from utils.database import db
from utils.email import send_email
from utils.memberships_poster import render_poster_png, render_poster_pdf

logger = logging.getLogger(__name__)


def _origin() -> str:
    return (os.environ.get("PUBLIC_ORIGIN")
            or os.environ.get("FRONTEND_ORIGIN")
            or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")


def _build_templates(studio_name: str, app_url: str) -> dict[str, str]:
    wa = (
        f"🎉 {studio_name} is now on GymAxis!\n\n"
        f"Book classes, track your pass, and never miss a session.\n\n"
        f"👉 {app_url}\n\n"
        f"Save this link or add it to your home screen for instant access."
    )
    ig = (
        f"✨ Big news, {studio_name} family.\n\n"
        f"Our brand-new booking app is live. One tap to book, one scan to check in.\n\n"
        f"Link in bio → book your next class 💪\n\n"
        f"#gymaxis #studiolife"
    )
    email = (
        f"Subject: {studio_name} · Our new member app is live 🎉\n\n"
        f"Hey,\n\n"
        f"We've just launched our new booking experience, powered by GymAxis.\n\n"
        f"What you get:\n"
        f"  • See live class times at a glance\n"
        f"  • Book in two taps and get instant confirmations\n"
        f"  • Scan a rotating QR at the door for check-in\n\n"
        f"Open the app: {app_url}\n\n"
        f"See you in class,\n{studio_name}"
    )
    return {"whatsapp": wa, "instagram": ig, "email": email}


def _build_email_html(studio_name: str, brand: str, app_url: str, brag_url: str, share_url: str, templates: dict[str, str]) -> str:
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:620px;margin:0 auto;background:#05070A;color:#fff;border-radius:16px;overflow:hidden;">
  <div style="padding:32px;background:linear-gradient(135deg,{brand}33 0%,transparent 100%);border-bottom:1px solid {brand}55;">
    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">Your launch kit is here</div>
    <h1 style="color:#fff;font-size:26px;margin:0;line-height:1.2;font-weight:800;">Go live today, {studio_name}.</h1>
    <p style="color:#d1d5db;margin:16px 0 0;">Everything you need to tell your members about your new app is attached. Poster for reception. Instagram assets for socials. Message templates for WhatsApp and email — no copywriting required.</p>
  </div>
  <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px;">Your links</div>
    <p style="margin:0 0 6px;">Member app: <a href="{app_url}" style="color:{brand};font-weight:700;text-decoration:none;">{app_url}</a></p>
    <p style="margin:0 0 6px;">Live stats card: <a href="{brag_url}" style="color:{brand};font-weight:700;text-decoration:none;">{brag_url}</a></p>
    <p style="margin:0 0 18px;">Shareable (for WhatsApp/LinkedIn): <a href="{share_url}" style="color:{brand};font-weight:700;text-decoration:none;">{share_url}</a></p>

    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin:20px 0 6px;">WhatsApp / SMS broadcast</div>
    <pre style="background:#05070A;padding:14px;border-radius:8px;color:#e5e7eb;white-space:pre-wrap;font-family:-apple-system,sans-serif;font-size:13px;margin:0;border-left:3px solid {brand};">{templates['whatsapp']}</pre>

    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin:20px 0 6px;">Instagram caption</div>
    <pre style="background:#05070A;padding:14px;border-radius:8px;color:#e5e7eb;white-space:pre-wrap;font-family:-apple-system,sans-serif;font-size:13px;margin:0;border-left:3px solid {brand};">{templates['instagram']}</pre>

    <div style="color:{brand};font-size:10px;font-weight:800;letter-spacing:0.2em;text-transform:uppercase;margin:20px 0 6px;">Email to members</div>
    <pre style="background:#05070A;padding:14px;border-radius:8px;color:#e5e7eb;white-space:pre-wrap;font-family:-apple-system,sans-serif;font-size:13px;margin:0;border-left:3px solid {brand};">{templates['email']}</pre>
  </div>
  <div style="background:#05070A;padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
    <p style="color:#6b7280;font-size:11px;margin:0;">GymAxis · Launch kit · Attached: A4 poster PDF · IG square PNG · IG story PNG</p>
  </div>
</div>"""


async def send_launch_kit(org: dict, force: bool = False) -> dict:
    """Build + email the launch kit to all operator users in the org."""
    org_id = org.get("id")
    if not org_id:
        return {"skipped": "no-org-id"}
    if not force and org.get("launch_kit_sent_at"):
        return {"skipped": "already_sent"}
    slug = org.get("slug")
    if not slug:
        return {"skipped": "no-slug"}

    users = await db.users.find(
        {"organization_id": org_id, "deactivated": {"$ne": True}, "email": {"$exists": True, "$ne": None}},
        {"_id": 0, "email": 1, "first_name": 1},
    ).to_list(50)
    if not users:
        return {"skipped": "no_recipients"}

    origin = _origin()
    app_url = f"{origin}/m/{slug}"
    brag_url = f"{origin}/m/{slug}/brag"
    share_url = f"{origin}/api/m/{slug}/share"

    templates = _build_templates(org.get("name") or "Your Studio", app_url)
    html = _build_email_html(
        org.get("name") or "Your Studio",
        org.get("primary_brand_colour") or "#19CDFF",
        app_url, brag_url, share_url, templates,
    )

    try:
        pdf_bytes = render_poster_pdf(
            studio_name=org.get("name") or "Your Studio",
            url=app_url,
            brand_hex=org.get("primary_brand_colour") or "#19CDFF",
            variant="book",
        )
        square_bytes = render_poster_png(
            studio_name=org.get("name") or "Your Studio",
            url=app_url,
            brand_hex=org.get("primary_brand_colour") or "#19CDFF",
            variant="book",
            fmt="square",
        )
        story_bytes = render_poster_png(
            studio_name=org.get("name") or "Your Studio",
            url=app_url,
            brand_hex=org.get("primary_brand_colour") or "#19CDFF",
            variant="book",
            fmt="story",
        )
    except Exception:
        logger.exception("[launch-kit] asset build failed")
        return {"skipped": "asset_build_failed"}

    attachments = [
        {"filename": f"{slug}-poster-a4.pdf", "content": base64.b64encode(pdf_bytes).decode("ascii")},
        {"filename": f"{slug}-instagram-square.png", "content": base64.b64encode(square_bytes).decode("ascii")},
        {"filename": f"{slug}-instagram-story.png", "content": base64.b64encode(story_bytes).decode("ascii")},
    ]

    sent: list[str] = []
    for u in users:
        ok = await send_email(
            u["email"],
            f"{org.get('name', 'Your Studio')} · Your launch kit is ready 🎉",
            html,
            attachments=attachments,
        )
        if ok:
            sent.append(u["email"])

    now = datetime.now(timezone.utc).isoformat()
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"launch_kit_sent_at": now, "launch_kit_recipients": sent}},
    )
    logger.info(f"[launch-kit] org={org_id} sent={len(sent)}")
    return {"sent": sent, "sent_at": now, "templates": templates,
            "links": {"app": app_url, "brag": brag_url, "share": share_url}}
