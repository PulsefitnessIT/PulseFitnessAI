"""Member-facing transactional emails for Pulse Fitness Memberships.

Three flows — booking confirmation, waitlist → booked promotion, and
operator-initiated class cancellation. All are fire-and-forget from the
route handlers (we never block the response on an email send).
"""
from __future__ import annotations

import logging
from datetime import datetime

from utils.email import send_email

logger = logging.getLogger(__name__)

_BRAND_BG = "#05070A"
_BRAND_ACCENT = "#19CDFF"


def _format_when(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%A %-d %B · %H:%M")
    except Exception:
        return iso_str


def _shell(eyebrow: str, title: str, body_html: str, footer: str = "Pulse Fitness Memberships") -> str:
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:{_BRAND_BG};color:#fff;border-radius:16px;overflow:hidden;">
  <div style="padding:28px 32px;border-bottom:1px solid rgba(25,205,255,0.25);">
    <div style="color:{_BRAND_ACCENT};font-size:10px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:8px;">{eyebrow}</div>
    <h1 style="color:#fff;font-size:22px;margin:0;line-height:1.3;font-weight:800;letter-spacing:-0.01em;">{title}</h1>
  </div>
  <div style="padding:24px 32px;background:#0A0C10;color:#e5e7eb;font-size:14px;line-height:1.6;">
    {body_html}
  </div>
  <div style="background:{_BRAND_BG};padding:14px 32px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
    <p style="color:#6b7280;font-size:11px;margin:0;">{footer}</p>
  </div>
</div>"""


def _class_card(occ: dict) -> str:
    name = occ.get("name") or "Your class"
    when = _format_when(occ.get("starts_at"))
    room = occ.get("room_name") or ""
    instructor = occ.get("instructor_name") or ""
    chips = " · ".join([x for x in (instructor, room) if x])
    colour = occ.get("colour") or _BRAND_ACCENT
    return f"""<div style="border-left:3px solid {colour};background:rgba(255,255,255,0.03);padding:14px 16px;border-radius:8px;margin:18px 0;">
      <div style="font-weight:800;font-size:15px;color:#fff;">{name}</div>
      <div style="color:#9ca3af;font-size:13px;margin-top:4px;">{when}</div>
      {f'<div style="color:#9ca3af;font-size:12px;margin-top:2px;">{chips}</div>' if chips else ''}
    </div>"""


async def send_booking_confirmation(member: dict, occurrence: dict) -> bool:
    """Emitted when a member successfully books (not waitlist)."""
    first = member.get("first_name") or "there"
    body = f"""<p>Hi {first},</p>
    <p>You're booked in. Here's what's on:</p>
    {_class_card(occurrence)}
    <p style="color:#9ca3af;font-size:13px;">Show your rotating QR pass on the <strong style="color:#fff;">Pass</strong> tab at reception. Need to cancel? Tap the class in your app — earlier is kinder to the waitlist.</p>"""
    html = _shell("Booking confirmed", f"See you at {occurrence.get('name') or 'class'}", body)
    return await send_email(
        member["email"], f"Booked · {occurrence.get('name') or 'class'}", html,
        organization_id=member.get("organization_id"),
    )


async def send_waitlist_promotion(member: dict, occurrence: dict) -> bool:
    """Emitted when a waitlisted member is promoted to booked."""
    first = member.get("first_name") or "there"
    body = f"""<p>Hi {first},</p>
    <p>A spot opened up — you've been promoted from the waitlist into the class. Your credit has been held.</p>
    {_class_card(occurrence)}
    <p style="color:#9ca3af;font-size:13px;">Can't make it any more? Please cancel in-app so the next member on the waitlist gets a chance.</p>"""
    html = _shell("You're in", f"Waitlist cleared · {occurrence.get('name') or 'class'}", body)
    return await send_email(
        member["email"], f"You're in · {occurrence.get('name') or 'class'}", html,
        organization_id=member.get("organization_id"),
    )


async def send_class_cancelled(member: dict, occurrence: dict, reason: str | None = None) -> bool:
    """Emitted when the operator cancels an occurrence — per booked member."""
    first = member.get("first_name") or "there"
    reason_html = f'<p style="color:#9ca3af;font-size:13px;">Reason: {reason}</p>' if reason else ""
    body = f"""<p>Hi {first},</p>
    <p>This class has been cancelled by the studio — sorry for the disruption. Your credit (if any) has been refunded to your plan.</p>
    {_class_card(occurrence)}
    {reason_html}
    <p style="color:#9ca3af;font-size:13px;">Browse the timetable to rebook something else this week.</p>"""
    html = _shell("Class cancelled", f"{occurrence.get('name') or 'Class'} · {_format_when(occurrence.get('starts_at'))}", body)
    return await send_email(member["email"], f"Cancelled · {occurrence.get('name') or 'class'}", html)



async def send_dropin_invite(member: dict, occurrence: dict, app_url: str | None = None) -> bool:
    """Emitted when the studio has free spots in a soon-to-start class
    and broadcasts a drop-in invite to opted-in members."""
    first = member.get("first_name") or "there"
    cta = ""
    if app_url:
        cta = f'<p style="margin-top:18px;"><a href="{app_url}" style="display:inline-block;background:{_BRAND_ACCENT};color:#05070A;padding:12px 22px;border-radius:8px;font-weight:800;text-decoration:none;font-size:13px;letter-spacing:0.02em;">Grab your spot →</a></p>'
    body = f"""<p>Hi {first},</p>
    <p>A spot just opened up — first come, first served. We thought of you.</p>
    {_class_card(occurrence)}
    {cta}
    <p style="color:#9ca3af;font-size:13px;">You're getting this because you opted in to last-minute drop-in invites. Adjust this any time on your <strong style="color:#fff;">Profile</strong> tab.</p>"""
    html = _shell("Drop-in invite", f"Free spot · {occurrence.get('name') or 'class'}", body)
    return await send_email(member["email"], f"Free spot · {occurrence.get('name') or 'class'}", html)

async def send_missed_class_followup(member: dict, occurrence: dict) -> bool:
    """Phase 6 CRM: emitted after a no-show booking is marked. Empathic,
    not punitive — focused on rebooking."""
    first = member.get("first_name") or "there"
    body = f"""<p>Hi {first},</p>
    <p>We saved a spot for you and you didn't make it — no worries, life happens. Want to rebook this week?</p>
    {_class_card(occurrence)}
    <p style="color:#9ca3af;font-size:13px;">Tap any class in the timetable to book it. Tip: turn on <strong style="color:#fff;">drop-in invites</strong> in your profile so we can grab you a last-minute spot when one opens up.</p>"""
    html = _shell("We missed you", f"Rebook {occurrence.get('name') or 'a class'} this week", body)
    return await send_email(
        member["email"], f"Missed you · {occurrence.get('name') or 'class'}", html,
        organization_id=member.get("organization_id"),
    )


async def send_low_attendance_checkin(member: dict, attended_count: int, days: int = 30) -> bool:
    """Phase 6 CRM: member's attendance has dropped — gentle check-in."""
    first = member.get("first_name") or "there"
    body = f"""<p>Hi {first},</p>
    <p>Quick check-in — you've made it to <strong style="color:#fff;">{attended_count}</strong> session{'s' if attended_count != 1 else ''} in the last {days} days. We want to make sure the timetable is working for you.</p>
    <p style="color:#9ca3af;font-size:13px;">Reply to this email and let us know what would help — different class times, a fresh class type, or a 1-2-1 chat with a coach. We're here to make it stick.</p>"""
    html = _shell("How's it going?", "A quick check-in from the team", body)
    return await send_email(
        member["email"], f"How's training going, {first}?", html,
        organization_id=member.get("organization_id"),
    )


async def send_high_engagement_celebration(member: dict, attended_count: int, days: int = 30) -> bool:
    """Phase 6 CRM: high-attendance member — celebrate + ask for referral."""
    first = member.get("first_name") or "there"
    # Iter 220p1 — referral-credit symbol follows the gym's market currency.
    from utils.database import db
    from utils.localization import org_localization
    _org = await db.organizations.find_one(
        {"id": member.get("organization_id")},
        {"_id": 0, "country_code": 1, "currency": 1, "timezone": 1},
    )
    _sym = org_localization(_org)["currency_symbol"]
    body = f"""<p>Hi {first},</p>
    <p>You've smashed <strong style="color:#fff;">{attended_count} sessions</strong> in the last {days} days. That's the top tier of our community — well done.</p>
    <p>Know someone who'd love training with you? Share your referral code from the <strong style="color:#fff;">Profile</strong> tab — you both get {_sym}5 credit when they join.</p>
    <p style="color:#9ca3af;font-size:13px;">Keep showing up. We see you.</p>"""
    html = _shell("You're flying", f"{attended_count} sessions · {days} days", body)
    return await send_email(
        member["email"], f"Top of the leaderboard, {first} 💪", html,
        organization_id=member.get("organization_id"),
    )
