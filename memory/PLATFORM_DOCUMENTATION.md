> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> The Version 1.0 (April 2026) baseline below is augmented by the
> Feb 2026 sprint (h-series). See `PRD.md` for the iter-level log;
> the table below summarises what's NEW since 1.0:
>
> | Capability | Status |
> | --- | --- |
> | CRM Phase 3 (territory tree, AI next-best-action, cross-module timeline, reports + date filters) | ✅ shipped |
> | Module-tailored trial onboarding (primary_module narrows /activation/me + /account/onboarding) | ✅ shipped |
> | 16 activation event types (was 8) — CRM lead/deal/quote, Marketing brand/audience/campaign, Operations fault | ✅ shipped + emit hooks wired |
> | Mobile rails — popover viewport clamp, `[data-fab-rail]` stacking, fixed trial banner spacer, horizontal-scroll wrappers on 9 MasterAdmin tables | ✅ shipped |
> | `Add Equipment` direct CTA on `EquipmentInfoTab` (previously only multi-machine AI Invoice Import) | ✅ shipped |
> | EngineerDiary week-view mobile fix (overflow-x-auto + min-w-[700px]) | ✅ shipped |
> | CreativeStudio 2-column mobile grid | ✅ shipped |
> | GitHub Actions Quality Gates (ESLint=0, Ruff/Bandit/Xenon/pip-audit clean, pytest CI suite, gitleaks, prod build smoke) | ✅ green & enforced |
> | Tool versions pinned in CI (`ruff==0.15.10`, `bandit==1.9.4`, `xenon==0.9.3`) | ✅ |
> | Production deployment | ✅ `gymaxis.com` live |
>
> ### Outstanding integrations (P1)
> - **Sicon** (CAPEX / parts / labour) — code path ready, waiting on
>   live credentials. See `memory/SICON_INTEGRATION_SPEC.md` + the
>   companion `docs/SICON_INTEGRATION_PROOF.md`.
> - **DocuSign** on CRM Quote send — code path ready, waiting on creds.
>
> ### Outstanding integrations (P2)
> - **Sage 200** ledger posting on payment + CRM lead conversion — MOCKED.
> - **Twilio SMS** — MOCKED.
>
> ### P3
> - Right-to-erasure workflow for personnel records.

---


# GymAxis AI - Complete Platform Documentation
## Version 1.0 | April 2026

---

# Table of Contents

1. Platform Overview
2. System Architecture
3. Platform Access Tiers and Roles
4. Universal Login System
5. Service Portal - GymAxis (Full)
6. Service Portal - Pulse Fitness Pro
7. Service Portal - Pulse Fitness Lite
8. CRM System
9. Master Admin Portal
10. Supplier Collaboration Portal
11. Integration Hub (Event Bus)
12. Email System (Resend)
13. PWA - Progressive Web App
14. Data Models Reference
15. API Reference Summary
16. Glossary

---

# 1. Platform Overview

GymAxis AI is an AI-native equipment management, service operations, and commercial CRM platform purpose-built for the fitness and leisure industry. It connects gym operators, service teams, sales professionals, and equipment suppliers into a single unified ecosystem.

## 1.1 Who Uses GymAxis AI?

The platform serves three distinct user groups, each with tailored interfaces and workflows:

- Gym Operators and Site Managers: These users are responsible for the day-to-day running of gym and leisure facilities. They use the platform to log equipment faults, manage maintenance schedules, communicate directly with equipment suppliers, run daily and weekly check sheets, view gym floor layouts, and generate operational reports. Their primary interface is the Service Portal, available in three variants (GymAxis, Pulse Fitness Pro, and Pulse Fitness Lite).

- Sales and Account Managers: These users work within the CRM system to manage the full commercial lifecycle. They handle sales pipelines, create and track deals and opportunities, generate quotes with digital signatures, manage contracts through a multi-stage approval workflow, respond to tenders using AI assistance, and maintain relationships with companies and contacts. The CRM is a separate system with its own authentication and role-based access.

- Platform Administrators: Administrators have access to the Master Admin portal, which provides platform-wide governance capabilities. They can create and manage organisations, provision users, toggle features per organisation, monitor platform health, view cross-organisation analytics, and manage subscription tiers. The Master Admin portal is accessible from the GymAxis dashboard for users with the master admin flag.

## 1.2 The Three Interconnected Systems

The platform is built as three interconnected systems that share data through an Integration Hub:

- Service Portal: Equipment management, fault reporting, AI-powered diagnosis, supplier collaboration, check sheets, gym layouts, reports, risk assessments, purchase orders, and financial operations. Available in three variants: GymAxis (dark theme, full features), Pulse Fitness Pro (light theme, full features), and Pulse Fitness Lite (light theme, feature-gated).

- CRM (Customer Relationship Management): A complete enterprise CRM with 13 modules covering the full commercial lifecycle. Includes pipeline management, contacts and companies, quotes with CPQ (Configure, Price, Quote), contracts management, tender engine, AI tools, workflow automation, calendar, documents, and settings.

- Master Admin: Platform-wide governance and analytics. Organisation management, user provisioning, feature toggles, subscription tiers, CRM analytics, payment tracking, and support tools.

## 1.3 Key Platform Capabilities

- AI-Powered Diagnosis: When a fault is logged, GPT-5.2 analyses the description and any attached photos to provide a diagnosis, recommended repair steps, estimated parts list, and time estimate.
- Two-Way Supplier Communication: Gym operators can message equipment suppliers directly from a fault record. Suppliers receive an email with a link to a public portal where they can respond, schedule engineer visits, and update case status, all without needing to create an account.
- Contract Lifecycle Management: Contracts flow through a defined lifecycle from Draft through to Active, with approval workflows, digital signatures, site and asset assignment, SLA configuration, and integration with Sicon and Sage 200.
- Event-Driven Architecture: All systems are connected through an Integration Hub that routes events between the Service Portal, CRM, and external systems (Sage 200, Sicon). When a deal is won in the CRM, a sales order is created in the Service Portal. When equipment reaches end of life, a replacement opportunity is created in the CRM.
- Progressive Web App: The platform can be installed on mobile devices as a standalone app, providing a native-like experience with persistent sessions and offline caching of static assets.

---

# 2. System Architecture

## 2.1 Technology Stack

- Frontend: React 18 with Tailwind CSS for styling and Shadcn/UI component library. The frontend is a single-page application (SPA) with client-side routing.
- Backend: FastAPI (Python) providing a RESTful API. All endpoints are prefixed with /api for proper routing through the Kubernetes ingress.
- Database: MongoDB for document storage. Collections are organised by domain (Service Portal, CRM, Integration).
- AI Engine: OpenAI GPT-5.2 accessed via the Emergent LLM Key. Used for fault diagnosis, tender response generation, lead scoring, email generation, meeting intelligence, deal insights, and data cleaning.
- Email: Resend email service with a verified sending domain (service.gymaxisai.com). Used for supplier notifications, password resets, purchase orders, and two-way comment notifications.
- Payments: Stripe integration for subscription management, payment collection, and quote payment links.
- ERP Integration: Sage 200 integration for financial data synchronisation (currently mocked, awaiting live API keys).
- Service Integration: Sicon Service Contracts for service case management and engineer dispatch (currently mocked, awaiting live API keys).
- Authentication: JWT (JSON Web Tokens) for both the Service Portal and CRM. The CRM additionally supports TOTP (Time-based One-Time Password) two-factor authentication.
- PWA: Service Worker for offline caching and a Web App Manifest for installability.

## 2.2 Scale

The platform exposes 422 API endpoints across 42 route modules, covering all aspects of equipment management, fault handling, supplier collaboration, commercial operations, and platform administration.

---

# 3. Platform Access Tiers and Roles

## 3.1 Access Tiers

The platform has five access tiers, each providing a different set of features and accessed through different routes:

GymAxis (Full): Route /dashboard. The complete service management platform with dark theme. Includes all equipment management features, fault handling with AI triage, check sheets, gym layouts, reports, Sicon integration, capex intelligence, financial operations, risk assessments, supplier management, and purchase orders. This is the flagship product aimed at larger operators who need the full suite of tools.

Pulse Fitness Pro: Route /pulse. Feature-identical to GymAxis but with a light theme branded for Pulse Fitness. Uses the same underlying components (IssueDetailPanel, FaultDialogs, etc.) with CSS custom properties to switch between dark and light themes. Any feature added to GymAxis must also be available in Pulse Fitness Pro and vice versa (the "Parity Rule").

Pulse Fitness Lite: Route /pulse. A reduced-feature variant of Pulse Fitness Pro for smaller organisations. Uses the same LiteDashboardPage component as Pro but with feature-gated access. Individual features can be enabled or disabled per organisation from the Master Admin portal using feature toggles.

CRM: Route /crm. A separate system with its own authentication. Provides the full commercial operations suite including pipeline management, contacts, companies, quotes/CPQ, contracts, tenders, AI tools, workflows, calendar, documents, and settings.

Master Admin: Route /master-admin. Accessible from the GymAxis dashboard navigation bar for users with the is_master_admin flag set to true. Provides platform-wide governance over organisations, users, features, subscriptions, and analytics.

## 3.2 Feature Toggle System (Lite vs Pro)

The Master Admin portal provides granular control over which features are available to each organisation. Features are grouped into categories:

General Features: Documents, Gym Layouts, Reports, Check Sheets. These are the standard operational tools that most organisations will need.

Service Portal Features: Sicon Integration, Capex Intelligence, Financial Operations. These are advanced features typically needed by larger organisations with more complex operational requirements.

CRM Module Features: Pipeline, Quotes/CPQ, Tender Engine, AI Tools, Workflows, Documents. These control which CRM modules are available to the organisation.

When a feature is disabled for an organisation, the corresponding tab or section is hidden from the user interface. The backend also enforces feature access to prevent direct API calls to disabled features.

## 3.3 User Roles

Service Portal Roles:
- Owner: Full access to all features, can manage staff, view all data across the organisation
- Manager: Can manage equipment, faults, and day-to-day operations. Can view reports and analytics.
- Staff: Can log faults, complete check sheets, and view equipment. Limited access to administrative functions.

CRM Roles:
- Owner: Full CRM access including team management, audit logs, and all settings. Can view and manage all deals, contacts, and activities.
- Admin: Same as Owner but cannot modify Owner accounts or access certain administrative settings.
- Manager: Can manage deals, contacts, activities, and view team performance. Can approve quotes and contracts.
- Sales Rep: Can create and manage their own deals, contacts, and activities. Limited visibility of other team members' data.

Master Admin:
- Users with the is_master_admin flag can access the Master Admin portal. This is typically reserved for GymAxis platform administrators rather than individual gym operators.

---

# 4. Universal Login System

## 4.1 How Login Works

The platform implements a Universal Login system that allows users to access both the Service Portal and CRM from a single login page. The workflow is as follows:

Step 1: The user navigates to the landing page and clicks the Login button, or navigates directly to the /login route.

Step 2: The user enters their email address and password and clicks Sign In.

Step 3: The system simultaneously attempts authentication against both the Service Portal user database (/api/auth/login) and the CRM user database (/api/crm/auth/login). Both requests are sent in parallel to minimise login time.

Step 4a - Single System User: If the user exists in only one system (either Service Portal or CRM), they are automatically redirected to that system's dashboard. No additional selection is required.

Step 4b - Dual System User: If the user's credentials are valid in both systems, a "Choose Your Workspace" dialog is displayed. This dialog presents two options:
- Service Portal: "Equipment management, maintenance and compliance" - directs to the equipment/fault management dashboard
- CRM System: "Sales pipeline, contacts, contracts and quotes" - directs to the CRM dashboard

Step 4c - Invalid Credentials: If authentication fails against both systems, an error message is displayed.

## 4.2 Authentication Features

JWT Token-Based Authentication: Both the Service Portal and CRM use JWT tokens for session management. The Service Portal stores its token in localStorage under the key "token", while the CRM stores its token under "crm_token". This separation allows users to be simultaneously logged into both systems in the same browser.

Password Reset: Users can request a password reset from the login page. The system sends an email (via Resend) containing a time-limited reset link. The link directs the user to a page where they can set a new password. Password reset is available for both Service Portal and CRM accounts.

Two-Factor Authentication (CRM Only): CRM users can optionally enable TOTP-based two-factor authentication. Setup involves scanning a QR code with an authenticator app (such as Google Authenticator or Authy). Once enabled, users must provide a 6-digit code from their authenticator app in addition to their password when logging in. 2FA can be configured from CRM Settings > Security.

Brute Force Protection: The login endpoints implement rate limiting to prevent brute force password attacks. After multiple failed login attempts, the account may be temporarily locked.

PWA Session Persistence: When the application is installed as a PWA (Progressive Web App) and running in standalone mode, login sessions are persisted in localStorage. This means users do not need to re-authenticate each time they open the app. Both Service Portal and CRM tokens are preserved across app restarts.

---

# 5. Service Portal - GymAxis (Full)

The GymAxis Service Portal is the full-featured equipment and service management platform. It is available at the /dashboard route and uses a dark theme. This section describes every feature in detail.

## 5.1 Dashboard Overview

Upon logging in, users are presented with a dashboard that provides an at-a-glance view of their facility's operational status:

Equipment Health Score: A percentage score calculated from the ratio of working equipment to total equipment, weighted by fault severity. Displayed as a prominent metric at the top of the dashboard.

Open Faults Summary: Shows the total number of open faults with a breakdown by severity (Critical, High, Medium, Low). Each severity level is colour-coded for quick identification.

Recent Activity Feed: A chronological list of recent platform activities including new faults logged, faults resolved, equipment added, check sheets completed, and supplier communications.

Quick Actions: Prominent buttons for the most common tasks - "Log Fault" to report a new equipment issue, and "Add Equipment" to register new equipment.

Lifecycle Alerts: Warnings about equipment approaching end-of-warranty, end-of-life, or requiring scheduled maintenance. Helps operators plan ahead for replacements and renewals.

## 5.2 Equipment Management

The Equipment Management module is the core of the Service Portal. It provides a complete register of all equipment across the organisation's sites.

### Equipment Register

The equipment register displays all equipment items as cards. Each card shows the equipment name, type, manufacturer, model, location, and current status. Cards have colour-coded left borders:
- Green border: Equipment is in good working order (no open faults)
- Red border: Equipment has one or more open faults

Users can filter equipment by site, type, and status. A search bar allows finding specific equipment by name, serial number, or manufacturer.

### Adding Equipment

To add new equipment, users click the "Add Equipment" button and complete a form with the following fields:
- Name: A descriptive name for the equipment (e.g., "Treadmill - Bay 3")
- Type: The equipment category (e.g., Treadmill, Cross Trainer, Rowing Machine, Free Weights)
- Manufacturer: The equipment manufacturer (e.g., Life Fitness, Technogym, Precor)
- Model: The specific model name or number
- Serial Number: The unique serial number from the manufacturer
- Location: Where the equipment is situated within the facility
- Installation Date: When the equipment was installed
- Warranty Expiry: When the manufacturer warranty expires
- Supplier: The supplier who provided the equipment
- Site: Which site the equipment belongs to (for multi-site organisations)

### Equipment Detail View

Clicking on an equipment card opens the detail view, which contains multiple tabs:

Specifications Tab: Displays all equipment details including manufacturer, model, serial number, installation date, warranty status, supplier, and location. All fields can be edited inline.

Fault History Tab: Lists all faults ever logged against this equipment, ordered by date. Each fault shows its status, severity, description, and resolution type.

Maintenance Schedule: Shows upcoming and historical maintenance activities for the equipment, including preventive maintenance schedules.

Predictive Maintenance: AI-powered analysis of fault patterns and equipment age to predict when maintenance will be needed. Helps operators move from reactive to proactive maintenance.

QR Code: Each equipment item has a unique QR code that can be printed and attached to the physical equipment. When scanned, the QR code leads to a public page where anyone (including gym members) can report faults.

Manuals and Documents: A section for uploading and storing equipment manuals, specification sheets, installation guides, and any other relevant documents.

Log Fault Button: Positioned prominently above the QR code, this button allows users to quickly log a new fault against this specific piece of equipment.

### CSV Import and Export

For organisations with large equipment inventories, the platform supports bulk operations:

CSV Import: Users can download a CSV template, populate it with equipment data, and upload it to create multiple equipment records at once. The import process validates the data and reports any errors.

CSV Export: The entire equipment register can be exported as a CSV file for external analysis or record-keeping.

### AI Equipment Import

The platform can recognise equipment from photographs. Users upload an image of a piece of equipment, and GPT-5.2 analyses the image to identify the manufacturer, model, and type. This information is pre-populated into the equipment creation form, saving time during initial setup.

### Equipment Statistics

Per-equipment statistics are tracked including:
- Total number of faults logged
- Fault frequency (faults per month)
- Mean Time Between Failures (MTBF)
- Total cost of repairs and parts
- Equipment uptime percentage

## 5.3 Fault Management

Fault management is the operational heart of the Service Portal. It covers the entire lifecycle of an equipment fault from initial report through to resolution.

### Logging a Fault

The fault logging process follows these steps:

Step 1 - Equipment Selection: The user selects which piece of equipment has the fault. If a fault is being logged from the equipment detail view, this step is skipped.

Step 2 - Existing Fault Check: The system checks if there are already open faults for the selected equipment. If open faults exist, a dialog is shown with two options:
- Cancel: Returns the user to the equipment detail view to review existing faults
- Continue: Proceeds with logging a new fault (for cases where the new issue is different from the existing one)

Step 3 - Fault Details: The user provides:
- Severity: Critical (equipment unusable, safety risk), High (equipment impaired, affects service), Medium (equipment degraded, workaround available), Low (cosmetic or minor issue)
- Description: A free-text description of the fault
- Photos/Videos: Optional media attachments showing the fault
- Steps Already Taken: Any troubleshooting the user has already attempted

Step 4 - AI Triage: Once submitted, GPT-5.2 automatically analyses the fault description and any attached images. The AI provides:
- Diagnosis: What is likely wrong with the equipment
- Recommended Repair Steps: Step-by-step instructions for attempting a fix
- Parts Required: A list of parts that may need to be ordered
- Estimated Repair Time: How long the repair is expected to take
- Severity Assessment: The AI's assessment of the fault severity, which may differ from the user's initial selection

Step 5 - Resolution Path: Based on the AI triage, the user chooses a resolution path:
- Self-Fix (AI Guided): Follow the AI's repair steps to fix the issue in-house
- Engineer Callout: Request an engineer visit through the Sicon integration
- Supplier Escalation: Contact the equipment supplier for support (opens the Supplier Communication workflow)

### Fault Cards and Status

Faults are displayed as cards with colour-coded borders indicating status:
- Red border: Open fault - not yet being worked on
- Orange border: In Progress - fault is being actively addressed
- Green border: Resolved - fault has been fixed

Each fault card shows the equipment name, severity badge, date logged, description excerpt, and current resolution status.

### Fault Detail Panel

Clicking on a fault card expands an inline detail panel (the IssueDetailPanel component) that shows the complete fault record:

Information Grid: Logged by (user name), date reported, assigned supplier, current resolution status, and site name.

Full Description: The complete fault description and any steps already taken by the user.

Fault Media: Photos and videos attached when the fault was logged. Displayed in a gallery format with lightbox viewing.

AI Triage Results: The full AI diagnosis including recommended repair steps, parts list, and severity assessment. Displayed in a structured format with clear headings.

Supplier Communication: An inline chat interface for communicating with the equipment supplier. Messages are displayed in an iMessage-style bubble format:
- Green bubbles (left-aligned): Messages from the gym/facility
- Blue bubbles (right-aligned): Messages from the supplier
The last 2 messages are shown by default. If there are 3 or more messages, a "Conversation History" button appears that expands to show the full scrollable conversation thread.

Scheduled Engineer Visit Banner: If the supplier has scheduled an engineer visit, a banner is displayed showing the scheduled date, engineer name, and any notes.

Supplier Card Button: Opens the full supplier portal page in a new browser tab, showing the complete case view from the supplier's perspective.

Attachments and Job Sheets: Section for uploading additional documents such as job sheets, invoices, and completion certificates.

Supplier Reference: A field for recording the supplier's own reference number for the case.

Purchase Order Creation: A button to create a purchase order linked to this fault, pre-populated with the supplier details.

Sicon Service Sync: A button to push this fault to the Sicon service system for engineer dispatch and tracking.

### Fault Resolution Status Logic

The resolution status displayed on a fault depends on its current state:

For resolved faults:
- "Self-fixed (AI guided)" - The user followed the AI's repair steps and resolved the issue
- "Engineer callout" - An engineer was dispatched and resolved the issue
- "Resolved" - Generic resolution (e.g., supplier replaced the equipment)

For open faults:
- "Awaiting supplier" - A supplier case has been created and we are waiting for a response
- "Engineer requested" - An engineer visit has been requested but not yet scheduled
- "Self-fix attempted" - The user attempted the AI-guided repair but it was not successful
- "In progress" - The fault is being actively worked on

### Fault Filters

Users can filter faults by:
- Status: Open, In Progress, Resolved
- Severity: Critical, High, Medium, Low
- Date range: Filter by when the fault was logged
- Equipment: Filter by specific equipment item

## 5.4 Check Sheets

Check sheets provide a structured way to ensure daily and weekly maintenance tasks are completed consistently.

### Templates

The platform comes with pre-built check sheet templates:
- Daily Gym Floor Check: A checklist of items to inspect at the start of each day (equipment power, safety features, cleanliness, signage)
- Weekly Maintenance Check: A more thorough checklist covering lubrication, belt tension, electronics, and calibration

Users can also create custom templates with their own check items, groupings, and pass/fail criteria.

### Completing Check Sheets

To complete a check sheet, the user selects a template and goes through each item, marking it as Pass, Fail, or N/A. For failed items, the user can add notes and optionally log a fault directly from the check sheet.

### Tracking and Compliance

Completed check sheets are stored with the user name, date, time, and all responses. Historical records can be viewed for compliance auditing. Reports show completion rates by template, by equipment, and by user, making it easy to identify gaps in maintenance routines.

## 5.5 Gym Layouts

The Gym Layouts module allows operators to create digital floor plans of their facilities.

### Creating Floor Plans

Users can create and edit floor plans by:
- Drawing rooms and zones
- Positioning equipment items from the equipment register onto the floor plan
- Equipment dimensions are automatically pulled from specification sheets where available
- Adding labels and annotations

### AI Floor Plan Detection

Users can upload a photograph or scan of an existing floor plan. GPT-5.2 analyses the image to detect equipment types and positions, providing a starting point for the digital layout.

### Equipment Legend

Each piece of equipment on the floor plan is numbered and linked to the equipment register. A legend panel lists all equipment with their numbers, names, and current status.

## 5.6 Reports and Analytics

The Reports module provides operational intelligence about equipment health and service performance.

Resolution Statistics: Breakdown of fault resolutions by type (self-fixed, engineer, supplier), average resolution time, and resolution rate over time.

Equipment Summary: Per-equipment report showing total faults, current status, age, maintenance history, and cost of ownership.

Operational Reports: 30-day rolling reports covering fault volumes, response times, equipment downtime, and check sheet compliance.

Fault Frequency Analysis: Identifies equipment with the highest fault rates, recurring fault types, and seasonal patterns.

Supplier Performance: Tracks supplier response times, resolution rates, and satisfaction ratings to help operators choose the best suppliers.

## 5.7 Sicon Service Integration

The Sicon integration connects GymAxis to the Sicon Service Management system for engineer dispatch and service case tracking.

Configuration: Administrators configure the Sicon connection with API credentials, endpoint URL, and mapping settings. A connection test verifies the integration is working.

Issue Sync: Faults can be pushed to Sicon, creating service cases that trigger the engineer dispatch workflow. The sync is initiated from the fault detail panel.

Data Retrieval: The integration can fetch case types, tracking statuses, and available engineers from Sicon, ensuring the GymAxis interface reflects the current state of the Sicon system.

Event Logging: All sync operations are logged with timestamps, status, and any error details for troubleshooting.

Note: The Sicon integration is currently mocked and awaiting live API keys.

## 5.8 Documents and Files

File Upload and Download: Users can upload and download files scoped to their organisation. Files are categorised for easy retrieval.

Specification Sheets: A searchable, filterable library of equipment specification sheets. Spec sheets include manufacturer details, dimensions, weight, power requirements, and maintenance intervals.

Equipment Manuals: Storage for equipment operation and maintenance manuals, linked to specific equipment items.

## 5.9 Risk Assessments

Manual Creation: Users can create risk assessments by defining hazards, controls, likelihood, severity, and resulting risk levels.

AI-Generated Assessments: Users describe a scenario (e.g., "changing the belt on a treadmill") and GPT-5.2 generates a comprehensive risk assessment including hazards, controls, PPE requirements, and emergency procedures.

Photo-Based Analysis: Users upload a photo of a workspace or situation, and the AI analyses it for potential hazards and recommends controls.

## 5.10 Financial Operations

Financial Configuration: Each organisation can configure its financial settings including cost centres, budget allocations, and reporting periods.

Cost Centre Management: Track expenditure by cost centre (e.g., Cardio Equipment, Free Weights, Building Maintenance).

Reserve Balance Tracking: Monitor reserve balances for equipment replacement and emergency repairs.

Monthly Burn Rate: Analysis of monthly expenditure trends with forecasting.

Stripe Onboarding: Organisations can connect their Stripe account for payment collection, enabling them to accept payments for services and subscriptions.

## 5.11 Capex Intelligence

Capital Expenditure Tracking: Record and track capital expenditure on equipment purchases, facility improvements, and technology investments.

Equipment Lifecycle Cost Analysis: Calculate the total cost of ownership for each piece of equipment including purchase price, maintenance costs, parts, and downtime costs.

Replacement Planning: Based on equipment age, fault history, and lifecycle costs, the system recommends when equipment should be replaced rather than repaired.

## 5.12 Supplier Management

Supplier Directory: A complete directory of equipment suppliers with contact details, specialisations, and service areas. Full CRUD (Create, Read, Update, Delete) operations.

Supplier API Integration: External API for supplier self-service and data synchronisation.

Supplier Dashboard: A dashboard view showing all active supplier cases, response times, and performance metrics.

Contact Resolution: The system resolves the correct contact email for supplier notifications based on the equipment type and supplier record.

## 5.13 Purchase Orders

Create POs: Purchase orders can be created from fault detail panels, pre-populated with the supplier and equipment details. Each PO has a unique PO number.

PO Line Items: Each PO can contain multiple line items with description, quantity, and unit price. Totals are calculated automatically.

PO Defaults: Organisations can set default values for PO fields such as delivery address, payment terms, and authorisation levels.

Supplier Email Notification: When a PO is created, the supplier receives an email notification with the PO details formatted as a professional document.

---

# 6. Service Portal - Pulse Fitness Pro

Pulse Fitness Pro is available at the /pulse route for users with the pulse_pro account type. It is feature-identical to GymAxis with the following differences:

Theme: Pulse Fitness Pro uses a light theme with Pulse Fitness branding colours, while GymAxis uses a dark theme. Both themes are implemented using CSS custom properties (variables), allowing shared components to render correctly in either theme.

Branding: The Pulse Fitness logo and colour scheme are used throughout the interface. The navigation bar, buttons, and accent colours reflect the Pulse Fitness brand.

Shared Components: Both GymAxis and Pulse Fitness Pro use the same underlying components. Key shared components include IssueDetailPanel (fault detail expansion), FaultDialogs (fault logging workflow including duplicate detection), and all equipment management components. CSS custom properties ensure these components render appropriately in both light and dark themes.

All Features Included: Every feature described in Section 5 (GymAxis) is available in Pulse Fitness Pro without exception. This includes AI triage, supplier communication with iMessage-style chat, status-coloured equipment and fault cards, duplicate fault detection with Cancel/Continue options, the full fault detail panel with all sections, equipment management with QR codes, check sheets, reports, gym layouts, documents, and all other modules.

### The Parity Rule

Any feature added to GymAxis MUST be mirrored to Pulse Fitness Pro, and vice versa. This is an absolute rule that ensures customers on either product receive identical functionality. The only differences between the two are visual (theme and branding), never functional. When developing new features, both the GymAxis dark theme and Pulse Pro light theme must be tested to ensure correct rendering.

---

# 7. Service Portal - Pulse Fitness Lite

Pulse Fitness Lite is available at the /pulse route for users with the lite account type. It uses the same LiteDashboardPage component as Pulse Fitness Pro but with feature-gated access.

## 7.1 Feature Toggle Control

The Master Admin portal controls which features are available to each Lite organisation. The following features can be independently enabled or disabled:

- Equipment Management: The core equipment register and detail views
- Fault Logging and AI Triage: The ability to log faults and receive AI diagnosis
- Check Sheets: Daily and weekly maintenance check sheets
- Reports: Operational reports and analytics
- Documents: Document upload and management
- Gym Layouts: Digital floor plan creation and management

## 7.2 How Feature Gating Works

Feature availability is controlled by the features object on the organisation record in the database. The Master Admin interface provides toggle switches for each feature, grouped by category.

When a feature is disabled:
- The corresponding tab or navigation item is hidden from the user interface
- Direct API calls to disabled features are rejected by the backend
- The UI dynamically adjusts its layout based on which features are enabled

## 7.3 Key Difference from Pro

The fundamental difference between Lite and Pro is that Lite organisations can have specific features turned off to create a simpler, more focused experience. This is useful for smaller organisations that only need a subset of the platform's capabilities, or for organisations that are gradually rolling out the platform to their teams.

Pro organisations always have access to all features. Lite organisations have a customisable feature set controlled by the platform administrator.

---

# 8. CRM System

The CRM (Customer Relationship Management) system is a complete enterprise-grade commercial operations platform available at the /crm route. It has its own authentication system, separate from the Service Portal.

## 8.1 Authentication

The CRM has a dedicated user database (crm_users collection) separate from the Service Portal user database. This separation allows for different role hierarchies and access controls.

JWT Tokens: CRM authentication tokens are stored in localStorage under the key crm_token, separate from the Service Portal token.

Role Hierarchy: The CRM implements a strict role hierarchy:
- Owner: Highest privilege level. Full access to all features, team management, audit logs, and system settings. Cannot be demoted by non-Owners.
- Admin: Near-full access. Can manage team members (except Owners), approve quotes and contracts, and access most settings.
- Manager: Can manage deals, contacts, activities, and view team performance. Can approve quotes and contracts within their authority level.
- Sales Rep: Can create and manage their own deals, contacts, and activities. Limited visibility of other team members' data.

Two-Factor Authentication: CRM users can optionally enable TOTP-based 2FA from Settings > Security. Setup involves scanning a QR code with an authenticator app. Once enabled, a 6-digit code is required at each login in addition to the password.

Cross-Login: Users who exist in both the Service Portal and CRM can switch between systems using the Universal Login workspace chooser. Each system maintains its own independent session.

## 8.2 Dashboard

The CRM dashboard provides role-appropriate metrics and quick access to key information.

Role-Based Views: The dashboard content adapts based on the user's role:
- Sales Manager: Pipeline value, win rate, team performance, deal velocity
- Service Admin: Open cases, resolution times, SLA compliance
- Engineer: Assigned cases, schedule, parts requests
- Director: Revenue metrics, forecast accuracy, team utilisation

Key Metrics: Pipeline total value, weighted forecast (sum of deal values multiplied by their probability), win rate (percentage of deals that reach Closed Won), and deal count by stage.

Recent Activity: The latest deals created or updated, activities logged, and system events.

Quick Stats Cards: At-a-glance metrics for the most important KPIs, customised by role.

## 8.3 Contacts

The Contacts module manages all individual contact records across the CRM.

Full CRUD Operations: Create, read, update, and delete contact records with the following fields:
- First Name and Last Name
- Email Address
- Phone Number
- Job Title
- Company (assigned via dropdown - unassigned contacts can be assigned to a company through the edit modal)
- LinkedIn Profile URL
- Source (how the contact was acquired: referral, website, event, cold call, etc.)
- Decision Maker Flag (boolean indicating if this contact has purchasing authority)

Company Assignment: When editing a contact, a company dropdown allows assigning the contact to an existing company. This is particularly useful for contacts that were initially created without a company association.

Company-First Filtering: In deal and quote creation workflows, selecting a company first filters the available contacts to only those associated with that company.

Activity History: Each contact has a timeline of all activities (emails, calls, meetings, tasks, notes) logged against them, providing a complete interaction history.

## 8.4 Companies

The Companies module manages business entity records with a comprehensive 11-tab detail view.

### 11-Tab Detail View

1. Overview: Company name, industry, employee count, website, phone, address, and key metrics. All fields support inline editing.
2. Contacts: List of all contacts associated with this company. Add new contacts or assign existing ones.
3. Deals: All deals/opportunities linked to this company with stage, value, and probability.
4. Cases: Service cases originating from the Integration Hub when equipment faults are escalated.
5. Assets: Equipment assets associated with this company's sites.
6. Quotes: All quotes generated for this company with status, value, and version information.
7. Drawings: Technical drawings and floor plans associated with the company's facilities.
8. Surveys: Site surveys and assessments conducted for this company.
9. Invoices: Financial records and invoice history.
10. Equipment: Equipment register for this company's sites.
11. Timeline: A chronological timeline of all activities, events, and system actions related to this company.

### AI Auto-Recognition (Companies House)

When creating or editing a UK company, the platform can automatically fetch data from Companies House:
- Company registration number
- Registered office address
- Director names (parsed from "SURNAME, FIRSTNAME" format into properly capitalised names)
- Company status and incorporation date

Director information is stored on the company record for quick reference during sales processes.

## 8.5 Pipeline (Deals and Opportunities)

The Pipeline module manages the sales process from initial lead through to deal closure.

### Kanban View

Deals are displayed as cards on a Kanban board with columns representing pipeline stages. Cards can be dragged between columns to update the deal stage. The Kanban view provides a visual overview of the entire pipeline at a glance.

Pipeline Stages:
1. Lead In: Initial interest or inquiry
2. Qualification: Assessing fit and budget
3. Proposal: Preparing and presenting a proposal
4. Negotiation: Terms and pricing discussion
5. Closed Won: Deal successfully closed
6. Closed Lost: Deal lost to competitor or abandoned

### List View

An alternative table view with sorting and filtering capabilities. Useful for large pipelines where the Kanban view becomes crowded.

### Deal Detail

Each deal has a detail view showing:
- Title, value, and current stage
- Associated company and contact
- Probability percentage (user-assigned estimate of deal closure likelihood)
- Weighted value (deal value multiplied by probability)
- Expected close date
- Source (where the deal originated)
- Competitor information
- Next steps
- Stage history (timeline of stage changes with dates)
- Linked quotes and activities

All fields support inline editing. Changes to deal stage trigger workflow events and Integration Hub notifications.

### Print Report

Deals can be exported as a printable report, sorted by probability, showing key metrics for pipeline review meetings.

## 8.6 Activity Feed

The Activity Feed tracks all interactions and tasks across the CRM.

### Activity Types with Specific Prompts

Each activity type has fields tailored to its purpose:

Email: From address, To address, subject, body, and any attachments. Captures the content of email communications.

Call: Duration (in minutes), outcome (connected, voicemail, no answer, busy), follow-up date, and notes. Tracks phone interactions and their results.

Meeting: Location, duration, attendees, agenda, and meeting notes. Records meeting details for future reference.

Task: Due date, priority (low, medium, high, urgent), assignee, and completion status. Creates actionable items with deadlines.

Note: Free-form notes that can be attached to a contact, company, or deal.

### Filtering and Search

Activities can be filtered by type, company, contact, opportunity, date range, and user. This makes it easy to find specific interactions or review all activities for a particular account.

### System-Generated Activities

The CRM automatically generates activity records for significant events such as contract creation, deal stage changes, quote acceptance, and workflow execution. These system activities provide a complete audit trail of commercial operations.

## 8.7 Calendar

The Calendar module provides an interactive visual calendar for managing meetings, calls, tasks, and follow-ups.

Interactive Month View: A traditional calendar grid showing the current month with events marked on their scheduled dates. Clicking on a day opens a dialog to create a new event on that date.

Event Types: Meeting, Call, Task, and Follow-up. Each type has a distinct colour for quick visual identification.

Type Filters: Toggle buttons to show or hide specific event types, allowing users to focus on particular types of activities.

Personal Calendar: Each staff member has their own calendar showing their scheduled events.

Team Calendar: Managers and Owners can view calendars for all team members, making it easy to coordinate schedules and identify availability.

Organisation-Scoped Staff Filtering: When viewing team calendars, staff can be filtered by organisation for multi-org deployments.

## 8.8 Quotes (CPQ - Configure, Price, Quote)

The Quotes module provides a full CPQ (Configure, Price, Quote) system for creating and managing sales quotes.

### Quote Lifecycle

Quotes follow a defined lifecycle:
1. Draft: Initial creation and editing
2. Sent: Quote has been sent to the customer
3. Accepted: Customer has accepted the quote
4. Expired: Quote has passed its validity period without acceptance

### Line Items

Each quote contains one or more line items with:
- Description of the product or service
- Quantity
- Unit Price
- Discount percentage (optional)
- Line Total (calculated automatically)

The quote total is calculated as the sum of all line item totals.

### Approval Workflow

Quotes above certain value thresholds require approval before they can be sent to the customer. The approval workflow routes the quote to the appropriate approver based on the organisation's approval rules.

### Digital Signature

Quotes include a canvas-based signature pad that works with both mouse and touch input. The customer can sign the quote directly in the browser, and the signature is captured and stored as part of the quote record.

### Quote Versioning

When a quote needs to be revised, the "Revise" action creates a new version (v2, v3, etc.). The original quote is marked as "superseded" and linked to the new version. A full version history chain is maintained, allowing users to review how a quote evolved over time.

### Quote List View

The quote list shows all quotes with company name, contact name, created by, status, total value, and version number. Quotes can be filtered by status and searched by quote number or company name.

### Payment Link

Accepted quotes can have a Stripe payment link generated, allowing the customer to make payment directly through a secure online payment page.

## 8.9 Contracts Management System

The Contracts module provides comprehensive lifecycle management for service, supply, maintenance, and umbrella contracts.

### 8-Tab Detail View

1. Overview: Contract title, number, type, tier, status, company, dates, annual value, and key terms.
2. Sites: Sites covered by the contract. Each site record includes the site name, address, and coverage notes.
3. Assets: Equipment assets covered by the contract. Each asset record includes the asset name and coverage type (Full Coverage, Parts Only, Labour Only, Inspection Only).
4. SLA and Coverage: Service Level Agreement configuration including response time hours, resolution time hours, whether parts are included, whether labour is included, number of visits per year, and preventive maintenance schedule.
5. Service Integration: Sicon service contract synchronisation. Shows sync status and allows pushing the contract to Sicon.
6. Billing: Financial details including annual value, billing frequency, payment terms, and Sage 200 synchronisation.
7. Approvals: The approval workflow showing submission history, approver decisions, and decision notes.
8. Timeline: A complete chronological timeline of all contract events including creation, edits, stage changes, approvals, and renewals.

### Contract Lifecycle

Contracts progress through a defined lifecycle of states:
1. Draft: Contract is being created and configured
2. Pending Approval: Contract has been submitted for internal approval
3. Approved: Contract has been approved internally
4. Sent: Contract has been sent to the customer
5. Signed: Customer has signed the contract (signature captured via digital signature pad)
6. Active: Contract is live and in effect
7. Expiring: Contract is within 90 days of its end date (triggers workflow alerts)
8. Expired: Contract has reached its end date without renewal
9. Renewed: Contract has been renewed (a new contract is created linked to this one)

### Contract Tiers

- Bronze: Basic coverage with standard response times
- Silver: Enhanced coverage with improved response times and additional visits
- Gold: Comprehensive coverage including parts and labour
- Platinum: Premium coverage with fastest response times and full parts and labour inclusion
- Bespoke: Custom terms negotiated on a case-by-case basis

### Contract Types

- Service: Covers ongoing service and maintenance
- Supply: Covers equipment supply and delivery
- Maintenance: Covers preventive and corrective maintenance
- Umbrella: A master contract covering multiple sites and service types

### Contract Workflows (Step by Step)

1. Create: A new contract can be created standalone, from an opportunity (when a deal reaches a certain stage), or from an accepted quote. The contract is pre-populated with relevant details from the source record.

2. Add Sites: The user attaches the sites covered by the contract. Each site entry includes the site name, address, and any specific coverage notes.

3. Add Assets: The user attaches the equipment assets covered by the contract. Each asset entry specifies the asset name and the type of coverage (Full Coverage, Parts Only, Labour Only, or Inspection Only).

4. SLA Configuration: The user configures the service level agreement including response time (hours to acknowledge), resolution time (hours to resolve), whether parts are included in the contract, whether labour is included, the number of visits per year, and the preventive maintenance schedule.

5. Submit for Approval: When the contract is ready, it is submitted for approval. The submitter selects an approver and can add notes explaining the contract terms or any special considerations.

6. Approve or Reject: The approver reviews the contract and either approves it (advancing it to the Approved state) or rejects it (returning it to Draft with feedback notes). Decision notes are recorded on the approval record.

7. Sign: The contract is presented to the customer for signature. A canvas-based signature pad captures the signature, and the contract advances to the Active state.

8. Renew: When a contract is approaching expiry, the "Renew" action creates a new Draft contract linked to the original as a renewal. A renewal opportunity is also created in the pipeline. The original contract is marked as Renewed.

9. Sicon Sync: The contract can be pushed to the Sicon Service system, creating a corresponding service contract for engineer dispatch. The sync status is tracked on the contract record.

10. Sage Sync: The contract can be pushed to Sage 200 for financial record-keeping and invoice generation. The Sage reference is stored on the contract record.

### Contract Stats Dashboard

The contracts list view includes a statistics bar showing:
- Total number of contracts
- Number of Active contracts
- Number in Draft state
- Number Pending Approval
- Number Expiring Soon (within 90 days)
- Total Active Annual Value (sum of annual values for all active contracts)

Contracts can be filtered by status and searched by title, contract number, or company name.

## 8.10 Tender Engine

The Tender Engine helps sales teams respond to RFPs (Requests for Proposal) and ITTs (Invitations to Tender) using AI assistance.

AI-Powered Response Generation: Users upload a tender document, and GPT-5.2 analyses the requirements to generate a draft response. The AI considers the organisation's capabilities, past proposals, and the specific requirements of the tender.

Tender Parsing: The AI extracts key requirements, evaluation criteria, submission deadlines, and scoring weightings from uploaded tender documents.

Win Strategy Analysis: GPT-5.2 analyses the tender requirements against the organisation's strengths and weaknesses to recommend a win strategy, highlight competitive advantages, and flag potential risks.

Knowledge Base: Historical tender responses and proposals are stored for reference. The AI uses this knowledge base to improve the quality and consistency of future responses.

Status Tracking: Tenders progress through stages: Draft, In Progress, Review, Submitted, Won, Lost. Each stage change is recorded for reporting and analysis.

## 8.11 AI Tools

The CRM includes a suite of AI-powered tools accessible from the AI Tools module.

Lead Scoring: GPT-5.2 analyses contact data, interaction history, company fit, and engagement patterns to generate a lead score from 0 to 100. Higher scores indicate contacts more likely to convert into deals.

Email Generator: Given a context (e.g., "follow up on the quote sent last week"), the AI drafts a professional email with appropriate tone, content, and call-to-action.

Meeting Intelligence:
- Pre-Meeting Briefing: Generates a briefing document with company background, contact history, open deals, and suggested talking points
- Post-Meeting Summary: Summarises meeting notes into a structured format
- Action Items Extraction: Identifies and lists action items from meeting notes

Deal Insights: AI analyses a specific deal's data including stage history, activity frequency, competitor information, and comparable deals to provide:
- Deal health assessment (on track, at risk, stalled)
- Next best actions
- Risk factors
- Win probability estimate

Data Cleaning Report: AI scans the CRM database and identifies data quality issues including duplicate records, incomplete fields, formatting inconsistencies, and stale data. Provides a prioritised list of records that need attention.

## 8.12 Workflows (Automation Engine)

The Workflows module provides a rule-based automation engine for automating repetitive CRM tasks.

### Trigger Types (7)

1. Deal Stage Change: Fires when a deal moves to a specific pipeline stage
2. New Contact: Fires when a new contact is created
3. Quote Accepted: Fires when a quote is marked as accepted
4. Task Overdue: Fires when a task passes its due date without completion
5. Contract Expiring: Fires when a contract enters the 90-day expiry window
6. New Activity: Fires when a new activity is logged
7. Meeting Scheduled: Fires when a calendar meeting event is created

### Action Types (6)

1. Send Email: Sends an email to a specified recipient with templated content
2. Create Task: Creates a task assigned to a specified user with due date and priority
3. Update Field: Updates a field on a record (e.g., set contact status to "Active" when a deal is won)
4. Create Activity: Logs an activity record (e.g., system note when a workflow fires)
5. Send Notification: Sends an in-app notification to a specified user
6. Webhook: Sends an HTTP POST request to an external URL with event data

### Pre-Built Templates (4)

1. New Lead Nurture: When a new contact is created, creates a follow-up task and sends a welcome email
2. Deal Won Onboarding: When a deal reaches Closed Won, creates onboarding tasks and notifies the delivery team
3. Quote Follow-Up: When a quote is sent, creates a follow-up task for 3 days later
4. Contract Renewal Reminder: When a contract enters the 90-day expiry window, creates a renewal task and notifies the account manager

### Workflow Management

Each workflow can be set to active or inactive. Inactive workflows do not fire even when their trigger conditions are met. Workflow execution is logged with timestamps, showing which trigger fired, which actions were executed, and the outcome.

## 8.13 Documents

The Documents module organises CRM-related documents into sub-tabs:

Spec Sheets: Technical specification documents for products and equipment.
Pre-Install: Pre-installation survey documents, site readiness checklists, and preparation guides.
Maintenance: Maintenance schedules, procedures, and service manuals.
Manuals: User manuals, operation guides, and training materials.

Each document shows a view button (to open in browser) and a download button. Documents are scoped to the organisation. Only users with the Owner role can delete documents.

## 8.14 Settings

The CRM Settings module provides administrative controls:

Import: Data import tools for bringing external data into the CRM. Supports structured data import for contacts, companies, and deals.

Team Management: Add new CRM users, edit user details (full name, email, role, job title, phone number). The role dropdown allows assigning users as Owner, Manager, or Sales Rep. The system protects the Owner role hierarchy, preventing non-Owners from modifying Owner accounts.

Security: Two-factor authentication setup. Users can enable TOTP 2FA by scanning a QR code with their authenticator app. The setup process verifies the code before enabling 2FA.

Sage 200: Configuration for the Sage 200 ERP integration (currently mocked, awaiting live API keys).

Audit Log: A complete log of all CRM actions with timestamps, user names, action types, and affected entities. Provides full traceability of who did what and when.

---

# 9. Master Admin Portal

The Master Admin portal provides platform-wide governance and analytics. It is accessible from the GymAxis dashboard navigation bar for users with the is_master_admin flag.

## 9.1 Platform Dashboard

The platform dashboard provides a high-level overview of the entire GymAxis platform:

Total Users: Count of all users across all organisations (Service Portal and CRM combined).
Total Organisations: Count of all registered organisations.
Total Equipment: Count of all equipment items across all organisations.
Total Faults: Count of all faults logged across the platform.
Revenue: Monthly Recurring Revenue (MRR) and growth metrics.
Subscription Statistics: Breakdown of organisations by subscription tier.
Platform Health: System status indicators for backend, database, and integrations.

## 9.2 Organisation Management

Create Organisations: New organisations can be created with the following settings:
- Organisation Name
- Portal Type: Service Portal, CRM, or Both
- Industry
- Employee Count
- Website, Phone, Address
- Primary Contact details

Organisation Details: Each organisation record includes full contact details, subscription information, and configuration settings.

Subscription Tier: A dropdown allows setting the subscription tier (Free, Pro, Premium, Enterprise). Upgrading or downgrading triggers appropriate changes to feature access and billing.

Account Type: Full (GymAxis), Lite (Pulse Lite), or Pulse Pro. This determines which interface variant the organisation's users see.

Status Management: Organisations can be set to Active or Suspended. Suspended organisations cannot log in.

Feature Toggles: Granular control over which features are available to each organisation, grouped into categories:
- General: Documents, Gym Layouts, Reports, Check Sheets
- Service Portal: Sicon Integration, Capex Intelligence, Financial Operations
- CRM Modules: Pipeline, Quotes/CPQ, Tender Engine, AI Tools, Workflows, Documents

Test Flag: Organisations can be marked as test accounts. Test accounts are excluded from platform analytics and billing.

## 9.3 User Management

The Master Admin can manage all users across all organisations from a single interface.

User List: Shows all users with their name, email, organisation, role, and status.

Inline Role Editing: The role can be changed directly from the user list using a dropdown (Owner, Manager, Staff).

Edit User Dialog: A dialog for editing user details including Full Name, Email, Job Title, Phone, and Role.

Password Reset: Generate a temporary password for a user. The user will be prompted to change it on next login.

Disable/Enable: Temporarily disable a user account (preventing login) or re-enable it.

Archive/Unarchive: Archive inactive users to keep the user list clean. Archived users cannot log in but their data is preserved.

Add Users: Create new users within an organisation. The system automatically routes the user to the correct database collection (Service Portal or CRM) based on the organisation's portal type.

## 9.4 CRM Analytics

Cross-Organisation Metrics: Platform-wide CRM performance data aggregated across all organisations.

Pipeline Analytics: Total pipeline value by stage, weighted forecast, average deal size, and deal velocity.

Quote Analytics: Quote volume by status, total quoted value, acceptance rate, and average quote turnaround time.

User Distribution: Breakdown of CRM users by role across the platform.

Activity Breakdown: Volume of activities by type (email, call, meeting, task, note) across all organisations.

Recent Activity: The latest deals and activities across the platform for monitoring.

Workflow Statistics: Number of active workflows, total executions, and success rates.

Tender Statistics: Tender volumes by status, win rate, and average response time.

## 9.5 Other Admin Modules

Payments: Stripe payment tracking across all organisations. View payment history, subscription status, and revenue.

Pulse Management: Pulse-specific organisation settings and configuration.

Spec Sheets: Global spec sheet management across all organisations.

Support: Platform support tools for handling user queries and issues.

Emails: Email system monitoring showing send volumes, delivery rates, and any failures.

Documents: Global document management across all organisations.

---

# 10. Supplier Collaboration Portal

The Supplier Collaboration Portal is a public, no-login-required interface that enables equipment suppliers to interact with gym operators about equipment faults.

## 10.1 How Suppliers Access the Portal

Each supplier case has a unique token that forms the URL: /supplier/case/{token}

Suppliers access the portal in two ways:
1. Email Link: When a gym operator sends a message about a fault, the supplier receives an email containing a "View and Reply" button that links to their case page.
2. Direct Link: The "Supplier Card" button in the gym's fault detail panel opens the supplier portal in a new browser tab.

No account or login is required. The unique token provides secure access to the specific case.

## 10.2 Supplier Case Page Features

Header: Displays the site name, current status badge, and a visual progress bar showing the case progression: Pending, Acknowledged, Engineer Scheduled, In Progress, Parts Ordered, Completed.

Schedule Engineer Visit: A form allowing the supplier to schedule an engineer visit with:
- Date (date picker)
- Engineer Name
- Notes (any special instructions or requirements)
When a visit is scheduled, a comment is automatically posted to the conversation and the gym receives an email notification.

Fault Details Section: Shows the equipment type, serial number, severity (colour-coded badge), fault description, and the date the fault was reported.

Equipment Information: Manufacturer, model, and location within the facility.

Fault Photos and Videos: A media gallery displaying all photos and videos attached to the original fault report. Images can be viewed in a lightbox.

### Two-Way Messaging (iMessage-Style Chat)

The messaging interface uses an iMessage-inspired design:
- Blue Bubbles (right-aligned): Messages from the supplier
- Green Bubbles (left-aligned): Messages from the gym operator

Name Confirmation Step: Before the supplier can send their first message, they must enter their name and click "Continue". This prevents accidental single-character messages and ensures all messages have a proper sender name attributed to them.

Attachments: Both parties can attach photos, videos, and documents to their messages.

Status Update: The supplier can update the case status from the portal, progressing it through the defined stages.

Status History: A collapsible timeline showing all status changes with dates and times.

Satisfaction Rating: Once a case reaches the Completed status, a satisfaction rating widget appears allowing the gym operator to rate the supplier's service from 1 to 5 stars with optional written feedback.

## 10.3 Two-Way Communication Workflow

### Gym to Supplier Communication

Step 1: The gym user navigates to a fault's detail panel and finds the Supplier Communication section.

Step 2: If no supplier email is stored for this fault, the user is prompted to enter the supplier's email address. The email is validated before proceeding.

Step 3: The system automatically creates a supplier case if one does not already exist. The case is created with the site name (not the organisation name) for clarity, along with the fault details and supplier contact information.

Step 4: The user's message is posted as a comment on the supplier case.

Step 5: An email is sent to the supplier via Resend:
- From Address: faults@service.gymaxisai.com
- From Name: The site name (e.g., "Tottenham Green Leisure Centre")
- Content: The message text with a "View and Reply" button linking to the supplier portal
- Footer: "Do not reply to this email - use the View and Reply button above to respond"

### Supplier to Gym Communication

Step 1: The supplier clicks the "View and Reply" link in the email they received, which opens the supplier case portal page.

Step 2: The supplier enters their name and clicks "Continue" to confirm.

Step 3: The supplier types their message and optionally attaches photos, videos, or documents.

Step 4: An email is sent to the gym contact via Resend:
- From Address: faults@service.gymaxisai.com
- From Name: "{Supplier Name} via GymAxis"
- Content: The message text with a "View and Reply" button
- Footer: "Do not reply to this email - use the View and Reply button above to respond"

Step 5: The message appears in the gym's fault detail panel in the Supplier Communication section.

### Display in Fault Detail Panel

The last 2 messages from either party are shown by default in the fault detail panel. If there are 3 or more messages, a "Conversation History" button appears. Clicking this button expands a scrollable thread showing the complete conversation. A "Supplier Card" button opens the full supplier portal page in a new browser tab.

---

# 11. Integration Hub (Event Bus)

The Integration Hub is an event-driven message bus that connects all platform systems, ensuring data consistency and enabling automated cross-system workflows.

## 11.1 Event Types

The following events are published and processed by the Integration Hub:

service_issue_created: Published when a new fault is logged in the Service Portal. Target: CRM. Action: Creates a corresponding service case in the CRM's Cases tab for the relevant company.

service_issue_updated: Published when a fault status changes in the Service Portal. Target: CRM. Action: Updates the linked CRM service case with the new status.

engineer_ber_flagged: Published when an engineer flags equipment as Beyond Economical Repair (BER). Target: CRM. Action: Creates a replacement opportunity in the CRM pipeline.

deal_closed_won: Published when a deal reaches the Closed Won stage in the CRM. Target: Service Portal. Action: Creates a sales order in the Service Portal for fulfilment.

quote_accepted: Published when a quote is accepted in the CRM. Target: Finance. Action: Creates an order record ready for invoicing.

invoice_created: Published when an invoice is generated. Target: CRM. Action: Links the invoice to the associated deal record.

payment_received: Published when a payment is processed. Target: Finance. Action: Records the payment against the outstanding invoice.

account_on_hold: Published when a finance hold is placed on an account. Target: Service Portal. Action: Flags the account in the Service Portal to alert service staff.

contract_activated: Published when a contract reaches the Active state. Target: Service Portal. Action: Enables contract coverage for the associated sites and equipment.

asset_end_of_life: Published when equipment reaches its predicted end of life. Target: CRM. Action: Creates a replacement opportunity in the pipeline.

## 11.2 Event Processing Pipeline

Events follow a four-stage processing pipeline:

1. Publish: The source system publishes an event with a type, payload, source system identifier, and priority level.
2. Route: The Integration Hub routes the event to the appropriate target system based on the event type.
3. Execute: The target system processes the event and performs the required action.
4. Log: The event and its outcome are logged in the integration_events collection for audit and troubleshooting.

### Processing Features

Automatic Retry: Failed events are retried with exponential backoff (increasing delays between retry attempts).

Priority Levels: Events are prioritised as urgent, high, normal, or low. Higher-priority events are processed first.

Health Monitoring: An API endpoint provides the current health status of the Integration Hub including queue depth, processing rates, and error rates.

### Source-of-Truth Rules

To prevent data conflicts, each system is the authoritative source for specific data domains:
- CRM: Owns commercial data (deals, quotes, contracts, contacts, companies)
- Sage 200: Owns financial data (invoices, payments, ledger entries)
- Service Portal: Owns operational data (equipment, faults, check sheets, supplier cases)

---

# 12. Email System (Resend)

The platform uses Resend as its email service provider, with a verified sending domain for professional email delivery.

## 12.1 Configuration

Domain: service.gymaxisai.com (verified and sending-enabled in Resend)
From Address: faults@service.gymaxisai.com
Dynamic From Name: The sender name changes based on context, using the site name for supplier notifications (e.g., "Tottenham Green Leisure Centre") or the supplier name for gym notifications (e.g., "Precor UK via GymAxis").

## 12.2 Email Flows

The platform sends emails in the following scenarios:

1. Fault to Supplier Notification: When a gym operator sends a message about a fault through the Supplier Communication section of a fault detail panel. The email contains the message text, fault details, equipment information, and a "View and Reply" button linking to the supplier portal.

2. Supplier to Gym Notification: When a supplier replies through the supplier portal. The email contains the supplier's message and a "View and Reply" button linking to the fault detail in the Service Portal.

3. Engineer Scheduled Notification: Automatically sent when a supplier schedules an engineer visit through the supplier portal. The email informs the gym contact of the scheduled date, engineer name, and any notes.

4. Purchase Order Email: When a purchase order is created, the supplier receives an email with the PO details including line items, quantities, unit prices, and total value formatted as a professional document.

5. Password Reset Email: When a user requests a password reset (available for both Service Portal and CRM accounts). The email contains a time-limited link to the password reset page.

## 12.3 Email Template Features

All emails use professional HTML templates with the following features:
- GymAxis branding and colour scheme
- Equipment details displayed in a structured table format
- Severity badges with colour coding matching the platform (Critical=red, High=orange, Medium=yellow, Low=green)
- Prominent "View and Reply" call-to-action button
- Footer notice: "Do not reply to this email - use the View and Reply button above to respond"
- Responsive design that renders correctly on mobile devices and desktop email clients

---

# 13. PWA - Progressive Web App

The platform supports installation as a Progressive Web App, providing a native app-like experience on mobile devices and desktop.

## 13.1 Install Prompt

After logging in (to either the Service Portal or CRM), users are shown an "Add GymAxis to Home Screen" banner. The behaviour differs by platform:

Android: The native browser install dialog is triggered via the beforeinstallprompt API. The user taps "Install" and the app is added to their home screen.

iOS (Safari): A step-by-step guide is shown with instructions:
1. Tap the Share button (square with arrow)
2. Scroll down and tap "Add to Home Screen"
3. Tap "Add" to confirm

The banner includes a "Later" button that dismisses the prompt. The dismissal is persisted in localStorage so the banner does not reappear for that user.

## 13.2 Standalone Mode

When launched from the home screen, the app runs in standalone mode without browser chrome (address bar, navigation buttons). This provides a cleaner, more focused experience that feels like a native application.

## 13.3 Persistent Sessions

In PWA standalone mode, authentication tokens are stored in localStorage, which persists across app restarts. This means users remain logged in between sessions. Both the Service Portal token and the CRM token are preserved, allowing dual-system users to switch between workspaces without re-authenticating.

## 13.4 Offline Caching

The service worker caches static assets (JavaScript bundles, CSS files, fonts, and images) for fast loading and basic offline support. The caching strategy is network-first for navigation requests (always tries to fetch the latest content from the server, falling back to the cache if the network is unavailable) and cache-first for static assets (serves from cache for speed, updating the cache in the background).

## 13.5 Web App Manifest

The manifest configures the installed app with:
- Name: GymAxis AI
- Short Name: GymAxis
- Theme Colour: #0A0A0A (dark)
- Background Colour: #0A0A0A (dark)
- Display: Standalone
- Orientation: Portrait

---

# 14. Data Models Reference

This section documents every MongoDB collection used by the platform, with field descriptions.

## 14.1 Service Portal Collections

users: Platform user accounts.
Fields: id, email, password (bcrypt hashed), full_name, organization_id, role (owner/manager/staff), account_type (full/lite/pulse_pro), is_master_admin, created_at, last_login.

organizations: Registered organisations.
Fields: id, name, portal_type (service/crm/both), subscription_tier (free/pro/premium/enterprise), account_type, features (object with boolean toggles), branding, industry, employee_count, website, phone, address, primary_contact, is_test, status, created_at.

sites: Physical facility locations.
Fields: id, name, organization_id, address, phone, manager, created_at.

equipment: Equipment register.
Fields: id, name, type, manufacturer, model, serial_number, location, installation_date, warranty_expiry, supplier, site_id, organization_id, status, created_at.

issues: Fault records.
Fields: id, serial_number, machine_type, issue_description, severity (critical/high/medium/low), status (open/in_progress/resolved), supplier, supplier_email, ai_triage (object with diagnosis, repair_steps, parts, time_estimate), resolution_type, resolution_notes, photos, videos, steps_taken, user_id, organization_id, site_id, supplier_case (embedded reference), created_at, resolved_at.

supplier_cases: Supplier collaboration cases.
Fields: id, issue_id, token (unique URL token), supplier_name, supplier_email, organization_name, site_contact_email, current_status, scheduled_date, engineer_name, schedule_notes, rating, rating_feedback, created_at.

supplier_case_comments: Messages in supplier cases.
Fields: id, case_id, author_name, author_role (gym/supplier), message, attachments (array of file objects), created_at.

check_sheet_templates: Check sheet template definitions.
Fields: id, name, description, items (array of check items), organization_id, created_by, created_at.

check_sheet_completions: Completed check sheet records.
Fields: id, template_id, equipment_id, responses (array of item results), completed_by, organization_id, created_at.

gym_layouts: Digital floor plans.
Fields: id, name, equipment_positions (array of positioned items), organization_id, created_by, created_at.

spec_sheets: Equipment specification documents.
Fields: id, name, manufacturer, dimensions, weight, power, maintenance_intervals, file_url, organization_id, created_at.

purchase_orders: Purchase orders.
Fields: id, po_number, issue_id, supplier_name, supplier_email, items (array: description, quantity, unit_price), total, organization_id, created_by, status, created_at.

risk_assessments: Risk assessment records.
Fields: id, title, description, hazards (array), controls (array), likelihood, severity, risk_level, organization_id, created_by, created_at.

password_reset_tokens: Temporary password reset tokens.
Fields: id, user_id, token, expires_at (TTL indexed), created_at.

## 14.2 CRM Collections

crm_users: CRM user accounts.
Fields: id, email, password (bcrypt hashed), full_name, organization_id, role (owner/admin/manager/sales_rep), job_title, phone, totp_secret (encrypted, optional), totp_enabled, created_at, last_login.

crm2_companies: Company records.
Fields: id, name, company_number, directors (array), industry, employee_count, website, phone, address, organization_id, created_by, created_at, updated_at.

crm2_contacts: Contact records.
Fields: id, first_name, last_name, email, phone, job_title, company_id, linkedin_url, source, is_decision_maker, organization_id, created_by, created_at, updated_at.

crm2_opportunities: Deal/opportunity records.
Fields: id, title, value, stage, company_id, contact_id, probability, weighted_value, expected_close_date, source, competitor, next_step, organization_id, created_by, created_at, updated_at.

crm2_activities: Activity records.
Fields: id, type (email/call/meeting/task/note), subject, body, company_id, contact_id, opportunity_id, duration, outcome, follow_up_date, location, attendees, due_date, priority, organization_id, created_by, created_at.

crm2_quotes: Quote records.
Fields: id, quote_number, company_id, company_name, contact_id, contact_name, items (array: description, quantity, unit_price, discount), total, status (draft/sent/accepted/expired/superseded), signature (base64 image data), parent_quote_id, version, created_by, organization_id, created_at, updated_at.

crm2_contracts: Contract records.
Fields: id, contract_number, title, type (service/supply/maintenance/umbrella), tier (bronze/silver/gold/platinum/bespoke), status, company_id, company_name, opportunity_id, quote_id, annual_value, start_date, end_date, sla (object: response_hours, resolution_hours, parts_included, labour_included, visits_per_year, preventive_maintenance), sicon_contract_id, sicon_sync_status, sage_reference, sage_sync_status, signed_by, signature, organization_id, created_by, created_at, updated_at.

crm2_contract_sites: Sites linked to contracts.
Fields: id, contract_id, site_name, address, notes, created_at.

crm2_contract_assets: Assets linked to contracts.
Fields: id, contract_id, asset_name, serial_number, coverage_type (full/parts_only/labour_only/inspection), notes, created_at.

crm2_contract_approvals: Contract approval records.
Fields: id, contract_id, status (pending/approved/rejected), decision, decision_notes, submitted_by, submitted_by_name, approver_id, approver_name, submitted_at, decided_at.

crm2_workflows: Workflow definitions.
Fields: id, name, description, trigger (object: type, conditions), actions (array of action objects), active (boolean), organization_id, created_by, created_at, updated_at.

crm2_workflow_runs: Workflow execution logs.
Fields: id, workflow_id, workflow_name, status (success/failed), trigger_context, actions_executed, error, organization_id, executed_at.

crm2_tenders: Tender records.
Fields: id, title, description, status (draft/in_progress/review/submitted/won/lost), requirements, ai_response, win_strategy, deadline, organization_id, created_by, created_at, updated_at.

crm2_orders: Order records (from won deals).
Fields: id, opportunity_id, company_id, items, total, status (pending_sync/synced/failed), sage_reference, organization_id, created_at.

crm2_calendar_events: Calendar event records.
Fields: id, title, description, type (meeting/call/task/follow_up), date, end_date, staff_id, staff_name, organization_id, created_at.

## 14.3 Integration Collections

integration_events: Event bus records.
Fields: id, event_type, source_system, target_system, entity_type, entity_id, status (pending/processing/completed/failed), payload (object), priority (urgent/high/normal/low), retry_count, error, created_at, processed_at.

---

# 15. API Reference Summary

Total Endpoints: 422 across 42 route modules.

## 15.1 Service Portal APIs (prefixed /api/)

Authentication (/auth): Registration, login, password reset, staff management, profile update. 16 endpoints covering the complete user lifecycle.

Equipment (/equipment): Full CRUD operations, CSV import and export, equipment statistics, manual uploads, AI image recognition. 18 endpoints.

Issues (/issues): Fault CRUD, AI triage, photo/video attachments, contact supplier workflow, status updates, resolution tracking. 8 endpoints.

Supplier Portal (/supplier): Supplier case management, comments from both gym and supplier sides, engineer scheduling, status updates, satisfaction rating. 21 endpoints total.

Check Sheets (/check-sheets): Template management, completion recording, compliance reports. 12 endpoints.

Gym Layouts (/gym-layouts): Floor plan CRUD, equipment positioning, AI detection from uploaded images, dimension management. 7 endpoints.

Sites (/sites): Multi-site management including CRUD operations and site-scoped data filtering. 5 endpoints.

Reports (/reports): Resolution statistics, equipment summaries, operational reports. 3 endpoints.

Sicon (/sicon): Service integration configuration, connection testing, issue sync, case types and engineer retrieval. 10 endpoints.

Spec Sheets (/spec-sheets): Searchable spec sheet library with CRUD, filtering, and download capabilities. 10 endpoints.

Purchase Orders (/purchase-orders): PO creation, line item management, supplier notification, PO defaults. 10 endpoints.

Risk Assessments (/risk-assessments): Manual creation, AI generation from description, AI generation from photo. 5 endpoints.

Financial Operations (/financial-ops): Financial configuration, cost centre management, reserve tracking, burn rate analysis, Stripe onboarding. 14 endpoints.

Capex (/capex): Capital expenditure tracking, lifecycle cost analysis, replacement planning. 6 endpoints.

Compliance (/compliance): GDPR data export, consent management, data retention, audit log. 7 endpoints.

Files (/files): File upload, download, categorisation, and management. 8 endpoints.

QR Codes (/qr-codes): QR code generation, public equipment information pages, public fault submission. 6 endpoints.

Payments (/payments): Stripe checkout session creation, subscription management, payment history. 5 endpoints.

Health Score (/health-score): Equipment health calculation algorithm. 1 endpoint.

## 15.2 CRM APIs (prefixed /api/crm/)

Authentication (/auth): CRM-specific login, registration, 2FA setup and verification, password reset. 10 endpoints.

Activities (/v2/activities): Activity feed CRUD with type-specific fields. 4 endpoints.

Companies (/v2/companies): Company CRUD with Companies House integration and 11-tab data retrieval. 5 endpoints.

Contacts (/v2/contacts): Contact CRUD with company assignment and activity history. 5 endpoints.

Opportunities (/v2/opportunities): Deal/pipeline management with Kanban and list views. 6 endpoints.

Dashboard (/v2/dashboard): Role-based analytics and metrics. 1 endpoint.

Cases (/v2/cases): Service case tracking linked from Integration Hub. 2 endpoints.

Assets (/v2/assets): Asset register management. 2 endpoints.

Quotes (/v2/quotes): Full CPQ with versioning, signatures, approval, and Stripe payment links. 8 endpoints.

Contracts (/v2/contracts): Complete contract lifecycle management with sites, assets, SLA, approvals, signatures, renewal, and external sync. 22 endpoints.

Workflows (/v2/workflows): Automation engine management and execution. 8 endpoints.

Tenders: AI-powered tender response management (via crm_v2 module).

Calendar: Calendar event management (via crm_v2 module).

Core (/core): Team management, user CRUD, audit log, import tools. 25 endpoints.

AI Tools (/ai): Lead scoring, email generation, meeting intelligence, deal insights, data cleaning. 8 endpoints.

Documents (/documents): CRM document management with categorisation. 4 endpoints.

Sage 200 (/sage200): Sage 200 ERP configuration and sync. 5 endpoints.

Inbox (/inbox): Activity feed and inbox management. 6 endpoints.

## 15.3 Master Admin APIs (prefixed /api/master-admin/)

Organisation management: CRUD, feature toggles, subscription tier management, account type changes, status management.

User management: Cross-organisation user listing, inline role editing, password reset, disable/enable, archive/unarchive, user creation.

Analytics: Platform statistics, CRM analytics, cross-organisation metrics.

Total: 27 endpoints.

## 15.4 Integration APIs (prefixed /api/)

Integration Hub (/integration/events): Event publishing, event retrieval, health monitoring, processing status. 4 endpoints.

---

# 16. Glossary

AI Triage: The automated process where GPT-5.2 analyses a fault description and any attached media to provide a diagnosis, repair steps, parts list, and time estimate.

BER (Beyond Economical Repair): A status applied to equipment when the cost of repair exceeds the value of the equipment, triggering a replacement workflow.

CPQ (Configure, Price, Quote): The process and toolset for creating sales quotes with configurable products, pricing, and discounting.

CRM (Customer Relationship Management): The commercial operations system for managing sales pipelines, contacts, companies, quotes, contracts, and tenders.

CSV (Comma-Separated Values): A file format used for bulk data import and export of equipment records.

Event Bus: The Integration Hub's message routing system that connects the Service Portal, CRM, and external systems.

Feature Toggle: A configuration setting that enables or disables a specific feature for an organisation, controlled from the Master Admin portal.

Integration Hub: The event-driven system that routes data between the Service Portal, CRM, Sage 200, and Sicon.

JWT (JSON Web Token): The token format used for authentication in both the Service Portal and CRM.

Kanban: A visual project management method using columns to represent stages, used for the CRM pipeline view.

MTBF (Mean Time Between Failures): A reliability metric tracking the average time between equipment faults.

MRR (Monthly Recurring Revenue): A key business metric tracking the total recurring revenue per month from all subscriptions.

Parity Rule: The requirement that any feature added to GymAxis must also be available in Pulse Fitness Pro, and vice versa.

PWA (Progressive Web App): A web application that can be installed on a device and run in standalone mode, providing a native app-like experience.

QR Code: A machine-readable code assigned to each piece of equipment, enabling public fault reporting by scanning with a mobile device.

Resend: The email service provider used for all platform email communications.

Sage 200: An Enterprise Resource Planning (ERP) system used for financial management and accounting. Integration is currently mocked.

Sicon: A service management system used for engineer dispatch and service case tracking. Integration is currently mocked.

SLA (Service Level Agreement): The agreed service standards defined in a contract, including response times, resolution times, and coverage levels.

Supplier Case: A collaboration record linking a fault to a supplier, enabling two-way communication through the Supplier Collaboration Portal.

TOTP (Time-based One-Time Password): A two-factor authentication method using a time-based code generated by an authenticator app.

Universal Login: The platform's login system that authenticates against both the Service Portal and CRM simultaneously, directing users to the appropriate system.

---

Document generated April 2026 - GymAxis AI Platform v1.0
