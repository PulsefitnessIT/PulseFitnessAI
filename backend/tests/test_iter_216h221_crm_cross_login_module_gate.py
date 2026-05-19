"""Iter 216h221 — CRM cross-login gate must read `modules.crm.enabled`
(the source of truth Master Admin's Feature Control panel writes to),
NOT the legacy `enabled_modules` array.

Reproduces Craig Henshall's "CRM is not enabled for your account" bug:
Master Admin had CRM toggled ON for Pulse Fitness Limited (Pulse Pro
account_type, `modules.crm.enabled=true`), yet the cross-login gate
read `enabled_modules` which the toggle never updates → 403.

These unit tests pin the contract going forward.
"""
from __future__ import annotations

from utils.module_access import has_module


def _org(account_type: str = "pulse_pro", modules_crm_enabled: bool | None = None, **extras) -> dict:
    """Build a synthetic org doc the same shape the cross-login gate sees."""
    org = {"id": "org-1", "account_type": account_type}
    if modules_crm_enabled is not None:
        org["modules"] = {"crm": {"enabled": modules_crm_enabled, "tier": "pro"}}
    org.update(extras)
    return org


def _user(account_type: str = "pulse_pro", is_master_admin: bool = False, **extras) -> dict:
    u = {
        "id": "u-1",
        "email": "owner@example.com",
        "organization_id": "org-1",
        "account_type": account_type,
        "is_master_admin": is_master_admin,
        "role": "owner",
    }
    u.update(extras)
    return u


# ─── Pulse Pro with CRM toggle ON (Craig's case) ──────────────────────
def test_pulse_pro_with_modules_crm_enabled_grants_access():
    """Master Admin toggle ON → cross-login MUST pass.

    The legacy gate read `enabled_modules` (an array) which the toggle
    doesn't populate, causing a false 403 even with a green toggle.
    """
    user = _user("pulse_pro")
    org = _org("pulse_pro", modules_crm_enabled=True, enabled_modules=["operations"])
    assert has_module(user, org, "crm") is True


def test_pulse_pro_with_modules_crm_disabled_denies():
    """Toggle OFF → cross-login MUST 403."""
    user = _user("pulse_pro")
    org = _org("pulse_pro", modules_crm_enabled=False)
    assert has_module(user, org, "crm") is False


def test_pulse_pro_without_modules_field_uses_account_type_defaults():
    """An org with no `modules` map at all falls back to account-type defaults.

    Pulse Pro's default CRM access is OFF until master admin grants it,
    so the gate should 403 (matching the existing UX where managers
    need to ask master admin to switch CRM on).
    """
    user = _user("pulse_pro")
    org = _org("pulse_pro", modules_crm_enabled=None)
    assert has_module(user, org, "crm") is False


# ─── Full account_type (legacy) still works ───────────────────────────
def test_legacy_full_account_type_grants_crm_by_default():
    """The `full` account_type defaults to all-modules-on (legacy)."""
    user = _user("full")
    org = _org("full", modules_crm_enabled=None)
    assert has_module(user, org, "crm") is True


# ─── Master admin always bypasses ─────────────────────────────────────
def test_master_admin_always_has_crm_access():
    user = _user("pulse_pro", is_master_admin=True)
    org = _org("pulse_pro", modules_crm_enabled=False)
    assert has_module(user, org, "crm") is True


# ─── Lite account_type — CRM gated even with toggle ON ────────────────
def test_lite_account_type_with_crm_toggle_on_grants_when_no_trial():
    """Lite + bolt-on CRM is gated by an active trial, not just the
    toggle. With no trial overlay, the matrix denies regardless of
    `modules.crm.enabled`. This keeps the existing Lite paywall."""
    user = _user("lite")
    org = _org("lite", modules_crm_enabled=True)
    # Lite + bolt-on without an active trial → denied.
    assert has_module(user, org, "crm") is False
