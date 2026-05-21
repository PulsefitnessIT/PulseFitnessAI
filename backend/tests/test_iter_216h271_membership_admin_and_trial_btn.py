"""Iter 216h271 — Master Admin Memberships loading bug + Free Trial
button visibility on the mobile marketing menu.

Two user-reported bugs (verbatim):
  1. *"Master Admin → Memberships is not loading — I also can't see
      memberships through the GymAxis/Pulse Fitness portal buttons
      on preview"*
  2. *"Free trial button — no text"* (mobile marketing menu)

### Root causes

**(1) Memberships master admin page stuck loading.**
Two of the ten endpoints the page fans out to (`/revenue`,
`/instructors`) were 500ing on a `KeyError: 'name'` —
`{o["id"]: o["name"]}` dict-comprehensions over the
`organizations` collection crashed on any org doc that didn't
have `name` set (e.g. partial fixtures / orphan records).
Because the frontend used `Promise.all`, one 500 rejected the
whole batch → loading state never cleared properly across all
tabs.

**(2) Mobile Free Trial button invisible.**
The Shadcn `<Button>` default (`bg-primary text-primary-foreground`)
sits on a white menu surface. With no explicit gradient + colour,
the primary tokens evaluated to a low-contrast/transparent combo
and the button appeared empty.

### Fixes

* `routes/master_admin_memberships.py` — every `o["name"]` /
  `o["id"]` access is now `o.get(...) or "—"` with a sentinel-id
  skip so a single bad org doc can't take down the endpoint.
* `useMembershipsAdmin.js` — switched `Promise.all` → `Promise.allSettled`
  so partial endpoint failures degrade gracefully (each tab loads
  what it can; a toast lists which sections failed).
* `Navbar.js` — mobile trial button now uses an explicit inline
  gradient + white text instead of relying on the Shadcn primary
  theme tokens. Same brand gradient as the hero CTA.
"""
from __future__ import annotations

import asyncio
import pathlib


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── 1. revenue_oversight no longer crashes on missing org names ─


def test_revenue_oversight_handles_org_without_name():
    """Single org doc missing `name` used to raise KeyError → 500.
    Pinning the fix via a static check on the source is more robust
    than mocking the full aggregation graph (which would require a
    fixture per pipeline stage). The live curl in the iter notes
    covers the actual endpoint behaviour."""
    src = pathlib.Path(
        "/app/backend/routes/master_admin_memberships.py"
    ).read_text()
    # The fix must guard the dict comp + skip orgs with no id
    rev_block = src.split("revenue_oversight")[1].split("@router")[0]
    assert 'o.get("name")' in rev_block, "revenue_oversight must use .get('name')"
    assert 'if o.get("id")' in rev_block, "revenue_oversight must skip orgs with no id"


# ─── 2. instructor_oversight likewise no longer crashes ────────


def test_instructor_oversight_handles_org_without_name():
    """Same hardening as revenue_oversight — the instructors endpoint
    builds the same `org_names` dict and was crashing on the same
    KeyError shape."""
    src = pathlib.Path(
        "/app/backend/routes/master_admin_memberships.py"
    ).read_text()
    # No more bare dict-access — must use .get() with a default
    assert 'o["name"] for o' not in src, (
        "Found `o[\"name\"] for o in ...` — must use o.get('name') or '—'"
    )


def test_no_more_brittle_org_name_dict_access():
    """Sweep — every org dict-access in this file must be guarded.
    Catches both the line 175 alert path and any future regressions."""
    src = pathlib.Path(
        "/app/backend/routes/master_admin_memberships.py"
    ).read_text()
    # Only legitimate strict access is on aggregations like `_id`
    bad_lines = [
        ln for ln in src.splitlines()
        if 'o["name"]' in ln
    ]
    assert not bad_lines, f"Brittle `o[\"name\"]` access still present: {bad_lines}"


# ─── 3. Frontend hook uses allSettled ─────────────────────────────


def test_memberships_admin_hook_uses_promise_allsettled():
    """Single endpoint failure must NOT nuke the whole page."""
    src = pathlib.Path(
        "/app/frontend/src/pages/MasterAdmin/AdminMemberships/useMembershipsAdmin.js"
    ).read_text()
    assert "Promise.allSettled" in src
    assert "Promise.all(" not in src.replace("Promise.allSettled", ""), (
        "Should have replaced Promise.all with Promise.allSettled — the old "
        "code rejects the whole batch on a single endpoint 500."
    )


def test_memberships_admin_hook_reports_failed_sections():
    """When one or more sections fail, the toast should tell the
    operator which ones — not just a generic 'failed to load'."""
    src = pathlib.Path(
        "/app/frontend/src/pages/MasterAdmin/AdminMemberships/useMembershipsAdmin.js"
    ).read_text()
    assert "failed.join(" in src
    # The toast wording must mention "section" so operators understand
    # this is a partial failure, not a full outage
    assert "section" in src.lower()


# ─── 4. Mobile Free Trial button now has visible text ─────────────


def test_mobile_trial_button_has_explicit_gradient_and_white_text():
    """The Shadcn primary defaults rendered invisible on the white
    mobile-menu surface. Force the brand gradient + white text via
    inline style so the button is visible regardless of theme tokens."""
    # Two surfaces carry a mobile Start-Free-Trial CTA — the shared
    # app Navbar AND the marketing-site MarketingShell. The user's
    # screenshot is the marketing one (gx-nav-mobile-trial) but we
    # pin both so a future refactor can't regress either.
    for path, testid in [
        ("/app/frontend/src/components/shared/Navbar.js", "mobile-trial-btn"),
        ("/app/frontend/src/pages/Marketing/MarketingShell.js", "gx-nav-mobile-trial"),
    ]:
        src = pathlib.Path(path).read_text()
        block = src.split(f'data-testid="{testid}"')[0].rsplit('<', 1)[1]
        assert "linear-gradient" in block, f"{testid}: missing explicit gradient"
        assert "gx-brand-from" in block, f"{testid}: should reference canonical brand tokens"
        assert "#fff" in block or "'white'" in block, f"{testid}: text must be explicitly white"


def test_mobile_trial_button_still_opens_signup_modal():
    """Sanity — the click handler shouldn't have changed."""
    src = pathlib.Path(
        "/app/frontend/src/components/shared/Navbar.js"
    ).read_text()
    block = src.split('data-testid="mobile-trial-btn"')[0].rsplit('<Button', 1)[1]
    assert "setIsLogin(false)" in block
    assert "setShowAuth(true)" in block
    assert "setMobileMenuOpen(false)" in block
