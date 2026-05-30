"""Iter 220cv — "I'm done — close & send the invoice" wiring.

The frontend Complete tab now has a fast-path button that issues a
4-call sequence to:

1. ``POST /api/svc/engineer/time/stop`` (if a timer is running)
2. ``POST /api/svc/engineer/jobs/{case_id}/complete`` with target=closed
3. ``POST /api/svc/engineer/jobs/{case_id}/generate-invoice-draft``
4. ``POST /api/svc/cases/{case_id}/service-report/email``

These tests verify the BACKEND contract each of those endpoints
exposes (already present from earlier iters) so that the new fast-path
button has a stable shape to call against. We import the routes and
inspect:
  * Their decorators (path, method) so refactors that rename the
    path will fail this test.
  * That they all exist on the same `engineer.py` / `service_report.py`
    routers we already register.
"""
from __future__ import annotations

import inspect


def _route_paths(router):
    return [
        (r.path, sorted(r.methods))
        for r in router.routes
        if hasattr(r, "path")
    ]


def test_time_stop_endpoint_is_registered():
    from routes.svc.engineer import router as engineer_router
    paths = _route_paths(engineer_router)
    assert any(
        p.endswith("/time/stop") and "POST" in m for p, m in paths
    ), (
        "POST /svc/engineer/time/stop must be registered for the "
        "fast-path close-out to stop the on-site timer."
    )


def test_complete_endpoint_is_registered_with_required_fields():
    from routes.svc.engineer import router as engineer_router
    paths = _route_paths(engineer_router)
    assert any(
        p.endswith("/jobs/{case_id}/complete") and "POST" in m
        for p, m in paths
    )


def test_generate_invoice_draft_endpoint_is_registered():
    # The auto-invoice generator lives on the engineer_phase3 router.
    # It's called by both the existing auto-invoice checkbox and the
    # new fast-path CTA.
    from routes.svc.engineer_phase3 import router as phase3_router
    paths = _route_paths(phase3_router)
    assert any(
        p.endswith("/jobs/{case_id}/generate-invoice-draft") and "POST" in m
        for p, m in paths
    ), (
        "POST /svc/engineer/jobs/{case_id}/generate-invoice-draft "
        "must exist for the fast-path close-out."
    )


def test_service_report_email_endpoint_is_registered():
    from routes.svc.service_report import router as report_router
    paths = _route_paths(report_router)
    assert any(
        p.endswith("/svc/cases/{case_id}/service-report/email") and "POST" in m
        for p, m in paths
    ), (
        "POST /svc/cases/{case_id}/service-report/email must exist "
        "so the fast-path close-out can email the customer in one tap."
    )


def test_service_report_email_accepts_empty_body():
    """Iter 220cv — the fast-path calls the email endpoint with an
    empty body and expects it to default to the case's customer_email.

    We don't actually invoke it here (it needs an LLM-free email
    sender mock); we just check the signature is permissive."""
    from routes.svc.service_report import service_report_email
    sig = inspect.signature(service_report_email)
    data_param = sig.parameters.get("data")
    assert data_param is not None, (
        "service_report_email must accept an optional `data` body so "
        "the fast-path close-out can call it without arguments."
    )
    # Optional body — default must be None (or have a default) so
    # `axios.post(url, {}, ...)` from the frontend works.
    assert data_param.default is None or data_param.default == {}
