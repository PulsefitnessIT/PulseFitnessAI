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
from routes.crm_contracts import router as crm_contracts_router
from routes.crm_modes import router as crm_modes_router
from routes.crm_territories import router as crm_territories_router
from routes.crm_audit import router as crm_audit_router
from routes.crm_permissions import router as crm_permissions_router
from routes.crm_forecast import router as crm_forecast_router
from routes.crm_picklists import router as crm_picklists_router
from routes.crm_stakeholders import router as crm_stakeholders_router
from routes.integration_hub import router as integration_hub_router


def register_crm(api_router: APIRouter) -> None:
    for r in (
        crm_auth_router, crm_core_router, crm_ai_router,
        crm_inbox_router, crm_workflows_router, crm_cpq_router,
        crm_sage200_router, crm_documents_router, crm_v2_router,
        crm_contracts_router, crm_modes_router, crm_territories_router,
        crm_audit_router, crm_permissions_router, crm_forecast_router,
        crm_picklists_router, crm_stakeholders_router,
        integration_hub_router,
    ):
        api_router.include_router(r)
