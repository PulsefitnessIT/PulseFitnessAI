"""Iter 220ay — Wave 7 Security Hardening · Pen-test handover.

Regression-locks the W7 deliverables so a future agent can't
accidentally delete the pen-tester onboarding doc, the seeder script,
or any of the 6 production env-flag references that need to be flipped
on before the engagement starts.
"""
from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent
ONBOARDING = pathlib.Path(__file__).resolve().parents[2] / "memory" / "SECURITY_AUDIT" / "PEN_TEST_ONBOARDING.md"
SEEDER = ROOT / "scripts" / "seed_pentest_tenant.py"


def test_onboarding_doc_exists():
    assert ONBOARDING.exists(), f"missing {ONBOARDING}"


def test_onboarding_doc_lists_all_six_production_flags():
    text = ONBOARDING.read_text(encoding="utf-8")
    for flag in (
        "ENFORCE_MASTER_ADMIN_MFA",
        "ENFORCE_EMAIL_RECIPIENT_VALIDATION",
        "STRICT_AV_MODE",
        "CLAMAV_HOST",
        "MFA_ENCRYPTION_KEY",
        "SSRF_EXTRA_DENYLIST_HOSTS",
    ):
        assert flag in text, f"production flag {flag!r} missing from onboarding brief"


def test_onboarding_doc_includes_test_tenant_credentials():
    text = ONBOARDING.read_text(encoding="utf-8")
    for cred in (
        "pentest-owner@gymaxis.test",
        "pentest-mgr@gymaxis.test",
        "pentest-staff@gymaxis.test",
        "pentest-mfa@gymaxis.test",
        "pentest-org-001",
    ):
        assert cred in text, f"credential / identifier {cred!r} missing from brief"


def test_onboarding_doc_lists_in_scope_and_out_of_scope():
    text = ONBOARDING.read_text(encoding="utf-8").lower()
    assert "in-scope" in text or "in scope" in text
    assert "out-of-scope" in text or "out of scope" in text


def test_onboarding_doc_links_risk_register():
    text = ONBOARDING.read_text(encoding="utf-8")
    # The brief must reference the risk register + audit baseline.
    assert "RISK_REGISTER.md" in text
    assert "SECURITY_AUDIT_PASS_1.md" in text


def test_seed_pentest_tenant_script_exists():
    assert SEEDER.exists(), f"missing {SEEDER}"


def test_seed_pentest_tenant_refuses_without_env_flag(monkeypatch):
    """The seeder must NEVER run by accident — it must bail unless
    ALLOW_PENTEST_SEED=true is explicitly set."""
    monkeypatch.delenv("ALLOW_PENTEST_SEED", raising=False)
    # Read the guard clause as text (the test isn't allowed to import
    # the module because that would touch the live MongoDB at startup).
    text = SEEDER.read_text(encoding="utf-8")
    assert "ALLOW_PENTEST_SEED" in text
    assert "Refusing to seed" in text


def test_seed_pentest_tenant_pins_org_id():
    text = SEEDER.read_text(encoding="utf-8")
    # Hard-coded so a future refactor can't drift into seeding into
    # a live org.
    assert "pentest-org-001" in text
    assert "pentest_tenant" in text  # tag so cleanup scripts can find it


def test_seed_pentest_tenant_includes_gdpr_erased_member():
    """F-12 RAG-context filter coverage needs at least one
    ``gdpr_erased=True`` member in the sample data so the pen-tester
    can verify that the AI assistant excludes them from context."""
    text = SEEDER.read_text(encoding="utf-8")
    assert '"gdpr_erased": True' in text


def test_test_credentials_md_references_pentest_tenant():
    """Ensure the central test-credentials file points at the sandbox
    so any agent (or testing subagent) can find the brief."""
    creds = pathlib.Path(__file__).resolve().parents[2] / "memory" / "test_credentials.md"
    text = creds.read_text(encoding="utf-8")
    assert "pentest-owner@gymaxis.test" in text
    assert "PEN_TEST_ONBOARDING.md" in text
