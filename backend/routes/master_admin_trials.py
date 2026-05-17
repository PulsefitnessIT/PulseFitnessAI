"""
Master Admin · Trials sub-router.

Iter 216h177 — Extracted from `routes/master_admin.py` as part of the
4,283 LoC → 5-6 focused routers decomposition (P1 perf-audit task).

Owns the trial lifecycle endpoints exposed under
`/api/master-admin/trials/*`: list trials, summarise conversion metrics,
extend a trial, open a Stripe Checkout to convert, and the manual
"mark converted" override.

Helpers `require_master_admin` and `log_activity` are still owned by the
parent `master_admin.py` module — we import them here so a single
audit-logging seam stays in one place.
"""
from datetime import datetime, timezone, timedelta
import logging
import os

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import log_activity, require_master_admin


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/master-admin/trials")
async def list_trials(user: dict = Depends(get_current_user)) -> dict:
    """List all trial organizations with status and time remaining."""
    require_master_admin(user)
    from utils.trial_lifecycle import compute_trial_state

    orgs = await db.organizations.find(
        {"is_trial": True}, {"_id": 0}
    ).sort("trial_ends_at", 1).to_list(500)

    result = []
    for o in orgs:
        state = compute_trial_state(o)
        primary = o.get("primary_contact", {}) or {}
        user_count = await db.users.count_documents({"organization_id": o["id"]})
        result.append({
            "id": o["id"],
            "name": o.get("name"),
            "legal_name": o.get("legal_name"),
            "tier": o.get("subscription_tier"),
            "primary_contact": {
                "name": primary.get("name", ""),
                "email": primary.get("email", ""),
            },
            "user_count": user_count,
            "trial_started_at": o.get("trial_started_at"),
            "trial_ends_at": o.get("trial_ends_at"),
            "trial_suspends_at": o.get("trial_suspends_at"),
            "trial_duration_days": o.get("trial_duration_days", 14),
            "trial_status": state.get("status"),
            "days_left": state.get("days_left", 0),
            "read_only": state.get("read_only", False),
            "locked_out": state.get("locked_out", False),
            "extended_by_days": o.get("trial_extended_by_days", 0),
            "reminders_sent": o.get("trial_reminders_sent", []),
            "converted_at": o.get("converted_at"),
        })
    return {"trials": result, "count": len(result)}


def _record_convert_time(o: dict, convert_times: list) -> None:
    """Append the days-to-convert for a converted org to convert_times."""
    try:
        started = datetime.fromisoformat(
            (o.get("trial_started_at") or o.get("created_at", "")).replace("Z", "+00:00")
        )
        converted = datetime.fromisoformat(o.get("converted_at", "").replace("Z", "+00:00"))
        convert_times.append((converted - started).total_seconds() / 86400.0)
    except Exception:
        pass


def _is_expiring_this_week(o: dict, now: datetime, week_out: datetime) -> bool:
    try:
        ends_at = datetime.fromisoformat(o.get("trial_ends_at", "").replace("Z", "+00:00"))
        return now <= ends_at <= week_out
    except Exception:
        return False


async def _classify_org_source(org_id: str) -> str:
    """Return 'crm_linked' or 'direct' based on the CRM source for this org."""
    crm_row = await db.crm_companies.find_one(
        {"linked_organization_id": org_id},
        {"_id": 0, "source": 1}
    )
    if crm_row and crm_row.get("source") and crm_row["source"] != "onboarding_packet_trial":
        return "crm_linked"
    return "direct"


async def _aggregate_trial_counts(orgs: list, now: datetime, week_out: datetime) -> tuple:
    """Walk the trial org list; return (by_status, by_source, convert_times, expiring_this_week)."""
    from utils.trial_lifecycle import compute_trial_state

    by_status = {"active": 0, "expiring_soon": 0, "expired": 0, "suspended": 0, "converted": 0}
    by_source = {"crm_linked": 0, "direct": 0}
    convert_times: list = []
    expiring_this_week = 0

    for o in orgs:
        if o.get("trial_status") == "converted":
            by_status["converted"] += 1
            _record_convert_time(o, convert_times)
        elif o.get("is_trial"):
            status = compute_trial_state(o).get("status", "active")
            by_status[status] = by_status.get(status, 0) + 1
            if _is_expiring_this_week(o, now, week_out):
                expiring_this_week += 1
        by_source[await _classify_org_source(o["id"])] += 1

    return by_status, by_source, convert_times, expiring_this_week


async def _compute_conversion_metrics(cutoff_30d: datetime, now: datetime, convert_times: list) -> tuple:
    """Compute (converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert)."""
    converted_30d = await db.organizations.count_documents({
        "trial_status": "converted",
        "converted_at": {"$gte": cutoff_30d.isoformat()}
    })
    ended_30d = await db.organizations.count_documents({
        "$or": [
            {"trial_status": "converted", "converted_at": {"$gte": cutoff_30d.isoformat()}},
            {"is_trial": True, "trial_ends_at": {"$lte": now.isoformat(), "$gte": cutoff_30d.isoformat()}},
        ]
    })
    conversion_rate_30d = round((converted_30d / ended_30d * 100), 1) if ended_30d > 0 else 0
    avg_days_to_convert = round(sum(convert_times) / len(convert_times), 1) if convert_times else 0
    return converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert


@router.get("/master-admin/trials/summary")
async def trials_summary(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate trial metrics for Master Admin dashboard widget."""
    require_master_admin(user)

    orgs = await db.organizations.find(
        {"$or": [{"is_trial": True}, {"trial_status": "converted"}]},
        {"_id": 0}
    ).to_list(2000)

    now = datetime.now(timezone.utc)
    week_out = now + timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    by_status, by_source, convert_times, expiring_this_week = await _aggregate_trial_counts(orgs, now, week_out)
    converted_30d, ended_30d, conversion_rate_30d, avg_days_to_convert = await _compute_conversion_metrics(
        cutoff_30d, now, convert_times
    )

    return {
        "total": by_status["active"] + by_status["expiring_soon"] + by_status["expired"] + by_status["suspended"],
        "by_status": by_status,
        "converted_30d": converted_30d,
        "ended_30d": ended_30d,
        "conversion_rate_30d": conversion_rate_30d,
        "avg_days_to_convert": avg_days_to_convert,
        "expiring_this_week": expiring_this_week,
        "by_source": by_source,
    }


@router.post("/master-admin/trials/{org_id}/extend")
async def extend_trial(org_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Extend a trial by N days. Resets reminder flags so the customer gets another nudge."""
    require_master_admin(user)
    days = int(body.get("days", 7))
    if days < 1 or days > 30:
        raise HTTPException(status_code=400, detail="days must be between 1 and 30")
    reason = (body.get("reason") or "").strip()

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or not org.get("is_trial"):
        raise HTTPException(status_code=404, detail="Trial org not found")

    current_end = org.get("trial_ends_at")
    try:
        end_dt = datetime.fromisoformat(current_end.replace("Z", "+00:00"))
    except Exception:
        end_dt = datetime.now(timezone.utc)

    new_end = end_dt + timedelta(days=days)
    new_suspend = new_end + timedelta(days=30)

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "trial_ends_at": new_end.isoformat(),
            "trial_suspends_at": new_suspend.isoformat(),
            "trial_status": "active",
            "status": "active",
            "trial_extended_by_days": (org.get("trial_extended_by_days", 0) + days),
            "trial_reminders_sent": [],
        }}
    )
    await log_activity(
        "trial_extended",
        f"Extended by {days} days. Reason: {reason or '—'}",
        user.get("email", ""), "organization", org_id,
    )
    return {"success": True, "new_end": new_end.isoformat(), "days_added": days}


def _resolve_stripe_price_id(target_tier: str) -> str:
    """Map a tier name to the configured Stripe price ID. Raises 400 if unconfigured."""
    from utils.database import STRIPE_PRICE_PRO, STRIPE_PRICE_STARTER, STRIPE_PRICE_ENTERPRISE
    price_map = {"starter": STRIPE_PRICE_STARTER, "pro": STRIPE_PRICE_PRO, "enterprise": STRIPE_PRICE_ENTERPRISE}
    price_id = price_map.get(target_tier)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"No Stripe price configured for tier {target_tier}")
    return price_id


def _build_trial_convert_session(org: dict, org_id: str, target_tier: str, origin_url: str):
    """Create a Stripe Checkout session for a trial → paid conversion."""
    import stripe
    from utils.database import STRIPE_API_KEY
    stripe.api_key = STRIPE_API_KEY
    price_id = _resolve_stripe_price_id(target_tier)
    primary_email = (org.get("primary_contact", {}) or {}).get("email", "")
    return stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{origin_url.rstrip('/')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}&trial_convert={org_id}",
        cancel_url=f"{origin_url.rstrip('/')}/dashboard",
        customer_email=primary_email or None,
        metadata={"trial_org_id": org_id, "trial_convert": "true", "tier": target_tier},
    )


@router.post("/master-admin/trials/{org_id}/convert")
async def convert_trial_to_paid(org_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Generate a Stripe Checkout session so the owner can upgrade to paid."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org or not org.get("is_trial"):
        raise HTTPException(status_code=404, detail="Trial org not found")

    target_tier = body.get("tier") or org.get("subscription_tier") or "pro"
    origin_url = body.get("origin_url", "") or os.environ.get("FRONTEND_URL", "")
    if not origin_url:
        raise HTTPException(status_code=400, detail="origin_url required")

    try:
        session = _build_trial_convert_session(org, org_id, target_tier, origin_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stripe checkout creation failed for org {org_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)[:200]}")

    await log_activity(
        "trial_convert_initiated",
        f"Stripe checkout created for tier {target_tier}",
        user.get("email", ""), "organization", org_id,
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/master-admin/trials/{org_id}/mark-converted")
async def mark_converted(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Manually mark a trial as converted."""
    require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "trial_status": "converted",
            "status": "active",
            "converted_at": datetime.now(timezone.utc).isoformat(),
            "is_trial": False,
        }}
    )
    await log_activity("trial_marked_converted", "", user.get("email", ""), "organization", org_id)
    return {"success": True}
