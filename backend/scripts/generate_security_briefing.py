"""Generate the Pulse Fitness security briefing as a printable PDF.

Run standalone:
    cd /app/backend && python -m scripts.generate_security_briefing

Output:
    /app/docs/SECURITY_BRIEFING_PULSE_FITNESS.pdf
"""
import os
from datetime import datetime
from fpdf import FPDF

MD_PATH = "/app/docs/SECURITY_BRIEFING_PULSE_FITNESS.md"
PDF_PATH = "/app/docs/SECURITY_BRIEFING_PULSE_FITNESS.pdf"


_ASCII_REPLACEMENTS = {
    "\u2014": " - ",   # em dash
    "\u2013": " - ",   # en dash
    "\u2018": "'",     # left single quote
    "\u2019": "'",     # right single quote
    "\u201c": '"',     # left double quote
    "\u201d": '"',     # right double quote
    "\u2022": "*",     # bullet (we never render it ourselves, just safety)
    "\u2026": "...",   # ellipsis
    "\u00a0": " ",     # non-breaking space
    "\u2713": "[ok]",  # check mark
    "\u00d7": "x",     # multiplication sign
}


def _ascii(text: str) -> str:
    """Latin-1-safe variant of a string, for Helvetica in fpdf2."""
    for src, dest in _ASCII_REPLACEMENTS.items():
        text = text.replace(src, dest)
    return text


# Typography (black on cream, print-friendly)
PRIMARY = (10, 10, 10)
MUTED = (110, 110, 110)
ACCENT = (0, 85, 255)
LIGHT_BG = (245, 246, 248)


class SecurityBriefingPDF(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 8, _ascii("Pulse Fitness - Platform Security Briefing"), align="L")
        self.set_x(self.w - self.r_margin - 40)
        self.cell(40, 8, datetime.now().strftime("%d %b %Y"), align="R")
        self.ln(10)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, _ascii(f"Page {self.page_no()}  -  Confidential - Prepared for the Director, Pulse Fitness"),
                 align="C")


def _write_title_block(pdf: SecurityBriefingPDF) -> None:
    pdf.set_text_color(*PRIMARY)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, "Platform Security Briefing", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "Prepared for the Director, Pulse Fitness", ln=True)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, datetime.now().strftime("%d %B %Y"), ln=True)
    pdf.ln(4)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(1.0)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(6)


def _write_section_heading(pdf: SecurityBriefingPDF, number: str, title: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*ACCENT)
    pdf.cell(12, 8, number)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 8, _ascii(title), ln=True)
    pdf.ln(1)


def _write_paragraph(pdf: SecurityBriefingPDF, text: str) -> None:
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*PRIMARY)
    pdf.multi_cell(0, 5.5, _ascii(text))
    pdf.ln(2)


def _write_bullet(pdf: SecurityBriefingPDF, text: str) -> None:
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*PRIMARY)
    # Indent the bullet by shifting left margin, then restore after.
    old_left = pdf.l_margin
    pdf.set_left_margin(old_left + 4)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.5, _ascii("-  " + text))
    pdf.set_left_margin(old_left)


def _write_callout(pdf: SecurityBriefingPDF, text: str) -> None:
    pdf.ln(2)
    pdf.set_fill_color(*LIGHT_BG)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*PRIMARY)
    pdf.multi_cell(0, 5.2, _ascii(text), fill=True, border=0)
    pdf.ln(2)


def _write_two_col_row(pdf: SecurityBriefingPDF, label: str, description: str) -> None:
    start_y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*PRIMARY)
    pdf.multi_cell(55, 5.0, _ascii(label), border=0)
    end_y_label = pdf.get_y()

    pdf.set_xy(pdf.l_margin + 55, start_y)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5.0, _ascii(description), border=0)
    end_y_desc = pdf.get_y()

    pdf.set_y(max(end_y_label, end_y_desc) + 1)


# ── Content blocks (kept small so the generator is readable) ────────

def _section_one_liner(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "1", "In one sentence")
    _write_callout(
        pdf,
        "Customer data lives in a private, encrypted database behind multi-layer "
        "authentication; the Sicon link uses credentials that never leave our server "
        "and travel only over encrypted channels."
    )


def _section_emergent(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "2", 'What "Emergent" actually does')
    _write_paragraph(
        pdf,
        "Emergent is our deployment platform — the place the application runs. "
        "Think of it as the landlord of the building our software lives in."
    )
    _write_bullet(pdf, "Every customer request reaches the application only over HTTPS (TLS 1.2+), the same encryption used by online banking.")
    _write_bullet(pdf, "The application runs in an isolated container — other Emergent customers on the same hardware cannot see our traffic, memory, or files.")
    _write_bullet(pdf, "Emergent provides the network perimeter, DDoS protection, and certificate infrastructure that secures every URL.")
    _write_callout(
        pdf,
        "Important: Emergent does not have access to customer data, passwords, or Sicon "
        "credentials. They host the container; we control what runs inside."
    )


def _section_access(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "3", "How customer access is controlled")
    rows = [
        ("HTTPS everywhere", "Every page load, API call, and file upload is encrypted in transit."),
        ("Password hashing (bcrypt)", "Passwords are never stored as readable text. Even our own engineers cannot see a customer's password."),
        ("JWT session tokens", "Each login produces a short-lived signed token. Stolen tokens expire automatically."),
        ("Rate-limited logins", "A brute-force attempt on any account is blocked after 5 failures."),
        ("Role separation", "Owner / Manager / Staff / Service Desk / Master Admin — each role can only see what it needs."),
        ("Per-organisation isolation", "Every database query is filtered by organisation ID at the code level. Customer A cannot see Customer B's data."),
        ("Audit log", "Every action Pulse Fitness internal staff take on a customer account is recorded — who, what, when. Cannot be edited or deleted."),
        ("GDPR right-to-erasure", "Archived organisations are permanently deleted after 365 days, with 7-day advance email notice."),
    ]
    for label, desc in rows:
        _write_two_col_row(pdf, label, desc)


def _section_sicon(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "4", "The Sicon Service link — specifically")
    _write_paragraph(
        pdf,
        "The integration with Sicon Service is the single biggest concern customers raise, "
        "so here is exactly what happens:"
    )
    _write_bullet(pdf, "Sicon credentials live on our server, in environment variables — never in the browser. A customer using the Pulse app never sees, and never can see, the Sicon password.")
    _write_bullet(pdf, "Every call to Sicon is HTTPS-only, with certificate validation. No data ever crosses the internet in plain text.")
    _write_bullet(pdf, "Basic Auth over TLS — the authentication method Sicon themselves recommend. The username and password are transmitted only inside the encrypted tunnel.")
    _write_bullet(pdf, "Scoped per-organisation — each Pulse customer's Sicon config is stored separately. A fault from Oxford reaches Sicon with Oxford's company ID only.")
    _write_bullet(pdf, "One-way push for new faults; we poll Sicon for updates every 5 minutes. We never expose any Sicon endpoint directly to the customer's browser.")
    _write_bullet(pdf, "Failure mode is safe — if the Sicon connection drops, faults queue locally and retry automatically. No data is lost.")
    _write_callout(
        pdf,
        "Plain-English summary: a customer reporting a treadmill fault will see "
        '"Sent to Sicon" — but the credentials that authenticated that call never '
        "left our server and never touched their device."
    )


def _section_payments(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "5", "Payment and financial data")
    _write_paragraph(
        pdf,
        "We use Stripe for every card transaction. Stripe holds PCI-DSS Level 1 "
        "certification — the strictest standard in the industry. No card number, "
        "CVV, or full billing detail is ever stored on the Pulse platform. "
        "We only see a Stripe customer reference."
    )


def _section_worst_case(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "6", "Worst-case analysis")
    _write_paragraph(
        pdf,
        "Even if an attacker bypassed every perimeter layer and reached our application:"
    )
    _write_bullet(pdf, "Passwords are useless to them — bcrypt-hashed, practically un-reversible.")
    _write_bullet(pdf, "Card details do not exist to steal — they live only at Stripe.")
    _write_bullet(pdf, "Sicon credentials are encrypted at rest in environment configuration.")
    _write_bullet(pdf, "Customer data is partitioned — compromising one account cannot by itself expose another.")
    _write_bullet(pdf, "Audit log means every Service Desk action is permanently recorded. Insider misuse is traceable to an individual within hours.")


def _section_roadmap(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "7", "What we commit to do next")
    _write_paragraph(pdf, "Already on the roadmap; putting them in writing makes the commitment explicit:")
    _write_bullet(pdf, "Independent penetration test before customer go-live with real equipment data.")
    _write_bullet(pdf, "Two-factor authentication (2FA) for all Pulse Fitness internal staff and customer owners who opt in.")
    _write_bullet(pdf, "SSO / SAML integration for enterprise customers federating their identity provider.")
    _write_bullet(pdf, "Quarterly security reviews with a written summary to the Director.")


def _section_contact(pdf: SecurityBriefingPDF) -> None:
    _write_section_heading(pdf, "8", "Single point of contact")
    _write_paragraph(
        pdf,
        "Any question from the Director's team can come directly to our engineering "
        "lead. We will respond inside one working day and share what we can without "
        "revealing anything that could itself weaken the platform."
    )


def _write_footer_signature(pdf: SecurityBriefingPDF) -> None:
    pdf.ln(6)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0, 4.5,
        _ascii(
            f"Document version 1.0 - prepared {datetime.now().strftime('%d %B %Y')} for the "
            "Director of Pulse Fitness. For internal use only."
        )
    )


def build_pdf(output_path: str = PDF_PATH) -> str:
    pdf = SecurityBriefingPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(left=18, top=16, right=18)
    pdf.add_page()

    _write_title_block(pdf)
    _section_one_liner(pdf)
    _section_emergent(pdf)
    _section_access(pdf)
    _section_sicon(pdf)
    _section_payments(pdf)
    _section_worst_case(pdf)
    _section_roadmap(pdf)
    _section_contact(pdf)
    _write_footer_signature(pdf)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path


if __name__ == "__main__":
    path = build_pdf()
    print(f"Wrote: {path}  ({os.path.getsize(path)} bytes)")
