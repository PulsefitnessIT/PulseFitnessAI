# UX & Process Analyst Backlog
*Captured: 2026-04-28 (iteration 210). Master designer + process analyst review.*

This file is the canonical source for design / UX / analytics improvements that
came out of the pre-meeting strategic review. Each item has a rough effort
estimate and a "why" so we can pick them off in any order.

---

## 🎨 Design / UX

### D1. Design tokens layer (3h)
Replace hard-coded zinc/blue/cyan with CSS custom properties:
`--color-brand-primary`, `--color-surface-canvas`, `--color-surface-card`,
`--radius-card`, `--radius-pill`, `--shadow-elevated`, `--font-heading`,
`--font-body`. Lets us re-skin a 3rd brand in a day and unifies dark mode.

### D2. Empty-state pass (2h)
Top-10 panels need: name what's missing → why it matters → single CTA.
Targets: invoice list, payments list, equipment list, member list, marketing
campaigns, audit log, leads list, deals list, login events, mobile builder.

### D3. Button hierarchy audit (2h)
~8 button variants in the wild → cap at 3: Primary (one per screen),
Secondary, Tertiary. Document in design system page.

### D4. Typography lock-in (1h)
Pick 2 typefaces (heading + body), enforce. Today: pulse-font-heading +
system fallback + ad-hoc inline overrides.

### D5. Dark-mode commit (1d)
Half-baked across Master Admin. Either fully audit contrast ratios + ensure
every panel honours `dark:` classes, or strip dark mode out. **Decision
required.**

### D6. Mobile member-portal nav: 7 → 5 + More sheet (2h)
At 375px each tab is 53px wide; ergonomics research wants ≥44px + breathing
room. Move Family + Plan into a "More" bottom-sheet.

### D7. Login modal premium polish (2h)
Subtle gradient glow, brand tagline, 3-second submit animation
("Verifying… Loading dashboard…"). First impression on every customer.

### D8. Information density audit (3h)
Apply rule-of-three: max 3 KPIs per row, 3 hierarchy levels per page.
Pages that fail today: Master Admin Overview (30+ tiles), Tasks panel,
Operations Dashboard.

### D9. Landing-page motion ✅ SHIPPED (iter 210, Option A)

### D10. Public `/trust` page ✅ SHIPPED (iter 210, Option B)

---

## 📊 Process / Analytics

### P1. PostHog / Mixpanel installation (1h)
Single highest-leverage item on this list. Without behavioural analytics
every other product decision is guess-work. Recommend PostHog free tier
(self-host option, GDPR-friendly).

### P2. Pricing-page lost-intent capture (2h)
- Exit-intent modal: "what stopped you?" with 1-line text field
- Currency-toggle abandonment event when user switches to USD/EUR but
  doesn't click "Start trial"

### P3. Activation event tracking ✅ SHIPPED (iter 210, Option B)

### P4. Support ticket ↔ org context right-rail (2h)
On every support ticket: plan, MRR, NPS, last 3 logins. Turns support from
cost centre to account management.

### P5. Master Admin Overview rewrite — leading indicators (3h)
Replace vanity totals with actionable signals:
- Orgs with falling DAU (last 7d vs prior 7d)
- Contracts up for renewal in 30d
- Support cases > 48h old
- Integrations failing > 24h

### P6. NPS / CSAT loop (4h)
After onboarding completion + after trial end: 1-question NPS with optional
comment. Dashboard tile + per-org timeline.

### P7. Audit-log → per-org activity feed (2h)
Surface `audit_logs` as a customer-facing activity feed. Self-serve
forensics ("who changed our booking rules?") + soft compliance moat for
SOC 2 / ISO 27001 conversations.

### P8. Mobile App Builder card-tap analytics (3h)
Track `member_card_tap` events. Show a heat-map back to the operator in the
builder ("73% tap Class Booking · 0.4% tap Refer a Friend"). Continuous
optimisation loop.

---

## 🚀 Demo / Sales

### S1. ⌘K command palette ✅ SHIPPED (iter 210, Option A)

### S2. Live "active sessions" map (1d)
Geo-IP visualisation on `/login-events` — investors love watching real-time
dots light up across a UK map. Mentioned in iter 208 wrap-up.

### S3. Scheduled price changes (4h)
Master Admin can commit a price change to a future date. Audit-log calendar
view. Auto-email blast to active subscribers.

---

## ⏳ Already shipped / committed

- iter 207: Auth + CRM cross-login refactor + xenon rank-C lock
- iter 208: Auto-renewal cron + Login Event Timeline
- iter 209: Sidebar consolidation 21 → 14
- iter 210: ⌘K palette · Landing motion · Public `/trust` · Activation tracking

---

## Decisions still pending from the user
1. **D5 (Dark mode)**: commit fully or strip? Half-baked is worst of both
   worlds.
2. **P1 (PostHog vs Mixpanel)**: brand preference? Self-host vs SaaS?
3. **D6 (Mobile portal nav)**: comfortable with the More-sheet pattern?
