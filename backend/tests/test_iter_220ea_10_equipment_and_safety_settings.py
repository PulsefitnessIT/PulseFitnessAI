"""Iter 220ea·10 — Equipment redesign, Account-Settings H&S link,
per-job H&S waiver.

Three connected fixes off a live user report:

1. The Equipment tab's action row was 3 buttons that stacked
   vertically on a 412 px phone, and the machine row truncated
   names + hid serial numbers. Both redesigned.
2. The H&S template editor was only reachable from Service Desk
   (the platform admin console). Now also reachable from the
   Engineer App's Account Settings drawer — closer to where the
   engineer actually works.
3. Some visits don't need an H&S signoff (parts drop, courtesy
   check, doc-only visit). The expanded checklist now has a "Not
   needed for this job" affordance that POSTs to a new
   `/safety/waive` endpoint and records the audit trail.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
MACHINES   = FRONTEND / "pages/ServiceOps/Engineer/WorkVisitMachinesCard.js"
SETTINGS   = FRONTEND / "pages/ServiceOps/Engineer/EngineerAccountSettings.js"
ROUTES     = FRONTEND / "routes/AppRoutes.js"


def _read(p: Path) -> str:
    return p.read_text()


# ── 1 · Equipment tab redesign ───────────────────────────────────


def test_machines_action_row_uses_grid_layout():
    """The action buttons (From site · New asset) now sit in a
    `grid grid-cols-2` so they're equal-width and never stack
    vertically on a phone. Iter 220ea·11 dropped the "Add
    machine" button — see test_iter_220ea_11_equipment_cleanups."""
    src = _read(MACHINES)
    assert 'className="grid grid-cols-2 gap-2"' in src
    # Two surviving test-ids.
    assert 'data-testid="machines-load-from-site-btn"' in src
    assert 'data-testid="machines-new-asset-link"' in src


def test_machine_row_name_no_longer_truncated():
    src = _read(MACHINES)
    # The row name is no longer wrapped in a `truncate` element —
    # it now uses `break-words` so long machine names wrap to a
    # second line instead of disappearing into an ellipsis.
    assert 'text-sm font-extrabold text-slate-900 leading-snug break-words' in src
    # And the meta line carries the serial number.
    assert 'data-testid={`machine-row-meta-${row.id}`}' in src
    assert 'font-mono">SN ' in src


def test_machine_row_action_buttons_on_own_line():
    """Serviced / Cleaned pills moved off the header row onto
    their own action row so the header has the full width for
    the machine name + meta."""
    src = _read(MACHINES)
    # The row root is now a `space-y-2` column container.
    assert 'p-3 space-y-2"' in src
    # And the Serviced / Cleaned buttons are rendered AFTER the
    # header row inside a `pl-9` action row.
    assert 'flex items-center gap-2 pl-9' in src


# ── 2 · Account Settings → H&S checklist link ───────────────────


def test_account_settings_has_safety_row():
    src = _read(SETTINGS)
    assert 'data-testid="engineer-settings-section-safety"' in src
    # The Row component takes a `testid` prop and forwards it as
    # `data-testid` on the outer button (see the helper at the
    # top of EngineerAccountSettings.js).
    assert 'testid="engineer-settings-safety-row"' in src
    assert "Pre-job H&S checklist" in src
    # And it routes to the dedicated engineer-side template editor.
    assert "navigate('/svc/engineer/h-s-checklist')" in src


def test_safety_template_route_registered():
    src = _read(ROUTES)
    assert '/svc/engineer/h-s-checklist' in src
    # And the lazy import points at the existing admin component.
    assert "ServiceOpsSafetyTemplateAdmin" in src
    assert "@/pages/ServiceOps/SafetyTemplateAdmin" in src


# ── 3 · Per-job H&S waiver UI ────────────────────────────────────


def test_inline_checklist_exposes_waive_affordance():
    src = _read(JOB_DETAIL)
    # The "Not needed for this job?" link toggles the waiver panel.
    assert 'data-testid="summary-safety-waive-open"' in src
    assert 'data-testid="summary-safety-waive-panel"' in src
    assert 'data-testid="summary-safety-waive-confirm"' in src
    assert 'data-testid="summary-safety-waive-cancel"' in src
    # And the reason input is bounded so we can't blow up the
    # audit trail with a 100 kB blob.
    assert "maxLength={500}" in src


def test_inline_checklist_waive_posts_correct_endpoint():
    src = _read(JOB_DETAIL)
    assert "/svc/engineer/jobs/${caseId}/safety/waive" in src
    # And we send `reason` (optional, may be empty).
    assert "{ reason: waiveReason.trim() }" in src


# ── 4 · Backend waiver endpoint contract ─────────────────────────


@pytest.mark.skip(
    reason="Requires running MongoDB + auth context; covered by E2E iter 220e_e2e_smoke."
)
def test_safety_waive_endpoint_marks_case_and_unblocks_timer():
    """Placeholder — E2E coverage lives in the Playwright suite."""
    pass


def test_safety_waive_route_registered_in_safety_module():
    src = (Path("/app/backend/routes/svc/safety.py")).read_text()
    assert '@router.post("/svc/engineer/jobs/{case_id}/safety/waive")' in src
    assert "engineer_safety_waive" in src
    # And the on-site timer gate honours the waiver flag.
    eng = (Path("/app/backend/routes/svc/engineer.py")).read_text()
    assert 'not case.get("safety_signoff_waived")' in eng
    assert 'safety_waived = bool(case.get("safety_signoff_waived"))' in eng
