> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> Parity check below remains useful as a feature gap analysis vs
> HubSpot Professional. Items now closed since the audit was first
> written:
>
> | HubSpot feature | GymAxis status (Feb 2026) |
> | --- | --- |
> | Territory management with drag-drop ownership | ✅ shipped (CRM Phase 3 — territory tree) |
> | AI next-best-action on Contact / Company | ✅ shipped (CRM Phase 3) |
> | Cross-module activity timeline | ✅ shipped (CRM Phase 3) |
> | Per-report date-range filters | ✅ shipped (CRM Phase 3) |
> | Website-first enrichment | ✅ shipped (CRM Phase 3) |
> | Module-specific trial onboarding | ✅ shipped (iter 216h227) |
> | DocuSign on Quote send | 🟢 code-ready, waiting on creds |
> | Sequences (drip nurture) | 🟡 partial — see Marketing Suite PRD |
> | Predictive lead scoring | 🟢 next-best-action covers this; full model planned |
>
> Outstanding gaps from the original audit that remain genuinely
> open are documented in `memory/ROADMAP.md` § P1/P2.

---


# HubSpot Parity Audit

**Baseline**: Professional (Marketing Hub + Smart CRM)  
**Last audited**: 2026-04-29  
**Total features**: 74  
**Coverage**: **70%** (shipped + partial)  

## Summary

| Status | Count | % |
| --- | ---: | ---: |
| ✅ Shipped | 34 | 46% |
| ⚠️ Partial | 18 | 24% |
| ❌ Missing | 17 | 23% |
| ➖ Not planned | 5 | 7% |

## Feature matrix

### CRM Core

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Contacts | Free | ✅ | routes/crm_core.py — /api/crm/contacts CRUD + GDPR opt-outs | — |
| Companies | Free | ✅ | routes/crm_v2.py — /api/crm/companies CRUD | — |
| Deals (sales pipeline) | Free | ✅ | routes/crm_v2.py — deal stages + pipeline board UI | — |
| Tickets | Free | ✅ | routes/support.py — service desk + Pulse ticket flow | — |
| Tasks & to-dos | Free | ⚠️ | routes/crm_v2.py — /api/crm/activities<br>_Gap: No bulk-task creator or task templates. No overdue-task email digests._ | **P2** |
| Lifecycle stages (Lead → Customer) | Free | ✅ | Iter 222 — Lead/Prospect/Customer tags on contacts | — |
| Custom properties (contacts/deals) | Starter | ⚠️ | schemas allow extra fields, but no user-facing property builder UI<br>_Gap: HubSpot lets admins define fields without code. We require schema changes._ | **P1** |
| Custom objects | Enterprise | ➖ | —<br>_Gap: Enterprise-only in HubSpot; not needed for fitness-industry focus._ | — |
| Active & static lists / segments | Free | ⚠️ | frontend/Marketing/AudiencesTab.js — basic audience builder<br>_Gap: No saved rule-based active lists with auto-refresh. No list history/versions._ | **P1** |
| Association labels (e.g. decision maker) | Starter | ❌ | —<br>_Gap: Contacts can associate with companies but we don't support labeled roles._ | **P2** |
| 1:1 email tracking (opens / clicks) | Free | ⚠️ | Resend webhook captures opens for broadcast emails<br>_Gap: No Gmail/Outlook extension for 1:1 rep emails. No per-contact timeline._ | **P1** |
| Email templates for sales reps | Free | ⚠️ | routes/crm_ai.py — AI-generated sales emails<br>_Gap: No saved reusable template library with merge tokens._ | **P2** |
| Meetings scheduler (Calendly-style) | Starter | ⚠️ | routes/crm_ai.py — meeting intelligence + recording summaries<br>_Gap: No public booking link; relies on external Calendly._ | **P1** |
| In-app calling (VOIP) | Starter | ❌ | —<br>_Gap: No Twilio/HubSpot-calling parity. Would need Twilio integration._ | **P2** |
| Quotes & CPQ | Starter | ✅ | routes/crm_cpq.py — full CPQ with line items, PDF, Stripe links | — |
| Contracts & e-signature | Pro | ✅ | routes/crm_contracts.py — e-sign + versioning | — |
| Shared team inbox | Starter | ✅ | routes/crm_inbox.py — conversations + assignment | — |
| Document sharing & tracking | Starter | ✅ | routes/crm_documents.py + master_admin_documents_lib.py | — |
| AI deal insights & next-best actions | Pro | ✅ | routes/crm_ai.py — /api/crm/ai/deal-insights (Claude) | — |

### Marketing — Lead Gen

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Forms (pop-up, embedded, standalone) | Free | ❌ | —<br>_Gap: No form builder. Leads currently come in via Pulse contact page + direct API._ | **P1** |
| Form automation (email reply, CRM update) | Starter | ❌ | —<br>_Gap: Depends on mkt-forms shipping first._ | **P1** |
| Landing page builder | Starter | ❌ | —<br>_Gap: No WYSIWYG landing page editor. Landing pages currently code-built in React._ | **P1** |
| Smart CTAs with targeting | Starter | ❌ | —<br>_Gap: No targeted-CTA engine (by device/country/referrer). Static CTAs only._ | **P2** |
| Live chat (widget) | Free | ⚠️ | Help Centre AI assistant is on-site, but no human-agent handoff.<br>_Gap: No real-time human operator chat._ | **P2** |
| Conversational chatbots | Starter | ✅ | Help Centre AI (Claude) + Ask Support Desk + Fault triage bot | — |
| WhatsApp Business integration | Pro | ❌ | —<br>_Gap: No WhatsApp channel. Member comms limited to email + SMS (mocked)._ | **P2** |
| Facebook Messenger integration | Free | ➖ | —<br>_Gap: Not relevant for B2B SaaS; skip._ | — |
| Ad management (Google / Meta / LinkedIn) | Free | ⚠️ | frontend/Marketing/SocialTab.js scaffold — Meta only, not live<br>_Gap: Social tab scaffolded; real ad APIs pending user credentials. No cross-platform pixel._ | **P2** |
| Ad retargeting audiences | Free | ❌ | —<br>_Gap: No audience sync to ad platforms._ | **P2** |
| Social media scheduling | Pro | ⚠️ | Marketing/SocialTab.js + CreativeStudioTab.js<br>_Gap: UI exists; live publishing pending real API credentials._ | **P2** |
| Lead scoring | Pro | ✅ | routes/crm_ai.py — /api/crm/ai/lead-score (Claude-scored) | — |
| Active segments (dynamic rule-based) | Starter | ⚠️ | Marketing/AudiencesTab.js — static only<br>_Gap: Segments don't auto-refresh when contacts change._ | **P1** |
| Answer Engine Optimisation (ChatGPT/Gemini visibility) | Pro | ❌ | —<br>_Gap: New HubSpot feature (2025). No parity — but arguably novel enough to ship if Pulse wants ChatGPT search visibility._ | **P2** |

### Marketing — Automation

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Email marketing (broadcast) | Free | ✅ | routes/marketing_director.py — Resend-powered campaigns | — |
| Email automation sequences | Starter | ⚠️ | frontend/Marketing/JourneyCanvas.js + JourneysTab.js<br>_Gap: Journey canvas exists but limited trigger types. No true multi-step drip._ | **P1** |
| Email A/B testing | Pro | ❌ | —<br>_Gap: No A/B split-send logic on broadcast emails._ | **P1** |
| Smart/personalised email content | Pro | ⚠️ | Merge tokens supported on sender email; no conditional blocks.<br>_Gap: HubSpot lets you swap blocks based on contact properties. We don't._ | **P1** |
| Send-time optimisation (AI) | Pro-Beta | ❌ | —<br>_Gap: No ML-chosen send time per recipient._ | **P2** |
| Email health reporting (bounces, deliverability) | Free | ✅ | Iter 219 — EmailHealthPill + /api/email-health | — |
| Transactional/single-send email API | Pro | ✅ | Resend API wired across backend. | — |
| Omni-channel marketing workflows | Pro | ⚠️ | crm_workflows.py + JourneyCanvas.js<br>_Gap: Email only today. No SMS/push/in-app triggers from the same canvas._ | **P1** |
| Workflow actions (update CRM, create task, …) | Starter | ✅ | crm_workflows.py — actions on contact/deal updates | — |
| Cookie consent / GDPR banner | Free | ✅ | Cookie banner component + GDPR opt-outs on contacts (Iter 222) | — |
| Programmable email (CRM-data-driven content) | Pro-Beta | ❌ | —<br>_Gap: No mechanism to embed CRM-queried tables into email body._ | **P2** |

### Marketing — Analytics

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Reporting dashboards | Free | ✅ | Master Admin Analytics + Pulse Reports | — |
| Custom report builder | Pro | ⚠️ | KPIPerformanceDashboard — preset lenses<br>_Gap: No drag-and-drop chart builder. Users can't define their own metrics._ | **P1** |
| Website traffic analytics | Free | ❌ | —<br>_Gap: No pageview/session tracking on our marketing sites._ | **P1** |
| Campaign reporting | Pro | ⚠️ | Marketing/PerformanceTab.js<br>_Gap: Per-campaign open/click counts. No revenue attribution._ | **P1** |
| SEO analytics & recommendations | Pro | ❌ | —<br>_Gap: No on-page SEO audits or keyword tracking._ | **P2** |
| Google Search Console integration | Pro | ❌ | —<br>_Gap: No GSC data pull for SEO reporting._ | **P2** |
| Multi-touch revenue attribution | Enterprise | ➖ | —<br>_Gap: Enterprise-only; over-engineered for our target segment._ | — |
| Customer journey analytics | Enterprise | ➖ | —<br>_Gap: Enterprise-only; defer._ | — |
| Role-based analytics lenses | None (GymAxis unique) | ✅ | Manager/Regional/Director 3-role lenses (Iter ~195)<br>_Gap: Novel to GymAxis — not a HubSpot feature._ | — |

### Marketing — Content

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Blog CMS | Starter | ❌ | —<br>_Gap: No blog module. GymAxis marketing team would need to use WordPress/Webflow._ | **P2** |
| Website / page builder | Pro | ➖ | —<br>_Gap: Out of scope — our marketing pages ship with the app._ | — |
| AI content assistant (writer) | Pro | ✅ | Claude-powered Campaign Wizard copilot + AI Creative Studio | — |
| AI image generation | Pro | ✅ | Gemini Nano Banana — CreativeStudioTab.js | — |
| Brand kit (fonts, colours, logos) | Pro | ✅ | Marketing/BrandKitTab.js | — |
| Video hosting & analytics | Pro | ❌ | —<br>_Gap: No native video hosting._ | **P2** |

### Operations

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| User management & teams | Starter | ✅ | Master Admin → Roles (with Service Desk + Pulse admin delegation) | — |
| Granular permissions / limit access | Enterprise | ⚠️ | Role-based guards in FastAPI deps; no per-record field-level restrictions.<br>_Gap: Can't yet say 'user X cannot see deal property Y'._ | **P2** |
| Audit log (admin activity) | Enterprise | ✅ | audit_logs + admin_activity_log collections; LoginEventsPanel | — |
| SSO (SAML / OIDC) | Enterprise | ⚠️ | Emergent-managed Google OAuth; no SAML yet.<br>_Gap: No SAML IdP integration (Okta/Azure AD)._ | **P2** |
| MFA (TOTP + backup codes) | Free | ✅ | auth/mfa endpoints + QR / backup codes | — |
| GDPR opt-out management | Free | ✅ | utils/gdpr.py + per-contact opt-out toggles (Iter 222) | — |
| Data export (admin) | Free | ✅ | Iter 225 Master Admin DB Viewer — JSON + CSV | — |
| 2,000+ app integrations marketplace | Free | ⚠️ | Sicon, Sage 200, Stripe, Resend, Gemini, Claude, Meta (scaffold)<br>_Gap: Curated deep integrations beat breadth for fitness vertical; no open marketplace._ | — |

### Fitness-Vertical

| Feature | HubSpot tier | Status | Our implementation / gap | Priority |
| --- | --- | :---: | --- | :---: |
| Equipment fleet + fault triage | None | ✅ | Full equipment CRUD + AI Fault Triage (Iter 223)<br>_Gap: Novel to GymAxis._ | — |
| Memberships + class bookings | None | ✅ | memberships.py + instructor / member portals<br>_Gap: Novel to GymAxis._ | — |
| Gym Floor shared-credential staff login | None | ✅ | gym_floor.py + handover diary + fault logging<br>_Gap: Novel to GymAxis._ | — |
| Automated dunning + collections dashboard | None | ✅ | invoice_dunning.py + collections_dashboard.py (Iter 213-214)<br>_Gap: Novel to GymAxis._ | — |
| Sicon Service integration + field mapping UI | None | ✅ | sicon_mapping.py + SiconMappingPanel.js (Iter 221)<br>_Gap: Novel to GymAxis._ | — |
| Manufacturer spec-sheet library + auto-match | None | ✅ | spec_sheets.py + admin library<br>_Gap: Novel to GymAxis._ | — |
| Equipment image catalogue (manufacturer sitemap ingest) | None | ✅ | manufacturer_catalogue.py + CataloguePanel (Iter 226)<br>_Gap: Novel to GymAxis._ | — |

## Notable gaps (prioritised for roadmap)

### P1 — next-quarter candidates
- **Custom properties (contacts/deals)** — HubSpot lets admins define fields without code. We require schema changes.
- **Active & static lists / segments** — No saved rule-based active lists with auto-refresh. No list history/versions.
- **1:1 email tracking (opens / clicks)** — No Gmail/Outlook extension for 1:1 rep emails. No per-contact timeline.
- **Meetings scheduler (Calendly-style)** — No public booking link; relies on external Calendly.
- **Forms (pop-up, embedded, standalone)** — No form builder. Leads currently come in via Pulse contact page + direct API.
- **Form automation (email reply, CRM update)** — Depends on mkt-forms shipping first.
- **Landing page builder** — No WYSIWYG landing page editor. Landing pages currently code-built in React.
- **Active segments (dynamic rule-based)** — Segments don't auto-refresh when contacts change.
- **Email automation sequences** — Journey canvas exists but limited trigger types. No true multi-step drip.
- **Email A/B testing** — No A/B split-send logic on broadcast emails.
- **Smart/personalised email content** — HubSpot lets you swap blocks based on contact properties. We don't.
- **Omni-channel marketing workflows** — Email only today. No SMS/push/in-app triggers from the same canvas.
- **Custom report builder** — No drag-and-drop chart builder. Users can't define their own metrics.
- **Website traffic analytics** — No pageview/session tracking on our marketing sites.
- **Campaign reporting** — Per-campaign open/click counts. No revenue attribution.

### P2 — longer-term candidates
- **Tasks & to-dos** — No bulk-task creator or task templates. No overdue-task email digests.
- **Association labels (e.g. decision maker)** — Contacts can associate with companies but we don't support labeled roles.
- **Email templates for sales reps** — No saved reusable template library with merge tokens.
- **In-app calling (VOIP)** — No Twilio/HubSpot-calling parity. Would need Twilio integration.
- **Smart CTAs with targeting** — No targeted-CTA engine (by device/country/referrer). Static CTAs only.
- **Live chat (widget)** — No real-time human operator chat.
- **WhatsApp Business integration** — No WhatsApp channel. Member comms limited to email + SMS (mocked).
- **Ad management (Google / Meta / LinkedIn)** — Social tab scaffolded; real ad APIs pending user credentials. No cross-platform pixel.
- **Ad retargeting audiences** — No audience sync to ad platforms.
- **Social media scheduling** — UI exists; live publishing pending real API credentials.
- **Answer Engine Optimisation (ChatGPT/Gemini visibility)** — New HubSpot feature (2025). No parity — but arguably novel enough to ship if Pulse wants ChatGPT search visibility.
- **Send-time optimisation (AI)** — No ML-chosen send time per recipient.
- **Programmable email (CRM-data-driven content)** — No mechanism to embed CRM-queried tables into email body.
- **SEO analytics & recommendations** — No on-page SEO audits or keyword tracking.
- **Google Search Console integration** — No GSC data pull for SEO reporting.
- **Blog CMS** — No blog module. GymAxis marketing team would need to use WordPress/Webflow.
- **Video hosting & analytics** — No native video hosting.
- **Granular permissions / limit access** — Can't yet say 'user X cannot see deal property Y'.
- **SSO (SAML / OIDC)** — No SAML IdP integration (Okta/Azure AD).

## GymAxis differentiators (novel vs HubSpot)

The following features have no HubSpot equivalent and represent our fitness-vertical moat:

- **Role-based analytics lenses** — Manager/Regional/Director 3-role lenses (Iter ~195)
- **Equipment fleet + fault triage** — Full equipment CRUD + AI Fault Triage (Iter 223)
- **Memberships + class bookings** — memberships.py + instructor / member portals
- **Gym Floor shared-credential staff login** — gym_floor.py + handover diary + fault logging
- **Automated dunning + collections dashboard** — invoice_dunning.py + collections_dashboard.py (Iter 213-214)
- **Sicon Service integration + field mapping UI** — sicon_mapping.py + SiconMappingPanel.js (Iter 221)
- **Manufacturer spec-sheet library + auto-match** — spec_sheets.py + admin library
- **Equipment image catalogue (manufacturer sitemap ingest)** — manufacturer_catalogue.py + CataloguePanel (Iter 226)

---
_Data source: `backend/data/hubspot_parity.py`. Update there and redeploy to refresh this audit._
