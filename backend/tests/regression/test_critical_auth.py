"""Regression: Auth critical path.

Protects the Master Admin "why did this login fail?" diagnostics
journey — the trust-recovery work in h210.
"""
from tests.test_iter_216h210_login_failure_reason import (  # noqa: F401
    test_user_not_found_reason_audited,
    test_wrong_password_reason_audited,
    test_account_locked_reason_audited,
    test_login_events_endpoint_surfaces_failure_reason,
    test_client_errors_endpoint_master_admin_only,
    test_client_errors_endpoint_returns_grouped_counts,
)
