"""Shared test-credentials loader (Iter 215k).

Why this exists: code review flagged ~48 occurrences of test credentials
hardcoded across the test suite. The risk is low — these are documented
fixtures seeded into a local-only test DB, also recorded in
`/app/memory/test_credentials.md` — but it's still cleaner to centralise
the values and let CI override via environment variables when needed.

Usage:
    from tests.test_credentials import OPERATOR_EMAIL, OPERATOR_PASSWORD
    # or
    from tests.test_credentials import creds
    email, password = creds("operator")

Environment overrides (set in CI to use isolated test accounts):
    TEST_OPERATOR_EMAIL / TEST_OPERATOR_PASSWORD
    TEST_MEMBER_EMAIL / TEST_MEMBER_PASSWORD
    TEST_MASTER_ADMIN_EMAIL / TEST_MASTER_ADMIN_PASSWORD
    TEST_CRM_USER_EMAIL / TEST_CRM_USER_PASSWORD
    TEST_STUDIO_OPERATOR_EMAIL / TEST_STUDIO_OPERATOR_PASSWORD
"""
import os


def _env_or(key: str, default: str) -> str:
    """Return env var if set, else the documented fallback."""
    return os.environ.get(key, default)


# ── Operator (Tottenham/Pulse Pro) ──────────────────────────────
OPERATOR_EMAIL = _env_or("TEST_OPERATOR_EMAIL", "lee.somers@pulsefitness.com")
OPERATOR_PASSWORD = _env_or("TEST_OPERATOR_PASSWORD", "TempPass123!")

# ── Studio operator (Leeds, used by win-back tests) ─────────────
STUDIO_OPERATOR_EMAIL = _env_or("TEST_STUDIO_OPERATOR_EMAIL", "studio.leeds@gymaxisai.com")
STUDIO_OPERATOR_PASSWORD = _env_or("TEST_STUDIO_OPERATOR_PASSWORD", "Studio2026!")

# ── Member (Emma Wright demo account) ───────────────────────────
MEMBER_EMAIL = _env_or("TEST_MEMBER_EMAIL", "emma.wright@demo.gymaxis")
MEMBER_PASSWORD = _env_or("TEST_MEMBER_PASSWORD", "Member2026!")

# ── Master Admin ────────────────────────────────────────────────
MASTER_ADMIN_EMAIL = _env_or("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = _env_or("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")

# ── CRM Manager (Pulse Fitness, Tottenham) ──────────────────────
CRM_USER_EMAIL = _env_or("TEST_CRM_USER_EMAIL", "craig.henshall@pulsefitness.com")
CRM_USER_PASSWORD = _env_or("TEST_CRM_USER_PASSWORD", "Test123!")


def creds(role: str) -> tuple[str, str]:
    """Lookup helper: creds("operator") → (email, password)."""
    table = {
        "operator": (OPERATOR_EMAIL, OPERATOR_PASSWORD),
        "studio": (STUDIO_OPERATOR_EMAIL, STUDIO_OPERATOR_PASSWORD),
        "member": (MEMBER_EMAIL, MEMBER_PASSWORD),
        "master_admin": (MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD),
        "crm_user": (CRM_USER_EMAIL, CRM_USER_PASSWORD),
    }
    if role not in table:
        raise KeyError(f"Unknown role '{role}'. Valid: {sorted(table)}")
    return table[role]
