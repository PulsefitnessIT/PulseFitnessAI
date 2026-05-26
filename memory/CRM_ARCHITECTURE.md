> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> CRM Phase 3 has shipped end-to-end since the original v2 architecture
> doc was written. New surfaces & data flows:
>
> | New surface | Module | Route |
> | --- | --- | --- |
> | Drag-and-drop territory tree | CRM Phase 3 | `/api/crm/v2/territories` |
> | AI next-best-action | CRM Phase 3 | `/api/crm/v2/companies/{id}/next-best-action` |
> | Cross-module activity timeline | CRM Phase 3 | `/api/crm/v2/companies/{id}/timeline` |
> | Reports suite (per-report date filters) | CRM Phase 3 | `/api/crm/reports?from_iso=…&to_iso=…` |
> | Website-first enrichment | CRM Phase 3 | `/api/crm/v2/companies/auto-recognize` |
> | Quote send + DocuSign hook | CPQ | `/api/crm/v2/quotes/{id}/send` |
>
> **Module-tailored trial onboarding (iter 216h227)**
> The `primary_module` captured at signup narrows the post-signup
> activation funnel to `crm`-relevant events only when a prospect
> arrives via the CRM module landing page. The picker (`MODULE_INTENT_MAP`
> in `ModulePage.js`) maps `crm → crm`, `service → operations`, etc.
>
> **Three new CRM activation event types** with emit hooks:
> - `first_lead_added`  — emitted by `POST /api/crm/companies`
> - `first_deal_created` — emitted by `POST /api/crm/deals`
> - `first_quote_sent`   — emitted by `POST /api/crm/quotes/{id}/send`
>
> All best-effort wrapped (`try/except`) so they never block CRM writes.
>
> **Schema additions**
> Picklists, products, quotes, deals all backed by collections
> `crm_picklists`, `crm_products`, `crm_v2_companies`, `crm_v2_contacts`,
> `crm_deals`, `crm_quotes`. Miller Heiman stakeholder mapping wired
> on contacts.

---


# GymAxis CRM — Enterprise Architecture Document
## Version 2.0 — Complete Rebuild

---

## 1. Product Architecture

### Platform Structure
```
GymAxis AI
├── Marketing Site (gymaxisai.com)
├── Self-Service Portal (/pulse) — Customer-facing service management
├── CRM Application (/crm) — Sales, service admin, engineering, leadership
└── Master Admin (/admin) — Platform governance
```

### Single Source of Truth Principle
Every record in the system is connected. A Company links to Contacts, Opportunities, Quotes, Orders, Assets, Cases, Visits, Documents, Invoices, and Activities. Every sidebar module operates on the same shared data model.

### Tech Stack
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python) + MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Payments**: Stripe
- **Accounting**: Sage 200 (bi-directional sync)
- **Auth**: JWT + RBAC

---

## 2. Data Model — Core Entities

### Account/Commercial Entities
| Entity | Key Fields | Links To |
|--------|-----------|----------|
| **Company** | name, sector, type, parent_id, account_owner, sla_tier, revenue_band | Sites, Contacts, Opportunities, Quotes, Orders, Assets, Cases, Contracts, Invoices, Documents, Activities |
| **Site** | name, address, company_id, site_type, status | Equipment/Assets, Cases, Visits, Contacts |
| **Contact** | first_name, last_name, email, phone, company_id, role, decision_maker, champion, gdpr_consent | Activities, Opportunities, Quotes, Cases, Messages, Meetings |
| **Opportunity** | title, company_id, contact_id, stage, value, probability, close_date, owner_id | Quotes, Activities, Tasks, Documents, Competitors, Stage History |
| **Quote** | quote_number, opportunity_id, company_id, status, total, valid_until | Line Items, Approvals, Orders, Documents |
| **Quote Line** | quote_id, product_id, quantity, unit_price, discount, total | Product |
| **Order** | order_number, quote_id, company_id, status, total | Line Items, Assets, Invoices, Contracts |
| **Contract** | contract_number, company_id, type, start_date, end_date, value, renewal_date | Assets, Cases, Invoices |
| **Invoice** | invoice_number, company_id, order_id, status, total, due_date, paid_date | Payments |
| **Product** | name, sku, category, unit_price, description, active | Quote Lines, Order Lines, Assets |

### Service Entities
| Entity | Key Fields | Links To |
|--------|-----------|----------|
| **Asset** | serial_number, product_id, company_id, site_id, status, install_date, warranty_expiry | Cases, Visits, Parts Usage, Contracts |
| **Service Case** | case_number, company_id, asset_id, severity, status, sla_due, assigned_to | Visits, Parts, Activities, Documents |
| **Visit** | case_id, engineer_id, site_id, scheduled_date, status, notes | Parts Used, Photos, Signature |
| **Part** | name, part_number, price, stock_level | Parts Usage |
| **Parts Usage** | visit_id, part_id, quantity, cost | Visit, Part |

### Activity Engine
| Entity | Key Fields | Links To |
|--------|-----------|----------|
| **Activity** | type (call/email/meeting/note/task/visit), subject, body, contact_id, company_id, opportunity_id, case_id, owner_id, due_date, completed_at | Everything — polymorphic link |
| **Message Thread** | channel (email/sms/whatsapp/chat), contact_id, company_id, status, assigned_to | Messages |
| **Message** | thread_id, direction, body, sender, timestamp | Thread |

### System Entities
| Entity | Key Fields | Links To |
|--------|-----------|----------|
| **User** | email, full_name, role, team_id, territory_id | Owned records |
| **Team** | name, manager_id | Users |
| **Role** | name, permissions | Users |
| **Territory** | name, regions, owner_id | Companies, Opportunities |
| **Workflow** | name, trigger, conditions, actions, active | Workflow Runs |
| **AI Agent** | name, type, model, prompt, active | Agent Action Logs |
| **Audit Log** | entity, entity_id, action, user_id, changes, timestamp | Everything |

---

## 3. Role-Based Permissions

| Capability | Sales Manager | Service Admin | Engineer | Director | CRM Admin |
|-----------|:---:|:---:|:---:|:---:|:---:|
| View Dashboard | Own pipeline | Service queue | My jobs | All rollup | System health |
| Manage Contacts | Full | View + link | View assigned | View all | Full |
| Manage Companies | Full | View + service | View assigned | View all | Full |
| Manage Pipeline | Full | View | — | View all | Full |
| Manage Quotes | Create/Edit | View | — | Approve | Full |
| Manage Cases | View | Full | Update assigned | View all | Full |
| Manage Visits | View | Dispatch | Complete assigned | View all | Full |
| AI Tools | Sales agents | Service agents | Knowledge agent | All | Configure |
| Settings | — | — | — | — | Full |
| Workflows | View own | View own | — | View all | Full |
| Forecasting | Own forecast | — | — | All forecasts | Full |
| Imports | — | — | — | Approve | Full |

---

## 4. Module Specifications

### 4.1 Dashboard
- **Sales Manager**: Pipeline value, weighted forecast, won revenue, deals by stage, stagnating deals, upcoming meetings, tasks due, AI next actions, recent activity
- **Service Admin**: Open cases by severity, engineer load, parts pending, SLA breaches, overdue visits, customer escalations
- **Engineer**: Today's visits, assigned cases, asset lookup, recent notes
- **Director**: Revenue rollup, pipeline health, service backlog, conversion rates, team performance, renewal pipeline
- Every widget drills to underlying records

### 4.2 Contacts
- Full profile with relationship score, decision-maker flag, champion/detractor tags
- Linked: company, opportunities, quotes, cases, activities, messages
- Actions: call, email, schedule meeting, add note, create opportunity
- AI summary, communication preferences, GDPR consent tracking

### 4.3 Companies
- Master commercial record with parent-child hierarchy
- Linked: sites, contacts, opportunities, quotes, orders, assets, cases, contracts, invoices
- Account plan, revenue history, service tier, upsell/renewal signals
- AI account summary

### 4.4 Pipeline
- Kanban + list views with custom stages
- Weighted forecast, win probability, stagnation alerts
- Stage exit criteria, deal checklists, buying committee
- Linked: contacts, quotes, activities, documents
- AI deal risk analysis, next-step recommendations

### 4.5 Inbox
- Unified timeline: email, SMS, WhatsApp, chat, internal notes
- SLA timers, sentiment detection, AI reply drafts
- Linked to contact/company/case records

### 4.6 Workflows
- Visual trigger → condition → action builder
- Templates for common flows (lead nurture, quote follow-up, renewal, service escalation)
- Supports delays, approvals, notifications, record updates, AI actions

### 4.7 Quotes (CPQ)
- Product catalog with bundles, pricing rules, discounts
- Quote → Approval → Send → Accept → Order → Contract → Asset → Invoice
- Versioning, digital signature, Sage 200 sync

### 4.8 Documents
- Linked to any record (contact, company, opportunity, case, visit)
- Version control, permissions, AI summary, OCR extraction
- Templates for proposals, contracts, service reports

### 4.9 AI Tools
- 14 autonomous/assistive agents
- Lead generation, qualification, nurturing, prospecting
- Sales coaching, account intelligence, quote assistant
- Service triage, engineer knowledge, parts recommendation
- Data quality, customer summary, renewal agent
- All actions logged, explainable, reviewable

### 4.10 Settings
- Users, teams, roles, permissions, territories
- Custom fields, stage rules, data governance
- Audit logs, branding, templates, integrations
- AI prompt management, consent management

---

## 5. MVP Scope (Phase 1)

### What we build NOW:
1. **Data model**: All core entities with relationships
2. **Activity engine**: Unified timeline across all records
3. **Dashboard**: Role-based with drill-through widgets
4. **Companies**: Full record page with linked modules
5. **Contacts**: Full profile with activity timeline
6. **Pipeline**: Kanban + list with stage management
7. **Global search / command palette**
8. **RBAC foundation**

### Phase 2:
- Inbox (unified messaging)
- Quotes (CPQ) with approval workflow
- Workflows automation engine
- AI Agents (lead gen, qualification, triage)
- Service integration (cases, visits, assets)

### Phase 3:
- Sage 200 bi-directional sync
- Import/migration tools
- Mobile/PWA with offline
- Forecasting & territory management
- Document intelligence

---

## 6. Service Portal Integration

The CRM and Self-Service portal share the same MongoDB collections:
- `equipment` → CRM sees as "Assets / Installed Base"
- `issues` → CRM sees as "Service Cases"
- `organizations` → CRM sees as "Companies"
- `users` → Self-service users, engineers
- `crm_users` → CRM users (sales, service admin, leadership)

This means:
- A fault logged in self-service instantly appears as a case in CRM
- An engineer completing a visit in self-service updates the CRM timeline
- A sales manager can see service history before meetings
- A Closed Won deal can trigger installation workflows in self-service

---

*Document version: 2.0 | Created: Apr 15 2026*
