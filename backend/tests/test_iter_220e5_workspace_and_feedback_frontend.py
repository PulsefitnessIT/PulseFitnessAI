"""Iter 220e5 — Frontend wiring: Review Queue + workspace badge + entitlement panel.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_review_queue_component_consumes_feedback_endpoints():
    src = _read("pages/CRM/Contracts/ContractReviewQueue.js")
    assert 'data-testid="contract-review-queue"' in src
    assert "/crm/v2/contracts/feedback-queue" in src
    assert "/crm/v2/contracts/feedback/${row.id}/action" in src
    # Three coordinator actions surfaced per open row.
    for action in ("review-accept-", "review-reject-", "review-note-"):
        assert action in src


def test_crm_contracts_page_renders_workspace_badge_and_review_tab():
    src = _read("pages/CRM/CRMContracts.js")
    assert 'data-testid="workspace-mode-badge"' in src
    assert 'view-tab-review' in src
    assert "useWorkspaceMode" in src
    # Review tab is gated on capabilities so future modes can hide it.
    assert "workspace.capabilities?.show_review_queue" in src


def test_engineer_entitlement_panel_exists_and_posts_feedback():
    src = _read("pages/ServiceOps/Engineer/EngineerEntitlementPanel.js")
    assert 'data-testid="engineer-entitlement-panel"' in src
    # Reads the new entitlement endpoint.
    assert "/svc/engineer/jobs/${caseId}/contract-entitlement" in src
    # Posts feedback back to CRM.
    assert "/svc/engineer/jobs/${caseId}/contract-feedback" in src
    # All seven engineer-facing yes/no fields render via `entitlement-fields`.
    assert 'data-testid="entitlement-fields"' in src


def test_engineer_job_detail_no_entitlement_panel_on_summary():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Iter 220ea·7 — EngineerEntitlementPanel was removed from the
    # Summary tab (it confused engineers on jobs without a CRM contract
    # link). Cover context is now conveyed by the cover banner + the
    # rose "Chargeable" pill. Guard against accidental re-introduction.
    assert "import EngineerEntitlementPanel" not in src
    assert "<EngineerEntitlementPanel" not in src
    # The cover banner is still the canonical cover surface on Summary.
    assert 'data-testid="jaag-cover-banner"' in src
