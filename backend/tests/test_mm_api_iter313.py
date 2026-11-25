"""Iteration 313 — Maintenance Master resolution centre, daily view, invoice-run preview (public URL).
Run after `mm_ui_seed.py seed`. Real upload e7a84748 is only READ (never committed)."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import io
import os
import time

import openpyxl
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or open(REPO + "/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]).rstrip("/")
MM = f"{BASE}/api/crm/v2/aftersales/maintenance-master"
REAL = "e7a84748-9c0d-4415-ba64-d66c621d3dae"
PW = "CmTest2026!"


def _login(email):
    r = requests.post(f"{BASE}/api/crm/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:120]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def coord():
    return _login("cm.coordinator@pulsefitness.test")


@pytest.fixture(scope="module")
def mgr():
    return _login("cm.aftersales@pulsefitness.test")


@pytest.fixture(scope="module")
def fin():
    return _login("cm.finance@pulsefitness.test")


@pytest.fixture(scope="module")
def seed_uid(coord):
    ups = requests.get(f"{MM}/uploads", headers=coord, timeout=30).json()["uploads"]
    u = next((u for u in ups if u["filename"].startswith("mmt_ui")), None)
    if not u:
        pytest.skip("seed upload missing")
    return u["id"]


# Real upload (read-only): unresolved queue sizes
def test_real_unresolved_counts(coord):
    r = requests.get(f"{MM}/uploads/{REAL}/rows", headers=coord, params={"unresolved": "true"}, timeout=60)
    assert r.status_code == 200
    n = r.json()["count"]
    r2 = requests.get(f"{MM}/uploads/{REAL}/rows", headers=coord, params={"unresolved": "true", "issue": "contract number"}, timeout=60)
    m = r2.json()["count"]
    print("real unresolved", n, "missing contract number", m)
    assert 1100 <= n <= 1180
    assert 770 <= m <= 820
    assert all("contract number" in " ".join(x["problems"]).lower() for x in r2.json()["rows"])


# Daily view: 9 cards, coordinators list, coordinator filter accepted
def test_daily_view(coord):
    r = requests.get(f"{MM}/daily", headers=coord, timeout=60)
    assert r.status_code == 200
    d = r.json()
    keys = {"expiring_soon", "renewals", "missing_information", "awaiting_approval", "service_attention", "follow_up",
            "import_exceptions", "unverified_billing", "sicon_pending"}
    assert keys <= set(d["cards"])
    assert d["today"] == time.strftime("%Y-%m-%d", time.gmtime())
    print({k: v["count"] for k, v in d["cards"].items()}, d["coordinators"][:5])
    if d["coordinators"]:
        r2 = requests.get(f"{MM}/daily", headers=coord, params={"coordinator": d["coordinators"][0]}, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["cards"]["expiring_soon"]["count"] <= d["cards"]["expiring_soon"]["count"]


# Resolution: row detail exposes raw + effective; correct needs reason; bad field rejected
def test_row_detail_and_correct_validation(coord, seed_uid):
    rows = requests.get(f"{MM}/uploads/{seed_uid}/rows", headers=coord, params={"cls": "missing_information"}, timeout=30).json()["rows"]
    assert rows, "no missing-information row in seed"
    rid = rows[0]["id"]
    d = requests.get(f"{MM}/uploads/{seed_uid}/rows/{rid}", headers=coord, timeout=30).json()
    assert "raw" in d and "effective" in d and d["problems"]
    base = f"{MM}/uploads/{seed_uid}/rows/{rid}"
    assert requests.post(f"{base}/correct", headers=coord, json={"fields": {"contract_number": "X"}, "reason": " "}).status_code == 400
    assert requests.post(f"{base}/correct", headers=coord, json={"fields": {"status": "x"}, "reason": "r"}).status_code == 400
    assert requests.post(f"{base}/correct", headers=coord, json={"fields": {"end_date": "notadate"}, "reason": "r"}).status_code == 400
    assert requests.post(f"{base}/decision", headers=coord, json={"action": "skip", "note": ""}).status_code == 400


# Invoice-run: validation + shape (preview only)
def test_invoice_run_shape(fin):
    assert requests.get(f"{MM}/invoice-run", headers=fin, params={"period": "2026-13x"}).status_code == 400
    r = requests.get(f"{MM}/invoice-run", headers=fin, params={"period": "2026-12"}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["preview_only"] is True and d["posting_enabled"] is False
    for k in ("proposed", "net", "needs_information", "already_invoiced", "duplicates"):
        assert k in d["totals"]
    x = requests.get(f"{MM}/invoice-run/export", headers=fin, params={"period": "2026-12"}, timeout=60)
    assert x.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(x.content), read_only=True)
    assert {"Summary", "Invoice run"} <= set(wb.sheetnames)


# Customer search
def test_customer_search(coord):
    r = requests.get(f"{MM}/customers", headers=coord, params={"q": "a"})
    assert r.status_code == 200 and r.json()["customers"] == []
