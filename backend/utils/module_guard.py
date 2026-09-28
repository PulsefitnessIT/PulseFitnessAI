"""FastAPI dependency factory: 403 if the caller's org has the module disabled.

Usage at route level:

    from utils.module_guard import require_module

    @router.get("/marketing/campaigns", dependencies=[Depends(require_module("marketing"))])
    async def list_campaigns(...): ...

Iter 215bf — `require_module` now also accepts a tuple/list of module keys
to mean **any of these grants access** (OR semantics). This is used for
"lite CRM" endpoints (contacts, custom-properties, lead-capture forms)
that are honoured under either a CRM **or** a Marketing license, so
Marketing-only customers still have a working contact directory:

    require_module(("crm", "marketing"))   # contacts read/write
    require_module("crm")                  # pipelines / deals / inbox stay CRM-strict

Or at router level via ``APIRouter(dependencies=[...])``. Master admins
always pass — they need to be able to provision/configure orgs whose
modules are off.
"""
from __future__ import annotations
from typing import Callable, Sequence, Union

from fastapi import Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_access import has_module, is_mod_org


ModuleKey = Union[str, Sequence[str]]


def require_module(module_key: ModuleKey) -> Callable:
    keys: tuple[str, ...]
    if isinstance(module_key, str):
        keys = (module_key,)
    else:
        keys = tuple(module_key)
    if not keys:
        raise ValueError("require_module: at least one module key is required")

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("is_master_admin"):
            return user
        org = await db.organizations.find_one(
            {"id": user.get("organization_id")},
            {"_id": 0, "account_type": 1, "modules": 1},
        )
        if not any(has_module(user, org, k) for k in keys):
            label = " or ".join(k.title() for k in keys)
            raise HTTPException(
                403,
                f"This organisation does not have the {label} "
                f"module enabled. Ask your administrator to enable it.",
                headers={"X-Module-Access-Denied": ",".join(keys)},
            )
        return user
    return _dep


def require_module_or_roles(
    modules: Sequence[str] = ("operations",),
    *,
    allow_service_desk: bool = True,
    allow_inventory: bool = True,
    allow_engineer: bool = True,
    allow_mod: bool = True,
) -> Callable:
    """403 unless the caller may use an operational surface (equipment / faults
    / PPM). Access is granted to ANY of:

      • Platform / master admins (never locked out — they provision orgs).
      • A user whose org grants one of ``modules`` (e.g. "operations", and for
        faults also "crm" since the CRM calendar legitimately reads issues).
      • Service-Desk users (``is_service_desk``) — the desk lives in faults /
        equipment / PPM. Includes desk impersonation sessions.
      • Inventory & Distribution users (``is_inventory``).
      • Engineers (``is_engineer`` / ``engineer_id`` / role=="engineer") — the
        Engineer app reads the shared equipment API (Work Visit machine picker,
        manufacturers list) even though the Operations dashboard UI is hidden
        from them. Without this they'd 403 on their own tools.
      • MOD (defence) orgs — they run the Operations Portal / equipment / PPM
        via these shared routers yet never resolve a standard module to true.

    This blocks the users we intend to (e.g. Memberships- or Marketing-only,
    or CRM-only for Operations-specific routers) without breaking the roles
    that share these endpoints. Mirrors `require_module` (403 shape, master
    bypass) but with the operational-role allowances.
    """
    keys = tuple(modules)
    if not keys:
        raise ValueError("require_module_or_roles: at least one module key is required")

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("is_master_admin") or user.get("is_pulse_admin"):
            return user
        if allow_service_desk and user.get("is_service_desk"):
            return user
        if allow_inventory and user.get("is_inventory"):
            return user
        if allow_engineer and (
            user.get("is_engineer") or user.get("engineer_id")
            or (user.get("role") or "").lower() == "engineer"
        ):
            return user
        org = await db.organizations.find_one(
            {"id": user.get("organization_id")},
            {"_id": 0, "account_type": 1, "modules": 1, "is_mod": 1},
        )
        if allow_mod and is_mod_org(org):
            return user
        if any(has_module(user, org, k) for k in keys):
            return user
        label = " or ".join(k.title() for k in keys)
        raise HTTPException(
            403,
            f"The {label} module is not enabled for your account. "
            f"Ask your administrator to grant access.",
            headers={"X-Module-Access-Denied": ",".join(keys)},
        )
    return _dep


__all__ = ["require_module", "require_module_or_roles"]
