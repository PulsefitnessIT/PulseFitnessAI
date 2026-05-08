"""
Shared Sicon helpers used by both routes/sicon.py and utils/sicon_sync.py.
Lives in utils/ to keep the dependency direction one-way:
  routes/sicon.py → utils/sicon_common.py
  utils/sicon_sync.py → utils/sicon_common.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict

from utils.database import db
from utils.sicon_client import SiconClient, decrypt_value

logger = logging.getLogger(__name__)


async def get_sicon_config(organization_id: str) -> Optional[Dict]:
    """Retrieve Sicon config for an organization."""
    return await db.sicon_config.find_one({"organization_id": organization_id}, {"_id": 0})


async def get_sicon_client(organization_id: str) -> Optional[SiconClient]:
    """Create a SiconClient from stored config. Returns None if not configured."""
    config = await get_sicon_config(organization_id)
    if not config or not config.get("enabled") or not config.get("base_url"):
        return None
    return SiconClient(
        base_url=config["base_url"],
        username=decrypt_value(config.get("username_enc", "")),
        password=decrypt_value(config.get("password_enc", "")),
        company_id=config.get("company_id", 0),
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
