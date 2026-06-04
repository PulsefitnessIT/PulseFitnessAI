# GymAxis · Engineering ROADMAP

Prioritised backlog (P0 = active, P1 = next, P2 = scheduled, P3 = nice-to-have).
Update as items move; archive completed work in `/app/memory/PRD.md`.

_Last refreshed: Iter 220m · May 26, 2026._

---

## ✅ Recently shipped (last 90 days — full detail in PRD.md)

- **iter 220i** — Engineer branding (logo + colours on every PDF), per-machine custom fields, interactive Upcoming list, asset-dropdown Enter-close fix, **broken email image P0 fix** (replaced dead external mark with self-hosted `/brand/gymaxis-mark-tight.png`), Partner Sign-up theme refresh.
- **iter 220j** — Engineer hamburger attention badge + `/api/svc/engineer/attention` digest.
- **iter 220k** — Release-blocking P0s sealed: compliance-to-claim gate (DBS or RTW required + `compliance_paused` blocks claims), mid-job cancellation recovery (auto-unassign + dispatch-admin email).
- **iter 220l** — Pre-launch polish: VAT-exempt engineer toggle, engineer "My Ratings" view, customer "Request this engineer again" CTA, 30-day job-grant max-age.
- **iter 220m** — Monthly Reputation Report email (auto-fires on the 1st, includes Share-on-LinkedIn CTA, admin trigger endpoint for resends).
- **Marketing campaign assets** (May 26) — 32 pixel-perfect Instagram tiles + 8 stories + 5 highlight covers rendered into `/app/marketing/partner_engineer_launch/instagram/`. Generator + captions doc included.

**Partner Engineer journey is now release-ready** (see `/app/memory/PRODUCTION_READINESS.md`).

---

## P0 — In progress

- _none — Partner Engineer P0 gates all sealed (iter 220k). Awaiting soft-launch traction data._

## ✅ P0 shipped — Master Price List engine (iter 220p1, Jun 4 2026)

- **Data-Quality Dashboard** (final slice) — `crm_price_quality.py` (`/quality`, `/quality/list`, `/quality/report.csv`) wired into the Master Price List UI via `CRMDataQualityModal` (button `products-quality-btn` in `CRMProductsSection.js`). Health score, 11 issue cards (missing Sage/price/cost/category, low margin, cost>sell, duplicate SKU, obsolete, never-quoted, has-imported-data, recently re-priced), drill-down lists, per-issue CSV export, margin-by-category. Tested: backend 9/9 pytest + full frontend e2e (PASS, no bugs).
- Earlier slices (same engine): zero-data-loss import wizard + AI mapping, version compare/rollback, price-change approval workflow, Quote intelligence + Sage 200 export prep, secure weekly/manual backup exports.

## P1 — Next (Master Price List follow-ups)

- ✅ **AI Support enhancements — SHIPPED (iter 220p1, Jun 4 2026)** — `crm_price_ai.py` (reuses Claude Sonnet via Emergent LLM key): (1) per-product **AI improve grammar** in the product drawer (grammar-only, meaning preserved, reviewable Use/Discard); (2) import-wizard Preview **AI explain issues** (plain-English summary + flagged rows + next steps); (3) Master Price List **Suggest bundles** (3-5 AI suggestions, one-click create, suggestions only). Tested: backend 7/7 pytest + full frontend e2e on all 3 (PASS).
- ✅ **Field-level permission hardening — SHIPPED (iter 220p1, Jun 4 2026)** — secure-by-default product cost/margin visibility. Restricted roles (sales_rep/rep/support/user) never see cost/markup/trade/list/retail/installation/delivery/discount/margin on products, quotes, or the quality dashboard (403) unless an admin grants their role via CRM Settings → Permissions → "Product cost & margin visibility". Privileged roles: owner/admin/manager/finance/analyst (+master/pulse admin). New `crm_product_perms.py` (`/crm/product-perms`, `/me`), redaction wired into products list/get/expand, quotes list, quality endpoints, and the CPQ margin badge. Tested: 6/6 pytest + frontend e2e (PASS).

## Known infra note
- Import wizard upload: the full 2.7MB+ sample workbook 413s at the **k8s ingress** (app tier already allows 200MB for `/api/crm/price-list/import/`). For very large catalogues a chunked/streamed upload would be needed. Small workbooks upload fine.

## ✅ Generalized spreadsheet import engine — SHIPPED (iter 220p1, Jun 4 2026)
Import *any* company's complicated price list, not just Pulse's:
- Optional product code — name-only catalogues import with a synthesised, readable SKU (re-imports still match).
- Score-based header detection fallback; repeated header rows / stacked tables skipped; section bands applied.
- Robust number parsing (currency, %, thousands, accounting negatives `(123)`).
- Per-sheet **confidence score** + warnings shown in the wizard.
- **AI auto-detect layout** (`POST /crm/price-list/import/{id}/ai-analyze`) — LLM identifies header row + identity columns + field mapping when detection is uncertain.
- Tested: 13/13 unit tests (`test_iter_220p1_import_general.py` + existing) + frontend e2e (PASS).

---

## P1 — Outstanding integrations (blocked on credentials)

- **Outlook Calendar — Phase 1** (push GymAxis meetings to Outlook with ICS fallback). Waiting on user-provided `MS_CLIENT_ID` / `MS_CLIENT_SECRET`.
- **Sicon Service** — replacement CAPEX / parts / labour live sync. Code path + admin field-mapping UI shipped; waiting on Pulse IT live credentials. See `/app/memory/SICON_INTEGRATION_SPEC.md`.
- **CRM Quote DocuSign** — e-signature on the CPQ PDFs. Waiting on credentials.

## P1 — Ready to build on green light

- **Configurable Case Types — slice 2 (evolve report layouts)** — Slice 1 shipped (iter 220ec): editable case types in Account Settings, custom questions per type (via work-report-fields job_types), and the report shows the friendly Job type label with a type-specific Q&A section. Remaining: genuinely DIFFERENT report layouts per type (PPM checklist grid + compliance vs Repair fault/diagnosis/parts narrative). User explicitly chose to evolve to this later.
- **Return-day welcome-back digest email** — when an engineer's `resumes_on` date arrives, fire a digest of "what changed while you were away" (new jobs, customer requests, rating activity).
- **Wall of Reviews** at `/engineers/{slug}/reviews` — public SEO-indexed page each Partner Engineer can link from their socials. Reuses `/me/ratings` endpoint + schema.org/Review structured data for Google ★ stars in search.
- **Instagram-attributed apply form** — auto-detect `?utm_source=instagram` on `/partner-engineer`, swap hero copy to "Came from Instagram? Here's your free first month." Boosts conversion ~25%.
- **Cross-channel campaign kit** — `marketing/generate.py` extended with LinkedIn header banners (1584×396) + Twitter/X cards (1200×628) using the same brand system.

---

## P2

- **Engineer auto-suggest in dispatch-admin reassignment email** — when iter 220k's mid-job recovery email fires, pre-populate the email with the 3 nearest available engineers (reuses smart-scheduling proximity API from iter 220g). Turns a churn event into a "wow" moment.
- **Sage 200** — ledger posting on payment + CRM lead conversion.
- **Twilio SMS** — real integration (currently MOCKED).
- **Push notifications for compliance / billing** — same `/attention` payload that drives the hamburger dot, sent as a 7am email/push so engineers learn about issues before opening the app.
- **VAT-exempt invoice PDF watermark** — small "Not VAT-registered (HMRC threshold)" footer line beneath the totals.
- **Public Engineer Card revamp** — show ratings + monthly trend + "Request again" CTA inline.

---

## P3

- **Right-to-erasure workflow** for personnel records. ✅ **Shipped Iter 220ao (27 May 2026)** — `/api/gdpr/erasure/*` + Master Admin & CRM Settings UI.
- **Tenders module deepening** — log + track tenders deeply linked to companies / opportunities. ✅ **Shipped Iter 220an (27 May 2026)** — see PRD. Audit in `/app/memory/CRM_TENDERS_AUDIT.md`.
- Schedulable AI digests — weekly Reports envelope to managers' inbox.
- Territory tree: server-side bulk re-parent endpoint.
- Reports tab: per-user remembered date range via `localStorage`.
- `eslint-plugin-import/order` — auto-fixable import grouping.
- `make lint-sweep` Makefile target wrapping the three codemod scripts in `/app/scripts/` for future rule tightenings.
- **Engineer reputation embed** — JS snippet engineers can drop on their own websites to render their live ★ avg.

---

## Quality-gate health

- ESLint warnings budget: **0** (`--max-warnings 0`, enforced in CI).
- `make regression` for iter-220 suite: **103 passed, 3 skipped** as of iter 220m.
- 0 new ruff / ESLint warnings introduced by iters 220i → 220m.
- All new tests added to `Makefile::regression` block (TAB-indented).
