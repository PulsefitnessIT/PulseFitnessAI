"""
Iter 216h185 — master_admin.py decomposition phase 9: branding email
previews + test-flag + account-type.

After this iteration:
    routes/master_admin.py                  (~732 LoC, was 905)
    routes/master_admin_org_branding.py     (NEW, ~210 LoC, 3 routes)
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


def test_org_branding_module_imports_cleanly():
    importlib.import_module('routes.master_admin_org_branding')


def test_org_branding_routes_moved():
    from routes.master_admin_org_branding import router as new_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/organizations/{org_id}/test-flag', 'PUT'),
        ('/master-admin/organizations/{org_id}/test-email', 'POST'),
        ('/master-admin/organizations/{org_id}/account-type', 'PUT'),
    }
    moved_pairs = _route_pairs(new_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"org-branding sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"org-branding routes still in master_admin.py: {leaked}"


def test_preview_email_helpers_removed_from_parent():
    """Private helpers travelled with the route."""
    import routes.master_admin as parent
    for name in ('_build_preview_comment_email', '_build_preview_engineer_email'):
        assert not hasattr(parent, name), (
            f"{name} still exported by master_admin.py — delete it from the parent"
        )


def test_shared_helpers_still_exported_from_parent():
    import routes.master_admin as m
    for name in (
        'assert_org_in_pulse_scope',
        'log_activity',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_org_branding_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_org_branding_router' in body, (
        "master_admin_org_branding_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_800():
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 800, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
