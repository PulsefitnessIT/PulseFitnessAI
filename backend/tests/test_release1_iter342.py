"""Iteration 342 independent retest of Release 1 P0 items (activation, session revocation, team-management
side doors). Synthetic TST orgs/users only, removed by exact id."""
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402
from tests.test_release_ce import BYP, PW, _mk_org, _purge, _owner_invite, _accept, _tok_from  # noqa: E402

ISO_PW = "IsoDemo123!"


def _user(db, oid, role, sites=None, **kw):
    from utils.auth import hash_password
    uid = str(uuid.uuid4())
    email = f"tst.i342.{role}.{uid[:6]}@example.com"
    db.users.insert_one({"id": uid, "email": email, "organization_id": oid, "role": role, "full_name": role.title(),
                         "allowed_site_ids": sites or [], "password": hash_password(PW), **kw})
    return uid, email, {"Authorization": f"Bearer {_token(email)}"}


def _login(email, pw):
    return requests.post(f"{BASE}/api/auth/login", headers=BYP, json={"email": email, "password": pw}, timeout=30)


# --- A: logins / reset / registration sanity
def test_seeded_logins_and_password_reset_respond():
    for e in ("owner@isodemo.com", "manager@isodemo.com"):
        r = _login(e, ISO_PW)
        assert r.status_code == 200, (e, r.text)
        d = r.json()
        assert d.get("token") or d.get("requires_mfa") or d.get("requires_mfa_enrolment"), d
    r = requests.post(f"{BASE}/api/auth/password-reset/request", headers=BYP, json={"email": "nobody.tst@example.com"}, timeout=30)
    if r.status_code == 404:
        r = requests.post(f"{BASE}/api/auth/forgot-password", headers=BYP, json={"email": "nobody.tst@example.com"}, timeout=30)
    assert r.status_code == 200, r.text


# --- D: verification required, Sage hold, expiry
def test_owner_invite_requires_verification_sage_hold_and_expires(H):
    db = _db()
    oid = _mk_org(db)
    email = f"tst.i342.own.{uuid.uuid4().hex[:6]}@example.com"
    try:
        r = _owner_invite(H, oid, email, verification_method="")
        assert r.status_code in (400, 422), r.text
        db.customer_account_internal.insert_one({"org_id": oid, "sage_status": {"on_hold": True}})
        assert _owner_invite(H, oid, email).status_code == 409
        r = _owner_invite(H, oid, email, accounts_confirmed=True)
        assert r.status_code == 200, r.text
        tok = _tok_from(r.json()["link"])
        inv = db.secure_invitations.find_one({"id": r.json()["invitation"]["id"]})
        hrs = (datetime.fromisoformat(inv["expires_at"]) - datetime.fromisoformat(inv["created_at"])).total_seconds() / 3600
        assert round(hrs) == 72
        db.secure_invitations.update_one({"id": inv["id"]}, {"$set": {"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}})
        assert _accept(tok, email).status_code == 410
        assert db.users.count_documents({"email": email}) == 0
    finally:
        db.customer_account_internal.delete_many({"org_id": oid})
        _purge(db, oid)


# --- D: concurrency, LITE kept, same org/sites/equipment, MFA enrolment login, inactive member login
def test_concurrent_accept_single_user_lite_kept_and_mfa_login(H):
    db = _db()
    oid = _mk_org(db)
    site = f"{oid}-s1"
    db.sites.insert_one({"id": site, "organization_id": oid, "name": "TST Site"})
    db.equipment.insert_one({"id": f"{oid}-eq", "organization_id": oid, "site_id": site, "name": "TST Treadmill"})
    pre_uid, pre_email, pre_h = _user(db, oid, "staff")
    email = f"tst.i342.cc.{uuid.uuid4().hex[:6]}@example.com"
    try:
        # inactive org member cannot sign in before activation
        r = _login(pre_email, PW)
        print("inactive-org member login:", r.status_code, r.text[:200])
        inactive_login_blocked = r.status_code in (401, 403) or not r.json().get("token")
        link = _owner_invite(H, oid, email).json()["link"]
        tok = _tok_from(link)
        with ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(lambda _: _accept(tok, email).status_code, range(8)))
        assert codes.count(200) == 1, codes
        assert db.users.count_documents({"email": email}) == 1
        org = db.organizations.find_one({"id": oid})
        assert org["account_type"] == "lite" and org["enabled_modules"] == ["operations"] and org["subscription_tier"] == "free"
        assert db.sites.count_documents({"organization_id": oid}) == 1 and db.equipment.count_documents({"organization_id": oid}) == 1
        assert db.users.find_one({"email": email})["organization_id"] == oid
        d = _login(email, PW).json()
        assert d.get("requires_mfa_enrolment") is True and not d.get("token"), d
        assert inactive_login_blocked, "member of a pending_activation org was able to sign in"
    finally:
        _purge(db, oid)


# --- E: central revocation
def test_disabled_or_revoked_user_rejected_everywhere():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    uid, _, h = _user(db, oid, "manager")
    try:
        assert requests.get(f"{BASE}/api/auth/me", headers=h).status_code == 200
        for flag in ("is_active", "active"):
            db.users.update_one({"id": uid}, {"$set": {flag: False}})
            for p in ("/api/auth/me", "/api/gym-floor/handover"):
                assert requests.get(f"{BASE}{p}", headers=h).status_code == 401, (flag, p)
            db.users.update_one({"id": uid}, {"$unset": {flag: ""}})
        db.users.update_one({"id": uid}, {"$set": {"tokens_revoked_before": int(datetime.now(timezone.utc).timestamp()) + 5}})
        assert requests.get(f"{BASE}/api/auth/me", headers=h).status_code == 401
    finally:
        _purge(db, oid)


# --- C: manager cannot withdraw a legacy manager invite
def test_manager_cannot_delete_legacy_manager_invite():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa = f"{oid}-a"
    db.sites.insert_one({"id": sa, "organization_id": oid, "name": "A"})
    _, _, hm = _user(db, oid, "manager", [sa])
    lid = f"tst-i342-leg-{oid}"
    db.invites.insert_one({"id": lid, "organization_id": oid, "status": "pending", "role": "manager", "email": f"l.{oid}@example.com"})
    try:
        r = requests.delete(f"{BASE}/api/organization/invite/{lid}", headers=hm)
        print("legacy manager invite delete by manager:", r.status_code)
        assert db.invites.count_documents({"id": lid}) == 1
        assert r.status_code == 403, r.status_code
    finally:
        db.invites.delete_many({"id": lid})
        _purge(db, oid)


# --- B (side door): /api/account/team/* used by Account Settings -> Team must honour the same rules
def test_account_team_endpoints_enforce_manager_scope():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    mgr, _, hm = _user(db, oid, "manager", [sa])
    mgr2, _, _ = _user(db, oid, "manager", [sb])
    stb, _, _ = _user(db, oid, "staff", [sb])
    T = f"{BASE}/api/account/team"
    findings = {}
    try:
        r = requests.patch(f"{T}/{mgr}/site-access", headers=hm, json={"allowed_site_ids": []})
        findings["manager_widens_own_scope_to_all_sites"] = r.status_code
        db.users.update_one({"id": mgr}, {"$set": {"allowed_site_ids": [sa]}})
        hm = {"Authorization": f"Bearer {_token(db.users.find_one({'id': mgr})['email'])}"}
        r = requests.patch(f"{T}/{stb}/site-access", headers=hm, json={"allowed_site_ids": [sa]})
        findings["manager_moves_other_site_staff"] = r.status_code
        r = requests.patch(f"{T}/{mgr2}", headers=hm, json={"role": "staff"})
        findings["manager_demotes_other_manager"] = r.status_code
        r = requests.post(f"{T}/invite", headers=hm, json={"email": f"tst.i342.inv.{uuid.uuid4().hex[:6]}@example.com",
                                                           "full_name": "TST Inv", "role": "staff", "allowed_site_ids": [sb]})
        findings["manager_creates_staff_at_other_site_direct_user"] = r.status_code
        r = requests.delete(f"{T}/{mgr2}", headers=hm)
        findings["manager_deletes_other_manager"] = r.status_code
        print("ACCOUNT/TEAM findings:", findings)
        assert all(c in (403, 404) for c in findings.values()), findings
    finally:
        _purge(db, oid)


# --- E: 'disable' from Account Settings -> Team must stop sign-in and sessions
def test_team_status_disabled_blocks_access():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    _, _, ho = _user(db, oid, "owner")
    sid, semail, hs = _user(db, oid, "staff")
    try:
        r = requests.patch(f"{BASE}/api/account/team/{sid}", headers=ho, json={"status": "disabled"})
        assert r.status_code == 200, r.text
        me = requests.get(f"{BASE}/api/auth/me", headers=hs).status_code
        lg = _login(semail, PW)
        print("after status=disabled: /auth/me", me, "login", lg.status_code)
        assert me == 401 and lg.status_code in (401, 403)
    finally:
        _purge(db, oid)


# --- G: ordinary self-signup org is not blocked by the imported-customer gate
def test_self_signup_org_not_hit_by_import_gate():
    db = _db()
    oid = "tst-" + uuid.uuid4().hex[:10]
    db.organizations.insert_one({"id": oid, "name": "TST SelfSignup", "subscription_tier": "none"})
    _, _, ho = _user(db, oid, "owner")
    try:
        r = requests.post(f"{BASE}/api/payments/checkout/flex", headers=ho,
                          json={"plan": "module", "module_id": "operations", "origin_url": BASE})
        print("self-signup checkout/flex:", r.status_code, r.text[:160])
        assert not (r.status_code == 403 and "import" in r.text.lower()), r.text
    finally:
        _purge(db, oid)


# --- F: gym floor setup rules, cross-org handover isolation, manager site scope on handover delete
def test_gym_floor_setup_rules_and_handover_isolation():
    from tests.test_release1_gym_floor import _setup, _device, G
    db = _db()
    oid, other, sa, sb, own, ho = _setup(db)
    _, _, h_other = _user(db, other, "owner")
    _, _, hm_a = _user(db, oid, "manager", [sa])
    u1, u2 = f"tst-i342a-{own[:6]}", f"tst-i342b-{own[:6]}"
    try:
        assert requests.post(f"{G}/setup", headers=ho, json={"username": u1, "password": "secret12"}).status_code == 400
        ta = _device(ho, u1, sa)
        r = requests.post(f"{G}/setup", headers=ho, json={"username": u1, "password": "secret12", "site_id": sb})
        assert r.status_code == 409, r.text
        tb = _device(ho, u2, sb)
        assert requests.post(f"{G}/setup", headers=hm_a, json={"username": "tst-i342c", "password": "secret12", "site_id": sb}).status_code == 403
        nb = requests.post(f"{G}/handover", headers=tb, json={"staff_name": "B", "topic_id": "general", "notes": "TST site B note"}).json()["entry"]
        ng = requests.post(f"{G}/handover", headers=ho, json={"staff_name": "O", "topic_id": "general", "notes": "TST no-site note"}).json()["entry"]
        a_notes = {e["id"] for e in requests.get(f"{G}/handover", headers=ta).json()["entries"]}
        assert ng["id"] in a_notes and nb["id"] not in a_notes
        other_notes = {e["id"] for e in requests.get(f"{G}/handover", headers=h_other).json()["entries"]}
        assert not ({nb["id"], ng["id"]} & other_notes)
        assert requests.get(f"{G}/staff", headers=ta).status_code == 200
        # device tokens cannot reach payment / billing endpoints either
        for p in ("/api/payments/checkout/flex",):
            assert requests.post(f"{BASE}{p}", headers=ta, json={"plan": "module", "module_id": "operations"}).status_code in (401, 403)
        r = requests.delete(f"{G}/handover/{nb['id']}", headers=hm_a)
        print("site-A manager deletes site-B handover note:", r.status_code)
        assert r.status_code in (403, 404), "restricted manager deleted another site's handover note"
    finally:
        db.gym_floor_handover.delete_many({"organization_id": {"$in": [oid, other]}})
        db.gym_floor_topics.delete_many({"organization_id": {"$in": [oid, other]}})
        _purge(db, oid)
        _purge(db, other)
