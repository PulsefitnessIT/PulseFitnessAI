# Fault card title (make+model enrichment) + MOD fault email delivery fixes (A/B/C)
# All sends are MOCKED. Test data is TEST_-prefixed and removed by id afterwards.
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))


def _base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
    return url.rstrip("/")


BASE_URL = _base_url()
RUN = uuid.uuid4().hex[:6]


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _db():
    from routes.issues import db
    return db


CREATED = {"organizations": [], "users": [], "equipment": [], "issues": [],
           "suppliers": [], "email_to": []}


def now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    db = _db()

    async def go():
        for coll in ("organizations", "users", "equipment", "issues", "suppliers"):
            if CREATED[coll]:
                await db[coll].delete_many({"id": {"$in": CREATED[coll]}})
        if CREATED["issues"]:
            cases = await db.supplier_cases.find({"issue_id": {"$in": CREATED["issues"]}}, {"_id": 0, "id": 1}).to_list(100)
            cids = [c["id"] for c in cases]
            if cids:
                await db.supplier_case_comments.delete_many({"case_id": {"$in": cids}})
                await db.supplier_cases.delete_many({"id": {"$in": cids}})
        if CREATED["email_to"]:
            await db.email_send_events.delete_many({"to": {"$in": CREATED["email_to"]}})
    run(go())


# ───────────── Seed: two orgs, same serial in both ─────────────
ORG_A = f"TEST_org_a_{RUN}"
ORG_B = f"TEST_org_b_{RUN}"
USER_EMAIL = f"test_fault_{RUN}@example.test"
USER_PW = "TestFault#2026x"
IDS = {k: f"TEST_{k}_{RUN}" for k in ("eq1", "eq2", "eq3", "eqB", "i_cov", "i_serial", "i_prefix", "i_name", "i_cross", "i_none")}
JOB = f"TEST_job_{RUN}"


@pytest.fixture(scope="module")
def seeded():
    from utils.auth import hash_password
    db = _db()

    async def go():
        await db.organizations.insert_many([
            {"id": ORG_A, "name": f"TEST_Gym A {RUN}", "account_type": "gym", "created_at": now()},
            {"id": ORG_B, "name": f"TEST_Gym B {RUN}", "account_type": "gym", "created_at": now()},
        ])
        CREATED["organizations"] += [ORG_A, ORG_B]
        uid = f"TEST_user_{RUN}"
        await db.users.insert_one({"id": uid, "email": USER_EMAIL, "full_name": "TEST Fault User",
                                   "password": hash_password(USER_PW), "role": "owner",
                                   "organization_id": ORG_A, "active": True, "account_type": "gym",
                                   "must_change_password": False, "created_at": now()})
        CREATED["users"].append(uid)
        eqs = [
            {"id": IDS["eq1"], "organization_id": ORG_A, "serial_number": f"SN-A1-{RUN}", "name": "Treadmill 1",
             "manufacturer": "Life Fitness", "model": "95T", "equipment_type": "Treadmill"},
            {"id": IDS["eq2"], "organization_id": ORG_A, "serial_number": f"SN-A2-{RUN}", "name": "Bike 2",
             "manufacturer": "Life Fitness", "model": "Life Fitness Integrity", "equipment_type": "Bike"},
            {"id": IDS["eq3"], "organization_id": ORG_A, "serial_number": "", "name": f"NAME-{RUN}",
             "manufacturer": "Precor", "model": "EFX 835", "equipment_type": "Cross Trainer"},
            {"id": IDS["eqB"], "organization_id": ORG_B, "serial_number": f"SN-SHARED-{RUN}", "name": "Other org",
             "manufacturer": "Technogym", "model": "Excite", "equipment_type": "Treadmill"},
        ]
        await db.equipment.insert_many(eqs)
        CREATED["equipment"] += [e["id"] for e in eqs]
        base = {"organization_id": ORG_A, "status": "open", "severity": "medium",
                "issue_description": "TEST_ fault", "created_at": now()}
        issues = [
            {**base, "id": IDS["i_cov"], "serial_number": "UNRELATED", "machine_type": "Treadmill",
             "coverage_meta": {"equipment_id": IDS["eq1"]}, "job_id": JOB},
            {**base, "id": IDS["i_serial"], "serial_number": f"SN-A1-{RUN}", "machine_type": "Treadmill", "job_id": JOB},
            {**base, "id": IDS["i_prefix"], "serial_number": f"SN-A2-{RUN}", "machine_type": "Bike"},
            {**base, "id": IDS["i_name"], "serial_number": f"NAME-{RUN}", "machine_type": ""},
            {**base, "id": IDS["i_cross"], "serial_number": f"SN-SHARED-{RUN}", "machine_type": "Treadmill"},
            {**base, "id": IDS["i_none"], "serial_number": f"SN-NONE-{RUN}", "machine_type": ""},
        ]
        await db.issues.insert_many(issues)
        CREATED["issues"] += [i["id"] for i in issues]
    run(go())
    return True


@pytest.fixture(scope="module")
def token(seeded):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": USER_EMAIL, "password": USER_PW}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}: {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


def _get_issues(token):
    r = requests.get(f"{BASE_URL}/api/issues", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return {i["id"]: i for i in r.json()["issues"]}


class TestTitleEnrichment:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=20)
        assert r.status_code == 200

    def test_coverage_meta_and_serial_match(self, token):
        by = _get_issues(token)
        for k in ("i_cov", "i_serial"):
            i = by[IDS[k]]
            assert i["equipment_make"] == "Life Fitness"
            assert i["equipment_model"] == "95T"
            assert i["equipment_type"] == "Treadmill"
            assert i["equipment_name"] == "Treadmill 1"

    def test_name_match_and_prefix_model(self, token):
        by = _get_issues(token)
        assert by[IDS["i_prefix"]]["equipment_model"] == "Life Fitness Integrity"
        assert by[IDS["i_name"]]["equipment_make"] == "Precor"
        assert by[IDS["i_name"]]["equipment_model"] == "EFX 835"

    def test_no_cross_org_match(self, token):
        by = _get_issues(token)
        i = by[IDS["i_cross"]]
        for f in ("equipment_make", "equipment_model", "equipment_name", "equipment_type"):
            assert f not in i, f"cross-org leak: {f}={i.get(f)}"

    def test_no_match_has_no_fields(self, token):
        i = _get_issues(token)[IDS["i_none"]]
        assert "equipment_make" not in i and "equipment_model" not in i

    def test_jobs_endpoint_enriched(self, token):
        r = requests.get(f"{BASE_URL}/api/issues/jobs/{JOB}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 2
        assert all(i.get("equipment_make") == "Life Fitness" for i in d["issues"])


# ───────────── Fix A: _send_comment_notification ─────────────
class _FakeEmails:
    def __init__(self, fail_for):
        self.fail_for = {e.lower() for e in fail_for}
        self.calls = []

    def send(self, params):
        self.calls.append(params)
        if params["to"][0].lower() in self.fail_for:
            raise Exception("TEST_ simulated provider rejection")
        return {"id": "fake"}


class _FakeResend:
    def __init__(self, fail_for):
        self.Emails = _FakeEmails(fail_for)
        self.api_key = None


class TestCommentNotificationFixA:
    def _setup(self, monkeypatch, acct_type, fail_for):
        import routes.supplier_portal as sp
        fake = _FakeResend(fail_for)
        monkeypatch.setattr(sp, "resend", fake)
        monkeypatch.setattr(sp, "RESEND_API_KEY", "re_test_fake")
        db = _db()
        org_id = f"TEST_org_{acct_type}_{uuid.uuid4().hex[:6]}"
        issue_id = f"TEST_issue_{uuid.uuid4().hex[:8]}"
        run(db.organizations.insert_one({"id": org_id, "name": "TEST_ Org", "account_type": acct_type}))
        run(db.issues.insert_one({"id": issue_id, "organization_id": org_id, "machine_type": "Treadmill",
                                  "status": "open", "created_at": now()}))
        CREATED["organizations"].append(org_id)
        CREATED["issues"].append(issue_id)
        return sp, fake, issue_id

    def _case(self, issue_id, emails, acct=None):
        c = {"id": f"TEST_case_{uuid.uuid4().hex[:6]}", "issue_id": issue_id, "token": "TESTTOKEN",
             "supplier_name": "TEST Supplier", "supplier_email": emails[0], "organization_name": "TEST_ Org",
             "notify_emails": [{"email": e} for e in emails]}
        if acct:
            c["organization_account_type"] = acct
        return c

    def test_mod_case_from_mod_sender_partial_failure(self, monkeypatch):
        sp, fake, issue_id = self._setup(monkeypatch, "mod_site", [])
        ok, bad = f"ok_{RUN}@example.test", f"bad_{RUN}@example.test"
        fake.Emails.fail_for = {bad}
        CREATED["email_to"] += [ok, bad]
        comment = {"id": "c1", "message": "TEST_ msg", "author_name": "T", "author_role": "gym",
                   "created_at": now(), "attachments": []}
        res = run(sp._send_comment_notification(self._case(issue_id, [bad, ok.upper()]), comment, True))
        assert res == [ok.lower()]
        assert len(fake.Emails.calls) == 2
        for c in fake.Emails.calls:
            assert "@modservice.pulsefitness.com" in c["from"].lower(), c["from"]
            assert "pulsefitness.ai" not in c["from"].lower()
        rows = run(_db().email_send_events.find({"to": {"$in": [ok.upper(), bad]}}, {"_id": 0}).to_list(10))
        st = {r["to"].lower(): r["status"] for r in rows}
        CREATED["email_to"].append(ok.upper())
        assert st.get(ok) == "sent" and st.get(bad) == "failed", rows

    def test_mod_by_case_account_type(self, monkeypatch):
        sp, fake, issue_id = self._setup(monkeypatch, "gym", [])
        to = f"modacct_{RUN}@example.test"
        CREATED["email_to"].append(to)
        comment = {"id": "c2", "message": "m", "author_name": "T", "author_role": "gym", "created_at": now(), "attachments": []}
        res = run(sp._send_comment_notification(self._case(issue_id, [to], acct="mod_hq"), comment, True))
        assert res == [to]
        assert "@modservice.pulsefitness.com" in fake.Emails.calls[0]["from"].lower()

    def test_non_mod_case_uses_faults_ai_sender(self, monkeypatch):
        sp, fake, issue_id = self._setup(monkeypatch, "gym", [])
        to = f"gym_{RUN}@example.test"
        CREATED["email_to"].append(to)
        comment = {"id": "c3", "message": "m", "author_name": "T", "author_role": "gym", "created_at": now(), "attachments": []}
        res = run(sp._send_comment_notification(self._case(issue_id, [to]), comment, True))
        assert res == [to]
        assert "faults@service.pulsefitness.ai" in fake.Emails.calls[0]["from"].lower(), fake.Emails.calls[0]["from"]


# ───────────── Fix B: auto-dispatch + MOD fault notifications ─────────────
class TestModFaultNotificationsFixB:
    def _mod_org(self, with_overseas=True):
        db = _db()
        org_id = f"TEST_modsite_{uuid.uuid4().hex[:6]}"
        sup_id = f"TEST_sup_{uuid.uuid4().hex[:6]}"
        ov_email = f"overseas_{RUN}@example.test"
        doc = {"id": org_id, "name": "TEST_ MOD Site", "account_type": "mod_site"}
        if with_overseas:
            doc["service_supplier_id"] = sup_id
            run(db.suppliers.insert_one({"id": sup_id, "organization_id": org_id, "name": "TEST Overseas", "email": ov_email}))
            CREATED["suppliers"].append(sup_id)
        run(db.organizations.insert_one(doc))
        CREATED["organizations"].append(org_id)
        return org_id, ov_email

    def _issue(self, org_id, delivered_to):
        iid = f"TEST_modissue_{uuid.uuid4().hex[:8]}"
        d = {"id": iid, "organization_id": org_id, "status": "open", "machine_type": "Treadmill",
             "severity": "high", "issue_description": "TEST_", "created_at": now(),
             "auto_dispatched_supplier_email": f"pulse_{RUN}@example.test",
             "auto_dispatched_supplier_name": "Pulse", "auto_dispatch_delivered_to": delivered_to}
        run(_db().issues.insert_one(dict(d)))
        CREATED["issues"].append(iid)
        return d

    def _patch(self, monkeypatch, raise_for=()):
        import utils.email as ue
        from fastapi import HTTPException
        calls = []

        async def fake_send(to, subject, html, *a, **kw):
            calls.append((to, kw.get("kind")))
            if to.lower() in raise_for:
                raise HTTPException(400, "TEST_ recipient rejected")
            return True
        monkeypatch.setattr(ue, "send_email", fake_send)
        monkeypatch.setenv("MOD_SERVICE_EMAIL", f"pulse_{RUN}@example.test")
        return calls

    def test_thread_failed_pulse_gets_direct_email(self, monkeypatch):
        from routes.issues import _send_mod_fault_notifications
        calls = self._patch(monkeypatch)
        org_id, ov = self._mod_org(with_overseas=False)
        doc = self._issue(org_id, [])
        run(_send_mod_fault_notifications(doc, {"organization_id": org_id}))
        assert (f"pulse_{RUN}@example.test", "mod_fault_pulse") in calls
        stored = run(_db().issues.find_one({"id": doc["id"]}, {"_id": 0}))
        p = [n for n in stored["notified_recipients"] if n["role"] == "pulse"][0]
        assert p["delivered"] is True and p.get("via") != "supplier_thread"

    def test_thread_delivered_no_duplicate(self, monkeypatch):
        from routes.issues import _send_mod_fault_notifications
        calls = self._patch(monkeypatch)
        org_id, ov = self._mod_org(with_overseas=False)
        doc = self._issue(org_id, [f"PULSE_{RUN}@example.test".lower()])
        run(_send_mod_fault_notifications(doc, {"organization_id": org_id}))
        assert not any(c[1] == "mod_fault_pulse" for c in calls)
        stored = run(_db().issues.find_one({"id": doc["id"]}, {"_id": 0}))
        p = [n for n in stored["notified_recipients"] if n["role"] == "pulse"][0]
        assert p["delivered"] is True and p["via"] == "supplier_thread"

    def test_one_failure_does_not_stop_others(self, monkeypatch):
        from routes.issues import _send_mod_fault_notifications
        pulse = f"pulse_{RUN}@example.test"
        calls = self._patch(monkeypatch, raise_for={pulse})
        org_id, ov = self._mod_org(with_overseas=True)
        doc = self._issue(org_id, [])
        run(_send_mod_fault_notifications(doc, {"organization_id": org_id}))
        assert (ov, "mod_fault_overseas") in calls
        stored = run(_db().issues.find_one({"id": doc["id"]}, {"_id": 0}))
        nr = {n["role"]: n for n in stored["notified_recipients"]}
        assert nr["pulse"]["delivered"] is False and "rejected" in nr["pulse"]["error"]
        assert nr["overseas"]["delivered"] is True

    def test_auto_dispatch_stores_delivered_to(self, monkeypatch):
        import routes.issues as ri
        import routes.supplier_portal as sp
        org_id = f"TEST_gymdisp_{uuid.uuid4().hex[:6]}"
        run(_db().organizations.insert_one({"id": org_id, "name": "TEST_ Gym", "account_type": "gym"}))
        CREATED["organizations"].append(org_id)
        iid = f"TEST_disp_{uuid.uuid4().hex[:8]}"
        doc = {"id": iid, "organization_id": org_id, "status": "open", "machine_type": "Bike",
               "issue_description": "TEST_", "created_at": now()}
        run(_db().issues.insert_one(dict(doc)))
        CREATED["issues"].append(iid)
        sup_email = f"disp_{RUN}@example.test"

        async def fake_resolve(issue_doc, oid):
            return {"id": "TEST_sup", "name": "TEST Disp Supplier", "email": sup_email}

        async def fake_recips(*a, **kw):
            return []

        async def fake_notify(case, comment, to_supplier, ids_out=None):
            return [sup_email]
        monkeypatch.setattr(ri, "_resolve_fault_supplier", fake_resolve)
        monkeypatch.setattr(ri, "_mod_case_recipients", fake_recips)
        monkeypatch.setattr(sp, "_send_comment_notification", fake_notify)
        run(ri._auto_dispatch_to_primary_supplier(doc, {"full_name": "T", "email": f"site_{RUN}@example.test"}))
        stored = run(_db().issues.find_one({"id": iid}, {"_id": 0}))
        assert stored.get("auto_dispatch_delivered_to") == [sup_email]
        assert stored.get("auto_dispatched_supplier_email") == sup_email


# ───────────── Fix C: transactional kinds ─────────────
class TestRecipientValidationFixC:
    @pytest.mark.parametrize("kind", ["mod_fault_pulse", "mod_fault_overseas"])
    def test_mod_kinds_pass(self, monkeypatch, kind):
        import utils.web_security as ws
        monkeypatch.setattr(ws, "_ENFORCE_RECIPIENT_VALIDATION", True)
        run(ws.validate_email_recipient(to_email="MODService@pulsefitness.com", kind=kind,
                                        organization_id=f"TEST_nobody_{RUN}", db=_db()))

    def test_other_kind_still_rejected(self, monkeypatch):
        import utils.web_security as ws
        from fastapi import HTTPException
        monkeypatch.setattr(ws, "_ENFORCE_RECIPIENT_VALIDATION", True)
        with pytest.raises(HTTPException):
            run(ws.validate_email_recipient(to_email="MODService@pulsefitness.com", kind="fault_manager_notify",
                                            organization_id=f"TEST_nobody_{RUN}", db=_db()))
