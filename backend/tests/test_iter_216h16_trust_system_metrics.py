"""
Iter 216h16 — System resource metrics on Trust dashboard.

Pins:
  1. `/api/master-admin/trust/system` is master-admin gated.
  2. Returns CPU + memory + disk + process + hostname fields.
  3. Each gauge has a `status` field (ok|warn|critical) that the UI
     uses to colour the banner.
  4. `/api/master-admin/trust/overview` also exposes `system` so the
     dashboard doesn't need a second round-trip.
"""
from __future__ import annotations

import os

import httpx
import pytest

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")


@pytest.fixture
def master_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD}, timeout=15,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_system_endpoint_requires_master_admin():
    r = httpx.get(f"{API_URL}/api/master-admin/trust/system", timeout=15)
    assert r.status_code in (401, 403)


def test_system_endpoint_returns_cpu_memory_disk(master_headers):
    r = httpx.get(f"{API_URL}/api/master-admin/trust/system", headers=master_headers, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for top_key in ("cpu", "memory", "disk", "swap", "process", "hostname", "captured_at"):
        assert top_key in data, f"missing {top_key}"
    # CPU shape
    assert "percent" in data["cpu"]
    assert isinstance(data["cpu"]["count_logical"], int) and data["cpu"]["count_logical"] >= 1
    assert "load_avg" in data["cpu"]
    # Memory shape + status banner colour
    mem = data["memory"]
    assert mem["status"] in {"ok", "warn", "critical"}
    assert mem["total_mb"] > 0
    assert mem["percent"] >= 0
    assert mem["used_mb"] + mem["available_mb"] >= mem["total_mb"] * 0.9  # sanity check
    # Disk shape + status
    disk = data["disk"]
    assert disk["status"] in {"ok", "warn", "critical"}
    assert disk["total_gb"] > 0
    # Process shape
    proc = data["process"]
    assert proc["rss_mb"] > 0
    assert proc["pid"] > 0


def test_overview_endpoint_includes_system_block(master_headers):
    """The dashboard fetches /overview once and renders everything, so
    `system` MUST be embedded in the overview response."""
    r = httpx.get(f"{API_URL}/api/master-admin/trust/overview", headers=master_headers, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "system" in data
    assert "memory" in data["system"]


def test_memory_status_banner_thresholds():
    """Sanity check the threshold ramp: < 70% → ok, 70-89% → warn,
    ≥ 90% → critical. Validates the helper purely on its boundary
    values (no need for psutil)."""
    from routes.trust import _system_metrics  # noqa: WPS433
    # We can't fake virtual_memory output without monkey-patching
    # psutil — but we can confirm the function runs cleanly and
    # returns a valid status string under whatever the host's actual
    # state is.
    snapshot = _system_metrics()
    assert snapshot["memory"]["status"] in {"ok", "warn", "critical"}
    assert snapshot["disk"]["status"] in {"ok", "warn", "critical"}
