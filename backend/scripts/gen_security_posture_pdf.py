"""Generate a one-page branded 'Security Posture' PDF for the pen-test
handover + director demonstration. Standalone (no server needed):

    cd /app/backend && python scripts/gen_security_posture_pdf.py [output.pdf]

Output defaults to /app/security_posture_<YYYY-MM>.pdf.
"""
import sys
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

PULSE = HexColor("#19CDFF")
DARK = HexColor("#0A0C10")
SLATE = HexColor("#475569")
GREEN = HexColor("#16a34a")
AMBER = HexColor("#d97706")
LINE = HexColor("#e2e8f0")

W, H = A4


def _wrap(c, text, x, y, width, leading, font="Helvetica", size=9, color=SLATE):
    c.setFont(font, size)
    c.setFillColor(color)
    words, line = text.split(" "), ""
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, font, size) > width:
            c.drawString(x, y, line)
            y -= leading
            line = w
        else:
            line = test
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def build(path: str):
    c = canvas.Canvas(path, pagesize=A4)
    m = 16 * mm
    y = H - m

    # Header band
    c.setFillColor(DARK)
    c.rect(0, H - 34 * mm, W, 34 * mm, fill=1, stroke=0)
    c.setFillColor(PULSE)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(m, H - 18 * mm, "PulseFitness.ai — Security Posture")
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica", 10)
    c.drawString(m, H - 25 * mm, "Pen-test readiness & control summary — prepared for external tester + board review")
    c.setFont("Helvetica", 8)
    c.drawString(m, H - 30 * mm, f"Generated {datetime.now().strftime('%d %b %Y')}  ·  Checklist v1.3  ·  Confidential")

    y = H - 44 * mm

    # Headline status
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(m, y, "STATUS: READY FOR EXTERNAL PENETRATION TEST")
    y -= 6 * mm
    y = _wrap(c, "All 33 baseline findings (F-01 to F-33) closed and regression-tested. A 2026-06 "
                 "focused audit of the newer surfaces (Inventory & Distribution, Dealer/Logistics/Staff "
                 "portals, Customer Deliveries, public pricing) added SEC-001 to SEC-003 — all resolved or "
                 "documented. No open High/Critical remain.", m, y, W - 2 * m, 4.6 * mm, size=9)
    y -= 3 * mm

    def section(title):
        nonlocal y
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(m, y, title)
        y -= 2.5 * mm
        c.setStrokeColor(PULSE)
        c.setLineWidth(1.4)
        c.line(m, y, m + 28 * mm, y)
        y -= 5 * mm

    def row(label, value, color=SLATE):
        nonlocal y
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(m, y, label)
        c.setFillColor(color)
        c.setFont("Helvetica", 9)
        c.drawString(m + 52 * mm, y, value)
        y -= 5 * mm

    # New-surface findings
    section("2026-06 focused audit — new surfaces")
    row("SEC-001  HIGH", "FIXED & VERIFIED — portal tokens scoped out of operator APIs", GREEN)
    row("SEC-002  MEDIUM", "BY DESIGN — logistics on-site sign-off is a gated write path", AMBER)
    row("SEC-003  LOW", "FIXED — idempotency key on Stripe checkout create", GREEN)
    y -= 2 * mm

    # Controls always-on
    section("Core controls (OWASP Top 10 + LLM Top 10)")
    for lbl, val in [
        ("Access control", "Org-scoped queries; RBAC; 404 on cross-tenant; portal-token isolation"),
        ("Authentication", "bcrypt (cost 12), JWT HS256 + revocation, account lockout, login rate-limit"),
        ("Injection / XSS", "Parameterised Mongo; bleach sanitisation; server-rendered PDFs"),
        ("SSRF", "Always-on guard (ssrf_guard.py); internal-range denylist"),
        ("CORS", "Env allow-list (CORS_ORIGINS); wildcard rejected in production"),
        ("AI / LLM", "Prompt-injection guard, output sanitisation, per-tenant token budgets"),
        ("Payments", "Stripe webhook signature + idempotency; server-side price resolution"),
        ("Multi-tenant", "organization_id on every collection; per-site 403 isolation"),
    ]:
        row(lbl, val)
    y -= 2 * mm

    # Pre-kickoff env flags
    section("Set in the test/prod environment before kickoff")
    y = _wrap(c, "ENFORCE_MASTER_ADMIN_MFA=true  ·  ENFORCE_EMAIL_RECIPIENT_VALIDATION=true  ·  "
                 "STRICT_AV_MODE=true  ·  EXPOSE_API_DOCS=false  ·  STRIPE_WEBHOOK_SECRET=<set>  ·  "
                 "JWT_SECRET=<64-hex>.  Helper: scripts/toggle_pentest_flags.sh.",
              m, y, W - 2 * m, 4.6 * mm, size=9, color=DARK)
    y -= 2 * mm

    section("Accepted limitations (signed off)")
    y = _wrap(c, "Shared preview/prod secrets (platform tier — mitigated by org segregation); Twilio SMS "
                 "mocked; credential-blocked integrations (Sicon/DocuSign/Outlook) return not_configured. "
                 "These are expected and should not be logged as findings.",
              m, y, W - 2 * m, 4.6 * mm, size=9)

    # Footer
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(m, 16 * mm, W - m, 16 * mm)
    c.setFillColor(SLATE)
    c.setFont("Helvetica", 7.5)
    c.drawString(m, 12 * mm, "Full detail: SECURITY_AUDIT/PEN_TEST_READINESS_CHECKLIST.md (v1.3), RISK_REGISTER.md, RESIDUAL_RISK_SUMMARY.md")
    c.drawRightString(W - m, 12 * mm, "PulseFitness.ai — Confidential")
    c.showPage()
    c.save()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else f"/app/security_posture_{datetime.now().strftime('%Y-%m')}.pdf"
    build(out)
    print("Wrote", out)
