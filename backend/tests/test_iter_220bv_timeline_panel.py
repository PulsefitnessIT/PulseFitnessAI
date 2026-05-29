"""Iter 220bv — frontend `<TimelinePanel/>` wiring.

Locks in:

  1. The shared component exists at `components/CRM/TimelinePanel.js`
     and exports a default React component.
  2. The component calls `/api/crm/v2/timeline` with the right
     scope key and supports load-more pagination.
  3. All three drawers (Company / Opportunity / Tender) import and
     render the component with their respective scope.
  4. The component groups by day and renders status pills, deep
     links, and load-more.
  5. The component has the required `data-testid` attributes for
     e2e testing.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
COMPONENT = FRONTEND_SRC / "components" / "CRM" / "TimelinePanel.js"


# ══════════════════ 1 · Component exists with correct shape ═════════


def test_timeline_panel_component_exists():
    assert COMPONENT.exists(), f"missing: {COMPONENT}"
    text = COMPONENT.read_text()
    assert "export default function TimelinePanel" in text
    # Props it consumes.
    for prop in ("scope", "API", "headers", "isDark", "c"):
        assert prop in text


def test_timeline_panel_calls_correct_endpoint():
    text = COMPONENT.read_text()
    # Single-/api/ prefix (Iter 220bo regression guard).
    assert "/api/crm/v2/timeline" in text
    assert "/api/api/" not in text
    # Scope key built dynamically from scope.type.
    assert "${scope.type}_id" in text
    # Pagination plumbing.
    assert "limit" in text and "skip" in text


# ══════════════════ 2 · Day-grouping + status pills + deep-link ═════


def test_timeline_panel_groups_by_day_and_renders_pills():
    text = COMPONENT.read_text()
    # Day-grouping reducer.
    assert "_dayKey" in text and "_dayLabel" in text
    # Status pill rendering branch.
    assert "STATUS_TONE" in text
    # Deep-link click handler.
    assert "onDeepLink" in text or "deep_link" in text


def test_timeline_panel_has_required_testids():
    text = COMPONENT.read_text()
    for tid in (
        'data-testid="timeline-panel"',
        'data-testid="timeline-loading"',
        'data-testid="timeline-empty"',
        'data-testid="timeline-error"',
        'data-testid="timeline-load-more"',
    ):
        assert tid in text, f"missing testid: {tid}"


# ══════════════════ 3 · Drawers wire it with the right scope ════════


def test_opportunity_drawer_wires_timeline_panel():
    src = (FRONTEND_SRC / "pages" / "CRM" / "CRMPipeline.js").read_text()
    assert "import TimelinePanel from '@/components/CRM/TimelinePanel'" in src
    # When the opportunity drawer's `tab === 'timeline'` branch fires
    # it should render <TimelinePanel scope={{ type: 'opportunity' ... }} />.
    idx = src.find("tab === 'timeline'")
    assert idx > 0
    block = src[idx:idx + 600]
    assert "<TimelinePanel" in block
    assert "type: 'opportunity'" in block
    # The old hard-coded activity-only timeline (mapped over
    # `opp.activities`) must be gone.
    assert "opp.activities" not in src or "(opp.activities" not in block


def test_tender_drawer_wires_timeline_panel():
    src = (FRONTEND_SRC / "pages" / "CRM" / "CRMTenders.js").read_text()
    assert "import TimelinePanel from '@/components/CRM/TimelinePanel'" in src
    # Timeline tab is registered.
    assert "id: 'timeline'" in src
    # Render branch passes type='tender'.
    idx = src.find("activeTab === 'timeline'")
    assert idx > 0
    block = src[idx:idx + 600]
    assert "<TimelinePanel" in block
    assert "type: 'tender'" in block


def test_company_drawer_wires_timeline_panel():
    src = (FRONTEND_SRC / "pages" / "CRM" / "CRMCompanies.js").read_text()
    assert "import TimelinePanel from '@/components/CRM/TimelinePanel'" in src
    # A new section labelled 'Timeline' is registered.
    assert "id: 'timeline'" in src
    idx = src.find("activeSection === 'timeline'")
    assert idx > 0
    block = src[idx:idx + 600]
    assert "<TimelinePanel" in block
    assert "type: 'company'" in block


# ══════════════════ 4 · Defensive — no double wiring / dupes ════════


def test_only_one_timeline_panel_component_in_tree():
    """A future refactor must not silently fork the component."""
    matches: list[Path] = []
    for p in FRONTEND_SRC.rglob("*.js"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "export default function TimelinePanel" in text:
            matches.append(p)
    assert len(matches) == 1, (
        f"Expected exactly one TimelinePanel component, found: "
        f"{[str(m) for m in matches]}"
    )


def test_timeline_panel_has_load_more_pagination():
    text = COMPONENT.read_text()
    # Visual cue.
    assert "Load more" in text
    # Pagination state.
    assert "loadingMore" in text
    # The "remaining" count is shown so the user knows what's left.
    assert "remaining" in text.lower()


def test_timeline_panel_no_useauth_or_double_api():
    """Iter 220bo regression — keep the new component free of the
    legacy patterns we banned."""
    text = COMPONENT.read_text()
    assert "useAuth" not in text
    assert "/api/api/" not in text
