"""Iteration 314 — retest of iter313 fixes (public URL). Run after `mm_ui_seed.py seed`.
Real upload e7a84748 is only READ (never committed)."""
from tests._paths import REPO  # noqa: E402
import os
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    open(REPO + "/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
MM = f"{BASE}/api/crm/v2/aftersales/maintenance-master"
REAL = "e7a84748-9c0d-4415-ba64-d66c621d3dae"
PW = "CmTest2026!"


def _login(email):
    r = requests.post(f"{BASE}/api/crm/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def coord():
    return _login("cm.coordinator@pulsefitness.test")


@pytest.fixture(scope="module")
def mgr():
    return _login("cm.aftersales@pulsefitness.test")


@pytest.fixture(scope="module")
def seed_uid(coord):
    ups = requests.get(f"{MM}/uploads", headers=coord, timeout=30).json()["uploads"]
    u = next((u for u in ups if u["filename"].startswith("mmt_ui")), None)
    if not u:
        pytest.skip("seed upload missing")
    return u["id"]


# Route order: /contracts/workspace must return 200
def test_contracts_workspace_200(mgr):
    r = requests.get(f"{BASE}/api/crm/v2/contracts/workspace", headers=mgr, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert isinstance(r.json(), dict)


# Issue filter 'contract number missing' -> only truly missing numbers (786 on the real upload)
def test_real_missing_number_filter(coord):
    r = requests.get(f"{MM}/uploads/{REAL}/rows", headers=coord,
                     params={"unresolved": "true", "issue": "contract number missing"}, timeout=60)
    assert r.status_code == 200
    d = r.json()
    print("missing number", d["count"])
    assert d["count"] == 786
    assert all(any("contract number missing" in p.lower() for p in x["problems"]) for x in d["rows"])


# Skip ('Do not import') -> class skipped, counted in counts.skipped not new_contract; reset restores
def test_skip_classed_skipped(mgr, seed_uid):
    before = requests.get(f"{MM}/uploads/{seed_uid}", headers=mgr).json()["summary"]["counts"]
    dups = requests.get(f"{MM}/uploads/{seed_uid}/rows", headers=mgr, params={"cls": "duplicate_overlap"}).json()["rows"]
    assert len(dups) == 2
    rid = dups[0]["id"]
    r = requests.post(f"{MM}/uploads/{seed_uid}/rows/{rid}/decision", headers=mgr, json={"action": "skip", "note": "TEST_ skip"})
    assert r.status_code == 200, r.text
    time.sleep(1)
    u = requests.get(f"{MM}/uploads/{seed_uid}", headers=mgr).json()
    counts = u["summary"]["counts"]
    print("before", before, "after skip", counts)
    row = requests.get(f"{MM}/uploads/{seed_uid}/rows/{rid}", headers=mgr).json()
    assert row["cls"] == "skipped"
    assert counts["skipped"] == before.get("skipped", 0) + 1
    # the other duplicate becomes a new contract (no longer duplicated) - skipped row not counted as new
    assert counts["new_contract"] + counts["duplicate_overlap"] + counts["skipped"] == \
        before["new_contract"] + before["duplicate_overlap"] + before.get("skipped", 0)
    assert counts["new_contract"] <= before["new_contract"] + 1
    r = requests.post(f"{MM}/uploads/{seed_uid}/rows/{rid}/decision", headers=mgr, json={"action": "reset", "note": "TEST_ undo"})
    assert r.status_code == 200, r.text
    time.sleep(1)
    after = requests.get(f"{MM}/uploads/{seed_uid}", headers=mgr).json()["summary"]["counts"]
    assert after == before, (after, before)


# Invoice run: no blank-contract rows, orphans counted in excluded_not_live
@pytest.mark.parametrize("period", ["2026-11", "2026-12"])
def test_invoice_run_excludes_orphans(mgr, period):
    r = requests.get(f"{MM}/invoice-run", headers=mgr, params={"period": period}, timeout=60)
    assert r.status_code == 200
    d = r.json()
    print(period, d["totals"], [(x["contract_number"], x["amount"], x["status"]) for x in d["rows"]])
    assert all(x["contract_number"] for x in d["rows"]), "blank-contract rows proposed"
    assert all(x["customer"] for x in d["rows"])
    assert "excluded_not_live" in d["totals"]
    assert d["totals"]["excluded_not_live"] > 0


# Daily view: service_attention only counts live contracts; items carry contract_number/customer
def test_daily_service_attention(coord):
    d = requests.get(f"{MM}/daily", headers=coord, timeout=60).json()
    sa = d["cards"]["service_attention"]
    print("service_attention", sa["count"], sa["items"][:3], "coords", d["coordinators"])
    assert sa["count"] < 107
    for it in sa["items"]:
        assert it.get("contract_number") and it.get("id")
    for k in d["coordinators"][:2]:
        r = requests.get(f"{MM}/daily", headers=coord, params={"coordinator": k}).json()
        assert r["cards"]["service_attention"]["count"] <= sa["count"]
    r = requests.get(f"{MM}/daily", headers=coord, params={"coordinator": "ZZZ_nobody"}).json()
    assert r["cards"]["service_attention"]["count"] == 0
    assert all(c["count"] == 0 for k, c in r["cards"].items() if k != "import_exceptions")


# Post-commit (needs committed seed + TEST_ service schedule on MMT-1001): items carry contract_number; coordinator filter
def test_post_commit_daily_and_invoice(mgr):
    cs = requests.get(f"{MM}/contracts", headers=mgr, params={"q": "MMT-1001"}).json()["contracts"]
    if not cs:
        pytest.skip("seed not committed")
    d = requests.get(f"{MM}/daily", headers=mgr).json()["cards"]["service_attention"]
    print(d)
    assert d["count"] >= 1 and all(i["contract_number"] and i["customer"] for i in d["items"])
    z = requests.get(f"{MM}/daily", headers=mgr, params={"coordinator": "ZZZ_nobody"}).json()["cards"]["service_attention"]
    assert z["count"] == 0
    inv = requests.get(f"{MM}/invoice-run", headers=mgr, params={"period": "2026-12"}).json()
    a = [r for r in inv["rows"] if r["contract_number"] == "MMT-1001"]
    assert a and a[0]["amount"] == 1500 and a[0]["status"] == "proposed"
    assert all(r["contract_number"] for r in inv["rows"])
    full = requests.get(f"{MM}/contracts/{cs[0]['id']}", headers=mgr).json()["contract"]
    print("sicon", full.get("sicon_sync"))
    assert full["sicon_sync"]["state"] in ("held_for_sicon", "held_writes_disabled")
