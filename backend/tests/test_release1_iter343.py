"""Iteration 343 — deeper retest of /api/account/team/* guards, pending-activation login, handover delete scope.
Synthetic TST orgs/users only; everything removed by exact org id via _purge."""
import sys
import time
import uuid

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, _db, _token  # noqa: E402
from tests.test_release_ce import BYP, PW, _mk_org, _purge  # noqa: E402

T = f"{BASE}/api/account/team"


def _user(db, oid, role, sites=None, **kw):
    from utils.auth import hash_password
    uid = str(uuid.uuid4())
    email = f"tst.i343.{role}.{uid[:6]}@example.com"
    db.users.insert_one({"id": uid, "email": email, "organization_id": oid, "role": role, "full_name": role.title(),
                         "allowed_site_ids": sites or [], "password": hash_password(PW), **kw})
    return uid, email, {"Authorization": f"Bearer {_token(email)}"}


def _login(email, pw=PW):
    return requests.post(f"{BASE}/api/auth/login", headers=BYP, json={"email": email, "password": pw}, timeout=30)


def _org2(db):
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    return oid, sa, sb


# Team invite: secure invitation, no temp password, no user row, manager scope rules
def test_team_invite_secure_and_scoped():
    db = _db()
    oid, sa, sb = _org2(db)
    _, _, ho = _user(db, oid, "owner")
    _, _, hm = _user(db, oid, "manager", [sa])
    try:
        em = f"tst.i343.inv.{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{T}/invite", headers=hm, json={"email": em, "full_name": "TST Inv", "role": "staff"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "temp_password" not in d and "password" not in d, d
        assert d["delivery"] == "invitation" and d.get("invite_url"), d
        assert d["allowed_site_ids"] == [sa], d  # restricted manager defaults to own sites
        assert db.users.count_documents({"email": em}) == 0
        inv = db.secure_invitations.find_one({"id": d["id"]})
        assert inv and inv["organization_id"] == oid and inv["role"] == "staff"
        print("invitation_delivery:", d.get("invitation_delivery"))
        # outside sites -> 403, unknown site -> 400, manager inviting manager -> 403
        assert requests.post(f"{T}/invite", headers=hm, json={"email": "x" + em, "full_name": "X", "role": "staff",
                                                              "allowed_site_ids": [sb]}).status_code == 403
        assert requests.post(f"{T}/invite", headers=ho, json={"email": "y" + em, "full_name": "Y", "role": "staff",
                                                              "allowed_site_ids": ["nope-site"]}).status_code == 400
        assert requests.post(f"{T}/invite", headers=hm, json={"email": "z" + em, "full_name": "Z", "role": "manager",
                                                              "allowed_site_ids": [sa]}).status_code == 403
        # owner inviting a manager -> mfa flagged on the invitation
        r = requests.post(f"{T}/invite", headers=ho, json={"email": "m" + em, "full_name": "M", "role": "manager",
                                                           "allowed_site_ids": [sa]})
        assert r.status_code == 200, r.text
        inv = db.secure_invitations.find_one({"id": r.json()["id"]}, {"_id": 0})
        print("manager invitation mfa fields:", {k: v for k, v in inv.items() if "mfa" in k})
    finally:
        _purge(db, oid)


# PATCH / site-access / DELETE guards
def test_team_patch_guards_and_validation():
    db = _db()
    oid, sa, sb = _org2(db)
    own, _, ho = _user(db, oid, "owner")
    mgr, _, hm = _user(db, oid, "manager", [sa])
    sta, _, _ = _user(db, oid, "staff", [sa])
    stb, _, _ = _user(db, oid, "staff", [sb])
    try:
        assert requests.patch(f"{T}/{mgr}", headers=hm, json={"role": "staff"}).status_code == 403  # self
        assert requests.patch(f"{T}/{mgr}/site-access", headers=hm, json={"allowed_site_ids": [sa, sb]}).status_code == 403
        assert requests.patch(f"{T}/{own}", headers=hm, json={"status": "disabled"}).status_code == 403
        assert requests.patch(f"{T}/{stb}", headers=hm, json={"status": "disabled"}).status_code == 403
        assert requests.delete(f"{T}/{stb}", headers=hm).status_code == 403
        assert db.users.count_documents({"id": stb}) == 1
        # manager may manage own-site staff, but not widen to [] or out-of-scope
        assert requests.patch(f"{T}/{sta}/site-access", headers=hm, json={"allowed_site_ids": []}).status_code == 403
        assert requests.patch(f"{T}/{sta}/site-access", headers=hm, json={"allowed_site_ids": [sb]}).status_code == 403
        assert requests.patch(f"{T}/{sta}/site-access", headers=ho, json={"allowed_site_ids": ["bad-site"]}).status_code == 400
        assert requests.patch(f"{T}/{sta}/site-access", headers=ho, json={"allowed_site_ids": "x"}).status_code == 400
        assert requests.patch(f"{T}/{sta}/site-access", headers=hm, json={"allowed_site_ids": [sa]}).status_code == 200
        assert requests.patch(f"{T}/{sta}", headers=hm, json={"role": "manager"}).status_code == 403
        # manager cannot touch user in another org (404)
        oid2 = _mk_org(db, onboarding_status="active", portal_access="activated")
        try:
            x, _, _ = _user(db, oid2, "staff")
            assert requests.patch(f"{T}/{x}", headers=ho, json={"status": "disabled"}).status_code == 404
            assert requests.delete(f"{T}/{x}", headers=ho).status_code == 404
        finally:
            _purge(db, oid2)
    finally:
        _purge(db, oid)


# Promotion to manager sets MFA enrolment and revokes sessions; disable/enable round-trip
def test_promotion_mfa_and_disable_reenable():
    db = _db()
    oid, sa, _ = _org2(db)
    _, _, ho = _user(db, oid, "owner")
    sid, semail, hs = _user(db, oid, "staff", [sa])
    try:
        assert requests.get(f"{BASE}/api/auth/me", headers=hs).status_code == 200
        time.sleep(1.1)
        r = requests.patch(f"{T}/{sid}", headers=ho, json={"role": "manager"})
        assert r.status_code == 200, r.text
        u = db.users.find_one({"id": sid})
        assert u["role"] == "manager" and u.get("mfa_enrolment_required") is True, u
        assert requests.get(f"{BASE}/api/auth/me", headers=hs).status_code == 401  # old session revoked
        d = _login(semail).json()
        assert d.get("requires_mfa_enrolment") is True and not d.get("token"), d
        # disable -> login blocked; re-enable -> login allowed again
        assert requests.patch(f"{T}/{sid}", headers=ho, json={"status": "disabled"}).status_code == 200
        assert _login(semail).status_code in (401, 403)
        assert requests.patch(f"{T}/{sid}", headers=ho, json={"status": "active"}).status_code == 200
        assert _login(semail).status_code == 200
        # engineer promotion
        eid, _, _ = _user(db, oid, "staff", [sa])
        r = requests.patch(f"{T}/{eid}", headers=ho, json={"role": "engineer"})
        print("engineer promotion:", r.status_code, "mfa_enrolment_required=", db.users.find_one({"id": eid}).get("mfa_enrolment_required"))
    finally:
        db.svc_engineers.delete_many({"organization_id": oid})
        _purge(db, oid)


# pending_activation org: login 403; existing session behaviour logged
def test_pending_activation_member_login_blocked():
    db = _db()
    oid = _mk_org(db)
    email = None
    try:
        _, email, h = _user(db, oid, "manager")
        r = _login(email)
        assert r.status_code == 403 and not (r.headers.get("content-type", "").startswith("application/json") and r.json().get("token")), r.text
        wrong = _login(email, "wrong-pw-123")
        assert wrong.status_code == 401, wrong.status_code  # password checked before org state (no enumeration)
        me = requests.get(f"{BASE}/api/auth/me", headers=h).status_code
        print("pending_activation existing-session /auth/me:", me)
        crm = requests.post(f"{BASE}/api/crm/auth/login", headers=BYP, json={"email": email, "password": PW}, timeout=30)
        print("pending_activation CRM login:", crm.status_code, crm.text[:150])
    finally:
        db.crm_users.delete_many({"email": email})
        _purge(db, oid)


# Handover delete: restricted manager may delete own-site note, not other-site note
def test_handover_delete_scope():
    db = _db()
    oid, sa, sb = _org2(db)
    _, _, hm = _user(db, oid, "manager", [sa])
    na, nb = f"tst-i343-ha-{oid}", f"tst-i343-hb-{oid}"
    db.gym_floor_handover.insert_many([
        {"id": na, "organization_id": oid, "site_id": sa, "notes": "A", "staff_name": "A", "topic_id": "general"},
        {"id": nb, "organization_id": oid, "site_id": sb, "notes": "B", "staff_name": "B", "topic_id": "general"}])
    try:
        assert requests.delete(f"{BASE}/api/gym-floor/handover/{nb}", headers=hm).status_code == 404
        assert db.gym_floor_handover.count_documents({"id": nb}) == 1
        assert requests.delete(f"{BASE}/api/gym-floor/handover/{na}", headers=hm).status_code == 200
        assert db.gym_floor_handover.count_documents({"id": na}) == 0
    finally:
        db.gym_floor_handover.delete_many({"id": {"$in": [na, nb]}})
        _purge(db, oid)


# Legacy invites: manager cannot withdraw manager invite; site-restricted manager cannot withdraw staff invite; owner can
def test_legacy_invite_cancel_rules():
    db = _db()
    oid, sa, _ = _org2(db)
    _, _, ho = _user(db, oid, "owner")
    _, _, hm = _user(db, oid, "manager", [sa])
    lm, ls = f"tst-i343-lm-{oid}", f"tst-i343-ls-{oid}"
    db.invites.insert_many([{"id": lm, "organization_id": oid, "status": "pending", "role": "manager", "email": f"m.{oid}@example.com"},
                            {"id": ls, "organization_id": oid, "status": "pending", "role": "staff", "email": f"s.{oid}@example.com"}])
    try:
        assert requests.delete(f"{BASE}/api/organization/invite/{lm}", headers=hm).status_code == 403
        assert requests.delete(f"{BASE}/api/organization/invite/{ls}", headers=hm).status_code == 403
        assert db.invites.count_documents({"id": {"$in": [lm, ls]}}) == 2
        assert requests.delete(f"{BASE}/api/organization/invite/{lm}", headers=ho).status_code == 200
        assert db.invites.count_documents({"id": lm}) == 0
    finally:
        db.invites.delete_many({"id": {"$in": [lm, ls]}})
        _purge(db, oid)


# Side door: CRM login (/api/crm/auth/login) for disabled users and pending_activation orgs
def test_crm_login_side_door():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    poid = _mk_org(db)
    emails = []
    try:
        _, de, _ = _user(db, oid, "staff", status="disabled")
        _, pe, _ = _user(db, poid, "manager")
        emails = [de, pe]
        res = {}
        for k, e in (("disabled_status", de), ("pending_activation", pe)):
            r = requests.post(f"{BASE}/api/crm/auth/login", headers=BYP, json={"email": e, "password": PW}, timeout=30)
            res[k] = (r.status_code, bool(r.ok and r.json().get("token")))
            if r.ok and r.json().get("token"):
                me = requests.get(f"{BASE}/api/crm/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}, timeout=30)
                cr = db.crm_users.find_one({"email": e}, {"_id": 0, "role": 1})
                print(k, "crm /me:", me.status_code, "crm role:", cr)
        print("CRM login side door:", res)
        assert not any(tok for _, tok in res.values()), res
    finally:
        db.crm_users.delete_many({"email": {"$in": emails}})
        _purge(db, oid)
        _purge(db, poid)
