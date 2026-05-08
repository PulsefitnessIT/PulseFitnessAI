"""Tiny helper around routes/notification_prefs.py:can_send.

We keep this in a separate file so utils/lifecycle_emails.py can import
without forcing a routes->utils circular dep.
"""
from __future__ import annotations

# Map lifecycle templates to operator notification categories.
LIFECYCLE_TO_CATEGORY = {
    "welcome": "transactional",      # always send — onboarding-critical
    "day2_check": "feature_tips",
    "mid_trial": "feature_tips",
    "expiry_warn": "billing_alerts",
    "winback": "marketing",
}


async def can_send_lifecycle_email(user_id: str, template: str) -> bool:
    if not user_id:
        return True
    category = LIFECYCLE_TO_CATEGORY.get(template, "feature_tips")
    if category == "transactional":
        return True
    # Lazy import to avoid circular.
    from routes.notification_prefs import can_send
    return await can_send("user", user_id, category)
