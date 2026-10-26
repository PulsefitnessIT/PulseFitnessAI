"""Customer sign-off — shared rules for every engineer fault / service report.

A job (or PPM service) can't be completed until the customer has signed
(signature + printed name, optional email if different to the site's main
contact) or the engineer has recorded why no signature was possible.
The signed report is then emailed to the signer, copying the site contact.
"""
from __future__ import annotations

import asyncio
import base64
import html as _html
import io
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from utils.database import db

logger = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_TASKS: set = set()


def spawn(coro) -> None:
    """Fire-and-forget that keeps a reference until the task finishes."""
    t = asyncio.create_task(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def resolve_site_contact(case: dict) -> dict:
    """Main contact for the job's site: case → site → organisation."""
    name = (case.get("customer_name") or "").strip()
    email = (case.get("customer_email") or "").strip()
    site_id = case.get("site_id")
    if site_id and not email:
        site = await db.sites.find_one({"id": site_id}, {"_id": 0}) or {}
        email = (site.get("site_manager_email") or site.get("contact_email") or site.get("primary_contact_email") or site.get("email") or "").strip()
        name = name or (site.get("site_manager_name") or site.get("contact_name") or "").strip()
    if not email:
        for oid in filter(None, (site_id, case.get("organization_id"))):
            org = await db.organizations.find_one({"id": oid}, {"_id": 0}) or {}
            email = (org.get("primary_contact_email") or org.get("contact_email") or org.get("billing_email") or "").strip()
            name = name or (org.get("primary_contact_name") or org.get("contact_name") or "").strip()
            if email:
                break
    return {"name": name, "email": email.lower()}


def build_signoff(data: dict, *, case_id: str | None, organization_id: str, reference: str | None,
                  user: dict, ppm_service_id: str | None = None) -> dict:
    """Validate a sign-off payload into an svc_signatures document."""
    data = data or {}
    base = {"id": str(uuid.uuid4()), "organization_id": organization_id, "case_id": case_id,
            "case_reference": reference, "ppm_service_id": ppm_service_id,
            "signed_at": _now(), "created_at": _now(), "captured_by_id": user.get("id"),
            "captured_by_name": user.get("full_name") or user.get("email")}
    if data.get("unavailable"):
        reason = (data.get("reason") or data.get("unavailable_reason") or "").strip()
        if not reason:
            raise HTTPException(400, "Give a reason the customer could not sign")
        return {**base, "signed_by_name": "", "signed_by_email": "", "image_data": "",
                "unavailable": True, "unavailable_reason": reason}
    name = (data.get("signed_by_name") or "").strip()
    image = data.get("image_data") or ""
    email = (data.get("signed_by_email") or "").strip().lower()
    if not name or not image:
        raise HTTPException(400, "Customer signature and printed name are required")
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address for the customer")
    return {**base, "signed_by_name": name, "signed_by_email": email,
            "signed_by_role": (data.get("signed_by_role") or "").strip(),
            "image_data": image, "unavailable": False, "summary": (data.get("summary") or "").strip()}


async def latest_signoff(*, case_id: str | None = None, ppm_service_id: str | None = None) -> dict | None:
    q = {"case_id": case_id} if case_id else {"ppm_service_id": ppm_service_id}
    return await db.svc_signatures.find_one(q, {"_id": 0}, sort=[("signed_at", -1)])


async def require_signoff(*, case_id: str | None = None, ppm_service_id: str | None = None) -> dict:
    sig = await latest_signoff(case_id=case_id, ppm_service_id=ppm_service_id)
    if not sig:
        raise HTTPException(400, "Customer sign-off is required — capture a signature or record why the customer couldn't sign")
    return sig


def recipients(sig: dict | None, contact: dict) -> tuple[str, list[str]]:
    """(to, cc) for the signed report: signer first, site contact copied."""
    contact_email = (contact or {}).get("email") or ""
    signer = (sig or {}).get("signed_by_email") or ""
    to = signer or contact_email
    cc = [contact_email] if contact_email and signer and contact_email != signer else []
    return to, cc


def signoff_text_lines(sig: dict | None) -> list[str]:
    if not sig:
        return ["No customer sign-off captured"]
    when = (sig.get("signed_at") or "")[:16].replace("T", " ")
    if sig.get("unavailable"):
        return [f"Customer unable to sign — {sig.get('unavailable_reason') or 'no reason given'}", f"Recorded {when}"]
    lines = [f"Signed by: {sig.get('signed_by_name')}" + (f" ({sig['signed_by_role']})" if sig.get("signed_by_role") else "")]
    if sig.get("signed_by_email"):
        lines.append(f"Email: {sig['signed_by_email']}")
    lines.append(f"Signed {when}")
    return lines


def signature_bytes(sig: dict | None) -> bytes | None:
    img = (sig or {}).get("image_data") or ""
    if not img.startswith("data:image") or "," not in img:
        return None
    try:
        return base64.b64decode(img.split(",", 1)[1])
    except Exception:
        return None


def draw_signoff_canvas(c, x: float, y: float, sig: dict | None) -> float:
    """Draw the sign-off block on a reportlab canvas; returns the new y."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "CUSTOMER SIGN-OFF")
    y -= 6 * mm
    raw = signature_bytes(sig)
    if raw:
        try:
            c.drawImage(ImageReader(io.BytesIO(raw)), x, y - 24 * mm, width=60 * mm, height=24 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setFont("Helvetica", 9.5)
    ty = y - 4 * mm
    for line in signoff_text_lines(sig):
        c.drawString(x + (66 * mm if raw else 0), ty, line[:90])
        ty -= 5 * mm
    return min(ty, y - 26 * mm if raw else ty) - 2 * mm


def signoff_flowables(sig: dict | None, styles: dict) -> list:
    """Platypus flowables for the sign-off block."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Spacer, Table
    body = styles.get("body") or styles.get("muted")
    text = Paragraph("<br/>".join(line.replace("&", "&amp;") for line in signoff_text_lines(sig)), body)
    raw = signature_bytes(sig)
    cells = [text]
    if raw:
        try:
            cells = [Image(io.BytesIO(raw), width=60 * mm, height=22 * mm, kind="proportional"), text]
        except Exception:
            pass
    return [Table([cells], colWidths=[65 * mm, 105 * mm] if len(cells) == 2 else [170 * mm]), Spacer(1, 3 * mm)]


async def email_signed_pdf(*, sig: dict | None, contact: dict, pdf: bytes, filename: str, subject: str,
                           intro: str, organization_id: str | None) -> str:
    """Send the signed report; returns the address it went to ('' if none)."""
    to, cc = recipients(sig, contact)
    if not to:
        return ""
    from utils.email import send_email
    who = _html.escape(((sig or {}).get("signed_by_name") or contact.get("name") or "there").split()[0])
    html = (f"<div style='font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px'>"
            f"<h2 style='color:#0f172a;font-size:18px;margin:0 0 12px'>Hi {who},</h2>"
            f"<p style='color:#1f2937;font-size:14px;line-height:1.6'>{intro} Your signed report is attached as a PDF.</p>"
            f"<p style='color:#64748B;font-size:13px;margin-top:24px'>Thanks,<br/><b>Pulse Fitness</b></p></div>")
    try:
        ok = await send_email(to=to, cc=cc or None, subject=subject, html=html, organization_id=organization_id,
                              attachments=[{"filename": filename, "content": base64.b64encode(pdf).decode("ascii")}],
                              category="service", kind="signed_service_report")
        return to if ok else ""
    except Exception:
        logger.exception("signed report email failed")
        return ""
