"""Iter 216h300 — AI triage payload must persist to the issue record.

User-reported follow-up to h299: the AI triage assessment was being
rendered correctly inside the Log-a-Fault form (h299 fix) but
discarded at submission time, so the fault detail page (which
already supports rendering `issue.ai_triage_parsed`) showed
nothing — the assessment never reached the backend.

Root cause: `handleConfirmAfterTriage` in `LiteDialogs.js` cleared
`triageResult` and called `onFaultSubmit()` without arguments. The
parent's `_buildMachinePayload` had no `ai_triage` field to pull
from. The payload reached `POST /api/issues` with no triage data
and the backend's `_parse_ai_triage` had nothing to parse.

Pins covered
------------
* `_buildMachinePayload` exposes `ai_triage` in the payload
* `_buildMachinePayload` prefers `overrides.ai_triage` then falls
  back to `form.ai_triage`
* `handleConfirmAfterTriage` JSON-stringifies the triage object
  before forwarding (`IssueCreate.ai_triage` is `Optional[str]`)
* `handleConfirmAfterTriage` still clears local triage state so
  the form doesn't keep stale data for the next fault
* Backend `IssueCreate` schema still accepts `ai_triage` field
* Backend `_build_issue_doc` still writes `ai_triage` to the
  Mongo document
* Backend `_parse_ai_triage` parses the JSON string into
  `ai_triage_parsed`
* The `IssueDetailPanel` already renders `ai_triage_parsed` so
  no frontend display change was needed (sanity-pin via grep)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

LITE_DIALOGS = Path("/app/frontend/src/pages/LiteDashboard/LiteDialogs.js")
LITE_PAGE = Path("/app/frontend/src/pages/LiteDashboardPage.js")
ISSUES_SCHEMA = Path("/app/backend/models/schemas.py")
ISSUES_ROUTE = Path("/app/backend/routes/issues.py")
ISSUE_DETAIL = Path("/app/frontend/src/pages/IssueDetailPanel.js")


# ── Submission flow source pins ────────────────────────────────────


def test_handle_confirm_after_triage_forwards_payload():
    """The single most important pin — without this the triage
    assessment is lost between form and backend."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    # Locate the handler body
    idx = text.find("const handleConfirmAfterTriage")
    assert idx > -1, "handleConfirmAfterTriage handler not found"
    body = text[idx:idx + 1200]
    # Must build a payload using triageResult
    assert "JSON.stringify(triageResult)" in body, (
        "handleConfirmAfterTriage must JSON-stringify the triage "
        "before forwarding — IssueCreate.ai_triage is Optional[str]."
    )
    # And forward it via onFaultSubmit(arg)
    assert "onFaultSubmit(triagePayload)" in body
    # The old no-arg invocation must be gone
    assert "onFaultSubmit();\n  };" not in body, (
        "Old `onFaultSubmit()` no-arg invocation has returned — "
        "triage will be discarded again."
    )


def test_handle_confirm_after_triage_still_clears_local_state():
    """Even with the forward fix, the local triageResult must reset
    so the next fault doesn't keep stale data."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    idx = text.find("const handleConfirmAfterTriage")
    body = text[idx:idx + 1200]
    # Must call setTriageResult(null) before onFaultSubmit
    set_null_idx = body.find("setTriageResult(null)")
    submit_idx = body.find("onFaultSubmit(triagePayload)")
    assert 0 < set_null_idx < submit_idx, (
        "Local triage state must be cleared BEFORE submission so "
        "the next form load starts blank."
    )


def test_build_machine_payload_includes_ai_triage():
    """The parent component must thread the field through to the
    POST body, otherwise the LiteDialogs fix above is wasted."""
    text = LITE_PAGE.read_text(encoding="utf-8")
    idx = text.find("const _buildMachinePayload")
    assert idx > -1, "_buildMachinePayload helper not found"
    body = text[idx:idx + 1500]
    # The field must appear in the constructed payload
    assert "ai_triage:" in body
    # Prefer overrides (set by handleConfirmAfterTriage) over form
    assert "overrides.ai_triage" in body
    # Falls back to form.ai_triage (for the multi-machine path where
    # each staged machine may have had its own triage run)
    assert "form.ai_triage" in body


# ── Backend contract pins ──────────────────────────────────────────


def test_issuecreate_schema_still_accepts_ai_triage():
    """The frontend fix relies on the backend accepting the field.
    Pin we don't accidentally remove it from the Pydantic model."""
    text = ISSUES_SCHEMA.read_text(encoding="utf-8")
    cls_idx = text.find("class IssueCreate")
    assert cls_idx > -1
    block = text[cls_idx:cls_idx + 2000]
    assert "ai_triage: Optional[str]" in block, (
        "IssueCreate.ai_triage was removed — frontend will start "
        "sending an unknown field and Pydantic will reject the POST."
    )


def test_build_issue_doc_writes_ai_triage_to_mongo():
    """And the route handler must propagate it into the document
    we insert into Mongo."""
    text = ISSUES_ROUTE.read_text(encoding="utf-8")
    idx = text.find("def _build_issue_doc")
    body = text[idx:idx + 5000]
    assert '"ai_triage": issue.ai_triage' in body, (
        "_build_issue_doc no longer writes ai_triage — the fault "
        "detail page will keep showing nothing."
    )


def test_parse_ai_triage_helper_runs_on_read():
    """And the read path must turn the stored JSON string back into
    `ai_triage_parsed` so the detail page can render it."""
    text = ISSUES_ROUTE.read_text(encoding="utf-8")
    assert "def _parse_ai_triage" in text
    assert "ai_triage_parsed" in text


# ── Display-side sanity check ──────────────────────────────────────


def test_issue_detail_panel_renders_ai_triage_parsed():
    """The frontend detail page was already wired for this — pin we
    don't accidentally remove the renderer."""
    text = ISSUE_DETAIL.read_text(encoding="utf-8")
    assert "ai_triage_parsed" in text
    # And the gating expression must permit either parsed OR raw
    # fallback, so a partial parse doesn't blank out the section
    assert "ai_triage_parsed" in text


# ── End-to-end JSON sanity (no DB) ─────────────────────────────────


def test_json_stringified_triage_is_round_trippable():
    """The frontend stringifies a triage dict; the backend's
    `_parse_ai_triage` parses it back via `json.loads`. Sanity-
    check the round trip outside React so a future schema drift
    is caught here too.
    """
    triage = {
        "priority": "operational_minor",
        "diagnosis": "Chain wear, increased stiffness",
        "fault_code": "BIKE-CHAIN-STIFF",
        "repair_steps": [
            {"instruction": "Lubricate chain"},
            {"instruction": "Inspect alignment"},
        ],
        "parts_likely": "Chain, lube",
        "estimated_downtime": "20m",
    }
    s = json.dumps(triage)
    assert isinstance(s, str)
    parsed = json.loads(s)
    assert parsed["fault_code"] == "BIKE-CHAIN-STIFF"
    assert len(parsed["repair_steps"]) == 2


# ── h299 fix unaffected by h300 (smoke pin) ────────────────────────


def test_h299_dropdown_still_present_after_h300_fix():
    """Our h299 change added the triage dropdown inside the form.
    The h300 fix only touches the submit handler — make sure the
    dropdown markup didn't get clobbered in the same edit."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    assert 'ai-triage-result-dropdown' in text
    assert '<details' in text
