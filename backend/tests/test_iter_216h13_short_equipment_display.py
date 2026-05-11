"""
Iter 216h13 — Short equipment-row display for invoice imports.

Operator reported (with screenshots): rows imported from a Pulse
Fitness invoice were rendering with the full 200-char marketing line
("Premium StepMill with 18.5\\" (Cirrus V4) Touchscreen Console,
Apple/Samsung Watch Connectivity, …") as BOTH the equipment name AND
model. That blew the layout out of the row.

Expected shape (matches the rest of the GymAxis equipment list):
  - name          → short subtype noun ('Treadmill', 'StepMill', 'Upright Cycle')
  - manufacturer  → 'Pulse Fitness'
  - model         → short stock code ('260G', '200H-AAF')
  - description   → full marketing line (preserved for search)

Pins:
  1. `_short_equipment_name` picks the AI-extracted `equipment_name`
     when present and ≤ 40 chars, otherwise derives a heuristic from
     the description.
  2. `_short_model_code` prefers `stock_item_code` over `model`.
  3. `_build_equipment_doc` produces the new short shape AND keeps the
     full description in both `notes` and the dedicated `description`
     field.
"""
from __future__ import annotations

from routes.equipment_import import (
    _build_equipment_doc,
    _short_equipment_name,
    _short_model_code,
)

LONG_PULSE_DESCRIPTION = (
    "Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, "
    "Apple/Samsung Watch Connectivity, Content Mirroring & Wireless "
    "Charging in Sand Black (TRAKK Compatible)(110V/220V)"
)


def test_short_name_prefers_ai_extracted_equipment_name():
    eq = {"equipment_name": "Treadmill", "description": LONG_PULSE_DESCRIPTION}
    assert _short_equipment_name(eq) == "Treadmill"


def test_short_name_falls_back_to_description_heuristic_for_stepmill():
    eq = {"description": LONG_PULSE_DESCRIPTION}
    assert _short_equipment_name(eq) == "StepMill"


def test_short_name_recognises_upright_cycle():
    eq = {"description": "Club Line Upright Cycle with 10.1\" Tactile Key Console"}
    assert _short_equipment_name(eq) == "Upright Cycle"


def test_short_name_recognises_recumbent_cycle():
    eq = {"description": "Club Line Recumbent Cycle with 10.1\" Tactile Key Console"}
    assert _short_equipment_name(eq) == "Recumbent Cycle"


def test_short_name_rejects_long_ai_name_and_falls_back():
    """If the AI returns a 200-char string as `equipment_name`, we
    refuse it and use the heuristic instead."""
    eq = {"equipment_name": LONG_PULSE_DESCRIPTION, "description": LONG_PULSE_DESCRIPTION}
    out = _short_equipment_name(eq)
    assert out == "StepMill"
    assert len(out) <= 40


def test_short_name_last_resort_uses_category():
    eq = {"equipment_category": "Cardiovascular"}
    assert _short_equipment_name(eq) == "Cardiovascular"


def test_short_name_default_when_nothing_known():
    assert _short_equipment_name({}) == "Equipment"


def test_short_model_prefers_stock_item_code():
    eq = {"stock_item_code": "260G", "model": "Some long marketing line"}
    assert _short_model_code(eq) == "260G"


def test_short_model_falls_back_to_short_model_field():
    eq = {"model": "AAF-200"}
    assert _short_model_code(eq) == "AAF-200"


def test_short_model_returns_empty_for_long_model_string():
    """We refuse to use a 200-char marketing line as a 'model' code."""
    eq = {"model": LONG_PULSE_DESCRIPTION}
    assert _short_model_code(eq) == ""


def test_build_equipment_doc_uses_short_name_and_model():
    """End-to-end: the AI returns a long description + short stock
    code, and we end up with a clean row."""
    eq = {
        "make": "Pulse Fitness",
        "equipment_name": "StepMill",
        "model": "200H-AAF",
        "stock_item_code": "200H-AAF",
        "description": LONG_PULSE_DESCRIPTION,
        "equipment_category": "Cardiovascular",
        "serial_number": "PF-9001",
        "install_date": "18/11/2025",
    }
    ctx = {
        "target_user_id": "u-1", "target_org_id": "org-1",
        "supplier": "Pulse Fitness", "account_ref": "00000841",
        "invoice_number": "0000022528", "default_location": "Main Gym",
        "import_id": "imp-1", "batch_id": "",
    }
    doc = _build_equipment_doc(eq, ctx)
    assert doc["name"] == "StepMill"
    assert doc["model"] == "200H-AAF"
    assert doc["manufacturer"] == "Pulse Fitness"
    assert doc["serial_number"] == "PF-9001"
    # Full description is preserved for search
    assert doc["description"] == LONG_PULSE_DESCRIPTION
    assert LONG_PULSE_DESCRIPTION in doc["notes"]
    # No marketing line leaked into the short display fields
    assert "Touchscreen" not in doc["name"]
    assert "Touchscreen" not in doc["model"]


def test_build_equipment_doc_handles_missing_equipment_name():
    """When the AI didn't return `equipment_name`, the heuristic must
    still produce a usable short row."""
    eq = {
        "make": "Pulse Fitness",
        "model": LONG_PULSE_DESCRIPTION,  # AI bug: long line in `model`
        "stock_item_code": "260G",
        "description": LONG_PULSE_DESCRIPTION,
        "equipment_category": "Cardiovascular",
        "serial_number": "",
        "install_date": "",
    }
    ctx = {
        "target_user_id": "u-1", "target_org_id": "org-1",
        "supplier": "Pulse Fitness", "account_ref": "",
        "invoice_number": "0000022528", "default_location": "Main Gym",
        "import_id": "imp-1", "batch_id": "",
    }
    doc = _build_equipment_doc(eq, ctx)
    assert doc["name"] == "StepMill"
    assert doc["model"] == "260G"
    assert len(doc["name"]) <= 40
    assert len(doc["model"]) <= 24


def test_build_equipment_doc_does_not_duplicate_short_value_in_notes():
    """If name and description are identical (both 'Treadmill'), we
    don't append the description to the notes — keeps notes clean."""
    eq = {
        "equipment_name": "Treadmill",
        "description": "Treadmill",
        "model": "260G", "stock_item_code": "260G",
        "make": "Pulse Fitness",
    }
    ctx = {
        "target_user_id": "u-1", "target_org_id": "org-1",
        "supplier": "Pulse Fitness", "account_ref": "",
        "invoice_number": "0000022528", "default_location": "",
        "import_id": "imp-1", "batch_id": "",
    }
    doc = _build_equipment_doc(eq, ctx)
    # Notes only contains the "Imported from invoice" stub, no duplication
    assert doc["notes"] == "Imported from invoice 0000022528"
