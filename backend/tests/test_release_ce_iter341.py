"""Release C/E — iteration 341 retest of iteration_340 fixes. Synthetic TST orgs, removed by id."""
import asyncio
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, "/app/backend")
from tests.test_sage_sicon_customer_import import BASE, H, _db, _token  # noqa: F401,E402
from tests.test_release_ce import BYP, _mk_org, _purge, _tok_from, _owner_invite, _accept  # noqa: E402
from tests.test_release_ce_extended import _user  # noqa: E402

INV = f"{BASE}/api/organization/invite"


def _two_site_org(db, **kw):
    oid = _mk_org(db, onboarding_status="active", portal_access="activated", **kw)
    sa, sb = f"{oid}-a", f"{oid}-b"
    db.sites.insert_many([{"id": sa, "organization_id": oid, "name": "A"}, {"id": sb, "organization_id": oid, "name": "B"}])
    return oid, sa, sb


# Owner activation: only one pending owner invite per org; a stale (pending) owner invite after activation -> 410, no 2nd owner
def test_one_pending_owner_invite_and_stale_after_activation(H):
    db = _db()
    oid = _mk_org(db)
    a, b = f"tst.oa.{uuid.uuid4().hex[:6]}@example.com", f"tst.ob.{uuid.uuid4().hex[:6]}@example.com"
    try:
        _owner_invite(H, oid, a)
        rb = _owner_invite(H, oid, b).json()
        pend = list(db.secure_invitations.find({"organization_id": oid, "status": "pending"}))
        assert len(pend) == 1 and pend[0]["email"] == b
        # org activated by some other path while invite b still pending -> accept must 410 and not create a user
        db.organizations.update_one({"id": oid}, {"$set": {"onboarding_status": "active", "portal_access": "activated"}})
        r = _accept(_tok_from(rb["link"]), b)
        assert r.status_code == 410, r.text
        assert db.users.count_documents({"organization_id": oid}) == 0
        # master-admin cannot create a new owner invite now either
        assert _owner_invite(H, oid, f"tst.oc.{uuid.uuid4().hex[:6]}@example.com").status_code == 409
    finally:
        _purge(db, oid)


# Master admin revoke/reissue act only on owner_activation invites (staff invite -> 404)
def test_master_revoke_reissue_ignore_staff_invites(H):
    db = _db()
    oid, sa, _ = _two_site_org(db)
    _, _, ho = _user(db, oid, "owner")
    try:
        rs = requests.post(INV, headers=ho, json={"email": f"tst.s.{oid[-5:]}@example.com", "role": "staff"}).json()
        iid = rs["invitation"]["id"]
        base = f"{BASE}/api/master-admin/customer-activation/invitations/{iid}"
        assert requests.post(f"{base}/reissue", headers=H, timeout=30).status_code == 404
        assert requests.post(f"{base}/revoke", headers=H, timeout=30).status_code == 404
        assert db.secure_invitations.find_one({"id": iid})["status"] == "pending"
    finally:
        _purge(db, oid)


# Manager scope: cancel other-site staff invite / resend manager invite -> 403; own-site allowed; default sites
def test_manager_invite_scope_and_default_sites(H):
    db = _db()
    oid, sa, sb = _two_site_org(db)
    _, _, ho = _user(db, oid, "owner")
    _, _, hm = _user(db, oid, "manager", allowed_site_ids=[sa])
    try:
        rm = requests.post(INV, headers=ho, json={"email": f"tst.m.{oid[-5:]}@example.com", "role": "manager", "allowed_site_ids": [sa]}).json()
        rsb = requests.post(INV, headers=ho, json={"email": f"tst.sb.{oid[-5:]}@example.com", "role": "staff", "allowed_site_ids": [sb]}).json()
        rnone = requests.post(INV, headers=ho, json={"email": f"tst.sn.{oid[-5:]}@example.com", "role": "staff"}).json()
        res = {
            "cancel_site_b_staff": requests.delete(f"{INV}/{rsb['invitation']['id']}", headers=hm).status_code,
            "resend_manager_inv": requests.post(f"{INV}/{rm['invitation']['id']}/resend", headers=hm).status_code,
            "cancel_unscoped_staff": requests.delete(f"{INV}/{rnone['invitation']['id']}", headers=hm).status_code,
            "invite_site_b": requests.post(INV, headers=hm, json={"email": f"tst.x.{oid[-5:]}@example.com", "role": "staff", "allowed_site_ids": [sb]}).status_code,
            "invite_manager_role": requests.post(INV, headers=hm, json={"email": f"tst.y.{oid[-5:]}@example.com", "role": "manager"}).status_code,
        }
        assert res == {"cancel_site_b_staff": 403, "resend_manager_inv": 403, "cancel_unscoped_staff": 403,
                       "invite_site_b": 403, "invite_manager_role": 400}, res
        # default: no allowed_site_ids -> manager's own sites
        rd = requests.post(INV, headers=hm, json={"email": f"tst.d.{oid[-5:]}@example.com", "role": "staff"})
        assert rd.status_code == 200, rd.text
        assert rd.json()["invitation"]["allowed_site_ids"] == [sa] and "link" in rd.json()
        did = rd.json()["invitation"]["id"]
        # own-site resend and cancel work
        rr = requests.post(f"{INV}/{did}/resend", headers=hm)
        assert rr.status_code == 200 and rr.json()["invitation"]["allowed_site_ids"] == [sa]
        assert requests.delete(f"{INV}/{rr.json()['invitation']['id']}", headers=hm).status_code == 200
        assert db.secure_invitations.find_one({"id": rr.json()["invitation"]["id"]})["status"] == "revoked"
    finally:
        _purge(db, oid)


# Lockout counter is atomic: 8 concurrent wrong-email attempts -> invite revoked, count == 8
def test_wrong_email_lockout_atomic(H):
    db = _db()
    oid = _mk_org(db)
    em = f"tst.at.{uuid.uuid4().hex[:6]}@example.com"
    try:
        tok = _tok_from(_owner_invite(H, oid, em).json()["link"])
        with ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(lambda _: _accept(tok, "wrong@example.com").status_code, range(8)))
        assert all(c in (400, 410) for c in codes), codes
        inv = db.secure_invitations.find_one({"organization_id": oid})
        assert inv["status"] == "revoked" and inv["failed_attempts"] >= 5
        assert codes.count(400) == inv["failed_attempts"], (codes, inv["failed_attempts"])
        assert _accept(tok, em).status_code == 410
    finally:
        _purge(db, oid)


# Device sessions see handover notes for their site + site-less notes, never another site's
def test_device_handover_site_scope(H):
    db = _db()
    oid, sa, sb = _two_site_org(db, account_type="pulse_pro")
    _, _, ho = _user(db, oid, "owner")
    now = datetime.now(timezone.utc).isoformat()
    db.gym_floor_handover.insert_many([
        {"id": f"{oid}-h{i}", "organization_id": oid, "site_id": s, "staff_name": "x", "notes": f"note-{i}",
         "created_at": now, "flagged": False} for i, s in enumerate([sa, sb, None])])
    ua = f"tst-h-{oid[-6:]}"
    g = f"{BASE}/api/gym-floor"
    try:
        assert requests.post(f"{g}/setup", headers=ho, json={"username": ua, "password": "secret12", "site_id": sa}).status_code == 200
        ta = {"X-Gym-Floor-Token": requests.post(f"{g}/login", json={"username": ua, "password": "secret12"}).json()["token"]}
        notes = sorted(e["notes"] for e in requests.get(f"{g}/handover", headers=ta).json()["entries"])
        assert notes == ["note-0", "note-2"], notes
        owner_notes = sorted(e["notes"] for e in requests.get(f"{g}/handover", headers=ho).json()["entries"])
        assert owner_notes == ["note-0", "note-1", "note-2"]
    finally:
        db.gym_floor_handover.delete_many({"organization_id": oid})
        _purge(db, oid)


# Pro-trial reminder: claim released (and sent marker cleared) when the send fails, so the next sweep retries
def test_pro_trial_reminder_claim_released_on_failure():
    from utils import pro_trial_reminders as P
    from utils import email_claims
    from motor.motor_asyncio import AsyncIOMotorClient
    import utils.database as D
    db = _db()
    ends = datetime.now(timezone.utc) + timedelta(hours=12)
    oid = _mk_org(db, pro_trial_used_at=datetime.now(timezone.utc).isoformat(), pro_trial_reminder_sent_at=None,
                  module_trials={"operations": {"expires_at": ends.isoformat()}})
    key = email_claims.trial_ending_key(oid, ends.isoformat())
    called = []

    async def run():
        import os
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        adb = client[os.environ["DB_NAME"]]
        P.db, email_claims.db = adb, adb
        orig = P.send_trial_ending_email

        async def fail(org, *a, **k):
            if org["id"] == oid:
                called.append(org["id"])
            return 0
        P.send_trial_ending_email = fail
        try:
            await P.sweep_trial_reminders()
        finally:
            P.send_trial_ending_email = orig
            P.db = email_claims.db = D.db
            client.close()
    try:
        asyncio.run(run())
        assert called == [oid]
        assert db.email_send_claims.find_one({"key": key}) is None
        assert db.organizations.find_one({"id": oid}).get("pro_trial_reminder_sent_at") is None
    finally:
        db.email_send_claims.delete_many({"key": key})
        _purge(db, oid)
