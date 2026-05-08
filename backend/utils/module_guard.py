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
from utils.module_access import has_module


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
            )
        return user
    return _dep


__all__ = ["require_module"]
