"""Release 1 P0: company-code registration closed; staff role/site permission enforcement; ownership transfer;
legacy invitation migration. Direct API requests; synthetic TST data removed by id."""
import sys
import uuid

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402
from tests.test_release_ce import BYP, _mk_org, _purge  # noqa: E402

PW = "Tst!Release1#2026xyz"


def _users(db, oid, *specs):
    out = []
    for role, sites in specs:
        uid = str(uuid.uuid4())
        db.users.insert_one({"id": uid, "email": f"tst.{role}.{uid[:6]}@example.com", "organization_id": oid,
                             "role": role, "full_name": role.title(), "allowed_site_ids": sites})
        out.append((uid, {"Authorization": f"Bearer {_token(f'tst.{role}.{uid[:6]}@example.com')}"}))
    return out


def _register(code):
    email = f"tst.reg.{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE}/api/auth/register", headers=BYP, timeout=30,
                      json={"email": email, "password": PW, "full_name": "Reg Tester", "company_code": code})
    return r, email


def test_company_code_never_joins_active_or_inactive_org():
    db = _db()
    act = _mk_org(db, onboarding_status="active", portal_access="activated", company_code="TSTACT" + uuid.uuid4().hex[:4].upper())
    ina = _mk_org(db, company_code="TSTINA" + uuid.uuid4().hex[:4].upper())
    try:
        for oid in (act, ina):
            code = db.organizations.find_one({"id": oid})["company_code"]
            db.invites.insert_one({"id": "tst-leg-" + oid, "organization_id": oid, "status": "pending", "role": "manager",
                                   "email": "legacy." + oid + "@example.com"})
            r, email = _register(code)
            assert r.status_code == 403, r.text
            assert db.users.count_documents({"email": email}) == 0
            r = requests.post(f"{BASE}/api/auth/register", headers=BYP, timeout=30, json={
                "email": "legacy." + oid + "@example.com", "password": PW, "full_name": "Leg", "company_code": code})
            assert r.status_code == 403  # a legacy invite cannot be redeemed with the company code
            assert db.users.count_documents({"organization_id": oid}) == 0
        assert _register("NOSUCHCODE")[0].status_code == 403
    finally:
        db.invites.delete_many({"id": {"$in": ["tst-leg-" + act, "tst-leg-" + ina]}})
        _purge(db, act)
        _purge(db, ina)


def test_new_organisation_registration_still_works():
    db = _db()
    email = f"tst.neworg.{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE}/api/auth/register", headers=BYP, timeout=30,
                      json={"email": email, "password": PW, "full_name": "New Owner", "company_name": "TST New Gym"})
    try:
        assert r.status_code == 200, r.text
        u = db.users.find_one({"email": email})
        assert u["role"] == "owner"
    finally:
        u = db.users.find_one({"email": email})
        if u:
            _purge(db, u["organization_id"])


def test_staff_permission_and_role_enforcement():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    other = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb, sx = f"{oid}-a", f"{oid}-b", f"{other}-x"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"},
                          {"id": sx, "organization_id": other, "name": "X"}])
    (own, ho), (mgr, hm), (mgr2, _), (sta, hs), (stb, _) = _users(
        db, oid, ("owner", []), ("manager", [sa]), ("manager", [sb]), ("staff", [sa]), ("staff", [sb]))
    P = f"{BASE}/api/organization/staff"
    try:
        # staff cannot change anyone, including themselves
        assert requests.patch(f"{P}/{sta}/permissions", headers=hs, json={"timetable_view_only": False}).status_code == 403
        # manager cannot change own permissions, other managers, or staff at other sites
        assert requests.patch(f"{P}/{mgr}/permissions", headers=hm, json={"allowed_site_ids": []}).status_code == 403
        assert requests.patch(f"{P}/{mgr2}/permissions", headers=hm, json={"allowed_site_ids": [sa]}).status_code == 403
        assert requests.patch(f"{P}/{stb}/permissions", headers=hm, json={"allowed_site_ids": [sa]}).status_code == 403
        # manager cannot widen staff to unrestricted or to an unmanaged site
        assert requests.patch(f"{P}/{sta}/permissions", headers=hm, json={"allowed_site_ids": []}).status_code == 403
        assert requests.patch(f"{P}/{sta}/permissions", headers=hm, json={"allowed_site_ids": [sa, sb]}).status_code == 403
        # site IDs must belong to the organisation (owner too)
        assert requests.patch(f"{P}/{sta}/permissions", headers=ho, json={"allowed_site_ids": [sx]}).status_code == 400
        assert requests.patch(f"{P}/{sta}/permissions", headers=hm, json={"timetable_view_only": True}).status_code == 200
        assert db.users.find_one({"id": sta})["allowed_site_ids"] == [sa]
        # owner may change scope; the person's sessions are revoked
        assert requests.patch(f"{P}/{sta}/permissions", headers=ho, json={"allowed_site_ids": [sa, sb]}).status_code == 200
        assert db.users.find_one({"id": sta}).get("tokens_revoked_before")
        assert requests.get(f"{BASE}/api/auth/me", headers=hs).status_code == 401
        # roles: managers cannot change roles; owner cannot self-change or promote to owner directly
        R = lambda sid, role, h: requests.patch(f"{P}/{sid}/role", params={"role": role}, headers=h).status_code  # noqa: E731
        assert R(stb, "manager", hm) == 403
        assert R(mgr, "manager", hm) == 403
        assert R(own, "manager", ho) == 400
        assert R(stb, "owner", ho) == 400
        assert R(stb, "manager", ho) == 200
        u = db.users.find_one({"id": stb})
        assert u["role"] == "manager" and u["mfa_enrolment_required"] is True and u.get("tokens_revoked_before")
    finally:
        _purge(db, oid)
        _purge(db, other)


def test_ownership_transfer_requires_password_and_mfa():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    from utils.auth import hash_password
    (own, ho), (mgr, _) = _users(db, oid, ("owner", []), ("manager", []))
    db.users.update_one({"id": own}, {"$set": {"password": hash_password(PW)}})
    T = f"{BASE}/api/organization/ownership/transfer"
    try:
        assert requests.post(T, headers=ho, json={"target_user_id": mgr, "password": "wrong-password"}).status_code == 401
        assert requests.post(T, headers=ho, json={"target_user_id": mgr, "password": PW}).status_code == 409  # no MFA
        db.user_mfa.insert_one({"user_id": mgr, "enabled": True})
        assert requests.post(T, headers=ho, json={"target_user_id": mgr, "password": PW}).status_code == 200
        assert db.users.find_one({"id": mgr})["role"] == "owner" and db.users.find_one({"id": own})["role"] == "manager"
        assert db.organizations.find_one({"id": oid})["owner_id"] == mgr
    finally:
        _purge(db, oid)


def test_legacy_invites_migrate_to_secure_invitations(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    ina = _mk_org(db)
    ids = [f"tst-leg1-{oid}", f"tst-leg2-{oid}", f"tst-leg3-{ina}"]
    db.invites.insert_many([
        {"id": ids[0], "organization_id": oid, "status": "pending", "role": "manager", "email": f"m.{oid}@example.com"},
        {"id": ids[1], "organization_id": oid, "status": "pending", "role": "owner", "email": f"o.{oid}@example.com"},
        {"id": ids[2], "organization_id": ina, "status": "pending", "role": "staff", "email": f"s.{ina}@example.com"}])
    M = f"{BASE}/api/master-admin/legacy-invites/migrate"
    try:
        dry = requests.post(M, headers=H, json={}).json()
        mine = {p["legacy_id"]: p for p in dry["plan"] if p["legacy_id"] in ids}
        assert dry["apply"] is False and dry["reissued"] == 0
        assert mine[ids[1]]["role"] == "staff"  # legacy owner role is never carried over
        assert mine[ids[2]]["reason"] == "organisation_awaiting_activation"
        assert db.secure_invitations.count_documents({"organization_id": oid}) == 0
        requests.post(M, headers=H, json={"apply": True})
        assert db.invites.find_one({"id": ids[0]})["status"] == "migrated"
        assert db.invites.find_one({"id": ids[2]})["status"] == "retired"
        si = db.secure_invitations.find_one({"organization_id": oid, "email": f"m.{oid}@example.com"})
        assert si["status"] == "pending" and si["role"] == "manager" and si["require_mfa"] is True
        (_, ho), = _users(db, oid, ("owner", []))
        assert requests.post(M, headers=ho, json={}).status_code == 403
    finally:
        db.invites.delete_many({"id": {"$in": ids}})
        _purge(db, oid)
        _purge(db, ina)


def test_owner_with_other_org_login_is_flagged_not_duplicated(H):
    from tests.test_release_ce import _owner_invite
    db = _db()
    oid, other = _mk_org(db), _mk_org(db, onboarding_status="active", portal_access="activated")
    (uid, _), = _users(db, other, ("owner", []))
    email = db.users.find_one({"id": uid})["email"]
    try:
        r = _owner_invite(H, oid, email)
        assert r.status_code == 409 and "review" in r.text
        assert db.organizations.find_one({"id": oid})["activation_review_required"]["email"] == email
        assert db.users.count_documents({"email": email}) == 1
    finally:
        _purge(db, oid)
        _purge(db, other)


def test_interrupted_acceptance_recovers(H):
    from tests.test_release_ce import _owner_invite, _accept, _tok_from
    db = _db()
    oid = _mk_org(db)
    email = f"tst.rec.{uuid.uuid4().hex[:6]}@example.com"
    try:
        link = _owner_invite(H, oid, email).json()["link"]
        inv = db.secure_invitations.find_one({"organization_id": oid, "status": "pending"})
        # simulate a crash after the claim and user creation, before completion
        db.secure_invitations.update_one({"id": inv["id"]}, {"$set": {"status": "accepting", "accepting_at": "2020-01-01T00:00:00+00:00"}})
        db.users.insert_one({"id": str(uuid.uuid4()), "email": email, "organization_id": oid, "role": "owner",
                             "invited_via": inv["id"], "full_name": "Half Done"})
        assert _accept(_tok_from(link), email).status_code == 200
        assert db.users.count_documents({"email": email}) == 1
        assert db.secure_invitations.find_one({"id": inv["id"]})["status"] == "accepted"
        assert db.organizations.find_one({"id": oid})["onboarding_status"] == "active"
    finally:
        _purge(db, oid)


def test_imported_customer_cannot_buy_online_yet():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated", activated_via_invitation="tst-inv")
    (_, ho), = _users(db, oid, ("owner", []))
    try:
        for path, body in (("/api/payments/checkout/flex", {"plan": "module", "module_id": "operations"}),
                           ("/api/payments/checkout", {"package_id": "pro"})):
            r = requests.post(f"{BASE}{path}", headers=ho, json={**body, "origin_url": BASE})
            assert r.status_code == 403, (path, r.status_code, r.text)
    finally:
        _purge(db, oid)
