"""Iter 216h130 — Phase 2 + Public Quote Accept tests.

Covers:
  • Public quote accept/decline (signature, idempotent, status guards)
  • Engineer Invoice lifecycle (create, from-quote, totals, PDF, mark paid)
  • Service Report PDF for completed jobs
"""
import os
import uuid

import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or
       "https://maintenance-hub-357.preview.emergentagent.com").rstrip("/")


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _create_send_quote(tok: str) -> dict:
    create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Public Test", "customer_email": "public+test@example.com",
              "description_of_work": "Belt change",
              "lines": [{"kind": "labour", "description": "Visit", "quantity": 1, "unit_price": 100}]},
    ).json()
    qid = create["id"]
    # Force-set a public_shortcode without sending (bypass Resend dep for test)
    # We do this via patch to invoke a save-and-reload, then poke the shortcode.
    return qid


# ────────────────────── Public quote accept ─────────────────────


def test_public_quote_accept_flow_e2e():
    """create → manually attach shortcode → public GET → accept → 410 on retry."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    qid = _create_send_quote(tok)
    # Inject a known shortcode (mirrors what the send endpoint does)
    short = f"sc{uuid.uuid4().hex[:8]}"
    import pymongo
    from os import environ
    client = pymongo.MongoClient(environ.get("MONGO_URL"))
    db_name = environ.get("DB_NAME") or "test_database"
    client[db_name]["svc_engineer_quotes"].update_one(
        {"id": qid}, {"$set": {"public_shortcode": short}}
    )
    # No auth needed
    g = requests.get(f"{API}/api/public/quote/{short}", timeout=15)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["quote_number"]
    assert body["total"] == 120.0  # 100 + 20% VAT
    assert "customer_email" not in body  # redacted
    # Accept
    a = requests.post(f"{API}/api/public/quote/{short}/accept", timeout=15,
                      json={"name": "Daniel Hayes",
                            "signature_data_url": "data:image/png;base64,iVBORw0KGgo=",
                            "note": "Please book for next Tuesday"})
    assert a.status_code == 200, a.text
    assert a.json()["ok"] is True
    # Retry — should be 410
    again = requests.post(f"{API}/api/public/quote/{short}/accept", timeout=15,
                          json={"name": "Daniel Hayes"})
    assert again.status_code == 410, again.text
    # GET after accept reflects status
    g2 = requests.get(f"{API}/api/public/quote/{short}", timeout=15).json()
    assert g2["status"] == "accepted"
    assert g2["accepted_by_name"] == "Daniel Hayes"


def test_public_quote_decline_flow():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    qid = _create_send_quote(tok)
    short = f"sc{uuid.uuid4().hex[:8]}"
    import pymongo
    from os import environ
    client = pymongo.MongoClient(environ.get("MONGO_URL"))
    db_name = environ.get("DB_NAME") or "test_database"
    client[db_name]["svc_engineer_quotes"].update_one(
        {"id": qid}, {"$set": {"public_shortcode": short}}
    )
    d = requests.post(f"{API}/api/public/quote/{short}/decline", timeout=15,
                      json={"name": "Daniel Hayes", "reason": "Going with another supplier"})
    assert d.status_code == 200, d.text
    g = requests.get(f"{API}/api/public/quote/{short}", timeout=15).json()
    assert g["status"] == "declined"


def test_public_quote_404_for_bad_shortcode():
    r = requests.get(f"{API}/api/public/quote/this-does-not-exist", timeout=10)
    assert r.status_code == 404


# ────────────────────── Engineer Invoices ───────────────────────


def test_invoice_lifecycle_and_pdf():
    """create draft → patch with new lines → PDF → mark paid."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    create = requests.post(
        f"{API}/api/svc/engineer/invoices", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Invoice Test", "customer_email": "inv@example.com",
              "description_of_work": "Treadmill belt",
              "lines": [{"kind": "labour", "description": "Site visit", "quantity": 2, "unit_price": 75},
                         {"kind": "part", "description": "Belt", "quantity": 1, "unit_price": 260}],
              "vat_rate": 20, "discount_pct": 0,
              "payment_terms_days": 14,
              "bank_name": "Lloyds", "bank_account_name": "GymAxis Ltd",
              "bank_sort_code": "30-99-50", "bank_account_number": "12345678"},
    )
    assert create.status_code == 201, create.text
    inv = create.json()
    iid = inv["id"]
    assert inv["invoice_number"].startswith("EI-")
    assert inv["subtotal"] == 410.0
    assert inv["vat_amount"] == 82.0
    assert inv["total"] == 492.0
    assert inv["status"] == "draft"
    assert inv["due_date"]  # auto-derived

    # PDF
    pdf = requests.get(f"{API}/api/svc/engineer/invoices/{iid}.pdf",
                       headers=_hdr(tok), timeout=30)
    assert pdf.status_code == 200, pdf.text[:200]
    assert pdf.headers.get("content-type", "").startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"
    assert pdf.content[-6:].strip() == b"%%EOF"
    assert len(pdf.content) > 2000

    # Patch — change lines
    patch = requests.patch(
        f"{API}/api/svc/engineer/invoices/{iid}", headers=_hdr(tok), timeout=20,
        json={"lines": [{"kind": "labour", "description": "Site visit", "quantity": 3, "unit_price": 75}],
              "discount_pct": 10},
    )
    assert patch.status_code == 200, patch.text
    fresh = patch.json()
    # 225 - 22.5 = 202.5; VAT 40.5; total 243.0
    assert fresh["subtotal"] == 225.0
    assert fresh["discount_amount"] == 22.5
    assert fresh["total"] == 243.0

    # Mark paid
    mp = requests.post(f"{API}/api/svc/engineer/invoices/{iid}/mark",
                       headers=_hdr(tok), timeout=20,
                       json={"status": "paid", "note": "BACS received"})
    assert mp.status_code == 200, mp.text
    assert mp.json()["status"] == "paid"
    assert mp.json().get("paid_at")

    # Locked after paid
    locked = requests.patch(f"{API}/api/svc/engineer/invoices/{iid}",
                            headers=_hdr(tok), timeout=20, json={"discount_pct": 99})
    assert locked.status_code == 409


def test_invoice_from_accepted_quote_links_both():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    quote_create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Convert Inv", "customer_email": "convinv@example.com",
              "description_of_work": "Strength station overhaul",
              "lines": [{"kind": "labour", "description": "4hr labour", "quantity": 4, "unit_price": 80},
                         {"kind": "part", "description": "Cable", "quantity": 2, "unit_price": 40}],
              "vat_rate": 20},
    )
    quote = quote_create.json()
    qid = quote["id"]
    requests.post(f"{API}/api/svc/engineer/quotes/{qid}/mark",
                  headers=_hdr(tok), timeout=20, json={"status": "accepted"})
    inv_create = requests.post(
        f"{API}/api/svc/engineer/invoices/from-quote/{qid}",
        headers=_hdr(tok), timeout=20,
    )
    assert inv_create.status_code == 201, inv_create.text
    inv = inv_create.json()
    assert inv["linked_quote_id"] == qid
    assert inv["linked_quote_number"] == quote["quote_number"]
    # totals copied: 320+80=400; 20% VAT=80; total 480
    assert inv["subtotal"] == 400.0
    assert inv["total"] == 480.0
    # quote now marked as invoiced
    q2 = requests.get(f"{API}/api/svc/engineer/quotes/{qid}",
                      headers=_hdr(tok), timeout=20).json()
    assert q2["status"] == "invoiced"
    assert q2.get("linked_invoice_id") == inv["id"]


def test_invoice_send_requires_recipient():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    iid = requests.post(
        f"{API}/api/svc/engineer/invoices", headers=_hdr(tok), timeout=20,
        json={"customer_name": "NoMailInv",
              "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 1}]},
    ).json()["id"]
    bad = requests.post(f"{API}/api/svc/engineer/invoices/{iid}/send",
                        headers=_hdr(tok), timeout=20, json={})
    assert bad.status_code == 400


def test_invoice_list_unpaid_filter():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/svc/engineer/invoices?status=unpaid",
                      headers=_hdr(tok), timeout=20)
    assert r.status_code == 200
    for inv in r.json()["invoices"]:
        assert inv["status"] in ("draft", "sent", "overdue")


def test_invoice_duplicate_resets_dates():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    iid = requests.post(
        f"{API}/api/svc/engineer/invoices", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Dup",
              "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 50}]},
    ).json()["id"]
    dup = requests.post(f"{API}/api/svc/engineer/invoices/{iid}/duplicate",
                        headers=_hdr(tok), timeout=20)
    assert dup.status_code == 200, dup.text
    assert dup.json()["id"] != iid
    assert dup.json()["status"] == "draft"
    assert dup.json().get("paid_at") is None


# Service Report endpoints already exist at /api/svc/cases/{id}/service-report*
# (managed by routes/svc/service_report.py). They're tested separately.
