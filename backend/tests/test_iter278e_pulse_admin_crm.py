"""Iter 278e — Pulse Master Admin must never be locked out of modules.

A Pulse Master Admin has role ``pulse_master_admin`` and ``is_master_admin``
False (the platform flag is reserved for the GymAxis operator). The People
role editor markets the role as "platform-wide Master Admin access", so for
module entitlement they must be treated as a privileged admin. This was the
recurring "CRM is not enabled for your account" lock-out at CRM cross-login.

These are pure unit tests over the entitlement resolver — no network/DB.
"""
from utils.module_access import has_module, crm_modes, has_crm_access, resolve_module_access


PULSE_ADMIN = {"role": "pulse_master_admin", "is_master_admin": False, "organization_id": "pulse"}


def test_pulse_admin_gets_crm_when_org_default_off():
    org = {"account_type": "pulse_pro", "modules": {}}  # crm default False
    assert has_module(PULSE_ADMIN, org, "crm") is True
    assert has_crm_access(PULSE_ADMIN, org) is True
    assert crm_modes(PULSE_ADMIN, org) == {"leisure": True, "business": True}


def test_pulse_admin_gets_crm_when_org_doc_missing():
    # Cross-org admin whose organization_id doesn't resolve to a CRM org.
    assert has_module(PULSE_ADMIN, None, "crm") is True


def test_pulse_admin_override_cannot_lock_them_out():
    org = {"account_type": "pulse_pro", "modules": {}}
    locked = {**PULSE_ADMIN, "module_overrides": {"crm": False}}
    assert has_module(locked, org, "crm") is True


def test_pulse_admin_gets_all_modules():
    org = {"account_type": "lite", "modules": {}}
    access = resolve_module_access(PULSE_ADMIN, org)
    for key in ("operations", "memberships", "marketing", "crm"):
        assert access[key] is True, key


def test_is_pulse_admin_flag_also_recognised():
    user = {"role": "manager", "is_pulse_admin": True}
    assert has_module(user, {"account_type": "pulse_pro", "modules": {}}, "crm") is True


# ── Regression: ordinary staff must STILL be gated ────────────────────

def test_regular_staff_override_still_revokes():
    org = {"account_type": "pulse_pro", "modules": {"crm": {"enabled": True}}}
    staff = {"role": "manager", "is_master_admin": False, "module_overrides": {"crm": False}}
    assert has_module(staff, org, "crm") is False


def test_lite_org_staff_has_no_crm():
    staff = {"role": "manager"}
    assert has_module(staff, {"account_type": "lite", "modules": {}}, "crm") is False
