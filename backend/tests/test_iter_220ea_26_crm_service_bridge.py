"""Iter 220ea·26 — CRM ↔ Service Ops bridge (gaps G3 / G1 / G2).

  • G3 — ``resolve_sage_customer_id`` is v2-first with v1 fallback, by
    name OR email (was v1 + name only).
  • G1 — canonical ``company_id`` spine: ``find_company_id`` resolver,
    ``/svc/customers/crm-search`` picker, backfill endpoint, and
    auto-link on intake / engineer-customer create.
  • G2 — ``onboard_contract_to_service``: an activated PPM contract seeds
    a service customer + PPM schedule + first visit case (idempotent).
"""
import uuid
from pathlib import Path

import pytest
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers
from tests.shared_loop import run_async
import utils.database as _dbm
from utils.sales_to_service import onboard_contract_to_service
from utils.svc_crm_sync import find_company_id, push_customer_to_crm, resolve_sage_customer_id


class _DbProxy:
    """Always resolve against the CURRENT `utils.database.db`.

    The autouse `_rebind_motor_to_current_loop` fixture swaps in a fresh
    Motor client per test; a by-value `from utils.database import db`
    import would pin the original client (whose pool may be bound to a
    stale event loop mid-session) and trip
    ``RuntimeError: ... attached to a different loop`` in full runs.
    """

    def __getattr__(self, name):
        return getattr(_dbm.db, name)

    def __getitem__(self, name):
        return _dbm.db[name]


db = _DbProxy()

BASE = _test_backend_url()
BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


# ─────────────────────── G3 — Sage resolver ───────────────────────

def test_resolve_sage_customer_id_v2_first_then_v1():
    org = "i26g3_" + uuid.uuid4().hex[:8]

    async def scenario():
        # v2 company carries the sage id → must win.
        await db.crm2_companies.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org,
            "name": "Vertex Health", "email": "ops@vertex.io",
            "sage_customer_id": "SAGE-V2"})
        by_name = await resolve_sage_customer_id(org, name="Vertex Health")
        by_email = await resolve_sage_customer_id(org, name="", email="ops@vertex.io")
        # v1-only company → fallback must still resolve.
        await db.crm2_companies.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "name": "Apex Fit"})
        await db.crm_companies.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org,
            "name": "Apex Fit", "sage_customer_id": "SAGE-V1"})
        fallback = await resolve_sage_customer_id(org, name="Apex Fit")
        miss = await resolve_sage_customer_id(org, name="Nobody Ltd")
        await db.crm2_companies.delete_many({"organization_id": org})
        await db.crm_companies.delete_many({"organization_id": org})
        return by_name, by_email, fallback, miss

    by_name, by_email, fallback, miss = run_async(scenario())
    assert by_name == "SAGE-V2"
    assert by_email == "SAGE-V2"
    assert fallback == "SAGE-V1"
    assert miss == ""


# ─────────────────────── G1 — canonical link ──────────────────────

def test_find_company_id_resolves_crm_company():
    org = "i26g1_" + uuid.uuid4().hex[:8]
    cid = str(uuid.uuid4())

    async def scenario():
        await db.crm2_companies.insert_one({
            "id": cid, "organization_id": org, "name": "Nova Leisure",
            "email": "fm@nova.co", "postcode": "N1 9AA"})
        by_name = await find_company_id(org, name="Nova Leisure")
        by_email = await find_company_id(org, name="", email="fm@nova.co")
        miss = await find_company_id(org, name="Ghost Co")
        await db.crm2_companies.delete_many({"organization_id": org})
        return by_name, by_email, miss

    by_name, by_email, miss = run_async(scenario())
    assert by_name == cid
    assert by_email == cid
    assert miss == ""


def test_crm_search_and_backfill_endpoints(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        pytest.skip("no master admin token (rate limited?)")
    # Seed a company in the master admin's org, then search for it.
    name = "ZZBridgeTest " + uuid.uuid4().hex[:6]

    async def seed():
        u = await db.users.find_one({"email": "admin@gymaxisai.com"},
                                    {"_id": 0, "organization_id": 1})
        org = (u or {}).get("organization_id")
        await db.crm2_companies.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "name": name,
            "email": "x@zz.test", "sage_customer_id": "SAGE-ZZ"})
        return org

    org = run_async(seed())
    try:
        r = requests.get(f"{BASE}/api/svc/customers/crm-search",
                         params={"q": "ZZBridgeTest"}, headers=_h(token), timeout=20)
        assert r.status_code == 200, r.text
        names = [c["name"] for c in r.json().get("companies", [])]
        assert name in names
        # Backfill runs and returns the expected shape.
        b = requests.post(f"{BASE}/api/svc/admin/customers/backfill-crm-links",
                          headers=_h(token), timeout=60)
        assert b.status_code == 200, b.text
        body = b.json()
        assert "cases" in body and "customers" in body
        assert "linked" in body["cases"]
    finally:
        run_async(db.crm2_companies.delete_many({"organization_id": org, "name": name}))


# ─────────────────────── G2 — sales→service ───────────────────────

def test_onboard_contract_seeds_customer_schedule_and_case():
    org = "i26g2_" + uuid.uuid4().hex[:8]
    cid = str(uuid.uuid4())
    contract = {
        "id": str(uuid.uuid4()), "organization_id": org, "company_id": cid,
        "company_name": "Summit Gyms", "contract_number": "CT-26-9",
        "tier": "premium", "start_date": "2026-03-01", "end_date": "2027-02-28",
        "sla": {"preventive_maintenance": True, "visits_per_year": 4},
    }
    user = {"id": "u1", "organization_id": org, "full_name": "Rep"}

    async def scenario():
        await db.crm2_companies.insert_one({
            "id": cid, "organization_id": org, "name": "Summit Gyms",
            "email": "fm@summit.co", "postcode": "S1 2AB"})
        r1 = await onboard_contract_to_service(contract, user=user)
        cust = await db.svc_engineer_customers.find_one(
            {"organization_id": org, "company_id": cid}, {"_id": 0, "name": 1})
        sched = await db.svc_ppm_schedules.find_one(
            {"organization_id": org, "contract_id": contract["id"]},
            {"_id": 0, "interval_days": 1, "visits_per_year": 1})
        # Idempotent re-run.
        r2 = await onboard_contract_to_service(contract, user=user)
        n_sched = await db.svc_ppm_schedules.count_documents(
            {"organization_id": org, "contract_id": contract["id"]})
        n_case = await db.svc_cases.count_documents(
            {"organization_id": org, "case_type": "ppm"})
        # Non-PPM contract is ignored.
        r3 = await onboard_contract_to_service(
            {"id": str(uuid.uuid4()), "organization_id": org, "company_id": cid,
             "sla": {"preventive_maintenance": False, "visits_per_year": 0}},
            user=user)
        for c in ("crm2_companies", "svc_engineer_customers",
                  "svc_ppm_schedules", "svc_cases"):
            await db[c].delete_many({"organization_id": org})
        return r1, cust, sched, r2, n_sched, n_case, r3

    r1, cust, sched, r2, n_sched, n_case, r3 = run_async(scenario())
    assert r1["onboarded"] is True
    assert r1["case_id"]
    assert cust and cust["name"] == "Summit Gyms"
    assert sched and sched["visits_per_year"] == 4 and sched["interval_days"] == 91
    assert r2["reason"] == "already onboarded"
    assert n_sched == 1 and n_case == 1  # idempotent — no duplicates
    assert r3["onboarded"] is False


# ─────────────────── G2c — PPM recurrence rollover ────────────────

def test_ppm_rollover_creates_next_visit_on_completion(master_admin_token_session):
    token = master_admin_token_session
    if not token:
        pytest.skip("no master admin token (rate limited?)")
    sched_id = str(uuid.uuid4())

    async def org_of():
        u = await db.users.find_one({"email": "admin@gymaxisai.com"},
                                    {"_id": 0, "organization_id": 1})
        return (u or {}).get("organization_id")

    org = run_async(org_of())

    async def seed():
        # Schedule (12 visits/yr, 30-day interval) + a completed first visit.
        await db.svc_ppm_schedules.insert_one({
            "id": sched_id, "organization_id": org, "contract_id": str(uuid.uuid4()),
            "company_id": "", "customer_name": "Cadence Gyms QA", "customer_email": "",
            "site_postcode": "CB1 1AA", "visits_per_year": 12, "interval_days": 30,
            "start_date": "2026-02-01", "end_date": "2027-01-31",
            "next_due_date": "2026-02-01", "visits_generated": 1, "active": True})
        await db.svc_cases.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "case_type": "ppm",
            "status": "closed", "ppm_schedule_id": sched_id,
            "ppm_due_date": "2026-02-01", "scheduled_at": "2026-02-01T00:00:00+00:00",
            "reference": "PPM-QA-1", "created_at": "2026-02-01T00:00:00+00:00"})

    run_async(seed())
    try:
        # Roll via the real endpoint (runs in the server's healthy loop).
        r = requests.post(f"{BASE}/api/svc/admin/ppm/roll", headers=_h(token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("created", 0) >= 1

        async def next_open():
            return await db.svc_cases.find_one(
                {"organization_id": org, "ppm_schedule_id": sched_id,
                 "status": {"$ne": "closed"}}, {"_id": 0, "ppm_due_date": 1})

        async def n_open():
            return await db.svc_cases.count_documents(
                {"organization_id": org, "ppm_schedule_id": sched_id,
                 "status": {"$ne": "closed"}})

        nxt = run_async(next_open())
        assert nxt and nxt["ppm_due_date"] == "2026-03-03"  # 2026-02-01 + 30 days

        # Idempotent — rolling again leaves exactly one open visit.
        requests.post(f"{BASE}/api/svc/admin/ppm/roll", headers=_h(token), timeout=30)
        assert run_async(n_open()) == 1

        # Past end-date → schedule retired, no new visit.
        run_async(db.svc_ppm_schedules.update_one(
            {"id": sched_id}, {"$set": {"end_date": "2020-01-01"}}))
        run_async(db.svc_cases.update_many(
            {"organization_id": org, "ppm_schedule_id": sched_id},
            {"$set": {"status": "closed"}}))
        requests.post(f"{BASE}/api/svc/admin/ppm/roll", headers=_h(token), timeout=30)

        async def sched_active():
            s = await db.svc_ppm_schedules.find_one({"id": sched_id}, {"_id": 0, "active": 1})
            return s["active"]

        assert run_async(sched_active()) is False
    finally:
        run_async(db.svc_cases.delete_many(
            {"organization_id": org, "ppm_schedule_id": sched_id}))
        run_async(db.svc_ppm_schedules.delete_many({"id": sched_id}))


def test_ppm_rollover_worker_and_endpoint_wired():
    server = (BACKEND / "server.py").read_text()
    assert "ppm_rollover" in server and "ppm-rollover" in server
    links = (BACKEND / "routes" / "svc" / "customer_links.py").read_text()
    assert "/admin/ppm/roll" in links


# ─────────────────── G4 — field customer → CRM ────────────────────

def test_push_field_customer_to_crm_creates_and_matches():
    org = "i26g4_" + uuid.uuid4().hex[:8]
    user = {"id": "eng1", "organization_id": org, "full_name": "Field Eng"}

    async def scenario():
        # A) New field customer, no CRM match → creates a CRM company.
        cust_a = {"id": str(uuid.uuid4()), "organization_id": org,
                  "name": "Riverside Gym", "email": "gm@riverside.co",
                  "postcode": "LS1 1AA", "company_id": ""}
        await db.svc_engineer_customers.insert_one(dict(cust_a))
        r_a = await push_customer_to_crm(cust_a, user=user)
        co = await db.crm2_companies.find_one(
            {"organization_id": org, "id": r_a["company_id"]},
            {"_id": 0, "type": 1, "source": 1})
        linked = await db.svc_engineer_customers.find_one(
            {"id": cust_a["id"]}, {"_id": 0, "company_id": 1})
        # A') Idempotent — already linked, no duplicate company.
        r_a2 = await push_customer_to_crm(
            {**cust_a, "company_id": r_a["company_id"]}, user=user)
        n_riverside = await db.crm2_companies.count_documents(
            {"organization_id": org, "name": "Riverside Gym"})
        # B) Field customer matching an existing CRM company → links only.
        cid = str(uuid.uuid4())
        await db.crm2_companies.insert_one(
            {"id": cid, "organization_id": org, "name": "Peak Fitness"})
        cust_b = {"id": str(uuid.uuid4()), "organization_id": org,
                  "name": "Peak Fitness", "company_id": ""}
        r_b = await push_customer_to_crm(cust_b, user=user)
        n_peak = await db.crm2_companies.count_documents(
            {"organization_id": org, "name": "Peak Fitness"})
        for c in ("crm2_companies", "crm2_activities", "svc_engineer_customers"):
            await db[c].delete_many({"organization_id": org})
        return r_a, co, linked, r_a2, n_riverside, r_b, n_peak

    r_a, co, linked, r_a2, n_riverside, r_b, n_peak = run_async(scenario())
    assert r_a["created"] is True and r_a["linked"] is True
    assert co and co["type"] == "customer" and co["source"] == "service_field"
    assert linked["company_id"] == r_a["company_id"]
    assert r_a2["reason"] == "already linked" and n_riverside == 1
    assert r_b["created"] is False and r_b["linked"] is True and n_peak == 1


def test_push_endpoints_registered():
    src = (BACKEND / "routes" / "svc" / "customer_links.py").read_text()
    assert "/customers/{customer_id}/push-to-crm" in src
    assert "/admin/customers/push-unlinked-to-crm" in src
    fe = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerCustomers.js").read_text()
    assert "push-to-crm" in fe
    assert "Create in CRM" in fe



# ─────────────────────── source / wiring guards ───────────────────

def test_customer_links_router_registered():
    feats = (BACKEND / "route_registry" / "features.py").read_text()
    assert "svc_customer_links_router" in feats
    src = (BACKEND / "routes" / "svc" / "customer_links.py").read_text()
    assert "/customers/crm-search" in src
    assert "/admin/customers/backfill-crm-links" in src


def test_intake_and_models_carry_company_id():
    intake = (BACKEND / "routes" / "svc" / "intake.py").read_text()
    assert 'case["company_id"]' in intake
    assert "find_company_id" in intake
    cust = (BACKEND / "routes" / "svc" / "engineer_customers.py").read_text()
    assert "company_id" in cust
    assert "crm_company" in cust  # detail enrichment


def test_g2_wired_into_contract_activation():
    src = (BACKEND / "routes" / "crm_contracts.py").read_text()
    assert "onboard_contract_to_service" in src
    # Both activate + sign paths.
    assert src.count("onboard_contract_to_service") >= 2


def test_frontend_has_crm_link_control():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerCustomers.js").read_text()
    assert "CrmLinkRow" in src
    assert "crm-search" in src
    assert "crm_company" in src
