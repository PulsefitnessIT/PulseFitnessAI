> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> The single-source-of-truth model below remains the canonical
> design. Post-h225 additions worth surfacing in any future revision
> of this document:
>
> **Activation event bus (iter 216h216 + h227)**
> A new collection `activation_events` mediates between modules so
> CRM/Marketing/Operations/Memberships can each fire a milestone
> independently while the funnel renders a unified "first wins"
> timeline filtered to the operator's `primary_module`. 16 event
> types currently, each tagged with one of `always` / `operations` /
> `memberships` / `crm` / `marketing` so the rendering layer can
> show only what's relevant.
>
> ```
> CRM lead create ─┐
> CRM deal create ─┼─→ activation_events  ─→  /api/activation/me ─→ ActivationMilestonesCard.js
> CRM quote send  ─┘
> Marketing audience create ─┐
> Marketing brand-discovery  ─┼─→ activation_events
> Marketing campaign send    ─┘
> Operations equipment create ─┐
> Operations fault log         ─┴─→ activation_events
> ```
>
> Hooks at: `crm_core.py`, `crm_cpq.py`, `marketing/audiences.py`,
> `marketing/campaigns.py`, `marketing/brand_discovery.py`,
> `equipment.py`, `issues.py`. All wrapped in `try/except` so a
> failed emit never blocks the underlying write.
>
> **CRM ↔ Service Desk bridge** — when an Operations fault is
> escalated to engineer, `issues.py` mirrors it to `svc_cases`
> via `_mirror_issue_to_svc_case(...)`; same record is then
> visible in the CRM company timeline.
>
> **`primary_module` capture** — passed through from the marketing
> ModulePage CTAs to `/api/auth/register`, persisted on the org
> doc, and consumed by both `/account/onboarding` (Setup Checklist
> filter) and `/activation/me` (First Wins filter).

---


# GymAxis AI — Enterprise Integration Architecture
## Single Source of Truth for Sales, Service, and Finance

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    GymAxis AI Platform                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │   CRM    │  │ Service  │  │    AI    │  │ Master  │ │
│  │(Sales/   │  │ Portal   │  │ Engine   │  │ Admin   │ │
│  │Pipeline) │  │(Customer)│  │(Tenders) │  │(Govern.)│ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │              │              │      │
│  ┌────┴──────────────┴──────────────┴──────────────┴───┐ │
│  │              INTEGRATION HUB (Event Bus)             │ │
│  │  Events · Routing · Retry · Logging · Monitoring    │ │
│  └────┬──────────────┬──────────────┬──────────────┬───┘ │
│       │              │              │              │      │
│  ┌────┴─────┐  ┌─────┴────┐  ┌─────┴────┐  ┌─────┴───┐ │
│  │ Sage 200 │  │  Sicon   │  │  Orbit 4 │  │ Resend  │ │
│  │ (Finance)│  │ (Service)│  │  (Faults) │  │ (Email) │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Source of Truth Rules

| Entity | Owner | Source of Truth | Sync Direction |
|--------|-------|----------------|----------------|
| Company | CRM | CRM | CRM → Sage (on deal won) |
| Site | Service Portal | Service Portal | Service → CRM (on case) |
| Contact | CRM | CRM | CRM → Sage (manual) |
| Opportunity | CRM | CRM | Internal only |
| Quote | CRM | CRM | Internal only |
| Order | Shared | CRM creates, Sage fulfils | CRM → Sage |
| Contract | Shared | CRM commercial, Service operational | Bi-directional |
| Asset | Service Portal | Service Portal | Service → CRM |
| Service Case | Service Portal | Service Portal | Service → CRM |
| Engineer Visit | Service Portal | Service Portal | Service → CRM (read) |
| Invoice | Sage 200 | Sage 200 | Sage → CRM |
| Payment | Sage 200 | Sage 200 | Sage → CRM |
| Activity | CRM | CRM | Internal only |

**Conflict Resolution:**
- Financial data: Sage ALWAYS wins
- Commercial data (names, contacts): CRM wins
- Service data (status, notes): Service Portal wins
- Asset specs: Service Portal wins; commercial terms: CRM wins

---

## 3. Integration Event Flows

### Flow 1: Deal → Invoice → Payment
```
CRM: Deal closed won
  → Integration Hub: deal_closed_won
    → Create Sales Order (crm2_orders)
    → When Sage connected: Push to Sage 200
      → Sage creates Invoice
        → Webhook: invoice_created → CRM updates
          → Payment received → CRM activity logged
```

### Flow 2: Service Case → Engineer → Replacement Sale
```
Service Portal: Customer logs issue
  → Integration Hub: service_issue_created
    → CRM: Service Case created + Activity logged
      → Engineer dispatched → Visit logged
        → Engineer flags BER
          → Integration Hub: engineer_ber_flagged
            → CRM: Auto-create Opportunity (stage: Lead)
              → Sales team follows up
```

### Flow 3: Tender → Opportunity → Quote → Order
```
CRM: AI Tender Engine parses tender document
  → Creates Opportunity (linked to Company/Contact)
    → AI generates response + strategy
      → Quote created (with versioning)
        → Quote accepted → Order created
          → Integration Hub: deal_closed_won
```

---

## 4. API Architecture

### CRM API (`/api/crm/v2/*`)
- Companies, Contacts, Opportunities, Quotes, Activities
- Service Cases, Workflows, Tenders
- Auth: JWT (Bearer token)

### Service Portal API (`/api/issues`, `/api/equipment`, `/api/sites`)
- Issue management, Equipment tracking, Site management
- Auth: JWT (Bearer token)

### Finance API (`/api/crm/sage200/*`)
- Configuration, Customer sync, Invoice sync
- Auth: OAuth2 (Sage credentials)

### Integration Hub API (`/api/crm/integration-hub/*`)
- Event listing, retry, health monitoring
- Data model reference
- Auth: CRM JWT

### Webhook Endpoints
- `/api/webhooks/orbit4` — Orbit 4 ticket events
- `/api/webhooks/stripe` — Stripe payment events
- Future: `/api/webhooks/sage200` — Sage 200 notifications

---

## 5. Middleware / Event Bus Design

**Current Implementation:** In-process async event routing (MongoDB-backed)
**Production Path:** Add Redis/RabbitMQ for true async processing

### Event Lifecycle:
1. **Publish** → Event stored in `integration_events` collection
2. **Route** → Handler matched by `event_type`
3. **Execute** → Handler processes event
4. **Result** → Status updated (completed/failed/retry)
5. **Retry** → Failed events retried up to 3x (manual retry available)

### Event Types:
| Event | Source | Target | Handler |
|-------|--------|--------|---------|
| service_issue_created | Service Portal | CRM | Create service case |
| service_issue_updated | Service Portal | CRM | Update case status |
| engineer_ber_flagged | Service Portal | CRM | Auto-create opportunity |
| deal_closed_won | CRM | Finance | Create sales order |
| quote_accepted | CRM | Finance | Create sales order |
| invoice_created | Sage 200 | CRM | Sync invoice record |
| payment_received | Sage 200 | CRM | Update financial status |
| account_on_hold | Sage 200 | CRM | Alert sales team |
| contract_activated | CRM | Service | Set up SLA |
| asset_end_of_life | Service | CRM | Create renewal opportunity |

---

## 6. Data Sync Strategy

### Real-Time (Event-Driven):
- Service issue → CRM case (immediate)
- Deal won → Order creation (immediate)
- BER flag → Opportunity (immediate)
- Payment → CRM update (webhook)

### Scheduled (Batch):
- Sage customer sync (daily)
- Asset lifecycle check (weekly)
- Financial reconciliation (nightly)

### Manual:
- CRM → Sage contact push
- Bulk CSV import
- Data migration

---

## 7. Security Model

- **Authentication:** JWT (CRM/Portal), OAuth2 (Sage 200)
- **2FA:** TOTP for CRM users
- **RBAC:** Role-based per module (admin, manager, engineer, staff)
- **Encryption:** Credentials encrypted at rest (Sicon, Sage)
- **Audit:** All integration events logged with timestamp, user, payload
- **GDPR:** Contact data deletion cascades across linked entities
- **API Security:** Rate limiting, request validation, CORS

---

## 8. Monitoring & Health

### Integration Health Dashboard (`/api/crm/integration-hub/health`):
- Total events, success rate, failed count
- Per-system breakdown
- Recent errors with details
- Retry queue depth

### Alerting (via workflow engine):
- Integration failure → Notify admin
- Invoice overdue → Notify sales + finance
- Sage disconnect → Alert immediately

---

## 9. Collections Reference

| Collection | Domain | Description |
|------------|--------|-------------|
| crm2_companies | CRM | Companies/accounts |
| crm2_contacts | CRM | People |
| crm2_opportunities | CRM | Sales deals |
| crm2_quotes | CRM | Quotes with versioning |
| crm2_orders | CRM/Finance | Sales orders |
| crm2_activities | CRM | All activities |
| crm2_service_cases | CRM/Service | Service cases (CRM view) |
| crm2_workflows | CRM | Automation rules |
| crm2_tenders | CRM | AI tender outputs |
| crm2_invoices | Finance | Invoice records (from Sage) |
| crm2_documents | CRM | Files and documents |
| integration_events | Platform | Event bus log |
| integration_bridge | Platform | Cross-system record mapping |
| crm_integrations | Platform | Integration configs |
| issues | Service | Service portal issues |
| equipment | Service | Assets/equipment |
| sites | Service | Physical locations |
| service_contracts | Service | SLA/contract records |

---

## 10. Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| CRM API | LIVE | Full CRUD, workflows, AI |
| Service Portal API | LIVE | Issues, equipment, sites |
| Integration Hub | LIVE | Event bus, routing, health |
| Sage 200 Scaffolding | READY | Awaiting live API keys |
| Sicon Service | READY | Awaiting live API keys |
| Orbit 4 Bridge | READY | Webhooks + Sicon forwarding |
| Resend Email | READY | Awaiting DNS setup |
| Deal Won → Order | LIVE | Auto-creates on closed_won |
| Service → CRM Case | LIVE | Issues auto-bridge to CRM |
| BER → Opportunity | READY | Handler wired, needs UI trigger |
| Sage Invoice Sync | READY | Handler exists, needs Sage webhook |
| Payment Sync | READY | Handler exists, needs Sage webhook |
