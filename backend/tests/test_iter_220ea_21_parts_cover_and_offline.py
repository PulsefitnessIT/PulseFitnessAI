"""Iter 220ea·21 — Stock Phase 3: contract-cover on parts + offline queueing.

Two halves:

1. Pure unit tests for ``routes.svc.parts_cover.classify_part_cover`` —
   the covered/chargeable decision against a contract's inclusion /
   exclusion model. No IO, deterministic.
2. Source-level guards that the engineer-app "part used" callers now
   route through the offline outbox with an idempotency key, that the
   backend stamps cover onto the allocation, and that the invoice draft
   zero-rates covered parts.
"""
from pathlib import Path

from routes.svc.parts_cover import (
    COVER_CATEGORIES,
    classify_part_cover,
    derive_cover_category,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
BACKEND = Path(__file__).resolve().parents[1]


def _active_contract(inclusions=None, exclusions=None):
    return {
        "status": "active",
        "inclusions": {"maintenance": inclusions or []},
        "exclusions_structured": exclusions or [],
    }


# ─────────────────────────── classifier ───────────────────────────

def test_derive_explicit_category_wins():
    assert derive_cover_category({"cover_category": "major", "name": "Treadmill Belt"}) == "major"


def test_derive_heuristic_belt():
    assert derive_cover_category({"name": "Treadmill Running Belt", "sku": "BELT-1"}) == "treadmill_belts"


def test_derive_consumable_beats_deck_for_wax():
    # "Deck Lubricant Wax" must read as a consumable, not a deck part.
    assert derive_cover_category({"name": "Deck Lubricant Wax 1L"}) == "consumable"


def test_derive_default_wear_tear():
    assert derive_cover_category({"name": "Random Widget", "sku": "X1"}) == "wear_tear"


def test_covered_when_inclusion_present():
    c = _active_contract(inclusions=["treadmill_belts", "wear_tear_parts"])
    res = classify_part_cover({"name": "Treadmill Belt", "sku": "B1"}, c)
    assert res["covered"] is True
    assert res["chargeable"] is False
    assert res["cover_category"] == "treadmill_belts"


def test_chargeable_when_inclusion_absent():
    c = _active_contract(inclusions=["wear_tear_parts"])  # no major_parts
    res = classify_part_cover({"name": "Drive Motor 2HP", "sku": "M1"}, c)
    assert res["covered"] is False
    assert res["chargeable"] is True
    assert res["cover_category"] == "major"


def test_exclusion_overrides_inclusion():
    # upholstery is "included" but also explicitly excluded → chargeable.
    c = _active_contract(inclusions=["upholstery"], exclusions=["upholstery_excl"])
    res = classify_part_cover({"name": "Seat Upholstery Cushion", "sku": "U1"}, c)
    assert res["covered"] is False
    assert "exclud" in res["cover_reason"].lower()


def test_no_contract_is_chargeable():
    res = classify_part_cover({"name": "Treadmill Belt"}, None)
    assert res["covered"] is False
    assert res["chargeable"] is True
    assert "no active contract" in res["cover_reason"].lower()


def test_draft_contract_not_active_is_chargeable():
    c = _active_contract(inclusions=["treadmill_belts"])
    c["status"] = "draft"
    res = classify_part_cover({"name": "Treadmill Belt"}, c)
    assert res["covered"] is False


def test_sent_contract_counts_as_active():
    c = _active_contract(inclusions=["treadmill_belts"])
    c["status"] = "sent"
    res = classify_part_cover({"name": "Treadmill Belt"}, c)
    assert res["covered"] is True


def test_every_category_maps_to_inclusion_key():
    for meta in COVER_CATEGORIES.values():
        assert meta["inclusion"]
        assert meta["label"]


# ───────────────────── backend wiring guards ──────────────────────

def test_phase3_stamps_cover_on_use_and_consume():
    src = (BACKEND / "routes" / "svc" / "engineer_phase3.py").read_text()
    assert "from routes.svc.parts_cover import classify_part_cover" in src
    assert "_contract_for_case" in src
    # both the ad-hoc use and the consume path classify cover
    assert src.count("classify_part_cover(") >= 2


def test_invoice_draft_zero_rates_covered_parts():
    src = (BACKEND / "routes" / "svc" / "engineer_phase3.py").read_text()
    assert "covered by contract" in src.lower()
    assert "covered = bool(alloc.get(\"covered\"))" in src


def test_catalogue_cover_category_editable():
    src = (BACKEND / "routes" / "svc" / "parts_catalogue.py").read_text()
    assert "cover_category" in src


# ───────────────────── frontend offline guards ────────────────────

def test_machine_parts_used_uses_outbox_with_idempotency():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "WorkVisitMachinesCard.js").read_text()
    assert "outboxPost" in src
    assert "Idempotency-Key" in src
    assert "newIdemKey" in src
    # offline optimistic chip + cover badge testids
    assert "machine-parts-cover-" in src
    assert "machine-parts-charge-" in src


def test_jobdetail_parts_use_and_consume_route_through_outbox():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerJobDetailV2.js").read_text()
    # both addPartUsage and consume now use the outbox + idempotency
    assert src.count("Idempotency-Key") >= 2
    assert "parts-used-cover-" in src
    assert "parts-used-charge-" in src


def test_import_moved_to_account_settings_stock_section():
    cat = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "PartsCatalogue.js").read_text()
    settings = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerAccountSettings.js").read_text()
    # cover-category select stays on the catalogue edit drawer
    assert "edit-cover-category" in cat
    # import buttons removed from the main catalogue screen
    assert "catalogue-import-btn" not in cat
    assert "catalogue-empty-import-btn" not in cat
    # catalogue auto-opens the wizard only when arriving from settings
    assert "import" in cat and "can_manage" in cat
    # import now lives in Account Settings → Stock
    assert "engineer-settings-section-stock" in settings
    assert "engineer-settings-parts-import-row" in settings
    assert "engineer-settings-catalogue-row" in settings


def test_text_white_preserved_on_slate_dark_buttons():
    # Root-cause fix for the "black button" bug: slate-900/800 dark
    # buttons must keep white text in the light theme.
    css = (FRONTEND / "index.css").read_text()
    assert ".bg-slate-900.text-white" in css
    assert ".bg-slate-800.text-white" in css
