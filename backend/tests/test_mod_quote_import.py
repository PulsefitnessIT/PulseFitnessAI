"""MOD Auto Quote Writer — spreadsheet import endpoint tests."""
import io
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
CRM_LOGIN = f"{BASE_URL}/api/crm/auth/login"
IMPORT_URL = f"{BASE_URL}/api/crm/mod-quote/import-spreadsheet"

SAMPLE_ROWS = """Item,Machine,Qty,Notes
1,Life Fitness Treadmill,3,cardio
2,Concept2 Rower,2,
3,Upright Bike (non-powered),4,
,TOTALS,9,
5,Widget XYZ 9000 mystery unit,1,unknown
"""


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(CRM_LOGIN, json={
        "email": "admin@pulsefitness.com",
        "password": "C2s9yJ3YAhydB4d34-Bykg",
    }, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


def _assert_response_shape(payload, expected_ct="A"):
    assert payload.get("contract_type") == expected_ct
    for k in ("recognised_count", "matched_count", "needs_review_count", "note", "lines"):
        assert k in payload, f"missing key: {k}"
    assert isinstance(payload["lines"], list)
    for line in payload["lines"]:
        for k in ("description", "quantity", "rate_card_id", "rate_card_label",
                  "unit_price", "confidence", "matched", "needs_review"):
            assert k in line, f"line missing key: {k}"


def test_import_pasted_text(auth_headers):
    r = requests.post(
        IMPORT_URL,
        headers=auth_headers,
        data={"pasted_text": SAMPLE_ROWS, "contract_type": "A", "year": "1"},
        timeout=90,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    payload = r.json()
    _assert_response_shape(payload, "A")
    assert payload["recognised_count"] >= 3, f"expected ≥3 recognised, got {payload}"

    descs = " | ".join((l["description"] or "").lower() for l in payload["lines"])
    # Totals row should be skipped
    assert "totals" not in descs, "TOTALS row was not filtered"

    # Widget XYZ should be flagged needs_review with no unit_price
    widget = next((l for l in payload["lines"] if "widget" in (l["description"] or "").lower()), None)
    assert widget is not None, "Widget XYZ line not recognised"
    assert widget["needs_review"] is True
    assert widget["rate_card_id"] is None
    assert widget["unit_price"] in (None, 0, 0.0) or widget["unit_price"] is None

    # At least one matched line should have a positive unit_price for A
    matched_priced = [l for l in payload["lines"] if l["matched"] and l["unit_price"]]
    assert matched_priced, f"expected some matched priced lines: {payload['lines']}"


def test_import_csv_file(auth_headers):
    files = {"file": ("assets.csv", io.BytesIO(SAMPLE_ROWS.encode("utf-8")), "text/csv")}
    r = requests.post(
        IMPORT_URL,
        headers=auth_headers,
        data={"contract_type": "A", "year": "1"},
        files=files,
        timeout=90,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    payload = r.json()
    _assert_response_shape(payload, "A")
    assert payload["recognised_count"] >= 3


def test_import_requires_input(auth_headers):
    r = requests.post(IMPORT_URL, headers=auth_headers,
                      data={"contract_type": "A", "year": "1"}, timeout=30)
    assert r.status_code == 400


def test_import_rejects_unauth():
    r = requests.post(IMPORT_URL, data={"pasted_text": SAMPLE_ROWS,
                                        "contract_type": "A", "year": "1"}, timeout=30)
    assert r.status_code in (401, 403)


def test_import_bad_contract_type(auth_headers):
    r = requests.post(IMPORT_URL, headers=auth_headers,
                      data={"pasted_text": SAMPLE_ROWS,
                            "contract_type": "Z", "year": "1"}, timeout=30)
    assert r.status_code == 400
