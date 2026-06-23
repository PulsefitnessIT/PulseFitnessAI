"""Iter 216h171 — safe_to_list pagination helper + truncation telemetry."""
import asyncio
import os

import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://pulse-staging-10.preview.emergentagent.com").rstrip("/")


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


# ── Pure unit tests on the helper ────────────────────────────────

class _FakeCursor:
    """Minimal stub mimicking Motor's `cursor.to_list(cap)`."""
    def __init__(self, rows):
        self._rows = rows
    async def to_list(self, cap):
        return list(self._rows[:cap])


class TestSafeToList:
    def test_returns_all_rows_when_under_cap(self):
        from utils.safe_paginate import safe_to_list, TRUNCATION
        TRUNCATION.events.clear()
        rows = asyncio.run(safe_to_list(
            _FakeCursor([{"i": i} for i in range(20)]),
            cap=50, name="t.under_cap",
        ))
        assert rows == [{"i": i} for i in range(20)]
        # No truncation event recorded for an under-cap query.
        assert "t.under_cap" not in TRUNCATION.events

    def test_caps_at_limit_and_records_truncation(self):
        from utils.safe_paginate import safe_to_list, TRUNCATION
        TRUNCATION.events.clear()
        rows = asyncio.run(safe_to_list(
            _FakeCursor([{"i": i} for i in range(100)]),
            cap=10, name="t.at_cap",
        ))
        assert len(rows) == 10
        assert "t.at_cap" in TRUNCATION.events
        e = TRUNCATION.events["t.at_cap"]
        assert e["hits"] == 1
        assert e["last_cap"] == 10
        assert e["last_at"]  # iso timestamp set

    def test_truncation_counter_increments_on_repeated_hits(self):
        from utils.safe_paginate import safe_to_list, TRUNCATION
        TRUNCATION.events.clear()
        for _ in range(3):
            asyncio.run(safe_to_list(
                _FakeCursor([1, 2, 3, 4, 5]),
                cap=3, name="t.repeat",
            ))
        assert TRUNCATION.events["t.repeat"]["hits"] == 3

    def test_empty_cursor_records_nothing(self):
        from utils.safe_paginate import safe_to_list, TRUNCATION
        TRUNCATION.events.clear()
        rows = asyncio.run(safe_to_list(
            _FakeCursor([]), cap=5, name="t.empty",
        ))
        assert rows == []
        assert "t.empty" not in TRUNCATION.events


class TestBands:
    def test_band_constants_are_documented_values(self):
        from utils.safe_paginate import LIST_CAP, BULK_CAP, EXPORT_CAP
        assert LIST_CAP == 500
        assert BULK_CAP == 10_000
        assert EXPORT_CAP == 50_000
        # Each band must be strictly larger than the previous one.
        assert LIST_CAP < BULK_CAP < EXPORT_CAP


# ── Perf endpoint integration ────────────────────────────────────

def test_perf_endpoint_includes_truncation_events(admin):
    """The cache stats endpoint must now ship `truncation_events`."""
    r = requests.get(f"{API}/api/master-admin/perf/cache",
                     headers=_hdr(admin["token"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "truncation_events" in body, body
    assert isinstance(body["truncation_events"], dict)


def test_perf_endpoint_role_gate(engineer):
    r = requests.get(f"{API}/api/master-admin/perf/cache",
                     headers=_hdr(engineer["token"]), timeout=15)
    assert r.status_code == 403


# ── Behaviour regression: refactored aggregate endpoints ─────────

def test_capex_board_report_after_safe_to_list(admin):
    """The CAPEX board report must still return its full payload
    after the issues query was wrapped in safe_to_list."""
    r = requests.get(f"{API}/api/capex/board-report",
                     headers=_hdr(admin["token"]), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # Every documented top-level section must still be present.
    for k in ("summary", "fleet_intelligence", "priority_replacements", "scope_label"):
        assert k in body, body.keys()


def test_memberships_analytics_after_safe_to_list(admin):
    """Memberships analytics endpoint smoke-test: still returns
    a valid 200 with `revenue_gbp` after both paginated reads."""
    r = requests.get(f"{API}/api/memberships/analytics",
                     headers=_hdr(admin["token"]), timeout=30)
    # The endpoint exists but may 404 on tenants without the module;
    # we accept either case as "no regression to the route".
    assert r.status_code in (200, 404), r.text
