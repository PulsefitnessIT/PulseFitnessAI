"""Iter 220ea·21 — Stock Phase 3 · Contract-cover logic on parts.

Pure (no-IO) classifier that decides whether a part used on a job is
**covered by the linked service contract** (free to the customer) or
**chargeable**. It reuses the canonical contract cover model in
``crm_contract_templates`` (``inclusions.maintenance`` keys +
``exclusions_structured``) — no duplicate cover taxonomy.

A part is mapped to a *cover category* either explicitly (the catalogue
``cover_category`` field) or heuristically from its name / category /
SKU. Each cover category points at one contract inclusion key and an
optional set of exclusion keys that override it.

This module is import-only (no router); it is consumed by
``engineer_phase3.py`` when a part is used / consumed and by the invoice
draft builder so covered parts land at £0.
"""
from __future__ import annotations

# cover_category -> {inclusion key on contract, plain label, exclusion keys}
COVER_CATEGORIES: dict[str, dict] = {
    "treadmill_belts": {"inclusion": "treadmill_belts", "label": "Treadmill belt",  "exclusions": []},
    "treadmill_beds":  {"inclusion": "treadmill_beds",  "label": "Treadmill bed/deck", "exclusions": ["beds_excl"]},
    "upholstery":      {"inclusion": "upholstery",      "label": "Upholstery",      "exclusions": ["upholstery_excl"]},
    "consumable":      {"inclusion": "wear_tear_parts", "label": "Consumable",      "exclusions": []},
    "wear_tear":       {"inclusion": "wear_tear_parts", "label": "Wear & tear part", "exclusions": []},
    "major":           {"inclusion": "major_parts",     "label": "Major part",      "exclusions": []},
}

# Ordered keyword rules — first match wins. Tuned for gym equipment.
# Consumables (wax/lubricant/cleaner) are checked first so e.g.
# "Deck Lubricant Wax" maps to consumable, not the treadmill deck.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("consumable",      ("lubric", "wax", "clean", "consumable", "grease", "silicone", "wd40", "wd-40", "spray")),
    ("treadmill_belts", ("belt",)),
    ("treadmill_beds",  ("deck", "running bed", "tread bed", "deck board")),
    ("upholstery",      ("uphol", "cushion", "seat pad", "vinyl", "grip pad", "pad set")),
    ("major",           ("motor", "console", "pcb", "circuit", "board", "drive", "controller",
                         "inverter", "display", "incline", "actuator", "transformer")),
]

_ACTIVE_CONTRACT_STATUSES = {"active", "sent"}


def derive_cover_category(part: dict | None) -> str:
    """Return the cover category for a part — explicit field if set and
    valid, otherwise a keyword heuristic, defaulting to ``wear_tear``."""
    part = part or {}
    explicit = (part.get("cover_category") or "").strip().lower()
    if explicit in COVER_CATEGORIES:
        return explicit
    text = " ".join(
        str(part.get(k) or "") for k in ("name", "category", "mfr_part_number", "sku")
    ).lower()
    for cat, keywords in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            return cat
    return "wear_tear"


def classify_part_cover(part: dict | None, contract: dict | None) -> dict:
    """Classify a part as covered/chargeable against a contract.

    Returns a flat, persistable shape stamped onto the allocation:
        {cover_category, cover_label, covered, chargeable, cover_reason}
    """
    category = derive_cover_category(part)
    meta = COVER_CATEGORIES[category]
    label = meta["label"]

    base = {"cover_category": category, "cover_label": label}

    if not contract or (contract.get("status") or "") not in _ACTIVE_CONTRACT_STATUSES:
        return {**base, "covered": False, "chargeable": True,
                "cover_reason": "No active contract on this job — chargeable"}

    inclusions = (contract.get("inclusions") or {}).get("maintenance") or []
    exclusions = contract.get("exclusions_structured") or []

    # An explicit exclusion always overrides an inclusion.
    if any(e in exclusions for e in meta["exclusions"]):
        return {**base, "covered": False, "chargeable": True,
                "cover_reason": f"{label} excluded by contract — chargeable"}

    if meta["inclusion"] in inclusions:
        return {**base, "covered": True, "chargeable": False,
                "cover_reason": f"Covered by contract — {label.lower()}"}

    return {**base, "covered": False, "chargeable": True,
            "cover_reason": f"{label} not in contract cover — chargeable"}


__all__ = ["COVER_CATEGORIES", "derive_cover_category", "classify_part_cover"]
