"""Iter 316 – MOD Quotation founder stabilisation sprint: site truth, idempotency, revision race, Sage ref,
validity/extension/expiry, notify dry-run, handover setup, retired CRM endpoints. Does NOT import/approve rate lists."""
import os
import sys
import threading
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
sys.path.insert(0, os.path.dirname(__file__))
from mod_quotes_test_helpers import delete_groups, run  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MQ = f"{API}/mod-ops/quotes"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
ROWS = [{"row_id": "r0", "rate_card_id": "sor-2", "description": "Treadmills", "qty": 2, "coverage": "A", "label": ""},
        {"row_id": "r1", "rate_card_id": "sor-5", "description": "Benches", "qty": 2, "coverage": "B", "label": ""}]
CUSTOMER = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane", "Helensburgh", "G84 0EH"]}
CREATED: list[str] = []
S: dict = {}


def _db():
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw, **({"portal": portal} if portal else {})}
    r = requests.post(f"{API}/auth/login", json=body, headers=BYPASS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def mgr():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def cust():
    return _login("modsite.officer@army.mod.test", "ModSite123!", "mod")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = _db()
    hids = [h["id"] for h in db.mod_quote_handovers.find({"group_id": {"$in": CREATED}}, {"id": 1})]
    if hids:
        db.mod_service_contracts.delete_many({"source_handover_id": {"$in": hids}})
    if CREATED:
        run(delete_groups(CREATED))


def _create(mgr, **extra):
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"], "notes": "TEST_iter316", **extra})
    assert r.status_code == 200, r.text
    g = r.json()
    if g["id"] not in CREATED:
        CREATED.append(g["id"])
    return g


def _exceptions_for(g):
    until = (date.today() + timedelta(days=10)).isoformat()
    return [{"quote_id": q["id"], "line_no": ln["line_no"], "reason": "TEST commercial exception reason",
             "original_rate": ln["unit_price"], "proposed_rate": ln["unit_price"], "valid_until": until}
            for q in g["quotes"] for ln in (q.get("unverified_rate_lines") or [])]


def _publish(mgr, g):
    assert mgr.post(f"{MQ}/groups/{g['id']}/submit").status_code == 200
    r = mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": _exceptions_for(g)})
    assert r.status_code == 200, r.text
    r = mgr.post(f"{MQ}/groups/{g['id']}/publish", json={"quote_ids": [q["id"] for q in g["quotes"]]})
    assert r.status_code == 200, r.text
    return r.json()


# retired CRM quote creator
def test_crm_legacy_generate_retired(mgr):
    r = mgr.post(f"{API}/crm/mod-quote/generate", json={})
    assert r.status_code in (410, 401, 403), r.status_code


# server-side site truth
def test_invalid_site_rejected(mgr):
    r = mgr.post(f"{MQ}/groups", json={"customer": {**CUSTOMER, "site_id": "not-a-site"}, "rows": ROWS, "options": ["A"]})
    assert r.status_code == 422, r.text


def test_create_and_refs(mgr):
    g = _create(mgr)
    assert g["status"] == "draft" and len(g["quotes"]) == 2
    assert all(q["quote_number"].startswith("PFQ-") for q in g["quotes"])
    assert g["mod_site_id"] == SITE
    S["g"] = g


def test_revise_cannot_change_site(mgr):
    r = mgr.put(f"{MQ}/groups/{S['g']['id']}", json={"customer": {**CUSTOMER, "site_id": "other"}, "rows": ROWS, "options": ["A", "B"]})
    assert r.status_code == 409


# idempotency key: sequential + concurrent
def test_idempotency_sequential(mgr):
    key = f"TEST_idem_{uuid.uuid4().hex}"
    a = _create(mgr, idempotency_key=key)
    b = _create(mgr, idempotency_key=key)
    assert a["id"] == b["id"]
    assert _db().mod_quote_groups.count_documents({"idempotency_key": key}) == 1


def test_idempotency_concurrent(mgr):
    key = f"TEST_idemc_{uuid.uuid4().hex}"
    out = []

    def go():
        r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A"], "idempotency_key": key})
        out.append(r)
    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    ids = {r.json()["id"] for r in out if r.status_code == 200}
    CREATED.extend(i for i in ids if i not in CREATED)
    assert all(r.status_code == 200 for r in out), [r.status_code for r in out]
    assert len(ids) == 1, ids
    gid = ids.pop()
    visible = [q for q in _db().crm2_quotes.find({"mod_group_id": gid, "status": {"$nin": ["superseded", "staging", "failed_staging"]}})]
    assert len(visible) == 1, f"{len(visible)} current quotes for single-option group"


# concurrent revisions must not leave duplicate option sets
def test_concurrent_revise_no_duplicates(mgr):
    g = _create(mgr)
    out = []

    def go(q):
        rows = [dict(r) for r in ROWS]
        rows[0]["qty"] = q
        out.append(mgr.put(f"{MQ}/groups/{g['id']}", json={"customer": CUSTOMER, "rows": rows, "options": ["A", "B"]}))
    ts = [threading.Thread(target=go, args=(q,)) for q in (3, 4, 5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    cur = mgr.get(f"{MQ}/groups/{g['id']}").json()["quotes"]
    types = [q["mod_quote_type"] for q in cur]
    S["race"] = {"codes": [r.status_code for r in out], "types": types}
    assert sorted(types) == ["A", "B"], f"duplicate current options after concurrent revise: {types} codes={S['race']['codes']}"


# Sage reference
def test_sage_ref_rules(mgr):
    q = S["g"]["quotes"][0]
    assert mgr.post(f"{MQ}/quotes/{q['id']}/sage-ref", json={"sage_quote_number": "PFQ-000001", "verified": True}).status_code == 422
    assert mgr.post(f"{MQ}/quotes/{q['id']}/sage-ref", json={"sage_quote_number": "QT99001", "verified": False}).status_code == 422
    r = mgr.post(f"{MQ}/quotes/{q['id']}/sage-ref", json={"sage_quote_number": "qt99001", "verified": True})
    assert r.status_code == 200, r.text
    pdf = mgr.get(f"{MQ}/quotes/{q['id']}/pdf")
    assert pdf.content[:4] == b"%PDF" and "QT99001" in pdf.headers.get("content-disposition", "")


# validity settings & permissions
def test_validity_settings(mgr, rep):
    v = mgr.get(f"{MQ}/settings").json()["validity"]
    assert v["days"] >= 1 and v["status"] in ("provisional", "approved")
    assert rep.put(f"{MQ}/settings/validity", json={"days": 30}).status_code == 403


def test_publish_and_sage_locked(mgr):
    g = _publish(mgr, S["g"])
    assert g["status"] == "published"
    q = g["quotes"][0]
    assert q["valid_until"] and q.get("validity_basis")
    assert mgr.post(f"{MQ}/quotes/{q['id']}/sage-ref", json={"sage_quote_number": "QT99002", "verified": True}).status_code == 409
    S["pub"] = g


def test_customer_sees_coverage_and_expiry_flag(cust):
    d = cust.get(f"{API}/mod/site/quotes").json()
    grp = next(x for x in d["groups"] if x["id"] == S["g"]["id"])
    q = grp["quotes"][0]
    assert q["is_expired"] is False and set(q["coverage_summary"]) == {"A", "B"}


def test_extend_validity_validation(mgr, rep):
    gid = S["g"]["id"]
    assert rep.post(f"{MQ}/groups/{gid}/extend-validity", json={"valid_until": "2099-01-01", "reason": "TEST extension reason"}).status_code == 403
    assert mgr.post(f"{MQ}/groups/{gid}/extend-validity", json={"valid_until": "2020-01-01", "reason": "TEST extension reason"}).status_code == 422
    assert mgr.post(f"{MQ}/groups/{gid}/extend-validity", json={"valid_until": "2099-01-01", "reason": "short"}).status_code == 422
    bad = mgr.post(f"{MQ}/groups/{gid}/extend-validity", json={"valid_until": "not-a-date", "reason": "TEST extension reason"})
    S["bad_date_status"] = bad.status_code
    good = (date.today() + timedelta(days=45)).isoformat()
    r = mgr.post(f"{MQ}/groups/{gid}/extend-validity", json={"valid_until": good, "reason": "TEST extension reason"})
    assert r.status_code == 200 and r.json()["updated"] >= 1
    assert bad.status_code == 422, f"non-date valid_until accepted: {bad.status_code}"


def test_expired_quote_cannot_be_authorised(cust):
    q = S["pub"]["quotes"][0]
    db = _db()
    db.crm2_quotes.update_one({"id": q["id"]}, {"$set": {"valid_until": "2020-01-01"}})
    try:
        r = cust.post(f"{API}/mod/site/quotes/{q['id']}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"})
        assert r.status_code == 409 and "expired" in r.text
    finally:
        db.crm2_quotes.update_one({"id": q["id"]}, {"$set": {"valid_until": (date.today() + timedelta(days=30)).isoformat()}})


# notify must be dry-run (MOD_QUOTE_NOTIFY_LIVE unset)
def test_notify_dry_run(mgr):
    gid = S["g"]["id"]
    r = mgr.post(f"{MQ}/groups/{gid}/notify", json={"to": "test_officer@example.test", "confirm_to": "wrong@example.test"})
    assert r.status_code == 422
    r = mgr.post(f"{MQ}/groups/{gid}/notify", json={"to": "test_officer@example.test", "confirm_to": "TEST_OFFICER@example.test"})
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True and r.json()["sent"] is False
    ev = [e["kind"] for e in mgr.get(f"{MQ}/groups/{gid}").json()["events"]]
    assert "customer_notification_dry_run" in ev and "customer_notified" not in ev


# authorise → accept → handover setup (idempotent, role-gated)
def test_accept_and_handover_setup(mgr, rep, cust):
    qa = next(q for q in S["pub"]["quotes"] if q["mod_quote_type"] == "A")
    r = cust.post(f"{API}/mod/site/quotes/{qa['id']}/authorise", data={"authorising_officer": "TEST_Maj", "authorisation_date": "2026-01-10"})
    assert r.status_code == 200, r.text
    aid = r.json()["authorisation"]["id"]
    r = mgr.post(f"{MQ}/authorisations/{aid}/verify", json={"accept": True})
    assert r.status_code == 200, r.text
    hid = r.json()["handover_id"]
    h = mgr.get(f"{MQ}/handovers/{hid}").json()
    assert h["source_quote_number"] == qa["quote_number"] and isinstance(h["outstanding"], list)
    assert rep.post(f"{MQ}/handovers/{hid}/setup", json={"start_date": "2026-02-01"}).status_code == 403
    r1 = mgr.post(f"{MQ}/handovers/{hid}/setup", json={"start_date": "2026-02-01", "notes": "TEST"})
    assert r1.status_code == 200, r1.text
    r2 = mgr.post(f"{MQ}/handovers/{hid}/setup", json={"start_date": "2026-02-01"})
    assert r2.json().get("already") is True
    assert _db().mod_service_contracts.count_documents({"source_handover_id": hid}) == len(r1.json()["records"])
    # Option A has no B-coverage lines → only an A contract expected
    assert [x["contract_type"] for x in r1.json()["records"]] == ["A"]
    # stale/failed quotes must not be resurrected as not_selected visible
    stale = list(_db().crm2_quotes.find({"mod_group_id": S["g"]["id"], "status": "failed_staging"}, {"customer_visible": 1}))
    assert all(not q.get("customer_visible") for q in stale)


def test_handover_setup_rejects_bad_date(mgr):
    g = _create(mgr)
    pub = _publish(mgr, g)
    q = pub["quotes"][0]
    r = _cust_session().post(f"{API}/mod/site/quotes/{q['id']}/authorise", data={"authorising_officer": "TEST_y", "authorisation_date": "2026-01-10"})
    assert r.status_code == 200
    hid = mgr.post(f"{MQ}/authorisations/{r.json()['authorisation']['id']}/verify", json={"accept": True}).json()["handover_id"]
    r = mgr.post(f"{MQ}/handovers/{hid}/setup", json={"start_date": "rubbish"})
    assert r.status_code == 422, f"start_date 'rubbish' accepted: {r.status_code} {r.text[:200]}"


def _cust_session():
    return _login("modsite.officer@army.mod.test", "ModSite123!", "mod")


# structured commercial exceptions for unverified rates (sor-3 Spinning Bikes is unverified in preview)
def test_commercial_exceptions(mgr):
    rows = [{"row_id": "u0", "rate_card_id": "sor-3", "description": "Spin bikes", "qty": 2, "coverage": "A", "label": ""}]
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": rows, "options": ["A"], "notes": "TEST_iter316_exc"})
    assert r.status_code == 200, r.text
    g = r.json()
    CREATED.append(g["id"])
    q = g["quotes"][0]
    if not q.get("unverified_rate_lines"):
        pytest.skip("sor-3 no longer unverified")
    ln = q["unverified_rate_lines"][0]
    mgr.post(f"{MQ}/groups/{g['id']}/submit")
    r = mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True})
    assert r.status_code == 422 and r.json()["detail"]["lines"], r.text
    base = {"quote_id": q["id"], "line_no": ln["line_no"], "reason": "TEST commercial exception reason",
            "original_rate": ln["unit_price"], "proposed_rate": ln["unit_price"], "valid_until": (date.today() + timedelta(days=5)).isoformat()}
    assert mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": [{**base, "proposed_rate": 1.0}]}).status_code == 422
    assert mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": [{**base, "valid_until": "2020-01-01"}]}).status_code == 422
    assert mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": [{**base, "reason": "short"}]}).status_code == 422
    r = mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": [base]})
    assert r.status_code == 200, r.text
    r = mgr.post(f"{MQ}/groups/{g['id']}/publish", json={"quote_ids": [q["id"]]})
    assert r.status_code == 200, r.text
    snap = _db().crm2_quotes.find_one({"id": q["id"]})["pricing_snapshot"]
    assert snap["commercial_exceptions"][0]["authorised_by"]
