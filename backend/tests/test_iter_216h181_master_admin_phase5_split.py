"""
Iter 216h181 — master_admin.py decomposition phase 5: head-office
onboarding + CRM analytics extracted to TWO focused sub-routers.

After this iteration:
    routes/master_admin.py                    (~1,667 LoC, was 2,312)
    routes/master_admin_onboard.py            (NEW, ~340 LoC, 1 route)
    routes/master_admin_crm_analytics.py      (NEW, ~310 LoC, 1 route)

Tests verify:
  1. Both new modules import cleanly.
  2. Each new sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns.
  4. Public helpers (`merge_address`, `log_activity`,
     `require_master_admin`) still live in `routes.master_admin`.
  5. Both new routers are registered in `route_registry/admin.py`.
"""
import importlib
import os


BACKEND = '/app/backend'


def _route_pairs(router) -> set:
    return {
        (r.path, m)
        for r in router.routes
        for m in (getattr(r, 'methods', None) or ())
    }


def test_new_modules_import_cleanly():
    for mod in (
        'routes.master_admin_onboard',
        'routes.master_admin_crm_analytics',
    ):
        importlib.import_module(mod)


def test_onboard_route_moved_to_onboard_module():
    from routes.master_admin_onboard import router as onboard_router
    from routes.master_admin import router as parent_router

    expected_pairs = {('/master-admin/onboard-head-office', 'POST')}
    moved_pairs = _route_pairs(onboard_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"onboard sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"onboard routes still in master_admin.py: {leaked}"


def test_crm_analytics_route_moved_to_crm_analytics_module():
    from routes.master_admin_crm_analytics import router as crm_router
    from routes.master_admin import router as parent_router

    expected_pairs = {('/master-admin/crm-analytics', 'GET')}
    moved_pairs = _route_pairs(crm_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"crm analytics sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"crm analytics routes still in master_admin.py: {leaked}"


def test_crm_helpers_moved_off_parent():
    """The 15 private CRM-analytic helpers travelled with the route. The
    parent module must NOT also expose them (drift hazard)."""
    import routes.master_admin as parent
    for name in (
        '_crm_pipeline_analytics',
        '_crm_entity_counts',
        '_crm_quote_analytics',
        '_crm_workflow_stats',
        '_crm_user_and_activity_stats',
        '_crm_top_deals_at_risk',
        '_crm_renewals_due',
        '_crm_ai_usage_block',
        '_validate_head_office_payload',
    ):
        assert not hasattr(parent, name), (
            f"{name} still exported by master_admin.py — delete it from the parent"
        )


def test_shared_helpers_still_exported_from_parent():
    """The new sub-routers import these from `routes.master_admin`. They
    must stay there (also used by ~12 other modules)."""
    import routes.master_admin as m
    for name in (
        'log_activity',
        'merge_address',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_new_routers_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    for name in (
        'master_admin_onboard_router',
        'master_admin_crm_analytics_router',
    ):
        assert name in body, f"{name} not registered in route_registry/admin.py"


def test_master_admin_shrunk_below_1800():
    """Soft guard: after phase 5 the monolith should be well under 1,800
    LoC. Trips if endpoints get stuffed back in."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 1_800, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
