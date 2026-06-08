"""Iter 222 — Pulse Master Admins can read the admin list (Permissions matrix).

The SOC-2 Permissions matrix in People → Roles loads `/master-admin/pulse-admins`.
That GET is now readable by Pulse Master Admins (provisioning create/revoke
stays GymAxis-master-only). This pins the pure authorization helper.

End-to-end verified by curl: the Pulse test admin now gets the admins list
(was 403 "Master admin access required").
"""
import pytest
from fastapi import HTTPException

from routes.pulse_master_admin import _require_pulse_or_master, _require_gymaxis_master


def test_pulse_admin_can_read_list():
    _require_pulse_or_master({"role": "pulse_master_admin"})  # no raise
    _require_pulse_or_master({"is_pulse_admin": True})        # no raise


def test_master_admin_can_read_list():
    _require_pulse_or_master({"is_master_admin": True})  # no raise


def test_unprivileged_blocked_from_list():
    with pytest.raises(HTTPException) as exc:
        _require_pulse_or_master({"role": "owner"})
    assert exc.value.status_code == 403


def test_provisioning_still_master_only():
    # Pulse admins must NOT be able to provision/revoke other admins.
    with pytest.raises(HTTPException):
        _require_gymaxis_master({"is_pulse_admin": True})
    with pytest.raises(HTTPException):
        _require_gymaxis_master({"role": "pulse_master_admin"})
