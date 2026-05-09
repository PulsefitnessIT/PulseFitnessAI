"""Estate-wide module roll-up — Iter 216av · Phase 3 #8.

A single read-only endpoint summarising module entitlements across every
organisation under master-admin oversight. Used by HQ tier finance
operators for license audits and renewal forecasting.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import MODULE_KEYS, BOLT_ON_MODULES

router = APIRouter()


def _require_master(user: dict):
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")


@router.get("/master-admin/estate/modules-rollup")
async def estate_modules_rollup(user: dict = Depends(get_current_user)):
    """Estate-wide license / module roll-up.

    Returns:
      • by_module — per-module: enabled_orgs / paid / trial_active / trial_expiring_7d
      • by_tier   — orgs grouped by account_type with module density
      • trials_expiring_7d — list of (org_id, org_name, module, expires_at)
      • orphans   — orgs with NO modules enabled (red flag for billing)
    """
    _require_master(user)

    orgs = await db.organizations.find(
        {}, {"_id": 0, "id": 1, "name": 1, "account_type": 1, "modules": 1, "module_trials": 1, "created_at": 1, "subscription_status": 1},
    ).to_list(2000)

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=7)

    by_module: dict[str, dict] = {
        m: {"enabled": 0, "paid": 0, "trial_active": 0, "trial_expiring_7d": 0}
        for m in MODULE_KEYS
    }
    by_tier: dict[str, dict] = defaultdict(lambda: {"count": 0, "modules": defaultdict(int)})
    trials_expiring: list[dict] = []
    orphans: list[dict] = []

    for org in orgs:
        # We don't actually use resolve_module_access here because we want
        # to break out paid vs trial separately for the rollup. Re-derive
        # state directly from the org doc.
        modules_cfg = (org.get("modules") or {})
        trials_cfg = (org.get("module_trials") or {})
        at = org.get("account_type", "full")

        actual_access: dict[str, bool] = {}
        for k in MODULE_KEYS:
            cfg = modules_cfg.get(k) or {}
            paid = bool(cfg.get("enabled"))
            trial = trials_cfg.get(k) or {}
            trial_expires_raw = trial.get("expires_at")
            trial_active = False
            if trial_expires_raw:
                try:
                    te = datetime.fromisoformat(str(trial_expires_raw).replace("Z", "+00:00"))
                    trial_active = te > now
                    if trial_active and te <= horizon:
                        by_module[k]["trial_expiring_7d"] += 1
                        trials_expiring.append({
                            "organization_id": org["id"],
                            "organization_name": org.get("name"),
                            "module": k,
                            "expires_at": te.isoformat(),
                        })
                except (TypeError, ValueError):
                    pass
            # Account-type baseline (full = everything; lite = ops only; pro/mod = ops only by default)
            baseline = False
            if at == "full" or at == "lite" and k == "operations" or at in ("pulse_pro",) and k == "operations":
                baseline = True

            enabled = paid or trial_active or (baseline and k not in BOLT_ON_MODULES)
            actual_access[k] = enabled

            if enabled:
                by_module[k]["enabled"] += 1
                by_tier[at]["modules"][k] += 1
            if paid:
                by_module[k]["paid"] += 1
            if trial_active:
                by_module[k]["trial_active"] += 1

        by_tier[at]["count"] += 1
        if not any(actual_access.values()):
            orphans.append({
                "organization_id": org["id"],
                "organization_name": org.get("name"),
                "account_type": at,
                "subscription_status": org.get("subscription_status"),
            })

    # Convert tier defaults
    by_tier_out = {
        tier: {
            "count": data["count"],
            "modules": dict(data["modules"]),
        }
        for tier, data in by_tier.items()
    }

    trials_expiring.sort(key=lambda r: r["expires_at"])

    return {
        "as_of": now.isoformat(),
        "total_orgs": len(orgs),
        "by_module": by_module,
        "by_tier": by_tier_out,
        "trials_expiring_7d": trials_expiring,
        "orphans": orphans[:50],
        "orphans_count": len(orphans),
    }
