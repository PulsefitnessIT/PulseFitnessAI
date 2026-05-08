"""
Iter 215dl — CRM Lite derived flag tests.

CRM Lite is bundled with Marketing. It must be:
  - True whenever marketing is enabled for the user/org
  - True whenever full CRM is enabled
  - False for tenants with neither
  - True for master admins (everything is on)
  - Per-staff overrides on Marketing must also drop CRM Lite
"""
from utils.module_access import resolve_module_access


def _user(account_type="pulse_pro", is_master=False, overrides=None):
    return {
        "id": "u-1",
        "account_type": account_type,
        "is_master_admin": is_master,
        "module_overrides": overrides,
    }


def _org(modules=None, account_type="pulse_pro"):
    return {"account_type": account_type, "modules": modules or {}}


def test_crm_lite_true_when_marketing_enabled():
    user = _user("pulse_pro")
    org = _org({"marketing": {"enabled": True}}, account_type="pulse_pro")
    out = resolve_module_access(user, org)
    assert out["marketing"] is True
    assert out["crm"] is False
    assert out["crm_lite"] is True


def test_crm_lite_true_when_full_crm_enabled():
    user = _user("pulse_pro")
    org = _org({"crm": {"enabled": True}}, account_type="pulse_pro")
    out = resolve_module_access(user, org)
    assert out["crm"] is True
    assert out["crm_lite"] is True


def test_crm_lite_false_when_neither_enabled():
    user = _user("pulse_pro")
    org = _org({}, account_type="pulse_pro")
    out = resolve_module_access(user, org)
    assert out["marketing"] is False
    assert out["crm"] is False
    assert out["crm_lite"] is False


def test_crm_lite_master_admin_always_true():
    user = _user("full", is_master=True)
    org = None
    out = resolve_module_access(user, org)
    assert out["crm_lite"] is True


def test_crm_lite_dropped_by_per_staff_override_on_marketing():
    user = _user("pulse_pro", overrides={"marketing": False, "crm": False})
    org = _org({"marketing": {"enabled": True}}, account_type="pulse_pro")
    out = resolve_module_access(user, org)
    # Override removes marketing → crm_lite must drop too.
    assert out["marketing"] is False
    assert out["crm_lite"] is False
