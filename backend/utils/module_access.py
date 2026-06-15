"""Module access entitlements.

A "module" is one of the top-level GymAxis products: `operations`,
`memberships`, `marketing`, or `crm`.

Resolution layers (top wins):
  1. GymAxis master admin → all modules ON.
  2. MOD users (mod_site/mod_branch/mod_org) → none of the gym modules apply.
  3. Org-level matrix (`organization.modules.<key>.enabled`) — toggled by
     Master Admin in `FeatureControlPanel`.
  4. Active 3-day bolt-on trials (`organization.module_trials.<key>.expires_at`
     in the future) — operator can self-serve start; auto-revoke on expiry.
  5. Otherwise fall back to historical account_type defaults so pre-matrix
     orgs keep working.
  6. Per-staff `module_overrides` (set by Owner/Manager in Team Settings)
     can REVOKE access for a specific user even when the org has the
     module on. It cannot grant access the org doesn't have.

Iter 238 — Pulse Lite tier explicitly excludes Memberships / CRM /
Marketing. The matrix can no longer override that *permanently*; instead,
operators must upgrade Lite → Pro and then opt-in to each bolt-on
(potentially via a 3-day trial). This is enforced in the API guards in
`routes/module_trials.py`.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

# The 4 customer-facing modules the matrix controls
MODULE_KEYS = ("operations", "memberships", "marketing", "crm")
# Modules that require Pulse Pro to bolt onto an org. Operations is
# bundled with both Lite and Pro so it never appears here.
BOLT_ON_MODULES = ("memberships", "marketing", "crm")
TRIAL_DURATION_DAYS = 3


def _is_platform_admin(user: Optional[dict]) -> bool:
    """True for elevated platform-wide admins who must never be locked out
    of a module by org-entitlement or per-staff override gates.

    Covers the GymAxis operator master admin (``is_master_admin``) AND Pulse
    Master Admins (role ``pulse_master_admin`` / ``is_pulse_admin``). The
    People role editor explicitly markets the Pulse Master Admin role as
    "platform-wide Master Admin access", yet the user record keeps
    ``is_master_admin=False`` (that flag is reserved for the GymAxis owner).
    Without recognising the Pulse role here, a Pulse Master Admin gets gated
    like ordinary staff — which surfaced as the recurring "CRM is not enabled
    for your account" lock-out at the CRM cross-login.
    """
    if not user:
        return False
    return bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("role") == "pulse_master_admin"
    )


def _account_type_defaults(account_type: str) -> dict[str, bool]:
    if account_type in ("mod_site", "mod_branch", "mod_org"):
        return {"operations": False, "memberships": False, "marketing": False, "crm": False}
    if account_type == "lite":
        return {"operations": True, "memberships": False, "marketing": False, "crm": False}
    if account_type in ("pulse_pro", "full"):
        # Pulse Pro INCLUDES operations + the user can bolt on the rest.
        # Defaults stay False for bolt-ons until the operator opts in
        # (free trial or paid). `full` is GymAxis-side and grants all.
        if account_type == "full":
            return {"operations": True, "memberships": True, "marketing": True, "crm": True}
        return {"operations": True, "memberships": False, "marketing": False, "crm": False}
    return {"operations": True, "memberships": False, "marketing": False, "crm": False}


def _trial_active(org: Optional[dict], module: str) -> bool:
    """True iff org has a non-expired trial running for this module."""
    if not org:
        return False
    trial = ((org.get("module_trials") or {}).get(module) or {})
    expires = trial.get("expires_at")
    if not expires:
        return False
    try:
        dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt > datetime.now(timezone.utc)


def _org_module_access(user: dict, org: Optional[dict]) -> dict[str, bool]:
    """Resolve org-level module access (ignoring per-staff overrides)."""
    if _is_platform_admin(user):
        return {k: True for k in MODULE_KEYS}

    account_type = (org or {}).get("account_type") or user.get("account_type") or "full"
    defaults = _account_type_defaults(account_type)

    org_modules = ((org or {}).get("modules") or {})
    out = {}
    for key in MODULE_KEYS:
        cfg = org_modules.get(key)
        if isinstance(cfg, dict) and "enabled" in cfg:
            out[key] = bool(cfg["enabled"])
        else:
            out[key] = defaults[key]

        # Lite + bolt-on module: only allow if a trial is active. The
        # matrix cannot grant a bolt-on to a Lite org permanently —
        # they must upgrade to Pro first.
        if account_type == "lite" and key in BOLT_ON_MODULES:
            out[key] = _trial_active(org, key)
            continue

        # Active trial overlays — extends access even when the matrix
        # toggle is off (e.g. trial expired and was flipped off).
        if not out[key] and _trial_active(org, key):
            out[key] = True
    return out


def resolve_module_access(user: dict, org: Optional[dict]) -> dict[str, bool]:
    """Return effective {module: bool} for the given user.

    Iter 215dl — derives an extra `crm_lite` boolean. CRM Lite is the
    Marketing-only contact + segment kit; it's bundled with Marketing
    and also implicitly true whenever the user has full CRM access.
    Derived here (not stored) so existing seed data keeps working.
    """
    org_access = _org_module_access(user, org)

    if _is_platform_admin(user) or user.get("role") == "owner":
        out = dict(org_access)
        out["crm_lite"] = bool(out.get("marketing")) or bool(out.get("crm"))
        return out

    overrides = user.get("module_overrides")
    if not isinstance(overrides, dict):
        out = dict(org_access)
        out["crm_lite"] = bool(out.get("marketing")) or bool(out.get("crm"))
        return out

    out = dict(org_access)
    for key in MODULE_KEYS:
        if key in overrides:
            out[key] = bool(org_access.get(key)) and bool(overrides.get(key))
    out["crm_lite"] = bool(out.get("marketing")) or bool(out.get("crm"))
    return out


def has_module(user: dict, org: Optional[dict], module: str) -> bool:
    return bool(resolve_module_access(user, org).get(module, False))


def org_module_access(org: Optional[dict]) -> dict[str, bool]:
    """Pure ORG-level entitlement, independent of any specific user's
    privilege or per-staff overrides. Used by the People drawer's
    "Module access" diagnostics to show org-level vs user-level state."""
    return _org_module_access({}, org)


# ─── CRM modes (Iter 215c) ───────────────────────────────────────
# CRM has two distinct audiences:
#   • leisure  → member lifecycle (auto-bundled with the Memberships module)
#   • business → corporate / supplier sales (paid add-on, granted by Master
#                Admin or via Stripe self-serve upgrade)
# A user with at least one mode enabled has CRM access.

CRM_MODE_KEYS = ("leisure", "business")


def _business_crm_flag(org: Optional[dict]) -> bool:
    """True if Master Admin (or a paid upgrade) has switched on Business CRM."""
    if not org:
        return False
    crm_cfg = ((org.get("modules") or {}).get("crm") or {})
    # Multiple historical key names — accept any of them.
    return bool(
        crm_cfg.get("business_enabled")
        or crm_cfg.get("business")
        or crm_cfg.get("modes", {}).get("business")
    )


def crm_modes(user: dict, org: Optional[dict]) -> dict[str, bool]:
    """Return per-mode CRM access for this user.

    Iter 216h59 — decoupled from Memberships. Operators asked
    (Lee, prod feedback) for Memberships and CRM to work independently,
    so leisure-mode access now follows the CRM module toggle alone.
    Business CRM remains a per-org opt-in flag on top of that.
    """
    if _is_platform_admin(user):
        return {"leisure": True, "business": True}
    access = resolve_module_access(user, org)
    crm_cfg = ((org.get("modules") or {}).get("crm") or {}) if org else {}
    # Leisure (Members) CRM requires the CRM module ON, and is on by default
    # unless an admin / signup choice explicitly turns it off (Corporate-only).
    leisure = bool(access.get("crm")) and bool(crm_cfg.get("leisure_enabled", True))
    # Business CRM is the explicit per-org opt-in on top of CRM access.
    business = bool(_business_crm_flag(org)) and bool(access.get("crm"))
    return {"leisure": leisure, "business": business}


def has_crm_access(user: dict, org: Optional[dict]) -> bool:
    """True if the user can see ANY CRM surface."""
    modes = crm_modes(user, org)
    return any(modes.values())


def trial_status(org: Optional[dict]) -> dict:
    """Return per-module trial status for the org. Used by the upgrade
    UI to know whether each bolt-on can still be started fresh, is
    currently running, or has been used."""
    out: dict[str, dict] = {}
    trials = (org or {}).get("module_trials") or {}
    now = datetime.now(timezone.utc)
    for key in BOLT_ON_MODULES:
        rec = trials.get(key) or {}
        expires = rec.get("expires_at")
        started = rec.get("started_at")
        try:
            exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00")) if expires else None
        except ValueError:
            exp_dt = None
        if not started:
            status = "available"
        elif exp_dt and exp_dt > now:
            status = "active"
        else:
            status = "used"
        out[key] = {
            "status": status,
            "started_at": started,
            "expires_at": expires,
            "days_remaining": max(0, int((exp_dt - now).total_seconds() // 86400)) if exp_dt and exp_dt > now else 0,
        }
    return out


__all__ = [
    "MODULE_KEYS", "BOLT_ON_MODULES", "TRIAL_DURATION_DAYS",
    "CRM_MODE_KEYS",
    "resolve_module_access", "has_module", "org_module_access", "trial_status",
    "crm_modes", "has_crm_access",
]
