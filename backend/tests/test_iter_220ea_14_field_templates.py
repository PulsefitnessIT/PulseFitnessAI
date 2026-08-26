"""Iter 220ea·14 — Starter templates for Custom Report Fields.

Two new endpoints in `routes/svc/work_report_fields.py`:

* `GET  /api/svc/work-report-fields/templates`        — catalogue
* `POST /api/svc/work-report-fields/apply-template`   — seed fields

Cuts the cold-start "what fields should I even ask the engineer
to capture?" problem for new operators. Six templates ship out of
the box (Treadmill PPM, Treadmill repair, Cycle PPM, Rower PPM,
Strength PPM, Installation hand-over).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest


API_URL = (os.environ.get("REACT_APP_BACKEND_URL")
           or "https://photo-fix-verify.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASS = "MasterAdmin123!"


# ── Backend catalogue (source-level sanity) ──────────────────────


def test_field_templates_module_constant():
    """The shipped catalogue must contain at least the 6 documented
    starter templates with the keys the frontend reads."""
    from routes.svc import work_report_fields as wrf
    assert len(wrf.FIELD_TEMPLATES) >= 6
    ids = {t["id"] for t in wrf.FIELD_TEMPLATES}
    for expected in (
        "treadmill_ppm", "treadmill_repair", "cycle_ppm",
        "rower_ppm", "strength_ppm", "installation_handover",
    ):
        assert expected in ids, f"missing template: {expected}"
    # Each template must have these keys + a non-empty fields list.
    for t in wrf.FIELD_TEMPLATES:
        for k in ("id", "name", "summary", "scope_kind",
                  "job_types", "fields"):
            assert k in t, f"template {t.get('id')!r} missing key {k}"
        assert isinstance(t["fields"], list) and t["fields"], (
            f"template {t['id']} has no fields"
        )
        for f in t["fields"]:
            assert f["field_type"] in wrf.FIELD_TYPES, (
                f"template {t['id']} field {f.get('name')!r} has bad type"
            )


# ── Live endpoint tests (skipped if API unreachable) ─────────────


@pytest.fixture(scope="module")
def auth_token():
    """Login once for the whole module so we don't trip the rate
    limiter. Skips the live tests if the API is unreachable."""
    try:
        r = httpx.post(
            f"{API_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=10.0,
        )
    except Exception:
        pytest.skip("API unreachable")
    if r.status_code == 429:
        pytest.skip("Rate-limited")
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code}")
    return r.json().get("token")


def test_templates_endpoint_returns_catalogue(auth_token):
    r = httpx.get(
        f"{API_URL}/api/svc/work-report-fields/templates",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 200
    body = r.json()
    assert "templates" in body
    assert body.get("count", 0) >= 6
    # The frontend renders each template card with these fields.
    sample = body["templates"][0]
    for k in ("id", "name", "summary", "field_count", "fields"):
        assert k in sample, f"template response missing {k}"
    # And the inner fields carry enough for the preview <details>.
    for f in sample["fields"]:
        for k in ("name", "field_type", "required"):
            assert k in f


def test_apply_template_creates_fields_then_skips_duplicates(auth_token):
    """Two-step E2E: applying a template seeds its fields; applying
    the same template again skips all of them (idempotent).

    Cleans up the seeded fields at the end so the test is repeatable.
    """
    suffix = uuid.uuid4().hex[:6]
    # Use a fresh equipment_type so we don't collide with anything
    # the org already has. (`scope_value` override path.)
    scope_value = f"TestRig-{suffix}"
    headers = {"Authorization": f"Bearer {auth_token}"}

    # ── 1st apply: expect fields created ─────────────────────────
    r1 = httpx.post(
        f"{API_URL}/api/svc/work-report-fields/apply-template",
        headers=headers,
        json={
            "template_id": "treadmill_ppm",
            "scope_kind": "equipment_type",
            "scope_value": scope_value,
        },
        timeout=15.0,
    )
    assert r1.status_code == 201, r1.text
    body1 = r1.json()
    assert body1["template_id"] == "treadmill_ppm"
    assert body1["created_count"] >= 5
    assert body1["skipped_count"] == 0
    seeded_ids = [f["id"] for f in body1["created"]]
    # Sanity: every seeded field has `created_via_template`.
    for f in body1["created"]:
        assert f.get("created_via_template") == "treadmill_ppm"
        assert f["scope_value"] == scope_value

    # ── 2nd apply: every field should now be skipped ─────────────
    r2 = httpx.post(
        f"{API_URL}/api/svc/work-report-fields/apply-template",
        headers=headers,
        json={
            "template_id": "treadmill_ppm",
            "scope_kind": "equipment_type",
            "scope_value": scope_value,
        },
        timeout=15.0,
    )
    assert r2.status_code == 201
    body2 = r2.json()
    assert body2["created_count"] == 0
    assert body2["skipped_count"] >= 5

    # ── Cleanup: archive every seeded field ──────────────────────
    for fid in seeded_ids:
        httpx.delete(
            f"{API_URL}/api/svc/work-report-fields/{fid}",
            headers=headers, timeout=10.0,
        )


def test_apply_template_unknown_id_returns_404(auth_token):
    r = httpx.post(
        f"{API_URL}/api/svc/work-report-fields/apply-template",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"template_id": "this-template-does-not-exist"},
        timeout=10.0,
    )
    assert r.status_code == 404
    assert "not found" in r.text.lower()


def test_apply_template_validates_job_types(auth_token):
    """Iter 220ec — job_types accept any org-defined case-type slug, so a
    custom slug like `bogus_type` is KEPT; only malformed (non-slug)
    entries are silently dropped — never a 400 — so the frontend
    chip-toggle UI can be lenient."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    scope_value = f"TestRig-{uuid.uuid4().hex[:6]}"
    r = httpx.post(
        f"{API_URL}/api/svc/work-report-fields/apply-template",
        headers=headers,
        json={
            "template_id": "treadmill_ppm",
            "scope_kind": "equipment_type",
            "scope_value": scope_value,
            "job_types": ["repair", "bogus_type", "Not A Slug!", "ppm"],
        },
        timeout=15.0,
    )
    assert r.status_code == 201
    body = r.json()
    # Slug-formatted values kept (incl. custom types); malformed dropped.
    assert set(body["job_types"]) == {"repair", "bogus_type", "ppm"}
    # Cleanup
    for f in body["created"]:
        httpx.delete(
            f"{API_URL}/api/svc/work-report-fields/{f['id']}",
            headers=headers, timeout=10.0,
        )


# ── Frontend source guards ───────────────────────────────────────


def test_admin_ui_has_templates_button():
    from pathlib import Path
    src = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerWorkReportFields.js").read_text()
    # Header CTA + empty-state CTA.
    assert 'data-testid="wrf-templates-btn"' in src
    assert 'data-testid="wrf-empty-templates-btn"' in src
    # And the modal mounts on toggle.
    assert "function FieldTemplatesModal(" in src
    assert 'data-testid="wrf-templates-modal"' in src


def test_admin_ui_calls_apply_template_endpoint():
    from pathlib import Path
    src = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerWorkReportFields.js").read_text()
    assert "/svc/work-report-fields/templates" in src
    assert "/svc/work-report-fields/apply-template" in src
    # And the modal reloads the field list on success so the
    # newly-seeded rows show up immediately.
    assert "onApplied?.()" in src


# Silence "unused import" lint of datetime/timezone — keeping them
# in case future tests need timestamp assertions.
_ = (datetime, timezone)
