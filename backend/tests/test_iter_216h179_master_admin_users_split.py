"""
Iter 216h179 — master_admin.py Users CRUD + impersonate + reset-password
sub-router extraction.

After this iteration:
    routes/master_admin.py                  (~2,621 LoC, was 3,248)
    routes/master_admin_users.py            (NEW, ~655 LoC, 8 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The Users sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns
     (no double-registration).
  4. Public helpers (`assert_user_in_pulse_scope`, `_create_org_user`,
     `PULSE_VISIBLE_ACCOUNT_TYPES`) still live in `routes.master_admin`
     because the new sub-router (and other modules) import them.
  5. The new router is registered in `route_registry/admin.py`.
"""
import importlib
import os


BACKEND = '/app/backend'


def _route_paths(router) -> set:
    return {getattr(r, 'path', None) for r in router.routes}


def _route_pairs(router) -> set:
    return {
        (r.path, m)
        for r in router.routes
        for m in (getattr(r, 'methods', None) or ())
    }


def test_users_module_imports_cleanly():
    importlib.import_module('routes.master_admin_users')


def test_users_routes_moved_to_users_module():
    from routes.master_admin_users import router as users_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/users/{user_id}/invite-link', 'POST'),
        ('/master-admin/organizations/{org_id}/users', 'POST'),
        ('/master-admin/users', 'GET'),
        ('/master-admin/users/{user_id}/edit', 'PUT'),
        ('/master-admin/users/{user_id}/disable', 'PUT'),
        ('/master-admin/users/{user_id}/archive', 'PUT'),
        ('/master-admin/users/{user_id}', 'DELETE'),
        ('/master-admin/users/{user_id}/reset-password', 'PUT'),
        ('/master-admin/impersonate/{user_id}', 'POST'),
    }
    users_pairs = _route_pairs(users_router)
    missing = expected_pairs - users_pairs
    assert not missing, f"users sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"users routes still in master_admin.py: {leaked}"


def test_users_helpers_still_exported_from_parent():
    """Cross-module dependants (and the new sub-router itself) import
    these from `routes.master_admin`. They must stay there."""
    import routes.master_admin as m
    for name in (
        'PULSE_VISIBLE_ACCOUNT_TYPES',
        '_create_org_user',
        'assert_org_in_pulse_scope',
        'assert_user_in_pulse_scope',
        'is_pulse_only',
        'log_activity',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_users_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_users_router' in body, (
        "master_admin_users_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_2700():
    """Soft guard: after the Users extraction the monolith should be well
    under 2,700 LoC. If a future agent stuffs new endpoints back in here
    without following the sub-router pattern, this guard trips."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 2_700, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
