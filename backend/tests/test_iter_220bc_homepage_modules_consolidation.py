"""Iter 220bc — Homepage modules consolidation: 6 → 4 with hover-expanding
feature constellation (the user's mind-map sketch).

Locks down:
1. The 4 canonical modules exported from MarketingHome (single source
   of truth — drives both the orbit + the deep-dive grid).
2. AxisOrbit renders exactly 4 nodes + carries a hover-driven
   FeatureConstellation that fans out per-module sub-features.
3. Marketing nav and homepage copy reflect "four modules" (not six).
4. Each module's required sub-features are present (per the user's
   mind-map: Operations → Fault Logging / Check Sheets / CAPEX /
   Staffing; CRM → Companies / Pipeline / Forecast; Memberships →
   Timetable / Invoicing / Custom App; Marketing → Campaigns /
   Poster Maker).
"""
from __future__ import annotations

import pathlib
import re


FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
MK = FRONTEND / "pages" / "Marketing"


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def test_marketing_home_exports_exactly_four_modules():
    body = _read(MK / "MarketingHome.js")
    # Spot the canonical export.
    assert "export const MODULES" in body, "MarketingHome.MODULES export missing"
    # Count the four module ids — must all be present, and the dropped
    # six-module set (staffing/reporting as top-level) must NOT be.
    for mid in ("'service'", "'crm'", "'memberships'", "'marketing'"):
        assert mid in body, f"module id {mid} missing from MarketingHome.MODULES"
    # Staffing/Reporting must NOT be in the top-level module list any more.
    assert "id: 'staffing'" not in body, "Staffing should not be a top-level module"
    assert "id: 'reporting'" not in body, "Reporting should not be a top-level module"


def test_module_feature_constellations_match_user_mindmap():
    body = _read(MK / "MarketingHome.js")
    # Per the user's hand-drawn mind-map (Iter 220bc):
    required = {
        "Operations": ("Fault Logging", "Check Sheets", "CAPEX", "Staffing"),
        "CRM": ("Companies", "Pipeline", "Forecast"),
        "Memberships": ("Timetable", "Invoicing", "Custom App"),
        "Marketing": ("Campaigns", "Poster Maker"),
    }
    for module, features in required.items():
        for f in features:
            assert f in body, f"{module} module missing required feature {f!r}"


def test_orbit_renders_four_modules_and_constellation():
    body = _read(MK / "AxisOrbit.js")
    # Internal ORBIT_MODULES — mirror of MarketingHome.MODULES.
    assert "const ORBIT_MODULES" in body, "AxisOrbit must declare its 4-module set"
    for mid in ("'service'", "'crm'", "'memberships'", "'marketing'"):
        assert mid in body, f"AxisOrbit missing module id {mid}"
    # Hover-driven constellation component.
    assert "FeatureConstellation" in body, "AxisOrbit FeatureConstellation component missing"
    # On-hover state + reveal hooks.
    assert "useState" in body, "AxisOrbit must track activeId via React state"
    assert "setActiveId" in body, "AxisOrbit activeId setter missing"
    # Cardinal-position placement (4 nodes).
    assert "ORBIT_MODULES.length" in body, "orbit angle formula must scale to module count"
    # Per-feature data-testid for automated checks.
    assert "gx-orbit-feature-" in body, "feature pill data-testid prefix missing"


def test_orbit_dim_logic_focuses_hovered_module():
    """When a node is hovered, the other 3 must dim so the focus stays
    on the active branch (UX rule from user's "expand into features"
    sketch)."""
    body = _read(MK / "AxisOrbit.js")
    assert "dimmed" in body, "non-hovered nodes must dim — `dimmed` flag missing"
    assert "activeId !== null && !isActive" in body, "dim logic should fire when any node is active"


def test_marketing_nav_drops_staffing_and_reporting_tabs():
    body = _read(MK / "MarketingShell.js")
    # Block scope — must hit the NAV array specifically, not just any
    # mention of the words.
    nav_match = re.search(r"const NAV = \[(.*?)\];", body, re.DOTALL)
    assert nav_match, "NAV array not found in MarketingShell"
    nav_block = nav_match.group(1)
    assert "label: 'Staffing'" not in nav_block, "Staffing must be removed from top nav"
    assert "label: 'Reporting'" not in nav_block, "Reporting must be removed from top nav"
    # Confirm the four canonical modules are still in the nav.
    for label in ("Operations", "CRM", "Memberships", "Marketing"):
        assert f"label: '{label}'" in nav_block, f"{label} missing from top nav"


def test_homepage_copy_says_four_modules():
    body = _read(MK / "MarketingHome.js")
    assert "Four modules" in body, "homepage badge must read 'Four modules'"
    assert "four modules" in body or "Four modules" in body, "body copy must reference four modules"
    # Stat tile must list all four module names.
    assert "Operations · CRM · Memberships · Marketing" in body
    # And NOT the legacy six-module copy.
    assert "Six modules" not in body, "legacy 'Six modules' badge must be gone"
    assert "six modules" not in body, "legacy 'six modules' body copy must be gone"


def test_marketing_css_pauses_orbit_counter_on_hover():
    body = _read(MK / "marketing.css")
    assert ".gx-orbit-ring:hover .gx-orbit-counter" in body, \
        "Counter-spin must pause with the ring so the feature constellation stays readable"
    assert "@keyframes gx-orbit-feature-pop" in body, "feature pop-in keyframes missing"
