"""Iter 220e3 — Frontend wiring: Contract Wizard + Comparison Matrix + Cover tab.

Pins that the Phase B + Phase C UI surfaces actually exist in the
React source so they can't silently disappear during refactors.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_wizard_component_lives_in_contracts_folder():
    src = _read("pages/CRM/Contracts/ContractWizard.js")
    # The 10 steps spec'd by the operator must all be present.
    expected_steps = [
        "Customer & Site", "Assets", "Cover Type", "Inclusions",
        "Exclusions", "Consumables", "Response Times", "Pricing",
        "Terms", "Review & Send",
    ]
    for step in expected_steps:
        assert step in src, f"Wizard missing step '{step}'"
    # Pricing helper produces a margin %.
    assert "margin_percent" in src
    # Default export name is stable so CRM page imports keep working.
    assert "export default function ContractWizard" in src


def test_matrix_component_renders_grouped_rows():
    src = _read("pages/CRM/Contracts/ContractMatrix.js")
    assert 'data-testid="contract-comparison-matrix"' in src
    # Renders per-item rows and per-cell test ids so the PDF reuse
    # and Playwright reachability both work.
    assert "matrix-row-${item.key}" in src
    assert "matrix-cell-${col.id}-${item.key}" in src
    # Response-time band row.
    assert "matrix-row-rt-${band.key}" in src


def test_crm_contracts_page_renders_wizard_button_and_new_tabs():
    src = _read("pages/CRM/CRMContracts.js")
    assert "ContractWizard" in src
    assert 'open-contract-wizard-btn' in src
    assert 'create-contract-btn' in src        # quick-create still present
    # New Cover + Compare tabs are wired into the detail page.
    assert "id: 'cover'" in src
    assert "id: 'compare'" in src
    assert "CoverTab" in src
    assert "CompareTab" in src


def test_catalog_hook_provides_fallback_so_offline_still_renders():
    src = _read("pages/CRM/Contracts/contractCatalog.js")
    # If the API is briefly unavailable, the fallback constant ships
    # enough catalog to keep the wizard usable.
    assert "FALLBACK_CATALOG" in src
    assert "useContractCatalog" in src
    assert "useContractTemplates" in src
    # Treadmill belts/beds + upholstery must exist in the fallback
    # so the wizard works the moment a tenant opens it.
    for key in ("treadmill_beds", "treadmill_belts", "upholstery"):
        assert key in src
