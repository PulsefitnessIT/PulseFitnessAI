"""Iter 220ea·24 — Return Visit Brief + cross-org field share + stock polish.

Covers four shipped changes:
  • Service report PDF folds in a "Return Visit Brief" (per-machine
    further-work + parts-for-return).
  • Cross-org custom-field template sharing via a token/link
    (share → preview → import, idempotent).
  • Stock-take dedupe via Idempotency-Key + cleaner van labels.
  • Legacy EngineerJobDetail.js removed.
"""
from pathlib import Path

import pytest
import requests

from tests.conftest import _test_backend_url, rate_limit_bypass_headers

BASE = _test_backend_url()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
BACKEND = Path(__file__).resolve().parents[1]


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def _need(token):
    if not token:
        pytest.skip("no master admin token (rate limited?)")


# ─────────────────── field share live flow ────────────────────────

def test_field_share_preview_and_import_roundtrip(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    # Share all active fields.
    r = requests.post(f"{BASE}/api/svc/work-report-fields/share",
                      json={"label": "Iter24 test pack"}, headers=_h(token), timeout=30)
    if r.status_code == 400:
        pytest.skip("org has no custom fields to share")
    assert r.status_code == 201, r.text
    share = r.json()
    tok = share["token"]
    assert share["field_count"] >= 1
    # Preview.
    p = requests.get(f"{BASE}/api/svc/work-report-fields/shared/{tok}",
                     headers=_h(token), timeout=20)
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["field_count"] == share["field_count"]
    assert body["is_own_org"] is True
    assert isinstance(body["fields"], list) and body["fields"]
    # Import into the SAME org → every field is a dup → all skipped.
    imp = requests.post(f"{BASE}/api/svc/work-report-fields/shared/{tok}/import",
                        headers=_h(token), timeout=30)
    assert imp.status_code == 201, imp.text
    out = imp.json()
    assert out["created_count"] == 0
    assert out["skipped_count"] == share["field_count"]


def test_field_share_unknown_token_404(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    r = requests.get(f"{BASE}/api/svc/work-report-fields/shared/NOPE-NOPE-NOPE",
                     headers=_h(token), timeout=20)
    assert r.status_code == 404, r.text


# ─────────────────── stock-take idempotency (read-safe) ────────────

def test_stock_take_accepts_idempotency_header(master_admin_token_session):
    token = master_admin_token_session
    _need(token)
    # Empty warehouse SKU set → nothing to adjust, but the endpoint must
    # accept the Idempotency-Key header without error.
    h = {**_h(token), "Idempotency-Key": "iter24-noop-test"}
    r = requests.post(f"{BASE}/api/svc/admin/stock/stock-take",
                      json={"location": "warehouse", "counts": [
                          {"part_sku": "__ITER24_NOOP__", "counted_qty": 0}]},
                      headers=h, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["adjusted"] == 0


# ─────────────────── backend source guards ────────────────────────

def test_parts_request_allows_next_visit_urgency():
    src = (BACKEND / "routes" / "svc" / "engineer_parts_requests.py").read_text()
    assert '"next_visit"' in src
    assert "URGENCIES" in src


def test_service_report_renders_return_visit_brief():
    src = (BACKEND / "routes" / "svc" / "service_report.py").read_text()
    assert "RETURN VISIT BRIEF" in src
    assert "return_parts" in src
    assert "further_work" in src
    assert '"urgency": "next_visit"' in src


def test_admin_stock_stock_take_is_idempotent():
    src = (BACKEND / "routes" / "svc" / "admin_stock.py").read_text()
    assert "idempotency_key" in src
    # van label no longer leaks a raw UUID prefix.
    assert "Unnamed engineer" in src


def test_work_report_fields_has_share_endpoints():
    src = (BACKEND / "routes" / "svc" / "work_report_fields.py").read_text()
    assert "/work-report-fields/share" in src
    assert "/work-report-fields/shared/{token}" in src
    assert "svc_work_report_field_shares" in src
    assert "_live_share" in src


# ─────────────────── frontend / cleanup guards ────────────────────

def test_legacy_engineer_job_detail_removed():
    legacy = FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerJobDetail.js"
    assert not legacy.exists()
    routes = (FRONTEND / "routes" / "AppRoutes.js").read_text()
    assert "ServiceOpsEngineerJobLegacy" not in routes
    assert "jobs/:caseId/legacy" not in routes


def test_work_report_fields_ui_has_share_import():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "EngineerWorkReportFields.js").read_text()
    assert "wrf-share-btn" in src
    assert "ShareImportModal" in src
    assert "wrf-import-confirm" in src
    assert "?share=" in src


def test_admin_stock_ui_sends_stocktake_idempotency():
    src = (FRONTEND / "pages" / "ServiceOps" / "Engineer" / "AdminStock.js").read_text()
    # The stock-take POST now carries an Idempotency-Key header.
    assert "stock-take" in src
    assert "'Idempotency-Key': newIdem()" in src


# ─────────────────── social-tracker ReDoS guard ───────────────────

def test_social_tracker_meta_parse_is_linear():
    """The OG/meta parser must not catastrophically backtrack on large
    minified HTML (previously pegged the daily crawl loop at 100% CPU
    and wedged the whole backend on startup)."""
    import time

    from utils.social_tracker import parse_engagement_from_html

    big = "<html><head>"
    big += ('<meta charset="utf-8" ' + "x" * 50 + ">") * 4000
    big += '<meta property="og:title" content="GymAxis">'
    big += ('<meta property="og:description" content="1,234 likes, '
            '56 comments - GymAxis (@gymaxis): &quot;New kit&quot;">')
    big += "</head><body>" + ("a " * 100000) + "</body></html>"
    t = time.time()
    out = parse_engagement_from_html(big)
    elapsed = time.time() - t
    assert elapsed < 2.0, f"meta parse too slow ({elapsed:.2f}s) — possible ReDoS"
    assert out.get("likes") == 1234
    assert out.get("comments") == 56

