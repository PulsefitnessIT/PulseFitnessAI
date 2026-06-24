"""AI-feature access gate.

Pulse Lite is the free Operations tier: Dashboard / Equipment / Faults /
Documents and **no AI**. This dependency rejects AI endpoints server-side for
true Lite orgs, mirroring the frontend `isPro` gate so the boundary can't be
bypassed by hitting the API directly.

AI stays available for: Pulse Pro, MOD, master admins, and Lite orgs on an
active Pro trial.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.trial_lifecycle import compute_trial_state

_AI_UPGRADE_DETAIL = (
    "AI features are available on Pulse Pro. Upgrade your portal to unlock "
    "AI Diagnosis, fault triage and document Q&A."
)


async def require_ai_access(user: dict = Depends(get_current_user)) -> dict:
    """Allow the request through unless the caller is a true Lite org (no
    active Pro trial). Returns the user dict so it can replace
    `get_current_user` directly on AI endpoints."""
    if user.get("is_master_admin"):
        return user

    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {
            "_id": 0, "account_type": 1, "is_trial": 1, "trial_status": 1,
            "trial_ends_at": 1, "trial_suspends_at": 1, "trial_starts_at": 1,
            "trial_duration_days": 1, "trial_extended_by_days": 1,
        },
    ) or {}

    account_type = (org.get("account_type") or user.get("account_type") or "").lower()
    if account_type != "lite":
        return user  # pulse_pro / full / mod_* all keep AI

    trial = compute_trial_state(org)
    if trial.get("is_trial") and trial.get("can_use_platform"):
        return user  # Lite org on an active Pro trial keeps AI

    raise HTTPException(status_code=403, detail=_AI_UPGRADE_DETAIL)
