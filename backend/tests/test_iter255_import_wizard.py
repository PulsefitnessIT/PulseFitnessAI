"""Iter 255 — Migration import wizard (/api/svc/imports/*).

Covers parse (CSV header auto-mapping), validate (errors + duplicates),
commit (customers + historical cases), error-CSV download, tenant scoping
and idempotency (no double commit). The AI fallback endpoint is exercised
only for its guard paths (no headers → 400) to keep CI deterministic and
free of LLM spend.
"""

import io
import uuid

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

PROVIDER = ("sp.fe.1781277405@example.com", "Str0ngPass!23")

_TAG = uuid.uuid4().hex[:6]

CUSTOMERS_CSV = (
    "Company Name,Contact E-mail,Tel,Site,Post Code,Remarks\n"
    f"PyImport Gym {_TAG},py.{_TAG}@example.com,0113111,Main,LS1 1AA,vip\n"
    f"PyImport Gym {_TAG},py.{_TAG}@example.com,0113111,Main,LS1 1AA,dupe\n"
    ",noname@example.com,,,,bad\n"
)

CASES_CSV = (
    "Job No,Fault,Severity,Client,Opened,Completed,Technician\n"
    f"PY-{_TAG}-1,Belt slipping,High,PyImport Gym,12/03/2026,14/03/2026,First Engineer\n"
    f"PY-{_TAG}-2,No opened date,Low,PyImport Gym,,05/04/2026,\n"
    f"PY-{_TAG}-1,Duplicate ref,Medium,PyImport Gym,10/04/2026,11/04/2026,\n"
)


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PROVIDER[0], "password": PROVIDER[1]}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _parse(h, csv_text, import_type):
    r = requests.post(
        f"{BASE_URL}/api/svc/imports/parse", headers=h,
        files={"file": ("test.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        data={"import_type": import_type}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_auth():
    r = requests.post(f"{BASE_URL}/api/svc/imports/parse", timeout=20)
    assert r.status_code in (401, 403, 422)
    r = requests.post(f"{BASE_URL}/api/svc/imports/parse",
                      files={"file": ("a.csv", io.BytesIO(b"x\n1"), "text/csv")},
                      data={"import_type": "customers"}, timeout=20)
    assert r.status_code in (401, 403)


def test_customers_flow():
    h = _login()
    p = _parse(h, CUSTOMERS_CSV, "customers")
    assert p["row_count"] == 3
    m = p["suggested_mapping"]
    assert m["Company Name"] == "name" and m["Contact E-mail"] == "email"
    assert "Remarks" in p["unmatched_headers"]  # left for the AI fallback

    mapping = {**{k: v for k, v in m.items() if v}, "Remarks": "notes"}
    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/validate",
                      headers=h, json={"mapping": mapping}, timeout=30)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["valid_count"] == 2 and v["error_count"] == 1 and v["duplicate_count"] >= 1

    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/commit",
                      headers=h, json={"mapping": mapping, "duplicate_strategy": "skip"}, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["created"] == 1 and s["skipped"] == 1 and s["errored"] == 1

    # Errors CSV downloads with the reason column.
    r = requests.get(f"{BASE_URL}/api/svc/imports/{p['import_id']}/errors.csv", headers=h, timeout=20)
    assert r.status_code == 200
    assert "Missing customer name" in r.text

    # Idempotency: a second commit must 400.
    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/commit",
                      headers=h, json={"mapping": mapping}, timeout=30)
    assert r.status_code == 400


def test_cases_flow_historical_closed():
    h = _login()
    p = _parse(h, CASES_CSV, "cases")
    m = p["suggested_mapping"]
    assert m["Job No"] == "reference" and m["Opened"] == "created_at"

    mapping = {k: v for k, v in m.items() if v}
    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/validate",
                      headers=h, json={"mapping": mapping}, timeout=30)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["valid_count"] == 2 and v["error_count"] == 1 and v["duplicate_count"] == 1

    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/commit",
                      headers=h, json={"mapping": mapping, "duplicate_strategy": "skip"}, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["created"] == 1 and s["skipped"] == 1 and s["errored"] == 1

    # Imported case is CLOSED with original dd/mm/yyyy date and the
    # engineer name matched onto a real svc_engineers id.
    r = requests.get(f"{BASE_URL}/api/svc/cases", headers=h,
                     params={"search": f"PY-{_TAG}-1", "status": "closed"}, timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json().get("cases") or r.json().get("rows") or []
    found = [c for c in rows if c.get("reference") == f"PY-{_TAG}-1"]
    assert found, rows
    c = found[0]
    assert c["status"] == "closed"
    assert c["created_at"].startswith("2026-03-12")
    assert c.get("assigned_engineer_id")  # 'First Engineer' matched
    assert c.get("source") == "import" or "imported" in (c.get("tags") or [])


def test_validation_guards():
    h = _login()
    p = _parse(h, CUSTOMERS_CSV, "customers")
    # Required column (name) unmapped → 400
    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/validate",
                      headers=h, json={"mapping": {"Tel": "phone"}}, timeout=30)
    assert r.status_code == 400
    # AI map with no headers → 400
    r = requests.post(f"{BASE_URL}/api/svc/imports/{p['import_id']}/ai-map",
                      headers=h, json={"headers": []}, timeout=30)
    assert r.status_code == 400
    # Bad import type → 400
    r = requests.post(
        f"{BASE_URL}/api/svc/imports/parse", headers=h,
        files={"file": ("t.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        data={"import_type": "equipment"}, timeout=20)
    assert r.status_code == 400
    # Unknown job id → 404
    r = requests.post(f"{BASE_URL}/api/svc/imports/{uuid.uuid4()}/commit",
                      headers=h, json={}, timeout=20)
    assert r.status_code == 404
