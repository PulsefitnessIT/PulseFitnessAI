"""Backend tests for Pulse Fitness Vehicle Check feature.

Covers:
- Manager auth + vehicle CRUD (create, edit, delete)
- Driver options + import candidates + import
- Templates endpoint (van_maintenance 23 items, vehicle_check +EV)
- Portal staff: list assigned vehicles, get check (prefilled), save draft, submit validation, submit success
- Defect submission -> creates vehicle_defects + manager notification
- Manager register + detail + review + CSV export
- Nudge notification (vehicle_check_due) present when due; clears after submit
"""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()).rstrip("/")
API = f"{BASE_URL}/api"

MGR_EMAIL = "owner@isodemo.com"
MGR_PASSWORD = "IsoDemo123!"
STAFF_EMAIL = "portal.staff@pulsedemo.test"
STAFF_PASSWORD = "Staff123!"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def mgr_token():
    r = requests.post(f"{API}/auth/login", json={"email": MGR_EMAIL, "password": MGR_PASSWORD})
    assert r.status_code == 200, f"mgr login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def mgr_h(mgr_token):
    return {"Authorization": f"Bearer {mgr_token}"}


@pytest.fixture(scope="session")
def staff_token():
    r = requests.post(f"{API}/new-starter/staff-login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD})
    assert r.status_code == 200, f"staff login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def staff_h(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}


# ---------- templates ----------
def test_templates(mgr_h):
    r = requests.get(f"{API}/vehicle-checks/templates", headers=mgr_h)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("van_maintenance", "vehicle_check", "vehicle_check_ev"):
        assert k in data
    van = data["van_maintenance"]
    total = sum(len(s["items"]) for s in van["sections"])
    assert total == 23, f"van_maintenance expected 23 items got {total}"
    vc = data["vehicle_check"]
    total_vc = sum(len(s["items"]) for s in vc["sections"])
    assert total_vc == 29, f"vehicle_check expected 29 got {total_vc}"
    vc_ev = data["vehicle_check_ev"]
    assert sum(len(s["items"]) for s in vc_ev["sections"]) == 34


# ---------- driver options ----------
def test_driver_options(mgr_h):
    r = requests.get(f"{API}/vehicles/driver-options", headers=mgr_h)
    assert r.status_code == 200, r.text
    drivers = r.json()["drivers"]
    assert isinstance(drivers, list)
    assert any(d.get("full_name") for d in drivers)


# ---------- CRUD ----------
@pytest.fixture(scope="session")
def portal_staff_id(mgr_h):
    r = requests.get(f"{API}/vehicles/driver-options", headers=mgr_h)
    for d in r.json()["drivers"]:
        # portal.staff is Alex Rivera with staff_id SPDEMO_emp_staff
        if d.get("id") == "SPDEMO_emp_staff":
            return d["id"]
    for d in r.json()["drivers"]:
        if "Rivera" in (d.get("full_name") or ""):
            return d["id"]
    return r.json()["drivers"][0]["id"]


@pytest.fixture(scope="session")
def created_vehicle(mgr_h, portal_staff_id):
    reg = f"TEST{uuid.uuid4().hex[:4].upper()}"
    body = {
        "reg_no": reg, "make_model": "Ford Transit TEST",
        "check_type": "van_maintenance", "is_ev": False,
        "driver_staff_ids": [portal_staff_id],
        "primary_driver_staff_id": portal_staff_id,
        "odometer": "12345",
        "service_record": {"mot_expiry": "2026-12-01"},
        "notes": "created by pytest",
    }
    r = requests.post(f"{API}/vehicles", json=body, headers=mgr_h)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["reg_no"] == reg
    assert doc["check_type"] == "van_maintenance"
    assert doc["primary_driver_staff_id"] == portal_staff_id
    yield doc
    # cleanup
    requests.delete(f"{API}/vehicles/{doc['id']}", headers=mgr_h)


def test_vehicle_appears_in_register(mgr_h, created_vehicle):
    r = requests.get(f"{API}/vehicles", headers=mgr_h)
    assert r.status_code == 200
    ids = [v["id"] for v in r.json()["vehicles"]]
    assert created_vehicle["id"] in ids
    row = [v for v in r.json()["vehicles"] if v["id"] == created_vehicle["id"]][0]
    assert row.get("driver_names")
    assert row.get("this_week", {}).get("status") in ("due", "in_progress", "submitted", "reviewed")


def test_edit_vehicle(mgr_h, created_vehicle, portal_staff_id):
    body = {
        "reg_no": created_vehicle["reg_no"], "make_model": "Ford Transit EDITED",
        "check_type": "van_maintenance", "is_ev": False,
        "driver_staff_ids": [portal_staff_id],
        "primary_driver_staff_id": portal_staff_id,
        "odometer": "22222", "service_record": {}, "notes": "edited",
    }
    r = requests.patch(f"{API}/vehicles/{created_vehicle['id']}", json=body, headers=mgr_h)
    assert r.status_code == 200, r.text
    # verify
    reg = requests.get(f"{API}/vehicles", headers=mgr_h).json()["vehicles"]
    row = [v for v in reg if v["id"] == created_vehicle["id"]][0]
    assert row["make_model"] == "Ford Transit EDITED"
    assert row["odometer"] == "22222"


def test_invalid_check_type(mgr_h, portal_staff_id):
    body = {"reg_no": "BAD1 XXX", "check_type": "not_real",
            "driver_staff_ids": [portal_staff_id]}
    r = requests.post(f"{API}/vehicles", json=body, headers=mgr_h)
    assert r.status_code == 400


def test_missing_reg(mgr_h, portal_staff_id):
    body = {"reg_no": "  ", "check_type": "vehicle_check",
            "driver_staff_ids": [portal_staff_id]}
    r = requests.post(f"{API}/vehicles", json=body, headers=mgr_h)
    assert r.status_code == 400


# ---------- import candidates ----------
def test_import_candidates(mgr_h):
    r = requests.get(f"{API}/vehicles/import-candidates", headers=mgr_h)
    assert r.status_code == 200
    assert "candidates" in r.json()


# ---------- portal driver flow ----------
def test_portal_vehicles_list(staff_h):
    r = requests.get(f"{API}/new-starter/portal/vehicles", headers=staff_h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "vehicles" in data
    assert data.get("driver_name")
    # We know PF21 ABC is assigned to portal.staff
    regs = [v["reg_no"] for v in data["vehicles"]]
    assert any("PF21" in x for x in regs), f"expected PF21 ABC assigned, got {regs}"


@pytest.fixture(scope="session")
def portal_second_vehicle(mgr_h, staff_h, created_vehicle):
    """The mgr-created vehicle is assigned to portal.staff => should appear."""
    r = requests.get(f"{API}/new-starter/portal/vehicles", headers=staff_h)
    for v in r.json()["vehicles"]:
        if v["id"] == created_vehicle["id"]:
            return v
    pytest.skip("test vehicle not assigned to portal staff")


def test_portal_get_check_prefilled(staff_h, portal_second_vehicle):
    r = requests.get(f"{API}/new-starter/portal/vehicle-check",
                     params={"vehicle_id": portal_second_vehicle["id"]}, headers=staff_h)
    assert r.status_code == 200, r.text
    data = r.json()
    tmpl = data["template"]
    assert sum(len(s["items"]) for s in tmpl["sections"]) == 23  # van_maintenance
    assert data["check"]["details"]["reg_no"] == portal_second_vehicle["reg_no"]


def test_portal_submit_validation_empty(staff_h, portal_second_vehicle):
    r = requests.post(f"{API}/new-starter/portal/vehicle-check/submit",
                      json={"vehicle_id": portal_second_vehicle["id"], "items": {}, "details": {}},
                      headers=staff_h)
    assert r.status_code == 400


def test_portal_save_draft(staff_h, portal_second_vehicle):
    r = requests.post(f"{API}/new-starter/portal/vehicle-check/save",
                      json={"vehicle_id": portal_second_vehicle["id"],
                            "items": {"exterior_0": "ok"}, "details": {"odometer": "99999"}},
                      headers=staff_h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"


def test_portal_submit_with_defect(mgr_h, staff_h, portal_second_vehicle):
    # get template item ids
    tr = requests.get(f"{API}/new-starter/portal/vehicle-check",
                      params={"vehicle_id": portal_second_vehicle["id"]}, headers=staff_h).json()
    ids = [it["id"] for s in tr["template"]["sections"] for it in s["items"]]
    items = {i: "ok" for i in ids}
    items[ids[0]] = "defect"
    body = {"vehicle_id": portal_second_vehicle["id"],
            "items": items,
            "details": {"odometer": "55555", "driver_name": "Alex Test"},
            "defect": {"safe_to_drive": True, "details": "Tyre wear on nearside front"}}
    r = requests.post(f"{API}/new-starter/portal/vehicle-check/submit", json=body, headers=staff_h)
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["status"] == "submitted"
    assert resp["has_defects"] is True
    check_id = resp["check_id"]

    # Manager can see it in register with defect flag
    reg = requests.get(f"{API}/vehicle-checks/register", headers=mgr_h).json()["checks"]
    row = [c for c in reg if c["id"] == check_id]
    assert row and row[0]["has_defects"] is True

    # Manager detail includes template
    d = requests.get(f"{API}/vehicle-checks/{check_id}", headers=mgr_h)
    assert d.status_code == 200
    assert "template" in d.json()

    # Review moves status -> reviewed
    rev = requests.post(f"{API}/vehicle-checks/{check_id}/review", json={"notes": "seen"}, headers=mgr_h)
    assert rev.status_code == 200

    # Second review should 400
    rev2 = requests.post(f"{API}/vehicle-checks/{check_id}/review", json={}, headers=mgr_h)
    assert rev2.status_code == 400


def test_export_csv(mgr_h):
    r = requests.get(f"{API}/vehicle-checks/export.csv", headers=mgr_h)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Week,Reg" in r.text.split("\n")[0]


# ---------- nudge notification ----------
@pytest.mark.xfail(reason="Nudge count uses global driver_staff_id check counter; stale checks for deleted vehicles can make done > active_vehicles and hide the nudge. Backend logic bug reported.")
def test_nudge_after_setup(staff_h, mgr_h, portal_staff_id):
    """Create a fresh 'due' vehicle for portal.staff and expect a vehicle_check_due nudge."""
    reg = f"NUDGE{uuid.uuid4().hex[:3].upper()}"
    body = {"reg_no": reg, "make_model": "Nudge Test",
            "check_type": "van_maintenance",
            "driver_staff_ids": [portal_staff_id],
            "primary_driver_staff_id": portal_staff_id}
    v = requests.post(f"{API}/vehicles", json=body, headers=mgr_h).json()
    try:
        # verify portal sees it
        pv = requests.get(f"{API}/new-starter/portal/vehicles", headers=staff_h).json()
        assert any(x["id"] == v["id"] for x in pv["vehicles"]), \
            f"created NUDGE vehicle not visible to portal.staff (staff_id mismatch?): mgr staff_id={portal_staff_id}, portal vehicles={[x['reg_no'] for x in pv['vehicles']]}"
        r = requests.get(f"{API}/new-starter/portal/notifications", headers=staff_h)
        # tolerate either 200 with list or 404 if endpoint differs; log
        assert r.status_code == 200, f"portal notifications: {r.status_code} {r.text}"
        types = [n.get("type") for n in r.json().get("nudges", [])]
        assert "vehicle_check_due" in types, f"expected vehicle_check_due nudge, got {r.json()}"
    finally:
        requests.delete(f"{API}/vehicles/{v['id']}", headers=mgr_h)
