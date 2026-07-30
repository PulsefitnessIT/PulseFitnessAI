"""Backend tests for MOD Automatic Quote Writer (Jan 2026).

Covers rate card, MOD sites, equipment auto-mapping, quote generation
(Type A/B/C), Type A contract provisioning, year overrides,
AI-match and PDF endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # frontend .env is the source of truth in this repo
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
                    break
    except Exception:
        pass

CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
MOD_SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": CRM_EMAIL, "password": CRM_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def crm_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


# ── Rate card ───────────────────────────────────────────────────────

def test_rate_card_has_30_lines(crm_headers):
    r = requests.get(f"{BASE_URL}/api/crm/mod-quote/rate-card", headers=crm_headers, timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 30, f"expected 30 SOR lines, got {len(items)}"
    labels = {i["label"]: i for i in items}
    tread = next(i for i in items if "Treadmill" in i["label"] and i.get("kind") == "service")
    assert tread["type_a_price"] == 56.73
    assert tread["type_b_price"] == 16
    bike = next(i for i in items if "Upright Bike" in i["label"] and i.get("kind") == "service")
    assert bike["type_a_price"] == 145.12
    assert bike["type_b_price"] == 21
    co = next(i for i in items if i.get("kind") == "call_out")
    assert co["type_b_price"] == 80
    poa = [i for i in items if i.get("is_poa")]
    assert len(poa) >= 3, f"expected >=3 POA lines, got {len(poa)}"


# ── MOD sites ───────────────────────────────────────────────────────

def test_mod_sites_lists_test_site(crm_headers):
    r = requests.get(f"{BASE_URL}/api/crm/mod-quote/mod-sites", headers=crm_headers, timeout=30)
    assert r.status_code == 200
    sites = r.json()["sites"]
    match = next((s for s in sites if s["id"] == MOD_SITE_ID), None)
    assert match, f"MOD Test Site {MOD_SITE_ID} not present. Sites: {[s['name'] for s in sites]}"
    assert match["equipment_count"] == 8, f"expected 8 equipment, got {match['equipment_count']}"


# ── Equipment auto-mapping ──────────────────────────────────────────

def test_equipment_auto_maps_all_8(crm_headers):
    r = requests.get(
        f"{BASE_URL}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 1},
        headers=crm_headers, timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["lines"]) == 8
    assert data["matched_count"] == 8, f"unmatched: {data.get('unmatched_count')}"
    for line in data["lines"]:
        assert line["matched"] is True
        assert line["unit_price"] is not None
        assert line["rate_card_id"]


# ── Quote generation ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mapped_lines(crm_headers):
    r = requests.get(
        f"{BASE_URL}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 1},
        headers=crm_headers, timeout=30,
    )
    r.raise_for_status()
    return [
        {
            "rate_card_id": l["rate_card_id"],
            "equipment_id": l["equipment_id"],
            "serial_number": l.get("serial_number"),
            "quantity": 1,
        }
        for l in r.json()["lines"]
    ]


def test_generate_type_a_creates_quote_and_contract(crm_headers, mapped_lines):
    payload = {
        "contract_type": "A",
        "year": 1,
        "site_id": MOD_SITE_ID,
        "site_name": "MOD Test Site",
        "lines": mapped_lines,
        "vat_rate": 20,
    }
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/generate", json=payload,
        headers=crm_headers, timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    q = body["quote"]
    assert q["quote_kind"] == "mod_sor"
    assert q["mod_contract_type"] == "A"
    assert abs(q["subtotal"] - 1057.52) < 0.5, f"subtotal={q['subtotal']}"
    # Contract-header line present, £0
    hdr = next((l for l in q["lines"] if l.get("is_contract_header")), None)
    assert hdr is not None
    assert hdr["unit_price"] == 0
    assert "Type A" in hdr["description"]
    # Contract created
    contract = body["contract"]
    assert contract is not None
    assert contract["status"] == "pending_activation"
    assert abs(contract["annual_value"] - 1057.52) < 0.5
    quote_id = q["id"]
    # Appears in v2 quotes list
    r2 = requests.get(f"{BASE_URL}/api/crm/v2/quotes", headers=crm_headers, timeout=30)
    assert r2.status_code == 200
    quotes = r2.json() if isinstance(r2.json(), list) else r2.json().get("quotes", [])
    assert any(x.get("id") == quote_id for x in quotes), "MOD quote not in /crm/v2/quotes"
    # Appears in contracts endpoint
    r3 = requests.get(f"{BASE_URL}/api/crm/mod-quote/contracts", headers=crm_headers, timeout=30)
    assert r3.status_code == 200
    assert any(c["quote_id"] == quote_id for c in r3.json()["contracts"])
    # PDF
    r4 = requests.get(f"{BASE_URL}/api/crm/v2/quotes/{quote_id}/pdf", headers=crm_headers, timeout=60)
    assert r4.status_code == 200
    assert "application/pdf" in r4.headers.get("content-type", "")
    assert r4.content[:4] == b"%PDF"
    # Save for cleanup
    pytest._mod_quote_ids = getattr(pytest, "_mod_quote_ids", []) + [quote_id]
    pytest._mod_contract_ids = getattr(pytest, "_mod_contract_ids", []) + [contract["id"]]


def test_generate_type_b_with_callouts_no_contract(crm_headers, mapped_lines):
    # Get type B lines (need type_b prices, not type_a)
    r0 = requests.get(
        f"{BASE_URL}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "B", "year": 1},
        headers=crm_headers, timeout=30,
    )
    b_lines = [
        {"rate_card_id": l["rate_card_id"], "equipment_id": l["equipment_id"], "quantity": 1}
        for l in r0.json()["lines"]
    ]
    payload = {
        "contract_type": "B", "year": 1, "site_id": MOD_SITE_ID,
        "site_name": "MOD Test Site", "lines": b_lines,
        "call_out_count": 3, "vat_rate": 20,
    }
    r = requests.post(f"{BASE_URL}/api/crm/mod-quote/generate", json=payload,
                      headers=crm_headers, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    q = body["quote"]
    assert q["mod_contract_type"] == "B"
    assert body["contract"] is None, "Type B must NOT create a contract"
    # 3 x £80 call-out
    co_lines = [l for l in q["lines"] if l.get("product_name") == "Call Out Charge"]
    assert len(co_lines) == 1
    assert co_lines[0]["quantity"] == 3
    assert co_lines[0]["unit_price"] == 80
    # VAT
    assert abs(q["vat_amount"] - round(q["subtotal"] * 0.20, 2)) < 0.05
    assert abs(q["total"] - (q["subtotal"] + q["vat_amount"])) < 0.05
    pytest._mod_quote_ids = getattr(pytest, "_mod_quote_ids", []) + [q["id"]]


def test_generate_type_c_uses_custom_price_no_contract(crm_headers):
    payload = {
        "contract_type": "C", "year": 1, "site_id": MOD_SITE_ID,
        "site_name": "MOD Test Site",
        "lines": [
            {"rate_card_id": None, "description": "Overseas custom",
             "unit_price": 999.99, "quantity": 2},
        ],
        "vat_rate": 20,
    }
    r = requests.post(f"{BASE_URL}/api/crm/mod-quote/generate", json=payload,
                      headers=crm_headers, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    q = body["quote"]
    assert q["mod_contract_type"] == "C"
    assert body["contract"] is None
    hdr = next(l for l in q["lines"] if l.get("is_contract_header"))
    assert "Type C" in hdr["description"]
    custom = next(l for l in q["lines"] if not l.get("is_contract_header"))
    assert custom["unit_price"] == 999.99
    assert custom["quantity"] == 2
    pytest._mod_quote_ids = getattr(pytest, "_mod_quote_ids", []) + [q["id"]]


# ── Year override ──────────────────────────────────────────────────

def test_year_override_flows_through(crm_headers):
    # Find sor-2 (Treadmill) to know its baseline; then set y2 override.
    put = requests.put(
        f"{BASE_URL}/api/crm/mod-quote/rate-card/sor-2",
        json={"type_a_price_y2": 60},
        headers=crm_headers, timeout=30,
    )
    assert put.status_code == 200, put.text
    assert put.json().get("type_a_price_y2") == 60
    # Query equipment with year=2 and confirm treadmill row picks up 60
    r = requests.get(
        f"{BASE_URL}/api/crm/mod-quote/equipment",
        params={"site_id": MOD_SITE_ID, "contract_type": "A", "year": 2},
        headers=crm_headers, timeout=30,
    )
    tread = next((l for l in r.json()["lines"] if l["rate_card_id"] == "sor-2"), None)
    assert tread is not None, "No treadmill line mapped to sor-2"
    assert tread["unit_price"] == 60, f"got {tread['unit_price']}"
    # Reset for idempotency
    requests.put(
        f"{BASE_URL}/api/crm/mod-quote/rate-card/sor-2",
        json={"type_a_price_y2": None},
        headers=crm_headers, timeout=30,
    )


def test_rate_card_edit_forbidden_for_non_admin():
    # Manager (site-restricted, non-admin) should get 403
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": "manager@isodemo.com", "password": "IsoDemo123!"},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip("manager login unavailable")
    tok = r.json().get("token") or r.json().get("access_token")
    put = requests.put(
        f"{BASE_URL}/api/crm/mod-quote/rate-card/sor-2",
        json={"type_a_price_y2": 999},
        headers={"Authorization": f"Bearer {tok}"}, timeout=30,
    )
    assert put.status_code == 403, f"expected 403, got {put.status_code} {put.text}"


# ── AI match ───────────────────────────────────────────────────────

def test_ai_match_ambiguous(crm_headers):
    r = requests.post(
        f"{BASE_URL}/api/crm/mod-quote/ai-match",
        json={"equipment": {"name": "StairMaster Gauntlet", "equipment_type": "Stepper"}},
        headers=crm_headers, timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rate_card_id" in body
    # accept any rate card id or explicit null (best-effort AI)
    if body["rate_card_id"] is not None:
        assert body["rate_card_id"].startswith("sor-")


# ── Cleanup ────────────────────────────────────────────────────────

def test_cleanup(crm_headers):
    """Best-effort cleanup of quotes/contracts created above."""
    from pymongo import MongoClient
    try:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME", "test_database")
        if not mongo_url:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.strip().split("=", 1)[1]
                    elif line.startswith("DB_NAME="):
                        db_name = line.strip().split("=", 1)[1]
        c = MongoClient(mongo_url)
        qids = getattr(pytest, "_mod_quote_ids", [])
        cids = getattr(pytest, "_mod_contract_ids", [])
        if qids:
            c[db_name].crm2_quotes.delete_many({"id": {"$in": qids}})
        if cids:
            c[db_name].mod_service_contracts.delete_many({"id": {"$in": cids}})
        c.close()
    except Exception as e:
        print(f"cleanup skipped: {e}")
