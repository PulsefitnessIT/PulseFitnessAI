"""Iter 220di — Admin React pages for PTW templates + COSHH register.

Pure-frontend feature surface; the backend API was already shipped
in Iter 220de. This file pins:

  * `ComplianceAdmin.js` exists and renders both PTW + COSHH tabs.
  * Component wires to the correct endpoints (POST/DELETE).
  * `ServiceDeskPage.js` mounts the new `compliance` insights tab.
  * Stable test IDs for the fork testing agent.

Lightweight live-endpoint smoke at the bottom: the underlying API
must remain reachable (it's the prerequisite for the admin page).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1 · Frontend wiring ──────────────────────────────────────────


def test_compliance_admin_component_exists():
    src = Path("/app/frontend/src/pages/ServiceOps/ComplianceAdmin.js").read_text()
    # Two named sub-components keep code-review legible.
    assert "function PtwAdmin" in src
    assert "function CoshhAdmin" in src
    assert "export default function ComplianceAdmin" in src


def test_compliance_admin_wires_correct_endpoints():
    src = Path("/app/frontend/src/pages/ServiceOps/ComplianceAdmin.js").read_text()
    # All four backend endpoints from Iter 220de.
    assert "/svc/compliance/ptw/templates" in src
    assert "/svc/compliance/coshh" in src
    # Soft-delete (DELETE) on both surfaces.
    assert "axios.delete(`${API}/svc/compliance/ptw/templates/${row.id}`" in src
    assert "axios.delete(`${API}/svc/compliance/coshh/${row.id}`" in src
    # POSTs send the right body keys.
    assert "hazard_category" in src
    assert "hazard_class" in src
    assert "sds_url" in src
    assert "validity_hours" in src


def test_compliance_admin_has_stable_test_ids():
    src = Path("/app/frontend/src/pages/ServiceOps/ComplianceAdmin.js").read_text()
    # Literal data-testid attributes in JSX.
    literal_ids = (
        "compliance-admin", "compliance-admin-tabs",
        # PTW
        "ptw-draft-name", "ptw-draft-category", "ptw-draft-validity",
        "ptw-draft-submit", "ptw-list", "ptw-empty",
        # COSHH
        "coshh-draft-name", "coshh-draft-supplier",
        "coshh-draft-class", "coshh-draft-sds", "coshh-draft-controls",
        "coshh-draft-submit", "coshh-list", "coshh-empty",
    )
    for tid in literal_ids:
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Test IDs passed via component prop appear as string-literal values.
    for tid in (
        "compliance-admin-tab-ptw", "compliance-admin-tab-coshh",
        "ptw-admin", "coshh-admin",
        "ptw-confirm-delete", "coshh-confirm-delete",
    ):
        assert f'"{tid}"' in src, f"missing prop-passed test-id: {tid}"


def test_service_desk_page_mounts_compliance_tab():
    src = Path("/app/frontend/src/pages/ServiceDeskPage.js").read_text()
    # Lazy import.
    assert "OpsCompliance" in src
    assert "./ServiceOps/ComplianceAdmin" in src
    # New insights tab declared + routed.
    assert "id: 'compliance'" in src
    assert "case 'compliance':" in src


# ── 2 · Backend prereq still healthy ─────────────────────────────


def test_ptw_template_list_endpoint_still_returns_seed():
    """Belt-and-braces: a regression on the backend endpoint would
    leave the new admin page perpetually empty. Pin the shape."""
    fdb = MagicMock()
    fdb.svc_ptw_templates.count_documents = AsyncMock(return_value=3)
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.to_list = AsyncMock(return_value=[
        {"id": "t1", "name": "Hot Work", "hazard_category": "hot_work",
         "validity_hours": 8, "hazards": [], "controls": []},
    ])
    fdb.svc_ptw_templates.find = MagicMock(return_value=cur)

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import list_ptw_templates
            return await list_ptw_templates(user={
                "id": "u-1", "organization_id": "org-1",
            })

    out = _run(run())
    assert "items" in out
    assert "categories" in out
    assert len(out["items"]) == 1


def test_coshh_list_endpoint_still_returns_seed():
    fdb = MagicMock()
    fdb.svc_coshh_entries.count_documents = AsyncMock(return_value=3)
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.to_list = AsyncMock(return_value=[
        {"id": "e1", "name": "WD-40", "hazard_class": "flammable",
         "active": True},
    ])
    fdb.svc_coshh_entries.find = MagicMock(return_value=cur)

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import list_coshh_entries
            return await list_coshh_entries(user={
                "id": "u-1", "organization_id": "org-1",
            })

    out = _run(run())
    assert "items" in out
    assert "hazard_classes" in out
    assert "flammable" in out["hazard_classes"]


def test_delete_coshh_is_soft_delete_not_destructive():
    """The admin page renders 'Retired' for soft-deleted entries.
    Pin the backend honours that (sets active=False, does NOT
    delete_one)."""
    fdb = MagicMock()
    fdb.svc_coshh_entries.update_one = AsyncMock(
        return_value=MagicMock(matched_count=1),
    )
    fdb.svc_coshh_entries.delete_one = AsyncMock()  # should NOT be called

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import delete_coshh_entry
            return await delete_coshh_entry(
                entry_id="e1", user={"id": "u-1", "organization_id": "org-1",
                                     "role": "owner"},
            )

    out = _run(run())
    assert out["ok"] is True
    fdb.svc_coshh_entries.update_one.assert_awaited_once()
    fdb.svc_coshh_entries.delete_one.assert_not_called()
    # Update sets active=False.
    set_doc = fdb.svc_coshh_entries.update_one.await_args.args[1]["$set"]
    assert set_doc["active"] is False
