"""Regression: CRM critical path.

Protects the customer-facing CRM concerns:
  • Coverage resolver (Operations equipment ↔ CRM aftersales contract).
  • Portal pills surface CRM access only for entitled roles.
  • CRM login falls back to platform password for cross-provisioned
    accounts (single-credential UX for owners + master admins).
  • Tags endpoint aggregates by frequency.

Note: live-server suites (test_crm_contracts.py, test_crm_team_management.py)
intentionally stay in their own files — they require uvicorn + auth tokens.
"""
# h198 — Equipment-CRM coverage resolver
from tests.test_iter_216h198_equipment_crm_coverage import (  # noqa: F401
    test_no_warranty_no_contract_returns_no_coverage,
    test_active_gold_contract_returned_as_best,
    test_higher_tier_wins_over_lower_tier_when_both_active,
    test_expired_contract_is_excluded_from_coverage,
    test_cancelled_status_contract_is_excluded,
    test_contract_expiring_within_90d_flagged_as_expiring_soon,
    test_manufacturer_warranty_still_surfaces_independently_of_crm,
    test_returns_404_when_equipment_not_found,
    test_orphan_contract_asset_without_matching_contract_is_skipped,
)
# h197 — Portal pills + CRM login fallback
from tests.test_iter_216h197_crm_auth_and_pills import (  # noqa: F401
    test_portal_pills_owner_with_crm_enabled_module,
    test_portal_pills_account_type_full_implies_crm,
    test_portal_pills_no_crm_for_basic_org,
    test_portal_pills_master_admin_always_has_crm_and_pulse_platform,
    test_crm_login_falls_back_to_platform_password_for_cross_provisioned,
    test_crm_login_creates_crm_users_row_when_missing,
    test_crm_login_rejects_wrong_platform_password,
    test_crm_login_native_password_still_works,
)
# h195 — CRM tags aggregation
from tests.test_iter_216h195_crm_tags import (  # noqa: F401
    test_tags_endpoint_aggregates_by_frequency,
    test_tags_endpoint_skips_blanks_and_none,
    test_tags_endpoint_handles_empty_collections,
)
