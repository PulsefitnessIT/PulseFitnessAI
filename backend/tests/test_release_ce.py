"""Release C (secure invitations, owner activation, site-scoped staff, site gym-floor devices, trial-reminder dedupe)
and Release E (LITE->PRO, cancel/end/reactivate, commercial reporting). Synthetic TST data, removed by id."""
import asyncio
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402

ENV = dict(line.split("=", 1) for line in open("/app/backend/.env").read().splitlines() if "=" in line)
BYP = {"x-ratelimit-bypass": ENV.get("RATE_LIMIT_BYPASS_SECRET", "").strip()}
PW = "Tst!Activation#2026xyz"


def _mk_org(db, **extra):
    oid = "tst-" + uuid.uuid4().hex[:10]
    db.organizations.insert_one({"id": oid, "name": f"TST Gym {oid[-5:]}", "account_type": "lite",
                                 "enabled_modules": ["operations"], "modules": {"operations": {"enabled": True, "tier": "lite"}},
                                 "subscription_tier": "free", "onboarding_status": "pending_activation",
                                 "portal_access": "not_activated", **extra})
    return oid


def _purge(db, oid):
    uids = [u["id"] for u in db.users.find({"organization_id": oid}, {"id": 1})]
    for c in ("users", "sites", "equipment", "gym_floor_credentials", "gym_floor_sessions", "gym_floor_handover",
              "secure_invitations", "commercial_events", "crm2_contacts"):
        db[c].delete_many({"organization_id": oid} if c != "crm2_contacts" else {"linked_organization_id": oid})
    db.onboarding_audit_events.delete_many({"org_id": oid})
    db.activation_events.delete_many({"organization_id": oid})
    db.organizations.delete_one({"id": oid})
    db.user_mfa.delete_many({"user_id": {"$in": uids}})


def _tok_from(link):
    return link.split("#token=", 1)[1]


def _owner_invite(H, oid, email, **kw):
    body = {"email": email, "full_name": "Olive Owner", "verification_method": "phone_callback",
            "verification_note": "Called back on account number", **kw}
    return requests.post(f"{BASE}/api/master-admin/customer-activation/{oid}/owner-invite", json=body, headers=H, timeout=30)


def _accept(tok, email, pw=PW, name="Olive Owner"):
    return requests.post(f"{BASE}/api/invitations/accept", headers=BYP, timeout=30,
                         json={"token": tok, "email": email, "full_name": name, "password": pw})


def test_owner_activation_single_use_lite_kept_mfa_forced(H):
    db = _db()
    oid = _mk_org(db)
    email = f"tst.owner.{uuid.uuid4().hex[:6]}@example.com"
    try:
        r = _owner_invite(H, oid, email)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery"]["mode"] == "held" and d["link"]  # emails switched off → link shown once
        inv = db.secure_invitations.find_one({"id": d["invitation"]["id"]})
        tok = _tok_from(d["link"])
        assert inv["token_hash"] != tok and tok not in str(inv)  # only the hash is stored
        assert d["invitation"]["verification"]["method"] == "phone_callback"
        # GET on the link does nothing (scanner-safe); inspect is a POST and does not consume
        ins = requests.post(f"{BASE}/api/invitations/inspect", json={"token": tok}, headers=BYP, timeout=30).json()
        assert ins["state"] == "valid" and ins["kind"] == "owner_activation" and "@example.com" in ins["email_hint"]
        assert email not in str(ins)
        # wrong email refused
        assert _accept(tok, "someone.else@example.com").status_code == 400
        # still pending, not activated
        assert db.organizations.find_one({"id": oid})["onboarding_status"] == "pending_activation"
        r = _accept(tok, email)
        assert r.status_code == 200, r.text
        assert r.json()["requires_mfa_setup"] is True
        org = db.organizations.find_one({"id": oid})
        assert org["onboarding_status"] == "active" and org["portal_access"] == "activated"
        assert org["account_type"] == "lite" and org["subscription_tier"] == "free"  # entitlement unchanged
        assert org["enabled_modules"] == ["operations"]
        u = db.users.find_one({"email": email})
        assert u["role"] == "owner" and u["mfa_enrolment_required"] is True and org["owner_id"] == u["id"]
        # single use
        assert _accept(tok, email).status_code == 410
        # login must force MFA enrolment, no session token
        lr = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, headers=BYP, timeout=30).json()
        assert lr.get("requires_mfa_enrolment") is True and not lr.get("token")
        # cannot invite again once activated
        assert _owner_invite(H, oid, "x" + email).status_code == 409
    finally:
        _purge(db, oid)


def test_owner_invite_guards_revoke_reissue_and_expiry(H):
    db = _db()
    oid = _mk_org(db)
    email = f"tst.owner.{uuid.uuid4().hex[:6]}@example.com"
    try:
        assert _owner_invite(H, oid, email, verification_method="guess").status_code == 400
        assert _owner_invite(H, oid, email, verification_note="").status_code == 422
        db.customer_account_internal.insert_one({"org_id": oid, "account_ref": "TSTX", "sage_status": {"on_hold": True}})
        assert _owner_invite(H, oid, email).status_code == 409  # Sage hold
        r1 = _owner_invite(H, oid, email, accounts_confirmed=True).json()
        r2 = _owner_invite(H, oid, email, accounts_confirmed=True).json()  # supersedes r1
        assert db.secure_invitations.find_one({"id": r1["invitation"]["id"]})["status"] == "superseded"
        assert _accept(_tok_from(r1["link"]), email).status_code == 410
        rv = requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{r2['invitation']['id']}/revoke", headers=H, timeout=30)
        assert rv.status_code == 200
        assert _accept(_tok_from(r2["link"]), email).status_code == 410
        r3 = _owner_invite(H, oid, email, accounts_confirmed=True).json()
        db.secure_invitations.update_one({"id": r3["invitation"]["id"]}, {"$set": {"expires_at": "2020-01-01T00:00:00+00:00"}})
        assert requests.post(f"{BASE}/api/invitations/inspect", json={"token": _tok_from(r3["link"])}, headers=BYP).json()["state"] == "expired"
        assert _accept(_tok_from(r3["link"]), email).status_code == 410
        re = requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{r3['invitation']['id']}/reissue", headers=H, timeout=30).json()
        assert _accept(_tok_from(re["link"]), email).status_code == 200
        # activation list shows the detail endpoint works for delegated view
        det = requests.get(f"{BASE}/api/master-admin/customer-activation/{oid}", headers=H, timeout=30).json()
        assert det["emails_live"] is False and any(i["status"] == "accepted" for i in det["invitations"])
    finally:
        db.customer_account_internal.delete_many({"org_id": oid})
        _purge(db, oid)


def test_non_pulse_user_cannot_invite_owner(H):
    db = _db()
    oid, other = _mk_org(db), _mk_org(db, onboarding_status="active", portal_access="activated")
    uid = str(uuid.uuid4())
    db.users.insert_one({"id": uid, "email": f"tst.{uid[:6]}@example.com", "organization_id": other, "role": "owner",
                         "full_name": "T", "is_pulse_staff": True, "onboarding_permissions": ["activation.invite"]})
    try:
        h = {"Authorization": f"Bearer {_token(f'tst.{uid[:6]}@example.com')}"}
        assert _owner_invite(h, oid, "a@example.com").status_code == 403  # stale delegation flag, not in Pulse org
    finally:
        _purge(db, oid)
        _purge(db, other)


def test_staff_invite_site_scope_and_manager_limits(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    own, mgr = str(uuid.uuid4()), str(uuid.uuid4())
    db.users.insert_many([
        {"id": own, "email": f"tst.o.{own[:6]}@example.com", "organization_id": oid, "role": "owner", "full_name": "O"},
        {"id": mgr, "email": f"tst.m.{mgr[:6]}@example.com", "organization_id": oid, "role": "manager", "full_name": "M",
         "allowed_site_ids": [sa]}])
    ho = {"Authorization": f"Bearer {_token(f'tst.o.{own[:6]}@example.com')}"}
    hm = {"Authorization": f"Bearer {_token(f'tst.m.{mgr[:6]}@example.com')}"}
    try:
        u = f"{BASE}/api/organization/invite"
        assert requests.post(u, headers=ho, json={"email": "x@example.com", "role": "staff", "allowed_site_ids": ["nope"]}).status_code == 400
        assert requests.post(u, headers=hm, json={"email": "y@example.com", "role": "manager"}).status_code == 400
        assert requests.post(u, headers=hm, json={"email": "y@example.com", "role": "staff", "allowed_site_ids": [sb]}).status_code == 403
        r = requests.post(u, headers=hm, json={"email": f"tst.s.{mgr[:5]}@example.com", "role": "staff", "allowed_site_ids": [sa]})
        assert r.status_code == 200 and "company_code" not in r.json() and r.json()["link"]
        rm = requests.post(u, headers=ho, json={"email": f"tst.mm.{mgr[:5]}@example.com", "role": "manager", "allowed_site_ids": [sb]}).json()
        assert rm["invitation"]["require_mfa"] is True
        lst = requests.get(f"{BASE}/api/organization/invites", headers=ho).json()["invites"]
        assert len(lst) == 2 and all("token_hash" not in i for i in lst)
        # manager cannot re-send owner's manager invite
        assert requests.post(f"{u}/{rm['invitation']['id']}/resend", headers=hm).status_code == 403
        assert _accept(_tok_from(r.json()["link"]), f"tst.s.{mgr[:5]}@example.com", name="Sam").status_code == 200
        su = db.users.find_one({"email": f"tst.s.{mgr[:5]}@example.com"})
        assert su["role"] == "staff" and su["allowed_site_ids"] == [sa] and su["organization_id"] == oid
        # existing email (any org) cannot be invited
        assert requests.post(u, headers=ho, json={"email": f"tst.m.{mgr[:6]}@example.com", "role": "staff"}).status_code == 409
        # cancel revokes
        assert requests.delete(f"{u}/{rm['invitation']['id']}", headers=ho).status_code == 200
        assert _accept(_tok_from(rm["link"]), f"tst.mm.{mgr[:5]}@example.com").status_code == 410
    finally:
        _purge(db, oid)


def test_gym_floor_devices_are_site_specific(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", account_type="pulse_pro")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    db.equipment.insert_many([{"id": f"{oid}-ea", "organization_id": oid, "site_id": sa, "name": "Tread A"},
                              {"id": f"{oid}-eb", "organization_id": oid, "site_id": sb, "name": "Tread B"}])
    own = str(uuid.uuid4())
    db.users.insert_one({"id": own, "email": f"tst.o.{own[:6]}@example.com", "organization_id": oid, "role": "owner", "full_name": "O"})
    ho = {"Authorization": f"Bearer {_token(f'tst.o.{own[:6]}@example.com')}"}
    ua, ub = f"tst-a-{own[:6]}", f"tst-b-{own[:6]}"
    try:
        g = f"{BASE}/api/gym-floor"
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ua, "password": "secret12"}).status_code == 400
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ua, "password": "secret12", "site_id": sa}).status_code == 200
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ua, "password": "secret12", "site_id": sb}).status_code == 409
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ub, "password": "secret12", "site_id": sb}).status_code == 200
        la = requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).json()
        assert la["site_id"] == sa and la["expires_at"]
        ta = {"X-Gym-Floor-Token": la["token"]}
        eq = requests.get(f"{g}/equipment", headers=ta).json()["equipment"]
        assert [e["name"] for e in eq] == ["Tread A"]
        requests.post(f"{g}/handover", headers=ta, json={"staff_name": "Sam", "topic_id": "general", "notes": "Site A note"})
        lb = requests.post(f"{g}/login", json={"username": ub, "password": "secret12"}).json()
        tb = {"X-Gym-Floor-Token": lb["token"]}
        assert requests.get(f"{g}/handover", headers=tb).json()["entries"] == []
        assert len(requests.get(f"{g}/handover", headers=ta).json()["entries"]) == 1
        st = requests.get(f"{g}/status", headers=ho).json()
        assert len(st["credentials"]) == 2 and all("password_hash" not in c for c in st["credentials"])
        # disabling device A signs it out immediately
        assert requests.post(f"{g}/devices/{oid}:{sa}/disable", headers=ho).status_code == 200
        assert requests.get(f"{g}/equipment", headers=ta).status_code == 401
        assert requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).status_code == 401
        # expired session refused
        db.gym_floor_sessions.update_one({"token": lb["token"]}, {"$set": {"expires_at": "2020-01-01T00:00:00+00:00"}})
        assert requests.get(f"{g}/equipment", headers=tb).status_code == 401
    finally:
        _purge(db, oid)


def test_trial_ending_email_sent_once_across_senders():
    from utils import email_claims
    db = _db()
    oid = "tst-" + uuid.uuid4().hex[:8]

    async def run():
        key = email_claims.trial_ending_key(oid, "2026-12-01T10:00:00+00:00")
        res = await asyncio.gather(*[email_claims.claim(key, sender=f"s{i}") for i in range(5)])
        return res, key
    loop = asyncio.new_event_loop()
    try:
        res, key = loop.run_until_complete(run())
        assert sum(res) == 1
    finally:
        db.email_send_claims.delete_many({"key": {"$regex": f"^trial_ending:{oid}"}})
        loop.close()


def test_lite_to_pro_upgrade_cancel_end_and_reporting(H):
    from routes import payments as P
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    db.sites.insert_one({"id": f"{oid}-a", "organization_id": oid, "name": "A"})
    db.equipment.insert_one({"id": f"{oid}-e", "organization_id": oid, "site_id": f"{oid}-a", "name": "Bike"})
    own = str(uuid.uuid4())
    em = f"tst.o.{own[:6]}@example.com"
    db.users.insert_one({"id": own, "email": em, "organization_id": oid, "role": "owner", "full_name": "O"})
    ho = {"Authorization": f"Bearer {_token(em)}"}
    sub = "sub_tst_" + uuid.uuid4().hex[:10]
    loop = asyncio.new_event_loop()
    try:
        sess = {"subscription": sub, "customer": "cus_tst", "metadata": {"billing_cycle": "monthly"}}
        loop.run_until_complete(P._activate_module_subscription(own, "operations", "cs_tst_" + own[:6], sess))
        loop.run_until_complete(P._activate_module_subscription(own, "operations", "cs_tst_" + own[:6], sess))  # idempotent
        org = db.organizations.find_one({"id": oid})
        assert org["account_type"] == "pulse_pro" and org["modules"]["operations"]["source"] == "paid"
        assert db.commercial_events.count_documents({"organization_id": oid, "event": "upgraded_lite_to_pro"}) == 1
        prods = {p["module"]: p for p in requests.get(f"{BASE}/api/account/billing/modules", headers=ho).json()["products"]}
        assert prods["operations"]["status"] == "active" and prods["crm"]["status"] == "not_subscribed"
        rep = requests.get(f"{BASE}/api/master-admin/commercial/summary", headers=H).json()
        assert rep["mrr"] >= 69 and rep["products"][0]["paying"] >= 1
        assert requests.get(f"{BASE}/api/master-admin/commercial/summary", headers=ho).status_code == 403
        # Stripe-side cancel at period end then subscription ends → back to LITE, data intact
        loop.run_until_complete(P._handle_subscription_updated({"id": sub, "cancel_at_period_end": True, "status": "active",
                                                                "current_period_end": 1893456000}))
        prods = {p["module"]: p for p in requests.get(f"{BASE}/api/account/billing/modules", headers=ho).json()["products"]}
        assert prods["operations"]["status"] == "cancelling"
        loop.run_until_complete(P._handle_subscription_deleted({"id": sub}))
        org = db.organizations.find_one({"id": oid})
        assert org["account_type"] == "lite" and org["modules"]["operations"]["enabled"] is True
        assert org["module_subscriptions"]["operations"]["status"] == "ended"
        assert db.equipment.count_documents({"organization_id": oid}) == 1 and db.sites.count_documents({"organization_id": oid}) == 1
        assert requests.post(f"{BASE}/api/account/billing/modules/operations/reactivate", headers=ho).status_code == 409
        # buying again = reactivation, same organisation
        sess2 = {"subscription": sub + "b", "customer": "cus_tst", "metadata": {"billing_cycle": "annual"}}
        loop.run_until_complete(P._activate_module_subscription(own, "operations", "cs_tst2_" + own[:6], sess2))
        assert db.commercial_events.count_documents({"organization_id": oid, "event": "reactivated"}) == 1
        assert db.organizations.find_one({"id": oid})["account_type"] == "pulse_pro"
        # admin-granted product is never switched off by a Stripe event
        db.organizations.update_one({"id": oid}, {"$set": {"modules.crm": {"enabled": True, "source": "admin"},
                                                           "module_subscriptions.crm.stripe_subscription_id": sub + "c"}})
        loop.run_until_complete(P._handle_subscription_deleted({"id": sub + "c"}))
        assert db.organizations.find_one({"id": oid})["modules"]["crm"]["enabled"] is True
        # invoiced product cannot be self-cancelled
        assert requests.post(f"{BASE}/api/account/billing/modules/crm/cancel", headers=ho, json={"reason": "cost"}).status_code == 409
        # staff cannot change products
        sid = str(uuid.uuid4())
        db.users.insert_one({"id": sid, "email": f"tst.s.{sid[:6]}@example.com", "organization_id": oid, "role": "staff", "full_name": "S"})
        hs = {"Authorization": f"Bearer {_token(f'tst.s.{sid[:6]}@example.com')}"}
        assert requests.post(f"{BASE}/api/account/billing/modules/operations/cancel", headers=hs, json={"reason": "x1"}).status_code == 403
    finally:
        loop.close()
        db.payment_transactions.delete_many({"session_id": {"$regex": "^cs_tst"}})
        _purge(db, oid)


def test_second_owner_invite_cannot_activate_after_first(H):
    db = _db()
    oid = _mk_org(db)
    a, b = f"tst.a.{uuid.uuid4().hex[:6]}@example.com", f"tst.b.{uuid.uuid4().hex[:6]}@example.com"
    try:
        ra = _owner_invite(H, oid, a).json()
        rb = _owner_invite(H, oid, b).json()  # different email: supersedes the first owner invite
        assert db.secure_invitations.find_one({"id": ra["invitation"]["id"]})["status"] == "superseded"
        assert _accept(_tok_from(ra["link"]), a).status_code == 410
        # force a stale second pending owner invite to simulate a race, then activate via b
        db.secure_invitations.update_one({"id": ra["invitation"]["id"]}, {"$set": {"status": "pending"}})
        assert _accept(_tok_from(rb["link"]), b).status_code == 200
        assert db.secure_invitations.find_one({"id": ra["invitation"]["id"]})["status"] == "superseded"
        db.secure_invitations.update_one({"id": ra["invitation"]["id"]}, {"$set": {"status": "pending"}})
        assert _accept(_tok_from(ra["link"]), a).status_code == 410
        assert db.users.count_documents({"organization_id": oid, "role": "owner"}) == 1
        r = requests.post(f"{BASE}/api/master-admin/customer-activation/invitations/{ra['invitation']['id']}/reissue", headers=H, timeout=30)
        assert r.status_code in (404, 409)
    finally:
        _purge(db, oid)


def test_manager_cannot_cancel_or_resend_outside_scope(H):
    db = _db()
    oid = _mk_org(db, onboarding_status="active", portal_access="activated")
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    own, mgr = str(uuid.uuid4()), str(uuid.uuid4())
    db.users.insert_many([
        {"id": own, "email": f"tst.o.{own[:6]}@example.com", "organization_id": oid, "role": "owner", "full_name": "O"},
        {"id": mgr, "email": f"tst.m.{mgr[:6]}@example.com", "organization_id": oid, "role": "manager", "full_name": "M",
         "allowed_site_ids": [sa]}])
    ho = {"Authorization": f"Bearer {_token(f'tst.o.{own[:6]}@example.com')}"}
    hm = {"Authorization": f"Bearer {_token(f'tst.m.{mgr[:6]}@example.com')}"}
    u = f"{BASE}/api/organization/invite"
    try:
        im = requests.post(u, headers=ho, json={"email": f"tst.x.{own[:5]}@example.com", "role": "manager"}).json()["invitation"]["id"]
        isb = requests.post(u, headers=ho, json={"email": f"tst.y.{own[:5]}@example.com", "role": "staff", "allowed_site_ids": [sb]}).json()["invitation"]["id"]
        assert requests.delete(f"{u}/{im}", headers=hm).status_code == 403
        assert requests.post(f"{u}/{isb}/resend", headers=hm).status_code == 403
        assert requests.delete(f"{u}/{isb}", headers=hm).status_code == 403
        # restricted manager with no sites given defaults to their own sites
        r = requests.post(u, headers=hm, json={"email": f"tst.z.{own[:5]}@example.com", "role": "staff"})
        assert r.status_code == 200 and r.json()["invitation"]["allowed_site_ids"] == [sa]
    finally:
        _purge(db, oid)
