"""Master-admin Social Media post library.

Stores ready-to-publish social media assets (image + caption + hashtags +
channel + posting notes). Seeded on first load with the GymAxis Instagram
mosaic + cover post set so the user has a working library out of the box.

Endpoints
---------
* ``GET    /api/master-admin/social-media-library``
* ``POST   /api/master-admin/social-media-library``
* ``DELETE /api/master-admin/social-media-library/{id}``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from routes.auth import get_current_user
from routes.master_admin import require_master_admin
from utils.database import db

router = APIRouter(tags=["social-media-library"])

CHANNELS = ["instagram", "linkedin", "facebook", "tiktok", "twitter", "all"]
CAMPAIGNS = ["mosaic_9up", "switch_thread", "engineer_recruit", "general", "evergreen"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Brand scoping ─────────────────────────────────────────────────────
#
# The library is shared by the GymAxis platform admin and delegated
# Pulse Master Admins. Each row carries a `brand` ('gymaxis' | 'pulse')
# so a Pulse admin never sees GymAxis-branded marketing assets (and vice
# versa). The seeded posts below are all GymAxis marketing → 'gymaxis'.


def _brand_for(user: dict) -> str:
    """Brand bucket the calling master-admin operates in.

    Delegated Pulse Master Admins → 'pulse'. The GymAxis platform admin
    (and anyone else who passes ``require_master_admin``) → 'gymaxis'.
    """
    if user.get("is_master_admin"):
        return "gymaxis"
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return "pulse"
    return "gymaxis"


# ── Seed-once state ───────────────────────────────────────────────────
#
# Previously the list endpoint re-seeded a campaign whenever it was
# empty, so deleting every post in a campaign made them reappear on the
# next load ("I delete the posts but they come back"). We now record a
# one-time seed marker in ``platform_config`` so deletions persist.


async def _seed_done(key: str) -> bool:
    doc = await db.platform_config.find_one({"_id": "social_library_seed"})
    return bool(doc and doc.get(key))


async def _mark_seed_done(key: str) -> None:
    await db.platform_config.update_one(
        {"_id": "social_library_seed"},
        {"$set": {key: True, "updated_at": _now()}},
        upsert=True,
    )


# ── Seed: GymAxis mosaic + cover-post campaign ────────────────────────


SEED_ROWS: list[dict[str, Any]] = [
    # ── 9-tile mosaic — POST IN REVERSE ORDER (tile_09 first, tile_01 last)
    {
        "label": "Mosaic · Tile 09 · GymAxis lockup",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_09.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 1,
        "caption": (
            "Smarter fitness. Stronger business.\n\n"
            "The platform built by gym operators, for gym operators.\n\n"
            "What's coming over the next 8 days: a 9-piece mosaic of why the "
            "smartest gyms in the UK are switching to GymAxis. Save this post. "
            "Watch the grid build.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymAxis", "SmarterFitnessStrongerBusiness", "FitnessSaaS",
            "GymOperators", "UKFitness", "HealthClubManagement", "FitnessIndustry",
        ],
        "notes": "Post #1 of the mosaic. Lands in the bottom-right profile slot.",
    },
    {
        "label": "Mosaic · Tile 08 · 6 service icons",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_08.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 2,
        "caption": (
            "Service. CRM. Memberships. Marketing. Staffing. Reporting.\n\n"
            "Six modules. One login. Zero CSV exports between them.\n\n"
            "If your operation lives in five tabs and a WhatsApp group, "
            "you're paying for the same data three times.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymOps", "FitnessTech", "GymCRM", "MembershipManagement",
            "FacilityManagement", "GymAxis",
        ],
        "notes": "Post #2 of the mosaic. Lands in the bottom-centre profile slot.",
    },
    {
        "label": "Mosaic · Tile 07 · Your Axis. Your Advantage.",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_07.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 3,
        "caption": (
            "Your axis. Your advantage.\n\n"
            "Powerful tools. Smarter insights. Better results.\n\n"
            "The same operators who used to lose Sundays to spreadsheets are "
            "now closing them out by 4pm Friday. The lever isn't more hours. "
            "It's the right axis.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymOwnerLife", "FitnessBusiness", "BoutiqueFitness",
            "GymManagement", "OperationalExcellence", "GymAxis",
        ],
        "notes": "Post #3 of the mosaic. Lands in the bottom-left profile slot.",
    },
    {
        "label": "Mosaic · Tile 06 · Focus / Growth / Performance",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_06.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 4,
        "caption": (
            "Focus. Growth. Performance.\n\n"
            "Three words that should describe your operations dashboard. "
            "Not your motivational poster.\n\n"
            "Real-time KPIs at the site level, the region level, the estate "
            "level. One screen. No exports.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "KPI", "BusinessIntelligence", "FitnessOperations",
            "MultiSiteOps", "HealthClubGroup", "GymAxis",
        ],
        "notes": "Post #4. Lands in the middle-right profile slot.",
    },
    {
        "label": "Mosaic · Tile 05 · GA hero (centre)",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_05.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 5,
        "caption": (
            "GA.\n\n"
            "The axis your gym has been missing.\n\n"
            "One platform. Memberships, classes, equipment, faults, billing, "
            "ERP — all sharing the same source of truth in real time.\n\n"
            "This is what 'smarter fitness, stronger business' looks like "
            "under the hood.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymAxis", "OnePlatform", "FitnessSaaS", "GymTech",
            "SmarterFitness", "StrongerBusiness",
        ],
        "notes": "Post #5 of the mosaic. The centre/hero tile. Lands in the dead-centre slot.",
    },
    {
        "label": "Mosaic · Tile 04 · One Platform. Everything Connected.",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_04.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 6,
        "caption": (
            "One platform. Everything connected.\n\n"
            "A new member signs up at 6:47am. The class waitlist auto-fills, "
            "the access pass provisions, the membership ledger reconciles "
            "into Sage 200, and the welcome SMS goes out — before your duty "
            "manager has finished their first coffee.\n\n"
            "That's the difference between a tech stack and a platform.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "OnePlatform", "Sage200", "ERP", "GymAutomation",
            "MemberJourney", "FitnessSaaS", "GymAxis",
        ],
        "notes": "Post #6 of the mosaic. Lands in the middle-left profile slot.",
    },
    {
        "label": "Mosaic · Tile 03 · Members First / Data Driven / Built For Fitness",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_03.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 7,
        "caption": (
            "Members first. Data driven. Built for fitness.\n\n"
            "Generic CRMs were built to sell software seats. GymAxis was "
            "built on the gym floor — by the same engineers who used to "
            "chase broken treadmills at 6am.\n\n"
            "Every workflow exists because an operator asked for it.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "BuiltForFitness", "DataDriven", "MembersFirst",
            "GymManagement", "FitnessIndustry", "GymAxis",
        ],
        "notes": "Post #7 of the mosaic. Lands in the top-right profile slot.",
    },
    {
        "label": "Mosaic · Tile 02 · Stronger Business",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_02.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 8,
        "caption": (
            "Stronger business.\n\n"
            "Everything you need to run, grow, and scale.\n\n"
            "Multi-site reporting. Native ERP. PPM check-sheets. Live SLA "
            "clocks. Group fitness scheduling. CRM. HR. All native. None "
            "bolted on.\n\n"
            "The stack you wish you'd started with.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "StrongerBusiness", "ScaleYourGym", "FitnessSaaS",
            "GymOperators", "GymAxis",
        ],
        "notes": "Post #8 of the mosaic. Lands in the top-centre profile slot.",
    },
    {
        "label": "Mosaic · Tile 01 · Smarter Fitness (final)",
        "image_url": "/marketing/mosaic_tiles_fhd_native/tile_01.png",
        "channel": "instagram",
        "campaign": "mosaic_9up",
        "post_order": 9,
        "caption": (
            "Smarter fitness.\n\n"
            "Smarter operations. Stronger business.\n\n"
            "The mosaic is complete. Tap through the grid — every tile is a "
            "reason. Then tap the link in bio and try it for yourself.\n\n"
            "14 days free. No card. No catch.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "SmarterFitness", "GymAxis", "FitnessSaaS", "StartFreeTrial",
            "UKGyms", "HealthClub", "FitnessIndustry",
        ],
        "notes": "Post #9 — the LAST one to post. Lands in the top-left profile slot, completing the mosaic.",
    },
    # ── Mosaic master + 7 single posts as bonus ─────────────────────────
    {
        "label": "Mosaic · Master canvas (5760×5760)",
        "image_url": "/marketing/mosaic_master_fhd_native.png",
        "channel": "all",
        "campaign": "mosaic_9up",
        "post_order": 10,
        "caption": (
            "The full GymAxis mosaic in one shot. Save it. Share it.\n\n"
            "Smarter fitness. Stronger business."
        ),
        "hashtags": ["GymAxis", "SmarterFitnessStrongerBusiness"],
        "notes": "Use as a LinkedIn document post / website hero / printed spec sheet. Day-10 carousel companion.",
    },
    {
        "label": "Switch · 01 · Cover (9 reasons)",
        "image_url": "/marketing/instagram_campaign/01_cover.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 1,
        "caption": (
            "9 reasons gym operators are switching to GymAxis.\n\n"
            "One thread. No fluff. Just what your spreadsheet, your CRM, and "
            "your maintenance email chain were never going to fix.\n\n"
            "Save this — you'll want to come back to it.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymOperators", "GymManagement", "FitnessSaaS",
            "HealthClubManagement", "GymTech", "GymOwnerLife",
            "FitnessIndustry", "UKFitness", "BoutiqueFitness", "GymAxis",
        ],
        "notes": "Cover post for the 'Switch' carousel campaign.",
    },
    {
        "label": "Switch · 02 · Multi-machine fault batching",
        "image_url": "/marketing/instagram_campaign/02_multi_fault.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 2,
        "caption": (
            "One job. Every broken machine. One tap.\n\n"
            "Five faults across three rigs used to mean three engineer "
            "visits, three invoices, and three different SLAs slipping at "
            "once. GymAxis batches them under a single job ID — but tracks "
            "every machine's resolution clock independently.\n\n"
            "Your engineers love it. Your finance lead loves it more.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymMaintenance", "FitnessEquipment", "FacilityManagement",
            "GymOps", "PreventiveMaintenance", "GymTech",
            "LeisureCentre", "GymAxis",
        ],
        "notes": "",
    },
    {
        "label": "Switch · 03 · SLA clock + named owner",
        "image_url": "/marketing/instagram_campaign/03_sla_clock.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 3,
        "caption": (
            "Every fault has a named owner and a live SLA clock.\n\n"
            "No more 'I thought you were chasing it.' GymAxis assigns "
            "ownership at the moment of logging, surfaces the countdown on "
            "every dashboard it touches, and escalates automatically when "
            "the clock turns red.\n\n"
            "Accountability isn't a culture problem. It's a software problem.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GymManagement", "SLA", "OperationalExcellence",
            "FitnessOperations", "GymOwners", "HealthClub",
            "LeisureManagement", "GymAxis",
        ],
        "notes": "",
    },
    {
        "label": "Switch · 04 · Paperless check sheets",
        "image_url": "/marketing/instagram_campaign/04_check_sheets.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 4,
        "caption": (
            "Your check sheets just went paperless.\n\n"
            "Daily. Weekly. Monthly. Every PPM your insurer asks for, "
            "captured on the floor in seconds, time-stamped, geo-stamped, "
            "and audit-ready before the engineer's even left the building.\n\n"
            "The clipboard era is over.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "PreventiveMaintenance", "PPM", "FacilityManagement",
            "GymCompliance", "HealthAndSafety", "GymOps",
            "LeisureIndustry", "GymAxis",
        ],
        "notes": "",
    },
    {
        "label": "Switch · 07 · Group fitness on autopilot",
        "image_url": "/marketing/instagram_campaign/07_classes.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 7,
        "caption": (
            "Classes fill themselves. Waitlists too.\n\n"
            "Smart scheduling reads attendance patterns. Smart waitlists "
            "move members in the second a slot opens. Smart no-show recovery "
            "DMs the next three names — automatically.\n\n"
            "Your studio manager gets their evenings back.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "GroupFitness", "ClassScheduling", "BoutiqueFitness",
            "GymMarketing", "MemberRetention", "FitnessSaaS",
            "StudioManagement", "GymAxis",
        ],
        "notes": "Posts 05 & 06 of the Switch series are pending image regen (budget cap).",
    },
    {
        "label": "Switch · 08 · Multi-site, one pane",
        "image_url": "/marketing/instagram_campaign/08_multi_site.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 8,
        "caption": (
            "Every site on one dashboard.\n\n"
            "Estate-wide uptime. Open faults. NPS. MRR. Engineer load. Class "
            "fill rate. All of it, every site, on one screen — drillable to "
            "the individual machine in two clicks.\n\n"
            "Run five gyms with the focus you used to give one.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "MultiSiteOps", "FitnessChain", "GymGroup",
            "LeisureOperations", "BusinessIntelligence", "FitnessSaaS",
            "HealthClubGroup", "GymAxis",
        ],
        "notes": "",
    },
    {
        "label": "Switch · 09 · CTA close (Start free)",
        "image_url": "/marketing/instagram_campaign/09_cta.png",
        "channel": "instagram",
        "campaign": "switch_thread",
        "post_order": 9,
        "caption": (
            "Migrate in a weekend. Start free.\n\n"
            "Built by operators, for operators. No sales call required. Spin "
            "up a trial estate, import your equipment list, and watch your "
            "first SLA clock start ticking before you finish your coffee.\n\n"
            "14 days. No card. No catch.\n\n"
            "Start a free trial — link in bio."
        ),
        "hashtags": [
            "StartFreeTrial", "GymSoftware", "FitnessSaaS",
            "GymOperators", "DigitalTransformation", "BuiltByOperators",
            "GymAxis", "SmarterFitnessStrongerBusiness",
        ],
        "notes": "Closing CTA. Pin alongside Mosaic Tile 09 for max conversion.",
    },
]

# ── Engineer tester recruitment campaign ("WE NEED YOU!") ─────────────


ENGINEER_RECRUIT_ROWS: list[dict[str, Any]] = [
    {
        "label": "Engineer Recruit · 01 · WE NEED YOU (hero)",
        "image_url": "/marketing/engineer_recruit/post_01.png",
        "post_order": 1,
        "caption": (
            "WE NEED YOU — fitness equipment engineers.\n\n"
            "We're opening 10 tester spaces on the GymAxis Engineer App. Real "
            "service jobs, a serious mobile toolkit, and your own business — we "
            "just need sharp engineers to help us put it through its paces.\n\n"
            "10 spaces. 10-day free trial. Stay on if you love it.\n\n"
            "Apply in 5 minutes — link in bio."
        ),
        "hashtags": [
            "FitnessEquipment", "GymEngineer", "FieldService", "GymMaintenance",
            "FitnessIndustry", "PPM", "NowHiring", "UKFitness", "GymTech", "GymAxis",
        ],
        "notes": (
            "HERO — POST THIS FIRST + pin it. 9:16 (1080x1920) works for IG "
            "Reels/Stories and TikTok. TikTok hook (read aloud over the image): "
            "'Fitness equipment engineers — we need you. Ten tester spaces, ten-day "
            "free trial.' Link in bio -> /partners/engineers."
        ),
    },
    {
        "label": "Engineer Recruit · 02 · One job, every machine",
        "image_url": "/marketing/engineer_recruit/post_02.png",
        "post_order": 2,
        "caption": (
            "One job. Every machine.\n\n"
            "Five faults across three rigs used to mean three visits, three "
            "invoices and three slipping SLAs. The GymAxis Engineer App batches "
            "them under a single visit — but tracks every machine's resolution "
            "clock independently.\n\n"
            "Less admin. More wrench time.\n\n"
            "10 tester spaces open — apply free, link in bio."
        ),
        "hashtags": [
            "GymEngineer", "FieldService", "GymMaintenance", "FitnessEquipment",
            "PreventiveMaintenance", "GymTech", "FitnessIndustry", "GymAxis",
        ],
        "notes": "TikTok hook: 'One job. Every broken machine. One tap.'",
    },
    {
        "label": "Engineer Recruit · 03 · Works offline",
        "image_url": "/marketing/engineer_recruit/post_03.png",
        "post_order": 3,
        "caption": (
            "Works offline. Always.\n\n"
            "Plant rooms and basements kill your signal — but not your paperwork. "
            "The app captures the whole visit offline and syncs the second you're "
            "back on data. Nothing lost, nothing re-typed.\n\n"
            "10 tester spaces — apply free, link in bio."
        ),
        "hashtags": [
            "FieldService", "GymMaintenance", "OfflineFirst", "GymEngineer",
            "FitnessEquipment", "GymTech", "FitnessIndustry", "GymAxis",
        ],
        "notes": "TikTok hook: 'No signal in the plant room? The app doesn't care.'",
    },
    {
        "label": "Engineer Recruit · 04 · Parts & van stock",
        "image_url": "/marketing/engineer_recruit/post_04.png",
        "post_order": 4,
        "caption": (
            "Know what's on the van.\n\n"
            "Track your van stock, log the exact parts used on each machine, and "
            "fire a reorder before you run dry. Covered-vs-chargeable is worked "
            "out for you, so billing is never a guess.\n\n"
            "10 tester spaces — apply free, link in bio."
        ),
        "hashtags": [
            "VanStock", "StockControl", "FieldService", "GymMaintenance",
            "FitnessEquipment", "GymEngineer", "GymTech", "GymAxis",
        ],
        "notes": "TikTok hook: 'Every part, every van, every job — accounted for.'",
    },
    {
        "label": "Engineer Recruit · 05 · Paperless check-sheets",
        "image_url": "/marketing/engineer_recruit/post_05.png",
        "post_order": 5,
        "caption": (
            "Paperless check-sheets.\n\n"
            "Daily, weekly, monthly PPM and H&S sign-offs — captured on the floor, "
            "time-stamped and geo-stamped, audit-ready before you leave the "
            "building. The clipboard era is over.\n\n"
            "10 tester spaces — apply free, link in bio."
        ),
        "hashtags": [
            "PPM", "HealthAndSafety", "GymCompliance", "GymMaintenance",
            "FieldService", "PreventiveMaintenance", "FitnessEquipment", "GymAxis",
        ],
        "notes": "TikTok hook: 'Binned the clipboard. Every check-sheet, done on the floor.'",
    },
    {
        "label": "Engineer Recruit · 06 · Photos to reports",
        "image_url": "/marketing/engineer_recruit/post_06.png",
        "post_order": 6,
        "caption": (
            "Photos to reports — instantly.\n\n"
            "Snap before-and-after photos and the app builds a clean, branded "
            "service report with signatures, then sends it to the customer before "
            "you've driven off. You look pro on every single job.\n\n"
            "10 tester spaces — apply free, link in bio."
        ),
        "hashtags": [
            "FieldService", "ServiceReport", "GymMaintenance", "FitnessEquipment",
            "GymEngineer", "GymTech", "FitnessIndustry", "GymAxis",
        ],
        "notes": "TikTok hook: 'Snap. Sign. Sent. Branded report before you leave.'",
    },
    {
        "label": "Engineer Recruit · 07 · Get paid (CTA close)",
        "image_url": "/marketing/engineer_recruit/post_07.png",
        "post_order": 7,
        "caption": (
            "Get paid — without the chase.\n\n"
            "Raise quotes on-site, invoice in a tap, and get paid through the "
            "platform. The monthly fee starts at £30 and drops to free once you "
            "refer 10 active sites. Your business, levelled up.\n\n"
            "Final call: 10 tester spaces, 10-day free trial. Apply now — link in bio."
        ),
        "hashtags": [
            "GymEngineer", "RunYourBusiness", "FieldService", "FitnessEquipment",
            "NowHiring", "FitnessIndustry", "GymTech", "GymAxis",
        ],
        "notes": "CLOSING CTA — post last. TikTok hook: 'Quote, invoice, get paid — all in one app. Last 10 spaces.'",
    },
]


async def _seed_engineer_recruit() -> int:
    """Insert the 'WE NEED YOU!' engineer recruitment campaign rows ONCE.

    Guarded by a persistent seed marker so that once an admin deletes
    these posts they stay deleted (previously they reappeared whenever
    the campaign count hit zero)."""
    if await _seed_done("engineer_recruit_seeded"):
        return 0
    existing = await db.social_media_library.count_documents({"campaign": "engineer_recruit"})
    if existing > 0:
        await _mark_seed_done("engineer_recruit_seeded")
        return 0
    docs = []
    for r in ENGINEER_RECRUIT_ROWS:
        docs.append({
            "id": str(uuid.uuid4()),
            "label": r["label"],
            "image_url": r["image_url"],
            "channel": "all",  # 9:16 asset — Instagram (Reels/Stories) + TikTok
            "campaign": "engineer_recruit",
            "brand": "gymaxis",
            "post_order": r.get("post_order", 0),
            "caption": r.get("caption", ""),
            "hashtags": r.get("hashtags", []),
            "notes": r.get("notes", ""),
            "enabled": True,
            "created_at": _now(),
            "created_by": "system_seed",
        })
    if docs:
        await db.social_media_library.insert_many(docs)
    await _mark_seed_done("engineer_recruit_seeded")
    return len(docs)




async def _seed_if_empty() -> int:
    """Insert the GymAxis seed rows ONCE. Idempotent via a persistent
    seed marker so deletions are never undone by a later load."""
    if await _seed_done("gymaxis_seeded"):
        return 0
    # Backfill brand on any legacy rows that predate brand scoping so
    # the brand filter below behaves consistently.
    await db.social_media_library.update_many(
        {"brand": {"$exists": False}}, {"$set": {"brand": "gymaxis"}},
    )
    existing = await db.social_media_library.count_documents({})
    if existing > 0:
        await _mark_seed_done("gymaxis_seeded")
        return 0
    docs = []
    for r in SEED_ROWS:
        docs.append(
            {
                "id": str(uuid.uuid4()),
                "label": r["label"],
                "image_url": r["image_url"],
                "channel": r.get("channel", "instagram"),
                "campaign": r.get("campaign", "general"),
                "brand": "gymaxis",
                "post_order": r.get("post_order", 0),
                "caption": r.get("caption", ""),
                "hashtags": r.get("hashtags", []),
                "notes": r.get("notes", ""),
                "enabled": True,
                "created_at": _now(),
                "created_by": "system_seed",
            }
        )
    if docs:
        await db.social_media_library.insert_many(docs)
    await _mark_seed_done("gymaxis_seeded")
    return len(docs)


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/master-admin/social-media-library")
async def list_posts(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    brand = _brand_for(user)
    seeded = 0
    # Only the GymAxis platform admin triggers (one-time) seeding of the
    # GymAxis marketing library. Pulse admins start with a clean,
    # Pulse-only library — no GymAxis assets cross over.
    if brand == "gymaxis":
        seeded += await _seed_if_empty()
        seeded += await _seed_engineer_recruit()

    if brand == "pulse":
        query: dict[str, Any] = {"brand": "pulse"}
    else:
        # GymAxis admin sees GymAxis + any legacy rows without a brand.
        query = {"$or": [{"brand": "gymaxis"}, {"brand": {"$exists": False}}, {"brand": None}]}

    rows = (
        await db.social_media_library
        .find(query, {"_id": 0})
        .sort([("campaign", 1), ("post_order", 1), ("created_at", -1)])
        .to_list(length=2000)
    )
    return {"rows": rows, "count": len(rows), "seeded": seeded}


@router.post("/master-admin/social-media-library")
async def add_post(body: dict = Body(...), user: dict = Depends(get_current_user)):
    require_master_admin(user)
    image_url = (body.get("image_url") or "").strip()
    if not image_url:
        raise HTTPException(400, "image_url required")
    if not image_url.startswith(("http://", "https://", "data:", "/")):
        raise HTTPException(400, "image_url must start with http(s)://, data:image/, or /")
    label = (body.get("label") or "").strip()[:160] or "Untitled"
    channel = (body.get("channel") or "instagram").strip().lower()[:32]
    if channel not in CHANNELS:
        channel = "instagram"
    campaign = (body.get("campaign") or "general").strip().lower()[:60]
    raw_tags = body.get("hashtags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.replace("#", "").split(",")]
    hashtags = [t.strip() for t in raw_tags if t and t.strip()][:30]

    row = {
        "id": str(uuid.uuid4()),
        "label": label,
        "image_url": image_url,
        "channel": channel,
        "campaign": campaign,
        "brand": _brand_for(user),
        "post_order": int(body.get("post_order") or 0),
        "caption": (body.get("caption") or "").strip()[:2200],
        "hashtags": hashtags,
        "notes": (body.get("notes") or "").strip()[:600],
        "enabled": bool(body.get("enabled", True)),
        "created_at": _now(),
        "created_by": user.get("email") or user.get("id"),
    }
    await db.social_media_library.insert_one(row.copy())
    row.pop("_id", None)
    return {"ok": True, "row": row}


@router.delete("/master-admin/social-media-library/{post_id}")
async def delete_post(
    post_id: str = Path(..., min_length=1),
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    brand = _brand_for(user)
    # Scope the delete to the caller's brand so a Pulse admin can only
    # remove Pulse posts (and vice versa). Combined with the seed-once
    # marker above, deletions now persist across reloads.
    if brand == "pulse":
        match = {"id": post_id, "brand": "pulse"}
    else:
        match = {"id": post_id, "brand": {"$ne": "pulse"}}
    res = await db.social_media_library.delete_one(match)
    if not res.deleted_count:
        raise HTTPException(404, "Post not found")
    return {"ok": True}


__all__ = ["router"]
