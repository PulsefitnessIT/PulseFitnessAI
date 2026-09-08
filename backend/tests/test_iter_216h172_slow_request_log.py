"""Iter 216h172 — Slow-request middleware + extended perf endpoint."""
import asyncio
import os

import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://allocation-wizard-ai.preview.emergentagent.com").rstrip("/")


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


# ── Pure-unit tests on the ring ──────────────────────────────────

class TestSlowRequestRing:
    def test_record_appears_in_snapshot(self):
        from utils.slow_request_log import SlowRequestRing
        ring = SlowRequestRing(capacity=5)
        ring.record(method="GET", path="/api/x", duration_ms=2000,
                    status=200, user_agent="ua")
        snap = ring.snapshot()
        assert snap["total_slow_count"] == 1
        assert snap["recent"][0]["path"] == "/api/x"
        assert snap["hottest_endpoints"][0]["hits"] == 1
        assert snap["hottest_endpoints"][0]["worst_ms"] == 2000

    def test_capacity_is_respected(self):
        from utils.slow_request_log import SlowRequestRing
        ring = SlowRequestRing(capacity=3)
        for i in range(7):
            ring.record(method="GET", path=f"/api/x{i}", duration_ms=2000,
                        status=200, user_agent="ua")
        snap = ring.snapshot()
        # Recent ring keeps only the last 3, but total_slow_count tracks all 7.
        assert snap["total_slow_count"] == 7
        assert len(snap["recent"]) == 3

    def test_hottest_endpoints_groups_uuid_paths(self):
        from utils.slow_request_log import SlowRequestRing
        ring = SlowRequestRing(capacity=20)
        # Three different case ids — should collapse to one `{id}` row.
        for cid in ("abc-12345-foo", "xyz-67890-bar", "qrs-11223-baz"):
            ring.record(method="GET", path=f"/api/svc/cases/{cid}",
                        duration_ms=2500, status=200, user_agent="ua")
        snap = ring.snapshot()
        endpoints = [r["endpoint"] for r in snap["hottest_endpoints"]]
        assert any("{id}" in e for e in endpoints), endpoints
        # All three slow calls roll up into one bucket.
        target = next(r for r in snap["hottest_endpoints"] if "{id}" in r["endpoint"])
        assert target["hits"] == 3

    def test_reset_clears_ring_and_total(self):
        from utils.slow_request_log import SlowRequestRing
        ring = SlowRequestRing(capacity=5)
        for _ in range(3):
            ring.record(method="GET", path="/api/x", duration_ms=2000,
                        status=200, user_agent="ua")
        n = ring.reset()
        assert n == 3
        snap = ring.snapshot()
        assert snap["total_slow_count"] == 0
        assert snap["recent"] == []
        assert snap["hottest_endpoints"] == []


# ── Middleware wired into the running app ────────────────────────

def test_perf_endpoint_carries_slow_requests_section(admin):
    """The extended cache endpoint must now return the slow_requests block."""
    r = requests.get(f"{API}/api/master-admin/perf/cache",
                     headers=_hdr(admin["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "slow_requests" in body, body
    slow = body["slow_requests"]
    for k in ("slow_threshold_ms", "ring_size",
              "total_slow_count", "recent", "hottest_endpoints"):
        assert k in slow, slow.keys()
    # Section already present on every existing iter 170/171 key too.
    for k in ("entries", "hits", "misses", "hit_ratio", "truncation_events"):
        assert k in body, body.keys()


def test_perf_slow_clear_role_gate(engineer):
    r = requests.post(f"{API}/api/master-admin/perf/slow-requests/clear",
                      headers=_hdr(engineer["token"]), timeout=10)
    assert r.status_code == 403


def test_perf_slow_clear_returns_cleared_count(admin):
    r = requests.post(f"{API}/api/master-admin/perf/slow-requests/clear",
                      headers=_hdr(admin["token"]), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "cleared" in body
    assert isinstance(body["cleared"], int)


def test_health_endpoint_does_not_pollute_slow_ring(admin):
    """The middleware must skip the `/health` probes so Kubernetes
    liveness/readiness checks never appear in the slow log."""
    # Hit /health a few times to confirm it's ignored.
    for _ in range(3):
        requests.get(f"{API}/api/health", timeout=10)
    r = requests.get(f"{API}/api/master-admin/perf/cache",
                     headers=_hdr(admin["token"]), timeout=15)
    assert r.status_code == 200
    recent = r.json()["slow_requests"]["recent"]
    for entry in recent:
        assert not entry["path"].startswith("/api/health"), entry
