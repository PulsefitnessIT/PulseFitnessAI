"""Module trials + Lite-to-Pro upgrade (Iter 238).

Self-serve endpoints for operators to:
  • Start a 3-day free trial of Memberships / CRM / Marketing (Pulse Pro
    only — Lite must upgrade first).
  • Upgrade their org from Pulse Lite → Pulse Pro.
  • Read which bolt-ons they can still trial vs already used.

Pricing references in `pricing_plans` are the source of truth for the UI;
this module only mutates `organizations.account_type` + `module_trials`
+ records to the existing `account_change_audit` collection.

Auth: org owner or master admin. Operators below owner level get a
clear 403 with `notifyApiError`-friendly detail so the upgrade UI can
explain the next step.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import (
    BOLT_ON_MODULES, TRIAL_DURATION_DAYS,
    resolve_module_access, trial_status,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def _resolve_org(user: dict) -> dict:
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0},
    )
    if not org:
        # Iter 216h272 — last-resort safety net: master admins must
        # never see the operator-facing module pages crash on a
        # missing org doc. The startup seeder normally self-heals
        # this on boot, but if it failed (e.g. mid-restore) we still
        # synthesise a minimal full-access org so the UI can render.
        if user.get("is_master_admin"):
            return {
                "id": user.get("organization_id") or "master-admin",
                "name": "Pulse Fitness AI Admin",
                "account_type": "full",
                "subscription_tier": "premium",
                "modules": {
                    "memberships": {"enabled": True, "source": "seed"},
                    "crm": {"enabled": True, "source": "seed"},
                    "marketing": {"enabled": True, "source": "seed"},
                },
            }
        raise HTTPException(404, "Organisation not found")
    return org


def _require_owner_or_master(user: dict) -> None:
    if user.get("is_master_admin"):
        return
    role = (user.get("role") or "").lower()
    if role == "owner":
        return
    raise HTTPException(
        403, "Only the organisation owner (or a master admin) can change billing — please ask them to upgrade.",
    )


@router.get("/me/module-trials")
async def get_module_trials(user: dict = Depends(get_current_user)):
    """Operator-facing: what's the upgrade picture for my org?"""
    org = await _resolve_org(user)
    return {
        "account_type": org.get("account_type"),
        "module_access": resolve_module_access(user, org),
        "trials": trial_status(org),
        "trial_duration_days": TRIAL_DURATION_DAYS,
        "bolt_on_modules": list(BOLT_ON_MODULES),
        "is_owner": (user.get("role") or "").lower() == "owner" or bool(user.get("is_master_admin")),
    }


@router.post("/me/module-trials/start")
async def start_module_trial(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    _require_owner_or_master(user)
    module = (body.get("module") or "").strip().lower()
    if module not in BOLT_ON_MODULES:
        raise HTTPException(400, f"module must be one of {list(BOLT_ON_MODULES)}")
    org = await _resolve_org(user)
    if (org.get("account_type") or "").lower() == "lite":
        raise HTTPException(
            400,
            "Pulse Lite cannot start bolt-on trials. Upgrade to Pulse Pro first, then start your free trial.",
        )
    statuses = trial_status(org)
    current = statuses.get(module, {})
    if current.get("status") == "used":
        raise HTTPException(409, f"The free trial of {module.capitalize()} has already been used.")
    if current.get("status") == "active":
        raise HTTPException(409, f"A trial of {module.capitalize()} is already running.")

    started_at = _now()
    expires_at = started_at + timedelta(days=TRIAL_DURATION_DAYS)
    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            f"module_trials.{module}.started_at": started_at.isoformat(),
            f"module_trials.{module}.expires_at": expires_at.isoformat(),
            f"module_trials.{module}.started_by": user["id"],
            f"modules.{module}.enabled": True,
            f"modules.{module}.source": "trial",
            "updated_at": _now_iso(),
        }},
    )
    await db.account_change_audit.insert_one({
        "id": f"trial-{org['id']}-{module}-{int(started_at.timestamp())}",
        "organization_id": org["id"],
        "actor_id": user["id"],
        "kind": "module_trial_start",
        "module": module,
        "expires_at": expires_at.isoformat(),
        "created_at": _now_iso(),
    })
    return {
        "ok": True,
        "module": module,
        "started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "days_remaining": TRIAL_DURATION_DAYS,
    }


@router.post("/me/upgrade-to-pro")
async def upgrade_to_pulse_pro(
    body: dict = Body(default_factory=dict), user: dict = Depends(get_current_user),
):
    """Self-serve Lite → Pro upgrade. Records to the audit trail and
    optionally auto-starts trials for any modules the operator selected
    on the upgrade screen.

    body = {"start_trials": ["memberships", "crm", "marketing"]}
    """
    _require_owner_or_master(user)
    org = await _resolve_org(user)
    current = (org.get("account_type") or "").lower()
    if current == "pulse_pro":
        return {"ok": True, "already_pro": True}
    if current != "lite":
        raise HTTPException(400, f"Cannot upgrade from '{current}' — only Pulse Lite orgs upgrade to Pro.")

    await db.organizations.update_one(
        {"id": org["id"]},
        {"$set": {
            "account_type": "pulse_pro",
            "previous_account_type": current,
            "upgraded_at": _now_iso(),
            "upgraded_by": user["id"],
            "updated_at": _now_iso(),
        }},
    )
    await db.account_change_audit.insert_one({
        "id": f"upgrade-{org['id']}-{int(_now().timestamp())}",
        "organization_id": org["id"],
        "actor_id": user["id"],
        "kind": "account_type_upgrade",
        "from": current,
        "to": "pulse_pro",
        "created_at": _now_iso(),
    })

    # Optional bolt-on trials at the same time.
    requested = body.get("start_trials") or []
    started: list[dict] = []
    if isinstance(requested, list):
        for module in requested:
            mod = str(module).strip().lower()
            if mod not in BOLT_ON_MODULES:
                continue
            # Re-fetch org so trial_status sees the previous record.
            fresh = await _resolve_org(user)
            statuses = trial_status(fresh)
            if statuses.get(mod, {}).get("status") == "used":
                continue
            started_at = _now()
            expires_at = started_at + timedelta(days=TRIAL_DURATION_DAYS)
            await db.organizations.update_one(
                {"id": org["id"]},
                {"$set": {
                    f"module_trials.{mod}.started_at": started_at.isoformat(),
                    f"module_trials.{mod}.expires_at": expires_at.isoformat(),
                    f"module_trials.{mod}.started_by": user["id"],
                    f"modules.{mod}.enabled": True,
                    f"modules.{mod}.source": "trial",
                }},
            )
            started.append({
                "module": mod,
                "expires_at": expires_at.isoformat(),
                "days_remaining": TRIAL_DURATION_DAYS,
            })

    return {
        "ok": True,
        "account_type": "pulse_pro",
        "trials_started": started,
    }
