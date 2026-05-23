"""Core platform routes: auth, equipment, issues, files, payments, sites, fault codes/templates."""
from fastapi import APIRouter

from routes.auth import router as auth_router
from routes.account import router as account_router
from routes.site_data_export import router as site_data_export_router
from routes.master_admin_perf import router as master_admin_perf_router
from routes.equipment import router as equipment_router
from routes.issues import router as issues_router
from routes.files import router as files_router
from routes.payments import router as payments_router
from routes.sites import router as sites_router
from routes.fault_codes import router as fault_codes_router
from routes.fault_templates import router as fault_templates_router
from routes.support import router as support_router
from routes.support_escalate import router as support_escalate_router
from routes.nudges import router as nudges_router
from routes.security_manifest import router as security_manifest_router
from routes.sso import router as sso_router
from routes.gym_floor import router as gym_floor_router
from routes.ui_errors import router as ui_errors_router
from routes.client_errors import router as client_errors_router
from routes.platform_issues import router as platform_issues_router
from routes.marketing_downloads import router as marketing_downloads_router


def register_core(api_router: APIRouter) -> None:
    for r in (
        auth_router, account_router, site_data_export_router,
        master_admin_perf_router,
        equipment_router, issues_router, files_router,
        payments_router, sites_router, fault_codes_router, fault_templates_router,
        support_router, support_escalate_router, nudges_router, security_manifest_router,
        sso_router, gym_floor_router, ui_errors_router, client_errors_router, platform_issues_router,
        marketing_downloads_router,
    ):
        api_router.include_router(r)
