"""Iter 216h128 — Pulse Sales (CAPEX-sourced internal pipeline).

Verifies tenant isolation, lifecycle, sweep idempotency, and update API.
"""
import os
import uuid

import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or
       "https://service-ops-hub-6.preview.emergentagent.com").rstrip("/")


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def test_pulse_sales_blocks_non_admin():
    """Customer-tier users must NOT be able to read internal Pulse opps."""
    jack = _login("jack.ottey@thirdspace.london", "Test123!")
    r = requests.get(f"{API}/api/pulse-sales/opportunities",
                     headers=_hdr(jack), timeout=20)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


def test_pulse_sales_blocks_anonymous():
    r = requests.get(f"{API}/api/pulse-sales/opportunities", timeout=20)
    assert r.status_code in (401, 403), r.status_code


def test_pulse_sales_sweep_and_list():
    """Master admin can run the sweep and read back the opportunity list."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    sweep = requests.post(f"{API}/api/pulse-sales/sweep-capex",
                          headers=_hdr(tok), timeout=120)
    assert sweep.status_code == 200, sweep.text
    res = sweep.json().get("result", {})
    assert res.get("orgs_scanned", 0) >= 1, res
    assert res.get("errors", 1) == 0, res

    listing = requests.get(f"{API}/api/pulse-sales/opportunities",
                           headers=_hdr(tok), timeout=30)
    assert listing.status_code == 200
    opps = listing.json().get("opportunities", [])
    assert len(opps) > 0, "no opportunities returned"
    sample = opps[0]
    for k in ("id", "organization_id", "organization_name", "equipment_id",
              "equipment_name", "capex_status", "capex_score",
              "replacement_cost", "severity_signal", "status",
              "auto_dismiss_at"):
        assert k in sample, f"missing key {k}"
    assert sample["source"] == "capex.scan"


def test_pulse_sales_summary_shape():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/pulse-sales/summary",
                     headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("by_status", "by_severity", "active_pipeline_value", "top_orgs"):
        assert k in j, f"missing summary key {k}"
    for st in ("new", "contacted", "qualified", "won", "lost", "dismissed"):
        assert st in j["by_status"]


def test_pulse_sales_patch_status_and_note():
    """Updating an opportunity persists status, assignee, and notes."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    list_r = requests.get(f"{API}/api/pulse-sales/opportunities?limit=5",
                          headers=_hdr(tok), timeout=20)
    opps = list_r.json()["opportunities"]
    if not opps:
        import pytest
        pytest.skip("no opportunities seeded")
    opp_id = opps[0]["id"]
    note_text = f"automated test note {uuid.uuid4().hex[:6]}"
    r = requests.patch(
        f"{API}/api/pulse-sales/opportunities/{opp_id}",
        headers=_hdr(tok), timeout=20,
        json={"status": "qualified", "assigned_to": "sales@pulsefitness.com",
              "note": note_text},
    )
    assert r.status_code == 200, r.text
    fresh = r.json()["opportunity"]
    assert fresh["status"] == "qualified"
    assert fresh["assigned_to"] == "sales@pulsefitness.com"
    assert any(n["text"] == note_text for n in fresh.get("notes", []))


def test_pulse_sales_invalid_status_rejected():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    list_r = requests.get(f"{API}/api/pulse-sales/opportunities?limit=1",
                          headers=_hdr(tok), timeout=20)
    opps = list_r.json()["opportunities"]
    if not opps:
        import pytest
        pytest.skip("no opps")
    opp_id = opps[0]["id"]
    r = requests.patch(
        f"{API}/api/pulse-sales/opportunities/{opp_id}",
        headers=_hdr(tok), timeout=20,
        json={"status": "garbage"},
    )
    assert r.status_code == 400, r.text


def test_pulse_sales_sweep_idempotent():
    """Two sweeps in a row should not re-create rows — only update them."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    first = requests.post(f"{API}/api/pulse-sales/sweep-capex",
                          headers=_hdr(tok), timeout=120).json()["result"]
    second = requests.post(f"{API}/api/pulse-sales/sweep-capex",
                           headers=_hdr(tok), timeout=120).json()["result"]
    # Second pass should produce 0 new rows for the same data state.
    assert second["created"] == 0, second
    # And the same number of orgs should be scanned.
    assert second["orgs_scanned"] == first["orgs_scanned"]


def test_pulse_sales_scope_is_pulse_and_mod_only():
    """Top-orgs returned should only be Pulse Pro or MOD tenants — never
    a generic GymAxis-scoped org."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/pulse-sales/summary",
                     headers=_hdr(tok), timeout=20)
    top = r.json().get("top_orgs", [])
    allowed = {"pulse_pro", "mod_site", "mod_branch", "mod_org"}
    for o in top:
        assert o["account_type"] in allowed, (
            f"unexpected tenant in Pulse Sales scope: {o}"
        )
