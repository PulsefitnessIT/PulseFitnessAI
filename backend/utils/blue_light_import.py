"""
Blue Light onboarding import — spreadsheet parsing + normalisation.

Turns a customer equipment spreadsheet (the "Kenya import" column format, plus
common variants) into normalised station/asset rows ready for validation and
bulk creation. Supports CSV, XLSX (every worksheet — a tab name is used as the
station when there is no location column) and pasted TSV/CSV text.

Pure/stateless: no DB access here. The route layer does validation + writes.
"""
from io import BytesIO, StringIO
import re
import pandas as pd

# Canonical field -> set of accepted header aliases (compared after canon()).
HEADER_ALIASES = {
    "station_name":   {"location", "site", "sitename", "station", "stationname",
                        "gym", "gymname", "base", "camp", "building", "facility"},
    "sub_location":   {"sublocation", "zone", "area", "room", "floor", "space"},
    "equipment_type": {"equipmenttype", "type", "assettype", "equipment"},
    "category":       {"category", "class", "classification"},
    "manufacturer":   {"manufacturer", "make", "brand"},
    "model":          {"model", "modelcode", "modelnumber", "modelname"},
    "serial_number":  {"serialnumber", "serial", "serialno", "frameserialnumber",
                        "frameserial", "sn"},
    "console_serial": {"consoleserialnumber", "consoleserial"},
    "asset_number":   {"assetnumber", "servicesportassetnumber", "assetno",
                        "assettag", "assetid", "assetref"},
    "mod_code":       {"modcode", "mod"},
    "warranty_end":   {"warrantyexpiry", "warrantyend", "warranty",
                        "warrantyexpirydate", "warrantyexp"},
    "asset_name":     {"name", "assetname", "description", "itemname"},
    "notes":          {"notes", "note", "comments", "comment", "remarks"},
    "quantity":       {"quantity", "qty", "count"},
}

# Columns exposed in the downloadable template (Kenya import order).
TEMPLATE_COLUMNS = [
    "name", "equipment_type", "manufacturer", "model", "serial_number",
    "asset_number", "mod_code", "quantity", "location", "sub_location",
    "warranty_expiry", "notes",
]

TEMPLATE_SAMPLE_ROWS = [
    ["", "TREADMILL", "TECHNOGYM", "RUN 600", "DEK6EL19000057", "", "MOD-TREAD",
     "1", "Exeter Fire Station", "Gym", "22/09/2026", ""],
    ["", "BIKE - (UPRIGHT)", "WATTBIKE", "TRAINER", "22032574", "", "MOD-UBIKEP",
     "1", "Exeter Fire Station", "Gym", "22/09/2026", ""],
    ["", "ROWER", "CONCEPT 2", "D2", "430797643", "", "MOD-ROW",
     "1", "Bruton Fire Station", "", "22/09/2026", ""],
]

_BLANK_SERIALS = {"", "na", "n/a", "none", "nil", "-", "--", "tbc", "unknown", "n\\a"}


def canon(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").strip().lower())


def _map_columns(columns):
    """Map DataFrame column labels -> canonical field names."""
    mapping = {}
    for col in columns:
        ck = canon(col)
        if not ck:
            continue
        for field, aliases in HEADER_ALIASES.items():
            if ck in aliases and field not in mapping.values():
                mapping[col] = field
                break
    return mapping


# Fields offered in the manual column-mapping dropdown (UI order). MOD code is
# intentionally excluded — not needed for Blue Light services — but still parsed
# automatically if a column matches its aliases.
FIELD_LABELS = {
    "station_name": "Station / Location",
    "sub_location": "Sub-location",
    "equipment_type": "Equipment type",
    "manufacturer": "Manufacturer",
    "model": "Model",
    "serial_number": "Serial number",
    "asset_number": "Asset number",
    "warranty_end": "Warranty expiry",
    "asset_name": "Name",
    "notes": "Notes",
}


def _auto_field(header) -> str:
    """Best auto-detected field for a single header, or '' if none."""
    ck = canon(header)
    if not ck:
        return ""
    for field, aliases in HEADER_ALIASES.items():
        if ck in aliases:
            return field
    return ""


def signature(headers) -> str:
    """Stable fingerprint of a spreadsheet layout (sorted, canonicalised headers)."""
    return "|".join(sorted({canon(h) for h in headers if canon(h)}))


def _all_headers(frames):
    seen, s = [], set()
    for df in frames.values():
        if df is None or df.empty:
            continue
        for c in df.columns:
            key = str(c)
            if canon(key) and key not in s:
                s.add(key)
                seen.append(key)
    return seen


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none"):
        return ""
    return s


def parse_date(v) -> str:
    """Best-effort date -> ISO YYYY-MM-DD. Handles DD/MM/YYYY, YYYY-MM-DD, etc."""
    s = _clean(v)
    if not s:
        return ""
    s = s.split(" ")[0]
    for sep in ("/", "-", "."):
        if sep in s:
            parts = s.split(sep)
            if len(parts) == 3:
                a, b, cc = [p.strip() for p in parts]
                try:
                    if len(a) == 4:                 # YYYY-MM-DD
                        y, m, d = int(a), int(b), int(cc)
                    else:                           # DD/MM/YYYY (UK)
                        d, m, y = int(a), int(b), int(cc)
                        if y < 100:
                            y += 2000
                    if 1 <= m <= 12 and 1 <= d <= 31:
                        return f"{y:04d}-{m:02d}-{d:02d}"
                except ValueError:
                    return ""
    return ""


def _frames(content=None, filename=None, text=None):
    """Return {sheet_name: DataFrame(dtype=str)} for the given input."""
    name = (filename or "").lower()
    if text is not None:
        df = pd.read_csv(StringIO(text), sep=None, engine="python",
                         dtype=str, keep_default_na=False)
        return {"": df}
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content), sheet_name=None, dtype=str)
    # default: CSV
    df = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    return {"": df}


def _row_to_norm(rec: dict, sheet: str, row_no: int, default_station: str) -> dict:
    manufacturer = _clean(rec.get("manufacturer"))
    model = _clean(rec.get("model"))
    name = _clean(rec.get("asset_name"))
    etype = _clean(rec.get("equipment_type")) or _clean(rec.get("category"))
    asset_name = name or f"{manufacturer} {model}".strip() or etype
    serial = _clean(rec.get("serial_number")) or _clean(rec.get("console_serial"))
    if serial.lower() in _BLANK_SERIALS:
        serial = ""
    station = _clean(rec.get("station_name")) or _clean(sheet) or _clean(default_station)
    qty = _clean(rec.get("quantity"))
    try:
        qty_n = max(1, int(float(qty))) if qty else 1
    except ValueError:
        qty_n = 1
    return {
        "station_name": station,
        "sub_location": _clean(rec.get("sub_location")),
        "equipment_type": etype,
        "manufacturer": manufacturer,
        "model": model,
        "serial_number": serial,
        "asset_number": _clean(rec.get("asset_number")),
        "mod_code": _clean(rec.get("mod_code")),
        "warranty_end": parse_date(rec.get("warranty_end")),
        "asset_name": asset_name,
        "notes": _clean(rec.get("notes")),
        "quantity": qty_n,
        "source_sheet": _clean(sheet),
        "source_row": row_no,
    }


def parse_import(content=None, filename=None, text=None, default_station="", column_map=None):
    """
    Parse a spreadsheet/CSV/paste into normalised rows.

    `column_map` (optional) maps ORIGINAL header text -> canonical field (or "" /
    "ignore" to skip a column). It overrides auto-detection, letting the operator
    map unusual layouts. Returns (rows, meta). `meta` describes the detected
    columns + effective mapping so the UI can render a mapping table and remember
    it for next time.
    """
    column_map = column_map or {}
    frames = _frames(content=content, filename=filename, text=text)
    all_headers = _all_headers(frames)
    sheets_named = any(str(s).strip() for s in frames.keys())

    # Effective field per header: manual override wins, else auto-detect.
    def _eff_field(header):
        if header in column_map:
            f = column_map[header]
            return "" if f in ("ignore", None) else f
        return _auto_field(header)

    effective = {h: _eff_field(h) for h in all_headers}

    rows, recognised = [], False
    for sheet_name, df in frames.items():
        if df is None or df.empty:
            continue
        colmap = {c: effective.get(str(c), "") for c in df.columns
                  if effective.get(str(c), "") in HEADER_ALIASES}
        if colmap:
            recognised = True
        renamed = df.rename(columns=colmap)
        for idx, r in renamed.iterrows():
            rec = {}
            for field in HEADER_ALIASES:
                if field in renamed.columns:
                    val = r[field]
                    if isinstance(val, pd.Series):
                        val = next((x for x in val.tolist() if _clean(x)), "")
                    rec[field] = val
            norm = _row_to_norm(rec, str(sheet_name), int(idx) + 2, default_station)
            if not any([norm["station_name"], norm["equipment_type"], norm["manufacturer"],
                        norm["model"], norm["serial_number"], norm["asset_number"]]):
                continue
            rows.append(norm)

    columns = [{"header": h, "field": effective.get(h, ""), "auto": _auto_field(h)}
               for h in all_headers]
    mapped_fields = {f for f in effective.values() if f}
    unmapped = [h for h in all_headers if not effective.get(h)]
    missing_required = []
    if "station_name" not in mapped_fields and not default_station and not sheets_named:
        missing_required.append("station_name")
    if not (mapped_fields & {"equipment_type", "manufacturer", "model", "serial_number", "asset_name"}):
        missing_required.append("equipment")

    meta = {
        "sheets": [str(s) for s in frames.keys()],
        "recognised_columns": recognised,
        "columns": columns,
        "mapping": {h: f for h, f in effective.items() if f},
        "signature": signature(all_headers),
        "field_labels": FIELD_LABELS,
        "unmapped": unmapped,
        "missing_required": missing_required,
    }
    return rows, meta


def template_csv() -> str:
    buf = StringIO()
    buf.write(",".join(TEMPLATE_COLUMNS) + "\n")
    for row in TEMPLATE_SAMPLE_ROWS:
        buf.write(",".join(row) + "\n")
    return buf.getvalue()
