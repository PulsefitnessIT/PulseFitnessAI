# Iter 294: gym comment edit/delete (15-min, own only), author_user_id on POST, delivery-status endpoint + access rules.
# Requires: python tests/_seed_comment_edit_delivery_294.py seed (and `send` for the delivered tick check).
import os, sys, time
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
load_dotenv(os.path.join(BK, ".env"))
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PW = "TestCmt294#2026"
TOK = "TEST_294_case_mod_tok"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(uid):
    r = requests.post(f"{API}/auth/login", json={"email": f"{uid.lower()}@example.test", "password": PW, "portal": "mod" if "gym" not in uid and "outsider" not in uid else ""},
                      headers={"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")})
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed for {uid}: {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def owner():
    return _login("TEST_294_owner")


def _url(cid, tok=TOK):
    return f"{API}/supplier/case/{tok}/comments/gym/{cid}"


class TestEditDelete:
    def test_edit_own_fresh(self, owner):
        r = requests.patch(_url("TEST_294_c_own_edit"), json={"message": "TEST_ edited text"}, headers=owner)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["message"] == "TEST_ edited text" and d.get("edited_at")
        assert "edit_history" not in d
        row = mdb.supplier_case_comments.find_one({"id": "TEST_294_c_own_edit"})
        assert row["message"] == "TEST_ edited text"
        assert row["edit_history"][0]["message"] == "TEST_ msg own_edit"

    @pytest.mark.parametrize("cid,code", [
        ("TEST_294_c_other", 403), ("TEST_294_c_own_old", 403), ("TEST_294_c_supplier", 403),
        ("TEST_294_c_legacy", 403), ("TEST_294_c_deleted", 404), ("nope-id", 404)])
    def test_edit_denied(self, owner, cid, code):
        r = requests.patch(_url(cid), json={"message": "TEST_ x"}, headers=owner)
        assert r.status_code == code, r.text
        r2 = requests.delete(_url(cid), headers=owner)
        assert r2.status_code == code, r2.text

    def test_wrong_token_and_case(self, owner):
        assert requests.patch(_url("TEST_294_c_own_edit", "bad-token"), json={"message": "x"}, headers=owner).status_code == 404
        # comment belongs to a different case than this token
        assert requests.patch(_url("TEST_294_c_own_edit", "TEST_294_case_gym_tok"), json={"message": "x"}, headers=owner).status_code == 404

    def test_empty_edit_400(self, owner):
        r = requests.patch(_url("TEST_294_c_own_edit"), json={"message": "   "}, headers=owner)
        assert r.status_code == 400

    def test_unauthenticated(self):
        assert requests.patch(_url("TEST_294_c_own_edit"), json={"message": "x"}).status_code in (401, 403)

    def test_delete_soft_and_hidden(self, owner):
        r = requests.delete(_url("TEST_294_c_own_del"), headers=owner)
        assert r.status_code == 200 and r.json()["success"] is True
        row = mdb.supplier_case_comments.find_one({"id": "TEST_294_c_own_del"})
        assert row and row.get("deleted_at")
        iss = requests.get(f"{API}/issues/TEST_294_i_mod", headers=owner).json()
        ids = [c["id"] for c in iss["supplier_case"]["comments"]]
        assert "TEST_294_c_own_del" not in ids and "TEST_294_c_deleted" not in ids
        assert all("edit_history" not in c for c in iss["supplier_case"]["comments"])
        pub = requests.get(f"{API}/supplier/case/{TOK}").json()
        pids = [c["id"] for c in pub.get("comments", [])]
        assert "TEST_294_c_own_del" not in pids and "TEST_294_c_own_edit" in pids
        assert all("edit_history" not in c for c in pub["comments"])
        lst = requests.get(f"{API}/supplier/case/{TOK}/comments").json()
        items = lst if isinstance(lst, list) else lst.get("comments", [])
        assert "TEST_294_c_own_del" not in [c["id"] for c in items]
        assert all("edit_history" not in c for c in items)
        # deleting again -> 404
        assert requests.delete(_url("TEST_294_c_own_del"), headers=owner).status_code == 404


class TestPostStoresAuthor:
    def test_add_gym_comment_in_process(self, monkeypatch):
        from tests.conftest import drive_async
        import routes.supplier_portal as sp
        sent = []

        async def fake(*a, **k):
            sent.append(1)
        monkeypatch.setattr(sp, "_send_comment_notification", fake)
        res = drive_async(sp.add_gym_comment(TOK, message="TEST_ inproc", author_name="", file=None,
                                             user={"id": "TEST_294_owner", "full_name": "T"}))
        assert res["author_user_id"] == "TEST_294_owner" and res["author_role"] == "gym"
        assert sent == [1]
        assert mdb.supplier_case_comments.find_one({"id": res["id"]})["author_user_id"] == "TEST_294_owner"


class TestDeliveryStatus:
    def test_access_rules(self):
        out = _login("TEST_294_outsider")
        assert requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status", headers=out).status_code == 404
        locked = _login("TEST_294_locked")
        # site-locked user outside the site: the MOD scope filter hides it (404) — must match GET /issues/{id}
        a = requests.get(f"{API}/issues/TEST_294_i_mod", headers=locked).status_code
        b = requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status", headers=locked).status_code
        assert a in (403, 404) and a == b
        assert requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status").status_code in (401, 403)

    def test_non_mod_supplier_only(self):
        h = _login("TEST_294_gymowner")
        r = requests.get(f"{API}/issues/TEST_294_i_gym/delivery-status", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["recipients"]) == 1 and d["recipients"][0]["role"] == "supplier"
        assert d["recipients"][0]["email"] == "inda294@example.test"
        assert d["supplier_case_token"] == "TEST_294_case_gym_tok"

    def test_mod_statuses_and_real_delivered(self, owner):
        d = None
        for _ in range(4):
            r = requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status", headers=owner)
            assert r.status_code == 200, r.text
            d = r.json()
            by = {x["role"]: x for x in d["recipients"]}
            if by["pulse"]["status"] == "delivered":
                break
            time.sleep(62)
        by = {x["role"]: x for x in d["recipients"]}
        print({k: (v["status"], v.get("event")) for k, v in by.items()})
        assert len(d["recipients"]) == 3  # supplier from case not duplicated
        assert by["overseas"]["status"] == "failed"
        assert by["supplier"]["status"] in ("pending", "unknown")
        assert by["pulse"]["status"] == "delivered"
        row = mdb.issues.find_one({"id": "TEST_294_i_mod"})
        rec = {x["role"]: x for x in row["notified_recipients"]}
        assert rec["pulse"]["delivery_status"] == "delivered" and rec["pulse"].get("delivery_checked_at")
        assert rec["overseas"]["delivery_status"] == "failed"

    def test_not_requeried_within_60s(self, owner):
        requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status", headers=owner)
        before = mdb.issues.find_one({"id": "TEST_294_i_mod"})
        b = {x["role"]: x.get("delivery_checked_at") for x in before["notified_recipients"]}
        requests.get(f"{API}/issues/TEST_294_i_mod/delivery-status", headers=owner)
        after = mdb.issues.find_one({"id": "TEST_294_i_mod"})
        a = {x["role"]: x.get("delivery_checked_at") for x in after["notified_recipients"]}
        assert a["supplier"] == b["supplier"] and b["supplier"]


def test_health():
    r = requests.get(f"{API}/health")
    assert r.status_code == 200
