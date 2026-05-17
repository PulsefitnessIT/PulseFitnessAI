"""
Iter 216h184 — master_admin.py decomposition phase 8: org integration
health sub-router.

After this iteration:
    routes/master_admin.py                       (~905 LoC, was 1,239)
    routes/master_admin_integration_health.py    (NEW, ~360 LoC, 3 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The integration-health sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns.
  4. The 2 private helpers (`_check_code_collision`,
     `_integration_status`) are gone from the parent (drift guard).
  5. `_create_org_user` STAYS on the parent because
     `routes/master_admin_users.py` imports it directly — it sits
     between the two extracted blocks and must be preserved.
  6. The new router is registered in `route_registry/admin.py`.
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


def test_integration_health_module_imports_cleanly():
    importlib.import_module('routes.master_admin_integration_health')


def test_integration_health_routes_moved():
    from routes.master_admin_integration_health import router as new_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/organizations/{org_id}/verify-mappings', 'POST'),
        ('/master-admin/organizations/{org_id}/integration-health', 'GET'),
        ('/master-admin/integrations-hub', 'GET'),
    }
    moved_pairs = _route_pairs(new_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"integration-health sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"integration-health routes still in master_admin.py: {leaked}"


def test_integration_helpers_removed_from_parent():
    """Private helpers travelled with the route."""
    import routes.master_admin as parent
    for name in ('_check_code_collision', '_integration_status'):
        assert not hasattr(parent, name), (
            f"{name} still exported by master_admin.py — delete it from the parent"
        )


def test_create_org_user_preserved_on_parent():
    """`_create_org_user` lives BETWEEN the two extracted blocks in the
    original file. It must survive the surgical deletion intact because
    `routes/master_admin_users.py` imports it."""
    import routes.master_admin as m
    assert hasattr(m, '_create_org_user'), (
        "_create_org_user must stay on routes.master_admin — "
        "master_admin_users.py imports it"
    )


def test_shared_helpers_still_exported_from_parent():
    import routes.master_admin as m
    for name in (
        'assert_org_in_pulse_scope',
        'is_pulse_only',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_integration_health_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_integration_health_router' in body, (
        "master_admin_integration_health_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_1000():
    """Soft guard: after phase 8 the monolith should be under 1,000 LoC."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 1_000, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
