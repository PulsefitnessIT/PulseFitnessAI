# Regression: vehicle photo cookie auth, operator-staff routing opt-in,
# driver notes + extra photos, weekly reminder email (cron + manager).
import os
import io
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
mdb = _mc[os.environ.get("DB_NAME", "test_database")]

DRIVER = ("vc.driver@pulsefitness.test", "Driver123!")
OWNER = ("portal@pulsefitness.ltd", "PulseFleet123!")
DEMO_MGR = ("portal.manager@pulsedemo.test", "Manager123!")


def _cron_secret():
    for line in open("/app/backend/.env"):
        if line.startswith("WEBHOOK_CRON_SECRET="):
            return line.split("=", 1)[1].strip().strip('"')


def _login(email, pw):
    mdb.rate_buckets.delete_many({})  # test aid: avoid 429 on repeated logins
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    assert s.cookies.get("ga_session"), "no ga_session cookie"
    return s, r.json()


@pytest.fixture(scope="module")
def driver():
    return _login(*DRIVER)[0]


@pytest.fixture(scope="module")
def owner():
    return _login(*OWNER)[0]


@pytest.fixture(scope="module")
def demo_mgr():
    return _login(*DEMO_MGR)[0]


# ---------- BUG 1: photo served via cookie ----------
class TestPhotoCookieAuth:
    def test_defect_photo_cookie(self, demo_mgr):
        r = demo_mgr.get(f"{BASE_URL}/api/vehicle-defects")
        assert r.status_code == 200, r.text
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("defects") or data.get("items") or [])
        fids = [f for d in rows for f in (d.get("photo_ids") or [])]
        assert fids, f"no defect photos in demo org: {str(data)[:300]}"
        fid = fids[0]
        r = demo_mgr.get(f"{BASE_URL}/api/vehicle-checks/photo/{fid}?auth=cookie")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/")
        assert len(r.content) > 50
        # no auth -> 401
        r2 = requests.get(f"{BASE_URL}/api/vehicle-checks/photo/{fid}?auth=cookie")
        assert r2.status_code == 401
        r3 = requests.get(f"{BASE_URL}/api/vehicle-checks/photo/{fid}")
        assert r3.status_code == 401

    def test_cross_org_forbidden(self, owner, demo_mgr):
        doc = mdb.files.find_one({"category": "vehicle-photos", "organization_id": "iso-demo-org"})
        if not doc:
            pytest.skip("no iso-demo photo")
        r = owner.get(f"{BASE_URL}/api/vehicle-checks/photo/{doc['id']}?auth=cookie")
        assert r.status_code == 403


# ---------- BUG 2: routing / module opt-in ----------
class TestOperatorStaffModules:
    def test_driver_portal_only(self, driver):
        me = driver.get(f"{BASE_URL}/api/auth/me").json()
        ma = me.get("module_access") or (me.get("user") or {}).get("module_access") or {}
        print("driver module_access", ma)
        assert ma.get("operations") is not True
        assert not any(v for k, v in ma.items() if k != "crm_lite"), ma

    def test_grant_then_revoke_operations(self, owner):
        r = owner.post(f"{BASE_URL}/api/staffing/access/reports/VCTEST_staff/modules",
                       json={"modules": ["operations"]})
        assert r.status_code == 200, r.text
        assert "operations" in r.json()["granted_modules"], r.json()
        u = mdb.users.find_one({"email": DRIVER[0]})
        assert u["module_overrides"].get("operations") is True
        s, _ = _login(*DRIVER)
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        ma = me.get("module_access") or (me.get("user") or {}).get("module_access") or {}
        assert ma.get("operations") is True, ma
        # revoke
        r = owner.post(f"{BASE_URL}/api/staffing/access/reports/VCTEST_staff/modules", json={"modules": []})
        assert r.status_code == 200
        u = mdb.users.find_one({"email": DRIVER[0]})
        assert u["module_overrides"].get("operations") is False
        s, _ = _login(*DRIVER)
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        ma = me.get("module_access") or (me.get("user") or {}).get("module_access") or {}
        assert ma.get("operations") is not True


# ---------- FEATURE 3: driver notes + extra photos ----------
def _png():
    # 1x1 PNG
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class TestDriverNotes:
    def test_notes_save_submit_pdf(self, driver, owner):
        mdb.vehicle_checks.delete_many({"vehicle_id": "VCTEST_vehicle"})
        mdb.vehicle_defects.delete_many({"vehicle_id": "VCTEST_vehicle"})
        r = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["check"]["driver_notes"] == ""
        assert d["check"]["photos"]["extra"] == []
        ids = [it["id"] for sec in d["template"]["sections"] for it in sec["items"]]
        fids = []
        for _ in range(2):
            up = driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/photo",
                             files={"file": ("x.png", io.BytesIO(_png()), "image/png")})
            assert up.status_code == 200, up.text
            fids.append(up.json()["file_id"])
        body = {"vehicle_id": "VCTEST_vehicle", "details": {"driver_name": "VC Driver", "odometer": "1234"},
                "items": {i: "ok" for i in ids}, "driver_notes": "TEST_ note line1\nline2",
                "photos": {"vehicle": {}, "defect": [], "extra": fids}}
        r = driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/save", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"
        g = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"}).json()
        assert g["check"]["driver_notes"] == "TEST_ note line1\nline2"
        assert g["check"]["photos"]["extra"] == fids
        # driver can view own extra photo
        assert driver.get(f"{BASE_URL}/api/vehicle-checks/photo/{fids[0]}?auth=cookie").status_code == 200
        r = driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/submit", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"
        cid = r.json()["check_id"]
        # manager view
        c = owner.get(f"{BASE_URL}/api/vehicle-checks/{cid}")
        assert c.status_code == 200, c.text
        cj = c.json()
        cj = cj.get("check", cj)
        assert cj["driver_notes"].startswith("TEST_ note")
        assert cj["photos"]["extra"] == fids
        p = owner.get(f"{BASE_URL}/api/vehicle-checks/{cid}/pdf")
        assert p.status_code == 200
        assert p.headers["content-type"].startswith("application/pdf")
        assert p.content[:4] == b"%PDF"

    def test_save_after_submit_keeps_status(self, driver):
        # A draft save on an already-submitted check should not revert it.
        g = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"}).json()
        if g["check"].get("status") != "submitted":
            pytest.skip("not submitted")
        body = {"vehicle_id": "VCTEST_vehicle", "details": g["check"]["details"], "items": g["check"]["items"],
                "driver_notes": g["check"]["driver_notes"], "photos": g["check"]["photos"]}
        r = driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/save", json=body)
        print("save-after-submit status:", r.status_code, r.text[:200])
        assert r.status_code == 409, "draft save on a submitted check must be rejected"
        again = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"}).json()
        assert again["check"]["status"] == "submitted"

    def test_removing_last_photo_persists(self, driver):
        import io
        g = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"}).json()
        if g["check"].get("status") in ("submitted", "reviewed"):
            pytest.skip("check locked")
        png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                            "1f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082")
        up = driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/photo",
                         files={"file": ("x.png", io.BytesIO(png), "image/png")}).json()
        base = {"vehicle_id": "VCTEST_vehicle", "items": {}, "driver_notes": "x"}
        driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/save",
                    json={**base, "photos": {"vehicle": {}, "defect": [], "extra": [up["file_id"]]}})
        driver.post(f"{BASE_URL}/api/new-starter/portal/vehicle-check/save",
                    json={**base, "photos": {"vehicle": {}, "defect": [], "extra": []}})
        after = driver.get(f"{BASE_URL}/api/new-starter/portal/vehicle-check", params={"vehicle_id": "VCTEST_vehicle"}).json()
        assert after["check"]["photos"]["extra"] == []


# ---------- FEATURE 4: weekly reminder ----------
class TestReminders:
    def test_cron_auth(self):
        u = f"{BASE_URL}/api/vehicle-checks/cron/weekly-reminder"
        assert requests.post(u).status_code == 401
        assert requests.post(u, headers={"Authorization": "Bearer wrong"}).status_code == 401
        r = requests.post(u, headers={"Authorization": f"Bearer {_cron_secret()}"})
        assert r.status_code == 200 and r.json() == {"accepted": True}

    def test_manager_send_dedupe(self, owner):
        # make check outstanding
        mdb.vehicle_checks.delete_many({"vehicle_id": "VCTEST_vehicle"})
        mdb.vehicle_check_reminders.delete_many({"staff_id": "VCTEST_staff"})
        r = owner.post(f"{BASE_URL}/api/vehicle-checks/send-reminders")
        assert r.status_code == 200, r.text
        d = r.json()
        print("first", d)
        assert set(d) >= {"week_commencing", "sent", "skipped", "failed"}
        rem = mdb.vehicle_check_reminders.find_one({"staff_id": "VCTEST_staff"})
        assert rem, "no reminder doc written"
        assert "VC26 TST" in rem["vehicles"]
        notif = mdb.staff_notifications.find_one({"dedupe_key": f"veh_remind:VCTEST_staff:{d['week_commencing']}"}) \
            if "staff_notifications" in mdb.list_collection_names() else None
        print("notif", bool(notif), rem["status"])
        r2 = owner.post(f"{BASE_URL}/api/vehicle-checks/send-reminders").json()
        print("second", r2)
        if rem["status"] == "sent":
            assert r2["sent"] == 0 and r2["skipped"] >= 1

    def test_submitted_not_emailed(self, owner):
        mdb.vehicle_check_reminders.delete_many({"staff_id": "VCTEST_staff"})
        from datetime import date, timedelta
        wk = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        v = mdb.vehicles.find_one({"id": "VCTEST_vehicle"})
        mdb.vehicle_checks.insert_one({"id": "TEST_chk_rem", "organization_id": v["organization_id"],
                                       "vehicle_id": "VCTEST_vehicle", "week_commencing": wk, "status": "submitted"})
        try:
            r = owner.post(f"{BASE_URL}/api/vehicle-checks/send-reminders")
            assert r.status_code == 200
            assert mdb.vehicle_check_reminders.find_one({"staff_id": "VCTEST_staff"}) is None
        finally:
            mdb.vehicle_checks.delete_one({"id": "TEST_chk_rem"})

    def test_driver_cannot_send(self, driver):
        r = driver.post(f"{BASE_URL}/api/vehicle-checks/send-reminders")
        assert r.status_code in (401, 403)
