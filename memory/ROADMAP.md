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

---

## P1 — Outstanding integrations (blocked on credentials)

- **Outlook Calendar — Phase 1** (push GymAxis meetings to Outlook with ICS fallback). Waiting on user-provided `MS_CLIENT_ID` / `MS_CLIENT_SECRET`.
- **Sicon Service** — replacement CAPEX / parts / labour live sync. Code path + admin field-mapping UI shipped; waiting on Pulse IT live credentials. See `/app/memory/SICON_INTEGRATION_SPEC.md`.
- **CRM Quote DocuSign** — e-signature on the CPQ PDFs. Waiting on credentials.

## P1 — Ready to build on green light

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

- **Right-to-erasure workflow** for personnel records.
- **Tenders module deepening** — log + track tenders deeply linked to companies / opportunities. Audit lives in `/app/memory/CRM_TENDERS_AUDIT.md`.
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
