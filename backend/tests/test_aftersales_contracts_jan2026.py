"""
Aftersales Contract Automation Engine — Backend Tests
Tests /api/crm/v2/aftersales/* endpoints via CRM token.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
AFS = f"{API}/crm/v2/aftersales"

CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{API}/crm/auth/login", json={"email": CRM_EMAIL, "password": CRM_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def h(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


# ── Ruleset / Packages / Config Stats / Wording ──────────────────────────────

def test_ruleset(h):
    r = requests.get(f"{AFS}/ruleset", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d.get("rate_groups", [])) == 7, f"rate_groups={len(d.get('rate_groups', []))}"
    cts = {c.get("code") or c.get("name", "").lower(): c for c in d.get("contract_types", [])}
    # Look for silver/gold/platinum
    def _find(name):
        for c in d["contract_types"]:
            n = (c.get("code") or c.get("name") or "").lower()
            if name in n:
                return c
        return None
    silver = _find("silver"); gold = _find("gold"); plat = _find("platinum")
    assert silver and gold and plat
    def _adj(c):
        return c.get("pricing_factor") or c.get("adjustment_factor") or c.get("factor") or c.get("multiplier")
    assert abs(float(_adj(silver)) - 0.8) < 0.001, silver
    assert abs(float(_adj(gold)) - 1.0) < 0.001, gold
    assert abs(float(_adj(plat)) - 1.3) < 0.001, plat
    assert len(d.get("console_rules", [])) > 0


def test_packages(h):
    r = requests.get(f"{AFS}/packages", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    pkgs = d if isinstance(d, list) else d.get("packages", [])
    codes = {(p.get("code") or p.get("key") or "").lower() for p in pkgs}
    assert {"silver", "gold", "platinum"}.issubset(codes), codes


def test_service_config_stats(h):
    r = requests.get(f"{AFS}/service-configs/stats", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("total") == 490, d
    assert d.get("eligible") == 453, d


def test_wording_conflicts(h):
    r = requests.get(f"{AFS}/wording-conflicts", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    items = d if isinstance(d, list) else d.get("items", d.get("conflicts", []))
    unresolved = [c for c in items if not c.get("resolved")]
    assert len(unresolved) >= 1
    assert any("carriage" in (c.get("text","")+c.get("description","")+c.get("title","")).lower() or "platinum" in str(c).lower() for c in unresolved)


# ── Deterministic Pricing Engine (CRITICAL) ──────────────────────────────────

def test_pricing_gold_200h_series3_qty2(h):
    payload = {
        "lines": [{"model": "200H", "console_type": "Console 6 (Series 3)", "qty": 2}],
        "contract_type": "gold",
    }
    r = requests.post(f"{AFS}/pricing/calculate", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    line = d["lines"][0]
    assert abs(line["annual_unit_gold"] - 344.3706) < 0.001, line
    assert abs(line["annual_line_gold"] - 688.7412) < 0.001, line
    s = d["summary"]
    assert abs(s["gold_base_annual"] - 688.74) < 0.02, s
    assert abs(s["final_annual"] - 688.74) < 0.02, s
    assert abs(s["monthly"] - 57.40) < 0.05, s


def test_pricing_platinum_3yr_discount10(h):
    payload = {
        "lines": [{"model": "200H", "console_type": "Console 6 (Series 3)", "qty": 2}],
        "contract_type": "platinum",
        "term_years": 3,
        "quote_discount_pct": 10,
    }
    r = requests.post(f"{AFS}/pricing/calculate", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    s = d["summary"]
    assert abs(s["gold_base_annual"] - 688.74) < 0.02, s
    assert abs(s["contract_type_annual"] - 895.36) < 0.02, s
    assert abs(s["final_annual"] - 805.82) < 0.02, s
    assert abs(s["term_total"] - 2417.46) < 0.05, s
    assert d.get("quote_health") == "REVIEW_REQUIRED", d.get("quote_health")
    reasons = " ".join(d.get("reasons", []) + d.get("issues", []) + d.get("health_reasons", [])).lower()
    assert "discount" in reasons or "approval" in reasons, d


def test_pricing_legacy_no_rrp_manual_required(h):
    payload = {
        "lines": [{"model": "200C", "console_type": "Console 6 (Series 3)", "qty": 1}],
        "contract_type": "gold",
    }
    r = requests.post(f"{AFS}/pricing/calculate", headers=h, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    line = d["lines"][0]
    assert line.get("annual_line_gold", 0) == 0, line
    assert d.get("quote_health") in ("REVIEW_REQUIRED", "BLOCKED"), d.get("quote_health")
    reasons = " ".join(d.get("reasons", []) + d.get("issues", []) + d.get("health_reasons", []) + [line.get("reason","")]).lower()
    assert "manual" in reasons and "rrp" in reasons, d


# ── Versioning ───────────────────────────────────────────────────────────────

def _versions_count(h):
    r = requests.get(f"{AFS}/versions", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return len(d if isinstance(d, list) else d.get("versions", []))

def test_version_increments_on_contract_type_update(h):
    r = requests.get(f"{AFS}/ruleset", headers=h, timeout=30).json()
    plat = None
    for c in r["contract_types"]:
        if "platinum" in (c.get("key") or c.get("code") or c.get("name") or "").lower():
            plat = c; break
    assert plat, "platinum not found"
    pid = plat["id"]
    orig = plat["pricing_factor"]
    before = _versions_count(h)
    up = requests.put(f"{AFS}/contract-types/{pid}", headers=h, json={"pricing_factor": 1.31}, timeout=30)
    assert up.status_code in (200, 204), up.text
    after = _versions_count(h)
    assert after > before, f"versions did not increment: {before} -> {after}"
    # restore
    requests.put(f"{AFS}/contract-types/{pid}", headers=h, json={"pricing_factor": orig}, timeout=30)


def test_version_increments_on_rate_group_update(h):
    r = requests.get(f"{AFS}/ruleset", headers=h, timeout=30).json()
    rg = r["rate_groups"][0]
    rid = rg["id"]
    orig = rg["standard_pct"]
    before = _versions_count(h)
    up = requests.put(f"{AFS}/rate-groups/{rid}", headers=h, json={"standard_pct": orig + 0.001}, timeout=30)
    assert up.status_code in (200, 204), up.text
    after = _versions_count(h)
    assert after > before, f"versions did not increment: {before} -> {after}"
    requests.put(f"{AFS}/rate-groups/{rid}", headers=h, json={"standard_pct": orig}, timeout=30)


# ── Supportability ───────────────────────────────────────────────────────────

def test_supportability_statuses(h):
    r = requests.get(f"{AFS}/supportability/statuses", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    items = d if isinstance(d, list) else d.get("statuses") or d.get("items", [])
    assert len(items) == 6, items


def test_supportability_evaluate_200c_manual_review(h):
    r = requests.post(f"{AFS}/supportability/evaluate", headers=h, json={"model": "200C"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("status") == "manual_review", d


def test_supportability_decision_memory_and_delete(h):
    model = "200C"
    # Record decision (valid status id)
    r = requests.post(
        f"{AFS}/supportability/decisions",
        headers=h,
        json={"model": model, "status": "fully_supported", "reason": "TEST_ jan2026"},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    did = r.json().get("id") or r.json().get("_id")
    assert did

    # Evaluate → source decision_memory
    ev = requests.post(f"{AFS}/supportability/evaluate", headers=h, json={"model": model}, timeout=30)
    assert ev.status_code == 200
    assert ev.json().get("source") == "decision_memory", ev.json()

    # Delete
    dl = requests.delete(f"{AFS}/supportability/decisions/{did}", headers=h, timeout=30)
    assert dl.status_code in (200, 204), dl.text


# ── Dashboard / Priorities ───────────────────────────────────────────────────

def test_dashboard_cards(h):
    r = requests.get(f"{AFS}/dashboard", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # Look for ACV and active contracts anywhere in payload
    flat = str(d)
    assert "165000" in flat.replace(",", "") or d.get("annual_contract_value") == 165000, d
    active = d.get("active_contracts")
    if active is None:
        # Search nested
        for v in d.values():
            if isinstance(v, dict) and v.get("active_contracts") == 1:
                active = 1; break
    assert active == 1 or "1" in str(d.get("cards", "")), d


def test_priorities_ok(h):
    r = requests.get(f"{AFS}/priorities", headers=h, timeout=30)
    assert r.status_code == 200, r.text
