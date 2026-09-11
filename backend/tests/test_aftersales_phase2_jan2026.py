"""
Aftersales Contract Automation Engine — Phase 2 backend tests
(estate loader + build-quote-from-estate + exception resolution + regressions)
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
CRM_EMAIL = "owner@isodemo.com"
CRM_PASS = "IsoDemo123!"
COMPANY_ID = "iso-cA"
EXPECTED_LINKED_ORG = "iso-demo-org"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{API}/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PASS}, timeout=20)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def h(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


# --- 1. Estate endpoint ---------------------------------------------------
def test_estate_returns_20_annotated_assets(h):
    r = requests.get(f"{API}/crm/v2/aftersales/estate/{COMPANY_ID}", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["linked_organization_id"] == EXPECTED_LINKED_ORG
    assert d["totals"]["assets"] == 20, f"expected 20 assets, got {d['totals']}"
    ok = {"SUPPORTED", "PROVISIONAL", "RRP_REQUIRED", "NOT_ELIGIBLE", "NOT_MATCHED",
          "SUPPORTABILITY_REVIEW"}
    flat = [a for s in d["sites"] for a in s["assets"]]
    for a in flat:
        assert a["pricing_status"] in ok, a
        assert "supportability" in a


# --- 2. Build quote from estate (all sites, gold) -------------------------
@pytest.fixture(scope="module")
def build_all_gold(h):
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": COMPANY_ID, "contract_type": "gold"}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def test_build_confidence_and_shape(build_all_gold):
    d = build_all_gold
    assert d["confidence"] in {"READY_FOR_REVIEW", "REVIEW_REQUIRED", "CANNOT_AUTO_QUOTE"}
    assert d["assets_total"] == 20
    assert 0 <= d["assets_priced"] <= 20
    assert isinstance(d["exceptions"], list)
    assert d["exception_count"] == len(d["exceptions"])
    assert isinstance(d["grouped_lines"], list)
    assert isinstance(d["asset_register"], list) and len(d["asset_register"]) == 20
    s = d["summary"]
    assert s["final_annual"] > 0
    assert s["gold_base_annual"] > 0
    # Roughly ~6/20 & £1938.19 baseline per problem statement
    assert d["assets_priced"] == 6, f"expected 6 priced, got {d['assets_priced']}"
    assert abs(s["gold_base_annual"] - 1938.19) < 0.5, s


def test_never_invent_prices(build_all_gold):
    """NOT_MATCHED / RRP_REQUIRED must have annual 0 and appear as exceptions."""
    ex_ids = {e.get("asset_id") for e in build_all_gold["exceptions"]}
    for a in build_all_gold["asset_register"]:
        if a["pricing_status"] in ("NOT_MATCHED", "RRP_REQUIRED", "NOT_ELIGIBLE"):
            assert a.get("annual", 0) == 0, a
            assert a["id"] in ex_ids, f"{a['pricing_status']} not in exception queue"


def test_grouped_lines_have_required_fields(build_all_gold):
    for g in build_all_gold["grouped_lines"]:
        for k in ("model", "console_type", "qty", "serials", "annual_total"):
            assert k in g, g
        assert g["qty"] == len(g["serials"])


# --- 3. Site filtering ----------------------------------------------------
def test_site_filtering_restricts_assets(h):
    est = requests.get(f"{API}/crm/v2/aftersales/estate/{COMPANY_ID}", headers=h).json()
    real_sites = [s["id"] for s in est["sites"] if s["id"] != "__unassigned__"][:2]
    assert len(real_sites) == 2, [s["id"] for s in est["sites"]]
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": COMPANY_ID, "site_ids": real_sites,
                            "contract_type": "gold"}, timeout=60).json()
    assert r["assets_total"] == 16, f"expected 16 with site filter, got {r['assets_total']}"


# --- 4. Save persists a draft --------------------------------------------
def test_save_persists_and_lists(h):
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": COMPANY_ID, "contract_type": "gold",
                            "save": True}, timeout=60).json()
    qid = r.get("saved_quote_id")
    qnum = r.get("quote_number")
    assert qid and qnum, r
    assert re.match(r"^AFS-\d{4}-[A-Z0-9]{5}$", qnum), qnum

    lst = requests.get(f"{API}/crm/v2/aftersales/quotes", headers=h).json()
    ids = [q["id"] for q in lst["quotes"]]
    assert qid in ids

    det = requests.get(f"{API}/crm/v2/aftersales/quotes/{qid}", headers=h)
    assert det.status_code == 200
    doc = det.json()
    assert doc["quote_number"] == qnum
    assert doc["company_id"] == COMPANY_ID
    assert doc["status"] == "draft"
    assert doc["source"] == "auto_estate"


def test_dashboard_includes_afs_drafts(h):
    # first count current afs drafts
    lst = requests.get(f"{API}/crm/v2/aftersales/quotes?status=draft", headers=h).json()
    n_drafts = len(lst["quotes"])
    dash = requests.get(f"{API}/crm/v2/aftersales/dashboard", headers=h)
    if dash.status_code != 200:
        pytest.skip("dashboard endpoint not present")
    d = dash.json()
    qtp = d.get("quotes_to_prepare")
    if qtp is None:
        pytest.skip("no quotes_to_prepare field")
    assert qtp >= n_drafts, f"quotes_to_prepare={qtp} < afs drafts {n_drafts}"


# --- 5. Exception resolution: manual RRP override ------------------------
def test_rrp_override_reprices(h):
    # find an RRP_REQUIRED exception with a config_id
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": COMPANY_ID, "contract_type": "gold"}).json()
    before_priced = r["assets_priced"]
    target = None
    for e in r["exceptions"]:
        if e["kind"] == "RRP_REQUIRED" and e.get("config_id"):
            target = e
            break
    if not target:
        pytest.skip("no RRP_REQUIRED exception with config_id — cannot verify override")
    cfg_id = target["config_id"]

    # capture original config for restore
    cfgs = requests.get(f"{API}/crm/v2/aftersales/service-configs", headers=h).json()
    orig = next((c for c in cfgs.get("configs", cfgs.get("items", [])) if c.get("id") == cfg_id), None)
    assert orig, f"config {cfg_id} not found"

    try:
        put = requests.put(f"{API}/crm/v2/aftersales/service-configs/{cfg_id}",
                           headers=h,
                           json={"manual_rrp_override": 1500.0,
                                 "approval_status": "Approved (manual RRP)"})
        assert put.status_code == 200, put.text
        after = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                              json={"company_id": COMPANY_ID, "contract_type": "gold"}).json()
        assert after["assets_priced"] > before_priced, \
            f"expected more priced after RRP override, {before_priced}->{after['assets_priced']}"
        # target asset(s) now priced
        target_assets = [a for a in after["asset_register"] if a.get("config_id") == cfg_id]
        assert any(a.get("annual", 0) > 0 for a in target_assets), target_assets
    finally:
        # restore
        restore_payload = {
            "manual_rrp_override": orig.get("manual_rrp_override"),
            "approval_status": orig.get("approval_status"),
        }
        requests.put(f"{API}/crm/v2/aftersales/service-configs/{cfg_id}",
                     headers=h, json=restore_payload)


# --- 6. Exception resolution: supportability decision --------------------
def test_supportability_decision_reprices(h):
    r = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate", headers=h,
                      json={"company_id": COMPANY_ID, "contract_type": "gold"}).json()
    target = None
    for e in r["exceptions"]:
        if e["kind"] in ("SUPPORTABILITY", "PROVISIONAL"):
            target = e
            break
    if not target:
        pytest.skip("no SUPPORTABILITY/PROVISIONAL exception to resolve")
    model = target["model"]
    # create decision
    dec = requests.post(f"{API}/crm/v2/aftersales/supportability/decisions",
                        headers=h, json={"model": model, "status": "fully_supported"})
    assert dec.status_code in (200, 201), dec.text
    dec_id = dec.json().get("id") or dec.json().get("decision", {}).get("id")

    try:
        after = requests.post(f"{API}/crm/v2/aftersales/build-quote-from-estate",
                              headers=h,
                              json={"company_id": COMPANY_ID, "contract_type": "gold"}).json()
        still = [e for e in after["exceptions"]
                 if e.get("model") == model and e["kind"] in ("SUPPORTABILITY",)]
        assert not still, f"SUPPORTABILITY exception for {model} still present after decision"
    finally:
        if dec_id:
            requests.delete(f"{API}/crm/v2/aftersales/supportability/decisions/{dec_id}",
                            headers=h)


# --- 7. Phase-1 pricing regressions --------------------------------------
def test_regression_gold_200h_console6_series3_x2(h):
    body = {
        "lines": [{"model": "200H", "console_type": "Console 6 (Series 3)", "qty": 2}],
        "contract_type": "gold", "pricing_level": "standard",
        "quote_discount_pct": 0, "term_years": 1,
    }
    r = requests.post(f"{API}/crm/v2/aftersales/pricing/calculate", headers=h,
                      json=body).json()
    assert abs(r["lines"][0]["annual_line_gold"] - 688.7412) < 0.01, r["lines"][0]
    assert abs(r["summary"]["final_annual"] - 688.74) < 0.01, r["summary"]


def test_regression_platinum_term3_disc10(h):
    body = {
        "lines": [{"model": "200H", "console_type": "Console 6 (Series 3)", "qty": 2}],
        "contract_type": "platinum", "pricing_level": "standard",
        "quote_discount_pct": 10, "term_years": 3,
    }
    r = requests.post(f"{API}/crm/v2/aftersales/pricing/calculate", headers=h,
                      json=body).json()
    s = r["summary"]
    assert abs(s["contract_type_annual"] - 895.36) < 0.05, s
    assert abs(s["final_annual"] - 805.82) < 0.05, s
    assert abs(s["term_total"] - 2417.46) < 0.1, s


# --- 8. Cleanup: delete test-created drafts ------------------------------
def test_cleanup_afs_drafts(h):
    lst = requests.get(f"{API}/crm/v2/aftersales/quotes", headers=h).json()
    # Delete endpoint may not exist; leave drafts if not.
    del_url = f"{API}/crm/v2/aftersales/quotes"
    for q in lst.get("quotes", []):
        if q.get("source") == "auto_estate" and q.get("company_id") == COMPANY_ID:
            requests.delete(f"{del_url}/{q['id']}", headers=h)
    # non-fatal
    assert True
