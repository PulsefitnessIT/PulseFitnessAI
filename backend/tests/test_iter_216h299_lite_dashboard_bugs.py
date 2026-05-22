"""Iter 216h299 — Three Lite-Dashboard bug fixes.

Closes three reported regressions visible on the maintenance hub
preview environment:

1. Equipment Detail → "Log Fault for this Machine" — modal opens
   then immediately disappears. Caused by Radix Dialog seeing the
   originating click as "outside" the new fault dialog (since it
   originated in the just-closed equipment dialog). Fixed in
   `LiteDashboardPage.js` by deferring `setShowFaultDialog(true)`
   to the next animation frame.

2. AI Triage results render at the bottom of the Log-a-Fault form
   instead of under "Steps Already Taken" in a collapsible
   dropdown. Fixed in `LiteDialogs.js`.

3. QR scan page doesn't display the machine photo when the only
   photo source is the auto-matched manufacturer image or
   spec-sheet hero. Fixed in `routes/qr_codes.py`.

Pins covered
------------
* Public equipment endpoint returns `photo_url` when only
  `photo_path` is set (legacy + new uploads)
* Falls back to `auto_image_url` when neither photo_path nor
  photo_url is set
* Falls back to `spec_sheet_image` when no operator photo and
  no auto-matched image exists
* Returns `None` when the equipment has no photo source at all
* The frontend bug fixes are pinned via string-presence checks
  so they can't quietly revert (this is the only "regression
  prevention" path that doesn't require booting React).
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _ensure_emergentintegrations_chat():
    """An earlier test in the regression suite stubs
    `emergentintegrations.llm` as a bare module (no `__path__`).
    When `routes.qr_codes` is imported later it does
    `from emergentintegrations.llm.chat import ...` and Python
    refuses because the cached `emergentintegrations.llm` isn't a
    package. Re-install proper package stubs (with `__path__`) so
    the dotted import resolves no matter the test order.
    """
    pkg = sys.modules.get("emergentintegrations")
    if pkg is None or not hasattr(pkg, "__path__"):
        pkg = types.ModuleType("emergentintegrations")
        pkg.__path__ = []  # noqa: ERA001 — marks the stub as a package
        sys.modules["emergentintegrations"] = pkg
    llm = sys.modules.get("emergentintegrations.llm")
    if llm is None or not hasattr(llm, "__path__"):
        llm = types.ModuleType("emergentintegrations.llm")
        llm.__path__ = []
        sys.modules["emergentintegrations.llm"] = llm
        pkg.llm = llm
    chat = sys.modules.get("emergentintegrations.llm.chat")
    if chat is None:
        chat = types.ModuleType("emergentintegrations.llm.chat")
        sys.modules["emergentintegrations.llm.chat"] = chat
        llm.chat = chat
    # Stub the symbols routes.qr_codes imports
    for name in ("LlmChat", "UserMessage", "FileContentWithMimeType", "ImageContent"):
        if not hasattr(chat, name):
            setattr(chat, name, MagicMock())


_ensure_emergentintegrations_chat()

# Import routes.qr_codes once at module-load (after the stubs are
# in place) so subsequent tests don't trigger a re-import that
# could race with whatever later tests do to sys.modules.
from routes import qr_codes as _qr_codes  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _request_stub():
    """Minimal FastAPI Request stub for `resolve_frontend_url`."""
    req = MagicMock()
    req.url.scheme = "https"
    req.url.hostname = "gymaxisai.com"
    req.headers = {}
    return req


# ── Bug 3: QR scan endpoint photo fallback chain ───────────────────


def test_public_equipment_uses_photo_url_when_path_present():
    fake_db = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value={
        "id": "eq1", "name": "Treadmill 7", "organization_id": "org-1",
        "photo_path": "gymaxis/equipment-photos/eq1/abc.jpg",
        "photo_url": "preview-url-ignored",
        "auto_image_url": "https://manufacturer.example.com/a.jpg",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Test Gym"})
    fake_db.issues.count_documents = AsyncMock(return_value=0)
    with patch.object(_qr_codes, "db", fake_db), \
         patch.object(_qr_codes, "resolve_frontend_url", return_value="https://gymaxisai.com"):
        out = _run(_qr_codes.public_equipment_info("eq1", _request_stub()))
    # When photo_path is present, we ALWAYS re-derive from the current
    # request host (so legacy preview-URL records keep working) — the
    # auto_image_url fallback must NOT be used.
    assert out["photo_url"] == "https://gymaxisai.com/api/public/equipment/eq1/photo"


def test_public_equipment_falls_back_to_auto_image_when_no_upload():
    """The bug the user reported: machine has only an auto-matched
    manufacturer image, QR scan page shows blank."""
    fake_db = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value={
        "id": "eq2", "name": "Bike 3", "organization_id": "org-1",
        # Crucially — no photo_path or photo_url, but auto_image_url is set
        "auto_image_url": "https://cdn.technogym.com/bike-3.jpg",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Test Gym"})
    fake_db.issues.count_documents = AsyncMock(return_value=0)
    with patch.object(_qr_codes, "db", fake_db), \
         patch.object(_qr_codes, "resolve_frontend_url", return_value="https://gymaxisai.com"):
        out = _run(_qr_codes.public_equipment_info("eq2", _request_stub()))
    assert out["photo_url"] == "https://cdn.technogym.com/bike-3.jpg"


def test_public_equipment_falls_back_to_spec_sheet_image_when_no_auto_match():
    fake_db = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value={
        "id": "eq3", "name": "Rower 2", "organization_id": "org-1",
        "spec_sheet_image": "https://cdn.gymaxis.com/spec-sheet/rower-2.jpg",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Test Gym"})
    fake_db.issues.count_documents = AsyncMock(return_value=0)
    with patch.object(_qr_codes, "db", fake_db), \
         patch.object(_qr_codes, "resolve_frontend_url", return_value="https://gymaxisai.com"):
        out = _run(_qr_codes.public_equipment_info("eq3", _request_stub()))
    assert out["photo_url"] == "https://cdn.gymaxis.com/spec-sheet/rower-2.jpg"


def test_public_equipment_returns_none_when_no_photo_sources():
    """Placeholder still gets rendered client-side; backend just signals
    "no photo" with a None. Must not crash, must not 500."""
    fake_db = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value={
        "id": "eq4", "name": "Mystery", "organization_id": "org-1",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Test Gym"})
    fake_db.issues.count_documents = AsyncMock(return_value=0)
    with patch.object(_qr_codes, "db", fake_db), \
         patch.object(_qr_codes, "resolve_frontend_url", return_value="https://gymaxisai.com"):
        out = _run(_qr_codes.public_equipment_info("eq4", _request_stub()))
    assert out["photo_url"] is None


def test_public_equipment_fallback_order_auto_before_spec():
    """When both auto_image_url and spec_sheet_image are set, the
    auto match wins (matches the dashboard's `fallbackImageUrl`
    ladder in LiteDialogs.js:180-192)."""
    fake_db = MagicMock()
    fake_db.equipment.find_one = AsyncMock(return_value={
        "id": "eq5", "name": "Both", "organization_id": "org-1",
        "auto_image_url": "https://manufacturer.example.com/a.jpg",
        "spec_sheet_image": "https://cdn.example.com/spec.jpg",
    })
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Test Gym"})
    fake_db.issues.count_documents = AsyncMock(return_value=0)
    with patch.object(_qr_codes, "db", fake_db), \
         patch.object(_qr_codes, "resolve_frontend_url", return_value="https://gymaxisai.com"):
        out = _run(_qr_codes.public_equipment_info("eq5", _request_stub()))
    assert out["photo_url"] == "https://manufacturer.example.com/a.jpg"


# ── Bug 1: Log-Fault modal disappears (static source check) ────────


LITE_PAGE = Path("/app/frontend/src/pages/LiteDashboardPage.js")
LITE_DIALOGS = Path("/app/frontend/src/pages/LiteDashboard/LiteDialogs.js")


def test_log_fault_for_equipment_defers_dialog_open():
    """The Radix-disappearing-modal bug returns the moment the
    handler synchronously closes the equipment dialog AND opens
    the fault dialog in the same render pass. Pin the
    requestAnimationFrame deferral so a future cleanup doesn't
    quietly reintroduce the regression.

    Other call sites that open the fault dialog from a quick-action
    button (overview tab, mobile bottom nav) are NOT affected
    because those clicks don't originate inside another open dialog.
    """
    text = LITE_PAGE.read_text(encoding="utf-8")
    # Find the onLogFaultForEquipment handler specifically
    handler_idx = text.find("onLogFaultForEquipment={")
    assert handler_idx > -1, "onLogFaultForEquipment handler not found"
    # Inspect the next 800 chars (the whole handler body)
    handler_block = text[handler_idx:handler_idx + 800]
    # The handler must defer the fault-dialog open
    assert "requestAnimationFrame(() => setShowFaultDialog(true))" in handler_block, (
        "onLogFaultForEquipment must defer setShowFaultDialog via "
        "requestAnimationFrame — see iter 216h299 fix."
    )
    # And must NOT contain the synchronous handoff inside this specific handler
    sync_pattern = "setActiveTab('faults');\n          setShowFaultDialog(true);"
    assert sync_pattern not in handler_block, (
        "Synchronous handoff is back in onLogFaultForEquipment — "
        "Radix will swallow the dialog. Use requestAnimationFrame instead."
    )


# ── Bug 2: AI triage dropdown placement (static source check) ──────


def test_ai_triage_results_render_under_steps_already_taken():
    """The triage <details> dropdown must live inside the same
    <div> that wraps the Steps Already Taken textarea, NOT down
    at the bottom of the form."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    steps_idx = text.find("lite-fault-steps-taken")
    triage_idx = text.find("ai-triage-result-dropdown")
    submit_idx = text.find("lite-fault-submit")
    assert steps_idx > -1, "Steps Already Taken textarea not found"
    assert triage_idx > -1, (
        "AI triage dropdown missing — it must live under Steps Already Taken"
    )
    assert submit_idx > -1
    # The dropdown must appear AFTER the steps field …
    assert steps_idx < triage_idx, "Triage dropdown is above Steps field"
    # … and BEFORE the submit button (i.e. mid-form, not at the bottom)
    assert triage_idx < submit_idx, "Triage dropdown is below the submit button"


def test_ai_triage_dropdown_uses_collapsible_details():
    """User explicitly asked for a dropdown box. Pin that we used
    a <details>/<summary> rather than rendering inline."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    # The dropdown markup
    assert '<details' in text
    assert '<summary' in text
    # And the test-id the BA can use to target it in e2e
    assert 'ai-triage-result-dropdown' in text


def test_old_bottom_of_form_triage_block_is_gone():
    """Pin we removed the duplicate render that used to sit at the
    bottom of the form — otherwise the user sees the AI assessment
    twice."""
    text = LITE_DIALOGS.read_text(encoding="utf-8")
    # The old block opened with this exact comment
    assert "{/* AI Triage Results (Pro only) */}" not in text, (
        "Old bottom-of-form triage block is still present — "
        "duplicate render."
    )
    # Confirm exactly ONE occurrence of the test-id (the new dropdown);
    # zero or two would mean the block was either removed entirely or
    # duplicated.
    assert text.count('data-testid="ai-triage-result"') == 1
