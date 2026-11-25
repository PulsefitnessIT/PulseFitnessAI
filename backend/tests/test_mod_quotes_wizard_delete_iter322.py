"""Iter322: MOD quotation wizard feedback — rows without description, MOD-CALLOUT call-out code,
Notes appended in brackets, PDF item code, owner-only DELETE of groups (403/409/200 + cascade + audit), /me owner flag."""
import io
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
from utils.auth import hash_password  # noqa: E402

API = f"{_test_backend_url().rstrip('/')}/api"
MQ = f"{API}/mod-ops/quotes"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
PULSE_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
CUSTOMER = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane", "Helensburgh", "G84 0EH"]}
# Manual rows with NO description (wizard no longer has a description box)
ROWS = [{"row_id": "r1", "rate_card_id": "sor-2", "qty": 2, "coverage": "A", "label": "TEST_Note gym floor"},
        {"row_id": "r2", "rate_card_id": "sor-5", "qty": 1, "coverage": "B", "label": ""}]
RUN = uuid.uuid4().hex[:8]
OWNER_EMAIL = f"test_modowner_{RUN}@example.test"
OWNER_PW = "TestOwner123!"
CREATED: list = []
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module", autouse=True)
def owner_user():
    now = datetime.now(timezone.utc).isoformat()
    uid = f"TEST_owner_{RUN}"
    DB.users.insert_one({"id": uid, "email": OWNER_EMAIL, "full_name": "TEST MOD Owner", "organization_id": PULSE_ORG,
                         "role": "owner", "account_type": "pulse_pro", "module_overrides": {"mod_operations": True},
                         "mod_quote_role": "pricing_admin_manager", "password": hash_password(OWNER_PW),
                         "must_change_password": False, "created_at": now})
    yield uid
    DB.users.delete_one({"id": uid})
    for gid in CREATED:  # remove any groups the test made that were not deleted through the API
        DB.crm2_quotes.delete_many({"mod_group_id": gid})
        for c in ("mod_quote_events", "mod_quote_authorisations", "mod_quote_followups", "mod_quote_handovers"):
            DB[c].delete_many({"group_id": gid})
        DB.crm2_activities.delete_many({"mod_group_id": gid})
        DB.crm2_opportunities.delete_many({"mod_group_id": gid})
        DB.mod_quote_groups.delete_one({"id": gid})
        DB.mod_quote_deletions.delete_many({"group_id": gid})


@pytest.fixture(scope="module")
def mgr():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def owner(owner_user):
    return _login(OWNER_EMAIL, OWNER_PW)


def _create(s, rows=ROWS, options=("A", "B", "AB")):
    r = s.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": rows, "options": list(options), "callout_qty": 2,
                                     "idempotency_key": f"TEST_{uuid.uuid4()}"}, timeout=60)
    assert r.status_code == 200, r.text
    g = r.json()
    CREATED.append(g["id"])
    return g


# preview: rows without description, MOD-CALLOUT, notes in brackets, label-based issues
class TestPreview:
    def test_preview_no_description(self, mgr):
        r = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B", "AB"], "callout_qty": 2})
        assert r.status_code == 200, r.text
        o = r.json()["options"]
        assert set(o) == {"A", "B", "AB"}
        for t in o:
            assert o[t]["issues"] == [], o[t]["issues"]
        co = [ln for ln in o["B"]["lines"] if ln.get("kind") == "call_out"]
        assert len(co) == 1 and co[0]["item_code"] == "MOD-CALLOUT" and co[0]["qty"] == 2
        assert not co[0]["description"].startswith("-"), co[0]["description"]
        tread = [ln for ln in o["A"]["lines"] if ln.get("row_id") == "r1"][0]
        assert tread["description"].endswith("(TEST_Note gym floor)")
        assert not any(ln.get("kind") == "call_out" for ln in o["A"]["lines"] + o["AB"]["lines"])

    def test_issue_uses_item_label(self, mgr):
        rows = [{"row_id": "x1", "rate_card_id": "sor-2", "qty": 1, "coverage": None}]
        r = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": rows, "options": ["AB"]})
        iss = r.json()["options"]["AB"]["issues"]
        assert iss and not iss[0].startswith(":") and "choose Type A or Type B" in iss[0], iss
        rows = [{"row_id": "x2", "rate_card_id": None, "qty": 1}]
        iss = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": rows, "options": ["A"]}).json()["options"]["A"]["issues"]
        assert iss and iss[0].startswith("Unselected item"), iss

    def test_qty_change_changes_totals(self, mgr):
        a = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A"]}).json()["options"]["A"]["net"]
        rows2 = [dict(ROWS[0], qty=3), ROWS[1]]
        b = mgr.post(f"{MQ}/preview", json={"customer": CUSTOMER, "rows": rows2, "options": ["A"]}).json()["options"]["A"]["net"]
        assert b > a


# groups: save rows without description, PDF shows MOD-CALLOUT, /me owner flag
class TestGroupAndPdf:
    def test_create_and_pdf(self, mgr):
        g = _create(mgr)
        assert len(g["quotes"]) == 3
        assert all("description" in r for r in g["rows"])
        qb = [q for q in g["quotes"] if q["mod_quote_type"] == "B"][0]
        assert [ln for ln in qb["lines"] if ln.get("kind") == "call_out"][0]["item_code"] == "MOD-CALLOUT"
        r = mgr.get(f"{MQ}/quotes/{qb['id']}/pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        from pypdf import PdfReader
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        assert "MOD-CALLOUT" in text
        assert "1B " not in text.replace("\n", " ")
        assert "TEST_Note gym floor" in text.replace("\n", " ")  # notes appended in brackets
        GROUPS["mgr"] = g["id"]

    def test_me_owner_flags(self, mgr, rep, owner):
        assert mgr.get(f"{MQ}/me").json()["owner"] is False
        assert rep.get(f"{MQ}/me").json()["owner"] is False
        assert owner.get(f"{MQ}/me").json()["owner"] is True


GROUPS: dict = {}


# DELETE /groups/{gid}: 403 non-owner, 409 accepted/handed_over, 200 cascade + audit
class TestDelete:
    def test_non_owner_forbidden(self, mgr, rep):
        g = _create(mgr)
        GROUPS["del"] = g["id"]
        assert mgr.delete(f"{MQ}/groups/{g['id']}").status_code == 403
        assert rep.delete(f"{MQ}/groups/{g['id']}").status_code == 403
        assert mgr.get(f"{MQ}/groups/{g['id']}").status_code == 200

    @pytest.mark.parametrize("status", ["accepted", "handed_over"])
    def test_accepted_conflict(self, mgr, owner, status):
        g = _create(mgr, options=("A",))
        DB.mod_quote_groups.update_one({"id": g["id"]}, {"$set": {"status": status}})
        r = owner.delete(f"{MQ}/groups/{g['id']}")
        assert r.status_code == 409, r.text
        assert DB.mod_quote_groups.count_documents({"id": g["id"]}) == 1

    def test_owner_delete_cascade(self, mgr, owner):
        gid = GROUPS["del"]
        DB.mod_quote_followups.insert_one({"id": f"TEST_fu_{RUN}", "group_id": gid})
        DB.mod_quote_authorisations.insert_one({"id": f"TEST_au_{RUN}", "group_id": gid})
        nq = DB.crm2_quotes.count_documents({"mod_group_id": gid})
        assert nq >= 3
        r = owner.delete(f"{MQ}/groups/{gid}")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True and r.json()["deleted_quotes"] == nq
        assert mgr.get(f"{MQ}/groups/{gid}").status_code == 404
        assert DB.crm2_quotes.count_documents({"mod_group_id": gid}) == 0
        for c in ("mod_quote_followups", "mod_quote_authorisations", "mod_quote_events"):
            assert DB[c].count_documents({"group_id": gid}) == 0, c
        aud = DB.mod_quote_deletions.find_one({"group_id": gid})
        assert aud and aud["deleted_by"] == f"TEST_owner_{RUN}" and len(aud["quote_numbers"]) == nq
        assert owner.delete(f"{MQ}/groups/{gid}").status_code == 404
        assert gid not in [g["id"] for g in mgr.get(f"{MQ}/groups").json().get("groups", [])]

    def test_unauth(self):
        assert requests.delete(f"{MQ}/groups/nonexistent").status_code in (401, 403)
