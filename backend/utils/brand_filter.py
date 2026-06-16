"""
Iter 216h18 — Brand-scoped query filter.

Single source of truth for the Master Admin brand context that the
frontend BrandContext (`/app/frontend/src/pages/MasterAdmin/BrandContext.js`)
ships in every list request as `?brand={all|pulse|gymaxis}`.

A record belongs to:
  • PULSE   — `account_type` in {pulse_pro, pulse_lite, pulse}
              OR `is_pulse_admin == True`
              OR `brand` in {pulse, pulse_fitness}
  • GYMAXIS — `account_type` in {full, gymaxis, gymaxis_admin, lite, ""}
              OR account_type absent
              OR `brand` in {gymaxis, ""}
  • all     — no filter applied

`lite`/null are intentionally classified as Pulse Fitness (Pulse Fitness is the
platform default — Pulse Fitness customers are explicitly marked).
This matches the production reality where 21 orgs have account_type
NULL and they are all legacy Pulse Fitness customers.
"""
from __future__ import annotations

from typing import Optional

PULSE_ACCOUNT_TYPES = ["pulse_pro", "pulse_lite", "pulse"]
GYMAXIS_ACCOUNT_TYPES = ["full", "gymaxis", "gymaxis_admin", "lite", ""]
PULSE_BRAND_VALUES = ["pulse", "pulse_fitness"]
GYMAXIS_BRAND_VALUES = ["gymaxis", ""]


def normalise_brand(value: Optional[str]) -> str:
    """Coerce the frontend brand string to one of {all, pulse, gymaxis}."""
    v = (value or "").strip().lower()
    if v in ("pulse", "pulse_fitness"):
        return "pulse"
    if v in ("gymaxis",):
        return "gymaxis"
    return "all"


def brand_filter_clause(brand: Optional[str], collection: str = "users") -> dict:
    """Return a MongoDB query fragment that scopes results to the
    requested brand. Empty dict when brand=all.

    `collection` toggles which field-shape we expect:
      - "users"          : checks `account_type`, `is_pulse_admin`, `brand`
      - "organizations"  : checks `account_type`, `brand`
      - "generic"        : checks `brand` only (for records that
                           already carry a denormalised brand field)
    """
    canonical = normalise_brand(brand)
    if canonical == "all":
        return {}

    if collection == "users":
        if canonical == "pulse":
            return {
                "$or": [
                    {"account_type": {"$in": PULSE_ACCOUNT_TYPES}},
                    {"is_pulse_admin": True},
                    {"brand": {"$in": PULSE_BRAND_VALUES}},
                ],
            }
        return {
            "$or": [
                {"account_type": {"$in": GYMAXIS_ACCOUNT_TYPES}},
                {"account_type": {"$exists": False}},
                {"is_pulse_admin": {"$ne": True}, "brand": {"$in": GYMAXIS_BRAND_VALUES}},
            ],
        }

    if collection == "organizations":
        if canonical == "pulse":
            return {
                "$or": [
                    {"account_type": {"$in": PULSE_ACCOUNT_TYPES}},
                    {"brand": {"$in": PULSE_BRAND_VALUES}},
                ],
            }
        return {
            "$or": [
                {"account_type": {"$in": GYMAXIS_ACCOUNT_TYPES}},
                {"account_type": {"$exists": False}},
                {"brand": {"$in": GYMAXIS_BRAND_VALUES}},
            ],
        }

    # collection == "generic"
    if canonical == "pulse":
        return {"brand": {"$in": PULSE_BRAND_VALUES}}
    return {
        "$or": [
            {"brand": {"$in": GYMAXIS_BRAND_VALUES}},
            {"brand": {"$exists": False}},
        ],
    }


def merge_brand_filter(query: dict, brand: Optional[str], collection: str = "users") -> dict:
    """Merge an existing Mongo query with the brand filter.

    Handles the case where `query` already has an `$or` (rare in the
    codebase) by promoting both into an `$and` so neither clause
    silently overrides the other.
    """
    extra = brand_filter_clause(brand, collection)
    if not extra:
        return query
    if not query:
        return extra
    if "$or" in query and "$or" in extra:
        # Promote both into $and so neither $or is lost.
        merged_and = list(query.get("$and") or [])
        merged_and.append({"$or": query.pop("$or")})
        merged_and.append({"$or": extra.pop("$or")})
        return {**query, **extra, "$and": merged_and}
    return {**query, **extra}
