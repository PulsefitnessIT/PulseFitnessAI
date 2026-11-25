"""Synthetic Schedule B ("Tender SOR") workbook for tests.

Same sheet layout as the LSLDC0223 Schedule B. Only the categories used by the historical
HMNB Clyde regression quotes carry their historical prices; every other value is synthetic.
"""
import io

import openpyxl

ROWS = [
    ("1B", "Call Out Charge,", "MOD-CALLOUT", "SER900001", 80.0),
    ("2A", "Treadmills,", "MOD-TREAD-A", "SER100135", 255.0), ("2B", "Treadmills,", "MOD-TREAD-B", "SER900003", 24.0),
    ("4A", "Rowing Machine,", "MOD-ROW-A", "SER900004", 72.56), ("4B", "Rowing Machine,", "MOD-ROW-B", "SER900005", 16.0),
    ("5A", "Benches,", "MOD-BENCH-A", "SER900006", 43.53), ("5B", "Benches,", "MOD-BENCH-B", "SER900007", 7.0),
    ("8A", "Cross Trainer, Non Powered,", "MOD-XT-A", "SER900008", 157.2),
    ("8B", "Cross Trainer, Non Powered,", "MOD-XT-B", "SER900009", 24.0),
    ("14A", "Synthetic Rower Variant,", "MOD-ROW-A", "SER900010", 99.0),
    ("18A", "Upright Bike, Non Powered,", "MOD-UBIKE-A", "SER900011", 157.2),
    ("18B", "Upright Bike, Non Powered,", "MOD-UBIKE-B", "SER900012", 16.0),
    ("20A", "SingleStation Strength Machine,", "MOD-STRENGTH-A", "SER900013", 90.0),
    ("20B", "SingleStation Strength Machine,", "MOD-STRENGTH-B", "SER900014", 16.0),
    ("23A", "Multigym, 2 Station,", "MOD-MULTI2-A", "SER900015", 145.12),
    ("23B", "Multigym, 2 Station,", "MOD-MULTI2-B", "SER900016", 21.0),
    ("26A", "Synthetic Category X,", "MOD-RAD-A", "SER900017", 50.0),
    ("27A", "Synthetic Category Y,", "MOD-RAD-A", "SER900018", 60.0),
    ("28C", "Synthetic Parts Allowance,", "MOD-PARTS-C", "SER900019", "POA"),
]


def synthetic_sor_bytes(overrides: dict | None = None) -> bytes:
    """overrides: {uid: price} to simulate a changed price list."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tender SOR"
    ws.append(["Legend"])
    ws.append(["SYNTHETIC TEST DATA — not commercial pricing"])
    ws.append([])
    ws.append([])
    ws.append(["Unique Identifier (serial no)", None, "Item Description", "Sage Item Code", "TL Number",
               "Extended Item Description", "Unit of Measure", "Year 1 Price"])
    for uid, name, sage, tl, price in ROWS:
        p = (overrides or {}).get(uid, price)
        ws.append([uid, None, name, sage, tl, f"{name} synthetic description", "Each", p])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
