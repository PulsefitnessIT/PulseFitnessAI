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
        hb = r.json().get("heartbeat_at")
        if hb and hb != STATE.get("last_hb_" + job_id) and r.json().get("started_at") != hb:
            STATE["beats"] = STATE.get("beats", 0) + 1
        STATE["last_hb_" + job_id] = hb
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
        # Stage A: every line verified against the printed text, serial + source page correct, no unexplained change
        import re as _re
        tag = T[-6:]
        bad_q = [ln["line_no"] for ln in lines if ln.get("quantity") != 2 or ln.get("qty_validation") not in ("verified", "corrected_from_source")]
        corrected = [ln for ln in lines if ln.get("qty_validation") == "corrected_from_source"]
        unexplained = [ln["line_no"] for ln in corrected if ln.get("quantity_ai") in (None, 2)]
        sers = [s for ln in lines for s in ln.get("serials") or []]
        want = {f"SN{tag}{n:05d}" for n in range(1, 401)}
        wrong_page = []
        for ln in lines:
            if len(ln.get("serials") or []) != 1:
                continue
            n = int(ln["serials"][0][-5:])
            pg = (n - 1) // 20 + 1
            nums = [int(x) for x in _re.findall(r"\d+", ln.get("source") or "")]
            if nums and not (min(nums) <= pg <= max(nums)):
                wrong_page.append((ln["line_no"], ln["source"], pg))
        print("qty_validation", {v: sum(1 for ln in lines if ln.get("qty_validation") == v) for v in
                                 ("verified", "corrected_from_source", "unverified", "invalid")}, "corrected", len(corrected))
        assert not bad_q, f"lines without verified qty 2: {bad_q[:10]}"
        assert not unexplained, unexplained[:10]
        assert set(sers) == want and len(sers) == 400, (len(set(sers)), len(sers))
        assert not wrong_page, wrong_page[:5]
        assert all(ln.get("source_text") and "Qty 2" in ln["source_text"] for ln in lines)
        print("heartbeat changes observed while running:", STATE.get("beats", 0))

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
        # Stage A structured pricing: exact cell values, every row accounted for, no AI
        exp = {f"TEST Machine Type {i + 1:03d} Treadmill model - commercial cardio unit incl PPM visit and safety check":
               float(f"{10 + (i % 90)}.{i % 100:02d}") for i in range(700)}
        got = {x["type"]: x["service_price"] for x in res["machine_services"]}
        assert got == exp
        assert {x["location"]: x["price"] for x in res["travel"]} == {f"TEST Site Town {i + 1:02d}": 40.0 + i for i in range(20)}
        assert {x["type"]: x["hourly_rate"] for x in res["repairs"]} == {f"TEST Repair Type {i + 1}": 25.0 + i for i in range(5)}
        rec = res["reconciliation"]
        print("reconciliation", {k: v for k, v in rec.items() if k != "issues"})
        assert rec["source_rows"] == 725 and rec["verified"] == 725 and rec["blocking"] == 0
        assert res["coverage"]["complete"] is True and res["coverage"].get("method") == "structured cells"


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
        # Lifecycle (Stage A): approved but NOT issued while live email is off
        assert d["status"] == "renewal_approved", d["status"]
        assert not d.get("renewal_issued_at")
        prev = mdb.crm2_contracts.find_one({"id": d["previous_contract_id"]})
        assert not prev.get("auto_renewal_sent_at"), "previous contract must not be marked renewal-sent"
        act = mdb.crm2_activities.find_one({"organization_id": OP, "subject": {"$regex": f"{T}-1/R2"}}, sort=[("_id", -1)])
        assert act and "awaiting issue" in act["subject"].lower(), act
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


# =====================================================================================
# Stage A / B certification (Jan 2026): small mixed invoice quantities, apply gate,
# multi-sheet xlsx structured pricing, incomplete-rate save gate, renewal manual issue,
# job dedupe / stale heartbeat / retry, build-info access.
# =====================================================================================
XTRA = {"orgs": [], "sites": [], "afs_quotes": [], "reviews_company": [], "jobs": []}
MT = T[-6:].upper()


def small_mixed_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io as _io
    b = _io.BytesIO()
    cv = canvas.Canvas(b, pagesize=A4)
    rows = ["Pulse Fitness Limited - Sales Invoice TEST_MIX", "Invoice No: TEST-MIX-77  Date: 14/03/2026",
            "Customer: TEST_ Mixed Leisure Ltd", "Item code | Description | Qty | Serial",
            f"PF-TR-900 Pulse Fusion Treadmill 900 Qty 1 Serial SNM{MT}01",
            f"PF-TR-900 Pulse Fusion Treadmill 900 Qty 2 Serials SNM{MT}02, SNM{MT}03",
            "PF-BK-300 Pulse Upright Bike 300 Qty 10",
            f"PF-TR-910 Pulse Fusion Treadmill 910 Qty 3 Serial SNM{MT}04",
            f"PF-RW-200 Pulse Rower 200 Serial SNM{MT}05",
            f"PF-XT-500 Pulse Cross Trainer 500 Qty two Serial SNM{MT}06",
            "PF-ST-100 Pulse Stepper 100 Qty 1",
            "PF-ST-100 Pulse Stepper 100 Qty 1",
            "PF-SP-BLT Treadmill running belt spare part Qty 4"]
    y = 800
    for r in rows:
        cv.drawString(40, y, r)
        y -= 18
    cv.showPage()
    cv.save()
    return b.getvalue()


MIX = small_mixed_pdf()


class TestSmallMixedInvoice:
    def test_concurrent_posts_one_job_and_quantities(self, coord):
        from concurrent.futures import ThreadPoolExecutor
        up, _ = chunk_upload("cm-test-coord", MIX, f"{T}_mix.pdf")
        r = complete("cm-test-coord", up)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        body = {"file_id": fid, "doc_type": "sales_invoice"}
        with ThreadPoolExecutor(2) as ex:
            res = list(ex.map(lambda _: requests.post(f"{AFS}/build-quote/imports/from-file", headers=coord, json=body, timeout=60), range(2)))
        js = [x.json() for x in res]
        print("concurrent", js)
        assert all(x.status_code == 200 for x in res)
        assert js[0]["job_id"] == js[1]["job_id"], js
        assert sum(1 for x in js if x.get("joined")) == 1, js
        assert mdb.crm2_afs_doc_jobs.count_documents({"organization_id": OP, "dedupe": {"$regex": ":sales_invoice$"},
                                                      "id": js[0]["job_id"]}) == 1
        CREATED["jobs"].append(js[0]["job_id"])
        j = poll(coord, js[0]["job_id"])
        assert j["status"] == "done", j
        imp = j["import"]
        CREATED["imports"].append(imp["id"])
        STATE["mix_import"] = imp["id"]
        lines = imp["lines"]
        for ln in lines:
            print(ln["line_no"], ln.get("item_code"), ln.get("quantity"), ln.get("quantity_ai"), ln.get("qty_validation"),
                  ln.get("serials"), ln.get("flags"), ln.get("decision"), "|", ln.get("source_text"))
        STATE["mix_lines"] = lines
        assert len(lines) == 9, len(lines)

    def _by(self, pred):
        ls = [ln for ln in STATE.get("mix_lines") or [] if pred(ln)]
        assert ls, "line not found"
        return ls

    def test_qty_1_2_10_verified(self):
        l1 = self._by(lambda ln: f"SNM{MT}01" in ln["serials"])[0]
        l2 = self._by(lambda ln: f"SNM{MT}02" in ln["serials"])[0]
        l10 = self._by(lambda ln: (ln.get("item_code") or "") == "PF-BK-300")[0]
        assert (l1["quantity"], l1["qty_validation"]) == (1, "verified"), l1
        assert (l2["quantity"], l2["qty_validation"]) == (2, "verified") and sorted(l2["serials"]) == [f"SNM{MT}02", f"SNM{MT}03"], l2
        assert "serial_mismatch" not in l2["flags"]
        assert (l10["quantity"], l10["qty_validation"]) == (10, "verified"), l10

    def test_one_serial_qty_3_keeps_3_and_flags(self):
        ln = self._by(lambda ln: f"SNM{MT}04" in ln["serials"])[0]
        assert ln["quantity"] == 3 and "serial_mismatch" in ln["flags"], ln

    def test_missing_qty_is_null_and_blocking(self):
        ln = self._by(lambda ln: f"SNM{MT}05" in ln["serials"])[0]
        assert ln["quantity"] is None, f"missing printed qty became {ln['quantity']} ({ln['qty_validation']})"
        assert "quantity_unconfirmed" in ln["flags"] and ln["decision"] != "accepted"

    def test_invalid_qty_two_is_invalid(self):
        ln = self._by(lambda ln: f"SNM{MT}06" in ln["serials"])[0]
        assert ln["quantity"] is None, f"'Qty two' became {ln['quantity']} ({ln['qty_validation']})"
        assert "quantity_unconfirmed" in ln["flags"]
        assert ln["qty_validation"] == "invalid", ln["qty_validation"]

    def test_repeated_descriptions_and_spare(self):
        st = self._by(lambda ln: (ln.get("item_code") or "") == "PF-ST-100")
        assert len(st) == 2 and all(x["quantity"] == 1 and x["qty_validation"] == "verified" for x in st), st
        sp = self._by(lambda ln: (ln.get("item_code") or "") == "PF-SP-BLT")[0]
        assert sp["quantity"] == 4 and "spare_part" in sp["flags"] and sp["decision"] == "excluded", sp

    def test_apply_refuses_accepted_line_without_quantity(self, coord):
        lines = STATE.get("mix_lines")
        assert lines
        org, co, site = f"{T}_org", f"{T}_apco", f"{T}_site"
        mdb.organizations.insert_one({"id": org, "name": f"{T} Ops Org"})
        mdb.crm2_companies.insert_one({"id": co, "organization_id": OP, "name": f"{T} Mixed Leisure", "linked_organization_id": org})
        mdb.sites.insert_one({"id": site, "organization_id": org, "name": f"{T} Site"})
        XTRA["orgs"].append(org); XTRA["sites"].append(site); CREATED["companies"].append(co)  # noqa: E702
        STATE["ap_co"], STATE["ap_org"] = co, org
        mdb.crm2_afs_quote_imports.update_one({"id": STATE["mix_import"]}, {"$set": {"company_id": co}})
        cfg = {"id": f"{T}_cfg"}
        mdb.crm2_afs_service_configs.insert_one({"id": cfg["id"], "organization_id": OP, "model": f"{T} Rower 200", "console_type": "",
                                                 "contract_eligible": True, "rate_group": "Standard Equipment"})
        XTRA["cfgs"] = [cfg["id"]]
        target = next((ln for ln in lines if ln["quantity"] is None), None)
        if target is None:  # extractor defaulted the missing qty (known bug) — simulate the expected null to test the apply gate
            target = next(ln for ln in lines if f"SNM{MT}05" in ln["serials"])
            mdb.crm2_afs_quote_imports.update_one({"id": STATE["mix_import"], "lines.line_no": target["line_no"]},
                                                  {"$set": {"lines.$.quantity": None}})
            print("SIMULATED null quantity on line", target["line_no"])
        others = [{"line_no": ln["line_no"], "decision": "excluded"} for ln in lines if ln["line_no"] != target["line_no"]]
        bad = requests.post(f"{AFS}/build-quote/imports/{STATE['mix_import']}/apply", headers=coord, timeout=60, json={
            "site_id": site, "decisions": others + [{"line_no": target["line_no"], "decision": "accepted", "config_id": cfg["id"]}]})
        print("apply no qty", bad.status_code, bad.text[:200])
        assert bad.status_code == 400 and "quantity" in bad.text.lower()
        ok = requests.post(f"{AFS}/build-quote/imports/{STATE['mix_import']}/apply", headers=coord, timeout=60, json={
            "site_id": site, "decisions": others + [{"line_no": target["line_no"], "decision": "accepted", "config_id": cfg["id"], "quantity": 2}]})
        print("apply with qty", ok.status_code, ok.text[:300])
        assert ok.status_code == 200, ok.text
        saved = mdb.crm2_afs_quote_imports.find_one({"id": STATE["mix_import"]})
        t = next(ln for ln in saved["lines"] if ln["line_no"] == target["line_no"])
        assert t["quantity"] == 2 and t["qty_validation"] == "confirmed_by_coordinator"
        assert mdb.equipment.count_documents({"organization_id": org}) >= 1


def tender_xlsx() -> bytes:
    import io as _io
    from openpyxl import Workbook
    wb = Workbook()
    a = wb.active
    a.title = "Service Prices"
    for r in [["Machine type", "Price"], ["TEST Treadmill", 55], ["TEST Upright Bike", 30], ["TEST Rower", "POA"],
              ["TEST Cross Trainer", None], ["Total", 85]]:
        a.append(r)
    b = wb.create_sheet("Gym B Service")
    for r in [["Machine type", "Price"], ["TEST Treadmill", 55], ["TEST Upright Bike", 35]]:
        b.append(r)
    t = wb.create_sheet("Travel")
    for r in [["Location", "Price"], ["TEST Leeds", 40], ["TEST York", 52.5], ["TEST Hull", 61]]:
        t.append(r)
    out = _io.BytesIO()
    wb.save(out)
    return out.getvalue()


class TestStructuredXlsx:
    def test_multi_sheet_reconciliation(self, coord):
        x = tender_xlsx()
        up, _ = chunk_upload("cm-test-coord", x, f"{T}_tender.xlsx", ct="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r = complete("cm-test-coord", up)
        assert r.status_code == 200, r.text
        s = requests.post(f"{AFS}/extract-pricing-jobs", params={"file_id": r.json()["id"]}, headers=coord, timeout=30)
        assert s.status_code == 200, s.text
        CREATED["jobs"].append(s.json()["job_id"])
        STATE["xlsx_file"] = r.json()["id"]
        res = poll(coord, s.json()["job_id"], limit=120)["result"]
        print("svc", res["machine_services"]); print("travel", res["travel"]); print("rec", res["reconciliation"])  # noqa: E702
        svc = res["machine_services"]
        tm = [x for x in svc if x["type"] == "TEST Treadmill"]
        assert len(tm) == 1 and len(tm[0]["source_rows"]) == 2 and tm[0]["service_price"] == 55 and not tm[0].get("needs_review")
        bk = [x for x in svc if x["type"] == "TEST Upright Bike"]
        assert sorted(x["service_price"] for x in bk) == [30, 35] and all(x.get("needs_review") for x in bk)
        assert {x["location"]: x["price"] for x in res["travel"]} == {"TEST Leeds": 40, "TEST York": 52.5, "TEST Hull": 61}
        rec = res["reconciliation"]
        assert rec["review"] == 1 and rec["invalid"] == 1 and rec["excluded"] == 1 and rec["conflicts"] == 2
        assert rec["blocking"] == 4 and res["coverage"]["complete"] is False
        assert rec["source_rows"] == 10 and rec["verified"] == 7
        STATE["xlsx_res"] = res


class TestBlockIncompleteRates:
    def _body(self, **kw):
        return {"company_id": STATE.get("ap_co") or "x", "machine_rates": [{"type": "TEST Treadmill", "service_price": 55}],
                "travel_rates": [], "repair_rates": [], **kw}

    def test_save_with_needs_review_422(self, coord):
        assert STATE.get("ap_co")
        b = self._body(save=True, machine_rates=[{"type": "TEST Bike", "service_price": 30, "needs_review": True}])
        r = requests.post(f"{AFS}/build-custom-quote", headers=coord, json=b, timeout=60)
        assert r.status_code == 422, r.text
        r2 = requests.post(f"{AFS}/build-custom-quote", headers=coord, json=self._body(save=True, source_blocking=2), timeout=60)
        assert r2.status_code == 422, r2.text
        r3 = requests.post(f"{AFS}/build-custom-quote", headers=coord, json=self._body(save=True, source_blocking=2, rate_review_reason="short"), timeout=60)
        assert r3.status_code == 422, r3.text
        assert mdb.crm2_afs_rate_reviews.count_documents({"company_id": STATE["ap_co"]}) == 0

    def test_preview_still_works(self, coord):
        r = requests.post(f"{AFS}/build-custom-quote", headers=coord, json=self._body(save=False, source_blocking=2), timeout=60)
        print("preview", r.status_code, r.text[:300])
        assert r.status_code == 200, r.text

    def test_save_with_reason_records_review(self, coord):
        XTRA["reviews_company"].append(STATE["ap_co"])
        r = requests.post(f"{AFS}/build-custom-quote", headers=coord, timeout=60,
                          json=self._body(save=True, source_blocking=2, rate_review_reason="TEST customer confirmed POA rows excluded"))
        print("save", r.status_code, r.text[:300])
        assert r.status_code == 200, r.text
        for q in mdb.crm2_afs_quotes.find({"company_id": STATE["ap_co"]}, {"id": 1}):
            XTRA["afs_quotes"].append(q["id"])
        rv = mdb.crm2_afs_rate_reviews.find_one({"company_id": STATE["ap_co"]})
        assert rv and rv["unresolved"] == 2 and rv["by"] == "cm.coordinator@pulsefitness.test" and "POA" in rv["reason"]


class TestRenewalManualIssue:
    @pytest.fixture(scope="class", autouse=True)
    def seed(self):
        co, prev, ren = f"{T}_co2", f"{T}_prev2", f"{T}_ren2"
        mdb.crm2_companies.insert_one({"id": co, "organization_id": OP, "name": f"{T} Leisure 2", "email": "test.renewal2@example.test"})
        mdb.crm2_contacts.insert_one({"id": f"{T}_ct2", "organization_id": OP, "company_id": co, "email": "test.renewal2@example.test", "name": "TEST"})
        end = (date.today() + timedelta(days=40)).isoformat()
        mdb.crm2_contracts.insert_many([
            {"id": prev, "organization_id": OP, "company_id": co, "status": "active", "contract_number": f"{T}-2",
             "annual_value": 1000, "end_date": end, "title": f"{T} contract 2"},
            {"id": ren, "organization_id": OP, "company_id": co, "status": "renewal_pending_approval", "previous_contract_id": prev,
             "contract_number": f"{T}-2/R2", "annual_value": 1000, "renewal_uplift_percent": 0, "title": f"{T} renewal 2"}])
        CREATED["companies"].append(co); CREATED["contacts"].append(f"{T}_ct2"); CREATED["contracts"] += [prev, ren]  # noqa: E702
        STATE["ren2"], STATE["prev2"] = ren, prev
        yield

    def test_approve_then_list_label(self, coord):
        r = requests.post(f"{API}/crm/workspace/renewals/{STATE['ren2']}/approve-send", headers=coord, json={}, timeout=60)
        assert r.status_code == 200, r.text
        row = next(x for x in requests.get(f"{API}/crm/workspace/renewals", headers=coord, timeout=30).json()["renewals"] if x["id"] == STATE["ren2"])
        print("label", row["comms_status"], row["comms_label"])
        assert row["comms_status"] == "awaiting_dispatch" and "awaiting issue" in row["comms_label"].lower()

    def test_dispatch_noop_when_off(self):
        os.environ.pop("CM_RENEWAL_EMAIL_LIVE", None)
        from utils.cm_renewals import dispatch_queued_renewals
        out = asyncio.run(dispatch_queued_renewals(OP))
        assert out == {"live": False, "sent": 0, "failed": 0}
        assert mdb.crm2_contracts.find_one({"id": STATE["ren2"]})["renewal_email_state"] == "awaiting_dispatch"

    def test_mark_issued_perm_validation_and_effect(self):
        coord_h, _ = _crm("cm-test-coord")
        asm, r = _crm("cm-test-asm")
        assert asm, r.text
        u = f"{API}/crm/workspace/renewals/{STATE['ren2']}/mark-issued"
        assert requests.post(u, headers=coord_h, json={"evidence": "TEST handed over"}, timeout=30).status_code == 403
        assert requests.post(u, headers=asm, json={"evidence": "abc"}, timeout=30).status_code == 422
        ok = requests.post(u, headers=asm, json={"evidence": "TEST handed to site manager"}, timeout=30)
        assert ok.status_code == 200, ok.text
        d = mdb.crm2_contracts.find_one({"id": STATE["ren2"]})
        assert d["status"] == "sent" and d["renewal_issued_via"] == "manual" and d.get("renewal_issued_at")
        assert d["renewal_email_state"] == "cancelled"
        assert mdb.crm2_contracts.find_one({"id": STATE["prev2"]}).get("auto_renewal_sent_at")
        again = requests.post(u, headers=asm, json={"evidence": "TEST second time"}, timeout=30)
        assert again.status_code == 409
        c = requests.post(f"{API}/crm/workspace/renewals/{STATE['ren2']}/cancel-email", headers=asm, json={"reason": "TEST x"}, timeout=30)
        assert c.status_code == 409


class TestJobReliability:
    def test_stale_heartbeat_marks_interrupted_and_retry_creates_new_job(self, coord):
        fid = STATE.get("xlsx_file")
        assert fid
        fdoc = mdb.files.find_one({"id": fid})
        dedupe = f"{fdoc['content_hash']}:pricing"
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        jid = f"{T}_stalejob"
        mdb.crm2_afs_doc_jobs.insert_one({"id": jid, "organization_id": OP, "kind": "pricing", "dedupe": dedupe,
                                          "active_key": f"{OP}:{dedupe}", "status": "running", "created_at": old,
                                          "started_at": old, "heartbeat_at": old})
        CREATED["jobs"].append(jid)
        g = requests.get(f"{AFS}/build-quote/jobs/{jid}", headers=coord, timeout=30).json()
        print("stale", g)
        assert g["status"] == "failed" and g.get("interrupted") is True and "retry" in g["error"].lower()
        assert "active_key" not in mdb.crm2_afs_doc_jobs.find_one({"id": jid})
        s = requests.post(f"{AFS}/extract-pricing-jobs", params={"file_id": fid}, headers=coord, timeout=30).json()
        CREATED["jobs"].append(s["job_id"])
        assert s["job_id"] != jid and not s.get("joined")
        assert poll(coord, s["job_id"], limit=120)["status"] == "done"

    def test_stale_active_job_does_not_block_new_post(self, coord):
        fid = STATE.get("xlsx_file")
        fdoc = mdb.files.find_one({"id": fid})
        dedupe = f"{fdoc['content_hash']}:pricing"
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        jid = f"{T}_stalejob2"
        mdb.crm2_afs_doc_jobs.insert_one({"id": jid, "organization_id": OP, "kind": "pricing", "dedupe": dedupe,
                                          "active_key": f"{OP}:{dedupe}", "status": "running", "created_at": old,
                                          "started_at": old, "heartbeat_at": old})
        CREATED["jobs"].append(jid)
        s = requests.post(f"{AFS}/extract-pricing-jobs", params={"file_id": fid}, headers=coord, timeout=30).json()
        CREATED["jobs"].append(s["job_id"])
        assert s["job_id"] != jid and not s.get("joined"), s
        assert mdb.crm2_afs_doc_jobs.find_one({"id": jid})["status"] == "failed"


class TestBuildInfo:
    def test_access(self):
        assert requests.get(f"{API}/build-info", timeout=30).status_code == 401
        assert requests.get(f"{API}/build-info", headers=_main("cm-test-coord"), timeout=30).status_code == 403
        adm = mdb.users.find_one({"is_master_admin": True}, {"id": 1})
        r = requests.get(f"{API}/build-info", headers=_main(adm["id"]), timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        print(b)
        assert b["fingerprint"]["combined"] and b["started_at"] and set(b["flags"]) >= {"CM_RENEWAL_EMAIL_LIVE", "MOD_QUOTE_NOTIFY_LIVE"}
        assert b["flags"]["CM_RENEWAL_EMAIL_LIVE"] is False and b["flags"]["MOD_QUOTE_NOTIFY_LIVE"] is False


@pytest.fixture(scope="module", autouse=True)
def cleanup_stage_ab():
    yield
    orgs = XTRA["orgs"]
    eq_ids = [e["id"] for e in mdb.equipment.find({"organization_id": {"$in": orgs}}, {"id": 1})] if orgs else []
    if eq_ids:
        mdb.crm2_afs_equipment_claims.delete_many({"equipment_id": {"$in": eq_ids}})
        mdb.equipment.delete_many({"id": {"$in": eq_ids}})
    mdb.sites.delete_many({"id": {"$in": XTRA["sites"]}})
    mdb.organizations.delete_many({"id": {"$in": orgs}})
    mdb.crm2_afs_quotes.delete_many({"id": {"$in": XTRA["afs_quotes"]}})
    mdb.crm2_afs_rate_reviews.delete_many({"company_id": {"$in": XTRA["reviews_company"]}})
    mdb.crm2_afs_service_configs.delete_many({"id": {"$in": XTRA.get("cfgs", [])}})
    mdb.crm2_activities.delete_many({"organization_id": OP, "subject": {"$regex": T}})
