"""HubSpot Parity Audit — feature-by-feature comparison against HubSpot
Professional (CRM + Marketing Hub).

Source of truth: curated from hubspot.com/pricing/marketing (crawled
2026-04-29), cross-referenced against HubSpot's public feature matrix
and Academy documentation.

Each row:
    {
        "id": stable slug,
        "category": "CRM Core" | "Marketing — Lead Gen" | "Marketing — Automation" | …
        "feature": human-readable name,
        "hubspot_tier": "Free" | "Starter" | "Pro" | "Enterprise",
        "our_status": "shipped" | "partial" | "missing" | "not_planned",
        "our_implementation": where/how we ship it (file, endpoint, or "—"),
        "gap_notes": what's missing vs HubSpot (if partial/missing),
        "priority": "P0" | "P1" | "P2" | "none",  # our roadmap priority
    }

The file is hand-curated — this module just exposes it to the admin UI.
Update `FEATURE_MATRIX` and increment `LAST_AUDITED` when re-running.
"""
from __future__ import annotations

LAST_AUDITED = "2026-04-30"
HUBSPOT_BASELINE = "Professional (Marketing Hub + Smart CRM)"

# Short-form status codes — kept tight so the UI table stays scannable.
# shipped    → behaviourally equivalent to HubSpot Pro
# partial    → exists but narrower scope / missing sub-features
# missing    → not built yet, candidate for roadmap
# not_planned → deliberately out-of-scope for Pulse Fitness
FEATURE_MATRIX: list[dict] = [
    # ──────── CRM CORE (Smart CRM) ────────
    {
        "id": "crm-contacts", "category": "CRM Core", "feature": "Contacts",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/crm_core.py — /api/crm/contacts CRUD + GDPR opt-outs",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-companies", "category": "CRM Core", "feature": "Companies",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/crm_v2.py — /api/crm/companies CRUD",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-deals", "category": "CRM Core", "feature": "Deals (sales pipeline)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/crm_v2.py — deal stages + pipeline board UI",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-tickets", "category": "CRM Core", "feature": "Tickets",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/support.py — service desk + Pulse ticket flow",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-tasks", "category": "CRM Core", "feature": "Tasks & to-dos",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "routes/crm_v2.py — /api/crm/activities",
        "gap_notes": "No bulk-task creator or task templates. No overdue-task email digests.",
        "priority": "P2",
    },
    {
        "id": "crm-lifecycle", "category": "CRM Core", "feature": "Lifecycle stages (Lead → Customer)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "Iter 222 — Lead/Prospect/Customer tags on contacts",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-custom-props", "category": "CRM Core", "feature": "Custom properties (contacts/deals)",
        "hubspot_tier": "Starter", "our_status": "partial",
        "our_implementation": "schemas allow extra fields, but no user-facing property builder UI",
        "gap_notes": "HubSpot lets admins define fields without code. We require schema changes.",
        "priority": "P1",
    },
    {
        "id": "crm-custom-objects", "category": "CRM Core", "feature": "Custom objects",
        "hubspot_tier": "Enterprise", "our_status": "not_planned",
        "our_implementation": "—",
        "gap_notes": "Enterprise-only in HubSpot; not needed for fitness-industry focus.",
        "priority": "none",
    },
    {
        "id": "crm-lists", "category": "CRM Core", "feature": "Active & static lists / segments",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "frontend/Marketing/AudiencesTab.js — basic audience builder",
        "gap_notes": "No saved rule-based active lists with auto-refresh. No list history/versions.",
        "priority": "P1",
    },
    {
        "id": "crm-associations", "category": "CRM Core", "feature": "Association labels (e.g. decision maker)",
        "hubspot_tier": "Starter", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "Contacts can associate with companies but we don't support labeled roles.",
        "priority": "P2",
    },
    {
        "id": "crm-email-tracking", "category": "CRM Core", "feature": "1:1 email tracking (opens / clicks)",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "Resend webhook captures opens for broadcast emails",
        "gap_notes": "No Gmail/Outlook extension for 1:1 rep emails. No per-contact timeline.",
        "priority": "P1",
    },
    {
        "id": "crm-email-templates", "category": "CRM Core", "feature": "Email templates for sales reps",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "routes/crm_ai.py — AI-generated sales emails",
        "gap_notes": "No saved reusable template library with merge tokens.",
        "priority": "P2",
    },
    {
        "id": "crm-meetings", "category": "CRM Core", "feature": "Meetings scheduler (Calendly-style)",
        "hubspot_tier": "Starter", "our_status": "partial",
        "our_implementation": "routes/crm_ai.py — meeting intelligence + recording summaries",
        "gap_notes": "No public booking link; relies on external Calendly.",
        "priority": "P1",
    },
    {
        "id": "crm-calling", "category": "CRM Core", "feature": "In-app calling (VOIP)",
        "hubspot_tier": "Starter", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No Twilio/HubSpot-calling parity. Would need Twilio integration.",
        "priority": "P2",
    },
    {
        "id": "crm-quotes", "category": "CRM Core", "feature": "Quotes & CPQ",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "routes/crm_cpq.py — full CPQ with line items, PDF, Stripe links",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-contracts", "category": "CRM Core", "feature": "Contracts & e-signature",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "routes/crm_contracts.py — e-sign + versioning",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-inbox", "category": "CRM Core", "feature": "Shared team inbox",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "routes/crm_inbox.py — conversations + assignment",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-documents", "category": "CRM Core", "feature": "Document sharing & tracking",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "routes/crm_documents.py + master_admin_documents_lib.py",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "crm-deal-insights", "category": "CRM Core", "feature": "AI deal insights & next-best actions",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "routes/crm_ai.py — /api/crm/ai/deal-insights (Claude)",
        "gap_notes": "", "priority": "none",
    },

    # ──────── MARKETING — LEAD GEN ────────
    {
        "id": "mkt-forms", "category": "Marketing — Lead Gen", "feature": "Forms (pop-up, embedded, standalone)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/marketing_forms.py + Marketing/FormsAndPagesTab.js + /forms/{slug} hosted page (Iter 228)",
        "gap_notes": "Embedded `<script>` snippet for 3rd-party sites is v2.",
        "priority": "none",
    },
    {
        "id": "mkt-form-automation", "category": "Marketing — Lead Gen", "feature": "Form automation (email reply, CRM update)",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "Form submit auto-creates CRM contact (lifecycle=Lead) + sends notify + optional confirmation email (Iter 228)",
        "gap_notes": "",
        "priority": "none",
    },
    {
        "id": "mkt-landing-pages", "category": "Marketing — Lead Gen", "feature": "Landing page builder",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "routes/marketing_forms.py /pages + Marketing/PageBuilderDialog.js + /p/{slug} public page with UTM tracking (Iter 228)",
        "gap_notes": "Single hero+body+form template. Multi-template + drag-drop deferred to v2.",
        "priority": "none",
    },
    {
        "id": "mkt-ctas", "category": "Marketing — Lead Gen", "feature": "Smart CTAs with targeting",
        "hubspot_tier": "Starter", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No targeted-CTA engine (by device/country/referrer). Static CTAs only.",
        "priority": "P2",
    },
    {
        "id": "mkt-chat", "category": "Marketing — Lead Gen", "feature": "Live chat (widget)",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "Help Centre AI assistant is on-site, but no human-agent handoff.",
        "gap_notes": "No real-time human operator chat.",
        "priority": "P2",
    },
    {
        "id": "mkt-chatbots", "category": "Marketing — Lead Gen", "feature": "Conversational chatbots",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "Help Centre AI (Claude) + Ask Support Desk + Fault triage bot",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-whatsapp", "category": "Marketing — Lead Gen", "feature": "WhatsApp Business integration",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No WhatsApp channel. Member comms limited to email + SMS (mocked).",
        "priority": "P2",
    },
    {
        "id": "mkt-messenger", "category": "Marketing — Lead Gen", "feature": "Facebook Messenger integration",
        "hubspot_tier": "Free", "our_status": "not_planned",
        "our_implementation": "—",
        "gap_notes": "Not relevant for B2B SaaS; skip.",
        "priority": "none",
    },
    {
        "id": "mkt-ads", "category": "Marketing — Lead Gen", "feature": "Ad management (Google / Meta / LinkedIn)",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "frontend/Marketing/SocialTab.js scaffold — Meta only, not live",
        "gap_notes": "Social tab scaffolded; real ad APIs pending user credentials. No cross-platform pixel.",
        "priority": "P2",
    },
    {
        "id": "mkt-ad-retargeting", "category": "Marketing — Lead Gen", "feature": "Ad retargeting audiences",
        "hubspot_tier": "Free", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No audience sync to ad platforms.",
        "priority": "P2",
    },
    {
        "id": "mkt-social-scheduling", "category": "Marketing — Lead Gen", "feature": "Social media scheduling",
        "hubspot_tier": "Pro", "our_status": "partial",
        "our_implementation": "Marketing/SocialTab.js + CreativeStudioTab.js",
        "gap_notes": "UI exists; live publishing pending real API credentials.",
        "priority": "P2",
    },
    {
        "id": "mkt-lead-scoring", "category": "Marketing — Lead Gen", "feature": "Lead scoring",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "routes/crm_ai.py — /api/crm/ai/lead-score (Claude-scored)",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-segments-active", "category": "Marketing — Lead Gen", "feature": "Active segments (dynamic rule-based)",
        "hubspot_tier": "Starter", "our_status": "partial",
        "our_implementation": "Marketing/AudiencesTab.js — static only",
        "gap_notes": "Segments don't auto-refresh when contacts change.",
        "priority": "P1",
    },
    {
        "id": "mkt-aeo", "category": "Marketing — Lead Gen", "feature": "Answer Engine Optimisation (ChatGPT/Gemini visibility)",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "New HubSpot feature (2025). No parity — but arguably novel enough to ship if Pulse wants ChatGPT search visibility.",
        "priority": "P2",
    },

    # ──────── MARKETING — AUTOMATION & EMAIL ────────
    {
        "id": "mkt-email-marketing", "category": "Marketing — Automation", "feature": "Email marketing (broadcast)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "routes/marketing_director.py — Resend-powered campaigns",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-email-automation", "category": "Marketing — Automation", "feature": "Email automation sequences",
        "hubspot_tier": "Starter", "our_status": "partial",
        "our_implementation": "frontend/Marketing/JourneyCanvas.js + JourneysTab.js",
        "gap_notes": "Journey canvas exists but limited trigger types. No true multi-step drip.",
        "priority": "P1",
    },
    {
        "id": "mkt-email-ab", "category": "Marketing — Automation", "feature": "Email A/B testing",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No A/B split-send logic on broadcast emails.",
        "priority": "P1",
    },
    {
        "id": "mkt-email-smart-content", "category": "Marketing — Automation", "feature": "Smart/personalised email content",
        "hubspot_tier": "Pro", "our_status": "partial",
        "our_implementation": "Merge tokens supported on sender email; no conditional blocks.",
        "gap_notes": "HubSpot lets you swap blocks based on contact properties. We don't.",
        "priority": "P1",
    },
    {
        "id": "mkt-email-send-time", "category": "Marketing — Automation", "feature": "Send-time optimisation (AI)",
        "hubspot_tier": "Pro-Beta", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No ML-chosen send time per recipient.",
        "priority": "P2",
    },
    {
        "id": "mkt-email-health", "category": "Marketing — Automation", "feature": "Email health reporting (bounces, deliverability)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "Iter 219 — EmailHealthPill + /api/email-health",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-email-send-api", "category": "Marketing — Automation", "feature": "Transactional/single-send email API",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "Resend API wired across backend.",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-workflows-omni", "category": "Marketing — Automation", "feature": "Omni-channel marketing workflows",
        "hubspot_tier": "Pro", "our_status": "partial",
        "our_implementation": "crm_workflows.py + JourneyCanvas.js",
        "gap_notes": "Email only today. No SMS/push/in-app triggers from the same canvas.",
        "priority": "P1",
    },
    {
        "id": "mkt-workflows-tasks", "category": "Marketing — Automation", "feature": "Workflow actions (update CRM, create task, …)",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "crm_workflows.py — actions on contact/deal updates",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-cookie-consent", "category": "Marketing — Automation", "feature": "Cookie consent / GDPR banner",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "Cookie banner component + GDPR opt-outs on contacts (Iter 222)",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "mkt-programmable-email", "category": "Marketing — Automation", "feature": "Programmable email (CRM-data-driven content)",
        "hubspot_tier": "Pro-Beta", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No mechanism to embed CRM-queried tables into email body.",
        "priority": "P2",
    },

    # ──────── MARKETING — ANALYTICS & REPORTING ────────
    {
        "id": "ana-dashboards", "category": "Marketing — Analytics", "feature": "Reporting dashboards",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "Master Admin Analytics + Pulse Reports",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ana-custom-reports", "category": "Marketing — Analytics", "feature": "Custom report builder",
        "hubspot_tier": "Pro", "our_status": "partial",
        "our_implementation": "KPIPerformanceDashboard — preset lenses",
        "gap_notes": "No drag-and-drop chart builder. Users can't define their own metrics.",
        "priority": "P1",
    },
    {
        "id": "ana-web-traffic", "category": "Marketing — Analytics", "feature": "Website traffic analytics",
        "hubspot_tier": "Free", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No pageview/session tracking on our marketing sites.",
        "priority": "P1",
    },
    {
        "id": "ana-campaigns", "category": "Marketing — Analytics", "feature": "Campaign reporting",
        "hubspot_tier": "Pro", "our_status": "partial",
        "our_implementation": "Marketing/PerformanceTab.js",
        "gap_notes": "Per-campaign open/click counts. No revenue attribution.",
        "priority": "P1",
    },
    {
        "id": "ana-seo", "category": "Marketing — Analytics", "feature": "SEO analytics & recommendations",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No on-page SEO audits or keyword tracking.",
        "priority": "P2",
    },
    {
        "id": "ana-gsc", "category": "Marketing — Analytics", "feature": "Google Search Console integration",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No GSC data pull for SEO reporting.",
        "priority": "P2",
    },
    {
        "id": "ana-revenue-attrib", "category": "Marketing — Analytics", "feature": "Multi-touch revenue attribution",
        "hubspot_tier": "Enterprise", "our_status": "not_planned",
        "our_implementation": "—",
        "gap_notes": "Enterprise-only; over-engineered for our target segment.",
        "priority": "none",
    },
    {
        "id": "ana-journey", "category": "Marketing — Analytics", "feature": "Customer journey analytics",
        "hubspot_tier": "Enterprise", "our_status": "not_planned",
        "our_implementation": "—",
        "gap_notes": "Enterprise-only; defer.",
        "priority": "none",
    },
    {
        "id": "ana-kpi-lenses", "category": "Marketing — Analytics", "feature": "Role-based analytics lenses",
        "hubspot_tier": "None (GymAxis unique)", "our_status": "shipped",
        "our_implementation": "Manager/Regional/Director 3-role lenses (Iter ~195)",
        "gap_notes": "Novel to GymAxis — not a HubSpot feature.",
        "priority": "none",
    },

    # ──────── MARKETING — CONTENT ────────
    {
        "id": "cms-blog", "category": "Marketing — Content", "feature": "Blog CMS",
        "hubspot_tier": "Starter", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No blog module. GymAxis marketing team would need to use WordPress/Webflow.",
        "priority": "P2",
    },
    {
        "id": "cms-website", "category": "Marketing — Content", "feature": "Website / page builder",
        "hubspot_tier": "Pro", "our_status": "not_planned",
        "our_implementation": "—",
        "gap_notes": "Out of scope — our marketing pages ship with the app.",
        "priority": "none",
    },
    {
        "id": "cms-ai-content", "category": "Marketing — Content", "feature": "AI content assistant (writer)",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "Claude-powered Campaign Wizard copilot + AI Creative Studio",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "cms-ai-images", "category": "Marketing — Content", "feature": "AI image generation",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "Gemini Nano Banana — CreativeStudioTab.js",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "cms-brand-kit", "category": "Marketing — Content", "feature": "Brand kit (fonts, colours, logos)",
        "hubspot_tier": "Pro", "our_status": "shipped",
        "our_implementation": "Marketing/BrandKitTab.js",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "cms-video", "category": "Marketing — Content", "feature": "Video hosting & analytics",
        "hubspot_tier": "Pro", "our_status": "missing",
        "our_implementation": "—",
        "gap_notes": "No native video hosting.",
        "priority": "P2",
    },

    # ──────── OPERATIONS / ADMIN ────────
    {
        "id": "ops-user-mgmt", "category": "Operations", "feature": "User management & teams",
        "hubspot_tier": "Starter", "our_status": "shipped",
        "our_implementation": "Master Admin → Roles (with Service Desk + Pulse admin delegation)",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ops-permissions", "category": "Operations", "feature": "Granular permissions / limit access",
        "hubspot_tier": "Enterprise", "our_status": "partial",
        "our_implementation": "Role-based guards in FastAPI deps; no per-record field-level restrictions.",
        "gap_notes": "Can't yet say 'user X cannot see deal property Y'.",
        "priority": "P2",
    },
    {
        "id": "ops-audit-log", "category": "Operations", "feature": "Audit log (admin activity)",
        "hubspot_tier": "Enterprise", "our_status": "shipped",
        "our_implementation": "audit_logs + admin_activity_log collections; LoginEventsPanel",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ops-sso", "category": "Operations", "feature": "SSO (SAML / OIDC)",
        "hubspot_tier": "Enterprise", "our_status": "partial",
        "our_implementation": "Emergent-managed Google OAuth; no SAML yet.",
        "gap_notes": "No SAML IdP integration (Okta/Azure AD).",
        "priority": "P2",
    },
    {
        "id": "ops-mfa", "category": "Operations", "feature": "MFA (TOTP + backup codes)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "auth/mfa endpoints + QR / backup codes",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ops-gdpr", "category": "Operations", "feature": "GDPR opt-out management",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "utils/gdpr.py + per-contact opt-out toggles (Iter 222)",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ops-data-export", "category": "Operations", "feature": "Data export (admin)",
        "hubspot_tier": "Free", "our_status": "shipped",
        "our_implementation": "Iter 225 Master Admin DB Viewer — JSON + CSV",
        "gap_notes": "", "priority": "none",
    },
    {
        "id": "ops-integrations", "category": "Operations", "feature": "2,000+ app integrations marketplace",
        "hubspot_tier": "Free", "our_status": "partial",
        "our_implementation": "Sicon, Sage 200, Stripe, Resend, Gemini, Claude, Meta (scaffold)",
        "gap_notes": "Curated deep integrations beat breadth for fitness vertical; no open marketplace.",
        "priority": "none",
    },

    # ──────── FITNESS-VERTICAL DIFFERENTIATORS (GymAxis unique) ────────
    {
        "id": "gym-equipment-fleet", "category": "Fitness-Vertical", "feature": "Equipment fleet + fault triage",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "Full equipment CRUD + AI Fault Triage (Iter 223)",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-memberships", "category": "Fitness-Vertical", "feature": "Memberships + class bookings",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "memberships.py + instructor / member portals",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-gym-floor", "category": "Fitness-Vertical", "feature": "Gym Floor shared-credential staff login",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "gym_floor.py + handover diary + fault logging",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-dunning", "category": "Fitness-Vertical", "feature": "Automated dunning + collections dashboard",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "invoice_dunning.py + collections_dashboard.py (Iter 213-214)",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-sicon", "category": "Fitness-Vertical", "feature": "Sicon Service integration + field mapping UI",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "sicon_mapping.py + SiconMappingPanel.js (Iter 221)",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-spec-sheets", "category": "Fitness-Vertical", "feature": "Manufacturer spec-sheet library + auto-match",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "spec_sheets.py + admin library",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
    {
        "id": "gym-image-catalogue", "category": "Fitness-Vertical", "feature": "Equipment image catalogue (manufacturer sitemap ingest)",
        "hubspot_tier": "None", "our_status": "shipped",
        "our_implementation": "manufacturer_catalogue.py + CataloguePanel (Iter 226)",
        "gap_notes": "Novel to GymAxis.",
        "priority": "none",
    },
]


def get_matrix() -> list[dict]:
    """Public accessor — copy-safe (callers may mutate freely)."""
    return [dict(row) for row in FEATURE_MATRIX]


def get_summary() -> dict:
    """Aggregate counts for the header of the admin UI."""
    totals = {"shipped": 0, "partial": 0, "missing": 0, "not_planned": 0}
    for row in FEATURE_MATRIX:
        totals[row["our_status"]] = totals.get(row["our_status"], 0) + 1
    total = len(FEATURE_MATRIX)
    covered = totals["shipped"] + totals["partial"]
    coverage_pct = round((covered / total) * 100) if total else 0
    return {
        "last_audited": LAST_AUDITED,
        "hubspot_baseline": HUBSPOT_BASELINE,
        "total_features": total,
        "counts": totals,
        "coverage_pct": coverage_pct,
    }
