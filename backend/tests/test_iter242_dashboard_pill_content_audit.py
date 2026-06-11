"""Iter 242 — Cross-dashboard pill-vs-content audit (recurrence guard).

After the iter-241 production bug (Pulse ops: Reports / Suppliers /
Gym Layout pills with NO content for pulse_master_admin), this audit
codifies the invariant across EVERY tabbed dashboard in the platform:

    If a tab pill is offered, clicking it must mount content.

Audited surfaces and their mechanisms:
- GymAxis ops      — pills in Dashboard/DashboardTabs.js, content in
                     DashboardPage.js <TabsContent> ('digest' is an
                     allowed deep-link-only hidden tab).
- MOD Pro portal   — pillar buttons + `activePillar === 'x'` renders.
- Memberships      — TABS list + `tab === 'x'` / `[..].includes(tab)`.
- CRM              — NAV_ITEMS + renderContent switch (default: present).
- Marketing suite  — nav ids + switch cases (default: present).
- Pulse ops        — covered by test_iter241 (tabVisible invariant).
"""

import re

SRC = "/app/frontend/src"


def _read(path: str) -> str:
    return open(f"{SRC}/{path}", encoding="utf-8").read()


def test_gymaxis_ops_every_pill_has_content():
    pills = set(re.findall(r"\{ id: '([a-z-]+)',\s*label", _read("pages/Dashboard/DashboardTabs.js")))
    content = set(re.findall(r'<TabsContent value="([a-z-]+)"', _read("pages/DashboardPage.js")))
    missing = pills - content
    assert not missing, f"GymAxis ops pills with NO content (blank page): {sorted(missing)}"
    # Hidden deep-link-only tabs are allowed, but keep the list explicit
    # so new orphans are a conscious decision.
    orphans = content - pills
    assert orphans <= {"digest"}, f"unexpected orphan TabsContent in GymAxis ops: {sorted(orphans)}"


def test_mod_portal_every_pillar_renders():
    src = _read("pages/MODPortal/MODProDashboard.js")
    pillars = set(re.findall(r"\{ id: '([a-z-]+)',\s*label:", src))
    assert pillars, "MOD pillar list not found — extraction broke, update this test"
    for p in pillars:
        assert f"activePillar === '{p}'" in src, f"MOD pillar '{p}' has no content render"


def test_memberships_every_tab_renders():
    src = _read("pages/Memberships/MembershipsConsole.js")
    pills = set(re.findall(r"\{ id: '([a-z_-]+)',\s*label", src))
    eq_renders = set(re.findall(r"(?:\btab\w*|\bview|\bactiveTab) === '([a-z_-]+)'", src))
    # tabs rendered through grouped hubs: ['a','b'].includes(tab)
    group_renders = {
        tid for arr in re.findall(r"\[((?:'[a-z_-]+',?\s*)+)\]\.includes\(tab\)", src)
        for tid in re.findall(r"'([a-z_-]+)'", arr)
    }
    missing = pills - eq_renders - group_renders
    assert not missing, f"Memberships pills with NO content: {sorted(missing)}"


def _nav_block_ids(src: str, anchor: str) -> set[str]:
    start = src.index(anchor)
    end = src.index("];", start)
    return set(re.findall(r"\{ id: '([a-z_-]+)'", src[start:end]))


def test_crm_every_nav_item_has_a_switch_case():
    src = _read("pages/CRM/CRMApp.js")
    nav_ids = _nav_block_ids(src, "const NAV_ITEMS = [")
    assert nav_ids, "CRM NAV_ITEMS not found — extraction broke, update this test"
    cases = set(re.findall(r"case '([a-z_-]+)':", src))
    missing = nav_ids - cases
    assert not missing, f"CRM nav items with NO renderContent case: {sorted(missing)}"
    assert "default:" in src, "CRM renderContent must keep a default fallback"


def test_marketing_suite_every_tab_has_a_switch_case():
    src = _read("pages/MarketingSuite.js")
    ids = set(re.findall(r"\{ id: '([a-z_-]+)'", src))
    cases = set(re.findall(r"case '([a-z_-]+)':", src))
    missing = ids - cases
    assert not missing, f"Marketing suite tabs with NO case: {sorted(missing)}"
    assert "default:" in src, "Marketing suite renderer must keep a default fallback"
