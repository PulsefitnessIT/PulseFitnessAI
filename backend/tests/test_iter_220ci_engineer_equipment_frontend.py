"""Iter 220ci — Engineer Equipment Tab · frontend wiring pins.

The backend test file already covers the API contract. This file pins
the JS-side glue that's easy to silently break with a future refactor:

  * Routes ``/svc/engineer/equipment`` + ``/svc/engineer/equipment/new``
    are registered in ``routes/AppRoutes.js``.
  * The Engineer Workspace sidebar exposes a nav button to the
    Equipment list (so the desktop 3-column UI has an entry point).
  * The mobile Home (EngineerHomeV2) exposes a Quick Action tile.
  * The WorkVisitMachinesCard inside a job shows a "New asset" link
    that pre-fills ``case_id=`` — closes the "create + auto-attach"
    flow the operator asked for.
  * Critical data-testids are present so the testing agent can drive
    the form end-to-end.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_routes_register_equipment_pages():
    src = _read("routes/AppRoutes.js")
    assert 'path="/svc/engineer/equipment"' in src
    assert 'path="/svc/engineer/equipment/new"' in src
    # Lazy-loaded with the named export wrapper.
    assert "ServiceOpsEngineerEquipmentForm" in src
    assert "EngineerEquipmentForm" in src


def test_workspace_sidebar_has_equipment_nav():
    src = _read("pages/ServiceOps/Engineer/EngineerWorkspace.js")
    assert 'testid="ws-nav-equipment"' in src
    assert "/svc/engineer/equipment" in src


def test_home_v2_has_equipment_quick_action():
    src = _read("pages/ServiceOps/Engineer/EngineerHomeV2.js")
    assert 'testid="qa-equipment"' in src
    assert "/svc/engineer/equipment" in src


def test_work_visit_machines_card_has_new_asset_link():
    src = _read("pages/ServiceOps/Engineer/WorkVisitMachinesCard.js")
    assert 'data-testid="machines-new-asset-link"' in src
    # Must pre-fill case_id query so the new asset auto-attaches.
    assert "/svc/engineer/equipment/new?case_id=" in src


def test_equipment_form_exposes_all_required_testids():
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    expected = [
        # List page.
        "engineer-equipment-page",
        "equipment-add-btn",
        "equipment-search-input",
        "equipment-refresh-btn",
        # Form page.
        "engineer-equipment-form-page",
        "equipment-form-name",
        "equipment-form-type",
        "equipment-form-manufacturer",
        "equipment-form-model",
        "equipment-form-location",
        "equipment-form-serial",
        "equipment-form-status",
        "equipment-form-notes",
        "equipment-form-submit",
    ]
    for tid in expected:
        assert tid in src, f"missing data-testid={tid!r} in EngineerEquipment.js"


def test_equipment_form_mandatory_fields_marked_with_asterisk():
    """The form is meant to make the FIVE mandatory fields visually
    obvious. We pin that by counting ``required`` props on FormField
    components — must be at least 5 (name, type, manufacturer, model,
    location). Site becomes a 6th when multi-site."""
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    required_count = len(re.findall(r"<FormField[^>]*\brequired\b", src))
    assert required_count >= 5, (
        f"expected ≥5 required FormFields, found {required_count}"
    )
