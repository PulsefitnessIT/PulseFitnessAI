"""Iter 220 P1 — price-list backup/export helper unit tests."""
from datetime import datetime, timezone

from routes.crm_price_backup import _columns, _to_csv, _to_xlsx, _scope_query, _compute_next_run


def test_columns_gate_cost_margin():
    labels = [lbl for _, lbl in _columns(include_cost=False, include_margin=False)]
    assert "Cost Price" not in labels and "Margin %" not in labels
    labels2 = [lbl for _, lbl in _columns(include_cost=True, include_margin=True)]
    assert "Cost Price" in labels2 and "Margin %" in labels2
    # cost sits right after Sell Price
    assert labels2.index("Cost Price") == labels2.index("Sell Price") + 1


def test_scope_query():
    user = {"organization_id": "o1"}
    assert _scope_query(user, "live", "") == {"organization_id": "o1", "active": True}
    assert _scope_query(user, "archived", "") == {"organization_id": "o1", "active": False}
    assert _scope_query(user, "all", "") == {"organization_id": "o1"}
    assert _scope_query(user, "category", "Cardio") == {"organization_id": "o1", "category": "Cardio", "active": True}


def test_to_csv_has_bom_and_header():
    out = _to_csv(["A", "B"], [[1, 2], [3, 4]])
    assert out.startswith(b"\xef\xbb\xbf")   # UTF-8 BOM for Excel
    assert b"A,B" in out and b"3,4" in out


def test_to_xlsx_is_zip():
    out = _to_xlsx(["A", "B"], [[1, 2]])
    assert out[:2] == b"PK"   # xlsx is a zip


def test_compute_next_run_is_future_and_correct_weekday():
    nxt = _compute_next_run(0, "06:00")   # Monday 06:00
    dt = datetime.fromisoformat(nxt)
    assert dt > datetime.now(timezone.utc)
    assert dt.weekday() == 0 and dt.hour == 6 and dt.minute == 0
