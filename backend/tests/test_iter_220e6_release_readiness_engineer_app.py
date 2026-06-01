"""Iter 220e6 — Engineer App release-readiness gap closure.

Pins:
* ErrorBoundary wraps the engineer routes (#1).
* Outbox utility shape + retryable-status decisions (#2).
* AppRoutes wraps engineer routes with the boundary (#3 redirect lives).
* Window error reporter helper exists (#4).
* Outbox status pill component is mounted (#2 visibility).
* Entitlement endpoint hides the panel for contract-less tenants (#11).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── Gap #1 — Engineer route ErrorBoundary ────────────────────


def test_engineer_error_boundary_component_exists():
    src = _read("components/shared/EngineerErrorBoundary.jsx")
    # Class component with the React error-boundary lifecycle hooks.
    assert "getDerivedStateFromError" in src
    assert "componentDidCatch" in src
    # Posts the crash to the existing collector.
    assert "/client-errors" in src
    # Recoverable UI (not just a white screen with text).
    assert 'data-testid="engineer-error-boundary"' in src
    assert 'data-testid="engineer-eb-reset-btn"' in src


def test_app_routes_wraps_engineer_routes_with_boundary():
    src = _read("routes/AppRoutes.js")
    assert "import EngineerErrorBoundary" in src
    # Iter 220ea·24 — EVERY authenticated /svc/engineer/* route must be
    # wrapped in EngineerErrorBoundary so a render crash on any screen
    # shows the friendly fallback instead of white-screening the whole
    # SPA. Scan all such route lines and assert the boundary is present.
    import re

    route_lines = [
        ln for ln in src.splitlines()
        if 'path="/svc/engineer' in ln and "user ?" in ln
        and 'Navigate to="/login"' in ln
    ]
    # Sanity: we expect the full engineer surface (>25 routes).
    assert len(route_lines) >= 25, f"only found {len(route_lines)} engineer routes"
    unwrapped = [
        re.search(r'path="([^"]+)"', ln).group(1)
        for ln in route_lines
        if "EngineerErrorBoundary" not in ln
    ]
    assert not unwrapped, f"engineer routes not wrapped in error boundary: {unwrapped}"


# ── Gap #2 — Offline write outbox ─────────────────────────────


def test_outbox_module_exports_post_put_patch_and_drain():
    src = _read("utils/engineerOutbox.js")
    assert "export function outboxPost" in src
    assert "export function outboxPut" in src
    assert "export function outboxPatch" in src
    assert "export async function drainOutbox" in src
    # Retryable status set covers the actual network breakage codes.
    for code in ("0", "408", "429", "500", "502", "503", "504"):
        assert code in src
    # Uses IndexedDB primitives, not localStorage (LS would blow size).
    assert "indexedDB" in src
    # Drains on `online` event AND on a periodic ticker.
    assert "addEventListener('online'" in src
    assert "setInterval" in src


def test_outbox_status_pill_component_is_mounted_in_engineer_home():
    src = _read("pages/ServiceOps/Engineer/EngineerHomeV2.js")
    assert "OutboxStatusPill" in src
    assert "installEngineerErrorReporters" in src
    # The pill renders in the header so engineers see queued items.
    assert "<OutboxStatusPill" in src


def test_complete_job_call_uses_outbox():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The single most important mutating call (Complete job) now uses
    # the offline-safe outbox wrapper.
    assert "outboxPost(`${API}/svc/engineer/jobs/${job.id}/complete`" in src
    # Signature too — they ride together.
    assert "outboxPost(`${API}/svc/engineer/signature`" in src
    # User-visible toast acknowledges the queued state.
    assert "Saved offline" in src


# ── Gap #4 — Global JS error reporter ─────────────────────────


def test_global_error_reporter_helper_hooks_both_handlers():
    src = _read("utils/engineerStatusBoot.jsx")
    # Single install function — idempotent — covers both window
    # surfaces (sync errors AND unhandled promise rejections).
    assert "installEngineerErrorReporters" in src
    assert "addEventListener('error'" in src
    assert "addEventListener('unhandledrejection'" in src
    # Posts to the existing /client-errors collector.
    assert "/client-errors" in src


# ── Gap #11 — Entitlement panel hides on contract-less tenant ──


def test_entitlement_panel_hides_when_tenant_has_no_contracts():
    from routes.crm_contract_workspace import engineer_entitlement
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-solo",
    })
    fdb.crm2_contracts.find_one = AsyncMock(return_value=None)
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(engineer_entitlement("case-1",
                                        user={"id": "u-1", "organization_id": "org-solo"}))
    assert out["tenant_has_contracts"] is False
    assert out["tone"] == "neutral"
    assert out["label"] == ""


def test_entitlement_panel_still_red_when_tenant_uses_contracts_but_case_unlinked():
    from routes.crm_contract_workspace import engineer_entitlement
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-enterprise",
        # No contract_id — case isn't linked.
    })
    # Only call is the any_contract scan → returns a stub so the
    # tenant is known to use contracts elsewhere.
    fdb.crm2_contracts.find_one = AsyncMock(return_value={"id": "other-contract"})
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(engineer_entitlement("case-1",
                                        user={"id": "u-1", "organization_id": "org-enterprise"}))
    assert out["tenant_has_contracts"] is True
    assert out["tone"] == "red"
    assert "No contract on file" in out["label"]


def test_entitlement_panel_renders_neutral_branch_in_frontend():
    src = _read("pages/ServiceOps/Engineer/EngineerEntitlementPanel.js")
    # The panel suppresses itself completely on contract-less tenants
    # so the red "No contract" banner doesn't sit on every job.
    assert "tenant_has_contracts === false" in src
