"""Canonical MOD PTE Service & Repair Schedule of Rates (SOR) rate card.

Source: `04 - LSLDC0223 - Schedule B to T&C's - The Supply of PTE Service and
Repair SOR.xlsx`. These are the *contracted* framework prices and must not be
altered per-quote (Type A / Type B are fixed). Only Type C (Overseas), Repairs
and Refurbishment are POA (Price On Application) — those allow a custom price
line on the quote.

Each entry carries a Type A (all-inclusive 12-month service, per item / year)
price and a Type B (ad-hoc call-out visit) price, plus optional Year 2/3/4
override prices (nullable — the admin can set these at pricing anniversaries;
they fall back to Year 1 when unset). `match_keywords` drive the automatic
mapping of a site's equipment onto the correct SOR line.
"""
from __future__ import annotations

CURRENCY = "GBP"

# item_no, code_a, code_b, sicon_a, sicon_b, equipment_type, variant,
# type_a_price, type_b_price, keywords
_SERVICE_LINES = [
    ("2", "2A", "2B", "PAT SER100135", "PAT SER100136", "Treadmill", "standard", 56.73, 16.0,
     ["treadmill", "running machine", "95t", "tread"]),
    ("3", "3A", "3B", "PAT SER100127", "PAT SER100128", "Spinning Bikes", "standard", 72.56, 16.0,
     ["spin", "spinning", "group cycle", "indoor cycle", "studio bike", "ic bike"]),
    ("4", "4A", "4B", "PAT SER100123", "PAT SER100124", "Rowing Machine", "standard", 43.53, 7.0,
     ["rowing machine", "rower", "row erg", "concept2", "concept 2"]),
    ("5", "5A", "5B", "PAT SER100078", "PAT SER100079", "Benches", "standard", 157.20, 24.0,
     ["bench", "flat bench", "adjustable bench", "weight bench"]),
    ("6", "6A", "6B", "PAT SER100081", "PAT SER100082", "Cardio Wave", "standard", 157.20, 24.0,
     ["cardio wave", "wave"]),
    ("7", "7A", "7B", "PAT SER100083", "PAT SER100084", "Climbers", "standard", 157.20, 24.0,
     ["climber", "climbing", "vertical climber", "jacobs ladder", "maxi climber"]),
    ("8", "8A", "8B", "PAT SER100085", "PAT SER100086", "Cross Trainer", "non_powered", 157.20, 24.0,
     ["cross trainer", "cross-trainer", "crosstrainer", "elliptical", "x-trainer"]),
    ("9", "9A", "9B", "PAT SER100087", "PAT SER100088", "Cross Trainer", "powered", 157.20, 24.0,
     ["cross trainer powered", "powered cross trainer", "powered elliptical"]),
    ("10", "10A", "10B", "PAT SER100089", "PAT SER100090", "Grappler", "standard", 120.93, 24.0,
     ["grappler"]),
    ("11", "11A", "11B", "PAT SER100091", "PAT SER100092", "Hand Bike", "standard", 133.02, 16.0,
     ["hand bike", "handbike", "arm bike", "arm ergometer", "upper body ergometer", "ube"]),
    ("12", "12A", "12B", "PAT SER100117", "PAT SER100118", "Recumbent Bike", "non_powered", 157.20, 16.0,
     ["recumbent", "recumbent bike"]),
    ("13", "13A", "13B", "PAT SER100119", "PAT SER100120", "Recumbent Bike", "powered", 157.20, 16.0,
     ["recumbent powered", "powered recumbent"]),
    ("14", "14A", "14B", "PAT SER100121", "PAT SER100122", "Rowers", "powered", 72.56, 16.0,
     ["powered rower", "water rower", "air rower powered", "dynamic rower"]),
    ("15", "15A", "15B", "PAT SER100129", "PAT SER100130", "Squat Rack", "standard", 97.50, 10.0,
     ["squat rack", "power rack", "squat stand", "rack"]),
    ("16", "16A", "16B", "PAT SER100131", "PAT SER100132", "Stepper", "non_powered", 157.20, 24.0,
     ["stepper", "step machine", "step mill"]),
    ("17", "17A", "17B", "PAT SER100133", "PAT SER100134", "Steppers", "powered", 157.20, 16.0,
     ["stepper powered", "powered stepper", "stairmaster", "stair climber"]),
    ("18", "18A", "18B", "PAT SER100137", "PAT SER100138", "Upright Bike", "non_powered", 145.12, 21.0,
     ["upright bike", "exercise bike", "cycle", "bike", "cardio bike"]),
    ("19", "19A", "19B", "PAT SER100139", "PAT SER100140", "Upright Bike", "powered", 145.12, 21.0,
     ["upright bike powered", "powered bike", "self powered bike"]),
    ("20", "20A", "20B", "PAT SER100125", "PAT SER100126", "SingleStation Strength Machine", "standard", 145.12, 21.0,
     ["single station", "strength machine", "leg press", "chest press", "lat pulldown",
      "cable machine", "selectorised", "pin loaded", "leg extension", "leg curl", "strength"]),
    ("21", "21A", "21B", "PAT SER100093", "PAT SER100094", "Multi Station Bodylift", "standard", 207.50, 24.0,
     ["bodylift", "body lift"]),
    ("22", "22A", "22B", "PAT SER100095", "PAT SER100096", "Multi Station Chin & Dips", "standard", 145.12, 24.0,
     ["chin", "dip", "chin and dips", "chin & dips", "chin dip"]),
    ("23", "23A", "23B", "PAT SER100101", "PAT SER100102", "Multigym", "2_station", 145.12, 24.0,
     ["multigym 2", "2 station", "two station", "multi gym 2"]),
    ("24", "24A", "24B", "PAT SER100103", "PAT SER100104", "Multigym", "3_station", 145.12, 21.0,
     ["multigym 3", "3 station", "three station", "multi gym 3"]),
    ("25", "25A", "25B", "PAT SER100585", "PAT SER100582", "Multigym", "3plus_station", 145.12, 21.0,
     ["multigym 3+", "3+ station", "multi station", "multigym", "multi gym", "functional trainer",
      "cable crossover", "jungle gym"]),
    ("26", "26A", "26B", "PAT SER100583", "PAT SER100584", "Freedom Trainer", "standard", 207.50, 24.0,
     ["freedom trainer", "functional", "free motion", "freemotion", "dual adjustable pulley", "dap"]),
    ("27", "27A", "27B", "PAT SER100115", "PAT SER100116", "Radiant Trainer", "standard", 145.12, 24.0,
     ["radiant trainer", "radiant"]),
]

# Special / non-equipment lines.
_SPECIAL_LINES = [
    {
        "item_no": "1", "code": "1B", "sicon_ref": "PAT SER100080",
        "kind": "call_out", "equipment_type": "Call Out Charge (Type B / UK Only)",
        "variant": "standard", "type_a_price": None, "type_b_price": 80.0,
        "is_poa": False, "allow_custom_price": False, "keywords": [],
    },
    {
        "item_no": "28", "code": "28C", "sicon_ref": "PAT SER100143",
        "kind": "poa", "equipment_type": "Overseas Service (Type C)",
        "variant": "standard", "type_a_price": None, "type_b_price": None,
        "is_poa": True, "allow_custom_price": True, "keywords": [],
    },
    {
        "item_no": "29", "code": "29REP", "sicon_ref": "PAT SER100141",
        "kind": "poa", "equipment_type": "Repairs (Quote Required)",
        "variant": "standard", "type_a_price": None, "type_b_price": None,
        "is_poa": True, "allow_custom_price": True, "keywords": [],
    },
    {
        "item_no": "30", "code": "30REF", "sicon_ref": "PAT SER100142",
        "kind": "poa", "equipment_type": "Refurbishment (User/Supplier Defined)",
        "variant": "standard", "type_a_price": None, "type_b_price": None,
        "is_poa": True, "allow_custom_price": True, "keywords": [],
    },
]

_VARIANT_LABEL = {
    "standard": "", "powered": "Powered", "non_powered": "Non-Powered",
    "2_station": "2 Station", "3_station": "3 Station", "3plus_station": "3+ Station",
}


def variant_label(variant: str) -> str:
    return _VARIANT_LABEL.get(variant, variant.replace("_", " ").title())


def build_seed_rate_card() -> list[dict]:
    """Return the full rate card as documents ready to insert into Mongo."""
    docs: list[dict] = []
    for (item_no, code_a, code_b, sicon_a, sicon_b, etype, variant,
         a_price, b_price, keywords) in _SERVICE_LINES:
        label = etype + (f" — {variant_label(variant)}" if variant_label(variant) else "")
        docs.append({
            "id": f"sor-{item_no}",
            "item_no": item_no,
            "kind": "service",
            "equipment_type": etype,
            "variant": variant,
            "label": label,
            "code_a": code_a, "code_b": code_b,
            "sicon_ref_a": sicon_a, "sicon_ref_b": sicon_b,
            "currency": CURRENCY,
            "type_a_price": a_price,
            "type_b_price": b_price,
            # Year 2/3/4 overrides (pricing anniversaries) — null falls back to Y1.
            "type_a_price_y2": None, "type_a_price_y3": None, "type_a_price_y4": None,
            "type_b_price_y2": None, "type_b_price_y3": None, "type_b_price_y4": None,
            "is_poa": False,
            "allow_custom_price": False,
            "match_keywords": keywords,
            "sort_order": int(item_no),
        })
    for s in _SPECIAL_LINES:
        docs.append({
            "id": f"sor-{s['item_no']}",
            "item_no": s["item_no"],
            "kind": s["kind"],
            "equipment_type": s["equipment_type"],
            "variant": s["variant"],
            "label": s["equipment_type"],
            "code_a": s.get("code"), "code_b": s.get("code"),
            "sicon_ref_a": s["sicon_ref"], "sicon_ref_b": s["sicon_ref"],
            "currency": CURRENCY,
            "type_a_price": s["type_a_price"],
            "type_b_price": s["type_b_price"],
            "type_a_price_y2": None, "type_a_price_y3": None, "type_a_price_y4": None,
            "type_b_price_y2": None, "type_b_price_y3": None, "type_b_price_y4": None,
            "is_poa": s["is_poa"],
            "allow_custom_price": s["allow_custom_price"],
            "match_keywords": s["keywords"],
            "sort_order": int(s["item_no"]),
        })
    return docs


def price_for(entry: dict, contract_type: str, year: int = 1) -> float | None:
    """Resolve the contracted price for a rate-card entry, contract type and
    year (falling back to Year 1 when a later-year override is unset)."""
    ct = (contract_type or "A").upper()
    base_key = "type_a_price" if ct == "A" else "type_b_price"
    base = entry.get(base_key)
    if year and year > 1:
        yr_key = f"{base_key}_y{year}"
        if entry.get(yr_key) is not None:
            return entry.get(yr_key)
    return base


def _tokens(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


def match_equipment(equip: dict, rate_card: list[dict], contract_type: str = "A") -> dict:
    """Best-effort map a single equipment doc onto a service rate-card line.

    Returns { rate_card_id, matched (bool), confidence (0-1),
    suggestions: [ {rate_card_id, label, score} ] }.
    """
    hay = _tokens(equip.get("equipment_type", ""), equip.get("name", ""),
                  equip.get("model", ""), equip.get("brand", ""),
                  equip.get("category", ""))
    powered_hint = "powered" in hay and "non" not in hay.split("powered")[0][-6:]
    scored: list[tuple[float, dict]] = []
    for entry in rate_card:
        if entry.get("kind") != "service":
            continue
        score = 0.0
        for kw in entry.get("match_keywords", []):
            if kw in hay:
                # Longer / more specific keywords score higher.
                score = max(score, 0.4 + min(len(kw), 24) / 40.0)
        # Nudge variant selection using powered/non-powered hints.
        if score > 0:
            if entry["variant"] == "powered" and powered_hint:
                score += 0.15
            if entry["variant"] == "non_powered" and not powered_hint:
                score += 0.08
        if score > 0:
            scored.append((round(min(score, 0.99), 3), entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    suggestions = [
        {"rate_card_id": e["id"], "label": e["label"], "score": s}
        for s, e in scored[:4]
    ]
    if scored:
        best_score, best = scored[0]
        return {
            "rate_card_id": best["id"],
            "matched": best_score >= 0.5,
            "confidence": best_score,
            "suggestions": suggestions,
        }
    return {"rate_card_id": None, "matched": False, "confidence": 0.0, "suggestions": []}



# ── MOD-code → SOR service line ─────────────────────────────────────
# Pulse kit lists / lease plans carry a "MOD Code" column (e.g. MOD-UBIKE,
# MOD-STRENGTH) that deterministically identifies the SOR service line. When
# present it should be trusted over fuzzy description matching — otherwise a
# strength "Row" gets mis-read as a CV rower, etc.
MOD_CODE_TO_ITEM_NO: dict[str, str] = {
    "MOD-TREAD": "2",
    "MOD-SPIN": "3",
    "MOD-ROW": "4",
    "MOD-BENCH": "5",
    "MOD-CARDIOWAVE": "6",
    "MOD-WAVE": "6",
    "MOD-CLIMBER": "7",
    "MOD-XT": "8",
    "MOD-XTP": "9",
    "MOD-GRAPPLER": "10",
    "MOD-HANDBIKE": "11",
    "MOD-RBIKE": "12",
    "MOD-RBIKEP": "13",
    "MOD-SQUAT": "15",
    "MOD-STEPPER": "16",
    "MOD-STEPPERP": "17",
    "MOD-UBIKE": "18",
    "MOD-UBIKEP": "19",
    "MOD-STRENGTH": "20",
    "MOD-BODYLIFT": "21",
    "MOD-CHINDIP": "22",
    "MOD-MULTI2": "23",
    "MOD-MULTI3": "24",
    "MOD-MULTI": "25",
    "MOD-FREEDOM": "26",
    "MOD-RADIANT": "27",
    # Human-friendly aliases people type on kit lists / import templates so
    # "zero manual matching" holds even when the code isn't the canonical key.
    "MOD-TREADMILL": "2", "MOD-RUN": "2",
    "MOD-SPINNING": "3", "MOD-SPINBIKE": "3", "MOD-CYCLE": "3", "MOD-GROUPCYCLE": "3",
    "MOD-ROWING": "4", "MOD-ROWER": "4",
    "MOD-BENCHES": "5",
    "MOD-CLIMBERS": "7", "MOD-CLIMB": "7",
    "MOD-CROSSTRAINER": "8", "MOD-CROSS": "8", "MOD-ELLIPTICAL": "8",
    "MOD-CROSSTRAINERP": "9",
    "MOD-RECUMBENT": "12", "MOD-RECUMBENTBIKE": "12", "MOD-RBIKE-NP": "12",
    "MOD-SQUATRACK": "15", "MOD-RACK": "15",
    "MOD-STEP": "16", "MOD-STEPPERS": "16",
    "MOD-BIKE": "18", "MOD-UPRIGHT": "18", "MOD-UPRIGHTBIKE": "18", "MOD-UBIKE-NP": "18",
    "MOD-STRENGTHMACHINE": "20", "MOD-SINGLESTATION": "20",
    "MOD-MULTI3PLUS": "25", "MOD-MULTISTATION": "25",
}


def normalise_mod_code(v) -> str:
    """Uppercase, strip whitespace, and ensure a leading 'MOD-' so lookups are
    tolerant of 'MOD-Spin', ' mod ubike ', 'MOD UBIKE' etc."""
    import re as _re
    s = _re.sub(r"\s+", "", str(v or "")).upper()
    if not s:
        return ""
    if not s.startswith("MOD-"):
        s = _re.sub(r"^MOD", "MOD-", s) if s.startswith("MOD") else "MOD-" + s
    return s


def match_by_mod_code(mod_code, rate_card: list[dict]) -> dict | None:
    """Return the rate-card service line for a MOD code, or None."""
    item_no = MOD_CODE_TO_ITEM_NO.get(normalise_mod_code(mod_code))
    if not item_no:
        return None
    return next((e for e in rate_card
                 if e.get("kind") == "service" and str(e.get("item_no")) == item_no), None)
