"""GymAxis Help Centre — seed guide corpus.

Every guide is a self-contained, structured object following the brand's
mandatory help format: title → description → steps → UI notes → tips →
common mistakes → related actions. Guides are grouped by one of 10
canonical categories and tagged with roles so the Help Centre can show
only what the current user actually has access to.

Why a file (not DB)?
- Guides are product-editorial content, reviewed alongside code changes.
- They benefit from code review, linting, and git history.
- No write UI or admin needed to ship the initial corpus.

If/when we add user-authored guides later, we can merge an admin-written
DB collection with this corpus — the public API already takes the union.
"""
from __future__ import annotations

import re

from typing import Literal, TypedDict

# Canonical category IDs — frontend renders these in this order.
CATEGORIES: list[dict] = [
    {"id": "getting-started", "label": "Getting Started",      "blurb": "Your first 15 minutes on GymAxis."},
    {"id": "crm",              "label": "CRM",                   "blurb": "Contacts, companies, pipeline, deals."},
    {"id": "service",          "label": "Service & Faults",      "blurb": "Log, triage and resolve equipment issues."},
    {"id": "memberships",      "label": "Memberships & Bookings","blurb": "Members, plans, classes, timetable."},
    {"id": "marketing",        "label": "Marketing Suite",       "blurb": "Audiences, campaigns, AI Creative Director."},
    {"id": "staffing",         "label": "Staffing & Rota",       "blurb": "Smart Rota, marketplace, payroll, live floor."},
    {"id": "staff",            "label": "Staff Access",          "blurb": "Gym Floor kiosk and staff roles."},
    {"id": "reporting",        "label": "Reporting & Analytics", "blurb": "Dashboards, exports, weekly digest."},
    {"id": "admin",            "label": "Admin & Settings",      "blurb": "Users, sites, branding, security."},
    {"id": "integrations",     "label": "Integrations",          "blurb": "Sicon, Sage 200, Stripe, Resend, Meta."},
    {"id": "ai",               "label": "AI Features",           "blurb": "AI Director, copilot, assistant, triage."},
]

Role = Literal["owner", "manager", "staff", "gym_floor", "master_admin"]
ALL_ROLES: tuple[Role, ...] = ("owner", "manager", "staff", "gym_floor", "master_admin")


class Guide(TypedDict, total=False):
    id: str
    category: str
    title: str
    description: str         # <=140 chars — shown on the card
    read_minutes: int        # approximate
    roles: list[str]         # empty = visible to all
    popular: bool            # show on "Most popular" rail
    updated_at: str          # ISO date
    steps: list[dict]        # [{title, body, ui_hint?}]
    tips: list[str]
    mistakes: list[str]
    related: list[str]       # ids of related guides
    module: str              # matches Navbar module routes: operations|memberships|crm|marketing|admin
    # Optional interactive walkthrough — reuses GuidedTour (Joyride).
    # Each step targets a `[data-testid=...]` in the live app. The
    # Help Centre "Start walkthrough" button fires an event consumed
    # by the GuidedTour host mounted at the App root.
    walkthrough: dict        # {initial_route: "/pulse", steps: [{target, title, content, placement?}]}


GUIDES: list[Guide] = [
    # ── Getting Started ─────────────────────────────────────────────
    {
        "id": "gs-first-login",
        "category": "getting-started",
        "module": "operations",
        "title": "Your first 15 minutes on GymAxis",
        "description": "The exact order to set up your site, invite staff, and log your first fault.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Open the 'Start' tab in any module",      "body": "Every module now ships with a guided Start tab — it walks you through the next useful action based on what's configured already.", "ui_hint": "Look for the sparkle icon on the left of the tab bar."},
            {"title": "Import your equipment",                   "body": "Operations → Start → 'Add your equipment'. Drop in a CSV or add machines one by one.", "ui_hint": "Serials, suppliers and warranty expiry can all be pasted from your current spreadsheet."},
            {"title": "Invite your team",                         "body": "Admin → Users → 'Invite'. Pick a role (Owner, Manager, Staff, Gym Floor) and they get a magic-link email."},
            {"title": "Log your first fault",                    "body": "Operations → Faults → 'Log a fault'. Snap a photo, pick a severity, and GymAxis routes it to the right supplier automatically."},
            {"title": "Set up weekly reports",                   "body": "Reports → Weekly Digest. Choose recipients — the first digest lands next Monday 7 am."},
        ],
        "tips": [
            "Invite one trusted manager before inviting everyone — it's a good dry run.",
            "You can switch modules in the top-right module switcher at any time.",
            "Hit ⌘/Ctrl + K anywhere to jump to any tab quickly.",
        ],
        "mistakes": [
            "Don't import equipment AFTER logging faults — serials won't auto-link.",
            "Avoid inviting staff as Owners 'just in case' — roles are granular and can be upgraded later.",
        ],
        "related": ["admin-invite-user", "service-log-fault", "reporting-weekly-digest"],
    },
    {
        "id": "gs-modules-overview",
        "category": "getting-started",
        "module": "operations",
        "title": "The four GymAxis modules explained",
        "description": "Operations, Memberships, CRM and Marketing — what each is for, who uses it, when to switch.",
        "read_minutes": 2,
        "roles": [],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Operations",   "body": "Equipment, faults, check-sheets, suppliers, compliance. This is your floor team's home."},
            {"title": "Memberships",  "body": "Members, plans, timetable, classes, instructors, check-in. Member-facing activities live here."},
            {"title": "CRM",           "body": "Contacts, companies, pipeline, deals, contracts, tenders. Use this for sales conversations, B2B accounts, and internal partner-manager work."},
            {"title": "Marketing",    "body": "Audiences, campaigns, AI Creative Director, journeys, social. Everything that sends a member a message."},
            {"title": "Switch modules", "body": "Top-right: pick a module from the switcher. Your role and permissions follow you across every module automatically."},
        ],
        "tips": [
            "You don't need to 'belong' to only one module — a manager typically uses all four.",
            "Each module has its own Start tab for first-time users. You can hide it per-device once you're familiar.",
        ],
        "mistakes": [],
        "related": ["gs-first-login", "admin-roles-explained"],
    },

    # ── CRM ────────────────────────────────────────────────────────
    {
        "id": "crm-add-contact",
        "category": "crm",
        "module": "crm",
        "title": "Add a contact (and link it to a company)",
        "description": "The fastest path to building a clean, de-duplicated contact list.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "CRM → Contacts → New contact",    "body": "Top-right '+ New' button. Name + email are the only required fields."},
            {"title": "Link to a company (optional)",    "body": "Start typing the company name in the 'Company' field — GymAxis auto-suggests matches. Pick one or click '+ Create new'."},
            {"title": "Save",                             "body": "The contact is created and a welcome activity is logged in their timeline. No email sent unless you choose to."},
        ],
        "tips": [
            "Use the bulk CSV import for 50+ contacts — avoid 50 'new contact' submissions.",
            "Link to a company up-front — un-linked contacts are harder to search later.",
        ],
        "mistakes": [
            "Duplicate checking is email-based — if you leave email blank, duplicates can slip in.",
        ],
        "related": ["crm-company-setup", "crm-pipeline-first-deal"],
        "walkthrough": {
            "initial_route": "/crm",
            "steps": [
                {"target": "[data-testid='crm-tabs-desktop']",   "title": "CRM tabs",        "content": "All CRM sections live behind these pills.", "placement": "bottom"},
                {"target": "[data-testid='crm-nav-contacts']",   "title": "Open 'Contacts'", "content": "Click Contacts. This is where people — not companies — are tracked.", "placement": "bottom"},
            ],
        },
    },
    {
        "id": "crm-pipeline-first-deal",
        "category": "crm",
        "module": "crm",
        "title": "Run your first deal through the pipeline",
        "description": "Create a deal, move it across stages, and send a quote — in under 5 minutes.",
        "read_minutes": 4,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "CRM → Pipeline → '+ New deal'",   "body": "Pick the contact + company, add deal value and expected close date."},
            {"title": "Drag the card across stages",     "body": "Lead → Qualified → Proposal → Won/Lost. The activity feed on the right auto-logs every move."},
            {"title": "Generate a quote in Proposal",    "body": "Open the deal → 'Create quote'. GymAxis pulls pricing from your CPQ library. Versions are tracked automatically."},
            {"title": "Send the quote",                   "body": "'Send for signature' emails the PDF and tracks opens. E-signature comes back into the deal."},
        ],
        "tips": [
            "Set 'Expected close date' honestly — the AI forecast in Dashboard uses it.",
            "Use '@mention' in deal comments to loop in a colleague — they get a notification.",
        ],
        "mistakes": [
            "Don't re-key quote prices manually — update the CPQ library once and every future quote pulls the new rate.",
        ],
        "related": ["crm-add-contact", "crm-company-setup"],
    },
    {
        "id": "crm-company-setup",
        "category": "crm",
        "module": "crm",
        "title": "Set up a multi-site company record",
        "description": "Capture group contracts, sites, and AI-recognised organisations.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "popular": False,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "CRM → Companies → '+ New'",       "body": "Company name, HQ postcode and industry are enough to start."},
            {"title": "Add your contacts",                 "body": "Open the company record → Contacts tab → '+ Add contact' to link existing or new contacts to the company."},
            {"title": "Add sites",                         "body": "Use the 'Sites' tab on the company record to add each gym location. Each site can have its own primary contact."},
            {"title": "Attach a contract",                "body": "'Contracts' tab → '+ New contract'. Pick the pricing model (per-site, group rate, multi-year) — GymAxis calculates renewal value on the fly."},
        ],
        "tips": [
            "Tagging companies by 'Franchise' vs 'Independent' makes pipeline forecasting cleaner.",
        ],
        "mistakes": [
            "Don't create one 'mega company' for every franchise — build one company per operating entity.",
        ],
        "related": ["crm-add-contact", "crm-contracts-overview"],
    },
    {
        "id": "crm-contracts-overview",
        "category": "crm",
        "module": "crm",
        "title": "Attach and manage a contract",
        "description": "Track SLAs, billing, renewal dates, and approvals on one record.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Open the company",                "body": "CRM → Companies → pick the company → Contracts tab."},
            {"title": "Add contract details",             "body": "Term length, start/end date, SLA tier, billing frequency and total contract value."},
            {"title": "Assign approvers",                  "body": "Pick the people who sign internally. GymAxis routes renewals to them automatically 90 days before the end date."},
            {"title": "Upload signed PDF",                 "body": "Drop the file into the Documents tab. OCR indexes it so you can search clauses later."},
        ],
        "tips": [
            "Set renewal reminders to 90 / 60 / 30 days — avoid renewal scrambles.",
        ],
        "mistakes": [
            "Uploading unsigned drafts as 'active' confuses the renewal engine.",
        ],
        "related": ["crm-company-setup"],
    },

    # ── Service & Faults ───────────────────────────────────────────
    {
        "id": "service-log-fault",
        "category": "service",
        "module": "operations",
        "title": "How to log a fault in under 60 seconds",
        "description": "The fastest way to report an issue so it routes to the right supplier automatically.",
        "read_minutes": 1,
        "roles": [],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Operations → Faults → 'Log a fault'",  "body": "Or scan the QR code on the machine directly from your phone."},
            {"title": "Pick the equipment",                    "body": "Start typing the serial or equipment name. GymAxis auto-fills type, supplier and warranty."},
            {"title": "Choose severity",                        "body": "Operational Minor / Fault Present / Limited Use / Out of Order / Safety Critical. Severity determines who gets the alert."},
            {"title": "Add a photo",                            "body": "Optional but strongly recommended — AI triages the issue from the photo and suggests likely causes."},
            {"title": "Submit",                                  "body": "GymAxis emails the supplier, logs a tracking note on Sicon (if connected), and adds the fault to Reports."},
        ],
        "tips": [
            "Scanning the QR on the machine skips the equipment picker.",
            "Safety Critical faults also notify owners by SMS.",
        ],
        "mistakes": [
            "Don't log faults for the same issue twice — GymAxis flags duplicates, but check before submitting.",
            "Avoid skipping the photo — it's the biggest predictor of same-day supplier acceptance.",
        ],
        "related": ["service-triage-ai", "service-supplier-portal"],
        "walkthrough": {
            "initial_route": "/pulse",
            "steps": [
                {"target": "[data-testid='pulse-dashboard-tabs']",    "title": "Operations tabs",      "content": "Your home base. We'll switch to Faults next.", "placement": "bottom"},
                {"target": "[data-testid='lite-tab-faults']",          "title": "Click 'Faults'",       "content": "This is where every fault in your site lives. Click it to open the Faults tab.", "placement": "bottom"},
                {"target": "[data-testid='faults-content']",           "title": "The Faults view",      "content": "Use the 'Log a fault' button at the top. We'll auto-route your report to the right supplier.", "placement": "top"},
            ],
        },
    },
    {
        "id": "service-triage-ai",
        "category": "service",
        "module": "operations",
        "title": "Let the AI triage a fault for you",
        "description": "Understand how GymAxis recommends severity and likely root cause.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Open a logged fault with a photo",   "body": "Operations → Faults → pick a fault. The 'AI triage' card appears in the side panel."},
            {"title": "Read the recommendation",            "body": "GymAxis explains the likely fault (e.g. 'Display flicker — probable PSU'), severity, and suggested next step."},
            {"title": "Accept or override",                  "body": "Click 'Apply triage' to update severity + supplier routing, or edit manually — either way your decision trains the model."},
        ],
        "tips": [
            "Triage confidence is shown as a % — below 60% we recommend manual review.",
        ],
        "mistakes": [
            "Don't rely on triage for Safety Critical judgements — always double-check physically.",
        ],
        "related": ["service-log-fault"],
    },

    # ── Memberships ────────────────────────────────────────────────
    {
        "id": "mbr-onboard-first",
        "category": "memberships",
        "module": "memberships",
        "title": "Onboard your first member",
        "description": "From empty state to a welcomed member in under 5 minutes.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Memberships → Start → 'Bulk import members'",  "body": "For 10+ members — drag your CSV, confirm column mapping, click Import."},
            {"title": "Or add one manually",                            "body": "Memberships → Members → '+ New'. Name, email, plan, start date."},
            {"title": "Assign a plan",                                  "body": "Pick from your existing plans, or click 'Create plan' if you haven't set any up yet."},
            {"title": "Send welcome email",                             "body": "Toggle 'Send welcome email' before saving. Uses the brand template from Brand Kit."},
        ],
        "tips": [
            "Bulk import de-dupes on email automatically.",
            "You can drag Stripe customer IDs into the CSV to preserve payment history.",
        ],
        "mistakes": [
            "Saving without a plan leaves the member in 'Unassigned' — fine as a holding state, but they can't book classes until a plan is set.",
        ],
        "related": ["mbr-first-plan", "mbr-first-class"],
        "walkthrough": {
            "initial_route": "/memberships",
            "steps": [
                {"target": "[data-testid='mbr-tabs-desktop']",   "title": "Memberships tabs", "content": "These tabs hold everything member-facing.", "placement": "bottom"},
                {"target": "[data-testid='mbr-tab-start']",      "title": "Open 'Start'",      "content": "The Start tab walks you through the first useful action.", "placement": "bottom"},
                {"target": "[data-testid='mbr-tab-members']",    "title": "Members directory", "content": "Click 'Members' when you're ready to add real people — CSV or manual both work.", "placement": "bottom"},
            ],
        },
    },
    {
        "id": "mbr-first-plan",
        "category": "memberships",
        "module": "memberships",
        "title": "Create your first membership plan",
        "description": "Price, term, benefits, and class-pack inclusions.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Memberships → Plans → '+ New plan'", "body": "Plan name (e.g. 'Peak Monthly'), billing cycle, price."},
            {"title": "Class packs (optional)",              "body": "Include 4/8/unlimited class entries per cycle — GymAxis auto-decrements as members book."},
            {"title": "Stripe-ready",                         "body": "Stripe price IDs are auto-created on save. No manual Stripe config needed."},
        ],
        "tips": [
            "Lead with the plan your best members are on — name it clearly.",
        ],
        "mistakes": [
            "Don't overload one plan with every benefit — three plans outperform seven.",
        ],
        "related": ["mbr-onboard-first", "int-stripe-connect"],
    },
    {
        "id": "mbr-first-class",
        "category": "memberships",
        "module": "memberships",
        "title": "Publish your first class",
        "description": "Add a class to the timetable that members can book themselves.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Memberships → Timetable → click a slot", "body": "Pick the start date/time — GymAxis opens the class editor."},
            {"title": "Fill the details",                       "body": "Class name, instructor, room, capacity, recurrence."},
            {"title": "Publish",                                  "body": "Members see it on their app immediately. Booking opens per your booking rules."},
        ],
        "tips": [
            "Set a waitlist cap so full classes still capture demand.",
        ],
        "mistakes": [
            "Don't publish a class with no instructor — it looks broken to members.",
        ],
        "related": ["mbr-onboard-first"],
    },

    # ── Marketing ──────────────────────────────────────────────────
    {
        "id": "mkt-first-campaign",
        "category": "marketing",
        "module": "marketing",
        "title": "Launch your first campaign with the Wizard",
        "description": "The guided 5-step wizard writes the copy and picks the audience for you.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Marketing → Start → 'Build a campaign'", "body": "Opens the Campaign Wizard modal over whichever tab you're on."},
            {"title": "Pick a goal",                             "body": "Fill empty classes / Win back inactive / Promote a class / Upsell PT / Retention touch / Custom. AI Copilot suggests the best one based on your data."},
            {"title": "Confirm the audience",                   "body": "AI pre-picks the segment — you can swap if you like."},
            {"title": "Review the AI-written copy",             "body": "Subject + body in your brand voice. Edit or regenerate any time."},
            {"title": "Pick a send time and launch",            "body": "Default to AI-optimised 'Tue 7 AM' or pick your own. Undo banner gives you 60 seconds to cancel."},
        ],
        "tips": [
            "Start with a small, targeted audience (50–200) — better results than blasting everyone.",
            "Use the Creative Studio afterwards to generate a matching social post.",
        ],
        "mistakes": [
            "Don't skip the undo banner — launching to the wrong segment is the fastest way to upset members.",
        ],
        "related": ["mkt-ai-director", "mkt-audiences-101"],
        "walkthrough": {
            "initial_route": "/marketing",
            "steps": [
                {"target": "[data-testid='mkt-tabs-desktop']",     "title": "Marketing tabs",   "content": "This is your Marketing Suite. Every section lives behind a pill.", "placement": "bottom"},
                {"target": "[data-testid='marketing-tab-start']",  "title": "Open 'Start'",      "content": "The Start tab is where guided flows begin — click it.", "placement": "bottom"},
                {"target": "[data-testid='mkt-start-tab'], [data-testid='mkt-start-wizard-btn']", "title": "Build a campaign", "content": "Click 'Build a campaign' and our 5-step wizard will write the copy, pick the audience, and schedule the send for you.", "placement": "top"},
            ],
        },
    },
    {
        "id": "mkt-ai-director",
        "category": "marketing",
        "module": "marketing",
        "title": "Use AI Creative Director for full campaigns",
        "description": "One prompt → strategy, multi-format copy, brand-locked poster, segment variants.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Marketing → Creative Studio → AI Director", "body": "The recommended default — big prompt box at the top."},
            {"title": "Describe your campaign in plain English",   "body": "'Announce our new Monday 6am HIIT class to regular morning members.' That's all."},
            {"title": "Review strategy + variants",                 "body": "GymAxis returns email + SMS + Instagram + Push copy, plus a brand-locked poster image."},
            {"title": "Push to Wizard to launch",                   "body": "'Send to Campaign Wizard' pre-fills everything — you just pick a send time."},
        ],
        "tips": [
            "Brand-lock uses your logo + accent colour from Brand Kit — keep that up to date.",
        ],
        "mistakes": [
            "Don't over-edit the AI output — small tweaks usually beat rewrites.",
        ],
        "related": ["mkt-first-campaign", "mkt-brand-kit"],
    },
    {
        "id": "mkt-audiences-101",
        "category": "marketing",
        "module": "marketing",
        "title": "Build your first audience segment",
        "description": "Use plain English or the rule builder to define who gets what.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Marketing → Audiences → '+ New'",       "body": "Type a plain-English description — 'high spenders at risk of churn'. AI drafts rules for you."},
            {"title": "Or use the rule builder manually",      "body": "Combine conditions (plan, attendance, lifetime value, last-visit) with AND/OR."},
            {"title": "Save as dynamic or snapshot",            "body": "Dynamic = auto-refresh. Snapshot = frozen list. Use snapshot for one-offs."},
        ],
        "tips": [
            "Always preview the count — if it's <10 or >80% of members, the segment is probably wrong.",
        ],
        "mistakes": [
            "Don't use snapshots for recurring journeys — the list goes stale fast.",
        ],
        "related": ["mkt-first-campaign"],
    },
    {
        "id": "mkt-brand-kit",
        "category": "marketing",
        "module": "marketing",
        "title": "Set up your Brand Kit",
        "description": "Logo, colours, typography — applied to every AI-generated creative.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Marketing → Brand Kit",             "body": "Upload logo (SVG preferred), pick primary + accent colours."},
            {"title": "Describe your brand voice",         "body": "One short line — e.g. 'Warm, encouraging, never preachy'. AI feeds this directly to the copy LLM."},
            {"title": "Save",                                "body": "Every future campaign, poster and member email uses these settings."},
        ],
        "tips": [
            "SVG logos scale cleanly across posters, emails and member app.",
        ],
        "mistakes": [
            "Avoid leaving brand voice blank — it's the single biggest driver of AI copy quality.",
        ],
        "related": ["mkt-ai-director"],
    },

    # ── Staff & Rota ───────────────────────────────────────────────
    {
        "id": "staff-gym-floor-login",
        "category": "staff",
        "module": "operations",
        "title": "Log in to Gym Floor mode",
        "description": "A locked-down touch-friendly view for shared tablets on the floor.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff", "gym_floor"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Go to /gym-floor",                  "body": "Or open the QR code printed on your front-desk card."},
            {"title": "Enter the site code + password",    "body": "Your manager provides these. No personal login needed."},
            {"title": "Tap 'Log a fault' or 'Check-in'",   "body": "Gym Floor can only do two things — log faults and run check-sheets. Zero risk of accidental admin changes."},
        ],
        "tips": [
            "Pin the tablet in kiosk mode for a truly locked-down front-desk experience.",
        ],
        "mistakes": [
            "Don't share a staff password with Gym Floor users — use the Gym Floor credentials instead.",
        ],
        "related": ["admin-invite-user"],
    },

    # ── Reporting ──────────────────────────────────────────────────
    {
        "id": "reporting-weekly-digest",
        "category": "reporting",
        "module": "operations",
        "title": "Enable the Weekly Digest",
        "description": "A 1-page weekly summary mailed to owners + managers every Monday.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Reports → Weekly Digest",            "body": "Toggle 'Email me' on."},
            {"title": "Choose who else receives it",        "body": "Add any email — recipients don't need a GymAxis login."},
            {"title": "Customise sections",                  "body": "Faults, financial summary, CAPEX alerts, membership churn — turn each section on/off."},
        ],
        "tips": [
            "Digest works best with at least 2 weeks of data behind it.",
        ],
        "mistakes": [
            "Don't email the digest to every staff member — it's a leadership tool.",
        ],
        "related": ["reporting-exports"],
    },
    {
        "id": "reporting-exports",
        "category": "reporting",
        "module": "operations",
        "title": "Export data for finance or audits",
        "description": "CSV / Excel exports with audit-ready structure.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Reports → pick a report",            "body": "e.g. Faults by supplier / Membership revenue / CAPEX priority."},
            {"title": "Filter by date range",                "body": "Pre-sets: This month / Last quarter / YTD / Custom."},
            {"title": "Click Export",                         "body": "CSV and XLSX download instantly. Password-protected Excel is a paid feature."},
        ],
        "tips": [
            "YTD exports make insurance audits quick.",
        ],
        "mistakes": [],
        "related": ["reporting-weekly-digest"],
    },

    # ── Admin & Settings ───────────────────────────────────────────
    {
        "id": "admin-invite-user",
        "category": "admin",
        "module": "admin",
        "title": "Invite a team member",
        "description": "Add a user with the right role — takes 30 seconds.",
        "read_minutes": 1,
        "roles": ["owner", "manager", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Settings → Users → '+ Invite'",     "body": "Email address, role, optional site restriction."},
            {"title": "Pick role",                           "body": "Owner, Manager, Staff, Gym Floor. See related guide for the full breakdown."},
            {"title": "Send",                                 "body": "Magic-link email. They set their own password on first login."},
        ],
        "tips": [
            "Restrict staff to specific sites if your business is multi-site.",
        ],
        "mistakes": [
            "Don't upgrade everyone to Manager 'just in case' — roles can be upgraded later without re-inviting.",
        ],
        "related": ["admin-roles-explained", "admin-security-mfa"],
        "walkthrough": {
            "initial_route": "/master-admin",
            "steps": [
                {"target": "body", "title": "Admin Console", "content": "Once you're here, look for the Users sidebar item — that's where invitations and role management live.", "placement": "center"},
            ],
        },
    },
    {
        "id": "admin-roles-explained",
        "category": "admin",
        "module": "admin",
        "title": "Roles & permissions explained",
        "description": "What Owner, Manager, Staff, Gym Floor and Master Admin can each do.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Owner",        "body": "Everything. Billing, users, sites, integrations, delete accounts."},
            {"title": "Manager",      "body": "Everything except billing + user role changes."},
            {"title": "Staff",        "body": "Day-to-day operations. Log faults, manage members, run campaigns (if permitted)."},
            {"title": "Gym Floor",    "body": "Kiosk mode — log faults and run check-sheets only. No admin surface."},
            {"title": "Master Admin", "body": "Internal GymAxis staff only. Cross-organisation view."},
        ],
        "tips": [
            "One Owner per site is plenty — every extra Owner is a security risk.",
        ],
        "mistakes": [],
        "related": ["admin-invite-user"],
    },
    {
        "id": "admin-security-mfa",
        "category": "admin",
        "module": "admin",
        "title": "Turn on two-factor auth (MFA)",
        "description": "Protect your account with an authenticator app.",
        "read_minutes": 2,
        "roles": [],
        "popular": False,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Account → Security → Enable MFA",   "body": "Scan the QR with Authy, 1Password or Google Authenticator."},
            {"title": "Save backup codes",                  "body": "Download them — one-time codes in case you lose your device."},
            {"title": "Confirm with a 6-digit code",        "body": "Done. Future logins require the code."},
        ],
        "tips": [
            "Enforce MFA for all Owners + Managers via Settings → Security.",
        ],
        "mistakes": [
            "Don't store backup codes in the same password manager as your login — keep a copy offline too.",
        ],
        "related": [],
    },

    # ── Integrations ───────────────────────────────────────────────
    {
        "id": "int-stripe-connect",
        "category": "integrations",
        "module": "admin",
        "title": "Connect Stripe for member payments",
        "description": "One-click Stripe Connect — handles plans, refunds, and PCI compliance.",
        "read_minutes": 3,
        "roles": ["owner", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Memberships → Settings → Payments", "body": "Click 'Connect Stripe'."},
            {"title": "Sign in to Stripe",                  "body": "Use your existing Stripe account or create a new one. Takes ~2 minutes for a new account."},
            {"title": "Authorise GymAxis",                  "body": "Read-only + charge + refund permissions. You can revoke at any time from Stripe directly."},
            {"title": "Go live",                             "body": "Your plans become purchasable instantly. GymAxis handles webhooks, dunning, and failed card retries."},
        ],
        "tips": [
            "Start in Test mode if you want to preview flows without real charges.",
        ],
        "mistakes": [
            "Don't disconnect Stripe mid-month — in-flight subscriptions will fail to renew.",
        ],
        "related": ["mbr-first-plan"],
    },
    {
        "id": "int-sage200",
        "category": "integrations",
        "module": "admin",
        "title": "Sync finance data to Sage 200",
        "description": "Push invoices, payments and credit notes to Sage automatically.",
        "read_minutes": 3,
        "roles": ["owner", "master_admin"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Integrations → Sage 200 → Connect", "body": "Paste your Sage API credentials (from your Sage account admin)."},
            {"title": "Map nominal codes",                   "body": "Assign a nominal code per revenue type — memberships, PT, day passes."},
            {"title": "Enable sync",                          "body": "Daily auto-sync at 1 am. Retry queue handles transient Sage outages."},
        ],
        "tips": [],
        "mistakes": [
            "Don't map everything to one nominal — you'll lose insight in Sage reports.",
        ],
        "related": ["int-sicon"],
    },
    {
        "id": "int-sicon",
        "category": "integrations",
        "module": "admin",
        "title": "Connect Sicon Service Manager",
        "description": "Bi-directional sync for cases, engineer visits, and tracking notes.",
        "read_minutes": 3,
        "roles": ["master_admin"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Integrations → Sicon → Connect",    "body": "Paste your Sicon R260200c API key."},
            {"title": "Map sites and engineers",             "body": "Link each GymAxis site + engineer to its Sicon counterpart."},
            {"title": "Enable event hooks",                   "body": "Faults, AI triage, supplier replies and engineer visits auto-post as tracking notes in Sicon."},
        ],
        "tips": [],
        "mistakes": [],
        "related": [],
    },

    # ── AI Features ────────────────────────────────────────────────
    {
        "id": "ai-assistant",
        "category": "ai",
        "module": "marketing",
        "title": "Using the AI Marketing Assistant",
        "description": "Chat with Claude about your marketing data and get one-click actions.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Marketing → open the bottom-right assistant", "body": "Click the sparkle icon. The assistant is context-aware to whichever tab you're on."},
            {"title": "Ask a question",                               "body": "'Why did last week's open rate drop?' or 'Which members are about to lapse?'"},
            {"title": "Accept an action",                              "body": "The assistant suggests one concrete action (switch tab, instantiate a template, clear demo data). Click to execute."},
        ],
        "tips": [
            "Short, specific questions beat long paragraphs.",
        ],
        "mistakes": [
            "Don't expect access to private member PII through the assistant — it's scoped to aggregate data.",
        ],
        "related": ["mkt-first-campaign"],
    },
    {
        "id": "ai-campaign-copilot",
        "category": "ai",
        "module": "marketing",
        "title": "Meet the Campaign Copilot",
        "description": "The AI rail inside Campaign Wizard that writes copy, picks audiences, and explains why.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Open Campaign Wizard",             "body": "Marketing → 'Build a campaign'. The copilot is on the right."},
            {"title": "Watch it think per step",           "body": "A 'Thinking…' indicator shows while Claude generates tailored suggestions for that step."},
            {"title": "One-click apply",                    "body": "Each suggestion has a button to apply it — populates the form instantly."},
        ],
        "tips": [],
        "mistakes": [],
        "related": ["mkt-first-campaign", "ai-assistant"],
    },
    {
        "id": "ai-fault-triage",
        "category": "ai",
        "module": "operations",
        "title": "AI fault triage explained",
        "description": "How GymAxis predicts severity, root cause, and supplier routing from a photo.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-27",
        "steps": [
            {"title": "Log a fault with a photo",         "body": "Photo quality matters — bright, sharp, close-up works best."},
            {"title": "Open the fault",                     "body": "The AI triage card appears — severity, likely cause, recommended action."},
            {"title": "Train the model by accepting or editing", "body": "Every accept/override trains the triage model for your site."},
        ],
        "tips": [],
        "mistakes": [],
        "related": ["service-log-fault", "service-triage-ai"],
    },

    # ── New features added in iterations 198-207 ───────────────────
    {
        "id": "gs-setup-checklist",
        "category": "getting-started",
        "module": "operations",
        "title": "The Setup Checklist explained",
        "description": "First-login progress pill — gets you to value in under 15 minutes.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Look bottom-right after first login",  "body": "A small 'Setup progress 0/6' pill appears once you sign in."},
            {"title": "Click to expand the checklist",        "body": "Six tasks with one-tap deep-links: add a site, invite a teammate, log your first fault, add equipment, create a member, send a campaign."},
            {"title": "Tasks tick off automatically",         "body": "Completing each underlying action ticks the box — no manual marking needed."},
            {"title": "Hits 6/6 → checklist disappears",      "body": "Sticky welcome surface only while it's useful. Reappears for new owners."},
        ],
        "tips": [
            "The pill respects light/dark mode. If it ever looks dark on a light background, that's a bug — flag it to support.",
            "Master admins don't see the checklist (they're not setting up an org).",
        ],
        "mistakes": [
            "Don't dismiss it for the team — every new owner benefits from it on day one.",
        ],
        "related": ["gs-first-login", "gs-modules-overview"],
    },
    {
        "id": "service-onboard-from-invoice",
        "category": "service",
        "module": "operations",
        "title": "Onboard equipment from a supplier invoice",
        "description": "Drop in a PDF, AI extracts every line item — full fleet onboarded in minutes.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Operations → Equipment → Add equipment", "body": "Or trigger from the Setup Checklist's 'Add your equipment' tile."},
            {"title": "Click 'Import from Invoice'",            "body": "Three options appear: Invoice PDF, CSV upload, or a CSV template download."},
            {"title": "Drop in the supplier invoice PDF",       "body": "AI parses every line item — make, model, serial, install date, qty. You see a preview before committing."},
            {"title": "Review + commit",                         "body": "Edit anything that looks wrong, then 'Add to fleet'. Equipment shows up in the list with spec-sheet hero images auto-pulled."},
        ],
        "tips": [
            "The CSV template is the fastest path if you already have a spreadsheet of kit.",
            "Spec-sheet matching works best when you fill in the manufacturer field — Pulse Fitness, Life Fitness, Technogym, Matrix all have first-class matches.",
        ],
        "mistakes": [
            "Don't drop in a low-resolution scan — OCR quality matters. Use the original PDF if you have it.",
            "Empty manufacturer = no spec-sheet match = generic placeholder image. Always fill it in.",
        ],
        "related": ["service-log-fault", "admin-bulk-import"],
    },
    {
        "id": "mbr-analytics-roles",
        "category": "memberships",
        "module": "memberships",
        "title": "Analytics — Manager / Regional / Director views",
        "description": "Three role-shaped lenses on the same data, switchable in one click.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Memberships → Analytics",                 "body": "Three pills top-right: Manager (30d), Regional (60d), Director (90d)."},
            {"title": "Manager view",                            "body": "Day-to-day operating metrics — last 30 days. Revenue, churn, attendance, instructor leaderboard."},
            {"title": "Regional view",                           "body": "60-day window. Adds site-by-site comparisons and class-template performance."},
            {"title": "Director view",                            "body": "90-day window. Adds revenue forecasts, lifetime-value cohorts, retention curves."},
        ],
        "tips": [
            "All three views stay visible in light AND dark mode — if any pill text disappears in light mode, that's a regression worth flagging.",
            "Charts respect the theme — Revenue trend / Revenue by product flip with light/dark.",
        ],
        "mistakes": [
            "Don't switch roles every refresh — pick the lens for the question you're answering, then stick with it.",
        ],
        "related": ["mbr-first-plan", "reporting-weekly-digest"],
    },
    {
        "id": "mkt-campaign-wizard-copilot",
        "category": "marketing",
        "module": "marketing",
        "title": "AI Copilot inside the Campaign Wizard",
        "description": "Claude Sonnet 4.5 writes audience filters, subject lines, body copy and journey steps on demand.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Marketing → Campaigns → New campaign",   "body": "The wizard launches. AI Copilot button is top-right of every step."},
            {"title": "Audience step — 'Suggest audience'",     "body": "Copilot reads your real members, churn signals and last 30 days of activity, then drafts a filter you can tweak."},
            {"title": "Copy step — 'Suggest subject + body'",   "body": "Generates 3 subject lines + a body draft in your brand voice. Click to swap, click again to refine."},
            {"title": "Review step — 'Suggest journey'",         "body": "Recommends follow-up steps (reminder email, SMS nudge, push) and timings calibrated to your churn data."},
        ],
        "tips": [
            "Rate-limited to 30 requests/minute per user to protect LLM budget — you'll never see this unless you're hammering it.",
            "Copilot output is a draft, not gospel. Always review the copy before sending — your brand, your voice.",
        ],
        "mistakes": [
            "Don't paste copilot output into other channels (e.g. Instagram captions) without re-reading. The copy is calibrated to email + SMS tone.",
        ],
        "related": ["mkt-first-campaign", "mkt-ai-director"],
    },
    {
        "id": "staffing-overview",
        "category": "staffing",
        "module": "operations",
        "title": "Tour of the Staffing Console",
        "description": "10 tabs that replace RotaCloud + Connecteam — Rota, Marketplace, Payroll, Live Floor, AI insights.",
        "read_minutes": 4,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Operations → Staffing tab",              "body": "Managers + owners see 'Staffing'; staff see 'Gym Floor'. Same module, different role lens."},
            {"title": "Rota — drag-drop shifts",                 "body": "Build the week. Drag a staff member onto a slot, copy a week to next week, publish in one click. AI flags compliance issues (under-18, overtime, 11-hour rest)."},
            {"title": "Staff — profiles, certifications, contracts","body": "One row per staff member. Tracks lifeguard renewals, contract type, hourly cost, weekly cap."},
            {"title": "Time Off — leave requests + approvals",  "body": "Staff submit; managers approve or decline with one tap. Auto-deducts from holiday allowance."},
            {"title": "Shift Marketplace — peer-to-peer cover", "body": "Staff post 'I can't work Sat 9-12'; teammates pick it up; manager rubber-stamps."},
            {"title": "Performance — KPIs per staff",            "body": "Attendance, sessions delivered, member NPS feedback, fault-resolution time."},
            {"title": "Payroll — CSV export for accounts",        "body": "One-click monthly payroll. Honours PAYE, holiday pay, overtime rules."},
            {"title": "Live Floor — who's on shift right now",    "body": "Wall-mounted dashboard. AI moderates handover notes between shifts."},
            {"title": "Rules — org-level guardrails",             "body": "Min rest hours, max consecutive days, manager approval for overtime — set once."},
            {"title": "Announcements + AI Insights",              "body": "Broadcast to a single shift or the whole team. AI Insights flags emerging patterns ('Saturday mornings are understaffed 4 weeks running')."},
        ],
        "tips": [
            "Start with Rules — set your guardrails once and the rota can't violate them.",
            "Marketplace cuts manager firefighting in half — let staff sort their own swaps.",
        ],
        "mistakes": [
            "Don't bulk-import staff before configuring Rules — you'll miss compliance flags on the import.",
            "Don't share Live Floor on a public-facing screen — it shows staff names + shifts.",
        ],
        "related": ["staffing-marketplace", "staff-gym-floor-login"],
    },
    {
        "id": "staffing-marketplace",
        "category": "staffing",
        "module": "operations",
        "title": "Shift marketplace — staff cover their own swaps",
        "description": "Peer-to-peer shift swap that keeps managers out of the firefighting loop.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Staff: open Staffing → Shift Market",     "body": "See your own upcoming shifts and any open cover requests."},
            {"title": "Post a shift you can't cover",             "body": "One tap. Add an optional reason (sickness, personal). Goes to the team feed."},
            {"title": "Teammates pick it up",                     "body": "Anyone qualified for the role can claim it. First-come-first-served."},
            {"title": "Manager rubber-stamps",                    "body": "Manager sees the swap in their queue. One-click approve or decline."},
            {"title": "Rota auto-updates",                         "body": "Once approved, both staff are notified and the rota reflects the swap immediately."},
        ],
        "tips": [
            "Most swaps go through without manager intervention — only edge cases need approval.",
            "Pair with the Rules tab to set 'requires manager approval over X swaps/month' if you want guardrails.",
        ],
        "mistakes": [
            "Don't disable the marketplace — managers spend ~3hrs/week firefighting cover otherwise.",
        ],
        "related": ["staffing-overview"],
    },
    {
        "id": "admin-security-checks",
        "category": "admin",
        "module": "admin",
        "title": "Master Admin → Trust & Reliability → Security Checks",
        "description": "Curated build-hardening timeline + live audit feed — for auditors, pen-testers and customer security questionnaires.",
        "read_minutes": 3,
        "roles": ["master_admin"],
        "popular": True,
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Master Admin → Trust & Reliability",      "body": "Two top tabs: Live platform health (default) and Security Checks."},
            {"title": "Click 'Security checks'",                  "body": "Shows 22+ controls grouped by category (auth, data, ops, scale, code, external review)."},
            {"title": "Filter by category",                       "body": "Pills at top: Authentication, Data protection, Operations, Scale, Code quality, External review."},
            {"title": "Live audit-events feed",                   "body": "Bottom panel: real runtime events from the security_audit_log (supplier tokens issued, MFA challenges, password resets, role changes)."},
            {"title": "Download PDF",                              "body": "Top-right button. Branded multi-page PDF — perfect attachment for RFPs, pen-test scopes, customer security questionnaires."},
        ],
        "tips": [
            "Visible to BOTH GymAxis and Pulse Fitness master admins — same backbone, both brands.",
            "The PDF is generated live from the codebase, not a static document. It can never drift from reality.",
        ],
        "mistakes": [
            "Don't paste the live audit feed into a public deck — it contains real org IDs.",
        ],
        "related": ["admin-security-mfa"],
    },
    {
        "id": "admin-domain-cutover",
        "category": "admin",
        "module": "admin",
        "title": "Domain cutover — gymaxisai.com + pulsefitness.ai",
        "description": "Step-by-step playbook for moving from preview to your custom production domains.",
        "read_minutes": 5,
        "roles": ["master_admin"],
        "updated_at": "2026-04-28",
        "steps": [
            {"title": "Configure DNS",                            "body": "A records on the apex + CNAMEs on `app` for both domains, pointing at Emergent's prod ingress."},
            {"title": "TLS auto-provisions",                      "body": "Let's Encrypt cert provisions in ~5 min once DNS resolves. Verify with curl -I."},
            {"title": "Set backend env vars",                     "body": "ENVIRONMENT=production, FRONTEND_URL, BRAND_URL_GYMAXIS, BRAND_URL_PULSE, CORS_ORIGINS (all six brand origins)."},
            {"title": "Set frontend env var",                     "body": "REACT_APP_BACKEND_URL points at the API origin. Both brands hit the same API; the brand split is on the SPA-serving domain."},
            {"title": "Trigger redeploy",                          "body": "Emergent → Deployments → Redeploy. Backend picks up CORS + brand env. Frontend rebuilds with new API URL."},
            {"title": "Run data migration",                        "body": "cd backend && python scripts/fix_iteration204_data.py — one-shot, idempotent."},
            {"title": "Smoke test",                                 "body": "Login on both domains, trigger a supplier-case email, confirm View & Reply links use the brand-correct domain."},
        ],
        "tips": [
            "Full runbook lives at memory/DOMAIN_CUTOVER_RUNBOOK.md — TTL 300 during cutover so DNS mistakes propagate fast.",
            "Both domains can run in parallel during the cutover — DNS lets you split traffic by hostname.",
        ],
        "mistakes": [
            "Don't forget CORS_ORIGINS — without it, Pulse customers calling the GymAxis API get a 403.",
            "Don't run the data migration twice — wait, it IS idempotent. Run it as many times as you want.",
        ],
        "related": ["admin-security-checks"],
    },

    # ── Iter 215m: Help-guide content sprint (P1) ────────────────────
    # Adds ~30 guides covering the workflows the AI Orb most commonly
    # gets asked about — resolving faults, freezing memberships,
    # cancelling members, rota publishing, payroll exports, billing,
    # integrations, etc. Same schema as above; guide ids are scoped by
    # category prefix so the search synonym map keeps working.

    # CRM
    {
        "id": "crm-mode-switch",
        "category": "crm", "module": "crm",
        "title": "CRM modes — Leisure vs Business",
        "description": "Leisure CRM auto-bundles with Memberships; Business CRM is a paid add-on. Switch between them.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Open the CRM module",                     "body": "Navbar → CRM. The mode pill (top-right of the CRM toolbar) shows your current mode."},
            {"title": "Leisure mode",                             "body": "Auto-enabled when Memberships is on. Optimised for member journeys: leads → trial → joiner → active member."},
            {"title": "Business mode",                            "body": "Optimised for B2B sales pipelines: companies, deals, contracts, multi-touch attribution."},
            {"title": "Switching",                                "body": "Use the mode pill to switch. The dataset is shared; the views and properties surface different fields."},
            {"title": "Upgrade to Business",                      "body": "If your org doesn't have Business yet, the pill opens an upgrade screen. Master Admin can also flip the flag from Org Billing."},
        ],
        "tips": ["Leisure → Business is non-destructive — your Leisure deals stay visible.", "Master admins always see both modes."],
        "mistakes": ["Don't ask Pulse Leisure customers to set up Business pipelines — it confuses the funnel."],
        "related": ["crm-add-contact", "crm-pipeline-first-deal"],
    },
    {
        "id": "crm-bulk-import",
        "category": "crm", "module": "crm",
        "title": "Bulk-import contacts from CSV",
        "description": "Drop in a CSV (max 50k rows) and map columns to GymAxis fields. De-dupes on email.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "CRM → Contacts → Import",                 "body": "Top-right 'Import' button. Drag-drop your CSV."},
            {"title": "Map columns",                              "body": "GymAxis suggests mappings; tweak any that look wrong. Required: email."},
            {"title": "Review duplicates",                        "body": "Existing contacts (matched on email) are flagged — choose 'skip' or 'update'."},
            {"title": "Run the import",                           "body": "Goes through in the background; you'll get a summary email when it's done."},
        ],
        "tips": ["Add a `source` column to track where each batch came from.", "UTF-8 only — re-save your CSV as UTF-8 if the import errors on accents."],
        "mistakes": ["Don't import the same CSV twice on the same day — use the duplicate report instead."],
        "related": ["crm-add-contact"],
    },
    {
        "id": "crm-custom-properties",
        "category": "crm", "module": "crm",
        "title": "Custom properties — extend the CRM schema",
        "description": "Add your own fields (e.g., 'Joining fee paid?' or 'Referral code') without a developer.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Master Admin → Custom Properties",        "body": "Available to org owners + master admins. Existing properties listed; click 'New'."},
            {"title": "Pick a type",                              "body": "Text, Number, Dropdown, Date, Boolean. Dropdowns let you preset choices."},
            {"title": "Pick the object",                          "body": "Contact, Company, Deal, or Membership. The field appears on that record's detail view."},
            {"title": "Save → instantly available",               "body": "All users see the new field on the next page load."},
        ],
        "tips": ["Group similar properties into a 'section' to keep the detail view tidy.", "Hide rarely-used properties via the visibility toggle on the property row."],
        "mistakes": ["Don't make a property required after the fact — existing records will fail validation."],
        "related": ["crm-add-contact"],
    },
    {
        "id": "crm-pipeline-stages",
        "category": "crm", "module": "crm",
        "title": "Customise pipeline stages",
        "description": "Add, rename, reorder or merge stages. Per-pipeline, per-org.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "CRM → Deals → Manage pipeline",           "body": "Cog icon next to the pipeline switcher."},
            {"title": "Drag to reorder",                          "body": "Hold a stage card and drop it into the new position."},
            {"title": "Edit a stage",                             "body": "Click the pencil — change name, win/lose treatment, automation hooks."},
            {"title": "Add a stage",                              "body": "'+ Add stage' at the bottom. Default probability auto-suggested."},
        ],
        "tips": ["Keep total stages to 5–7 — research shows longer pipelines reduce close rates by 12%."],
        "mistakes": ["Don't delete a stage with open deals — move them first or you'll lose forecast accuracy."],
        "related": ["crm-pipeline-first-deal"],
    },
    {
        "id": "crm-activity-timeline",
        "category": "crm", "module": "crm",
        "title": "The activity timeline on every record",
        "description": "Every email, call, note, status change — auto-aggregated into one timeline per contact / deal / company.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Open any contact / deal / company",        "body": "The right-hand panel is the activity timeline."},
            {"title": "Filter by type",                           "body": "Pills: Emails · Calls · Meetings · Notes · System."},
            {"title": "Add a note",                               "body": "'+ Add note' at the top. Notes are markdown-aware; they sync to the linked deal as well."},
            {"title": "Auto-logged events",                       "body": "Form submissions, payment receipts, plan changes, fault links — all log themselves automatically."},
        ],
        "tips": ["@mention a teammate in a note to ping them — they get a notification."],
        "mistakes": ["Don't paste long PII into notes (passport numbers, etc.) — use the Documents tab instead, which is encrypted."],
        "related": ["crm-add-contact"],
    },

    # SERVICE & FAULTS
    {
        "id": "service-resolve-fault",
        "category": "service", "module": "operations",
        "title": "Resolve a fault — and what auto-resolves",
        "description": "Mark a fault complete, attach a service report, or let GymAxis auto-close on supplier confirmation.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Operations → Faults → open the fault",    "body": "Click any fault row to expand the detail drawer."},
            {"title": "Mark resolved",                            "body": "Bottom-right green button. Add a resolution note (required) and optional photo of the fix."},
            {"title": "Auto-resolve on supplier confirmation",   "body": "If a supplier marks the case complete via their reply email, the fault auto-closes and the equipment status flips back to In Service."},
            {"title": "Re-open if needed",                        "body": "Resolved faults are read-only for 24h, then 'Re-open' becomes available — the new instance links to the old one."},
        ],
        "tips": ["Photos of the fix become part of the asset's service history — useful for warranty disputes."],
        "mistakes": ["Don't resolve a fault without a note — auditors and your future self will thank you."],
        "related": ["service-log-fault", "service-triage-ai"],
    },
    {
        "id": "service-supplier-management",
        "category": "service", "module": "operations",
        "title": "Manage suppliers — invite, link, and disable",
        "description": "Suppliers handle their own cases via a magic-link portal. Set who's allowed to log faults to which supplier.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Operations → Suppliers",                   "body": "Lists every linked supplier with case count, average response time, and status pill."},
            {"title": "Invite a new supplier",                    "body": "'Invite supplier' top-right. Enter contact email; they get a magic link to set up their portal account."},
            {"title": "Link to manufacturer brands",              "body": "On the supplier detail page, link the brands they cover. New faults on those brands auto-route to them."},
            {"title": "Disable a supplier",                        "body": "If they go bust or you switch — pause them. Existing open cases finish; no new ones are routed to them."},
        ],
        "tips": ["The Supplier portal is white-labeled — they see your brand, not GymAxis."],
        "mistakes": ["Don't delete a supplier with a long case history — disable instead, so the audit trail survives."],
        "related": ["service-log-fault"],
    },
    {
        "id": "service-equipment-photos",
        "category": "service", "module": "operations",
        "title": "Upload equipment photos and spec sheets",
        "description": "Per-machine photos override catalogue images. Useful for older or custom kit.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Operations → Equipment → open a machine", "body": "Detail drawer has a 'Photos' tab."},
            {"title": "Drop in up to 6 photos",                   "body": "5MB each, JPEG/PNG/WebP. The first photo becomes the cover image everywhere."},
            {"title": "Spec sheets (PDF)",                         "body": "Same panel — drop in user manuals, electrical specs, parts diagrams."},
            {"title": "Catalogue fallback",                        "body": "If you don't upload anything, GymAxis falls back to the manufacturer image catalogue (matched by brand + model)."},
        ],
        "tips": ["Photograph the serial-plate too — saves a trip when a supplier asks for it."],
        "mistakes": ["Don't upload photos with members' faces — privacy. Frame the equipment only."],
        "related": ["service-log-fault"],
    },
    {
        "id": "service-qr-codes",
        "category": "service", "module": "operations",
        "title": "Print equipment QR codes for one-tap fault logging",
        "description": "Stick a QR code on every machine — staff scan, snap, log a fault in <30 seconds.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Operations → Equipment → Bulk → 'Print QR'", "body": "Generates an A4 sheet of QR labels (16 per page, peelable)."},
            {"title": "Stick on the equipment",                    "body": "Top-right of the machine, eye level. Staff and members can both use them."},
            {"title": "Scan with any phone camera",                "body": "Goes to the public fault-log page (no login needed) — pre-fills the equipment, asks for description + photo."},
            {"title": "Logged fault appears in your dashboard",   "body": "Auto-linked to the right asset; AI triage runs in <30 seconds."},
        ],
        "tips": ["Pair with the Gym Floor kiosk to capture which staff member logged it."],
        "mistakes": ["Don't reprint codes after a serial change — the QR encodes the equipment ID, not the serial."],
        "related": ["service-log-fault", "staff-gym-floor-login"],
    },
    {
        "id": "service-warranty-tracking",
        "category": "service", "module": "operations",
        "title": "Track warranties and warranty expiry alerts",
        "description": "GymAxis nags you 30 days before warranty expiry so you can make a final claim.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Equipment detail → Warranty tab",         "body": "Set start date, length (months), and supplier."},
            {"title": "30-day expiry email",                      "body": "GymAxis emails the owner 30 days before expiry. The fault-log dialog shows a warranty banner if the asset is still covered."},
            {"title": "Bulk-set warranties",                      "body": "From the Equipment list, select multiple → Bulk → 'Set warranty' — useful after a fleet purchase."},
        ],
        "tips": ["Check the supplier's terms — some warranties only cover parts, not labour."],
        "mistakes": ["Don't ignore the 30-day email — submit a final inspection request before expiry to maximise claim window."],
        "related": ["service-log-fault"],
    },
    {
        "id": "service-capex",
        "category": "service", "module": "operations",
        "title": "CAPEX scoring — when does a repair become a replacement?",
        "description": "Auto-score every fault against a configurable threshold. >£X repair = replace recommendation.",
        "read_minutes": 3,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Master Admin → Finance → CAPEX",          "body": "Set thresholds per equipment category (cardio, strength, free weights)."},
            {"title": "Auto-scoring on each fault",               "body": "Quote received → if quote ≥ threshold AND machine age ≥ X years, GymAxis flags 'Consider replacing'."},
            {"title": "CAPEX dashboard",                           "body": "Operations → Reports → CAPEX. Lists candidates by score; one-click 'Get replacement quote'."},
            {"title": "Approval workflow",                         "body": "Optional: route flagged cases to the owner for approval before the supplier proceeds."},
        ],
        "tips": ["Review thresholds annually — equipment values + supplier rates drift."],
        "mistakes": ["Don't set a threshold of £0 — every fault becomes a CAPEX recommendation, which defeats the point."],
        "related": ["reporting-weekly-digest"],
    },

    # MEMBERSHIPS
    {
        "id": "mbr-freeze-membership",
        "category": "memberships", "module": "memberships",
        "title": "Freeze a membership — holiday, injury, suspension",
        "description": "Pause billing for 1–12 weeks. Member retains access on resume; no churn impact.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Memberships → Members → open the member", "body": "Detail drawer."},
            {"title": "Click 'Freeze'",                           "body": "Pick a duration (1–12 weeks) and a reason (Holiday / Injury / Other)."},
            {"title": "Billing pauses immediately",               "body": "Stripe subscription paused until the resume date. Member sees a 'Frozen' banner on their portal."},
            {"title": "Auto-resume",                               "body": "On resume date, billing restarts and access is re-enabled. No staff action needed."},
        ],
        "tips": ["Members can self-serve a freeze in their portal if you toggle it on (Settings → Member self-service)."],
        "mistakes": ["Don't freeze annual plans without pro-rating — set a 'Pause discount' policy instead."],
        "related": ["mbr-cancel-membership"],
    },
    {
        "id": "mbr-cancel-membership",
        "category": "memberships", "module": "memberships",
        "title": "Cancel a membership (and retain the contact)",
        "description": "End the plan but keep them in CRM for win-back. Sets the right Stripe cancel flags.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Memberships → Members → open the member", "body": "Detail drawer."},
            {"title": "Click 'Cancel plan'",                      "body": "Pick a reason — required. The reasons feed your churn reporting."},
            {"title": "Cancel timing",                             "body": "Choose 'End of period' (default) or 'Immediately' (rare — refunds the prorate)."},
            {"title": "Auto-enrolled in winback",                 "body": "Cancelled members are auto-bucketed into the Winback CRM segment for follow-up campaigns."},
        ],
        "tips": ["Surface the 'Pause' option in the cancel dialog — a third of cancellers will freeze instead."],
        "mistakes": ["Don't delete the member record on cancel — you'll lose churn analytics + winback ability."],
        "related": ["mbr-freeze-membership", "mkt-first-campaign"],
    },
    {
        "id": "mbr-payment-recovery",
        "category": "memberships", "module": "memberships",
        "title": "Payment recovery — automated dunning",
        "description": "Failed Stripe charges? GymAxis retries on day 1, 3, 7 and emails the member with a self-serve update link.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Failed payment detected",                  "body": "Stripe webhook fires → GymAxis logs the failure → member's 'Payment status' badge turns amber."},
            {"title": "Day 1 — soft email",                       "body": "Friendly reminder with one-click update link."},
            {"title": "Day 3 — firmer email + retry",             "body": "Stripe retries the card; if still failing, email asks them to update payment method."},
            {"title": "Day 7 — final notice",                      "body": "Suspends access. Member retains the plan for 30 more days for self-recovery; cancels otherwise."},
        ],
        "tips": ["Master Admin → Collections shows real-time aging buckets across all orgs.", "Customise the dunning copy per brand in Master Admin → Emails."],
        "mistakes": ["Don't disable dunning to be 'nice' — recovered payments avg 18% of would-be churn."],
        "related": ["mbr-cancel-membership", "int-stripe-connect"],
    },
    {
        "id": "mbr-instructor-portal",
        "category": "memberships", "module": "memberships",
        "title": "Instructor portal — who teaches, who gets paid",
        "description": "Instructors log in to /instructor and see their schedule, attendance, and pay.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Memberships → Instructors → 'Invite'",    "body": "Send a magic link. Instructor sets their own password on first login."},
            {"title": "Set rate per class",                       "body": "Per-instructor rate (default) or per-class override. Used by the payroll export."},
            {"title": "Instructor logs in at /instructor",        "body": "Tabs: Today · Week · Pay. They see only their own classes."},
            {"title": "Auto-attendance from member check-ins",   "body": "When members tap their TOTP pass at the door, attendance updates the instructor's class card live."},
        ],
        "tips": ["The Pay tab shows the running monthly total — instructors love this transparency."],
        "mistakes": ["Don't share an instructor account between two people — attendance + pay get tangled."],
        "related": ["mbr-first-class"],
    },
    {
        "id": "mbr-totp-pass",
        "category": "memberships", "module": "memberships",
        "title": "Member TOTP pass — anti-fraud check-in",
        "description": "Rotating 30-second QR code on the member's phone, scanned at the door. Replaces wristbands.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Member opens their portal → 'Pass'",      "body": "30-second TOTP QR. Auto-rotates so screenshots become useless."},
            {"title": "Reception scans with any tablet",          "body": "Verifies the TOTP server-side; green check or red cross in <500ms."},
            {"title": "Failed scans logged",                      "body": "5 failed scans in 5 minutes auto-flag the account for review."},
            {"title": "Class entry too",                           "body": "Same QR works at studio doors; auto-marks attendance for the class they're booked into."},
        ],
        "tips": ["Pair with a £20 access controller (any TOTP-capable reader) — no proprietary hardware needed."],
        "mistakes": ["Don't fall back to 'show your face to reception' as a hack — defeats the whole anti-fraud point."],
        "related": ["mbr-onboard-first"],
    },

    # MARKETING
    {
        "id": "mkt-form-builder",
        "category": "marketing", "module": "marketing",
        "title": "Form builder — capture leads from your website",
        "description": "Drag-drop form builder. Embed via iframe or paste a public link into Instagram bio.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Marketing → Forms → 'New form'",          "body": "Pick a template (Class trial / Lead magnet / PT enquiry / Generic) or start blank."},
            {"title": "Drag fields",                              "body": "Text, email, phone, dropdown, file upload, hidden UTM. Auto-saved every 5 seconds."},
            {"title": "Set the destination",                       "body": "Submissions become CRM contacts in the segment of your choice. Optional: trigger a campaign on submit."},
            {"title": "Embed",                                     "body": "iframe code, public link, or QR code — print on flyers."},
        ],
        "tips": ["Hide UTM source / medium / campaign as form fields populated by URL — auto-attribution for free."],
        "mistakes": ["Don't ask for too much — every required field drops conversion by ~7%."],
        "related": ["mkt-audiences-101"],
    },
    {
        "id": "mkt-deliverability",
        "category": "marketing", "module": "marketing",
        "title": "Email deliverability — domain warm-up checklist",
        "description": "Before blasting your full list: verify SPF/DKIM, warm the domain over 7 days, prune disengaged contacts.",
        "read_minutes": 4,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Verify SPF + DKIM",                        "body": "Master Admin → Integration Health → Resend row should be green. If not, set the DNS records Resend asks for."},
            {"title": "Warm-up week",                             "body": "Days 1–2: 100 emails. Days 3–4: 500. Days 5–7: ramp to 2k. Helps ISPs trust your sending pattern."},
            {"title": "Prune disengaged",                          "body": "Audience → 'Disengaged 90d' segment → remove or move to a low-frequency campaign."},
            {"title": "Watch the bounce rate",                     "body": "<2% is healthy. >5% = stop and investigate before sending more."},
        ],
        "tips": ["Use the 'Soft warm-up' template — Marketing → Templates → 'Welcome ramp'."],
        "mistakes": ["Don't blast 50k cold emails on day 1 from a brand-new domain — inbox providers will junk you for months."],
        "related": ["mkt-first-campaign", "int-resend"],
    },
    {
        "id": "mkt-ab-testing",
        "category": "marketing", "module": "marketing",
        "title": "A/B test a subject line in 3 clicks",
        "description": "Send variant A and variant B to 10% each, then auto-send the winner to the remaining 80%.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Marketing → Campaigns → New",             "body": "Compose your campaign as normal."},
            {"title": "Toggle 'A/B test subject'",                "body": "Section appears: enter the second variant. GymAxis defaults to a 4-hour decision window."},
            {"title": "Pick the winning metric",                  "body": "Open rate (default) or click rate. Open rate works for short campaigns; click rate is more reliable but slower."},
            {"title": "Schedule + go",                             "body": "Variants send to 10% each at the start time. Winner sends to remaining 80% after the decision window."},
        ],
        "tips": ["Test ONE thing at a time — subject OR sender name OR send-time, not all three."],
        "mistakes": ["Don't A/B test on lists smaller than 2,000 — the winner won't be statistically significant."],
        "related": ["mkt-first-campaign"],
    },
    {
        "id": "mkt-segments",
        "category": "marketing", "module": "marketing",
        "title": "Smart segments — auto-updating CRM groups",
        "description": "Define rules ('Joined in last 30d AND no class booked'). Segment auto-updates as data changes.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Marketing → Audiences → New segment",     "body": "Pick a base set (All members, All contacts, Active leads)."},
            {"title": "Add filter rules",                          "body": "Dropdowns: field · operator · value. AND/OR groupings."},
            {"title": "Preview the count",                         "body": "Live count updates as you add rules — ensures the segment isn't too narrow."},
            {"title": "Save → use in campaigns",                   "body": "Segment becomes a target choice in the campaign composer."},
        ],
        "tips": ["The 'Inactive 30d' segment is gold for win-back — set up a recurring monthly campaign to it."],
        "mistakes": ["Don't bury cancelled members in a generic 'All' segment — they react badly to upsell emails."],
        "related": ["mkt-audiences-101"],
    },

    # STAFFING
    {
        "id": "staffing-publish-rota",
        "category": "staffing", "module": "operations",
        "title": "Publish the rota — and what staff see",
        "description": "Drag-drop the week, hit Publish. Staff get push notifications + an email with their shifts.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Staffing → Rota → pick the week",         "body": "Drag staff onto shifts. Hold Alt-drag to copy a shift to another day."},
            {"title": "Compliance flags",                          "body": "Red dot on a shift = AI flagged a rule violation (under-rest, over-cap, missing certification). Hover for details."},
            {"title": "Hit 'Publish'",                              "body": "Sends notifications. The published version is locked; further edits create a 'pending changes' diff."},
            {"title": "Approve change requests",                  "body": "Staff can request swaps (Marketplace) or time-off — approve in one click."},
        ],
        "tips": ["Publish at the same time each week — staff plan their lives around it."],
        "mistakes": ["Don't publish a rota with red flags — they're either compliance breaches (illegal) or burnout signals (expensive)."],
        "related": ["staffing-overview", "staffing-time-off"],
    },
    {
        "id": "staffing-time-off",
        "category": "staffing", "module": "operations",
        "title": "Time-off requests + approvals",
        "description": "Staff request, managers approve. Auto-deducts from holiday allowance.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Staff: Staffing → Time Off → 'Request'",  "body": "Pick dates + reason. Auto-submitted to manager."},
            {"title": "Manager: 'Time Off' inbox",                "body": "One-click approve or decline with note. Push notif to the requester."},
            {"title": "Auto-deducted from allowance",             "body": "Holiday allowance set per staff (Staff tab → contract). Approved leave decrements automatically."},
            {"title": "Auto-blocks rota",                          "body": "Approved leave blocks that staff member from being assigned a shift on those days."},
        ],
        "tips": ["Set an org-wide cap ('Max 2 staff off per day') — Staffing → Rules."],
        "mistakes": ["Don't let staff manually edit their own allowance — they will, generously."],
        "related": ["staffing-publish-rota"],
    },
    {
        "id": "staffing-payroll-export",
        "category": "staffing", "module": "operations",
        "title": "Monthly payroll export",
        "description": "One CSV with hours worked, overtime, holiday pay, and totals — drop into Sage Payroll or Xero.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Staffing → Payroll",                       "body": "Pick the pay period (default: last calendar month)."},
            {"title": "Review",                                    "body": "Per-staff row: regular hours, overtime, holiday, sickness, total pay."},
            {"title": "Click 'Export CSV'",                        "body": "Downloads a payroll-ready CSV. Bank-friendly columns (sort code, account number) are pulled from each staff profile."},
            {"title": "Import into Sage Payroll / Xero",          "body": "Both tools accept the standard column layout — no remapping needed."},
        ],
        "tips": ["Run a draft a week before payday and email staff their estimate — catches disputes early."],
        "mistakes": ["Don't fix a dispute by editing the CSV — fix it in GymAxis (corrects future runs too) and re-export."],
        "related": ["staffing-overview"],
    },
    {
        "id": "staffing-live-floor",
        "category": "staffing", "module": "operations",
        "title": "Live Floor — wall-mounted shift dashboard",
        "description": "Fullscreen dashboard for staff areas. Shows who's on, handover notes, and emerging issues.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Staffing → Live Floor",                    "body": "Press F11 / 'Make fullscreen' for the wall-mount layout."},
            {"title": "Who's on right now",                        "body": "Tiles per staff member: name, role, end time. Auto-rotates the tile order so no one's always at the bottom."},
            {"title": "Handover diary",                             "body": "Outgoing shift writes a note; incoming reads. AI moderates for offensive content."},
            {"title": "Emerging issues",                            "body": "AI Insights surfaces patterns: 'Sat AM under-staffed 4 weeks running'. Acknowledge or route to manager."},
        ],
        "tips": ["Don't run on a public-facing screen — staff names + shift hours are visible."],
        "mistakes": ["Don't replace the handover diary with a WhatsApp group — you lose the audit trail and AI moderation."],
        "related": ["staffing-overview"],
    },

    # ADMIN
    {
        "id": "admin-org-billing",
        "category": "admin", "module": "admin",
        "title": "Org Billing — see and edit a customer's plan",
        "description": "Master Admin only. View their subscription, modules, balance, and invoice history in one place.",
        "read_minutes": 3,
        "roles": ["master_admin"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Master Admin → Finance → Org Billing",    "body": "Search for the org. Detail page shows plan, modules toggled on, MRR, and balance."},
            {"title": "Toggle modules",                           "body": "Each module has a switch. Toggling on adds the line to their next invoice; toggling off reverts at end of period."},
            {"title": "Manual invoice",                            "body": "'Issue invoice' button — for one-off fees (setup, training). Sent via Stripe."},
            {"title": "BACS payment recording",                   "body": "If they paid by bank transfer, mark the invoice paid manually. Triggers a receipt email."},
        ],
        "tips": ["Always issue invoices in the org's local currency — exchange rate at issue time is locked."],
        "mistakes": ["Don't toggle off a module without notifying the customer — their team loses access mid-day."],
        "related": ["admin-invite-user"],
    },
    {
        "id": "admin-integration-health",
        "category": "admin", "module": "admin",
        "title": "Master Admin → Integration Health",
        "description": "Live status of every third-party service: DB, Stripe, Resend, Storage, LLM. Master-admin only.",
        "read_minutes": 2,
        "roles": ["master_admin"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Master Admin → Security → Integration Health", "body": "Sub-tab under Security."},
            {"title": "Summary strip",                             "body": "4 counters: Healthy / Degraded / Down / Not configured. Total count below."},
            {"title": "Per-row status",                            "body": "Each integration: green/amber/red dot + latency + human message + expand for details."},
            {"title": "Re-run a single check",                     "body": "Refresh icon on each row — useful after fixing a DNS issue or rotating an API key."},
            {"title": "What customers see",                         "body": "Nothing. This is a developer/HQ tool. Customer-facing emails NEVER show 'Resend domain not verified'-style errors."},
        ],
        "tips": ["Run all checks before a customer call — answers 'is X working?' before they ask."],
        "mistakes": ["Don't paste this dashboard into a customer chat — it leaks internal account IDs."],
        "related": ["admin-security-checks", "int-resend"],
    },
    {
        "id": "admin-data-wipe",
        "category": "admin", "module": "admin",
        "title": "Reset an org's data (test environments only)",
        "description": "Master Admin → Data Wipe. Surgical reset — keeps the org, deletes their data.",
        "read_minutes": 3,
        "roles": ["master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Master Admin → Database → Data Wipe",     "body": "Open the org you want to reset; select what to wipe (faults / equipment / members / all)."},
            {"title": "Confirm with the org name",                "body": "Typed-confirmation prevents accidental wipes."},
            {"title": "Run",                                       "body": "Background job; you'll get a Slack/email when complete. Restore: not possible — wipe is destructive."},
        ],
        "tips": ["Use 'Reset to baseline' for demo orgs — re-seeds them with the canonical demo dataset."],
        "mistakes": ["Don't run on production orgs without an explicit ticket from the customer + 1-week reminder window."],
        "related": ["admin-security-checks"],
    },
    {
        "id": "admin-password-reset",
        "category": "admin", "module": "admin",
        "title": "Reset a user's password",
        "description": "Issue a 7-day temp password or send a self-serve reset link.",
        "read_minutes": 1,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Admin → Users → click the user",          "body": "Detail panel."},
            {"title": "'Reset password'",                          "body": "Choose: send self-serve link (default) OR issue temp password (you read it out, they change it on first login)."},
            {"title": "User is logged out everywhere",            "body": "All sessions invalidated. They re-authenticate with the new credential."},
        ],
        "tips": ["Temp passwords are 7-day TTL and `must_change_password=true` — auto-redirected to /change-password on first login."],
        "mistakes": ["Don't email a temp password — read it out over a known-secure channel (verified phone)."],
        "related": ["admin-invite-user", "admin-security-mfa"],
    },

    # INTEGRATIONS
    {
        "id": "int-resend",
        "category": "integrations", "module": "admin",
        "title": "Resend — verify your sending domain",
        "description": "Without DKIM/SPF, your emails land in spam. 5-minute fix.",
        "read_minutes": 3,
        "roles": ["owner", "master_admin"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Master Admin → Integration Health → Resend", "body": "If amber/red, click expand for the failure reason."},
            {"title": "Add the DNS records",                       "body": "Resend dashboard shows the exact records (4–6 entries: TXT, MX, CNAME)."},
            {"title": "Wait for propagation",                       "body": "Usually 5–60 minutes. Click 'Re-run' on Integration Health to recheck."},
            {"title": "Test send",                                  "body": "Marketing → Campaigns → 'Send test'. Verify deliverability with mail-tester.com — aim for 9/10+."},
        ],
        "tips": ["Verify on a subdomain (e.g. 'send.yourdomain.com') so the apex stays free for transactional senders."],
        "mistakes": ["Don't use a generic ESP shared sending IP — your reputation gets tarred by every other tenant."],
        "related": ["admin-integration-health", "mkt-deliverability"],
    },
    {
        "id": "int-meta-socials",
        "category": "integrations", "module": "marketing",
        "title": "Connect Meta (Instagram + Facebook) for social posting",
        "description": "Schedule and post from GymAxis to your Meta-owned channels.",
        "read_minutes": 3,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Marketing → Channels → Meta → 'Connect'", "body": "OAuth flow with Facebook Business — pick the page + IG account."},
            {"title": "Permissions",                              "body": "GymAxis requests the minimum scopes: pages_manage_posts, instagram_content_publish, pages_read_engagement."},
            {"title": "Schedule from the AI Director",            "body": "Marketing → AI Director → generate post + image → 'Schedule on Meta' — single click, multi-channel."},
            {"title": "Comment + DM aggregation (later)",         "body": "Roadmap: pull comments + DMs into a unified inbox. Not yet shipped."},
        ],
        "tips": ["Keep the connected user a service account, not the owner — Meta tokens last longer and survive personnel changes."],
        "mistakes": ["Don't hard-link your personal IG — token revoked the moment you log out of FB."],
        "related": ["mkt-ai-director"],
    },
    {
        "id": "int-orbit4",
        "category": "integrations", "module": "admin",
        "title": "Orbit 4 — sync member access and scanners",
        "description": "Two-way sync between GymAxis members and Orbit 4 access control.",
        "read_minutes": 3,
        "roles": ["owner", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Master Admin → Orbit 4",                   "body": "Click 'Connect' — paste your Orbit 4 site key + API token."},
            {"title": "Map sites + access groups",                "body": "Each GymAxis site maps to one Orbit 4 site; member plans map to access groups."},
            {"title": "Sync test",                                  "body": "'Run dry-run sync' shows what would change. Review then 'Apply'."},
            {"title": "Real-time updates",                          "body": "After connection, plan changes (freeze, cancel, upgrade) reflect in Orbit 4 within ~30 seconds."},
        ],
        "tips": ["Run dry-run first — protects against accidental access removal during initial mapping."],
        "mistakes": ["Don't disconnect without a 'Pause sync' first — open journeys (e.g., a member mid-class) get terminated."],
        "related": ["int-sicon"],
    },
    {
        "id": "int-twilio-sms",
        "category": "integrations", "module": "marketing",
        "title": "SMS via Twilio (currently MOCKED)",
        "description": "Marketing → Channels → SMS. Real Twilio integration is on the roadmap (Q2 2026).",
        "read_minutes": 1,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Roadmap status",                           "body": "SMS sending currently logs to a dev table only. Real Twilio integration ships in P2."},
            {"title": "What works today",                          "body": "Compose flow + segment targeting works end-to-end. The send button stubs the actual SMS — you'll see it in the audit log."},
            {"title": "Want it accelerated?",                      "body": "Master Admin → Tasks → 'Request feature' bumps priority based on customer demand."},
        ],
        "tips": ["For urgent SMS needs today, use the manual export — Marketing → Audiences → 'Export phones' → drop into your existing SMS tool."],
        "mistakes": ["Don't tell members 'we'll text you' until SMS is live — set expectations correctly."],
        "related": ["mkt-first-campaign"],
    },

    # AI
    {
        "id": "ai-orb-page-context",
        "category": "ai", "module": "operations",
        "title": "Ask Pulse (AI Orb) — knows where you are",
        "description": "The cyan orb (bottom-right) reads your current screen so 'how do I do this?' resolves to the right answer.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Click the orb (bottom-right of every page)", "body": "Drawer opens. Asks 'what would you like to do?'."},
            {"title": "It knows your current screen",             "body": "Pathname, active tab, selected record — all auto-attached. You don't have to repeat 'I'm on the faults page'."},
            {"title": "Cite-able help guides",                     "body": "Answers reference the Help Centre when relevant — click any title to read the full guide."},
            {"title": "One-click actions",                          "body": "When intent is clear, the response includes a button that does the thing (e.g. 'Resolve fault #1234'). Always asks confirmation first."},
        ],
        "tips": ["Phrase questions naturally — 'how do I freeze Emma's plan?' works better than 'membership_freeze.'"],
        "mistakes": ["Don't paste sensitive data (passwords, full card numbers) — even with masking, bad habit."],
        "related": ["ai-assistant", "ai-fault-triage"],
    },
    {
        "id": "ai-image-generation",
        "category": "ai", "module": "marketing",
        "title": "AI image generation (Nano Banana)",
        "description": "Generate on-brand campaign visuals from a text prompt. ~3 seconds per image.",
        "read_minutes": 2,
        "roles": ["owner", "manager"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Marketing → AI Director → 'New visual'",  "body": "Prompt box. Brand kit auto-applied (logo, colour palette, voice)."},
            {"title": "Generate variants",                         "body": "4 variants per prompt. Hover to enlarge; click to copy / download / push to a campaign."},
            {"title": "Iterate",                                   "body": "Right-click a variant → 'Use as base' → tweak the prompt → re-generate. Faster than starting fresh."},
            {"title": "Token cost",                                "body": "Each generation uses ~£0.01 of credit. Master Admin → AI usage tracks burn rate."},
        ],
        "tips": ["Generate at 1920×1080 — works for IG, Twitter, ad tiles, and your own website hero."],
        "mistakes": ["Don't generate photorealistic faces — Nano Banana sometimes hallucinates wrong fingers/teeth. Stick to gym scenes, equipment, abstract."],
        "related": ["mkt-ai-director", "mkt-brand-kit"],
    },

    # REPORTING
    {
        "id": "reporting-capex-dashboard",
        "category": "reporting", "module": "operations",
        "title": "CAPEX dashboard — replacement candidates at a glance",
        "description": "Auto-scored list of equipment that costs more to repair than to replace.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Operations → Reports → CAPEX",            "body": "Sorted by score. Each row: machine, age, total repair spend, replacement quote, recommendation."},
            {"title": "One-click 'Get replacement quote'",        "body": "Routes to the linked supplier as a quote-only case (not a fault) — keeps your service desk clean."},
            {"title": "Approval flow",                              "body": "Owners can require sign-off above £X. Without it, managers can act on recommendations directly."},
        ],
        "tips": ["Review monthly — equipment values + supplier rates drift."],
        "mistakes": ["Don't auto-approve — context (member feedback, brand consistency) still matters."],
        "related": ["service-capex"],
    },
    {
        "id": "reporting-financial-ops",
        "category": "reporting", "module": "admin",
        "title": "Financial Ops — reserves, cost centres, top-up",
        "description": "Track operational reserves, allocate to cost centres, set auto-top-up rules.",
        "read_minutes": 3,
        "roles": ["owner", "master_admin"],
        "updated_at": "2026-04-29",
        "steps": [
            {"title": "Master Admin → Finance → Financial Ops",  "body": "Top tabs: Reserves · Cost centres · Auto top-up."},
            {"title": "Set a reserve target",                       "body": "e.g. '90 days OPEX'. Dashboard shows current vs target."},
            {"title": "Allocate transactions to cost centres",   "body": "Bulk-tag from invoices. Used in the P&L report."},
            {"title": "Auto-top-up",                                "body": "When a reserve drops below threshold, GymAxis nudges you (email) or auto-transfers (configurable) from a linked account."},
        ],
        "tips": ["Pair with weekly digest — KPIs land in your inbox without opening the dashboard."],
        "mistakes": ["Don't set the auto-top-up too aggressive — surprise transfers wreck cash flow."],
        "related": ["reporting-weekly-digest"],
    },

    # MEMBERSHIPS (Iter 215p studio additions)
    {
        "id": "mbr-studio-mode",
        "category": "memberships", "module": "memberships",
        "title": "Studio Mode — simplified layout for small studios",
        "description": "One toggle flips the Memberships console into a 5-tab layout optimised for 1-3 person teams (yoga / dance / pilates / wellness).",
        "read_minutes": 2,
        "roles": ["owner", "manager", "master_admin"],
        "popular": True,
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Memberships → top-right 'Studio Mode off' pill",  "body": "Click to flip ON. The tab bar collapses from 14 tabs down to Start · Dashboard · Timetable · Members · Plans · Check-in."},
            {"title": "Quickstart appears on the Start tab",             "body": "First time you enable Studio Mode, a 4-step wizard offers to create a sample drop-in + monthly plan, a weekly class template, and schedule the next 8 weeks."},
            {"title": "Shareable booking URL",                            "body": "Quickstart ends with a QR code + copyable link you can paste into Instagram bio, emails, or flyers. Clients book without an app."},
            {"title": "Switch back any time",                             "body": "Click the pill again to restore the full 14-tab layout. Data isn't touched — it's a pure UI preference."},
        ],
        "tips": [
            "Studio Mode is per-organisation. Different franchisees can choose different layouts.",
            "Running the Quickstart a second time is safe — it skips anything that already exists.",
        ],
        "mistakes": [
            "Don't enable Studio Mode for a 200-member leisure centre — you'll lose the Instructor, Promotions, and Booking Rules tabs you need.",
        ],
        "related": ["mbr-first-plan", "mbr-first-class", "gs-first-login"],
    },
    # GETTING STARTED
    {
        "id": "gs-help-centre-tour",
        "category": "getting-started", "module": "operations",
        "title": "Tour of the Help Centre",
        "description": "60+ guides, AI Orb integration, walkthroughs. How to find the right answer in <30 seconds.",
        "read_minutes": 2,
        "roles": ["owner", "manager", "staff"],
        "updated_at": "2026-04-30",
        "steps": [
            {"title": "Navbar → Help",                            "body": "Or click any 'Learn more' link inline. The Help Centre opens in the same window."},
            {"title": "Search bar",                                "body": "Type a question or keyword. Search expands synonyms — 'log a fault', 'raise a ticket', 'log machine issue' all hit the same guide."},
            {"title": "Categories",                                "body": "11 sections — Getting Started, CRM, Service, Memberships, Marketing, Staffing, Staff, Reporting, Admin, Integrations, AI."},
            {"title": "Walkthroughs",                              "body": "Some guides have a 'Start walkthrough' button — Joyride-powered overlay that points at real UI elements."},
            {"title": "Or just ask the AI Orb",                    "body": "Bottom-right cyan orb. It cites Help Centre guides in its answers."},
        ],
        "tips": ["Bookmark the Help Centre as your team's homepage — drives self-serve and reduces ticket volume."],
        "mistakes": ["Don't ask the AI Orb if a guide already answers it — the orb costs LLM tokens; the guide is free."],
        "related": ["ai-orb-page-context", "gs-first-login"],
    },
]


# ─── Public helpers ──────────────────────────────────────────────────
def guide_by_id(guide_id: str) -> Guide | None:
    for g in GUIDES:
        if g.get("id") == guide_id:
            return g
    return None


def visible_to_role(guide: Guide, role: str | None) -> bool:
    """Return True if `role` is allowed to see `guide`.

    - Empty/missing `roles` → visible to everyone.
    - master_admin sees everything.
    - otherwise exact-match against the roles list.
    """
    roles = guide.get("roles") or []
    if not roles:
        return True
    if role == "master_admin":
        return True
    return role in roles


def list_guides(role: str | None = None, category: str | None = None,
                module: str | None = None, popular_only: bool = False) -> list[dict]:
    """Return guide cards (not full bodies) filtered by role/category/module."""
    out: list[dict] = []
    for g in GUIDES:
        if not visible_to_role(g, role):
            continue
        if category and g.get("category") != category:
            continue
        if module and g.get("module") != module:
            continue
        if popular_only and not g.get("popular"):
            continue
        out.append({
            "id": g["id"],
            "category": g["category"],
            "module": g.get("module"),
            "title": g["title"],
            "description": g["description"],
            "read_minutes": g.get("read_minutes", 2),
            "popular": bool(g.get("popular")),
            "updated_at": g.get("updated_at"),
        })
    return out


# ── Search synonym map ──────────────────────────────────────────────
# Keep this small + curated. Each key is a token the user might type;
# values are alternates we should *also* search the corpus for. The
# search function expands the needle with these, so "machine" finds
# guides that only say "equipment", "raise" finds "log", etc.
_SEARCH_SYNONYMS: dict[str, list[str]] = {
    "add":         ["create", "new", "register"],
    "create":      ["add", "new"],
    "new":         ["add", "create"],
    "piece":       ["item", "asset"],
    "machine":     ["equipment", "asset"],
    "equipment":   ["machine", "asset", "kit"],
    "kit":         ["equipment", "machine"],
    "asset":       ["equipment", "machine"],
    "fault":       ["issue", "problem", "ticket", "case"],
    "issue":       ["fault", "problem", "ticket"],
    "problem":     ["fault", "issue"],
    "ticket":      ["case", "fault"],
    "case":        ["ticket", "fault"],
    "raise":       ["log", "submit", "open", "report"],
    "log":         ["raise", "submit", "open", "report"],
    "submit":      ["raise", "log", "open"],
    "report":      ["raise", "log"],
    "member":      ["customer", "client", "user"],
    "customer":    ["member", "client"],
    "client":      ["member", "customer"],
    "class":       ["session", "booking"],
    "session":     ["class"],
    "booking":     ["class", "session", "reservation"],
    "invoice":     ["bill", "statement"],
    "bill":        ["invoice", "statement"],
    "renew":       ["renewal", "extend"],
    "delete":      ["remove"],
    "remove":      ["delete"],
    "edit":        ["update", "change", "modify"],
    "update":      ["edit", "change", "modify"],
    "change":      ["edit", "update"],
    "rota":        ["schedule", "shift"],
    "schedule":    ["rota", "shift"],
    "shift":       ["rota", "schedule"],
    # Iter 215m additions — match the new help-corpus topics.
    "freeze":      ["pause", "suspend", "hold"],
    "pause":       ["freeze", "suspend"],
    "suspend":     ["freeze", "pause"],
    "cancel":      ["end", "terminate", "stop"],
    "end":         ["cancel", "terminate"],
    "membership":  ["plan", "subscription"],
    "plan":        ["membership", "subscription"],
    "subscription":["membership", "plan"],
    "dunning":     ["recovery", "failed", "retry"],
    "recovery":    ["dunning", "retry"],
    "qr":          ["scan", "code", "label"],
    "scan":        ["qr", "code"],
    "warranty":    ["guarantee", "cover"],
    "deliverability":["spam", "spf", "dkim", "dns"],
    "domain":      ["dns", "verify", "deliverability"],
    "payroll":     ["pay", "wage", "salary"],
    "pay":         ["payroll", "wage", "salary"],
    "publish":     ["release", "send"],
    "approve":     ["accept", "confirm"],
    "decline":     ["reject", "deny"],
    "import":      ["upload", "csv", "bulk"],
    "csv":         ["import", "upload"],
    "bulk":        ["import", "many", "all"],
}

_STOP_WORDS = {
    "a", "an", "and", "the", "of", "to", "in", "on", "for",
    "i", "how", "do", "can", "where", "what", "is",
}


def _expand_query(q: str) -> list[str]:
    """Tokenise a user query, drop stop words, expand with synonyms."""
    raw = (q or "").lower().strip()
    if not raw:
        return []
    tokens = [t for t in re.findall(r"[a-z0-9]+", raw) if t not in _STOP_WORDS]
    expanded: set[str] = set(tokens)
    for t in tokens:
        for syn in _SEARCH_SYNONYMS.get(t, []):
            expanded.add(syn)
    return list(expanded)


def search_guides(q: str, role: str | None = None) -> list[dict]:
    """Token-scored case-insensitive search across title + description + step bodies.

    Scoring: each guide gets +3 per token hit in title, +2 per hit in
    description, +1 per hit in any step body. Synonyms add to the
    needle set so e.g. "add a piece of equipment" expands to also
    look for create / new / item / machine / kit / asset.

    Falls back to the raw substring match if tokenisation produces
    nothing useful (e.g. queries shorter than a stop word).
    """
    needle_raw = (q or "").strip().lower()
    if not needle_raw:
        return []

    tokens = _expand_query(needle_raw)
    if not tokens:
        # Pure stop-word query — degrade gracefully.
        tokens = [needle_raw]

    scored: list[tuple[int, dict]] = []
    for g in GUIDES:
        if not visible_to_role(g, role):
            continue
        title = (g.get("title", "") or "").lower()
        desc = (g.get("description", "") or "").lower()
        steps_blob = " ".join(
            (s.get("title", "") + " " + s.get("body", "")).lower()
            for s in g.get("steps", [])
        )
        score = 0
        for t in tokens:
            if t in title:
                score += 3
            if t in desc:
                score += 2
            if t in steps_blob:
                score += 1
        # Direct phrase match is a bonus.
        if needle_raw in title or needle_raw in desc:
            score += 4
        if score > 0:
            scored.append((score, {
                "id": g["id"],
                "category": g["category"],
                "title": g["title"],
                "description": g["description"],
                "module": g.get("module"),
                "_score": score,
            }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:20]]



# ─── Walkthroughs ────────────────────────────────────────────────────
# Joyride-shaped walkthroughs for guides that DON'T already inline one.
# Keeping these out of the main GUIDES blob keeps the editorial copy
# easy to scan; they're merged at module-import time below.
#
# Each step targets a `[data-testid=...]` selector in the live app. If
# a target doesn't exist on the page, Joyride logs a warning and skips
# the step — that's an acceptable graceful degradation for guides that
# touch features not yet visible on the user's plan.
_WALKTHROUGHS: dict[str, dict] = {
    "gs-first-login": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='pulse-dashboard-tabs']", "title": "Welcome",       "content": "These are your Operations tabs. We'll switch to Equipment first.", "placement": "bottom"},
            {"target": "[data-testid='lite-tab-equipment']",   "title": "Add equipment",  "content": "Click Equipment to import your machines (CSV or manual).",        "placement": "bottom"},
            {"target": "[data-testid='lite-tab-faults']",      "title": "Then Faults",    "content": "Faults is where you log every issue. We'll route to suppliers automatically.", "placement": "bottom"},
        ],
    },
    "gs-modules-overview": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='module-switcher']", "title": "Module switcher", "content": "Use this to jump between Operations, Memberships, CRM and Marketing — your role follows you everywhere.", "placement": "bottom"},
        ],
    },
    "crm-pipeline-first-deal": {
        "initial_route": "/crm",
        "steps": [
            {"target": "[data-testid='crm-tabs-desktop']",       "title": "CRM tabs",   "content": "Pipeline lives in the deals section.", "placement": "bottom"},
            {"target": "[data-testid='crm-nav-pipeline']",       "title": "Open Pipeline", "content": "Click Pipeline. Drag deals across stages here.", "placement": "bottom"},
        ],
    },
    "crm-company-setup": {
        "initial_route": "/crm",
        "steps": [
            {"target": "[data-testid='crm-tabs-desktop']", "title": "CRM tabs",  "content": "Companies sit alongside Contacts.",  "placement": "bottom"},
            {"target": "[data-testid='crm-nav-companies']", "title": "Companies", "content": "Click Companies — multi-site groups live here.", "placement": "bottom"},
        ],
    },
    "crm-contracts-overview": {
        "initial_route": "/crm",
        "steps": [
            {"target": "[data-testid='crm-tabs-desktop']",       "title": "CRM tabs",   "content": "Contracts are inside the contracts section.", "placement": "bottom"},
            {"target": "[data-testid='crm-nav-contracts']",      "title": "Open Contracts", "content": "Click Contracts to manage SLAs, billing, and renewals.", "placement": "bottom"},
        ],
    },
    "service-triage-ai": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='lite-tab-faults']",  "title": "Open Faults",      "content": "AI triage appears on every fault that has a photo.", "placement": "bottom"},
            {"target": "[data-testid='faults-content']",    "title": "Pick a fault",     "content": "Click any fault row to see the AI triage card on the right.", "placement": "top"},
        ],
    },
    "mbr-first-plan": {
        "initial_route": "/memberships",
        "steps": [
            {"target": "[data-testid='mbr-tabs-desktop']",  "title": "Memberships tabs", "content": "Plans is its own tab.",      "placement": "bottom"},
            {"target": "[data-testid='mbr-tab-plans']",     "title": "Open Plans",        "content": "Click Plans to create or edit pricing.", "placement": "bottom"},
        ],
    },
    "mbr-first-class": {
        "initial_route": "/memberships",
        "steps": [
            {"target": "[data-testid='mbr-tabs-desktop']",     "title": "Memberships tabs", "content": "Timetable is where classes go live.", "placement": "bottom"},
            {"target": "[data-testid='mbr-tab-timetable']",    "title": "Open Timetable",    "content": "Click Timetable. Empty cells become new classes when you click them.", "placement": "bottom"},
        ],
    },
    "mkt-ai-director": {
        "initial_route": "/marketing",
        "steps": [
            {"target": "[data-testid='mkt-tabs-desktop']",          "title": "Marketing tabs",     "content": "Creative Studio holds the AI Director.", "placement": "bottom"},
            {"target": "[data-testid='marketing-tab-creative']",    "title": "Open Creative Studio", "content": "Click Creative Studio. The big prompt box at the top is the AI Director.", "placement": "bottom"},
        ],
    },
    "mkt-audiences-101": {
        "initial_route": "/marketing",
        "steps": [
            {"target": "[data-testid='mkt-tabs-desktop']",        "title": "Marketing tabs", "content": "Audiences is its own tab.", "placement": "bottom"},
            {"target": "[data-testid='marketing-tab-audiences']", "title": "Open Audiences", "content": "Click Audiences to build dynamic segments.", "placement": "bottom"},
        ],
    },
    "mkt-brand-kit": {
        "initial_route": "/marketing",
        "steps": [
            {"target": "[data-testid='mkt-tabs-desktop']",      "title": "Marketing tabs", "content": "Brand Kit applies your style to every AI creative.", "placement": "bottom"},
            {"target": "[data-testid='marketing-tab-brand']",   "title": "Open Brand Kit", "content": "Click Brand Kit. Logo, colours and brand voice live here.", "placement": "bottom"},
        ],
    },
    "staff-gym-floor-login": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='lite-tab-gym-floor']", "title": "Gym Floor",  "content": "Click Gym Floor to manage the touch-friendly kiosk used by your front desk.", "placement": "bottom"},
        ],
    },
    "reporting-weekly-digest": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='lite-tab-reports']",   "title": "Reports",       "content": "Reports is where the Weekly Digest is configured.", "placement": "bottom"},
        ],
    },
    "reporting-exports": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='lite-tab-reports']",   "title": "Reports",   "content": "Click Reports — every CSV/Excel export starts here.", "placement": "bottom"},
        ],
    },
    "admin-roles-explained": {
        "initial_route": "/master-admin",
        "steps": [
            {"target": "body", "title": "Admin Console", "content": "Look for the Users sidebar item — every role and permission lives there.", "placement": "center"},
        ],
    },
    "admin-security-mfa": {
        "initial_route": "/account",
        "steps": [
            {"target": "body", "title": "Account → Security", "content": "Look for the Security panel. The Enable MFA button is at the top.", "placement": "center"},
        ],
    },
    "int-stripe-connect": {
        "initial_route": "/memberships",
        "steps": [
            {"target": "[data-testid='mbr-tabs-desktop']",     "title": "Memberships",   "content": "Payments lives inside Settings.", "placement": "bottom"},
            {"target": "[data-testid='mbr-tab-settings']",     "title": "Open Settings", "content": "Click Settings → Payments → 'Connect Stripe'.", "placement": "bottom"},
        ],
    },
    "int-sage200": {
        "initial_route": "/master-admin",
        "steps": [
            {"target": "body", "title": "Admin Console", "content": "Look for Integrations → Sage 200 in the sidebar. Paste your API credentials there.", "placement": "center"},
        ],
    },
    "int-sicon": {
        "initial_route": "/master-admin",
        "steps": [
            {"target": "body", "title": "Admin Console", "content": "Look for Integrations → Sicon. Map your sites and engineers there.", "placement": "center"},
        ],
    },
    "ai-assistant": {
        "initial_route": "/marketing",
        "steps": [
            {"target": "[data-testid='unified-assistant-toggle']", "title": "Open the assistant", "content": "Click the sparkle icon. The assistant is context-aware — it knows what tab you're on.", "placement": "left"},
        ],
    },
    "ai-campaign-copilot": {
        "initial_route": "/marketing",
        "steps": [
            {"target": "[data-testid='mkt-tabs-desktop']", "title": "Marketing", "content": "The Copilot lives inside the Campaign Wizard. Open the Start tab and click 'Build a campaign'.", "placement": "bottom"},
        ],
    },
    "ai-fault-triage": {
        "initial_route": "/pulse",
        "steps": [
            {"target": "[data-testid='lite-tab-faults']",  "title": "Open Faults", "content": "AI triage automatically appears on faults that include a photo.", "placement": "bottom"},
        ],
    },
}

# Merge into the canonical GUIDES list at module import time so existing
# helpers (`guide_by_id`, list_guides, search_guides) automatically see
# the walkthrough field. Skip if the guide already has an inline one.
for _g in GUIDES:
    _wid = _g.get("id")
    if _wid and _wid in _WALKTHROUGHS and not _g.get("walkthrough"):
        _g["walkthrough"] = _WALKTHROUGHS[_wid]
