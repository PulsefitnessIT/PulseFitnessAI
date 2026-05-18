"""Regression: Memberships critical path.

Re-exports test functions from per-iter files that protect the core
Memberships journey. Run via:

    pytest backend/tests/regression/test_critical_memberships.py -q

Anyone touching Memberships should run *this* file before shipping.
"""
# h201 — Instructor create: email format + phone required
from tests.test_iter_216h201_instructor_validation import (  # noqa: F401
    test_create_instructor_rejects_missing_email,
    test_create_instructor_rejects_invalid_email_format,
    test_create_instructor_rejects_missing_phone,
    test_create_instructor_rejects_whitespace_only_phone,
    test_create_instructor_happy_path_inserts_doc,
    test_create_instructor_trims_whitespace_on_email_and_phone,
)
# h207 — Edit drawer parity (Members + Instructors)
from tests.test_iter_216h207_edit_drawer_gdpr import (  # noqa: F401
    test_member_patch_rejects_invalid_email,
    test_member_patch_rejects_empty_phone,
    test_member_patch_rejects_empty_emergency_phone,
    test_member_patch_stamps_gdpr_consent_audit,
    test_member_patch_skips_consent_when_unchanged,
    test_create_instructor_requires_gdpr_consent,
    test_create_instructor_with_gdpr_stamps_audit,
    test_patch_instructor_stamps_consent_on_change,
    test_patch_instructor_rejects_invalid_email,
)

# h216 — Memberships module gate: orgs without operations don't see "Add equipment"
from tests.test_iter_216h216_activation_module_filter import (  # noqa: F401
    test_memberships_only_org_hides_equipment_milestone,
)
