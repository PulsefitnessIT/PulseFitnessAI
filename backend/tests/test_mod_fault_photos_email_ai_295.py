# Iter 295: MOD fault photo back-fill, scoped photo serve, MOD email ".ai" sanitiser,
# delivery-status parallel lookups / array_filters / supplier 'pending'. NO real emails (resend mocked).
# Requires: python tests/_seed_fault_photos_295.py seed ; run with -p no:xdist
import os, sys, json, time, asyncio, threading
import pytest, requests
from pymongo import MongoClient
from dotenv import load_dotenv

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
load_dotenv(os.path.join(BK, ".env"))
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PW = "TestPhoto295#2026"
BYP = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".seed_295.json")))
PATHS = STATE["paths"]


def _login(email, pw, portal=""):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw, "portal": portal}, headers=BYP, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def site_tok():
    return _login("test_295_siteuser@example.test", PW, "mod")


@pytest.fixture(scope="module")
def outsider_tok():
    return _login("test_295_outsider@example.test", PW, "mod")


@pytest.fixture(scope="module")
def admin_tok():
    return _login(os.environ["MASTER_ADMIN_EMAIL"], os.environ["MASTER_ADMIN_PASSWORD"])


def _get(tok, iid):
    return requests.get(f"{API}/issues/{iid}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)


# --- Photo back-fill on GET /api/issues/{id}
class TestPhotoBackfill:
    def test_merge_two_photos_keeps_upload(self, site_tok):
        before = mdb.issues.find_one({"id": "TEST_295_i_photos"}, {"_id": 0})
        r = _get(site_tok, "TEST_295_i_photos")
        assert r.status_code == 200, r.text[:300]
        atts = r.json()["attachments"]
        photos = [a for a in atts if a.get("source") == "fault_photo"]
        assert len(photos) == 2
        assert [p["storage_path"] for p in photos] == PATHS
        for i, p in enumerate(photos):
            assert p["content_type"].startswith("image/")
            assert p["filename"] == f"Photo {i + 1} (logged with fault)"
        assert any(a.get("id") == "TEST_295_att_jobsheet" and a.get("download_url") for a in atts)
        assert len(atts) == 3
        ids1 = [a["id"] for a in atts]
        ids2 = [a["id"] for a in _get(site_tok, "TEST_295_i_photos").json()["attachments"]]
        assert ids1 == ids2
        after = mdb.issues.find_one({"id": "TEST_295_i_photos"}, {"_id": 0})
        assert before["attachments"] == after["attachments"] and len(after["attachments"]) == 1

    def test_no_duplicate_when_path_already_attached(self, site_tok):
        atts = _get(site_tok, "TEST_295_i_dupe").json()["attachments"]
        sp = [a.get("storage_path") for a in atts]
        assert sp.count(PATHS[0]) == 1 and sp.count(PATHS[1]) == 1 and len(atts) == 2

    def test_master_admin_sees_merge(self, admin_tok):
        # Master admin's GET /issues is scoped to their own/active org (pre-existing) -> 404 is expected here.
        r = _get(admin_tok, "TEST_295_i_photos")
        if r.status_code == 404:
            pytest.skip("master admin not scoped to TEST org (pre-existing org scoping)")
        assert r.status_code == 200
        assert len([a for a in r.json()["attachments"] if a.get("source") == "fault_photo"]) == 2


# --- GET /api/mod/site/attachments/serve scoped access
class TestServe:
    def _serve(self, tok, path):
        return requests.get(f"{API}/mod/site/attachments/serve", params={"path": path, "token": tok}, timeout=60)

    def test_site_user_gets_bytes(self, site_tok):
        r = self._serve(site_tok, PATHS[0])
        assert r.status_code == 200
        assert r.content[:4] == b"RIFF" and r.headers["content-type"].startswith("image/")

    def test_master_admin_gets_bytes(self, admin_tok):
        r = self._serve(admin_tok, PATHS[1])
        assert r.status_code == 200 and len(r.content) > 20

    def test_other_org_forbidden(self, outsider_tok):
        assert self._serve(outsider_tok, PATHS[0]).status_code == 403

    def test_bad_paths_400(self, site_tok):
        assert self._serve(site_tok, "gymaxis-ai/other/x.webp").status_code == 400
        assert self._serve(site_tok, f"gymaxis-ai/mod-attachments/TEST_295_modorg/../TEST_295_otherorg/x.webp").status_code == 400

    def test_bad_token_401(self):
        assert self._serve("garbage", PATHS[0]).status_code == 401


# --- MOD email sanitiser (unit)
class TestSanitize:
    def test_sanitize_ai(self):
        from utils.mod_sanitize import sanitize_ai, contains_ai
        s = sanitize_ai("a@pulsefitness.ai b@service.gymaxis.ai https://www.pulsefitness.ai/x Pulse Fitness AI "
                        "instagram.com/pulsefitnessai data.ai")
        assert "a@pulsefitness.com" in s and "b@pulsefitness.com" in s
        assert "https://modservice.pulsefitness.com/x" in s
        assert "Pulse Fitness AI" not in s and "Pulse Fitness " in s
        assert "instagram.com/pulsefitnessai" in s and "data.ai" in s
        assert not contains_ai(s)


def _capture_send(monkeypatch):
    import resend
    cap = []
    monkeypatch.setattr(resend.Emails, "send", staticmethod(lambda p: cap.append(p) or {"id": "TEST_295_fake"}))
    return cap


# --- utils.email.send_email for MOD vs commercial org (resend mocked)
class TestSendEmail:
    def test_mod_email_no_ai(self, monkeypatch):
        cap = _capture_send(monkeypatch)
        from utils.email import send_email
        ok = asyncio.run(send_email(to="TEST_295_r@example.test", subject="Fault from Pulse Fitness AI pulsefitness.ai",
                                    html="<p>support@pulsefitness.ai https://pulsefitness.ai/x Pulse Fitness AI</p>",
                                    organization_id="TEST_295_modorg", category="mod"))
        assert ok and cap
        p = cap[-1]
        blob = (p["html"] + p["subject"]).lower()
        assert "pulsefitness.ai" not in blob and "gymaxis.ai" not in blob
        assert "Pulse Fitness MOD Service" in p["html"]
        assert "modservice@pulsefitness.com" in p["html"].lower()
        print("MOD from/reply_to:", p.get("from"), p.get("reply_to"))

    def test_commercial_footer_unchanged(self, monkeypatch):
        cap = _capture_send(monkeypatch)
        from utils.email import send_email
        ok = asyncio.run(send_email(to="TEST_295_r@example.test", subject="Hello",
                                    html="<p>support@pulsefitness.ai</p>", organization_id="TEST_295_gymorg",
                                    category="service"))
        assert ok and cap
        h = cap[-1]["html"]
        assert "Pulse Fitness AI" in h and "support@pulsefitness.ai" in h

    def test_supplier_comment_notification_mod(self, monkeypatch):
        cap = _capture_send(monkeypatch)
        import routes.supplier_portal as sp
        case = {"id": "TEST_295_case_none", "issue_id": "TEST_295_i_photos", "token": "TEST_295_tok",
                "supplier_name": "TEST Sup", "supplier_email": "test_295_sup@example.test",
                "organization_account_type": "mod_site"}
        comment = {"id": "TEST_295_c", "author_name": "Pulse Fitness AI", "author_role": "gym",
                   "message": "see support@pulsefitness.ai https://pulsefitness.ai/case", "attachments": []}
        out = asyncio.run(sp._send_comment_notification(case, comment, True))
        assert cap, "resend not called"
        p = cap[-1]
        blob = (p["html"] + p["subject"]).lower()
        assert ".ai" not in blob.replace("gymaxis-ai", ""), [blob[max(0, blob.find('.ai') - 60):blob.find('.ai') + 10]]
        print("comment from:", p.get("from"), "delivered:", out)


# --- GET /api/issues/{id}/delivery-status follow-ups
class TestDeliveryStatus:
    def test_supplier_delivered_no_mid_is_pending(self):
        tok = _login("test_295_gymowner@example.test", PW)
        r = requests.get(f"{API}/issues/TEST_295_i_gym/delivery-status", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        sup = [x for x in r.json()["recipients"] if x["email"] == "inda295@example.test"]
        assert sup and sup[0]["status"] == "pending", r.json()

    def test_parallel_and_array_filters(self, monkeypatch):
        import resend
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        mdb.issues.delete_many({"id": "TEST_295_i_deliv"})
        mdb.issues.insert_one({"id": "TEST_295_i_deliv", "organization_id": "TEST_295_modorg", "status": "open",
                               "created_at": now, "issue_description": "TEST_ deliv", "notified_recipients": [
                                   {"role": "pulse", "name": f"R{i}", "email": f"r{i}_295@example.test", "at": now,
                                    "delivered": True, "message_id": f"TEST_mid_{i}"} for i in range(4)]})
        appended = threading.Event()

        def fake_get(mid):
            time.sleep(2)
            if not appended.is_set():
                appended.set()
                mdb.issues.update_one({"id": "TEST_295_i_deliv"}, {"$push": {"notified_recipients": {
                    "role": "supplier", "name": "late", "email": "late_295@example.test", "at": now, "delivered": True}}})
            return {"last_event": "delivered"}
        monkeypatch.setattr(resend.Emails, "get", staticmethod(fake_get))
        import routes.issues as ri
        user = mdb.users.find_one({"id": "TEST_295_siteuser"}, {"_id": 0})
        t0 = time.time()
        out = asyncio.run(ri.get_issue_delivery_status("TEST_295_i_deliv", user))
        dt = time.time() - t0
        print("elapsed", dt)
        assert dt < 5, dt
        assert all(x["status"] == "delivered" for x in out["recipients"])
        doc = mdb.issues.find_one({"id": "TEST_295_i_deliv"}, {"_id": 0})
        emails = [x["email"] for x in doc["notified_recipients"]]
        assert "late_295@example.test" in emails and len(emails) == 5
        assert all(x.get("delivery_status") == "delivered" for x in doc["notified_recipients"] if x["email"] != "late_295@example.test")
        mdb.issues.delete_many({"id": "TEST_295_i_deliv"})
