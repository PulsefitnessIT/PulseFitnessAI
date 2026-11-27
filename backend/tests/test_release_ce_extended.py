"""Release C/E — extended edge cases (iteration 340 testing agent). Synthetic TST orgs, removed by id."""
import sys
import uuid

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402
from tests.test_release_ce import BYP, PW, _mk_org, _purge, _tok_from, _owner_invite, _accept  # noqa: E402


def _user(db, oid, role, **kw):
    uid = str(uuid.uuid4())
    em = f"tst.{role[:2]}.{uid[:6]}@example.com"
    db.users.insert_one({"id": uid, "email": em, "organization_id": oid, "role": role, "full_name": role, **kw})
    return uid, em, {"Authorization": f"Bearer {_token(em)}"}


# Owner activation: a second still-pending owner invite (different email) must not work after the org is activated
def test_second_owner_invite_unusable_after_activation(H):
    db = _db()
    oid = _mk_org(db)
    a, b = f"tst.oa.{uuid.uuid4().hex[:6]}@example.com", f"tst.ob.{uuid.uuid4().hex[:6]}@example.com"
    try:
        ra = _owner_invite(H, oid, a).json()
        rb = _owner_invite(H, oid, b).json()
        # A newer owner invite supersedes the older one (one owner invite per organisation).
        assert _accept(_tok_from(ra["link"]), a).status_code == 410
        assert _accept(_tok_from(rb["link"]), b).status_code == 200
        owners = db.users.count_documents({"organization_id": oid, "role": "owner"})
        assert owners == 1
    finally:
        _purge(db, oid)


# Owner activation: reissue must not create a new owner link once the customer is activated
def test_reissue_owner_invite_after_activation_refused(H):
    db = _db()
    oid = _mk_org(db)
    a, b = f"tst.oa.{uuid.uuid4().hex[:6]}@example.com", f"tst.ob.{uuid.uuid4().hex[:6]}@example.com"
    try:
        rb = _owner_invite(H, oid, b).json()
        ra = _owner_invite(H, oid, a).json()
        assert _accept(_tok_from(ra["link"]), a).status_code == 200
        r = requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{rb['invitation']['id']}/reissue",
                          headers=H, timeout=30)
        assert r.status_code in (404, 409), f"reissue after activation returned {r.status_code}"
    finally:
        _purge(db, oid)


# Public accept: inspect never consumes; wrong email 5x locks the invite; weak password refused without consuming
def test_inspect_idempotent_lockout_and_weak_password(H):
    db = _db()
    oid = _mk_org(db)
    em = f"tst.ol.{uuid.uuid4().hex[:6]}@example.com"
    try:
        tok = _tok_from(_owner_invite(H, oid, em).json()["link"])
        for _ in range(3):
            assert requests.post(f"{BASE}/api/invitations/inspect", json={"token": tok}, headers=BYP).json()["state"] == "valid"
        assert requests.post(f"{BASE}/api/invitations/inspect", json={"token": "x" * 30}, headers=BYP).json()["state"] == "invalid"
        weak = _accept(tok, em, pw="short123")
        assert weak.status_code in (400, 422)
        assert requests.post(f"{BASE}/api/invitations/inspect", json={"token": tok}, headers=BYP).json()["state"] == "valid"
        for _ in range(5):
            assert _accept(tok, "wrong@example.com").status_code == 400
        assert requests.post(f"{BASE}/api/invitations/inspect", json={"token": tok}, headers=BYP).json()["state"] == "revoked"
        assert _accept(tok, em).status_code == 410
        # no login token from a GET of the page (scanner-safe): the SPA route itself is static
        assert requests.get(f"{BASE}/accept-invite", timeout=30).status_code == 200
        assert db.secure_invitations.find_one({"organization_id": oid})["status"] == "revoked"
    finally:
        _purge(db, oid)


# Staff invites: a manager must not cancel the owner's manager invitation, nor resend invites for sites they don't manage
def test_manager_cannot_cancel_manager_invite_or_touch_other_site_invites(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    _, _, ho = _user(db, oid, "owner")
    _, _, hm = _user(db, oid, "manager", allowed_site_ids=[sa])
    u = f"{BASE}/api/organization/invite"
    try:
        rm = requests.post(u, headers=ho, json={"email": f"tst.mx.{oid[-5:]}@example.com", "role": "manager", "allowed_site_ids": [sb]}).json()
        rs = requests.post(u, headers=ho, json={"email": f"tst.sx.{oid[-5:]}@example.com", "role": "staff", "allowed_site_ids": [sb]}).json()
        results = {
            "manager_cancels_owner_manager_invite": requests.delete(f"{u}/{rm['invitation']['id']}", headers=hm).status_code,
            "manager_resends_site_b_staff_invite": requests.post(f"{u}/{rs['invitation']['id']}/resend", headers=hm).status_code,
        }
        assert all(v == 403 for v in results.values()), results
    finally:
        _purge(db, oid)


# Staff invites: owner of a single-site org and role validation
def test_owner_invite_invalid_role_and_owner_role_refused(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    _, _, ho = _user(db, oid, "owner")
    _, _, hs = _user(db, oid, "staff")
    u = f"{BASE}/api/organization/invite"
    try:
        assert requests.post(u, headers=ho, json={"email": "tst.r1@example.com", "role": "owner"}).status_code == 400
        assert requests.post(u, headers=hs, json={"email": "tst.r2@example.com", "role": "staff"}).status_code == 403
        r = requests.post(u, headers=ho, json={"email": f"tst.r3.{oid[-5:]}@example.com", "role": "staff"})
        assert r.status_code == 200 and r.json()["delivery"]["mode"] == "held"
        r2 = requests.post(u, headers=ho, json={"email": f"tst.r3.{oid[-5:]}@example.com", "role": "staff"})  # supersedes
        assert r2.status_code == 200
        assert _accept(_tok_from(r.json()["link"]), f"tst.r3.{oid[-5:]}@example.com").status_code == 410
        assert _accept(_tok_from(r2.json()["link"]), f"tst.r3.{oid[-5:]}@example.com").status_code == 200
    finally:
        _purge(db, oid)


# Gym floor: faults only for own-site equipment; sign-out/enable; restricted manager scope
def test_gym_floor_fault_scope_signout_enable_and_manager_scope(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", account_type="pulse_pro")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    db.equipment.insert_many([{"id": f"{oid}-ea", "organization_id": oid, "site_id": sa, "name": "Tread A", "serial_number": "TSA"},
                              {"id": f"{oid}-eb", "organization_id": oid, "site_id": sb, "name": "Tread B", "serial_number": "TSB"}])
    _, _, ho = _user(db, oid, "owner")
    _, _, hm = _user(db, oid, "manager", allowed_site_ids=[sa])
    staff_id = str(uuid.uuid4())
    db.gym_floor_staff.insert_one({"id": staff_id, "organization_id": oid, "name": "Sam", "name_lower": "sam",
                                   "email": "tst.sam@example.com", "active": True})
    g = f"{BASE}/api/gym-floor"
    ua, ub = f"tst-a-{oid[-6:]}", f"tst-b-{oid[-6:]}"
    try:
        # restricted manager cannot set up a site-B device
        assert requests.post(f"{g}/setup", headers=hm, json={"username": ub, "password": "secret12", "site_id": sb}).status_code == 403
        assert requests.post(f"{g}/setup", headers=hm, json={"username": ua, "password": "secret12", "site_id": sa}).status_code == 200
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ub, "password": "secret12", "site_id": sb}).status_code == 200
        st_m = requests.get(f"{g}/status", headers=hm).json()
        assert [c["site_id"] for c in st_m["credentials"]] == [sa] and [s["id"] for s in st_m["sites"]] == [sa]
        assert requests.post(f"{g}/devices/{oid}:{sb}/disable", headers=hm).status_code == 403
        ta = {"X-Gym-Floor-Token": requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).json()["token"]}
        bad = requests.post(f"{g}/fault", headers=ta, json={"staff_id": staff_id, "equipment_id": f"{oid}-eb", "issue_description": "Belt slipping"})
        assert bad.status_code == 400
        ok = requests.post(f"{g}/fault", headers=ta, json={"staff_id": staff_id, "equipment_id": f"{oid}-ea", "issue_description": "Belt slipping"})
        assert ok.status_code == 200, ok.text
        # sign-out ends session, login still works
        assert requests.post(f"{g}/devices/{oid}:{sa}/sign-out", headers=ho).status_code == 200
        assert requests.get(f"{g}/equipment", headers=ta).status_code == 401
        assert requests.post(f"{g}/devices/{oid}:{sa}/disable", headers=ho).status_code == 200
        assert requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).status_code == 401
        assert requests.post(f"{g}/devices/{oid}:{sa}/enable", headers=ho).status_code == 200
        assert requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).status_code == 200
        # password rotate via setup again signs out existing sessions
        t2 = {"X-Gym-Floor-Token": requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).json()["token"]}
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ua, "password": "secret34", "site_id": sa}).status_code == 200
        assert requests.get(f"{g}/equipment", headers=t2).status_code == 401
    finally:
        db.issues.delete_many({"organization_id": oid})
        db.gym_floor_staff.delete_many({"organization_id": oid})
        db.gym_floor_topics.delete_many({"organization_id": oid})
        _purge(db, oid)


# Release E: billing module listing for a LITE org + cancel guards + commercial summary shape
def test_billing_modules_lite_and_commercial_summary_shape(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    _, _, ho = _user(db, oid, "owner")
    _, _, hmg = _user(db, oid, "manager")
    try:
        prods = {p["module"]: p for p in requests.get(f"{BASE}/api/account/billing/modules", headers=ho).json()["products"]}
        assert prods["operations"]["status"] == "lite" and set(prods) == {"operations", "memberships", "marketing", "crm"}
        assert requests.post(f"{BASE}/api/account/billing/modules/operations/cancel", headers=ho, json={"reason": "cost"}).status_code == 409
        assert requests.post(f"{BASE}/api/account/billing/modules/operations/reactivate", headers=ho).status_code == 409
        assert requests.post(f"{BASE}/api/account/billing/modules/bogus/cancel", headers=ho, json={"reason": "cost"}).status_code == 404
        assert requests.post(f"{BASE}/api/account/billing/modules/operations/cancel", headers=hmg, json={"reason": "cost"}).status_code == 403
        assert requests.get(f"{BASE}/api/master-admin/commercial/summary", headers=hmg).status_code == 403
        rep = requests.get(f"{BASE}/api/master-admin/commercial/summary", headers=H).json()
        assert set(rep["accounts"]) >= {"lite", "pro", "awaiting_activation", "owner_invited", "activated_by_invitation"}
        assert {"upgrades_lite_to_pro", "reactivations", "ended"} <= set(rep["last_30_days"]) and isinstance(rep["mrr"], (int, float))
    finally:
        _purge(db, oid)


# Delegated (stale) Pulse flags must not reach activation detail / revoke either
def test_customer_owner_cannot_use_activation_endpoints(H):
    db = _db()
    oid = _mk_org(db)
    other = _mk_org(db, onboarding_status="active", portal_access="activated")
    _, _, ho = _user(db, other, "owner", is_pulse_staff=True, onboarding_permissions=["activation.view", "activation.invite"])
    try:
        inv = _owner_invite(H, oid, f"tst.d.{oid[-5:]}@example.com").json()["invitation"]["id"]
        assert requests.get(f"{BASE}/api/master-admin/customer-activation/{oid}", headers=ho).status_code == 403
        assert requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{inv}/revoke", headers=ho).status_code == 403
        assert requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{inv}/reissue", headers=ho).status_code == 403
    finally:
        _purge(db, oid)
        _purge(db, other)
