"""Iter 216h152 — SVC → CRM activity emit + service-revenue YTD tile.

Audits the new SVC ↔ CRM seam from the Feb 2026 process review:

  • Closing a service case writes a `service_visit` activity into
    crm2_activities and (best-effort) links to the matching company.
  • Finalising an invoice writes a `service_invoice` activity carrying
    amount_net + amount_gross in metadata.
  • `GET /api/crm/v2/service-revenue/ytd` aggregates the above into a
    top-line £ total, per-month split and top-5 companies.
  • Re-closing / re-finalising does NOT duplicate the activity row
    (idempotent on case_id+kind).
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def admin_sess():
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


@pytest.fixture
def crm_sess(admin_sess):
    """Exchange the main JWT for a CRM-scoped token via /crm/auth/cross-login.
    Returns a dict with {`token`, `user`} mirroring admin_sess shape."""
    r = requests.post(
        f"{API}/api/crm/auth/cross-login",
        headers=_hdr(admin_sess["token"]),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"],
            "user": {"organization_id": admin_sess["user"]["organization_id"]}}


def _seed_case(db, org_id, *, status: str, customer_name: str = "",
               customer_email: str = "", site_postcode: str = ""):
    case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": case_id,
        "organization_id": org_id,
        "reference": f"SR-{case_id[:5]}",
        "title": "SVC→CRM emit test",
        "status": status,
        "priority": "P2",
        "site_name": "Test Site",
        "site_postcode": site_postcode,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "assigned_engineer_id": None,
        "estimated_minutes": 60,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return case_id


def _seed_company(db, org_id, *, name: str, email: str = "",
                  postcode: str = ""):
    cid = str(uuid.uuid4())
    db["crm2_companies"].insert_one({
        "id": cid,
        "organization_id": org_id,
        "name": name,
        "email": email,
        "postcode": postcode,
        "type": "customer",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return cid


def _seed_quote(db, org_id, case_id, *, net: float, status: str = "approved"):
    qid = str(uuid.uuid4())
    db["svc_quotes"].insert_one({
        "id": qid,
        "organization_id": org_id,
        "case_id": case_id,
        "reference": f"Q-{qid[:5]}",
        "status": status,
        "net": net,
        "subtotal": net,
        "vat": round(net * 0.2, 2),
        "gross": round(net * 1.2, 2),
        "total": round(net * 1.2, 2),
        "lines": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return qid


# ── Case close → service_visit activity ─────────────────────────

def test_close_emits_service_visit_activity(admin_sess):
    tok = admin_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    company_id = _seed_company(db, org_id, name="Acme Gyms Ltd",
                               email="ops@acme.example",
                               postcode="N15 4QT")
    case_id = _seed_case(db, org_id, status="repaired",
                         customer_name="Acme Gyms Ltd",
                         site_postcode="N15 4QT")
    try:
        # Two-step legal transition: repaired → closed.
        r = requests.post(
            f"{API}/api/svc/cases/{case_id}/transition",
            headers=_hdr(tok), json={"to": "closed", "reason": "QA test"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Activity row must exist with case_id + company_id linkage.
        act = db["crm2_activities"].find_one(
            {"organization_id": org_id, "case_id": case_id,
             "type": "service_visit"},
        )
        assert act is not None, "service_visit activity must be emitted on close"
        assert act["company_id"] == company_id, "must link to matched CRM company"
        assert "Service visit closed" in (act.get("subject") or "")
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["crm2_activities"].delete_many({"case_id": case_id})
        db["crm2_companies"].delete_one({"id": company_id})


def test_close_without_matching_company_still_emits_activity(admin_sess):
    """No matching CRM company — activity should still be written
    (company_id null) so the timeline doesn't lose service history."""
    tok = admin_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="repaired",
                         customer_name="One-Off Customer No CRM Match")
    try:
        r = requests.post(
            f"{API}/api/svc/cases/{case_id}/transition",
            headers=_hdr(tok), json={"to": "closed"}, timeout=15,
        )
        assert r.status_code == 200, r.text
        act = db["crm2_activities"].find_one(
            {"organization_id": org_id, "case_id": case_id,
             "type": "service_visit"},
        )
        assert act is not None
        assert act.get("company_id") in (None, "")
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["crm2_activities"].delete_many({"case_id": case_id})


def test_close_idempotent_on_reclose(admin_sess):
    """Re-closing (e.g. via the rare CLOSED→? path or repeated webhook
    delivery) must NOT create duplicate activity rows — the upsert
    keys on (case_id, type)."""
    tok = admin_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    case_id = _seed_case(db, org_id, status="repaired",
                         customer_name="Idempotency QA")
    try:
        r1 = requests.post(
            f"{API}/api/svc/cases/{case_id}/transition",
            headers=_hdr(tok), json={"to": "closed"}, timeout=15,
        )
        assert r1.status_code == 200
        # CLOSED→INVOICED is the only legal forward transition, but the
        # state machine allows the no-op closed→closed silently
        # (returns the case unchanged). The CRM activity hook still
        # fires because the code checks `case.status == "closed"`.
        r2 = requests.post(
            f"{API}/api/svc/cases/{case_id}/transition",
            headers=_hdr(tok), json={"to": "closed"}, timeout=15,
        )
        # Even if 200/400, we must not have duplicate rows.
        count = db["crm2_activities"].count_documents(
            {"organization_id": org_id, "case_id": case_id,
             "type": "service_visit"},
        )
        assert count == 1, f"expected 1 service_visit row, got {count}"
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["crm2_activities"].delete_many({"case_id": case_id})


# ── Invoice finalise → service_invoice activity ─────────────────

def test_finalise_emits_service_invoice_with_amount(admin_sess):
    tok = admin_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    company_id = _seed_company(db, org_id, name="Revenue Gym Group")
    case_id = _seed_case(db, org_id, status="closed",
                         customer_name="Revenue Gym Group")
    _seed_quote(db, org_id, case_id, net=1234.56)
    try:
        r = requests.post(
            f"{API}/api/svc/billing/{case_id}/invoice/finalise",
            headers=_hdr(tok), timeout=20,
        )
        assert r.status_code == 200, r.text
        act = db["crm2_activities"].find_one(
            {"organization_id": org_id, "case_id": case_id,
             "type": "service_invoice"},
        )
        assert act is not None
        meta = act.get("metadata") or {}
        assert meta.get("amount_net") == 1234.56
        assert meta.get("amount_gross") == round(1234.56 * 1.2, 2)
        assert meta.get("currency") in (None, "GBP")
        assert act["company_id"] == company_id
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_case_events"].delete_many({"case_id": case_id})
        db["svc_quotes"].delete_many({"case_id": case_id})
        db["svc_sage_invoice_outbox"].delete_many({"case_id": case_id})
        db["crm2_activities"].delete_many({"case_id": case_id})
        db["crm2_companies"].delete_one({"id": company_id})


# ── Service-revenue-YTD tile aggregation ────────────────────────

def test_service_revenue_ytd_aggregates(admin_sess, crm_sess):
    tok = crm_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    company_id = _seed_company(db, org_id, name="YTD Test Gym")
    # Seed two service_invoice activities directly.
    seeded_ids = []
    for amt in (500.0, 250.0):
        aid = str(uuid.uuid4())
        case_id = str(uuid.uuid4())
        seeded_ids.append((aid, case_id))
        db["crm2_activities"].insert_one({
            "id": aid,
            "organization_id": org_id,
            "type": "service_invoice",
            "case_id": case_id,
            "company_id": company_id,
            "subject": f"Invoice {aid[:5]}",
            "metadata": {"amount_net": amt, "amount_gross": amt * 1.2,
                          "currency": "GBP"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    try:
        r = requests.get(
            f"{API}/api/crm/v2/service-revenue/ytd",
            headers=_hdr(tok), timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["currency"] == "GBP"
        assert body["total_net"] >= 750.0  # our two seeds, plus anything pre-existing
        # Confirm the company appears in the top-5 list.
        top_ids = [c["company_id"] for c in body["top_companies"]]
        assert company_id in top_ids
        # Per-month for current month carries at least our seed amounts.
        now_month = datetime.now(timezone.utc).month
        month_total = next(
            m["revenue_net"] for m in body["per_month"] if m["month"] == now_month
        )
        assert month_total >= 750.0
    finally:
        for aid, cid in seeded_ids:
            db["crm2_activities"].delete_one({"id": aid})
        db["crm2_companies"].delete_one({"id": company_id})


def test_service_revenue_ytd_scoped_to_company(admin_sess, crm_sess):
    tok = crm_sess["token"]
    org_id = admin_sess["user"]["organization_id"]
    db = _mongo()
    cid_a = _seed_company(db, org_id, name="Scope-A Gym")
    cid_b = _seed_company(db, org_id, name="Scope-B Gym")
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    db["crm2_activities"].insert_many([
        {"id": a, "organization_id": org_id, "type": "service_invoice",
         "case_id": str(uuid.uuid4()), "company_id": cid_a,
         "metadata": {"amount_net": 100.0},
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": b, "organization_id": org_id, "type": "service_invoice",
         "case_id": str(uuid.uuid4()), "company_id": cid_b,
         "metadata": {"amount_net": 200.0},
         "created_at": datetime.now(timezone.utc).isoformat()},
    ])
    try:
        r = requests.get(
            f"{API}/api/crm/v2/service-revenue/ytd",
            headers=_hdr(tok), params={"company_id": cid_a}, timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["scope"] == "company"
        # Only company A's £100 must appear.
        top_ids = [c["company_id"] for c in body["top_companies"]]
        assert cid_a in top_ids
        assert cid_b not in top_ids
    finally:
        db["crm2_activities"].delete_many({"id": {"$in": [a, b]}})
        db["crm2_companies"].delete_many({"id": {"$in": [cid_a, cid_b]}})
