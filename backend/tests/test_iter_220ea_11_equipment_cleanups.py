"""Iter 220ea·11 — Equipment tab follow-up cleanups.

Two more cleanups from a live user report:

1. The "Site equipment" info card (the blue help bubble at the
   top of the Equipment tab explaining how to use "From site")
   is removed. The action buttons on the Machines card make it
   self-explanatory and the help text was eating vertical space
   on a phone.
2. The "Add machine" button is removed. Every machine must be
   backed by a real asset record so engineers pick either:
     • **From site** — existing equipment for this gym
     • **New asset** — create a new equipment record and attach it
   The old blank-row "Add machine" path created orphan rows with
   no asset linkage.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
MACHINES   = FRONTEND / "pages/ServiceOps/Engineer/WorkVisitMachinesCard.js"


def _read(p: Path) -> str:
    return p.read_text()


# ── 1 · Site equipment info card removed ─────────────────────────


def test_site_equipment_info_card_removed():
    src = _read(JOB_DETAIL)
    # The help-bubble text is gone.
    assert "Tap From site to pre-load every machine at this" not in src
    assert "Tap <strong>From site</strong> to pre-load every machine at this" not in src
    # And the literal "Site equipment" heading on the help card is
    # gone too (the card was a separate `<div>` above the Machines
    # card).
    assert ">Site equipment</p>" not in src


# ── 2 · Add machine button removed ───────────────────────────────


def test_add_machine_button_removed():
    src = _read(MACHINES)
    # The blank-row "Add machine" action button is gone.
    assert 'data-testid="machines-add-btn"' not in src
    # And the action grid collapses from 3 columns to 2 columns.
    assert 'className="grid grid-cols-2 gap-2"' in src
    assert 'className="grid grid-cols-3 gap-2"' not in src


def test_two_action_buttons_remain_with_test_ids():
    """The two surviving actions keep their existing test-ids so
    the E2E suite and any older bookmarks/menus still work."""
    src = _read(MACHINES)
    assert 'data-testid="machines-load-from-site-btn"' in src
    assert 'data-testid="machines-new-asset-link"' in src


def test_addrow_helper_still_used_by_site_picker():
    """`addRow` itself isn't deleted — it's still the function the
    "From site" multi-select picker calls when the engineer
    confirms their selection. Only the top-level button that
    bypassed asset linkage is gone."""
    src = _read(MACHINES)
    # The helper definition + its picker call-site remain.
    assert "const addRow = async (preset = {})" in src
    # And the picker's "Add N" CTA still uses it.
    assert "Add {selected.size" in src
