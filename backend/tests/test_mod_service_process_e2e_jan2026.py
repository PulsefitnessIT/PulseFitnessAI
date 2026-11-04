# MOD service process end-to-end: MOD fault log -> ESP + Pulse notified -> ESP engineer
# claims & completes in engineer app with customer sign-off -> MOD fault shows engineer
# report -> Pulse close-out email for Sicon. Runs sequentially; shared state in module dict.
import os
import time
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"


def _env(key):
    with open("/app/backend/.env") as f:
        for ln in f:
            if ln.startswith(key + "="):
                return ln.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
ENG_ID = "esp-test-eng-1"
PULSE = "modservice@pulsefitness.com"
SIG_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
           "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
S: dict = {}


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    if not tok:
        pytest.skip(f"no token for {email}: {list(r.json())}")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def mod_h():
    return _login("test@army.mod.test", "ModTest123!", "mod")


@pytest.fixture(scope="module")
def eng_h():
    return _login("esp.test.eng@example.com", "EspTest123!", "mod")


def _events_for(ref, since):
    return list(DB.email_send_events.find(
        {"subject": {"$regex": ref}, "created_at": {"$gte": since}}, {"_id": 0, "payload.html": 0}))


# ── STEP 1: MOD logs fault ──────────────────────────────────────────
def test_step1_mod_logs_fault(mod_h):
    S["t0"] = datetime.now(timezone.utc)
    eq = requests.get(f"{API}/mod/site/equipment", headers=mod_h, timeout=30).json()["equipment"]
    open_eq = {i.get("equipment_id") for i in DB.issues.find(
        {"organization_id": SITE_ID, "status": {"$ne": "resolved"}}, {"equipment_id": 1})}
    cands = [e for e in eq if e["id"] not in open_eq] or eq
    S["equipment"] = cands[0]
    S["equip_status_before"] = cands[0].get("status")
    staff = requests.get(f"{API}/mod/site/staff", headers=mod_h, timeout=30).json()
    staff = staff.get("staff", staff) if isinstance(staff, dict) else staff
    body = {"equipment_id": cands[0]["id"], "fault_type": "not_working",
            "description": "TEST_ process check - start button unresponsive, console will not power up",
            "onset": "today", "usable": "no", "safe_in_service": "yes"}
    if staff:
        body["reporter_staff_id"] = staff[0]["id"]
    r = requests.post(f"{API}/mod/site/faults", json=body, headers=mod_h, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    S["issue_id"], S["ref"] = d["issue_id"], d["ticket_ref"]
    print("ISSUE", d)
    time.sleep(4)
    issue = DB.issues.find_one({"id": S["issue_id"]}, {"_id": 0})
    assert issue and issue.get("bfpo_case_id"), "bfpo_case_id not set"
    S["case_id"] = issue["bfpo_case_id"]
    S["reporter_email"] = issue.get("reporter_email")
    case = DB.svc_cases.find_one({"id": S["case_id"]}, {"_id": 0})
    assert case["organization_id"] == "bfpo-mod-org"
    assert case["site_id"] == SITE_ID
    assert case["mod_issue_id"] == S["issue_id"]
    S["notified"] = issue.get("notified_recipients")
    print("NOTIFIED", S["notified"], "CASE status", case["status"], case.get("assigned_engineer_id"))


def test_step1_emails_attempted_to_provider_and_pulse():
    evs = _events_for(S["ref"], S["t0"])
    tos = {(e.get("to") or "").lower(): e for e in evs}
    print("EMAIL EVENTS", [(e["to"], e["subject"], e["status"], (e.get("payload") or {}).get("from"))
                           for e in evs])
    assert PULSE in tos, "No email attempt to MODService@pulsefitness.com"
    prov = [n["email"].lower() for n in (S["notified"] or []) if n["role"] != "pulse"]
    assert prov, "No external service provider recipient resolved"
    for p in prov:
        assert p in tos, f"No email attempt to provider {p}"
    S["fault_events"] = evs


def test_step1_fault_emails_sender_is_modservice_domain():
    bad = [(e["to"], (e.get("payload") or {}).get("from")) for e in S["fault_events"]
           if "modservice.pulsefitness.com" not in ((e.get("payload") or {}).get("from") or "")]
    assert not bad, f"Fault notification emails not sent from modservice domain: {bad}"


# ── STEP 2: ESP engineer sees + claims ──────────────────────────────
def test_step2_engineer_sees_and_claims(eng_h):
    case = DB.svc_cases.find_one({"id": S["case_id"]}, {"_id": 0})
    dash = requests.get(f"{API}/svc/engineer/dashboard", headers=eng_h, timeout=30).json()
    print("KPIs", dash.get("kpis"))
    if case.get("assigned_engineer_id") and case["assigned_engineer_id"] != ENG_ID:
        S["auto_alloc_other"] = case["assigned_engineer_id"]
        DB.svc_cases.update_one({"id": S["case_id"]}, {"$set": {
            "assigned_engineer_id": ENG_ID, "assigned_engineer_name": "ESP Test Engineer"}})
        print("Reassigned from", case["assigned_engineer_id"])
        return
    if case.get("assigned_engineer_id") == ENG_ID:
        S["auto_alloc_self"] = True
        jobs = requests.get(f"{API}/svc/engineer/jobs", headers=eng_h, timeout=30).json()
        print("auto-allocated to ESP engineer; jobs payload keys", list(jobs)[:5] if isinstance(jobs, dict) else len(jobs))
        return
    assert dash["kpis"]["site_new_jobs"] >= 1
    terr = requests.get(f"{API}/svc/engineer/queue/territory", headers=eng_h, timeout=30).json()
    ids = [j.get("id") for j in (terr.get("items") or terr.get("jobs") or terr.get("cases") or [])]
    assert S["case_id"] in ids, f"case not in territory queue ({len(ids)} jobs)"
    r = requests.post(f"{API}/svc/engineer/queue/{S['case_id']}/claim", json={}, headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text
    assert DB.svc_cases.find_one({"id": S["case_id"]})["assigned_engineer_id"] == ENG_ID


# ── STEP 3: engineer works the job ──────────────────────────────────
def test_step3_en_route_on_site_note(eng_h):
    r = requests.post(f"{API}/svc/engineer/time/start", json={"case_id": S["case_id"], "category": "travel"},
                      headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text
    assert DB.svc_cases.find_one({"id": S["case_id"]})["status"] == "en_route"
    st = requests.get(f"{API}/svc/engineer/jobs/{S['case_id']}/safety", headers=eng_h, timeout=30)
    assert st.status_code == 200, st.text
    items = [i["id"] for i in st.json()["template"]["items"]]
    r = requests.post(f"{API}/svc/engineer/jobs/{S['case_id']}/safety/signoff", json={
        "ticked_item_ids": items, "signature_image": SIG_PNG, "remarks": "TEST_"}, headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/svc/engineer/time/start", json={"case_id": S["case_id"], "category": "on_site"},
                      headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text
    assert DB.svc_cases.find_one({"id": S["case_id"]})["status"] == "on_site"
    r = requests.post(f"{API}/svc/engineer/jobs/{S['case_id']}/handoff-note",
                      json={"note": "TEST_ PCB for start button faulty, replacing"}, headers=eng_h, timeout=30)
    print("handoff-note", r.status_code)
    r = requests.post(f"{API}/svc/cases/{S['case_id']}/notes",
                      json={"body": "TEST_ Found failed start button PCB", "visibility": "customer"},
                      headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text


def test_step3_complete_requires_signoff(eng_h):
    r = requests.post(f"{API}/svc/engineer/jobs/{S['case_id']}/complete",
                      json={"summary": "x", "target": "awaiting_sign_off"}, headers=eng_h, timeout=30)
    assert r.status_code == 400 and "sign" in r.text.lower()


def test_step3_signature_and_complete(eng_h):
    r = requests.post(f"{API}/svc/engineer/signature", json={
        "case_id": S["case_id"], "signed_by_name": "TEST_ Cpl Signer", "image_data": SIG_PNG,
        "signed_by_role": "PTI"}, headers=eng_h, timeout=30)
    assert r.status_code == 200, r.text
    S["t_complete"] = datetime.now(timezone.utc)
    r = requests.post(f"{API}/svc/engineer/jobs/{S['case_id']}/complete", json={
        "summary": "Replaced start button PCB, tested OK", "target": "awaiting_sign_off"},
        headers=eng_h, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "awaiting_sign_off"


# ── STEP 4: MOD portal sees the engineer's work ─────────────────────
def test_step4_mod_fault_shows_engineer_report(mod_h):
    r = requests.get(f"{API}/mod/site/faults/{S['issue_id']}", headers=mod_h, timeout=30)
    assert r.status_code == 200
    d = r.json()
    print("ISSUE status", d.get("status"), "report", d.get("engineer_report"),
          "timeline", [t.get("event") for t in d.get("timeline") or []])
    assert d["status"] == "resolved"
    rep = d["engineer_report"]
    assert rep["summary"] == "Replaced start button PCB, tested OK"
    assert rep["signed_by_name"] == "TEST_ Cpl Signer"
    assert rep["engineer_name"] and rep["completed_at"]
    assert d["resolution_note"] == "Replaced start button PCB, tested OK"
    ev = [t.get("event") for t in d.get("timeline") or []]
    for need in ("engineer_en_route", "engineer_on_site", "engineer_report"):
        assert need in ev, f"timeline missing {need}"


def test_step4_service_report_pdf(mod_h):
    r = requests.get(f"{API}/mod/site/faults/{S['issue_id']}/service-report.pdf", headers=mod_h, timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


# ── STEP 5: Pulse close-out ─────────────────────────────────────────
def test_step5_pulse_close_out_and_signed_report_emails():
    time.sleep(8)
    evs = list(DB.email_send_events.find({"created_at": {"$gte": S["t_complete"]}}, {"_id": 0}))
    close = [e for e in evs if e["subject"].startswith("Close on Sicon ·") and S["ref"] in e["subject"]]
    print("POST-COMPLETE EVENTS", [(e["to"], e["subject"][:70], e["status"],
                                    (e.get("payload") or {}).get("from")) for e in evs if S["ref"] in e["subject"]])
    assert close, "No 'Close on Sicon' email attempt"
    c = close[0]
    assert c["to"].lower() == PULSE
    p = c.get("payload") or {}
    if c["status"] != "sent":
        assert p.get("attachments") and p["attachments"][0]["filename"].endswith(".pdf")
        assert "modservice.pulsefitness.com" in p.get("from", "")
        assert "Replaced start button PCB" in p.get("html", "")
    signed = [e for e in evs if e["subject"].startswith("Signed service report") and S["ref"] in e["subject"]]
    assert signed, "No signed service report email attempt"
    assert signed[0]["to"].lower() == (S["reporter_email"] or "").lower()
    if signed[0]["status"] != "sent":
        assert "modservice.pulsefitness.com" in signed[0]["payload"]["from"]


def test_step5_case_visible_in_service_desk():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@pulsefitness.com",
                                                 "password": "C2s9yJ3YAhydB4d34-Bykg"}, timeout=30)
    tok = r.json().get("token")
    if not tok:
        pytest.skip(f"master admin login needs MFA: {list(r.json())}")
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API}/bfpo/staff/jobs", headers=h, timeout=60)
    print("bfpo/staff/jobs", r.status_code, "found:", S["ref"] in r.text)
    S["mod_ops_found"] = r.status_code == 200 and S["ref"] in r.text
    r2 = requests.get(f"{API}/svc/cases", params={"search": S["ref"]}, headers=h, timeout=30)
    print("svc/cases search", r2.status_code, "found:", S["ref"] in r2.text, r2.text[:120])
    assert S["mod_ops_found"] or S["ref"] in r2.text, "case not findable by Pulse"


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    if os.environ.get("KEEP_MOD_E2E_DATA"):
        print("KEEP", S.get("issue_id"), S.get("case_id"))
        return
    cid, iid = S.get("case_id"), S.get("issue_id")
    if cid:
        for col in ("svc_case_events", "svc_signatures", "svc_time_entries", "svc_case_safety_signoffs",
                    "svc_engineer_job_drafts", "sicon_outbox"):
            DB[col].delete_many({"case_id": cid})
        DB.svc_cases.delete_one({"id": cid})
    if iid:
        DB.supplier_cases.delete_many({"issue_id": iid})
        DB.issues.delete_one({"id": iid})
    if S.get("equipment"):
        DB.equipment.update_one({"id": S["equipment"]["id"]},
                                {"$set": {"status": S["equip_status_before"]}})
