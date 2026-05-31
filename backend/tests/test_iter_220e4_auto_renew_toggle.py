"""Iter 220e4-followup — discoverable Auto-renew toggle.

Pins that the auto-renew opt-in is exposed both in the 10-step
wizard (Step 1) AND as a one-click toggle pill on the contract
Detail header — so contract coordinators don't have to dig into the
Edit modal to enable the autopilot.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_wizard_step1_exposes_auto_renew_toggle():
    src = _read("pages/CRM/Contracts/ContractWizard.js")
    assert 'data-testid="wizard-auto-renew-toggle"' in src
    # The autopilot prose is present so coordinators know what they're enabling.
    assert "autopilot will draft a renewal" in src
    # Default form carries the field.
    assert "auto_renew: false" in src
    # Finalise payload carries it through to the backend.
    assert "auto_renew: !!form.auto_renew" in src


def test_contract_detail_renders_one_click_auto_renew_toggle():
    src = _read("pages/CRM/CRMContracts.js")
    assert 'data-testid="contract-auto-renew-toggle"' in src
    # Optimistic UI hits the existing PUT endpoint.
    assert "toggleAutoRenew" in src
    assert '`${API}/crm/v2/contracts/${contractId}`' in src
    # Pill reflects current state.
    assert "Auto-renew: {contract.auto_renew ? 'On' : 'Off'}" in src
