"""Feature routes: check sheets, AI, reports, imports, KPI, PPM, QR, Sicon, etc.

Some features are `account_type`-gated via `require_feature`. The gating table lives
here so adding/removing gates is a one-line edit without touching individual routers.
"""
from fastapi import APIRouter, Depends

from utils.feature_guard import require_feature

from routes.check_sheets import router as check_sheets_router
from routes.reports import router as reports_router
from routes.ai_diagnosis import router as ai_diagnosis_router
from routes.risk_assessments import router as risk_assessments_router
from routes.purchase_orders import router as purchase_orders_router
from routes.suppliers import router as suppliers_router
from routes.suppliers_catalogue import router as suppliers_catalogue_router
from routes.digest import router as digest_router
from routes.onboarding import router as onboarding_router
from routes.gym_layouts import router as gym_layouts_router
from routes.health_score import router as health_score_router
from routes.supplier_portal import router as supplier_portal_router
from routes.qr_codes import router as qr_codes_router
from routes.sicon import router as sicon_router
from routes.sicon_mapping import router as sicon_mapping_router
from routes.expiry_alerts import router as expiry_alerts_router
from routes.integrations import router as integrations_router
from routes.capex import router as capex_router
from routes.financial_ops import router as financial_ops_router
from routes.equipment_import import router as equipment_import_router
from routes.sites_import import router as sites_import_router
# Iter 216h138 — MOD-specific bulk-import pipeline (1000+ sites)
from routes.mod_sites_bulk_import import router as mod_sites_bulk_import_router
from routes.invoice_wizard_parse import router as invoice_wizard_parse_router
from routes.spec_sheets import router as spec_sheets_router
from routes.compliance import router as compliance_router
from routes.kpi_engine import router as kpi_router
from routes.ppm_engine import router as ppm_router
from routes.pulse_upgrade import router as pulse_upgrade_router
from routes.contact import router as contact_router
from routes.mod_portal import router as mod_portal_router
from routes.mod_compliance import router as mod_compliance_router
from routes.mod_incidents import router as mod_incidents_router
from routes.memberships import router as memberships_router
from routes.memberships_payments import router as memberships_payments_router
from routes.instructor_portal import router as instructor_portal_router
from routes.memberships_ops import router as memberships_ops_router
from routes.memberships_analytics import router as memberships_analytics_router
from routes.memberships_promotions import router as memberships_promotions_router
from routes.memberships_family import router as memberships_family_router
from routes.memberships_calendar import router as memberships_calendar_router
from routes.memberships_public import router as memberships_public_router
from routes.memberships_phase3 import router as memberships_phase3_router
from routes.memberships_ai import router as memberships_ai_router
from routes.memberships_phase4 import router as memberships_phase4_router
from routes.memberships_phase6 import router as memberships_phase6_router
from routes.help import router as help_router
from routes.staffing import router as staffing_router
from routes.staffing_clock import router as staffing_clock_router
from routes.staffing_comms import router as staffing_comms_router
from routes.staffing_tasks import router as staffing_tasks_router
from routes.staffing_hr import router as staffing_hr_router
from routes.staffing_ai_phase6 import router as staffing_ai_phase6_router
from routes.crm_setup import router as crm_setup_router
from routes.master_admin_estate_rollup import router as master_admin_estate_rollup_router
from routes.back_in_service import router as back_in_service_router
from routes.marketing_chat import router as marketing_chat_router
from routes.master_admin_sales_insights import router as master_admin_sales_insights_router
from routes.launch_readiness import router as launch_readiness_router
from routes.member_app_builder import router as member_app_builder_router
from routes.portal_gdpr import router as portal_gdpr_router
from routes.usage_meter import router as usage_meter_router
from routes.notification_prefs import router as notification_prefs_router
from routes.feedback import router as feedback_router
from routes.saved_searches import router as saved_searches_router
from routes.csv_export import router as csv_export_router
from routes.help_search import router as help_search_router
from routes.account_billing import router as account_billing_router
from routes.lifecycle_emails_admin import router as lifecycle_emails_admin_router
from routes.admin_refunds import router as admin_refunds_router
from routes.partners import router as partners_router

# Iter 215dn — Service Operations Phase 1 (replaces Sicon Service)
from routes.svc.cases import router as svc_cases_router
from routes.svc.intake import router as svc_intake_router
from routes.svc.desk import router as svc_desk_router
# Iter 215dp — Phase 2 Engineer Mobile API
from routes.svc.engineer import router as svc_engineer_router
from routes.svc.engineers_admin import router as svc_engineers_admin_router
from routes.svc.engineer_quotes import router as svc_engineer_quotes_router
from routes.svc.engineer_invoices import router as svc_engineer_invoices_router
from routes.svc.engineer_invoice_payments import (
    router as svc_engineer_invoice_payments_router,
    public_router as svc_engineer_invoice_payments_public_router,
)
# Iter 216h132 — Stripe Connect (Express) for Engineer Partners
from routes.svc.engineer_stripe_connect import (
    router as svc_engineer_stripe_connect_router,
    public_router as svc_engineer_stripe_connect_public_router,
)
# Iter 216h133 — Engineer App Phase 3 (mileage, parts-used, invoice-from-job)
from routes.svc.engineer_phase3 import router as svc_engineer_phase3_router
# Iter 216h134 — Engineer App AI Report Assistant (Whisper + GPT-5.2)
from routes.svc.engineer_ai import router as svc_engineer_ai_router
# Iter 216h136 — Engineer App Phase 3.5: parts-request workflow
from routes.svc.engineer_parts_requests import (
    engineer_router as svc_engineer_parts_requests_router,
    admin_router as svc_engineer_parts_requests_admin_router,
)
# Iter 215dq — Phase 3 Scheduler + Parts catalogue
from routes.svc.parts import router as svc_parts_router
from routes.svc.scheduler import router as svc_scheduler_router
# Iter 215dr — Phase 4 Inventory deepening (reorder, low-stock, POs)
from routes.svc.inventory import router as svc_inventory_router
# Iter 220ea·19 — Engineer App Phase 5: Stock Control hub (engineer reads)
from routes.svc.engineer_stock import router as svc_engineer_stock_router
# Iter 220ea·20 — Phase 5b: Parts Catalogue + Bulk Import
from routes.svc.parts_catalogue import router as svc_parts_catalogue_router
from routes.svc.parts_import import router as svc_parts_import_router
# Iter 220ea·22 — Phase 4: Office/Admin stock overview
from routes.svc.admin_stock import router as svc_admin_stock_router
# Iter 220ea·26 — G1: Canonical CRM customer link (search + backfill)
from routes.svc.customer_links import router as svc_customer_links_router
# Iter 215ds — Phase 5 AI Assistant Layer (Claude Sonnet 4.5)
from routes.svc.ai import router as svc_ai_router
# Iter 215dt — Phase 6 Quoting & Billing
from routes.svc.billing import router as svc_billing_router
# Iter 215du — Phase 7 Reports & Audit dashboards
from routes.svc.reports import router as svc_reports_router
# Iter 254 — Owner Analytics (SLA compliance, utilisation, revenue/job)
from routes.svc.analytics import router as svc_analytics_router
# Iter 255 — Migration import wizard (customers/sites + historical cases)
from routes.svc.imports import router as svc_imports_router
# Iter 256 — Provider-native desk Customers tab
from routes.svc.desk_customers import router as svc_desk_customers_router
# Iter 215dv — Phase 7b Customer Comms Hub
from routes.svc.comms import router as svc_comms_router
# Iter 216y — Phase 6+ Saved Views
from routes.svc.views import router as svc_views_router
# Iter 215dy — Phase 8 D Integrations admin console
from routes.svc.integrations.health import router as svc_integrations_health_router
# Iter 216h82 — Customer-facing per-job Service Report PDF + email
from routes.svc.service_report import router as svc_service_report_router
from routes.svc.legacy_reports import router as svc_legacy_reports_router
# Iter 216h83 — Public customer live-tracking
from routes.svc.public_tracking import router as svc_public_tracking_router
# Iter 216h89 — Pre-job H&S / RAMS signoff
from routes.svc.safety import router as svc_safety_router
# Iter 220de — Compliance Pack (PTW, COSHH, LOTO)
from routes.svc.compliance import router as svc_compliance_router
# Iter 220dg — Engineer outbound ETA push to customer
from routes.svc.engineer_eta_update import router as svc_eta_update_router
# Iter 220dh — Master Admin unified Pending Review queue
from routes.master_admin_pending_review import router as mad_pending_review_router
# Iter 220dm — PPM-due reminder sweeper
from routes.svc.ppm_reminders import router as svc_ppm_reminders_router
# Iter 216h91 — Engineer live location ping
from routes.svc.engineer_location import router as svc_engineer_location_router
# Iter 216h93 — Comprehensive platform vitals (master-admin only)
from routes.health_full import router as health_full_router
# Iter 216h140 — Engineer Diary & Admin Dispatch (Phase 4)
from routes.svc.diary import (
    engineer_router as svc_diary_engineer_router,
    admin_router as svc_diary_admin_router,
)
# Iter 216h142 — Engineer Notifications + Web Push (Phase 4 / Slice 2)
from routes.svc.notifications import router as svc_notifications_router
# Iter 216h144 — Engineer independence (self-create + supplier card)
from routes.svc.independence import (
    engineer_router as svc_independence_router,
    public_router as svc_intake_public_router,
)
# Iter 216h147 — Engineer self-claim queue
from routes.svc.engineer_queue import router as svc_engineer_queue_router
# Iter 216h146 — Inbound email webhook
from routes.svc.inbound_email import (
    public_router as svc_inbound_email_public_router,
    engineer_router as svc_inbound_email_engineer_router,
)
# Iter 216h259 — Engineer Lite CRM (saved customers, shared org-wide)
from routes.svc.engineer_customers import router as svc_engineer_customers_router
# Iter 220 — Work Report custom fields (engineer + admin configurable)
from routes.svc.work_report_fields import router as svc_work_report_fields_router
# Iter 220ec — Configurable case types (Repair / PPM / custom)
from routes.svc.case_types import router as svc_case_types_router
# Iter 220d — Per-machine work reports + quick-add note presets
from routes.svc.per_machine_reports import router as svc_per_machine_reports_router
# Iter 220ci — Engineer-side strict-validation equipment create
from routes.svc.engineer_equipment import router as svc_engineer_equipment_router
# Iter 220g — Smart scheduling suggestions (proximity-based)
from routes.svc.scheduling_suggestions import router as svc_scheduling_router
# Iter 220i — Engineer / org branding (logo + colours for PDF + portal)
from routes.svc.branding import router as svc_branding_router
# Iter 220j — Engineer attention digest (pulsing-dot data source)
from routes.svc.attention import router as svc_attention_router
# Iter 220l — Engineer self-service ratings view
from routes.svc.engineer_ratings import router as svc_engineer_ratings_router
# Iter 220s — Unified Accident, Near-Miss, Hazard, RIDDOR module
from routes.incidents import router as incidents_router


# Routers that require a specific `account_type` feature to be enabled.
# Pulse Lite / Pulse Pro orgs are 403'd unless the master admin has granted the feature.
_GYMAXIS_ONLY_ROUTERS = (
    (kpi_router, "kpi_engine"),
    (sicon_router, "sicon_integration"),
    (sicon_mapping_router, "sicon_integration"),
)

# Routers shared across all tiers but still individually toggleable per-org.
_PER_ORG_GATED_ROUTERS = (
    (ppm_router, "ppm_engine"),
)

# Routers available to every logged-in user regardless of account type.
_UNGATED_ROUTERS = (
    check_sheets_router, reports_router, ai_diagnosis_router,
    risk_assessments_router, purchase_orders_router, suppliers_router,
    suppliers_catalogue_router,
    digest_router, onboarding_router, gym_layouts_router,
    health_score_router, supplier_portal_router, qr_codes_router,
    expiry_alerts_router, integrations_router,
    capex_router, financial_ops_router, equipment_import_router, sites_import_router, mod_sites_bulk_import_router, invoice_wizard_parse_router,
    spec_sheets_router, compliance_router,
    pulse_upgrade_router, contact_router, mod_portal_router, mod_compliance_router, mod_incidents_router,
    # Iter 215bm — phase3 router MUST be registered BEFORE the main
    # memberships_router. Phase3 owns `/memberships/instructors/performance`
    # which would otherwise be eaten by `/memberships/instructors/{instructor_id}`
    # (the path-param route swallows the literal "performance"). Same logic
    # for the other phase routers that add specific sibling endpoints.
    memberships_phase3_router,
    memberships_phase4_router,
    memberships_phase6_router,
    memberships_router, memberships_payments_router, instructor_portal_router,
    memberships_ops_router, memberships_analytics_router,
    memberships_promotions_router,
    memberships_family_router, memberships_calendar_router,
    memberships_public_router,
    memberships_ai_router,
    portal_gdpr_router,
    usage_meter_router,
    notification_prefs_router,
    feedback_router,
    saved_searches_router,
    csv_export_router,
    help_search_router,
    account_billing_router,
    lifecycle_emails_admin_router,
    admin_refunds_router,
    partners_router,
    help_router,
    staffing_router,
    staffing_clock_router,
    staffing_comms_router,
    staffing_tasks_router,
    staffing_hr_router,
    staffing_ai_phase6_router,
    crm_setup_router,
    master_admin_estate_rollup_router,
    back_in_service_router,
    marketing_chat_router,
    master_admin_sales_insights_router,
    launch_readiness_router,
    member_app_builder_router,
    # Iter 215dn — Service Ops native routers
    svc_cases_router, svc_intake_router, svc_desk_router,
    # Iter 215dp — Phase 2 Engineer Mobile
    svc_engineer_router, svc_engineers_admin_router,
    # Iter 216h129 — Engineer Quote Builder + PDF + Email
    svc_engineer_quotes_router,
    # Iter 216h130 — Engineer Invoice Builder
    svc_engineer_invoices_router,
    # Iter 216h131 — Stripe Payment Link on engineer invoices
    svc_engineer_invoice_payments_router,
    svc_engineer_invoice_payments_public_router,
    # Iter 216h132 — Stripe Connect (Express) for Engineer Partners
    svc_engineer_stripe_connect_router,
    svc_engineer_stripe_connect_public_router,
    # Iter 216h133 — Engineer App Phase 3 (mileage, parts-used, invoice-from-job)
    svc_engineer_phase3_router,
    # Iter 216h134 — Engineer App AI Report Assistant (Whisper + GPT-5.2)
    svc_engineer_ai_router,
    # Iter 216h136 — Engineer App Phase 3.5: parts-request workflow
    svc_engineer_parts_requests_router,
    svc_engineer_parts_requests_admin_router,
    # Iter 215dq — Phase 3 Scheduler + Parts
    svc_parts_router, svc_scheduler_router,
    # Iter 215dr — Phase 4 Inventory deepening
    svc_inventory_router,
    # Iter 220ea·19 — Engineer App Phase 5: Stock Control hub
    svc_engineer_stock_router,
    # Iter 220ea·20 — Phase 5b: Parts Catalogue + Bulk Import
    svc_parts_catalogue_router,
    svc_parts_import_router,
    # Iter 220ea·22 — Phase 4: Office/Admin stock overview
    svc_admin_stock_router,
    # Iter 220ea·26 — G1: Canonical CRM customer link
    svc_customer_links_router,
    # Iter 215ds — Phase 5 AI Assistant
    svc_ai_router,
    # Iter 215dt — Phase 6 Billing
    svc_billing_router,
    # Iter 215du — Phase 7 Reports & Audit
    svc_reports_router,
    svc_analytics_router,
    svc_imports_router,
    svc_desk_customers_router,
    # Iter 215dv — Phase 7b Comms Hub
    svc_comms_router,
    # Iter 216y — Phase 6+ Saved Views
    svc_views_router,
    # Iter 215dy — Phase 8 D Integrations admin console
    svc_integrations_health_router,
    # Iter 216h82 — per-job Service Report PDF + email
    svc_service_report_router,
    # Iter 220ea·33 — Legacy report import wizard (AI → branded PDF)
    svc_legacy_reports_router,
    # Iter 216h83 — public live tracking
    svc_public_tracking_router,
    # Iter 216h89 — Pre-job H&S signoff
    svc_safety_router,
    # Iter 220de — Compliance Pack (PTW, COSHH, LOTO)
    svc_compliance_router,
    # Iter 220dg — Engineer outbound ETA push
    svc_eta_update_router,
    # Iter 220dh — Master Admin unified Pending Review queue
    mad_pending_review_router,
    # Iter 220dm — PPM-due reminder sweeper
    svc_ppm_reminders_router,
    # Iter 216h91 — Engineer live location ping
    svc_engineer_location_router,
    # Iter 216h93 — Platform vitals dashboard (master admin)
    health_full_router,
    # Iter 216h140 — Engineer Diary & Admin Dispatch (Phase 4)
    svc_diary_engineer_router,
    svc_diary_admin_router,
    # Iter 216h142 — Notifications + Web Push (Phase 4 / Slice 2)
    svc_notifications_router,
    # Iter 216h144 — Engineer independence (self-create + supplier card)
    svc_independence_router,
    svc_intake_public_router,
    # Iter 216h147 — Engineer self-claim queue
    svc_engineer_queue_router,
    # Iter 216h146 — Inbound email webhook
    svc_inbound_email_public_router,
    svc_inbound_email_engineer_router,
    # Iter 216h259 — Engineer Lite CRM
    svc_engineer_customers_router,
    # Iter 220 — Work Report custom fields
    svc_work_report_fields_router,
    # Iter 220ec — Configurable case types
    svc_case_types_router,
    # Iter 220d — Per-machine work reports + quick-add presets
    svc_per_machine_reports_router,
    # Iter 220ci — Engineer-side strict-validation equipment create
    svc_engineer_equipment_router,
    # Iter 220g — Smart scheduling suggestions
    svc_scheduling_router,
    # Iter 220i — Engineer/org branding for PDFs + portal
    svc_branding_router,
    # Iter 220j — Engineer attention digest
    svc_attention_router,
    # Iter 220l — Engineer ratings (self-view)
    svc_engineer_ratings_router,
    # Iter 220s — Unified Accident, Near-Miss, Hazard, RIDDOR
    incidents_router,
)


def register_features(api_router: APIRouter) -> None:
    for router, feature_key in (*_GYMAXIS_ONLY_ROUTERS, *_PER_ORG_GATED_ROUTERS):
        api_router.include_router(router, dependencies=[Depends(require_feature(feature_key))])
    for router in _UNGATED_ROUTERS:
        api_router.include_router(router)
