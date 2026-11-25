"""HTTP regression tests (public URL) for MOD Operations → Quotations + MODService customer quotes portal."""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from mod_quotes_test_helpers import create_other, delete_groups, delete_other, run  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MQ = f"{API}/mod-ops/quotes"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
RUN = uuid.uuid4().hex[:6]

CLYDE = [("sor-5", "Benches", 2, "B", ""), ("sor-20", "Single Station Strength", 4, "B", ""),
         ("sor-23", "Multigym 2 Station", 1, "B", ""), ("sor-2", "Treadmills", 2, "A", ""),
         ("sor-8", "Cross Trainer", 1, "A", ""), ("sor-4", "Rowers", 2, "A", "Rowers"),
         ("sor-4", "Ski-Ergs", 2, "A", "Ski-Ergs"), ("sor-18", "Airbikes", 2, "A", "Airbikes"),
         ("sor-18", "Assault Bikes", 2, "A", "Assault Bikes")]
ROWS = [{"row_id": f"r{i}", "rate_card_id": rid, "description": d, "qty": q, "coverage": cv, "label": lb}
        for i, (rid, d, q, cv, lb) in enumerate(CLYDE)]
TOTALS = {"A": (2178.42, 435.68, 2614.10), "B": (379.00, 75.80, 454.80), "AB": (1685.24, 337.05, 2022.29)}
CUSTOMER = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane", "Helensburgh", "Dunbartonshire", "G84 0EH", "Great Britain"]}
CREATED: list[str] = []
STATE: dict = {}


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def mgr():
    s = _mgr_session()
    from pymongo import MongoClient
    coll = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].mod_sor_rate_card
    snapshot = list(coll.find({}, {"_id": 0}))
    from tests.mod_quote_fixtures import synthetic_sor_bytes
    r = s.post(f"{API}/mod-ops/quotes/rates/import-preview", files={"file": ("sor.xlsx", synthetic_sor_bytes())})
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/mod-ops/quotes/rates/{r.json()['price_list_id']}/approve", json={"effective_from": "2026-01-01", "confirm": True})
    if r.status_code == 409 and "SYNTHETIC" in r.text:
        pytest.skip("Target server protects its live rate card from synthetic data; "
                    "run against a test server started with MOD_RATES_ALLOW_SYNTHETIC=true")
    assert r.status_code == 200, r.text
    yield s

    for e in snapshot:
        coll.replace_one({"id": e["id"]}, e)


def _mgr_session():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def cust():
    return _login("modsite.officer@army.mod.test", "ModSite123!", "mod")


@pytest.fixture(scope="module")
def other():
    info = run(create_other(RUN))
    s = _login(info["email"], info["password"], "mod")
    yield s
    run(delete_other(info["org_id"], info["user_id"]))


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED:
        run(delete_groups(CREATED))


# capabilities
def test_caps(mgr, rep):
    m = mgr.get(f"{MQ}/me").json()
    r = rep.get(f"{MQ}/me").json()
    assert m["manager"] and m["pricing"]
    assert r["sales"] and not r["manager"] and not r["pricing"]
    assert rep.get(f"{MQ}/rates/price-lists").status_code == 403


# customer search
def test_customer_search(mgr):
    r = mgr.get(f"{MQ}/customers", params={"q": "MOD Test Site"})
    assert r.status_code == 200
    assert any(c["site_id"] == SITE for c in r.json()["customers"])


# preview totals reference
def test_preview_reference_totals(mgr):
    r = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B", "AB"]})
    assert r.status_code == 200, r.text
    o = r.json()["options"]
    for t, (n, v, g) in TOTALS.items():
        assert (o[t]["net"], o[t]["vat"], o[t]["gross"]) == (n, v, g), (t, o[t]["net"], o[t]["vat"], o[t]["gross"])
    codes_b = [ln["item_code"] for ln in o["B"]["lines"]]
    assert codes_b[:2] == ["CON-MOD-002", "MOD-CALLOUT"]
    assert "MOD-CALLOUT" not in [ln["item_code"] for ln in o["AB"]["lines"]]


# qty change recalculates
def test_preview_recalc(mgr):
    rows = [dict(r) for r in ROWS]
    rows[3]["qty"] = 3
    o = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": rows, "options": ["A", "B", "AB"]}).json()["options"]
    assert o["A"]["gross"] > 2614.10 and o["B"]["gross"] > 454.80 and o["AB"]["gross"] > 2022.29


# CSV import
def test_import_csv(mgr):
    files = {"file": ("eq.csv", b"Description,Qty\nTreadmill,2\nRowing machine,2\n", "text/csv")}
    r = mgr.post(f"{MQ}/import-equipment", files=files)
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 2 and rows[0]["qty"] == 2
    STATE["import_rows"] = rows


# full workflow
def test_create_group(mgr):
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B", "AB"], "notes": f"TEST_{RUN}"})
    assert r.status_code == 200, r.text
    g = r.json()
    CREATED.append(g["id"])
    STATE["gid"] = g["id"]
    assert g["status"] == "draft" and len(g["quotes"]) == 3
    assert all(q["quote_number"].startswith("PFQ-") for q in g["quotes"])
    STATE["q"] = {q["mod_quote_type"]: q["id"] for q in g["quotes"]}


def test_draft_not_visible_to_customer(cust):
    r = cust.get(f"{API}/mod/site/quotes")
    assert r.status_code == 200
    ids = {q["id"] for q in r.json()["quotes"]}
    assert not ids & set(STATE["q"].values())
    assert cust.get(f"{API}/mod/site/quotes/{STATE['q']['A']}").status_code == 404


def test_submit_and_rep_cannot_approve(mgr, rep):
    gid = STATE["gid"]
    assert mgr.post(f"{MQ}/groups/{gid}/submit").status_code == 200
    assert mgr.post(f"{MQ}/groups/{gid}/submit").status_code == 409
    assert rep.post(f"{MQ}/groups/{gid}/approve", json={"approve": True}).status_code == 403


def test_approve_and_publish(mgr):
    gid = STATE["gid"]
    r = mgr.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "commercial_exception_reason": "TEST exception reason for test"})
    assert r.status_code == 200, r.text
    r = mgr.post(f"{MQ}/groups/{gid}/publish", json={"quote_ids": list(STATE["q"].values())})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"
    assert mgr.get(f"{MQ}/quotes/{STATE['q']['A']}/pdf").content[:4] == b"%PDF"
    z = mgr.get(f"{MQ}/groups/{gid}/pdfs.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"


def test_customer_sees_published_and_isolation(cust, other):
    r = cust.get(f"{API}/mod/site/quotes").json()
    grp = next(g for g in r["groups"] if g["id"] == STATE["gid"])
    assert [q["mod_quote_type"] for q in grp["quotes"]] == ["A", "B", "AB"]
    assert cust.get(f"{API}/mod/site/quotes/{STATE['q']['AB']}/pdf").content[:4] == b"%PDF"
    assert cust.get(f"{API}/mod/site/quote-groups/{STATE['gid']}/zip").content[:2] == b"PK"
    assert other.get(f"{API}/mod/site/quotes/{STATE['q']['AB']}").status_code == 404
    assert other.get(f"{API}/mod/site/quote-groups/{STATE['gid']}/zip").status_code == 404
    assert cust.post(f"{API}/mod/site/quotes/{STATE['q']['AB']}/sign", json={"signer_name": "x"}).status_code == 409


def test_revision_supersedes(mgr, cust):
    gid = STATE["gid"]
    rows = [dict(r) for r in ROWS]
    rows[0]["qty"] = 3
    r = mgr.put(f"{MQ}/groups/{gid}", json={"customer": CUSTOMER, "rows": rows, "options": ["A", "B", "AB"]})
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["revision"] == 2 and g["status"] == "draft" and len(g["superseded"]) == 3
    vis = {q["id"] for q in cust.get(f"{API}/mod/site/quotes").json()["quotes"]}
    assert not vis & set(STATE["q"].values()), "superseded quotes still visible"
    assert not vis & {q["id"] for q in g["quotes"]}, "new draft revision visible"
    mgr.post(f"{MQ}/groups/{gid}/submit")
    mgr.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "commercial_exception_reason": "TEST exception reason for test"})
    ids = [q["id"] for q in g["quotes"]]
    assert mgr.post(f"{MQ}/groups/{gid}/publish", json={"quote_ids": ids}).status_code == 200
    STATE["q2"] = {q["mod_quote_type"]: q["id"] for q in g["quotes"]}


def test_authorise_and_accept_idempotent(mgr, cust):
    qid = STATE["q2"]["AB"]
    old = STATE["q"]["AB"]
    assert cust.post(f"{API}/mod/site/quotes/{old}/authorise", data={"authorising_officer": "x", "authorisation_date": "2026-01-10"}).status_code == 404
    r = cust.post(f"{API}/mod/site/quotes/{qid}/authorise",
                  data={"authorising_officer": "TEST_Maj Smith", "authorisation_date": "2026-01-10", "po_reference": f"TEST-PO-{RUN}"},
                  files={"evidence": ("po.txt", b"TEST evidence", "text/plain")})
    assert r.status_code == 200, r.text
    aid = r.json()["authorisation"]["id"]
    assert cust.post(f"{API}/mod/site/quotes/{qid}/authorise", data={"authorising_officer": "x", "authorisation_date": "2026-01-10"}).status_code == 409
    q = mgr.get(f"{MQ}/authorisations").json()["items"]
    assert any(a["id"] == aid for a in q)
    assert mgr.get(f"{MQ}/authorisations/{aid}/evidence").content == b"TEST evidence"
    r = mgr.post(f"{MQ}/authorisations/{aid}/verify", json={"accept": True})
    assert r.status_code == 200, r.text
    assert mgr.post(f"{MQ}/authorisations/{aid}/verify", json={"accept": True}).status_code == 409
    g = mgr.get(f"{MQ}/groups/{STATE['gid']}").json()
    assert g["status"] == "handed_over" and g["accepted_quote_id"] == qid
    hs = [h for h in mgr.get(f"{MQ}/handovers").json()["items"] if h["group_id"] == STATE["gid"]]
    assert len(hs) == 1
    assert mgr.put(f"{MQ}/groups/{STATE['gid']}", json={"customer": CUSTOMER, "rows": ROWS}).status_code == 409


def test_revision_with_pending_auth_blocks_new_auth(mgr, cust):
    """Edge: revise while an authorisation is pending → can customer authorise the new revision?"""
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"]})
    g = r.json()
    CREATED.append(g["id"])
    gid = g["id"]
    mgr.post(f"{MQ}/groups/{gid}/submit")
    mgr.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "commercial_exception_reason": "TEST exception reason for test"})
    mgr.post(f"{MQ}/groups/{gid}/publish", json={"quote_ids": [q["id"] for q in g["quotes"]]})
    qa = next(q["id"] for q in g["quotes"] if q["mod_quote_type"] == "A")
    assert cust.post(f"{API}/mod/site/quotes/{qa}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"}).status_code == 200
    # revision while authorisation_submitted: Edit button hidden in UI for this status, API allows it
    r = mgr.put(f"{MQ}/groups/{gid}", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"]})
    STATE["rev_with_pending_status"] = r.status_code
    if r.status_code != 200:
        return
    g2 = r.json()
    mgr.post(f"{MQ}/groups/{gid}/submit")
    mgr.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "commercial_exception_reason": "TEST exception reason for test"})
    mgr.post(f"{MQ}/groups/{gid}/publish", json={"quote_ids": [q["id"] for q in g2["quotes"]]})
    qa2 = next(q["id"] for q in g2["quotes"] if q["mod_quote_type"] == "A")
    r = cust.post(f"{API}/mod/site/quotes/{qa2}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"})
    assert r.status_code == 200, f"stale pending authorisation blocks new revision: {r.status_code} {r.text}"
