"""Pre-defined fault code taxonomy for gym-equipment fault reporting.

Each fault has an assignable code that powers trend analysis and poor-performing-part
reporting. Codes are grouped by category for UI display (grouped dropdown / analytics
breakdowns).
"""
from typing import Any

# Each code: (code, label, description shown in tooltip)
FAULT_CODE_CATEGORIES: list[dict[str, Any]] = [
    {
        "category": "mechanical",
        "label": "Mechanical",
        "codes": [
            ("BEL-01", "Belt slipping / worn",         "Running or drive belt has lost grip or shows wear"),
            ("BEL-02", "Belt torn / broken",           "Running or drive belt has failed and needs replacement"),
            ("BRG-01", "Bearing noise",                "Audible squeak / grind from a bearing"),
            ("BRG-02", "Bearing seizure",              "Bearing has locked up; part will not rotate"),
            ("CAB-01", "Cable frayed",                 "Resistance or selector cable has visible wear strands"),
            ("CAB-02", "Cable snapped",                "Resistance or selector cable has fully failed"),
            ("PUL-01", "Pulley damage",                "Pulley wheel cracked, chipped, or misaligned"),
            ("CHN-01", "Chain worn / stretched",       "Drive chain has elongated or shows link wear"),
            ("ROL-01", "Roller worn / cracked",        "Treadmill roller surface damaged"),
        ],
    },
    {
        "category": "electrical",
        "label": "Electrical",
        "codes": [
            ("ELC-01", "Console not powering on",      "Main display dead — check supply, fuse, PCB"),
            ("ELC-02", "Display / screen fault",       "Screen lit but showing garbled output or errors"),
            ("ELC-03", "Wiring loose / damaged",       "Visible cabling issue between components"),
            ("ELC-04", "Sensor malfunction",           "HR, speed, incline, or position sensor misreading"),
            ("MOT-01", "Motor noise / grinding",       "Audible abnormality from the drive motor"),
            ("MOT-02", "Motor not running",            "Motor does not engage on start"),
            ("MOT-03", "Motor overheating",            "Thermal cut-out triggered or case very hot"),
            ("INV-01", "Inverter / drive fault",       "Variable-speed drive error code or trip"),
        ],
    },
    {
        "category": "hydraulic",
        "label": "Hydraulic / Pneumatic",
        "codes": [
            ("HYD-01", "Hydraulic leak",               "Fluid leak observed at seal or hose"),
            ("HYD-02", "Loss of resistance",           "Piston no longer provides expected load"),
            ("PNE-01", "Air-cylinder leak",            "Pneumatic cylinder leaking or losing pressure"),
        ],
    },
    {
        "category": "structural",
        "label": "Structural / Frame",
        "codes": [
            ("FRM-01", "Frame crack",                  "Visible crack in a main frame member"),
            ("FRM-02", "Weld failure",                 "Weld has cracked or separated"),
            ("FRM-03", "Loose fasteners",              "Bolts or screws backed out under load"),
            ("PAD-01", "Upholstery torn / worn",       "Seat or bench pad needs recovering"),
            ("PAD-02", "Handle grip deteriorated",     "Rubber / foam grip has split or fallen off"),
        ],
    },
    {
        "category": "weight_stack",
        "label": "Weight Stack / Strength",
        "codes": [
            ("WGT-01", "Pin stuck",                    "Weight selector pin will not insert or release"),
            ("WGT-02", "Weight plate damage",          "Plate cracked, chipped, or missing"),
            ("WGT-03", "Selector malfunction",         "Electronic or magnetic selector not tracking"),
            ("WGT-04", "Stack guide rails worn",       "Stack travels unevenly or noisily"),
        ],
    },
    {
        "category": "safety",
        "label": "Safety-Critical",
        "codes": [
            ("SAF-01", "Emergency stop not functioning", "E-stop button does not cut power"),
            ("SAF-02", "Safety lock / latch broken",   "Rack catch, spin-bike pop-pin, or similar failed"),
            ("SAF-03", "Guard / cover missing",        "Belt cover, flywheel guard, or shroud absent"),
            ("SAF-04", "Tether / clip malfunction",    "Treadmill safety key or lanyard does not trigger stop"),
        ],
    },
    {
        "category": "software",
        "label": "Software / Firmware",
        "codes": [
            ("SFW-01", "Firmware error / crash",       "Console reports error code or reboots"),
            ("SFW-02", "Connectivity issue",           "Wi-Fi, Bluetooth, or ANT+ not connecting"),
            ("SFW-03", "App integration broken",       "Zwift / Peloton / partner app pairing failed"),
        ],
    },
    {
        "category": "wear",
        "label": "Wear & Consumables",
        "codes": [
            ("WR-01",  "Lubrication needed",           "Routine belt / deck / chain lubrication due"),
            ("WR-02",  "Cleaning required",            "Cosmetic clean or deep-clean needed"),
            ("WR-03",  "Routine adjustment",           "Tension, alignment, or calibration re-adjust"),
        ],
    },
    {
        "category": "other",
        "label": "Other",
        "codes": [
            ("OTH-01", "Cosmetic damage",              "Paint, sticker, or non-functional mark"),
            ("OTH-02", "Unknown / to be assessed",     "Fault confirmed but root cause not yet determined"),
        ],
    },
]


# Flat lookup: code -> label (used for enrichment + validation)
def _build_flat_map() -> dict[str, str]:
    flat = {}
    for cat in FAULT_CODE_CATEGORIES:
        for code, label, _desc in cat["codes"]:
            flat[code] = label
    return flat


FAULT_CODE_LABELS: dict[str, str] = _build_flat_map()
VALID_FAULT_CODES: set[str] = set(FAULT_CODE_LABELS.keys())


def fault_code_category(code: str) -> str | None:
    """Return the category slug for a given code, or None if unknown."""
    for cat in FAULT_CODE_CATEGORIES:
        if any(c == code for c, _l, _d in cat["codes"]):
            return cat["category"]
    return None
