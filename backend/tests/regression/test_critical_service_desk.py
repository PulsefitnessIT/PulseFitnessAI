"""Regression: Service Desk critical path.

Protects the Operations → Service Desk bridge end-to-end:
  • Auto-warranty resolver picks contract over manufacturer warranty
    correctly when both exist (h199).
  • Issue→svc_case mirror routes the case as Contract / Warranty /
    Chargeable based on resolved coverage (h199).
  • Engineer phase-3 mobile flows: mileage log, parts consumption,
    invoice draft generation (h133).

Note: live-server integration suites (test_iter_216h152_svc_crm_sync.py
needing admin_sess fixture, test_service_desk_create_iteration199.py
needing admin_headers) intentionally stay in their own files — they need
a running uvicorn + master admin token. Add to this file only when a
new isolated unit test exists.
"""
# h199 — Auto warranty check + svc_case mirror routing
from tests.test_iter_216h199_auto_warranty_check import (  # noqa: F401
    test_coverage_to_case_meta_uncovered,
    test_coverage_to_case_meta_under_contract,
    test_coverage_to_case_meta_warranty_only,
    test_resolve_equipment_coverage_picks_contract_over_warranty,
    test_resolve_equipment_coverage_returns_chargeable_when_uncovered,
    test_resolve_equipment_coverage_handles_empty_input,
    test_resolve_coverage_for_issue_with_no_serial_returns_uncovered,
    test_resolve_coverage_for_issue_with_no_org_returns_uncovered,
    test_resolve_coverage_for_issue_finds_contract_via_serial,
    test_resolve_coverage_for_issue_missing_equipment_returns_uncovered,
    test_mirror_issue_routes_contract_case_when_under_gold,
    test_mirror_issue_routes_chargeable_when_uncovered,
    test_mirror_issue_routes_warranty_only_case,
)
# h133 — Engineer phase-3: mileage, parts, invoice draft
from tests.test_iter_216h133_engineer_phase3 import (  # noqa: F401
    test_mileage_endpoint_creates_logs_and_lists,
    test_mileage_endpoint_rejects_zero_miles,
    test_mileage_endpoint_404s_for_unknown_case,
    test_parts_use_creates_allocation_marked_fulfilled,
    test_parts_consume_flips_existing_allocation,
    test_generate_invoice_draft_composes_all_three_sources,
    test_generate_invoice_draft_rejects_empty_job,
)
