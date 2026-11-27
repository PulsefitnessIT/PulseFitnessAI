"""Release 1 — imported customers can't buy or start paid products online until Pulse has passed a genuine
Stripe test-mode lifecycle and sets IMPORTED_CUSTOMER_PURCHASES_ENABLED=true. Self-signup journeys are untouched."""
import os

from fastapi import Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


async def assert_imported_purchase_allowed(user: dict) -> None:
    if os.environ.get("IMPORTED_CUSTOMER_PURCHASES_ENABLED", "").strip().lower() == "true":
        return
    org = await db.organizations.find_one({"id": user.get("organization_id")},
                                          {"_id": 0, "activated_via_invitation": 1, "onboarding_status": 1})
    if org and (org.get("activated_via_invitation") or org.get("onboarding_status") == "pending_activation"):
        raise HTTPException(status_code=403, detail="Online purchasing for your account isn't open yet. Contact Pulse Fitness to add products.")


async def imported_purchase_gate(user: dict = Depends(get_current_user)) -> None:
    await assert_imported_purchase_allowed(user)
