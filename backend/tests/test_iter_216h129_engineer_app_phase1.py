"""Iter 216h129 — Engineer App Phase 1.

Validates the new Engineer Home v2 dashboard endpoint and the full
engineer-side Quote workflow (create → patch → PDF → mark → convert).
"""
import os
import uuid

import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or
       "https://platform-doctor.preview.emergentagent.com").rstrip("/")


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def test_engineer_dashboard_shape():
    """Engineer dashboard returns the expected KPIs + lists."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/svc/engineer/dashboard",
                     headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "kpis" in j
    for k in ("today_jobs", "upcoming_jobs", "overdue_jobs",
              "awaiting_parts", "awaiting_customer",
              "quote_pending", "quote_accepted", "quote_invoiced",
              "earnings_this_month", "notifications_unread"):
        assert k in j["kpis"], f"missing kpi: {k}"
    assert isinstance(j["today_jobs"], list)
    assert isinstance(j["pending_quotes"], list)


def test_engineer_quote_lifecycle():
    """create → list → patch → totals recomputation → mark accepted."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    # Create
    create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={
            "customer_name": "Test Customer", "customer_email": "test+quote@example.com",
            "description_of_work": "Treadmill belt replacement",
            "lines": [
                {"kind": "labour", "description": "2hr engineer labour", "quantity": 2, "unit_price": 75},
                {"kind": "part", "description": "Belt", "quantity": 1, "unit_price": 260},
            ],
            "vat_rate": 20, "discount_pct": 0, "valid_days": 30,
        },
    )
    assert create.status_code == 201, create.text
    quote = create.json()
    qid = quote["id"]
    assert quote["quote_number"].startswith("EQ-")
    # subtotal 150+260 = 410, VAT 82 = total 492
    assert quote["subtotal"] == 410.0
    assert quote["vat_amount"] == 82.0
    assert quote["total"] == 492.0
    assert quote["status"] == "draft"

    # List + filter
    listing = requests.get(f"{API}/api/svc/engineer/quotes?status=draft",
                            headers=_hdr(tok), timeout=20)
    assert listing.status_code == 200
    assert any(q["id"] == qid for q in listing.json()["quotes"])

    # Patch — add line and discount
    patch = requests.patch(
        f"{API}/api/svc/engineer/quotes/{qid}",
        headers=_hdr(tok), timeout=20,
        json={"discount_pct": 10,
              "lines": [
                  {"kind": "labour", "description": "2hr engineer labour", "quantity": 2, "unit_price": 75},
                  {"kind": "part", "description": "Belt", "quantity": 1, "unit_price": 260},
                  {"kind": "travel", "description": "Travel", "quantity": 40, "unit_price": 0.50},
              ]},
    )
    assert patch.status_code == 200, patch.text
    fresh = patch.json()
    # New subtotal: 150+260+20 = 430; -10% = 387; VAT 77.4; total 464.4
    assert fresh["subtotal"] == 430.0
    assert fresh["discount_amount"] == 43.0
    assert fresh["vat_amount"] == 77.4
    assert fresh["total"] == 464.4

    # Mark accepted
    mark = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/mark",
                         headers=_hdr(tok), timeout=20,
                         json={"status": "accepted", "note": "customer confirmed via phone"})
    assert mark.status_code == 200, mark.text
    assert mark.json()["status"] == "accepted"
    assert mark.json().get("accepted_at")


def test_engineer_quote_pdf():
    """PDF endpoint returns a real PDF byte stream."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={
            "customer_name": "PDF Test",
            "description_of_work": "Belt change",
            "lines": [{"kind": "labour", "description": "Visit", "quantity": 1, "unit_price": 100}],
        },
    )
    qid = create.json()["id"]
    pdf = requests.get(f"{API}/api/svc/engineer/quotes/{qid}.pdf",
                       headers=_hdr(tok), timeout=30)
    assert pdf.status_code == 200, pdf.text[:200]
    assert pdf.headers.get("content-type", "").startswith("application/pdf"), pdf.headers
    body = pdf.content
    assert body[:4] == b"%PDF"
    assert body[-6:].strip() == b"%%EOF"
    assert len(body) > 2000


def test_engineer_quote_locks_edit_after_accept():
    """Once accepted, lines can't be edited (409)."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    qid = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Lock Test",
              "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 50}]},
    ).json()["id"]
    requests.post(f"{API}/api/svc/engineer/quotes/{qid}/mark",
                  headers=_hdr(tok), timeout=20,
                  json={"status": "accepted"})
    bad = requests.patch(f"{API}/api/svc/engineer/quotes/{qid}",
                         headers=_hdr(tok), timeout=20,
                         json={"discount_pct": 99})
    assert bad.status_code == 409, bad.text


def test_engineer_quote_convert_to_job():
    """Accepted quote converts to a new svc_case."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Convert Test", "customer_email": "convert@example.com",
              "site_name": "Convert Site",
              "asset_name": "Treadmill", "asset_serial": "ABC123",
              "description_of_work": "Big motor swap",
              "lines": [{"kind": "labour", "description": "labour", "quantity": 4, "unit_price": 80}]},
    )
    qid = create.json()["id"]
    requests.post(f"{API}/api/svc/engineer/quotes/{qid}/mark",
                  headers=_hdr(tok), timeout=20, json={"status": "accepted"})
    conv = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/convert-to-job",
                         headers=_hdr(tok), timeout=20)
    assert conv.status_code == 200, conv.text
    data = conv.json()
    assert data["success"] is True
    assert data["case_id"]
    assert data["case_reference"].startswith("SC-")
    # Second attempt should 409 (already converted)
    conv2 = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/convert-to-job",
                          headers=_hdr(tok), timeout=20)
    assert conv2.status_code == 409


def test_engineer_quote_duplicate():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    create = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "Dup Test",
              "lines": [{"kind": "labour", "description": "a", "quantity": 1, "unit_price": 1}]},
    )
    qid = create.json()["id"]
    orig_number = create.json()["quote_number"]
    dup = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/duplicate",
                        headers=_hdr(tok), timeout=20)
    assert dup.status_code == 200, dup.text
    assert dup.json()["id"] != qid
    assert dup.json()["quote_number"] != orig_number
    assert dup.json()["status"] == "draft"


def test_engineer_quote_invalid_status_rejected():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    qid = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "x",
              "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 1}]},
    ).json()["id"]
    bad = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/mark",
                        headers=_hdr(tok), timeout=20,
                        json={"status": "garbage"})
    assert bad.status_code == 400


def test_engineer_quote_send_requires_email():
    """Send call with no recipient (and no customer_email saved) must 400."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    qid = requests.post(
        f"{API}/api/svc/engineer/quotes", headers=_hdr(tok), timeout=20,
        json={"customer_name": "NoMail",  # intentionally no email
              "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 1}]},
    ).json()["id"]
    bad = requests.post(f"{API}/api/svc/engineer/quotes/{qid}/send",
                        headers=_hdr(tok), timeout=20, json={})
    assert bad.status_code == 400, bad.text
