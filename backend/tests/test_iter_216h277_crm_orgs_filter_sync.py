"""Iter 216h277 — CRM Orgs list shows orgs whose CRM module is enabled
via either storage shape.

The bug: Master Admin → CRM tab → Organisations rendered EMPTY even when
admins had enabled the CRM module on real tenants (Lee's Feb 2026
preview screenshot showed Third Space + Pulse with `modules.crm.enabled=
True` but the CRM Orgs tab was empty).

Root cause: an org's "CRM is enabled" signal lives in THREE places that
weren't synced by `PUT /organizations/{id}/features`:

  1. `portal_type` (legacy: 'service_portal' | 'crm' | 'both')
  2. `enabled_modules` (array, e.g. ['operations', 'crm'])
  3. `modules` (dict, e.g. {'crm': {'enabled': True, 'tier': 'pro'}})

The Features tab only writes (3); the Master Admin CRM Orgs tab only
read (1). Result: CRM-enabled orgs never showed up in the CRM tab.

This iter:

* Backend — `update_org_features` now derives (1) + (2) from the per-
  module dict so all three shapes stay coherent on every features
  PUT going forward.
* Backend — `update_org_details` (which writes `enabled_modules` from
  the Modules picker) now also writes the corresponding `modules`
  dict so the Features tab sees the same picture.

The matching frontend filter fix is verified by the existing UI
regression — this file pins the backend coherence guarantee.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from routes.master_admin_orgs import update_org_details, update_org_features


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"email": "admin@gymaxisai.com", "is_master_admin": True}


def test_features_put_syncs_enabled_modules_and_portal_type():
    """Toggling CRM on via the Features tab also flips enabled_modules
    and portal_type so the CRM Orgs filter (which reads either) finds it."""
    fake_db = MagicMock()
    # Existing org has zero modules dict + service_portal default.
    fake_db.organizations.find_one = AsyncMock(return_value={
        "features": {}, "modules": {},
    })

    calls: list = []

    async def capture_update(filt, update):
        calls.append({"filter": filt, "update": update})
    fake_db.organizations.update_one = AsyncMock(side_effect=capture_update)

    with patch("routes.master_admin_orgs.db", fake_db), \
         patch("routes.master_admin_orgs.assert_org_in_pulse_scope", AsyncMock()), \
         patch("routes.master_admin_orgs.log_activity", AsyncMock()):
        body = {"modules": {"crm": {"enabled": True, "tier": "pro"}}}
        result = _run(update_org_features("org-1", body=body, user=_admin()))

    assert result == {"success": True}
    # First call writes the $set; second call (audit log) may $push only.
    set_doc = next(c["update"]["$set"] for c in calls if "$set" in c["update"])
    # 1. modules dict updated
    assert set_doc["modules"]["crm"]["enabled"] is True
    # 2. enabled_modules array now contains crm
    assert "crm" in set_doc["enabled_modules"]
    # 3. portal_type reflects the change ('crm' since only CRM is on)
    assert set_doc["portal_type"] == "crm"


def test_features_put_disabling_all_modules_keeps_operations_default():
    """If all four modules are toggled off in one PUT, enabled_modules
    must never go empty (every org has Operations by product policy)."""
    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "features": {}, "modules": {"crm": {"enabled": True, "tier": "pro"}},
    })
    calls: list = []

    async def capture_update(filt, update):
        calls.append({"update": update})
    fake_db.organizations.update_one = AsyncMock(side_effect=capture_update)

    with patch("routes.master_admin_orgs.db", fake_db), \
         patch("routes.master_admin_orgs.assert_org_in_pulse_scope", AsyncMock()), \
         patch("routes.master_admin_orgs.log_activity", AsyncMock()):
        body = {"modules": {
            "operations": {"enabled": False, "tier": "pro"},
            "memberships": {"enabled": False, "tier": "pro"},
            "marketing":   {"enabled": False, "tier": "pro"},
            "crm":         {"enabled": False, "tier": "pro"},
        }}
        _run(update_org_features("org-1", body=body, user=_admin()))

    set_doc = next(c["update"]["$set"] for c in calls if "$set" in c["update"])
    assert set_doc["enabled_modules"] == ["operations"]
    assert set_doc["portal_type"] == "service_portal"


def test_features_put_both_modules_on_yields_portal_type_both():
    """An org with Operations + CRM enabled gets portal_type='both' so
    legacy consumers (route guards, sidebar) still see it correctly."""
    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={"features": {}, "modules": {}})
    calls: list = []

    async def capture_update(filt, update):
        calls.append({"update": update})
    fake_db.organizations.update_one = AsyncMock(side_effect=capture_update)

    with patch("routes.master_admin_orgs.db", fake_db), \
         patch("routes.master_admin_orgs.assert_org_in_pulse_scope", AsyncMock()), \
         patch("routes.master_admin_orgs.log_activity", AsyncMock()):
        body = {"modules": {
            "operations": {"enabled": True, "tier": "pro"},
            "crm":        {"enabled": True, "tier": "pro"},
        }}
        _run(update_org_features("org-1", body=body, user=_admin()))

    set_doc = next(c["update"]["$set"] for c in calls if "$set" in c["update"])
    assert set(set_doc["enabled_modules"]) >= {"operations", "crm"}
    assert set_doc["portal_type"] == "both"


def test_details_put_with_enabled_modules_syncs_modules_dict():
    """Saving the Modules picker on Details ALSO updates the per-module
    dict — so the Features tab sees the same enablement state."""
    fake_db = MagicMock()
    # `update_org_details` reads `modules` to merge tiers.
    fake_db.organizations.find_one = AsyncMock(return_value={"modules": {}})
    calls: list = []

    async def capture_update(filt, update):
        calls.append({"update": update})
        return MagicMock(matched_count=1)
    fake_db.organizations.update_one = AsyncMock(side_effect=capture_update)

    with patch("routes.master_admin_orgs.db", fake_db), \
         patch("routes.master_admin_orgs.assert_org_in_pulse_scope", AsyncMock()), \
         patch("routes.master_admin_orgs.log_activity", AsyncMock()), \
         patch("routes.master_admin_orgs._ensure_primary_contact_user", AsyncMock()):
        body = {"enabled_modules": ["operations", "crm"]}
        _run(update_org_details("org-1", body=body, user=_admin()))

    set_doc = next(c["update"]["$set"] for c in calls if "$set" in c["update"])
    assert set_doc["enabled_modules"] == ["operations", "crm"]
    assert set_doc["portal_type"] == "both"
    # Modules dict was rewritten to match.
    assert set_doc["modules"]["crm"]["enabled"] is True
    assert set_doc["modules"]["operations"]["enabled"] is True
    assert set_doc["modules"]["memberships"]["enabled"] is False
    assert set_doc["modules"]["marketing"]["enabled"] is False
    # Default tier present even on the newly-toggled-on entries.
    assert set_doc["modules"]["crm"]["tier"] == "pro"


def test_reconcile_script_union_of_three_storages():
    """The one-shot reconcile script (`scripts.reconcile_org_modules`)
    is non-destructive — it takes the UNION of dict + array so an
    org with CRM enabled in either place ends up enabled in both."""
    from scripts.reconcile_org_modules import _reconcile

    # Third-space-like org: dict says CRM+memberships+marketing,
    # array says only operations. UNION → all four.
    diff = _reconcile({
        "id": "tenant-3space",
        "portal_type": "service_portal",
        "enabled_modules": ["operations"],
        "modules": {
            "crm":         {"enabled": True, "tier": "pro"},
            "memberships": {"enabled": True, "tier": "pro"},
            "marketing":   {"enabled": True, "tier": "pro"},
        },
    })
    assert diff is not None
    assert set(diff["enabled_modules"]) == {"operations", "crm", "memberships", "marketing"}
    assert diff["portal_type"] == "both"

    # Invalid array value ('service_portal' is NOT a module id) gets stripped.
    diff2 = _reconcile({
        "id": "mod-1",
        "portal_type": "service_portal",
        "enabled_modules": ["service_portal"],
        "modules": {},
    })
    assert diff2 == {"enabled_modules": ["operations"]}

    # Already-coherent org → no diff.
    diff3 = _reconcile({
        "id": "happy-1",
        "portal_type": "service_portal",
        "enabled_modules": ["operations"],
        "modules": {"operations": {"enabled": True, "tier": "pro"}},
    })
    assert diff3 is None
