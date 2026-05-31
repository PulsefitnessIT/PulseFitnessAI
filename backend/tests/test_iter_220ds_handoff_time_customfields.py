"""Iter 220ds — Engineer job UX adjustments (Feb 2026 operator feedback).

Three pins driven by the post-Treadmill-belt-slip screenshot:

  1. **Handoff notes** move OFF Summary (composer) ONTO Complete.
     Summary now renders handoff notes in **read-only** mode and
     **only** when a PREVIOUS engineer left context (true
     second-visit case). First-visit jobs have a clean Summary.
  2. **Travel button removed from the Time tab** — having two
     entry points (Travel tab's "Start trip" + Time tab's
     "Travel") was confusing. Time is now strictly on-site + admin.
  3. **WorkReportCustomFields removed from Complete** — concept
     retained (state, payload, component file) but the per-machine
     rework is pending. Engineers don't see it on the close-out
     screen for now.

Also pins ``viewer_user_id`` on the engineer GET case payload so
the read-only handoff panel can filter the current engineer's own
notes out.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── 1 · Handoff notes split: Summary read-only, Complete composer ─


def test_handoff_panel_supports_mode_prop():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The component now accepts a `mode` prop and a
    # `currentUserId` for read-only filtering on Summary.
    assert "mode = 'compose'" in src
    assert "currentUserId" in src
    assert "readOnly = mode === 'read-only'" in src


def test_summary_renders_handoff_in_read_only_mode():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The Summary-side <HandoffNotesPanel ... /> must explicitly
    # opt into read-only + pass the viewer's id.
    assert 'mode="read-only"' in src
    assert "currentUserId={job.viewer_user_id}" in src


def test_complete_renders_handoff_composer():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="complete-handoff-card"' in src
    assert 'mode="compose"' in src


def test_summary_handoff_panel_hidden_when_no_previous_notes():
    """Source-level guard: the read-only branch must early-return
    `null` when there are no visible notes."""
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert "if (visibleNotes.length === 0) return null" in src


def test_engineer_get_case_pins_viewer_user_id():
    src = (Path("/app/backend/routes/svc/engineer.py")).read_text(encoding="utf-8")
    assert '"viewer_user_id": user.get("id")' in src


# ── 2 · Travel button removed from Time tab ───────────────────────


def test_time_tab_no_travel_button():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="time-start-travel"' not in src
    # The Time-tab timer grid drops from grid-cols-3 (on_site /
    # travel / admin) to grid-cols-2.
    assert (
        'data-testid="time-start-card"' in src
        and 'grid grid-cols-2 gap-2' in src
    )
    # On-site + admin buttons remain reachable.
    assert 'data-testid="time-start-on_site"' in src
    assert 'data-testid="time-start-admin"' in src


def test_travel_tab_still_renders():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The Travel tab is still mounted as the canonical entry point.
    assert "{ id: 'travel'" in src
    assert "activeTab === 'travel'" in src


# ── 3 · WorkReportCustomFields off Complete (concept retained) ────


def test_complete_does_not_render_custom_fields_component():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The component is no longer instantiated on Complete.
    assert "<WorkReportCustomFields" not in src
    # ... and the import is commented out, NOT deleted.
    assert (
        "// import WorkReportCustomFields from './WorkReportCustomFields'"
        in src
    )
    # State + payload plumbing is retained so the future re-add is
    # a one-line change.
    assert "custom_fields: customFields" in src


def test_custom_fields_component_file_retained():
    """The component file MUST still exist so future iters can
    re-render it (likely per-machine on the Equipment tab)."""
    p = FRONTEND / "pages/ServiceOps/Engineer/WorkReportCustomFields.js"
    assert p.exists(), "WorkReportCustomFields.js must NOT be deleted"
