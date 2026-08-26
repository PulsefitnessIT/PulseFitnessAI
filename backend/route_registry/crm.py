"""CRM routes: auth, core, AI, inbox, workflows, CPQ, Sage 200, documents, v2, contracts, hub."""
from fastapi import APIRouter

from routes.crm_auth import router as crm_auth_router
from routes.crm_core import router as crm_core_router
from routes.crm_ai import router as crm_ai_router
from routes.crm_inbox import router as crm_inbox_router
from routes.crm_workflows import router as crm_workflows_router
from routes.crm_cpq import router as crm_cpq_router
from routes.crm_sage200 import router as crm_sage200_router
from routes.crm_documents import router as crm_documents_router
from routes.crm_v2 import router as crm_v2_router
from routes.crm_quote_sage import router as crm_quote_sage_router
from routes.crm_quote_invoicing import router as crm_quote_invoicing_router
from routes.crm_quote_fulfilment import router as crm_quote_fulfilment_router
from routes.crm_contracts import router as crm_contracts_router
from routes.crm_contract_templates import router as crm_contract_templates_router
from routes.crm_contract_send import router as crm_contract_send_router
from routes.crm_contract_lifecycle import router as crm_contract_lifecycle_router
from routes.crm_contract_workspace import (
    router as crm_contract_workspace_router,
    engineer_router as crm_contract_engineer_router,
)
from routes.crm_lead_conversion import router as crm_lead_conversion_router
from routes.crm_modes import router as crm_modes_router
from routes.crm_territories import router as crm_territories_router
from routes.crm_audit import router as crm_audit_router
from routes.crm_permissions import router as crm_permissions_router
from routes.crm_forecast import router as crm_forecast_router
from routes.crm_picklists import router as crm_picklists_router
from routes.crm_stakeholders import router as crm_stakeholders_router
from routes.crm_products import router as crm_products_router
from routes.crm_price_list import router as crm_price_list_router
from routes.crm_price_changes import router as crm_price_changes_router
from routes.crm_price_backup import router as crm_price_backup_router
from routes.crm_price_quality import router as crm_price_quality_router
from routes.crm_price_ai import router as crm_price_ai_router
from routes.crm_product_perms import router as crm_product_perms_router
from routes.crm_website_recognize import router as crm_website_recognize_router
from routes.crm_reports import router as crm_reports_router
from routes.crm_phase3 import router as crm_phase3_router
from routes.crm_journey_enrol import router as crm_journey_enrol_router
from routes.crm_site_surveys import router as crm_site_surveys_router
from routes.crm_mod_quote import router as crm_mod_quote_router
from routes.crm_mod_quote import public_router as crm_quote_public_router
from routes.integration_hub import router as integration_hub_router


def register_crm(api_router: APIRouter) -> None:
    for r in (
        crm_auth_router, crm_core_router, crm_ai_router,
        crm_inbox_router, crm_workflows_router, crm_cpq_router,
        crm_sage200_router, crm_documents_router, crm_v2_router,
        crm_quote_sage_router,
        crm_quote_invoicing_router,
        crm_quote_fulfilment_router,
        crm_contracts_router, crm_contract_templates_router,
        crm_contract_send_router, crm_contract_lifecycle_router,
        crm_contract_workspace_router, crm_contract_engineer_router,
        crm_lead_conversion_router,
        crm_modes_router, crm_territories_router,
        crm_audit_router, crm_permissions_router, crm_forecast_router,
        crm_picklists_router, crm_stakeholders_router, crm_products_router,
        crm_price_list_router,
        crm_price_changes_router,
        crm_price_backup_router,
        crm_price_quality_router,
        crm_price_ai_router,
        crm_product_perms_router,
        crm_website_recognize_router,
        crm_reports_router, crm_phase3_router,
        crm_journey_enrol_router,
        crm_site_surveys_router,
        crm_mod_quote_router,
        crm_quote_public_router,
        integration_hub_router,
    ):
        api_router.include_router(r)
