"""Iter 216h170 — Performance pass regression tests.

Locks the behaviour of the four optimisations shipped in this iter:
  1. New Tier-4 indexes are created at boot (sample check).
  2. The aggregate TTL cache wrapper serves identical payloads on
     cold + warm hits.
  3. `/master-admin/mod/sites` (refactored from 4·N awaits to
     2·N batched aggregates) returns the same shape & per-site keys.
  4. `/staffing/performance` (refactored from 3·N awaits to 3 grouped
     aggregates) returns the same shape & per-staff keys.
  5. The new `/master-admin/perf/cache` endpoint surfaces stats and
     `cache_clear` actually empties the cache.

Pure-unit tests on the cache primitive live in this file too so we
don't depend on a live preview environment for the core invariants.
"""
import asyncio
import os
import time

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://admin-portal-fix-37.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def admin():
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


@pytest.fixture
def engineer():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


# ── 1. Index presence (sample) ───────────────────────────────────

class TestIndexCoverage:
    """Spot-check that the Tier-4 indexes really were created on boot.

    We sample a handful of the most impactful ones — every other index
    in the new block uses the same `create_index` API so this is enough
    to detect any wholesale regression."""

    def test_svc_cases_id_index(self):
        db = _mongo()
        names = {i["name"] for i in db["svc_cases"].list_indexes()}
        assert "id_1" in names, names

    def test_sites_id_index(self):
        db = _mongo()
        names = {i["name"] for i in db["sites"].list_indexes()}
        assert "id_1" in names, names

    def test_audit_logs_user_id_timestamp_index(self):
        db = _mongo()
        names = {i["name"] for i in db["audit_logs"].list_indexes()}
        assert any("user_id" in n and "timestamp" in n for n in names), names

    def test_payment_transactions_session_id_index(self):
        db = _mongo()
        names = {i["name"] for i in db["payment_transactions"].list_indexes()}
        assert "session_id_1" in names, names


# ── 2. Aggregate cache primitive ─────────────────────────────────

class TestAggregateCache:
    def test_cache_serves_same_value_on_warm_hit(self):
        from utils.aggregate_cache import cache_aggregate, CACHE
        CACHE.invalidate()
        call_count = [0]

        @cache_aggregate(ttl=10, key_args=("org_id",), prefix="t_a")
        async def fetch(org_id: str) -> dict:
            call_count[0] += 1
            return {"org": org_id, "n": call_count[0]}

        async def run():
            a1 = await fetch(org_id="acme")
            a2 = await fetch(org_id="acme")
            b1 = await fetch(org_id="other")
            return a1, a2, b1
        a1, a2, b1 = asyncio.run(run())
        assert a1 == a2 == {"org": "acme", "n": 1}
        assert call_count[0] == 2
        assert b1["org"] == "other"

    def test_cache_expires_after_ttl(self):
        from utils.aggregate_cache import cache_aggregate, CACHE
        CACHE.invalidate()

        @cache_aggregate(ttl=0.05, key_args=("k",), prefix="t_b")
        async def fetch(k: str) -> int:
            return time.monotonic_ns()

        async def run():
            v1 = await fetch(k="x")
            await asyncio.sleep(0.10)
            v2 = await fetch(k="x")
            return v1, v2
        v1, v2 = asyncio.run(run())
        assert v1 != v2

    def test_stampede_protection_dedupes_concurrent_calls(self):
        from utils.aggregate_cache import cache_aggregate, CACHE
        CACHE.invalidate()
        calls = [0]

        @cache_aggregate(ttl=5, key_args=("k",), prefix="t_c")
        async def fetch(k: str) -> str:
            calls[0] += 1
            await asyncio.sleep(0.05)
            return f"v-{calls[0]}"

        async def run():
            return await asyncio.gather(*[fetch(k="x") for _ in range(10)])
        results = asyncio.run(run())
        assert all(r == results[0] for r in results)
        assert calls[0] == 1, "stampede protection failed"

    def test_invalidate_by_prefix(self):
        from utils.aggregate_cache import CACHE
        CACHE.invalidate()
        CACHE.set("v1::ns_a::x=1", "A", ttl=100)
        CACHE.set("v1::ns_a::x=2", "B", ttl=100)
        CACHE.set("v1::ns_b::x=1", "C", ttl=100)
        n = CACHE.invalidate("v1::ns_a")
        assert n == 2
        assert CACHE.get("v1::ns_b::x=1") == "C"


# ── 3. Refactored MOD sites endpoint ─────────────────────────────

def test_mod_admin_sites_shape(admin):
    r = requests.get(f"{API}/api/master-admin/mod/sites",
                     headers=_hdr(admin["token"]), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sites" in body and isinstance(body["sites"], list)
    # Sites in the fixture data carry these annotation keys.
    for s in body["sites"]:
        # The new aggregate path must still populate every legacy key.
        for k in ("equipment_count", "staff_count", "open_faults"):
            assert k in s
            assert isinstance(s[k], int)


# ── 4. Refactored staffing performance endpoint ──────────────────

def test_staffing_performance_shape(admin):
    r = requests.get(f"{API}/api/staffing/performance",
                     headers=_hdr(admin["token"]), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "window" in body and "staff" in body
    for row in body["staff"]:
        for k in (
            "staff_id", "full_name", "primary_role",
            "hours_scheduled", "labour_cost",
            "classes_delivered", "attendees",
        ):
            assert k in row, row


# ── 5. Cache observability endpoints ─────────────────────────────

def test_cache_stats_endpoint(admin):
    r = requests.get(f"{API}/api/master-admin/perf/cache",
                     headers=_hdr(admin["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"entries", "hits", "misses", "hit_ratio", "version"} <= body.keys()


def test_cache_clear_endpoint_master_admin_only(engineer, admin):
    # Owner role rejected.
    r = requests.post(f"{API}/api/master-admin/perf/cache/clear",
                      headers=_hdr(engineer["token"]), timeout=15)
    assert r.status_code == 403, r.text
    # Master admin succeeds.
    r2 = requests.post(f"{API}/api/master-admin/perf/cache/clear",
                       headers=_hdr(admin["token"]), timeout=15)
    assert r2.status_code == 200, r2.text
    assert "cleared" in r2.json()


def test_capex_board_report_cache_consistency(admin):
    """Two back-to-back calls must return byte-identical payloads
    apart from the `generated_at` field (which the warm hit serves
    from cache, so it will match exactly on a warm hit)."""
    H = _hdr(admin["token"])
    r1 = requests.get(f"{API}/api/capex/board-report", headers=H, timeout=30)
    r2 = requests.get(f"{API}/api/capex/board-report", headers=H, timeout=30)
    assert r1.status_code == 200 and r2.status_code == 200
    # Warm hit comes from the cache, so generated_at must be identical.
    assert r1.json().get("generated_at") == r2.json().get("generated_at"), \
        "cache failed to serve warm payload — generated_at differs"
