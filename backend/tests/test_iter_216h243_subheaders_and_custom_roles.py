"""Iter 216h243 — Sub-header platform sweep + custom staff roles.

Validates:

1. **ListPanel header suppression** — title + subtitle props are
   accepted but no longer rendered (one-place fix for every
   Memberships sub-tab).
2. **CRM sub-pages** — H1 and description blocks removed from
   CRMTerritories, CRMForecast, CRMReports. Page padding tightened
   from ``py-6 space-y-6`` to ``py-3 space-y-3`` so content sits
   flush under the tab pill bar.
3. **Custom staff roles endpoints** — ``GET /staffing/roles``,
   ``POST /staffing/roles``, ``DELETE /staffing/roles/{role}`` are
   registered; ``_allowed_roles_for(org_id)`` blends platform
   defaults with the org's ``custom_staff_roles``.
4. **Add Staff dialog** — role select carries the dynamic list +
   "+ Add new role…" option that pops an inline input.
5. **HR profile** — primary role field is editable with the same
   dynamic dropdown.
"""
from __future__ import annotations

import inspect
import pathlib
import re


def test_list_panel_suppresses_title_block():
    src = pathlib.Path("/app/frontend/src/components/shared/ListPanel.js").read_text()
    assert "const showTitleBlock = false" in src, "ListPanel title block must be suppressed"
    # Title + subtitle props must still be accepted on the API for backward compat.
    assert "title" in src and "subtitle" in src


def test_crm_subpages_h1_and_description_removed():
    """The three CRM sub-pages in the user's screenshots must no
    longer carry their old H1 + description blocks."""
    for fname, h1_text, desc_substr in (
        ("/app/frontend/src/pages/CRM/CRMTerritories.js",
            "Territory & coverage",
            "Define geographic coverage areas"),
        ("/app/frontend/src/pages/CRM/CRMForecast.js",
            "Forecast & quotas",
            "Track per-rep attainment"),
        ("/app/frontend/src/pages/CRM/CRMReports.js",
            "Reports & analytics",
            "Pipeline health, quote conversion"),
    ):
        text = pathlib.Path(fname).read_text(encoding="utf-8")
        assert f">{h1_text}<" not in text, f"{fname}: H1 '{h1_text}' still rendered"
        assert desc_substr not in text, f"{fname}: description '{desc_substr}…' still present"
    # Page padding tightened.
    for fname in (
        "/app/frontend/src/pages/CRM/CRMTerritories.js",
        "/app/frontend/src/pages/CRM/CRMForecast.js",
        "/app/frontend/src/pages/CRM/CRMReports.js",
    ):
        text = pathlib.Path(fname).read_text(encoding="utf-8")
        assert re.search(r'py-3 space-y-3', text), f"{fname}: tight padding not applied"


def test_custom_staff_roles_endpoints_registered():
    from routes.staffing import router
    paths = {r.path for r in router.routes}
    assert "/staffing/roles" in paths
    assert "/staffing/roles/{role}" in paths


def test_allowed_roles_for_helper_exists():
    from routes import staffing
    assert hasattr(staffing, "_allowed_roles_for")
    # Sanity-check signature is async.
    assert inspect.iscoroutinefunction(staffing._allowed_roles_for)


def test_create_staff_uses_allowed_roles_helper():
    from routes import staffing
    src = inspect.getsource(staffing.create_staff)
    assert "_allowed_roles_for" in src, "create_staff must validate against org-extended role set"


def test_update_staff_uses_allowed_roles_helper():
    from routes import staffing
    src = inspect.getsource(staffing.update_staff)
    assert "_allowed_roles_for" in src, "update_staff must validate against org-extended role set"


def test_add_staff_role_validation_paths():
    """The POST /staffing/roles endpoint must enforce length, dedupe,
    and reject collisions with platform defaults."""
    from routes import staffing
    src = inspect.getsource(staffing.add_staff_role)
    assert "max 60" in src or "len(name) > 60" in src
    assert "already a platform default" in src
    assert "already exists" in src


def test_staffing_console_dropdown_loads_dynamic_roles():
    src = pathlib.Path("/app/frontend/src/pages/LiteDashboard/StaffingConsole.js").read_text()
    assert "/staffing/roles" in src
    assert "+ Add new role" in src
    assert '__add_new__' in src
    assert 'data-testid="staff-add-role-new-input"' in src


def test_hr_profile_renders_primary_role_dropdown():
    src = pathlib.Path("/app/frontend/src/pages/LiteDashboard/staffing/HRTab.js").read_text()
    assert "/staffing/roles" in src
    assert 'data-testid="hr-primary-role"' in src
    assert "primary_role" in src
