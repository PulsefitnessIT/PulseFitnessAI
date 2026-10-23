"""Creative Studio image storage — Emergent Object Storage instead of base64-in-Mongo.

Each stored variant looks like::

    {"storage_path": "...", "token": "<random>", "mime": "image/png",
     "model": "...", "url": "/api/marketing/creative/file/<token>"}

The ``url`` is an unguessable capability link (marketing imagery is meant
to be shared), served through the backend — storage URLs are never exposed.
"""
from __future__ import annotations

import asyncio
import base64
import secrets
import uuid

from fastapi import HTTPException

from utils.database import APP_NAME, db, get_object, put_object
from routes.marketing.helpers import logger

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
        "image/gif": "gif", "image/svg+xml": "svg"}
FILE_URL_PREFIX = "/api/marketing/creative/file/"


def can_create(user: dict) -> bool:
    """Owners, Managers and Master Admins may generate / upload / delete."""
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return True
    return (user.get("role") or "").lower() in {"owner", "manager", "master_admin", "pulse_master_admin"}


def require_creator(user: dict) -> None:
    if not can_create(user):
        raise HTTPException(403, "Only Owners, Managers and Master Admins can create or change Creative Studio images")


async def store_image(org_id: str, data: bytes, mime: str, model: str) -> dict:
    mime = (mime or "image/png").split(";", 1)[0].strip().lower()
    path = f"{APP_NAME}/marketing-creative/{org_id}/{uuid.uuid4()}.{_EXT.get(mime, 'bin')}"
    result = await asyncio.to_thread(put_object, path, data, mime)
    token = secrets.token_urlsafe(24)
    return {"storage_path": result.get("path") or path, "token": token, "mime": mime,
            "size": result.get("size"), "model": model, "url": f"{FILE_URL_PREFIX}{token}"}


def _split_data_url(url: str) -> tuple[str, bytes] | None:
    if not (url or "").startswith("data:") or "," not in url:
        return None
    head, b64 = url.split(",", 1)
    mime = head[5:].split(";", 1)[0] or "image/png"
    try:
        return mime, base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None


async def store_data_url(org_id: str, url: str, model: str | None) -> dict:
    """Move a ``data:`` URL into storage; non-data URLs are returned untouched."""
    parsed = _split_data_url(url)
    if not parsed:
        return {"url": url, "model": model}
    mime, raw = parsed
    return await store_image(org_id, raw, mime, model or "unknown")


async def variant_b64(variant: dict) -> str | None:
    """Base64 payload of a variant (for passing as a Nano Banana reference)."""
    url = variant.get("url") or ""
    if url.startswith("data:") and "," in url:
        return url.split(",", 1)[1]
    if variant.get("storage_path"):
        try:
            raw, _ = await asyncio.to_thread(get_object, variant["storage_path"])
            return base64.b64encode(raw).decode()
        except Exception as exc:  # noqa: BLE001
            logger.info("[creative] reference fetch failed: %s", exc)
    return None


async def migrate_assets(assets: list[dict]) -> None:
    """Move any legacy base64 variants of these assets into storage (in place)."""
    for a in assets:
        variants = a.get("variants") or []
        if not any((v.get("url") or "").startswith("data:") for v in variants):
            continue
        try:
            new = [await store_data_url(a["organization_id"], v.get("url") or "", v.get("model"))
                   if (v.get("url") or "").startswith("data:") else v for v in variants]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[creative] storage migration failed for %s: %s", a.get("id"), exc)
            continue
        await db.marketing_creative_assets.update_one({"id": a["id"]}, {"$set": {"variants": new}})
        a["variants"] = new
