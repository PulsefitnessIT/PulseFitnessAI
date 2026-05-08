# GymAxis Marketing Site (iter 215an–215aq)

Brand & design tokens — see `/app/design_guidelines.json`.

Pages:
- `/` → `<MarketingHome />` (this dir / Home.jsx)
- `/platform/service` → `<ServicePage />`
- `/platform/crm` → `<CRMPage />`
- `/platform/memberships` → `<MembershipsModulePage />`
- `/platform/marketing` → `<MarketingModulePage />`
- `/platform/staffing` → `<StaffingPage />`
- `/platform/reporting` → `<ReportingPage />`

All module pages share the `<ModulePage>` template (same 8-section structure):
HERO → PROBLEM/SOLUTION → FEATURES → VISUAL SECTIONS → AI → INTEGRATIONS → RESULTS → CTA

Each module has its own accent color from the blue→purple range:
- service: #06B6D4 (cyan)
- crm: #6366F1 (indigo)
- memberships: #8B5CF6 (violet)
- marketing: #D946EF (fuchsia)
- staffing: #A855F7 (purple)
- reporting: #2563EB (blue)
