"""Iter 317 – narrow retest of iter316 fixes: date typing (extend/setup), concurrent revise guard, regex escape,
portal published_at + Sage number as quote_number. Cleans up only the groups it creates."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
import sys
import threading

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(REPO + "/frontend/.env")
load_dotenv(REPO + "/backend/.env")
sys.path.insert(0, os.path.dirname(__file__))
from mod_quotes_test_helpers import delete_groups, run  # noqa: E402
from test_mod_quotes_stabilisation_iter316 import CUSTOMER, ROWS, _exceptions_for  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MQ = f"{API}/mod-ops/quotes"
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
CREATED: list[str] = []
S: dict = {}


def _db():
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw, portal=None):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw, **({"portal": portal} if portal else {})}, headers=BYPASS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def mgr():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


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


def _create(mgr):
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"], "notes": "TEST_iter317"})
    assert r.status_code == 200, r.text
    CREATED.append(r.json()["id"])
    return r.json()


# regex escape on search
@pytest.mark.parametrize("path", ["/groups", "/customers"])
def test_search_paren_no_regex_error(mgr, path):
    r = mgr.get(f"{MQ}{path}", params={"q": "("})
    assert r.status_code == 200, r.text[:200]


# concurrent revise -> exactly one wins (repeat 3 times to catch races)
@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_concurrent_revise_one_wins(mgr, attempt):
    g = _create(mgr)
    out = []
    barrier = threading.Barrier(2)

    def go(q):
        rows = [dict(r) for r in ROWS]
        rows[0]["qty"] = q
        barrier.wait()
        # independent connections (shared Session pool can serialise the two calls)
        out.append(requests.put(f"{MQ}/groups/{g['id']}", headers=dict(mgr.headers), json={"customer": CUSTOMER, "rows": rows, "options": ["A", "B"]}))
    ts = [threading.Thread(target=go, args=(q,)) for q in (3, 4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    codes = sorted(r.status_code for r in out)
    cur = mgr.get(f"{MQ}/groups/{g['id']}").json()["quotes"]
    assert sorted(q["mod_quote_type"] for q in cur) == ["A", "B"], [q["mod_quote_type"] for q in cur]
    assert codes == [200, 409], codes
    loser = next(r for r in out if r.status_code == 409)
    assert "changed by someone else" in loser.text
    # db: exactly one current (non hidden) quote per option
    vis = list(_db().crm2_quotes.find({"mod_group_id": g["id"], "status": {"$nin": ["superseded", "staging", "failed_staging"]}}, {"mod_quote_type": 1}))
    assert sorted(v["mod_quote_type"] for v in vis) == ["A", "B"]


# extend-validity non-date -> 422; publish w/ Sage number first for portal check
def test_publish_with_sage_then_extend_bad_date(mgr):
    g = _create(mgr)
    qa = next(q for q in g["quotes"] if q["mod_quote_type"] == "A")
    r = mgr.post(f"{MQ}/quotes/{qa['id']}/sage-ref", json={"sage_quote_number": "QT31701", "verified": True})
    assert r.status_code == 200, r.text
    assert mgr.post(f"{MQ}/groups/{g['id']}/submit").status_code == 200
    g2 = mgr.get(f"{MQ}/groups/{g['id']}").json()
    r = mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": _exceptions_for(g2)})
    assert r.status_code == 200, r.text
    r = mgr.post(f"{MQ}/groups/{g['id']}/publish", json={"quote_ids": [q["id"] for q in g2["quotes"]]})
    assert r.status_code == 200, r.text
    S["pub"] = r.json()
    for bad in ("not-a-date", "", "2026-13-45", 12345):
        rr = mgr.post(f"{MQ}/groups/{g['id']}/extend-validity", json={"valid_until": bad, "reason": "0123456789"})
        assert rr.status_code == 422, f"{bad!r}: {rr.status_code}"


def test_portal_group_published_at_and_sage(cust):
    d = cust.get(f"{API}/mod/site/quotes").json()
    grp = next(x for x in d["groups"] if x["id"] == S["pub"]["id"])
    assert grp["published_at"]
    qa = next(q for q in grp["quotes"] if q["mod_quote_type"] == "A")
    qb = next(q for q in grp["quotes"] if q["mod_quote_type"] == "B")
    assert qa["quote_number"] == "QT31701" and qa["internal_ref"].startswith("PFQ-")
    assert qb["quote_number"].startswith("PFQ-")


def test_handover_setup_bad_date(mgr, cust):
    q = S["pub"]["quotes"][0]
    r = cust.post(f"{API}/mod/site/quotes/{q['id']}/authorise", data={"authorising_officer": "TEST_z", "authorisation_date": "2026-01-10"})
    assert r.status_code == 200, r.text
    v = mgr.post(f"{MQ}/authorisations/{r.json()['authorisation']['id']}/verify", json={"accept": True})
    assert v.status_code == 200, v.text
    hid = v.json()["handover_id"]
    for bad in ("rubbish", "2026-02-30"):
        rr = mgr.post(f"{MQ}/handovers/{hid}/setup", json={"start_date": bad})
        assert rr.status_code == 422, f"{bad}: {rr.status_code}"
    assert _db().mod_service_contracts.count_documents({"source_handover_id": hid}) == 0
