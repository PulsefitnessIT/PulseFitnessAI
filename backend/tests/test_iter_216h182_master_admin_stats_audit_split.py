"""
Iter 216h182 — master_admin.py decomposition phase 6: platform stats +
audit-log surface extracted.

After this iteration:
    routes/master_admin.py                 (~1,434 LoC, was 1,667)
    routes/master_admin_stats_audit.py     (NEW, ~260 LoC, 4 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The Stats + Audit sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns.
  4. The 3 stats helpers (`_get_platform_counts`,
     `_get_subscription_stats`, `_get_growth_data`) are gone from the
     parent (drift guard) but `_resolve_pulse_scope_org_ids` stays
     because `routes/sites.py` and `routes/assistant.py` import it.
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


def test_stats_audit_module_imports_cleanly():
    importlib.import_module('routes.master_admin_stats_audit')


def test_stats_audit_routes_moved():
    from routes.master_admin_stats_audit import router as new_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/stats', 'GET'),
        ('/master-admin/audit-logs', 'GET'),
        ('/master-admin/audit-logs/facets', 'GET'),
        ('/master-admin/audit-logs/export.csv', 'GET'),
    }
    moved_pairs = _route_pairs(new_router)
    missing = expected_pairs - moved_pairs
    assert not missing, f"stats/audit sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"stats/audit routes still in master_admin.py: {leaked}"


def test_stats_helpers_removed_from_parent():
    """Private helpers travelled with the route."""
    import routes.master_admin as parent
    for name in (
        '_get_platform_counts',
        '_get_subscription_stats',
        '_get_growth_data',
    ):
        assert not hasattr(parent, name), (
            f"{name} still exported by master_admin.py — delete it from the parent"
        )


def test_resolve_pulse_scope_org_ids_stays_on_parent():
    """`routes/sites.py` and `routes/assistant.py` import this directly,
    so it MUST stay on `routes.master_admin`."""
    import routes.master_admin as m
    assert hasattr(m, '_resolve_pulse_scope_org_ids'), (
        "_resolve_pulse_scope_org_ids must stay on routes.master_admin — "
        "other modules import it directly"
    )


def test_shared_helpers_still_exported_from_parent():
    import routes.master_admin as m
    for name in (
        'require_master_admin',
        '_resolve_pulse_scope_org_ids',
        'is_pulse_only',
        'log_activity',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_stats_audit_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_stats_audit_router' in body, (
        "master_admin_stats_audit_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_1500():
    """Soft guard: after phase 6 the monolith should be under 1,500 LoC."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 1_500, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
