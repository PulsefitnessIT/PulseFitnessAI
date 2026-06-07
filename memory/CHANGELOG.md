# Changelog

## Jun 7, 2026 — Split sales decks + real app screenshots

- Finalised two audience-split sales presentations with "GymAxisAI" branding + white-pill logo:
  - `GymAxisAI-Operators-Presentation.pdf` (14pp) and `GymAxisAI-Suppliers-Presentation.pdf` (12pp), served from `/app/frontend/public/downloads/` and linked in the public marketing footer (`MarketingShell.js`, testids `gx-footer-sales-deck-operators` / `-suppliers`). Old combined deck deleted.
- Replaced wireframe mockups with **real, populated, Pulse-free screenshots** captured from a new neutral demo tenant **"Apex Fitness Group"** (`apex-demo-org`, account_type `full` → GymAxis branding):
  - Operators deck: CRM sales pipeline, Operations equipment register, Memberships analytics.
  - Suppliers deck: engineer job dashboard (Service Desk slide), asset fault/service log.
  - Marketing slide (operators) + Van-stock & Engineer-phone slides (suppliers) kept their wireframes — no convincing demo data without disproportionate seeding.

### Follow-up (same day) — last 2 wireframe slides now real + marketing routing bugfix
- Seeded Apex **Marketing** (4 audiences + 5 email campaigns w/ metrics, A/B) and engineer **Van stock** (9 parts, low/out badges, £4,112 value) via `backend/seed_apex_marketing_vanstock.py`.
- **Bug fixed (platform-wide):** `routes/marketing_downloads.py` had a greedy `GET /marketing/{slug}` catch-all that shadowed `GET /api/marketing/campaigns|audiences|templates`, 404-ing the Marketing **Campaigns/Audiences/Templates** tabs for *all* orgs (incl. master admin). Replaced with explicit per-slug routes (public PDF URLs unchanged: `mod-briefing.pdf`, `mod.pdf`, `sicon-access.pdf`). Regression test: `tests/test_marketing_downloads_no_shadow.py` (2/2).
- Operators deck Marketing slide + Suppliers deck Van-stock slide now use real screenshots. **All 7 mock slides across both decks are now real app screenshots.** Only the Engineer-phone illustration (dark mobile mockup) remains a designed graphic by intent.
- New artifacts: `backend/seed_apex_demo.py`, `backend/seed_apex_crm.py` (idempotent), `sales/capture_*.py`, `sales/embed_shots.py`, `sales/render_pdf.py` (now renders both decks). Demo login + re-seed steps recorded in `test_credentials.md`.
