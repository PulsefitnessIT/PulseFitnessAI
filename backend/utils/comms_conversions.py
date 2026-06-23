"""Pulse Fitness AI — Comms conversion attribution (Phase 2).

``record_conversion`` attributes an outcome (booking, payment, quote
accepted, etc.) to the most recent comms campaign that reached the person
within an attribution window — preferring a clicked send, then opened,
then merely sent. Stored in ``comms_conversions`` and rolled up onto the
campaign metrics. Fire-and-forget: never raises into the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from utils.database import db
from routes.marketing.helpers import _new_id, _now_iso

logger = logging.getLogger("comms_conversions")

_DEFAULT_WINDOW_DAYS = 30


async def record_conversion(
    org_id: str, email: str, ctype: str, *,
    value_gbp: float = 0.0, source: str = "", meta: dict | None = None,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> bool:
    try:
        email = (email or "").strip().lower()
        if not org_id or not email or "@" not in email:
            return False
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        # attribution: clicked > opened > sent, most recent first
        campaign_id = None
        for q in (
            {"clicked_at": {"$nin": [None, ""]}},
            {"opened_at": {"$nin": [None, ""]}},
            {},
        ):
            msg = await db.marketing_messages.find_one(
                {"organization_id": org_id, "contact_email": email,
                 "sent_at": {"$gte": cutoff}, **q},
                sort=[("sent_at", -1)],
            )
            if msg:
                campaign_id = msg.get("campaign_id")
                break
        doc = {
            "id": _new_id(), "organization_id": org_id, "email": email,
            "type": ctype, "value_gbp": float(value_gbp or 0), "source": source,
            "campaign_id": campaign_id, "meta": meta or {}, "created_at": _now_iso(),
        }
        await db.comms_conversions.insert_one(doc)
        if campaign_id:
            await db.marketing_campaigns.update_one(
                {"id": campaign_id},
                {"$inc": {"metrics.converted": 1, "metrics.revenue_gbp": float(value_gbp or 0)}},
            )
        from routes.comms_growth import fire_comms_webhook
        await fire_comms_webhook(org_id, "conversion.recorded",
                                 {"email": email, "type": ctype, "value_gbp": float(value_gbp or 0),
                                  "campaign_id": campaign_id})
        return True
    except Exception as exc:  # pragma: no cover — never break the caller
        logger.info("[comms-conv] record failed (%s/%s): %s", ctype, email, exc)
        return False
