"""GDPR Compliance & Audit Trail utilities."""
from datetime import datetime, timezone
from utils.database import db
import logging

logger = logging.getLogger(__name__)


async def audit_log(
    action: str,
    user_id: str,
    user_email: str,
    resource_type: str = "",
    resource_id: str = "",
    details: str = "",
    ip_address: str = "",
) -> None:
    """Write an immutable audit log entry."""
    entry = {
        "action": action,
        "user_id": user_id,
        "user_email": user_email,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "ip_address": ip_address,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.audit_logs.insert_one(entry)
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")
