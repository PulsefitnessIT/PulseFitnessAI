"""Iter 216h247 — Memberships polish round.

Three fixes:

1. **Class template editor portaled** — `StudioBuilderTab`'s inline
   ``<fixed inset-0>`` modal was clipped by a transformed ancestor in
   Pulse Pro (same root cause as h242 Add Staff). Now portaled to
   ``document.body``.
2. **Instructor dropdown** — replaced the free-text input with a
   ``<select>`` that lists org instructors and offers a final
   "+ Add new instructor…" option. Picking it routes the user to
   the Instructors tab via the new ``onAddInstructor`` callback.
3. **Tab reorder** — Memberships top-level pills regrouped into:
   onboarding → daily ops → people → commercial → marketing →
   intelligence → tools.
"""
from __future__ import annotations

import pathlib


def test_class_template_editor_is_portaled():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/StudioBuilderTab.js").read_text()
    # createPortal is imported from react-dom.
    assert "import { createPortal } from 'react-dom'" in src
    # The editor's return wraps in createPortal(..., document.body).
    assert "return createPortal((" in src, "ClassTemplateEditor must use createPortal"
    assert "), document.body);" in src, "ClassTemplateEditor must portal to document.body"


def test_class_template_editor_has_instructor_dropdown():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/StudioBuilderTab.js").read_text()
    assert 'data-testid="cte-instructor-select"' in src, "instructor must be a select"
    assert "+ Add new instructor" in src, "must offer add-new option"
    assert "onAddInstructor" in src, "must wire the add-instructor callback"
    assert "/memberships/instructors" in src, "must load directory"


def test_studio_builder_passes_add_instructor_callback():
    """The parent StudioBuilderTab must close itself and bubble the
    add-instructor request to the SchedulingHub tab."""
    src = pathlib.Path("/app/frontend/src/pages/Memberships/StudioBuilderTab.js").read_text()
    # Default export accepts onAddInstructor prop.
    assert "export default function StudioBuilderTab({ API, headers, onAddInstructor })" in src
    # And passes a wrapped version to the editor.
    assert "onAddInstructor={() => { setShowNewClass(false); onAddInstructor?.(); }}" in src


def test_memberships_console_routes_add_instructor_to_instructors_tab():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsConsole.js").read_text()
    # SchedulingHubTab must declare onSetTab and pass it through.
    assert "function SchedulingHubTab({ API, headers, activeTabHint, onSetTab })" in src
    assert "onAddInstructor={() => onSetTab?.('instructors')}" in src


def test_memberships_tab_order_rationalised():
    """The TABS array must place daily-ops + people groups before the
    commercial / analytics blocks."""
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsConsole.js").read_text()
    # Anchor: 'schedule' (daily ops) must appear before 'analytics'
    # (commercial block). Iter 230 — the old 'studio-brain' tab was
    # retired, so 'analytics' is the new commercial-block anchor.
    schedule_idx = src.index("id: 'schedule'")
    analytics_idx = src.index("id: 'analytics'")
    assert schedule_idx < analytics_idx, "schedule must come before analytics"
    # 'instructors' must sit alongside 'members' (people group), not after invoicing.
    instructors_idx = src.index("id: 'instructors'")
    invoicing_idx = src.index("id: 'invoicing'")
    assert instructors_idx < invoicing_idx, "instructors must precede invoicing in the new order"
    # 'checkin' must precede 'members' (daily ops before people).
    checkin_idx = src.index("id: 'checkin'")
    members_idx = src.index("id: 'members'")
    assert checkin_idx < members_idx, "checkin (daily ops) must come before members"
