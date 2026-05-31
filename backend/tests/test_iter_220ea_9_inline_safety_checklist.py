"""Iter 220ea·9 — Inline H&S checklist on Summary tab.

The Engineer App's H&S checklist UI was only ever in the legacy
`EngineerJobDetail.js` (Iter 216h89). When V2 launched the banner
on the Summary tab jumped to the Complete tab, where the
checklist UI was never ported — so engineers landed on a
dead-end. This iter ports the checklist inline into Summary so
the banner expands a working tickable card right there.

Backend endpoint reused as-is: `POST /api/svc/engineer/jobs/{case_id}/safety/signoff`
(see `routes/svc/safety.py:166`).
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"


def _read() -> str:
    return JOB_DETAIL.read_text()


# ── 1 · Banner now toggles inline checklist (no tab jump) ────────


def test_banner_no_longer_jumps_to_complete_tab():
    src = _read()
    # The old wiring is gone everywhere.
    assert "onJumpToSafety" not in src
    # The banner button now toggles local state.
    assert "setSafetyOpen(v => !v)" in src
    # And exposes aria affordances for screen readers.
    assert "aria-expanded={safetyOpen}" in src
    assert 'aria-controls="summary-safety-checklist-inline"' in src


# ── 2 · Inline checklist component ───────────────────────────────


def test_safety_checklist_inline_component_exists():
    src = _read()
    assert "function SafetyChecklistInline(" in src
    assert 'data-testid="summary-safety-checklist-inline"' in src
    assert 'data-testid="summary-safety-checklist-items"' in src


def test_inline_checklist_posts_to_correct_endpoint():
    """Re-uses the existing backend safety/signoff endpoint —
    `POST /api/svc/engineer/jobs/{caseId}/safety/signoff` — so
    the v1 endpoint contract (ticked_item_ids + signature_image +
    remarks) keeps working without backend changes."""
    src = _read()
    assert "/svc/engineer/jobs/${caseId}/safety/signoff" in src
    # And we send the canonical body shape.
    for key in ("ticked_item_ids", "signature_image", "remarks"):
        assert key in src


def test_inline_checklist_blocks_submit_when_required_items_missing():
    src = _read()
    assert "missingRequired" in src
    assert "Missing required items" in src
    assert "before signing off" in src


def test_inline_checklist_requires_signature():
    """The legacy v1 endpoint rejects an empty `signature_image`.
    The inline UI must guard the same boundary so the engineer
    sees a clear "Signature required" toast rather than a 400."""
    src = _read()
    assert "Signature required" in src
    assert "<SignatureCanvas" in src


def test_inline_checklist_close_button():
    src = _read()
    assert 'data-testid="summary-safety-checklist-close"' in src


def test_inline_checklist_reloads_job_on_signoff():
    """On successful signoff the parent reloads the job, which
    flips the H&S stat to "Cleared", collapses the banner (because
    `safetyNeeded` becomes false), and unlocks the on-site timer."""
    src = _read()
    assert "onSignedOff?.()" in src
    assert "setSafetyOpen(false);" in src


# ── 3 · Empty-template safe-path ─────────────────────────────────


def test_inline_checklist_handles_empty_template():
    """Edge case: the organisation hasn't configured a template
    yet. We show a polite "no checklist configured" message
    instead of an empty card."""
    src = _read()
    assert 'data-testid="summary-safety-checklist-empty"' in src
    assert "No checklist template is configured" in src


# ── 4 · Stale guidance copy updated ──────────────────────────────


def test_arrival_error_copy_points_to_summary_banner():
    """The fallback error message when the engineer tries to
    start the on-site timer without an H&S signoff must point
    them at the Summary banner, not the (now non-existent)
    Complete-tab checklist."""
    src = _read()
    assert "Tap the amber banner at the top of Summary" in src
    assert "Open the Complete tab and tick off the H&S items" not in src
