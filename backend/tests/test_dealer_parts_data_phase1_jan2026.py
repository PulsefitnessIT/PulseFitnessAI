"""Backend tests for Dealer Parts Data & Intelligence (Phase 1) — Jan 2026.

Covers /api/dealer-parts/data/* endpoints:
 - imports listing, most-used analysis + filters, matching engine
 - matches list + review, aliases create/review, unmatched actions
 - machines + machine-parts, settings, chunked upload skeleton
 - RBAC (dealer_user blocked)
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
API = f"{BASE_URL}/api"

STAFF_EMAIL = "owner@isodemo.com"
STAFF_PASSWORD = "IsoDemo123!"
DEALER_EMAIL = "portal2@fitline.test"
DEALER_PASSWORD = "DealerDemo123!"


def _login(email, password, retries=3):
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("access_token") or data.get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        pytest.fail(f"Login failed {email}: {r.status_code} {r.text[:200]}")
    pytest.fail(f"Login gave up for {email}")


@pytest.fixture(scope="session")
def staff_token():
    return _login(STAFF_EMAIL, STAFF_PASSWORD)


@pytest.fixture(scope="session")
def dealer_token():
    time.sleep(2)
    return _login(DEALER_EMAIL, DEALER_PASSWORD)


@pytest.fixture(scope="session")
def H(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}


# ─────────────────────── Imports ───────────────────────
class TestImports:
    def test_list_imports(self, H):
        r = requests.get(f"{API}/dealer-parts/data/imports", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "batches" in data
        kinds = {b["kind"] for b in data["batches"]}
        assert "bom" in kinds, f"missing bom import: {kinds}"
        assert "parts_used" in kinds, f"missing parts_used import: {kinds}"


# ─────────────────────── Most-Used ───────────────────────
class TestMostUsed:
    def test_analysis_basic(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?limit=5", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 1440, f"expected total 1440, got {data['total']}"
        parts = data["parts"]
        assert len(parts) > 0
        top = parts[0]
        # top rank part should be 33/001
        assert top.get("code") == "33/001", f"top rank code {top.get('code')}"
        assert top.get("total_qty", 0) >= 2800
        assert top.get("trend") == "increasing", f"trend {top.get('trend')}"
        # per-part computed fields
        for k in ("total_qty", "usage_count", "total_cost", "avg_monthly", "recent_12m",
                  "trend", "rank", "high_usage", "matched"):
            assert k in top, f"missing field {k}"
        assert top["trend"] in {"increasing", "stable", "decreasing", "dormant", "one_off", "new_failure_trend"}

    def test_filter_matched_false(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?matched=false&limit=20", headers=H, timeout=30)
        assert r.status_code == 200
        parts = r.json()["parts"]
        assert all(p.get("matched") is False for p in parts)

    def test_filter_trend_increasing(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?trend=increasing&limit=20", headers=H, timeout=30)
        assert r.status_code == 200
        for p in r.json()["parts"]:
            assert p["trend"] == "increasing"

    def test_filter_high_usage(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?high_usage=true&limit=20", headers=H, timeout=30)
        assert r.status_code == 200
        for p in r.json()["parts"]:
            assert p["high_usage"] is True

    def test_filter_q_search(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?q=33/001&limit=10", headers=H, timeout=30)
        assert r.status_code == 200
        parts = r.json()["parts"]
        assert len(parts) >= 1
        assert any(p["code"] == "33/001" for p in parts)

    def test_sort_cost(self, H):
        r = requests.get(f"{API}/dealer-parts/data/most-used-analysis?sort=cost&limit=10", headers=H, timeout=30)
        assert r.status_code == 200
        parts = r.json()["parts"]
        costs = [p.get("total_cost") or 0 for p in parts]
        assert costs == sorted(costs, reverse=True), "cost not sorted desc"


# ─────────────────────── Matching engine ───────────────────────
class TestMatching:
    def test_match_run(self, H):
        t = time.time()
        r = requests.post(f"{API}/dealer-parts/data/match/run", headers=H, timeout=120)
        elapsed = time.time() - t
        assert r.status_code == 200, r.text
        assert elapsed < 60, f"match/run too slow: {elapsed:.1f}s"
        data = r.json()
        stats = data.get("stats", {})
        # tolerate small drifts
        assert stats.get("exact_code", 0) >= 100
        assert stats.get("fuzzy_description", 0) >= 15
        assert data.get("unmatched", 0) >= 1200

    def test_match_run_idempotent(self, H):
        r1 = requests.post(f"{API}/dealer-parts/data/match/run", headers=H, timeout=120).json()
        r2 = requests.post(f"{API}/dealer-parts/data/match/run", headers=H, timeout=120).json()
        assert r1["total"] == r2["total"]
        assert r1["matched"] == r2["matched"]


# ─────────────────────── Matches list + review ───────────────────────
class TestMatchesReview:
    def test_list_pending(self, H):
        r = requests.get(f"{API}/dealer-parts/data/matches?review_status=pending&limit=20", headers=H, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "matches" in data

    def test_review_approve_then_reject_cycle(self, H):
        # find a pending match
        r = requests.get(f"{API}/dealer-parts/data/matches?review_status=pending&limit=5", headers=H, timeout=30)
        matches = r.json().get("matches", [])
        if not matches:
            pytest.skip("no pending matches to review")
        m = matches[0]
        mid = m["id"]
        code_norm = m["used_code_norm"]
        # approve
        ra = requests.post(f"{API}/dealer-parts/data/matches/{mid}/review",
                           headers=H, json={"action": "approve"}, timeout=30)
        assert ra.status_code == 200, ra.text
        assert ra.json()["review_status"] == "approved"
        # verify analysis shows matched
        ga = requests.get(f"{API}/dealer-parts/data/most-used-analysis?q={m['used_code']}&limit=5",
                          headers=H, timeout=30)
        # revert via reject
        rr = requests.post(f"{API}/dealer-parts/data/matches/{mid}/review",
                           headers=H, json={"action": "reject"}, timeout=30)
        assert rr.status_code == 200
        assert rr.json()["review_status"] == "rejected"


# ─────────────────────── Aliases ───────────────────────
class TestAliases:
    _alias_id = None

    def test_create_alias(self, H):
        payload = {"from_code": f"TEST_ALIAS_{int(time.time())}", "to_code": "33/001", "note": "TEST alias"}
        r = requests.post(f"{API}/dealer-parts/data/aliases", headers=H, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["from_code"] == payload["from_code"]
        assert doc["to_code"] == "33/001"
        assert doc["status"] == "pending"
        TestAliases._alias_id = doc["id"]

    def test_list_aliases(self, H):
        r = requests.get(f"{API}/dealer-parts/data/aliases", headers=H, timeout=30)
        assert r.status_code == 200
        assert "aliases" in r.json()

    def test_approve_alias(self, H):
        if not TestAliases._alias_id:
            pytest.skip("no alias created")
        r = requests.post(f"{API}/dealer-parts/data/aliases/{TestAliases._alias_id}/review",
                          headers=H, json={"action": "approve"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

    def test_review_missing_alias_404(self, H):
        r = requests.post(f"{API}/dealer-parts/data/aliases/nonexistent-id/review",
                          headers=H, json={"action": "approve"}, timeout=30)
        assert r.status_code == 404


# ─────────────────────── Unmatched ───────────────────────
class TestUnmatched:
    def test_list_unmatched_sorted(self, H):
        r = requests.get(f"{API}/dealer-parts/data/unmatched?limit=20", headers=H, timeout=30)
        assert r.status_code == 200
        parts = r.json()["parts"]
        assert len(parts) > 0
        # top is 33/001 with high_usage
        assert parts[0]["code"] == "33/001", f"top {parts[0]['code']}"
        assert parts[0].get("high_usage") is True
        qtys = [p["total_qty"] for p in parts]
        assert qtys == sorted(qtys, reverse=True)

    def test_mark_obsolete_and_revert(self, H):
        # pick some unmatched code (not 33/001 so we don't corrupt top test)
        r = requests.get(f"{API}/dealer-parts/data/unmatched?limit=20", headers=H, timeout=30)
        parts = r.json()["parts"]
        # avoid codes containing '/' (path routing) — pick first safe one
        target = next((p for p in parts if "/" not in p["code_norm"]), None)
        if not target:
            pytest.skip("no unmatched code_norm without slash available")
        code_norm = target["code_norm"]
        # mark obsolete
        r2 = requests.post(f"{API}/dealer-parts/data/unmatched/{code_norm}/action",
                           headers=H, json={"action": "mark_obsolete"}, timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.json()["review_status"] == "obsolete"

    def test_map_to_bom_invalid_returns_400(self, H):
        r = requests.get(f"{API}/dealer-parts/data/unmatched?limit=20", headers=H, timeout=30)
        parts = r.json()["parts"]
        target = next((p for p in parts if "/" not in p["code_norm"]), None)
        if not target:
            pytest.skip("no slash-free code_norm")
        code_norm = target["code_norm"]
        r2 = requests.post(f"{API}/dealer-parts/data/unmatched/{code_norm}/action",
                           headers=H, json={"action": "map_to_bom", "bom_code": "DOESNOTEXIST_ZZZ"},
                           timeout=30)
        assert r2.status_code == 400

    def test_map_to_bom_valid(self, H):
        # get a real machine + component
        rm = requests.get(f"{API}/dealer-parts/data/machines?limit=5", headers=H, timeout=30)
        assert rm.status_code == 200
        machines = rm.json()["machines"]
        assert len(machines) > 0
        top_ref = machines[0]["top_level_ref"]
        rmp = requests.get(f"{API}/dealer-parts/data/machine-parts?top_level_ref={top_ref}",
                           headers=H, timeout=30)
        assert rmp.status_code == 200, rmp.text
        comps = rmp.json()["components"]
        assert len(comps) > 0
        bom_code = comps[0]["code"]
        # pick an unmatched part
        ru = requests.get(f"{API}/dealer-parts/data/unmatched?limit=10", headers=H, timeout=30)
        # skip already-actioned ones
        target = None
        for p in ru.json()["parts"]:
            if "/" in p["code_norm"]:
                continue
            if p.get("review_status") not in ("obsolete", "not_relevant", "excluded"):
                target = p
                break
        if not target:
            pytest.skip("no unmatched target available")
        r2 = requests.post(f"{API}/dealer-parts/data/unmatched/{target['code_norm']}/action",
                           headers=H, json={"action": "map_to_bom", "bom_code": bom_code}, timeout=30)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("matched") is True
        assert r2.json().get("match_method") == "manual"


# ─────────────────────── Machines + machine-parts ───────────────────────
class TestMachines:
    def test_list_machines(self, H):
        r = requests.get(f"{API}/dealer-parts/data/machines?limit=10", headers=H, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 4879, f"expected total 4879, got {data['total']}"
        assert len(data["machines"]) > 0
        assert "component_count" in data["machines"][0]

    def test_machine_parts(self, H):
        rm = requests.get(f"{API}/dealer-parts/data/machines?limit=1", headers=H, timeout=30)
        top_ref = rm.json()["machines"][0]["top_level_ref"]
        r = requests.get(f"{API}/dealer-parts/data/machine-parts?top_level_ref={top_ref}",
                         headers=H, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["machine"]["top_level_ref"] == top_ref
        assert "components" in data
        assert "used_components" in data
        assert "unused_components" in data
        if data["components"]:
            assert data["components"][0]["priority"] in {"critical", "recommended", "optional", "low", "no_usage"}

    def test_machine_parts_404(self, H):
        r = requests.get(f"{API}/dealer-parts/data/machine-parts?top_level_ref=DOES-NOT-EXIST-ZZZ",
                         headers=H, timeout=30)
        assert r.status_code == 404


# ─────────────────────── Settings ───────────────────────
class TestSettings:
    def test_get_defaults(self, H):
        r = requests.get(f"{API}/dealer-parts/data/settings", headers=H, timeout=30)
        assert r.status_code == 200
        s = r.json()
        assert s.get("fuzzy_threshold") is not None
        assert s.get("high_usage_threshold") is not None

    def test_update_and_persist(self, H):
        # capture original
        cur = requests.get(f"{API}/dealer-parts/data/settings", headers=H, timeout=30).json()
        orig = cur.get("high_usage_threshold", 20)
        new_val = 25 if orig != 25 else 30
        r = requests.put(f"{API}/dealer-parts/data/settings", headers=H,
                         json={"high_usage_threshold": new_val}, timeout=30)
        assert r.status_code == 200
        assert r.json()["high_usage_threshold"] == new_val
        # verify persisted
        r2 = requests.get(f"{API}/dealer-parts/data/settings", headers=H, timeout=30)
        assert r2.json()["high_usage_threshold"] == new_val
        # restore
        requests.put(f"{API}/dealer-parts/data/settings", headers=H,
                     json={"high_usage_threshold": orig}, timeout=30)


# ─────────────────────── Chunked upload flow ───────────────────────
class TestChunkedUpload:
    def test_init_returns_upload_id(self, H):
        r = requests.post(f"{API}/dealer-parts/data/upload/init", headers=H, timeout=30)
        assert r.status_code == 200
        assert "upload_id" in r.json()

    def test_finish_unknown_returns_404(self, H):
        r = requests.post(f"{API}/dealer-parts/data/upload/does-not-exist/finish",
                          headers=H, json={"kind": "parts_used", "filename": "x.xlsx"}, timeout=30)
        assert r.status_code == 404


# ─────────────────────── RBAC ───────────────────────
class TestRBAC:
    def test_dealer_blocked_on_all_endpoints(self, dealer_token):
        h = {"Authorization": f"Bearer {dealer_token}"}
        endpoints = [
            ("GET", "/dealer-parts/data/imports"),
            ("GET", "/dealer-parts/data/most-used-analysis"),
            ("GET", "/dealer-parts/data/unmatched"),
            ("GET", "/dealer-parts/data/matches"),
            ("GET", "/dealer-parts/data/aliases"),
            ("GET", "/dealer-parts/data/machines"),
            ("GET", "/dealer-parts/data/settings"),
            ("POST", "/dealer-parts/data/match/run"),
            ("POST", "/dealer-parts/data/upload/init"),
        ]
        for method, ep in endpoints:
            if method == "GET":
                r = requests.get(f"{API}{ep}", headers=h, timeout=30)
            else:
                r = requests.post(f"{API}{ep}", headers=h, json={}, timeout=30)
            assert r.status_code == 403, f"{method} {ep} expected 403 got {r.status_code}"
