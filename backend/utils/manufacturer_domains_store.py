"""Master-admin editable overrides for the manufacturer-domain map.

The seed list lives in :pydata:`utils.equipment_image_lookup.MANUFACTURER_DOMAINS`
(33+ entries hand-curated for known gym brands). Operators occasionally
need to add a niche supplier the seed doesn't cover — e.g. a new local
brand or a regional distributor — without waiting for a release.

This module backs that with a Mongo-stored override list. The catalogue
ingest paths read both: seed first, then overlay overrides. Overrides
can also disable a seed entry (via ``enabled=False``).

Iter 238f: ships the override mechanism + admin CRUD. The hardcoded
seed stays as the source of truth so a fresh DB still works.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils.database import db
from utils.equipment_image_lookup import MANUFACTURER_DOMAINS as _SEED


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_key(raw: str) -> str:
    return (raw or "").strip().lower()


async def list_overrides() -> list[dict]:
    """All admin-added or admin-modified entries, newest first."""
    cursor = db.manufacturer_domains_overrides.find(
        {}, {"_id": 0},
    ).sort("created_at", -1)
    return await cursor.to_list(length=500)


async def upsert_override(*, key: str, domain: str, label: str | None = None,
                          enabled: bool = True, actor: str | None = None) -> dict:
    """Create or update an override row keyed by lowercase manufacturer
    name. Domain is normalised by stripping protocol/leading-www."""
    k = _normalise_key(key)
    if not k:
        raise ValueError("key required")
    d = (domain or "").strip().lower()
    d = d.removeprefix("http://").removeprefix("https://").removeprefix("www.")
    d = d.split("/", 1)[0]
    if not d:
        raise ValueError("domain required")

    now = _now()
    row = {
        "key": k,
        "domain": d,
        "label": (label or k.title()).strip()[:80],
        "enabled": bool(enabled),
        "updated_at": now,
        "updated_by": actor,
    }
    await db.manufacturer_domains_overrides.update_one(
        {"key": k},
        {"$set": row, "$setOnInsert": {"created_at": now, "created_by": actor}},
        upsert=True,
    )
    return await db.manufacturer_domains_overrides.find_one({"key": k}, {"_id": 0})


async def delete_override(key: str) -> int:
    res = await db.manufacturer_domains_overrides.delete_one({"key": _normalise_key(key)})
    return res.deleted_count


async def merged_domains() -> dict[str, dict[str, Any]]:
    """Return ``{key: {domain, label, enabled, source}}`` — seed first,
    overrides applied on top. Used by ingest jobs and the admin UI."""
    out: dict[str, dict[str, Any]] = {}
    for k, dom in _SEED.items():
        out[k] = {"key": k, "domain": dom, "label": k.title(), "enabled": True, "source": "seed"}
    async for row in db.manufacturer_domains_overrides.find({}, {"_id": 0}):
        out[row["key"]] = {
            "key": row["key"],
            "domain": row.get("domain", ""),
            "label": row.get("label") or row["key"].title(),
            "enabled": bool(row.get("enabled", True)),
            "source": "override",
        }
    return out


async def merged_simple_map() -> dict[str, str]:
    """Simple ``{key: domain}`` map (enabled rows only) for use by the
    legacy lookup paths that don't care about labels/sources."""
    return {
        k: row["domain"]
        for k, row in (await merged_domains()).items()
        if row.get("enabled") and row.get("domain")
    }


__all__ = [
    "list_overrides", "upsert_override", "delete_override",
    "merged_domains", "merged_simple_map",
]
