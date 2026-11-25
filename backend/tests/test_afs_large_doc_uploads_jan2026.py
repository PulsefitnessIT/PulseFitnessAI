"""Large Aftersales document uploads (Jan 2026): chunked upload protocol, background import / pricing jobs,
org isolation, renewal-email gate, Maintenance Master reason rules, MOD chase dispatch guards.
Synthetic TEST_ data only. No live emails (renewal live switch off; MOD send_email mocked)."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import asyncio
import hashlib
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(REPO + "/backend/.env")
load_dotenv(REPO + "/frontend/.env")
sys.path.insert(0, REPO + "/backend")
sys.path.insert(0, REPO + "/backend/tests/fixtures")
from utils.auth import create_token  # noqa: E402
from afs_large_docs import big_invoice_pdf, tender_csv  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
AFS = f"{API}/crm/v2/aftersales"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
CHUNK = 1024 * 1024
T = f"TEST_lg_{uuid.uuid4().hex[:6]}"
CREATED = {"files": [], "imports": [], "jobs": [], "contracts": [], "companies": [], "contacts": [], "groups": [],
           "quotes": [], "followups": [], "sessions": []}


def _main(uid):
    return {"Authorization": f"Bearer {create_token(uid)}"}


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers=_main(uid), timeout=30)
    if r.status_code != 200:
        return None, r
    return {"Authorization": f"Bearer {r.json()['token']}"}, r


@pytest.fixture(scope="module")
def coord():
    h, r = _crm("cm-test-coord")
    assert h, r.text
    return h


@pytest.fixture(scope="module")
def admin():
    h, r = _crm("cm-test-admin")
    assert h, r.text
    return h


def chunk_upload(uid, data, name, sha=None, stop_after=None, ct="application/pdf"):
    hdr = _main(uid)
    n = (len(data) + CHUNK - 1) // CHUNK
    r = requests.post(f"{API}/files/upload/chunks/init", headers=hdr, timeout=30, json={
        "filename": name, "size": len(data), "content_type": ct, "category": "contracts", "total_chunks": n,
        **({"sha256": sha} if sha else {})})
    assert r.status_code == 200, r.text
    uid_ = r.json()["upload_id"]
    CREATED["sessions"].append(uid_)
    for i in range(n if stop_after is None else stop_after):
        p = requests.put(f"{API}/files/upload/chunks/{uid_}/{i}", data=data[i * CHUNK:(i + 1) * CHUNK],
                         headers={**hdr, "Content-Type": "application/octet-stream"}, timeout=60)
        assert p.status_code == 200, p.text
    return uid_, n


def complete(uid, upload_id):
    r = requests.post(f"{API}/files/upload/chunks/{upload_id}/complete", headers=_main(uid), timeout=90)
    if r.status_code == 200:
        CREATED["files"].append(r.json()["id"])
    return r


def poll(h, job_id, limit=240):
    t0 = time.time()
    while time.time() - t0 < limit:
        r = requests.get(f"{AFS}/build-quote/jobs/{job_id}", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("done", "failed"):
            return r.json()
        time.sleep(4)
    pytest.fail("job did not finish")


PDF = big_invoice_pdf(tag=T[-6:])
PDF_SHA = hashlib.sha256(PDF).hexdigest()
STATE = {}


# ---------- Root cause + chunk protocol ----------
class TestChunkProtocol:
    def test_legacy_direct_upload_over_2mib_is_413(self, coord):
        r = requests.post(f"{AFS}/build-quote/imports", headers=coord, timeout=60,
                          data={"doc_type": "sales_invoice"}, files={"file": ("TEST_big.pdf", PDF, "application/pdf")})
        assert r.status_code == 413, r.status_code

    def test_resume_after_partial_then_idempotent_complete(self):
        upload_id, n = chunk_upload("cm-test-coord", PDF, f"{T}_invoice.pdf", sha=PDF_SHA, stop_after=1)
        st = requests.get(f"{API}/files/upload/chunks/{upload_id}/status", headers=_main("cm-test-coord"), timeout=30).json()
        assert st["received_chunks"] == 1 and st["missing"] == list(range(1, n))
        early = complete("cm-test-coord", upload_id)
        assert early.status_code == 400 and "Missing chunks" in early.text
        hdr = {**_main("cm-test-coord"), "Content-Type": "application/octet-stream"}
        for i in st["missing"]:
            assert requests.put(f"{API}/files/upload/chunks/{upload_id}/{i}", data=PDF[i * CHUNK:(i + 1) * CHUNK],
                                headers=hdr, timeout=60).status_code == 200
        r1 = complete("cm-test-coord", upload_id)
        assert r1.status_code == 200, r1.text
        f = r1.json()
        assert f["content_hash"] == PDF_SHA and f["size"] == len(PDF) or f["original_size"] == len(PDF)
        r2 = complete("cm-test-coord", upload_id)
        assert r2.status_code == 200 and r2.json()["id"] == f["id"]
        assert mdb.files.count_documents({"id": f["id"]}) == 1
        assert mdb.files.count_documents({"upload_method": "chunked", "content_hash": PDF_SHA, "user_id": "cm-test-coord",
                                          "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}}) == 1
        STATE["file_id"] = f["id"]

    def test_wrong_sha256_fails_integrity(self):
        upload_id, _ = chunk_upload("cm-test-coord", PDF, f"{T}_bad.pdf", sha="0" * 64)
        r = complete("cm-test-coord", upload_id)
        assert r.status_code == 400 and "integrity" in r.text.lower(), r.text


# ---------- Background import ----------
class TestImportJob:
    def test_import_from_file_reads_all_lines(self, coord):
        assert STATE.get("file_id")
        r = requests.post(f"{AFS}/build-quote/imports/from-file", headers=coord, timeout=60,
                          json={"file_id": STATE["file_id"], "doc_type": "sales_invoice"})
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("job_id"):
            CREATED["jobs"].append(body["job_id"])
            again = requests.post(f"{AFS}/build-quote/imports/from-file", headers=coord, timeout=60,
                                  json={"file_id": STATE["file_id"], "doc_type": "sales_invoice"}).json()
            assert again.get("job_id") in (body["job_id"], None)
            j = poll(coord, body["job_id"])
            assert j["status"] == "done", j
            imp = j["import"]
        else:
            imp = body["import"]
        CREATED["imports"].append(imp["id"])
        STATE["import_id"] = imp["id"]
        lines = imp["lines"]
        qty = sum(float(ln.get("quantity") or ln.get("qty") or 0) for ln in lines)
        print("lines", len(lines), "qty", qty, "coverage", imp.get("coverage"))
        assert len(lines) == 400, len(lines)
        assert imp.get("coverage")
        # Every printed row says 'Qty 2' — the extractor must copy it, not 'fix' it to the serial count.
        assert qty == 800, f"quantities altered by extraction: total {qty} (expected 800)"

    def test_reimport_same_file_is_existing(self, coord):
        assert STATE.get("import_id")
        r = requests.post(f"{AFS}/build-quote/imports/from-file", headers=coord, timeout=60,
                          json={"file_id": STATE["file_id"], "doc_type": "sales_invoice"})
        assert r.status_code == 200
        assert r.json()["import"]["existing"] is True and r.json()["import"]["id"] == STATE["import_id"]
        assert mdb.crm2_afs_quote_imports.count_documents({"organization_id": OP, "sha256": PDF_SHA}) == 1


# ---------- Security ----------
class TestSecurity:
    def test_other_org_file_id_is_404(self, coord):
        small = b"%PDF-1.4\n" + os.urandom(2000) + b"\n%%EOF"
        up, _ = chunk_upload("iso-owner", small, f"{T}_iso.pdf")
        r = complete("iso-owner", up)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        a = requests.post(f"{AFS}/build-quote/imports/from-file", headers=coord, json={"file_id": fid, "doc_type": "sales_invoice"}, timeout=30)
        b = requests.post(f"{AFS}/extract-pricing-jobs", params={"file_id": fid}, headers=coord, timeout=30)
        assert a.status_code == 404 and b.status_code == 404, (a.text, b.text)

    def test_other_org_job_is_404(self):
        job = mdb.crm2_afs_doc_jobs.find_one({"organization_id": OP}, {"_id": 0, "id": 1})
        h, r = _crm("iso-owner")
        if not h:
            pytest.skip(f"iso owner has no CRM: {r.status_code}")
        g = requests.get(f"{AFS}/build-quote/jobs/{job['id']}", headers=h, timeout=30)
        assert g.status_code in (403, 404), g.status_code
        print("iso owner job status code", g.status_code)

    def test_no_quotes_maintenance_is_403(self):
        h, r = _crm("cm-test-sales")
        if h:
            g = requests.post(f"{AFS}/build-quote/imports/from-file", headers=h, json={"file_id": "x", "doc_type": "sales_invoice"}, timeout=30)
            assert g.status_code == 403
        h2, r2 = _crm("cm-test-none")
        if h2:
            assert requests.get(f"{AFS}/build-quote/jobs/x", headers=h2, timeout=30).status_code == 403
        else:
            assert r2.status_code in (401, 403)


# ---------- Pricing extraction job (real LLM, one call set) ----------
class TestPricingJob:
    def test_csv_700_rows_all_service_prices(self, coord):
        csv = tender_csv(700)
        up, _ = chunk_upload("cm-test-coord", csv, f"{T}_tender.csv", ct="text/csv")
        r = complete("cm-test-coord", up)
        assert r.status_code == 200, r.text
        s = requests.post(f"{AFS}/extract-pricing-jobs", params={"file_id": r.json()["id"]}, headers=coord, timeout=30)
        assert s.status_code == 200, s.text
        CREATED["jobs"].append(s.json()["job_id"])
        j = poll(coord, s.json()["job_id"], limit=400)
        assert j["status"] == "done", j
        res = j["result"]
        print("svc", len(res.get("machine_services") or []), "travel", len(res.get("travel") or []),
              "repairs", len(res.get("repairs") or []), "coverage", res.get("coverage"))
        assert len(res["machine_services"]) == 700
        assert len(res.get("travel") or []) == 20


# ---------- Renewal email gate ----------
class TestRenewalGate:
    @pytest.fixture(scope="class", autouse=True)
    def seed(self):
        co, ct, prev, ren = f"{T}_co", f"{T}_ct", f"{T}_prev", f"{T}_ren"
        mdb.crm2_companies.insert_one({"id": co, "organization_id": OP, "name": f"{T} Leisure", "email": "test.renewal@example.test"})
        mdb.crm2_contacts.insert_one({"id": ct, "organization_id": OP, "company_id": co, "email": "test.renewal@example.test", "name": "TEST"})
        end = (date.today() + timedelta(days=40)).isoformat()
        mdb.crm2_contracts.insert_many([
            {"id": prev, "organization_id": OP, "company_id": co, "status": "active", "contract_number": f"{T}-1",
             "annual_value": 1000, "end_date": end, "title": f"{T} contract"},
            {"id": ren, "organization_id": OP, "company_id": co, "status": "renewal_pending_approval", "previous_contract_id": prev,
             "contract_number": f"{T}-1/R2", "annual_value": 1000, "renewal_uplift_percent": 0, "title": f"{T} renewal"}])
        CREATED["companies"].append(co); CREATED["contacts"].append(ct); CREATED["contracts"] += [prev, ren]  # noqa: E702
        STATE["ren"] = ren
        yield

    def test_approve_queues_no_email(self, coord):
        r = requests.post(f"{API}/crm/workspace/renewals/{STATE['ren']}/approve-send", headers=coord, json={}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["email_delivered"] is False and r.json()["comms_status"] == "awaiting_dispatch"
        d = mdb.crm2_contracts.find_one({"id": STATE["ren"]})
        assert d["renewal_comms_status"] == "awaiting_dispatch" and d["renewal_email_state"] == "awaiting_dispatch"
        assert mdb.email_logs.count_documents({"to": "test.renewal@example.test"}) == 0 if "email_logs" in mdb.list_collection_names() else True

    def test_renewals_list_shows_queued_state(self, coord):
        r = requests.get(f"{API}/crm/workspace/renewals", headers=coord, timeout=30)
        assert r.status_code == 200
        row = next(x for x in r.json()["renewals"] if x["id"] == STATE["ren"])
        print("list comms_status:", row["comms_status"], row["comms_label"])
        assert row["comms_status"] == "awaiting_dispatch", row["comms_label"]

    def test_resend_409_when_off(self, coord):
        r = requests.post(f"{API}/crm/workspace/renewals/{STATE['ren']}/resend", headers=coord, timeout=30)
        assert r.status_code == 409 and "switched off" in r.text

    def test_cancel_email_needs_approve_perm_and_reason(self, coord, admin):
        assert requests.post(f"{API}/crm/workspace/renewals/{STATE['ren']}/cancel-email", headers=coord, json={"reason": "TEST stop"}, timeout=30).status_code == 403
        assert requests.post(f"{API}/crm/workspace/renewals/{STATE['ren']}/cancel-email", headers=admin, json={}, timeout=30).status_code == 422
        r = requests.post(f"{API}/crm/workspace/renewals/{STATE['ren']}/cancel-email", headers=admin, json={"reason": "TEST customer asked"}, timeout=30)
        assert r.status_code == 200, r.text
        assert mdb.crm2_contracts.find_one({"id": STATE["ren"]})["renewal_email_state"] == "cancelled"


# ---------- Maintenance Master reason rule ----------
class TestMMEditReason:
    @pytest.fixture(scope="class", autouse=True)
    def seed(self):
        cid = f"{T}_mm"
        mdb.crm2_contracts.insert_one({"id": cid, "organization_id": OP, "status": "active", "contract_number": f"{T}-MM",
                                       "mm_record_key": f"{T}_key", "revision": 1, "annual_value": 500, "start_date": "2025-01-01",
                                       "end_date": "2026-12-31", "payment_frequency": "Annual", "visits_per_year": 2,
                                       "mm": {"comments": "old"}})
        CREATED["contracts"].append(cid)
        STATE["mm"] = cid
        yield

    @pytest.mark.parametrize("field,val", [("start_date", "2025-02-01"), ("end_date", "2027-01-31"), ("annual_value", 650),
                                           ("payment_frequency", "Monthly"), ("direct_debit", "Yes"), ("visits_per_year", 4)])
    def test_substantive_without_reason_422(self, coord, field, val):
        rev = mdb.crm2_contracts.find_one({"id": STATE["mm"]})["revision"]
        r = requests.patch(f"{AFS}/maintenance-master/contracts/{STATE['mm']}", headers=coord, timeout=30,
                           json={"revision": rev, "changes": {field: val}, "reason": "abc"})
        assert r.status_code == 422, (field, r.status_code, r.text)

    def test_sicon_id_without_reason_rejected(self, admin):
        rev = mdb.crm2_contracts.find_one({"id": STATE["mm"]})["revision"]
        r = requests.patch(f"{AFS}/maintenance-master/contracts/{STATE['mm']}", headers=admin, timeout=30,
                           json={"revision": rev, "changes": {"sicon_contract_id": "TEST-SIC-1"}})
        assert r.status_code == 422, r.text

    def test_comments_only_ok_and_history(self, coord):
        r = requests.patch(f"{AFS}/maintenance-master/contracts/{STATE['mm']}", headers=coord, timeout=30,
                           json={"revision": 1, "changes": {"comments": "TEST new comment"}})
        assert r.status_code == 200, r.text
        r2 = requests.patch(f"{AFS}/maintenance-master/contracts/{STATE['mm']}", headers=coord, timeout=30,
                            json={"revision": 2, "changes": {"annual_value": 700}, "reason": "TEST agreed uplift"})
        assert r2.status_code == 200, r2.text
        c = mdb.crm2_contracts.find_one({"id": STATE["mm"]})
        assert c["revision"] == 3 and c["annual_value"] == 700 and c["mm"]["comments"] == "TEST new comment"
        ch = list(mdb.crm2_contract_changes.find({"contract_id": STATE["mm"]}))
        assert {x["field"] for x in ch} == {"comments", "annual_value"}
        assert any(x["reason"] == "TEST agreed uplift" for x in ch)


# ---------- MOD chase dispatch guards (send_email mocked; never live) ----------
class TestModChaseDispatch:
    def test_expired_or_changed_address_not_sent(self, monkeypatch):
        if mdb.mod_quote_followups.count_documents({"email_status": "ready"}):
            pytest.skip("real ready follow-ups exist — dispatcher is global, not running it")
        g1, g2 = f"{T}_g1", f"{T}_g2"
        yesterday, future = (date.today() - timedelta(days=1)).isoformat(), (date.today() + timedelta(days=20)).isoformat()
        for g, to in ((g1, "a@example.test"), (g2, "changed@example.test")):
            mdb.mod_quote_groups.insert_one({"id": g, "organization_id": OP, "status": "published", "revision": 1,
                                             "customer": {"contact_email": to}, "created_by": "cm-test-coord"})
        mdb.crm2_quotes.insert_many([
            {"id": f"{g1}_q", "mod_group_id": g1, "customer_visible": True, "valid_until": yesterday, "status": "sent", "organization_id": OP},
            {"id": f"{g2}_q", "mod_group_id": g2, "customer_visible": True, "valid_until": future, "status": "sent", "organization_id": OP}])
        mdb.mod_quote_followups.insert_many([
            {"id": f"{g1}_f", "group_id": g1, "revision": 1, "chase_no": 1, "email_status": "ready", "contact_email": "a@example.test", "email_attempts": 0},
            {"id": f"{g2}_f", "group_id": g2, "revision": 1, "chase_no": 1, "email_status": "ready", "contact_email": "orig@example.test", "email_attempts": 0}])
        CREATED["groups"] += [g1, g2]; CREATED["quotes"] += [f"{g1}_q", f"{g2}_q"]; CREATED["followups"] += [f"{g1}_f", f"{g2}_f"]  # noqa: E702
        sent = []

        async def fake_send(*a, **k):
            sent.append(a)
            return False
        import utils.email
        monkeypatch.setattr(utils.email, "send_email", fake_send)
        from utils import mod_quote_chase
        from utils.database import client
        out = asyncio.get_event_loop().run_until_complete(mod_quote_chase.dispatch_ready(True, {"1": {}}))
        assert sent == [] and out["sent"] == 0
        f1, f2 = mdb.mod_quote_followups.find_one({"id": f"{g1}_f"}), mdb.mod_quote_followups.find_one({"id": f"{g2}_f"})
        assert f1["email_status"] == "not_applicable" and "expired" in f1["email_reason"]
        assert f2["email_status"] == "not_applicable" and "address" in f2["email_reason"]
        _ = client


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    mdb.files.delete_many({"id": {"$in": CREATED["files"]}})
    mdb.file_upload_sessions.delete_many({"id": {"$in": CREATED["sessions"]}})
    mdb.file_upload_chunks.delete_many({"upload_id": {"$in": CREATED["sessions"]}})
    mdb.crm2_afs_quote_imports.delete_many({"id": {"$in": CREATED["imports"]}})
    mdb.crm2_afs_doc_jobs.delete_many({"id": {"$in": CREATED["jobs"]}})
    mdb.crm2_contracts.delete_many({"id": {"$in": CREATED["contracts"]}})
    mdb.crm2_contract_changes.delete_many({"contract_id": {"$in": CREATED["contracts"]}})
    mdb.crm2_companies.delete_many({"id": {"$in": CREATED["companies"]}})
    mdb.crm2_contacts.delete_many({"id": {"$in": CREATED["contacts"]}})
    mdb.crm2_activities.delete_many({"organization_id": OP, "subject": {"$regex": f"^Renewal issued: {T}"}})
    mdb.mod_quote_groups.delete_many({"id": {"$in": CREATED["groups"]}})
    mdb.crm2_quotes.delete_many({"id": {"$in": CREATED["quotes"]}})
    mdb.mod_quote_followups.delete_many({"id": {"$in": CREATED["followups"]}})
