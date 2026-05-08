"""Iter 216d — one-shot migrations run on backend boot.

These are idempotent — running them twice does nothing extra. They fix two
data-quality issues reported by the user on production:

  1. Companies House names stored in SCREAMING CAPS.
     Re-cases any org whose `name` is fully uppercase AND has a
     `company_number` (i.e. came from CH) to friendly Title Case.

  2. Pulse Pro / Pulse Lite orgs missing branding inheritance.
     Legacy orgs created before Iter 215el's `onboard_head_office` flow
     have no `branding` field, so the operator-facing UI falls back to
     GymAxis branding. This backfills `branding.company_name = "Pulse
     Fitness"` and the cyan brand colour for any Pulse-tier org that
     doesn't already have one.

Run via the FastAPI startup hook (see server.py).
"""
from __future__ import annotations
import logging
from utils.database import db
from utils.companies_house_client import _smart_case

logger = logging.getLogger(__name__)


async def _recase_companies_house_names() -> int:
    """Re-case org names that look like CH all-caps. Returns count fixed."""
    cursor = db.organizations.find(
        {"company_number": {"$exists": True, "$ne": ""}},
        {"_id": 0, "id": 1, "name": 1},
    )
    fixed = 0
    async for org in cursor:
        name = (org.get("name") or "").strip()
        # Only fix if fully uppercase (or fully title with all caps tokens —
        # e.g. "PULSE FITNESS LIMITED"). Skip names that are already mixed
        # case so we never clobber operator-edited names.
        if not name or name != name.upper():
            continue
        new_name = _smart_case(name)
        if new_name and new_name != name:
            await db.organizations.update_one(
                {"id": org["id"]}, {"$set": {"name": new_name}}
            )
            fixed += 1
            logger.info("[iter216d] recased org %s: '%s' → '%s'", org["id"], name, new_name)
    return fixed


async def _backfill_pulse_branding() -> int:
    """Add branding inheritance to legacy Pulse orgs missing it."""
    cursor = db.organizations.find(
        {
            "account_type": {"$in": ["lite", "pulse_pro"]},
            "$or": [
                {"branding": {"$exists": False}},
                {"branding.company_name": {"$exists": False}},
                {"branding.company_name": ""},
            ],
        },
        {"_id": 0, "id": 1, "name": 1, "branding": 1},
    )
    fixed = 0
    pulse_brand = {"primary_color": "#66ccff", "company_name": "Pulse Fitness"}
    async for org in cursor:
        existing = org.get("branding") or {}
        merged = {**pulse_brand, **{k: v for k, v in existing.items() if v}}
        await db.organizations.update_one(
            {"id": org["id"]}, {"$set": {"branding": merged}}
        )
        fixed += 1
        logger.info("[iter216d] backfilled Pulse branding for org %s (%s)", org["id"], org.get("name"))
    return fixed


async def run_iter_216d_migrations() -> dict:
    """Run all migrations, return a summary dict for the boot log."""
    try:
        recased = await _recase_companies_house_names()
        branded = await _backfill_pulse_branding()
        logger.info("[iter216d] migrations done: recased=%d, branded=%d", recased, branded)
        return {"recased": recased, "branded": branded}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[iter216d] migration failed (non-fatal): %s", exc)
        return {"error": str(exc)}
