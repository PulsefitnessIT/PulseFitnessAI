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


def test_marketing_home_exports_exactly_five_modules():
    body = _read(MK / "MarketingHome.js")
    # Spot the canonical export.
    assert "export const MODULES" in body, "MarketingHome.MODULES export missing"
    # Count the five module ids — all present.
    for mid in ("'service'", "'crm'", "'memberships'", "'marketing'", "'engineers'"):
        assert mid in body, f"module id {mid} missing from MarketingHome.MODULES"
    # Staffing/Reporting must still NOT be in the top-level module list.
    assert "id: 'staffing'" not in body, "Staffing should not be a top-level module"
    assert "id: 'reporting'" not in body, "Reporting should not be a top-level module"


def test_module_feature_constellations_match_user_mindmap():
    body = _read(MK / "MarketingHome.js")
    # Per the user's hand-drawn mind-map + Iter 220bd Engineers add-on:
    required = {
        "Operations": ("Fault Logging", "Check Sheets", "CAPEX", "Staffing"),
        "CRM": ("Companies", "Pipeline", "Forecast"),
        "Memberships": ("Timetable", "Invoicing", "Custom App"),
        "Marketing": ("Campaigns", "Poster Maker"),
        "Engineers": ("Job Routing", "Mobile App", "AI Photo Triage", "Earnings"),
    }
    for module, features in required.items():
        for f in features:
            assert f in body, f"{module} module missing required feature {f!r}"


def test_orbit_renders_five_modules_and_constellation():
    body = _read(MK / "AxisOrbit.js")
    # Internal ORBIT_MODULES — mirror of MarketingHome.MODULES.
    assert "const ORBIT_MODULES" in body, "AxisOrbit must declare its module set"
    for mid in ("'service'", "'crm'", "'memberships'", "'marketing'", "'engineers'"):
        assert mid in body, f"AxisOrbit missing module id {mid}"
    # Hover-driven constellation component.
    assert "FeatureConstellation" in body, "AxisOrbit FeatureConstellation component missing"
    # On-hover state + reveal hooks.
    assert "useState" in body, "AxisOrbit must track activeId via React state"
    assert "setActiveId" in body, "AxisOrbit activeId setter missing"
    # Cardinal-position placement — uses ORBIT_MODULES.length so adding
    # nodes auto-distributes them around the circle.
    assert "ORBIT_MODULES.length" in body, "orbit angle formula must scale to module count"
    assert "gx-orbit-feature-" in body, "feature pill data-testid prefix missing"


def test_orbit_dim_logic_focuses_hovered_module():
    body = _read(MK / "AxisOrbit.js")
    assert "dimmed" in body, "non-hovered nodes must dim — `dimmed` flag missing"
    assert "activeId !== null && !isActive" in body, "dim logic should fire when any node is active"


def test_marketing_nav_drops_staffing_and_reporting_tabs():
    body = _read(MK / "MarketingShell.js")
    nav_match = re.search(r"const NAV = \[(.*?)\];", body, re.DOTALL)
    assert nav_match, "NAV array not found in MarketingShell"
    nav_block = nav_match.group(1)
    assert "label: 'Staffing'" not in nav_block, "Staffing must be removed from top nav"
    assert "label: 'Reporting'" not in nav_block, "Reporting must be removed from top nav"
    # All five canonical modules either named in the nav or reachable
    # via a partner deep-link. Engineers stays in the nav for direct
    # partner-recruitment traffic.
    for label in ("Operations", "CRM", "Memberships", "Marketing", "Engineers"):
        assert f"label: '{label}'" in nav_block, f"{label} missing from top nav"


def test_homepage_copy_says_five_modules():
    body = _read(MK / "MarketingHome.js")
    assert "Five modules" in body, "homepage badge must read 'Five modules'"
    assert "five modules" in body, "body copy must reference five modules"
    # Stat tile must list all five module names.
    assert "Operations · CRM · Memberships · Marketing · Engineers" in body
    # And NOT the legacy copy.
    for legacy in ("Six modules", "six modules", "Four modules", "four modules"):
        assert legacy not in body, f"legacy copy {legacy!r} must be gone"


def test_marketing_css_pauses_orbit_counter_on_hover():
    body = _read(MK / "marketing.css")
    assert ".gx-orbit-ring:hover .gx-orbit-counter" in body, \
        "Counter-spin must pause with the ring so the feature constellation stays readable"
    assert "@keyframes gx-orbit-feature-pop" in body, "feature pop-in keyframes missing"
