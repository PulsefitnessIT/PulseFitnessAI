"""Iter323: MOD Operations integrity sprint — engineer coverage (territories vs specific sites, mod_site orgs,
validation/dedupe), Master Admin parity, engineer visibility, allocation outside coverage (override reason),
deactivation with per-job decisions + access revocation, resend-invite guard, MOD quote recall-then-delete with
snapshot, follow-up email wording approval (dry run)."""
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url  # noqa: E402
from utils.auth import create_token, hash_password  # noqa: E402

API = f"{_test_backend_url().rstrip('/')}/api"
B = f"{API}/bfpo"
MQ = f"{API}/mod-ops/quotes"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
RUN = uuid.uuid4().hex[:8]
MOD_SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"  # MOD Test Site (organizations account_type mod_site)
PULSE_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
INHOUSE = "pulse-inhouse-mod"
ENG: dict = {}     # key -> {"id", "email", "pw"}
CASES: list = []
GROUPS: list = []
OWNER_ID = f"TEST_owner323_{RUN}"
OWNER_EMAIL = f"test_owner323_{RUN}@example.test"
PW = "TestOwner123!"


def _sess(token):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    return requests.post(f"{API}/auth/login", json=body, timeout=30)


def _login_sess(email, pw, portal=None):
    r = _login(email, pw, portal)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    return _sess(r.json()["token"])


def _minted(uid, mfa=False):
    return _sess(create_token(uid, mfa_verified=mfa))


@pytest.fixture(scope="module", autouse=True)
def setup_cleanup():
    DB.users.insert_one({"id": OWNER_ID, "email": OWNER_EMAIL, "full_name": "TEST MOD Owner 323", "organization_id": PULSE_ORG,
                         "role": "owner", "account_type": "pulse_pro", "module_overrides": {"mod_operations": True},
                         "mod_quote_role": "pricing_admin_manager", "password": hash_password(PW),
                         "must_change_password": False, "created_at": datetime.now(timezone.utc).isoformat()})
    fu_orig = DB.mod_quote_settings.find_one({"id": "followup_emails"})
    yield
    DB.users.delete_one({"id": OWNER_ID})
    for e in ENG.values():
        DB.users.delete_one({"id": e["id"]})
        DB.svc_engineers.delete_many({"id": e["id"]})
        DB.bfpo_invites.delete_many({"user_id": e["id"]})
    for cid in CASES:
        DB.svc_cases.delete_one({"id": cid})
        for c in ("svc_case_events", "svc_events", "case_events"):
            DB[c].delete_many({"case_id": cid})
    for gid in GROUPS:
        DB.crm2_quotes.delete_many({"mod_group_id": gid})
        for c in ("mod_quote_events", "mod_quote_authorisations", "mod_quote_followups", "mod_quote_handovers"):
            DB[c].delete_many({"group_id": gid})
        DB.crm2_activities.delete_many({"mod_group_id": gid})
        DB.crm2_opportunities.delete_many({"mod_group_id": gid})
        DB.mod_quote_groups.delete_one({"id": gid})
        DB.mod_quote_deletions.delete_many({"group_id": gid})
    # restore follow-up wording exactly as before
    if fu_orig:
        fu_orig.pop("_id", None)
        DB.mod_quote_settings.replace_one({"id": "followup_emails"}, fu_orig, upsert=True)
    else:
        DB.mod_quote_settings.delete_one({"id": "followup_emails"})
    DB.mod_quote_settings_audit.delete_many({"by": {"$in": [OWNER_ID, (DB.users.find_one({"email": "modsales.manager@pulsedemo.test"}) or {}).get("id")]},
                                             "at": {"$gte": START}})


START = datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def mgr():
    return _login_sess("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login_sess("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def owner():
    return _login_sess(OWNER_EMAIL, PW)


@pytest.fixture(scope="module")
def admin():
    a = DB.users.find_one({"email": "admin@pulsefitness.com"}, {"id": 1})
    return _minted(a["id"], mfa=True)  # MFA-verified token minted for API tests (admin not enrolled in preview)


def _create_eng(mgr, key, terr=None, sites=None, mode="temp"):
    email = f"test_eng323_{key}_{RUN}@example.test"
    body = {"full_name": f"TEST_Eng {key} {RUN}", "email": email, "bfpo_role": "engineer", "password_mode": mode,
            "temp_password": "TestEng123!" if mode == "temp" else None,
            "bfpo_territory_ids": terr or [], "bfpo_site_ids": sites or []}
    r = mgr.post(f"{B}/staff/engineers", json=body)
    assert r.status_code == 200, r.text
    m = r.json()["member"]
    ENG[key] = {"id": m["id"], "email": email, "pw": "TestEng123!"}
    return m


def _team(mgr):
    return {m["id"]: m for m in mgr.get(f"{B}/staff/team").json()["members"]}


def _case(terr, site, status="new", assigned=None):
    cid = f"TEST_case323_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    DB.svc_cases.insert_one({"id": cid, "organization_id": "bfpo-mod-org", "bfpo": True, "reference": f"TEST-{cid[-6:]}",
                             "title": "TEST_ coverage job", "status": status, "priority": "p3", "territory_id": terr,
                             "site_id": site, "site_name": "TEST site", "assigned_engineer_id": assigned,
                             "created_at": now, "updated_at": now})
    CASES.append(cid)
    return cid


# ── Sites endpoint by role ──
class TestSites:
    def test_staff_sees_bfpo_and_mod_sites(self, mgr):
        r = mgr.get(f"{B}/sites")
        assert r.status_code == 200, r.text
        kinds = [s["kind"] for s in r.json()["sites"]]
        assert kinds.count("bfpo_site") == 7, kinds.count("bfpo_site")
        assert kinds.count("mod_site") >= 74

    def test_lead_sees_only_bfpo(self):
        r = _minted("bfpo-lead").get(f"{B}/sites")
        assert r.status_code == 200
        assert {s["kind"] for s in r.json()["sites"]} == {"bfpo_site"}


# ── Coverage scenarios ──
class TestCoverage:
    def test_create_scenarios(self, mgr):
        m = _create_eng(mgr, "sites", sites=[MOD_SITE, MOD_SITE, " "])
        assert m["bfpo_site_ids"] == [MOD_SITE] and m["bfpo_territory_ids"] == []
        _create_eng(mgr, "terr", terr=["terr-cyp", "terr-cyp"])
        _create_eng(mgr, "both", terr=["terr-gib"], sites=["site-falk-1"])
        _create_eng(mgr, "none")
        t = _team(mgr)
        c = t[ENG["sites"]["id"]]["coverage"]
        assert c["status"] == "sites" and c["territories"] == [] and c["sites"][0]["kind"] == "mod_site" and not c["sites"][0]["missing"]
        c = t[ENG["terr"]["id"]]["coverage"]
        assert c["status"] == "territory" and [x["id"] for x in c["territories"]] == ["terr-cyp"] and c["countries"] == ["Cyprus"]
        c = t[ENG["both"]["id"]]["coverage"]
        assert c["status"] == "territory_and_sites" and set(c["countries"]) == {"Gibraltar", "Falkland Islands"}
        c = t[ENG["none"]["id"]]["coverage"]
        assert c["status"] == "none" and c["issues"]

    def test_invalid_rejected_nothing_saved(self, mgr):
        email = f"test_eng323_bad_{RUN}@example.test"
        r = mgr.post(f"{B}/staff/engineers", json={"full_name": "TEST_bad", "email": email, "password_mode": "temp",
                                                     "temp_password": "TestEng123!", "bfpo_site_ids": ["nope-site"]})
        assert r.status_code == 422, r.text
        assert DB.users.count_documents({"email": email}) == 0
        r = mgr.patch(f"{B}/staff/engineers/{ENG['none']['id']}", json={"bfpo_territory_ids": ["terr-nope"]})
        assert r.status_code == 422
        assert DB.users.find_one({"id": ENG["none"]["id"]})["bfpo_territory_ids"] == []

    def test_missing_reference_flagged(self, mgr):
        DB.users.update_one({"id": ENG["terr"]["id"]}, {"$push": {"bfpo_territory_ids": "terr-deleted", "bfpo_site_ids": "site-deleted"}})
        c = _team(mgr)[ENG["terr"]["id"]]["coverage"]
        assert any(x["missing"] for x in c["territories"]) and any(x["missing"] for x in c["sites"])
        assert any("territory" in i for i in c["issues"]) and any("site" in i for i in c["issues"])
        DB.users.update_one({"id": ENG["terr"]["id"]}, {"$set": {"bfpo_territory_ids": ["terr-cyp"], "bfpo_site_ids": []}})


# ── Master Admin parity ──
class TestMasterAdminParity:
    def test_ma_patch_shows_in_team(self, mgr, admin):
        eid = ENG["none"]["id"]
        url = f"{API}/master-admin/mod-estate/external-providers/{INHOUSE}/engineers/{eid}"
        r = admin.patch(url, json={"territory_ids": ["terr-ken"], "site_ids": [MOD_SITE, "site-gib-1", MOD_SITE]})
        assert r.status_code == 200, r.text
        c = _team(mgr)[eid]["coverage"]
        assert [t["id"] for t in c["territories"]] == ["terr-ken"] and [s["id"] for s in c["sites"]] == [MOD_SITE, "site-gib-1"]
        r = admin.patch(url, json={"site_ids": ["nope"]})
        assert r.status_code == 422
        assert DB.users.find_one({"id": eid})["bfpo_site_ids"] == [MOD_SITE, "site-gib-1"]

    def test_staff_patch_shows_in_ma(self, mgr, admin):
        eid = ENG["none"]["id"]
        r = mgr.patch(f"{B}/staff/engineers/{eid}", json={"bfpo_territory_ids": [], "bfpo_site_ids": ["site-cyp-2"]})
        assert r.status_code == 200
        r = admin.get(f"{API}/master-admin/mod-estate/external-providers")
        assert r.status_code == 200, r.text
        found = None
        for p in r.json().get("providers") or r.json().get("items") or []:
            for e in p.get("engineers", []):
                if e.get("id") == eid:
                    found = e
        assert found, "engineer not in MA list"
        assert found["territory_ids"] == [] and found["site_ids"] == ["site-cyp-2"]


# ── Visibility, allocation, coverage endpoint ──
class TestAllocation:
    def test_engineer_sites(self):
        ids = [s["id"] for s in _minted(ENG["sites"]["id"]).get(f"{B}/sites").json()["sites"]]
        assert ids == [MOD_SITE]
        ids = {s["id"] for s in _minted(ENG["both"]["id"]).get(f"{B}/sites").json()["sites"]}
        assert ids == {"site-gib-1", "site-gib-2", "site-falk-1"}

    def test_outside_coverage(self, mgr):
        cid = _case("terr-falk", "site-falk-1")
        et = _minted(ENG["terr"]["id"])
        assert cid not in [j["id"] for j in et.get(f"{B}/jobs").json()["jobs"]]
        assert et.get(f"{B}/jobs/{cid}").status_code == 404
        assert cid in [j["id"] for j in _minted(ENG["both"]["id"]).get(f"{B}/jobs").json()["jobs"]]
        cov = mgr.get(f"{B}/staff/jobs/{cid}/coverage").json()["engineers"]
        assert cov[ENG["terr"]["id"]]["covers"] is False and cov[ENG["both"]["id"]]["covers"] is True
        r = mgr.post(f"{B}/staff/jobs/{cid}/allocate", json={"engineer_id": ENG["terr"]["id"]})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "outside_coverage", r.text
        r = mgr.post(f"{B}/staff/jobs/{cid}/allocate", json={"engineer_id": ENG["terr"]["id"], "override_reason": "TEST_cover leave"})
        assert r.status_code == 200, r.text
        assert cid in [j["id"] for j in et.get(f"{B}/jobs").json()["jobs"]]
        tl = mgr.get(f"{B}/staff/jobs/{cid}").json()
        assert "TEST_cover leave" in str(tl), "override reason not in job timeline"


# ── Deactivation, access, resend invite ──
class TestDeactivation:
    def test_open_jobs_and_decisions(self, mgr):
        eid = ENG["terr"]["id"]
        c2 = _case("terr-cyp", "site-cyp-1", status="assigned", assigned=eid)
        c3 = _case("terr-cyp", "site-cyp-1", status="assigned", assigned=eid)
        c1 = CASES[0]
        tok = _login(ENG["terr"]["email"], ENG["terr"]["pw"], "mod")
        assert tok.status_code == 200 and "token" in tok.json(), tok.text
        ENG["terr"]["token"] = tok.json()["token"]
        oj = mgr.get(f"{B}/staff/engineers/{eid}/open-jobs").json()["jobs"]
        assert {c1, c2, c3} <= {j["id"] for j in oj}
        r = mgr.post(f"{B}/staff/engineers/{eid}/status", json={"active": False})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "open_jobs" and len(r.json()["detail"]["jobs"]) == 3
        bad = [{"case_id": c1, "action": "reassign", "engineer_id": ENG["both"]["id"], "reason": ""},
               {"case_id": c2, "action": "unassign", "reason": "x"}, {"case_id": c3, "action": "keep", "reason": "x"}]
        assert mgr.post(f"{B}/staff/engineers/{eid}/status", json={"active": False, "job_decisions": bad}).status_code == 422
        assert DB.users.find_one({"id": eid})["is_active"] is True
        dec = [{"case_id": c1, "action": "reassign", "engineer_id": ENG["both"]["id"], "reason": "TEST_reassign"},
               {"case_id": c2, "action": "unassign", "reason": "TEST_queue"},
               {"case_id": c3, "action": "keep", "reason": "TEST_keep"}]
        r = mgr.post(f"{B}/staff/engineers/{eid}/status", json={"active": False, "job_decisions": dec})
        assert r.status_code == 200, r.text
        assert DB.svc_cases.find_one({"id": c1})["assigned_engineer_id"] == ENG["both"]["id"]
        assert DB.svc_cases.find_one({"id": c2})["assigned_engineer_id"] is None
        held = DB.svc_cases.find_one({"id": c3})
        assert held["management_hold"] is True and held["assigned_engineer_id"] is None and held["held_from_engineer_id"] == eid
        assert "TEST_queue" in str(mgr.get(f"{B}/staff/jobs/{c2}").json())

    def test_deactivated_access(self, mgr):
        eid = ENG["terr"]["id"]
        assert _sess(ENG["terr"]["token"]).get(f"{B}/me").status_code in (401, 403)
        r = _login(ENG["terr"]["email"], ENG["terr"]["pw"], "mod")
        assert r.status_code == 403 and "disabled" in r.text.lower(), r.text
        r = mgr.post(f"{B}/staff/jobs/{CASES[0]}/allocate", json={"engineer_id": eid, "override_reason": "x"})
        assert r.status_code == 409
        r = mgr.post(f"{B}/staff/engineers/{eid}/resend-invite")
        assert r.status_code == 409
        assert DB.users.find_one({"id": eid})["is_active"] is False
        assert _team(mgr)[eid]["coverage"]["issues"][-1].startswith("Account deactivated")

    def test_reactivate(self, mgr):
        eid = ENG["terr"]["id"]
        assert mgr.post(f"{B}/staff/engineers/{eid}/status", json={"active": True}).status_code == 200
        r = _login(ENG["terr"]["email"], ENG["terr"]["pw"], "mod")
        assert r.status_code == 200 and "token" in r.json(), r.text
        assert _sess(r.json()["token"]).get(f"{B}/me").status_code == 200

    def test_pending_invite_cannot_reactivate(self, mgr):
        _create_eng(mgr, "inv", terr=["terr-gib"], mode="invite")
        eid = ENG["inv"]["id"]
        assert mgr.post(f"{B}/staff/engineers/{eid}/status", json={"active": False}).status_code == 200
        # Deactivation revokes pending invites; a stale link is also refused if replayed.
        assert DB.bfpo_invites.find_one({"user_id": eid, "status": {"$ne": "accepted"}}) is None
        DB.bfpo_invites.insert_one({"id": f"TEST_{eid}", "user_id": eid, "email": "x@example.test", "token": f"TEST_tok_{eid}",
                                    "organization_id": "bfpo-mod-org", "status": "pending", "expires_at": "9999-01-01"})
        r = requests.post(f"{B}/invite/TEST_tok_{eid}/accept", json={"password": "TestEng123!"})
        assert r.status_code == 403
        assert requests.get(f"{B}/invite/TEST_tok_{eid}").json()["reason"] == "deactivated"
        assert DB.users.find_one({"id": eid})["is_active"] is False, "old invite link re-activated a deactivated engineer"
        DB.bfpo_invites.delete_many({"user_id": eid})


# ── MOD quotes recall → delete + snapshot ──
CUSTOMER = {"site_id": MOD_SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane"]}
ROWS = [{"row_id": "r1", "rate_card_id": "sor-2", "qty": 1, "coverage": "A", "label": ""}]


def _group(mgr):
    r = mgr.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A"], "idempotency_key": f"TEST_{uuid.uuid4()}"})
    assert r.status_code == 200, r.text
    GROUPS.append(r.json()["id"])
    return r.json()["id"]


class TestQuoteDelete:
    @pytest.mark.parametrize("status", ["published", "customer_review", "authorisation_submitted"])
    def test_issued_needs_recall(self, mgr, owner, status):
        gid = _group(mgr)
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": status, "published_at": START}})
        r = owner.delete(f"{MQ}/groups/{gid}")
        assert r.status_code == 409 and "recall" in r.text.lower()
        assert mgr.post(f"{MQ}/groups/{gid}/withdraw", json={"reason": "TEST_recall"}).status_code == 200
        DB.mod_quote_followups.insert_one({"id": f"TEST_fu_{gid}", "group_id": gid})
        DB.mod_quote_authorisations.insert_one({"id": f"TEST_au_{gid}", "group_id": gid})
        r = owner.delete(f"{MQ}/groups/{gid}")
        assert r.status_code == 200, r.text
        d = DB.mod_quote_deletions.find_one({"group_id": gid})
        snap = d["snapshot"]
        assert d["issued"] is True and snap["group"]["id"] == gid and snap["quotes"] and snap["events"]
        assert snap["authorisations"] and snap["followups"]
        assert DB.mod_quote_groups.count_documents({"id": gid}) == 0

    def test_draft_delete_and_deleted_list(self, mgr, owner):
        gid = _group(mgr)
        assert owner.delete(f"{MQ}/groups/{gid}").status_code == 200
        r = owner.get(f"{MQ}/deleted")
        assert r.status_code == 200 and gid in [x["group_id"] for x in r.json()["deleted"]]
        assert "snapshot" not in r.json()["deleted"][0]
        assert mgr.get(f"{MQ}/deleted").status_code == 403

    @pytest.mark.parametrize("status", ["accepted", "handed_over"])
    def test_accepted_never(self, mgr, owner, status):
        gid = _group(mgr)
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": status}})
        assert owner.delete(f"{MQ}/groups/{gid}").status_code == 409


# ── Follow-up email wording ──
class TestFollowupWording:
    def test_flow(self, mgr, rep, owner):
        r = mgr.get(f"{MQ}/followup-emails")
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d["templates"]) == {"1", "2", "3"} and d["live_switch_on"] is False
        assert d["can_edit"] is True and d["can_approve"] is False
        assert owner.get(f"{MQ}/followup-emails").json()["can_approve"] is True
        tpl = {k: {"subject": v["subject"], "body": v["body"] + "\n\nTEST_edit"} for k, v in d["templates"].items()}
        assert rep.put(f"{MQ}/followup-emails", json={"templates": tpl}).status_code == 403
        r = mgr.put(f"{MQ}/followup-emails", json={"templates": tpl})
        assert r.status_code == 200 and r.json()["approved"] is False
        assert mgr.post(f"{MQ}/followup-emails/approve").status_code == 403
        r = owner.post(f"{MQ}/followup-emails/approve")
        assert r.status_code == 200 and mgr.get(f"{MQ}/followup-emails").json()["approved"] is True
        bad = {**tpl, "2": {"subject": "", "body": "x"}}
        assert mgr.put(f"{MQ}/followup-emails", json={"templates": bad}).status_code == 422
        assert mgr.get(f"{MQ}/followup-emails").json()["approved"] is True
        assert mgr.put(f"{MQ}/followup-emails", json={"templates": tpl}).json()["approved"] is False
        owner.post(f"{MQ}/followup-emails/approve")
        r = mgr.post(f"{MQ}/followups/run")
        assert r.status_code == 200 and r.json()["live_email"] is False, r.text
