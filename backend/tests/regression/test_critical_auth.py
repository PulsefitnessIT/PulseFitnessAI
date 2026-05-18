"""Regression: Auth critical path.

Protects the Master Admin "why did this login fail?" diagnostics
journey + the 24h platform-issues aggregator (h210 + h215).
"""
from tests.test_iter_216h210_login_failure_reason import (  # noqa: F401
    test_user_not_found_reason_audited,
    test_wrong_password_reason_audited,
    test_account_locked_reason_audited,
    test_login_events_endpoint_surfaces_failure_reason,
    test_client_errors_endpoint_master_admin_only,
    test_client_errors_endpoint_returns_grouped_counts,
)
# h215 — Platform-issues-24h aggregator (Master Admin home tile)
from tests.test_iter_216h215_platform_issues_24h import (  # noqa: F401
    test_platform_issues_master_admin_only,
    test_platform_issues_green_when_quiet,
    test_platform_issues_amber_at_mid_volume,
    test_platform_issues_red_when_noisy,
    test_platform_issues_breakdown_contract,
)
