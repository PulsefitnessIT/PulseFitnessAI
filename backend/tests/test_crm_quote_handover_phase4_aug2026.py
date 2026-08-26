"""CRM · CPQ v2 Handover & Close (Equipment Sales Phase 4).

Covers routes/crm_quote_handover.py:
  GET  /api/crm/v2/quotes/{id}/handover
  POST /api/crm/v2/quotes/{id}/handover/jobs   (auto / explicit)
  POST /api/crm/v2/quotes/{id}/complete        (+ force)
  POST /api/crm/v2/quotes/{id}/reopen
"""
import os

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"
V2 = f"{BASE}/api/crm/v2"
SUPPLIER = "Pulse Fitness Ltd"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/crm/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"CRM login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def app_client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"App login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no app token: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_quote_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_quote_ids):
    yield
    from pymongo import MongoClient
    be = dotenv_values("/app/backend/.env")
    mc = MongoClient(be["MONGO_URL"])
    sdb = mc[be["DB_NAME"]]
    for qid in created_quote_ids:
        sdb.crm2_quotes.delete_many({"id": qid})
        sdb.purchase_orders.delete_many({"quote_id": qid})
        sdb.equipment.delete_many({"quote_id": qid})
        sdb.crm2_invoices.delete_many({"quote_id": qid})
        sdb.issues.delete_many({"quote_id": qid})
        sdb.svc_cases.delete_many({"quote_id": qid})
    mc.close()


def _new_quote(client, created_quote_ids, note="TEST_handover_phase4"):
    r = client.post(f"{V2}/quotes", json={
        "notes": note,
        "vat_rate": 0,
        "lines": [
            {"description": "TEST_ Treadmill H1", "line_type": "sale", "quantity": 1,
             "unit_price": 5000, "cost_price": 3000, "manufacturer": "Pulse",
             "model": "H1", "discount": 0},
        ],
    }, timeout=60)
    assert r.status_code in (200, 201), f"create quote failed {r.status_code}: {r.text[:400]}"
    q = r.json().get("quote") or r.json()
    qid = q.get("id")
    assert qid
    created_quote_ids.append(qid)
    return qid


# ── Happy-path lifecycle: not ready → jobs → deliver+invoice → complete → reopen
class TestHandoverLifecycle:
    def test_full_lifecycle(self, client, app_client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids)

        # 1. Initial handover view — not ready, both reasons, 1 suggestion
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        assert r.status_code == 200, r.text[:400]
        v = r.json()
        comp = v["completion"]
        assert comp["deal_status"] == "open", comp
        assert comp["ready"] is False
        joined = " | ".join(comp["reasons"]).lower()
        assert "not fully invoiced" in joined, comp["reasons"]
        assert "not fully delivered" in joined, comp["reasons"]
        assert comp["invoiced_ok"] is False and comp["delivered_ok"] is False
        assert v["jobs"] == []
        assert len(v["suggestions"]) == 1, v["suggestions"]
        assert v["suggestions"][0]["case_type"] == "install"

        # 2. Complete before ready → 400
        r = client.post(f"{V2}/quotes/{qid}/complete", json={}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

        # 3. Auto-create install jobs
        r = client.post(f"{V2}/quotes/{qid}/handover/jobs", json={"auto": True}, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        b = r.json()
        assert len(b["created"]) == 1, b["created"]
        job = b["created"][0]
        assert job["case_type"] == "install", job
        assert len(b["jobs"]) == 1
        job_id = job["id"]

        # 3b. Job is a real Operations job (db.issues) visible via /api/issues
        r = app_client.get(f"{BASE}/api/issues", timeout=60)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        rows = payload if isinstance(payload, list) else (payload.get("issues") or payload.get("items") or [])
        mine = [i for i in rows if i.get("id") == job_id]
        assert mine, f"handover job {job_id} not found in /api/issues ({len(rows)} rows)"
        assert mine[0].get("quote_id") == qid
        assert "_id" not in mine[0]

        # 4. DELIVER — raise PO then receive with serial
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders",
                        json={"supplier_name": SUPPLIER, "vat_rate": 0}, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        po = r.json()["purchase_order"]
        eq_line = next(i["line_id"] for i in po["items"] if i["is_equipment"])
        r = client.post(f"{V2}/quotes/{qid}/purchase-orders/{po['id']}/receive",
                        json={"items": [{"line_id": eq_line, "received_qty": 1,
                                         "serials": ["TEST_SN-H1-001"]}]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert len(r.json()["created_equipment"]) == 1

        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        comp = r.json()["completion"]
        assert comp["delivered_ok"] is True, comp
        assert comp["ready"] is False, "must still be blocked on invoicing"

        # 5. INVOICE — 100% final stage
        r = client.post(f"{V2}/quotes/{qid}/schedule/auto",
                        json={"deposit_percent": 0, "final_percent": 100}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        stages = r.json()["stages"]
        assert len(stages) == 1, stages
        sid = stages[0]["id"]
        r = client.post(f"{V2}/quotes/{qid}/stages/{sid}/invoice", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]

        # 6. Ready = true
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        comp = r.json()["completion"]
        assert comp["invoiced_ok"] is True, comp
        assert comp["delivered_ok"] is True, comp
        assert comp["ready"] is True, comp
        assert comp["reasons"] == [], comp["reasons"]

        # 7. Complete
        r = client.post(f"{V2}/quotes/{qid}/complete", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        comp = r.json()["completion"]
        assert comp["deal_status"] == "completed", comp
        assert comp["completed_at"], comp

        # 7b. Double complete → 400
        r = client.post(f"{V2}/quotes/{qid}/complete", json={}, timeout=60)
        assert r.status_code == 400, r.status_code

        # 8. Reopen
        r = client.post(f"{V2}/quotes/{qid}/reopen", json={}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["completion"]["deal_status"] == "open"
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        assert r.json()["completion"]["deal_status"] == "open"


# ── Force path ────────────────────────────────────────────────────
class TestForceComplete:
    def test_force_complete_not_ready(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids, "TEST_handover_force")
        r = client.post(f"{V2}/quotes/{qid}/complete",
                        json={"force": True, "reason": "customer collected"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        comp = r.json()["completion"]
        assert comp["deal_status"] == "completed", comp

        from pymongo import MongoClient
        be = dotenv_values("/app/backend/.env")
        mc = MongoClient(be["MONGO_URL"])
        doc = mc[be["DB_NAME"]].crm2_quotes.find_one({"id": qid}, {"_id": 0})
        mc.close()
        assert doc.get("deal_completed_forced") is True, doc.get("deal_completed_forced")
        assert doc.get("deal_completed_reason") == "customer collected", doc.get("deal_completed_reason")


# ── Explicit job creation + guards ────────────────────────────────
class TestJobsAndGuards:
    def test_explicit_job_creation(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids, "TEST_handover_explicit")
        r = client.post(f"{V2}/quotes/{qid}/handover/jobs", json={
            "jobs": [{"case_type": "ppm", "title": "TEST_ PPM visit"}]}, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        created = r.json()["created"]
        assert len(created) == 1 and created[0]["case_type"] == "ppm", created
        assert created[0]["machine_type"] == "TEST_ PPM visit", created

        # persisted on the handover view
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        jobs = r.json()["jobs"]
        assert len(jobs) == 1 and jobs[0]["case_type"] == "ppm", jobs

    def test_invalid_case_type_falls_back_to_install(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids, "TEST_handover_badtype")
        r = client.post(f"{V2}/quotes/{qid}/handover/jobs", json={
            "jobs": [{"case_type": "bogus", "title": "TEST_ Bogus"}]}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        assert r.json()["created"][0]["case_type"] == "install"

    def test_no_jobs_payload_rejected(self, client, created_quote_ids):
        qid = _new_quote(client, created_quote_ids, "TEST_handover_nojobs")
        r = client.post(f"{V2}/quotes/{qid}/handover/jobs", json={}, timeout=60)
        assert r.status_code in (400, 422), f"{r.status_code}: {r.text[:200]}"

    def test_unknown_quote_404(self, client):
        r = client.get(f"{V2}/quotes/no-such-quote-xyz/handover", timeout=60)
        assert r.status_code == 404, r.status_code
        r = client.post(f"{V2}/quotes/no-such-quote-xyz/complete", json={}, timeout=60)
        assert r.status_code == 404, r.status_code
        r = client.post(f"{V2}/quotes/no-such-quote-xyz/reopen", json={}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unauthenticated_rejected(self):
        for path, method in (("handover", "get"), ("complete", "post"), ("reopen", "post")):
            fn = getattr(requests, method)
            r = fn(f"{V2}/quotes/anything/{path}", timeout=60) if method == "get" else fn(
                f"{V2}/quotes/anything/{path}", json={}, timeout=60)
            assert r.status_code in (401, 403), f"{path}: {r.status_code}"

    def test_open_jobs_do_not_block_completion(self, client, created_quote_ids):
        """Open linked jobs are informational only — completion must not be blocked
        by them (jobs_ok false but ready driven by delivered+invoiced)."""
        qid = _new_quote(client, created_quote_ids, "TEST_handover_openjobs")
        client.post(f"{V2}/quotes/{qid}/handover/jobs", json={"auto": True}, timeout=60)
        r = client.get(f"{V2}/quotes/{qid}/handover", timeout=60)
        comp = r.json()["completion"]
        assert comp["open_job_count"] >= 1, comp
        assert comp["jobs_ok"] is False, comp
        assert all("job" not in x.lower() for x in comp["reasons"]), comp["reasons"]
