"""Pulse Fitness Marketing Suite routes — package aggregator (Pass 2 split).

Each section of the legacy 1874-line `routes/marketing.py` is now a
focused submodule. This `__init__.py` is the single public entry-point:
it constructs ONE master `router` mounting all sub-routers and re-exports
helpers that other parts of the codebase already import.

External imports remain backwards-compatible:
  • `from routes.marketing import router`
  • `from routes.marketing import _get_entitlement, _require_feature`
  • `from routes.marketing import _evaluate_audience, _build_filter`
  • `from routes.marketing import DEFAULT_PLANS, _seed_default_plans_once`
"""
from fastapi import APIRouter

from routes.marketing import (
    admin,
    assistant,
    attribution,
    audiences,
    brand_discovery,
    brand_kit,
    campaigns,
    contacts,
    creative,
    dashboard,
    dynamic_lists,
    entitlement,
    insights,
    journeys,
    social,
    starter_pack,
    templates,
    tour,
)

# Helper / utility re-exports
from routes.marketing.helpers import (  # noqa: F401
    DEFAULT_PLANS,
    _get_entitlement,
    _get_org_subscription,
    _get_plan,
    _new_id,
    _now_iso,
    _org_id,
    _require_admin,
    _require_feature,
    _seed_default_plans_once,
    logger,
)
from routes.marketing.audiences import _build_filter, _evaluate_audience  # noqa: F401


router = APIRouter()
for sub in (
    entitlement,
    audiences,
    campaigns,
    contacts,
    creative,
    journeys,
    insights,
    dashboard,
    social,
    admin,
    templates,
    attribution,
    assistant,
    tour,
    brand_kit,
    brand_discovery,
    starter_pack,
    dynamic_lists,
):
    router.include_router(sub.router)


__all__ = [
    "router",
    "DEFAULT_PLANS",
    "_get_entitlement",
    "_get_org_subscription",
    "_get_plan",
    "_new_id",
    "_now_iso",
    "_org_id",
    "_require_admin",
    "_require_feature",
    "_seed_default_plans_once",
    "_build_filter",
    "_evaluate_audience",
    "logger",
]
