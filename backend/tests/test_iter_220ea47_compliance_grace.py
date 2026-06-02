"""Iter 220ea·47 — trial compliance grace for partner engineers.

New partner engineers can claim jobs WITHOUT compliance docs for the first
N days after approval (so they can actually trial the Engineer App). After
the grace lapses, the existing DBS/RTW claim gate re-applies.
"""
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException

from routes import partners


NOW = datetime.now(timezone.utc)


# ── Pure helpers ──────────────────────────────────────────────────

def test_grace_active_for_fresh_approval():
    g = partners._compliance_grace_info({"approved_at": NOW.isoformat()})
    assert g["active"] is True
    assert g["days_left"] in (partners._COMPLIANCE_GRACE_DAYS, partners._COMPLIANCE_GRACE_DAYS - 1)


def test_grace_expired_after_window():
    old = (NOW - timedelta(days=partners._COMPLIANCE_GRACE_DAYS + 5)).isoformat()
    g = partners._compliance_grace_info({"approved_at": old})
    assert g["active"] is False
    assert g["days_left"] == 0


def test_grace_falls_back_to_created_at():
    g = partners._compliance_grace_info({"created_at": (NOW - timedelta(days=1)).isoformat()})
    assert g["active"] is True


def test_grace_inactive_without_anchor():
    assert partners._compliance_grace_info({})["active"] is False


def test_valid_claim_doc_requires_dbs_or_rtw():
    assert partners._has_valid_claim_doc({"compliance_docs": {}}) is False
    assert partners._has_valid_claim_doc({"compliance_docs": {"dbs": {"file": {"k": 1}}}}) is True
    assert partners._has_valid_claim_doc({"compliance_docs": {"rtw": {"file": {"k": 1}}}}) is True
    # Safeguarding / PL alone must NOT unlock claiming.
    assert partners._has_valid_claim_doc({"compliance_docs": {"safeguarding": {"file": {"k": 1}}}}) is False


# ── Claim gate integration (evaluate_engineer_app_access mocked) ──

import asyncio


def _decision(approved_at, docs=None):
    return {
        "allowed": True,
        "reason": "partner_active",
        "subscription": {"status": "active"},
        "app_fee_tier": {"price_gbp": 30},
        "partner": {"approved_at": approved_at, "compliance_docs": docs or {}},
    }


def test_claim_allowed_during_grace_without_docs(monkeypatch):
    async def fake_eval(user):
        return _decision(NOW.isoformat(), docs={})
    monkeypatch.setattr(partners, "evaluate_engineer_app_access", fake_eval)
    out = asyncio.run(partners.require_engineer_compliance_to_claim(user={"id": "u1"}))
    assert out == {"id": "u1"}  # allowed — no 403 despite zero docs


def test_claim_blocked_after_grace_without_docs(monkeypatch):
    old = (NOW - timedelta(days=partners._COMPLIANCE_GRACE_DAYS + 3)).isoformat()

    async def fake_eval(user):
        return _decision(old, docs={})
    monkeypatch.setattr(partners, "evaluate_engineer_app_access", fake_eval)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(partners.require_engineer_compliance_to_claim(user={"id": "u1"}))
    assert ei.value.status_code == 403
    assert ei.value.detail["reason"] == "compliance_required"


def test_claim_allowed_after_grace_with_dbs(monkeypatch):
    old = (NOW - timedelta(days=partners._COMPLIANCE_GRACE_DAYS + 3)).isoformat()

    async def fake_eval(user):
        return _decision(old, docs={"dbs": {"file": {"k": 1}}})
    monkeypatch.setattr(partners, "evaluate_engineer_app_access", fake_eval)
    out = asyncio.run(partners.require_engineer_compliance_to_claim(user={"id": "u1"}))
    assert out == {"id": "u1"}
