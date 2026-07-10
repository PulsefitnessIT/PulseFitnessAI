# Competitive Gap Analysis — Simpro & Orbit4 (Jul 10, 2026)

Source: crawled `helpguide.simprogroup.com` + `orbit4.org/resources`, enriched with web research.

## The two competitors
- **Simpro** — market-leading field-service management for *trades* (electrical, HVAC, fire, security, plumbing). Deep PPM/job-costing/contract engine + a large paid add-on ecosystem + AI layer ("Lightning", "JustAsk", "Delight", "Fast Cash").
- **Orbit4** — our *closest* competitor: commercial **fitness-equipment** asset-lifecycle platform. Sells the full journey: asset management → service ticketing → **residual valuation (WeBuyGymEquipment)** → **sustainable disposal/resale** → **vendor tendering marketplace**. Umbrella of FitnessCompared, FitnessFinance, WeServiceGymEquipment, WeBuyGymEquipment.

## Where we already MATCH or BEAT them (no action needed)
We are already broader than both across ops+CRM+memberships+marketing. Confirmed in codebase:
- PPM engine (`ppm_engine.py`, `svc/pm.py`, `svc/ppm_reminders.py`) — Simpro Maintenance Planner parity.
- Live engineer ETA/location + public tracking (`svc/engineer_location.py`, `engineer_eta_update.py`, `public_tracking.py`) — SimTrac/live-tech-tracking parity.
- QR asset scanning (`qr_codes.py`, `svc/engineer_qr.py`) — Orbit4 QR parity.
- AR chasing / dunning / collections (`invoice_dunning.py`, `collections_dashboard.py`, `revenue_autopilot.py`) — Simpro "Fast Cash" parity.
- Compliance checklists / safety / risk assessments (`check_sheets.py`, `svc/safety.py`, `risk_assessments.py`, `mod_compliance.py`) — audit-ready parity.
- Vendor/service-provider tendering + billing (`service_provider*.py`, CRM Tenders) — Orbit4 tendering-marketplace parity.
- AI assistant + AI triage (`assistant.py`, `ai_diagnosis.py`) — "JustAsk"/"Lightning" direction.
- **We ingest Orbit4 tickets** (`svc/orbit4.py`) — we interoperate WITH the competitor (strong judo move).
- Multi-module RBAC, memberships, marketing suite, tenant-branded PDFs, territory map (now with role filter + offices + geocoding).

## TRUE GAPS — whitespace to pull ahead (nothing found in codebase)
### P0 — Orbit4's flagship, and our biggest strategic hole
1. **Asset Financial Intelligence / Residual Value & TCO.** No residual-value, depreciation, book-value, resale/trade-in, or total-cost-of-ownership tracking. Orbit4's *entire* pitch is "know your equipment's true value + the sweet-spot to upgrade". We have the richest asset register in the market but don't monetise the financial layer. Build: per-asset purchase cost + depreciation curve → live book/residual value → TCO (capex + cumulative service/parts spend from our own case data, which Orbit4 *can't* see as deeply as we can) → "upgrade sweet-spot" alert → optional resale/trade-in lead.
2. **Cap-Spend budgets.** Per-site/estate capital budget with spend-to-date vs cap, overspend guardrails. Ties directly to #1.

### P1 — 2026 table-stakes / conversion drivers
3. **ESG / Sustainability reporting.** Carbon + e-waste + circular-economy report from asset lifespan & disposal data. Increasingly *mandatory* for the enterprise/estate operators both competitors target. We already hold the service history — turn it into an auditable Environmental Benefits Report.
4. **Contract inflation indexing (CPI/RPI auto-uplift).** Simpro auto-adjusts recurring contract rates by index + per-SLA charge rates. We have contracts + recurring; add scheduled index-linked uplift.
5. **Full branded Customer Self-Service Portal.** We have public case tracking + supplier/instructor portals, but not a single customer portal to book jobs, request quotes, view invoices, and see their site assets + full service history + certificates (Simpro parity, and a retention/upsell surface).

### P2 — polish / smaller wins
6. **NPS / satisfaction programme.** We have engineer ratings + feedback; add a proper NPS capture (post-case + member app) and a trend dashboard (Orbit4 markets member NPS in-app).
7. **AI "ask your data" analytics.** Natural-language querying of ops/CRM data ("which sites cost the most to service last quarter?") — Simpro "JustAsk". We have the assistant; wire it to reporting.
8. **In-app guided onboarding + public roadmap/changelog** (Simpro "Walk-Me-Through" + Product Portal) — reduces churn, signals momentum.

## Founder's recommendation
Lead with **#1 Asset Financial Intelligence + #2 Cap-Spend**, then **#3 ESG report**. This is where Orbit4 makes its money and where we have an unfair advantage: we already own the deepest service/parts-cost history, so our TCO and ESG numbers are more accurate than a valuation-only competitor's. This flips us from "ops tool" to "the system that tells operators when/what to replace and proves their sustainability" — a CFO/estate-director-level story neither competitor fully owns end-to-end.
