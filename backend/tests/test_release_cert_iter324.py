"""Iter324: final release certification — verifies the iter323 follow-up fixes.
Engineers: deactivation reassign outside coverage needs override reason (422 code outside_coverage, atomic),
'keep' = management hold (unassigned + hold flags, survives reactivation, cleared by allocate), held jobs vs engineer
queue, dangling coverage ids don't block unrelated edits (MOD Ops + Master Admin parity).
Quotes follow-ups: email state machine (awaiting_approval → release 409 while off / cancel), RBAC, idempotent run,
dispatch_ready exactly-once under concurrency (send_email mocked — no real email)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url  # noqa: E402
from utils.auth import create_token  # noqa: E402

API = f"{_test_backend_url().rstrip('/')}/api"
B = f"{API}/bfpo"
MQ = f"{API}/mod-ops/quotes"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
RUN = uuid.uuid4().hex[:8]
INHOUSE = "pulse-inhouse-mod"
MOD_SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
ENG: dict = {}
CASES: list = []
GROUPS: list = []
FUPS: list = []


def _sess(token):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def _login_sess(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed {email}: {r.status_code}")
    return _sess(r.json()["token"])


@pytest.fixture(scope="module")
def mgr():
    return _login_sess("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login_sess("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def admin():
    a = DB.users.find_one({"email": "admin@pulsefitness.com"}, {"id": 1})
    return _sess(create_token(a["id"], mfa_verified=True))


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for e in ENG.values():
        DB.users.delete_one({"id": e["id"]})
        DB.svc_engineers.delete_many({"id": e["id"]})
        DB.bfpo_invites.delete_many({"user_id": e["id"]})
    for cid in CASES:
        DB.svc_cases.delete_one({"id": cid})
        for c in ("svc_case_events", "svc_events", "case_events"):
            DB[c].delete_many({"case_id": cid})
    for gid in GROUPS:
        DB.crm2_quotes.delete_many({"mod_group_id": gid})
        for c in ("mod_quote_events", "mod_quote_authorisations", "mod_quote_followups", "mod_quote_handovers"):
            DB[c].delete_many({"group_id": gid})
        DB.crm2_activities.delete_many({"mod_group_id": gid})
        DB.crm2_opportunities.delete_many({"mod_group_id": gid})
        DB.mod_quote_groups.delete_one({"id": gid})
    for fid in FUPS:
        DB.mod_quote_followups.delete_one({"id": fid})


def _eng(mgr, key, terr=None, sites=None):
    email = f"test_eng324_{key}_{RUN}@example.test"
    r = mgr.post(f"{B}/staff/engineers", json={"full_name": f"TEST_Eng324 {key}", "email": email, "bfpo_role": "engineer",
                                               "password_mode": "temp", "temp_password": "TestEng123!",
                                               "bfpo_territory_ids": terr or [], "bfpo_site_ids": sites or []})
    assert r.status_code == 200, r.text
    ENG[key] = {"id": r.json()["member"]["id"]}
    return ENG[key]["id"]


def _case(terr, site, assigned=None, status="assigned"):
    cid = f"TEST_case324_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    DB.svc_cases.insert_one({"id": cid, "organization_id": "bfpo-mod-org", "bfpo": True, "reference": f"TEST-{cid[-6:]}",
                             "title": "TEST_ iter324 job", "status": status, "priority": "p3", "territory_id": terr,
                             "site_id": site, "site_name": "TEST site", "assigned_engineer_id": assigned,
                             "created_at": now, "updated_at": now})
    CASES.append(cid)
    return cid


# ── Deactivation decisions ──
class TestDeactivationDecisions:
    def test_reassign_outside_coverage_requires_override(self, mgr):
        leaver = _eng(mgr, "leaver", terr=["terr-cyp"])
        gib = _eng(mgr, "gib", terr=["terr-gib"])
        cid = _case("terr-cyp", "site-cyp-1", assigned=leaver)
        dec = [{"case_id": cid, "action": "reassign", "engineer_id": gib, "reason": "TEST_leaving"}]
        r = mgr.post(f"{B}/staff/engineers/{leaver}/status", json={"active": False, "job_decisions": dec})
        assert r.status_code == 422, r.text
        d = r.json()["detail"]
        assert d["code"] == "outside_coverage" and d["case_id"] == cid
        # atomic: nothing applied
        assert DB.users.find_one({"id": leaver})["is_active"] is True
        assert DB.svc_cases.find_one({"id": cid})["assigned_engineer_id"] == leaver
        dec[0]["override_reason"] = "TEST_override cover"
        r = mgr.post(f"{B}/staff/engineers/{leaver}/status", json={"active": False, "job_decisions": dec})
        assert r.status_code == 200, r.text
        assert DB.svc_cases.find_one({"id": cid})["assigned_engineer_id"] == gib
        tl = str(mgr.get(f"{B}/staff/jobs/{cid}").json())
        assert "TEST_override cover" in tl and "TEST_leaving" in tl

    def test_keep_hold_survives_reactivation_and_cleared_by_allocate(self, mgr):
        leaver = _eng(mgr, "holder", terr=["terr-cyp"])
        cid = _case("terr-cyp", "site-cyp-1", assigned=leaver)
        r = mgr.post(f"{B}/staff/engineers/{leaver}/status",
                     json={"active": False, "job_decisions": [{"case_id": cid, "action": "keep", "reason": "TEST_hold"}]})
        assert r.status_code == 200, r.text
        c = DB.svc_cases.find_one({"id": cid})
        assert c["management_hold"] is True and c["assigned_engineer_id"] is None and c["held_from_engineer_id"] == leaver
        assert mgr.post(f"{B}/staff/engineers/{leaver}/status", json={"active": True}).status_code == 200
        assert DB.svc_cases.find_one({"id": cid}).get("management_hold") is True, "hold should survive reactivation"
        r = mgr.post(f"{B}/staff/jobs/{cid}/allocate", json={"engineer_id": leaver})
        assert r.status_code == 200, r.text
        c = DB.svc_cases.find_one({"id": cid})
        assert "management_hold" not in c and "held_from_engineer_id" not in c and c["assigned_engineer_id"] == leaver

    def test_held_job_not_offered_to_engineers(self, mgr):
        """A job held for management review should not appear in an in-coverage engineer's open queue."""
        leaver = _eng(mgr, "holder2", terr=["terr-cyp"])
        peer = _eng(mgr, "peer", terr=["terr-cyp"])
        cid = _case("terr-cyp", "site-cyp-1", assigned=leaver)
        r = mgr.post(f"{B}/staff/engineers/{leaver}/status",
                     json={"active": False, "job_decisions": [{"case_id": cid, "action": "keep", "reason": "TEST_hold2"}]})
        assert r.status_code == 200
        ps = _sess(create_token(peer))
        jobs = [j["id"] for j in ps.get(f"{B}/jobs").json()["jobs"]]
        r = ps.post(f"{B}/jobs/{cid}/accept", json={})
        c = DB.svc_cases.find_one({"id": cid})
        print(f"peer sees held job: {cid in jobs}; accept -> {r.status_code}; assigned={c.get('assigned_engineer_id')}; hold={c.get('management_hold')}")
        assert r.status_code in (403, 404, 409) and c.get("assigned_engineer_id") is None, \
            "engineer could self-accept a job held for management review (hold bypassed)"
        assert cid not in jobs, "management-held job is visible to in-coverage engineers as an unassigned job"

    def test_engineer_cannot_accept_job_assigned_to_other(self, mgr):
        owner_eng = _eng(mgr, "own", terr=["terr-cyp"])
        peer = ENG.get("peer", {}).get("id") or _eng(mgr, "peer", terr=["terr-cyp"])
        cid = _case("terr-cyp", "site-cyp-1", assigned=owner_eng)
        r = _sess(create_token(peer)).post(f"{B}/jobs/{cid}/accept", json={})
        c = DB.svc_cases.find_one({"id": cid})
        print(f"peer accept other's job -> {r.status_code}; assigned={c.get('assigned_engineer_id')}")
        assert c["assigned_engineer_id"] == owner_eng, "a peer engineer took over a job allocated to someone else"


# ── Dangling coverage references ──
class TestDanglingCoverage:
    def test_staff_patch_name_only_with_dangling(self, mgr):
        eid = _eng(mgr, "dangle", terr=["terr-cyp"])
        DB.users.update_one({"id": eid}, {"$push": {"bfpo_site_ids": "site-deleted-324"}})
        u = DB.users.find_one({"id": eid})
        r = mgr.patch(f"{B}/staff/engineers/{eid}", json={"full_name": "TEST_Eng324 renamed",
                                                            "bfpo_territory_ids": u["bfpo_territory_ids"], "bfpo_site_ids": u["bfpo_site_ids"]})
        assert r.status_code == 200, r.text
        # removing it works
        r = mgr.patch(f"{B}/staff/engineers/{eid}", json={"bfpo_site_ids": []})
        assert r.status_code == 200 and DB.users.find_one({"id": eid})["bfpo_site_ids"] == []
        # newly-submitted unknown still rejected
        assert mgr.patch(f"{B}/staff/engineers/{eid}", json={"bfpo_site_ids": ["site-new-unknown"]}).status_code == 422

    def test_master_admin_patch_with_dangling(self, mgr, admin):
        eid = _eng(mgr, "dangle_ma", terr=["terr-cyp"])
        DB.users.update_one({"id": eid}, {"$push": {"bfpo_site_ids": "site-deleted-324"}})
        url = f"{API}/master-admin/mod-estate/external-providers/{INHOUSE}/engineers/{eid}"
        r = admin.patch(url, json={"full_name": "TEST_Eng324 ma", "territory_ids": ["terr-cyp"], "site_ids": ["site-deleted-324"]})
        assert r.status_code == 200, f"Master Admin edit blocked by stale reference (parity gap): {r.status_code} {r.text[:200]}"


# ── Follow-up customer email state machine ──
CUSTOMER = {"site_id": MOD_SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer324", "contact_email": "test_officer324@example.test",
            "address_lines": ["Faslane"]}
ROWS = [{"row_id": "r1", "rate_card_id": "sor-2", "qty": 1, "coverage": "A", "label": ""}]


def _published(rep, mgr):
    r = rep.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A"], "idempotency_key": f"TEST_324_{uuid.uuid4()}"})
    assert r.status_code == 200, r.text
    g = r.json()
    GROUPS.append(g["id"])
    assert rep.post(f"{MQ}/groups/{g['id']}/submit").status_code == 200
    assert mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": []}).status_code == 200
    p = rep.post(f"{MQ}/groups/{g['id']}/publish", json={"quote_ids": [q["id"] for q in g["quotes"]]})
    assert p.status_code == 200, p.text
    return g["id"]


class TestFollowupEmails:
    def test_run_creates_awaiting_and_is_idempotent(self, rep, mgr):
        gid = _published(rep, mgr)
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"chase_schedule.0.due": "2026-01-01"}})
        r = mgr.post(f"{MQ}/followups/run")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["live_email"] is False and body["emails_sent"] == 0 and "awaiting_release" in body
        fs = list(DB.mod_quote_followups.find({"group_id": gid}))
        assert len(fs) == 1 and fs[0]["email_status"] == "awaiting_approval" and fs[0]["revision"] == 1
        # re-arm schedule → duplicate prevented by unique index
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"chase_schedule.0.status": "pending"}})
        assert mgr.post(f"{MQ}/followups/run").status_code == 200
        assert DB.mod_quote_followups.count_documents({"group_id": gid}) == 1
        assert DB.mod_quote_groups.find_one({"id": gid})["chase_schedule"][0]["status"] == "task_created"
        TestFollowupEmails.fid = fs[0]["id"]
        TestFollowupEmails.gid = gid

    def test_release_blocked_while_off(self, mgr):
        r = mgr.post(f"{MQ}/followups/{self.fid}/email", json={"action": "release"})
        assert r.status_code == 409 and "switched off" in r.text
        assert DB.mod_quote_followups.find_one({"id": self.fid})["email_status"] == "awaiting_approval"

    def test_rep_cannot_decide(self, rep):
        assert rep.post(f"{MQ}/followups/{self.fid}/email", json={"action": "cancel"}).status_code == 403

    def test_invalid_action_and_unknown(self, mgr):
        assert mgr.post(f"{MQ}/followups/{self.fid}/email", json={"action": "send"}).status_code == 422
        assert mgr.post(f"{MQ}/followups/nope-{RUN}/email", json={"action": "cancel"}).status_code == 404

    def test_cancel_then_locked(self, mgr):
        r = mgr.post(f"{MQ}/followups/{self.fid}/email", json={"action": "cancel", "note": "TEST_not needed"})
        assert r.status_code == 200, r.text
        f = DB.mod_quote_followups.find_one({"id": self.fid})
        assert f["email_status"] == "cancelled" and f["email_reason"] == "TEST_not needed"
        assert mgr.post(f"{MQ}/followups/{self.fid}/email", json={"action": "cancel"}).status_code == 409
        items = mgr.get(f"{MQ}/followups", params={"everyone": "true"}).json()["items"]
        assert any(i["id"] == self.fid and i["email_status"] == "cancelled" for i in items)

    def test_dispatch_exactly_once_concurrent(self, monkeypatch):
        """In-process: one `ready` follow-up, two concurrent dispatchers, send_email mocked → exactly one send."""
        if DB.mod_quote_followups.count_documents({"email_status": {"$in": ["ready", "sending"]}}):
            pytest.skip("other ready/sending follow-ups exist — would be dispatched by this test")
        from utils import email as email_mod
        from utils import mod_quote_chase as chase
        from utils.mod_quote_followup_emails import DEFAULTS
        from utils.database import db as adb
        calls = []

        async def fake_send(to, subject, html, atts=None, **kw):
            calls.append(to)
            await asyncio.sleep(0.05)
            if kw.get("result_out") is not None:
                kw["result_out"]["message_id"] = "TEST_msg_324"
            return True
        monkeypatch.setattr(email_mod, "send_email", fake_send)
        fid = f"TEST_fup324_{RUN}"
        FUPS.append(fid)
        DB.mod_quote_followups.insert_one({"id": fid, "group_id": self.gid, "organization_id": "x", "chase_no": 9,
                                           "revision": 1, "contact_email": "test_officer324@example.test", "status": "open",
                                           "email_status": "ready", "email_attempts": 0, "due": "2026-01-01"})

        async def both():
            return await asyncio.gather(chase.dispatch_ready(True, DEFAULTS | {"9": DEFAULTS["1"]}),
                                        chase.dispatch_ready(True, DEFAULTS | {"9": DEFAULTS["1"]}))
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(both())
        finally:
            loop.close()
        assert calls == ["test_officer324@example.test"], calls
        assert sum(r["sent"] for r in res) == 1
        f = DB.mod_quote_followups.find_one({"id": fid})
        assert f["email_status"] == "sent" and f["email_message_id"] == "TEST_msg_324"
        _ = adb
