# Known Bugs & Recurring Pitfalls

> Read this **first** when picking up work. Re-introducing one of these
> wastes a session. Update on every fix / new finding.

_Last refreshed: Iter 220m · May 26, 2026_

---

## ✅ Fixed since h232 (iter 220i → 220m)

- **P0 broken customer-email image** (iter 220i) — every customer-facing email (service reports, lifecycle, partner emails) was rendering with a broken GymAxis mark in Gmail/Outlook. Root cause: the external `customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/gymaxis-mark-tight.png` URL started returning **403 Forbidden** in late 2026. Fixed by self-hosting at `/brand/gymaxis-mark-tight.png` resolved against `EMAIL_PUBLIC_BASE_URL` / `FRONTEND_URL`. Override via `EMAIL_GYMAXIS_LOGO_URL` env var.

- **P0 data-loss: engineer drafts wiping on tab switch** (iter 220c) — Per-machine work-report draft autosaving via `svc_engineer_drafts` + tab-switch warnings.

- **Partner Sign-up washed-out theme** (iter 220i) — Replaced pastel `slate-50 → purple-50 → indigo-100` with rich dark `slate-950 → indigo-950 → purple-900` gradient. Loading + error states rebalanced for legibility.

- **Asset dropdown not closing on Enter** (iter 220i) — `MachineAssetPicker` in `WorkVisitMachinesCard.js` now auto-picks single match on Enter, closes silently when no match so free-text is accepted.

- **Engineers had no path back to Partner Dashboard from inside the Engineer App** (iter 220i+ ad-hoc fix) — Added Partner Engineer row at the top of `EngineerAccountSettings` drawer with live status subtitle.

- **Stranded customer risk on mid-job subscription cancellation** (iter 220k) — When Stripe subscription flips to `canceled`/`unpaid`/`incomplete_expired`, any in-flight `svc_cases` assigned to that engineer auto-unassign + flip to `new` with `needs_reassignment=true` + `partner_access_lost` audit event + dispatch-admin email digest.

- **KYC bypass on first job claim** (iter 220k) — New `require_engineer_compliance_to_claim` dependency blocks `/queue/{id}/claim` + `/jobs/self-create` until partner has DBS OR RTW on file (non-expired) AND `compliance_paused` is False. Master admins / internal employees / customer-grant engineers exempt.

- **Stale job grants reusable forever** (iter 220l) — Grants now get `expires_at = now + expires_in_days` (default 30, capped 365). `_has_access_via_grant` filters expired entries out.

- **VAT charged by sole-trader engineers below £85k threshold** (iter 220l) — New `vat_registered` flag on `partner_engineers` (default True for backward compat). When false, every invoice/quote PDF + email auto-applies `vat_rate=0` and shows "Not chargeable" in place of the VAT row.

- **Pre-existing iter 220i test fixtures**: `test_iter_220i_full.py` was mishandling the `/svc/engineer/jobs?when=...` `{by_day: {...}}` response shape and 0-indexing into a dict (`KeyError: 0`). Fixed in iter 220k.

---

## ✅ Fixed since h212 (iter 216h225 → h232)

- **`exhaustive-deps` doom loop** (h226-deps-walk) — 82 sites
  manually reviewed. One real bug found: `TrustDashboard.refreshTick`
  was calling a stale `load` closure after token rotation. Fixed by
  including `load` in deps. The other 81 sites got explicit
  `-- intentional:` rationales documenting why their suppression is
  safe.

- **Module-tailored trial onboarding leak** (h227) — every trial saw
  every module's First Wins. Fixed by adding `primary_module` to
  `UserRegister`, narrowing `/activation/me` + `/account/onboarding`
  to the operator's intent.

- **Mobile UX bugs** (h228 / h229 / h230 / h231):
  - CRM "+" QuickCreate menu off-screen on phones → anchor flipped on
    `max-sm`.
  - Welcome header clipped behind trial banner → fixed with 62px
    inline spacer below the fixed banner.
  - NotificationsBell panel off-screen → switched to viewport-anchored
    fixed positioning on `max-sm`.
  - 9 MasterAdmin tables clipping silently → wrapped in
    `overflow-x-auto`.
  - EngineerDiary week-grid squashed to ~55px cells → wrapped in
    `overflow-x-auto` with `min-w-[700px]`.
  - EquipmentInfoTab missing Add Equipment button + action row
    overflowing → button added, row switched to flex-wrap.
  - 3 global FABs (UnifiedAssistant + FeedbackWidget + NPSWidget) now
    opted into `[data-fab-rail]` so they stack deterministically
    (76px / 152px / 228px from bottom) instead of overlapping.

- **GitHub Actions Quality Gate failures** (h232):
  - `bandit --exit-zero-on-skipped` flag never existed → removed.
  - Secret-detection grep matched test fixtures → added
    `--exclude-dir=tests`.
  - Pytest couldn't import `tests.shared_loop` under bare `pytest` →
    added `pythonpath = ["."]` to `pyproject.toml`.
  - Tool-version drift in CI → pinned `ruff==0.15.10`, `bandit==1.9.4`,
    `xenon==0.9.3`.
  - Mongo missing from Quality Gate's `python-quality` job →
    added `services: mongodb` sidecar.

---

## 🐛 Active issues (P0 / P1 still open)

### P0 — None currently open. (h208 site_id fix shipped.)

### P2 — UX polish (h212 audit findings — ALL RESOLVED in h214)
- ~~NPS popup appears on every page~~ → **FIXED h214**: `localStorage`-persisted dismissal + 7-day client-side "last shown" cooldown.
- ~~PWA "Install App" prompt too frequent~~ → **FIXED h214**: once-per-session via `sessionStorage` + 7-day cross-session throttle + delay raised 3s → 30s (engagement signal).
- ~~CSP violations for emergent-main.js / PostHog / Cloudflare~~ → **FIXED h214**: added `https://assets.emergent.sh`, `https://*.posthog.com`, `https://*.i.posthog.com`, `https://static.cloudflareinsights.com` to `script-src`.

### P1 — Class Builder reported "crash" (Iter 216h209 — COULD NOT REPRODUCE)
- **Reporter**: Craig (live preview).
- **Testing result (h209 audit)**: ClassEditorModal opens cleanly on `e1.agent@gymaxisai.com` tenant. All form fields render correctly: Class Name, Category, Colour picker, Instructor dropdown, Room/Studio, Days of Week, Start Time, Duration, Capacity, Booking Opens, Cancel Cutoff, Credits to Book, Max Waitlist, Waitlist enabled. No JavaScript errors observed in Playwright with capture_logs=true.
- **Possible causes**: (1) Tenant-specific data issue, (2) Browser-specific, (3) Network timeout perceived as crash.
- **Repro steps needed**: Craig to provide exact tenant/org, browser + version, console screenshot at time of crash.
- **Status**: Downgraded to P2 pending reproduction evidence.
- **Defensive measures shipped in h209**:
  - `ModalErrorBoundary` (`/app/frontend/src/components/shared/ModalErrorBoundary.jsx`) wraps Class Builder, Plan Editor, Add Member. Any future render crash → readable fallback ("Couldn't render this dialog — Retry / Close") + auto-POST to `/api/client-errors` with full stack + component_stack + URL + user-agent.
  - Backend `POST /api/client-errors` stores to `client_errors` collection. Grep this when a stakeholder reports a future "crash" without details.

### P1 — Discoverability of class_pack plans (FIXED in h209)
- Before h209, "credit packs" were a hidden `kind` toggle. Now a dedicated **Credit Packs** subtab is in Plans.
- **Prevention**: any plan `kind` that has its own UX (course, class_pack, bundle) should get its own discoverable subtab.

---

## ⚠️ Mocked / gated integrations (NOT real prod-ready)

| Integration | State | What works | What doesn't |
|-------------|-------|------------|--------------|
| Twilio SMS | ❌ MOCKED | Send-attempt logs to console | Real delivery, delivery receipts |
| Sage 200 | ❌ MOCKED | Schema + endpoints stubbed | Live posting on payment / lead-convert |
| Sicon (CAPEX) | ⚠️ READY — awaiting creds | Full integration code path + admin field-mapping UI in `/master-admin/integrations` shipped. Unit tests green. See `/app/memory/SICON_INTEGRATION_SPEC.md` + `/app/memory/SICON_INTEGRATION_PROOF.md`. | Live API calls — needs Pulse IT to provide credentials. |
| Microsoft Graph (Outlook) | ❌ MOCKED | Code paths designed | Live push — needs `MS_CLIENT_ID` + `MS_CLIENT_SECRET`. |
| DocuSign | ❌ MOCKED | PDF generation works | Live signature flow — awaiting credentials. |
| Stripe Connect | ⚠️ GATED | Test mode works with sk_test_emergent | Production checkout requires Express onboarding per tenant |
| Resend Email | ⚠️ GATED | SDK wired | No API key in env → emails log to console only |
| PostHog analytics | ⚠️ CSP-blocked | Client embeds it | CSP `script-src` rejects the third-party CDN — sees console errors (cosmetic) |

---

## 🔁 Recurring footguns (avoid re-introducing)

### F-1 — Radix `<Select>` inside Radix `<Dialog>` auto-closes
- **Why**: Radix portals Select content to `document.body`; clicking an option fires `onPointerDownOutside` on the Dialog.
- **Fix pattern (h205)**: Use native `<input list="datalist">` or native `<select>`. `DialogContent` already has defensive `onPointerDownOutside` handler in `components/ui/dialog.jsx`.

### F-2 — New documents missing `site_id` are invisible to filtered dashboards
- **Why**: Multi-site orgs filter list endpoints by `?site_id=<active>`. Any doc inserted without `site_id` won't show.
- **Fix pattern (h208)**: On insert, look up the parent entity (equipment, member, etc.) and inherit its `site_id`.
- **Endpoints already hardened**: `/api/issues`, `/api/issues/batch`, `/api/gym-floor/faults`.
- **Still to audit**: New endpoints in /api/svc/*, /api/marketing/*, /api/crm/*.

### F-3 — MongoDB `_id` leak in API responses
- **Pattern**: `db.collection.find({}, {"_id": 0})` projection MUST be used. `find_one_and_update`, `insert_one` mutate the input dict to add `_id` → `doc.pop("_id", None)` before returning.

### F-4 — Datetime aware vs naive
- Use `datetime.now(timezone.utc)`. Never `datetime.utcnow()` (deprecated).
- Stored as ISO string for portability.

### F-5 — Master admin organization_id assumption
- Master admins have an `organization_id` of `9fa701ef-…` (the GymAxis Master Admin org). They are NOT cross-org by default; queries scoped to org will be near-empty. Use the `?as=operator` preview path or impersonation to test operator flows.

### F-6 — Bcrypt $ characters in .env
- A `$` in a bcrypt hash inside `.env` gets shell-expanded. Always quote the value or use single-quoted heredoc when writing.

### F-7 — `bg-white dark:bg-zinc-900/<opacity>` is parser-broken
- Tailwind reads this as `bg-white` (solid white, no opacity) + `dark:bg-zinc-900/X` (faint dark). Always use `bg-white/<opacity>` for a translucent overlay (h206 sweep fixed 121 instances).

### F-8 — Edit-drawer vs Create-modal validation drift
- Drift between POST and PATCH endpoints causes data to enter the DB in inconsistent states. **Rule**: every PATCH should mirror its POST's validation (h207 fixed Members + Instructors).

### F-9 — External `customer-assets.emergentagent.com` URLs go 403 over time
- The Emergent customer-assets bucket revokes access to artifacts intermittently. Any image hard-coded against `https://customer-assets.emergentagent.com/...` in a customer-facing email or PDF will silently break in Gmail / Outlook.
- **Rule (iter 220i)**: serve all brand assets from `/app/frontend/public/brand/` resolved against `EMAIL_PUBLIC_BASE_URL` or `FRONTEND_URL`. Use `customer-assets.emergentagent.com` only for one-off internal artifacts that won't be referenced from production emails.

### F-10 — `_id: 0` projection alone isn't enough for nested partner.subscription docs
- `_public()` in `routes/partners.py` strips the top-level `_id` but nested subdocs returned from aggregations can still carry one. When in doubt, materialise the response into a typed dict and explicitly include only the keys you want.

---

## ✅ Recently fixed (last 10 iters — don't break)

| Iter | Fix |
|------|-----|
| h218 | Supplier picker sweep — `single` mode added to `SupplierMultiPicker`. Free-text inputs on Parts Catalogue (Add part dialog) and Invoice Import Wizard (Step 2 supplier override) swapped to the picker. Per-org custom brands now flow across surfaces. |
| h217 | Supplier dropdown standardisation — `SupplierMultiPicker` (chips + typeahead + "+ Add new") replaces free-text on both engineer apply wizards. Public catalogue endpoint serves 25 curated UK suppliers without auth. |
| h216 | Craig's 7-bug screenshot batch — engineer apply (mandatory mobile, radius min 5km, mobile-friendly stepper, gradient button), NPS gated to 5+ logins, activation timeline module-aware (no "add equipment" prompt for Memberships-only orgs), login counter wired |
| h215 | Platform Issues (24h) Master Admin home tile + auto-refresh + deep-link rows |
| h214 | UX polish — NPS localStorage + 7d cooldown, PWA prompt session-throttled + 30s delay, CSP whitelisted emergent/posthog/cloudflare hosts (closes h212 P2s) |
| h213 | Regression suite wired into pre-deploy.sh + GitHub Quality Gate + `make regression-full` |
| h212 | Service Desk + CRM + MOD audit — no P0s, 0 P1s, 3 P2s now fixed in h214. Cross-portal isolation + MFA enrolment verified. |
| h211 | Regression suite extended Service Desk (20) + MOD (19) + CRM (20). Total now 84 isolated tests, ~2 min runtime, pre-deployment gate. |
| h210 | Login-failure reason classification + Master Admin diagnostics (`/master-admin?section=login-events` shows colour-coded reason badges; `?section=client-errors` shows React render crashes from ModalErrorBoundary) |
| h209 | Credit Packs subtab discoverability + full audit passed |
| h208 | Issues inherit site_id from equipment |
| h207 | Edit drawer GDPR + email/phone parity (Members + Instructors) |
| h206 | Dark-mode sweep (bg-white/x fractional opacity, 31 files) |
| h205 | Radix Select/Dialog portal conflict (FaultDialogs datalist) |
| h204 | Front-desk Desk Sales Report |
| h203 | Sell Pack At Desk (cash flow) |
| h202 | Buy Credits Stripe checkout (member portal) |
| h201 | Instructor email/phone required on create |
| h200 | Add member GDPR consent + email/phone required |

---

## Update protocol

- Found a bug? Add a P0/P1 entry above with reporter + repro steps.
- Fixed a bug? Move it to "Recently fixed" with the iter tag.
- Hit a footgun more than once? Add it to "Recurring footguns".
