"""Feature-gating utilities.

Controls access to account-type-restricted features (KPI, PPM, Sicon, Sage, etc.)
and org-level feature toggles set from Master Admin.

Default behaviour:
    - GymAxis ('full') accounts         → every feature enabled by default
    - Pulse Pro ('pulse_pro') accounts  → PRO_DEFAULT_FEATURES enabled by default
                                           (KPI Engine, AI Audits, Multi-site etc.);
                                           GYMAXIS_ONLY_FEATURES disabled unless
                                           explicitly enabled per-org.
    - Pulse Lite ('lite') accounts      → enterprise features disabled (hard lock,
                                           customer upgrades to Pro to unlock).

Master-admins bypass all checks.
Per-org overrides in `organizations.features[<key>] = bool` always win.
"""
from fastapi import Depends, HTTPException
from utils.auth import get_current_user
from utils.database import db


# Keys that REQUIRE a GymAxis ('full') account — off by default on every Pulse tier.
# These are enterprise integrations that don't fit the Pulse customer journey.
GYMAXIS_ONLY_FEATURES = {
    "sicon_integration",
    "sage_integration",
}

# Keys auto-enabled for BOTH GymAxis ('full') AND Pulse Pro ('pulse_pro').
# Pulse Lite ('lite') users get these OFF by default — upgrading to Pro unlocks them.
PRO_DEFAULT_FEATURES = {
    "kpi_engine",
    "multi_site",
    "ai_audits",
}

# All known feature keys — used so we never 403 an unknown key.
KNOWN_FEATURES = GYMAXIS_ONLY_FEATURES | PRO_DEFAULT_FEATURES | {
    "ppm_engine",
    "qr_scanning",
    "api_access",
    "white_label",
    "crm_pipeline",
    "crm_quotes",
    "crm_tenders",
    "crm_ai_tools",
    "crm_workflows",
    "crm_documents",
}


# Iter 216au · Phase 2 #5 — feature → parent module mapping. When a
# feature requires a parent module (e.g. CRM features need module_access.crm),
# `_feature_enabled_for_user` short-circuits to false if the parent module
# isn't enabled for the org. Keeps `feature_guard` and `module_access` from
# disagreeing in production.
FEATURE_PARENT_MODULE: dict[str, str] = {
    "crm_pipeline":   "crm",
    "crm_quotes":     "crm",
    "crm_tenders":    "crm",
    "crm_ai_tools":   "crm",
    "crm_workflows":  "crm",
    "crm_documents":  "crm",
}


def _feature_default_for_account(feature_key: str, account_type: str) -> bool:
    """Default on/off state for a feature given an account type (before per-org overrides)."""
    if feature_key in GYMAXIS_ONLY_FEATURES:
        return account_type == "full"
    if feature_key in PRO_DEFAULT_FEATURES:
        return account_type in ("full", "pulse_pro")
    # Non-enterprise features default to enabled
    return True


async def _feature_enabled_for_user(user: dict, feature_key: str) -> bool:
    """Resolve whether a feature is enabled for the given user's org."""
    if user.get("is_master_admin"):
        return True

    org_id = user.get("organization_id")
    if not org_id:
        return False

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1, "account_type": 1, "modules": 1, "module_trials": 1})
    if not org:
        return False

    # Iter 216au · Phase 2 #5 — short-circuit when the parent module is
    # disabled. Without this, an org could have `crm_pipeline=true` while
    # `module_access.crm=false`, leading to drive-by 200s on CRM endpoints
    # for orgs that haven't actually paid for the CRM module.
    parent = FEATURE_PARENT_MODULE.get(feature_key)
    if parent:
        from utils.module_access import resolve_module_access  # local import — avoid cycles
        access = resolve_module_access(user, org)
        if not access.get(parent):
            return False

    features = org.get("features") or {}
    account_type = org.get("account_type", "full")

    # Explicit per-org override wins.
    if feature_key in features:
        return bool(features[feature_key])

    return _feature_default_for_account(feature_key, account_type)


def require_feature(feature_key: str):
    """FastAPI dependency factory — 403 if feature is disabled for caller's org."""

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if not await _feature_enabled_for_user(user, feature_key):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature_key}' is not enabled for your account. "
                       f"Contact your account manager to enable it.",
            )
        return user

    return _dep


async def get_enabled_features(user: dict) -> dict:
    """Return the resolved feature map for a user (used by /auth/me and frontend).

    Keys returned: every feature in GYMAXIS_ONLY_FEATURES + PRO_DEFAULT_FEATURES,
    with their effective true/false value accounting for account type + per-org overrides.
    """
    if user.get("is_master_admin"):
        return {k: True for k in (GYMAXIS_ONLY_FEATURES | PRO_DEFAULT_FEATURES)}

    org_id = user.get("organization_id")
    if not org_id:
        return {}

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1, "account_type": 1})
    if not org:
        return {}

    features = dict(org.get("features") or {})
    account_type = org.get("account_type", "full")

    for key in GYMAXIS_ONLY_FEATURES | PRO_DEFAULT_FEATURES:
        if key not in features:
            features[key] = _feature_default_for_account(key, account_type)

    return features
