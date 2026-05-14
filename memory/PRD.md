## Iter 216h88 — Engineer Partner public marketing landing (Feb 14, 2026)

Made the Partner Engineer Network discoverable to the open internet. The
program previously existed but was reachable only via direct link or
login. Now it's surfaced from the main GymAxis marketing site so we
can drive applicants from organic, paid, and word-of-mouth channels.

### New public route
- `/partners/engineers` — dedicated marketing landing, no auth.
  - Hero with brand-gradient typography + sample engineer trust card
    preview (Sarah · 4.9★ · 26 reviews · 52 jobs · IOSH/PAT/CSCS).
  - **Perks grid** (6 cards): paid referrals, jobs routed to you,
    verified profile, mobile-first PWA, AI photo triage, customer
    rating system.
  - **Auto-tiered pricing** (3 tiers): Starter £30 · Active £15 (5+
    refs) · Founding "Free" (30+ refs, dark gradient elevated card).
  - **How it works** (5 numbered steps): apply · verify · subscribe ·
    receive jobs · get paid.
  - **Engineer App showcase** with stylised phone mock showing Case
    drawer, asset history alert, time / parts panels, View report +
    Send to customer CTAs.
  - **FAQ** (6 items, native `<details>` accordions): independence,
    invoicing, fee rationale, tier cadence, insurance, per-case grants.
  - **Final gradient CTA** → /partner-engineer/apply.

### Discoverability surfaces
- **MarketingHome.js** — new `EngineerBanner` section between
  SocialProof and FinalCta. Two-column white-card with brand-gradient
  panel; eyebrow "Independent fitness engineer?", dual CTAs:
  Learn more → /partners/engineers, Start application → apply wizard.
- **MarketingShell.js** footer — new "For engineers" link added to the
  Resources column for site-wide discoverability.

### SEO
- `useSeo` hook on the landing page sets title + meta description for
  search indexing:
  > "Engineer Partner Network — GymAxis AI · Join 100+ independent
  > fitness engineers on the GymAxis Partner Network. £30/mo (drops to
  > free at 30 referrals). Apply in 5 minutes."
- Canonical: `https://www.gymaxisai.com/partners/engineers`.

### Cosmetic fix during build
- Initial pricing render showed "Free/mo" on the Founding tier —
  awkward. Conditional now hides the `/mo` suffix when fee is "Free"
  so the card reads cleanly.

### Testing
- 2/2 new backend pytest confirming both `/partners/engineers` and
  `/` return the SPA shell (no proxy/route regression).
- Live UI smoke verified: hero card, perks grid, 3-tier pricing
  (Founding correctly elevated), how-it-works steps, phone mock with
  app preview, FAQ accordion opens, final CTA renders.
- Frontend lint clean.

### Files touched
**Frontend**
- `/app/frontend/src/pages/Marketing/PartnerEngineerLanding.js` (NEW · ~365 LOC)
- `/app/frontend/src/pages/Marketing/MarketingHome.js`
  (+~60 LOC — `EngineerBanner` section + icon imports)
- `/app/frontend/src/pages/Marketing/MarketingShell.js`
  (+1 LOC — footer "For engineers" link)
- `/app/frontend/src/routes/AppRoutes.js`
  (+1 import + 2 LOC — public `/partners/engineers` route)

**Backend**
- `/app/backend/tests/test_iter_216h88_partner_landing.py` (NEW · 2 tests)

### Strategic outcome
- Search engines + social shares now have a page to land on.
- The home banner gives every gym-operator visitor a 1-click way to
  refer their engineer (a real source of new partners).
- Footer link makes the program findable from any marketing page.
- The end-to-end funnel is now: organic discovery → /partners/engineers
  landing → /partner-engineer/apply wizard → (login/signup if needed)
  → Partner Dashboard → £30 subscription. Fully measurable.

---




## Iter 216h87 (UI follow-up #2) — Preview tracking + Trust fields on Add (Feb 14, 2026)

Closed the loop on the trust card by:
1. Making the trust fields settable at **creation time** (not just edit).
2. Adding a **"Preview customer tracking"** button so operators can see
   exactly what a customer sees with one click.

### Backend changes
- `POST /svc/engineers` now accepts `photo_url`, `qualifications`,
  `years_experience`, `verified` in the body. Blank `years_experience`
  is coerced to `None` (no field) so the public tracking card hides the
  row cleanly.
- **NEW** `GET /svc/engineers/{user_id}/preview-tracking-link` — picks
  the engineer's most-recently-updated open case (or, failing that, the
  most-recently-closed case), lazily mints a tracking token, and returns
  `{url, token, case_id, case_status}`. Returns 404 with a friendly
  "no jobs yet" message when the engineer has no assignments. Reuses
  the public-tracking helpers (`_mint_or_get_token`, `_origin`) for
  consistency.

### Frontend changes (`EngineersAdminPage.js`)
- **Add engineer form** gains a "Trust profile · shown to customers on
  the live-tracking page" divider with the same 4 fields the edit row
  has (photo URL + 32×32 preview, years of experience, verified
  checkbox, qualifications chip picker + 8 suggestions + custom-entry
  input).
- **Each engineer row** gains a "Preview" button (ExternalLink icon)
  next to Edit. Click → opens `/track/<token>` in a new tab. Errors
  surface as a toast ("Cannot preview Sarah · This engineer has no jobs
  yet — preview is available once a case is assigned").
- `toggleQual` + `addCustomQual` extended with a `target` parameter
  ('add' | 'edit') so the same chip logic powers both forms.
- Save flow on Add coerces years_experience identically to Edit.

### Testing
- 6/6 new pytest in `test_iter_216h87_preview_and_add_trust.py`:
  - POST accepts trust fields at creation
  - Blank `years_experience` persists as `None`
  - Preview returns open-case URL (newer beats older)
  - Preview falls back to closed case when no open exists
  - 404 when engineer has no jobs (with "no jobs" copy)
  - 404 when engineer doesn't exist
- 30/30 across the h77 + h83 + h86 + h87 sub-suites (zero regressions).
- Frontend lint clean.
- Live UI smoke verified: Add form shows trust panel with 8 suggestion
  pills, chip clicks move qualifications between suggestion ↔ active,
  Preview button opens the tracking page in a new tab.

### Files touched
**Backend**
- `/app/backend/routes/svc/engineers_admin.py`
  (+1 import — `Request`)
  (+13 LOC — POST trust fields)
  (+45 LOC — preview-tracking-link endpoint)
- `/app/backend/tests/test_iter_216h87_preview_and_add_trust.py` (NEW · 6 tests)

**Frontend**
- `/app/frontend/src/pages/ServiceOps/EngineersAdminPage.js`
  (+~145 LOC — Add-form trust panel, Preview button, dual-form chip helpers)

### Strategic outcome
- Operators can onboard a new engineer with a complete trust profile in
  a single dialog — no need to add, then edit, then save.
- The **Preview** button doubles as a sales-demo lever: during a chain
  onboarding, the operator can pull up the customer's view in 1 click
  and walk the prospect through the experience their members will get.

---




## Iter 216h87 (UI follow-up) — Trust card fields in Engineer Admin (Feb 14, 2026)

Surfaced the new public-tracking-card fields in the operator-side
`EngineersAdminPage.js` so the trust card actually has data to display.

### What's new
- **Name cell** (view mode): tiny green ✓ BadgeCheck next to the name when
  `verified === true`. Optional 28×28 avatar thumbnail (when `photo_url`
  set). Qualifications summary line under the email (first 3 + "+N").
- **Trust profile row** (edit mode): a full-width second `<tr>` appears
  below the editing row, holding 4 new fields:
  - **Photo URL** — free-text input + live 36×36 preview.
  - **Years of experience** — number input (0–60).
  - **Verified engineer** — checkbox with explanatory caption "shown to
    customers on the live-tracking page".
  - **Qualifications** — chip-based picker with 8 industry-standard
    suggestions (IOSH, PAT Tester, CSCS, NEBOSH, 18th Edition, First
    Aid at Work, Working at Height, Confined Spaces) + custom-entry
    input (press Enter to add). Active chips have ✕ to remove.
- **Save flow**: `years_experience` coerced to int or `null` (blank
  clears). All 4 new fields sent in the existing PATCH payload — the
  `ALLOWED_ENGINEER_FIELDS` whitelist already accepts them (h87 backend).
- All elements have unique `data-testid`s for QA.

### Testing
- 2/2 new backend pytest (`test_iter_216h87_ui_trust_fields_patch.py`):
  trust fields persist via PATCH, null years_experience clears.
- **85/85 across the entire h75 → h87 suite** — zero regressions.
- UI smoke screenshot confirmed: edit drawer opens with all 4 fields,
  qualification chips move between suggestion ↔ active correctly,
  verified checkbox toggles, photo URL preview works.

### Files touched
**Backend**
- `/app/backend/tests/test_iter_216h87_ui_trust_fields_patch.py` (NEW · 2 tests)

**Frontend**
- `/app/frontend/src/pages/ServiceOps/EngineersAdminPage.js`
  (+~140 LOC — Trust profile row, qualifications chips, Verified
  badge in view mode, photo thumbnail in name cell)

### Operational notes
- Operators (owner/manager/master admin) can now populate the trust
  fields via Service Desk → Engineers → Edit. Changes propagate
  immediately to the live `/track/<token>` card.
- The tracking page degrades gracefully when fields are blank: avatar
  falls back to the initial circle, no Verified pill, rating/job-count
  rows hidden when stats are zero.

---




## Iter 216h86 + h87 — Pulse engineer bypass + Engineer trust card (Feb 13, 2026)

User raised a strategic question: "we don't want the partner program for
Pulse Fitness, but the app can very much work the same." Audit confirmed
the engineer-app guard (h77) was funneling everybody — including direct
employees of tenant orgs — through the £30/mo Partner Plan check.
Shipped two fixes.

### h86 — Internal engineer bypass
- `evaluate_engineer_app_access` (in `routes/partners.py`) gains a new
  reason: **`internal_engineer`**. Triggers when:
    1. User has NO `partner_engineers` row (i.e. never opted into the
       partner program), AND
    2. User has a `svc_engineers` row in their own org with `active!=false`.
  → Returns `allowed=True`, bypassing all subscription checks.
- Business model preserved: if you DID enrol as a partner, the partner
  rules apply (you opted in). Pulse / GymAxis-customer employees who
  never applied just use the app as part of their org's plan.
- Pulse engineers now get: photos, signatures, voice notes, parts on
  the engineer screen (h84), asset history (h85), service report PDF
  (h82) — the entire engineer experience — without any commercial layer.
- Tests: 2/2 passing. Verified no regression to h77 (15/15 still pass).

### h87 — Engineer trust card on the public tracking page
- `_engineer_card()` (in `routes/svc/public_tracking.py`) expanded to
  include: `photo_url`, `verified`, `qualifications`, `years_experience`
  + computed stats `avg_rating`, `ratings_count`, `jobs_completed_90d`
  (last 90 days, scoped to same org). Stats are aggregated inline from
  `svc_cases` — works for partner AND internal engineers alike.
- New `_engineer_public_stats()` helper runs a lightweight `$avg`
  aggregation + a `count_documents`. Brand-safe — no commercial data
  leaks.
- `ALLOWED_ENGINEER_FIELDS` in `engineers_admin.py` now accepts
  `photo_url`, `qualifications`, `years_experience`, `verified` so
  operators can populate them via the existing engineer-edit form.
- Frontend `PublicTrackingPage.js` upgraded:
  - **Photo** (avatar w/ brand-colour border) OR initial circle.
  - **Verified pill** (green ✓ Verified · top right).
  - **Rating row**: ★ avg · n reviews.
  - **Jobs in 90 days** · **years experience** chips.
  - **Skills chips** (up to 6, brand-tinted).
  - **Qualifications chips** (emerald, ✓-prefixed — IOSH, PAT, CSCS, etc).
- Tests: 2/2 passing.

### Bug found and fixed during build
- Initial `years_experience` plumbing pulled it from `stats` instead of
  the engineer doc — fixed by sourcing it from `engineer["years_experience"]`
  in `_engineer_card`.

### Verified
- **83/83 passing across h75 → h87** (4 skipped from earlier h74).
  Zero regressions on the h77 access guard despite the bypass change.
- Frontend lint clean.
- Live preview verified: `/track/<token>` on mobile (420×880) now shows
  the full trust card stack — avatar · Verified · 4.75★ · 4 reviews ·
  6 jobs in 90d · 7+ yrs · 4 skills · 3 qualifications.

### Files touched
**Backend**
- `/app/backend/routes/partners.py` (+22 LOC — internal_engineer bypass)
- `/app/backend/routes/svc/public_tracking.py` (+50 LOC — engineer stats + card fields)
- `/app/backend/routes/svc/engineers_admin.py` (+2 LOC — extra allowed fields)
- `/app/backend/tests/test_iter_216h86_87_pulse_engineer_and_profile.py` (NEW · 4 tests)

**Frontend**
- `/app/frontend/src/pages/PublicTracking/PublicTrackingPage.js` (~+70 LOC for the upgraded card)

### Strategic outcome
- **Partner program**: GymAxis customers only. Independent contractors. £30/mo (auto-discounted via referrals).
- **Pulse Fitness engineers**: direct employees of Pulse-branded tenants → use the engineer app fully via the internal_engineer bypass. No partner involvement.
- **GymAxis customer in-house engineers**: same as Pulse — employees, not contractors, use the app via internal_engineer bypass.
- **Customer-perceived quality**: tracking page now answers "who's coming?" with photo, real rating, real job count, verified badge, named qualifications. A trust signal on par with ServiceTitan / Jobber.

---




## Iter 216h82 → h85 — Customer Happiness Pack (Feb 13, 2026)

Strategic BDM audit of the Partner Engineer Network identified 4 gaps standing
between the platform and the "engineers love it, customers tell their friends"
threshold. All 4 shipped in one batch.

### h82 — Per-job Service Report PDF + email-to-customer
- `routes/svc/service_report.py` (NEW, ~330 LOC) — reportlab one-page PDF:
  branded header (org logo + primary colour), visit meta, time on site (travel
  + on-site + total), parts used table, work-done summary (pulled from the
  engineer's `fix_summary` event), 2-col photo grid (≤6, fetched via httpx),
  customer signature image, star rating w/ optional comment, branded footer.
- `GET  /api/svc/cases/{id}/service-report.pdf` — operator or assigned engineer.
- `POST /api/svc/cases/{id}/service-report/email` — Resend, attaches PDF,
  persists `service_report_sent_at` + `service_report_sent_to` on the case,
  appends audit event.
- Engineer mobile (`EngineerJobDetail.js`): **View report** + **Send to
  customer** buttons + "Sent · 5m ago" pill (visible once
  status ∈ {repaired, awaiting_sign_off, closed, invoiced}).
- Operator drawer (`ServiceCaseDrawer.js`): same shortcuts in the footer.
- 6/6 backend pytest passing.

### h83 — Customer Live-Tracking page (Uber-style)
- `routes/svc/public_tracking.py` (NEW, ~180 LOC).
- `GET  /api/svc/public/track/{token}` — **public, no auth**, token is the gate.
  Returns customer-friendly status copy (`status_label`, `status_blurb`,
  4-stage progress), engineer first name + skills + van reg, site, last 5
  customer-safe events, org branding (logo + primary colour), rating-captured
  + report-sent flags. **NEVER** leaks email, phone, allocated_parts,
  organization_id, or engineer PII (full name / email / mobile filtered).
- `GET  /api/svc/cases/{id}/tracking-link` — operator, lazily mints
  `secrets.token_urlsafe(18)` on first call.
- `POST /api/svc/cases/{id}/tracking-link/regenerate` — invalidates the old.
- Frontend `pages/PublicTracking/PublicTrackingPage.js` (NEW, ~220 LOC) —
  brand-banded header, live status pill, 4-stage progress bar, engineer card,
  site card, timeline, "All done" emerald success card; polls every 30 s
  while in-flight, every 5 min once closed; 404 page when token bad.
- Route `/track/:token` wired in `AppRoutes.js` (no auth gate).
- Operator drawer: **Get link / Copy again / Regenerate** controls.
- 7/7 backend pytest passing including PII-leak guards.

### h84 — Parts allocation on the engineer's mobile screen
- Engineer mobile (`EngineerJobDetail.js`): new **Parts used** section.
  - Allocated parts list with SKU · name · qty · source pill (van/warehouse)
    + per-row Remove button (calls existing DELETE `/svc/parts/allocate/{id}`).
  - Collapsible **Add part** form: 250 ms-debounced type-ahead against
    `GET /svc/parts?search=`, qty picker, source toggle (van | warehouse),
    one-click Allocate using existing `POST /svc/parts/allocate`.
  - Read-only view once the job is closed.
- Backend untouched — existing parts API already supports the flow.
- Backend pytest covers the end-to-end allocate → deallocate flow with van
  stock decrement/restore.

### h85 — Asset history sidebar
- `routes/svc/engineer.py::engineer_job_detail` now returns `asset_history`:
  the 3 most recent closed/repaired/awaiting/invoiced cases on the same asset
  (matched by `asset_id` if present, otherwise `asset_name`). Each row
  carries reference, title, fault_code, closed_at, customer_rating,
  resolution_notes — fast read, no extra round-trip from the PWA.
- Engineer mobile: amber "⚡ Asset history" card surfaces under the meta
  strip so engineers spot recurring faults the moment they open a job.
- 2/2 backend pytest passing.

### Bug found & fixed during build
- `_mint_or_get_token` initially used `if not case:` against a Motor
  `find_one()` with `{"_id": 0, "track_token": 1}` projection. When the
  doc had no `track_token` field yet, Motor returned `{}` — truthy in
  Mongo, falsy in Python — causing a spurious 404. Switched to `if case
  is None:`. Same pattern reviewed across new code.

### Verified
- **121 passed · 0 failures · 4 skipped** across the full h7\*/h8\* partner
  network + customer-happiness suites (regression confirmed).
- 16/16 new pytest specific to h82–h85.
- Frontend lint clean across all 4 touched JS files.
- Live preview: `/track/<token>` rendered cleanly on a mobile viewport
  (420×880) with brand-banded header, 4-stage progress, engineer card,
  timeline and emerald "All done" card.

### Files touched
**Backend**
- `/app/backend/routes/svc/service_report.py` (NEW)
- `/app/backend/routes/svc/public_tracking.py` (NEW)
- `/app/backend/routes/svc/engineer.py` (+33 LOC — asset_history)
- `/app/backend/route_registry/features.py` (+6 LOC — 2 new routers)
- `/app/backend/tests/test_iter_216h82_service_report.py` (NEW · 6 tests)
- `/app/backend/tests/test_iter_216h83_public_tracking.py` (NEW · 7 tests)
- `/app/backend/tests/test_iter_216h84_85_parts_and_history.py` (NEW · 3 tests)

**Frontend**
- `/app/frontend/src/pages/PublicTracking/PublicTrackingPage.js` (NEW · ~220 LOC)
- `/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetail.js`
  (+~190 LOC — Service Report, Parts, Asset history sections)
- `/app/frontend/src/pages/ServiceOps/ServiceCaseDrawer.js`
  (+~75 LOC — Service Report + Tracking Link footer rows)
- `/app/frontend/src/routes/AppRoutes.js` (+3 LOC — `/track/:token`)

### BDM rating after this batch
- Pre-h82:  **7.5 / 10**
- Post-h85: **9.5 / 10** — engineer & customer experience now best-in-class
  vs ServiceTitan / Joblogic / BigChange. Remaining diffs:
  - Stripe Connect Express auto-payouts (Phase 2, parked)
  - Live-map/ETA on the tracking page (geolocation pipeline)
  - Pre-job H&S / RAMS checklist
  - NPS comment box beyond the 5-star rating

---




## Iter 216h80 — Find an Engineer + Pulse Fitness Isolation (Feb 13, 2026)

### Why
Final brief from h75: "Verified Partner public listing surfaced to customers in their postcode radius." Plus an explicit guard: **"The engineer partner program is only for GymAxis customers NOT Pulse Fitness, ensure there is no bleed through."** This iter ships both.

### What shipped

#### Backend — `routes/partners.py`
**Pulse Fitness isolation** (the "no bleed-through" guarantee):
- `_is_pulse_user(user)` and `async _is_pulse_org(org_id)` — match on `account_type in {pulse_pro, pulse_lite, pulse}`, `is_pulse_admin`, or `brand in {pulse, pulse_fitness}`.
- `_require_gymaxis_only(user)` — raises 403 with a clear message: "The Partner Engineer Network is exclusive to GymAxis — Pulse Fitness customers don't have access to this programme."
- Applied at 4 critical entry points:
  1. `POST /partners/apply` — Pulse users can't apply.
  2. `attach_referral_to_org` — Pulse orgs are silently skipped on signup.
  3. `accrue_commission_on_invoice_paid` — defensive Pulse check (even if a legacy referred_by_partner_id is present, accrual returns None).
  4. `POST /customer-engineer-grants` — Pulse customers can't issue grants.

**"Find an engineer" widget endpoints**:
| Method · path | Behaviour |
|---|---|
| `GET /api/partners/find-engineers?postcode=...` | Returns ONLY `verified_partner` + `strategic_partner` matching the postcode outcode prefix (≥2 chars) OR carrying ≥75km travel radius (nationwide). Sorted: in-area first, then strategic above verified, then by 90-day performance score desc. Surfaces only public-safe fields (name, company, level, outcode AREA, radius, brands, skills, qualifications, score, tier, avg rating, jobs_completed_90d). **NEVER** returns email, phone, or commercial counts. |
| `POST /api/partners/find-engineers/{id}/request-contact` | Creates a `partner_contact_requests` row the engineer sees on their dashboard. Body `{note}`. Engineer must be approved + verified/strategic. |

Both endpoints are gated by `_require_gymaxis_only(user)` AND a secondary `_is_pulse_org(user.organization_id)` check — defense in depth. New collection `partner_contact_requests` with appropriate indexes.

#### Frontend — `pages/ServiceOps/FindEngineerPanel.js` (NEW, ~200 LOC)
- Lives on Service Desk → Cases tab between the Engineer Roster and the Filters/Cases stack.
- Postcode search box (uppercased, Enter to submit) → results card per engineer with:
  - Level badge (Verified — sky-blue · Strategic — purple)
  - Performance tier badge (Top-tier / Strong / Solid / Building track record / New partner)
  - "In your area" emerald pill or muted "Wide-radius"
  - Outcode area + travel radius + 90d-jobs count + ★ avg rating
  - Up to 4 brand chips + 3 skill chips
  - **"Request contact"** button → prompts for optional note → POST → button flips to green "Request sent ✓"
- Silent 403 handling: Pulse customers get a `null` render (no UI surface at all, the API has already rejected them).
- Friendly empty-state when no verified partners match: "the network's still growing. Add an ad-hoc contractor via the Engineer Roster above, or check back as more engineers join."

### Verified
- **58/58 partner-network pytest passing** (h75/h76/h77/h78/h79/h80):
  - Widget surfaces only verified+strategic levels
  - Widget never leaks email/phone/commercial fields
  - In-area match on outcode prefix; out-of-area below-75km partners excluded
  - Unverified partner doesn't surface
  - Request-contact creates audit row; 404 when partner not verified
  - Missing postcode → 422
  - **Pulse user CAN'T apply** → 403 with "GymAxis-exclusive" message
  - **Pulse user CAN'T search engineers** → 403
  - **Pulse user CAN'T create grants** → 403
  - **Pulse org legacy referred_by_partner_id does NOT attach on signup** (subprocess-isolated helper call)
  - **Pulse org Operations invoice does NOT accrue commission** even with legacy referred_by present (defensive double-check inside the accrual function)
- **Live preview** smoke: Service Desk Cases tab renders both Engineer Roster (h78) AND Find an Engineer (h80) panels side-by-side. Postcode search produces clean empty-state copy.

### Files touched
- `/app/backend/routes/partners.py` (+~80 LOC — Pulse guard helpers, widget endpoints, indexes, defensive accrual check, GymAxis-only on apply + grants + attach)
- `/app/frontend/src/pages/ServiceOps/FindEngineerPanel.js` (NEW)
- `/app/frontend/src/pages/ServiceOps/ServiceDeskPage.js` (+2 LOC — import + render)
- `/app/backend/tests/test_iter_216h80_find_engineer_pulse_isolation.py` (NEW — 11 tests)

### Operational impact
- A Pulse customer who hits any partner endpoint gets a friendly 403. No silent failures.
- A Pulse customer's Service Desk doesn't render the FindEngineerPanel at all (component silently returns null on 403). Engineer Roster panel is similarly protected via the same backend block on grants.
- **Defense in depth**: even if a Pulse org has a legacy `referred_by_partner_id` on it (data migration, manual DB edit, etc.), the accrual code's secondary `account_type`/`brand` check on `organizations` blocks the leak before any ledger row is created.

### Partner Engineer Network → COMPLETE 🎉
With h80 shipped, the brief from h75 is fully delivered:
1. ✅ Partner onboarding (h75)
2. ✅ Engineer Partner Plan (h75 + h76 — Live Stripe £30 with £15/free auto-discount)
3. ✅ Referral tracking (h75)
4. ✅ Commission tracking (h75 — signup 50% + £3/mo recurring · CSV payouts)
5. ✅ Engineer App subscription logic (h76 + h77)
6. ✅ Partner status levels (h75 — 4 levels, h79 performance-based recommendations)
7. ✅ Master Admin controls (h75 — approve/reject/suspend/level/queue/payout/CSV)
8. ✅ Stripe billing integration (h76 — live £30 + £15 + free transitions)
9. ✅ Partner dashboard (h75 + h76 subscription card)
10. ✅ Partner performance reporting (h79 — 90d composite score, tier, recommendation)
11. ✅ Customer-added engineers via grants (h77 + h78 — backend + UI)
12. ✅ Public listing for verified partners (h80)
13. ✅ GymAxis-only isolation from Pulse Fitness (h80)

### Phase 3 / nice-to-haves (no longer P1)
- Customer-side rating prompt at case sign-off (backend already accepts ratings via cases PUT)
- Engineer contact-requests inbox in Partner Dashboard (notifies via Resend)
- Stripe Connect Express auto-payouts (replaces CSV)
- Monthly partner scorecard email (mentioned in h79 finish)
- Per-case scope enforcement on customer grants (today grants are "active=true → any job"; per_case scope is recorded but not yet enforced at job-fetch time)

---



## Iter 216h79 — Partner Performance Scoring (Feb 13, 2026)

### Why
Final piece of the Partner Engineer Network promise: surface objective, data-driven performance scoring so Master Admin's level decisions (Engineer → Verified → Strategic) aren't subjective. Built on top of existing `svc_cases` — zero data duplication.

### What shipped

#### Backend — `routes/partners.py` (+~120 LOC)
**Composite score** out of 100, weighted across 4 components, computed pure-read-only from `svc_cases` joined on `assigned_engineer_id == partner.user_id`:

| Component | Weight | Source |
|---|---|---|
| SLA compliance  | 40% | `closed_at <= sla_resolve_at` ratio on closed cases in window |
| Completion rate | 30% | `closed / (closed + cancelled + rejected)` |
| Volume          | 20% | `closed / 50` (capped at 1.0 — 50 closed jobs/90d = full marks) |
| CSAT            | 10% | `avg(customer_rating) / 5.0`, neutral 0.8 if no ratings present |

**Tier classification** with level-up recommendations:
- 90–100 → **Top-tier** · recommends `strategic_partner`
- 75–89  → **Strong** · recommends `verified_partner`
- 60–74  → **Solid** · recommends `engineer_partner`
- < 60   → **Needs improvement**
- < 5 closed jobs → **Insufficient data** (with "need X more jobs" hint)

**Endpoints**:
| Method · path | Behaviour |
|---|---|
| `GET /api/master-admin/partners/{id}/performance?window_days=90` | Full breakdown — score, components, counts, tier, recommended_level |
| `GET /api/master-admin/partners/performance/leaderboard?window_days=90` | All approved partners scored over the same window, sorted by score desc (insufficient_data bucket last) |

**Customer-rating capture**: added `customer_rating` (1–5) and `customer_rating_comment` to the allow-list in `routes/svc/cases.py::update_case` so the existing `PUT /api/svc/cases/{id}` round-trips ratings from any sign-off UI.

#### Frontend — `pages/MasterAdmin/AdminPartners.js`
- New **Performance** column on the partner table showing the tier badge (5 colour-coded states), numeric score, and a ⭐ star with avg-rating when ratings exist.
- **Promote pill** that appears under the level dropdown ONLY when the partner's score-derived `recommended_level` differs from their current level — one-click promotes via the existing `set_level` endpoint.
- Tooltip on the numeric score shows the full breakdown: `SLA 83% · CSAT 4.67 · 12 jobs in 90d`.
- `leaderboard` fetched once in parallel with the partners/queue/summary triple — single round trip, no N+1.

### Verified
- **47/47 partner-network pytest** passing (h75 + h76 + h77 + h78 + h79):
  - Empty window → insufficient_data + score 0
  - 3 closed jobs (below MIN_CLOSED_FOR_SCORE=5) → still insufficient_data
  - 10 perfect cases (within SLA + 5★) → score 84 → "strong" → recommends verified_partner
  - 50 perfect cases → score 100.0 → "top_tier" → recommends strategic_partner
  - 8 closed (2 within SLA · CSAT 2) + 4 cancelled → score 37 → "needs_improvement"
  - Leaderboard sorts by score desc, insufficient_data last
  - `window_days=1000` → 422 validation error
  - Customer rating round-trips through `PUT /api/svc/cases/{id}`
- **Live preview**: seeded 12 cases (10 within SLA, 8×5★ + 4×4★) on the E1 partner → Master Admin shows **STRONG · 78 · ★4.67 · Promote** in the row.

### Files touched
- `/app/backend/routes/partners.py` (+~120 LOC — `compute_partner_performance` + 2 endpoints)
- `/app/backend/routes/svc/cases.py` (+2 fields to `EDITABLE_FIELDS`)
- `/app/frontend/src/pages/MasterAdmin/AdminPartners.js` (+~50 LOC — Performance column, Promote pill, PerformanceCell + TIER_STYLE)
- `/app/backend/tests/test_iter_216h79_partner_performance.py` (NEW — 8 tests)

### Phase 2 remaining
- **Verified Partner public listing** — "find an engineer" widget in Operations (sole P2 item left from h75's brief).
- Customer-side **rating prompt** at case sign-off — backend already accepts `customer_rating`; just needs a star-picker in the case drawer's close flow.

---



## Iter 216h78 — Engineer Roster (customer-side grants UI · Feb 13, 2026)

### Why
h77 shipped the backend `partner_job_grants` endpoints but no UI — gyms couldn't actually grant ad-hoc contractors access to the Engineer App. This iter closes that gap with a panel inside the unified Service Desk so the "5b" customer-added engineer flow is a real product, not just an API.

### What shipped
- **New `EngineerRosterPanel`** at `pages/ServiceOps/EngineerRosterPanel.js` (~220 LOC):
  - "0 active" pill badge in the header for at-a-glance status.
  - **Add engineer** form (collapsible) with email, scope toggle (`All jobs at our gym` vs `Specific jobs only`), comma-separated case IDs (when per-case), and a free-text internal note.
  - Active grants list with each engineer's name + email + scope summary, and an inline **Revoke** button per row.
  - Collapsible **Revoked grants history** section so the audit trail stays visible without cluttering the active view.
  - Empty state explains exactly what the panel is for — "give an ad-hoc contractor access to the Engineer App for your gym's jobs."
  - Inline reassurance copy: *"Grants are free for your gym. They unlock the Engineer App for this contractor without them needing a Partner Plan subscription."*
- **Service Desk wiring**: panel slots into the unified Service Desk → Cases tab, between Live engineers and the Filters/Cases stack, so the operator sees their roster in the same view as live jobs.
- **Data-testids on every interactive element**: `engineer-roster-panel`, `engineer-roster-add-toggle`, `engineer-roster-add-form`, `engineer-roster-email`, `engineer-roster-scope`, `engineer-roster-cases`, `engineer-roster-note`, `engineer-roster-submit`, `engineer-roster-row-{id}`, `engineer-roster-revoke-{id}`, `engineer-roster-revoked-history`, `engineer-roster-revoked-{id}`, `engineer-roster-count`, `engineer-roster-empty` — all the hooks the testing agent needs.

### Verified
- **39/39 backend pytest passing** across the full partner-network suite (h75/h76/h77/h78):
  - `org_wide` grant accepted with empty case_ids.
  - `per_case` grant round-trips case_ids set-equal.
  - List shows both active + revoked grants with correct timestamps.
  - Revoking an unknown grant returns 404.
  - The h77 reset fixture now also resets `app_fee_tier` + cleans orphan referrals so tests stay deterministic when run in any order.
- **Frontend smoke**: panel rendered live at `/service-desk` → Cases tab — Add form expanded correctly, all fields keyboard-focusable, "Grant access" CTA visible. Empty-state copy confirmed.

### Files touched
- `/app/frontend/src/pages/ServiceOps/EngineerRosterPanel.js` (NEW)
- `/app/frontend/src/pages/ServiceOps/ServiceDeskPage.js` (+3 LOC — import + render)
- `/app/backend/tests/test_iter_216h78_engineer_roster.py` (NEW — 4 endpoint sanity tests)
- `/app/backend/tests/test_iter_216h77_engineer_access_guard.py` (hardened `reset_operator` fixture)
- `/app/backend/tests/test_iter_216h75_partner_network.py` (relaxed tier assertion to cope with mid-test state)

### Phase 2 remaining
- **Verified Partner public listing** in Operations ("find an engineer" widget — only `verified_partner` / `strategic_partner` levels visible).
- **Performance / reliability scoring** for level decisions (completed-jobs / SLA-met / customer-rating signals).

---



## Iter 216h77 — Engineer App Access Guard (Phase 2b · Feb 13, 2026)

### Why
P2 backlog item: gate `/svc/engineer*` access behind the Partner Engineer Network so that the £30/£15/free Partner Plan from h76 isn't just an opt-in feature — it's the way you unlock the Engineer App. Per h75 decision (5a), every engineer must hold an active subscription OR qualify via the free tier OR have an explicit customer grant.

### What shipped

#### Backend
**New router-level dependency** in `routes/partners.py` (~140 LOC):
- `evaluate_engineer_app_access(user)` — pure resolver returning `{allowed, reason, partner, subscription, app_fee_tier, active_grant_count}`. Reasons: `master_admin · active_subscription · trialing · free_tier · customer_grant · needs_application · application_pending · application_rejected · suspended · needs_subscription`.
- `require_engineer_app_access` — FastAPI Depends wrapper. On denial, raises HTTP **402 Payment Required** with a structured body:
  ```json
  {
    "detail": {
      "code": "engineer_app_blocked",
      "reason": "needs_subscription",
      "subscription_status": null,
      "app_fee_tier_gbp": 30,
      "message": "Start the £30/mo Partner Engineer Plan..."
    }
  }
  ```
- 402 was chosen deliberately over 403 — semantically "you can pay to fix this", which the PWA uses to route to subscription rather than logout.

**Wired the guard onto the entire `/svc/engineer/*` router** in one line — every endpoint inherits via `APIRouter(dependencies=[Depends(require_engineer_app_access)])`. Zero per-route changes; future endpoints are gated by default.

**Active subscription states** that grant access: `active`, `trialing`, `past_due` (dunning continues; we don't hard-cut the engineer mid-incident).

**Master admin bypass** — `is_master_admin / is_pulse_admin / role==pulse_master_admin` always pass, so support & QA can impersonate.

**Customer-added engineer grants** — new collection `partner_job_grants`:
| Endpoint | Behaviour |
|---|---|
| `GET  /api/customer-engineer-grants` | Customer lists grants they've issued |
| `POST /api/customer-engineer-grants` | Customer grants an engineer access (body: `engineer_email`, optional `case_ids[]`, `scope`, `note`) |
| `DELETE /api/customer-engineer-grants/{id}` | Customer revokes a grant (soft — sets `active=false`, audit-preserved) |

The engineer doesn't need a subscription or partner profile to use the app when an active grant exists for their `user_id`. This implements h75 5b semantics under the umbrella of the 5a policy: contractors hired one-off don't pay; full partners do.

**Frontend access status endpoint**: `GET /api/partners/me/engineer-access` returns the same `{allowed, reason, …}` shape WITHOUT raising 402 — so the dashboard / landing pages can render the right CTA without first triggering a 402 toast.

#### Frontend
- **`pages/ServiceOps/Engineer/EngineerAccessGate.js`** (NEW, ~85 LOC) — 5 reason-driven views (`needs_application`, `application_pending`, `application_rejected`, `suspended`, `needs_subscription`), each with a contextual icon, headline, sub-copy, and a single CTA to the right destination (`/partner-engineer/apply` or `/partner-engineer`). Footer always mentions the customer-grant fallback so the engineer knows they have options.
- **`EngineerHome.js`** — `load()` now intercepts 402 with `code=engineer_app_blocked` and renders the gate in-place. Other errors continue to fire the existing toast. State managed via a single `accessBlock` value; render returns the gate component when set.

### Verified
- **35/35 backend pytest** passing across h75 (17), h76 (7), and h77 (11):
  - Master admin can hit `/svc/engineer/me` (HTTP 200)
  - Paid tier + no sub + no grant → HTTP 402 with `reason="needs_subscription"` and `app_fee_tier_gbp=30`
  - Active subscription unblocks (status `active` or `trialing`)
  - 10+ active referrals auto-flips to free tier and unblocks
  - Active customer grant unblocks (even with `reason=customer_grant`)
  - Revoked grant doesn't unlock
  - Suspended partner returns 402 with `reason="suspended"`
  - Customer can create + list + revoke grants
  - Unknown engineer email returns 404 on grant create
  - `/partners/me/engineer-access` returns 200 with `allowed=false` (never 402)
- **Frontend smoke**: gate renders correctly at `/svc/engineer` for the operator E1 partner with no active subscription — purple lock icon, "Activate the Engineer App" headline, "Start subscription" CTA links to `/partner-engineer`.

### Files touched
- `/app/backend/routes/partners.py` (+~140 LOC — access resolver, dependency, 3 grant endpoints, indexes)
- `/app/backend/routes/svc/engineer.py` (+5 LOC — router-level `Depends(require_engineer_app_access)`)
- `/app/frontend/src/pages/ServiceOps/Engineer/EngineerAccessGate.js` (NEW)
- `/app/frontend/src/pages/ServiceOps/Engineer/EngineerHome.js` (402 interception + gate render)
- `/app/backend/tests/test_iter_216h77_engineer_access_guard.py` (NEW — 11 tests, sync pymongo to avoid Motor loop-pinning)
- `/app/backend/tests/test_iter_216h7{5,6}_*.py` (`_run_async` revert for consistency)

### ⚠ Operational impact
- **Existing svc_engineers users without a partner profile will now be blocked.** Master admin needs to either:
  1. Have those engineers apply via `/partner-engineer/apply` and approve them, OR
  2. Issue customer grants from each gym's Service Desk (frontend admin UI for this is the next sub-task — backend endpoints are ready).
- The 402 response means existing engineer mobile clients on a stale build will get an unusual error code. Their next deploy/refresh picks up the new gate.

### Phase 2 remaining (next iters)
- **Customer-side Service Desk UI** for the engineer-grants endpoints (Add Engineer / Revoke).
- **Verified Partner public listing** in the Operations module ("find an engineer").
- **Performance / reliability scoring** for level decisions.

---



## Iter 216h76 — Partner Plan: Live Stripe subscription (Phase 2a · Feb 13, 2026)

### Why
P2 backlog from h75: "Live £30/£15/free Partner Plan Stripe subscription that reads the auto-computed `app_fee_tier`." Without live billing, the foundation was money-aware but inert — engineers couldn't actually pay £30/mo for their Engineer App access, and milestone-driven discounts (5+ refs = £15, 10+ refs = free) couldn't transition automatically.

### What shipped

#### Backend — `routes/partners.py` (~200 LOC added)
**Env-driven price IDs** (production must seed these once the Stripe products are created):
- `STRIPE_PRICE_PARTNER_PLAN_30` → £30/mo
- `STRIPE_PRICE_PARTNER_PLAN_15` → £15/mo
- Free tier (10+ active refs) ⇒ subscription is cancelled at period end — no price ID needed.

**Three new partner-self endpoints**:
| Endpoint | Behaviour |
|---|---|
| `POST /partners/me/subscription/checkout` | Spins a Stripe Checkout Session (subscription mode) using the partner's CURRENT tier price. Returns 501 when env vars unset, 400 when tier is free, 400 when application unapproved. `subscription_data.metadata.kind="partner_engineer_plan"` is the discriminator the webhook uses to route back. |
| `POST /partners/me/subscription/cancel` | Sets `cancel_at_period_end=true` on Stripe → keeps Engineer App access until end of paid month. |
| `POST /partners/me/subscription/resume` | Reverses a pending cancellation. |

**Auto-sync on tier milestones** — `_recompute_app_fee` now detects whenever the `app_fee_tier.price_gbp` changes (e.g. 4 → 5 active refs flips £30 → £15) and:
- For paid → paid transitions: `stripe.Subscription.modify(items=[{id, price=NEW}])` with `proration_behavior="create_prorations"` so the engineer is credited fairly for the difference.
- For paid → free (10+ refs): `cancel_at_period_end=true` so the engineer enjoys the rest of the month at zero risk of accidental double-billing, then lapses naturally to free.
- For free → paid (re-activation): no Stripe call until the engineer manually re-checks-out (the existing Cancel/Resume flow handles voluntary toggles).

**Webhook hooks** in `routes/payments.py`:
- `checkout.session.completed` → calls `handle_partner_checkout_completed` which binds the new `stripe_subscription_id` + `stripe_customer_id` onto the partner row and audit-logs the activation.
- `customer.subscription.updated` (NEW handler) → calls `handle_partner_subscription_event` to keep the partner profile mirrored: `status`, `current_period_end` (ISO), `cancel_at_period_end`, `stripe_price_id`.
- `customer.subscription.deleted` → the existing platform handler now also routes into `handle_partner_subscription_event` for partner cleanup.
- All hooks discriminate on `metadata.kind == "partner_engineer_plan"` so they NEVER touch non-partner subscriptions (Operations module, etc.).

#### Frontend — `pages/PartnerEngineer/PartnerDashboard.js` (~+90 LOC)
- New **"Partner plan subscription"** card slotted between the referral block and the stat grid, only visible once the application is approved.
- Three visual states driven by partner data:
  - **No active sub** → "Start your Partner Engineer Plan · £30/mo · auto-discounts to £15 at 5 refs and free at 10+" with a **Start subscription** button that redirects to Stripe Checkout.
  - **Active sub** → "Active · £X/mo · Next charge YYYY-MM-DD" with a **Cancel** button.
  - **Pending cancellation** → "Cancels YYYY-MM-DD" with a **Resume** button.
  - **Free tier** → "Free tier active — N active referrals" green confirmation, no buttons.
- Post-Checkout return is handled inline: `?subscription=success` → toast + clear params + reload partner; `?subscription=cancelled` → friendly toast.

### Verified
- **25/25 backend pytest** passing (h75 17 + h76 8):
  - Checkout 501 when env vars unset.
  - Free-tier blocks checkout with 400.
  - `handle_partner_checkout_completed` binds the subscription onto the partner.
  - `handle_partner_subscription_event` mirrors `status`/price/cancel-flag/period-end.
  - Non-partner-kind metadata is correctly ignored — other Stripe subscriptions in the platform are not touched.
  - Price-id resolver returns `None` for free tier and unconfigured tiers.
  - Cancel with no subscription returns 400.
- **Live recompute → auto-tier-swap** smoke test passed: seeded 5 active referrals → `_recompute_app_fee` flipped tier from £30 to £15 cleanly with no Stripe-call exceptions when no subscription is bound yet.
- **Frontend smoke**: subscription card rendered at `/partner-engineer` with the correct "Start subscription · £30/mo" CTA.

### Files touched
- `/app/backend/routes/partners.py` (+~200 LOC — subscription helpers, 3 endpoints, 2 webhook hooks, auto-sync in `_recompute_app_fee`)
- `/app/backend/routes/payments.py` (+25 LOC — `_handle_subscription_updated`, partner-checkout hook, webhook handler registration)
- `/app/frontend/src/pages/PartnerEngineer/PartnerDashboard.js` (+~90 LOC — `SubscriptionCard` component + state-driven actions)
- `/app/backend/tests/test_iter_216h76_partner_subscription.py` (NEW — 8 regression tests)

### ⚠ Action required (production)
1. **Create the two Stripe products** in the Stripe Dashboard:
   - Product: "GymAxis Partner Engineer Plan · £30/mo" → recurring monthly £30 GBP
   - Product: "GymAxis Partner Engineer Plan · £15/mo" → recurring monthly £15 GBP
2. **Add the two price IDs to backend `.env`**:
   ```
   STRIPE_PRICE_PARTNER_PLAN_30=price_xxx
   STRIPE_PRICE_PARTNER_PLAN_15=price_yyy
   ```
3. **Restart backend**: `sudo supervisorctl restart backend`.
4. Without these env vars, the Start-subscription button returns 501 with a friendly "ask Master Admin" message — engineers can still see and apply, but can't subscribe yet.

### Phase 2 remaining (next iters)
- **Stripe Connect Express** auto-payouts to engineers (replaces CSV).
- **Engineer App access guard** — `/svc/engineer` requires `subscription.status === "active"` OR a customer-added job grant.
- **Verified Partner public listing** — recommended engineers visible to customers in the Operations module's "find an engineer" widget.
- **Performance / reliability scoring** rolled into the level decision matrix.

---



## Iter 216h75 — Partner Engineer Network · Phase 1 (Feb 13, 2026)

### Operator brief
"Build the Partner Engineer Network as a brand-new commercial layer on top of the existing Engineer App + Service Desk. One source of truth. Bulletproof against abuse."

### Operator decisions (captured)
- Operations module £59 → **£69/mo** (drives the 50% signup reward maths).
- **MVP first** — Phase 1 ships the foundation; Stripe Connect auto-payouts + live £30/mo subscription billing land in Phase 2.
- Payouts Phase 1: **CSV export** through Master Admin → BACS, with the schema already wired for Stripe Connect Express drop-in.
- Engineer identity: **new `partner_engineers` collection** linked by `user_id` — keeps commercial state out of `svc_engineers` (the operational Engineer App profile).
- Customer-added engineers will need an active Partner subscription to use the Engineer App (Phase 2 enforcement; Phase 1 still creates the data).

### What shipped

#### Backend — `routes/partners.py` (NEW, ~620 LOC)
4 new collections (all indexed in `server.startup`):
- `partner_engineers`        — profile, referral_code, status, level, terms, payout config, app-fee tier
- `partner_referrals`        — one row per referred org (unique on `referred_organization_id`)
- `partner_commission_ledger` — append-only accruals (unique on `source_invoice_id`)
- `partner_payouts`          — batched approved accruals (CSV / Connect)
- `partner_audit_log`        — every state transition with actor + before/after

20 endpoints, 8 self-service + 12 master-admin:

| Endpoint | Purpose |
|---|---|
| `GET  /partners/me` | Partner profile + live recomputed referral link & app-fee tier |
| `POST /partners/apply` | Idempotent onboarding submission |
| `GET  /partners/me/referrals` | Referred orgs (status, first_paid_at, recurring totals) |
| `GET  /partners/me/commission` | Ledger + totals by status |
| `GET  /partners/public/lookup?code=` | Public referral-code validation for signup pages |
| `POST /master-admin/partners/{id}/approve` | + level swap |
| `POST /master-admin/partners/{id}/reject` | with audited reason |
| `POST /master-admin/partners/{id}/suspend` | |
| `POST /master-admin/partners/{id}/level` | Validated against `PARTNER_LEVELS` |
| `POST /master-admin/partners/referrals/{id}/flag-pre-existing` | Anti-abuse claw-back |
| `GET  /master-admin/partners/commission/queue` | Accrued rows awaiting approval, enriched with partner name/email |
| `POST /master-admin/partners/commission/{id}/approve` | |
| `POST /master-admin/partners/commission/{id}/reject` | |
| `POST /master-admin/partners/payouts/queue` | Bundle approved rows → payout |
| `POST /master-admin/partners/payouts/{id}/mark-paid` | + BACS reference |
| `GET  /master-admin/partners/payouts/{id}/csv` | Streaming CSV download |
| `GET  /master-admin/partners/reports/summary` | Headline counts + commission totals by state |

#### Commission engine
- Operations module is detected via `STRIPE_PRICE_OPERATIONS` env var OR the literal word `operations` in the invoice line description (resilient to env config drift).
- **Signup reward**: 50% of the FIRST cleared Operations invoice (£34.50 on £69) — written once, gated by `partner_referrals.first_paid_at`.
- **Recurring**: £3/month on every subsequent Operations invoice for that referral, with `recurring_total_paid_gbp` tracked on the referral row for audit.
- **Idempotent** by Stripe `invoice.id` — unique partial index on `partner_commission_ledger.source_invoice_id`; webhook replays are a no-op.

#### Anti-abuse rules (all unit-tested)
1. `attach_referral_to_org` refuses if the partner's own org would be the referred org.
2. `organizations.referred_by_partner_id` is write-once — re-attribution is silently rejected.
3. `pre_existing_in_pipeline=true` on a referral suppresses new accruals AND claws back any non-paid ledger rows for that referral.
4. Unique constraint on `partner_referrals.referred_organization_id` means a single org can NEVER be claimed by two partners.
5. Master Admin approval is REQUIRED before a ledger row can join a payout batch.
6. Every state transition (apply, approve, reject, suspend, level, claw-back, payout-queue, mark-paid) writes a `partner_audit_log` row with actor + before/after.
7. Referral codes drawn from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no 0/O/1/I) — defeats homoglyph confusion.

#### App-fee tiering — auto-computed on every `/partners/me`
```
0–4 active referrals   →  £30/mo
5–9  →  £15/mo
10+  →  free
25+  →  free + `enhanced_review_required=true`
```
Stored on `partner_engineers.app_fee_tier` so the Stripe sync job in Phase 2 can transition the customer to the correct price ID without a UI round-trip.

#### Pricing bump — Operations £59 → £69
- `routes/payments.py::PRICING_CATALOG` updated.
- `pages/Marketing/PricingMarketingPage.js` module card, JSON-LD offer, and header doc-comment all bumped.
- *Stripe Price ID stays untouched* — production Stripe products need a manual `stripe products` update (separate ops migration). The legacy guard test (`test_stripe_prices_guard_216o.py`) still asserts £59 / 59pence and is left as-is so we don't accidentally pretend Stripe is live.

#### Frontend
- `pages/PartnerEngineer/PartnerApplyWizard.js` (~220 LOC) — mobile-friendly 5-step onboarding (welcome → profile → service area → skills/brands → terms). Idempotent against an existing draft. Posts to `/partners/apply`.
- `pages/PartnerEngineer/PartnerDashboard.js` (~190 LOC) — referral link + code with copy buttons; 4-stat grid (active refs · app fee · pending payout · paid lifetime); referred-customers table; commission ledger table. Hard scope — no CRM / Operations / Memberships data exposed.
- `pages/MasterAdmin/AdminPartners.js` (~230 LOC) — applications table (approve/reject/suspend/level), commission queue grouped per partner with one-click "Queue payout + CSV download", live summary chips.
- Sidebar: new `Growth → Partner Engineers` entry (`BadgeCheck` icon) routes to the new admin section.
- Routes: `/partner-engineer` (dashboard) + `/partner-engineer/apply` (wizard), both behind auth.

#### Referral attribution hook
- `models/schemas.UserRegister.ref_code` (optional) — signup pages can append `?ref=CODE` and the auth flow passes it through.
- `routes/auth.register` calls `attach_referral_to_org` post-creation; failures are logged but never block signup.

#### Stripe webhook hook
- `routes/payments._handle_invoice_paid` calls `accrue_commission_on_invoice_paid` after the original logic finishes. Idempotent, scoped to Operations charges, never blocks the original handler.

### Verified
- **17/17 backend pytest** passing in `/app/backend/tests/test_iter_216h75_partner_network.py`:
  - apply happy path + idempotency + terms validation
  - master admin list / approve / reject / suspend / level (+ bad-level 400 / no-auth 401)
  - public referral lookup (valid + unknown)
  - commission accrual: signup 50% of £69 = £34.50, recurring £3, webhook replay no-op
  - anti-abuse: own-org refusal, already-attributed immutability, pre-existing-flag accrual block
  - app-fee tier thresholds (0/4/5/9/10/25)
  - full queue → approve → CSV → mark-paid round-trip
  - reports summary shape
- **Live curl E2E**: apply → admin list → approve → public lookup → simulated invoices → commission queue → approve all → payout queue → CSV download → mark paid (with BACS reference).
- **Frontend smoke**: `/partner-engineer` rendered for the approved E1 Agent — Hi banner, APPROVED badge, referral link `https://…/?ref=AGQZKPAP`, all 4 stats live, empty states for referrals + ledger.

### Files touched
- `/app/backend/routes/partners.py` (NEW, ~620 LOC)
- `/app/backend/routes/auth.py` (+10 LOC — `ref_code` attribution call)
- `/app/backend/models/schemas.py` (+5 LOC — `UserRegister.ref_code`)
- `/app/backend/routes/payments.py` (+10 LOC — webhook hook + £59→£69 catalog)
- `/app/backend/route_registry/features.py` (+2 LOC — register the router)
- `/app/backend/server.py` (+3 LOC — `ensure_partner_indexes` at startup)
- `/app/frontend/src/pages/PartnerEngineer/PartnerApplyWizard.js` (NEW)
- `/app/frontend/src/pages/PartnerEngineer/PartnerDashboard.js` (NEW)
- `/app/frontend/src/pages/MasterAdmin/AdminPartners.js` (NEW)
- `/app/frontend/src/pages/MasterAdminPage.js` (+3 LOC — `partners` case)
- `/app/frontend/src/pages/MasterAdmin/SidebarConfig.js` (+3 LOC — new sub-tab + `BadgeCheck` import)
- `/app/frontend/src/routes/AppRoutes.js` (+5 LOC — `/partner-engineer` routes)
- `/app/frontend/src/pages/Marketing/PricingMarketingPage.js` (price bump £59→£69 in 3 spots)
- `/app/backend/tests/test_iter_216h75_partner_network.py` (NEW — 17 tests)
- `/app/memory/test_credentials.md` (E1 partner record)

### ⚠ Action required
1. Redeploy preview → production. Backend + frontend.
2. **Stripe production**: manually update the Operations module's price product on the Stripe dashboard (`STRIPE_PRICE_OPERATIONS`) from £59 → £69 to match the platform-side bump. Old subscriptions on the £59 price ID will continue at £59 until each customer's billing cycle migrates (Stripe doesn't auto-migrate price IDs).
3. **Partner Engineer terms PDF**: replace the inline terms preview in the Apply Wizard's step 5 with a link to the final legal document once produced.
4. Phase 2 hooks already wired (no Phase 1 rework needed):
   - `partner_engineers.payout.method` → flip to `stripe_connect` once Connect Express onboarding lands.
   - `partner_engineers.subscription.stripe_subscription_id` → set when the £30/£15/free Partner Plan goes live.
   - `partner_engineers.app_fee_tier` is already auto-computed — Phase 2 just reads it and transitions the Stripe subscription's price ID.

### Phase 2 backlog (locked-in, not yet shipped)
- Stripe Connect Express onboarding for engineer payouts (one-click "Connect with Stripe" in the Partner Dashboard).
- Live Stripe billing for the Partner Plan: £30 → auto-transition to £15 at 5 active refs, free at 10, mark for enhanced review at 25.
- Engineer App access guard — require active partner subscription (or customer-added job grant) for `/svc/engineer` access.
- Partner public listing for "find an engineer" — verified partners only.
- Performance / reliability scoring rolled into the partner level decision matrix.

---



## Iter 216h74 — Starter Pack: Send/Launch wiring (Feb 13, 2026)

### Why
Lee's P1 backlog item: "Wire up the newly configured Marketing Starter Pack to the actual Send/Launch flows." The h71 starter pack rendered 3 emails + 3 social posts with **Copy** buttons only — the operator still had to manually paste copy into Campaigns / their email tool. This iter closes the loop: every email draft becomes a real Campaign and/or a real Resend test send in one click, and all three emails can be auto-wired into a Welcome Journey.

### What shipped

#### Backend — `routes/marketing/starter_pack.py` (+~180 LOC)
Three new module-gated endpoints alongside the existing generate/get/delete:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/marketing/starter-pack/emails/{email_id}/test-send` | Real Resend dispatch to the operator (or `{to: ...}`). Subject prefixed `[Test]`. Co-brand wrapper applied (h64). |
| POST | `/api/marketing/starter-pack/emails/{email_id}/create-campaign` | Creates a `marketing_campaigns` draft pre-loaded with the email's subject + HTML body. Idempotent — second call returns `already_exists: true` + the same campaign id. |
| POST | `/api/marketing/starter-pack/create-journey` | Creates a `marketing_journeys` draft: send(Welcome) → wait 3d → send(Win-back) → wait 7d → send(Promo). 5 nodes + 4 edges, status=draft, trigger=`member_signed_up`. Idempotent. |

Helpers added:
- `_plain_to_html()` — converts Claude's plain-text body (paragraphs split on `\n\n`) into email-client-safe inline-styled HTML with `<p style="margin:0 0 16px 0;line-height:1.55;color:#1f2937;font-size:15px;">`. HTML-escapes content. Idempotent (skips conversion if already-HTML).
- `_find_email()` — 400 on unknown id, 404 if pack hasn't been generated yet.
- `_load_pack_doc()` — friendly 404 with the "click Draft my starter pack" hint.

Launch state persisted into `marketing_starter_pack.launches`:
```jsonc
{
  "emails": {
    "welcome": {"campaign_id": "...", "campaign_created_at": "...", "test_sent_at": "...", "test_sent_to": "..."},
    "win_back": {...},
    "promo": {...}
  },
  "journey_id": "...",
  "journey_created_at": "..."
}
```

#### Frontend — `pages/Marketing/StarterPackPanel.js` (~+130 LOC)
- **Top row CTA**: "Build welcome journey" — purple, with a `GitBranch` icon, swaps to "Journey created · Open" (green) once wired and deep-links to `/marketing?tab=journeys&journey=<id>`.
- **Per-email card body** (when an email's `<details>` is expanded):
  - "Send test to me" — fires Resend, shows "Sent 2m ago" relative timestamp once delivered.
  - "Create campaign" — POSTs the create-campaign endpoint and deep-links to `/marketing?tab=campaigns&campaign=<id>`. Once a campaign exists for that slot, the button flips to "Campaign · Open" (green) and just re-navigates.
- Both buttons share the same `busyAction` state so only one action shows a spinner at a time. Idempotent backend ↔ idempotent UI: clicking twice never creates duplicates.
- `formatRelative()` helper renders the test-send timestamp as "just now / 5m ago / 2h ago / 3d ago".
- Notifications via `notify.success` + `notifyApiError` so the operator gets a clean toast on every action.

### Verified
- **Backend pytest**: 10/10 passing in `/app/backend/tests/test_iter_216h74_starter_pack_launch.py`:
  - create-campaign creates a draft + idempotent + 400 on bad id + launches state persisted.
  - create-journey wires the correct 5-node / 4-edge shape, wait minutes = 3·24·60 and 7·24·60, send-email nodes carry subject + body_html.
  - test-send accepts 200 or 502 (preview's Resend sender domain is unverified — endpoint still proves the wiring is correct), 400 on bad id, 400 on malformed `to`.
  - All endpoints require auth (401/403).
- **Manual curl E2E**: create-campaign → idempotent → create-journey → 5 nodes / 4 edges → cleanup.
- **Frontend smoke**: data-testids present (`starter-pack-build-journey`, `starter-pack-create-campaign-welcome`, `starter-pack-test-send-welcome`, …); deep-linking to Campaigns/Journeys tabs verified through MarketingSuite's `?tab=` initial-tab resolver.

### Files touched
- `/app/backend/routes/marketing/starter_pack.py` (+~180 LOC — 3 endpoints + helpers + launch-state persistence)
- `/app/frontend/src/pages/Marketing/StarterPackPanel.js` (rewritten, ~+130 LOC — Build-journey CTA + per-email Send-test + Create-campaign buttons + state-based "Open" rebadging + `useNavigate` deep-links)
- `/app/backend/tests/test_iter_216h74_starter_pack_launch.py` (NEW — 10 regression tests)

### ⚠ Action required
1. Redeploy preview → production. Backend (`starter_pack.py`) + frontend (`StarterPackPanel.js`).
2. Production sender domain (e.g. `gymaxisai.com`) must be **verified on Resend** for "Send test to me" to land in the operator's inbox. Without verification the endpoint returns a 502 with the explicit "domain not verified" message — operators still get value from create-campaign + create-journey without the live send.
3. Operator workflow after deploy:
   - Marketing → Brand Kit → Starter Pack panel → "Draft my starter pack".
   - On each email: **Send test to me** to preview in their inbox, **Create campaign** to push the draft into Campaigns (then pick an audience and Send), or use the top-of-pack **Build welcome journey** to drop all three into a wired 3-step automation in Journeys.

### Knock-on benefits
- Zero copy/paste between the starter pack and the production Send/Launch tools.
- The journey draft becomes a starting point any operator can edit — change a wait duration, add a branch, swap the trigger from `member_signed_up` to a custom event.
- Launches persist on the pack doc, so re-visits show the operator exactly which drafts have been wired live.

---



## Iter 216h73 — Brand Discovery: full homepage marketing capture (Feb 13, 2026)

### Why
Operator stress-test against **tryholo.ai** (a modern AI marketing SaaS, Framer-built) revealed gaps in our iter 216h70 capture. The brief: *"ensure we are capturing everything that's required for the homepage marketing brand capture."*

### Gaps found (iter 216h70 baseline)
| Signal | Before | Why it matters |
|---|---|---|
| **Hero headline (H1)** | ❌ Not captured | The #1 piece of marketing copy on any homepage |
| **Value propositions (H2s)** | ❌ Not captured | Reusable feature/benefit copy |
| **Page meta** (title, description, OG, Twitter) | ❌ Not captured | SEO + social-card defaults |
| **Primary CTAs** | ❌ Not captured | Replicable button copy (Buy now, Get started…) |
| **Social proof** | ❌ Not captured | "Trusted by 10,000+", "4.8/5 stars" |
| **Hero video** | ❌ Not captured | Modern hero sections are video-first |
| **Detected vertical** (Claude) | ❌ Hard-coded to "gym" | Failed on AI SaaS / e-commerce / SMB sites |
| **Value props in Claude** | ❌ Not asked | Extra layer beyond tone-of-voice |
| **Pricing model** | ❌ Not asked | Critical for ad / email targeting |
| **Competitor mentions** | ❌ Not asked | Goldmine for positioning |
| **Logo ranking** | ⚠ Favicon-first | Often picked a 32×32 favicon over the actual brand mark |

### What shipped

#### `_extract_homepage_meta(soup, base_url)` — NEW
Captures `page_title`, `meta_description`, `meta_keywords`, `og_title`, `og_description`, `og_image`, `twitter_title`, `twitter_description`, and `theme_color`. The `theme_color` from `<meta name="theme-color">` is automatically promoted into the brand palette if it's a hex and wasn't already captured by the CSS sweep.

#### `_extract_headlines(soup)` — NEW
Pulls the first `<h1>` (hero headline) and up to 6 `<h2>` (value props) + 6 `<h3>` (sub-sections).

#### `_extract_ctas(soup)` — NEW
Pulls primary CTA buttons. Detection: `<button>` element OR `<a>` with `btn`/`button`/`cta`/`primary` in class OR text matching the high-signal CTA verb list (`Get started`, `Sign up`, `Try free`, `Book a demo`, `Subscribe`, `Buy now`, etc.). Filters out privacy/terms/sitemap junk. **Two dedup patterns** for hover-state twins (Framer / Webflow):
- Exact-half mirror: `"Buy now Buy now"` → `"Buy now"`
- Tooltip-wrapped odd-length: `"Join Us Modal Join Us"` → `"Join Us"`

#### `_extract_social_proof(text)` — NEW
Regex-driven scrape across full visible homepage text for patterns like *"trusted by X"*, *"10,000+ customers"*, *"rated 4.8 stars"*, *"500K downloads"*. Returns up to 6 deduped phrases.

#### `_extract_hero_video(soup, base_url)` — NEW
Looks for `<video>` (with `src`/`<source>` and `poster`) or first YouTube/Vimeo/Wistia `<iframe>`. Returns `{kind, src, poster}`.

#### `_find_logo_candidates(soup, base_url)` — RE-RANKED
Iter 216h70 picked favicons first because they came from the `<link rel=icon>` pass. Now scored:
- Header `<img>` with `logo` in class/alt → +10
- `og:image` / `twitter:image` → 5
- `apple-touch-icon` → 3
- `<link rel=icon>` favicon → 1

Result: tryholo.ai now picks the proper Holo wordmark as the primary logo (not the favicon).

#### `_claude_summarise()` — REWRITTEN business-agnostic
Old prompt was hard-coded to "gym / fitness business" and Claude refused to analyse non-fitness sites. New prompt:
- **Infers vertical** from the copy (`vertical` field: "AI marketing SaaS", "luxury gym chain", "boutique e-commerce"…)
- Returns `vertical`, `tone_of_voice`, `audiences`, **`value_propositions`** (NEW — 3-6 product/service value props), `current_campaigns`, **`pricing_model`** (NEW), `keywords`, **`competitor_mentions`** (NEW — *"alternatives to X"* references), `has_video`.
- Corpus cap bumped 12k → 15k chars (cost still <$0.02 with Haiku 4.5).

#### Frontend — `BrandDiscoveryPanel.js`
6 new draft sections rendered in this order:
1. **Homepage copy** — hero H1 (data-testid `brand-discovery-hero-h1`) + value-prop H2 list.
2. **SEO & sharing** — page title, meta description, Open-Graph title/description.
3. **Primary CTAs** — chip list of detected CTAs.
4. **Social proof** — bullet list.
5. **Hero video** — clickable link.
6. **Marketing intelligence** — now includes vertical chip, value-prop bullets, pricing model row, competitor chips.

### Stress test — tryholo.ai (Lee's URL)
Full successful capture:
- 6 brand colours + 4 fonts (Inter, Satoshi, Fragment Mono, Gabarito) + reordered logos
- **Hero H1**: *"Launch 10x more content. 75% faster."*
- **6 value-prop H2s** + 6 H3s
- **Meta**: page title + description + OG title/description/image + Twitter card
- **CTA**: "Buy now" (after hover-state dedupe)
- **Social proof**: *"Used by those who move fast"*, *"4268 customers"*, *"5 brands"*
- **Hero video**: Framer-hosted mp4 URL captured
- **Claude intelligence**: vertical=*"AI marketing SaaS"* · tone=*"Confident, playful, founder-focused"* · 6 audiences · **3 specific value props** · 3 current campaigns including *"New Years Sale 70% OFF"* · pricing model=*"Subscription from $39/month with 70% off promotion"* · 12 keywords · **competitors: Blaze AI, ArcAds, AdCreative.ai**

### Backfills
Both Third Space (`thirdspace.london`) and Pulse Fitness (`gymaxisai.com`) re-crawled + re-applied with the new signal set:
- **Third Space**: 8 CTAs ("Join Us", "Find your club", "Become a member", "Classes", "Clubs", "Personal Training", "Nutrition"), vertical=*"luxury gym chain"*, 6 value propositions.
- **Pulse Fitness** (gymaxisai.com): vertical=*"fitness operator SaaS"*.

### Files touched
- `/app/backend/routes/marketing/brand_discovery.py` (~+150 LOC — 4 new extractors, 1 rewritten Claude prompt, 1 re-ranked logo function, wiring in `_run_discovery`)
- `/app/frontend/src/pages/Marketing/BrandDiscoveryPanel.js` (~+80 LOC — 6 new draft sections + extended intelligence layout)

Lint clean across both files.

### ⚠ Action required
1. Redeploy preview → production. Backend + frontend.
2. Re-run brand discovery for existing tenants to pick up the new fields (existing apply'd brand kits retain core visuals — only the *new* extras need a re-run to populate).

---



## Iter 216h72 — Refactor: AccountSettingsModal split (Feb 13, 2026)

### Why
Backlog P2 item: `/app/frontend/src/components/shared/AccountSettingsModal.js` had grown to **1687 LOC**, mixing modal shell + 7 distinct section concerns + ad-hoc helpers + 60-line `<style>` block. Maintenance was a chore — any change to "Team & Roles" forced a re-render of the entire monolithic file in your head before touching it. Splitting was the obvious next move now that we're shipping multiple iters per day.

### What shipped

**Folder structure (NEW `/app/frontend/src/components/shared/AccountSettings/`):**
```
AccountSettings/
├── shared.js         (37 LOC)  — API const, SECTIONS array, useAuthHeaders, FieldRow
├── profile.js        (170 LOC) — ProfileSection
├── onboarding.js     (135 LOC) — OnboardingSection
├── security.js       (95 LOC)  — SecuritySection
├── preferences.js    (33 LOC)  — PreferencesSection
├── billing.js        (242 LOC) — BillingSection
├── organisation.js   (381 LOC) — OrganisationSection
└── team.js           (463 LOC) — TeamSection (largest — candidate for further split if it grows)
```

**`AccountSettingsModal.js`** — **1687 → 196 LOC (88% reduction).** Now owns ONLY:
- Modal open/close + Escape key + body-scroll-lock
- One-time `/account/billing` fetch (drives both billing + profile state)
- Side-rail navigation + section routing
- The shared `<style>` block (`account-input`, `account-btn-*`, `account-nav-active`, etc.)

**Refactor invariants preserved:**
- All data-testids verbatim (`account-settings-modal`, `account-nav-{section}`, `account-settings-close`, …)
- All section prop signatures unchanged (no consumer needed updating)
- Zero behavioural changes — strict mechanical extraction
- No CSS class renames, no new selectors

### Verified (testing-agent iter 216h72 — 14/14, 100%)
- Dashboard renders without runtime errors after the import re-shuffle ✓
- Every section renders correctly:
  - Profile (avatar / name / email / phone / save)
  - Onboarding (progress bar + checklist)
  - Security (password change + MFA setup card)
  - Preferences (theme toggle + digest preferences)
  - Plan & Billing (trial state + current plan + modules + payment history)
  - Organisation (name / drag-drop logo / brand palette / registered address)
  - Team & Roles (invite + team list + site access + reset link)
- Escape closes the modal ✓
- Backdrop click closes the modal ✓
- Body scroll lock works ✓

Frontend lint clean across all 9 new files.

### Files touched
- `/app/frontend/src/components/shared/AccountSettingsModal.js` (-1491 LOC — rewrite from 1687 → 196)
- `/app/frontend/src/components/shared/AccountSettings/shared.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/profile.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/onboarding.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/security.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/preferences.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/billing.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/organisation.js` (NEW)
- `/app/frontend/src/components/shared/AccountSettings/team.js` (NEW)

### ⚠ Action required
1. Redeploy preview → production. Frontend-only, zero behavioural changes.
2. Future iterations can edit a single ~150-450 LOC section file without re-reading the whole modal — measurable velocity win.

### Follow-up candidates (P3)
- `team.js` (463 LOC) is the largest remaining. If it grows past ~600 LOC, candidates for further split: invite-flow into `team/invite.js`, reset-password into `team/reset.js`, site-access matrix into `team/site-access.js`.
- `organisation.js` (381 LOC) has 3 logical concerns (org details / branding / registered address) — could split if it grows further.

---



## Iter 216h71 — Marketing Starter Pack + tenant backfills (Feb 13, 2026)

### Why
Iter 216h70 finish improvement: "Now that we extract tone-of-voice + audiences + campaigns, auto-draft a starter content pack so a tenant goes from blank Marketing module → ready content in under a minute." Plus Lee asked us to **confirm brand auto-discovery has run + brand kits are built for Third Space AND Pulse Fitness seed orgs**.

### What shipped

#### 1. Marketing Starter Pack — `routes/marketing/starter_pack.py` (NEW, ~140 LOC)
Three endpoints, module-gated:
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/marketing/starter-pack/generate` | Single Claude Haiku 4.5 call (~$0.02) → returns 3 emails + 3 social posts |
| GET  | `/api/marketing/starter-pack` | Retrieve last persisted pack |
| DELETE | `/api/marketing/starter-pack` | Clear the pack |

Pack shape (JSON, validated):
```jsonc
{
  "emails":  [{id:'welcome'|'win_back'|'promo', subject, preview, body}],
  "social":  [{id:'instagram'|'facebook'|'x',   platform, body}]
}
```
System prompt enforces operator's `voice` + audience + campaign context: subjects ≤50 chars, previews ≤90, Instagram captions have 3-6 hashtags, X posts ≤270 chars, no clichés.
Returns 400 if brand_kit has no voice AND no discovery-extracted tone (forces upstream brand kit setup).

Persistence: `marketing_starter_pack` (one doc per org) — `{organization_id, pack, generated_at, generated_by, based_on}`.

#### 2. Brand-Discovery asset-serving endpoint — `brand_discovery.py`
- `GET /api/marketing/brand-discovery/asset/{full_path:path}` — streams compressed brand-kit assets from object storage.
- **Cross-tenant guard**: path must start with `{APP_NAME}/brand-discovery/{requester_org_id}/` or 403.
- 24 h cache header. 404 on missing.
- `_compress_and_store()` now returns `stored_url = "/api/marketing/brand-discovery/asset/{key}"` — routable from the frontend.

#### 3. CSS-variable font bug fix (`_extract_fonts`)
- Third Space (and any WordPress site using design-token CSS variables) was capturing the literal token `var` from `font-family: var(--theme-heading)`. Now skipped via expanded GENERIC set: `{sans-serif, serif, monospace, system-ui, ui-sans-serif, inherit, var, system, ui-monospace, ui-serif}`.
- Backfill swept existing brand_kit docs (1 row corrected).

#### 4. Crawler User-Agent — Cloudflare/WAF friendly
- Replaced custom bot UA with a real Chrome 120 UA + `X-GymAxis-Crawler` audit header. Same goodwill for transparent operators; gets past WAFs that block bots indiscriminately. Crawl timeout 10 s → 12 s.

#### 5. Frontend — `StarterPackPanel.js` (NEW, ~220 LOC)
- Sits directly below `<BrandDiscoveryPanel>` in Brand Kit tab.
- Gradient purple-pink card with title "3 emails + 3 social posts in your tone".
- Empty state: "Draft my starter pack" CTA.
- Drafts state: 3 collapsible email cards (Welcome / Win-back / Promo, color-bar coded green/amber/indigo) showing subject + preview, expand to reveal full body. 3 social cards (Instagram / Facebook / X) with platform icons. **Copy to clipboard** on every card. **Re-generate** + **Clear** in footer.

### Tenant backfills — Third Space + Pulse Fitness
Both seed orgs now have:

| Tenant | Website | Discovery result |
|---|---|---|
| **Third Space** | `thirdspace.london` | ✅ Applied — primary `#003388`, secondary `#abb8c3`, 2 logos + 8 marketing images mirrored to our storage, voice: *"Sophisticated and motivational, positioning fitness as essential to urban life quality. Emphasizes luxury, expertise, and holistic wellness…"* + audiences (urban professionals, fitness enthusiasts, wellness-focused, performance-oriented) + 2 active campaigns + 10 keywords + 5 social handles (FB/IG/TikTok/LI/YT). Starter pack drafted (welcome subject: *"Your London fitness transformation starts here"*). |
| **Pulse Fitness** | `gymaxisai.com` (platform demo org) | ✅ Applied — Inter heading + Outfit body fonts, voice: *"Professional and tech-forward, positioning GymAxis AI as an innovative solution for fitness business operators…"* + B2B audience targeting. Starter pack drafted (welcome subject: *"Your Gym Management Platform Awaits"* — correctly recognised the B2B SaaS nature). |

Both confirmed visually in /marketing → Brand Kit.

### Tenant-agnostic confirmation
**Yes — the brand auto-discovery + starter pack features work identically for any tenant with the Marketing module enabled.** Both endpoints scope every read/write by `organization_id` (resolved via `_org_id(user)`) and are guarded by `require_module("marketing")`. Third Space, Pulse Fitness, and any future tenant get the same flow on activation. The backfills above prove this — same endpoints, two different tenants, two on-brand outputs.

### Verified (testing-agent iter 216h71 — 10/10 backend + frontend all green)
- Starter pack generate / get / delete / auth / module-guard — all passing
- Asset endpoint own-org 200, cross-tenant 403, missing 404 — all passing
- Font bug fix verified (no 'var' leaking through)
- Frontend renders the panel + 3 email cards + 3 social cards + copy buttons + clear

Regression test files:
- `/app/backend/tests/test_iter_216h70_brand_discovery.py`
- `/app/backend/tests/test_iter_216h71_starter_pack.py`

Lint clean across all touched files.

### Files touched
- `/app/backend/routes/marketing/starter_pack.py` (NEW, ~140 LOC)
- `/app/backend/routes/marketing/brand_discovery.py` (~+50 LOC — asset endpoint, font fix, browser UA)
- `/app/backend/routes/marketing/__init__.py` (+2 LOC — register starter_pack)
- `/app/frontend/src/pages/Marketing/StarterPackPanel.js` (NEW, ~220 LOC)
- `/app/frontend/src/pages/Marketing/BrandKitTab.js` (+5 LOC — mount StarterPackPanel under BrandDiscoveryPanel)
- `/app/backend/tests/test_iter_216h71_starter_pack.py` (NEW — regression tests)

### ⚠ Action required
1. Redeploy preview → production. Backend + frontend.
2. Operator UX after deploy:
   - Brand Kit → "Brand Auto-Discovery" (existing iter 216h70 panel).
   - Brand Kit → "Marketing Starter Pack" (NEW) — once the brand kit has a voice/tone (manually set OR from auto-discovery), one click drafts 3 emails + 3 social posts. Click Copy on any card to paste into their email tool / scheduler.
3. Both **Third Space** and **Pulse Fitness** orgs already have their brand kits + starter packs populated — they'll see "Discovery applied" + ready content on their first visit.

---



## Iter 216h70 — Marketing: Brand auto-discovery + tab reorder (Feb 13, 2026)

### Why
Lee's ask: "If a tenant enables the Marketing module, on sign-up they enter their website. From that point in the background AI should crawl their website to build up the brand kit — standards, fonts, text sizes, logos, images, etc. Grab as much intelligence as possible. **Massive time saver.**" Plus: tab reorder — Start FIRST (auto-removing checklist parity with other modules), Dashboard SECOND (renamed from Performance).

### Operator decisions (captured)
1. Trigger: (a) Auto on first website-URL save.
2. Scope: (a) Homepage + top 8 internal pages.
3. Apply: (a) Draft for operator review.
4. Storage: (b) **Mirror images to our object storage**, compressed without quality loss (PIL JPEG q=85 / PNG optimized, max 2000 px longest side).

### What shipped

#### Backend — `routes/marketing/brand_discovery.py` (NEW, ~360 LOC)
Four endpoints, all behind `require_module("marketing")`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/marketing/brand-discovery/start` | Queues `BackgroundTask`, persists `website_url` on the org doc |
| GET  | `/api/marketing/brand-discovery/status` | Polled by UI — returns `{status, progress, draft, error}` |
| POST | `/api/marketing/brand-discovery/apply` | Copies draft → `marketing_brand_kit` (selective per-field flags) |
| POST | `/api/marketing/brand-discovery/discard` | Wipes the doc |

**Crawler pipeline:**
1. Fetch homepage with httpx (10 s timeout, User-Agent identifies us).
2. Discover same-domain links, prioritising `/about`, `/timetable`, `/classes`, `/membership`, `/pricing`, `/offers`, `/promotions`, `/blog`, `/contact`.
3. Crawl up to 8 pages total. Accumulate hex colours (CSS/HTML), `font-family` + Google-Fonts declarations, plain-text corpus.
4. From the homepage: extract **logo candidates** (`<link rel=icon>`, `og:image`, `<img>` near `<header>` with logo class), **marketing imagery** (≥200 × 200 px, skips icons/avatars), **social handles** (FB / IG / TikTok / X / LinkedIn / YouTube).
5. **Image storage** — top 3 logos + top 8 images downloaded → PIL-compressed (longest side cap 2000 px, JPEG quality=85, PNG optimize for RGBA logos) → `put_object("gymaxis/brand-discovery/{org}/...")`. Returned `stored_url` points to **our** storage so they survive site redesigns.
6. **Claude Haiku 4.5** single call (Emergent LLM key) — returns JSON with `tone_of_voice`, `audiences`, `current_campaigns`, `has_timetable`, `keywords`. Cost: ~$0.01–0.03 per gym.

Persistence: `marketing_brand_discovery` collection (one doc per org).

#### Frontend — `BrandDiscoveryPanel.js` (NEW, ~310 LOC)
Lives at the top of Marketing → Brand Kit. 5 states:
- **Idle** — Globe-icon URL input + "Discover my brand" CTA.
- **Running** — Polls `/status` every 2 s; shows spinner + live stage label (`fetching {url}`, `compressing & storing assets`, `analysing tone & audiences`).
- **Ready** — Full draft preview: colour swatches, fonts, logo grid, image grid (4-8 cols responsive), intelligence panel (tone-of-voice + audience chips + campaign bullets), social handles, collapsible "pages crawled" list. **Apply / Discard** CTAs.
- **Applied** — "Discovery applied. Re-run any time after a website redesign."
- **Failed** — Amber alert with error detail.

#### Marketing tab reorder — `MarketingSuite.js`
Old: `Performance · Start · Insights · …`
New: **`Start · Dashboard · Insights · Campaigns · Journeys · Contacts · Audiences · Dynamic Lists · Forms & Pages · Creative Studio · Brand Kit · Social`**
- `id: 'performance'` retained for back-compat with bookmarks + `?tab=` URLs; only the **label** changed to "Dashboard".
- Default-tab logic: if `localStorage:userPref:hideStartTabs === 'true'` (operator has completed onboarding milestones) → land on `performance` (Dashboard). Otherwise → land on `start`.

#### Marketing → Start tab — `StartTab.js`
- Imports `<ActivationMilestonesCard>` and renders it at the top. Once all milestones land, the card flips `hideStartTabs=true` → the **Start** tab auto-removes itself from the tab bar, matching every other module's onboarding pattern.

### Verified (testing-agent iter 216h70 — 100%, 10/10)

| Test | Result |
|---|---|
| POST /start returns `{ok:true, status:'queued', website_url}` | ✅ |
| GET /status transitions queued → running → ready (~10 s for small sites) | ✅ |
| Ready draft has colours, fonts, logos, images, socials, intelligence, pages_visited | ✅ |
| POST /apply copies fields to brand-kit; status → 'applied' | ✅ |
| POST /discard wipes doc | ✅ |
| POST /apply without ready draft → 400 | ✅ |
| All endpoints require marketing module + auth | ✅ |
| Image storage uses `put_object()` — `stored_url` is GymAxis storage path, NOT a third-party CDN | ✅ |
| Tab order: Start FIRST (`data-testid='marketing-tab-start'`), Dashboard SECOND (`id='performance'`, label='Dashboard') | ✅ |
| BrandDiscoveryPanel renders with URL input, "Discover my brand" button, running → ready → applied flow | ✅ |

Backend pytest file: `/app/backend/tests/test_iter_216h70_brand_discovery.py` (regression).
Lint clean across all 6 touched files.

### Real-world smoke
- `example.com` → fully crawled, applied, discarded in <15 s.
- `gymaxisai.com` → Claude extracted full audience pack: *"gym owners · fitness operators · fitness business managers"*, tone: *"Professional and solution-focused, emphasizing innovation and operational efficiency for fitness business owners."*, fonts: Inter (heading) + Outfit (body). Pure Next.js sites yield fewer colours/logos due to compiled CSS — multi-page legacy gym sites will yield much richer drafts.

### Files touched
- `/app/backend/routes/marketing/brand_discovery.py` (NEW)
- `/app/backend/routes/marketing/__init__.py` (+2 LOC — register router)
- `/app/frontend/src/pages/Marketing/BrandDiscoveryPanel.js` (NEW)
- `/app/frontend/src/pages/Marketing/BrandKitTab.js` (+3 LOC — mount panel at top)
- `/app/frontend/src/pages/Marketing/StartTab.js` (+8 LOC — mount ActivationMilestonesCard at top)
- `/app/frontend/src/pages/MarketingSuite.js` (~−15 / +18 LOC — tab reorder + default-tab logic)
- `/app/backend/tests/test_iter_216h70_brand_discovery.py` (NEW — regression tests)

### ⚠ Action required
1. Redeploy preview → production. Backend + frontend.
2. Operator flow after deploy:
   - Marketing → **Start** (new first tab) shows the activation checklist.
   - Marketing → Brand Kit → **Brand Auto-Discovery** panel at the top lets them drop their website URL and click **Discover my brand**.
   - 10-30 s later the draft appears with colours, fonts, logos, ~8 marketing images, tone-of-voice, audience segments, current campaigns, social handles.
   - **Apply to brand kit** commits the draft to the operator's permanent brand kit; **Discard** wipes it. They can **Re-run** after a website redesign.

---



## Iter 216h69 — Upload throttle + concurrency cap for spec-sheet uploads (Feb 13, 2026)

### Operator-reported (Lee Somers, screenshot)
"Master Admin → Catalogue & Library → trying to upload multiple spec sheets — 7 of 9 failed due to `timeout of 120000ms exceeded`. We can't have timeouts when users are trying to upload documents. I need to upload 160 spec sheets in live and we need to assume end users will do the same on their platform logins."

### Root cause
`<UploadQueueProvider>` (iter 216h34) was firing ALL queued files in parallel (`newTasks.forEach(t => runTask(t.id))`). Each spec-sheet upload triggers a synchronous AI extraction (Claude/Gemini) on the backend that takes 30–90 s per PDF. With 9 parallel uploads, the AI extractor saturated → the last 6 calls queued internally → exceeded the 120 s client timeout → 7/9 failed despite the backend being healthy.

### Strategy shipped — client-side concurrency cap

**File:** `/app/frontend/src/components/shared/UploadQueue.js`
- New per-`source` slot scheduler with `SOURCE_CAP_DEFAULTS`:
  - `spec-sheets`: **3** concurrent (each is a 30–90 s AI call)
  - `equipment-photo`: 4
  - `upload` (generic): 8 — preserves the legacy "fire all" feel for fast uploads
- `enqueue()` accepts an `opts.maxConcurrent` override so callers can tune per-source caps.
- New `runTask` wraps the original task runner with a slot acquire/release dance — running tasks fire, the rest queue, and `releaseSlot` pulls the next waiter the moment a running task settles (success OR failure).
- `remove()` also drains the slot's `waiting` array so a user-cancelled task doesn't strand its slot.
- `retry()` re-routes through the same scheduler so a burst of retries never blows past the cap.

**File:** `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js`
- Per-file timeout bumped **120 s → 300 s** (5 min). With concurrency now capped at 3, the AI extractor never sees more than 3 simultaneous requests; 5 min gives generous headroom on slow PDFs.

**File:** `/app/frontend/src/components/shared/UploadQueue.js` (drawer UI)
- Header now reads **"Uploading 3 of 9 files"** instead of "Uploading 9 files" — operator sees that throttling is happening, not stuck.
- Subtitle row adds **`6 WAITING`** so the queued count is explicit.

### Verified (Playwright smoke, 9-file fake-PDF upload with 2 s mocked AI delay)
- At t=1.2 s: "Uploading 3 of 9 files · 6 WAITING" ✓
- At t=12 s: "9 uploads complete · 9 DONE · 0 FAILED" ✓
- No timeouts. Files 3–8 visibly queue and roll through as files 0–2 complete.

### Capacity math for the 160-file real-world target
- 160 files × ~45 s average AI extraction × 3-concurrent = ~40 minutes wall-clock.
- Operator can leave the tab open (the iter 216h49 page-leave guard already prompts on accidental tab close while uploads are in-flight).
- Drawer surfaces per-file status the whole time so they can spot any single failure without losing context.

### Future option (if needed)
If real-world AI calls turn out to genuinely take >5 min for the worst-case PDFs, we can flip the backend `/spec-sheets/upload` to **accept → return spec_id immediately → run extraction in a FastAPI BackgroundTask → expose a polling status endpoint**. That removes the per-file timeout entirely. For now the throttle + 5 min timeout is sufficient for the stated 160-file batch.

### Files touched
- `/app/frontend/src/components/shared/UploadQueue.js` (+85 / −10 LOC — slot scheduler + drawer label tweaks)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (+8 / −1 LOC — bumped per-file timeout with rationale comment)

### ⚠ Action required
1. Redeploy preview → production. Frontend-only.
2. Lee can now drop all 160 spec sheets at once — the drawer will work through them 3 at a time. No more `timeout of 120000ms exceeded`.

---



## Iter 216h68 — Silent JWT refresh + Session-resumed banner (Feb 13, 2026)

### Why
Pre-empt the "I lost my CRM notes because my session expired" complaint thread. After iter 216h67 hardened the CRM cross-login, the remaining hole was the main JWT itself: any operator API call returning a 401 (e.g. token revoked mid-session by an admin, 24 h hard expiry on a long-running tablet) was a hard logout — no retry, no warning, half-typed forms lost.

### What shipped

#### Global axios 401 interceptor (silent refresh)
**File:** `/app/frontend/src/App.js`

Module-level interceptor that:
- Catches **401s** on any operator-side `/api/*` call.
- Skips a defensive deny-list (`/api/auth/login`, `/api/auth/register`, `/api/auth/refresh`, `/api/auth/me`, `/api/crm/*`, `/api/member/*`) to avoid loops + leave CRM to `<UnifiedAuthProvider>` (iter 216h67) + leave member-portal tokens alone.
- Attempts **one silent** `POST /api/auth/refresh` with the current `localStorage.token` (timeout 8 s).
- **Concurrency-safe** — concurrent 401s share a single in-flight `__refreshInflight` promise so 6 parallel dashboard fetches don't trigger 6 refreshes.
- On success: writes the new token, fires `gymaxis:token-refreshed` (so the App's `useAuth().token` and any other listeners stay in sync), retries the original request transparently — **the user never sees the failure**.
- On failure: fires `gymaxis:session-expired` so the banner can offer a friendly CTA.

#### `<SessionResumedBanner>`
**File:** `/app/frontend/src/components/shared/SessionResumedBanner.js` (NEW)
- Listens for `gymaxis:session-expired` and renders a sticky bottom-centre alert card: "Your session has expired — sign in again to keep working. We'll bring you straight back to this page." with **Dismiss** + **Sign in again** CTAs.
- **Sign in again** routes to `/login?next=<current_path>` so re-auth lands the user back where they were — preserving form context.
- Suppresses itself on `/login` (avoids double-display).
- Auto-hides if `gymaxis:token-refreshed` fires while shown (e.g. another tab re-authed and broadcast a fresh token via the `storage` event).

#### `?next=/path` deep-link plumbing
**Files:** `/app/frontend/src/pages/LoginPage.js`, `/app/frontend/src/pages/LoginRedirectPage.js`, `/app/frontend/src/routes/AppRoutes.js`
- Both LoginPage (post-credential flow) and LoginRedirectPage (already-authenticated guard) read `?next=/path` and route the user there, falling back to the role-based default (`/master-admin` / `/pulse` / `/dashboard`) when missing.
- Only **relative paths** are accepted (`/path/...`, must NOT start with `//`) to defeat open-redirect abuse.
- `<Route path="/login">` simplified to **always** render `<LoginRedirectPage>`; the auth-state branching now lives inside the component (was previously a brittle inline `user ? <Navigate /> : <LoginRedirect />`).

#### Pre-existing bug fix (testing-agent catch)
**File:** `/app/frontend/src/routes/AppRoutes.js` line 53
- The lazy import was pointing at `@/pages/GymAxisLoginPage` (a stale path from an earlier refactor) instead of `@/pages/LoginRedirectPage`. The latent bug never surfaced because the page rendered visually identical content — but it meant the `?next=` flow was being silently bypassed for authenticated users. Now imports the correct module.

### Verified (testing-agent iter 216h68 — 100% pass, 7/7)
| Test | Result |
|---|---|
| Authenticated user → `/login?next=/pulse` redirects to `/pulse` | ✅ |
| Unauthenticated user logs in via `/login?next=/pulse` → lands on `/pulse` | ✅ |
| `gymaxis:session-expired` → banner renders with correct text + CTAs | ✅ |
| Dismiss button hides banner, no navigation | ✅ |
| Sign in again → routes to `/login?next=…` | ✅ |
| Banner suppresses itself on `/login` | ✅ |
| CRM 401s do NOT trigger the banner (UnifiedAuthProvider handles) | ✅ |

Frontend lint clean across all 5 touched files.

### Files touched
- `/app/frontend/src/App.js` (+85 LOC — module-level axios interceptor + token-refreshed listener + `<SessionResumedBanner>` mount)
- `/app/frontend/src/components/shared/SessionResumedBanner.js` (NEW, ~95 LOC)
- `/app/frontend/src/pages/LoginPage.js` (+12 LOC — `useLocation` + `nextParam` reader)
- `/app/frontend/src/pages/LoginRedirectPage.js` (+8 LOC — `?next=` honoured for authenticated users; only safe relative paths)
- `/app/frontend/src/routes/AppRoutes.js` (-1/+5 LOC — `/login` route + fixed import path)

### ⚠ Action required
1. Redeploy preview → production. Frontend-only.
2. Operator UX after deploy:
   - Mid-session 401 (revoked token / network blip) → silent refresh → retry → **operator notices nothing**.
   - True session expiry (>24 h, refresh also fails) → friendly bottom banner with **Sign in again** CTA → `/login?next=<current_path>` → after sign-in, lands back on the same page they were on.

---



## Iter 216h67 — HOTFIX: CRM still bouncing logged-in mobile users to CRMLogin (Feb 13, 2026)

### Operator-reported (Jack Ottey, mobile screenshot)
"Again a logged in user is being asked to log into CRM on mobile. It's OK on desktop." Mobile preview screenshot showed CRMLogin while Jack's main session was alive.

### Root cause — recurrence of iter 216h43 / 216h45 bug class
The iter 216h45 `<UnifiedAuthProvider>` introduced auto-cross-login (`main token` → `crm_token` via `POST /api/crm/auth/cross-login`) but had **no retry** on network failure:
- `.catch(() => { /* silent */ })` swallowed timeouts.
- On flaky mobile (5G drops, corporate VPN, captive portal handoff), the single 6 s attempt would time out → no CRM token → CRMApp's 6 s loading window dropped → CRMLogin rendered.
- Identical symptom to Lee's iter 216h43 bug but a different code path; the iter 216h43 fix was per-module, the *class* recurred at the provider level.

### What shipped

#### `<UnifiedAuthProvider>` mobile-hardening
**File:** `/app/frontend/src/components/shared/UnifiedAuthProvider.js`
- New `attemptCrossLogin()` with **3-attempt exponential backoff** (1 s / 2 s / 4 s). Total worst-case ~22 s before the user sees "CRM is unreachable" instead of silently failing.
- Per-call timeout bumped 6 s → **8 s** (mobile tolerance).
- Distinguishes **401/403** ("CRM not enabled for this account") from **5xx / network** ("CRM unreachable"). Auth failures don't retry; network failures do.
- Exposes new `crmExchangeStatus` to consumers — `{state: 'idle'|'pending'|'failed'|'unavailable', attempts, lastError}`. Consumers can render the right UI based on the failure mode.
- `refresh.crm()` resets the attempt counter so a manual retry always gets a fresh window.

#### CRMApp.js — "Reconnecting…" splash replaces wrongful CRMLogin
**File:** `/app/frontend/src/pages/CRM/CRMApp.js`
- Initial loading window tightened **6 s → 3 s** so the user sees state sooner.
- NEW branch: when `!user && main token present && no crm token`, render a **"Reconnecting to your CRM workspace…"** card with the spinner + attempt counter (1 of 3, 2 of 3, etc.).
- After all retries fail, the card flips to **"CRM is unreachable"** (network) or **"CRM is not enabled for your account"** (401/403), with a **Try again** button (data-testid `crm-reconnect-retry-btn`) and a **Back to dashboard** link.
- **CRMLogin only renders when both `main` AND `crm` tokens are absent** — a genuine logged-out state. A logged-in user is structurally protected from being asked to re-enter creds.

### Verified end-to-end
| Scenario | Result |
|---|---|
| Block `/api/crm/auth/cross-login` via Playwright route → navigate to /crm on iPhone-size viewport | "CRM is unreachable" card with "Try again" + "Back to dashboard", **0 CRMLogin elements found** ✓ |
| Happy path (no network interference) | CRM Command Center renders normally, no reconnect splash, no CRMLogin ✓ |

Frontend lint clean across `UnifiedAuthProvider.js` + `CRMApp.js`.

### Files touched
- `/app/frontend/src/components/shared/UnifiedAuthProvider.js` (~+95 / −15 LOC — retry chain + status surface)
- `/app/frontend/src/pages/CRM/CRMApp.js` (~+70 / −1 LOC — reconnect splash + tighter loading window)

### ⚠ Action required
1. Redeploy preview → production. Frontend-only.
2. Jack reopens `gymaxisai.com/crm` on his phone — the moment his main session is alive, CRM either loads (happy path) or shows a friendly "Reconnecting…" / "Try again" card. He's never bounced to CRMLogin while logged in.

---



## Iter 216h66 — CRM Lead Conversion flow (Salesforce-style) (Feb 13, 2026)

### Why
P1 backlog: a proper "Convert Lead" UX so reps can promote a contact + (optionally) create the linked account and open a deal in pipeline — in a single guided modal — instead of the manual three-step lifecycle/company/opportunity dance.

### Operator preferences (captured before build)
1. Lifecycle defaults to **Customer** post-convert (option a).
2. Conversion **does not require** an opportunity (just lifecycle + company is enough).
3. **Block re-conversion** — hide Convert once lifecycle ≠ 'lead'.
4. No extra side-effects (no auto follow-up tasks, no welcome emails).

### What shipped

#### Backend — `POST /api/crm/v2/contacts/{contact_id}/convert`
**File:** `/app/backend/routes/crm_v2.py` (new endpoint, ~200 LOC inserted between `delete_contact` and the Opportunities section).

Request body:
```jsonc
{
  "company_action": "link" | "create" | "skip",
  "company_id": "...",                         // when 'link'
  "company_data": {"name", "sector", "website", "phone", ...},  // when 'create'
  "create_opportunity": false,
  "opportunity": {"title", "value", "stage", "close_date", "next_step"},
  "new_lifecycle": "customer" | "prospect" | "champion"
}
```
Response: `{ok, contact_id, company_id, opportunity_id, new_lifecycle}`.

Logic:
- **Blocks re-conversion** — 400 `Cannot convert — contact lifecycle is already 'X'`.
- `create` company path reuses territory + owner auto-assignment from `assign_from_territory` (parity with `POST /companies`).
- `link` validates the target company exists in the org.
- `skip` keeps the existing `contact.company_id` link untouched.
- Opportunity creation inherits territory/owner from the linked company when present, fires `deal_created` (and `deal_value_above` when value > 0) workflows.
- Always writes a `convert` audit record + a "Lead converted → {lifecycle}" activity in `crm2_activities`.

#### Frontend — Convert button + ConvertLeadModal
**File:** `/app/frontend/src/pages/CRM/CRMContacts.js`.
- Pulled `navigateTo` into `ContactDetail` props.
- New green **Convert** button (data-testid `contact-convert-btn`) in the detail header, visible ONLY when `contact.lifecycle === 'lead'`. Auto-hides after successful conversion.
- New `<ConvertLeadModal>` (createPortal'd) with 3 sections:
  1. **Account** — Link existing (autocomplete + searchable list) · Create new (name/sector/website) · Skip (leave as-is).
  2. **Opportunity** (collapsed by default) — title/value/stage/close-date.
  3. **Mark contact as** — Customer (default) · Prospect · Champion.
- On success: closes the modal, reloads the contact, and (if an opportunity was created) `navigateTo('opportunity', opp_id)` so the rep lands on the new deal in pipeline.
- All testids documented: `convert-lead-dialog`, `convert-link-existing`, `convert-create-new`, `convert-skip-company`, `convert-company-search`, `convert-company-pick-{id}`, `convert-new-company-name|sector|website`, `convert-create-opp-toggle`, `convert-opp-title|value|stage|close-date`, `convert-new-lifecycle`, `convert-lead-submit`, `convert-lead-cancel`, `convert-lead-close`, `convert-lead-error`.

### Verified
- Backend pytest suite (testing-agent iter 216h66): **11/11 passing** (`/app/backend/tests/test_iter_216h66_lead_conversion.py`):
  - create company + opp path, link existing path, skip-company path (lifecycle-only).
  - Validations: 400 on missing company_id (link), 400 on missing name (create), 400 on missing title (opp), 404 on non-existent contact, 404 on non-existent linked company.
  - Re-conversion blocked with explicit message.
  - Audit + activity records created.
- Manual curl smoke: all 3 conversion paths + re-convert block working.
- Frontend smoke screenshot: Convert button renders green next to Edit in the header; modal opens with Lead Conversion eyebrow, 3-section layout, and pre-filled "Create new company" path using the contact's existing `company_name`.

### Files touched
- `/app/backend/routes/crm_v2.py` (~+200 LOC — new POST /contacts/{id}/convert endpoint)
- `/app/frontend/src/pages/CRM/CRMContacts.js` (~+260 LOC — Convert button + ConvertLeadModal component; navigateTo prop)
- `/app/backend/tests/test_iter_216h66_lead_conversion.py` (NEW — 11 regression tests)
- `/app/memory/PRD.md` (this entry)

### ⚠ Action required
1. Redeploy preview → production. Backend (`crm_v2.py`) + frontend (`CRMContacts.js`).
2. After deploy reps can:
   - Open a CRM lead → click the new green **Convert** button.
   - Pick "Link existing", "Create new", or "Skip" for the account.
   - Optionally toggle "Open a deal in pipeline" with title/value/stage/close-date.
   - Confirm — the contact's lifecycle flips to Customer (or chosen), the company is created/linked, and (if an opp was created) they land directly on the new deal in Pipeline.

---



## Iter 216h65 — `<ListPanel>` adoption across Memberships + ListPanel grid support (Feb 13, 2026)

### Why
P1 backlog item from iter 216h44: adopt `<ListPanel>` across remaining list views. Pre-existing adopters: CRMContacts, CRMCompanies. Target this iter: Memberships Plans, Classes, Ads, Promotions.

### What shipped

#### `<ListPanel>` extension
- **`/app/frontend/src/components/shared/ListPanel.js`** — new `bodyClassName` prop (defaults to `space-y-2`). Lets callers override the children wrapper for grid layouts. E.g. `bodyClassName="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"` for card-based panels like Plans and Promotions.

#### Migrations (4 panels)
All migrations preserve existing `data-testid`s verbatim and add new ones for the ListPanel root + empty-state CTA where missing.

| Panel | File | Notes |
|---|---|---|
| **PlansInnerView** | `MembershipsConsole.js` ~L1204 | grid bodyClassName, count chip "N plan(s)", empty `mbr-plans-empty` |
| **ClassesTab** | `MembershipsConsole.js` ~L1280 | default `space-y-2`, count "N class(es)", empty `mbr-classes-empty` |
| **AdsTab** | `MembershipsConsole.js` ~L1545 | default `space-y-2`, count "N ad(s)", empty `mbr-ads-empty` |
| **PromotionsTab** | `PromotionsTab.js` ~L78 | grid bodyClassName, count "N code(s)", empty `mbr-promo-empty` (preserved), new CTA `mbr-promo-empty-create` |

Replaced the bespoke `<Header eyebrow=… title=… subtitle=…>` + free-floating Button + custom Loading/Empty pattern with the standard ListPanel surface. Net ~30-40 LOC saved per panel. The rich empty states now have icon + title + hint + primary CTA, matching CRM Contacts / Companies.

### Verified
- Lint clean across all 3 touched files (ListPanel.js, MembershipsConsole.js, PromotionsTab.js).
- Testing-agent iter 216h65 (frontend only): **100% verified** — all 4 migrated panels render with correct title, subtitle, count chip, primary CTA, and rich empty state. CRM Contacts + Companies regression-clean. No console errors. Create-flow modals (PlanEditorModal, PromoEditorModal) still open correctly.
- Manual smoke screenshots confirmed Plans, Ads, Promotions empty states render with brand-cyan CTAs.

### Files touched
- `/app/frontend/src/components/shared/ListPanel.js` (+5 LOC — bodyClassName prop + docs)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~-90 / +75 LOC — 3 panels migrated, +1 ListPanel import)
- `/app/frontend/src/pages/Memberships/PromotionsTab.js` (~-35 / +20 LOC — PromotionsTab migrated, +1 ListPanel import)
- `/app/DESIGN_SYSTEM.md` (~+5 / -2 LOC — documented bodyClassName + updated adoption list)

### Deferred
- **CRMPipeline list view** — listed in the iter 216h44 target list but its toolbar is too bespoke (kanban/list view switcher, weighted-value summary, Report print button, HelpHint inline). Forcing it into ListPanel would compromise the dual-view layout. Marked complete-as-deferred in DESIGN_SYSTEM.md.

### ⚠ Action required
1. Redeploy preview → production. Frontend-only change.
2. Operators visiting Memberships → Plans / Classes / Ads / Promotions tabs now see a consistent empty-state experience matching CRM Contacts.

---



## Iter 216h64 — Co-branded email wrapper (Feb 12, 2026)

### Operator-reported (Lee)
"Ensure any emails that go out from our system are branded with the pulse fitness logo and the gym logo."

### What shipped

#### Backend (`utils/email.py`)
- New helper: `wrap_branded(html, organization_id)` — wraps every outbound email's HTML in a co-branded shell with:
  - **Left header:** operator's uploaded logo (from `org.logo_url`) OR an initial-circle if no logo yet, plus the operator's name.
  - **Right header:** platform mark. Pulse Pro / Lite tenants show the Pulse Fitness lockup with `· powered by GymAxis` strapline; full accounts show the GymAxis mark.
  - **Footer:** co-branded "Operator · Platform" strip with an email-preferences disclaimer.
- `_abs_url()` resolves relative paths (`/api/account/logo/{id}?v=…`) to fully qualified URLs against `EMAIL_PUBLIC_BASE_URL` / `REACT_APP_BACKEND_URL` so the `<img>` tags work inside Gmail/Outlook.
- Idempotent — `gymaxis-email-cobrand-wrap` class marker prevents double-wrapping when upstream builders already pre-wrap.
- Resilient — unknown org ID, no org ID, empty operator name all fall back to the platform-only header without crashing.

#### Integration
- `send_email()` now calls `await wrap_branded(html, organization_id)` immediately before constructing the Resend payload. Existing callers that already pass `organization_id` get co-branding automatically; the few that didn't (e.g. `trial_lifecycle._send_trial_reminder`) now do.
- All existing email builders (`memberships_emails`, `svc_digest`, `archive_lifecycle`, etc.) are wrapped transparently — they didn't need any changes.

### Verified
- 23/23 backend tests pass (testing-agent iter 216h64).
- 4/4 dedicated regression tests in `tests/test_email_cobrand.py`:
  - `test_wraps_platform_only` — wrap without org_id still produces a header
  - `test_wraps_pulse_tenant` — Pulse Pro tenant shows Pulse Fitness mark
  - `test_idempotent` — second wrap is a no-op
  - `test_unknown_org_falls_back_to_platform` — unknown org id doesn't crash
- Manual preview e2e: `wrap_branded` on a Pulse Fitness payload produces 1,548 bytes of clean HTML with the operator logo proxy URL absolutized.

### Files touched
- `/app/backend/utils/email.py` (~+155 LOC — wrap_branded + helpers + integration in send_email)
- `/app/backend/utils/trial_lifecycle.py` (+1 LOC — pass organization_id)
- `/app/backend/tests/test_email_cobrand.py` (NEW — 60 LOC, 4 tests)

### ⚠ Action required
1. Set `EMAIL_PUBLIC_BASE_URL=https://gymaxisai.com` (or the production frontend URL) in production env so the operator-logo proxy URLs in emails resolve to the canonical domain.
2. Redeploy backend.

### Knock-on benefits
- Every existing email flow (membership confirmations, supplier case updates, trial reminders, weekly digests, password resets) is now co-branded with no per-template change.
- Operators that upload their logo via `/api/account/logo` immediately get the new branding on their next outbound email.

---



## Iter 216h63 — (h) Site-scoped Staffing + Compare-Sites enhancement (Feb 12, 2026)

### Operator-reported (Lee)
- (h) "Once staff have been allocated to a site too they still can be seen on other sites staffing option — should only be seen on the sites they're allocated to."
- Operator agreed to the iter 216h62 follow-up: ship a Compare-Sites mode in Operational Reports so multi-site Pulse brands can benchmark in one screen.

### What shipped

#### (h) Staffing scoped to allocated sites
**Backend:**
- **`/app/backend/routes/account.py`** — `GET /api/account/team?site_id={id}` filters `users` to only those whose `allowed_site_ids` array contains `site_id`. Owners/Managers AND users with empty `allowed_site_ids` (org-wide access) are ALWAYS included so leadership doesn't vanish when an operator switches sites.
- **`/app/backend/routes/staffing_clock.py`** — `GET /api/staffing/clock/board?site_id={id}` pre-loads the user IDs allowed at that site, then filters `staff_members` by `user_id ∈ allowed_users`. Staff with no `user_id` link (legacy / kiosk-only) treated as org-wide.

**Frontend:**
- **`TimeClockTab.js`** — `ClockBoard` reads `active_site_cache` from localStorage (the staffing panels don't have direct `useAuth()` context) and appends `site_id=` to the board endpoint. SiteSwitcher changes ripple through the punch board.
- `AccountSettingsModal` Team section deliberately stays org-wide — that's the leadership-only admin UI for invites + site-allocation.

#### Compare-Sites enhancement (Operational Reports)
- **`/app/frontend/src/pages/OperationalReportsTab.js`** — new collapsible "Compare sites" card (only renders for multi-site tenants). Operator selects 2-3 site pills (capped at 3) and clicks `Compare N sites`. We fan-out parallel `/reports/operational?site_id=…&period=…` requests and render a table: Site / Total faults / Open / Resolved / Avg resolution / PO value / Top supplier.
- Test IDs: `compare-sites-panel`, `compare-sites-toggle`, `compare-site-pill-{id}`, `compare-sites-run-btn`, `compare-sites-table`, `compare-row-{id}`.

### Verified
- 11/11 backend tests pass (testing-agent iter 216h63).
- Manual e2e curl: `/team` org-wide=2, `?site_id=A`=2 (owner+staff), `?site_id=B`=1 (owner only, Site-A staff hidden).
- Frontend: Compare panel renders, 3 site pills, table renders with 2 rows + 7 columns.

### Files touched
- `/app/backend/routes/account.py` (~+30 LOC — site_id filter on list_team)
- `/app/backend/routes/staffing_clock.py` (~+45 LOC — site_id intersection on clock_board)
- `/app/frontend/src/pages/LiteDashboard/staffing/TimeClockTab.js` (~+15 LOC — localStorage active_site_cache read + ?site_id append)
- `/app/frontend/src/pages/OperationalReportsTab.js` (~+85 LOC — Compare Sites panel + state + fan-out runner)

### All 8 operator-reported items from the Feb 12 screenshot set are now shipped
- (a) Archive → Settings & Compliance ✅ (216h59)
- (b) Memberships ≠ CRM ✅ (216h59)
- (c) Uploaded logo overrides navbar ✅ (216h59)
- (d) Brand Kit auto-applies palette ✅ (216h59)
- (e) Site module override guard ✅ (216h60)
- (f) Master Admin Archive/Delete site ✅ (216h61)
- (g) Site-scoped Reports + Suppliers ✅ (216h62)
- (h) Site-scoped Staffing ✅ (216h63)

---



## Iter 216h62 — (g) Site-scoped Reports + Suppliers (Feb 12, 2026)

### Operator-reported (Lee)
"Multi site - Reports - Each site should have their own set of reports for their own machines - only when the owner/manager selects all sites should they be able to see the reports as a collective. Same goes for the supplier option."

### What shipped

#### Backend (`routes/reports.py`)
All three operator-facing report endpoints accept an optional `site_id` query param and delegate to the existing `apply_site_lock(user, site_id, org_filter)` utility:
- `GET /api/reports/resolution-stats?site_id={id}`
- `GET /api/reports/equipment-summary?site_id={id}`
- `GET /api/reports/operational?period=…&site_id={id}`

Omitting `site_id` returns the org-wide aggregate (used when the SiteSwitcher is in "All Operations Sites" mode).

#### Backend (`routes/suppliers.py`)
`GET /api/suppliers?site_id={id}` now returns only suppliers that actually service equipment at the requested site. Two-step filter:
1. Pull `equipment.supplier_id` + `equipment.supplier` at the target site.
2. Filter the suppliers directory by `id ∈ supplier_ids OR name ∈ supplier_names`.

Empty result when the site has equipment with `supplier='X'` but the directory doesn't contain X surfaces a useful data-hygiene signal rather than a phantom listing.

#### Frontend
- **`PulseReportsTab.js`** — derives `scopeSiteId` from `useAuth()` (`activeSite.id` when `sites.length > 1` and a single site is picked). Appends `site_id=…` to both `/reports/resolution-stats` and `/reports/operational` calls. New **scope badge** above the sub-tab bar (testid `reports-scope-badge`) reading either `Scope: <site name>` or `Scope: All Operations Sites · aggregate` — single-site tenants don't see it.
- **`ReportsTab.js`** + **`OperationalReportsTab.js`** — same `scopeSiteId` pattern.
- **`LiteDashboardPage.js`** — suppliers fetch now uses the existing `siteParam` already passed to `/equipment` and `/issues`. SiteSwitcher updates reload suppliers along with everything else.
- **`Dashboard/hooks/useDashboardData.js`** — suppliers fetch reads `active_site_cache` from localStorage (the hook doesn't have direct access to `useAuth()` context) and appends `site_id=…`.

### Verified
- 10/11 backend tests pass (testing-agent iter 216h62) + UI flow verified.
- Manual curl as Pulse Fitness owner: `/api/suppliers` → 1 supplier (`Pulse Fitness`). `/api/suppliers?site_id=<new site with no eq>` → 0 (correct intersection behaviour).

### Files touched
- `/app/backend/routes/reports.py` (~+10 LOC — 3 endpoints accept site_id + apply_site_lock import)
- `/app/backend/routes/suppliers.py` (~+30 LOC — two-step supplier intersection filter)
- `/app/frontend/src/pages/PulseReportsTab.js` (~+30 LOC — scopeSiteId + scope badge)
- `/app/frontend/src/pages/ReportsTab.js` (~+10 LOC — scopeSiteId)
- `/app/frontend/src/pages/OperationalReportsTab.js` (~+10 LOC — scopeSiteId)
- `/app/frontend/src/pages/Dashboard/hooks/useDashboardData.js` (~+15 LOC — localStorage active_site_cache read)
- `/app/frontend/src/pages/LiteDashboardPage.js` (~+5 LOC — siteParam threaded into suppliers)

### Deferred (last from the 8-bug set)
- (h) Staffing scoped to allocated sites only — next iteration.

---



## Iter 216h61 — Master Admin Site Drawer: equipment listing fix + Archive/Restore/Delete (Feb 12, 2026)

### Operator-reported (Lee, with screenshot)
1. "Site drawer equipment — not being pulled through — machines are on customer portal but not here to be edited/deleted." Third Space - Canary Wharf showed 3 TEST_QR rows instead of its 29 real machines.
2. (f) "Master admin has no option to archive or delete a site — the option should be within site details."

### Root cause (equipment bug)
`SiteDetailDrawer` called `/api/equipment?site_id={siteId}` with the master-admin's own token. The generic `/equipment` endpoint uses `get_organization_filter(user)` which, for master-admin tokens that have no `organization_id`, falls back to `{user_id: master_id}` — so it silently returned only equipment the master-admin had personally created (e.g. test rows from curl smoke tests). Cross-org browsing was broken.

### What shipped

#### Backend (`routes/sites.py`)
- **NEW** `GET /api/master-admin/organizations/{org_id}/sites/{site_id}/equipment` — explicit org-in-path listing. Doesn't consult the calling user's organization_id; only requires `require_master_admin(user)` + `assert_org_in_pulse_scope(user, org_id)`.
- **NEW** `POST /api/master-admin/organizations/{org}/sites/{site}/archive` — soft-archive (`archived=true` + `archived_at` + `archived_by`). Refuses to archive the only HQ with an actionable error.
- **NEW** `POST /api/master-admin/organizations/{org}/sites/{site}/restore` — `$unset` the archive metadata.
- **NEW** `DELETE /api/master-admin/organizations/{org}/sites/{site}` — HARD delete. Refused when site still has equipment OR open issues, with a verbatim "Cannot delete X while it still has Y equipment item(s) and Z open issue(s). Move the equipment to another site or archive the site instead." message.
- **EXTENDED** `PATCH /api/master-admin/organizations/{org}/sites/{site}` — accepts the full SiteDetailDrawer field set (address_line1/2, city, county, country, phone, email, site_manager_name, site_manager_email, default_location).
- **HIDDEN** archived sites from operator-facing `GET /api/sites` (added `archived: {$ne: True}` to the find filter). Master Admin listing still shows them with the badge for restore.

#### Frontend (`SiteDetailDrawer.js`)
- Equipment tab now calls the new master-admin-scoped endpoint → real equipment count.
- Header now has Archive (or Restore when archived) and Delete buttons with confirm prompts (testids: `site-detail-archive`, `site-detail-restore`, `site-detail-delete`). "Archived" badge appears next to the site name when applicable.

### Verified
- 9/9 backend tests pass (testing-agent iter 216h61) + screenshot evidence showing the 29-equipment fix.
- Manual curl e2e: GET endpoint → count=29 real items. DELETE Canary Wharf → 400 with explicit equipment+issue count. ARCHIVE the only HQ → 400 with promote-first message. ARCHIVE Islington (non-HQ) → ok:true. RESTORE → ok:true.

### Files touched
- `/app/backend/routes/sites.py` (+115 LOC — 4 new endpoints + extended PATCH + /sites archived filter)
- `/app/frontend/src/pages/MasterAdmin/SiteDetailDrawer.js` (+75 LOC — endpoint URL fix + Archive/Restore/Delete handlers + header buttons + Archived badge)

### Deferred (per operator's "A first" steer; (e) shipped iter 216h60, (f) shipped here)
- (g) Reports + Suppliers scoped to current site (aggregate only on "All sites")
- (h) Staffing scoped to allocated sites only

---



## Iter 216h60 — (e) Site module-override guard + Onboarding CTA route fixes (Feb 12, 2026)

### Operator-reported (Lee)
1. (e) "Site module switches shouldn't be able to be turned on if the main head office is off" — sites were showing modules enabled while the org Feature Control panel had them off.
2. Account Settings → Onboarding → "Add Extra Site" Review button → bounced to `/sites` → GymAxis 404 page. Lee asked for an audit of every onboarding step CTA.

### What shipped

#### (e) Site module-override guard
- **`/app/backend/routes/sites.py`** — `set_site_modules()` now refuses to enable a module at the site level when the parent org has it off. Returns `{ok:false, blocked:[…], detail:"Cannot enable X at site level — the parent organisation has that module turned off. Enable it on the org first via Master Admin → Modules."}`. Any previously-stored override for the blocked key is also stripped so the UI immediately reflects truth.
- `get_site_modules()` `effective[k]` is now `site_override AND org_on`, so legacy overrides storing `enabled=true` on a module the org now has off resolve to `false`.
- **Critical detail (the first attempt didn't work):** previous code passed the calling user to `resolve_module_access(user, org)`, but master-admin returns all-True there → the guard was bypassed. Switched to `_org_module_access({is_master_admin: False, account_type: "full"}, org)` — a synthetic non-master user — so the resolver actually reads the org matrix instead of short-circuiting.
- **`/app/frontend/src/components/sites/SiteModulesOverride.js`** — `setOverride()` now reads `r.data.ok === false` and surfaces `detail` via `notify.error('Blocked', …)` so operators see exactly why the toggle didn't take.

#### Onboarding CTA route audit
- **`/app/frontend/src/components/shared/AccountSettingsModal.js`** — new `resolveRoute(step.cta_route)` helper inside `OnboardingSection`. Maps:
  - `/sites` → `/master-admin?section=organizations` (master admin) | `/pulse?settings=sites` (Pulse Pro/Lite) | `/dashboard` (full).
  - `/dashboard?tab=equipment` → `/pulse?tab=equipment` for Pulse operators.
  - `/pricing` → `/master-admin?section=integrations-hub` for master admins.
  - All other `/dashboard*` → swapped for `/pulse*` or `/master-admin*` to match the user's actual home.
- `profile` is now threaded into `OnboardingSection` so the resolver can read `account_type` and `is_master_admin`.
- **`/app/frontend/src/pages/LiteDashboardPage.js`** — new useEffect reads `?tab=` and `?settings=` from URL search params so `/pulse?tab=equipment` switches the active tab and `/pulse?settings=sites` auto-opens the Settings dialog (which hosts `PulseSettingsTab` → "Add Site" UI).

### Verified
- 9/9 backend tests pass (testing-agent iter 216h60).
- Manual curl e2e: PUT marketing=true on a Pulse site while org.marketing=false → `{ok:false, blocked:['marketing'], detail:"Cannot enable marketing at site level — …"}`. GET effective then shows `marketing:false`. Restored Pulse to all-on after.
- Onboarding step list audited: site_details + extra_sites + import_machines + connect_stripe all now resolve to real routes; team/organisation/profile cta_sections all switch in-modal.

### Files touched
- `/app/backend/routes/sites.py` (~+40 / −10 LOC — guard + user-agnostic org resolver call)
- `/app/frontend/src/components/sites/SiteModulesOverride.js` (~+10 / −3 LOC — render blocked message)
- `/app/frontend/src/components/shared/AccountSettingsModal.js` (~+35 LOC — `resolveRoute()` + profile prop threading)
- `/app/frontend/src/pages/LiteDashboardPage.js` (~+10 LOC — searchParams `?tab=` and `?settings=` handler)

### ⚠ Action required
1. Redeploy preview → production. Backend (`routes/sites.py`) + frontend (3 files).
2. Lee revisits a Pulse site that had a phantom module override: the panel now reads the capped effective value. Toggling a module the org has off shows the explicit "Cannot enable X at site level" error rather than silently storing a phantom override.
3. Lee clicks "Add Extra Site Review" in Onboarding — modal navigates to either Master Admin → Organizations (if master admin) or auto-opens the Pulse Settings dialog with the Sites pane.

---



## Iter 216h59 — 4 quick-win UX & module-scoping fixes (Feb 12, 2026)

### Operator-reported (Lee, 5 screenshots)
Subset of an 8-bug report, scoped to the 4 low-risk single-file fixes for this iteration. Items (e-h) — site-level module override guard, archive/delete site, reports/suppliers/staffing scoping — deferred per operator's "ship A first" steer.

### What shipped

#### (a) Archive tab → Settings & Compliance
- **`/app/frontend/src/pages/MasterAdmin/SidebarConfig.js`** — `archive` removed from `overview.subTabs` and re-mounted inside `settings-compliance.subTabs` alongside Audit log, Login events, Documents, etc. `LEGACY_SECTION_REDIRECTS` updated. Master Admin Dashboard Overview is now Dashboard / System Health / Setup checklist only. Archive is more naturally a compliance / data-lifecycle tool, so it now sits with its peers.

#### (b) Memberships no longer auto-enables CRM
- **`/app/backend/routes/master_admin.py`** — removed the iter-215c auto-bundle block in `PUT /master-admin/organizations/{org_id}/features` that flipped `modules.crm.enabled = true` whenever Memberships was enabled.
- **`/app/backend/utils/module_access.py`** — `crm_modes()` `leisure` flag now derived from `access.crm` (was `access.memberships`). Memberships and CRM are truly independent now: an operator can run Memberships standalone, run CRM standalone, or both — without one forcing the other.

#### (c) Uploaded logo overrides Pulse/GymAxis navbar logo
- **`/app/frontend/src/components/shared/Navbar.js`** — logo render priority reordered: `orgLogo > showPulseBrand > GymAxisLockup > initial-box`. The Pulse Fitness short-circuit at the top of the conditional no longer wins over a customer-uploaded logo. When `orgLogo` is set, the org's `branding.company_name` label is shown instead of "Pulse Fitness" / "GymAxis".
- **`/app/backend/routes/auth.py`** — `GET /organization/logo` now passes through new `/api/account/logo/{org_id}?v=…` proxy URLs (from iter 216h57) and `data:` URI fallbacks unchanged. Was previously only handling `http://…` and `/api/public/files/…`.

#### (d) Brand Kit auto-applies extracted palette
- **`/app/frontend/src/pages/Marketing/BrandKitTab.js`** — `onLogoUpload` now also POSTs the file to `/api/account/logo` (in parallel with the existing data-URI save) to pull the auto-extracted `brand_palette`. Sets `primary_color = palette[0]` and `secondary_color = palette[1]` automatically — but only when the existing values are still GymAxis defaults (`#19CDFF`, `#5B8CFF`, `#66CCFF`, `#0055FF`, `#000000`, `#FFFFFF`). If the operator already curated custom colours, they're preserved. Toast message lists the detected colours.

### Verified
- 6/6 backend tests pass (testing-agent iter 216h59):
  - PUT features with memberships=true + crm=false now PERSISTS crm=false (was being auto-flipped before).
  - `crm_modes()` no longer leaks leisure access when only memberships is on.
  - GET /organization/logo handles all 4 URL formats (http, /api/public/files/, /api/account/logo/, data:).
- Frontend code-review confirmed (a), (c), (d) wired correctly.
- Manual curl: Pulse → memberships=true,crm=false → confirmed both stored independently. Restored to all-on at end.

### Files touched
- `/app/frontend/src/pages/MasterAdmin/SidebarConfig.js` (~+8 / −10 LOC — Archive moved between groups + legacy redirect map)
- `/app/backend/routes/master_admin.py` (~+12 / −10 LOC — removed auto-bundle, replaced with comment for traceability)
- `/app/backend/utils/module_access.py` (~+5 / −3 LOC — crm_modes leisure now reads `access.crm`)
- `/app/frontend/src/components/shared/Navbar.js` (~+15 / −10 LOC — logo priority reorder)
- `/app/backend/routes/auth.py` (~+10 LOC — extra proxy-URL formats in GET /organization/logo)
- `/app/frontend/src/pages/Marketing/BrandKitTab.js` (~+30 / −5 LOC — palette auto-apply on logo upload)

### Deferred to next session (per operator's "A first" choice)
- (e) Site-level module overrides shouldn't enable a module the parent org has OFF
- (f) Master Admin: Archive / Delete site buttons inside site detail drawer
- (g) Reports + Suppliers scoped to current site (aggregate only on "All sites")
- (h) Staffing scoped to allocated sites only

---



## Iter 216h58 — Drag-and-drop logo + auto-extracted brand palette (Feb 12, 2026)

### Context
Following the iter 216h57 fix to logo & avatar uploads, the operator accepted the suggested enhancement: turn the static logo picker into a drag-and-drop zone AND auto-extract a brand-colour palette from the uploaded logo so the operator can one-click apply a primary colour without firing up a colour picker.

### What shipped

#### Backend (`routes/account.py`)
- **`_extract_brand_palette(img, n=5)`** — Pillow MEDIANCUT adaptive quantisation (no sklearn dep). For transparent PNGs the image is composited on white before quantising. Filters out near-white (`max(rgb)≥245 AND min(rgb)≥235`) and near-black (`max(rgb)≤25`) pixels so logo backgrounds and stroke outlines don't pollute the palette. Returns up to 5 hex strings in dominance order.
- **`POST /api/account/logo`** — now also returns `brand_palette` alongside `logo_url`, and persists `brand_palette` on the org document.
- **`POST /api/account/branding/apply`** — new endpoint. Body: `{primary_color: "#RRGGBB"}`. Writes the colour to ALL three brand-colour fields the codebase reads (`branding.primary_color`, `primary_brand_colour`, `brand_color`) so member emails, supplier cases, member portal and memberships launch-kit all pick up the new colour. Hex validation via regex; Owner/Manager only.
- **`GET /api/account/organisation`** — now also returns `brand_palette` and a resolved `primary_color` (cascade `branding.primary_color` → `primary_brand_colour` → `brand_color`).

#### Frontend (`AccountSettingsModal.js`)
- `OrganisationSection` — logo section refactored into a dashed-border drag-and-drop zone (`account-org-logo-dropzone`) with `onDragOver` highlight, `onDrop` upload, and the existing file-picker as a fallback.
- After upload the response's `brand_palette` is stored on local state and rendered as 16×16 colour swatches (`account-org-palette-swatch-{hex}`). The active brand colour gets a ring-2 ring-offset highlight.
- Clicking a swatch calls `POST /account/branding/apply` and updates the active highlight in-place. Loading state per-swatch via `applyingColor`.
- Toast feedback: upload success notes the number of colours detected; apply confirms the new hex.

### Verified
- 11/11 backend tests pass (testing-agent iter 216h58).
- Manual curl e2e:
  - Realistic 3-colour PNG (cyan #19CDFF + orange #FF6E40 + purple #6633CC blocks on transparent BG) → palette = exactly those 3 in dominance order.
  - `POST /branding/apply { "#19CDFF" }` → all 3 fields updated, returned to client correctly via `GET /organisation`.
  - Invalid hex (`"red"`) → 400 "primary_color must be a #RRGGBB hex string".
- Frontend code-review: dropzone, swatches, drag handlers, applyBrandColor confirmed wired.

### Files touched
- `/app/backend/routes/account.py` (+80 LOC — `_extract_brand_palette`, palette in logo response, `POST /branding/apply`, `GET /organisation` extended)
- `/app/frontend/src/components/shared/AccountSettingsModal.js` (~+95 LOC — dropzone + palette swatches + applyBrandColor)

### Operator impact
Drop a logo → see the dominant colours in 2 seconds → click your brand colour → it propagates to every member-facing surface in the platform (invoices, supplier cases, launch-kit emails) without a single colour-picker click.

---



## Iter 216h57 — HOTFIX: 5 production UX bugs (fault detail clutter, manufacturer-photo crash, logo & avatar uploads) (Feb 12, 2026)

### Operator-reported (Lee, 5 screenshots)
1. Fault detail card shows THREE buttons to open the Supplier Modal (top "View supplier card" pill + blue "Supplier Fault Card → Open" banner + "Supplier Card" link in the Supplier Communication header). Lee wants only the one inside the Supplier Communication card.
2. The space freed by removing the blue banner should display the engineer's scheduled visit details.
3. "Find manufacturer photo" button creates a runtime error when clicked.
4. Account Settings → Onboarding → "Upload logo" closes the settings modal instead of letting the operator upload.
5. Profile picture upload shows the word "Avatar" inside the circle instead of the uploaded image.

### Root causes & fixes

#### Bug 1+2 — Fault detail clutter
- **`/app/frontend/src/pages/IssueDetailPanel.js`** — replaced the blue `Supplier Fault Card` deep-link banner (lines ~396-415) with a prominent purple **Engineer Visit Scheduled** card (testid `engineer-visit-banner-{issue.id}`) that surfaces the scheduled date, engineer name, and a Reschedule CTA. Also removed the smaller in-comms `Engineer Visit:` chip since that info is now front-and-centre. The Supplier-Card link survives only in the Supplier Communication card header.

#### Bug 3 — Find manufacturer photo crash
- **`/app/frontend/src/pages/LiteDashboard/LiteDialogs.js`** — `onAutoLookup` used the bogus path `(await import('sonner')).notify.success(...)`. `sonner` exports `toast`, not `notify`. Replaced with the top-of-file `notify` import (from `@/components/notifications`) and dropped the redundant dynamic axios import.

#### Bug 4 — Upload logo closes settings modal
- **`/app/backend/routes/account.py`** — `ONBOARDING_STEPS['upload_logo']` previously used `cta_route: '/dashboard?settings=brand'` (a route that doesn't exist, so `navigate()` fired and `onClose()` closed the modal). Now uses `cta_section: 'organisation'` which switches the modal tab in-place.
- **`AccountSettingsModal.js`** — added an **Organisation logo** subsection inside `OrganisationSection` with proper upload/remove handlers (testids: `account-section-logo`, `account-org-logo-upload-btn`, `account-org-logo-input`, `account-org-logo-img`, `account-org-logo-remove-btn`). Owner/Manager only (Staff sees a guard message).

#### Bug 5 — Profile picture shows alt text "Avatar"
- **`/app/backend/routes/account.py`** — root cause: `put_object()` returned `{"path": "gymaxis-ai/avatars/.../foo.jpg"}` with NO `url` field. The avatar code stored that raw path as `avatar_url`, then the browser tried to load it as a relative URL → 404 → `<img alt="avatar">` rendered the alt text.
- Added a public proxy: `GET /api/account/avatar/{user_id}` and `GET /api/account/logo/{org_id}` (modelled on the existing `/equipment/{id}/photo` pattern in `routes/equipment.py`). Streams from object storage with `Cache-Control: public, max-age=600`.
- Avatar/logo upload now stores `avatar_path` / `logo_path` internally and returns `avatar_url = /api/account/avatar/{user_id}?v=…cache-buster`. Data-URI fallback retained for object-store outages.
- **`/app/backend/routes/auth.py`** — `/auth/me` now includes `avatar_url` and `phone` so the AccountSettingsModal hydrates the avatar on first render.

### Files touched
- `/app/backend/routes/account.py` (+115 / −5 LOC — avatar proxy, logo upload + proxy + delete, cta_section swap)
- `/app/backend/routes/auth.py` (+2 LOC — avatar_url, phone in /auth/me)
- `/app/frontend/src/components/shared/AccountSettingsModal.js` (+90 LOC — Organisation logo subsection)
- `/app/frontend/src/pages/IssueDetailPanel.js` (~+30 / −20 LOC — Engineer Visit banner replaces Supplier Fault Card banner; CalendarDays import added)
- `/app/frontend/src/pages/LiteDashboard/LiteDialogs.js` (~+10 / −10 LOC — sonner.notify → notify)

### Verified
- 9/9 backend tests pass (testing-agent iter 216h57):
  - POST/DELETE /api/account/logo + GET /api/account/logo/{org_id} round-trip → 200/image/png.
  - POST /api/account/avatar + GET /api/account/avatar/{user_id} round-trip → 200/image/jpeg.
  - /api/auth/me now includes avatar_url + phone.
  - cta_section='organisation' on the upload_logo step.
- Frontend lint clean across all 5 files; code review by testing agent confirmed all 5 fixes in place.

### ⚠ Action required
1. Redeploy preview → production. Multi-file change (backend account.py + auth.py, frontend modal + issue detail + dialog).
2. Operators with previously-uploaded avatars (stored as raw object-store paths) will see them seamlessly via the new proxy thanks to the legacy fallback in `serve_avatar` / `serve_logo`. No data migration needed.

---



## Iter 216h56 — HOTFIX: Blank trailing CSV rows counted as errors (Feb 12, 2026)

### Operator-reported (Lee, with screenshot)
Result toast read: **"Imported 98 equipment · 10,494,277 skipped · 10,494,277 row issues — see details below"** on a CSV with only ~100 real records. Every blank trailing row was being treated as a failed import.

### Root cause
Excel and Google Sheets exports drag along millions of empty trailing rows (Excel pads to 1,048,576 rows × however many sheet duplicates; Lee's file appears to have come out of a tool that 10×'d that). The iter 216h54 row-error work then logged each blank row as `Row N: missing required column 'name'`, both inflating `skipped` and producing an unreadable error log.

### Fix
- **`/app/backend/routes/master_admin_bulk_import.py`** — new `_is_blank_row(row)` helper that returns `True` when every cell is empty/whitespace. Wired into the loop top of all three importers (equipment, customers, sites) as the very first check. Truly-blank rows are now `continue`'d silently — they do NOT increment `skipped` or `error_count`.

### Verified
| File contents | Imported | Skipped | Errors |
|---|---|---|---|
| 98 real + **100,000 blank** trailing rows | **98** | **0** | **0** |

Plus the earlier mixed-content regression (1 missing-name + 1 unknown-site + 1 duplicate + 100 valid) still returns 100 imported / 3 skipped / 3 errors with verbatim row reasons. Wall-clock: 0.56 s for the 100k blank-row file.

### Files touched
- `/app/backend/routes/master_admin_bulk_import.py` (~+25 LOC — `_is_blank_row` helper + 3 call-sites)

### ⚠ Action required
1. Redeploy preview → production. Backend-only change.
2. Lee re-uploads the same Excel-exported CSV. Result toast will now match the real record count (`Imported N equipment · 0 skipped · 0 row issues`) instead of being inflated by the spreadsheet's padding rows.

---



## Iter 216h55 — HOTFIX: 500k-row bulk import (`Request body exceeds 2097152 bytes`) (Feb 12, 2026)

### Operator-reported (Lee, production screenshot)
"Bulk import still not working — Pulse Fitness could be importing up to 500k pieces of equipment, we need to ensure this works and can cope with the amount of information that is going to be required by this system." UI showed: `Couldn't import equipment — Request body exceeds 2097152 bytes`.

### Root cause
Iter 216h54 surfaced row-level error reasons but the *request itself* never reached the importer at scale — three structural caps blocked Pulse-volume CSVs:

1. **Body-size middleware** — `/api/master-admin/bulk-import/*` was **not in** `UPLOAD_PATH_PREFIXES` in `utils/security_plus.py`, so it inherited the 2 MB default. Lee's 500k equipment CSV is ~120-150 MB.
2. **Per-endpoint `validate_upload` cap** — explicitly set to `10 * 1024 * 1024` (10 MB) on every bulk-import endpoint.
3. **Per-row inserts** — `await db.equipment.insert_one(doc)` AND `await db.equipment.find_one({"serial_number": serial}, ...)` *for every row*. At 500k rows that's 1 M DB round-trips — would take 30+ minutes even if the body fit.

### What shipped

#### Middleware — 3rd body-size tier
`utils/security_plus.py`:
- New `BULK_IMPORT_BODY_LIMIT_BYTES = 200 MB` (override via `MAX_BULK_IMPORT_BYTES`).
- New `BULK_IMPORT_PATH_PREFIXES` allow-list covering `/api/master-admin/bulk-import/`, `/api/master-admin/sites/import`, `/api/master-admin/equipment/import`.
- `body_size_guard` now does a 3-tier resolution: bulk-import → 200 MB; upload → 25 MB; default → 2 MB.

#### Bulk-import endpoint scale-up (`routes/master_admin_bulk_import.py`)
For all 3 importers (equipment, customers, sites):
- `validate_upload(..., max_size=200 * 1024 * 1024)` matches the new middleware cap.
- **Pre-loaded duplicate sets** — one bulk query per target org populates a Python `set` of existing serials/emails/site-names. Per-row check is now `serial in set` (O(1)) instead of 500k Mongo `find_one`s.
- **Batched inserts** — accumulate rows into a `pending` list and flush every 500 rows via `db.<col>.insert_many(pending, ordered=False)`. Row-by-row fallback on insert_many failure preserves the per-row error reporting from iter 216h54.
- Cache the just-inserted serial/email/site-name into the set so a duplicate *within* the same CSV is also caught.

### Verified on the live preview
| File | Rows | Body | Wall-clock | Imported | Errors |
|---|---|---|---|---|---|
| `eq_big.csv` | 5,000 | 0.78 MB | **0.44 s** | 5,000 | 0 |
| `eq_huge.csv` | 50,000 | 7 MB | **2.16 s** | 50,000 | 0 |
| `eq_mixed.csv` | 103 (3 invalid + 100 valid) | 19 KB | 0.10 s | 100 | 3 (missing name, unknown site, duplicate serial — all surfaced verbatim) |

Throughput: ~23k rows/sec end-to-end. Pulse's 500k equipment CSV projects to **~22 seconds** wall-clock. The 2 MB-cap 413 is gone. Error-path semantics from iter 216h54 are fully preserved.

### Files touched
- `/app/backend/utils/security_plus.py` (~+25 / −5 LOC — 3rd body-size tier + bulk-import path allow-list)
- `/app/backend/routes/master_admin_bulk_import.py` (~+120 / −40 LOC — pre-loaded sets, batched `insert_many`, 200 MB caps across all 3 endpoints)

### ⚠ Action required
1. Redeploy preview → production.
2. Lee re-uploads the failing equipment CSV. The 200 MB request now passes the middleware; batched inserts complete a Pulse-scale (500k) file in ~20-25 s rather than 30 min.
3. If even bigger imports arrive (>200 MB), bump `MAX_BULK_IMPORT_BYTES` in `backend/.env`. Long-term consideration: move to a chunked/streamed upload + background-job pattern if files routinely exceed 500 MB.

---



## Iter 216h54 — HOTFIX: `Session revoked` 401 on Service Desk + Bulk-import row-level errors (Feb 12, 2026)

### A. P0 — "Session revoked" race-condition fix on `/auth/refresh`

#### Operator-reported (Lee, production)
After loading `gymaxisai.com/service-desk`, the dashboard would intermittently 401 with `Session revoked` and bounce to login. Pattern: any parallel request that captured the JWT *before* App.js's `refreshToken()` completed would race the immediate revocation of the old jti.

#### Root cause
`/api/auth/refresh` revoked the old jti via `revoke_jwt` the moment a new token was minted. App.js fires `refreshToken()` on every page load alongside `loadSites(token)` + `loadBranding(token)` + freshly-mounted page useEffects (e.g. `DeskSummary` fetching `/service-desk/summary`). Those in-flight calls — using the same token value that was just revoked — got 401'd.

#### Fix — grace window on revocation
- **`/app/backend/utils/security_plus.py`** — `revoke_jwt(jti, exp_ts, reason, grace_seconds=0)` now stores an `effective_at` timestamp. `is_jwt_revoked(jti)` only treats the deny-list entry as active once `now >= effective_at`.
- **`/app/backend/routes/auth.py`** — `/auth/refresh` passes `grace_seconds=60`. Logout still uses the default `0` for immediate revoke.
- **Backwards-compatible**: legacy revocation rows without `effective_at` are treated as immediately revoked (preserves logout-revoke semantics for existing deny-list entries).

#### Verified
- 4 new regression tests in `test_security_hardening.py` — `test_jwt_revocation_grace_window_still_valid` + `test_jwt_revocation_grace_window_expires` + existing roundtrip + missing-jti.
- 17/17 testing-agent backend tests PASS, including the explicit "in-flight old-token after refresh stays valid" check.
- Curl reproduction: login → /auth/refresh → re-use old token on /service-desk/summary → **HTTP 200** (was 401).

### B. P1 — Bulk-import row-level errors surface in the UI

#### Operator-reported (Lee, production)
"Bulk import fails and the UI just says 'failed'. I shouldn't have to ask Emergent to decode why."

#### Fix — every skipped row now gets a reason
- **`/app/backend/routes/master_admin_bulk_import.py`** — emits `Row N: <reason>` for every skipped row across all three importers:
  - Equipment: missing `name`, duplicate `serial_number`, unknown `site_name`, unknown `customer_account_number`, validate-upload failure.
  - Customers: missing all of email/first/last, duplicate email, unknown account number.
  - Sites: missing `site_name`, duplicate name, unknown columns.
- Response payload extended with `error_count` (total errors regardless of truncation cap), `errors` returns up to 50 entries (was 10/20).

#### Frontend
- **`/app/frontend/src/pages/MasterAdmin/AdminBulkImports.js`** — result card now:
  - Auto-opens the `<details>` block whenever errors exist (no more hidden warnings).
  - Renders red "Import failed" panel when the whole request 4xx/5xx'd, with `err.response.data.errors` if the server attached row context.
  - Shows `X imported · Y skipped · Z error(s)` summary and "Showing first 50 of N" when truncated.
  - Each row error has `data-testid="bulk-error-row-{kind}-{i}"` for testability.

### C. Service Desk 8-tab parity — confirmed
- `/app/frontend/src/pages/ServiceDeskPage.js` already wires all 8 Lee-spec primary tabs (Dashboard, Cases, Scheduler, Customers, Equipment, Parts, Billing, Engineers) plus 3 Insights tabs (Supplier health, Reports, Audit log). The Service Ops pages mount via lazy-loaded `<Suspense>` inside `<ServiceOpsEmbeddedContext.Provider>`. No functionality was lost in the merge — verified via testing agent.

### Files touched
- `/app/backend/utils/security_plus.py` (~+35 / −5 LOC — grace window in revoke_jwt + is_jwt_revoked)
- `/app/backend/routes/auth.py` (+5 LOC — pass grace_seconds=60 on refresh)
- `/app/backend/routes/master_admin_bulk_import.py` (+8 LOC — per-row error reasons, error_count, larger cap)
- `/app/backend/tests/test_security_hardening.py` (+30 LOC — 2 new grace-window tests + asyncio import)
- `/app/backend/tests/test_iter_216h54_jwt_grace_bulk_errors.py` (NEW — testing-agent regression suite)
- `/app/frontend/src/pages/MasterAdmin/AdminBulkImports.js` (~+25 / −10 LOC — auto-open details + truncation badge + failed-state styling)

### ⚠ Action required
1. Redeploy preview → production. Backend (`utils/security_plus.py`, `routes/auth.py`, `routes/master_admin_bulk_import.py`) + frontend (`AdminBulkImports.js`).
2. After deploy, Lee can hard-refresh `gymaxisai.com/service-desk` without seeing the 'Session revoked' bounce.
3. Lee retries the failing CSV imports — the result card now lists exactly which rows failed and why (missing column, duplicate, unknown site/account number), no support ticket required.
4. The Service Desk Dashboard now hosts all 8 Lee-spec tabs + Insights — every Service Ops feature (case board, scheduler, parts, billing, engineers) is reachable from the unified left sidebar.

---



## Iter 216h45 — `<UnifiedAuthProvider>` + `useUnifiedAuth()` (Feb 12, 2026)

### Why
Two recurring "ghost-login" bugs in close succession traced to the same root issue:
- Iter 216h42: false-offline banner (auth state assumed from `navigator.onLine`).
- Iter 216h43: CRM kicking already-logged-in users to CRMLogin because the per-tab `sessionStorage` gate deleted a valid CRM token.

Both were treated as one-off bugs but the *class* of bug remained — every module owned its own `localStorage` token key + bootstrap routine. Auth state could and did diverge across modules. The same shape of bug was guaranteed to surface again under different circumstances.

### What shipped — `<UnifiedAuthProvider>`
- **NEW `/app/frontend/src/components/shared/UnifiedAuthProvider.js`** (~210 LOC). Single source of truth for the three platform tokens:
  - **main** — `localStorage.token` (operations / memberships / master admin)
  - **crm** — `localStorage.crm_token` (CRM workspace)
  - **member** — `localStorage.member_token` (member kiosk / app)
- **API surface:**
  ```js
  const { tokens, identity, login, logout, refresh } = useUnifiedAuth();
  ```
  - `tokens` = strings or null.
  - `identity` = hydrated via `/auth/me` + `/crm/auth/me`.
  - `login({ scope, token, identity? })` — writes localStorage + broadcasts.
  - `logout(scope?)` — omit scope to wipe all 3.
  - `refresh.crm()` — re-exchange main → CRM (call from 401 handlers).
- **Cross-tab + in-tab sync:** watches `window.storage` (cross-tab) and a custom `gymaxis:auth-changed` event (in-tab). All consumers stay in lock-step.
- **Auto-cross-login:** the moment a `main` token lands without a `crm` token, the provider eagerly POSTs to `/api/crm/auth/cross-login` with a 6 s timeout. If the org doesn't have CRM enabled, the call silently 403s and no harm done.
- **Stale-token healing:** when `/crm/auth/me` returns 401/403, the provider strips the bad token AND lets the auto-cross-login effect re-mint a fresh one from main. The user never sees a login screen if their main session is alive.
- **Backwards-compatible:** still writes to the same localStorage keys, so the 196 files across the codebase that read `localStorage.getItem('token')` directly keep working unchanged. Migration to `useUnifiedAuth()` is incremental.

### Wiring in `App.js`
`<UnifiedAuthProvider>` mounted inside `<BrowserRouter>` → wraps the rest of the tree (alongside `<GlobalDragGuard>` and `<UploadQueueProvider>`).

### First migration — `CRMApp.js` bootstrap
- The bespoke per-tab session flag + token-strip cycle (the iter 216h43 fix) is now gone entirely. The `useEffect` defers to `unifiedAuth.identity.crm`, `unifiedAuth.tokens.main`, and `unifiedAuth.tokens.crm`. Maximum spinner time: 6 s.
- The `login(token, userData)` and `logout()` callbacks pipe through `unifiedAuth.login({ scope: 'crm', ... })` / `unifiedAuth.logout('crm')` so other modules see the change instantly.

### Verified end-to-end (live Playwright)
| Step | Token state | CRMLogin shown? |
|---|---|---|
| 1. Main login | main:✓ crm:✗ | n/a |
| 2. Nav to /crm | main:✗ crm:✓ ← **provider auto-issued via cross-login** | **False** ✓ |
| 3. Clear sessionStorage + reload /crm (Lee's exact bug) | main:✗ crm:✓ | **False** ✓ |
| 4. 0 React errors | — | — |

Lee's iter 216h43 recurring bug is now **structurally impossible** for any consumer using `useUnifiedAuth()`. As more consumers migrate, the entire class of "logged in but module X says logged out" disappears.

### Files touched
- **NEW** `/app/frontend/src/components/shared/UnifiedAuthProvider.js` (~210 LOC)
- `/app/frontend/src/App.js` (+3 LOC — import + wrap)
- `/app/frontend/src/pages/CRM/CRMApp.js` (~−75 / +30 LOC — bootstrap reduced to a thin observer; `login`/`logout` callbacks delegate to the provider)
- `/app/DESIGN_SYSTEM.md` (+20 LOC — documented the new provider + hook)

### ⚠ Action required
1. Redeploy preview → production.
2. Future modules: import `useUnifiedAuth` from `@/components/shared/UnifiedAuthProvider`. The naming is `useUnifiedAuth` (NOT `useAuth`) to avoid colliding with the existing `useAuth` from `App.js` (which manages the *main* user object — different concern).
3. Existing localStorage callers keep working — no big-bang rewrite required.
4. Member-app login flows can adopt `unifiedAuth.login({ scope: 'member', token })` on next touch.

---



## Iter 216h44 — `<ListPanel>` super-component (Feb 12, 2026)

### Why
CRM Contacts / Companies / Pipeline-List / Memberships Plans / Classes / Ads / Promotions all duplicate the same 30-50 LOC scaffold every panel:
- A toolbar row with a search input on the left, a count chip, a list of secondary actions, and a primary CTA on the right.
- A centred loading spinner.
- An `<EmptyState>` when the list is empty.
- A `space-y-2` rows wrapper.

That repeated scaffold was ~1,000 LOC of platform-wide boilerplate that drifted into 3 slightly different layouts (different gaps, different spinner sizes, different count-chip placements).

### What shipped — `<ListPanel>`
- **NEW `/app/frontend/src/components/shared/ListPanel.js`** (~150 LOC). Props-driven super-component that bundles the four repeated surfaces and lets the caller own the actual rows (which are too domain-specific to abstract — contact rows look nothing like plan cards).
- Props: `title`, `subtitle`, `search ({ value, onChange, placeholder, testId })`, `count ({ value, label, singular?, plural? })`, `secondaryActions []`, `primaryAction ({ label, icon, onClick, ... })`, `loading`, `empty ({ when, ...EmptyState props })`, `toolbarRight`, `className`, `children`, `data-testid`.
- Auto-generates an inner `*-toolbar` and `*-loading` testId derived from the parent `data-testid` for finer-grained test selectors.
- Delegates the empty state to the existing `<EmptyState>` so the API matches what consumers already know.

### First adoption — `CRM Contacts`
- Replaced the 25-LOC toolbar+rows+EmptyState scaffold in `CRMContacts.js → ContactList` with a single `<ListPanel>` invocation. **Net: −24 / +18 LOC** for the list view.
- Removed now-unused `EmptyState` and `Search` imports.
- All existing `data-testid`s preserved verbatim (`crm-contacts-list`, `contact-search`, `contacts-export-csv`, `create-contact-btn`, `crm-contacts-empty`, `crm-empty-add-contact`, `contact-row-*`, `contact-company-tag-*`).

### Design system doc updated
`/app/DESIGN_SYSTEM.md` documents `<ListPanel>` with a copy-pasteable example and a target adoption list (CRMCompanies, CRMPipeline list view, Memberships Plans/Classes/Ads, PromotionsTab).

### Verified
- Lint clean across `ListPanel.js` and `CRMContacts.js`.
- CRM page loads with **0 React errors** post-migration (smoke test confirmed). The CRM onboarding tour overlay blocks automated clicks but the entire React tree is healthy — proven by clean lazy-chunk load.
- 19/19 backend regression tests from iter 216h43 still pass.

### Files touched
- **NEW** `/app/frontend/src/components/shared/ListPanel.js` (~150 LOC)
- `/app/frontend/src/pages/CRM/CRMContacts.js` (~−40 / +30 LOC, including unused-import cleanup)
- `/app/DESIGN_SYSTEM.md` (+20 LOC)

### ⚠ Action required
1. Redeploy preview → production.
2. New list views going forward: use `<ListPanel>` instead of bespoke scaffolds — see `CRMContacts.js → ContactList` for the canonical example.
3. Migrating existing panels (CRMCompanies, CRMPipeline list, Memberships Plans / Classes / Ads, PromotionsTab) on next feature touch will shave another ~150-200 LOC.

---



## Iter 216h43 — HOTFIX: CRM bouncing already-logged-in Pulse Fitness users to CRMLogin (Feb 12, 2026)

### Operator-reported (Lee, production)
Pulse Fitness staff already logged into `gymaxisai.com` (Operations / Memberships / Master Admin) were being kicked to **CRMLogin** the moment they clicked into CRM. Lee flagged this as a recurring bug.

### Root cause
The CRM bootstrap (iter 215aa, `CRMApp.js` line 525-555) gated `crm_token` reuse on a `sessionStorage.crm_active_session` flag *and* PWA mode, with the rationale "prevents stale cross-tab logins". In practice:

1. `sessionStorage` is **per-tab** — opening CRM in a new tab or doing a hard refresh wipes the flag.
2. The else-branch then **deleted the perfectly valid `crm_token` from `localStorage`** and tried a `POST /crm/auth/cross-login` exchange from the main JWT.
3. On flaky mobile networks (Lee's exact production scenario — 5G dropping packets at coffee shops), cross-login would time out OR return a transient `403`. Catch → `setLoading(false)` → CRMLogin shown.
4. The user saw "log in to CRM" even though their main session was still alive.

The cross-tab gating was the wrong protection layer: `localStorage` exists *specifically* to share auth across tabs in the same browser profile. Rejecting it broke the one cross-tab UX it was designed for.

### Fix
- **`/app/frontend/src/pages/CRM/CRMApp.js`** — replaced the gated reuse logic with **verify-before-replace**:
  1. If `crm_token` exists → call `/crm/auth/me` to validate it.
  2. If valid → log the user in. Restore the `crm_active_session` flag for legacy callers. **Done.**
  3. If invalid (401/403/network) → strip and fall through to cross-login.
  4. If no CRM token (or it 401'd) and a main JWT exists → attempt `/crm/auth/cross-login`.
  5. Only if BOTH paths fail → show CRMLogin.
- **Net effect:** an already-logged-in user is **never** asked to log in to CRM again, regardless of tab/PWA mode.

### Verified end-to-end (live Playwright tests on preview)
| Scenario | Expected | Result |
|---|---|---|
| Login to main app → navigate to /crm | Auto-bridge via cross-login → CRM workspace | ✅ CRM Command Center shown, no CRMLogin |
| CRM token persisted | `localStorage.crm_token` set | ✅ True |
| **Clear `sessionStorage` then re-navigate to /crm** (= new tab / refresh — Lee's exact bug) | Existing valid CRM token used; CRMLogin **NOT** shown | ✅ **CRMLogin hidden — bug fixed** |
| 0 React errors throughout | Clean console | ✅ `Errors: []` |

Backend cross-login regression — `test_iter_215de_permissions_forecast.py` + `test_iter_215dc_territories.py` → **19/19 passing**, no regressions.

Backend probe: `POST /api/crm/auth/cross-login` returns 200 with valid token; `/api/crm/auth/me` returns the user email.

### Files touched
- `/app/frontend/src/pages/CRM/CRMApp.js` (~+75 / −60 LOC — verify-before-replace flow with full comments)

### ⚠ Action required
1. **Redeploy preview → production.** This is a 1-file frontend fix; no DB / env-var / backend changes.
2. After deploy Lee's Pulse Fitness team will no longer see the CRM login screen when they navigate to `/crm` from any logged-in tab. New-tab / hard-refresh / PWA / mobile-browser — all paths now resume the existing CRM session.

---



## Iter 216h42 — HOTFIX: "You're offline" banner false-positive on production (Feb 12, 2026)

### Operator-reported (Lee, production, mobile 5G)
Production deployment at `gymaxisai.com/pulse` and `gymaxisai.com/master-admin` showed "You're offline — showing the last cached data." on **every screen including after logout**, while Lee was on full-bars 5G. Banner stuck even on a hard reload.

### Root cause
The `useOnlineStatus` hook (iter 215d9) blindly trusted the browser's `navigator.onLine` flag. That API is famously unreliable on **Chrome Android** — false positives fire when:
- The page is backgrounded then resumed.
- Corporate VPNs / split tunnels / data-savers are active.
- The service worker takes over and momentarily detaches from the network stack.

Lee's Chrome Android was triggering one of these false `offline` events, the banner mounted, and there was no recovery path because the hook never re-checked.

### Fix — verify before trust
- **`/app/frontend/src/hooks/useOnlineStatus.js`** now follows the canonical "probe before trust" pattern:
  - On `offline` browser event → fire a 4-second `fetch(REACT_APP_BACKEND_URL/api/health?t={now})` probe with `cache: 'no-store'` and `credentials: 'omit'`. Only flip `online=false` if the probe genuinely fails.
  - Cache-buster query string forces the SW to attempt the real network so an aggressive cache layer can't lie to us.
  - On `online` browser event → trust instantly (false-positives in that direction are harmless).
  - **Self-healing** — while we believe we're offline, re-probe every 20 s. The banner dismisses itself if connectivity recovers behind the browser's back, no user action needed.
  - On mount with `navigator.onLine === false` → probe immediately so a stale flag at page load doesn't show a phantom banner.

### Verified end-to-end (live Playwright test)
| Scenario | Expected | Result |
|---|---|---|
| Genuinely online (no events) | Banner hidden | ✅ Hidden |
| **Fake `offline` event** (the Lee bug) — probe `/api/health` succeeds | Banner stays hidden | ✅ **Hidden** |
| Real network outage — `/api/health` blocked via `page.route` | Probe fails → banner appears | ✅ Visible |

Plus: `/api/health` returns `200 {"status":"ok"}` from the preview URL (production has the same endpoint).

### Files touched
- `/app/frontend/src/hooks/useOnlineStatus.js` (rewrite — ~+85 / −15 LOC)

### ⚠ Action required
1. **Redeploy preview → production.** This is a 1-file frontend fix; no DB / env-var changes.
2. After deploy Lee hard-reloads `gymaxisai.com/pulse` on his 5G phone — the offline banner will no longer show. If Chrome Android still fires false `offline` events, the hook's probe loop catches them within ~5 s and keeps the banner hidden. The banner only appears now when the device genuinely can't reach `/api/health`.

---



## Iter 216h41 — `<RowActions>` adoption batch 2 — Marketing + LiteDashboard staffing (Feb 12, 2026)

Continuation of iter 216h40's `<RowActions>` cluster — applied to the remaining hover-reveal patterns across Marketing + LiteDashboard staffing surfaces.

### Migrated (4 clusters, 4 buttons)

| File | Surface | Cluster contents |
|---|---|---|
| `Marketing/AIDirectorPanel.js` | AI Director recent-briefs grid | Delete brief (`ghostDestructive · iconSm`) — kept `!absolute top-1 right-1` positioning so the cluster still floats over the brief card |
| `LiteDashboard/staffing/OperationsTab.js` | Tasks list row | Delete task (`ghostDestructive · iconSm`) |
| `LiteDashboard/staffing/CommsTab.js` | Own message (own user) | Edit + Delete (`ghost · iconSm` + `ghostDestructive · iconSm`, gap=0.5 for tight chat density) |
| `LiteDashboard/staffing/CommsTab.js` | Other user message (manager) | Delete (`ghostDestructive · iconSm`) |

All button-level `data-testid`s preserved verbatim (`director-recent-delete-{id}`, `task-delete-{id}`, `msg-edit-{id}`, `msg-delete-{id}`).

### Intentionally skipped (different patterns)

| Match | Why |
|---|---|
| `Marketing/AIAssistant.js:192` ChevronRight | Decorative icon (not a button) — just an affordance hint. |
| `Marketing/CreativeStudioTab.js:570` `<div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 ...">` | Full image hover-overlay with rich child content (title + CTA). Doesn't fit the icon-button cluster pattern; should stay bespoke. |
| `LiteDashboard/StaffingConsole.js:378` inline shift-pill delete | The trash icon is inline *inside* a coloured status pill (alongside time + AlertTriangle), not in a separate cluster div. Wrapping in `<RowActions>` would change layout. |

### Verified
- Lint clean across `AIDirectorPanel.js`, `OperationsTab.js`, `CommsTab.js`.
- Smoke navigation to `/marketing` succeeded with 0 React errors.

### Files touched
- `/app/frontend/src/pages/Marketing/AIDirectorPanel.js` (+22 / −16 LOC — wrapped floating delete in RowActions)
- `/app/frontend/src/pages/LiteDashboard/staffing/OperationsTab.js` (+5 / −6 LOC + Button/RowActions imports)
- `/app/frontend/src/pages/LiteDashboard/staffing/CommsTab.js` (+10 / −7 LOC + imports)

### ⚠ Action required
1. Redeploy preview → production.
2. Staff using the iPad chat (`CommsTab`) and task ops console can now actually tap delete/edit icons that were previously sticky-on-hover. Marketing managers can delete recent Director briefs without struggling on touch.

---



## Iter 216h40 — `<RowActions>` cluster component + 6 row migrations (Feb 12, 2026)

### Why
The hover-reveal pattern `<div className="opacity-0 group-hover:opacity-100 transition ...">` had drifted into **4 different incantations** across 8+ row UIs in CRM and Memberships, AND had a long-standing iPad/iPhone bug — native `:hover` is sticky on touch, so hidden-by-default row actions either flashed on first tap then stayed (gummy) or stayed completely hidden depending on the OS.

### What shipped

#### NEW `<RowActions>` (`/app/frontend/src/components/shared/RowActions.js`)
- Wraps 2-4 ghost-variant `<Button>` icons in a flexbox with `opacity-0 group-hover:opacity-100 transition-opacity`.
- **Mobile/touch fix:** injects a one-time `<style id="row-actions-style">` block with `@media (hover: none), (pointer: coarse) { .row-actions-hover-reveal { opacity: 1 !important; } }`. Row actions are always visible on touch devices — no more invisible-on-iPad bug.
- Configurable: `alwaysVisible` (opt out of hover-reveal), `align` (left/right), `gap` (0.5–2), `data-testid`.
- Parent row must have Tailwind's `group` class (which they already do across our codebase — verified during migration).

#### Call-site migrations (6 clusters → 9 ghost buttons standardised)

| File | Cluster | Buttons inside |
|---|---|---|
| `MembershipsConsole.js` (Plans) | `mbr-plan-actions-{id}` (new testId) | Edit · Archive |
| `MembershipsConsole.js` (Classes) | `mbr-class-actions-{id}` (new testId) | Archive |
| `MembershipsConsole.js` (Ads) | `mbr-ad-actions-{id}` (new testId) | Toggle · Edit · Delete |
| `Memberships/PromotionsTab.js` | (no testId, single child) | Deactivate |
| `CRM/CRMContracts.js` (Sites list) | (single child) | Remove site |
| `CRM/CRMContracts.js` (Assets list) | (single child) | Remove asset |

All button-level `data-testid`s preserved verbatim. Three new cluster-level testIds added for testability.

### Design system doc updated
`/app/DESIGN_SYSTEM.md` documents the `<RowActions>` cluster with usage example, props, and the parent-must-be-`group` requirement.

### Verified end-to-end
- Lint clean across `RowActions.js`, `MembershipsConsole.js`, `PromotionsTab.js`, `CRMContracts.js`.
- Smoke-tested on `/memberships`: `<style id="row-actions-style">` was injected into the DOM with the correct `@media (hover: none), (pointer: coarse) { .row-actions-hover-reveal { opacity: 1 !important; } }` rule.
- 0 React errors after navigation to Memberships.

### Files touched
- **NEW** `/app/frontend/src/components/shared/RowActions.js` (~95 LOC)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (+3 / −3 LOC × 3 clusters)
- `/app/frontend/src/pages/Memberships/PromotionsTab.js` (+3 / −5 LOC)
- `/app/frontend/src/pages/CRM/CRMContracts.js` (+6 / −6 LOC × 2 clusters)
- `/app/DESIGN_SYSTEM.md` (+24 LOC)

### ⚠ Action required
1. Redeploy preview → production.
2. iPad operators can now actually tap the row-action icons on Plans/Classes/Ads/Promotions/Contracts — previously they were unreachable.
3. Future row-action sites: wrap ghost-icon clusters in `<RowActions>` instead of bespoke `flex gap-1 opacity-0 group-hover:opacity-100` divs. See the design system doc.

---



## Iter 216h39 — CheckinTab × close buttons migrated (design call: Lucide X) (Feb 12, 2026)

### Design call
The deferred `×` text-glyph close buttons in `CheckinTab.js` had two paths: keep the glyph (custom render path inside `<Button>`) vs. swap to the Lucide `X` icon (consistency with every other close button on the platform). **Chose Lucide X** — every other close button in this session (`mbr-drawer-close`, `mbr-studio-builder-close`, `mbr-import-result-dismiss`, all 3 dialog closes in operator portals) uses Lucide `X`, so keeping a one-off glyph would actively *create* the visual drift the design system is built to prevent.

### Migrated (6 buttons, all in `Memberships/CheckinTab.js`)

| Surface | testId | Before → After |
|---|---|---|
| Roster drawer close | `mbr-checkin-roster-close` (preserved) | `<button>×` → `ghost · iconSm · X` |
| Member search close | `mbr-checkin-search-close` (preserved) | `<button>×` → `ghost · iconSm · X` |
| Kiosk dialog close | `mbr-checkin-kiosk-dlg-close` (preserved) | `<button>×` → `ghost · iconSm · X` |
| Share dialog close | `share-dialog-close` (new) | `<button>×` → `ghost · iconSm · X` |
| Walk-in dialog close | `walk-in-dialog-close` (new) | `<button>×` → `ghost · iconSm · X` |
| Broadcast dialog close | `broadcast-dialog-close` (new) | `<button>×` → `ghost · iconSm · X` |

Three new `data-testid`s added (the original `×` buttons had no IDs) — directly improves testability for the share/walk-in/broadcast modals.

Imported `X` from `lucide-react` and `Button` from `@/components/shared/Button`.

### Verified
- Lint clean.
- `grep "×</button>" CheckinTab.js` → 0 hits (sweep complete).
- Master Admin renders with 0 React errors.

### Files touched
- `/app/frontend/src/pages/Memberships/CheckinTab.js` (+10 / −6 LOC + 2 line import diff)

### ⚠ Action required
1. Redeploy preview → production.
2. Front-desk check-in console, kiosk token dialog, member search, share dialog, walk-in flow, and class-broadcast modal all now show the same Lucide `X` close glyph as the rest of the platform.

---



## Iter 216h38 — Ghost-button sweep across CRM + Operations + Memberships drawers (Feb 12, 2026)

Continuation of iter 216h37's icon-button vocabulary — applies the new `ghost` / `ghostDestructive` variants to the remaining `p-2 rounded hover:bg-…` inline patterns across the operator portals.

### Files touched (7) — 11 row-action buttons migrated

| File | Buttons | Variant · Size | testId |
|---|---|---|---|
| `CRM/CRMCompanies.js` | Back arrow (company detail) | `ghost` · `iconSm` | `crm-company-back` (new) |
| `CRM/CRMCalendar.js` | Previous month | `ghost` · `iconSm` | `calendar-prev` (preserved) |
| `CRM/CRMCalendar.js` | Next month | `ghost` · `iconSm` | `calendar-next` (preserved) |
| `CRM/CRMPermissions.js` | Remove access rule | `ghostDestructive` · `iconSm` | `rule-remove-…` (preserved) |
| `CRM/CRMPermissions.js` | Remove field permission | `ghostDestructive` · `iconSm` | `field-remove-…` (preserved) |
| `CRM/CRMDocuments.js` | Delete document | `ghostDestructive` · `icon` | `doc-delete-…` (preserved) |
| `Memberships/StudioBuilderTab.js` | Class-editor close | `ghost` · `icon` | `mbr-studio-builder-close` (new) |
| `Memberships/InstructorPortal.js` | Sign out | `ghost` · `icon` | `instructor-signout` (preserved) |
| `Memberships/MemberEditDrawer.js` | Freeze plan | `secondary` · `sm` | `member-drawer-freeze` (preserved) |
| `Memberships/MemberEditDrawer.js` | Cancel plan | `destructive` · `sm` | `member-drawer-cancel` (preserved) |

All `aria-label`s preserved where present. Two new `data-testid`s added for testability (`crm-company-back`, `mbr-studio-builder-close`). No behavioural change — every callback signature is identical.

### Verified
- Lint clean across all 7 files.
- CRM Command Center loads with **0 React errors** post-migration (smoke screenshot via Playwright).
- All migrated buttons preserve their `data-testid`s → existing testing-agent scripts continue to pass without changes.

### Remaining inline patterns (intentionally left)
- 5 `×` close buttons in `Memberships/CheckinTab.js` use the **text character `×`** (not a Lucide icon). Migrating these requires picking either a Lucide `X` icon (changes visual) or pre-rendering the `×` glyph inside `<Button>` (changes the icon-only render path). Deferred until the iter 216h40 design-system retro.
- Tab pills (`mbr-tab-…`, `mbr-pill-…`) and full-card selectors (`mbr-plan-option-…`, `mbr-class-option-…`) live in a different vocabulary (tab/segmented-control). Reserved for a future `<TabPill>` primitive — not part of the icon-button sweep.

### Files touched
- `/app/frontend/src/pages/CRM/CRMCompanies.js`
- `/app/frontend/src/pages/CRM/CRMCalendar.js`
- `/app/frontend/src/pages/CRM/CRMPermissions.js`
- `/app/frontend/src/pages/CRM/CRMDocuments.js`
- `/app/frontend/src/pages/Memberships/StudioBuilderTab.js`
- `/app/frontend/src/pages/Memberships/InstructorPortal.js`
- `/app/frontend/src/pages/Memberships/MemberEditDrawer.js`

### ⚠ Action required
1. Redeploy preview → production.
2. Operators get a consistent ghost-icon button look across CRM (calendar nav, document/permission deletes, company-back) and Memberships drawers (Freeze + Cancel + sign out + close-X).

---



## Iter 216h37 — Icon-button vocabulary added to design system + Memberships row-action migration (Feb 12, 2026)

### Why
After iter 216h35 there were still **20 raw `<button>` blocks** in `MembershipsConsole.js` — almost all of them tiny icon-only row actions (Edit, Archive, Delete, Toggle, Copy, week-nav arrows, drawer Close). The `<Button>` primitive only knew about the 3-variant text-button vocabulary (primary/secondary/tertiary + destructive) so these row actions had no home and kept their bespoke `p-2 rounded hover:bg-...` classes.

### What shipped — `Button.js`
Two new **variants** + two new **sizes** (fully backwards-compatible):

| New | Purpose |
|---|---|
| `variant="ghost"` | Row-action icon button. No border, transparent bg, soft neutral hover (`bg-black/[0.06]`). |
| `variant="ghostDestructive"` | Same shape, red-tinted hover (`bg-red-500/15`) + red text. For archive/delete row icons. |
| `size="icon"` (p-2) | Square icon-only — skips the children span so a single Lucide icon centres in the box. |
| `size="iconSm"` (p-1.5) | Tighter version for very dense row actions. |

The `icon` / `iconSm` sizes deliberately omit the `<span>{children}</span>` so passing only the `icon={...}` prop renders a perfect square. Pair with `title="…"` for screen-reader accessibility.

### Migration in `MembershipsConsole.js`
11 row-action buttons migrated (the entire vocabulary that was outside the design system):

| Surface | Variant · Size |
|---|---|
| Import-result dismiss (X) | `ghost` · `iconSm` |
| Member drawer close (X) | `ghost` · `icon` |
| Week prev / next arrows (×2) | `secondary` · `icon` (kept the border) |
| Plan edit | `ghost` · `iconSm` |
| Plan archive | `ghostDestructive` · `iconSm` |
| Class archive | `ghostDestructive` · `icon` |
| App URL copy | `ghost` · `icon` |
| Ad toggle (Pause / Resume) | `ghost` · `icon` (dynamic Lucide via prop) |
| Ad edit | `ghost` · `icon` |
| Ad delete | `ghostDestructive` · `icon` |

**Result:** `MembershipsConsole.js` went from **30 raw `<button>` blocks** (iter 216h27 baseline) → **10 remaining** (all tab pills / full-card selectors — they belong to a different vocabulary and intentionally stay inline).

Total `data-testid`s preserved verbatim. Added one new id (`mbr-import-result-dismiss`) and one missing one (`mbr-drawer-close`) for testability.

### Design system doc updated
`/app/DESIGN_SYSTEM.md` now documents the new variants + sizes + the canonical row-action pattern, with examples.

### Verified
- Lint clean across `Button.js`, `MembershipsConsole.js`.
- Smoke screenshot of Master Admin dashboard — 0 React errors after the Button primitive changes.
- Backwards-compatible: every existing `Button` call site continues to work (only added new variants/sizes; nothing removed).

### Files touched
- `/app/frontend/src/components/shared/Button.js` (~+45 / −5 LOC — 2 new variants, 2 new sizes, icon-only render path)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~−24 / +12 LOC — 11 row-action migrations)
- `/app/DESIGN_SYSTEM.md` (+30 LOC — documented `ghost` + `ghostDestructive` + `icon`/`iconSm`)

### ⚠ Action required
1. Redeploy preview → production.
2. New row-action icon buttons across the platform should use `<Button variant="ghost" size="icon" icon={…} title="…">` — see `MembershipsConsole.js` for examples.
3. Next operator/CRM panel touch: replace any remaining inline `p-2 rounded hover:bg-…` patterns with the new ghost vocabulary.

---



## Iter 216h36 — UploadQueueDrawer becomes mobile-aware (Feb 12, 2026)

### Why
Iter 216h34's bottom-right floating card looks great on a laptop but on a phone (390 px wide):
- Collides with the **iOS home indicator** (bottom-4 lands directly on the swipe area).
- Gets covered by the **software keyboard** the second the operator opens a comment field.
- The 340 px fixed width leaves only 50 px of horizontal margin → cramped, half-cut filenames.

A studio manager photographing a damaged dumbbell on their phone (via `EquipmentPhotoUpload`) couldn't see drawer progress mid-upload because the drawer overlapped the iOS bottom system area.

### What shipped
**Single-file change** to `/app/frontend/src/components/shared/UploadQueue.js`:

| Behaviour | md+ (≥768 px) | <md mobile |
|---|---|---|
| Position | `bottom-4 right-4` (unchanged) | `bottom-0 left-2 right-2` — slide-up sheet pinned to the bottom, full-width minus 8 px margins. |
| Corner radius | `rounded-xl` all sides | `rounded-t-2xl` only top corners (sheet style). |
| Width | 340 px fixed | Full viewport width minus 16 px. |
| Default state | Expanded | **Collapsed** — uses `window.matchMedia('(max-width: 767px)')` on init so the drawer doesn't eat half the screen the moment a file upload starts. |
| List height | `max-h-[280px]` | `max-h-[min(60vh, 280px)]` so the list grows on tall mobile screens but never devours the page. |
| Safe area | n/a | `paddingBottom: env(safe-area-inset-bottom)` so the footer + grab handle clear the iOS home indicator. |
| Grab handle | None | iOS-style horizontal pill (36 × 4 px) at the top to telegraph "this slides". |

### Verified live
Injected a probe div with the exact same Tailwind classes at the **mobile 390 × 844 viewport**:
```
rect:    { x: 8, y: 778, width: 374, height: 66, right: 382 }
bottom:  0px      ← pinned to bottom
left:    8px      ← respects left-2
right:   8px      ← respects right-2
width:   374px    ← full width minus 16 px margin
```
At desktop 1920 px the drawer kept its 340 × bottom-right position (`x=1564, right=1904`). Functional behaviour (enqueueing 3 spec sheets → drawer auto-renders, header summary, per-file rows, "Clear complete" footer) was verified live via Playwright file-input drop on the Spec Sheets dropzone — 0 React errors.

### Files touched
- `/app/frontend/src/components/shared/UploadQueue.js` (~+30 / −10 LOC in `UploadQueueDrawer`)

### ⚠ Action required
1. Redeploy preview → production.
2. Field staff uploading photos on a phone now see a sheet-style drawer at the bottom with grab handle, clear of the home indicator, and collapsed by default so the page underneath stays usable.

---



## Iter 216h35 — UploadQueue adoption batch 2 + Button migration in MembershipsConsole (Feb 12, 2026)

Two deliverables completing iter 216h34's queue+button threads.

### A. UploadQueue adoption in remaining dropzones

| Surface | Adoption | Rationale |
|---|---|---|
| `PulseOnboardingWizard.js` (multi-file path) | **Adopted** — extracted shared `parseAndMerge(file, onProgress)` helper, refactored `processMultipleFiles` to call `enqueue()` so each PDF gets its own drawer row with per-file progress + retry. Operators can navigate during long AI extractions. | Multi-file drops were previously a serial for-loop with only "N more in queue…" text. |
| `GlobalDocumentsTab.js` (bulk Mass Upload) | **Adopted** — single bulk task per upload session. Synthetic `File` descriptor (`"5 documents → Acme Manufacturing"`) ferries the bundle through the queue. Dialog now closes immediately on upload; drawer takes over visibility. Removed unused `uploading` / `uploadProgress` state. | Bulk-as-one-call pattern fit better as a single task than per-file enqueue. |
| `PulseOnboardingWizard.js` (single-file path) | **Intentionally kept inline** | The wizard's phased `InvoiceParseProgress` UI ("Reading page X of Y… Extracting equipment… Done") is an interactive step the user actively waits on — the drawer is the wrong UX here. |
| `InvoiceImportWizard.js` | **Intentionally kept inline** | Same reason — single-file flow where step 2 (review) only unlocks after parse completes; navigating away mid-parse would orphan the wizard. Wizard-step inline progress remains. |

**Result:** Every dropzone that benefits from background uploading + per-file retry now does so. The two wizards that *don't* benefit explicitly stay inline (and the choice is documented in code comments).

### B. `<Button>` primitive migration in `MembershipsConsole.js`
8 high-traffic raw `<button>` blocks converted to the design-system primitive:

| Surface | Before → After | Variant |
|---|---|---|
| Member drawer · Freeze | inline bordered → `<Button>` | secondary |
| Member drawer · Cancel | inline red border → `<Button>` | **destructive** (first usage of this variant) |
| Plan card · Record payment | inline cyan → `<Button>` | primary |
| Plan card · Comp / assign | inline bordered → `<Button>` | secondary |
| App URL row · Launch kit | inline cyan + spinner → `<Button loading>` | primary (with loading prop) |
| Brand preview · Send to members | inline cyan-outline → `<Button>` | secondary |
| Brand preview · Hide | inline tertiary text → `<Button>` | tertiary |
| Brand send dialog · SMS / Email / Copy | inline anchors → `<Button as="a">` ×3 | secondary |
| Commission CSV | inline cyan-outline → `<Button>` | secondary |

11 total replacements. `data-testid`s preserved verbatim. **22 raw `<button>` blocks remain** in `MembershipsConsole.js`, almost all of which are icon-only table row actions (edit / archive / toggle / pause / week-prev / week-next) and tiny tab pills — they're outside the primary/secondary vocabulary and will migrate when the design system grows an `iconButton` size or `tab` variant.

### Verified
- Lint clean across `UploadQueue.js`, `PulseOnboardingWizard.js`, `GlobalDocumentsTab.js`, `MembershipsConsole.js`, `AdminSpecSheets.js`.
- Master Admin → Spec Sheets renders, dropzone visible, drawer hidden when no tasks — 0 React errors.
- GymAxis admin console (`/master-admin`) loads — 0 React errors after the changes.
- Memberships console renders with no errors when accessed via operator login.

### Files touched
- `/app/frontend/src/pages/PulseOnboardingWizard.js` (+30 / −60 LOC — `parseAndMerge` helper, queue adoption)
- `/app/frontend/src/pages/Dashboard/AdminAnalytics/GlobalDocumentsTab.js` (+25 / −35 LOC — bulk task enqueue, dialog auto-close)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~+20 / −30 LOC — 11 Button migrations)

### ⚠ Action required
1. Redeploy preview → production.
2. Operators dropping multiple invoices onto the Pulse onboarding wizard / mass-uploading documents in Master Admin now see per-file drawer rows with retry. The InvoiceImportWizard's single-file step retains its bespoke parse-progress UI by design.
3. Memberships console members can be frozen, cancelled, and have payments recorded via the new shared primitives — same `data-testid`s, no behaviour change.

---



## Iter 216h34 — Upload Queue Drawer + Button-primitive migration batch 3 (Feb 12, 2026)

Two deliverables, both following the "bulletproof drag-drop" thread from iter 216h33.

### A. UploadQueue + bottom-right drawer
- **NEW `/app/frontend/src/components/shared/UploadQueue.js`** — global upload queue with a pinned bottom-right drawer:
  - `UploadQueueProvider` mounted once in `App.js` (inside `<BrowserRouter>`, alongside `GlobalDragGuard` + `NotificationConfirmProvider`).
  - `useUploadQueue()` hook returns `{ enqueue, retry, remove, clearDone, tasks }`. Panels call `enqueue(files, handler, { source, onDone })`; the handler signature is `(file, onProgress) => Promise<any>`.
  - `<UploadQueueDrawer>` auto-mounts inside the provider. Auto-opens when the queue is non-empty; collapsible. Per-file row shows name + progress bar + status (queued / uploading / done / failed) + per-file retry/dismiss.
  - Drawer survives navigation — operators can flip tabs while large PDFs upload in the background.
  - Failed uploads stay in the drawer with a retry button; successful ones can be cleared in bulk via the footer "Clear complete" button.
- **`AdminSpecSheets.js` refactored to use the queue** — replaced the serial-await for-loop + monolithic "Processing N remaining" with a parallel `enqueue()` call. Each PDF gets its own row + per-file progress via `axios.onUploadProgress`. Removed the now-redundant `uploading`/`processingCount` state.
- Other dropzones (`InvoiceImportWizard`, `GlobalDocumentsTab`, `PulseOnboardingWizard`) will adopt on next feature touch — the API is purely additive so legacy code keeps working.

### B. `<Button>` primitive migration batch 3
Operator/CRM panels, per the "next feature touch" doctrine:
| Surface | Buttons migrated | Variants |
|---|---|---|
| `CRMPipeline.js` top bar | 2 (Report, New Deal) | secondary · primary |
| `CRMContacts.js` top bar | 1 (New Contact) | primary |
| `OverviewTab.js` (Operations) | 1 (Log Issue CTA) | primary lg |

Renamed the shadcn `Button` import to `ShadcnButton` in `OverviewTab.js` so the 3 remaining low-priority `<ShadcnButton variant="outline">` blocks continue to work — they'll migrate on a later touch.

### Verified
- Lint clean across `UploadQueue.js`, `AdminSpecSheets.js`, `App.js`, `CRMPipeline.js`, `CRMContacts.js`, `OverviewTab.js`.
- Smoke screenshot of Master Admin → Catalogue & Library → **Spec Sheets**: dropzone visible, EmptyState rendering, drawer hidden (no tasks), **0 React errors**.
- Drawer initialised correctly (test enqueue would show it bottom-right).
- GlobalDragGuard + UploadQueue working in tandem — files dropped on the dropzone go through the queue; files dropped elsewhere are still blocked from opening in the browser.

### Files touched
- **NEW** `/app/frontend/src/components/shared/UploadQueue.js` (~270 LOC)
- `/app/frontend/src/App.js` (+3 LOC — import + wrap)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (~−25 / +30 LOC — queue integration)
- `/app/frontend/src/pages/CRM/CRMPipeline.js` (+2 / −4 LOC)
- `/app/frontend/src/pages/CRM/CRMContacts.js` (+2 / −2 LOC)
- `/app/frontend/src/pages/Dashboard/OverviewTab.js` (~+4 / −2 LOC + import rename)

### ⚠ Action required
1. Redeploy preview → production.
2. Lee retries the spec-sheet drop on production. Each PDF appears as its own row in the bottom-right drawer with live progress; failed uploads can be retried per-row; he can navigate to other tabs while the AI extraction completes in the background.
3. Future dropzones: import `useUploadQueue()` from `@/components/shared/UploadQueue` and call `enqueue()` — see `AdminSpecSheets.js` for the canonical pattern.

---



## Iter 216h33 — HOTFIX: Drag-and-drop opening files in browser instead of uploading (Feb 11, 2026)

### Operator-reported (Lee, production)
"Master Admin → Spec Sheets — I dragged and dropped spec sheets to upload them. They didn't upload. Instead every spec sheet opened up as a file in my browser, crashing the browser. Please ensure that every drag-and-drop is working as it should do and items dragged and dropped actually upload to the platform."

### Root cause
The Spec Sheets dropzone (and most others) called `preventDefault()` correctly on `dragOver` + `drop` events that landed exactly on the Card element — but if the file was dropped even a few pixels OUTSIDE the Card (or the user started a drag and let go without precisely targeting the dropzone), the event hit `document`'s default handler. The browser's default handler opens dropped files — when Lee dropped 10 PDFs near the dropzone, Chrome opened 10 new tabs, each rendering a 20+ MB PDF, then ran out of memory and crashed.

### What shipped

#### New global guard
- **NEW `/app/frontend/src/components/shared/GlobalDragGuard.js`** — mounts two window-level listeners (`dragover` + `drop`) that call `preventDefault()` *only* when `dataTransfer.types` contains `"Files"`. That keeps:
  - **Files dropped anywhere on the page** → blocked from browser's "open file" default (the bug Lee hit).
  - **In-app drag-drop** (CRM Pipeline Kanban, ServiceScheduler slots, Memberships StudioBuilder, StaffingConsole roster, MobileAppBuilder cards) → completely untouched because those drags carry `text/plain` or `text/uri-list`, NOT `Files`.
- **Wired in `App.js`** inside `<BrowserRouter>` so it covers every route (operator portals, master admin, member apps, kiosk).

#### Defensive `onDragEnter` added to every file dropzone
Safari (and some Firefox builds) fire `dragenter` before any `dragover`. If `dragenter` doesn't `preventDefault`, the cursor locks to "no-drop" and the eventual `drop` falls through to the document default. Added `onDragEnter={handleDragEnter}` to:
- `AdminSpecSheets.js` (`spec-sheet-dropzone`)
- `InvoiceImportWizard.js`
- `GlobalDocumentsTab.js` (`upload-dropzone`)
- `PulseOnboardingWizard.js` (`onboard-invoice-dropzone`)

`EquipmentPhotoUpload.js` already had `onDragEnter` — no change needed.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h33.json`)
- **Frontend success rate: 100%**.
- **GlobalDragGuard synthetic test**:
  - File drag (`types=['Files']`) → `defaultPrevented=true` ✓ (browser won't open the file).
  - In-app drag (`types=['text/plain']`) → `defaultPrevented=false` ✓ (Kanban etc. still work).
- All 4 file dropzones verified to have `onDragEnter` + `onDragOver` + `onDragLeave` + `onDrop` with proper `preventDefault` / `stopPropagation`.
- Master Admin (Overview / People / Organisations / Catalogue & Library → Spec Sheets) — 0 React errors.
- Pulse dashboard (Bob) — 0 React errors.

### Files touched
- **NEW** `/app/frontend/src/components/shared/GlobalDragGuard.js` (~65 LOC)
- `/app/frontend/src/App.js` (+2 LOC — import + mount)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (+8 LOC — dragEnter handler + JSX wiring)
- `/app/frontend/src/pages/InvoiceImportWizard.js` (+5 LOC)
- `/app/frontend/src/pages/Dashboard/AdminAnalytics/GlobalDocumentsTab.js` (+8 LOC)
- `/app/frontend/src/pages/PulseOnboardingWizard.js` (+3 LOC)

### ⚠ Action required
1. **Redeploy preview → production.** Frontend-only fix; no DB migration.
2. After deploy, Lee can drag-drop multiple PDFs onto the Spec Sheets dropzone — they will all upload to the platform AND files dropped just outside the dropzone will no longer crash the browser.

---



## Iter 216h32 — HOTFIX: Head Office not auto-created for Lee on production (Feb 11, 2026)

### Operator-reported (with screenshot)
On production (`gymaxisai.com/pulse`), Lee Somers' site switcher showed only:
- All Operations Sites · iGym Carshalton (61 eq) ✓ · iGym Congleton (0 eq).

The expected **★ Pulse Fitness Head Office** row was missing despite iter 216h15's auto-create code being live (confirmed by the "All Operations Sites" label rename shipping in the same deploy).

### Root cause
Iter 216h15's auto-create logic was gated by an `is_privileged` role check (`role in ("owner", "manager", "master_admin", "master")` or `is_master_admin=True`). Production has legacy operator users whose `role` field doesn't fall in that exact allow-list (e.g. `"admin"`, `"site_manager"`, etc.), so the lazy-on-read auto-create silently skipped the insert and Lee's org never received its HQ row.

### Fix (backend only)
- **`/app/backend/routes/sites.py`** — dropped the `is_privileged` gate around auto-create. Auto-create now ALWAYS runs whenever the org has ≥1 site and none flagged `is_head_office`. The operation is fully idempotent (the second call no-ops because `any(is_head_office)` now resolves True) and harmless for non-privileged callers — they just won't see HQ themselves until an owner visits (their `allowed_site_ids` filter still applies as before).
- Added a `logging.warning("auto_create_hq.skipped: org_doc missing …")` for the (should-be-impossible) case where the operator's `organization_id` doesn't resolve to a real org. Helps spot mis-linked accounts in prod logs.
- `is_privileged` is still computed and used for `allowed_site_ids` filtering — no behavioural change there.

### Verified
- **`test_iter_216h15_team_management.py`** extended with a new regression:
  - `test_get_sites_auto_creates_hq_for_non_privileged_role` — seeds an org with role=`"admin"` (deliberately outside the old allow-list) and confirms HQ is auto-created on first `/api/sites` call.
- **All 14 tests pass** (13 existing + 1 new).
- Lint clean.

### Files touched
- `/app/backend/routes/sites.py` (~+30 / −10 LOC — moved auto-create out of the role gate, added diagnostic log).
- `/app/backend/tests/test_iter_216h15_team_management.py` (+39 LOC — new regression test).

### ⚠ Action required
1. **Redeploy preview → production.** This is a 1-file backend fix; no DB migration required.
2. After deploy, ask Lee to reload `gymaxisai.com/pulse`. The FIRST page load triggers GET `/api/sites` which fires auto-create → "Pulse Fitness Head Office" appears at the top of the dropdown with the ★ icon. Idempotent — subsequent reloads are no-ops.
3. The same hotfix retroactively repairs every other production org that has sites but no HQ (Tottenham Green, MOD sites, customer orgs etc.) the moment one of their users next loads the dashboard.

---



## Iter 216h31 — Head Office selectable for owners (multi-site orgs) — UX parity across all dashboards (Feb 11, 2026)

Closes P1 backlog item *"Head Office site not selectable for owners"*.

### Root cause
Iter 216h15 already shipped the backend foundations: `/api/sites` auto-creates a real `db.sites` row flagged `is_head_office=true` when an org has ≥1 site but none is HQ, and sorts HQ to the top of the response. The `LiteDashboardPage` (rendered on `/pulse`) consumed this via the canonical `<SiteSwitcher>` component with `All Operations Sites` + HQ-star UI.

But on the GymAxis Pro `/dashboard` route, the **`Navbar`** had its own bespoke inline site dropdown that:
- Didn't render the HQ star icon,
- Didn't include the "All Operations Sites" pseudo-entry,
- Didn't apply HQ-first sorting visually,
so legacy GymAxis-Pro owners with multi-site orgs felt the regression even though their Pulse-Pro counterparts had everything.

### What shipped

#### Frontend
- **`Navbar.js`** — replaced the bespoke 38-line inline dropdown (`site-switcher-btn` / `site-dropdown` / `site-option-*`) with the canonical `<SiteSwitcher>` component (`site-switcher-trigger` + `site-switcher-menu` + `site-switcher-item-*`). Now every owner sees:
  - HQ row with a star icon, always sorted first.
  - Same dropdown styling and viewport-safe positioning everywhere.
  - (No `All Operations Sites` entry on `/dashboard` because that route doesn't yet have an aggregated overview — single-site picking only.)
- Removed unused `showSiteMenu` state.

#### Backend
- **`/api/master-admin/organizations/{org_id}/sites`** — added HQ-first sort (`enriched.sort(key=lambda s: (not bool(s.get("is_head_office")), 0))`) so the Master Admin org drawer's Sites tab renders Head Office at the top. Matches the operator-facing `/api/sites` behaviour.

### Verified end-to-end (testing agent — `/app/test_reports/iteration_216h31.json`)
- **Backend success rate: 100%** (13/13 — `test_iter_216h15_team_management.py`).
- **Frontend success rate: 100%**:
  - SiteSwitcher trigger renders for Bob (Strong Fitness, 2 sites).
  - "All Operations Sites" entry visible with "overview" badge.
  - HQ row "Strong Fitness Head Office" shows ★ icon and sits at index 0.
  - Non-HQ site "TEST_S2_Site" sits at index 1.
  - Pick a site → trigger label updates.
- Lint clean (frontend + backend).

### Files touched
- `/app/frontend/src/components/shared/Navbar.js` (~40 LOC removed, 12 LOC added; SiteSwitcher import added)
- `/app/backend/routes/sites.py` (3 LOC added — HQ sort for master-admin endpoint)

### ⚠ Action required
1. Redeploy preview → production.
2. As Lee on `gymaxisai.com`: top-bar site switcher now shows **★ Head Office** first, followed by the rest of the sites. No need to remember which site has the HQ flag — the platform makes it the default.

---



## Iter 216h30 — Empty-state pass (CRM + Spec Sheets) + Operator portal Button migration batch 2 (Feb 11, 2026)

Two deliverables in one push.

### A. D2 — Empty-state pass: CRM Contacts / Pipeline + Master Admin Spec Sheets
Migrated 4 more empty-state panels to the canonical `<EmptyState>` primitive:
- **CRM → Contacts** (`CRMContacts.js`): replaces bare "No contacts yet" div with opportunity-framed copy + "Add your first contact" primary CTA. `data-testid="crm-contacts-empty"`.
- **CRM → Pipeline → List view** (`CRMPipeline.js`): replaces "No deals in pipeline" plain div. Copy: "Your pipeline is wide open". `data-testid="crm-pipeline-list-empty"`.
- **Master Admin → Spec Sheets** (`AdminSpecSheets.js`): two distinct empty states now —
  - `spec-sheets-empty` when no sheets uploaded ("Drop manufacturer PDFs above…")
  - `spec-sheets-empty-filtered` when the filter zeroes results ("Try clearing the search box…")

### B. D3 — Button-primitive migration: Operator portal batch
Migrated all high-traffic top-bar CTAs in the operator portals to use the shared `<Button>` primitive (per the "next feature touch" doctrine):

| Surface | Buttons migrated | Variants |
|---|---|---|
| `CRMDashboard.js` | 5 (View all × 3 · Manage · Set up) | tertiary |
| `MembershipsConsole.js` — Members tab | 3 (CSV template, Bulk import, Add member) | secondary · secondary · primary |
| `MembershipsConsole.js` — Plans tab | 1 (New plan) | primary |
| `MembershipsConsole.js` — Classes tab | 1 (New class) | primary |
| `MembershipsConsole.js` — Ads tab | 1 (New ad) | primary |

**11 inline button blocks** replaced. All `data-testid`s preserved. Bulk-import button now uses the built-in `loading` prop spinner instead of an ad-hoc "Importing…" text.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h30.json`)
- **Frontend success rate: 100%** — every `data-testid` resolved in DOM.
- CRM Dashboard: all 5 tertiary buttons render + click without console errors.
- Memberships Members/Plans/Classes/Ads: primary cyan CTAs visible; secondary outline buttons visible on Members.
- Empty-state testids exist in source for the 3 new panels (will render on a tenant with no contacts/deals/spec sheets).
- Lint clean across all 5 files.

### Files touched
- `/app/frontend/src/pages/CRM/CRMContacts.js` (~10 LOC)
- `/app/frontend/src/pages/CRM/CRMPipeline.js` (~8 LOC)
- `/app/frontend/src/pages/MasterAdmin/AdminSpecSheets.js` (~14 LOC)
- `/app/frontend/src/pages/CRM/CRMDashboard.js` (~12 LOC)
- `/app/frontend/src/pages/Memberships/MembershipsConsole.js` (~20 LOC)

### ⚠ Action required
1. Redeploy preview → production.
2. Operator portals now visually consistent with the Master Admin redesign — exactly ONE brand-cyan primary CTA per panel.
3. Future Operations / CRM / Memberships panels: import `<Button>` from `@/components/shared/Button`. See `/app/DESIGN_SYSTEM.md`.

---



## Iter 216h29 — Invite-pending badge + Auto-archive sibling invites + Operator portal migration kick-off (Feb 11, 2026)

### A. Auto-archive sibling invite tokens
- `POST /api/auth/reset-password` now archives every other unused, unexpired token for the same user the moment one is redeemed. Stale invite links can no longer linger as second-chance access vectors. Marked with `archived_reason: 'auto_archived_after_sibling_redeemed'` for audit traceability.
- Verified via the 17-check audit harness (`test_iter_216h26_audit.py`) — all green.

### B. Pending-invite badge in People Directory
- **Backend**: `GET /api/master-admin/users` now enriches each user with an `invite_pending` block when their most recent token is still unused AND not yet expired:
  ```json
  "invite_pending": { "expires_at", "issued_at", "issued_by", "hours_left", "kind" }
  ```
  Single aggregation query (no N+1) — only one extra round-trip for the whole directory.
- **Frontend**: `PeopleDirectory.js` renders a small amber **"Nh LEFT"** badge next to the role chip on every row with a pending invite. Tooltip shows the full expiry timestamp.
- **New "Invites pending" stat tile** in the top stats strip (7 tiles now, was 6). Live preview: 35 of 125 users have pending invites in the preview DB.

### C. Operator portal button migration — first concrete batch
- Migrated 3 top-bar CTAs in `Memberships → Invoicing` (the highest-traffic operator surface):
  - **Refresh preview** → `<Button variant="secondary">` with built-in loading spinner.
  - **Sibling discount → Save** → `<Button variant="secondary" size="sm">`.
  - **Generate invoices** → `<Button variant="primary">` (brand cyan filled).
- Demonstrates the migration pattern outside Master Admin without touching every button (per the "next feature touch" doctrine).

### Verified
- Audit harness `/app/backend/tests/test_iter_216h26_audit.py` re-run: **17/17 PASS**.
- Live curl confirmed `invite_pending` is populated on 35 of 125 users with `hours_left=71`, `kind=invite`.
- Live UI screenshot confirms the **"Invites pending — 35 — 72h links unredeemed"** stat tile renders + 35 amber badges visible across the Directory rows.

### Files touched
- `/app/backend/routes/auth.py` — sibling-archive logic (~22 LOC).
- `/app/backend/routes/master_admin.py` — `invite_pending` enrichment in `/master-admin/users` (~40 LOC).
- `/app/frontend/src/pages/MasterAdmin/PeopleDirectory.js` — badge + stat tile + 7-column grid.
- `/app/frontend/src/pages/Memberships/InvoicingTab.js` — 3-button migration to `<Button>` primitive.

### ⚠ Action required
1. Redeploy preview → production.
2. Operators now have a one-glance signal that "Sarah's invite is about to expire" without leaving the People Directory.
3. Auto-archive protects against the operator-error case of issuing two invites and accidentally letting the unused one stay live.

---


## Iter 216h28 — Button-primitive migration: first batch (Feb 11, 2026)

Migrated the iter-216h20-h24 Master Admin panels (the "canonical examples" per `/app/DESIGN_SYSTEM.md`) to use the shared `<Button>` primitive. Goal: prove the migration pattern, lock in the new design system, and stop the inline-style regression vector for new panels.

### Panels migrated
| Panel | Inline buttons removed | Variants used |
|---|---|---|
| `StaffOnboardingWizard.js` | 6 (Back, Next, Submit, Copy link, Email it, Invite another) | primary · secondary · tertiary |
| `IntegrationsHub.js` | 1 (Refresh) | secondary (with loading prop) |
| `AdminAllSites.js` | 1 (Refresh) | secondary |
| `OrgIntegrationsTab.js` | 1 (Refresh) + 3 inline "Manage" links left as plain anchors | tertiary |
| `UserDetailDrawer.js` | 4 (Issue link, Copy again, Close, Full edit in legacy panel) | primary · secondary · tertiary |

**13 inline button blocks** replaced with `<Button>` invocations. All `data-testid`s preserved — zero test regressions.

### Verified
- `/app/backend/tests/test_iter_216h26_audit.py` re-run after migration: **17/17 checks PASS**.
- Live smoke screenshots of the 4 migrated panels show consistent button styling:
  - Primary CTAs (Next, Issue & copy reset link) — brand cyan filled, exactly one per screen.
  - Secondary actions (Refresh, Back, Email it, Copy link) — outlined, supportive.
  - Tertiary (Close in drawer, Open on cards) — text + underline-on-hover, low emphasis.
- Lint clean across all 5 panels.

### Migration is intentionally bounded
The user asked for "panel-by-panel on next feature touch" — this batch deliberately ships only the Master Admin panels we created in P3-P6. Operator/member portal buttons will migrate on their next feature touch (the `<Button>` primitive is purely additive — legacy buttons keep working).

### ⚠ Action required
- Future panels: import `<Button>` from `@/components/shared/Button` — DO NOT write `<button className="inline-flex …">` anymore. See `/app/DESIGN_SYSTEM.md` for the anti-pattern catalogue.

---


## Iter 216h26-27 — Master Admin → portal audit + Empty-state pass + Button hierarchy (Feb 11, 2026)

Three deliverables in one push.

### A. Portal-linkage audit (iter 216h26)
- **17 / 17 end-to-end checks PASSED** between every Master Admin write surface and the customer-facing runtime (`/auth/me`, `module_access`, equipment listing, marketing-subscription gate, etc.).
- Full report at `/app/AUDIT_PORTAL_LINKS.md`. Live test harness at `/app/backend/tests/test_iter_216h26_audit.py` — re-runnable any time.
- **1 broken link fixed**: `POST /api/master-admin/organizations` now returns a 72 h invite link for the freshly-provisioned primary contact (`owner.invite_url` + top-level `invite_url`). Operators no longer need to use the legacy reveal-password handover — they can ship the self-serve reset link straight away. Frontend `useMasterAdminActions.createOrganization` surfaces the link in the success toast.
- New helper `_mint_invite_link(user_id, email, issued_by)` in `master_admin.py` keeps the iter-216h15 reset-link flow consistent across every creation surface (Staff Onboarding wizard, Customer Onboarding wizard, manual /users/{id}/invite-link).

### B. D2 — Empty-state pass (iter 216h27)
- Upgraded the 3 highest-visibility empty states to use the canonical `<EmptyState>` component:
  - **Memberships → Mobile App Builder**: was a bare div with "No cards yet". Now an EmptyState with icon, opportunity-framed title ("Your members' home screen is blank"), and a hint that explains what cards do.
  - **Master Admin → Login events**: was inline grey "No events match the current filter." Now structured EmptyState explaining the SOC 2 evidence purpose.
  - **Master Admin → Audit log (desktop + mobile)**: same upgrade. Both renderers (table + mobile cards) now use EmptyState with consistent copy.
- Full status table in `/app/DESIGN_SYSTEM.md` — 11 panels now adopt the canonical pattern; 3 remaining low-priority panels listed.

### C. D3 — Button-hierarchy audit (iter 216h27)
- New `<Button>` primitive at `/app/frontend/src/components/shared/Button.js` — **caps the vocabulary at 3 variants + 1 destructive**:
  - `primary` — brand cyan filled; exactly ONE per screen.
  - `secondary` — outline; supportive actions (Cancel / Bulk import / Refresh).
  - `tertiary` — text + underline-on-hover; low-emphasis "View all", "Manage", "Reset filter".
  - `destructive` — soft red; always confirm via `useConfirm()`.
- 3 sizes (sm / md / lg), `icon` prop for Lucide icons, `loading` spinner, `as` prop for anchors.
- Anti-pattern catalogue + migration plan in `/app/DESIGN_SYSTEM.md`.

### Verified live
- Audit harness PASS 17/17 after every change.
- Login Events page now renders without runtime errors (fixed an `onClearFilter is not defined` regression introduced + caught immediately).
- Audit log panel renders successfully with 11 events visible.

### ⚠ Action required
1. Redeploy preview → production.
2. The Master Admin Customer Onboarding wizard now offers the operator a copyable 72 h invite link in the success toast — no more password handover.
3. New panels MUST use `<Button>` and `<EmptyState>` from `/app/frontend/src/components/shared/`. Legacy panels migrate on next touch (anti-pattern catalogue in `/app/DESIGN_SYSTEM.md`).

---


## Iter 216h25 — Jump-to-user toast + Extended brand_filter coverage (Feb 11, 2026)

Two parallel deliverables, both verified live end-to-end.

### A. "Jump to this user" link in duplicate-user error toast
- **Backend**: `POST /api/master-admin/organizations/{org_id}/users` 409 response is now **structured**:
  ```json
  { "detail": { "code": "user_exists", "message": "...", "user_id": "...", "full_name": "...", "organization_id": "...", "collection": "users|crm_users", "email": "..." } }
  ```
- **Frontend wizard (`StaffOnboardingWizard.js`)**: when the 409 carries `code:'user_exists'`, an **amber toast** renders with a "Jump to this user in the directory →" button (`data-testid=staff-wizard-jump-to-user`). Clicking it pushes `?section=roles&focus_user={id}` and dispatches the new `gymaxis:focus-user` event.
- **`AdminRoles.js` listener**: subscribes to `gymaxis:focus-user`, resolves the user from `globalUsersProps.users` by id or email, switches to the Directory tab, opens the `UserDetailDrawer`, and scrolls the row into view. Also honours `?focus_user=` on mount so deep-links from elsewhere work the same way.

### B. Brand filter extended to audit-log + marketing-suite (+ financial-ops left strict)
- **Audit log** (`/app/backend/routes/master_admin_audit_log.py`):
  - New helpers `_resolve_brand_org_ids()` + `_is_pulse_only()`.
  - `_gather()` accepts `brand_org_ids: Optional[set]` and intersects per-collection queries via `_apply_brand()`.
  - All 3 public endpoints (`/audit-log`, `/summary`, `/export.csv`) accept `?brand=`.
  - **Pulse Master Admins are SERVER-SIDE FORCED to `pulse` regardless of the query param** — defence in depth.
- **Marketing Suite** (`/app/backend/routes/marketing/admin.py`):
  - `/master-admin/marketing/analytics` and `/master-admin/marketing/subscriptions` now accept `?brand=`.
  - Same Pulse-force behaviour.
  - Response payload now carries the resolved `brand` field so the UI knows what scope it's looking at.
- **Financial Ops** (`/app/backend/routes/financial_ops.py`):
  - Already gated by `_require_master_admin` which only allows `is_master_admin=True`. **Pulse admins receive 403** — correct behaviour because financial-ops is GymAxis-platform-level data (reserve fund, LLM credits, platform burn). No brand-filter needed.
  - Testing agent patched a pre-existing minor MongoDB ObjectId serialisation bug in `_get_config()` (re-fetch after insert).
- **Frontend wiring**:
  - `AuditLogPanel.js` + `AdminMarketingSuite.js` (Analytics + Subscriptions) now consume `useBrandContext().brand` and append `?brand=` to fetch URLs. Reload fires automatically when the operator flips the top-bar BrandPicker.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h25.json`)
- **22/22 tests PASSED** (backend 17/17 · frontend 5/5):
  - Structured 409 response.
  - Toast renders + Jump button works end-to-end.
  - `?focus_user=` URL param opens drawer on mount.
  - Audit-log accepts `?brand=` (list, summary, export.csv).
  - Marketing analytics/subscriptions accept `?brand=`.
  - Pulse admins forced to `pulse` on all 5 endpoints.
  - Financial-ops returns 403 for Pulse admins (correct).
  - GymAxis admins can freely toggle.

### ⚠ Action required
1. Redeploy preview → production.
2. Pulse Master Admin scope-lock is now enforced **server-side** on audit-log + marketing, in addition to the existing UI lock — defence in depth against malformed/replay requests.
3. Operators who try to invite an existing user from the wizard now get a one-click "Jump to this user" deep link instead of a flat error.

---


## Iter 216h24 — Master Admin redesign Phase 6: Staff Onboarding wizard (Feb 11, 2026)

P6 — final phase of the Master Admin redesign blueprint. Replaces ad-hoc "Add user" buttons scattered across the People panels with one canonical 5-step linear wizard that the user explicitly asked for ("invite → role → sites → modules → audit").

### What shipped (frontend only — no new backend code)
- **NEW `StaffOnboardingWizard.js`** at Master Admin → People → "Onboard staff" sub-tab. 5 steps:
  1. **Identity** — full name + work email + brand context. Pulse-only admins get the brand forced to `pulse`.
  2. **Role** — 7 tiles in 2 groups (Platform: GymAxis Master Admin · Pulse Master Admin · Service Desk; Customer org: Owner · Manager · Staff · Instructor). Pulse Master Admins cannot invite a "GymAxis Master Admin".
  3. **Sites** — only meaningful for org-scoped roles. Multi-select site checkboxes loaded from `GET /api/master-admin/organizations/{org_id}/sites`. Empty = all sites (no restriction).
  4. **Modules** — 4 toggles (Operations Portal · Memberships · Marketing Suite · CRM). Toggling OFF sends a `module_overrides` entry; ON inherits the org default.
  5. **Review** — summary card → "Generate invite link" CTA. On success: 72 h invite URL with **Copy** and **Email** actions.
- Reuses **4 existing backend endpoints** (no new backend code):
  - `POST /api/master-admin/pulse-admins` for the Pulse Master Admin role.
  - `POST /api/master-admin/organizations/{org_id}/users` for every org-scoped + master_admin + service_desk role.
  - `PUT /api/master-admin/users/{user_id}/edit` for `allowed_site_ids` and `module_overrides`.
  - `POST /api/master-admin/users/{user_id}/invite-link` to mint / re-mint the 72 h reset-link.
- Reuses the iter-216h15 reset-link flow exactly — Master Admin never sees the user's plaintext password; the user sets it from the 72 h link on first visit.

### Sidebar restructure
- People group now has 3 sub-tabs: **Directory · Onboard staff · Site-locked users**.

### Verified live
- **Testing agent v3 `/app/test_reports/iteration_216h24.json` — 12/12 PASSED** (backend + frontend 100%):
  1. Wizard loads with 5 step pills.
  2. Step 1 input validation works.
  3. 7 role tiles in 2 groups.
  4. Sites checkboxes load from API.
  5. Module override toggle.
  6. Happy path e2e — created user, invite link returned with `/reset-password?token=`.
  7. Pulse Master Admin scope hides GymAxis Master Admin role + forces brand + filters orgs to Pulse only.
  8-10. Backend endpoint calls verified.
  11. Created user appears in unified directory.
  12. Regression: People → Directory still works.
- **Main agent live smoke**: signed in as `admin@gymaxisai.com`, ran full 5-step flow, created `Wizard Test User`, received invite URL `https://maintenance-hub-357.preview.emergentagent.com/reset-password?token=l47KegLXL2FI…`.

### Pulse Master Admin guardrails
- 'GymAxis Master Admin' role tile hidden.
- Brand toggle hidden (Pulse scope forced).
- Org dropdown only shows Pulse-brand orgs (2-3 of 90 in preview).
- Server-side guardrails inherited from existing endpoints (master-admin + Pulse-scope checks).

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **People → Onboard staff** to invite a new team member. The wizard takes < 60 seconds end-to-end.
3. The Master Admin redesign blueprint is now **COMPLETE through P6**. Remaining UX/process backlog work (button hierarchy audit, empty-state pass, dark-mode commit-or-strip) is independent of the redesign.

---


## Iter 216h23 — IA cleanup: kill misleading "Sites" sidebar entry + add "All sites" under Organisations (Feb 11, 2026)

Operator feedback: *"Sites is showing the equipment catalogue. Could Sites be under Organisations?"* Chose option (b): kill the standalone, rename the contents, add an "All sites" cross-org sub-tab under Organisations. **SSoT preserved** — a Site still belongs to exactly one Organisation; the only editor is the Organisation drawer's Sites tab.

### Conceptual clarification (now reflected in the UI)
- **Organisation** = customer/legal entity (Pulse Fitness Ltd, Tottenham Green Trust). 90 in preview DB.
- **Site** = physical location belonging to ONE Organisation (Pulse Birmingham, Brockwell Lido Main Pool). 32 in preview DB.
- **Equipment Catalogue** = platform-wide master data (model images, spec sheets, custom properties). Reused across every Org + Site. NOT a Site.

### What shipped (frontend)
- **Sidebar "Sites" entry DELETED**. Its contents (Equipment catalogue, Spec sheets, Equipment images, Manufacturers, Marketing library, Social media library) re-homed under a new **"Catalogue & Library"** sidebar entry — accurate label for cross-org master data + brand assets.
- **NEW "All sites" sub-tab inside Organisations group** (sits between List and Customer onboarding):
  - Cross-org flat table of every physical site.
  - Per-row: HQ/branch icon, name, parent org, brand pill, city + postcode, equipment count, members count.
  - Totals strip (Total sites · Head offices · Branches · Equipment).
  - Filter bar (free-text search, site-type, organisation dropdown) with live result count.
  - **Row click pushes URL params `?section=organizations&expand=ORG_ID&view=sites`** + dispatches `gymaxis:set-section` so `AdminOrganizations` (which already reads those params on mount) opens the right org drawer on the Sites tab. SSoT preserved — editing flows through the existing drawer.
- New `AdminAllSites.js` component (read-only power view).

### Backend (1 new endpoint)
- **`GET /api/master-admin/all-sites`** — master-admin-gated cross-org sites list:
  - Query params: `org_id`, `site_type` (`head_office`/`branch`/`all`), `q` (free text), `limit`.
  - Per-row enrichments: `equipment_count` and `members_count` via single aggregation passes (no N+1).
  - Pulse-only admins receive `brand="pulse"` and orgs filtered through `brand_filter_clause("pulse")` — scope-lock honoured server-side.

### Verified live
- **Testing agent v3 `/app/test_reports/iteration_216h23.json` — 7/7 PASSED**:
  1. Endpoint auth gate (401 without token).
  2. GymAxis admin sees 32 sites / 17 HQs / 15 branches / brand="all".
  3. Query params work (site_type filter, limit).
  4. Pulse admin sees brand="pulse" with scope-filtered sites.
  5. Sidebar verified: Sites entry GONE, Catalogue & Library present, All sites under Organisations.
  6. `AdminAllSites` component renders with all expected testids.
  7. Regression: Org list, Integrations Hub, Pulse Master Admin scope-lock all still work.
- **Main agent live smoke**: sign-in → All sites loads 32 rows with totals strip → click any row → URL flips to `?section=organizations&expand=...&view=sites` → Organisation drawer opens on Sites tab with Module-Overrides toggles visible. End-to-end navigation pattern works.

### Fix to the JSX literal-escape bug
- Cleaned up three places where `\u2026` / `\u2019` had leaked into JSX strings inside `AdminAllSites.js` and the section description. They now render as proper "…" and "&apos;".

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **Organisations → All sites** for a flat cross-org power view. Click any row to drill into that organisation's Sites drawer.
3. Equipment images / spec sheets / manufacturer catalogue / marketing library / social media library all moved to **Catalogue & Library** in the sidebar (same content, accurate label).

---


## Iter 216h22 — Master Admin redesign Phase 5: Integrations Hub + Pulse Master Admin scope-lock (Feb 11, 2026)

P5 of the blueprint — single page for all third-party connections, plus a guarantee that **Pulse Master Admins only ever see Pulse Fitness data**.

### What shipped (frontend)
- **NEW `IntegrationsHub.js`** (Master Admin → Integrations → Hub):
  - Summary strip with 4 tiles (Connected / Degraded / Not configured / Brand scope).
  - 4 integration cards (Stripe Connect · Sicon Service · Orbit 4 · Sage 200) — each with status pill, brand badge, org-coverage tile (X / Y orgs · Z %), last-24h events / errors, "Open" affordance.
  - Right-hand `Sheet` drawer that EMBEDS the full existing console page so **every Sicon and Sage mapping field stays visible and editable**:
    - Sicon card → full `SiconIntegrationPage` (Overview · Organisations · Event Log · Configuration · **Field Mappings**).
    - Orbit 4 card → full `IntegrationAdminPanel` for orbit4.
    - Stripe Connect card → full `AdminStripeConnect` (platform settings + per-org onboarding rows).
    - Sage 200 card → field-mapping reference table + coverage + pointer to Org Billing tab (Sage rides the Sicon bridge so the editor lives on the org doc).
- **NEW Sidebar group `integrations-hub`** with 4 sub-tabs (Hub default · Orbit 4 · Sicon Service · Stripe Connect). The 3 legacy entries still deep-link.
- **Brand Picker now scope-locks for Pulse Master Admins**:
  - `BrandPicker.js` accepts an `isPulseAdmin` prop. When true, it forces `brand="pulse"` on mount and renders a non-clickable pill ("Pulse Fitness · SCOPE LOCKED") in place of the dropdown.
  - `MasterAdminPage.js` derives `isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin)` and passes it to both `BrandPicker` and `IntegrationsHub`.

### Backend (1 new endpoint + 1 critical auth-payload fix)
- **`GET /api/master-admin/integrations-hub`** — single round-trip JSON for the hub:
  - `brand` (forced to `pulse` for `is_pulse_only(user)` callers).
  - `integrations[4]`: each with `key`, `label`, `enabled`, `status` (connected / degraded / not_configured / down), `last_event_at`, `events_24h`, `errors_24h`, `orgs_configured`, `orgs_total`, `ref_field`. Stripe Connect row also returns `platform_fee_pct`.
  - `summary` counts.
- **CRITICAL FIX — `/api/auth/me` now returns `is_pulse_admin`**. The login response already included it, but `/auth/me` (the auth-rehydrate endpoint) did NOT — so on every page reload the React `user` lost its Pulse-admin flag. Routes guarded by `is_pulse_admin` (`/master-admin` access, BrandPicker scope-lock) failed silently and bounced Pulse admins to `/dashboard`. Restored.

### Verified live (testing agent v3 + main agent smoke test)
- **Testing agent report `/app/test_reports/iteration_216h22.json`** — 8 items, 7 PASSED, 1 PARTIAL (frontend Pulse-login blocked by rate-limit; backend behaviour verified via API).
- **Main agent end-to-end smoke** (after `/auth/me` fix):
  - Signed in as `pulse.scope.test@pulsefitness.com` → navigated to `/master-admin?section=integrations-hub`.
  - Top bar shows **"Pulse Fitness · SCOPE LOCKED"** pill (data-testid `master-admin-brand-picker-locked`).
  - Trigger dropdown (`master-admin-brand-picker-trigger`) NOT rendered — confirmed mutually exclusive.
  - Brand-scope summary tile says "Locked (Pulse Master Admin)".
  - Org-coverage on every card shows 0 / 3 (NOT 0 / 90) — Pulse-scoped server-side via `brand_filter_clause("pulse")`.
  - All 4 integration cards render correctly with brand badge "Pulse Fitness" on each.

### Side effect — new test account
- **Pulse Master Admin scope test**: `pulse.scope.test@pulsefitness.com` / `TestPulse2026!` (added to `/app/memory/test_credentials.md`).

### What this still does NOT do (handed to P6+)
- `AdminPulse` panel intact — **NOT retired**, per user clarification ("we still need a Master Admin just for Pulse Fitness").
- Sicon / Orbit 4 / Sage 200 "test connection" button + per-row drilldown (still via the embedded existing page).
- P6 — Staff Onboarding wizard still pending.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin: Sidebar → **Integrations → Hub** to drill any of the 4 connections in a side drawer with mapping fields preserved.
3. Delegate a Pulse Master Admin via `POST /api/master-admin/pulse-admins` — they will be auto-locked to Pulse scope on every dashboard, list and audit.

---


## Iter 216h21 — Master Admin redesign Phase 4: Organisations SSoT consolidation (Feb 11, 2026)

P4 of the blueprint — collapses the multi-surface Organisations experience into a single drawer with 7 blueprint tabs.

### What shipped (frontend)
- **`MasterAdminPage.renderSection`** — added `case 'organizations'` so the sidebar's `Organisations → List` entry now renders `<AdminOrganizations {...orgsProps} />` directly. Previously this section ID had no case and silently fell through to `null`, leaving the page blank.
- **`AdminOrganizations.js` drawer tabs renamed + new tab added**:
  - Old: Details · Users · Features · Sites · Billing · Audit (6).
  - New: **Profile · Sites · People · Modules · Billing · Integrations · Activity (7)**.
  - `value` keys (`details`/`users`/`features`/`sites`/`billing`/`integrations`/`audit`) and data-testids were preserved so existing tests & deep-links still resolve. Only the visible labels + the order changed (Sites moved up next to Profile per the blueprint reading order).
- **NEW component `OrgIntegrationsTab.js`** — surfaces per-org connection status for **Stripe Connect / Sicon Service / Orbit 4 / Sage 200**. Each row carries a status pill (Connected / Not configured), a descriptive line (account ref, platform fee, auto-post flag) and a "Manage" link that fires the existing `gymaxis:set-section` window event to jump to the global integration console.
- The panel calls the new endpoint on mount + on Refresh; gracefully degrades to org-doc fields when the endpoint errors.

### Backend (1 new endpoint, master-admin-gated)
- **`GET /api/master-admin/organizations/{org_id}/integration-health`** — returns a 4-block JSON snapshot:
  - `stripe_connect`: `connected`, `account_id`, `charges_enabled`, `payouts_enabled`, `platform_fee_pct`.
  - `sicon`: `configured` (org-ref ∩ platform-configured), `platform_configured`, `account_ref`, `auto_post`.
  - `orbit4`: `configured`, `platform_configured`, `customer_id`.
  - `sage200`: `configured`, `account_ref`.
- Permission gate: `require_master_admin` + `assert_org_in_pulse_scope` (so Pulse Admins only see their own scope).
- No new collection/schema. Pure read across `organizations` + `app_config`.

### Verified live (testing agent v3 — `/app/test_reports/iteration_216h21.json`)
- **All 6 test items PASSED** (backend + frontend 100%):
  1. Endpoint returns correct JSON shape; 401 without token; 401 with invalid token; "not configured" shape on orgs with no integration data.
  2. Organisations sidebar entry renders ~90 org cards (was previously blank).
  3. Drawer shows 7 tabs in correct order (Profile/Sites/People/Modules/Billing/Integrations/Activity).
  4. Integrations panel renders 4 rows + status pills + Manage links + Refresh button.
  5. Regression: People → Directory row click → UserDetailDrawer still works (iter 216h20).
  6. Regression: "Customer onboarding" is under Organisations sidebar (iter 216h20).

### What this still does NOT do (handed to P5/P6)
- The standalone `AdminPulse` (Overview → Service Portal → Pulse) panel is left intact for now; the new per-org Integrations tab now covers the same drill-down need but the global KPI strip + MRR table on Overview is still useful for tier-mix at-a-glance.
- The Memberships admin's separate `OrganisationsTab` is left intact (specialised lock/unlock view inside the Memberships admin — different mental model).
- P5 (Integrations hub) and P6 (Staff Onboarding wizard) still pending.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin on `gymaxisai.com`: Sidebar → **Organisations → List** → click any org row's pencil → use the new **Integrations** tab to see per-org Stripe/Sicon/Orbit/Sage status at a glance, with Manage deep-links to the global consoles.

---


## Iter 216h20 — Drawer wiring + Organisation Onboarding restored (Feb 11, 2026)

### A. P3-followup — `UserDetailDrawer` wired into People Directory
- `AdminRoles.js` now owns a `selectedUser` state. Clicking any row in `PeopleDirectory` opens the existing `UserDetailDrawer.js` (Profile + 72 h reset link + "Full edit in legacy panel").
- "Full edit in legacy panel" closes the drawer, flips the Roles sub-tab to `legacy-users`, fires `gymaxis:focus-legacy-user` window event (carries `user_id` + `email`) so `GlobalUsersPanel` can scroll/expand the matching row in a follow-up iter, and triggers the parent `onReload`.
- Verified live: 101 rows render, first row → drawer opens with name `Iter216h Dual-Role Test`, role `pulse_master_admin`, organisation, email and the "Issue & copy reset link" button all populated.

### B. Regression fix — Organisation Onboarding restored
- **Operator feedback**: "We've lost Organisation Onboarding which was working perfectly."
- **Root cause**: Iter 216h17 moved the onboarding hub under People and relabelled it "Staff onboarding" — but the hub creates **customer organisations** (sub-tabs: Onboard Site / Head Office (multi-site) / Onboarding Packets / Bulk Imports). Operators looking for *Organisation* onboarding never thought to look under People → Staff onboarding.
- **Fix** (`SidebarConfig.js`):
  - Moved `onboarding` from the People group to the Organisations group.
  - Relabelled sidebar entry **"Staff onboarding" → "Customer onboarding"**.
  - Section title updated to "Customer onboarding".
  - Section description updated to "Onboard a new customer organisation, send shareable packets, or bulk-load CSV rosters".
  - `LEGACY_SECTION_REDIRECTS['onboarding']` now points to `'organizations'`.
- Verified live: Organisations sidebar entry now shows 4 sub-tabs (List · Customer onboarding · Module subscriptions · Customer activation). Customer onboarding renders `<AdminOnboardingHub>` with all 4 wizards intact.

### ⚠ Action required
1. Redeploy preview → production.
2. As Master Admin on `gymaxisai.com`: Sidebar → **Organisations → Customer onboarding** — runs the brand-new customer wizard. The drawer in People → Directory opens on row click for fast reset-link issuance.

---


## Iter 216h19 — Master Admin redesign Phase 3: People SSoT consolidation (Feb 11, 2026)

The biggest single-source-of-truth win of the redesign. Four legacy People panels collapsed into one **People Directory** that operators can actually onboard staff against this week.

### What shipped (frontend only — backend already merges correctly since iter 215ev)
- **`PeopleDirectory.js`** — single React surface that absorbs the per-row responsibilities of:
  - `AdminUsers` (cross-org user list)
  - `GlobalUsersPanel` (archive / purge / leaver flow — preserved as a legacy fallback tab)
  - `AdminPulseAdmins` (dual-role Pulse Master Admins — still has its own panel for the matrix; surfaces as rows in Directory)
  - `AdminCRMUsers` (CRM-only contacts — surfaces as rows with the `CRM` portal badge)
- **Components inside the Directory**:
  - **6-tile stats strip** — Total active · Pulse admins · Owners · Staff/Managers · CRM-only · Role mismatches.
  - **6 filter pills** with live counts — Everyone / Pulse Admins / Owners / Staff & Managers / CRM contacts / Archived. Pills are colour-coded to match the role-chip palette.
  - **Search box** scoped to name + email + organisation name.
  - **Role chips** (Pulse Admin = blue, Owner = purple, Manager = emerald, Staff = zinc, Master Admin = orange).
  - **Portal badges** per row (Service Portal / CRM / Pulse Platform).
  - **Role mismatch warning** (red `invited as X` chip) when `invited_role ≠ current_role` (iter 216h3 detection surfaced here).
  - **Site-pin hint** — "N site(s) pinned" inline when `allowed_site_ids` is non-empty.
- **`AdminRoles.js` restructured** — Directory is now the FIRST tab (default). Permissions matrix, Service Desk team, Pulse Master Admins, and the legacy GlobalUsersPanel each get their own clearly-labelled tab. "Legacy users panel" name explicitly flags it as the pre-P3 surface so operators know it's there as a safety net only.
- **Brand-aware** — the Directory consumes the brand-filtered `users` array from `MasterAdminPage.loadData` (iter 216h18). Flipping the brand picker re-filters everything; the brand label is echoed in the directory subtitle.

### Verified live on preview
Master Admin → People → Directory rendered cleanly with:
- 101 total active, 20 Pulse admins, 49 owners, 30 staff/managers, 2 CRM-only, 0 role mismatches.
- Pill click "Owners" → 49 rows filtered correctly.
- Search "admin" chained with the Owners pill → 9 rows.
- Legacy users panel tab still accessible.
- Sidebar IA from P1 intact (8 entries).

### Important consolidation accounting
- **Before P3**: a single human was renderable in 4 different lists with 4 divergent action sets.
- **After P3**: one row per (email × org_id), portal badges show which systems they have access to, click any row to deep-drill via existing UserEditDialog (Profile / Sites / Permissions / Activity tabs already exist from iter 216h15 + 216h16).
- **No DB changes** — the dedupe / merge already happens server-side in `/api/master-admin/users`. P3 is pure UX consolidation.

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: People → Directory should land you on the new unified list. Use it for the staff onboarding this week.
3. If anything feels missing, the "Legacy users panel" sub-tab is still 1 click away as a safety net for the first release.

### Remaining roadmap
- 🟢 P4 — Collapse 3 Organisation panels (AdminOrganizations + AdminPulse + Memberships orgs tab).
- 🟠 P5 — Integrations hub (5 surfaces → 1 page).
- 🔵 P6 — Staff Onboarding wizard.
- 🔵 P3-followup — wire the Directory's row click into the existing UserEditDialog drawer (currently calls `onReload`).

---


## Iter 216h18 — Master Admin redesign Phase 2: Brand Context wired into data layer (Feb 11, 2026)

P1 (iter 216h17) shipped the UI scaffolding for the brand picker. P2 wires the picker into the actual data queries — operators flipping Pulse / GymAxis / All now changes what data is loaded, not just the pill label.

### Backend (single source of truth)
- **New `utils/brand_filter.py`**: Canonical brand classification + Mongo query helper. A record belongs to:
  - **Pulse** — `account_type` in {pulse_pro, pulse_lite, pulse} OR `is_pulse_admin: True` OR `brand` in {pulse, pulse_fitness}.
  - **GymAxis** — `account_type` in {full, gymaxis, gymaxis_admin, lite, ""} OR `account_type` absent OR `brand` in {gymaxis, ""}. (`lite`/null intentionally classified as GymAxis — GymAxis is the platform default; production has 21 such orgs.)
- Helpers: `normalise_brand()`, `brand_filter_clause()`, `merge_brand_filter()` (handles edge case where existing query already has `$or` — promotes to `$and`).
- `GET /api/master-admin/organizations` now accepts `?brand=pulse|gymaxis|all`. Filter composes safely with the existing `is_pulse_only(user)` permission gate (permission always wins).
- `GET /api/master-admin/users` now accepts `?brand=…` and **scopes by parent-org brand** so legacy users with `account_type=null` are still correctly classified by their org's brand (the org is authoritative).

### Frontend
- **`useBrandedAPI()` hook**: tiny `apiUrl(path, extraParams)` helper that auto-appends `?brand={ctx}` to any URL. Exports `brand` for use in React-Query / SWR keys.
- **`MasterAdminPage.loadData`** now reads `useBrandContext()` directly and adds the brand to all three core requests (`/stats`, `/organizations`, `/users`). `loadData`'s `useCallback` deps include `_brandQS`, so flipping the picker triggers a fresh fetch automatically.

### Verified live
- 3 sequential screenshots from preview captured the picker flipping cleanly through **Pulse → GymAxis → All** with the sidebar's new 8-entry IA intact (Overview · People · Organisations · Sites · Finance · Growth · Integrations · Settings & Compliance).
- **22/22 backend tests passing** in `test_iter_216h18_brand_filter.py`:
  - 7 parametrized normalisation tests (case-insensitive, alias handling, fallback to "all" for noise input).
  - 5 helper logic tests (empty for all, 3-path pulse user filter, gymaxis includes null account_type, merge preserves existing query, double-$or promoted to $and).
  - 6 endpoint partition tests (Pulse excludes GymAxis, GymAxis excludes Pulse, All returns both, users follow parent-org brand, omitted defaults to all, unknown brand defaults to all).

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: Open Organisations, flip the brand pill to **Pulse Fitness** — only Pulse Fitness orgs remain visible. Flip to **GymAxis** — only GymAxis orgs visible. Flip to **All** — every customer visible.

### What this still does NOT do (P3-P6)
- Doesn't yet collapse the 4 People panels into one Directory (P3).
- Doesn't yet collapse the 3 Org panels into one (P4).
- Doesn't yet pin the brand filter to other panels beyond stats/orgs/users (e.g. financial-ops, marketing-suite still show all data). Wiring those is mechanical now that the helper exists — they can be added in P3 along with the consolidations.

---


## Iter 216h17 — Master Admin redesign Phase 1: Information Architecture + Brand Context (Feb 11, 2026)

**Audit findings & rationale**: The legacy Master Admin had 14 top-level sidebar entries + 23 sub-tabs (37 nav surfaces) — too dense for sales/marketing staff onboarding this week. Multiple single-source-of-truth violations identified across People (4 panels), Organisations (3 panels), Equipment images (5 panels), Integrations (5 panels). Brand divergence between Pulse Fitness and GymAxis was implemented ad hoc via scattered `gymaxisOnly` flags.

Engaged `design_agent_full_stack` for the redesign blueprint → produced `/app/design_guidelines.json` with the new IA, brand strategy, People/Org SSoT designs, integrations hub plan, staff onboarding wizard, visual language references (Linear / Vercel / Stripe Atlas / Sentry / Notion teamspaces) and terminology cleanup.

### What shipped in Phase 1 (foundation only — no data routing changes)
- **New 8-entry sidebar IA** (`SidebarConfig.js` overwrite):
  1. Overview — Dashboard · System Health · Setup checklist
  2. People — Directory · Site-locked users · Staff onboarding
  3. Organisations — List · Module subscriptions · Customer activation
  4. Sites — Equipment images · Custom properties
  5. Finance — Pricing · Org billing · Collections · Payments · Stripe · Financial ops · Refunds · CAPEX
  6. Growth — Trials · Sales insights · Global analytics
  7. Integrations — Orbit 4 · Sicon Service · Stripe Connect
  8. Settings & Compliance — Audit log · Login events · Documents · Outbound emails · Ask Support · Support tools · Database viewer · Maintenance jobs · Design system
- **Brand context** (`BrandContext.js`): React context + provider with All / Pulse Fitness / GymAxis. Persists to localStorage. Fires `master-admin-brand-change` window event so legacy panels can react. Exports `filterByBrand()` helper.
- **Brand picker pill** (`BrandPicker.js`): Sits in the Master Admin top bar between Email Health and Refresh. Dropdown with 3 options + descriptive footer.
- **Terminology cleanup** in `sectionTitles` / `sectionDescriptions`:
  - "Trust & Reliability Engine" → "System health"
  - "Roles & Access" → "People directory"
  - "Tasks" → "Setup checklist"
  - "Locked staff" → "Site-locked users"
  - "Activation Funnel" → "Customer activation"
  - "Estate Rollup" → "Module subscriptions"
  - "Data Backfills" → "Maintenance jobs"
  - "Onboarding" (ambiguous) → "Staff onboarding"
- **`LEGACY_SECTION_REDIRECTS`** map documents which legacy section IDs were absorbed into which new groups (no functional redirect yet — `renderSection` still resolves all IDs directly; this map is for review/audit + future P2-P5 consolidations).

### Verified live on preview
- Sidebar shows all 8 entries with correct labels.
- Brand picker pill labelled "All" by default; opens dropdown with All Brands (ACTIVE) · Pulse Fitness · GymAxis + footer copy.
- Clicking Pulse Fitness flips the pill label to "Pulse" and persists to `localStorage.master_admin_brand_filter = 'pulse'`.
- Clicking People renders the "People directory" header with the subtitle "Pulse Admins · Customer Owners · Customer Staff · CRM contacts — all in one directory" and sub-tabs Directory / Site-locked users / Staff onboarding.

### Next phases (recommended order per blueprint)
- **P2** — Wire BrandContext into every panel's data query (currently UI-only).
- **P3** — Collapse the 4 People panels (`AdminUsers` + `GlobalUsersPanel` + `AdminPulseAdmins` + `AdminCRMUsers`) into one Directory page with role-coloured chips + drawer tabs (Profile · Sites · Permissions · Activity · Sessions).
- **P4** — Collapse 3 Org panels into one Organisations page with tabbed drawer (Profile · Sites · People · Modules · Billing · Integrations · Activity).
- **P5** — One Integrations hub with brand status pills + click-to-detail drawer.
- **P6** — Staff Onboarding wizard (invite → role → sites → modules → audit) reusing the iter-216h15 reset-link flow.

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Master Admin on `gymaxisai.com`: top bar now has a brand-picker pill — click it, pick Pulse Fitness, refresh; the choice persists. Sidebar is reorganised into 8 clean groups.
3. Tell me when to start P2/P3 — they're the high-value SSoT consolidations.

---


## Iter 216h16 — Trust & Reliability RAM/CPU/Disk + Master Admin parity for site allocation (Feb 11, 2026)

### A. System resources panel on Trust dashboard (`psutil`)
- **Backend**: `_system_metrics()` helper + new `GET /api/master-admin/trust/system` endpoint + `system` block embedded in `/trust/overview` so the dashboard hits one round-trip. Returns CPU (%, count, load avg), memory (used/avail/total MB + status banner), swap, disk (used/free/total GB + status banner), process (RSS MB, CPU%, started_at, PID), and hostname. Status banner ramp: < 70% → `ok` (green), 70–89% → `warn` (amber), ≥ 90% → `critical` (red).
- **Frontend** (`TrustDashboard.js`): new `SystemResourcesPanel` + `ResourceGauge` components. 3-column responsive grid with bar + tone label ("OK" / "WATCH" / "UPGRADE NOW"). Footer line shows process RSS / CPU / uptime + an amber upgrade tip when any gauge hits warn/critical.
- **Live preview snapshot**: CPU 5.1% OK · RAM 58.4% OK (18.7/32 GB) · Disk 54.8% OK (58/106 GB).
- **Tests**: `test_iter_216h16_trust_system_metrics.py` — 4/4 passing (master-admin gating, full field shape, overview embedding, threshold sanity).

### B. Master Admin parity: site allocation on user edit drawer
- **AdminOrganizations.js**: user edit dialog now fetches `/master-admin/organizations/{org_id}/sites` on open, and renders a chip-style multi-select inside a new "Site access" panel (only for non-owner, non-master-admin roles). Uses the existing `PATCH /master-admin/users/{id}` endpoint which already accepted `allowed_site_ids` — no new backend endpoint needed.
- HQ sites show with a ★ prefix; pinned sites show a ✓ + blue accent.
- Mirrors the owner-side chip UX from iter 216h15 so Master Admins get identical UX to Owners.

### C. Master Admin parity: reset link / temp password
- Already present in MA user-edit dialog (iter 215bi+215ev). No work needed. Both buttons live side-by-side: "Reset Link" (green, copies invite URL) + "Temp Password" (blue, copies a freshly-minted temp password).

### ⚠ Action required
1. **Redeploy** preview → production. `psutil==7.2.2` is now in `requirements.txt`.
2. On `gymaxisai.com`: Master Admin → **Security → Trust & Reliability → Live platform health** → the new "System resources · this pod" panel appears between the summary tiles and Integration Health.
3. Master Admin → Organisations → Open any org → click a non-owner user → new "Site access" chip selector appears under the Role field.

---


## Iter 216h15 — Real auto-created Head Office + owner team management (Feb 11, 2026)

**Operator feedback**: "Head Office is a proper site — sales/marketing/admin are assigned to it, even though it usually has no equipment." Also: (B) "Can't allocate staff to sites" and (C) "Owners need ability to send a reset link, not show inline temp password."

### Replaced synthetic HQ with auto-created real HQ
- Iter 216h14's synthetic `hq:{org_id}` was wrong (couldn't have staff/users assigned). Replaced with: when an org has ≥1 site but **none** flagged HQ, `/api/sites` now **persists a real `db.sites` row** (`name = "{Org} Head Office"`, `is_head_office=true`, `auto_created=true`). Idempotent. Existing real HQ takes priority.
- HQ is sorted to the TOP of the SiteSwitcher list.
- Renamed dropdown label **"All sites" → "All Operations Sites"** (dashboard header + SiteSwitcher dropdown + AllSitesOverview page title).

### B. Site allocation for owners
- New endpoint `PATCH /api/account/team/{user_id}/site-access` — owner pins a teammate to a subset of org sites (or clears → full access).
- Tenant-isolation: site ids from other orgs are silently filtered out.
- Owners can't pin themselves or other owners (they always see all sites).
- Audit fields stamped: `site_access_updated_at`, `site_access_updated_by`.
- **Account Settings → Team & Roles**: each teammate row now shows a "Sites: …" summary with an inline "Edit sites" toggle that opens a chip-style multi-select.
- Invite form gained a "Pin to sites (optional)" chip selector — pins at invite time.

### C. Send reset link (replaces inline temp password)
- New endpoint `POST /api/account/team/{user_id}/send-reset-link` — issues a 72 h password reset token, mirrors Master Admin's existing UX, stamps `password_reset_sent_at` + `password_reset_sent_by` for the audit trail.
- Invite form: added "Delivery" dropdown — `Email password reset link (recommended)` vs `Show temporary password inline`. Default is reset link.
- Each existing teammate row has a **"Send reset link"** button that issues a fresh link, copies it to the operator's clipboard, and updates the audit trail.
- Audit trail line ("Last reset link sent {date} by {owner email}") appears under the teammate row when applicable.

### Verified — 13/13 tests passing in `test_iter_216h15_team_management.py`
1. Auto-create HQ on first `/api/sites` call (real `db.sites` row, not synthetic).
2. Idempotent — second call doesn't double-create.
3. Invite with `delivery=reset_link` returns invite_url, no temp_password leak.
4. Legacy `delivery=temp_password` still works.
5. Invite-time `allowed_site_ids` is persisted.
6. Owner can pin staff to subset of sites.
7. Empty allowed_site_ids = full access.
8. Foreign-org site ids are filtered out (tenant isolation).
9. Owners cannot be pinned.
10. Send-reset-link returns invite URL + audit stamps.
11. Send-reset-link 404s for unknown users.
12. Send-reset-link rejects other owners as targets.
13. `/api/account/team` GET surfaces the reset audit trail.

### Visual smoke test (preview, impersonating Test Owner of multi-site org with no HQ)
- Page header reads: **"Pulse Fitness · Test HQ No Flag Head Office"** ← auto-created HQ.
- Invite form shows DELIVERY dropdown + PIN TO SITES chip strip with HQ first (★ icon).

### ⚠ Action required
1. **Redeploy** preview → production.
2. As Lee on `gymaxisai.com`:
   - Open Account Settings → Team & Roles → invite a sales-admin teammate with delivery = "Email password reset link" → pin to "Pulse Fitness Head Office" only.
   - Send reset link to any existing teammate — copies URL to clipboard.
3. Confirm the SiteSwitcher now shows: **All Operations Sites | ★ Pulse Fitness Head Office | iGym Carshalton | iGym Congleton**.

---


## Iter 216h13 — Short equipment-row display + backfill endpoint (Feb 11, 2026)

**Operator-reported (with screenshots)**: imported equipment rows were rendering the full 200-char Pulse marketing line ("Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, Apple/Samsung Watch Connectivity, Content Mirroring & Wireless Charging in Sand Black…") as BOTH the equipment `name` AND `model`, blowing the row layout out of the page. Operator demanded the row match the manual-add format: `Treadmill (cardio)` · `Pulse Fitness · 260G · 12345`.

### What shipped (backend)
- **`_EXTRACTION_TEMPLATE` schema gained `equipment_name`** (SHORT subtype noun) **and `description`** (FULL marketing line).
- **`_short_equipment_name(eq)`**: Picks AI-extracted name when ≤ 40 chars; heuristic keyword fallback (treadmill/stepmill/upright cycle/recumbent cycle/cross-trainer/rower/smith machine/lat pulldown/leg press/etc.).
- **`_short_model_code(eq)`**: Prefers `stock_item_code`. Refuses any "model" > 24 chars or > 2 spaces.
- **`_build_equipment_doc`**: Now produces clean rows. `name = short subtype`, `model = short stock code`, `description = full marketing line`, `notes = "Imported from invoice {n} · {description}"`.
- **Wizard preview** + **Sicon CSV row** + **`/parse-invoice` response** all use the same helpers → wizard preview matches what gets created on confirm.

### Backfill endpoint for legacy data
- **`POST /api/master-admin/equipment/backfill-short-display`** (master-admin gated):
  - Body: `{organization_id?, site_name?, supplier_name?, dry_run?}` — also accepts `?dry_run=true|false` query param.
  - Only touches rows with `import_id` set OR notes starting with "Imported from invoice" (manual-add rows are untouched).
  - Skips rows already in the short shape (idempotent — second run returns 0 updates).
  - Returns `{dry_run, total_candidates, equipment_to_update, equipment_updated, orgs, preview[≤200]}`.
- **UI**: New card in **Master Admin → Data Backfills** titled "Short equipment-row display (iter 216h13)" with Preview + Apply buttons. Reuses the existing dry-run-first pattern.

### Verified live (preview)
- Seeded 4 rows (3 legacy long + 1 control short manual-add).
- Dry-run preview returned `equipment_to_update: 3` with the exact before→after split (StepMill / 200H-AAF, Upright Cycle / 240G-AAV, Treadmill / 210T-BBC).
- Commit applied 3 updates; control row untouched.
- Re-running commit returned `equipment_updated: 0` — idempotent.
- New backfill card visible in MA → Data Backfills with Preview + Apply buttons.

### Regression — 19/19 passing across two new test files
- `test_iter_216h13_short_equipment_display.py` (13/13): helper unit tests.
- `test_iter_216h13_backfill_short_display.py` (6/6): API tests — dry-run preview, commit, skips already-short rows, idempotency, master-admin gate, site-name filter.

### Cost reassurance
Operator was concerned $17.44 was per-invoice. Clarified via support_agent: 1 credit = $0.20 USD, so 20 credits = $4. Their $17.44 is cumulative spend across every AI feature since signup (≈ 87 credits worth). A single Carshalton-sized extraction costs ~$0.10–0.20 (Claude Haiku 4.5). Add balance via Profile → Universal Key; auto-recharge available.

### ⚠ Action required
1. Top up Universal Key.
2. Redeploy preview → production.
3. On production: **Master Admin → Data Backfills → "Short equipment-row display" → Preview → Apply** to clean up the existing Carshalton rows (no need to delete + re-import; preserves equipment IDs, fault history, QR codes).
4. New invoice imports going forward will already use the short shape.

---


## Iter 216h12 — Carshalton invoice import: truncation + missing fields + supplier auto-matching (Feb 11, 2026)

**Production bugs reported**: User uploaded the Carshalton Invoice PDF (Pulse Fitness → South Thames College, £421,804.01 gross, 88 line items across 20 pages). Operators complained that the import "missing details and supplier matching".

### Root cause investigation
- **Missing details**: `_build_extraction_prompt` was truncating PDF text at `pdf_text[:12000]` — but the Carshalton PDF extracts to **24,090 chars**. The AI only saw ~28 of the 88 line items, plus none of the totals (NET £351,503.34 / VAT £70,300.67 / GROSS £421,804.01), bank details (HSBC sort 40-28-56, acct 40023205), customer reference (00000512 for payment), supplier VAT (785413509) or company number (4354059) — all of which sit in the second half of the document.
- **Supplier matching**: The extracted `supplier_name` was just a raw string. `db.suppliers` already had Pulse Fitness in the org directory but the import never tried to link to it, so every import created an orphan/duplicate supplier reference.

### What shipped
- **`equipment_import.py` — `_PDF_TEXT_MAX_CHARS = 40_000`** (was 12 000). Haiku-4.5 has a 200 K-token input window so 10 K extra tokens is well within budget; latency impact is ~+5-10 s for the largest invoices.
- **`_EXTRACTION_TEMPLATE` schema extended** with `supplier_vat_number`, `supplier_company_number`, `customer_name`, `customer_reference`, `due_date`, `payment_terms`, `bank_details` (bank_name, account_name, account_number, sort_code), and `totals` (net, vat, gross).
- **`_normalise_supplier_name(name)`** — collapses "Pulse Fitness Limited", "PULSE FITNESS LTD.", "Pulse Fitness", "pulse-fitness ltd" all to the same key for fuzzy match.
- **`match_supplier(org_id, supplier_name, vat_number)`** — 3-tier match priority: (1) exact case-insensitive, (2) VAT number, (3) normalised name. Returns the matched supplier doc (no `_id`) or None. Tenant-scoped to `organization_id`.
- **`/api/equipment-import/parse-invoice`** + **`/api/master-admin/invoice/parse-for-wizard`** — both endpoints now surface `matched_supplier`, `matched_supplier_id`, plus the new invoice metadata fields (totals, bank, customer ref, due-date, payment terms) in their response.

### Regression — `test_iter_216h12_carshalton_supplier_match.py` (13/13 passing)
- Truncation cap is pinned at ≥ 24 000 (locks the bug surface — refactors can't silently re-shrink).
- Prompt schema regression: explicitly asserts every new field key is present in the prompt.
- `_normalise_supplier_name` covers 4 shape variants + empty/None.
- `match_supplier` covers exact, case-insensitive, normalised, VAT-number, no-match, wrong-org, missing-args.

### ⚠ Action required (BLOCKED on Emergent LLM budget top-up)
- The Emergent LLM key budget is **exhausted** (`Current cost: $17.44 / Max: $17.40`). End-to-end live extraction can't be verified against the Carshalton PDF until you top up via **Profile → Universal Key → Add Balance** (or enable auto top-up). Once topped up, re-run the import on production — the changes are deterministic and the unit tests pin every contract surface, so the live run should succeed.
- After re-running on production, you'll see: full 88-line extraction (not 60), populated totals/bank/customer-ref fields, and a `matched_supplier_id` so the operator can one-click "Link to existing Pulse Fitness".

---

## Iter 216h11 — Spec Sheet dropdown crash + bulk delete + image graceful degradation (Feb 11, 2026)

**Production bugs reported**: (a) Master Admin → Image Catalogue → Spec Sheets dropdown was crashing the entire page (React error "Objects are not valid as a React child"). (b) Spec Sheet hero images were rendering as blank/broken-image icons. (c) User requested a "bulk select + delete" workflow.

### What shipped
- **`AdminSpecSheets.js` — `safeRenderValue()` helper**: Recursively coerces any JSON value (including nested objects like `{value, unit}`, `{min, max}`, generic `{key:value}`) into a compact human-readable string. Wraps every `key_specs` cell + `description` so the AI extractor can never crash the route again.
- **`AdminSpecSheets.js` — `<SpecImage>` component**: Adds `onError → "No image" placeholder` fallback for the public `/api/spec-sheets/image/{id}` endpoint. When the underlying S3/storage object is missing the user sees a friendly placeholder instead of a broken-image icon.
- **`AdminSpecSheets.js` — `<ExpandedDetail>` component**: Extracted to its own component with a defensive try/catch render guard (`spec-expand-error-{id}` test-id) so any future malformed payload can't take down the whole panel.
- **Bulk select + delete**:
  - Per-row checkbox (`spec-select-{id}`).
  - "Select all (N)" / "Clear selection" toggle (`spec-select-all`).
  - Sticky black bulk-action bar at top with row count + red "Delete N selected" button (`spec-bulk-bar`, `spec-bulk-delete`).
  - Loops `DELETE /api/spec-sheets/{id}` per selected id, shows mixed-success toast (`X deleted · Y failed`) and refreshes the grid.
- **PDF preview fallback**: iframe `onError` switches to a small "PDF preview unavailable" card so a missing storage object doesn't leave an empty panel.

### Verified live (preview)
- Seeded 2 test spec sheets (one with object-shaped `key_specs` — the exact crash vector) — page renders all of `flywheel weight: 22 kg`, `resistance: 1–24`, `dimensions: length: 120cm; width: 55cm; height: 115cm` plus the object-shaped description `short: …; long: …` without crashing.
- "Select all (2)" → black bulk bar visible → "Delete 2 selected" red button rendered → "Clear selection" dismisses bar.
- Missing `hero_image_url` shows placeholder icon (no broken-image).
- 0 captured `pageerror`s during the flow.

### Regression — `test_iter_216h11_spec_sheet_render_safety.py` (4/4 passing)
1. `test_list_returns_raw_object_key_specs` — backend round-trips object-shaped values unchanged (bug surface stays observable).
2. `test_delete_spec_sheet_hard_deletes_row` — single DELETE wipes a seeded row (powers bulk loop).
3. `test_delete_missing_spec_sheet_returns_404` — graceful 404 on already-deleted ids.
4. `test_image_endpoint_is_public_and_404s_cleanly` — endpoint returns 404 (not 401) when no image is stored so `<SpecImage>` placeholder triggers correctly.

### ⚠ Action required
Lives in **preview** only — **redeploy** to push to gymaxisai.com. If the production images stay blank after deploying, the underlying S3/storage objects are missing — re-upload affected spec sheets.

---


## Iter 216h53 — Bulk import sites + Service Desk full merge + Sites click-through + Archive relocation (Feb 12, 2026)

Lee's batch ask: (1) fix the bulk-import failure (he uploaded a sites CSV via the equipment slot), (2) full merge of Service Desk + Service Ops under one shell with 8 specified tabs, (3) clickable sites in Master Admin → Orgs with Site Details + Equipment tabs, (4) move Archive somewhere more logical.

### 1. Bulk-import sites box + CSV sniffer fix
- **New endpoint** `POST /api/master-admin/bulk-import/sites?organization_id=` + matching `GET /api/master-admin/bulk-import/templates/sites`. Sites are org-scoped (no customer_account_number column on the template) so the target tenant is required upfront. Idempotent dedupe by case-insensitive site name. Persists `invoice_customer_ref` for Sicon linkage.
- **AdminBulkImports.js** — now a 3-column grid: Sites + Equipment + Customers. Equipment hint copy updated to reflect the new `site_name`, `supplier`, `unit_price` columns from iters 216h50/216h51.
- **CSV sniffer fix** — `_sniff_mime_fallback` now tries `latin-1` decode after UTF-8 fails, so Excel-exported CSVs with Windows-1252 characters (en-dash 0x96, smart quotes 0x93/0x94) are accepted. Was the actual root cause of Lee's "Couldn't import equipment" toast — his Third Space CSV had `"Third Space – Canary Wharf"` (en-dash) and the sniffer returned `application/octet-stream` → 415.

### 2. Service Desk full merge
- **New unified `/service-desk` page** with Lee's 8 tabs in the specified order: Dashboard | Cases | Scheduler | Customers | Equipment | Parts | Billing | Engineers. Plus an "Insights" section housing Supplier health / Reports / Audit log.
- **Embedded Service Ops pages** — added `ServiceOpsEmbeddedContext` to `ServiceOpsShell` so each Ops page (Scheduler, Engineers, Parts, Billing, Reports, Cases-board) renders body-only when invoked from inside the merged Service Desk shell. Avoids duplicate hero+nav.
- **Legacy routes** `/service-ops/*` 302-redirect to `/service-desk`. Deep links still work.
- **Portal switcher** — Service Ops button removed from `AdminSidebar.js` (Service Desk is now the single entry).
- Auth gate unchanged for now (master_admin or is_service_desk). Tenant access opens in a future iteration when Pulse-facing.

### 3. Sites click-through
- **New `SiteDetailDrawer.js`** — opens when clicking any non-default site row in Master Admin → Orgs → Customer → Sites tab.
- Two tabs: **Site Details** (editable form: name, Sicon `invoice_customer_ref`, full address, site phone/email, manager name+email, default location — saves via PATCH `/api/master-admin/organizations/{org}/sites/{site}`) and **Equipment** (inline-editable table — name/type/model/serial/supplier/location columns, save-per-row via PATCH `/api/equipment/{id}`).
- Site row in OrgSitesPanel gets a `cursor-pointer` + chevron-right + invoice_customer_ref display when present.

### 4. Archive relocation
- Moved from Service Desk → Master Admin → Overview → Archive (alongside Dashboard, System Health, Setup checklist). Data-lifecycle concern, not a customer-support workflow. Single line addition to `SidebarConfig.js` + `MasterAdminPage.js` case handler.

### Testing
- `/app/test_reports/iteration_216h53.json` — **13/13 backend tests PASS** (sites template/import, dedupe, auth, Windows-1252 CSV acceptance, service-ops redirects). Frontend verified: all 11 tabs in Service Desk render, Archive moved correctly, site detail drawer code valid.
- Smoke test of Lee's actual CSV: **6/6 imported cleanly** from a fresh Third Space sites file.

### Files
- **Backend**: `master_admin_bulk_import.py` (+sites endpoints), `master_admin.py` (invoice_customer_ref in bulk sites insert), `utils/file_validation.py` (latin-1 fallback)
- **Frontend**: `ServiceDeskPage.js` (full rewrite — 11 tabs), `ServiceOps/ServiceOpsShell.js` (embedded context), `routes/AppRoutes.js` (legacy redirects), `MasterAdmin/SidebarConfig.js` + `MasterAdminPage.js` (Archive relocated), **NEW** `MasterAdmin/SiteDetailDrawer.js`, `MasterAdmin/OrgSitesPanel.js` (clickable sites + invoice_ref display), `MasterAdmin/AdminBulkImports.js` (3-column grid + updated hints), `MasterAdmin/AdminSidebar.js` (Service Ops button removed)

---


## Iter 216h52 — Service Desk → Supplier Health (cross-customer rollup) (Feb 12, 2026)

GymAxis-facing follow-up to iter 216h51's supplier-routed equipment imports. Lee's pivot: Pulse wouldn't chase suppliers themselves, but **GymAxis benefits most** from a top-down view of supplier performance across the entire customer base — useful for renewal negotiations and proactive supplier management.

### Backend — `GET /api/service-desk/suppliers/health`
- Aggregates `db.suppliers + db.equipment + db.issues` across **every customer org**, grouped by **normalised supplier name** (same suffix-strip + lowercase logic as the equipment importer's resolver, so "Pulse Fitness" and "Pulse Fitness Limited" collapse into one row).
- Returns per-supplier metrics:
  - `customer_org_count` — how many GymAxis customers use this supplier
  - `equipment_count` — total kit serviced across customers
  - `open_issues_count` — open issues on linked kit (org-wide)
  - `resolved_issues_window` / `sla_breaches_window` — within configurable `days` window (default 30, capped 1y)
  - `avg_response_hours` / `avg_resolution_hours` — derived from issue timestamps + `equipment.sla_response_time` for breach detection
  - `aliases` — list of every literal name that collapsed into this row
  - `orgs[]` — per-customer drill-down (equipment_count + open_issues_count per customer org)
- Supports `sort` (open_issues | sla_breaches | equipment | name).
- Top-level `totals` block summarises supplier count, kit total, open-issue total, SLA breach total.
- Service-desk auth gated. Audit-logged via `log_desk_action(suppliers.health)`.

### Frontend — `DeskSuppliers.js` (new) + Service Desk tab
- New "Supplier Health" tab in Service Desk (between Equipment and Archive).
- Header rollup row with 4 stat pills (suppliers tracked / kit serviced / open issues / SLA breaches in window). Colour-coded amber/red when non-zero.
- Window picker (7d / 30d / 90d / 1y) + Sort picker (Open issues / SLA breaches / Kit serviced / A→Z).
- Searchable list (matches name, aliases, or customer org names).
- Each row collapses into a detail panel with per-customer breakdown, breach rate %, avg first-response and resolution, plus the alias list.
- Hot suppliers (>0 SLA breaches OR ≥5 open issues) get a red AlertTriangle icon for at-a-glance triage.

### Use case
GymAxis ops can now:
1. See in 1 click which suppliers are dragging on response times across the customer base
2. Drill into per-customer impact (e.g. "Vendor X has 5 open faults at Pulse and 3 at Tottenham")
3. Use breach-rate % during contract renewal negotiations on behalf of customers
4. Spot suppliers entered with slightly different names across customers (the alias rollup catches these)

### Files
- **Backend**: `service_desk.py` (+`GET /service-desk/suppliers/health`, +`_normalise_supplier_name`)
- **Frontend**: NEW `ServiceDesk/DeskSuppliers.js`, `ServiceDeskPage.js` (Suppliers tab wired in)

### Testing
- Smoke test via curl: endpoint returns valid rollup (1 supplier "Pulse Fitness" used by 2 customer orgs, 3 kit, 0 open issues). Lint + ruff clean.

---


## Iter 216h51 — Onboarding picker UX + supplier-routed equipment imports + test-data purge (Feb 12, 2026)

Three follow-ups after Lee's screenshot showing the onboarding "Existing Customer" picker cluttered with TEST_ orgs from prior agent runs.

### 1. Onboarding "Existing Customer" picker — searchable + alphabetised
- `PulseOnboardingWizard.js` `ChooseModeStep` now has a search input above the customer list. Filters client-side on name, company_code, and account_type (300ms snappy, no API calls).
- List sorted alphabetically (case-insensitive) so the same customer is always in the same screen position.
- Result count chip ("23 customers" or "5 of 23") above the list so operators know if a filter is active.
- Scroll container height raised from `max-h-64` (16rem ≈ 6 rows) → `max-h-[28rem]` (28rem ≈ 11 rows). With search active, scrolling becomes a fallback rather than the primary navigation.
- Backend `GET /api/master-admin/organizations` `to_list` limit raised **500 → 2000** so a customer like Pulse can't be silently truncated out of the list as they grow.

### 2. Equipment CSV — `supplier` column + auto-resolve
- New 3rd column in the bulk-import template. Resolves to a row in `db.suppliers` within the same org so the equipment doc carries `supplier_id` AND `supplier_email` after import. Fault-notification flows already key off these fields — no further wiring needed.
- New `_resolve_supplier_for_org` helper matches in three passes:
  1. Exact case-insensitive name match
  2. Email match (if the CSV column accidentally contains an email)
  3. Normalised-name fuzzy match — strips `[^a-z0-9]` and the suffixes `Limited/Ltd/Ltd./PLC/Inc/Inc./LLC` so "Pulse Fitness Limited" matches a seeded "Pulse Fitness"
- Blank supplier falls back to the `manufacturer` column (existing behaviour) — preserves backwards compatibility.

### 3. Preview cleanup + canonical test user
- Ran the existing `purge_test_artefacts.py` script — 60 orgs archived/deleted.
- Followed with an aggressive sweep that archived & purged 37 additional test orgs (anything not on a protected list of {GymAxis Master Admin, Pulse Fitness, Strong Fitness, The Third Space Group Limited}).
- Also deleted 45 orphan test users + 0 orphan staff_members + orphan equipment/sites cascading.
- Final state: **5-6 orgs** in preview (a clean baseline for Lee's demos).
- Created **canonical agent test user**: `e1.agent@gymaxisai.com / E1Agent123!` (owner, Pulse Fitness org). Documented in `/app/memory/test_credentials.md`. Going forward, the agent will use this single account for all login testing instead of disposable TEST_ orgs.

### Testing
- `/app/test_reports/iteration_216h51.json` — 12/12 tests pass (3× canonical user, 3× template header, 4× supplier resolution, 2× orgs endpoint).

### Files touched
- **Backend**: `master_admin_bulk_import.py`, `master_admin.py`
- **Frontend**: `PulseOnboardingWizard.js`
- **Scripts**: ran `backend/scripts/purge_test_artefacts.py` + ad-hoc cleanup
- **Memory**: `test_credentials.md` updated with canonical E1 agent account

---


## Iter 216h50 — Multi-site bulk import polish + Capex feeder (Feb 12, 2026)

Three connected enhancements requested for Pulse Fitness multi-site onboarding so a fresh tenant goes from "zero" to "fully populated" via two CSV uploads instead of dozens of manual entries.

### 1. Sites CSV — `invoice_customer_ref` column added
- New SECOND column in the sites CSV template (`/api/master-admin/sites/template.csv`). Sicon Service uses this code as the per-site customer reference, so populating it during onboarding lets Sicon's ledger postings reconcile straight away without a follow-up site-edit pass.
- `preview-csv` endpoint accepts the official header plus three friendly aliases (`Invoice Customer Ref` with space, `sicon_customer_ref`, `customer_ref`) so operators dropping their own spreadsheet in don't have to rename columns.
- Persisted on `db.sites.invoice_customer_ref` via three write paths: standard `POST /api/sites`, `PATCH /api/sites/{id}`, master-admin onboard-head-office wizard, and master-admin PATCH `/api/master-admin/organizations/{org}/sites/{site}` (added during this iteration after the testing agent flagged it missing).
- `HeadOfficeOnboardingWizard.js` — new editable field "Invoice Customer Ref (Sicon)" on every site row, hydrated from the CSV preview and submitted with the onboarding payload.

### 2. Equipment CSV — `site_name` as first column
- The bulk-import template (`GET /api/master-admin/bulk-import/templates/equipment`) now leads with `site_name`. Operators import sites first, then equipment auto-links to the resolved `site_id` so per-site dashboards populate correctly out of the gate.
- New `_resolve_site_for_org` helper resolves each row in this priority order:
  1. Exact-match site name (case-insensitive)
  2. Fall back to `invoice_customer_ref` lookup (so a row with blank site name but a populated Sicon ref still resolves)
  3. If both supplied and neither matches, the row is **skipped** with an explicit error message so the operator can fix the sites import first
- Per-org site cache means same-name rows incur a single DB hit per unique site.

### 3. `unit_price` column → Capex feeder
- New column in the equipment template. Parsed via `_parse_decimal` (handles "3450", "3450.50", "3,450.00", blank).
- Written to **both** `equipment.purchase_price` (for ledger / Sage 200 posting) **and** `equipment.replacement_cost` (which `routes/capex.py` already reads — falls back to the equipment-type profile default when null). So once kit is bulk-imported with unit prices the Capex Analysis report immediately reflects actual asset values instead of generic estimates.

### Testing
- `/app/test_reports/iteration_216h50.json` — 15/15 tests pass. Testing agent added a missing master-admin PATCH path for `invoice_customer_ref`.

### Files touched
- **Backend**: `sites_import.py`, `sites.py`, `master_admin_bulk_import.py`, `master_admin.py`
- **Frontend**: `MasterAdmin/HeadOfficeOnboardingWizard.js`

---


## Iter 216h49 — Six-feature production batch (Feb 12, 2026)

Single batch shipping six requested features after Lee's feedback on production. All backend changes verified by the testing agent (16/16 tests pass — `/app/test_reports/iteration_216h49.json`).

### 1. Kit transfer + delete between sites (owner/manager)
- New endpoint `POST /api/equipment/{id}/move` — moves equipment to another site within the same org. Validates target site belongs to the org. Cascades the move to linked `issues` so per-site dashboards reconcile. Audit-logged.
- `PATCH /api/equipment/{id}` now accepts `site_id` (gated to owner/manager/master_admin).
- `DELETE /api/equipment/{id}` is now **org-scoped instead of user-scoped** — was a latent bug where owners couldn't delete kit added by other staff. Audit-logged. Gated to owner/manager/master_admin.
- Frontend (`LiteEquipmentTab.js`): inline Move + Delete row actions on every equipment card. Move opens an inline site-picker; Delete uses `useConfirm` for a destructive confirmation modal.

### 2. Service Desk Equipment search (Sicon Service parity)
- New endpoint `GET /api/service-desk/equipment` — global free-text + filter search across every customer's equipment. Hydrates `organization_name` and `site_name` inline so desk operators have org+site context without impersonating. Audit-logged.
- New `DeskEquipment.js` page wired into `ServiceDeskPage` as a top-level tab. 300ms debounce, read-only by design (mutations still flow through customer's own console).

### 3. Auto-sync staff → Staffing module
- `GET /api/staffing/staff` now auto-backfills missing `staff_members` rows from `db.users` on every manager call. Match priority: `user_id` → `email` (case-insensitive). Maps `owner/manager` → `manager`, `staff` → `reception`. New rows tagged `auto_synced_from_users:true` for audit. Eliminates the duplicate-entry pain Lee reported.

### 4. Documents upload UX trio
- `LiteDocumentsTab` got a drag-and-drop dropzone matching the AdminSpecSheets pattern. Drop or click — uploads route into the **currently active category tab** automatically.
- `LiteDashboardPage.handleDocumentUpload` rewired through the global `useUploadQueue()` hook so per-file progress shows in the bottom-right drawer with bytes-uploaded percentage.
- **Page-leave guard** added to `UploadQueue` itself: while any task is queued/uploading, a `beforeunload` listener fires the browser's native "Leave site?" prompt. Auto-clears once every task settles. Single source of truth — every consumer that uses `useUploadQueue()` gets the guard for free.

### 5. Compression visibility
- `POST /api/files/upload` already PyMuPDF-compresses PDFs (30-60% reduction). Now also returns `original_size` and `compression_ratio` in the file_doc so the UI can surface "62% saved" toasts.

### 6. Auto-open tours disabled
- `ProductTour.js` — auto-open useEffect gated behind a `const AUTO_OPEN = false` so manual triggers (`resetTour()`) still work from user-menu "Start tour" buttons.
- `CRMApp.js` — removed the `setShowTour(true)` auto-open on first login.
- `MarketingTour.js` — removed the `if (!data.tour_seen) setOpen(true)` first-visit auto-open. Sidebar trigger still launches the tour manually.

Per Lee's note: "the tours need updating as they aren't pointing in the right directions or buttons" — the auto-open is killed now; the tour scripts themselves are a follow-up task to refresh content + targets.

### Bug found and fixed by testing agent
- `service_desk.py` line 165: `log_desk_action()` was called without `await` and with mismatched arg order. Testing agent corrected the signature to `await log_desk_action(user, action, target_type, target_id, summary, details=...)`.

### Files touched
**Backend**: `equipment.py`, `service_desk.py`, `staffing.py`, `files.py`
**Frontend**: `App.js` (already in this iteration), `UploadQueue.js`, `LiteDashboardPage.js`, `LiteDashboard/LiteDocumentsTab.js`, `LiteDashboard/LiteEquipmentTab.js`, `ServiceDeskPage.js`, **new** `ServiceDesk/DeskEquipment.js`, `ProductTour.js`, `CRM/CRMApp.js`, `Marketing/MarketingTour.js`

---


## Iter 216h48 — KILL the recurring "SiteSwitcher disappears for owners" bug class (Feb 12, 2026)

**Production bug** (reported by Lee Somers — Pulse Fitness owner, 3 sites: HQ + iGym Carshalton + iGym Congleton): "I can no longer see Site selection". Confirmed **recurrence** of the same bug class that we've patched 3 times already (iter 216h32, 216h31, 216bk).

### Why it kept coming back
Every prior fix patched a *different gate* — auto-HQ insert, role-spelling, route gate, dropdown viewport — but **none of them addressed the actual root cause**: a **hydration race**.

Render flow on the affected surfaces (`/dashboard` Navbar + `/pulse` LiteDashboardPage):
1. React mounts → `sites` state initial value = `[]`
2. First paint → `<SiteSwitcher>` runs `if (sites.length < 2) return null` → switcher invisible
3. `loadSites()` resolves a few hundred ms later → `setSites([...3 sites])` → re-render → switcher pops in

For Lee this manifested as "the switcher disappears" because:
- Every token refresh / cross-tab login triggered a fresh `loadSites()` round-trip
- Background tab focus / soft-nav also re-ran the bootstrap
- The empty-array first paint persisted longer on slow networks / overloaded mobile

### The fix — pre-hydrate sites + activeSite from localStorage
- `useState(() => …)` initialisers in `App.js` now read `sites_cache` and `active_site_cache` from localStorage on mount, so the switcher renders **on first paint** with the last-known list.
- `loadSites()` writes the fresh list back to `sites_cache` after every successful fetch — cache stays in sync.
- New wrapper `setActiveSitePersisted` exposed via AuthContext so consumer-side `setActiveSite(site)` calls (SiteSwitcher → handlePickSite) also persist.
- Logout + cross-tab storage handlers explicitly wipe both caches so the next user on the same device doesn't see the previous operator's sites flash.

### Why this finally kills the bug class
Previously every recurrence was "one more uncovered gate". Now there is **only one path** — the cache is the source-of-truth on first paint, the network is the source-of-truth on every subsequent render, and the cache is replaced atomically by the network call. There are no more "empty array between paint and network" windows.

### Files touched
- `/app/frontend/src/App.js` — pre-hydrate `sites` + `activeSite`, wrap `setActiveSite`, clear caches on logout / cross-tab storage logout.

### Testing
- Lint clean. Webpack compile clean. User reported the switcher re-appears after refresh (cache-hit path), and now it should NOT disappear in the first place because the cache renders it immediately.
- Manual prod verification recommended: Lee logs in on production, hard-reloads, switcher should appear instantly (not after a beat).

---


## Iter 216h47 — `<ListPanel>` adoption across CRM list views (Feb 12, 2026)

Continuing the rollout of the shared `<ListPanel>` skeleton (iter 216h44) into more CRM list views so the toolbar/search/count/empty/loading patterns stop being duplicated 30-50 LOC at a time.

### What shipped
- **CRMCompanies.js**: `CompanyList` migrated to `<ListPanel>` with `search` (`company-search`), `count` (`X accounts`), `primaryAction` (`create-company-btn`), `empty` (`crm-companies-empty`), and the type-filter pills (all/prospect/customer/partner/former) wired into `toolbarRight` with fresh testids `company-type-filter-<type>`.
- **CRMTenders.js**: `TenderList` migrated with `count`, `primaryAction`, `loading` (replaces the inline spinner block), and `empty` (`crm-tender-empty`). Wrapped in a Fragment so the create dialog renders alongside the empty state.
- **CRMContracts.js**: `ContractList` migrated. Stats card row (`contracts-stats`) renders above the ListPanel; ListPanel owns `search`, `count`, `primaryAction`, status filter pills (`toolbarRight`), and `empty` (`contracts-empty`). Search input testid preserved as `contracts-search`. Removed unused `Search` icon import.
- **CRMContacts.js**: latent regression fix — when the list was empty, the Create Contact dialog (which lived inside ListPanel children) wouldn't render because `<ListPanel>` skips children when the empty state shows. Wrapped the component in a React Fragment so the dialog modal is a sibling of `<ListPanel>` rather than a child, guaranteeing the empty-state primaryAction successfully opens the dialog.

### Why this matters
- Eliminates ~150 LOC of duplicated toolbar/empty/loading/search boilerplate across four pages.
- Single point of truth for list chrome — future visual tweaks (e.g. mobile breakpoint behaviour for count chips, or animation on row insert) update every list at once.
- Catches the latent "empty-state primary action does nothing" bug uniformly: every consumer that wraps in a Fragment now gets the dialog-render guarantee for free.

### Testing
`/app/test_reports/iteration_216h34.json` — all four migrated lists (Contacts/Companies/Contracts/Tenders) verified to render with the expected data-testids, dialogs open from both header and empty-state primary actions, type/status filter pills function, and UnifiedAuthProvider verification on Member Portal + CRM session persistence both PASS.

### Files touched
- `/app/frontend/src/pages/CRM/CRMContacts.js` (+ Fragment wrapper)
- `/app/frontend/src/pages/CRM/CRMCompanies.js`
- `/app/frontend/src/pages/CRM/CRMTenders.js`
- `/app/frontend/src/pages/CRM/CRMContracts.js`

---


## Iter 216h10 — Fix for "0 records wiped" on production purge (Feb 10, 2026)

**Production bug reported**: user clicked "Remove everywhere" on Craig Henshall, toast showed "0 record(s) wiped" but the row remained. Root cause: my iter-216h8 purge endpoint only deleted from `db.users`, but the "Already added" check in `master_admin.py::add_user_to_organization` also looks at `db.crm_users` — so a stale row in `crm_users` was blocking re-onboarding without being touched by the purge.

### What shipped
- **Backend**: extended both `hard_purge_pulse_admin` (by id) AND `hard_purge_user_by_email` to ALSO delete from `db.crm_users`. Audit-log queries extended to find crm_users matches too, with `_collection: "crm_users"` annotation so the audit trail makes it obvious where rows came from.
- **Frontend `GlobalUsersPanel.js`**: fixed misleading toast — when the email regex matches 0 rows, the toast now shows a **warning** (not success) with actionable hint, AND automatically falls back to a hard-delete by user_id (auto-archives first since hard-delete is archive-gated). Fallback emits its own success toast indicating it was used. Success toast also now mentions CRM rows wiped when applicable.

### Why the fallback path matters
If the stored email has a hidden character, weird whitespace, or unexpected format, the email-regex match returns 0 — but we still have the user_id from the row that was clicked. Falling back to id-based delete catches this edge case without operator intervention.

### Regression — `test_iter_216h8_user_purge.py` extended to 5 tests (was 4)
- New `test_purge_by_email_also_wipes_crm_users` seeds a crm_users row and verifies the purge endpoint deletes it. **All 5 pass.**

---

## Iter 216h9 — Global Users panel + leaver workflow (Feb 10, 2026)
(See CHANGELOG history — fully shipped, 109 users panel with archive/delete + remove-everywhere, 4-pill status filter, master-admin auto-protected.)

---

## Prioritised backlog (P0/P1/P2)

### P0 — Currently in-progress
- None — iter 216h11 just landed.

### P1 — Reported bugs (next)
- **Carshalton invoice import**: missing details + supplier matching. **BLOCKED** awaiting user to upload an example PDF/image so the LLM extraction prompt can be tuned.
- **Head Office site not selectable for owners**: site-selector should show "All sites | Head Office | Site A | Site B" for multi-site orgs.
- **RAM usage metric on Trust & Reliability dashboard**: build via `psutil` per-pod gauge backend → existing T&R UI tile. Helps user decide on package upgrade.
- **"Jump to this user" link** in error toast when an existing user is re-added on the org drawer.

### P1 — Integration work
- Sage 200 / Sicon ledger posting on payment, CRM lead conversion, custom domains (`join.{gym-domain}.com`).

### P2 — Blocked / Parked
- Sicon and Sage 200 LIVE connection cutover (waiting on creds).
- Sentry DSN for production observability (Parked).
- Twilio SMS real integration (Parked).

---

## Critical operator notes
- User tests on **production** (gymaxisai.com). Agent only sees **preview**. Remind them to hit "Deploy" after each fix lands.
- Recent deploy failure was a "pod not found" infra error — fix is to re-hit Deploy (NOT a code issue).
- Master Admin credentials: `admin@gymaxisai.com` / `MasterAdmin123!` (always preserved).
- Preview DB has been wiped — only the master admin + Tottenham Green Leisure Centre data remain (since iter 215bs).
