"""Admin routes: master admin, analytics, documents, docs export, archive, service desk."""
from fastapi import APIRouter

from routes.master_admin import router as master_admin_router
from routes.master_admin_memberships import router as master_admin_memberships_router
from routes.pulse_master_admin import router as pulse_master_admin_router
from routes.pulse_stripe_phase2 import router as pulse_stripe_phase2_router
from routes.master_admin_bulk_import import router as master_admin_bulk_import_router
from routes.equipment_image_admin import router as equipment_image_admin_router
from routes.marketing import router as marketing_router
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
from routes.admin_docs_static import router as admin_docs_static_router
from routes.trust import router as trust_router
from routes.security_checks import router as security_checks_router
from routes.support_admin import router as support_admin_router
from routes.support_escalate import admin_router as support_escalate_admin_router
from routes.master_admin_pricing import router as master_admin_pricing_router
from routes.master_admin_billing import router as master_admin_billing_router
from routes.master_admin_login_events import router as master_admin_login_events_router
from routes.master_admin_audit_log import router as master_admin_audit_log_router
from routes.activation_events import router as activation_events_router
from routes.master_admin_documents_lib import router as master_admin_documents_lib_router
from routes.invoice_share import router as invoice_share_router
from routes.invoice_dunning import router as invoice_dunning_router
from routes.collections_dashboard import router as collections_dashboard_router
from routes.sales_pack import router as sales_pack_router
from routes.email_health import router as email_health_router
from routes.triage_feedback import router as triage_feedback_router
from routes.master_admin_db_viewer import router as master_admin_db_viewer_router
from routes.master_admin_catalogue import router as master_admin_catalogue_router
from routes.master_admin_hubspot_parity import router as master_admin_hubspot_parity_router
from routes.marketing_forms import router as marketing_forms_router
from routes.cross_module_tips import router as cross_module_tips_router
from routes.custom_properties import router as custom_properties_router
from routes.module_trials import router as module_trials_router
from routes.master_admin_manufacturer_domains import router as master_admin_manufacturer_domains_router
from routes.marketing_image_library import router as marketing_image_library_router
from routes.integration_health import router as integration_health_router
from routes.companies_house import router as companies_house_router
from routes.postcodes import router as postcodes_router


def register_admin(api_router: APIRouter) -> None:
    for r in (
        master_admin_router, master_admin_memberships_router,
        pulse_master_admin_router, pulse_stripe_phase2_router,
        master_admin_bulk_import_router,
        equipment_image_admin_router,
        marketing_router,
        marketing_director_router,
        assistant_router,
        data_wipe_router,
        admin_analytics_router, admin_documents_router,
        docs_export_router, onboarding_packets_router, feature_presets_router,
        archive_router, service_desk_admin_router, service_desk_router,
        admin_docs_static_router, trust_router, security_checks_router, support_admin_router,
        support_escalate_admin_router,
        master_admin_pricing_router, master_admin_billing_router,
        master_admin_login_events_router,
        master_admin_audit_log_router,
        activation_events_router,
        master_admin_documents_lib_router,
        invoice_share_router,
        invoice_dunning_router,
        collections_dashboard_router,
        sales_pack_router,
        email_health_router,
        triage_feedback_router,
        master_admin_db_viewer_router,
        master_admin_catalogue_router,
        master_admin_manufacturer_domains_router,
        marketing_image_library_router,
        master_admin_hubspot_parity_router,
        cross_module_tips_router,
        custom_properties_router,
        module_trials_router,
        integration_health_router,
        companies_house_router,
        postcodes_router,
    ):
        api_router.include_router(r)
    api_router.include_router(marketing_forms_router, prefix="/marketing")
