"""Iter 220dw — Customer-portal Log-a-Fault: case_type + serial_unknown.

The dashboard's Log-a-Fault dialog (used by gym staff to log
faults on equipment they manage) now surfaces:

  * **Job Type dropdown** — Repair / PPM / Install / Inspection /
    Callout / Audit. Drives the engineer Summary chip + custom-
    field auto-load (iters 220dt/220du/220dv).
  * **Serial unknown checkbox** + reason dropdown — escape hatch
    for rubbed-off plates. When ticked, the serial input disables
    and the case is stamped so the engineer's first-visit task
    can capture it (iter 220dt backend).

Backend already accepts both fields (iter 220dt). This iter wires
them into the user-facing form, the empty-form scaffold, and pins
the contract.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── 1 · Job-type dropdown on the form ─────────────────────────────


def test_log_a_fault_dialog_renders_case_type_dropdown():
    src = _read("pages/Dashboard/FaultDialogs.js")
    assert 'data-testid="issue-case-type-wrapper"' in src
    assert 'data-testid="issue-case-type-select"' in src
    # All six slugs available.
    for slug, label in (
        ("repair", "Repair"),
        ("ppm", "Preventative Maintenance Service"),
        ("install", "Installation"),
        ("inspection", "Safety / compliance inspection"),
        ("callout", "Emergency callout"),
        ("audit", "Asset audit"),
    ):
        assert f'<option value="{slug}">{label}</option>' in src, (
            f"missing {slug} option in Log-a-Fault dialog"
        )
    # Default value comes from the form ("repair" via the empty
    # scaffold or whatever the user picked).
    assert "issueForm.case_type || 'repair'" in src


# ── 2 · Serial-unknown checkbox + reason ──────────────────────────


def test_log_a_fault_dialog_renders_serial_unknown_controls():
    src = _read("pages/Dashboard/FaultDialogs.js")
    assert 'data-testid="issue-serial-unknown-wrap"' in src
    assert 'data-testid="issue-serial-unknown"' in src
    # Reason dropdown only appears when checkbox is ticked.
    assert "issueForm.serial_unknown && (" in src
    assert 'data-testid="issue-serial-unknown-reason"' in src
    # The three operator-supplied reasons.
    for reason in ("rubbed_off", "not_visible", "never_had_one"):
        assert f'value="{reason}"' in src
    # The serial input disables when unknown is ticked so customers
    # can't half-fill both.
    assert "disabled={!!issueForm.serial_unknown}" in src


# ── 3 · Empty-form scaffold initialises both fields ───────────────


def test_empty_issue_form_carries_new_fields():
    src = _read("pages/Dashboard/hooks/useIssueWorkflow.js")
    assert "case_type: 'repair'" in src
    assert "serial_unknown: false" in src
    assert "serial_unknown_reason: ''" in src


# ── 4 · Payload propagation (currentMachine spread) ───────────────


def test_log_a_fault_payload_inherits_new_fields_via_spread():
    """The POST payload is built with ``...currentMachine`` (which
    is the active form object). Pin the spread so a future refactor
    that switches to picking explicit fields doesn't accidentally
    drop the new ones."""
    src = _read("pages/Dashboard/hooks/useIssueWorkflow.js")
    assert "...currentMachine," in src
    # Backend endpoint contract unchanged.
    assert "axios.post(`${API}/issues`" in src
