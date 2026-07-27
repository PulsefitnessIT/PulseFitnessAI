"""Rehost MOD Test Site equipment photos onto our own object storage.

The tender-demo fleet was seeded with external stock-photo hotlinks
(images.unsplash.com / images.pexels.com). Those load fine server-side but
are flaky on mobile (hotlink throttling / referrer) — the public QR scan
page showed a broken image. This downloads each external photo and stores
it in our object store, then repoints photo_url at the same-origin public
endpoint (/api/public/equipment/{id}/photo) with photo_path + content-type,
so images always load on any device. IDs are preserved (existing QR codes
keep working).

Run: cd /app/backend && PYTHONPATH=/app/backend python scripts/rehost_mod_test_site_photos.py
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import requests

from utils.database import db, APP_NAME, put_object
from routes.equipment import _public_photo_url

SITE_ID = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


async def main() -> None:
    eq = await db.equipment.find(
        {"organization_id": SITE_ID, "photo_url": {"$regex": "^https?://"}},
        {"_id": 0, "id": 1, "name": 1, "photo_url": 1},
    ).to_list(100)
    if not eq:
        print("Nothing to rehost (no external photo_url on this site).")
        return

    now = datetime.now(timezone.utc).isoformat()
    done = failed = 0
    for e in eq:
        src = e["photo_url"]
        try:
            r = requests.get(src, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            ct = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            if ct not in _EXT:
                ct = "image/jpeg"
            ext = _EXT[ct]
            path = f"{APP_NAME}/equipment-photos/{e['id']}/{uuid.uuid4()}.{ext}"
            result = put_object(path, r.content, ct)
            storage_path = result.get("path", path)
            await db.equipment.update_one(
                {"id": e["id"]},
                {"$set": {
                    "photo_url": _public_photo_url(e["id"]),
                    "photo_path": storage_path,
                    "photo_content_type": ct,
                    "photo_source": "seed_rehosted",
                    "updated_at": now,
                }},
            )
            done += 1
            print(f"✓ {e['name']}  ({len(r.content)//1024} KB, {ct})")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"✗ {e['name']}: {exc}")

    print(f"\nRehosted {done} photo(s), {failed} failed.")


if __name__ == "__main__":
    asyncio.run(main())
