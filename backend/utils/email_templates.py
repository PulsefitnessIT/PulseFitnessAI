"""Shared, email-client-safe HTML building blocks for supplier / customer
transactional emails (fault reports, communication, scheduling, welcome,
reassignment).

Design system: /app/design_guidelines.json — table-based layout, inline
styles only, no flexbox/grid, bulletproof (Outlook-safe) buttons, ghost
tables for the 600px container, and a header that shows the customer's
imported logo when available (with a clean org-name fallback).

Everything here is pure string building — no DB / IO — so it's trivially
reusable across routes.
"""
from __future__ import annotations

import html as _html
from typing import Optional

FONT_STACK = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,"
    "sans-serif,'Apple Color Emoji','Segoe UI Emoji'"
)

WRAPPER_BG = "#F4F5F7"
CARD_BG = "#FFFFFF"
BORDER = "#E4E4E7"
TEXT_PRIMARY = "#18181B"
TEXT_SECONDARY = "#3F3F46"
TEXT_MUTED = "#71717A"
DEFAULT_BRAND = "#0055FF"

# Severity / status → email-safe badge palette (bg, text, border).
_BADGE_PALETTE = {
    "safety_critical": ("#FEE2E2", "#991B1B", "#FCA5A5"),
    "critical": ("#FEE2E2", "#991B1B", "#FCA5A5"),
    "out_of_order": ("#FFEDD5", "#9A3412", "#FDBA74"),
    "operational_fault": ("#FEF9C3", "#854D0E", "#FDE047"),
    "fault": ("#FEF9C3", "#854D0E", "#FDE047"),
    "limited_use": ("#FEF9C3", "#854D0E", "#FDE047"),
    "medium": ("#FEF9C3", "#854D0E", "#FDE047"),
    "operational_minor": ("#DBEAFE", "#1E40AF", "#93C5FD"),
    "minor": ("#DBEAFE", "#1E40AF", "#93C5FD"),
    "low": ("#DBEAFE", "#1E40AF", "#93C5FD"),
    "warranty": ("#DCFCE7", "#166534", "#86EFAC"),
    "neutral": ("#F4F5F7", "#3F3F46", "#E4E4E7"),
}


def esc(value: Optional[str]) -> str:
    """HTML-escape a value for safe interpolation into an email body."""
    return _html.escape(str(value), quote=True) if value is not None else ""


def _brand(brand_color: Optional[str]) -> str:
    color = (brand_color or "").strip()
    return color if color.startswith("#") and len(color) in (4, 7) else DEFAULT_BRAND


def badge(label: str, kind: str = "neutral") -> str:
    """Return an inline severity/status/warranty chip."""
    bg, fg, bd = _BADGE_PALETTE.get((kind or "neutral").lower(), _BADGE_PALETTE["neutral"])
    return (
        f'<span style="display:inline-block;padding:4px 10px;border-radius:12px;'
        f'font-family:{FONT_STACK};font-size:12px;font-weight:bold;line-height:1;'
        f'background:{bg};color:{fg};border:1px solid {bd};">{esc(label)}</span>'
    )


def bulletproof_button(url: str, label: str, brand_color: Optional[str] = None,
                       testid: str = "email-cta") -> str:
    """Outlook-safe CTA button. Uses VML (roundrect) for the Word rendering
    engine in desktop Outlook, and a padded anchor everywhere else."""
    color = _brand(brand_color)
    safe_url = esc(url)
    safe_label = esc(label)
    return (
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
        'style="margin:24px 0 8px;"><tr><td align="center">'
        '<!--[if mso]>'
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
        f'xmlns:w="urn:schemas-microsoft-com:office:word" '
        f'href="{safe_url}" style="height:48px;v-text-anchor:middle;width:240px;" '
        f'arcsize="16%" strokecolor="{color}" fillcolor="{color}">'
        f'<w:anchorlock/>'
        f'<center style="color:#FFFFFF;font-family:sans-serif;font-size:16px;font-weight:bold;">{safe_label}</center>'
        '</v:roundrect>'
        '<![endif]-->'
        '<!--[if !mso]><!-- -->'
        f'<a href="{safe_url}" target="_blank" data-testid="{testid}" '
        f'style="font-family:{FONT_STACK};font-size:16px;font-weight:bold;'
        f'color:#FFFFFF;text-decoration:none;display:inline-block;padding:14px 28px;'
        f'background:{color};border:1px solid {color};border-radius:8px;">{safe_label}</a>'
        '<!--<![endif]-->'
        '</td></tr></table>'
        # Plain-text fallback link (some corporate Outlook configs strip buttons).
        f'<p style="font-family:{FONT_STACK};font-size:12px;color:{TEXT_MUTED};'
        f'margin:4px 0 0;text-align:center;">Button not working? Open: '
        f'<a href="{safe_url}" target="_blank" style="color:{color};">{safe_url}</a></p>'
    )


def info_card(inner_html: str, *, bg: str = "#FAFAFA", border: str = BORDER,
              accent: Optional[str] = None) -> str:
    """A bordered content card (used for fault summaries / feature blocks)."""
    border_left = f"border-left:4px solid {accent};" if accent else ""
    return (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
        f'width="100%" style="background:{bg};border:1px solid {border};{border_left}'
        f'border-radius:8px;margin:0 0 16px;"><tr><td style="padding:16px 18px;">'
        f'{inner_html}</td></tr></table>'
    )


def paragraph(text_html: str, *, color: str = TEXT_SECONDARY, size: str = "16px",
              margin: str = "0 0 16px") -> str:
    return (
        f'<p style="font-family:{FONT_STACK};font-size:{size};line-height:24px;'
        f'color:{color};margin:{margin};">{text_html}</p>'
    )


def _header(brand_color: str, logo_url: Optional[str], org_name: str,
            eyebrow: Optional[str], title: str) -> str:
    org_name = esc(org_name) or "Pulse Fitness"
    if logo_url:
        brand_block = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
            'style="background:#FFFFFF;border:1px solid #E4E4E7;border-radius:8px;">'
            '<tr><td style="padding:8px 12px;">'
            f'<img src="{esc(logo_url)}" alt="{org_name}" height="40" '
            'style="display:block;height:40px;max-height:40px;width:auto;max-width:180px;'
            'border:0;outline:none;text-decoration:none;"></td></tr></table>'
        )
    else:
        brand_block = (
            f'<p style="font-family:{FONT_STACK};font-size:18px;font-weight:bold;'
            f'color:{TEXT_PRIMARY};margin:0;">{org_name}</p>'
        )
    eyebrow_html = (
        f'<p style="font-family:{FONT_STACK};font-size:12px;font-weight:bold;'
        f'letter-spacing:0.06em;text-transform:uppercase;color:{brand_color};'
        f'margin:20px 0 4px;">{esc(eyebrow)}</p>'
        if eyebrow else ""
    )
    return (
        f'<tr><td style="height:4px;background:{brand_color};font-size:0;line-height:0;">&nbsp;</td></tr>'
        '<tr><td style="padding:28px 32px 20px;background:#FFFFFF;'
        f'border-bottom:1px solid {BORDER};">'
        f'{brand_block}'
        f'{eyebrow_html}'
        f'<h1 style="font-family:{FONT_STACK};font-size:22px;font-weight:bold;'
        f'line-height:30px;color:{TEXT_PRIMARY};margin:8px 0 0;">{esc(title)}</h1>'
        '</td></tr>'
    )


def _footer(platform_footer: str, note: Optional[str]) -> str:
    note_html = (
        f'<p style="font-family:{FONT_STACK};font-size:12px;line-height:18px;'
        f'color:#B91C1C;margin:6px 0 0;">{esc(note)}</p>'
        if note else ""
    )
    return (
        f'<tr><td style="padding:24px 32px;background:{WRAPPER_BG};'
        f'border-top:1px solid {BORDER};">'
        f'<p style="font-family:{FONT_STACK};font-size:12px;line-height:18px;'
        f'color:{TEXT_MUTED};margin:0;">{esc(platform_footer)}</p>'
        f'{note_html}'
        '</td></tr>'
    )


def email_shell(*, title: str, body_html: str, brand_color: Optional[str] = None,
                logo_url: Optional[str] = None, org_name: str = "",
                eyebrow: Optional[str] = None,
                platform_footer: str = "Sent via Pulse Fitness",
                footer_note: Optional[str] = None,
                preheader: Optional[str] = None) -> str:
    """Compose a full, email-client-safe HTML document from a body fragment.

    `body_html` is dropped into the white content card between the branded
    header (with logo) and the footer.
    """
    color = _brand(brand_color)
    pre = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        f'{esc(preheader)}</div>' if preheader else ""
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:{WRAPPER_BG};">
{pre}
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background:{WRAPPER_BG};">
<tr><td align="center" style="padding:40px 20px;">
<!--[if mso]><table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600"><tr><td><![endif]-->
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background:{CARD_BG};border:1px solid {BORDER};border-radius:12px;overflow:hidden;">
{_header(color, logo_url, org_name, eyebrow, title)}
<tr><td style="padding:32px;background:{CARD_BG};">
{body_html}
</td></tr>
{_footer(platform_footer, footer_note)}
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body></html>"""


__all__ = [
    "email_shell", "bulletproof_button", "badge", "info_card",
    "paragraph", "esc", "FONT_STACK", "TEXT_PRIMARY", "TEXT_SECONDARY",
    "TEXT_MUTED", "BORDER", "DEFAULT_BRAND",
]
