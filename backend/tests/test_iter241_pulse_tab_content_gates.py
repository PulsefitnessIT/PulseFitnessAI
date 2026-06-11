"""Iter 241 — Production bug: Reports / Suppliers / Gym Layout tabs blank
for Pulse Master Admins on /pulse.

Root cause: the tab PILLS (buildTabs) and the tab CONTENT (TabsContent
gates) used different hand-written role lists. The content gates said
`owner || manager` and forgot `pulse_master_admin` — the same omission
as the iter-237 site-switcher bug — so the pill rendered but clicking
it mounted nothing.

Fix + recurrence guard: a single `isManagerial` flag for role gates, and
the INVARIANT that content visibility derives from the same TABS list as
the pills via `tabVisible(id)` — they can never diverge again.
"""

import re

PAGE = "/app/frontend/src/pages/LiteDashboardPage.js"


def _src() -> str:
    return open(PAGE, encoding="utf-8").read()


def test_content_gates_derive_from_pill_list():
    src = _src()
    for tab in ("reports", "gym-layout", "suppliers"):
        assert f"tabVisible('{tab}')" in src, (
            f"{tab} content must be gated by tabVisible() — the same source as the pills"
        )
    assert "const tabVisible = (id) => TABS.some" in src


def test_no_handwritten_role_gates_on_tab_content():
    """No TabsContent may be gated by a raw owner/manager role list again."""
    src = _src()
    for m in re.finditer(r"userRole === '(?:owner|manager)'[^\n]*&&\s*\(\s*\n\s*<TabsContent", src):
        raise AssertionError(f"hand-written role gate on TabsContent: {m.group(0)[:80]}")


def test_is_managerial_includes_pulse_admins():
    src = _src()
    # Iter 243 — isManagerial is now derived from the central capability
    # helper; pulse-admin inclusion is asserted against capabilities.js.
    assert "const isManagerial = can(user, 'manage_operations', { role: userRole })" in src
    caps = open("/app/frontend/src/utils/capabilities.js", encoding="utf-8").read()
    assert "user?.is_master_admin || isPulseAdmin(user)" in caps
    # The staffing label, site switcher and nudge banner all ride the flag.
    assert src.count("isManagerial") >= 4


def test_every_tabscontent_has_a_matching_pill():
    """Structural invariant: each <TabsContent value=X> in the page maps to
    a tab id that buildTabs can offer (no orphan content), and each tab id
    offered has a TabsContent (no orphan pill → blank page)."""
    src = _src()
    content_ids = set(re.findall(r'<TabsContent value="([a-z-]+)"', src))
    pill_ids = set(re.findall(r"\{ id: '([a-z-]+)',\s*label", src))
    missing_content = pill_ids - content_ids
    assert not missing_content, (
        f"tab pills with NO content (blank page when clicked): {sorted(missing_content)}"
    )
    orphan_content = content_ids - pill_ids
    assert not orphan_content, f"TabsContent without any pill: {sorted(orphan_content)}"
