# GymAxis · MOD Estate Operations Platform — Briefing Pack

Production-grade leave-behind deck for the UK Ministry of Defence.
A4 landscape (297 × 210 mm), 16 slides, brand-aligned with the
GymAxis public site (`#0055FF` → `#19CDFF`, Montserrat / Nunito).

## Files

| Path | Purpose |
|------|---------|
| `GymAxis_MOD_Briefing.pdf` | **The deliverable.** Send this to MOD. |
| `index.html`               | Master deck (open in any modern browser). |
| `render_pdf.py`            | Re-renders the PDF from `index.html` via Playwright. |
| `screenshots/`             | 12 real screenshots from the live MOD portal. |

## Deck contents (16 slides)

1. Cover — *Mission-ready gyms, across every base.*
2. The problem — paper check-sheets, WhatsApp faults, Excel registers.
3. The promise — one platform, three Services, three tiers (HQ / branch / site).
4. The MOD Service Portal — `/MODService` hardened sign-in.
5. Operational readiness — HQ rollup, gym health score, SLA.
6. Single source of truth — asset register, QR codes, warranty.
7. Reactive faults — gym-floor in 10 seconds, OFFICIAL classification guard.
8. Daily checks — JSP 375 / RIDDOR / PUWER aligned check-sheets.
9. Operational triptych — documents · staffing · suppliers.
10. Reports — KPIs, CAPEX, risk, weekly digest.
11. Security — 9-tile grid covering identity, separation, classification, crypto, audit, hosting, quality, pen-test.
12. Compliance — JSP 375 / 440, HSE/RIDDOR, PUWER, NCSC, GDPR, ISO 27001, Cyber Essentials Plus.
13. Rollout — 90 days · pilot · branch-wide · estate-wide.
14. Commercial value — −40% MTTR, +3 yrs asset life, 100% audit coverage.
15. Why GymAxis — quote, 6 differentiators.
16. Next steps — working session · security review · 3-site pilot.

## Regenerating the PDF

```bash
cd /app/marketing/mod-presentation
python3 render_pdf.py
```

## Refreshing screenshots

Screenshots are captured live from the running MOD portal as the
`army-catterick` site account. To refresh, log into `/MODService`
in the preview environment and screenshot the same tabs into
`screenshots/0?_*.jpeg`.

## Classification

The deck is marked **OFFICIAL — SENSITIVE · COMMERCIAL IN CONFIDENCE**
on every slide footer. It contains no actual MOD data — only Catterick
Garrison *demo* records seeded for product development.
