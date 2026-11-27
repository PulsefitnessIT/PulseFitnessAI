"""Release E — commercial lifecycle for paid products (purchase, LITE->PRO, cancel, end, reactivate) + reporting.

Every change is recorded in `commercial_events`. Ending a product never deletes data: the organisation, its sites,
equipment and history stay; only the paid entitlement is switched off (Operations falls back to LITE).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from utils.database import db

PAID_MODULES = ("operations", "memberships", "marketing", "crm")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_event(org_id: str, event: str, module: str = "", **meta) -> None:
    await db.commercial_events.insert_one({"id": str(uuid.uuid4()), "organization_id": org_id, "event": event,
                                           "module": module, "at": _now(), **meta})


async def on_module_paid(org_id: str, module: str, *, previous: dict, billing_cycle: str = "monthly",
                         actor_id: str = "") -> None:
    """Called after a module purchase is confirmed. `previous` is the org doc before the change."""
    prev_sub = ((previous.get("module_subscriptions") or {}).get(module) or {})
    if prev_sub.get("status") == "ended":
        event = "reactivated"
    elif module == "operations" and previous.get("account_type") == "lite":
        event = "upgraded_lite_to_pro"
    else:
        event = "purchased"
    s = {f"module_subscriptions.{module}.status": "active", f"module_subscriptions.{module}.billing_cycle": billing_cycle}
    if module == "operations" and previous.get("subscription_tier") in (None, "", "free", "none", "lite"):
        s["subscription_tier"] = "pro"
    await db.organizations.update_one(
        {"id": org_id}, {"$set": s, "$addToSet": {"enabled_modules": module},
                         "$unset": {f"module_subscriptions.{module}.ended_at": "",
                                    f"module_subscriptions.{module}.cancel_at_period_end": ""}})
    await record_event(org_id, event, module, actor_id=actor_id, billing_cycle=billing_cycle,
                       from_account_type=previous.get("account_type"))


async def _org_for_subscription(sub_id: str) -> tuple[Optional[dict], Optional[str]]:
    if not sub_id:
        return None, None
    for m in PAID_MODULES:
        org = await db.organizations.find_one({f"module_subscriptions.{m}.stripe_subscription_id": sub_id}, {"_id": 0})
        if org:
            return org, m
    return None, None


async def end_module(org: dict, module: str, reason: str) -> bool:
    """Switch off a paid product at the end of its subscription. Admin-granted products are left alone."""
    cfg = ((org.get("modules") or {}).get(module) or {})
    if cfg.get("source") != "paid":
        return False
    now = _now()
    s = {f"modules.{module}.enabled": False, f"modules.{module}.source": "ended",
         f"module_subscriptions.{module}.status": "ended", f"module_subscriptions.{module}.ended_at": now,
         f"module_subscriptions.{module}.end_reason": reason, "updated_at": now}
    if module == "operations" and org.get("account_type") in ("pulse_pro", "lite"):
        s["account_type"] = "lite"
        s[f"modules.{module}.enabled"] = True  # LITE Operations stays: same records, Pro features off
        s[f"modules.{module}.tier"] = "lite"
        s[f"modules.{module}.source"] = "lite"
        s["subscription_tier"] = "free"
    res = await db.organizations.update_one({"id": org["id"], f"modules.{module}.source": "paid"},
                                            {"$set": s, **({} if module == "operations" else
                                                           {"$pull": {"enabled_modules": module}})})
    if res.modified_count:
        await record_event(org["id"], "ended", module, reason=reason)
    return bool(res.modified_count)


async def on_subscription_deleted(data: dict) -> bool:
    org, module = await _org_for_subscription(data.get("id"))
    if not org:
        return False
    return await end_module(org, module, "stripe_subscription_ended")


async def on_subscription_updated(data: dict) -> bool:
    org, module = await _org_for_subscription(data.get("id"))
    if not org:
        return False
    cap = bool(data.get("cancel_at_period_end"))
    end = data.get("current_period_end")
    s = {f"module_subscriptions.{module}.cancel_at_period_end": cap,
         f"module_subscriptions.{module}.stripe_status": data.get("status")}
    if end:
        s[f"module_subscriptions.{module}.current_period_end"] = datetime.fromtimestamp(int(end), tz=timezone.utc).isoformat()
    await db.organizations.update_one({"id": org["id"]}, {"$set": s})
    if data.get("status") in ("canceled", "unpaid", "incomplete_expired"):
        await end_module(org, module, f"stripe_status_{data.get('status')}")
    return True


def module_state(org: dict, module: str) -> dict:
    from utils.module_access import _trial_active
    cfg = ((org.get("modules") or {}).get(module) or {})
    sub = ((org.get("module_subscriptions") or {}).get(module) or {})
    src = cfg.get("source")
    if src == "paid" and cfg.get("enabled"):
        status = "cancelling" if sub.get("cancel_at_period_end") else "active"
    elif src == "trial" and _trial_active(org, module):
        status = "trial"
    elif src == "admin" and cfg.get("enabled"):
        status = "included"
    elif sub.get("status") == "ended":
        status = "ended"
    elif module == "operations" and org.get("account_type") == "lite":
        status = "lite"
    else:
        status = "not_subscribed"
    return {"module": module, "status": status, "source": src, "billing_cycle": sub.get("billing_cycle"),
            "current_period_end": sub.get("current_period_end"), "ended_at": sub.get("ended_at"),
            "has_stripe_subscription": bool(sub.get("stripe_subscription_id"))}
