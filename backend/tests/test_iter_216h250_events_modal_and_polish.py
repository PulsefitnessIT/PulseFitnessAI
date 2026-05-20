"""Iter 216h250 — Events modal redesign + Setup wizard contrast +
Parent-portal Preview + Module discovery + slug exposure.

User feedback (Feb 20, 2026):
- "I couldn't create an event if I used an event name that wasn't shown
  it cancelled the event - said invalid type - audit the whole process"
- "Memberships wizard - completely in dark mode?" (low contrast)
- "Parent portal - Preview button - so the owner/manager can see how
  the parent portal is being viewed by customers"
- "If the user signs up for 1 module then there should be the option
  to unlock the other modules after sign up."

Fixes:
1. EventsTab: window.prompt() chain replaced with Pulse-themed
   ModalShell forms. Kind is now a <select> (no more silent "Invalid
   type" cancel).
2. SetupWizard: explicit white text on headings/inputs + visible
   input fills/borders.
3. ParentPortalTab: Preview banner with an "Open /m/<slug>" CTA.
4. /account/organisation now surfaces `slug`.
5. MembershipsStartTab: ModuleDiscoveryCard with /pricing CTA.
"""
from __future__ import annotations

import pathlib


# ─── EventsTab: prompts gone, modals in ─────────────────────────────

def test_events_tab_replaces_prompts_with_modals():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/EventsTab.js").read_text()
    # No more *executed* window.prompt() — only allowed in comments.
    # Strip comments, then search.
    import re
    no_comments = re.sub(r"//.*$|/\*.*?\*/", "", src, flags=re.DOTALL | re.MULTILINE)
    assert "window.prompt(" not in no_comments, "EventsTab must use modals, not window.prompt"
    # New components exist.
    for name in ("CreateEventModal", "RehearsalModal", "CostumeModal"):
        assert f"function {name}" in src, f"missing {name} component"
    # ModalShell + Input + Select imported from _shared.
    assert "from '@/pages/Memberships/_shared'" in src
    # Kind picker is a dropdown bound to KIND_META.
    assert "kindOptions = Object.entries(KIND_META)" in src


def test_events_tab_modal_testids_present():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/EventsTab.js").read_text()
    # Shared Input uses `testid`, ModalActions uses `testId`. Either prop
    # plus literal `data-testid` are all valid.
    def has(tid):
        return any(p in src for p in (
            f'testid="{tid}"', f'testId="{tid}"', f'data-testid="{tid}"',
        ))
    for tid in (
        "events-create-name", "events-create-kind",
        "events-create-date", "events-create-submit",
    ):
        assert has(tid), f"missing test id {tid}"
    # The empty-state CTA uses an explicit data-testid.
    assert 'data-testid="events-empty-create"' in src
    # Modal-level testIds wired via ModalShell `testId` prop.
    for testid in ("events-create-modal", "events-rehearsal-modal", "events-costume-modal"):
        assert f'testId="{testid}"' in src, f"missing modal testId={testid}"


# ─── SetupWizard contrast ────────────────────────────────────────────

def test_setup_wizard_inputs_have_visible_fill():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    # The Input component must not use the old invisible fill combo.
    # We check the specific old className that was replaced.
    assert "bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30" not in src, (
        "Input component must have visible fill, not the old bg-black/40 combo"
    )
    # Explicit inline style fills replaced them.
    assert "background: 'rgba(255,255,255,0.06)'" in src
    assert "border: '1px solid rgba(255,255,255,0.18)'" in src


def test_setup_wizard_heading_is_explicitly_white():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    # StepShell forces explicit colour so a light theme can't override it.
    assert "color: '#ffffff'" in src, "wizard heading must force explicit white"


# ─── Parent portal Preview button ───────────────────────────────────

def test_parent_portal_has_preview_button():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/ParentPortalTab.js").read_text()
    assert 'data-testid="parent-portal-preview-btn"' in src
    assert "window.open(`/m/${slug}`" in src
    assert "/account/organisation" in src, "must fetch the org to get slug"


def test_account_organisation_exposes_slug():
    src = pathlib.Path("/app/backend/routes/account.py").read_text()
    # _serialise_org returns the slug so the FE can build /m/<slug>.
    assert 'payload["slug"] = org.get("slug", "")' in src


# ─── Module discovery ───────────────────────────────────────────────

def test_memberships_start_has_module_discovery_card():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsStartTab.js").read_text()
    assert "function ModuleDiscoveryCard()" in src
    assert 'data-testid="mbr-module-discovery"' in src
    assert 'data-testid="mbr-module-discovery-cta"' in src
    # CTA routes to /pricing.
    assert 'href="/pricing?from=memberships"' in src
