"""Iter 220e3 — Phase D/E/F/G frontend surfaces wired through.

Pins that the public accept page, renewals dashboard, reports
dashboard and "Send / PDF" actions on contract detail all live in
the source. Frontend-only assertions — backend behaviour is covered
by ``test_iter_220e3_contracts_phase_def_g.py``.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_public_accept_page_renders_signature_canvas():
    src = _read("pages/CRM/Contracts/PublicContractAcceptPage.js")
    assert 'data-testid="public-accept-page"' in src
    assert 'data-testid="accept-canvas"' in src
    assert 'data-testid="accept-sign-btn"' in src
    # POSTs to the public sign endpoint.
    assert "/crm/v2/public/contracts/${token}/sign" in src


def test_public_accept_route_registered():
    src = _read("routes/AppRoutes.js")
    assert "/contracts/accept/:token" in src
    assert "PublicContractAcceptPage" in src


def test_reports_and_renewals_dashboards_wire_into_crm_contracts():
    src = _read("pages/CRM/CRMContracts.js")
    assert "ContractsReportsDashboard" in src
    assert "ContractsRenewalsDashboard" in src
    # Top-level view switcher.
    assert 'view-tab-list' in src
    assert 'view-tab-renewals' in src
    assert 'view-tab-reports' in src


def test_contract_detail_exposes_pdf_and_send_buttons():
    src = _read("pages/CRM/CRMContracts.js")
    assert 'contract-download-pdf-btn' in src
    assert 'contract-send-btn' in src
    # PDF download hits the auth'd contract PDF endpoint.
    assert "/crm/v2/contracts/${contractId}/pdf" in src


def test_renewals_dashboard_has_run_reminders_button():
    src = _read("pages/CRM/Contracts/ContractDashboards.js")
    assert 'run-renewal-reminders-btn' in src
    assert "/crm/v2/contracts/renewals/run-reminders" in src
    # Renders the three buckets explicitly.
    assert "renewal-bucket-${b.key}" in src
    # All three thresholds present.
    assert "'30'" in src and "'60'" in src and "'90'" in src
