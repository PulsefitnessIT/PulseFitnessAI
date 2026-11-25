"""Milestone 1 — approved terms, customer e-signature, link security,
automatic activation, welcome pack, coordinator ownership, overdue PPM.

Fictional data only (prefix ``cm_m1_``); everything is removed afterwards.
"""
from tests._paths import REPO  # noqa: E402
import asyncio
import io
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_m1_"
AFS = f"{API}/crm/v2/aftersales"
PUB = f"{API}/public/afs/agreement"
SIG = "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
_saved_terms = []


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _tiny_pdf():
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b)
    cv.drawString(72, 720, "TEST maintenance terms")
    cv.save()
    return b.getvalue()


def _quote(qid, company, **kw):
    doc = {"id": qid, "organization_id": OP, "company_id": company, "quote_number": qid.upper(), "status": "accepted",
           "contract_type": "m1_plan", "linked_organization_id": f"{T}cust-{company}", "visits_per_year": 2,
           "preferred_payment": "annual", "requested_start_date": "2026-01-01",
           "summary": {"final_annual": 1200.0, "term_years": 1, "vat_pct": 0.2},
           "grouped_lines": [{"model": "TM1", "qty": 1, "serials": ["S1"], "annual_total": 1200.0}], "asset_register": []}
    doc.update(kw)
    mdb.crm2_afs_quotes.insert_one(doc)


def _company(cid, coord=None):
    mdb.organizations.insert_one({"id": f"{T}cust-{cid}", "name": f"M1 {cid} Ltd"})
    mdb.sites.insert_one({"id": f"{T}site-{cid}", "organization_id": f"{T}cust-{cid}", "name": "Main"})
    mdb.crm2_companies.insert_one({"id": cid, "organization_id": OP, "name": f"M1 {cid}", "legal_name": f"M1 {cid} Ltd",
                                   "linked_organization_id": f"{T}cust-{cid}", "email": "customer@example.test",
                                   **({"coordinator_id": coord} if coord else {})})


def _ready_agreement(qid, company, h):
    _quote(qid, company)
    aid = requests.post(f"{AFS}/quotes/{qid}/accept", headers=h, json={}).json()["agreement_id"]
    assert requests.post(f"{AFS}/agreements/{aid}/generate", headers=h).status_code == 200
    return aid


def _send(aid, h, email="signer@example.test"):
    r = requests.post(f"{AFS}/agreements/{aid}/send-for-signature", headers=h,
                      json={"signatory_name": "Sam Signer", "email": email})
    return r


def _open(key):
    return mdb.crm2_activities.count_documents({"organization_id": OP, "dedupe_key": key, "status": "open"})


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd=REPO + "/backend",
                   env={**os.environ, "PYTHONPATH": REPO + "/backend"}, check=True)
    _saved_terms.extend(mdb.crm2_afs_terms.find({"organization_id": OP, "status": "approved"}, {"_id": 0, "id": 1}))
    mdb.crm2_afs_terms.update_many({"organization_id": OP, "status": "approved"}, {"$set": {"status": "m1_parked"}})
    for c in ("a", "b", "c", "d"):
        _company(f"{T}co-{c}", coord="cm-test-coord" if c == "a" else None)
    yield
    rx = {"$regex": f"^{T}"}
    ags = [a["id"] for a in mdb.crm2_afs_agreements.find({"company_id": rx}, {"id": 1})]
    cons = [c["id"] for c in mdb.crm2_contracts.find({"company_id": rx}, {"id": 1})]
    for coll in ("crm2_afs_service_schedules", "crm2_afs_billing", "crm2_afs_finance_sync"):
        mdb[coll].delete_many({"contract_id": {"$in": cons}})
    for coll in ("crm2_contracts", "crm2_companies", "crm2_afs_quotes", "crm2_afs_agreements"):
        mdb[coll].delete_many({"$or": [{"id": rx}, {"company_id": rx}]})
    mdb.organizations.delete_many({"id": rx})
    mdb.sites.delete_many({"id": rx})
    mdb.crm2_activities.delete_many({"$or": [{"company_id": rx}, {"agreement_id": {"$in": ags}}]})
    mdb.crm2_afs_terms.delete_many({"organization_id": OP, "version": rx})
    mdb.crm2_afs_terms.update_many({"organization_id": OP, "status": "m1_parked"}, {"$set": {"status": "approved"}})
    mdb.crm2_activities.delete_many({"organization_id": OP, "dedupe_key": "cm:terms-missing"})


def test_1_terms_required_upload_and_approval():
    h, asm = _crm("cm-test-coord"), _crm("cm-test-asm")
    aid = _ready_agreement(f"{T}q1", f"{T}co-a", h)
    r = _send(aid, h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "terms_not_approved"
    assert _open("cm:terms-missing") == 1
    files = {"file": ("terms.pdf", _tiny_pdf(), "application/pdf")}
    assert requests.post(f"{AFS}/terms?version={T}v1", headers=h, files=files).status_code == 403
    assert requests.post(f"{AFS}/terms?version={T}v1", headers=asm,
                         files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 400
    t = requests.post(f"{AFS}/terms?version={T}v1", headers=asm, files=files).json()
    assert t["status"] == "pending_approval" and len(t["sha256"]) == 64
    assert _send(aid, h).status_code == 409   # uploaded but not yet approved
    r = requests.post(f"{AFS}/terms/{t['id']}/approve", headers=asm)
    assert r.status_code == 400 and "Open and read" in r.text          # must inspect the PDF first
    assert requests.get(f"{AFS}/terms/{t['id']}/file", headers=asm).content.startswith(b"%PDF")
    assert requests.post(f"{AFS}/terms/{t['id']}/approve", headers=asm).json()["status"] == "approved"
    assert _open("cm:terms-missing") == 0
    # Word files are reference copies only and can never be approved for issue.
    w = requests.post(f"{AFS}/terms?version={T}word", headers=asm,
                      files={"file": ("t.docx", b"PK\x03\x04word", "application/octet-stream")}).json()
    assert w["status"] == "reference_only"
    requests.get(f"{AFS}/terms/{w['id']}/file", headers=asm)
    assert requests.post(f"{AFS}/terms/{w['id']}/approve", headers=asm).status_code == 400


def test_2_unready_agreement_cannot_be_sent():
    h = _crm("cm-test-coord")
    _quote(f"{T}q2", f"{T}co-b", requested_start_date=None)
    aid = requests.post(f"{AFS}/quotes/{T}q2/accept", headers=h, json={}).json()["agreement_id"]
    r = _send(aid, h)
    assert r.status_code == 400


def test_3_customer_signs_once_and_contract_auto_activates():
    h = _crm("cm-test-coord")
    aid = mdb.crm2_afs_agreements.find_one({"quote_id": f"{T}q1"})["id"]
    assert _open(f"cm:agreement-send:{aid}") == 1
    r = _send(aid, h)
    assert r.status_code == 200, r.text
    out = r.json()
    token = out["path"].split("/as/")[1]
    ag = mdb.crm2_afs_agreements.find_one({"id": aid})
    assert ag["status"] == "sent" and ag["document"]["sha256"] == out["document_hash"]
    assert "token" not in str(ag["signature_request"]).replace("token_hash", "")  # only the hash is stored
    # Preview email key is invalid → truthful failure + recovery action (never "sent").
    if out["delivery_status"] == "failed":
        assert _open(f"cm:agreement-email-failed:{aid}") == 1 and _open(f"cm:agreement-sign:{aid}") == 0
    assert _open(f"cm:agreement-send:{aid}") == 0

    pub = requests.get(f"{PUB}/{token}").json()
    assert pub["agreement_number"] == ag["agreement_number"] and pub["customer"] == f"M1 {T}co-a Ltd"
    assert "annual_value" in pub and "organization_id" not in pub and "token_hash" not in str(pub)
    assert mdb.crm2_afs_agreements.find_one({"id": aid})["status"] == "viewed"
    pdf = requests.get(f"{PUB}/{token}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    body = {"signatory_name": "Sam Signer", "position": "Director", "email": "signer@example.test",
            "authority_confirmed": True, "consent_confirmed": True, "signature_data_url": SIG,
            "document_hash": "0" * 64}
    assert requests.post(f"{PUB}/{token}/sign", json=body).status_code == 409   # wrong document version
    assert requests.post(f"{PUB}/{token}/sign", json={**body, "document_hash": pub["document_hash"],
                                                      "consent_confirmed": False}).status_code == 400
    body["document_hash"] = pub["document_hash"]
    results = [requests.post(f"{PUB}/{token}/sign", json=body) for _ in range(3)]
    assert all(x.status_code == 200 for x in results)
    assert sum(1 for x in results if x.json().get("already_signed")) == 2
    ag = mdb.crm2_afs_agreements.find_one({"id": aid})
    s = ag["signature"]
    assert s["method"] == "customer_esignature" and s["document_hash"] == ag["document"]["sha256"]
    assert s["signed_at"] and s["consent_text"] and s["authority_confirmed"]
    assert ag["signed_document"]["sha256"] and ag["status"] == "active"   # auto-activated
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": aid}) == 1
    c = mdb.crm2_contracts.find_one({"source_agreement_id": aid})
    for k in ("send", "sign", "email-failed", "activate", "complete"):
        assert _open(f"cm:agreement-{k}:{aid}") == 0
    wp = c["welcome_pack"]
    assert wp["status"] in ("accepted_by_provider", "failed")
    if wp["status"] == "failed":
        assert _open(f"cm:welcome-failed:{c['id']}") == 1
    # Re-running activation never sends a second welcome pack automatically.
    again = requests.post(f"{AFS}/agreements/{aid}/activate", headers=h, json={}).json()
    assert again["already_active"]
    assert len(mdb.crm2_contracts.find_one({"id": c["id"]})["welcome_pack"]["history"]) == 1
    # Document cannot change after signing.
    assert requests.patch(f"{AFS}/agreements/{aid}", headers=h, json={"payment_method": "monthly"}).status_code == 400


def test_4_link_security_expired_revoked_and_replaced():
    h = _crm("cm-test-coord")
    aid = _ready_agreement(f"{T}q3", f"{T}co-c", h)
    old = _send(aid, h).json()["path"].split("/as/")[1]
    new = _send(aid, h).json()["path"].split("/as/")[1]
    assert requests.get(f"{PUB}/{old}").status_code == 404           # replaced link stops working
    assert requests.get(f"{PUB}/not-a-real-token-at-all-xxxxxxxx").status_code == 404
    other = mdb.crm2_afs_agreements.find_one({"quote_id": f"{T}q1"})
    assert requests.get(f"{PUB}/{new}").json()["agreement_number"] != other["agreement_number"]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    mdb.crm2_afs_agreements.update_one({"id": aid}, {"$set": {"signature_request.expires_at": past}})
    assert requests.get(f"{PUB}/{new}").status_code == 410
    assert _open(f"cm:agreement-link-expired:{aid}") == 1
    fresh = _send(aid, h).json()["path"].split("/as/")[1]
    assert requests.post(f"{AFS}/agreements/{aid}/signature-link/revoke", headers=h).status_code == 200
    assert requests.get(f"{PUB}/{fresh}").status_code == 410
    assert mdb.crm2_afs_agreements.find_one({"id": aid})["status"] == "ready"


def test_5_conflict_review_takes_precedence_over_activate_task():
    h = _crm("cm-test-coord")
    mdb.crm2_contracts.insert_one({"id": f"{T}old", "organization_id": OP, "company_id": f"{T}co-d", "status": "active",
                                   "contract_number": "M1-OLD", "end_date": "2026-12-31"})
    aid = _ready_agreement(f"{T}q4", f"{T}co-d", h)
    token = _send(aid, h).json()["path"].split("/as/")[1]
    pub = requests.get(f"{PUB}/{token}").json()
    r = requests.post(f"{PUB}/{token}/sign", json={"signatory_name": "Dee Signer", "email": "dee@example.test",
                                                    "authority_confirmed": True, "consent_confirmed": True,
                                                    "signature_data_url": SIG, "document_hash": pub["document_hash"]})
    assert r.status_code == 200 and r.json()["activated"] is False
    assert mdb.crm2_afs_agreements.find_one({"id": aid})["status"] == "activation_attention"
    assert _open(f"cm:activation-conflict:{aid}") == 1 and _open(f"cm:agreement-activate:{aid}") == 0
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": aid}) == 0


def test_6_customer_decline_and_coordinator_reassignment():
    h = _crm("cm-test-coord")
    mdb.crm2_contracts.delete_one({"id": f"{T}old"})
    _quote(f"{T}q5", f"{T}co-b")
    aid = requests.post(f"{AFS}/quotes/{T}q5/accept", headers=h, json={}).json()["agreement_id"]
    requests.post(f"{AFS}/agreements/{aid}/generate", headers=h)
    token = _send(aid, h).json()["path"].split("/as/")[1]
    assert requests.post(f"{PUB}/{token}/decline", json={"name": "Bo", "reason": "Budget"}).status_code == 200
    assert _open(f"cm:agreement-declined:{aid}") == 1
    assert requests.post(f"{PUB}/{token}/sign", json={"signatory_name": "Bo B", "email": "b@example.test",
                                                       "authority_confirmed": True, "consent_confirmed": True,
                                                       "signature_data_url": SIG, "document_hash": "0" * 64}).status_code == 409
    act = mdb.crm2_activities.find_one({"dedupe_key": f"cm:agreement-declined:{aid}"})
    assert act["owner_id"] == "system"
    coord = mdb.users.find_one({"id": "cm-test-coord"})
    assert coord, "seeded coordinator"
    r = requests.put(f"{API}/crm/workspace/customers/{T}co-b/coordinator", headers=_crm("cm-test-asm"),
                     json={"user_id": "cm-test-coord"})
    assert r.status_code == 200 and r.json()["tasks_reassigned"] >= 1
    act = mdb.crm2_activities.find_one({"dedupe_key": f"cm:agreement-declined:{aid}"})
    assert act["owner_id"] == "cm-test-coord" and act["owner_history"][-1]["from_id"] == "system"
    r = requests.put(f"{API}/crm/workspace/customers/{T}co-b/coordinator", headers=_crm("cm-test-asm"), json={"user_id": None})
    act = mdb.crm2_activities.find_one({"dedupe_key": f"cm:agreement-declined:{aid}"})
    assert act["owner_id"] == "system" and len(mdb.crm2_companies.find_one({"id": f"{T}co-b"})["coordinator_history"]) == 2
    assert requests.put(f"{API}/crm/workspace/customers/{T}co-b/coordinator", headers=_crm("cm-test-fin"),
                        json={"user_id": None}).status_code == 403


def test_7_overdue_ppm_is_shown_first():
    h = _crm("cm-test-coord")
    c = mdb.crm2_contracts.find_one({"company_id": f"{T}co-a", "source": "aftersales"})
    plan = requests.get(f"{AFS}/contracts/{c['id']}/schedules", headers=h).json()
    # Contract started 2026-01-01 with 2 visits/yr: the first visit date is already past.
    first = sorted(v["planned_date"] for v in plan["service"]["visits"])[0]
    assert plan["service"]["next_due"] == first
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert plan["service"]["next_due_overdue"] == (first < today)
    assert plan["service"]["overdue"] == sum(1 for v in plan["service"]["visits"] if v["planned_date"] < today)


def test_8_welcome_pack_once_with_provider_confirmation(monkeypatch):
    import utils.email as em
    from utils.cm_agreements import send_welcome_pack
    c = mdb.crm2_contracts.find_one({"company_id": f"{T}co-a", "source": "aftersales"})
    calls = []

    async def fake_send(to, subject, html, attachments=None, **kw):
        calls.append(to)
        kw["result_out"]["message_id"] = "msg-test-1"
        return True
    monkeypatch.setattr(em, "send_email", fake_send)

    async def run():
        from utils.database import db
        db.client.get_io_loop = asyncio.get_running_loop
        r1 = await send_welcome_pack(OP, c["id"], actor="test", reissue=True)
        r2 = await send_welcome_pack(OP, c["id"], actor="test")
        return r1, r2
    r1, r2 = asyncio.run(run())
    assert r1["status"] == "accepted_by_provider" and r1["message_id"] == "msg-test-1"
    assert r2["status"] == "duplicate_prevented" and len(calls) == 1
    assert _open(f"cm:welcome-failed:{c['id']}") == 0


def test_9_signed_pdf_storage_failure_blocks_activation_and_is_retryable(monkeypatch):
    import utils.cm_agreements as cma
    h = _crm("cm-test-coord")
    mdb.crm2_contracts.delete_many({"company_id": f"{T}co-d"})
    _company(f"{T}co-e")
    aid = _ready_agreement(f"{T}q9", f"{T}co-e", h)
    token = _send(aid, h).json()["path"].split("/as/")[1]
    pub = requests.get(f"{PUB}/{token}").json()
    # Simulate storage failure by recording a signature exactly as the public endpoint does,
    # then running the storage step in-process with a failing object store.
    r = requests.post(f"{PUB}/{token}/sign", json={"signatory_name": "Eve Signer", "email": "eve@example.test",
                                                    "authority_confirmed": True, "consent_confirmed": True,
                                                    "signature_data_url": SIG, "document_hash": pub["document_hash"]})
    assert r.status_code == 200
    # Roll the agreement back to "signed, copy missing" to exercise the failure path deterministically.
    c = mdb.crm2_contracts.find_one({"source_agreement_id": aid})
    if c:
        mdb.crm2_contracts.delete_one({"id": c["id"]})
        mdb.crm2_afs_service_schedules.delete_many({"contract_id": c["id"]})
        mdb.crm2_afs_billing.delete_many({"contract_id": c["id"]})
        mdb.equipment.update_many({"contract_cover.contract_id": c["id"]}, {"$unset": {"contract_cover": ""}})
    mdb.crm2_afs_agreements.update_one({"id": aid}, {"$set": {"status": "signed"},
                                                     "$unset": {"signed_document": "", "contract_id": "", "activation_steps": ""}})

    async def boom(*a, **k):
        raise RuntimeError("object store unavailable")
    monkeypatch.setattr(cma, "_put", boom)

    async def run():
        from utils.database import db
        db.client.get_io_loop = asyncio.get_running_loop
        return await cma.store_signed_copy(OP, aid)
    assert asyncio.run(run()) is False
    ag = mdb.crm2_afs_agreements.find_one({"id": aid})
    assert ag["signature"]["method"] == "customer_esignature" and ag["signed_document_error"]
    assert _open(f"cm:signed-doc-failed:{aid}") == 1
    r = requests.post(f"{AFS}/agreements/{aid}/activate", headers=h, json={})
    assert r.status_code == 409 and "signed_document_missing" in r.text
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": aid}) == 0
    monkeypatch.undo()
    r = requests.post(f"{AFS}/agreements/{aid}/signed-document/retry", headers=h)
    assert r.status_code == 200, r.text
    ag = mdb.crm2_afs_agreements.find_one({"id": aid})
    assert ag["signed_document"]["status"] == "verified" and _open(f"cm:signed-doc-failed:{aid}") == 0
    assert r.json()["activation"]["activated"] is True and ag["status"] == "active"
    assert mdb.crm2_contracts.count_documents({"source_agreement_id": aid}) == 1


def test_10_welcome_pack_never_sent_without_signed_attachment(monkeypatch):
    import utils.email as em
    from utils.cm_agreements import send_welcome_pack
    c = mdb.crm2_contracts.find_one({"company_id": f"{T}co-e", "source": "aftersales"})
    aid = c["source_agreement_id"]
    saved = mdb.crm2_afs_agreements.find_one({"id": aid})["signed_document"]
    mdb.crm2_afs_agreements.update_one({"id": aid}, {"$unset": {"signed_document": ""}})
    calls = []

    async def fake_send(*a, **k):
        calls.append(1)
        return True
    monkeypatch.setattr(em, "send_email", fake_send)

    async def run():
        from utils.database import db
        db.client.get_io_loop = asyncio.get_running_loop
        return await send_welcome_pack(OP, c["id"], actor="test", reissue=True)
    r = asyncio.run(run())
    assert r["status"] == "blocked" and not calls and _open(f"cm:welcome-failed:{c['id']}") == 1
    mdb.crm2_afs_agreements.update_one({"id": aid}, {"$set": {"signed_document": saved}})
    r = asyncio.run(run())
    assert r["status"] == "accepted_by_provider" and len(calls) == 1 and r["attachment"] is True
    assert _open(f"cm:welcome-failed:{c['id']}") == 0


def test_11_finance_can_read_signed_document_but_not_act():
    fin = _crm("cm-test-fin")
    aid = mdb.crm2_afs_agreements.find_one({"quote_id": f"{T}q9"})["id"]
    assert requests.get(f"{AFS}/agreements/{aid}/document", headers=fin).content.startswith(b"%PDF")
    assert requests.post(f"{AFS}/agreements/{aid}/signed-document/retry", headers=fin).status_code == 403
    assert requests.post(f"{AFS}/agreements/{aid}/activate", headers=fin, json={}).status_code == 403
