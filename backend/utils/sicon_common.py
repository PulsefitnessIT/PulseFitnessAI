"""
Shared Sicon helpers used by both routes/sicon.py and utils/sicon_sync.py.
Lives in utils/ to keep the dependency direction one-way:
  routes/sicon.py → utils/sicon_common.py
  utils/sicon_sync.py → utils/sicon_common.py
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict

from utils.database import db
from utils.sicon_client import SiconClient, decrypt_value

logger = logging.getLogger(__name__)


def env_allow_writes() -> bool:
    """§18/§35 — writes stay OFF unless SICON_ALLOW_WRITES is explicitly truthy."""
    return (os.environ.get("SICON_ALLOW_WRITES") or "").strip().lower() in ("1", "true", "yes", "on")


def env_page_size() -> int:
    """Sicon page size ($max per request). Default 200 — proven working for
    full-estate equipment pagination and ~4x fewer round-trips than 50, which
    matters at 111k-line estates. Override with SICON_PAGE_SIZE if needed."""
    try:
        return int(os.environ.get("SICON_PAGE_SIZE") or 200)
    except (ValueError, TypeError):
        return 200


async def get_sicon_config(organization_id: str) -> Optional[Dict]:
    """Retrieve Sicon config for an organization."""
    return await db.sicon_config.find_one({"organization_id": organization_id}, {"_id": 0})


def get_sicon_client_from_env() -> Optional[SiconClient]:
    """Build a client from server-side SICON_* env vars. Used for the read-side
    import layer / automated tests. Returns None when SICON_BASE_URL is unset."""
    base = (os.environ.get("SICON_BASE_URL") or "").strip()
    if not base:
        return None
    try:
        company_id = int(os.environ.get("SICON_COMPANY_ID") or 0)
    except (ValueError, TypeError):
        company_id = 0
    return SiconClient(
        base_url=base,
        username=os.environ.get("SICON_USERNAME", ""),
        password=os.environ.get("SICON_PASSWORD", ""),
        company_id=company_id,
        allow_writes=env_allow_writes(),
        page_size=env_page_size(),
        contract_base_url=(os.environ.get("SICON_CONTRACT_BASE_URL") or "").strip() or base,
    )


async def get_sicon_client(organization_id: str) -> Optional[SiconClient]:
    """Create a SiconClient from stored config, falling back to SICON_* env
    vars when the org has no DB config. allow_writes/page_size always come from
    the environment so writes cannot be enabled per-org by accident."""
    config = await get_sicon_config(organization_id)
    if not config or not config.get("enabled") or not config.get("base_url"):
        return get_sicon_client_from_env()
    return SiconClient(
        base_url=config["base_url"],
        username=decrypt_value(config.get("username_enc", "")),
        password=decrypt_value(config.get("password_enc", "")),
        company_id=config.get("company_id", 0),
        allow_writes=env_allow_writes(),
        page_size=env_page_size(),
        contract_base_url=config.get("contract_base_url")
        or (os.environ.get("SICON_CONTRACT_BASE_URL") or "").strip()
        or config["base_url"],
    )


async def log_sicon_event(organization_id: str, action: str, details: str,
                           success: bool, user_id: str = "system") -> None:
    """Write an audit log entry for Sicon API activity."""
    await db.sicon_audit_log.insert_one({
        "organization_id": organization_id,
        "action": action,
        "details": details,
        "success": success,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
