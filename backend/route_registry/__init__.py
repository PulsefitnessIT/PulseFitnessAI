"""Route registry — split by domain (core / features / admin / crm).

`route_registration.py` used to contain every import for every router in the app
(53 of them), which tripped tight-coupling warnings on code reviews. Splitting by
domain means each registry module owns a ~10-import scope, and each domain can be
audited in isolation.

Public entry point: `register_routes(api_router)` below.
"""
from fastapi import APIRouter

from route_registry.core import register_core
from route_registry.features import register_features
from route_registry.admin import register_admin
from route_registry.crm import register_crm


def register_routes(api_router: APIRouter) -> None:
    """Register every route module on the given API router."""
    register_core(api_router)
    register_features(api_router)
    register_admin(api_router)
    register_crm(api_router)
