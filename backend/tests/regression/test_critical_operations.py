"""Regression: Operations critical path.

The "log a fault" journey is the most-used in the platform. Protects:
  • POST /api/issues inherits site_id from equipment (h208)
  • Batch fault creation shares a job_id
  • Coverage meta (warranty / aftersales) stamped at intake (h199)
"""
from tests.test_iter_216h208_issue_site_inherit import (  # noqa: F401
    test_resolve_coverage_includes_site_id,
    test_resolve_coverage_handles_no_equipment_site_id,
    test_create_issue_stamps_site_id_from_equipment,
    test_create_issue_omits_site_id_when_equipment_has_none,
)

# h216 — Module-aware activation timeline (operations module gate)
from tests.test_iter_216h216_activation_module_filter import (  # noqa: F401
    test_operations_only_org_hides_memberships_milestones,
    test_full_account_type_sees_every_milestone,
    test_legacy_user_with_no_module_data_sees_all_milestones,
    test_no_org_returns_empty_timeline,
)
