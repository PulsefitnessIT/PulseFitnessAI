"""Iter 220q — Master Admin Attribution dashboard.

The marketing executive needs a single-screen view of which campaigns
are converting Partner Engineer applications. This iter ships:

  * A new React component `AdminPartnerAttribution` that consumes
    `GET /api/partners/attribution-summary` and renders three top-line
    stats (landings · applications · overall conversion %) plus a
    sortable per-source table with a gradient mini-bar visual for the
    landings volume.
  * Mounted inside `AdminPartners.js` above the Applications list so
    it's the first thing a master admin sees on the Partners tab.

The endpoint itself was built + tested in iter 220o
(`test_iter_220o_instagram_attribution.py::test_attribution_summary_*`).
This file pins the UI contract — the component must exist, fetch the
correct endpoint, render the canonical brand gradient, expose
data-testids for E2E + screenshot snapshotting, and handle the
empty / loading / error states without crashing.
"""
from __future__ import annotations

import pathlib

COMPONENT = pathlib.Path("/app/frontend/src/pages/MasterAdmin/AdminPartnerAttribution.js")
PARENT = pathlib.Path("/app/frontend/src/pages/MasterAdmin/AdminPartners.js")


def test_attribution_component_exists():
    assert COMPONENT.exists(), (
        "AdminPartnerAttribution component must exist — it's the Master Admin "
        "consumer of /partners/attribution-summary."
    )


def test_attribution_component_fetches_attribution_summary_endpoint():
    src = COMPONENT.read_text()
    assert "/api/partners/attribution-summary" in src, (
        "Component must call the iter 220o backend endpoint"
    )
    # And uses an Authorization Bearer header (master-admin gated).
    assert "Authorization" in src
    assert "Bearer" in src


def test_attribution_component_handles_loading_empty_and_error_states():
    """A dashboard without graceful fallbacks crashes mid-marketing-call.
    Pin all three branches at the source level."""
    src = COMPONENT.read_text()
    # Loading spinner
    assert "Loader2" in src and "animate-spin" in src
    # Empty state copy explains the UTM-only counter behaviour
    assert "admin-attribution-empty" in src
    assert "UTM-tagged" in src, (
        "Empty state must explain that this counts UTM-tagged landings "
        "only — organic traffic lives elsewhere"
    )
    # Error state surfaces the API's `detail`
    assert "admin-attribution-error" in src
    # Refresh control so the admin can re-poll without a full page reload
    assert "admin-attribution-refresh" in src


def test_attribution_component_renders_brand_gradient_not_pulse_cyan():
    """GymAxis master-admin surface — must use canonical navy→purple
    gradient. Pin against accidental Pulse cyan use."""
    src = COMPONENT.read_text()
    assert "#2563EB" in src and "#9D4CDD" in src, (
        "Mini bars + 'Overall conversion' stat tile must use the canonical "
        "navy→purple gradient — see /app/BRAND_PALETTE.md"
    )
    assert "#19CDFF" not in src, (
        "Master Admin Partners is a GymAxis surface — Pulse cyan must not "
        "appear here. See /app/BRAND_PALETTE.md §2."
    )


def test_attribution_table_exposes_required_columns():
    """Every column the marketing team needs must be wired up. Pin the
    table head so a future visual tweak can't silently drop a column."""
    src = COMPONENT.read_text()
    for header in ("Source", "Medium", "Campaign", "Landings", "Applications", "Conversion"):
        assert f">{header}<" in src, f"Table must expose a `{header}` column"


def test_attribution_table_has_per_row_testid_for_e2e():
    """A row-keyed testid lets E2E + screenshot snapshots target a
    specific source (e.g. `admin-attribution-row-instagram`) without
    relying on row index."""
    src = COMPONENT.read_text()
    assert "admin-attribution-row-" in src, (
        "Each row must have a `admin-attribution-row-{source}` testid"
    )
    assert "admin-attribution-table" in src


def test_attribution_top_stats_are_present_and_keyed():
    """Three top-line stat tiles: landings, applications, conversion%.
    Pin each so the dashboard layout can't silently lose one."""
    src = COMPONENT.read_text()
    for tid in ("admin-attr-stat-landings",
                "admin-attr-stat-applications",
                "admin-attr-stat-conversion"):
        assert tid in src, f"Stat tile `{tid}` must be present"


def test_attribution_component_mounted_above_applications_list():
    """The marketing-attribution panel must be the FIRST section after
    the summary chips on the Partners tab — that's the placement
    pinned by the user story ('every marketing huddle starts with
    where are this week's applications coming from')."""
    parent_src = PARENT.read_text()
    assert "import AdminPartnerAttribution" in parent_src, (
        "AdminPartners must import AdminPartnerAttribution"
    )
    assert "<AdminPartnerAttribution" in parent_src, (
        "Component must be rendered"
    )
    # Placement check: appears AFTER the summary chips block but
    # BEFORE the Applications section.
    attribution_pos = parent_src.find("<AdminPartnerAttribution")
    apps_section_pos = parent_src.find("Applications${applications.length")
    assert attribution_pos > 0 and apps_section_pos > 0, (
        "Both anchors must be present in AdminPartners"
    )
    assert attribution_pos < apps_section_pos, (
        "Attribution panel must render above the Applications section "
        "(it's the first thing the marketing team needs to see)."
    )
