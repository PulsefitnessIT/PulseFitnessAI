"""Iter 216d — multi-machine fault job (`job_id` grouping) regression.

Pins the contract for the multi-machine "log a fault" workflow:

  • POST /api/issues/batch creates N issues, all stamped with one
    `job_id`, so each machine still has its own SLA + status + report
    row but the fault list can group them.
  • GET /api/issues/jobs/{job_id} returns every sibling, plus the
    aggregate progress fields (`total`, `resolved`, `all_resolved`).
  • The single-issue path (POST /api/issues) still works and returns
    `job_id=null` (legacy back-compat).
  • Resolving one sibling does NOT close the others — partial-fix
    state is preserved per-machine.

If any of these regress, Lee's "I want multi-machine again" feature is
broken.
"""
import requests

import pytest

from tests.conftest import (
    _test_backend_url,
    rate_limit_bypass_headers,
    REGULAR_USER_EMAIL,
    REGULAR_USER_PASSWORD,
)


@pytest.fixture(scope="module")
def regular_token() -> str:
    base = _test_backend_url()
    resp = requests.post(
        f"{base}/api/auth/login",
        json={"email": REGULAR_USER_EMAIL, "password": REGULAR_USER_PASSWORD},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert token
    return token


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def _delete_test_issue(token: str, issue_id: str) -> None:
    """Best-effort cleanup. Endpoint may be admin-only; ignore failures."""
    try:
        requests.delete(
            f"{_test_backend_url()}/api/issues/{issue_id}",
            headers=_hdr(token),
            timeout=5,
        )
    except Exception:
        pass


def test_batch_creates_n_issues_with_shared_job_id(regular_token):
    base = _test_backend_url()
    payload = {
        "machines": [
            {
                "serial_number": "ITER216D-T1",
                "machine_type": "Treadmill",
                "issue_description": "Belt slipping",
                "severity": "operational_minor",
            },
            {
                "serial_number": "ITER216D-T2",
                "machine_type": "Treadmill",
                "issue_description": "Console dead",
                "severity": "operational_major",
            },
            {
                "serial_number": "ITER216D-T3",
                "machine_type": "Treadmill",
                "issue_description": "Heart rate sensor broken",
                "severity": "operational_minor",
            },
        ],
    }
    r = requests.post(
        f"{base}/api/issues/batch",
        json=payload,
        headers=_hdr(regular_token),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    job_id = data["job_id"]
    assert job_id and len(job_id) >= 8
    assert data["count"] == 3
    assert len(data["issues"]) == 3
    serials = {i["serial_number"] for i in data["issues"]}
    assert serials == {"ITER216D-T1", "ITER216D-T2", "ITER216D-T3"}
    # Every sibling must carry the SAME job_id.
    assert all(i["job_id"] == job_id for i in data["issues"]), \
        f"expected every sibling to share job_id={job_id}, got {[i['job_id'] for i in data['issues']]}"

    try:
        # GET the grouped view.
        rg = requests.get(
            f"{base}/api/issues/jobs/{job_id}",
            headers=_hdr(regular_token),
            timeout=10,
        )
        assert rg.status_code == 200, rg.text
        gd = rg.json()
        assert gd["job_id"] == job_id
        assert gd["total"] == 3
        assert gd["resolved"] == 0
        assert gd["all_resolved"] is False
    finally:
        for issue in data["issues"]:
            _delete_test_issue(regular_token, issue["id"])


def test_single_issue_post_still_works_with_null_job_id(regular_token):
    """Legacy single-issue POST stays unchanged (back-compat)."""
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/issues",
        json={
            "serial_number": "ITER216D-LEGACY",
            "machine_type": "Treadmill",
            "issue_description": "Single-machine legacy log",
            "severity": "operational_minor",
        },
        headers=_hdr(regular_token),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    assert data.get("job_id") is None, \
        "single-issue legacy POST must NOT auto-generate a job_id"
    _delete_test_issue(regular_token, data["id"])


def test_partial_resolution_preserves_other_siblings(regular_token):
    """Resolving one sibling must NOT auto-close the others."""
    base = _test_backend_url()
    payload = {
        "machines": [
            {
                "serial_number": "ITER216D-PR1",
                "machine_type": "Bike",
                "issue_description": "Pedal loose",
                "severity": "operational_minor",
            },
            {
                "serial_number": "ITER216D-PR2",
                "machine_type": "Bike",
                "issue_description": "Display flickers",
                "severity": "operational_major",
            },
        ],
    }
    r = requests.post(f"{base}/api/issues/batch", json=payload, headers=_hdr(regular_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    job_id = data["job_id"]
    issues = data["issues"]
    first_id = issues[0]["id"]
    second_id = issues[1]["id"]

    try:
        # Resolve only the first one.
        r2 = requests.patch(
            f"{base}/api/issues/{first_id}",
            json={"status": "resolved"},
            headers=_hdr(regular_token),
            timeout=10,
        )
        assert r2.status_code == 200, r2.text

        rg = requests.get(
            f"{base}/api/issues/jobs/{job_id}",
            headers=_hdr(regular_token),
            timeout=10,
        )
        gd = rg.json()
        assert gd["total"] == 2
        assert gd["resolved"] == 1, "first sibling should be resolved"
        assert gd["all_resolved"] is False, \
            "the second machine is still open — job must NOT report all_resolved"

        statuses = {i["id"]: i["status"] for i in gd["issues"]}
        assert statuses[first_id] == "resolved"
        assert statuses[second_id] in ("open", "in_progress"), \
            f"sibling status corrupted by partial resolve: {statuses[second_id]}"
    finally:
        for iid in (first_id, second_id):
            _delete_test_issue(regular_token, iid)


def test_batch_rejects_empty_machines_list(regular_token):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/issues/batch",
        json={"machines": []},
        headers=_hdr(regular_token),
        timeout=10,
    )
    assert r.status_code == 400, r.text
    assert "machines" in r.text.lower()
