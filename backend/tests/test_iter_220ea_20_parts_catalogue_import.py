"""Iter 220ea·20 — Phase 5b: Parts Catalogue + Bulk Import.

Live HTTP tests for the catalogue browse + CSV import pipeline
(parse → validate → commit) added in ``parts_catalogue.py`` /
``parts_import.py``. Uses the master-admin token (owner/admin → can
manage). Skips gracefully if the token is unavailable.

The import is exercised with a small in-memory CSV that deliberately
contains a duplicate SKU, a missing-SKU row and an invalid numeric so
the validator's behaviour is asserted.
"""
import io
import uuid

import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_catalogue_browse_shape(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    r = requests.get(f"{BASE}/api/svc/parts/catalogue",
                     params={"page": 1, "page_size": 10}, headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("items", "total", "page", "pages", "show_cost", "can_manage"):
        assert k in b, f"missing {k}"
    assert b["can_manage"] is True
    assert b["show_cost"] is True


def test_catalogue_facets(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    r = requests.get(f"{BASE}/api/svc/parts/catalogue/facets", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "categories" in b and "manufacturers" in b and "total" in b


def test_catalogue_requires_auth():
    r = requests.get(f"{BASE}/api/svc/parts/catalogue", timeout=20)
    assert r.status_code in (401, 403)


def _csv_file():
    tag = uuid.uuid4().hex[:6].upper()
    rows = [
        "Part Number,Description,Manufacturer,Category,Qty,Cost Price,Sell Price,Min Stock,Reorder Qty,Bin",
        f"PYT-{tag}-A,Pytest Belt A,Pulse,Belts,4,38.50,79.99,2,6,A1",
        f"PYT-{tag}-A,Pytest Belt A dup,Pulse,Belts,1,38.50,79.99,2,6,A1",
        f"PYT-{tag}-B,Pytest Lube B,GymAxis,Consumables,10,5.20,12.99,4,20,B3",
        ",Missing SKU,Generic,Misc,5,1.00,2.00,1,1,Z9",
        f"PYT-{tag}-C,Pytest Keypad,LifeFit,Electronics,bad,22.00,49.50,2,5,D1",
    ]
    return io.BytesIO("\n".join(rows).encode()), tag


def test_import_parse_validate_commit_flow(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    h = _h(token)
    buf, tag = _csv_file()

    # PARSE (no AI — keep test deterministic/fast)
    r = requests.post(f"{BASE}/api/svc/parts/import/parse",
                      files={"file": (f"pyt-{tag}.csv", buf, "text/csv")},
                      data={"use_ai": "false"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["row_count"] == 5
    sid = p["session_id"]
    mapping = p["suggested_mapping"]
    # Heuristic mapping must catch the obvious ones.
    assert "sku" in mapping.values()
    assert "name" in mapping.values()

    # VALIDATE
    r = requests.post(f"{BASE}/api/svc/parts/import/validate",
                      json={"session_id": sid, "mapping": mapping, "use_ai": False},
                      headers=h, timeout=30)
    assert r.status_code == 200, r.text
    v = r.json()
    s = v["summary"]
    assert s["total"] == 5
    assert s["errors"] >= 2   # missing-SKU + invalid qty
    assert s["warnings"] >= 1  # in-file duplicate
    assert s["new"] >= 2

    # COMMIT
    r = requests.post(f"{BASE}/api/svc/parts/import/commit",
                      json={"session_id": sid, "mapping": mapping,
                            "options": {"mode": "upsert", "van_qty_mode": "set",
                                        "skip_duplicates": True}},
                      headers=h, timeout=30)
    assert r.status_code == 200, r.text
    c = r.json()["summary"]
    assert c["created"] >= 2
    assert c["skipped"] >= 1   # the in-file duplicate
    assert c["van_adjusted"] >= 2

    # The new parts are now browsable.
    r = requests.get(f"{BASE}/api/svc/parts/catalogue",
                     params={"search": f"PYT-{tag}"}, headers=h, timeout=20)
    assert r.status_code == 200
    assert r.json()["total"] >= 2


def test_validate_requires_sku_and_name(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        import pytest
        pytest.skip("no master admin token")
    h = _h(token)
    buf, tag = _csv_file()
    r = requests.post(f"{BASE}/api/svc/parts/import/parse",
                      files={"file": (f"pyt-{tag}.csv", buf, "text/csv")},
                      data={"use_ai": "false"}, headers=h, timeout=30)
    sid = r.json()["session_id"]
    # Map nothing → must reject (required fields unmapped).
    r = requests.post(f"{BASE}/api/svc/parts/import/validate",
                      json={"session_id": sid, "mapping": {}, "use_ai": False},
                      headers=h, timeout=20)
    assert r.status_code == 422, r.text
