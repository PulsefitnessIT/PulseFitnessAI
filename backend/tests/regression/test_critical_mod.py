"""Regression: MOD critical path.

The MOD portal is a separate brand + portal-isolation contract:
  • MOD account → /MODService only (not /pulse).
  • Non-MOD account → /pulse only (not /MODService).
  • HQ tier (mod_org / mod_branch) rollup endpoints aggregate child
    sites — equipment, issues, capex, gym-health-score.
  • Drilldown into a non-descendant site returns 403.
  • Bulk-import seeds sites + emits temp credentials.

These are isolated unit-style tests safe to run in any environment.
"""
# h113f — portal isolation (login orchestration)
from tests.test_iter_216h113f_mod_portal_isolation import (  # noqa: F401
    test_mod_account_on_mod_portal_succeeds,
    test_mod_account_on_standard_portal_blocked_with_clear_message,
    test_non_mod_account_on_mod_portal_blocked,
    test_non_mod_account_on_standard_portal_succeeds,
)
# h120 — HQ scope rollup contract
from tests.test_iter_216h120_mod_scope_rollup import (  # noqa: F401
    test_sites_returns_real_equipment_counts_for_mod_children,
    test_equipment_collective_rollup_for_mod_hq,
    test_equipment_drilldown_returns_only_that_site,
    test_issues_collective_rollup_for_mod_hq,
    test_capex_analysis_aggregates_whole_estate_for_mod_hq,
    test_capex_drilldown_returns_only_that_site,
    test_gym_health_score_drilldown_for_mod_hq,
    test_gym_health_score_collective_rollup_for_mod_hq,
    test_drilldown_into_unrelated_site_is_403,
    test_qr_endpoints_serve_for_mod_hq_child_equipment,
)
# h117 — bulk import contract (template + validation)
from tests.test_iter_216h117_mod_bulk_import import (  # noqa: F401
    test_template_download_returns_canonical_headers,
    test_bulk_import_requires_master_admin,
    test_bulk_import_creates_sites_and_returns_credentials,
    test_bulk_import_rejects_missing_site_name,
    test_bulk_import_inherits_branch_when_parent_is_mod_branch,
)
