"""Iter318 release sprint: MOD Quotations /rates/current, synthetic-rate guard, role visibility,
draft group lifecycle (idempotent create, submit, approval refused on unapproved rates, PDFs), portal isolation."""
import os
import sys
import uuid

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests

from tests.conftest import _test_backend_url  # noqa: E402

BASE_URL = _test_backend_url()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
MQ = f"{API}/mod-ops/quotes"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
ROWS = [{"row_id": "t1", "rate_card_id": "sor-2", "description": "TEST_Treadmills", "qty": 2, "coverage": "A", "label": ""},
        {"row_id": "t2", "rate_card_id": "sor-5", "description": "TEST_Benches", "qty": 1, "coverage": "B", "label": ""}]
CUSTOMER = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane", "Helensburgh", "G84 0EH"]}
STATE: dict = {}
CREATED: list = []


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def mgr():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    s = _login("modsales.manager@pulsedemo.test", "ModSales123!") if CREATED else None
    for gid in CREATED:
        s.post(f"{MQ}/groups/{gid}/withdraw", json={"reason": "TEST cleanup iter318"})
    pid = STATE.get("preview_pid")
    if pid:
        from pymongo import MongoClient
        MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].mod_sor_price_lists.delete_one({"id": pid, "status": "preview"})


# --- Schedule of Rates: /rates/current ---
def test_rates_current_manager(mgr):
    r = mgr.get(f"{MQ}/rates/current")
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["rows"], list) and len(d["rows"]) > 0
    assert isinstance(d["summary"], dict)
    assert d["customer_ready"] is False
    row = d["rows"][0]
    assert {"a", "b", "label", "item_no"} <= set(row)
    assert "status" in row["a"] and "price" in row["a"]
    STATE["rates_before"] = d["rows"]
    STATE["summary"] = d["summary"]
    print("summary", d["summary"], "live", (d.get("live_price_list") or {}).get("synthetic"))


def test_rates_current_rep_forbidden(rep):
    r = rep.get(f"{MQ}/rates/current")
    assert r.status_code == 403, r.text


def test_rep_capabilities(rep, mgr):
    rr, mr = rep.get(f"{MQ}/me"), mgr.get(f"{MQ}/me")
    assert rr.status_code == 200 and mr.status_code == 200
    print("rep caps", rr.json(), "mgr caps", mr.json())


# --- Synthetic workbook guard ---
def test_synthetic_import_preview_and_approve_blocked(mgr):
    from tests.mod_quote_fixtures import synthetic_sor_bytes
    r = mgr.post(f"{MQ}/rates/import-preview", files={"file": ("TEST_sor.xlsx", synthetic_sor_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["synthetic"] is True
    STATE["preview_pid"] = d["price_list_id"]
    a = mgr.post(f"{MQ}/rates/{d['price_list_id']}/approve", json={"effective_from": "2026-01-01", "confirm": True})
    assert a.status_code == 409, a.text
    assert "SYNTHETIC" in a.text


def test_live_card_unchanged_after_blocked_approve(mgr):
    r = mgr.get(f"{MQ}/rates/current")
    assert r.status_code == 200
    assert r.json()["rows"] == STATE["rates_before"]
    assert r.json()["customer_ready"] is False


def test_rep_cannot_import_rates(rep):
    from tests.mod_quote_fixtures import synthetic_sor_bytes
    r = rep.post(f"{MQ}/rates/import-preview", files={"file": ("TEST_sor.xlsx", synthetic_sor_bytes())})
    assert r.status_code == 403, r.text


# --- Draft group lifecycle ---
def test_create_group_idempotent(mgr):
    key = str(uuid.uuid4())
    body = {"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B", "AB"], "callout_qty": 1, "idempotency_key": key}
    r1 = mgr.post(f"{MQ}/groups", json=body)
    assert r1.status_code in (200, 201), r1.text
    gid = r1.json()["id"]
    CREATED.append(gid)
    r2 = mgr.post(f"{MQ}/groups", json=body)
    assert r2.status_code in (200, 201, 409), r2.text
    if r2.status_code != 409:
        if r2.json()["id"] != gid:
            CREATED.append(r2.json()["id"])
        assert r2.json()["id"] == gid, "duplicate group created for same idempotency key"
    STATE["gid"] = gid
    g = mgr.get(f"{MQ}/groups/{gid}").json()
    assert g["status"] == "draft"
    assert sorted(q["mod_quote_type"] for q in g["quotes"]) == ["A", "AB", "B"]
    STATE["quotes"] = {q["mod_quote_type"]: q["id"] for q in g["quotes"]}


def test_pdf_and_zip(mgr):
    qid = STATE["quotes"]["A"]
    r = mgr.get(f"{MQ}/quotes/{qid}/pdf")
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    z = mgr.get(f"{MQ}/groups/{STATE['gid']}/pdfs.zip")
    assert z.status_code == 200
    assert z.content[:2] == b"PK"


def test_submit_and_approve_refused(mgr, rep):
    gid = STATE["gid"]
    r = mgr.post(f"{MQ}/groups/{gid}/submit")
    assert r.status_code == 200, r.text
    g = mgr.get(f"{MQ}/groups/{gid}").json()
    assert g["status"] == "pending_approval"
    unv = sum(len(q.get("unverified_rate_lines") or []) for q in g["quotes"])
    assert unv > 0, "expected unverified lines (preview card is test data)"
    rr = rep.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "exceptions": []})
    assert rr.status_code == 403, rr.text
    a = mgr.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "exceptions": []})
    assert a.status_code in (400, 409, 422), a.text
    assert "detail" in a.json()
    print("approve refusal:", a.json()["detail"])
    assert mgr.get(f"{MQ}/groups/{gid}").json()["status"] == "pending_approval"


def test_portal_hides_unpublished():
    s = _login("modsite.officer@army.mod.test", "ModSite123!", portal="mod")
    r = s.get(f"{API}/mod/site/quotes")
    assert r.status_code == 200, r.text
    d = r.json()
    ids = {q["id"] for q in d["quotes"]}
    assert not (ids & set(STATE["quotes"].values())), "draft/pending quotes leaked to portal"
    assert all(q["status"] not in ("draft", "pending_approval", "approved") for q in d["quotes"])


def test_withdraw(mgr):
    gid = STATE["gid"]
    r = mgr.post(f"{MQ}/groups/{gid}/withdraw", json={"reason": "TEST iter318"})
    assert r.status_code == 200, r.text
    assert mgr.get(f"{MQ}/groups/{gid}").json()["status"] == "withdrawn"
