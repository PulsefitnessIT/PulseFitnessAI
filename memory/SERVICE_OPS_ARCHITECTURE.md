> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> Post-iter-215dn shipping that touches Service Ops:
>
> **Engineer Diary mobile fix (iter 216h229)**
> The `grid-cols-7` week view in `EngineerDiary.js` now wraps in
> `overflow-x-auto` with `min-w-[700px]` so day cells stay a readable
> ~100px wide on phones instead of squashing to ~55px.
>
> **Equipment Hub — single-machine Add CTA (iter 216h231)**
> `EquipmentInfoTab.js` had only multi-machine AI Invoice Import.
> Added a direct `Add Equipment` button (wired to the existing
> `AddEquipmentDialog`) and switched the action row to `flex-wrap`
> so on phones the buttons cleanly wrap instead of overflowing.
> `data-testid="add-equipment-btn"` for testability.
>
> **First-fault activation event (iter 216h227)**
> `POST /api/issues` now fires `first_fault_logged` to the activation
> bus, with `payload={"issue_id": ...}`. Wraps in `try/except` so
> a failed emit never blocks issue intake. The first-fault milestone
> appears in `ActivationMilestonesCard` for operations-trial users
> and links them straight to the faults tab.
>
> **CRM ↔ Service Desk mirror** — escalations from `issues.py` mirror
> into `svc_cases` via `_mirror_issue_to_svc_case()` so engineers
> dispatched from the Service Desk see the same record their CSM is
> tracking in CRM. Same record appears in the cross-module
> `/api/crm/v2/companies/{id}/timeline`.
>
> **Mobile rails (iter 216h228)** — global `[data-fab-rail]`
> stacking applies to the Engineer hub's report/feedback FABs;
> `html, body { overflow-x: hidden }` below `lg:` prevents the long-
> table Engineer pages from leaking horizontal scroll.

---


# GymAxis Service Operations Platform — Architecture Spec
**Codename: SERVICE OPS** · Replaces Sicon Service · iter 215dn (Feb 2026)

> Not a ticketing system. A native field-service operations platform built for fitness equipment service desks and engineers in the field.

---

## 1. WHAT EXISTS TODAY (foundation we can leverage)

| Component | Status | Notes |
|---|---|---|
| `fault_codes.py` / `fault_templates.py` | ✅ Live | Fault categorisation matrix |
| `SiconServicePanel.js` | ✅ Live | UI shell for Sicon-style case display |
| `SupplierCasePage.js` | ✅ Live | External-facing supplier case page |
| `sicon.py` integration | ✅ Live | Two-way sync — keep until cutover |
| `service_desk.py` | ⚠️ Mis-named | SaaS-tenant admin (NOT field service). Will rename to `desk_admin.py` |
| `crm_contracts.py` | ✅ Live | Contract entity (cover types, SLAs) |
| Operations issues (`issues.py`) | ✅ Live | Asset-linked fault logs — base for cases |
| `assets.py` | ✅ Live | Equipment register |
| `staffing.py` | ✅ Live | Engineer roster |

**Conclusion**: ~40% of foundational data already exists. Service Ops bolts on top by introducing the **case lifecycle**, **engineer mobile**, **scheduler**, **parts/van stock**, and **AI layer**.

---

## 2. SYSTEM ARCHITECTURE

```
                         ┌────────────────────────────────────┐
                         │  GymAxis SERVICE OPS PLATFORM      │
                         │                                    │
  Intake (3 channels) ──►│  ① Intake & Logging                │
   • portal              │  ② Service Desk Dashboard          │
   • email               │  ③ Case Management Engine ◄────────┤  AI Assistant Layer
   • phone               │  ④ Engineer Mobile                 │  (cross-cutting)
                         │  ⑤ Scheduling & Allocation         │
                         │  ⑥ Parts & Inventory               │
                         │  ⑦ Quoting & Billing               │
                         │  ⑨ Customer Comms Hub              │
                         │  ⑩ Reporting & Audit               │
                         └─┬──────────────────────────────────┘
                           │
                ┌──────────┴──────────────────────────┐
                │       ⑪ Integration Layer            │
                ├─────────┬───────┬───────┬───────────┤
                │   CRM   │ Memb. │  Ops  │ Sage/Sicon│
                └─────────┴───────┴───────┴───────────┘
```

### Backend module layout
```
/app/backend/
  routes/svc/
    intake.py           # POST /api/svc/intake (portal + email-to-case + phone-logged)
    cases.py            # CRUD + timeline + state machine
    desk.py             # Dashboard queries (SLA, queue, map)
    engineer.py         # Mobile-tuned endpoints (jobs, time, signatures, photos)
    scheduler.py        # Drag-drop diary + auto-assign engine
    parts.py            # Catalogue + van stock + reorder
    quoting.py          # Quotes & chargeable workflow
    comms.py            # Outbound email/SMS + template rendering
    reports.py          # SLA, FTF rate, productivity
    ai.py               # AI hooks (intake assist, summarise, recommend)
    integrations/
      sicon_sync.py     # Bridge during cutover
      sage_invoice.py   # Outbound invoice to Sage
      crm_link.py       # Link cases to CRM contacts/companies
  models/svc/
    case.py             # Case, CaseEvent, CaseAttachment, CaseSignature
    engineer.py         # EngineerProfile, VanStock, Skill, Availability
    part.py             # Part, PartLocation, PartMovement, ReorderRule
    quote.py            # Quote, QuoteLine
    sla.py              # SLAPolicy, SLAClock (response/resolution)
  utils/svc/
    state_machine.py    # new → assigned → en_route → on_site → ... → closed
    sla_engine.py       # Pause/resume on waiting-for-customer / parts
    geo.py              # Distance, postcode lookups (UK)
    notifications.py    # Email/SMS dispatcher
```

### MongoDB collections (new)
| Collection | Purpose |
|---|---|
| `svc_cases` | Master case record (one doc per service event) |
| `svc_case_events` | Append-only timeline (status, note, attachment, comm) |
| `svc_engineers` | Engineer profiles, home address, vehicle, skills |
| `svc_engineer_availability` | Day-by-day availability + holidays |
| `svc_parts` | Parts catalogue (SKU, name, supplier, cost, lead time) |
| `svc_van_stock` | Per-engineer rolling van inventory |
| `svc_part_movements` | Audit log: van↔warehouse↔job↔customer |
| `svc_quotes` | Chargeable quotes |
| `svc_sla_policies` | SLA matrices by contract type / priority |
| `svc_sla_clocks` | Per-case SLA timers (response, resolve) |
| `svc_comm_templates` | Email/SMS templates with variables |
| `svc_reorder_rules` | Min/max levels per (part × location) |

---

## 3. CASE LIFECYCLE (state machine)

```
NEW
 ├─► TRIAGED ──► ASSIGNED ──► EN_ROUTE ──► ON_SITE
 │                  ▲              │           │
 │                  │              │           ├─► PAUSED_PARTS  (SLA pause)
 │                  │              │           ├─► PAUSED_CUSTOMER (SLA pause)
 │                  │              │           └─► REPAIRED ──► AWAITING_SIGN_OFF
 │                  │              │                                 │
 │                  └──────────────┘                                 ▼
 │  REASSIGNED                                                    CLOSED ──► INVOICED
 └─► REJECTED (duplicate / out-of-scope)
```

State transitions are **enforced server-side** via `utils/svc/state_machine.py` — every change writes a row to `svc_case_events` with actor + timestamp + delta. Audit trail is free.

---

## 4. INTAKE — multi-channel

| Channel | How it lands in the system |
|---|---|
| **Customer portal** (Pulse Fitness / GymAxis) | Existing supplier-case form posts to `POST /api/svc/intake/portal` — includes photo upload, asset selector, AI-suggested fault code |
| **Email** | Mailbox poller (`comms.py` cron) → AI parser extracts site + asset + fault → creates draft case in `triage` queue |
| **Phone** | Service desk operator uses guided intake form on `/svc/intake/new` — same backend endpoint as portal, just `source=phone` |
| **WhatsApp** (future) | Twilio webhook → AI parse → draft case |

**AI-assisted intake** layer:
- `POST /api/svc/ai/triage` — input: free-text + photo URLs + site_id → output: suggested `fault_code_id`, `priority`, `likely_parts: [SKU…]`, `missing_field_prompts`, `estimated_visit_minutes`
- Re-uses the existing Emergent LLM key. Claude Sonnet for natural-language; Gemini Vision (Nano Banana) for photo classification (e.g. "treadmill belt frayed" → maps to fault code `TM-BLT-WEAR`).

---

## 5. SERVICE DESK DASHBOARD

```
┌──────────────────────────────────────────────────────────────┐
│  KPI strip:  Open: 47  ·  SLA at risk: 6  ·  Unassigned: 12  │
│              First-time fix: 78%  ·  Avg resolve: 4.3h        │
├───────────┬──────────────────────────────────────────────────┤
│ FILTERS   │  Queue (default: SLA at risk first)              │
│ ─────     │  ┌────────────────────────────────────────────┐  │
│ □ Warranty│  │ #SVC-1042  PureGym Holborn  Treadmill #14  │  │
│ □ Contract│  │ Belt frayed · P1 · SLA 1h 12m left  🔴     │  │
│ □ Charge  │  │ Assigned: J. Lee · ETA 14:20               │  │
│           │  └────────────────────────────────────────────┘  │
│ Site:▼    │  ┌────────────────────────────────────────────┐  │
│ Engineer:▼│  │ #SVC-1043  Anytime Brixton  Bike #03       │  │
│ Status:▼  │  │ Display dead · P2 · SLA 4h 30m  🟡         │  │
│           │  │ Unassigned                                 │  │
│           │  └────────────────────────────────────────────┘  │
├───────────┴────────────────────────┬─────────────────────────┤
│  Live map                          │  Engineer panel          │
│  (engineer pins + open cases)      │  • J. Lee · en route    │
│                                    │  • S. Khan · idle       │
│                                    │  • M. Chen · on site    │
└────────────────────────────────────┴─────────────────────────┘
```

**Key views**: Queue · Map · Calendar · Parts shortage · SLA risk.

---

## 6. ENGINEER MOBILE (React PWA — installs to home screen)

Single React route `/svc/engineer` — mobile-first, offline-capable (reuses the existing `offlineQueue` infrastructure from iter 215cd).

**Day flow**:
1. **Today** — list of jobs with travel time + ETA. Tap a job to open detail.
2. **Job detail** — site map link, asset history, manuals, `Start travel` button.
3. **On site** — `Start work` (timer auto-runs), notes (voice-to-text via Whisper), photo capture.
4. **Parts used** — barcode scan (camera) or pick from van stock.
5. **Sign-off** — customer signs on-screen, fault + remedy summary auto-generated by AI from notes.
6. **Close** — pushes case to `AWAITING_INVOICE` if chargeable, else `CLOSED`.

Offline support: every mutation queues to IndexedDB and replays when online (same primitives as ops/maintenance bg sync).

---

## 7. SCHEDULING & ALLOCATION

### Manual: drag-and-drop diary
- 7-day grid · engineers as rows · 30-min slots
- Coloured cards per case (red = SLA risk · green = on track)
- Drag a card to a slot → posts `POST /api/svc/scheduler/assign` → recomputes ETA + sends customer SMS

### Auto-assign (AI)
`POST /api/svc/scheduler/auto-assign?case_id=X` — pure scoring:

```
score(engineer, case) =
   100
   - (drive_minutes_from_prev_job × 1.0)
   - (skill_mismatch × 50)              # required skill missing
   + (van_stock_match × 20)             # has the likely parts
   - (sla_breach_risk × 30)             # would risk other jobs' SLA
   - (overtime_minutes × 0.5)
```

Picks the highest-scoring engineer with capacity. Optional manager confirmation step before commit.

### Route optimisation
End-of-day batch: re-orders the next day's jobs per engineer using nearest-neighbour heuristic on postcode centroids (UK Royal Mail data). Saves ~15-30 min/day per engineer.

---

## 8. PARTS & INVENTORY

| Concept | Behaviour |
|---|---|
| **Catalogue** | Master list of SKUs with supplier, cost, lead time |
| **Locations** | Warehouse (1 per region) · Van (1 per engineer) · Site (consigned stock) |
| **Movements** | Every part shift writes a `svc_part_movements` row — full audit |
| **Reorder rules** | Min/max per part×location; nightly job emits PO suggestions |
| **Job allocation** | Engineer picks part from van → quantity decremented → audit row written |

Engineer view: "My van" with per-part counts, low-stock warnings, "request from warehouse" button.

---

## 9. QUOTING & BILLING

- Chargeable cases (no contract / out-of-scope work) auto-produce a draft quote when engineer flags the case as `chargeable`.
- Quote builder: drag-in parts + labour rates (from contract or default) → generate PDF → email to customer.
- On approval → case moves to `APPROVED_CHARGEABLE` and engineer is dispatched.
- On completion → `Invoice` button posts to Sage via `integrations/sage_invoice.py`.

---

## 10. AI ASSISTANT LAYER (cross-cutting)

| Trigger | AI does |
|---|---|
| Intake form (after fault description typed) | Suggest fault_code, priority, likely parts |
| Photo uploaded at intake | Vision model classifies; e.g. "burn mark on display PCB" → `ELEC-BRN` |
| Engineer completes work notes | Generate customer-facing fix summary |
| Manager opens case after 4h | Risk summary: "SLA breach in 47 min, 2 parallel jobs assigned to same engineer" |
| Auto-assign request | Score engineers using rule engine + Claude tie-break for soft factors |
| Weekly report request | Generate human-readable narrative from KPIs |

All AI calls funnel through a single `utils/svc/ai_client.py` so we can swap models without touching feature code. Uses Emergent LLM key.

---

## 11. CUSTOMER COMMUNICATION HUB

- Outbound email + SMS with templates (`svc_comm_templates`) — variables like `{customer.first_name}`, `{engineer.name}`, `{case.eta}`.
- Trigger points: case created, assigned, engineer en route, on site, completed, awaiting sign-off.
- Inbound replies match by case ID footer (`Re: #SVC-1042`) → appended to timeline.
- All messages logged to `svc_case_events` with channel + delivery status (Twilio webhooks for SMS, Resend webhooks for email).
- Customer self-serve link: `https://mod-only-deploy.preview.emergentagent.com/svc/track/{token}` shows status, ETA, photos, lets them reply.

---

## 12. REPORTING & AUDIT

Cards/dashboards:
- **SLA performance** — % met / breached, by site, contract, engineer
- **First-time-fix rate** — % closed without parts callback
- **Engineer productivity** — jobs/day, billable %, drive ratio
- **Downtime** — asset uptime % (cases × duration / asset hours)
- **Parts usage** — top 20 SKUs, lead-time trend
- **Contract performance** — cost vs. SLA fee, profitability per contract

Audit log: every state transition + edit + comm + login is appended to `svc_audit_log` (separate from `svc_case_events` so the latter stays clean).

---

## 13. INTEGRATION MAPPING

| Source | Field flow |
|---|---|
| **CRM** | `crm2_contacts.id` → `svc_cases.contact_id` (customer master). Case creation pings CRM activity log. |
| **Memberships** | `members.usage_at_site` enriches case context ("286 visits today — high priority"). |
| **Operations** | `assets.id` → `svc_cases.asset_id`. Closing a case appends to asset history. |
| **Sage / Sicon** | During cutover: bidirectional sync. Post-cutover: outbound invoice only. |
| **Reporting engine** | `/api/svc/reports/*` consumed by existing `/reports` dashboards. |

---

## 14. PHASED ROLLOUT (recommended)

| Phase | Scope | Estimated effort | Why first |
|---|---|---|---|
| **Phase 1 — Foundation** | New `svc_*` collections, case state machine, intake form (portal + phone), service desk dashboard (queue + filters), case detail with timeline | 2-3 sessions | Replaces the most painful Sicon flows immediately |
| **Phase 2 — Engineer mobile** | PWA mobile app with offline, time tracking, photos, signatures | 2 sessions | Unlocks engineer productivity |
| **Phase 3 — Scheduling** | Drag-drop diary, manual + AI auto-assign, route optimisation | 2 sessions | High operator-time saving |
| **Phase 4 — Parts** | Catalogue, van stock, movements, reorder rules | 1-2 sessions | Improves first-time-fix rate |
| **Phase 5 — AI assistant** | Intake assist, photo vision, summarisation, risk surfacing | 1-2 sessions | Layered on now-stable foundation |
| **Phase 6 — Quoting + comms hub** | Quotes, Sage invoice, email/SMS templates, customer self-serve | 1-2 sessions | Closes the chargeable loop |
| **Phase 7 — Reports + audit** | Dashboards, full audit trail UI | 1 session | Builds on Phase 1-6 data |
| **Phase 8 — Sicon cutover** | Migration script + dual-run + retire `sicon.py` paths | 1 session | Final removal of dependency |

**Total**: ~12-15 focused build sessions. Each phase ships with tests + a screenshot demo + zero regression on existing flows.

---

## 15. NON-FUNCTIONAL REQUIREMENTS

- **Performance**: Service desk must handle 500 open cases without lag. All list endpoints paginated + indexed on `(organization_id, status, sla_breach_at)`.
- **Mobile-first**: Engineer app passes Lighthouse mobile ≥ 90 + offline scenario test.
- **Auditability**: Every mutation writes to `svc_case_events` AND `svc_audit_log` — two read paths so feature UI stays clean.
- **Security**: Engineer mobile uses scoped tokens that can ONLY read/write own jobs. Service desk uses ops-portal role gates.
- **i18n**: All customer-facing strings via i18n keys (`svc.*` namespace) — already follows existing pattern.

---

## 16. KEY DIFFERENTIATORS vs Freshworks / Zendesk / Intercom

These are help-desk tools. We are NOT building a help desk. Differentiators:

1. **Asset-aware** — every case is bound to a piece of equipment with full history; help-desks treat assets as freeform tags.
2. **Field-first** — the engineer experience is the primary UX, not a bolt-on app.
3. **Geographic intelligence** — drive time and route optimisation are core, not plugins.
4. **Native parts** — van stock + first-time-fix optimisation are baked in.
5. **Contract-aware billing** — chargeable vs. warranty vs. PPM is a first-class case attribute, not a custom field.
6. **Built on the GymAxis stack** — single login, single audit trail, single contact master with CRM/Marketing/Memberships.
7. **AI as a co-pilot, not a chatbot** — assists every step, never asked "did this resolve your issue?"

---

**Author**: GymAxis Engineering · iter 215dn · Feb 2026
**Status**: Architecture — ready for Phase 1 build approval
