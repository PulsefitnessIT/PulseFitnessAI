"""Iter 220ea·8 — Summary tab follow-up #2.

Source-level guards covering three small Summary cleanups in
`EngineerJobDetailV2.js`:

1. The lower chip row (`jaag-priority` / `jaag-cover-chip` /
   `jaag-case-type` / `jaag-machines` / `jaag-last-visit` /
   `jaag-customer-rating`) is gone. Priority and cover were
   duplicates of the top status-pill row, and the row as a whole
   was visual clutter on a 412 px phone.
2. A new **Case Type** pill (`summary-case-type-pill`) sits in
   the top status-pill row. Labels come from the existing
   `CASE_TYPE_LABELS` map (Repair · PPM · Installation ·
   Inspection · Callout · Audit).
3. The priority pill is now a `<button>` that toggles a
   `summary-priority-key` legend so a new engineer can read what
   "P1 / P2 / P3 / P4" actually mean.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND   = Path("/app/frontend/src")
JOB_DETAIL = FRONTEND / "pages/ServiceOps/Engineer/EngineerJobDetailV2.js"


def _read() -> str:
    return JOB_DETAIL.read_text()


# ── 1 · Lower chip row removed ───────────────────────────────────


def test_lower_chip_row_completely_removed():
    """The whole `jaag-*` chip row is gone — every test-id from
    the duplicate row must be absent."""
    src = _read()
    for tid in (
        "jaag-priority",
        "jaag-cover-chip",
        "jaag-case-type",
        "jaag-machines",
        "jaag-last-visit",
        "jaag-customer-rating",
    ):
        assert f'data-testid="{tid}"' not in src, (
            f"Lower chip {tid} must be removed from Summary"
        )


def test_unused_chip_row_helpers_removed():
    """`lastVisit` + `machineCount` locals inside JobAtAGlance
    used to feed the chip row. With the row gone, the helpers
    are pruned too — they'd be dead code otherwise."""
    src = _read()
    # The JobAtAGlance function used to compute these. They're
    # now gone; the stats grid computes its own `machineCount`
    # internally from `job.machines_count`.
    assert "const lastVisitDoc" not in src
    assert "const lastVisit " not in src
    # The `History` lucide-react icon is no longer imported.
    assert " History," not in src


# ── 2 · Case Type pill ───────────────────────────────────────────


def test_case_type_pill_exists_on_top_status_row():
    src = _read()
    assert 'data-testid="summary-case-type-pill"' in src
    # The pill uses the canonical labeller so future taxonomy
    # changes (new case_type values) flow through one place.
    assert "labelForCaseType(job.case_type)" in src


def test_case_type_pill_renders_after_priority_in_status_row():
    """Visual order inside the top pill row:
    status → SLA → priority → case-type → chargeable."""
    src = _read()
    status_pill   = src.index('data-testid="summary-status-pill"')
    priority_pill = src.index('data-testid="summary-priority-pill"')
    case_type     = src.index('data-testid="summary-case-type-pill"')
    assert status_pill < priority_pill < case_type, (
        "Status-pill row order regressed — expected "
        "status → priority → case-type"
    )


# ── 3 · Priority key legend ──────────────────────────────────────


def test_priority_pill_is_now_a_button():
    """It must render as a real `<button>` so it's keyboard
    accessible, with aria-expanded + aria-haspopup."""
    src = _read()
    # The pill block now opens with `<button ... onClick={() => setShowKey`
    assert "onClick={() => setShowKey((v) => !v)}" in src
    assert "aria-expanded={showKey}" in src
    assert 'aria-haspopup="dialog"' in src


def test_priority_key_legend_renders_four_tiers():
    src = _read()
    assert 'data-testid="summary-priority-key"' in src
    assert "const PRIORITY_KEY" in src
    for code in ("P1", "P2", "P3", "P4"):
        # The legend renders a row per tier with a stable test-id.
        assert f'summary-priority-key-row-${{p.code}}' in src or f'"summary-priority-key-row-{code}"' in src
    # And the legend uses the canonical labels + detail copy.
    for word in ("Critical", "High", "Standard", "Low"):
        assert word in src, f"missing priority label: {word}"


def test_priority_key_closes_on_outside_tap():
    """The popover uses a `wrapRef` + `mousedown` / `touchstart`
    listeners so it dismisses cleanly when the engineer taps
    away — important on a touch screen."""
    src = _read()
    assert "wrapRef" in src
    assert "document.addEventListener('mousedown', onDoc)" in src
    assert "document.addEventListener('touchstart', onDoc)" in src


def test_priority_key_has_close_button():
    src = _read()
    assert 'data-testid="summary-priority-key-close"' in src
