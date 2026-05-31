"""Iter 220ea·12 — Per-machine Work Actioned + Further Work + parts.

Four connected changes inside the Equipment tab's expanded row in
`WorkVisitMachinesCard.js`:

1. The "Machine" name picker (`MachineAssetPicker`) is removed
   from the row body. Once the engineer picks an asset via "From
   site" or "New asset", the name is locked — they shouldn't be
   able to overwrite it inline on the case.
2. The "Notes / Recommendations" textarea is renamed "Work
   actioned". The placeholder text is also updated to match
   ("Replaced drive belt, calibrated speed sensor, lubricated…").
3. A new "Further work required" textarea is added — for any work
   that's still needed on a return visit. Backed by a new
   `further_work` field on the `svc_work_visit_machines` row.
4. Two compact parts widgets live inside the row:
   • `MachineRowPartsUsed`     → POSTs to `/parts/use`        with `machine_id = row.id`
   • `MachineRowPartsForReturn`→ POSTs to `/parts-requests`   with `machine_id = row.id`
   Both render any existing tagged parts as chips/list rows.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
MACHINES   = FRONTEND / "pages/ServiceOps/Engineer/WorkVisitMachinesCard.js"
BACKEND    = Path("/app/backend/routes/svc/per_machine_reports.py")


def _read(p: Path) -> str:
    return p.read_text()


# ── 1 · Machine name picker removed from row body ────────────────


def test_inline_machine_asset_picker_removed_from_row_body():
    src = _read(MACHINES)
    # The expanded-row markup no longer wires up the picker.
    assert "<MachineAssetPicker" not in src
    # And there's no inline "Machine" label sitting above an input
    # in the row body. (The card still has a "Machines on this
    # visit" heading at the top, which is unrelated.)
    assert ">Machine</label>" not in src


# ── 2 · Notes / Recommendations → Work actioned ──────────────────


def test_row_body_label_renamed_to_work_actioned():
    src = _read(MACHINES)
    assert "Work actioned" in src
    assert "Notes / Recommendations" not in src


# ── 3 · Further work required field ──────────────────────────────


def test_further_work_textarea_present():
    src = _read(MACHINES)
    assert "Further work required" in src
    assert 'data-testid={`machine-further-work-${row.id}`}' in src
    # And the patch wires `further_work` through onPatch.
    assert "onPatch({ further_work: e.target.value })" in src


def test_further_work_field_on_backend_models():
    src = _read(BACKEND)
    # Both the create (MachineRowIn) and patch (MachineRowPatch)
    # accept the new field, bounded to 4000 chars (same as notes).
    assert "further_work: Optional[str] = Field(default=None, max_length=4000)" in src
    # And the PATCH endpoint normalises the value the same way it
    # normalises notes (strip → None if empty).
    assert 'if "further_work" in updates:' in src
    assert 'updates["further_work"] = (updates["further_work"] or "").strip() or None' in src


# ── 4 · Per-machine parts widgets ────────────────────────────────


def test_parts_used_widget_present():
    src = _read(MACHINES)
    assert "function MachineRowPartsUsed(" in src
    assert 'data-testid={`machine-parts-used-${row.id}`}' in src
    # And the add button POSTs to /parts/use with the row's id as
    # the `machine_id` so the customer report can link the part
    # to this specific asset.
    assert "/svc/engineer/jobs/${caseId}/parts/use" in src
    assert "machine_id: row.id" in src


def test_parts_for_return_widget_present():
    src = _read(MACHINES)
    assert "function MachineRowPartsForReturn(" in src
    assert 'data-testid={`machine-parts-return-${row.id}`}' in src
    # POSTs to the parts-requests endpoint with the row's id as
    # the machine_id so ops can group requests by asset.
    assert "/svc/engineer/parts-requests" in src
    assert "urgency: 'next_visit'" in src


def test_parts_widgets_share_inline_picker():
    """Both widgets use the same `MachineRowPartsPickerInline`
    component so the search + qty UI is consistent. Reduces
    duplicate code + makes the row feel coherent."""
    src = _read(MACHINES)
    assert "function MachineRowPartsPickerInline(" in src
    # Used by both wrapper widgets.
    used_count = src.count("<MachineRowPartsPickerInline")
    assert used_count == 2, f"expected 2 picker mounts, found {used_count}"


def test_parts_widgets_receive_case_and_row():
    """The card now passes `caseId` and `refreshRows` down to the
    MachineRow so the widgets can self-fetch and re-fetch."""
    src = _read(MACHINES)
    assert "caseId={caseId}" in src
    assert "refreshRows={load}" in src
    # And MachineRow destructures both.
    assert "row, index, caseId, expanded, onExpand, onPatch" in src
    assert "refreshRows," in src
