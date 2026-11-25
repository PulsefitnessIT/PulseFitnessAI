"""Wording for the 2/4/6-week customer follow-up emails. Drafts are editable; nothing is sent
to customers until an owner approves the current wording (and MOD_QUOTE_NOTIFY_LIVE is on)."""
import html
import os

from utils.database import db

SETTINGS_ID = "followup_emails"
PLACEHOLDERS = ("{contact_name}", "{site_name}", "{quote_list}", "{valid_until}", "{sender_name}", "{portal_line}")

DEFAULTS = {
    "1": {"subject": "Your Pulse Fitness maintenance quotation — {site_name}",
          "body": "Dear {contact_name},\n\nThank you for the opportunity to quote for the gym equipment maintenance at "
                  "{site_name}. We are just checking that the quotation reached you safely — a copy is attached.\n\n"
                  "{quote_list}\n\nThe prices are fixed until {valid_until}. If you have any questions about the "
                  "equipment list or the service types, simply reply to this email.\n\n{portal_line}"
                  "To go ahead, please reply with your purchase order or authorisation.\n\nKind regards,\n{sender_name}\nPulse Fitness"},
    "2": {"subject": "Following up: maintenance quotation for {site_name}",
          "body": "Dear {contact_name},\n\nI am following up on the maintenance quotation we sent for {site_name} "
                  "(attached again for convenience).\n\n{quote_list}\n\nIf anything needs changing — equipment, "
                  "quantities or the choice between Type A and Type B cover — let me know and I will issue a revised "
                  "quotation.\n\n{portal_line}Kind regards,\n{sender_name}\nPulse Fitness"},
    "3": {"subject": "Final reminder: maintenance quotation for {site_name}",
          "body": "Dear {contact_name},\n\nThis is a final reminder about the maintenance quotation for {site_name}, "
                  "attached once more.\n\n{quote_list}\n\nThe quotation remains valid until {valid_until}. If the "
                  "work is no longer needed, a quick reply saying so would be appreciated and we will close the "
                  "quotation.\n\n{portal_line}Kind regards,\n{sender_name}\nPulse Fitness"},
}


async def get_settings() -> dict:
    doc = await db.mod_quote_settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    return {"templates": doc.get("templates") or DEFAULTS, "approved": bool(doc.get("approved")),
            "approved_by_name": doc.get("approved_by_name"), "approved_at": doc.get("approved_at"),
            "updated_by_name": doc.get("updated_by_name"), "updated_at": doc.get("updated_at"),
            "is_default": not doc.get("templates")}


def render(tmpl: dict, g: dict, qs: list[dict], sender_name: str) -> tuple[str, str]:
    """(subject, html) — every value is escaped; the body keeps the staff-approved line breaks."""
    portal = os.environ.get("MOD_PORTAL_URL", "").rstrip("/")
    valid = min((q.get("valid_until") or "" for q in qs), default="") or "the date shown on the quotation"
    values = {
        "{contact_name}": g["customer"].get("contact_name") or "Customer",
        "{site_name}": g["customer"]["name"],
        "{valid_until}": valid,
        "{sender_name}": sender_name or "Pulse Fitness MOD Sales",
        "{portal_line}": (f"If your unit uses MODService you can also review and authorise it at {portal}.\n\n" if portal else ""),
    }
    subject = tmpl["subject"]
    for k, v in values.items():
        subject = subject.replace(k, v)
    rows = "".join(f"<li>{html.escape(q.get('sage_quote_number') or q['quote_number'])} — £{q['total']:,.2f} inc. VAT</li>"
                   for q in qs)
    body = html.escape(tmpl["body"])
    for k, v in values.items():
        body = body.replace(html.escape(k), html.escape(v))
    paras = "".join(f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in body.split("\n\n") if p.strip())
    return subject, paras.replace("<p>{quote_list}</p>", f"<ul>{rows}</ul>").replace("{quote_list}", f"<ul>{rows}</ul>")
