# GymAxis Design System — Master Admin + Operator portals
## Iter 220m (Brand canon refresh · May 26, 2026)

> **Brand palette → see [`/app/BRAND_PALETTE.md`](BRAND_PALETTE.md).**
> That doc is the **single source of truth** for hex codes, gradients,
> and "do not use" anti-patterns. Do not reproduce hex values here.
> This file covers component vocabulary (empty states, button hierarchy,
> shared primitives) only.

*Original iter: 216h27 · Feb 11, 2026*

Single canonical reference for empty states and button hierarchy. This doc was created as the deliverable for the **D2 Empty-state pass** and **D3 Button-hierarchy audit** items in `/app/memory/UX_AND_PROCESS_BACKLOG.md`. Whenever a new panel, tab, list, drawer or wizard is added, use the patterns below.

---

## D2 — Empty-state pattern (mandatory for every list/grid)

Use the shared `<EmptyState>` component at `/app/frontend/src/components/shared/EmptyState.js`. Three slots:

| Slot | Purpose | Constraint |
|---|---|---|
| `icon` | A Lucide icon that hints at the missing thing (`Users`, `Wallet`, `Receipt`, `ScrollText`, `Smartphone`…). | One per state. No emoji. |
| `title` | What's missing. ≤ 6 words. Avoid "No X". Prefer the *opportunity*: "Your members' home screen is blank" instead of "No cards yet". | Sentence case. |
| `hint` | Why it matters + how to fix. 1 short sentence. | ≤ 24 words. |
| `primaryAction` | Single CTA that fixes it. Optional but recommended. | Exactly one. |
| `secondaryAction` | "Clear filter", "View example", "Import CSV". | Optional. |

### Coverage status (iter 216h27)

| Panel | EmptyState adopted | testId | Iter |
|---|---|---|---|
| Memberships → MemberHome (no members) | ✅ | `mbr-empty-add` | 215bt |
| Memberships → Invoicing | ✅ | — | 215bt |
| Operations → Faults | ✅ × 2 | — | 215bt |
| CRM → Pipeline | ✅ (partial) | — | 215bt |
| Marketing → Campaigns | ✅ | — | 215bt |
| Marketing → Audiences | ✅ | — | 215bt |
| LiteDashboard → Staffing | ✅ | — | 215bt |
| LiteDashboard → Faults | ✅ | — | 215bt |
| **Memberships → Mobile App Builder** | ✅ ◀ **iter 216h27** | `mab-empty-state` | 216h27 |
| **Master Admin → Login events** | ✅ ◀ **iter 216h27** | `login-events-empty` | 216h27 |
| **Master Admin → Audit log (desktop + mobile)** | ✅ ◀ **iter 216h27** | `audit-log-empty`, `aud-empty-mobile` | 216h27 |

### Still TODO (low priority — content rich already)
- CRM → Leads list (current "No deals in pipeline" inline text)
- Master Admin → Spec Sheets (no list view yet, only upload)
- Service Desk → Tickets (handled by ticket app, not our concern)

---

## D3 — Button hierarchy — capped at 3 variants (+ 1 destructive)

Use the shared `<Button>` component at `/app/frontend/src/components/shared/Button.js`. **Do not write new inline button styles.** If your design needs a 4th variant, get explicit sign-off — it usually means the screen has too many actions competing.

### The vocabulary

| Variant | Visual | Use for | Rule of thumb |
|---|---|---|---|
| `primary` | Brand navy→purple gradient filled, white text, bold | The *one* "do the thing" action on the screen | **Exactly one per screen**. If you reach for two, the screen has two CTAs — split into a sub-task or demote one. |
| `secondary` | Outline + neutral background | Supporting actions next to the primary | Refresh, Cancel, Bulk import, Export. Pluralisable — 2-3 max next to a primary. |
| `tertiary` | Text-only with underline-on-hover | Low-emphasis links and inline navigation | "View all", "Manage", "Reset filter". No more than 4 visible at once. |
| `destructive` | Soft red filled | Delete / Archive / Revoke / Disconnect | Always confirm via `useConfirm()`. Never use as primary for first-render screens. |

### Sizes
- `sm` (text-xs, px-2.5 py-1.5) — inline in dense tables.
- `md` (text-sm, px-3 py-2) — **default**, use everywhere unless you have a reason.
- `lg` (text-sm, px-4 py-2.5) — hero CTAs in empty states + onboarding.
- `icon` (p-2, square) — Iter 216h37. **Icon-only** action button — pair with `ghost`/`ghostDestructive` + `title` for accessibility.
- `iconSm` (p-1.5, square) — Iter 216h37. Tighter version for very dense row actions (e.g. inline plan list actions).

### Iter 216h37 — Ghost variants (row actions)

`ghost` and `ghostDestructive` are dedicated to **row-action icon buttons**: edit / archive / delete / toggle / copy / week-nav / drawer-close. No border, transparent background, soft hover surface that doesn't compete with table content.

| Variant | Hover | Use for |
|---|---|---|
| `ghost` | Subtle neutral (`bg-black/[0.06]`) | Edit, Copy, Toggle, drawer Close, week prev/next, Resume. |
| `ghostDestructive` | Red-tinted (`bg-red-500/15`) | Archive, Delete, Cancel-row. |

Always pass a `title="…"` so the icon has an accessible label. Don't pass children — `icon` / `iconSm` sizes skip the text span automatically.

### Quick examples

```jsx
import Button from '@/components/shared/Button';
import { Plus, Download, Trash2 } from 'lucide-react';

// One primary, supporting secondaries.
<Button variant="primary" icon={Plus}>Add member</Button>
<Button variant="secondary" icon={Download}>Export CSV</Button>
<Button variant="tertiary">View all</Button>

// Destructive (always behind a confirm).
<Button variant="destructive" icon={Trash2}>Archive</Button>

// Iter 216h37 — Row-action icon buttons.
<Button variant="ghost" size="icon" icon={Edit3} title="Edit" />
<Button variant="ghost" size="icon" icon={Copy} title="Copy URL" />
<Button variant="ghostDestructive" size="iconSm" icon={Trash2} title="Archive" />

// Iter 216h40 — Cluster row-action buttons with hover-reveal + touch-friendly fallback.
<div className="group flex items-center justify-between …">
  <RowMeta />
  <RowActions>
    <Button variant="ghost" size="iconSm" icon={Edit3} title="Edit" />
    <Button variant="ghostDestructive" size="iconSm" icon={Trash2} title="Archive" />
  </RowActions>
</div>

// Iter 216h44 — `<ListPanel>` super-component bundles toolbar + loading + empty + rows.
<ListPanel
  search={{ value: q, onChange: setQ, placeholder: 'Search…', testId: 'list-search' }}
  count={{ value: total, label: 'contact' }}
  secondaryActions={[<ExportCsvButton key="csv" module="contacts" />]}
  primaryAction={{ label: 'New Contact', icon: Plus, onClick: openCreate, testId: 'create-contact-btn' }}
  loading={loading}
  empty={{ when: items.length === 0, icon: Users, title: 'No contacts yet', primaryAction: { label: 'Add your first contact', onClick: openCreate } }}
  data-testid="crm-contacts-list"
>
  {items.map(row => <Row key={row.id} row={row} />)}
</ListPanel>
```

### Iter 216h44 — `<ListPanel>`

Standardises the toolbar + loading + empty surfaces that every list view duplicates today. Rows stay caller-owned (too domain-specific to abstract).

Bundles:
- **Toolbar:** optional title/subtitle + search input + count chip + secondary actions array + primary CTA.
- **Loading state:** centred brand spinner.
- **Empty state:** delegates to `<EmptyState>` so the API matches existing usage.
- **Rows:** children in a `space-y-2` wrapper by default. Override with `bodyClassName` for grid layouts (Plans, Promotions cards) — e.g. `bodyClassName="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"`.

Adopted in CRM Contacts (iter 216h44), CRM Companies (iter 216h44 follow-up), Memberships Plans / Classes / Ads (iter 216h65), and Memberships Promotions (iter 216h65) — ~25 LOC saved per panel. Remaining target: CRMPipeline list view (deferred — its toolbar is too bespoke to fit without compromising the Kanban switcher).

### Iter 216h45 — `<UnifiedAuthProvider>` + `useUnifiedAuth()`

Single source of truth for all three platform tokens (main, crm, member). Watches `localStorage` cross-tab via `window.storage` plus an in-tab `gymaxis:auth-changed` event bus. **Auto-cross-logins** to CRM the moment the main token lands, eliminating the entire class of "logged in but CRM asks me to log in again" bugs.

API:
```js
const { tokens, identity, login, logout, refresh } = useUnifiedAuth();

tokens   = { main, crm, member };    // strings or null
identity = { main, crm };             // hydrated via /auth/me + /crm/auth/me
login({ scope, token, identity? });   // scope ∈ 'main'|'crm'|'member'
logout(scope?);                       // omit to wipe all 3
refresh.crm();                        // re-exchange main → CRM (use from 401 handlers)
```

Backwards-compatible: still writes to the same `token` / `crm_token` / `member_token` localStorage keys, so the 196 existing direct-localStorage readers across the platform keep working. Migration to `useUnifiedAuth()` is incremental.

First adoption: `CRMApp.js` bootstrap (iter 216h45). The bespoke per-tab session-flag + token-strip cycle (root cause of iter 216h43's Lee bug) is now gone entirely — the provider owns the auth lifecycle.

### Iter 216h40 — `<RowActions>` cluster

The hover-reveal pattern (`opacity-0 group-hover:opacity-100 transition`) had drifted into 4 slightly different incantations across CRM + Memberships row UIs. `<RowActions>` standardises it AND fixes a long-standing iPad/iPhone bug: native `:hover` is sticky on touch devices, so hidden-by-default row actions were unreachable on mobile. The component injects a one-time `@media (hover: none), (pointer: coarse)` rule that forces `opacity: 1` on touch.

Props:
- `alwaysVisible` — opt out of hover-reveal (detail pages).
- `align` — `right` (default) | `left`.
- `gap` — `0.5` | `1` (default) | `1.5` | `2`.
- `data-testid` — for tests.

Parent row **must** have the Tailwind `group` class.

### Anti-patterns we replaced (iter 216h27)
- Multiple `inline-flex items-center gap-1.5 text-xs font-semibold border rounded-md px-3 py-1.5 bg-white hover:bg-zinc-50` repeated everywhere → use `<Button variant="secondary">`.
- Custom blue-filled `style={{ background: '#0055FF' }}` (a **legacy / Pulse-only** hex — see `/app/BRAND_PALETTE.md`) for the "Generate" / "Save" CTA → use `<Button variant="primary">` which applies the canonical navy→purple gradient.
- 6+ variants of "View / Open / Manage" text links — collapse to `<Button variant="tertiary">`.

### Migration plan
The new component is opt-in — existing buttons will keep working. New panels MUST use `<Button>`. Old panels migrate over time on the panel's next feature touch. The `StaffOnboardingWizard.js`, `AdminAllSites.js`, `IntegrationsHub.js`, `OrgIntegrationsTab.js` shipped in iters 216h21-216h24 are the canonical examples for the new style — match their look when migrating.

---

## Iter 216h26 audit findings (see `/app/AUDIT_PORTAL_LINKS.md` for the full report)

**17 / 17 portal linkages verified.** One bug fixed: customer-onboarding org create now returns a 72 h invite link for the primary contact, alongside the legacy reveal-password handover (`POST /api/master-admin/organizations` → response payload `owner.invite_url`).
