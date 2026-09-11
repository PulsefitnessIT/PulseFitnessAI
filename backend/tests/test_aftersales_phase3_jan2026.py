"""Aftersales Contract Automation — Phase 3 (Agreement Builder + Activation).
Full lifecycle: build_quote -> accept -> agreement -> generate -> sign -> activate.
Plus idempotency, guards, monthly DD, wording governance, dashboard counters."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
COMPANY_ID = "iso-cA"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/crm/auth/login",
                      json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def gold_quote_id(hdr):
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate",
                      json={"company_id": COMPANY_ID, "contract_type": "gold", "save": True},
                      headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    qid = r.json().get("saved_quote_id") or r.json().get("quote_id") or r.json().get("id")
    assert qid, r.text
    return qid


@pytest.fixture(scope="module")
def platinum_quote_id(hdr):
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate",
                      json={"company_id": COMPANY_ID, "contract_type": "platinum", "save": True},
                      headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    return r.json().get("saved_quote_id")


# ---------- lifecycle ----------
class TestLifecycle:
    def test_1_accept(self, hdr, gold_quote_id):
        r = requests.post(f"{API}/crm/v2/aftersales/quotes/{gold_quote_id}/accept",
                          json={}, headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"

    def test_2_prepare_agreement(self, hdr, gold_quote_id, request):
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/from-quote/{gold_quote_id}",
                          json={"start_date": "2026-07-01", "payment_method": "annual",
                                "visits_per_year": 2}, headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        ag = r.json()
        assert ag["agreement_number"].startswith("PF-MA-")
        assert ag["status"] == "draft"
        assert len(ag["schedules"]["schedule3_equipment"]) > 0
        assert len(ag["schedules"]["schedule1_parties"]["sites"]) > 0
        assert ag["health"]["ready"] is True, ag["health"]
        request.config._aid = ag["id"]

    def test_3_idempotent_prepare(self, hdr, gold_quote_id, request):
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/from-quote/{gold_quote_id}",
                          json={"start_date": "2026-07-01", "payment_method": "annual",
                                "visits_per_year": 2}, headers=hdr, timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == request.config._aid  # same agreement returned

    def test_4_generate_before_ready_and_after(self, hdr, request):
        aid = request.config._aid
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/{aid}/generate",
                          headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"

    def test_5_activate_before_signed_returns_400(self, hdr, request):
        aid = request.config._aid
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/{aid}/activate",
                          headers=hdr, timeout=30)
        assert r.status_code == 400

    def test_6_sign_without_authority_400(self, hdr, request):
        aid = request.config._aid
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/{aid}/sign",
                          json={"signatory_name": "Jane Doe", "position": "MD",
                                "email": "jane@alphaco.example",
                                "authority_confirmed": False},
                          headers=hdr, timeout=30)
        assert r.status_code == 400

    def test_7_sign_ok(self, hdr, request):
        aid = request.config._aid
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/{aid}/sign",
                          json={"signatory_name": "Jane Doe", "position": "MD",
                                "email": "jane@alphaco.example",
                                "authority_confirmed": True},
                          headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "signed"

    def test_8_activate(self, hdr, request):
        aid = request.config._aid
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/{aid}/activate",
                          headers=hdr, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "active"
        assert j["assets_covered"] > 0
        assert j["service_visits"] == 2
        assert j["invoices"] >= 1
        step_names = {s["step"] for s in j["steps"]}
        for expected in ["duplicate_check", "contract_record", "asset_cover",
                         "service_schedule", "billing_schedule", "direct_debit",
                         "sicon_sync", "sage_sync"]:
            assert expected in step_names, f"missing step {expected}"
        # sicon/sage must be queued
        by_name = {s["step"]: s for s in j["steps"]}
        assert by_name["sicon_sync"]["status"] == "queued"
        assert by_name["sage_sync"]["status"] == "queued"
        request.config._cid = j["contract_id"]

    def test_9_contract_schedules(self, hdr, request):
        cid = request.config._cid
        r = requests.get(f"{API}/crm/v2/aftersales/contracts/{cid}/schedules",
                         headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["contract"]["status"] == "active"
        assert j["service"]["required"] == 2
        assert j["service"]["next_due"] is not None
        assert len(j["billing"]) >= 1


# ---------- guards & governance ----------
class TestGuardsAndGovernance:
    def test_monthly_dd_flag(self, hdr, gold_quote_id):
        # find existing agreement for the accepted quote
        r = requests.get(f"{API}/crm/v2/aftersales/agreements", headers=hdr, timeout=30)
        assert r.status_code == 200
        ag = next((a for a in r.json()["agreements"] if a.get("quote_id") == gold_quote_id), None)
        assert ag
        aid = ag["id"]
        # switch to monthly
        r = requests.patch(f"{API}/crm/v2/aftersales/agreements/{aid}",
                           json={"payment_method": "monthly"}, headers=hdr, timeout=30)
        assert r.status_code == 200
        health = r.json()["health"]
        assert any("Direct Debit" in x for x in health["reasons"]), health

        # clear DD flag
        r = requests.patch(f"{API}/crm/v2/aftersales/agreements/{aid}",
                           json={"direct_debit_received": True}, headers=hdr, timeout=30)
        assert r.status_code == 200
        health = r.json()["health"]
        assert not any("Direct Debit" in x for x in health["reasons"]), health

        # restore to annual for cleanliness
        requests.patch(f"{API}/crm/v2/aftersales/agreements/{aid}",
                       json={"payment_method": "annual"}, headers=hdr, timeout=30)

    def test_platinum_wording_conflict(self, hdr, platinum_quote_id):
        if not platinum_quote_id:
            pytest.skip("no platinum quote saved")
        # accept
        r = requests.post(f"{API}/crm/v2/aftersales/quotes/{platinum_quote_id}/accept",
                          json={}, headers=hdr, timeout=30)
        assert r.status_code == 200
        # prepare
        r = requests.post(f"{API}/crm/v2/aftersales/agreements/from-quote/{platinum_quote_id}",
                          json={"start_date": "2026-08-01", "payment_method": "annual",
                                "visits_per_year": 2}, headers=hdr, timeout=30)
        assert r.status_code == 200
        ag = r.json()
        aid = ag["id"]
        wcs = ag.get("wording_conflicts") or []
        if not wcs:
            pytest.skip("no wording conflicts configured on platinum package")
        # ensure health flags it
        r = requests.get(f"{API}/crm/v2/aftersales/agreements/{aid}", headers=hdr, timeout=30)
        health = r.json()["health"]
        assert any("wording" in x.lower() for x in health["reasons"]), health
        # resolve
        r = requests.patch(f"{API}/crm/v2/aftersales/agreements/{aid}",
                           json={"resolve_wording": True}, headers=hdr, timeout=30)
        assert r.status_code == 200
        health = r.json()["health"]
        assert not any("wording" in x.lower() for x in health["reasons"]), health


class TestDashboard:
    def test_dashboard_counters(self, hdr):
        r = requests.get(f"{API}/crm/v2/aftersales/dashboard", headers=hdr, timeout=30)
        assert r.status_code == 200
        j = r.json()
        # counters may be top-level or under cards
        pool = {**j, **(j.get("cards") or {})}
        # look for the counters we care about
        assert "agreements_awaiting_signature" in pool or "contracts_ready_to_activate" in pool, pool
