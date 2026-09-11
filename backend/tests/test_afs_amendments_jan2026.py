"""Backend tests for Aftersales mid-term amendments (Task 5).

Covers: amendable-assets listing, preview (no-write), apply add, apply remove
(regression: previous pro-rata line preserved), validation errors, and history.

Contract under test: AFSCOMPLDEMO-contract-1 (AlphaCo Site A, gold, monthly,
annual 4200, 6 monthly invoices £350, 2x 260G covered).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
CID = "AFSCOMPLDEMO-contract-1"
EFF = "2026-09-11"

CRM_EMAIL = "owner@isodemo.com"
CRM_PWD = "IsoDemo123!"


# ─── auth ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{API}/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PWD}, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, "No token in CRM login response"
    return tok


@pytest.fixture(scope="module")
def client(crm_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {crm_token}",
                      "Content-Type": "application/json"})
    return s


# ─── amendable-assets ────────────────────────────────────────────────────
def test_amendable_assets_baseline(client):
    r = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    ct = data["contract"]
    assert ct["annual_value"] == 4200 or round(ct["annual_value"], 2) == 4200.00, \
        f"expected baseline annual 4200, got {ct['annual_value']}"
    assert ct["billing_frequency"] == "monthly"
    assert ct["next_anniversary"], "next_anniversary must be present"
    covered = data["covered"]
    coverable = data["coverable"]
    assert len(covered) == 2, f"expected 2 covered assets, got {len(covered)}"
    # 260G covered @ 446.40
    for a in covered:
        assert round(a["annual"], 2) == 446.40, f"covered price mismatch: {a}"
    assert len(coverable) >= 10, f"expected many coverable, got {len(coverable)}"
    # There should be 220G items at 277.14
    g220 = [a for a in coverable if round(a["annual"], 2) == 277.14]
    assert len(g220) >= 2, f"expected >=2 220G @ £277.14 in coverable, got {len(g220)}"


@pytest.fixture(scope="module")
def two_220g_ids(client):
    r = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30)
    coverable = r.json()["coverable"]
    ids = [a["asset_id"] for a in coverable if round(a["annual"], 2) == 277.14][:2]
    assert len(ids) == 2
    return ids


# ─── preview (no writes) ──────────────────────────────────────────────────
def test_preview_add_two_220g_no_writes(client, two_220g_ids):
    body = {"action": "add", "asset_ids": two_220g_ids, "effective_date": EFF}
    r1 = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments/preview",
                     json=body, timeout=30)
    assert r1.status_code == 200, r1.text
    d = r1.json()
    assert round(d["delta_annual"], 2) == 554.27, f"delta_annual={d['delta_annual']}"
    assert d["current_annual"] == 4200
    assert round(d["new_annual"], 2) == 4754.27
    # pro-rata ~ 554.27 * days/365 ; sanity: 0 < pro_rata < delta
    assert 0 < d["pro_rata_amount"] < d["delta_annual"]
    # Second preview must be idempotent (no writes)
    r2 = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments/preview",
                     json=body, timeout=30)
    assert r2.status_code == 200
    # Contract untouched
    ck = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30).json()
    assert ck["contract"]["annual_value"] == 4200, "preview must NOT mutate contract"
    assert len(ck["covered"]) == 2, "preview must NOT mutate cover"


# ─── validation errors ───────────────────────────────────────────────────
def test_preview_empty_asset_ids_400(client):
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments/preview",
                    json={"action": "add", "asset_ids": [], "effective_date": EFF}, timeout=30)
    assert r.status_code == 400


def test_preview_bad_action_400(client, two_220g_ids):
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments/preview",
                    json={"action": "swap", "asset_ids": two_220g_ids,
                          "effective_date": EFF}, timeout=30)
    assert r.status_code == 400


def test_preview_invalid_asset_ids_400(client):
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments/preview",
                    json={"action": "add", "asset_ids": ["not-a-real-id-xyz"],
                          "effective_date": EFF}, timeout=30)
    assert r.status_code == 400
    assert "valid" in r.text.lower() or "none" in r.text.lower()


# ─── apply ADD ───────────────────────────────────────────────────────────
def test_apply_add_two_220g(client, two_220g_ids):
    body = {"action": "add", "asset_ids": two_220g_ids, "effective_date": EFF}
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments",
                    json=body, timeout=60)
    assert r.status_code == 200, r.text
    resp = r.json()
    assert round(resp["new_annual_value"], 2) == 4754.27
    pro_rata_add = resp["pro_rata_amount"]
    assert pro_rata_add > 0

    # Verify contract state
    ck = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30).json()
    assert round(ck["contract"]["annual_value"], 2) == 4754.27
    covered_ids = {a["asset_id"] for a in ck["covered"]}
    assert set(two_220g_ids).issubset(covered_ids), "added assets should now be covered"
    assert len(ck["covered"]) == 4

    # Verify billing: future unpaid regenerated to new_annual/12; pro_rata_amendment line present
    sched = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/schedules", timeout=30).json()
    invs = sched["billing"]
    pro_rata_lines = [i for i in invs if i.get("type") == "pro_rata_amendment"]
    assert len(pro_rata_lines) == 1, f"expected 1 pro-rata line, got {len(pro_rata_lines)}"
    assert round(pro_rata_lines[0]["amount"], 2) == round(pro_rata_add, 2)
    # Paid past invoices remain at £350
    paid = [i for i in invs if i.get("status") == "paid"]
    assert paid, "should have paid invoices"
    for p in paid:
        assert round(p["amount"], 2) == 350.00, f"paid should stay at 350, got {p}"
    # Future scheduled non-pro-rata regenerated to 4754.27/12 = 396.19
    new_monthly = round(4754.27 / 12.0, 2)
    future_reg = [i for i in invs if i.get("status") != "paid"
                  and i.get("type") != "pro_rata_amendment"
                  and (i.get("due_date") or "") >= EFF]
    assert future_reg, "should have future regenerated invoices"
    for f in future_reg:
        assert round(f["amount"], 2) == new_monthly, \
            f"future should be {new_monthly}, got {f}"


# ─── apply REMOVE — regression: pro_rata_amendment stays intact ─────────
def test_apply_remove_preserves_prior_pro_rata(client):
    # Grab a covered 260G id
    ck = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30).json()
    g260 = [a for a in ck["covered"] if round(a["annual"], 2) == 446.40]
    assert g260, "no 260G covered found for removal"
    target = g260[0]["asset_id"]

    # capture existing pro_rata_amendment line
    sched_before = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/schedules", timeout=30).json()
    prior_pro = [i for i in sched_before["billing"] if i.get("type") == "pro_rata_amendment"]
    assert len(prior_pro) == 1
    prior_amt = round(prior_pro[0]["amount"], 2)
    prior_due = prior_pro[0]["due_date"]

    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments",
                    json={"action": "remove", "asset_ids": [target],
                          "effective_date": EFF}, timeout=60)
    assert r.status_code == 200, r.text
    resp = r.json()
    # annual decreased by 446.40
    assert round(resp["new_annual_value"], 2) == round(4754.27 - 446.40, 2)
    assert resp["pro_rata_amount"] < 0, "remove should produce NEGATIVE credit"

    # Removed machine → moved back to coverable
    ck2 = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30).json()
    covered_ids = {a["asset_id"] for a in ck2["covered"]}
    coverable_ids = {a["asset_id"] for a in ck2["coverable"]}
    assert target not in covered_ids
    assert target in coverable_ids

    # CRITICAL REGRESSION: prior pro_rata_amendment line must be unchanged
    sched_after = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/schedules", timeout=30).json()
    pro_lines = [i for i in sched_after["billing"] if i.get("type") == "pro_rata_amendment"]
    assert len(pro_lines) == 2, f"should have 2 pro_rata lines (prev add + new remove), got {len(pro_lines)}"
    matches = [l for l in pro_lines if l["due_date"] == prior_due and round(l["amount"], 2) == prior_amt]
    assert matches, f"prior pro-rata line ({prior_amt}) must be preserved unchanged; got {pro_lines}"
    # And there's a NEW negative pro-rata line
    neg = [l for l in pro_lines if l["amount"] < 0]
    assert neg, "expected a negative pro-rata credit line"


# ─── apply validation errors ─────────────────────────────────────────────
def test_apply_empty_ids_400(client):
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments",
                    json={"action": "add", "asset_ids": [], "effective_date": EFF}, timeout=30)
    assert r.status_code == 400


def test_apply_wrong_action_400(client, two_220g_ids):
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments",
                    json={"action": "delete", "asset_ids": two_220g_ids,
                          "effective_date": EFF}, timeout=30)
    assert r.status_code == 400


def test_apply_remove_uncovered_id_400(client, two_220g_ids):
    # These 220G ids WERE added earlier; they are now covered — but let's use a truly uncovered id.
    ck = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendable-assets", timeout=30).json()
    if not ck["coverable"]:
        pytest.skip("no uncovered asset available")
    uncov = ck["coverable"][0]["asset_id"]
    r = client.post(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments",
                    json={"action": "remove", "asset_ids": [uncov],
                          "effective_date": EFF}, timeout=30)
    assert r.status_code == 400


# ─── history ─────────────────────────────────────────────────────────────
def test_history_newest_first(client):
    r = client.get(f"{API}/crm/v2/aftersales/contracts/{CID}/amendments", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 2
    rows = data["amendments"]
    actions = [row["action"] for row in rows[:2]]
    assert actions[0] == "remove" and actions[1] == "add", f"newest first order wrong: {actions}"
    for row in rows:
        for k in ("delta_annual", "pro_rata_amount", "previous_annual",
                  "new_annual", "asset_ids", "effective_date"):
            assert k in row, f"missing field {k} in history row"
