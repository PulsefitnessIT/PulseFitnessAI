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


## Jun 8, 2026 — Phase 2: Manufacturer manual auto-link + per-type custom check sheets

Two P0 production feature requests delivered (both backend + frontend, tested).

**Task 1 — Equipment "Manufacturer manual" auto-link (read-only, all roles).**
- `EquipmentDetailContent` (`frontend/src/pages/LiteDashboard/LiteDialogs.js`, Documents section ~line 349): when an equipment item has a matched Master-Admin spec sheet (`spec_sheet_id`), the Documents list now surfaces it as a **"Manufacturer manual"** card with a blue **Read-only** badge, a View action (testid `equip-manual-view`, switches to the Spec Sheet tab) and a Download link (testid `equip-manual-download` → public `GET /api/spec-sheets/pdf/{id}`). Card testid `equip-manufacturer-manual`. Visible/downloadable by ALL roles; only Master Admin uploads spec sheets. Matching logic unchanged (auto-match on equipment create/import). Verified visually on Apex demo (temp-attached spec sheet, then reverted).

**Task 2 — Custom check sheets assignable to an equipment type (replaces default).**
- Backend (`backend/routes/check_sheets.py`): `POST /api/maintenance/templates` and `/check-sheets/custom-template` now persist `equipment_type` (stripped; empty string = general). GET endpoints return it. Pytest 4/4 (`tests/test_iter_phase2_check_template_equipment_type.py`).
- Frontend (`frontend/src/pages/CheckSheetsTab.js`): create dialog has an **"Applies to equipment type"** dropdown (testid `template-equipment-type-select`, options = org equipment types + "Any — general template"). `handleStartSheet` loads the assigned custom template's items **instead of** the built-in default for that type. Group cards show a blue assigned badge (`custom-assigned-<type>`); custom-template cards show their type badge (`custom-template-type-<idx>`).

Preview-only — user must REDEPLOY to gymaxisai.com for production.
