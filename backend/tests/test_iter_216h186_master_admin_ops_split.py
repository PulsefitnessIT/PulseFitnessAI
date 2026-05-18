"""
Iter 216h186 — master_admin.py decomposition phase 10 (FINAL):
ops + backfills sub-router.

After this iteration:
    routes/master_admin.py            (~386 LoC, was 732)  — PURE helper module
    routes/master_admin_ops.py        (NEW, ~360 LoC, 5 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The ops sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns ANY routes
     (this is the final phase — it's now a pure helper module).
  4. All shared helpers still live on the parent (cross-module
     imports must keep working).
  5. The new router is registered in `route_registry/admin.py`.
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


def test_ops_module_imports_cleanly():
    importlib.import_module('routes.master_admin_ops')


def test_ops_routes_moved():
    from routes.master_admin_ops import router as new_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/test-data/purge', 'POST'),
        ('/master-admin/all-sites', 'GET'),
        ('/master-admin/users/locked-sites', 'GET'),
        ('/master-admin/equipment/backfill-pulse-supplier', 'POST'),
        ('/master-admin/equipment/backfill-spec-sheets', 'POST'),
    }
    moved_pairs = _route_pairs(new_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"ops sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"ops routes still in master_admin.py: {leaked}"


def test_parent_is_now_a_pure_helper_module():
    """Phase 10 is the final carve. After it, `master_admin.py` should
    own ZERO routes — it's a helper-only module from now on."""
    from routes.master_admin import router as parent_router
    parent_pairs = _route_pairs(parent_router)
    assert not parent_pairs, (
        f"master_admin.py still owns {len(parent_pairs)} route(s): {parent_pairs}"
    )


def test_all_shared_helpers_still_exported_from_parent():
    """The cross-module helper API surface MUST be intact — every
    sub-router (and routes/sites.py, routes/assistant.py, etc.) depends
    on these. If any disappears, ~20 modules break silently at startup."""
    import routes.master_admin as m
    for name in (
        # role / scope guards
        'require_master_admin',
        'require_gymaxis_master_only',
        'assert_org_in_pulse_scope',
        'assert_user_in_pulse_scope',
        'is_pulse_only',
        '_resolve_pulse_scope_org_ids',
        'PULSE_VISIBLE_ACCOUNT_TYPES',
        # audit + activity
        'log_activity',
        # address shape
        'compose_legacy_address',
        'merge_address',
        'ADDRESS_FIELDS',
        # primary contact / module helpers
        '_normalize_modules',
        '_modules_from_portal_type',
        '_derive_portal_type',
        '_generate_initial_password',
        '_mint_invite_link',
        '_ensure_primary_contact_user',
        '_create_org_user',
        # date parser
        '_parse_onboard_date',
        # constants
        'MASTER_ADMIN_EMAIL',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_ops_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_ops_router' in body, (
        "master_admin_ops_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_500():
    """Soft guard: after the final phase the monolith should be a thin
    helper module under 500 LoC. Trips loudly if anyone re-adds a route."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 500, (
        f"master_admin.py is {loc} LoC — it should be a pure helper module now"
    )
