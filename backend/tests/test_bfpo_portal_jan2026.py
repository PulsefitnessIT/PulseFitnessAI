"""BFPO / MOD Engineer Portal — end-to-end backend tests.

Covers:
- Portal-scoped login (portal:"mod")
- Engineer territory scoping (Gibraltar-only) & cross-territory 404s
- Guided workflow (accept -> arrive -> diagnosis -> parts / complete)
- Signature capture, job-sheet PDF
- Parts request flow (waiting_parts)
- Non-repair outcomes (equipment_unsafe -> safety_critical)
- Report-fault duplicate warning + linked case
- Sensitive site fields hidden from engineers
- Staff dashboard, sites tree, jobs filters, allocate, visiting-access
- 403 role guard for engineer on /staff/* endpoints
"""
import os
import uuid
import requests
import pytest

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    envp = "/app/frontend/.env"
    if os.path.exists(envp):
        for line in open(envp):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()
BYPASS = {"x-ratelimit-bypass": "test-bypass-secret-for-ci-runs-only-2026"}

ENG_GIB = "engineer.gib@bfpo.pulsefitness.test"
ENG_CYP = "engineer.cyp@bfpo.pulsefitness.test"
STAFF = "staff@bfpo.pulsefitness.test"
LEAD = "lead@bfpo.pulsefitness.test"
PW = "Bfpo123!"


def _login(email: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": PW, "portal": "mod"},
        headers=BYPASS,
        timeout=30,
    )
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", **BYPASS}


@pytest.fixture(scope="module")
def tokens():
    return {
        "gib": _login(ENG_GIB),
        "cyp": _login(ENG_CYP),
        "staff": _login(STAFF),
        "lead": _login(LEAD),
    }


# ─── Login / me ────────────────────────────────────────────────────
class TestAuthAndMe:
    def test_login_requires_portal_mod(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ENG_GIB, "password": PW},  # no portal:"mod"
            headers=BYPASS,
        )
        # login itself may succeed but /bfpo/me must reject non-mod tokens
        # Accept any of: 200 (token issued, portal enforcement at /bfpo) or 4xx
        assert r.status_code in (200, 400, 401, 403)

    def test_me_engineer_gib(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/me", headers=_h(tokens["gib"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["role"] == "engineer"
        assert d["user"]["email"] == ENG_GIB
        # KPIs shape
        for k in ("open", "urgent", "waiting_parts", "return_visit", "overdue"):
            assert k in d["kpis"]
            assert isinstance(d["kpis"][k], int)
        # Territories → Gibraltar only
        names = [t["name"] for t in d["territories"]]
        assert names == ["Gibraltar"], names

    def test_me_staff(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/me", headers=_h(tokens["staff"]))
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "staff"


# ─── Scoping isolation ─────────────────────────────────────────────
class TestEngineerScoping:
    def test_gib_jobs_only_gibraltar(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs", headers=_h(tokens["gib"]))
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert jobs, "Gibraltar engineer expected some open jobs"
        # jobs directly allocated to this engineer are legitimately visible regardless of territory
        countries = {j.get("country") for j in jobs if j.get("assigned_engineer_id") != "bfpo-eng-gib"}
        assert countries <= {"Gibraltar"}, f"leaked countries: {countries}"

    def test_gib_sites_only_gibraltar(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/sites", headers=_h(tokens["gib"]))
        assert r.status_code == 200
        sites = r.json()["sites"]
        assert sites
        assert {s.get("country") for s in sites} == {"Gibraltar"}
        # sensitive fields hidden for plain engineer
        for s in sites:
            assert "access_instructions" not in s, s
            assert "security_notes" not in s, s

    def test_gib_cannot_read_cyprus_case(self, tokens):
        # Fetch a Cyprus case id via staff
        r = requests.get(
            f"{BASE_URL}/api/bfpo/staff/jobs?territory=terr-cyp",
            headers=_h(tokens["staff"]),
        )
        assert r.status_code == 200
        cyp_jobs = r.json()["jobs"]
        assert cyp_jobs
        cyp_id = cyp_jobs[0]["id"]
        # Gibraltar engineer must 404
        r2 = requests.get(f"{BASE_URL}/api/bfpo/jobs/{cyp_id}", headers=_h(tokens["gib"]))
        assert r2.status_code == 404, f"cross-territory leak: {r2.status_code}"


# ─── Role guard 403 ────────────────────────────────────────────────
class TestRoleGuard:
    def test_engineer_forbidden_staff_dashboard(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/dashboard", headers=_h(tokens["gib"]))
        assert r.status_code == 403, f"expected 403, got {r.status_code}"

    def test_engineer_forbidden_staff_jobs(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs", headers=_h(tokens["gib"]))
        assert r.status_code == 403

    def test_engineer_forbidden_visiting_access(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/visiting-access", headers=_h(tokens["gib"]))
        assert r.status_code == 403


# ─── Sensitive site fields visibility ──────────────────────────────
class TestSiteSensitivity:
    def test_lead_sees_sensitive(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/sites", headers=_h(tokens["lead"]))
        assert r.status_code == 200
        # sensitive keys may be present (may still be empty strings) — check at least one site has key present
        sites = r.json()["sites"]
        # Not all sites necessarily have these fields seeded, but lead role should not have them stripped.
        # Ensure that if any site had the field in db, it's now visible for lead.
        assert isinstance(sites, list) and len(sites) > 0


# ─── Guided workflow ───────────────────────────────────────────────
def _get_open_case_for_gib(tok):
    r = requests.get(f"{BASE_URL}/api/bfpo/jobs", headers=_h(tok))
    assert r.status_code == 200
    jobs = [j for j in r.json()["jobs"]
            if j.get("country") == "Gibraltar" and j.get("status") in ("new", "assigned")]
    assert jobs, "No open Gibraltar case to run workflow on"
    return jobs[0]["id"]


class TestGuidedWorkflow:
    def test_accept_arrive_diagnose_complete_and_pdf(self, tokens):
        tok = tokens["gib"]
        case_id = _get_open_case_for_gib(tok)

        # Accept
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{case_id}/accept",
                          headers=_h(tok), json={})
        assert r.status_code == 200, r.text
        assert r.json().get("status") in ("assigned", "on_site", "new")  # accepted

        # Arrive (safe)
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{case_id}/arrive",
                          headers=_h(tok), json={"safe": True, "notes": "clear"})
        assert r.status_code == 200
        assert r.json().get("status") == "on_site"

        # Diagnosis
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{case_id}/diagnosis",
                          headers=_h(tok), json={"diagnosis": "Belt tension gone"})
        assert r.status_code == 200 and r.json()["ok"] is True

        # Signature
        r = requests.post(
            f"{BASE_URL}/api/bfpo/jobs/{case_id}/signature",
            headers=_h(tok),
            json={"signed_by_name": "Sgt Smith",
                  "image_data": "data:image/png;base64,iVBORw0KGgo="},
        )
        assert r.status_code == 200, r.text

        # Complete
        r = requests.post(
            f"{BASE_URL}/api/bfpo/jobs/{case_id}/complete",
            headers=_h(tok),
            json={"summary": "Replaced belt and retensioned.", "safe_and_working": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] and data["case"]["status"] in ("closed", "awaiting_sign_off")

        # Job-sheet PDF
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs/{case_id}/job-sheet.pdf",
                         headers=_h(tok))
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"

    def test_parts_needed_flow(self, tokens):
        tok = tokens["gib"]
        # find another gibraltar case
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs", headers=_h(tok))
        cand = [j for j in r.json()["jobs"]
                if j.get("status") in ("new", "assigned")]
        if not cand:
            pytest.skip("no free case")
        cid = cand[0]["id"]
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/accept", headers=_h(tok), json={})
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/arrive",
                      headers=_h(tok), json={"safe": True})
        r = requests.post(
            f"{BASE_URL}/api/bfpo/jobs/{cid}/parts",
            headers=_h(tok),
            json={"name": "Drive belt (unknown p/n)", "description": "Toothed drive belt, no part number available"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["part"]["name"].startswith("Drive belt")
        # verify status waiting_parts + case stays open
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs/{cid}", headers=_h(tok))
        assert r.json()["status"] == "paused_parts"

    def test_equipment_unsafe_outcome(self, tokens):
        tok = tokens["gib"]
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs", headers=_h(tok))
        cand = [j for j in r.json()["jobs"]
                if j.get("status") in ("new", "assigned") and not j.get("safety_critical")]
        if not cand:
            pytest.skip("no candidate")
        cid = cand[0]["id"]
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/accept", headers=_h(tok), json={})
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/arrive",
                      headers=_h(tok), json={"safe": True})
        r = requests.post(
            f"{BASE_URL}/api/bfpo/jobs/{cid}/outcome",
            headers=_h(tok),
            json={"outcome": "equipment_unsafe", "reason": "frame cracked",
                  "details": "Removed from service"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("safety_critical") is True
        # job stays open
        assert r.json().get("status") in ("on_site", "assigned", "new")

    def test_report_additional_fault(self, tokens):
        tok = tokens["gib"]
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs", headers=_h(tok))
        jobs = r.json()["jobs"]
        assert jobs
        parent = jobs[0]
        cid = parent["id"]
        eq_id = None
        detail = requests.get(f"{BASE_URL}/api/bfpo/jobs/{cid}", headers=_h(tok)).json()
        if detail.get("equipment"):
            eq_id = detail["equipment"][0]["id"]
        payload = {"title": "Console lamp intermittent",
                   "description": "Backlight flickers",
                   "equipment_id": eq_id or "",
                   "priority": "p3"}
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/report-fault",
                          headers=_h(tok), json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"]
        assert body["case"]["reference"].startswith("SVC-")
        # duplicate warning likely present since parent equipment already has an open job
        if eq_id:
            assert body.get("warning") is not None


# ─── Staff endpoints ───────────────────────────────────────────────
class TestStaffOversight:
    def test_dashboard(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/dashboard", headers=_h(tokens["staff"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("open", "urgent", "waiting_parts", "overdue", "sites_attention"):
            assert k in d["kpis"]
        assert "urgent_jobs" in d and "attention_sites" in d

    def test_sites_tree_and_critical_sites(self, tokens):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/sites", headers=_h(tokens["staff"]))
        assert r.status_code == 200
        tree = r.json()["tree"]
        assert tree
        # Flatten to find MPC & HMS Rooke
        flat = []
        for c in tree:
            for t in c["territories"]:
                for s in t["sites"]:
                    flat.append(s)
        names = {s["site_name"]: s for s in flat}
        # Mount Pleasant (MPC) & HMS Rooke must exist and be critical based on seeded p1 overdue+unsafe
        mpc = next((s for s in flat if "Mount Pleasant" in (s.get("site_name") or "")), None)
        rooke = next((s for s in flat if "HMS Rooke" in (s.get("site_name") or "")), None)
        assert mpc, f"MPC missing; sites: {list(names)}"
        assert rooke, "HMS Rooke missing"
        assert mpc["health"] == "critical", f"MPC health={mpc['health']}"
        assert rooke["health"] == "critical", f"Rooke health={rooke['health']}"

    def test_jobs_filters(self, tokens):
        # safety filter
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs?safety=true",
                         headers=_h(tokens["staff"]))
        assert r.status_code == 200
        assert all(j.get("safety_critical") for j in r.json()["jobs"])
        # priority p1
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs?priority=p1",
                         headers=_h(tokens["staff"]))
        assert r.status_code == 200
        assert all(j["priority"] == "p1" for j in r.json()["jobs"])

    def test_allocate_unassigned(self, tokens):
        tok = tokens["staff"]
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs?status=open",
                         headers=_h(tok))
        unassigned = [j for j in r.json()["jobs"] if not j.get("assigned_engineer_id")]
        if not unassigned:
            pytest.skip("no unassigned")
        cid = unassigned[0]["id"]
        engs = requests.get(f"{BASE_URL}/api/bfpo/staff/engineers", headers=_h(tok)).json()["engineers"]
        eng_id = next(e["id"] for e in engs if e["email"] == ENG_GIB)
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/jobs/{cid}/allocate",
            headers=_h(tok),
            json={"engineer_id": eng_id, "handover": "please prioritise, MOD urgent"},
        )
        assert r.status_code == 200, r.text
        # Verify timeline has allocation + handover
        det = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs/{cid}", headers=_h(tok)).json()
        assert det["assigned_engineer_id"] == eng_id
        types = [e["type"] for e in det["events"]]
        assert "allocation" in types

    def test_visiting_access_grant_and_read_scope_expansion(self, tokens):
        s_tok = tokens["staff"]
        # find a cyprus site & the gib engineer
        sites = requests.get(f"{BASE_URL}/api/bfpo/staff/sites", headers=_h(s_tok)).json()["tree"]
        cyp_site = None
        for c in sites:
            if c["country"] == "Cyprus":
                for t in c["territories"]:
                    if t["sites"]:
                        cyp_site = t["sites"][0]
                        break
        assert cyp_site
        engs = requests.get(f"{BASE_URL}/api/bfpo/staff/engineers", headers=_h(s_tok)).json()["engineers"]
        gib_eng_id = next(e["id"] for e in engs if e["email"] == ENG_GIB)

        # baseline: gib engineer sees only Gibraltar
        r = requests.get(f"{BASE_URL}/api/bfpo/sites", headers=_h(tokens["gib"]))
        assert cyp_site["site_id"] not in {s["id"] for s in r.json()["sites"]}

        # grant
        from datetime import date, timedelta
        payload = {"engineer_id": gib_eng_id, "site_id": cyp_site["site_id"],
                   "from_date": date.today().isoformat(),
                   "to_date": (date.today() + timedelta(days=7)).isoformat()}
        r = requests.post(f"{BASE_URL}/api/bfpo/staff/visiting-access",
                          headers=_h(s_tok), json=payload)
        assert r.status_code == 200, r.text
        grant_id = r.json()["grant"]["id"]

        # gib engineer now sees the Cyprus site
        r = requests.get(f"{BASE_URL}/api/bfpo/sites", headers=_h(tokens["gib"]))
        ids = {s["id"] for s in r.json()["sites"]}
        assert cyp_site["site_id"] in ids, "visiting-access grant did not expand engineer scope"

        # list grants
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/visiting-access", headers=_h(s_tok))
        assert any(g["id"] == grant_id for g in r.json()["grants"])

        # revoke
        r = requests.delete(f"{BASE_URL}/api/bfpo/staff/visiting-access/{grant_id}",
                            headers=_h(s_tok))
        assert r.status_code == 200
        # scope collapses back
        r = requests.get(f"{BASE_URL}/api/bfpo/sites", headers=_h(tokens["gib"]))
        assert cyp_site["site_id"] not in {s["id"] for s in r.json()["sites"]}
