"""Iter 216h263 — Fault detail card UX upgrades + auto-photo loading state.

User feedback with screenshots (Feb 21, 2026):
1. "Find manufacturer photo — needs to look like it's working — once
   pressed it looks dead until you get a toast notification."
2. "Fault card — under full description and steps already tried,
   what was recommended within the AI triage (if the customer is on
   pro) — add the AI triage within a dropdown box."
3. "The supplier/user needs the ability to add quotes to the fault
   card, pdf, place this card above Purchase order within the
   fault card."
4. "Move supplier reference/job number above the logged by and
   description — once this has been populated it should be included
   in the main fault line."

Backend changes:
* `POST /api/issues/{id}/attachments` now accepts an optional
  multipart `kind` form field. Persisted on the attachment doc so
  the fault detail card can render quote PDFs in a dedicated
  Quotes section.

Frontend changes:
* `EquipmentPhotoUpload` — "Find manufacturer photo" button now
  wraps the async lookup in its own loading state, swapping the
  Sparkles icon for a spinner + "Searching manufacturer site…"
  copy while the request is in flight.
* `IssueDetailPanel` — AI Triage now lives in a collapsible
  dropdown card. Supplier Reference card moved to the very top of
  the detail panel (above the Logged-by header grid). New Quotes
  card sits between Supplier Communication and Purchase Orders;
  the generic Attachments card now excludes quotes.
* `Dashboard/FaultsTab` + `LiteDashboard/LiteFaultsTab` — the
  fault list row now shows `| Ref: {supplier_ref}` once the
  reference is populated.
"""
from __future__ import annotations

import pathlib
import re
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Backend — attachments accepts `kind` ────────────────────────


def test_add_issue_attachment_persists_kind():
    """The attachment endpoint must save the `kind` field so the UI
    can pull quote PDFs into a dedicated card."""
    import asyncio
    from routes.issues import add_issue_attachment

    fake_file = MagicMock()
    fake_file.filename = "supplier-quote.pdf"
    fake_file.read = AsyncMock(return_value=b"%PDF-1.5 fake")

    captured = {}

    async def fake_find_one(query):
        return {"id": "issue-1", "organization_id": "org-1"}

    async def fake_update_one(query, update):
        captured["push"] = update["$push"]
        return MagicMock()

    fake_db = MagicMock()
    fake_db.issues.find_one = AsyncMock(side_effect=fake_find_one)
    fake_db.issues.update_one = AsyncMock(side_effect=fake_update_one)

    with patch("routes.issues.db", fake_db), \
         patch("routes.issues.put_object", return_value={"path": "x", "url": "https://x", "size": 12}), \
         patch("utils.file_validation.validate_upload", return_value="application/pdf"), \
         patch("routes.issues.get_organization_filter", return_value={"organization_id": "org-1"}):
        result = asyncio.get_event_loop().run_until_complete(
            add_issue_attachment(
                issue_id="issue-1",
                file=fake_file,
                kind="quote",
                user={"id": "u-1", "organization_id": "org-1", "full_name": "Lee"},
            )
        )

    assert result["kind"] == "quote"
    assert captured["push"]["attachments"]["kind"] == "quote"
    assert result["filename"] == "supplier-quote.pdf"


def test_add_issue_attachment_kind_defaults_to_none():
    import asyncio
    from routes.issues import add_issue_attachment

    fake_file = MagicMock()
    fake_file.filename = "photo.jpg"
    fake_file.read = AsyncMock(return_value=b"\xff\xd8\xff")

    fake_db = MagicMock()
    fake_db.issues.find_one = AsyncMock(return_value={"id": "i", "organization_id": "org-1"})
    fake_db.issues.update_one = AsyncMock(return_value=MagicMock())

    with patch("routes.issues.db", fake_db), \
         patch("routes.issues.put_object", return_value={"path": "x", "url": "u", "size": 3}), \
         patch("utils.file_validation.validate_upload", return_value="image/jpeg"), \
         patch("routes.issues.get_organization_filter", return_value={"organization_id": "org-1"}):
        result = asyncio.get_event_loop().run_until_complete(
            add_issue_attachment(
                issue_id="i",
                file=fake_file,
                kind=None,
                user={"id": "u", "organization_id": "org-1", "full_name": "X"},
            )
        )
    assert result["kind"] is None


# ─── 2. Find-manufacturer-photo loading state ───────────────────────


def test_equipment_photo_autolookup_button_has_loading_state():
    src = pathlib.Path(
        "/app/frontend/src/components/equipment/EquipmentPhotoUpload.js"
    ).read_text()
    # Local state + handler
    assert "autoLookingUp" in src
    assert "handleAutoLookup" in src
    # Spinner copy that the user requested ("looks dead" no more)
    assert "Searching manufacturer site" in src
    # Button disables itself while in flight
    assert "disabled={autoLookingUp}" in src


# ─── 3. IssueDetailPanel — AI Triage collapsible ────────────────────


def test_ai_triage_is_collapsible_dropdown():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/IssueDetailPanel.js"
    ).read_text())
    assert "ai-triage-toggle-" in src
    assert "ai-triage-dropdown-" in src
    assert "setShowAiTriage" in src
    # Chevron toggle for affordance
    assert "ChevronDown" in src and "ChevronUp" in src


# ─── 4. IssueDetailPanel — Supplier Ref moved to top ────────────────


def test_supplier_ref_is_above_logged_by():
    src = pathlib.Path(
        "/app/frontend/src/pages/IssueDetailPanel.js"
    ).read_text()
    ref_anchor = "Supplier Reference / Job Number"
    logged_by_anchor = ">Logged by<"
    ref_idx = src.find(ref_anchor)
    logged_idx = src.find(logged_by_anchor)
    assert ref_idx != -1, "Supplier Reference label missing"
    assert logged_idx != -1, "Logged by anchor missing"
    assert ref_idx < logged_idx, "Supplier Reference must render above the Logged-by grid"


def test_supplier_ref_input_still_present():
    """The actual input + save flow must still work after the move."""
    src = pathlib.Path(
        "/app/frontend/src/pages/IssueDetailPanel.js"
    ).read_text()
    assert "supplier-ref-input-" in src
    assert "save-ref-btn-" in src
    assert "handleSaveSupplierRef" in src


# ─── 5. IssueDetailPanel — Quotes card above Purchase Orders ────────


def test_quotes_card_exists_and_above_purchase_orders():
    src = pathlib.Path(
        "/app/frontend/src/pages/IssueDetailPanel.js"
    ).read_text()
    assert 'data-testid={`quotes-section-${issue.id}`}' in src
    # Upload control posts with kind=quote
    assert "handleFileUpload(e, 'quote')" in src
    quotes_idx = src.find("quotes-section-")
    po_idx = src.find("Purchase Orders ({purchaseOrders")
    assert quotes_idx != -1 and po_idx != -1
    assert quotes_idx < po_idx, "Quotes card must render above the Purchase Orders card"


def test_attachments_card_excludes_quote_kind():
    """Don't render quotes twice — generic Attachments now filters them out."""
    src = pathlib.Path(
        "/app/frontend/src/pages/IssueDetailPanel.js"
    ).read_text()
    assert "(a.kind || '').toLowerCase() !== 'quote'" in src


# ─── 6. Fault list rows surface the supplier reference ──────────────


def test_fault_row_shows_supplier_ref_when_populated():
    for path in (
        "/app/frontend/src/pages/Dashboard/FaultsTab.js",
        "/app/frontend/src/pages/LiteDashboard/LiteFaultsTab.js",
    ):
        src = pathlib.Path(path).read_text()
        assert "issue.supplier_ref" in src
        assert "Ref: ${issue.supplier_ref}" in src, f"missing Ref: prefix in {path}"
