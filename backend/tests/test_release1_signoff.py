"""Release 1 sign-off P0: one organisation access-state check everywhere, CRM token protection, and
invitation acceptance recovery at every interruption point. Synthetic TST data removed by id."""
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402
from tests.test_release_ce import BYP, _mk_org, _purge, _owner_invite, _accept, _tok_from, PW  # noqa: E402

ME = f"{BASE}/api/auth/me"
CRM_ME = f"{BASE}/api/crm/auth/me"


def _user(db, oid, role="owner", **extra):
    uid = str(uuid.uuid4())
    email = f"tst.so.{uid[:8]}@example.com"
    db.users.insert_one({"id": uid, "email": email, "organization_id": oid, "role": role, "full_name": "T", **extra})
    return uid, email, {"Authorization": f"Bearer {_token(email)}"}


def _crm(db, email, oid, **extra):
    from routes.crm_auth import crm_create_token
    cid = str(uuid.uuid4())
    db.crm_users.insert_one({"id": cid, "email": email, "organization_id": oid, "role": "manager", "full_name": "C", **extra})
    return cid, lambda **kw: {"Authorization": f"Bearer {crm_create_token(cid, **kw)}"}


@pytest.mark.parametrize("state", [{"onboarding_status": "pending_activation"}, {"portal_access": "not_activated"},
                                   {"provisioning_state": "importing"}])
def test_existing_sessions_lose_access_when_org_not_activated(state):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    uid, email, h = _user(db, oid)
    cid, crm_h = _crm(db, email, oid)
    try:
        assert requests.get(ME, headers=h).status_code == 200
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 200
        db.organizations.update_one({"id": oid}, {"$set": state})
        time.sleep(11)  # access-state cache window
        assert requests.get(ME, headers=h).status_code == 403
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 403
        assert requests.post(f"{BASE}/api/auth/refresh", headers=h).status_code in (401, 403)
    finally:
        db.crm_users.delete_many({"id": cid})
        _purge(db, oid)


def test_pulse_admin_not_blocked_by_customer_state(H):
    assert requests.get(ME, headers=H).status_code == 200


def test_crm_token_cannot_outrun_platform_account():
    from routes.crm_auth import crm_create_token  # noqa: F401
    import jwt
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    other = _mk_org(db, onboarding_status="active", portal_access="activated")
    uid, email, _ = _user(db, oid)
    cid, crm_h = _crm(db, email, oid, cross_login_provisioned=True)
    env = dict(line.split("=", 1) for line in open("/app/backend/.env").read().splitlines() if "=" in line)
    try:
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 200
        # a pending second-factor token is not a session
        pend = jwt.encode({"user_id": cid, "crm": True, "pending_2fa": True, "exp": int(time.time()) + 300},
                          env["JWT_SECRET"].strip('"'), algorithm="HS256")
        assert requests.get(CRM_ME, headers={"Authorization": f"Bearer {pend}"}).status_code == 401
        # platform MFA required -> CRM token without a second factor refused; with one accepted
        db.users.update_one({"id": uid}, {"$set": {"mfa_enrolment_required": True}})
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 401
        assert requests.get(CRM_ME, headers=crm_h(mfa=True)).status_code == 200
        db.users.update_one({"id": uid}, {"$unset": {"mfa_enrolment_required": ""}})
        # central session revocation applies to CRM tokens
        old = crm_h()
        time.sleep(1.1)
        db.users.update_one({"id": uid}, {"$set": {"tokens_revoked_before": int(time.time())}})
        assert requests.get(CRM_ME, headers=old).status_code == 401
        time.sleep(1.1)
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 200
        # disabled platform account
        db.users.update_one({"id": uid}, {"$set": {"status": "disabled"}})
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 401
        db.users.update_one({"id": uid}, {"$unset": {"status": ""}})
        # moved to another organisation -> old CRM identity stops
        db.users.update_one({"id": uid}, {"$set": {"organization_id": other}})
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 401
        # platform user removed -> orphaned cross-login CRM identity stops
        db.users.delete_one({"id": uid})
        assert requests.get(CRM_ME, headers=crm_h()).status_code == 401
        # CRM password login refused when the platform account needs MFA and CRM has no 2FA
        from utils.auth import hash_password
        uid2, email2, _ = _user(db, oid, password=hash_password(PW), mfa_enrolment_required=True)
        db.crm_users.insert_one({"id": str(uuid.uuid4()), "email": email2, "organization_id": oid, "role": "manager",
                                 "full_name": "C2", "password": hash_password(PW)})
        r = requests.post(f"{BASE}/api/crm/auth/login", headers=BYP, json={"email": email2, "password": PW})
        assert r.status_code == 403 and not r.json().get("token")
    finally:
        db.crm_users.delete_many({"organization_id": {"$in": [oid, other]}})
        _purge(db, oid)
        _purge(db, other)


def test_gym_floor_session_blocked_when_org_not_activated():
    from routes.gym_floor import _hash
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    db.sites.insert_one({"id": f"{oid}-a", "organization_id": oid, "name": "A"})
    u = f"tst-gfso-{oid[-6:]}"
    db.gym_floor_credentials.insert_one({"id": f"{oid}:{oid}-a", "organization_id": oid, "site_id": f"{oid}-a",
                                         "username": u, "password_hash": _hash("secret12"), "enabled": True})
    try:
        tok = requests.post(f"{BASE}/api/gym-floor/login", json={"username": u, "password": "secret12"}).json()["token"]
        hh = {"X-Gym-Floor-Token": tok}
        assert requests.get(f"{BASE}/api/gym-floor/equipment", headers=hh).status_code == 200
        db.organizations.update_one({"id": oid}, {"$set": {"onboarding_status": "pending_activation"}})
        time.sleep(11)
        assert requests.get(f"{BASE}/api/gym-floor/equipment", headers=hh).status_code == 401
    finally:
        _purge(db, oid)


def _interrupt(db, stage, inv_id, oid, email):
    """Recreate the database state left by a crash at `stage` of acceptance."""
    from utils.auth import hash_password
    uid = str(uuid.uuid4())
    if stage == "before_user":
        db.secure_invitations.update_one({"id": inv_id}, {"$set": {"status": "accepting", "accepting_at": "2020-01-01T00:00:00+00:00"}})
        return
    db.users.insert_one({"id": uid, "email": email, "organization_id": oid, "role": "owner", "invited_via": inv_id,
                         "full_name": "O", "password": hash_password(PW), "mfa_enrolment_required": True})
    if stage == "after_user":
        db.secure_invitations.update_one({"id": inv_id}, {"$set": {"status": "accepting", "accepting_at": "2020-01-01T00:00:00+00:00"}})
    elif stage == "after_org_activated":
        db.secure_invitations.update_one({"id": inv_id}, {"$set": {"status": "accepting", "accepting_at": "2020-01-01T00:00:00+00:00"}})
        db.organizations.update_one({"id": oid}, {"$set": {"onboarding_status": "active", "portal_access": "activated",
                                                         "activated_via_invitation": inv_id, "owner_id": uid}})
    elif stage == "after_accepted_before_org":  # older ordering: invitation consumed, organisation not yet activated
        db.secure_invitations.update_one({"id": inv_id}, {"$set": {"status": "accepted", "accepted_user_id": uid}})


@pytest.mark.parametrize("stage", ["before_user", "after_user", "after_org_activated", "after_accepted_before_org"])
@pytest.mark.parametrize("recover_by", ["accept_again", "sign_in"])
def test_interrupted_acceptance_recovers(H, stage, recover_by):
    db = _db()
    oid = _mk_org(db)
    email = f"tst.int.{uuid.uuid4().hex[:8]}@example.com"
    try:
        link = _owner_invite(H, oid, email).json()["link"]
        inv = db.secure_invitations.find_one({"organization_id": oid, "status": "pending"})
        _interrupt(db, stage, inv["id"], oid, email)
        if recover_by == "accept_again" or stage == "before_user":
            r = _accept(_tok_from(link), email)
            assert r.status_code in (200, 410), r.text
        else:
            requests.post(f"{BASE}/api/auth/login", headers=BYP, json={"email": email, "password": PW})
        org = db.organizations.find_one({"id": oid})
        assert db.users.count_documents({"email": email}) == 1
        assert db.users.count_documents({"organization_id": oid, "role": "owner"}) == 1
        assert db.secure_invitations.find_one({"id": inv["id"]})["status"] == "accepted"
        assert org["onboarding_status"] == "active" and org["portal_access"] == "activated" and org["id"] == oid
        assert org["account_type"] == "lite" and org["subscription_tier"] == "free" and org["enabled_modules"] == ["operations"]
    finally:
        _purge(db, oid)


def test_every_purchase_route_refuses_imported_customers():
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated", activated_via_invitation="tst-inv")
    _, _, h = _user(db, oid)
    routes = [("/api/payments/checkout", {"package_id": "pro"}), ("/api/payments/checkout/flex", {"plan": "module", "module_id": "crm"}),
              ("/api/me/crm-business/checkout", {}), ("/api/me/module-trials/start", {"module": "crm"}),
              ("/api/me/upgrade-to-pro", {}), ("/api/me/module-purchase/checkout", {"module": "crm"}),
              ("/api/financial-ops/checkout", {}), ("/api/financial-ops/llm-top-up", {})]
    try:
        for path, body in routes:
            r = requests.post(f"{BASE}{path}", headers=h, json={**body, "origin_url": BASE})
            assert r.status_code == 403, (path, r.status_code, r.text[:200])
        org = db.organizations.find_one({"id": oid})
        assert org["account_type"] == "lite" and not org.get("module_trials")
    finally:
        _purge(db, oid)


def test_test_mailbox_allowlist_only(monkeypatch):
    import asyncio
    from utils import secure_invites as SI, email as E
    sent = []

    async def fake(inv, link, name):
        sent.append((inv["email"], link))
        return True
    monkeypatch.setattr(E, "send_activation_invite_email", fake)
    monkeypatch.setenv("INVITATION_EMAILS_LIVE", "false")
    monkeypatch.setenv("INVITATION_TEST_RECIPIENTS", "it.test@pulsefitness.example")
    loop = asyncio.new_event_loop()
    try:
        a = loop.run_until_complete(SI._deliver({"email": "it.test@pulsefitness.example"}, "t" * 40, "Pulse"))
        b = loop.run_until_complete(SI._deliver({"email": "customer@example.com"}, "t" * 40, "Pulse"))
    finally:
        loop.close()
    assert a["mode"] == "sent" and b["mode"] == "held" and [x[0] for x in sent] == ["it.test@pulsefitness.example"]
    assert sent[0][1].endswith("/accept-invite#token=" + "t" * 40)


def test_purchase_gate_covers_imported_customers_activated_any_way_but_not_mod_estates():
    db = _db()
    imp = _mk_org(db, onboarding_status="active", portal_access="activated", created_via="sage_customer_import")
    mod = _mk_org(db, onboarding_status="active", portal_access="activated", created_via="mod_bulk_import")
    try:
        _, _, hi = _user(db, imp)
        _, _, hm = _user(db, mod)
        assert requests.post(f"{BASE}/api/me/upgrade-to-pro", headers=hi, json={}).status_code == 403
        assert requests.post(f"{BASE}/api/me/upgrade-to-pro", headers=hm, json={}).status_code != 403
    finally:
        _purge(db, imp)
        _purge(db, mod)
