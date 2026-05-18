# Known Bugs & Recurring Pitfalls

> Read this **first** when picking up work. Re-introducing one of these
> wastes a session. Update on every fix / new finding.

_Last refreshed: Iter 216h209 · Feb 18 2026_

---

## 🐛 Active issues (P0 / P1 still open)

### P0 — None currently open. (h208 site_id fix shipped.)

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
| Sicon (CAPEX) | ❌ MOCKED | Schema only | Live cost lookups — needs user credentials |
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

---

## ✅ Recently fixed (last 10 iters — don't break)

| Iter | Fix |
|------|-----|
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
