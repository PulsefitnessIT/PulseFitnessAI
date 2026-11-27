"""Release 1 P0 gym-floor validation: named-user sessions use central auth; shared devices are site/org bound."""
import sys
import time
import uuid

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, _db, _token  # noqa: E402
from tests.test_release_ce import _mk_org, _purge  # noqa: E402

G = f"{BASE}/api/gym-floor"


def _setup(db):
    oid = _mk_org(db, onboarding_status="active", account_type="pulse_pro")
    other = _mk_org(db, onboarding_status="active", account_type="pulse_pro")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"},
                          {"id": f"{other}-x", "organization_id": other, "name": "X"}])
    db.equipment.insert_many([{"id": f"{oid}-ea", "organization_id": oid, "site_id": sa, "name": "Tread A"},
                              {"id": f"{oid}-eb", "organization_id": oid, "site_id": sb, "name": "Tread B"},
                              {"id": f"{other}-ex", "organization_id": other, "site_id": f"{other}-x", "name": "Other"}])
    own = str(uuid.uuid4())
    email = f"tst.gf.{own[:6]}@example.com"
    db.users.insert_one({"id": own, "email": email, "organization_id": oid, "role": "owner", "full_name": "O"})
    return oid, other, sa, sb, own, {"Authorization": f"Bearer {_token(email)}"}


def _device(ho, username, site):
    assert requests.post(f"{G}/setup", headers=ho, json={"username": username, "password": "secret12", "site_id": site}).status_code == 200
    return {"X-Gym-Floor-Token": requests.post(f"{G}/login", json={"username": username, "password": "secret12"}).json()["token"]}


def test_named_user_sessions_use_central_auth():
    db = _db()
    oid, other, sa, sb, own, ho = _setup(db)
    try:
        assert requests.get(f"{G}/handover", headers=ho).status_code == 200
        db.users.update_one({"id": own}, {"$set": {"tokens_revoked_before": int(time.time()) + 5}})
        assert requests.get(f"{G}/handover", headers=ho).status_code == 401  # revoked session
        db.users.update_one({"id": own}, {"$unset": {"tokens_revoked_before": ""}, "$set": {"is_active": False}})
        assert requests.get(f"{G}/handover", headers=ho).status_code in (401, 403)  # deactivated
    finally:
        _purge(db, oid)
        _purge(db, other)


def test_device_is_bound_to_site_org_and_products():
    db = _db()
    oid, other, sa, sb, own, ho = _setup(db)
    u = f"tst-gfa-{own[:6]}"
    try:
        ta = _device(ho, u, sa)
        assert [e["name"] for e in requests.get(f"{G}/equipment", headers=ta).json()["equipment"]] == ["Tread A"]
        # fault against another site's or another organisation's equipment is refused
        for eq in (f"{oid}-eb", f"{other}-ex"):
            r = requests.post(f"{G}/fault", headers=ta, json={"equipment_id": eq, "staff_id": "x", "issue_description": "Belt slipping badly"})
            assert r.status_code in (400, 404), r.text
        # the device token is useless outside gym floor (CRM, memberships, marketing, finance)
        for path in ("/api/crm/v2/quotes", "/api/memberships/members", "/api/marketing/campaigns", "/api/account/billing/modules",
                     "/api/equipment", "/api/auth/me"):
            assert requests.get(f"{BASE}{path}", headers=ta).status_code in (401, 403), path
        # sign-out, disable and expiry all end access
        assert requests.post(f"{G}/devices/{oid}:{sa}/sign-out", headers=ho).status_code == 200
        assert requests.get(f"{G}/equipment", headers=ta).status_code == 401
        ta = {"X-Gym-Floor-Token": requests.post(f"{G}/login", json={"username": u, "password": "secret12"}).json()["token"]}
        db.gym_floor_sessions.update_one({"token": ta["X-Gym-Floor-Token"]}, {"$set": {"expires_at": "2020-01-01T00:00:00+00:00"}})
        assert requests.get(f"{G}/equipment", headers=ta).status_code == 401
        ta = {"X-Gym-Floor-Token": requests.post(f"{G}/login", json={"username": u, "password": "secret12"}).json()["token"]}
        assert requests.post(f"{G}/devices/{oid}:{sa}/disable", headers=ho).status_code == 200
        assert requests.get(f"{G}/equipment", headers=ta).status_code == 401
    finally:
        _purge(db, oid)
        _purge(db, other)


def test_legacy_org_wide_credential_cannot_bypass_sites():
    from routes.gym_floor import _hash
    db = _db()
    oid, other, sa, sb, own, ho = _setup(db)
    u = f"tst-gfl-{own[:6]}"
    try:
        db.gym_floor_credentials.insert_one({"id": oid, "organization_id": oid, "username": u, "password_hash": _hash("secret12"),
                                             "enabled": True})
        db.gym_floor_sessions.insert_one({"token": f"gfloor-tst-{own}", "organization_id": oid,
                                          "created_at": "2099-01-01T00:00:00+00:00"})
        assert requests.post(f"{G}/login", json={"username": u, "password": "secret12"}).status_code == 403
        assert requests.get(f"{G}/equipment", headers={"X-Gym-Floor-Token": f"gfloor-tst-{own}"}).status_code == 401
        db.sites.delete_one({"id": sb})  # with a single site the old login is bound to it
        r = requests.post(f"{G}/login", json={"username": u, "password": "secret12"}).json()
        assert r["site_id"] == sa
    finally:
        _purge(db, oid)
        _purge(db, other)
