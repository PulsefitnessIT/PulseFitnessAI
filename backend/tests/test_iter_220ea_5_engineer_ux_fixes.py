"""Iter 220ea·5 — Engineer App UX fixes.

Source-level guards covering:

* H&S Pre-job checklist banner now lives on the Summary tab and
  jumps to the Complete tab on click.
* Equipment-new round-trip lands back on the Equipment tab
  instead of bouncing to Summary.
* The bottom-right is consolidated into ONE SpeedDial; the three
  separate FABs (voice / ask / feedback) now hide on engineer
  routes and listen for `gx:open-*` events.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
EQUIPMENT  = FRONTEND / "pages/ServiceOps/Engineer/EngineerEquipment.js"
SPEED_DIAL = FRONTEND / "pages/ServiceOps/Engineer/EngineerSpeedDial.js"
VOICE_FAB  = FRONTEND / "pages/ServiceOps/Engineer/VoiceToJobButton.js"
ASK_FAB    = FRONTEND / "components/AskGymAxis.js"
FEEDBACK   = FRONTEND / "components/shared/FeedbackWidget.js"
APP_ROUTES = FRONTEND / "routes/AppRoutes.js"


# ── 1 · H&S checklist banner on Summary tab ──────────────────────


def test_summary_renders_safety_checklist_banner_when_needed():
    src = JOB_DETAIL.read_text()
    # Banner only shows when the engineer hasn't signed off AND a
    # template exists — otherwise we'd nag on every job.
    assert "const safetyNeeded" in src
    assert "!job.safety_signoff" in src
    assert "safety_template" in src
    # Test-id is stable for the e2e suite to assert against.
    assert 'data-testid="summary-safety-checklist-banner"' in src
    assert "Pre-job H&amp;S checklist" in src


def test_safety_banner_is_clickable_to_open_inline_checklist():
    """Iter 220ea·9 — The banner is a real button that toggles an
    INLINE checklist on Summary (no longer jumps to Complete tab,
    which never had the checklist UI ported from V1)."""
    src = JOB_DETAIL.read_text()
    # The banner is now an aria-expanded button that toggles
    # `safetyOpen` and renders SafetyChecklistInline below it.
    assert "setSafetyOpen(v => !v)" in src
    assert "aria-expanded={safetyOpen}" in src
    assert "<SafetyChecklistInline" in src
    # The old jump-to-complete wiring is gone.
    assert "onJumpToSafety" not in src


def test_safety_banner_appears_above_customer_block_in_summary():
    """Visual hierarchy: the safety call-out must come BEFORE the
    customer/site block so the engineer can't miss it. We assert on
    document order in the source."""
    src = JOB_DETAIL.read_text()
    banner_idx = src.index('data-testid="summary-safety-checklist-banner"')
    cust_idx   = src.index('data-testid="jaag-customer-name"')
    assert banner_idx < cust_idx, (
        "Safety banner must render before the customer block in JobAtAGlance"
    )


# ── 2 · Equipment-new round-trip stays on Equipment tab ──────────


def test_equipment_new_redirects_back_to_equipment_tab():
    src = EQUIPMENT.read_text()
    # When attached to a case, the post-save navigate must include
    # the explicit equipment tab query so the job-detail screen
    # re-mounts on the right tab instead of defaulting to Summary.
    assert "?tab=equipment" in src
    # The bare back-to-summary navigate must NOT be present.
    assert "navigate(`/svc/engineer/jobs/${caseId}`)" not in src


def test_job_detail_reads_tab_from_url_query():
    """The detail screen must honour `?tab=` on mount so the
    equipment round-trip lands cleanly. Also guards against typos
    (only known tabs are accepted)."""
    src = JOB_DETAIL.read_text()
    assert "searchParams.get('tab')" in src
    assert "validTabs.has(initialTab)" in src
    # Fall back to summary if the query is missing or unknown.
    assert "'summary'" in src


# ── 3 · Consolidated SpeedDial replaces the 3 separate FABs ──────


def test_speed_dial_component_exists_with_three_actions():
    assert SPEED_DIAL.is_file()
    src = SPEED_DIAL.read_text()
    for action_id, evt, testid in (
        ('voice',    'gx:open-voice',    'engineer-speed-dial-voice'),
        ('ask',      'gx:open-ask',      'engineer-speed-dial-ask'),
        ('feedback', 'gx:open-feedback', 'engineer-speed-dial-feedback'),
    ):
        assert f"'{action_id}'" in src
        assert f"'{evt}'" in src
        assert f"'{testid}'" in src
    # And it ships the launcher testid the smoke suite asserts on.
    assert 'data-testid="engineer-speed-dial-launcher"' in src
    # Sub-action buttons render `data-testid={testid}` driven by
    # the ACTIONS array (above).
    assert 'data-testid={testid}' in src


def test_speed_dial_is_mounted_on_engineer_routes_only():
    src = APP_ROUTES.read_text()
    assert "EngineerSpeedDial" in src
    # The mount must be inside the existing engineer-route guard.
    guard_idx = src.index("user && isEngineerRoute")
    mount_idx = src.index("<EngineerSpeedDial />")
    end_idx   = src.index("</Suspense>", mount_idx)
    assert guard_idx < mount_idx < end_idx


def test_voice_fab_listens_for_open_event_and_hides_on_engineer_route():
    src = VOICE_FAB.read_text()
    assert "window.addEventListener('gx:open-voice'" in src
    # Launcher render is gated on !isEngineerRoute.
    assert "isEngineerRoute" in src
    assert "{!isEngineerRoute &&" in src


def test_ask_orb_listens_for_open_event_and_hides_on_engineer_route():
    src = ASK_FAB.read_text()
    assert "window.addEventListener('gx:open-ask'" in src
    assert "isEngineerRoute" in src
    assert "{!isEngineerRoute &&" in src


def test_feedback_widget_listens_for_open_event_and_hides_on_engineer_route():
    src = FEEDBACK.read_text()
    assert "window.addEventListener('gx:open-feedback'" in src
    assert "isEngineerRoute" in src
    # Launcher render gated; the panel still renders so the
    # event-driven open path actually shows the form.
    assert "!open && !isEngineerRoute" in src


# ── 4 · SpeedDial UX niceties ────────────────────────────────────


def test_speed_dial_closes_on_outside_tap_and_escape():
    """A half-open dial that swallows the next tap is worse than no
    dial. The component must self-dismiss on outside-tap and
    Escape."""
    src = SPEED_DIAL.read_text()
    assert "addEventListener('mousedown'" in src
    assert "addEventListener('touchstart'" in src
    assert "e.key === 'Escape'" in src
