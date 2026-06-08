"""Iter 222 — Integration Health access gate.

Pulse Master Admins must be able to read the integration-health surface
(they legitimately monitor the third-party services their portal depends
on), while unprivileged users stay blocked.

End-to-end was verified by curl against the live preview: the Pulse test
admin (pulse.admin.test@pulsefitness.com) now gets the 5-check summary
instead of a 403. This unit test pins the pure authorization logic.
"""
import pytest
from fastapi import HTTPException

from routes.integration_health import _require_health_access


def test_master_admin_allowed():
    _require_health_access({"is_master_admin": True})  # no raise


def test_pulse_admin_allowed():
    _require_health_access({"is_pulse_admin": True})  # no raise


def test_unprivileged_blocked():
    with pytest.raises(HTTPException) as exc:
        _require_health_access({"role": "owner"})
    assert exc.value.status_code == 403


def test_empty_user_blocked():
    with pytest.raises(HTTPException):
        _require_health_access({})
