> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> Blueprint below unchanged. Mobile-specific implementations now in
> place since the doc was written:
>
> - **AdminMODConsole table** — wrapped in `overflow-x-auto` (iter
>   216h229) so the per-org rollup table scrolls horizontally on
>   phones instead of clipping.
> - **AdminMODSitesBulkImport** — same treatment.
> - **MOD operator dashboard** — inherits the global `[data-fab-rail]`
>   stacking + popover viewport clamp from the Wave 1 mobile audit.
>
> MOD-specific authentication / module gating logic is unchanged; the
> `account_type.startswith('mod_')` check still hides the Stripe
> onboarding step in the Setup Checklist (handled in
> `routes/account.py:onboarding_status`).

---


# Ministry of Defence (MOD) Service Portal — Design Blueprint

**Audience**: Pulse Fitness product + engineering team
**Parent platform**: Pulse Fitness Service Platform (Lite / Pro)
**Version**: 1.0 (Feb 2026)
**Author**: GymAxis Product & Systems
**Status**: Design Review — pending phased-build sign-off

---

## 0. Executive Framing

MOD sites are **not** a commercial customer — they are a structured, multi-tier estate with duty-of-care, accountability, and operational-readiness expectations far beyond civilian gyms. The portal must feel purpose-built for Army / Navy / RAF personnel, not a bolt-on to a commercial app.

Three non-negotiable outcomes:

1. **Perfect data capture every time** — no fault is ever logged with "it's broken, fix it" as the only description.
2. **Named accountability on every ticket** — every fault has a real human contactable by phone and email before the engineer leaves base.
3. **Service transparency** — MOD personnel never hit a black box. Status, assigned engineer, ETA and completion notes are always visible.

Differentiation against competitors (Technogym Connect, Matrix MyFit, generic CAFM tools): they all target a commercial estate. None has purpose-built MOD workflows, generic-site logins with named contact capture, or AI-guided triage that understands safety-critical flags. This is our wedge.

---

## 1. Full UX Flow (happy-path, site-user)

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│  Branded MOD   │ →  │ Home dashboard │ →  │ Log fault btn  │
│  login page    │    │ (site context) │    │ (big primary)  │
└────────────────┘    └────────────────┘    └────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Select equipment                                     │
│   • Recent machines (3-tap)                                  │
│   • Search by name                                           │
│   • QR scan (phase 2)                                        │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: Fault type (6 big tiles)                             │
│   Not working · Noise · Electrical · Damage · Safety · Other │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: Guided questions (conditional per type)              │
│   • What's happening? (free text, 40-char min)               │
│   • When did it start? (today / yesterday / this week / >1w) │
│   • Is it usable?  [Yes / Limited / No]                      │
│   • Is it safe to leave in service? [Yes / No — isolate]     │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: Photo / video (strongly encouraged, not forced)      │
│   • Camera capture or gallery                                │
│   • Up to 4 images, 2 videos                                 │
│   • WebP compression, <1MB each                              │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: Confirm contact (CRITICAL — no skip)                 │
│   [Dropdown: "Who is reporting this?"]                       │
│   • Pick existing staff → name / email / phone auto-fill     │
│   • [+ Add new contact inline]                               │
│   Copy: "This ensures our engineer can contact you and       │
│          resolve the issue faster."                          │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: AI pre-triage preview (differentiator)               │
│   "This looks like a belt-alignment issue. Usable with       │
│    caution. Estimated priority: MEDIUM.                      │
│    Engineer will contact Lt. Cpl. Jones within 2 hours."     │
│    [ Edit ] [ Submit ]                                       │
└──────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ CONFIRMATION                                                 │
│   Ticket #MOD-2026-01421                                     │
│   • Email sent to reporter                                   │
│   • Email sent to Pulse service desk                         │
│   • Appears in "Your open faults" on home dashboard          │
└──────────────────────────────────────────────────────────────┘
```

**Mobile-first principle**: each step is 1 screen, thumb-reachable primary CTA at the bottom, back gesture preserves step state. No multi-column forms on mobile.

---

## 2. Login Experience Design

### 2.1 Principles

- **Generic site credentials** — one login per site (e.g. `raf.brizenorton.gym@mod.pulsefitness.com` / `BrizeNorton2026!`). No per-user passwords for LITE tier.
- **Named accountability via staff picker**, not authentication. Shifted PTI staff may be hundreds across a base; authenticating each is unrealistic and creates forgotten-password chaos.
- **Dual-tier auth**: Master Pulse operators and PRO-tier MOD oversight personnel get individually-named accounts with MFA; site-level LITE users share site credentials.

### 2.2 Visual Design

Branded login page at `/mod` (distinct from `/pulse`):

- Dark slate background (`#0F1419`) with the MOD crest watermark at 6% opacity top-right
- Pulse Fitness logo top-left
- Hero copy: **"Ministry of Defence Service Portal"** + subtitle _"Log faults quickly and accurately to ensure rapid response."_
- Single card: site email + site password, optional "Switch site" quick-picker for shared terminals
- Footer strip showing Army / Navy / RAF crest trio in monochrome, reinforcing multi-branch scope
- Accessibility: WCAG AA, 4.5:1 text contrast, 44px tap targets, keyboard-only tabbing

### 2.3 Session Rules

- Site sessions last **8 hours** (single shift) then auto-expire
- PRO / Master Admin sessions last **30 minutes idle**, 2FA every 7 days
- Every login logged to `audit_log` with IP, user-agent, site_id

---

## 3. Fault-Logging Journey (detailed)

### 3.1 Step-by-step data capture

| Step | Field | Required | Validation |
|------|-------|----------|------------|
| 1 | `equipment_id` | ✓ | Must belong to the logged-in site |
| 2 | `fault_type` | ✓ | One of: `not_working`, `noise`, `electrical`, `damage`, `safety`, `other` |
| 3 | `description` | ✓ | ≥ 40 chars (prevents "it's broken") |
| 3 | `onset` | ✓ | `today` / `yesterday` / `this_week` / `older` |
| 3 | `usable` | ✓ | `yes` / `limited` / `no` |
| 3 | `safe_in_service` | ✓ | `yes` / `no` (no → triggers auto-isolation workflow) |
| 4 | `attachments[]` | optional but encouraged | ≤ 4 images + 2 videos, WebP ≤ 1MB each |
| 5 | `reporter_contact_id` OR inline `{name,email,phone}` | ✓ | Email format + E.164-ish phone check |
| 6 | `ai_triage_accepted` | auto | Captures whether the user edited AI priority |

### 3.2 Conditional branches

- `safety === 'yes'` (fault type) OR `safe_in_service === 'no'` → force **Priority: URGENT**, auto-email the on-call MOD Pulse engineer with a SMS fallback if ELEVENLABS_VOICE_ALERT is enabled.
- `usable === 'no'` + equipment is "safety-critical" (treadmill, rower) → **auto-isolate**: status flips to `out_of_service` and appears on an MOD-red-banner alert the next time any staff logs in.
- Multiple faults (> 2) on the same asset in 30 days → auto-tag `repeat_offender: true` and show a banner during step 1 ("This machine has had 3 faults this month — consider a depth inspection request").

### 3.3 Edge cases

- **Offline capture**: service worker queues POST body + attachments to IndexedDB, syncs on re-connect. Visible sync badge.
- **Duplicate detection**: if an open ticket exists on the same `equipment_id` with matching `fault_type`, prompt "Add to existing ticket #MOD-2026-01419?" before creating new.
- **Silent drop-off**: every step records `events.mod_fault_step_exit` so we can measure abandonment and fix friction.

---

## 4. Staff Management System

### 4.1 Data model

```
mod_site_staff {
  id: uuid
  site_id: uuid  // indexed
  name: str (required)
  role: str | null  (examples: "PTI", "Duty Manager", "Gym Corporal")
  email: str (required, validated)
  phone: str (required, E.164)
  is_active: bool
  created_at: iso
  updated_at: iso
  last_reported_at: iso | null   // for staff sort / MRU
  fault_count: int               // denormalised counter
}
```

Unique-per-site constraint on `(site_id, lower(email))`.

### 4.2 UX flows

- **Add**: 30-second modal (Name → Role → Email → Phone → Save). Validates email uniqueness per site. Inline add from step 5 of the fault wizard too.
- **Edit**: tap row → prefilled modal → save. Previous values audit-logged.
- **Remove**: soft-delete (`is_active=false`). Retain references from existing tickets; staff picker hides inactive.

### 4.3 "Who is reporting this?" picker (shown at fault step 5)

- Sorted by **Most Recently Used** (from `last_reported_at`)
- Top 5 shown as quick-tap chips; full list below
- "+ New contact" inline — adds to staff DB and selects in one action
- Search by name / role / email (client-side)

Result: after 2 weeks of use a site has a clean populated database, fault logging time drops from 90 seconds → 20 seconds, and every fault is contactable.

---

## 5. Role / Permission Model

```
MOD Organisation  (root tenant, is_mod: true)
├── Branch          (Army / Navy / RAF)
│   └── Site        (RAF Brize Norton, HMS Raleigh, Catterick Garrison…)
│       └── Equipment
```

### 5.1 Roles

| Role                     | Scope                       | Typical user                        | Auth            |
|--------------------------|-----------------------------|-------------------------------------|-----------------|
| `mod_site_user` (LITE)   | Single site                 | PTI / Duty Manager / Cpl            | Shared site creds |
| `mod_branch_pro` (PRO)   | All sites within a branch   | RAF HQ Facilities Manager           | Named + MFA     |
| `mod_organisation_pro` (PRO) | Entire MOD estate        | MOD Head of PT Estates              | Named + MFA     |
| `pulse_service_engineer` | Assigned sites only         | Pulse Fitness engineer              | Named + MFA     |
| `pulse_master_admin`     | Platform-wide + MOD sub-tree | Pulse ops                           | Existing        |

### 5.2 Capability matrix

| Capability                       | site-user | branch-pro | org-pro | engineer | master  |
|----------------------------------|:--------:|:----------:|:-------:|:--------:|:-------:|
| Log fault                        | ✓        | ✓          | ✓       | ✓        | ✓       |
| View own site equipment          | ✓        | ✓          | ✓       | ✓        | ✓       |
| View branch-level equipment      |          | ✓          | ✓       |          | ✓       |
| View org-wide equipment          |          |            | ✓       |          | ✓       |
| Add/edit/remove site staff       | ✓ (own)  | ✓ (branch) | ✓ (org) |          | ✓       |
| Change ticket status / assign    |          |            |         | ✓ (own)  | ✓       |
| KPI & contract dashboards        |          | ✓          | ✓       |          | ✓       |
| Multi-site comparison / reporting|          | ✓          | ✓       |          | ✓       |
| Provision sites / branch admins  |          |            |         |          | ✓       |

### 5.3 Database enforcement

Every query scoped to `site_id` (or branch_id for PRO). Master middleware decorator `@require_mod_scope(level='site'|'branch'|'org')` enforces. Absence of scope → 403, logged to `audit_log`.

---

## 6. AI Integration Points

| Hook                    | Trigger                           | Model              | Output                                   |
|-------------------------|-----------------------------------|--------------------|------------------------------------------|
| **Fault triage**        | Fault wizard step 6 preview       | Claude Haiku 4.5   | priority, safety_flag, likely_cause, quick_fix_suggestion |
| **Quick-fix hint**      | While typing `description` (debounced) | Claude Haiku 4.5 | one-line hint: "Have you checked the belt tension?" |
| **Categorisation**      | Server-side on save               | GPT-4o-mini        | `tags: ['belt','alignment','treadmill']` for analytics |
| **Severity escalation** | Post-save, matches safety lexicon | Regex + LLM fallback | elevates to URGENT, emails on-call      |
| **Repeat-asset nudge**  | Daily cron                        | Deterministic      | "RAF Brize TM-18 has had 4 faults in 30 days — suggest deep service" |
| **Pre-visit pack**      | When engineer assigned            | Claude Haiku 4.5   | Summary + likely spares + safety note + previous faults on asset |

All LLM calls go through the **Emergent LLM key** for cost/governance. Every AI response logged to `ai_decisions` with the exact prompt + output for audit.

---

## 7. Multi-Site Hierarchy

### 7.1 Data model

```
mod_organisations                  (1 — MOD root)
└── mod_branches                   (3 — Army / Navy / RAF)
    └── mod_sites                  (N — individual bases)
        └── equipment              (existing)
            └── issues             (existing, mod_site_id FK)
```

### 7.2 PRO dashboard (branch-level example)

```
RAF Facilities — Branch Dashboard
╔══════════════════════════════════════════════════════════╗
║ 34 sites · 1,284 machines · 97.4% availability           ║
╚══════════════════════════════════════════════════════════╝

Top offenders (by downtime, last 30d)
1. RAF Brize Norton .......... 42h  ████████████████████░░░
2. RAF Marham ................ 31h  ██████████████░░░░░░░░░
3. RAF Lossiemouth ........... 22h  ██████████░░░░░░░░░░░░░
4. RAF Waddington ............ 18h  ████████░░░░░░░░░░░░░░░

Open urgent faults across branch:  7
Engineers currently on-site:       3
Response SLA breach (last 7d):     1
```

### 7.3 Org-level dashboard

Same template, aggregated Army + Navy + RAF. Branch comparison card ("RAF 97.4% · Army 94.1% · Navy 96.8%"), open-urgent count, SLA-breach count, average response time per branch, rolling-year downtime vs target.

---

## 8. UI Wireframes (ASCII sketches)

### 8.1 Site home dashboard (mobile, 375px)

```
╭──────────────────────────────╮
│ 🇬🇧  RAF Brize Norton         │   ← site header, MOD crest left
│ PULSE FITNESS SERVICE PORTAL │
├──────────────────────────────┤
│                              │
│   ┌────────────────────┐     │
│   │ 🚨  LOG A FAULT    │     │  ← primary CTA, thumb-reach
│   └────────────────────┘     │
│                              │
│   Your open faults (3)       │
│   ┌──────────────────────┐   │
│   │ TM-18 · Belt issue   │   │
│   │ ETA: Today 14:00     │   │
│   │ Engineer: J. Patel   │   │
│   └──────────────────────┘   │
│   ┌──────────────────────┐   │
│   │ ST-04 · Cable stack  │   │
│   │ Status: Diagnosing   │   │
│   └──────────────────────┘   │
│                              │
│   Site health                │
│   Working: 92 / 96 (96%)     │
│   Overdue checks: 2          │
│   Repeat offenders: 1        │
│                              │
│  [Staff]  [Equipment] [Help] │
╰──────────────────────────────╯
```

### 8.2 Fault wizard — step 5 (contact)

```
╭──────────────────────────────╮
│ ← Step 5 of 6                │
│ Who is reporting this?       │
│                              │
│ This ensures our engineer    │
│ can contact you and resolve  │
│ the issue faster.            │
│                              │
│ ┌─────────────────────────┐  │
│ │ 🔍 Search or add new    │  │
│ └─────────────────────────┘  │
│                              │
│ Recent                       │
│ [ Sgt J Hughes · PTI     ✓]  │  ← selected
│ [ Cpl L Baker · Duty Mgr  ]  │
│ [ Lt R Owen · Ops         ]  │
│                              │
│ + Add new contact            │
│                              │
│ Auto-filled:                 │
│   Name  Sgt J Hughes         │
│   Email j.hughes@mod.gov.uk  │
│   Phone +44 7700 900111      │
│                              │
│ ┌──────────────────────────┐ │
│ │      CONTINUE →          │ │
│ └──────────────────────────┘ │
╰──────────────────────────────╯
```

### 8.3 PRO branch comparison (desktop)

```
┌───────────────────────────────────────────────────────────────┐
│ MOD ESTATES — RAF BRANCH OVERVIEW            last 30 days ▼   │
├───────────────────────────────────────────────────────────────┤
│  Sites: 34      Machines: 1,284     Availability: 97.4%      │
│  Open urgent: 7          Avg response: 3.8h                   │
├──────────────────┬────────────────────────────────────────────┤
│ Site list        │  ┌──────────────────────────────────────┐  │
│  • Brize Norton  │  │  Downtime trend (last 90d)          │  │
│  • Marham        │  │  ╱╲    ╱╲    ╱╲___╱╲      ___      │  │
│  • Lossiemouth   │  │ ╱  ╲  ╱  ╲  ╱       ╲__╱     ╲__   │  │
│  • Waddington    │  └──────────────────────────────────────┘  │
│  • Coningsby     │  Top offenders                             │
│  • Akrotiri      │  1. Brize Norton · TM-18 · 42h             │
│  • …28 more      │  2. Marham · ST-04 · 31h                   │
│                  │  3. Lossiemouth · RB-11 · 22h              │
└──────────────────┴────────────────────────────────────────────┘
```

### 8.4 Engineer Pre-Visit Pack (email + portal)

```
╔══════════════════════════════════════════════╗
║  Pulse Fitness · Engineer Pre-Visit Pack     ║
║  Ticket #MOD-2026-01421                      ║
╠══════════════════════════════════════════════╣
║  Site: RAF Brize Norton Gym                  ║
║  Site contact: Sgt J Hughes · +44 7700 900111║
║                                              ║
║  Asset: Treadmill TM-18 (Life Fitness 95T)   ║
║  Serial: LF-95T-2019-00842                   ║
║  Warranty: expires 14 Mar 2027               ║
║  Location: Cardio Hall, Row B, Bay 4         ║
║                                              ║
║  Fault: Belt-alignment / noise               ║
║  Priority: MEDIUM                            ║
║  AI diagnosis: Likely belt tension / align.  ║
║  Quick fix (try first):                      ║
║   • Check belt lateral play > 6mm            ║
║   • Torque tension bolts to 12Nm             ║
║                                              ║
║  Previous faults on this asset (12m):        ║
║   • 14 Jan 2026 · Display blank · resolved  ║
║   • 03 Dec 2025 · Noise  · resolved         ║
║                                              ║
║  Spares likely needed:                       ║
║   • LF-95T-BELT-STD (in van — 2 in stock)   ║
║   • LF-95T-MOTOR-BRUSH (depot)              ║
║                                              ║
║  Access notes: sign in at main gate, escort ║
║    required past barrier. PTI office to rear.║
╚══════════════════════════════════════════════╝
```

---

## 9. Data Capture Structure (canonical models)

### 9.1 Core collections (new)

```python
mod_organisations {
  id, name, created_at, feature_flags: {
    ai_triage: true, pre_visit_pack: true, sms_alerts: false
  }
}

mod_branches {
  id, organisation_id, name (Army|Navy|RAF), created_at
}

mod_sites {
  id, branch_id, name,
  code,                      # e.g. "RAF-BN"
  address, postcode, lat, lng,
  access_notes: str,
  escort_required: bool,
  primary_poc_staff_id: uuid,
  oncall_phone: str | null,
  created_at, updated_at
}

mod_site_staff { ... see section 4 ... }

mod_site_credentials {
  id, site_id, email, password_hash (bcrypt 12),
  last_rotated_at, rotation_due_at
}

mod_audit_log {
  id, site_id, user_id (nullable for site-creds),
  action (login|logout|fault.create|staff.add|staff.remove|status.change|...),
  target_id, before, after, ip, user_agent, created_at
}
```

### 9.2 Extended collections

```python
# Existing `issues` gains these fields when site is MOD:
issues {
  ...
  mod_site_id: uuid | null,
  mod_site_staff_id: uuid | null,   # reporter — always populated
  mod_ticket_ref: "MOD-YYYY-NNNNN",  # friendly ref, deterministic
  onset: str,
  usable: str,
  safe_in_service: str,
  ai_triage: {
    priority, safety_flag, likely_cause, quick_fix, model, latency_ms,
    accepted: bool, edited: bool
  },
  escalation_reason: str | null,
  pre_visit_pack_sent_at: iso | null,
}
```

### 9.3 Indexes

- `mod_sites(branch_id, name)`
- `mod_site_staff(site_id, lower(email)) UNIQUE`
- `mod_site_staff(site_id, last_reported_at DESC)` — staff picker MRU
- `issues(mod_site_id, status, created_at DESC)` — site open-faults feed
- `issues(mod_site_id, equipment_id, created_at DESC)` — duplicate detection + repeat-offender
- `mod_audit_log(site_id, created_at DESC)`

### 9.4 Fault-priority decision matrix (server-side, deterministic)

| `fault_type` | `safe_in_service` | `usable` | Result priority |
|--------------|-------------------|----------|-----------------|
| `safety` or `electrical` | any | any | **URGENT** |
| any          | `no`  | any     | **URGENT**      |
| any          | `yes` | `no`    | HIGH            |
| any          | `yes` | `limited`| MEDIUM        |
| any          | `yes` | `yes`   | LOW             |

AI may **upgrade** but never downgrade this deterministic baseline.

---

## 10. Security Model

### 10.1 Data isolation

- Every API handler accepts the request, resolves the session's `mod_scope` (site / branch / org / engineer / master), and **every read query receives an explicit `mod_site_id IN (...)` filter** — no ambient scoping.
- Cross-site access from a `mod_site_user` → HTTP 403 + `audit_log.entry` + rate-limit the source IP.

### 10.2 Authentication

| Tier              | Mechanism                                   |
|-------------------|---------------------------------------------|
| Site user (LITE)  | Shared site creds · bcrypt12 · 8-hour session · IP-limited to 5 failures / 15 min |
| Branch / org PRO  | Email + password + mandatory TOTP MFA (existing master-admin pattern) |
| Engineer          | Same PRO auth, scoped to assigned site list |
| Master admin      | Existing MFA flow |

### 10.3 Audit

Every single write produces an `mod_audit_log` row. Every login writes to the unified `audit_log`. Tamper-evident (existing fail-closed writer). Queryable by MOD PRO users within their scope. Exportable as CSV within 24h of request (matches existing GDPR export SLA).

### 10.4 Data protection

- PII retention 365 days post-last-login of a reporting contact, then email+phone auto-redacted to `hash:xxx`. Ticket record preserved for warranty / audit evidence.
- Site credentials rotate on a **180-day** cycle. Master admin gets a 14/7/1-day reminder chain. Forced rotation on 180.
- All traffic HSTS, TLS 1.2+, site-scoped CSP.
- Turnstile captcha on the MOD login form (already platform-wide).
- **Explicit MOD-grade controls** that are in-scope but require implementation: IP allow-list per site (optional), download of an activity digest every Monday to the site commander's email, mandatory 90-day fault data export for the Defence Digital audit stream.

### 10.5 Abuse & misuse protections

- Staff-add rate limit: 20 / hour / site.
- Fault-create rate limit: 30 / hour / site (stops accidental scripted spam; real sites will never hit this).
- Duplicate detection (§3.3) protects downstream engineer dispatch from bogus bulk tickets.
- Pulse master admin can **suspend** a site's write access from the admin console if misuse is detected, without revoking read access — preserves evidence.

---

## 11. Rollout — proposed phasing

Given the scope, I recommend 4 phases of ~1–2 days each. Pick your entry point.

### Phase 1 — Foundation (MVP, 2 days)
- `mod_organisations`, `mod_branches`, `mod_sites`, `mod_site_staff` models + CRUD
- Site-credential login page at `/mod` (new public route, Turnstile-protected)
- Site home dashboard (ASCII wireframe §8.1) with existing `issues` feed scoped to site
- Fault wizard steps 1–5 (equipment → fault type → guided questions → attachments → staff picker)
- Staff management CRUD modal with MRU sort
- Email on submission (re-uses existing Resend pipeline)
- Seed script for "RAF Brize Norton Gym" + 5 staff + 20 equipment for demo

### Phase 2 — AI & Engineer Ops (2 days)
- AI triage preview (step 6) via Claude Haiku 4.5 on Emergent key
- Deterministic priority matrix (§9.4) — server-side, cannot be gamed by the UI
- Escalation workflow (URGENT → on-call emailer)
- Engineer pre-visit pack (§8.4) generated on assignment, emailed to engineer + portal view
- Duplicate detection & repeat-offender banner

### Phase 3 — PRO & Multi-Site (1 day)
- `mod_branch_pro` + `mod_organisation_pro` roles + MFA
- Branch dashboard (§8.3) with top-offenders + downtime trend + SLA breach
- Org-level rollup across Army / Navy / RAF
- Per-scope CSV export for auditors

### Phase 4 — Polish & Proactive (1 day)
- Offline capture via service worker
- Proactive alerts (overdue check, repeat offender, maintenance overdue) driven by existing nightly scanners
- QR code scan from step 1 (re-uses existing `/equipment/{id}/qr-code`)
- Weekly digest email per site commander
- Pulse master admin MOD sub-console (list sites, rotate credentials, suspend, audit-log search)

---

## 12. Open questions — please confirm before we build

1. **Tenancy boundary**: is MOD a new `account_type='mod'` under Pulse Fitness (simplest, quickest), or a fully separate tenant with its own org-root (more defence-grade but more code)?
2. **Named vs shared login**: confirm shared site creds are acceptable under MOD InfoSec policy. If not, we switch LITE to named accounts with lightweight self-onboarding via site commander invite.
3. **IP allow-list per site** — nice-to-have or must-have before first rollout?
4. **Branch scope**: do we launch with all 3 branches (Army/Navy/RAF) seeded empty, or pilot on a single RAF site first?
5. **Pricing / commercial model**: is this a Pulse Pro customer on free Lite for life, or priced separately?
6. **Integration surface**: do we need to feed MOD's existing Defence Digital helpdesk (ServiceNow / similar) via webhook on ticket create?
7. **AI safety messaging**: we'll add "AI-suggested, not a substitute for engineer diagnosis" disclaimers throughout. Any specific legal wording you need us to use?

---

**Ready to build on your nod — tell me which phase(s) you want first and I'll confirm the 1–7 answers above before code lands.**
