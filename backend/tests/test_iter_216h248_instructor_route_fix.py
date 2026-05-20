"""Iter 216h248 — Add-new-instructor routing fix.

Bug: Clicking "+ Add new instructor" from the Class Template Editor
dropdown routed the operator to the Memberships "Start" screen instead
of the Instructors tab.

Root cause: ``STUDIO_TAB_IDS`` in MembershipsConsole did not include
``'instructors'``. When Studio Mode is on, the guard effect at the top
of MembershipsConsole forces any tab outside that allow-list back to
``'start'``. Because the dropdown ultimately calls ``setTab('instructors')``,
the guard immediately bounced the user back to Start.

Fix: add ``'instructors'`` to the allowed Studio-Mode tab set.
"""
from __future__ import annotations

import pathlib


def test_studio_tab_ids_includes_instructors():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsConsole.js").read_text()
    # Locate the STUDIO_TAB_IDS literal and confirm 'instructors' is in it.
    marker = "const STUDIO_TAB_IDS = useMemo(() => new Set(["
    idx = src.index(marker)
    end = src.index("])", idx)
    block = src[idx:end]
    assert "'instructors'" in block, (
        "STUDIO_TAB_IDS must include 'instructors' so the Add-new-instructor "
        "dropdown routes correctly in Studio Mode"
    )


def test_studio_tab_guard_still_present():
    """Guard effect itself must remain — we only changed the allow-list."""
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsConsole.js").read_text()
    assert "if (studio.studioMode && !STUDIO_TAB_IDS.has(tab)) setTab('start');" in src
