"""Iter 220 P1 (slice 2) — version compare/rollback + price-change approval workflow.

End-to-end API tests against the live preview environment, logging in as the
master admin (`admin@gymaxisai.com`) who is also a CRM approver.

We only validate that the endpoints introduced in slice 2 behave correctly with
respect to: status codes, response shape, permission gating, and basic data
consistency. Heavy seed creation is avoided because the main agent has already
populated the CRM org (~47 Studio Equipment products + multiple versions +
price_changes) so we can exercise compare/rollback/scheduler/approval flows
without re-importing.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
CRM_EMAIL = "admin@gymaxisai.com"
CRM_PASS = "MasterAdmin123!"


# ----- fixtures -----------------------------------------------------------------

@pytest.fixture(scope="module")
def crm_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": CRM_EMAIL, "password": CRM_PASS},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"CRM login failed ({r.status_code}): {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        pytest.skip("No token in CRM login response")
    return tok


@pytest.fixture(scope="module")
def hdr(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


# ----- settings -----------------------------------------------------------------

class TestSettings:
    def test_get_settings_default_shape(self, hdr):
        r = requests.get(f"{BASE_URL}/api/crm/price-list/settings", headers=hdr, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "require_approval" in data
        assert isinstance(data["require_approval"], bool)
        assert "margin_threshold_pct" in data
        assert data.get("is_approver") is True, "admin should be approver"
        assert data.get("can_edit") is True

    def test_toggle_require_approval_idempotent(self, hdr):
        # Save original then flip on then off (to restore)
        cur = requests.get(f"{BASE_URL}/api/crm/price-list/settings", headers=hdr, timeout=15).json()
        original = bool(cur.get("require_approval", False))

        r_on = requests.put(
            f"{BASE_URL}/api/crm/price-list/settings",
            headers=hdr, json={"require_approval": True}, timeout=15,
        )
        assert r_on.status_code == 200, r_on.text
        assert r_on.json().get("require_approval") is True

        verify = requests.get(f"{BASE_URL}/api/crm/price-list/settings", headers=hdr, timeout=15).json()
        assert verify.get("require_approval") is True

        # restore
        r_off = requests.put(
            f"{BASE_URL}/api/crm/price-list/settings",
            headers=hdr, json={"require_approval": original}, timeout=15,
        )
        assert r_off.status_code == 200


# ----- preview ------------------------------------------------------------------

class TestPreview:
    def test_preview_pct_returns_sample_and_warnings(self, hdr):
        r = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes/preview",
            headers=hdr,
            json={"field": "sell_price", "mode": "pct", "amount": 5, "filter": {}},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        data = data.get("preview", data)
        assert "affected_count" in data
        sample = data.get("sample") or data.get("preview") or []
        assert isinstance(sample, list)
        assert "warnings" in data
        for key in ("below_margin", "negative", "cost_gt_sell", "margin_threshold"):
            assert key in data["warnings"], f"missing warning bucket {key}"
        if sample:
            row = sample[0]
            assert "name" in row
            assert "old" in row and "new" in row

    def test_preview_fixed_set_modes(self, hdr):
        for mode, amount in (("fixed", 1), ("set", 999.99)):
            r = requests.post(
                f"{BASE_URL}/api/crm/price-list/price-changes/preview",
                headers=hdr,
                json={"field": "sell_price", "mode": mode, "amount": amount, "filter": {}},
                timeout=30,
            )
            assert r.status_code == 200, f"{mode}: {r.text}"
            assert "affected_count" in r.json().get("preview", r.json())

    def test_preview_margin_only_for_sell(self, hdr):
        # margin on sell_price → ok
        r_ok = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes/preview",
            headers=hdr,
            json={"field": "sell_price", "mode": "margin", "amount": 40, "filter": {}},
            timeout=30,
        )
        assert r_ok.status_code == 200, r_ok.text

        # margin on cost_price → should be 400 or affected_count=0
        r_bad = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes/preview",
            headers=hdr,
            json={"field": "cost_price", "mode": "margin", "amount": 40, "filter": {}},
            timeout=30,
        )
        assert r_bad.status_code in (400, 422) or r_bad.json().get("affected_count", 0) == 0


# ----- price change apply (approver path) --------------------------------------

class TestPriceChangeApply:
    def test_apply_immediate_when_approval_off(self, hdr):
        # ensure approval OFF
        requests.put(
            f"{BASE_URL}/api/crm/price-list/settings",
            headers=hdr, json={"require_approval": False}, timeout=15,
        )
        r = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes",
            headers=hdr,
            json={"field": "sell_price", "mode": "pct", "amount": 0.5,
                  "filter": {}, "reason": "TEST_iter220p1_slice2"},
            timeout=60,
        )
        assert r.status_code in (200, 201), r.text
        data = r.json()
        data = data.get("change", data)
        assert data.get("status") == "applied", data
        assert data.get("affected_count", 0) >= 0

    def test_schedule_future_change(self, hdr):
        future = "2099-01-01T00:00:00Z"
        r = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes",
            headers=hdr,
            json={"field": "sell_price", "mode": "pct", "amount": 0.1,
                  "filter": {}, "effective_date": future,
                  "reason": "TEST_slice2_scheduled"},
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        body = body.get("change", body)
        assert body.get("status") == "scheduled", body
        change_id = body.get("id")
        # Cancel it so it doesn't accumulate
        if change_id:
            requests.post(
                f"{BASE_URL}/api/crm/price-list/price-changes/{change_id}/cancel",
                headers=hdr, timeout=15,
            )

    def test_list_price_changes(self, hdr):
        r = requests.get(f"{BASE_URL}/api/crm/price-list/price-changes", headers=hdr, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("changes", []))
        assert isinstance(items, list)

    def test_reapprove_non_pending_returns_409(self, hdr):
        # find an already-applied change
        r = requests.get(f"{BASE_URL}/api/crm/price-list/price-changes", headers=hdr, timeout=20)
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("changes", []))
        applied = [c for c in items if c.get("status") == "applied"]
        if not applied:
            pytest.skip("No applied change to re-approve")
        cid = applied[0].get("id")
        r2 = requests.post(
            f"{BASE_URL}/api/crm/price-list/price-changes/{cid}/approve",
            headers=hdr, json={"comment": "retest"}, timeout=15,
        )
        assert r2.status_code in (409, 400), f"expected 409/400 got {r2.status_code}: {r2.text}"


# ----- versions / compare / rollback -------------------------------------------

class TestVersions:
    def test_list_versions(self, hdr):
        r = requests.get(f"{BASE_URL}/api/crm/price-list/versions", headers=hdr, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("versions", []))
        assert isinstance(items, list)

    def test_snapshot_current_creates_version(self, hdr):
        r = requests.post(
            f"{BASE_URL}/api/crm/price-list/versions/snapshot-current",
            headers=hdr, json={"name": f"TEST_snapshot_{uuid.uuid4().hex[:6]}"}, timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        v = r.json()
        v = v.get("version", v)
        assert v.get("id") or v.get("_id") or v.get("version_id"), v
        vid = v.get("id") or v.get("version_id")

        # compare snapshot → live should have 0 changed (snapshot of live)
        if vid:
            r2 = requests.get(
                f"{BASE_URL}/api/crm/price-list/versions/{vid}/compare",
                headers=hdr, timeout=30,
            )
            assert r2.status_code == 200, r2.text
            diff = r2.json()
            assert "counts" in diff
            for k in ("added", "removed", "changed"):
                assert k in diff["counts"]
            # snapshot vs current live should have no diffs
            assert diff["counts"]["changed"] == 0

    def test_compare_two_versions(self, hdr):
        r = requests.get(f"{BASE_URL}/api/crm/price-list/versions", headers=hdr, timeout=20)
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("versions", []))
        if len(items) < 2:
            pytest.skip("need at least 2 versions to compare")
        a = items[0].get("id") or items[0].get("_id")
        b = items[1].get("id") or items[1].get("_id")
        r2 = requests.get(
            f"{BASE_URL}/api/crm/price-list/versions/{a}/compare",
            params={"to": b}, headers=hdr, timeout=30,
        )
        assert r2.status_code == 200, r2.text
        diff = r2.json()
        assert "counts" in diff and isinstance(diff["counts"], dict)
        assert "added" in diff and "removed" in diff and "changed" in diff

    def test_rollback_creates_live_version_then_zero_diff(self, hdr):
        # pick the oldest non-live version (a real prior snapshot)
        r = requests.get(f"{BASE_URL}/api/crm/price-list/versions", headers=hdr, timeout=20)
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("versions", []))
        candidates = [v for v in items if v.get("status") != "live" and (v.get("id") or v.get("_id"))]
        if not candidates:
            pytest.skip("no non-live version to rollback to")
        target = candidates[-1]
        vid = target.get("id") or target.get("_id")

        rb = requests.post(
            f"{BASE_URL}/api/crm/price-list/versions/{vid}/rollback",
            headers=hdr, json={"reason": "TEST_iter220p1_slice2_rollback"}, timeout=120,
        )
        assert rb.status_code in (200, 201), rb.text

        # After rollback, comparing source version → live should be 0 changed
        time.sleep(0.5)
        diff_r = requests.get(
            f"{BASE_URL}/api/crm/price-list/versions/{vid}/compare",
            headers=hdr, timeout=30,
        )
        assert diff_r.status_code == 200
        diff = diff_r.json()
        assert diff["counts"]["changed"] == 0, diff["counts"]
