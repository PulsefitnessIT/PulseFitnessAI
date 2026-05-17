"""
Iter 216h180 — master_admin.py decomposition phase 4: Pulse sub-router.

After this iteration:
    routes/master_admin.py            (~2,312 LoC, was 2,621)
    routes/master_admin_pulse.py      (NEW, ~330 LoC, 3 routes)

Tests verify:
  1. The new module imports cleanly.
  2. The Pulse sub-router owns the extracted route patterns.
  3. The parent `master_admin.py` no longer owns those route patterns
     (no double-registration).
  4. Public helpers (`merge_address`, `_parse_onboard_date`,
     `log_activity`, `require_master_admin`) still live in
     `routes.master_admin` — the new sub-router and other modules
     depend on them.
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


def test_pulse_module_imports_cleanly():
    importlib.import_module('routes.master_admin_pulse')


def test_pulse_routes_moved_to_pulse_module():
    from routes.master_admin_pulse import router as pulse_router
    from routes.master_admin import router as parent_router

    expected_pairs = {
        ('/master-admin/pulse-stats', 'GET'),
        ('/master-admin/pulse-equipment-kits', 'GET'),
        ('/master-admin/onboard-pulse-site', 'POST'),
    }
    pulse_pairs = _route_pairs(pulse_router)
    missing = expected_pairs - pulse_pairs
    assert not missing, f"pulse sub-router missing routes: {missing}"

    parent_pairs = _route_pairs(parent_router)
    leaked = expected_pairs & parent_pairs
    assert not leaked, f"pulse routes still in master_admin.py: {leaked}"


def test_pulse_equipment_kits_catalogue_moved():
    """The static `PULSE_EQUIPMENT_KITS` dict moved with its only
    consumers. It must NOT also live on the parent module."""
    from routes.master_admin_pulse import PULSE_EQUIPMENT_KITS
    expected_kits = {
        'cardio_starter', 'cardio_full',
        'strength_starter', 'strength_full',
        'complete_gym',
    }
    assert expected_kits <= set(PULSE_EQUIPMENT_KITS.keys())

    import routes.master_admin as parent
    assert not hasattr(parent, 'PULSE_EQUIPMENT_KITS'), (
        "PULSE_EQUIPMENT_KITS still exported by master_admin.py — "
        "delete it from the parent to avoid drift."
    )


def test_pulse_helpers_still_exported_from_parent():
    """The new sub-router imports these from `routes.master_admin`. They
    must stay there (also used by ~12 other modules)."""
    import routes.master_admin as m
    for name in (
        '_parse_onboard_date',
        'log_activity',
        'merge_address',
        'require_master_admin',
    ):
        assert hasattr(m, name), f"public symbol missing from routes.master_admin: {name}"


def test_pulse_router_registered_in_admin_registry():
    body = open(os.path.join(BACKEND, 'route_registry/admin.py')).read()
    assert 'master_admin_pulse_router' in body, (
        "master_admin_pulse_router not registered in route_registry/admin.py"
    )


def test_master_admin_shrunk_below_2400():
    """Soft guard: after the Pulse extraction the monolith should be
    well under 2,400 LoC. Trips if endpoints get stuffed back in."""
    with open(os.path.join(BACKEND, 'routes/master_admin.py')) as f:
        loc = sum(1 for _ in f)
    assert loc < 2_400, (
        f"master_admin.py is {loc} LoC — extract new endpoints into a focused sub-router"
    )
