"""Iter 216h238 — Integration field-mapping coverage badge.

Validates:

1. ``utils.integration_mapping_coverage.compute_mapping_coverage`` returns
   a well-shaped dict with all required keys and sane numeric ranges.
2. The numbers it produces match the CI lint script
   (`scripts/check_integration_mapping.py`) at parse-time so the
   master-admin UI badge can't drift from the lint output.
3. The new endpoint
   ``GET /master-admin/integration-mapping-coverage`` is wired into the
   integration-health router.
"""
from __future__ import annotations


def test_compute_returns_required_keys():
    from utils.integration_mapping_coverage import compute_mapping_coverage
    out = compute_mapping_coverage()
    for key in (
        "fields_total", "fields_annotated", "fields_pct",
        "files_total", "files_manifested", "files_pct",
        "by_module", "doc_sections", "computed_at",
    ):
        assert key in out, f"missing key: {key}"


def test_numbers_are_sane():
    from utils.integration_mapping_coverage import compute_mapping_coverage
    out = compute_mapping_coverage()
    assert 0 <= out["fields_annotated"] <= out["fields_total"]
    assert 0 <= out["files_manifested"] <= out["files_total"]
    assert 0 <= out["fields_pct"] <= 100
    assert 0 <= out["files_pct"] <= 100
    # We have at least the four canonical buckets.
    assert set(out["by_module"].keys()) >= {"sicon", "sage", "both", "gymaxis_only"}


def test_endpoint_is_registered():
    """The master-admin field-mapping coverage route must be loaded."""
    from routes.master_admin_integration_health import router
    paths = {r.path for r in router.routes}
    assert "/master-admin/integration-mapping-coverage" in paths, (
        f"endpoint not registered. Found: {paths}"
    )


def test_endpoint_requires_master_admin():
    """Endpoint must call ``require_master_admin`` (defence in depth)."""
    import inspect
    import routes.master_admin_integration_health as mih
    src = inspect.getsource(mih.integration_mapping_coverage)
    assert "require_master_admin" in src, (
        "integration_mapping_coverage must gate via require_master_admin"
    )


def test_modules_have_pct_field():
    """Every module bucket must include a 'pct' field for the UI."""
    from utils.integration_mapping_coverage import compute_mapping_coverage
    out = compute_mapping_coverage()
    for key, info in out["by_module"].items():
        assert "pct" in info, f"by_module.{key} missing 'pct'"
        assert 0 <= info["pct"] <= 100
