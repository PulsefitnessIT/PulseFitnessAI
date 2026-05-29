"""Iter 220bt — frontend picklist UX polish.

Locks in:

  1. ``frontend/src/lib/picklistErrorHandler.js`` exists and exports
     both helper functions with the expected names.
  2. The helper recognises the backend's structured 400 payload shape
     and produces a "did you mean" suggestion.
  3. The opportunity create / save and the tender create / save flows
     all import + invoke ``notifyPicklistError`` so a bogus picklist
     value lands as a rich toast (not a silent console.error).

These are static / textual asserts — the actual rendering is covered
by the Playwright e2e suite when the user toggles to v3 testing.
"""
from __future__ import annotations

import re
from pathlib import Path


FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


# ══════════════ 1 · helper module exists with both exports ════════


def test_picklist_helper_module_exists_with_exports():
    helper = FRONTEND_SRC / "lib" / "picklistErrorHandler.js"
    assert helper.exists(), f"missing: {helper}"
    text = helper.read_text()
    assert "export function extractPicklistError" in text
    assert "export function notifyPicklistError" in text
    # The helper must read the structured payload shape the backend emits.
    assert "invalid_picklist_value" in text
    assert "valid_examples" in text
    assert "field_label" in text
    # Suggestion logic must be present.
    assert "suggestion" in text.lower()


def test_helper_does_not_use_useauth_or_double_api_prefix():
    """Iter 220bo regression — keep the new helper free of the
    legacy patterns we banned."""
    text = (FRONTEND_SRC / "lib" / "picklistErrorHandler.js").read_text()
    assert "useAuth" not in text
    assert "/api/api/" not in text


# ══════════════ 2 · CRMPipeline wires the helper ══════════════════


def test_crm_pipeline_imports_and_calls_notify_picklist_error():
    src = (FRONTEND_SRC / "pages" / "CRM" / "CRMPipeline.js").read_text()
    # Import line — exact module path so a future move shows up here.
    assert "from '@/lib/picklistErrorHandler'" in src
    assert "notifyPicklistError" in src
    assert "from '@/components/notifications'" in src
    # No silent console.error fallback on the create / save paths.
    # We count `console.error(e)` and require at least one call site
    # was converted away from it for the picklist surface.
    create_block_idx = src.find("const handleCreate = async")
    assert create_block_idx > 0
    # Look at the next ~600 chars (covers the try/catch).
    create_block = src[create_block_idx:create_block_idx + 800]
    assert "notifyPicklistError" in create_block
    # Edit / save path too.
    edit_block_idx = src.find("const saveEdit = async")
    assert edit_block_idx > 0
    edit_block = src[edit_block_idx:edit_block_idx + 800]
    assert "notifyPicklistError" in edit_block


# ══════════════ 3 · CRMTenders wires the helper ═══════════════════


def test_crm_tenders_imports_and_calls_notify_picklist_error():
    src = (FRONTEND_SRC / "pages" / "CRM" / "CRMTenders.js").read_text()
    assert "from '@/lib/picklistErrorHandler'" in src
    assert "notifyPicklistError" in src
    # Tender list-page create button.
    create_idx = src.find("const handleCreate = async")
    assert create_idx > 0
    create_block = src[create_idx:create_idx + 800]
    assert "notifyPicklistError" in create_block
    # Tender detail-page save (the company/opp re-link form).
    save_idx = src.find("const save = async")
    assert save_idx > 0
    save_block = src[save_idx:save_idx + 1000]
    assert "notifyPicklistError" in save_block


# ══════════════ 4 · helper smoke — token-overlap suggestion ═══════


def test_helper_suggestion_logic_via_textual_assertions():
    """The suggestion logic is pure JS but we can sanity-check the
    branches exist in source. The functional test runs via the e2e
    Playwright path."""
    text = (FRONTEND_SRC / "lib" / "picklistErrorHandler.js").read_text()
    # All three layers of the suggestion fallback must be present.
    assert "exact" in text.lower() or "toLowerCase()" in text  # case-insensitive match
    assert "includes" in text  # substring match
    assert "split" in text  # token overlap
    # Title casing for the toast.
    assert "Did you mean" in text


# ══════════════ 5 · companion lint-style guard rails ═════════════


def test_no_picklist_handler_duplicates():
    """A future refactor must not silently create a second
    picklist-error utility — one source of truth keeps the toast
    behaviour consistent across all CRM drawers."""
    matches: list[Path] = []
    for p in FRONTEND_SRC.rglob("*.js"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "export function notifyPicklistError" in text or \
           "export function extractPicklistError" in text:
            matches.append(p)
    assert len(matches) == 1, (
        "Multiple picklist-error helpers detected — should be exactly "
        "one canonical implementation under /lib/picklistErrorHandler.js. "
        f"Found in: {[str(m) for m in matches]}"
    )


def test_pipeline_and_tender_no_longer_swallow_console_error_on_save():
    """Confirm the silent ``catch (e) { console.error(e); }`` pattern
    was replaced for the picklist-touching saves. We allow it to
    remain on non-mutating reads / DnD reorders / activity adds that
    don't carry picklist payloads."""
    pipeline = (FRONTEND_SRC / "pages" / "CRM" / "CRMPipeline.js").read_text()
    # Specifically, the handleCreate + saveEdit blocks must NOT contain
    # the swallow pattern any more — they go through notifyPicklistError.
    for fn_name in ("handleCreate", "saveEdit"):
        idx = pipeline.find(f"const {fn_name} = async")
        assert idx > 0, f"{fn_name} not found in CRMPipeline.js"
        # Look at the function body — bounded by the next blank-line+`}`
        # closure (good enough; the functions are short).
        body = pipeline[idx:idx + 900]
        assert "console.error(e); }" not in body, (
            f"CRMPipeline.js::{fn_name} still swallows errors silently"
        )
