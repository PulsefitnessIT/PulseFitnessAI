"""One-shot migration: convert legacy equipment photo_url (storage keys) to
browser-loadable public URLs, and move the storage key to `photo_path`.

Idempotent — re-running is safe; records already migrated are skipped.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _public_photo_url(base: str, equipment_id: str) -> str:
    return f"{base}/api/public/equipment/{equipment_id}/photo"


def _public_gallery_url(base: str, equipment_id: str, photo_id: str) -> str:
    return f"{base}/api/public/equipment/{equipment_id}/photos/{photo_id}"


async def main():
    base = (os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").replace("/api", "").rstrip("/")
    if not base:
        print("WARN: no FRONTEND_URL/REACT_APP_BACKEND_URL set. URLs will be relative.")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    main_fixed = 0
    gallery_fixed = 0

    async for eq in db.equipment.find({}, {"_id": 0, "id": 1, "photo_url": 1, "photo_path": 1, "photos": 1}):
        updates = {}
        current = eq.get("photo_url") or ""
        # Legacy = storage key (no http, contains "/"), with no photo_path yet
        if current and not current.startswith("http") and "/" in current and not eq.get("photo_path"):
            updates["photo_path"] = current
            updates["photo_url"] = _public_photo_url(base, eq["id"])

        photos = eq.get("photos") or []
        new_photos = []
        changed = False
        for p in photos:
            url = p.get("url") or ""
            if url and not url.startswith("http") and "/" in url and not p.get("storage_path"):
                p = {**p, "storage_path": url, "url": _public_gallery_url(base, eq["id"], p["id"])}
                changed = True
            new_photos.append(p)
        if changed:
            updates["photos"] = new_photos
            gallery_fixed += 1

        if updates:
            if "photo_path" in updates:
                main_fixed += 1
            await db.equipment.update_one({"id": eq["id"]}, {"$set": updates})

    print(f"Migration complete: main photos fixed={main_fixed}, gallery records updated={gallery_fixed}")


if __name__ == "__main__":
    asyncio.run(main())
