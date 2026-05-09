"""Master Admin — Equipment Manufacturer Catalogue (iter 226).

Endpoints to manage the cached product-image catalogue:
  - GET  /api/master-admin/catalogue/stats     → per-domain counts
  - POST /api/master-admin/catalogue/ingest    → trigger background ingestion
  - GET  /api/master-admin/catalogue/jobs/{id} → job status
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.manufacturer_catalogue import (
    PRIORITY_DOMAINS,
    ensure_catalogue_indexes,
    ingest_domain,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/master-admin/catalogue/stats")
async def catalogue_stats(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    coll = db.manufacturer_catalogue
    pipe = [
        {"$group": {
            "_id": "$domain",
            "count": {"$sum": 1},
            "manufacturer_display": {"$first": "$manufacturer_display"},
            "last_ingested": {"$max": "$ingested_at"},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = []
    async for doc in coll.aggregate(pipe):
        rows.append({
            "domain": doc["_id"],
            "manufacturer_display": doc.get("manufacturer_display"),
            "products": doc["count"],
            "last_ingested": doc.get("last_ingested"),
        })
    total = await coll.estimated_document_count()
    # Surface zero-coverage priority domains as well (so the UI can show
    # which ones need ingesting). Use a friendly display label by reverse-
    # looking-up the longest alias in MANUFACTURER_DOMAINS.
    from utils.equipment_image_lookup import MANUFACTURER_DOMAINS
    display_for = {}
    for alias, dom in MANUFACTURER_DOMAINS.items():
        cur = display_for.get(dom)
        # Prefer the longer alias for the display label.
        if cur is None or len(alias) > len(cur):
            display_for[dom] = alias
    covered = {r["domain"] for r in rows}
    for d in PRIORITY_DOMAINS:
        if d not in covered:
            rows.append({
                "domain": d,
                "manufacturer_display": (display_for.get(d) or d.split(".")[0]).title(),
                "products": 0, "last_ingested": None,
            })
    rows.sort(key=lambda r: (-r["products"], r["domain"]))
    return {"total_products": total, "domains": rows}


@router.post("/master-admin/catalogue/ingest")
async def trigger_ingest(
    domain: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Kick off ingestion. If domain is supplied, ingest just that one;
    otherwise ingest all PRIORITY_DOMAINS in series.

    Returns immediately with a job_id — actual scraping runs in the
    background. Poll /jobs/{id} for progress.
    """
    require_master_admin(user)
    targets = [domain] if domain else list(PRIORITY_DOMAINS)
    if domain and domain not in PRIORITY_DOMAINS:
        # Allow ingestion of any curated manufacturer domain — we just
        # warn that priority is the recommended set.
        from utils.equipment_image_lookup import MANUFACTURER_DOMAINS
        if domain not in set(MANUFACTURER_DOMAINS.values()):
            raise HTTPException(status_code=400, detail=f"Unknown domain: {domain}")

    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "status": "running",
        "targets": targets,
        "results": [],
        "triggered_by": user.get("email"),
    }
    await db.catalogue_jobs.insert_one(job)
    job.pop("_id", None)

    asyncio.create_task(_run_job(job_id, targets))

    return {"job_id": job_id, "status": "running", "targets": targets}


async def _run_job(job_id: str, targets: list[str]) -> None:
    try:
        await ensure_catalogue_indexes()
        results: list[dict] = []
        for d in targets:
            try:
                stats = await ingest_domain(d)
            except Exception as exc:
                logger.warning("ingest failed for %s: %s", d, exc)
                stats = {"domain": d, "error": str(exc)}
            results.append(stats)
            # Stream interim progress to Mongo so the polling UI sees it.
            await db.catalogue_jobs.update_one(
                {"id": job_id},
                {"$set": {"results": results}},
            )
        await db.catalogue_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "complete",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "results": results,
            }},
        )
    except Exception as exc:
        logger.exception("catalogue job %s failed", job_id)
        await db.catalogue_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "error",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            }},
        )


@router.get("/master-admin/catalogue/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    doc = await db.catalogue_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc


@router.get("/master-admin/catalogue/jobs")
async def list_jobs(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    cursor = db.catalogue_jobs.find({}, {"_id": 0}).sort("started_at", -1).limit(20)
    jobs = await cursor.to_list(20)
    return {"jobs": jobs}



@router.post("/master-admin/catalogue/cleanup")
async def cleanup_catalogue_noise(
    domain: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216e — remove non-product noise from the catalogue.

    Pulse Fitness publishes Instagram/LinkedIn archive pages under
    their own URL slugs (e.g. /instagram-arm-only-workout/), which
    polluted the catalogue with 100+ social entries that look like
    products to the matcher. The fresh `SKIP_PATTERNS` regex (see
    `utils/manufacturer_catalogue.py`) drops these on future ingests;
    this endpoint removes the already-ingested ones in one shot.

    Pass `domain` to scope the cleanup; omit to clean every domain.
    Idempotent — safe to call repeatedly.
    """
    require_master_admin(user)
    noise_re = (
        r"/(?:instagram|linkedin|twitter|facebook|tiktok|youtube)-"
        r"|/social-|/event/|/events/|/exhibition/|/exhibitions/"
        r"|/article/|/articles/|/press-release/|/after-sales/|/aftersales/"
        r"|/maintenance-plan"
    )
    f: dict = {"page_url": {"$regex": noise_re, "$options": "i"}}
    if domain:
        f["domain"] = domain
    n = await db.manufacturer_catalogue.delete_many(f)
    return {"deleted": n.deleted_count, "scope": domain or "all"}


@router.post("/master-admin/catalogue/rematch-equipment")
async def rematch_equipment_to_catalogue(
    organization_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216e — re-run `auto_match_equipment_to_specs` for every
    piece of equipment in the (optionally scoped) org and persist the
    resulting `spec_sheet_image` / `manufacturer_page_url` onto the
    equipment row. Used after a fresh catalogue ingest to backfill
    images on equipment that was logged before the catalogue had
    coverage for that manufacturer.

    Returns counts of matched / unchanged / skipped rows.
    """
    require_master_admin(user)
    from routes.spec_sheets import auto_match_equipment_to_specs

    f: dict = {}
    if organization_id:
        f["organization_id"] = organization_id

    cursor = db.equipment.find(f, {"_id": 0})
    matched = unchanged = skipped = 0
    async for eq in cursor:
        result = await auto_match_equipment_to_specs(eq)
        if not result:
            skipped += 1
            continue
        # Don't overwrite explicit master-admin uploads with catalogue
        # fallbacks. Spec sheet IDs always win over catalogue IDs.
        update: dict = {}
        if result.get("spec_sheet_id") and eq.get("spec_sheet_id") != result["spec_sheet_id"]:
            update["spec_sheet_id"] = result["spec_sheet_id"]
            update["spec_sheet_url"] = result.get("spec_sheet_url", "")
        if result.get("spec_sheet_image") and eq.get("spec_sheet_image") != result["spec_sheet_image"]:
            update["spec_sheet_image"] = result["spec_sheet_image"]
        if result.get("manufacturer_catalogue_id") and not eq.get("spec_sheet_id"):
            update["manufacturer_catalogue_id"] = result["manufacturer_catalogue_id"]
            update["manufacturer_page_url"] = result.get("manufacturer_page_url", "")
        if update:
            await db.equipment.update_one({"id": eq["id"]}, {"$set": update})
            matched += 1
        else:
            unchanged += 1
    return {"matched": matched, "unchanged": unchanged, "skipped": skipped}
