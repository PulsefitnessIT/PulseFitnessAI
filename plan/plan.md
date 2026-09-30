# Pulse Fitness — MOD / BFPO Engineer Portal

A mobile-first service portal that lets Pulse Fitness engineers at MOD/BFPO sites around the world receive jobs, carry out repairs and planned servicing, and report back — while Pulse MOD staff in the UK watch the whole global operation from one live dashboard.
It is built as a new role-specific experience on top of the platform's existing engineer app and shared service-case engine, so a fault reported through the MOD service portal becomes the *same* job the engineer works and the *same* record staff track — never a duplicate copy.

## Who it's for
- **BFPO Engineers** (overseas, sometimes limited English, poor connectivity) — see only their assigned sites and jobs, do the work, report back.
- **BFPO Lead Engineers** — everything an engineer can do, plus visibility of jobs across their territory.
- **Pulse Fitness MOD Service Staff / Managers (UK)** — global operational oversight: what needs attention, what's overdue, what's waiting for parts, what engineers have completed.

## Core features and experience

**Engineer side (mobile-first, extremely simple):**
- A clean home screen answering "what needs my attention?" — cards for Open, Urgent, Waiting for Parts, and (later) Services Due, plus a simple "My Jobs" list.
- Simple job list with plain-English filters (All Open / New / In Progress / Waiting for Parts / Return Visit / Completed).
- A job detail screen with the reported fault front-and-centre, the equipment, and the site information — with a single primary button that changes with the job's state (Accept Job → Start Job → Continue → Update).
- A **guided step-by-step workflow**: I'm on site → is it safe? → diagnosis → was it repaired? If not repaired, plain-English reasons (Parts Needed, Return Visit, Unable to Access, Equipment Unsafe, etc.) each open a short, tap-friendly follow-up.
- **Parts Needed** flow that never forces an engineer to know a Pulse part number — pick from the equipment's parts, describe it, or photograph it; the job moves to Waiting for Parts and stays open.
- **Report another fault** during a visit — creates a proper linked case (with a warning if that equipment already has an open job), not a buried note.
- **Job completion** capturing work done, parts used, photos, and a safe/working confirmation; then an on-screen **signature** (with a "signature unavailable + reason" option) and an automatically generated, Pulse-branded **electronic job sheet** — no retyping.
- My Sites and an Equipment register (search by serial/model) with per-asset history.
- Job history (read-only once completed).
- Structured **operational updates** (Job completed, Parts required, Unable to access, Equipment unsafe, etc.) that surface to MOD staff — instead of loose WhatsApp/email.
- **Connectivity safety**: draft answers and photos autosave, uploads retry, and a clear Saved / Syncing / Synced / Needs Internet status. Engineers never see a technical error — only "Your work is saved, we'll sync when your connection returns." Repeated submissions never create duplicate jobs, photos or parts requests.

**Pulse MOD staff side (desktop-rich, actionable):**
- A **global BFPO dashboard**: KPI cards for Open, Urgent/Safety-Critical, Waiting for Parts, Overdue, and Sites Requiring Attention — every card clicks through to the underlying list (no dead numbers).
- A **global site view** organised by Country/Territory → Site, each with a simple health indicator (Normal / Attention Required / Critical) driven by explicit rules (overdue urgent job, multiple machines down, unresolved safety issue, access problem).
- A **live jobs view** with filters (territory, site, engineer, status, priority, age, safety-critical, overdue), opening the *same* case the engineer sees, with a full **activity timeline** (allocated → acknowledged → arrived → parts required → photos → status change → completed).
- **Job allocation / reallocation** to BFPO engineers, including a **handover** view so the next engineer sees the full history.
- **Temporary visiting-engineer access**: grant a UK engineer access to a site for a date range; when it expires they stop receiving new local jobs but keep permitted historical visibility.

**Cross-cutting:**
- Roles and permissions enforced on the server — an engineer can never reach another territory's site or job by changing a URL.
- Sensitive site information (access instructions, contacts, security notes) is permission-controlled.
- Timestamps stored consistently and shown in the site's local time, not UK time.
- The UI is structured for future translation (Spanish, Greek, German, Arabic, Malay, Swahili) without a rebuild.

## User flow
1. A MOD user reports a fault through the MOD service portal → it becomes a service case in the shared engine, visible to Pulse MOD staff.
2. Staff triage and allocate it to a BFPO engineer.
3. The engineer sees it on their home screen, opens it, and sees the equipment + the reported fault.
4. They tap **I'm on site**, confirm safety, record a diagnosis.
5. If parts are needed → they log the part (photo/description if no number) → job becomes **Waiting for Parts**, MOD staff see it immediately, the job stays open, and the visit is recorded on the asset history.
6. On the return visit they record the part fitted, confirm the machine is safe and working, capture sign-off, and complete the job.
7. A branded job sheet is generated automatically; equipment history, the MOD dashboard, and the shared case all update. The job moves to the engineer's history.

## UI/UX feel
- Engineer screens: big touch targets, one obvious primary action, icons **with** text (never colour alone), short plain English, minimal navigation (Home / Jobs / Sites / History / More), one-handed on a phone. Complex backend, effortless front end.
- Staff screens: professional, operational, information-dense but clear — KPI cards, filterable tables, attention panels; every stat drills into its list.
- Visually consistent with the existing Pulse Fitness service design (dark operational headers, cyan accent, card layouts), so it feels like one product, not a bolt-on.
- Every screen has proper loading / empty / error / offline / no-permission states with human-readable copy.

## Implementation phases

**Phase 1 — MVP (built now):**
- BFPO portal shell + navigation reusing the existing engineer app framework and shared service engine.
- Territory/site-based engineer scoping; BFPO Engineer and Lead Engineer roles; temporary visiting-engineer access.
- MOD faults flow into the shared case engine and become allocatable BFPO jobs (no duplicate job store).
- Engineer dashboard, job list, job detail, and the full guided workflow: on-site → safety → diagnosis → repair / parts / unable-to-fix / additional fault → completion.
- On-screen signature + auto-generated branded job sheet.
- My Sites + equipment register (search by serial/model) with per-asset history; read-only job history.
- Structured operational updates + activity timeline.
- Pulse MOD global dashboard with drill-down, global site view with rule-based health, live jobs view, allocation/reallocation, handover.
- Connectivity safety at the agreed level (autosave drafts, retry uploads, visible sync status, idempotent submissions) — not a full installable/offline PWA.
- Safety-critical workflow and duplicate-fault protection; server-side permission enforcement; timezone-correct display; strings structured for future localisation.

**Phase 2 — Planned servicing & reporting:**
- Configurable PPM inspection checklists per equipment category, equipment-by-equipment inspection with progress ("39 of 40 checked"), "issue found → create linked fault", and generated service certificates.
- Operational reports and management summaries with filters and PDF/Excel export.
- Notification preferences and richer digests.

**Phase 3 — Resilience, scanning & AI-readiness:**
- Full offline-first / installable PWA behaviour.
- QR/barcode equipment scanning.
- AI assists (suggested diagnosis, similar historical faults, service summaries, translation) — assistive only, never making safety-critical decisions.
- Deeper Sicon/Sage synchronisation of cases, sites, equipment and resources through the shared abstraction layer.

## Assumptions
- MOD faults originate in `modservice.pulsefitness.com`, which shares this deployment's database; the MVP links these through the shared service-case engine rather than building a new ingestion API. If any faults currently live only in a customer-facing fault log, they will be surfaced/allocated into the shared engineer case store so engineers work them directly.
- The existing engineer PWA (`/svc/engineer/*`) and its workflow, photo handling, signatures, drafts and offline-outbox are reused and wrapped in a BFPO-specific shell — not rebuilt. The BFPO experience is a scoped, simplified skin over the same engine.
- "Territory" reuses the platform's existing territory concept; sites reuse the existing MOD site records (with country/territory grouping). No duplicate Site/Asset/Engineer/Job entities are created.
- Realistic BFPO demo data (a few territories such as Gibraltar, Falklands, Cyprus, Kenya, with sites, equipment and sample faults) will be seeded so the MVP is demonstrable end-to-end without waiting on live external systems.
- Sicon remains READ-ONLY (`SICON_ALLOW_WRITES=false`); nothing in this build writes to Sicon.
- Job sheets are generated as a permanent record/PDF from workflow data; signature is captured on-screen but never mandatory where a site prohibits it.
- Lead Engineer permissions are configurable; the default is territory-wide read plus reallocation within their territory.
- Engineer-facing text defaults to plain English for the MVP; the localisation framework is prepared but additional languages are a later phase.
- The earlier "Case-Store Decision" is settled: imported/MOD cases are worked by engineers in the shared Service Desk case store (`svc_cases`), with idempotent linkage to their source.
