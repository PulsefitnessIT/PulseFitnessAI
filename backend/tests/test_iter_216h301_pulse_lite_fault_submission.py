"""Iter 216h301 — Pulse Lite "Log a fault" submission + AI helper text.

User-reported follow-up to h300. On the *Pulse Fitness Lite* portal
variant (non-AI tenants — `isPro === false`):

1. **Submission failed.** Clicking "Submit Fault Report" produced a
   toast: *"Couldn't log the fault. Please check your connection
   and try again."*

   Root cause: the basic-tier submit button was wired as
   `<Button onClick={onFaultSubmit}>` directly. React passes the
   click event as the first argument, so `handleFaultSubmit(event)`
   ran with `overrides = SyntheticEvent`. `_buildMachinePayload`
   then spread the event into the JSON body via `...overrides`,
   producing a payload containing DOM nodes / circular refs.
   axios' `JSON.stringify` either threw or produced garbage that
   short-circuited the request — the user saw the generic
   "check your connection" fallback because `err.response` was
   undefined.

   Fix: wrap the handler — `onClick={() => onFaultSubmit()}` —
   matching every other onClick in the same component.

2. **"helps AI diagnose faster" copy** appeared under
   *Any steps already taken?* even when AI is disabled for the
   tenant (Pulse Lite has no AI Triage button — the copy was a
   leftover hint from the Pro variant).

   Fix: gate the placeholder on `isPro`. Pro keeps the AI hint,
   Lite gets neutral copy ("gives the engineer a head start").
"""
from __future__ import annotations

from pathlib import Path

LITE_DIALOGS = Path("/app/frontend/src/pages/LiteDashboard/LiteDialogs.js")


# ── Bug 1: submission button must not pass the event to handler ────


def test_basic_submit_button_wraps_handler_in_arrow():
    """Pin: the Pulse Lite (non-isPro) "Submit Fault Report" button
    must NOT bind `onFaultSubmit` directly — that leaks the React
    click event into the payload as `overrides`."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    # The basic submit must use an arrow wrapper.
    assert 'onClick={() => onFaultSubmit()}' in text, (
        "Pulse Lite basic submit must wrap onFaultSubmit so the "
        "React click event doesn't get spread into the POST body."
    )


def test_no_bare_onfaultsubmit_onclick_remains():
    """Defence-in-depth — pin we don't reintroduce
    `onClick={onFaultSubmit}` anywhere in LiteDialogs.

    Direct binding leaks the SyntheticEvent into `_buildMachinePayload`
    via the `overrides` param, breaking the POST silently.
    """
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    assert "onClick={onFaultSubmit}" not in text, (
        "Bare onClick={onFaultSubmit} binding was re-introduced. "
        "Use onClick={() => onFaultSubmit()} instead."
    )


# ── Bug 2: AI hint copy must be gated on the tenant's AI features ──


def test_steps_taken_placeholder_gates_ai_hint_on_ispro():
    """Pin: the *Any steps already taken?* placeholder shows the AI
    hint only for `isPro` tenants. Pulse Lite (non-Pro) must get
    neutral copy.

    The previous static placeholder mentioned AI for everyone, which
    confused Lite users who have no AI Triage in their portal at all.
    """
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    # The placeholder block must reference isPro
    placeholder_idx = text.find("data-testid=\"lite-fault-steps-taken\"")
    assert placeholder_idx > -1, "steps-taken Textarea not found"
    # Look at a window around the textarea (before / after) since the
    # placeholder may be on its own line
    window = text[max(0, placeholder_idx - 600): placeholder_idx + 200]
    assert "isPro" in window, (
        "steps_taken placeholder must be gated on isPro — Pulse "
        "Lite tenants are still seeing the AI hint."
    )
    # Pro copy must still mention AI
    assert "helps AI diagnose faster" in window
    # Non-Pro fallback must NOT mention AI
    assert "gives the engineer a head start" in window


def test_old_static_ai_hint_placeholder_is_gone():
    """Make sure the bare, always-on AI hint placeholder string is
    no longer present *as a static attribute value*.

    We check for the exact attribute literal (with the surrounding
    quotes) so the regression test isn't tripped by the Pro branch
    of the ternary which still uses the same hint text inside a JS
    expression.
    """
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    assert 'placeholder="Have you tried anything to fix this? (helps AI diagnose faster)"' not in text, (
        "Static, always-on AI hint placeholder is back — Pulse "
        "Lite tenants will see the AI hint again."
    )


# ── Sanity: h300 triage-pass-through path is unaffected ────────────


def test_h300_triage_forwarding_still_present():
    """h300 added `onFaultSubmit(triagePayload)` to forward the AI
    assessment on the Pro path. The h301 fix only changes the Lite
    path's submit button — pin the h300 wiring still survives."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    assert "onFaultSubmit(triagePayload)" in text
    assert "JSON.stringify(triageResult)" in text


def test_pro_triage_button_still_wired_via_arrow_wrapper():
    """The Pro path's "Get AI Triage & Submit" button has always
    used arrow wrappers (handleTriage / handleConfirmAfterTriage).
    Pin that none of them regressed during the h301 edit."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    assert "onClick={handleTriage}" in text
    assert "onClick={handleConfirmAfterTriage}" in text
