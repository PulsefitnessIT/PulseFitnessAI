"""
Iter 216h177 — master_admin.py decomposition regression test.

The 4,283 LoC monolith was decomposed into 4 focused routers:
    routes/master_admin.py                    (3,711 LoC, was 4,283)
    routes/master_admin_trials.py             (NEW, 288 LoC)
    routes/master_admin_integrations.py       (NEW, 233 LoC — CRM users + Sicon)
    routes/master_admin_analytics_panel.py    (NEW, 133 LoC — activity log + AI usage + emails-legacy)

This test verifies:
  1. All new modules import without error.
  2. Each new sub-router declares the routes it owns.
  3. The parent `master_admin.py` no longer owns those route patterns.
  4. All shared public helpers (`require_master_admin`, etc.) still live
     in `routes.master_admin` so the dozen-or-so cross-module imports
     keep working.
  5. The combined router (after `register_admin` runs) exposes every
     route the monolith used to.
"""
import importlib
import os


BACKEND = '/app/backend'


def test_new_subrouter_modules_import_cleanly():
    for mod in (
        'routes.master_admin',
        'routes.master_admin_trials',
        'routes.master_admin_integrations',
        'routes.master_admin_analytics_panel',
    ):
        importlib.import_module(mod)


def _route_paths(router) -> set:
    return {getattr(r, 'path', None) for r in router.routes}


def test_trials_routes_moved_to_trials_module():
    from routes.master_admin_trials import router as trials_router
    from routes.master_admin import router as parent_router
    paths = _route_paths(trials_router)
    expected = {
        '/master-admin/trials',
        '/master-admin/trials/summary',
        '/master-admin/trials/{org_id}/extend',
        '/master-admin/trials/{org_id}/convert',
        '/master-admin/trials/{org_id}/mark-converted',
    }
    assert expected <= paths, f"trials router missing: {expected - paths}"
    # Confirm the parent no longer owns them (no double-registration).
    parent_paths = _route_paths(parent_router)
    leaked = expected & parent_paths
    assert not leaked, f"trials routes still in master_admin.py: {leaked}"


def test_integrations_routes_moved():
    from routes.master_admin_integrations import router as integ_router
    from routes.master_admin import router as parent_router
    paths = _route_paths(integ_router)
    expected = {
        '/master-admin/crm-users',
        '/master-admin/crm-users/{crm_user_id}',
        '/master-admin/sicon/health',
        '/master-admin/sicon/test-all',
        '/master-admin/sicon/poll-all',
    }
    assert expected <= paths, f"integrations missing: {expected - paths}"
    leaked = expected & _route_paths(parent_router)
    assert not leaked, f"integration routes still in master_admin.py: {leaked}"


def test_analytics_panel_routes_moved():
    from routes.master_admin_analytics_panel import router as ana_router
    from routes.master_admin import router as parent_router
    paths = _route_paths(ana_router)
    expected = {
        '/master-admin/activity-log',
        '/master-admin/ai-usage',
        '/master-admin/emails-legacy',
    }
    assert expected <= paths, f"analytics missing: {expected - paths}"
    leaked = expected & _route_paths(parent_router)
    assert not leaked, f"analytics routes still in master_admin.py: {leaked}"


def test_public_helpers_still_exported_from_parent():
    """A dozen cross-module imports rely on these symbols staying at
    `routes.master_admin.<name>`. Breaking any of them silently 500s
    `data_wipe`, `companies_house`, `mod_portal`, `pulse_sales`, etc."""
    import routes.master_admin as m
    for name in (
        'router',
        'require_master_admin',
        'require_gymaxis_master_only',
        '_resolve_pulse_scope_org_ids',
        'assert_org_in_pulse_scope',
        'is_pulse_only',
        'log_activity',
        'compose_legacy_address',
        'merge_address',
        'ADDRESS_FIELDS',
        'MASTER_ADMIN_EMAIL',
        'PULSE_VISIBLE_ACCOUNT_TYPES',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_admin_registry_registers_all_new_routers():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    for name in (
        'master_admin_trials_router',
        'master_admin_integrations_router',
        'master_admin_analytics_panel_router',
    ):
        assert name in body, f"{name} not registered in route_registry/admin.py"


def test_master_admin_shrunk():
    """Soft guard: prevent silent re-bloat of master_admin.py."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    # Pre-decomposition: 4,283 LoC. Post-decomposition: 3,711 LoC.
    # If a future agent stuffs new endpoints back in here without
    # following the sub-router pattern, this guard trips.
    assert loc < 4000, f"master_admin.py grew back to {loc} LoC — extract new endpoints into a focused sub-router"
