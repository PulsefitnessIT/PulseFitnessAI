"""Memberships MongoDB index ensure on app startup.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations


from fastapi import APIRouter

from utils.database import db


router = APIRouter(tags=["memberships"])



async def ensure_memberships_indexes() -> None:
    await db.members.create_index([("email", 1)], unique=True, sparse=True)
    await db.members.create_index([("organization_id", 1), ("status", 1)])
    await db.membership_plans.create_index([("organization_id", 1), ("active", 1)])
    await db.member_memberships.create_index([("member_id", 1), ("status", 1)])
    await db.member_memberships.create_index([("organization_id", 1), ("status", 1)])
    await db.class_templates.create_index([("organization_id", 1), ("archived", 1)])
    await db.class_occurrences.create_index([("organization_id", 1), ("starts_at", 1)])
    await db.class_occurrences.create_index([("template_id", 1), ("starts_at", 1)], unique=True)
    await db.bookings.create_index([("member_id", 1), ("status", 1)])
    await db.bookings.create_index([("occurrence_id", 1), ("status", 1)])
    await db.qr_rotation_secret.create_index([("member_id", 1)], unique=True)
    await db.member_checkins.create_index([("organization_id", 1), ("at", -1)])
