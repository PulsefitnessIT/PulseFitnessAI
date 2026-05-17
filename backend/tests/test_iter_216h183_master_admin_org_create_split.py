"""
Iter 216h183 — master_admin.py decomposition phase 7: org create +
primary-contact credentials sub-router.

After this iteration:
    routes/master_admin.py                  (~1,239 LoC, was 1,434)
    routes/master_admin_org_create.py       (NEW, ~230 LoC, 3 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The Org-create sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns.
  4. The 6 module-helpers (`_normalize_modules`,
     `_modules_from_portal_type`, `_derive_portal_type`,
     `_generate_initial_password`, `_mint_invite_link`,
     `_ensure_primary_contact_user`) STAY on the parent because
     `routes/master_admin_orgs.py` imports 4 of them directly —
     a regression here would silently break the iter-216h178 split.
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


def test_org_create_module_imports_cleanly():
    importlib.import_module('routes.master_admin_org_create')


def test_org_create_routes_moved():
    from routes.master_admin_org_create import router as new_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/organizations', 'POST'),
        ('/master-admin/organizations/{org_id}/primary-contact-credentials', 'GET'),
        ('/master-admin/organizations/{org_id}/send-primary-contact-credentials', 'POST'),
    }
    moved_pairs = _route_pairs(new_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"org-create sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"org-create routes still in master_admin.py: {leaked}"


def test_org_create_helpers_stay_on_parent():
    """These 6 helpers MUST stay on `routes.master_admin` because:
      • `routes/master_admin_orgs.py` (iter 216h178) imports 4 of them.
      • `routes/master_admin_users.py` (iter 216h179) imports `_create_org_user`.
    Moving them here would break those earlier splits."""
    import routes.master_admin as m
    for name in (
        '_normalize_modules',
        '_modules_from_portal_type',
        '_derive_portal_type',
        '_generate_initial_password',
        '_mint_invite_link',
        '_ensure_primary_contact_user',
        '_create_org_user',
    ):
        assert hasattr(m, name), (
            f"{name} must stay on routes.master_admin — sibling sub-routers import it"
        )


def test_shared_helpers_still_exported_from_parent():
    import routes.master_admin as m
    for name in (
        'PULSE_VISIBLE_ACCOUNT_TYPES',
        'assert_org_in_pulse_scope',
        'is_pulse_only',
        'log_activity',
        'merge_address',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_org_create_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_org_create_router' in body, (
        "master_admin_org_create_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_1300():
    """Soft guard: after phase 7 the monolith should be under 1,300 LoC."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 1_300, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
