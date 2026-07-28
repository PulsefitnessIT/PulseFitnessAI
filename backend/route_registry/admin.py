"""Admin routes: master admin, analytics, documents, docs export, archive, service desk."""
from fastapi import APIRouter

from routes.master_admin import router as master_admin_router
from routes.master_admin_orgs import router as master_admin_orgs_router
from routes.master_admin_org_cleanup import router as master_admin_org_cleanup_router
from routes.master_admin_test_data_purge import router as master_admin_test_data_purge_router
from routes.master_admin_users import router as master_admin_users_router
from routes.master_admin_pulse import router as master_admin_pulse_router
from routes.master_admin_onboard import router as master_admin_onboard_router
from routes.master_admin_dealer_onboard import router as master_admin_dealer_onboard_router
from routes.master_admin_crm_analytics import router as master_admin_crm_analytics_router
from routes.master_admin_stats_audit import router as master_admin_stats_audit_router
from routes.master_admin_org_create import router as master_admin_org_create_router
from routes.master_admin_integration_health import router as master_admin_integration_health_router
from routes.master_admin_integrity import router as master_admin_integrity_router
from routes.platform_integrity import router as platform_integrity_router
from routes.master_admin_org_branding import router as master_admin_org_branding_router
from routes.master_admin_ops import router as master_admin_ops_router
from routes.master_admin_trials import router as master_admin_trials_router
from routes.master_admin_growth_hub import router as master_admin_growth_hub_router
from routes.master_admin_integrations import router as master_admin_integrations_router
from routes.master_admin_analytics_panel import router as master_admin_analytics_panel_router
from routes.master_admin_memberships import router as master_admin_memberships_router
from routes.pulse_master_admin import router as pulse_master_admin_router
from routes.pulse_stripe_phase2 import router as pulse_stripe_phase2_router
from routes.master_admin_bulk_import import router as master_admin_bulk_import_router
from routes.equipment_image_admin import router as equipment_image_admin_router
from routes.marketing import router as marketing_router
from routes.comms import router as comms_router
from routes.comms_intel import router as comms_intel_router
from routes.comms_segments import router as comms_segments_router
from routes.comms_growth import (
    router as comms_growth_router,
    public_router as comms_public_api_router,
    webhook_router as comms_webhook_inbound_router,
)
from routes.marketing_director import router as marketing_director_router
from routes.assistant import router as assistant_router
from routes.data_wipe import router as data_wipe_router
from routes.admin_analytics import router as admin_analytics_router
from routes.admin_documents import router as admin_documents_router
from routes.docs_export import router as docs_export_router
from routes.onboarding_packets import router as onboarding_packets_router
from routes.feature_presets import router as feature_presets_router
from routes.archive import router as archive_router
from routes.service_desk_admin import router as service_desk_admin_router
from routes.service_desk import router as service_desk_router
from routes.master_admin_access_matrix import router as master_admin_access_matrix_router
from routes.admin_docs_static import router as admin_docs_static_router
from routes.trust import router as trust_router
from routes.security_checks import router as security_checks_router
from routes.support_admin import router as support_admin_router
from routes.support_escalate import admin_router as support_escalate_admin_router
from routes.master_admin_pricing import router as master_admin_pricing_router
from routes.master_admin_billing import router as master_admin_billing_router
from routes.master_admin_login_events import router as master_admin_login_events_router
from routes.master_admin_audit_log import router as master_admin_audit_log_router
from routes.master_admin_communications import (
    router as master_admin_communications_router,
    canned_router as master_admin_canned_replies_router,
)
from routes.master_admin_theme import router as master_admin_theme_router
from routes.master_admin_custom_domains import router as master_admin_custom_domains_router
from routes.public_host_config import router as public_host_config_router
from routes.public_quote import router as public_quote_router
from routes.public_demo_request import router as public_demo_request_router
from routes.activation_events import router as activation_events_router
from routes.master_admin_documents_lib import router as master_admin_documents_lib_router
from routes.invoice_share import router as invoice_share_router
from routes.invoice_dunning import router as invoice_dunning_router
from routes.collections_dashboard import router as collections_dashboard_router
from routes.sales_pack import router as sales_pack_router
from routes.email_health import router as email_health_router
from routes.triage_feedback import router as triage_feedback_router
from routes.master_admin_db_viewer import router as master_admin_db_viewer_router
from routes.master_admin_pulse_explorer import router as master_admin_pulse_explorer_router
from routes.master_admin_catalogue import router as master_admin_catalogue_router
from routes.master_admin_hubspot_parity import router as master_admin_hubspot_parity_router
from routes.marketing_forms import router as marketing_forms_router
from routes.cross_module_tips import router as cross_module_tips_router
from routes.custom_properties import router as custom_properties_router
from routes.module_trials import router as module_trials_router
from routes.master_admin_manufacturer_domains import router as master_admin_manufacturer_domains_router
from routes.marketing_image_library import router as marketing_image_library_router
from routes.social_media_library import router as social_media_library_router
from routes.marketing_addons import router as marketing_addons_router
from routes.pricing_drift_audit import router as pricing_drift_audit_router
from routes.stripe_connect import router as stripe_connect_router
from routes.public_signup import router as public_signup_router
from routes.tour_bookings import router as tour_bookings_router
from routes.signup_journeys import router as signup_journeys_router
from routes.integration_health import router as integration_health_router
from routes.companies_house import router as companies_house_router
from routes.postcodes import router as postcodes_router
from routes.mod_bulk_import import router as mod_bulk_import_router
from routes.mod_demo_seed import router as mod_demo_seed_router
from routes.pulse_sales import router as pulse_sales_router
from routes.onboarding_projects import router as onboarding_projects_router
from routes.onboarding_import import router as onboarding_import_router
from routes.onboarding_readiness import router as onboarding_readiness_router
from routes.onboarding_ai import router as onboarding_ai_router
from routes.onboarding_phase5 import router as onboarding_phase5_router


def register_admin(api_router: APIRouter) -> None:
    for r in (
        master_admin_router, master_admin_orgs_router,
        master_admin_org_cleanup_router,
        master_admin_test_data_purge_router,
        master_admin_users_router,
        master_admin_pulse_router,
        master_admin_onboard_router,
        master_admin_dealer_onboard_router,
        master_admin_crm_analytics_router,
        master_admin_stats_audit_router,
        master_admin_org_create_router,
        master_admin_integration_health_router,
        master_admin_integrity_router,
        platform_integrity_router,
        master_admin_org_branding_router,
        master_admin_ops_router,
        master_admin_trials_router,
        master_admin_growth_hub_router,
        master_admin_integrations_router,
        master_admin_analytics_panel_router,
        master_admin_memberships_router,
        pulse_master_admin_router, pulse_stripe_phase2_router,
        master_admin_bulk_import_router,
        mod_bulk_import_router,
        mod_demo_seed_router,
        equipment_image_admin_router,
        marketing_router,
        comms_router,
        comms_intel_router,
        comms_segments_router,
        comms_growth_router,
        comms_public_api_router,
        comms_webhook_inbound_router,
        marketing_director_router,
        assistant_router,
        data_wipe_router,
        admin_analytics_router, admin_documents_router,
        docs_export_router, onboarding_packets_router, feature_presets_router,
        archive_router, service_desk_admin_router, service_desk_router,
        master_admin_access_matrix_router,
        admin_docs_static_router, trust_router, security_checks_router, support_admin_router,
        support_escalate_admin_router,
        master_admin_pricing_router, master_admin_billing_router,
        master_admin_login_events_router,
        master_admin_audit_log_router,
        master_admin_communications_router,
        master_admin_canned_replies_router,
        master_admin_theme_router,
        master_admin_custom_domains_router,
        public_host_config_router,
        activation_events_router,
        master_admin_documents_lib_router,
        invoice_share_router,
        invoice_dunning_router,
        collections_dashboard_router,
        sales_pack_router,
        email_health_router,
        triage_feedback_router,
        master_admin_db_viewer_router,
        master_admin_pulse_explorer_router,
        master_admin_catalogue_router,
        master_admin_manufacturer_domains_router,
        marketing_image_library_router,
        social_media_library_router,
        marketing_addons_router,
        pricing_drift_audit_router,
        stripe_connect_router,
        public_signup_router,
        tour_bookings_router,
        signup_journeys_router,
        master_admin_hubspot_parity_router,
        cross_module_tips_router,
        custom_properties_router,
        module_trials_router,
        integration_health_router,
        companies_house_router,
        postcodes_router,
        pulse_sales_router,
        onboarding_projects_router,
        onboarding_import_router,
        onboarding_readiness_router,
        onboarding_ai_router,
        onboarding_phase5_router,
        public_quote_router,
        public_demo_request_router,
    ):
        api_router.include_router(r)
    api_router.include_router(marketing_forms_router, prefix="/marketing")
