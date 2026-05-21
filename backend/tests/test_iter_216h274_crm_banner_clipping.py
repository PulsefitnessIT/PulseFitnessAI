"""Iter 216h274 — CRM Cross-Module Tips banner clipped under navbar (P1 bug).

User report (with screenshot): *"CRM — it looks like there is a
card? Quick wins maybe? stuck at the top of the page under the
top navbar — can't scroll up to remove it."*

### Root cause

`CRMApp.js` rendered `<CrossModuleTipsBanner mode="crm" />` inside
a wrapper with NO top padding to clear the 81px fixed navbar.
The `pt-24` was applied only to the **next** sibling (the
"GymAxis Pro" header block), which left the banner sitting at
`top: ~16px` — fully clipped behind the navbar (`top: 0; height: 81px`).

The dismiss × button + the "Explore CRM" CTA were both unreachable
because they sat behind the fixed navbar.

Compare with Memberships / Marketing / LiteDashboard: all three
put `pt-24` on the parent `<main>` so the banner is the first
thing inside the padded region. CRMApp had its `pt-24` on the
wrong child.

### Fix

`CRMApp.js`: pulled the banner into a new
`<div className="pt-24 px-4 sm:px-6 max-w-7xl mx-auto" data-testid="crm-cross-module-tips-wrap">`
wrapper, and dropped the now-redundant `pt-24` from the
GymAxis Pro header block immediately below.

Live verification: banner top is now 96px (cleared the 81px
navbar by 15px of breathing room) and the dismiss × is clickable.
"""
from __future__ import annotations

import pathlib


def _crm_app() -> str:
    return pathlib.Path("/app/frontend/src/pages/CRM/CRMApp.js").read_text()


def test_cross_module_banner_wrapper_has_pt24():
    """The wrapper around <CrossModuleTipsBanner> in CRMApp.js must
    carry `pt-24` so the banner clears the 81px fixed navbar."""
    src = _crm_app()
    # Find the wrapper block
    assert 'data-testid="crm-cross-module-tips-wrap"' in src, (
        "expected the dedicated banner wrapper testid added in h274"
    )
    block = src.split('data-testid="crm-cross-module-tips-wrap"')[0].rsplit('<div', 1)[1]
    assert "pt-24" in block, (
        "banner wrapper MUST include pt-24 — without it the banner "
        "sits behind the fixed 81px navbar and the user can't scroll "
        "up to dismiss it (h274 regression)."
    )


def test_crm_app_header_no_longer_duplicates_pt24():
    """The pt-24 used to live on the GymAxis Pro header block.
    Since the banner wrapper now provides that padding, the header
    block must NOT add a SECOND pt-24 or the spacing doubles."""
    src = _crm_app()
    block = src.split('data-testid="crm-app-header"')[0].rsplit('<div', 1)[1]
    assert "pt-24" not in block, (
        "crm-app-header should no longer carry pt-24 — the banner "
        "wrapper above it already cleared the navbar."
    )


def test_banner_wraps_actual_banner_component():
    """Make sure the new wrapper actually contains the banner, not
    some other component."""
    src = _crm_app()
    # Pull the slice from the wrapper testid down to its </div>
    wrap_block = src.split('data-testid="crm-cross-module-tips-wrap">')[1].split("</div>")[0]
    assert "<CrossModuleTipsBanner" in wrap_block
    assert 'mode="crm"' in wrap_block


def test_other_module_pages_keep_their_pt24():
    """Sanity: Memberships / Marketing / LiteDashboard already had
    `pt-24` on the parent main — those must NOT regress. Their
    banner is the first child inside a padded `<main>`."""
    for path in (
        "/app/frontend/src/pages/Memberships/MembershipsConsole.js",
        "/app/frontend/src/pages/MarketingSuite.js",
        "/app/frontend/src/pages/LiteDashboardPage.js",
    ):
        src = pathlib.Path(path).read_text()
        assert "CrossModuleTipsBanner" in src, f"{path}: banner import gone?"
        assert "pt-24" in src or "pt-32" in src, (
            f"{path}: lost the navbar clearance padding"
        )
