"""Iter319: Year 4 Schedule of Rates live, 365-day validity, full quote journey (rep create → manager approve → publish),
2/4/6-week chase schedule, chase processing (dedupe, dry_run customer email, follow-up for creator), follow-up close,
role restrictions, chase cancellation for inactive groups, notify dry_run, synthetic workbook guard."""
import io
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
import pytest
import requests
from pymongo import MongoClient

from tests.conftest import _test_backend_url  # noqa: E402

API = f"{_test_backend_url().rstrip('/')}/api"
MQ = f"{API}/mod-ops/quotes"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
LIVE_VERSION = "SOR-2026-11-25-b498fc"
ROWS = [{"row_id": "t1", "rate_card_id": "sor-2", "description": "TEST_Treadmills", "qty": 2, "coverage": "A", "label": ""},
        {"row_id": "t2", "rate_card_id": "sor-5", "description": "TEST_Benches", "qty": 1, "coverage": "B", "label": ""}]
CUSTOMER = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_Officer", "contact_email": "test_officer@example.test",
            "address_lines": ["Faslane", "Helensburgh", "G84 0EH"]}
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE: dict = {}
CREATED: list = []


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def mgr():
    return _login("modsales.manager@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module")
def rep():
    return _login("modsales.rep@pulsedemo.test", "ModSales123!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED:
        s = _login("modsales.manager@pulsedemo.test", "ModSales123!")
        for gid in CREATED:
            s.post(f"{MQ}/groups/{gid}/withdraw", json={"reason": "TEST cleanup iter319"})
            DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"chase_schedule.$[p].status": "cancelled"}},
                                           array_filters=[{"p.status": "pending"}])
    if STATE.get("preview_pid"):
        DB.mod_sor_price_lists.delete_one({"id": STATE["preview_pid"], "status": "preview"})


def _published_group(rep, mgr, key_suffix):
    body = {"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B", "AB"], "callout_qty": 1,
            "idempotency_key": f"TEST_iter319_{key_suffix}_{uuid.uuid4()}"}
    r = rep.post(f"{MQ}/groups", json=body)
    assert r.status_code == 200, r.text
    g = r.json()
    CREATED.append(g["id"])
    assert rep.post(f"{MQ}/groups/{g['id']}/submit").status_code == 200
    a = mgr.post(f"{MQ}/groups/{g['id']}/approve", json={"approve": True, "exceptions": []})
    assert a.status_code == 200, f"approve needed exceptions? {a.text}"
    p = rep.post(f"{MQ}/groups/{g['id']}/publish", json={"quote_ids": [q["id"] for q in g["quotes"]]})
    assert p.status_code == 200, p.text
    return p.json()


# Schedule of Rates: Year 4 live list
def test_rates_current_year4_live(mgr):
    d = mgr.get(f"{MQ}/rates/current").json()
    assert d["customer_ready"] is True, d["summary"]
    assert "version" not in d["live_price_list"]  # provenance is Master Admin only
    assert d["live_price_list"]["effective_from"] == "2026-11-25"
    by = {}
    for r in d["rows"]:
        by.setdefault(r["label"], r)
    assert by["Treadmill"]["a"]["price"] == 255.0 and by["Treadmill"]["b"]["price"] == 24.0
    assert by["Call Out Charge (Type B / UK Only)"]["b"]["price"] == 80.0
    assert by["Call Out Charge (Type B / UK Only)"]["a"]["status"] == "n/a"
    assert by["Spinning Bikes"]["a"]["price"] == 56.73
    assert by["Rowing Machine"]["a"]["price"] == 72.56
    assert by["Radiant Trainer"]["a"]["price"] == 145.12 and by["Freedom Trainer"]["a"]["price"] == 145.12
    assert by["Multigym, 4 Station"]["a"]["price"] == 145.12
    for lbl, a in (("Multigym, 5 Station", 207.5), ("Multigym, 7 Station", 207.5), ("Multigym, 8 Station", 257.5),
                   ("Multigym, 9 Station", 257.5), ("Multigym, 10 Station", 257.5), ("Multigym, 12 Station", 257.5)):
        assert by[lbl]["a"]["price"] == a and by[lbl]["b"]["price"] == 21.0, lbl
    assert set(d["summary"]) <= {"verified", "poa"}, d["summary"]


# Validity setting 365 days approved
def test_validity_365(rep):
    v = rep.get(f"{MQ}/settings").json()["validity"]
    assert v["days"] == 365 and v["status"] == "approved"


# Full journey: publish → valid_until +365, chase schedule 14/28/42
def test_publish_sets_validity_and_chase(rep, mgr):
    g = _published_group(rep, mgr, "main")
    STATE["gid"] = g["id"]
    today = date.today()
    utc_today = datetime.now(timezone.utc).date()
    vis = [q for q in g["quotes"] if q.get("customer_visible")]
    assert len(vis) == 3
    for q in vis:
        assert q["valid_until"] == (utc_today + timedelta(days=365)).isoformat()
    cs = g["chase_schedule"]
    assert [c["weeks"] for c in cs] == [2, 4, 6]
    assert [c["due"] for c in cs] == [(today + timedelta(days=n)).isoformat() for n in (14, 28, 42)]
    assert all(c["status"] == "pending" for c in cs)


# Rep cannot run chases
def test_rep_cannot_run(rep):
    assert rep.post(f"{MQ}/followups/run").status_code == 403


# Chase processing creates exactly one follow-up for creator, deduped on re-run
def test_run_chase_once(mgr, rep):
    gid = STATE["gid"]
    DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"chase_schedule.0.due": "2026-01-01"}})
    r = mgr.post(f"{MQ}/followups/run")
    assert r.status_code == 200, r.text
    assert r.json()["live_email"] is False and r.json()["processed"] >= 1
    r2 = mgr.post(f"{MQ}/followups/run")
    assert r2.status_code == 200
    fus = list(DB.mod_quote_followups.find({"group_id": gid}, {"_id": 0}))
    assert len(fus) == 1
    rep_id = DB.users.find_one({"email": "modsales.rep@pulsedemo.test"})["id"]
    assert fus[0]["assigned_to"] == rep_id and fus[0]["email_status"] == "awaiting_approval" and fus[0]["chase_no"] == 1
    STATE["fid"] = fus[0]["id"]
    g = mgr.get(f"{MQ}/groups/{gid}").json()
    assert [c["status"] for c in g["chase_schedule"]] == ["task_created", "pending", "pending"]
    assert g["chase_schedule"][0]["email_status"] == "awaiting_approval"
    assert any(e["kind"] == "follow_up_due" for e in g["events"])


# Visibility: rep sees own; manager needs everyone=true
def test_followup_visibility(mgr, rep):
    fid = STATE["fid"]
    assert any(f["id"] == fid for f in rep.get(f"{MQ}/followups").json()["items"])
    assert not any(f["id"] == fid for f in mgr.get(f"{MQ}/followups").json()["items"])
    assert any(f["id"] == fid for f in mgr.get(f"{MQ}/followups?everyone=true").json()["items"])
    # rep everyone=true still restricted to own
    assert all(f["assigned_to"] == DB.users.find_one({"email": "modsales.rep@pulsedemo.test"})["id"]
               for f in rep.get(f"{MQ}/followups?everyone=true").json()["items"])


# Close follow-up
def test_followup_done(rep):
    fid, gid = STATE["fid"], STATE["gid"]
    assert rep.post(f"{MQ}/followups/{fid}/done", json={"outcome": "ab"}).status_code == 422
    r = rep.post(f"{MQ}/followups/{fid}/done", json={"outcome": "TEST_Spoke to officer, PO next week"})
    assert r.status_code == 200, r.text
    assert not any(f["id"] == fid for f in rep.get(f"{MQ}/followups").json()["items"])
    assert rep.post(f"{MQ}/followups/{fid}/done", json={"outcome": "again"}).status_code == 409
    ev = rep.get(f"{MQ}/groups/{gid}").json()["events"]
    assert any(e["kind"] == "follow_up_recorded" for e in ev)


# Notify defaults attach + dry run
def test_notify_dry_run(rep):
    gid = STATE["gid"]
    r = rep.post(f"{MQ}/groups/{gid}/notify", json={"to": "test_officer@example.test", "confirm_to": "test_officer@example.test"})
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True and r.json()["sent"] is False
    ev = rep.get(f"{MQ}/groups/{gid}").json()["events"]
    dr = [e for e in ev if e["kind"] == "customer_notification_dry_run"][0]
    assert dr["detail"]["attachments"] == 3


# Chase cancelled for inactive groups
@pytest.mark.parametrize("status", ["withdrawn", "authorisation_submitted", "accepted"])
def test_chase_cancelled_when_inactive(rep, mgr, status):
    g = _published_group(rep, mgr, status)
    gid = g["id"]
    if status == "withdrawn":
        assert rep.post(f"{MQ}/groups/{gid}/withdraw", json={"reason": "TEST"}).status_code == 200
    else:
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": status}})
    DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"chase_schedule.0.due": "2026-01-01"}})
    r = mgr.post(f"{MQ}/followups/run")
    assert r.status_code == 200 and r.json()["cancelled"] >= 1
    assert DB.mod_quote_followups.count_documents({"group_id": gid}) == 0
    cs = DB.mod_quote_groups.find_one({"id": gid})["chase_schedule"]
    assert cs[0]["status"] == "cancelled" and cs[0]["reason"] == status
    if status != "withdrawn":
        DB.mod_quote_groups.update_one({"id": gid}, {"$set": {"status": "published"}})


# Synthetic workbook guard
def test_synthetic_guard(mgr):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "1. Pricing Schedule "
    ws.append(["SYNTHETIC TEST DATA"])
    ws.append(["Item no", "TL Number", "Domestic Management Code (DMC)", "Supplier Part Number", "NSN (from Msys.PDM)",
               "Short Item Description \n(max char 30)", "Extended Item Description\n(max char 30)", "Service (S) or Goods (G)",
               "Year 3 Price", "Year 4 Estimated Quantity", "Year 4 Price"])
    ws.append(["2A", "SER2", "PAT", "MOD-TREAD-A", "N/A", "Treadmill,", "Type A Service", "S", 200, None, 999])
    buf = io.BytesIO()
    wb.save(buf)
    r = mgr.post(f"{MQ}/rates/import-preview", files={"file": ("TEST_synth.xlsx", buf.getvalue(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["synthetic"] is True
    STATE["preview_pid"] = r.json()["price_list_id"]
    a = mgr.post(f"{MQ}/rates/{STATE['preview_pid']}/approve", json={"effective_from": "2026-11-25", "confirm": True})
    assert a.status_code == 409


def test_live_list_unchanged(mgr):
    d = mgr.get(f"{MQ}/rates/current").json()
    assert d["customer_ready"] is True
