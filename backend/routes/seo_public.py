"""Public SEO surface — dynamic sitemap + crawler prerender.

Why this exists
---------------
The marketing site is a client-rendered React SPA. Two SEO consequences
this module fixes:

1. **Discovery** — the hand-maintained ``frontend/public/sitemap.xml``
   never listed the blog posts the SEO autopilot publishes, so Google was
   never told they exist. ``GET /api/seo/sitemap.xml`` builds the sitemap
   live from the ``seo_articles`` collection (+ the static marketing pages
   and comparison pages). robots.txt points at it.

2. **Crawlability of dynamic content** — non-JS crawlers (LinkedIn,
   Facebook, WhatsApp, Slack, X) and first-pass Googlebot don't see the
   per-article ``<head>`` the SPA sets after hydration. ``GET
   /api/seo/share/blog/{slug}`` returns a fully server-rendered HTML page
   (title + meta + Open Graph + Article/FAQ/Breadcrumb JSON-LD + the
   article body) and redirects human browsers to the real ``/blog/{slug}``
   SPA route. The SEO autopilot's social share links can point here so
   social cards are always correct; in production an edge rule
   (Cloudflare Worker / nginx ``map $http_user_agent``) can also route
   organic bot traffic for ``/blog/*`` here.

Everything is read-only and unauthenticated except the manual IndexNow
ping (master-admin).
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response

from utils.auth import get_current_user
from utils.database import db
from utils.indexnow import ping_indexnow

router = APIRouter(prefix="/api/seo", tags=["seo-public"])


def _site() -> str:
    return (os.environ.get("SEO_SITE_URL") or "https://www.gymaxisai.com").rstrip("/")


# Static, indexable marketing pages (mirror robots.txt Allow list) with a
# crawl priority. Comparison pages are appended from COMPARE_SLUGS.
STATIC_PAGES: list[tuple[str, str, float]] = [
    ("/", "weekly", 1.0),
    ("/pricing", "monthly", 0.9),
    ("/features", "monthly", 0.8),
    ("/blog", "daily", 0.8),
    ("/compare", "monthly", 0.7),
    ("/contact", "monthly", 0.7),
    ("/about", "monthly", 0.6),
    ("/security", "monthly", 0.5),
    ("/whats-new", "weekly", 0.5),
    ("/privacy", "yearly", 0.3),
    ("/terms", "yearly", 0.3),
    ("/legal/dpa", "yearly", 0.3),
    ("/legal/dpia", "yearly", 0.3),
]
COMPARE_SLUGS = ["clubready", "glofox", "mindbody"]

# Programmatic solution/use-case pages (content lives in the frontend
# data file src/pages/Marketing/Landing/solutionsData.js — keep the slug
# list in sync so they enter the sitemap).
SOLUTION_SLUGS = [
    "gym-maintenance-software",
    "ppm-software-for-gym-equipment",
    "gym-equipment-asset-management",
    "gym-crm-software",
    "leisure-centre-management-software",
    "fitness-equipment-service-management",
]

# A manufacturer needs at least this many quality products to earn its
# own landing page — keeps pages substantive (no thin/doorway content).
MANUFACTURER_MIN_PRODUCTS = 6

# Programmatic equipment-type maintenance pages (the *category* axis that
# complements the manufacturer/*brand* axis). Each type carries curated,
# substantive editorial (common faults + PM tasks + FAQ) and is filled with
# the real, serviceable machines of that type pulled live from the
# catalogue across every brand. A type only earns a page once it has
# EQUIPMENT_MIN_PRODUCTS real machines — thin types 404 until the
# catalogue grows, exactly like the manufacturer pages.
EQUIPMENT_MIN_PRODUCTS = 6

# Per-type include regex (the broad serviceable/non-serviceable filters
# still apply on top). `name`/`plural` drive the copy; `term` is the
# search-intent phrase used in the H1/title.
EQUIPMENT_TYPES: list[dict] = [
    {
        "slug": "treadmill",
        "name": "Treadmill",
        "plural": "treadmills",
        "term": "treadmill servicing & repair",
        "match": r"treadmill|\brunner\b|running machine",
        "intro": "Treadmills are the hardest-worked machines on any gym floor — and the most expensive to leave broken. GymAxis keeps every treadmill serviced, compliant and earning.",
        "faults": [
            "Belt slipping, fraying or off-centre tracking",
            "Worn or dry running deck causing motor strain",
            "Motor brush wear and overheating cut-outs",
            "Incline motor faults and mis-calibration",
            "Console, speed-sensor and firmware errors",
        ],
        "tasks": [
            "Belt tension, alignment and wear check",
            "Deck lubrication and wear measurement",
            "Motor brush inspection and current draw test",
            "Incline calibration and limit-switch test",
            "Firmware updates and speed-sensor verification",
        ],
    },
    {
        "slug": "exercise-bike",
        "name": "Exercise bike",
        "plural": "exercise bikes",
        "term": "exercise bike servicing & repair",
        "match": r"\bbike\b|indoor cycle|\bcycle\b|cycling|\bspin\b|spinning|recumbent|upright|airbike|air[\s-]?bike|assault|\batom\b|nucleus|proton",
        "intro": "From studio spin bikes to air bikes and recumbents, GymAxis keeps every exercise bike smooth, quiet and safe — with parts and service history on one record.",
        "faults": [
            "Crank and bottom-bracket bearing play",
            "Brake pad wear (friction) or magnetic resistance drift",
            "Drive belt tension and slippage",
            "Console battery and display faults",
            "Pedal, cleat and saddle wear",
        ],
        "tasks": [
            "Crank and bottom-bracket inspection",
            "Brake adjustment or resistance calibration",
            "Drive belt tension and alignment",
            "Console battery replacement and firmware check",
            "Saddle, handlebar and pedal security check",
        ],
    },
    {
        "slug": "rowing-machine",
        "name": "Rowing machine",
        "plural": "rowing machines",
        "term": "rowing machine servicing & repair",
        "match": r"\brower\b|rowing|\berg\b|ski[\s-]?erg|trakrow",
        "intro": "Keep every rower and ski-erg pulling true. GymAxis tracks chain, damper and monitor health so a worn handle never takes a machine off the floor.",
        "faults": [
            "Chain or handle strap wear",
            "Shock-cord stretch and slow recoil",
            "Damper and flywheel noise or stiffness",
            "Monitor battery and drag-factor errors",
            "Seat roller wear and rail grit",
        ],
        "tasks": [
            "Chain lubrication and link inspection",
            "Shock-cord tension and replacement",
            "Drag-factor calibration and flywheel clean",
            "Seat roller and rail inspection",
            "Monitor battery and firmware check",
        ],
    },
    {
        "slug": "cross-trainer",
        "name": "Cross trainer",
        "plural": "cross trainers",
        "term": "cross trainer & elliptical servicing",
        "match": r"elliptical|cross[\s-]?trainer|crosstrainer|\bglider\b",
        "intro": "Ellipticals and cross trainers hide their wear in the bearings and drive. GymAxis schedules the right PPM so they stay silent and smooth.",
        "faults": [
            "Pedal-arm and link bearing play",
            "Drive belt wear and slippage",
            "Resistance or brake drift",
            "Roller and ramp wear",
            "Console and sensor faults",
        ],
        "tasks": [
            "Bearing inspection and greasing",
            "Drive belt tension and alignment",
            "Ramp and roller clean and inspection",
            "Resistance calibration",
            "Console firmware and sensor check",
        ],
    },
    {
        "slug": "stair-climber",
        "name": "Stair climber",
        "plural": "stair climbers & steppers",
        "term": "stair climber & stepper servicing",
        "match": r"stepper|step machine|\bstair\b|climber|jacobs ladder|step[\s-]?mill|stepmill",
        "intro": "Steppers and stair climbers take constant load through their drive and steps. GymAxis keeps the maintenance planned and the evidence logged.",
        "faults": [
            "Step chain or belt wear",
            "Drive bearing noise",
            "Resistance or alternator faults",
            "Hand-rail and pedal wear",
            "Console and sensor errors",
        ],
        "tasks": [
            "Step chain and drive inspection",
            "Bearing greasing and noise check",
            "Resistance and alternator test",
            "Hand-rail and pedal security check",
            "Console firmware and sensor check",
        ],
    },
    {
        "slug": "strength-machine",
        "name": "Strength machine",
        "plural": "strength machines",
        "term": "strength machine servicing & repair",
        "match": (r"\bpress\b|pulldown|pull[\s-]?down|\brow\b|\bcurl\b|extension|\bfly\b|\bpec\b"
                  r"|pec[\s-]?dec|\blat\b|\bleg\b|\bchest\b|\bshoulder\b|\bcable\b|crossover"
                  r"|smith|functional|multi[\s-]?gym|adductor|abductor|\bdelt\b|\bcalf\b"
                  r"|\bglute\b|hack[\s-]?squat|\bdip\b|\bchin\b|converging|iso[\s-]?lateral"
                  r"|plate[\s-]?loaded|selectoriz|pin[\s-]?loaded"),
        "intro": "Selectorised and plate-loaded strength kit fails quietly — a frayed cable or worn pulley is a safety risk. GymAxis makes inspection and repair routine.",
        "faults": [
            "Cable fraying and end-fitting wear",
            "Pulley and bearing wear",
            "Weight-stack pin and guide-rod wear",
            "Upholstery tears and pad wear",
            "Loose bolts and frame play",
        ],
        "tasks": [
            "Cable inspection and replacement",
            "Pulley and bearing check",
            "Guide-rod lubrication and stack check",
            "Upholstery and pad inspection",
            "Bolt torque and frame inspection",
        ],
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lastmod(value) -> str:
    """Coerce a stored date/datetime/string into a YYYY-MM-DD sitemap stamp."""
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    s = str(value)
    return s[:10]


def _url_node(loc: str, lastmod: str, changefreq: str, priority: float) -> str:
    return (
        "  <url>\n"
        f"    <loc>{html.escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority:.1f}</priority>\n"
        "  </url>"
    )


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().replace("&", " and ")).strip("-")
    return re.sub(r"-{2,}", "-", s)


# Catalogue product pages that are clearly not individual products
# (homepages, generic landing copy) — excluded from landing pages so the
# rendered range stays high quality.
_NON_PRODUCT_TITLE = re.compile(
    r"(\bhome\b|world-class|shop all|all products|commercial (fitness|cardio|gym)"
    r"|fitness solutions|cardio- und|équipements|equipo comercial|attrezzature"
    r"|sitemap|collection|category|cookie|privacy|gym equipment for"
    r"|press release|press kit|pressemitteilung|\bnews\b|\bblog\b|newsletter|gift card|gift voucher"
    r"|prensa|presse|comunicado|communiqu|power of movement|\bbbc\b|webinar|podcast"
    r"|case stud|fallstudie|kundenstimmen|testimonial|\bcustomer\b|\bcontact\b"
    r"|\bstory\b|stories|\bstudie|caminadora|tapis|\bevent|exhibition|\bdemo\b"
    r"|jersey|bib short|t-shirt|hoodie|jacket|\bsock|\bcap\b|water bottle|clothing"
    r"|apparel|\btowel\b|\bcare kit\b|spare part|accessor)",
    re.IGNORECASE,
)
_LOCALE_SEG = re.compile(r"^[a-z]{2}([-_][a-z]{2})?$", re.IGNORECASE)
_PRODUCT_URL_HINT = re.compile(
    r"/(product|products|shop|cardio|strength|machine|machines|equipment|range"
    r"|gear|bike|bikes|treadmill|rower|cycle|cycling|console|collections/[^/]+/)",
    re.IGNORECASE,
)


def _looks_like_product(title: str, page_url: str) -> bool:
    """Keep only substantive, English-ish individual product pages."""
    if not title or _NON_PRODUCT_TITLE.search(title):
        return False
    # Product names are short; long titles are marketing sentences.
    if len(title.split()) > 7 or ":" in title:
        return False
    # Reject mostly non-ASCII (localised) titles.
    ascii_ratio = sum(c.isascii() for c in title) / max(len(title), 1)
    if ascii_ratio < 0.9:
        return False
    from urllib.parse import urlparse
    segs = [s for s in (urlparse(page_url).path or "").strip("/").split("/") if s]
    if not segs:                       # homepage
        return False
    if len(segs) == 1 and _LOCALE_SEG.match(segs[0]):  # locale root e.g. /de
        return False
    # URL must look like a product: a known product path, or a single
    # clean slug (many vendors host products at the root, e.g. /atom).
    if not _PRODUCT_URL_HINT.search(page_url) and len(segs) > 1:
        return False
    return True


# We only claim to *service* equipment with moving parts / electronics.
# A product must match this allowlist of serviceable machine types AND must
# NOT match the non-serviceable list below (free weights, benches, racks,
# accessories, apparel, flooring — anything with no moving parts).
_SERVICEABLE_MACHINE = re.compile(
    r"(treadmill|runner|\brunning machine|\bbike\b|e-?bike|cycle|cycling|\bspin\b|spinning"
    r"|elliptical|cross[\s-]?trainer|crosstrainer|\brower\b|rowing|trakrow|\berg\b"
    r"|ski[\s-]?erg|stepper|step machine|climber|\bstair|jacobs ladder|recumbent|upright"
    r"|airbike|air[\s-]?bike|assault|\bair\b|\btrainer\b|\batom\b|atomx|proton|nucleus"
    r"|\bpress\b|pulldown|pull[\s-]?down|\brow\b|\bcurl\b|extension|\bfly\b|\bpec\b"
    r"|pec[\s-]?dec|delt|\braise\b|adductor|abductor|\bthigh\b|calf|abdominal|crunch"
    r"|glute|hack[\s-]?squat|smith|\bcable\b|crossover|functional|multi[\s-]?gym"
    r"|jungle|\bpulley\b|motioncage|motion[\s-]?cage|leverage|\bchin\b|converging"
    r"|diverging|iso[\s-]?lateral|plate[\s-]?loaded|selectorized|pin[\s-]?loaded"
    r"|\bfts\b|vibration[\s-]?plate|power[\s-]?plate|dual[\s-]?adjustable|\bdip\b)",
    re.IGNORECASE,
)
_NON_SERVICEABLE = re.compile(
    r"(dumbbell|kettlebell|barbell|weight[\s-]?plate|bumper[\s-]?plate|olympic[\s-]?plate"
    r"|plate[\s-]?tree|plate[\s-]?rack|\bcollar\b|medicine[\s-]?ball|slam[\s-]?ball"
    r"|wall[\s-]?ball|\bbench\b|\brack\b|\bcage\b|\bstool\b|\btree\b|\bstorage\b"
    r"|\bpedal|saddle|\bmat\b|flooring|\btile\b|\bhandle|attachment|\bgrip\b|\bstem\b"
    r"|dongle|charger|power[\s-]?supply|\bbattery\b|sticker|\bstrap\b|\blever\b"
    r"|\bbundle\b|\bkit\b|holder|\bsensor\b|\bfan\b|seat[\s-]?post|\bpost\b|\btape\b"
    r"|\bcream\b|chamois|bum butter|stabilis|stabiliz|\bfoot\b|\bshort|jersey|\bsock"
    r"|\bshirt\b|\bglove|clothing|apparel|hyperice|hypervolt|normatec|venom|massage"
    r"|foam[\s-]?roll|percussion|monitor service|\bapp\b|software|\bgift|\bbar\b(?!bell)"
    r"|reconditioned|\bgrade\b|\bdraft\b|essentials|ultimate bundle|summer goals"
    r"|spring bundle|workout bundle|\bbag\b|\brope\b|skipping|resistance band|\bband\b"
    r"|\bpad\b|\bpads\b|\bdisc\b|connector|\brig\b|rebounder|rip trainer|\btrx\b"
    r"|\btest\b|\biter\d|boxing|balance disc|\bstation\b|spotter|\bpin\b(?!.?load)"
    r"|\bring\b|\bball\b|\bplate\b(?![\s-]?load))",
    re.IGNORECASE,
)
# Suffixes that mark a duplicate/variant of an existing machine, stripped
# before dedup so "Wattbike Atom - Reconditioned, Grade 1" folds into "Atom".
_VARIANT_SUFFIX = re.compile(
    r"\s*[-–—]\s*(reconditioned|grade\s*\d|refurbished|draft|ex[\s-]?demo).*$",
    re.IGNORECASE,
)


def _is_serviceable_machine(title: str) -> bool:
    """True only for equipment we can genuinely service (moving parts or
    electronics) — excludes free weights, benches, racks, accessories,
    apparel and flooring."""
    return bool(_SERVICEABLE_MACHINE.search(title)) and not _NON_SERVICEABLE.search(title)


def _norm_name(text: str) -> str:
    """Normalise an equipment name for cross-source matching."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


# Brand/range/category words stripped from a spec-sheet model to get a
# clean, comparable machine name (e.g. "Pulse Fitness Classic Strength
# 446H Seated Row" -> display "446H Seated Row", core "seated row").
_SPEC_STRIP = re.compile(
    r"\b(classic|club ?line|club|premium|strength|cardio|line|range"
    r"|selectoris\w*|selectoriz\w*|plate ?loaded|series)\b",
    re.IGNORECASE,
)


def _spec_display_title(model: str, manufacturer: str) -> str:
    t = re.sub(re.escape(manufacturer), "", model or "", flags=re.IGNORECASE)
    t = _SPEC_STRIP.sub("", t)
    t = re.sub(r"\s*/\s*", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -/")
    return t or (model or "")


def _spec_core_name(model: str, manufacturer: str) -> str:
    """Core machine name with brand, range words and model codes removed."""
    t = _spec_display_title(model, manufacturer)
    t = re.sub(r"\b\d{2,4}[a-zA-Z]?\b", "", t)  # drop model codes like 446H
    return _norm_name(t)


async def _manufacturer_names() -> list[dict]:
    """All distinct manufacturers in the catalogue (raw counts)."""
    pipeline = [
        {"$group": {
            "_id": "$manufacturer_display",
            "count": {"$sum": 1},
            "domain": {"$first": "$domain"},
        }},
        {"$match": {"_id": {"$ne": None}, "count": {"$gte": 20}}},
        {"$sort": {"count": -1}},
    ]
    return [
        {"name": r["_id"], "slug": _slugify(r["_id"]), "domain": r.get("domain")}
        async for r in db.manufacturer_catalogue.aggregate(pipeline)
    ]


async def _load_spec_sheets(name: str) -> list[dict]:
    """Spec-sheet products for a manufacturer, using the same hero image the
    ops module shows. Returns [{title, image_url, url, _norm}] — the image
    is the public spec-sheet hero endpoint."""
    out: list[dict] = []
    seen: set[str] = set()
    cursor = db.spec_sheets.find(
        {"manufacturer": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
         "hero_image_url": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "equipment_model": 1},
    )
    async for s in cursor:
        model = s.get("equipment_model") or ""
        display = _spec_display_title(model, name)
        core = _spec_core_name(model, name)
        if not core or not _is_serviceable_machine(display):
            continue
        if core in seen:
            continue
        seen.add(core)
        out.append({
            "title": display,
            "image_url": f"/api/spec-sheets/image/{s['id']}",
            "url": None,
            "_norm": core,
        })
    return out


async def _collect_products(name: str, *, limit: int = 24) -> list[dict]:
    """Filtered, deduped, high-quality product list for one manufacturer.

    Spec-sheet products (with their authoritative main picture) take
    priority; catalogue products fill the rest. A catalogue product that
    matches a spec sheet is skipped so the spec image wins — exactly how the
    operations module sources equipment photos."""
    spec_products = await _load_spec_sheets(name)
    spec_norms = {s["_norm"] for s in spec_products}
    seen: set[str] = set()
    products: list[dict] = []
    cursor = db.manufacturer_catalogue.find(
        {"manufacturer_display": name},
        {"_id": 0, "page_title": 1, "image_url": 1, "page_url": 1},
    )
    async for p in cursor:
        title = (p.get("page_title") or "").strip()
        img = p.get("image_url") or ""
        if not title or not img.startswith("http"):
            continue
        if not _looks_like_product(title, p.get("page_url") or ""):
            continue
        clean = re.split(r"\s[|–—]\s", title)[0].strip()
        clean = re.sub(r"\s*-\s*" + re.escape(name) + r"\s*$", "", clean,
                       flags=re.IGNORECASE).strip()
        clean = _VARIANT_SUFFIX.sub("", clean).strip()
        # Only list equipment we can genuinely service (moving parts).
        if not _is_serviceable_machine(clean):
            continue
        key = clean.lower()
        norm = _norm_name(clean)
        if not clean or key == name.lower() or key in seen:
            continue
        # A spec sheet already covers this machine — prefer its main picture.
        if norm in spec_norms:
            continue
        seen.add(key)
        products.append({"title": clean, "image_url": img, "url": p.get("page_url")})
    # Spec-sheet machines first (authoritative photos), then catalogue.
    spec_cards = [{"title": s["title"], "image_url": s["image_url"], "url": s["url"]}
                  for s in spec_products]
    return (spec_cards + products)[:limit]


async def get_landing_manufacturers(min_products: int = MANUFACTURER_MIN_PRODUCTS) -> list[dict]:
    """Manufacturers with enough *quality* products to earn a landing page —
    keeps thin/marketing-heavy catalogues (e.g. mostly case studies) out."""
    out = []
    for m in await _manufacturer_names():
        products = await _collect_products(m["name"])
        if len(products) >= min_products:
            out.append({**m, "product_count": len(products)})
    out.sort(key=lambda x: -x["product_count"])
    return out


async def get_manufacturer_detail(slug: str, *, limit: int = 24) -> Optional[dict]:
    match = next((m for m in await _manufacturer_names() if m["slug"] == slug), None)
    if not match:
        return None
    products = await _collect_products(match["name"], limit=limit)
    if len(products) < MANUFACTURER_MIN_PRODUCTS:
        return None
    return {**match, "products": products, "product_count": len(products)}


@router.get("/landing/manufacturers")
async def list_landing_manufacturers():
    """Public — manufacturers that have a maintenance landing page."""
    return {"manufacturers": await get_landing_manufacturers()}


@router.get("/landing/manufacturer/{slug}")
async def manufacturer_landing_detail(slug: str):
    """Public — one manufacturer's real product range + meta for the
    /maintenance/{slug} landing page."""
    detail = await get_manufacturer_detail(slug)
    if not detail or len(detail.get("products") or []) == 0:
        raise HTTPException(404, "Manufacturer landing not found")
    return detail


# ── Equipment-type (category) landing pages ──────────────────────────

def _equipment_type(slug: str) -> Optional[dict]:
    return next((t for t in EQUIPMENT_TYPES if t["slug"] == slug), None)


async def _collect_equipment_by_type(type_def: dict, *, limit: int = 24) -> list[dict]:
    """Real, serviceable machines of one type across every brand, deduped.

    Spec-sheet machines (authoritative photos) come first, then catalogue
    products. The broad serviceable/non-serviceable filters apply on top of
    the type's include regex so only genuine machines of this category show.
    """
    type_re = re.compile(type_def["match"], re.IGNORECASE)
    products: list[dict] = []
    seen: set[str] = set()

    # Spec sheets of this type (use the same hero image the ops module shows).
    spec_cursor = db.spec_sheets.find(
        {"hero_image_url": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "equipment_model": 1, "manufacturer": 1, "equipment_type": 1},
    )
    async for s in spec_cursor:
        model = s.get("equipment_model") or ""
        etype = s.get("equipment_type") or ""
        hay = f"{model} {etype}"
        if not type_re.search(hay) or not _is_serviceable_machine(hay):
            continue
        mfr = s.get("manufacturer") or ""
        display = _spec_display_title(model, mfr) or model
        key = _norm_name(f"{mfr} {display}")
        if not key or key in seen:
            continue
        seen.add(key)
        products.append({
            "title": display,
            "image_url": f"/api/spec-sheets/image/{s['id']}",
            "url": None,
            "manufacturer": mfr or None,
        })

    # Catalogue products of this type across all brands.
    cursor = db.manufacturer_catalogue.find(
        {}, {"_id": 0, "page_title": 1, "image_url": 1, "page_url": 1, "manufacturer_display": 1},
    )
    async for p in cursor:
        title = (p.get("page_title") or "").strip()
        img = p.get("image_url") or ""
        if not title or not img.startswith("http"):
            continue
        if not _looks_like_product(title, p.get("page_url") or ""):
            continue
        mfr = (p.get("manufacturer_display") or "").strip()
        clean = re.split(r"\s[|–—]\s", title)[0].strip()
        if mfr:
            clean = re.sub(r"\s*-\s*" + re.escape(mfr) + r"\s*$", "", clean, flags=re.IGNORECASE).strip()
        clean = _VARIANT_SUFFIX.sub("", clean).strip()
        if not clean or not type_re.search(clean) or not _is_serviceable_machine(clean):
            continue
        key = _norm_name(f"{mfr} {clean}")
        if not key or key in seen:
            continue
        seen.add(key)
        products.append({"title": clean, "image_url": img, "url": p.get("page_url"),
                         "manufacturer": mfr or None})
    return products[:limit]


async def get_landing_equipment(min_products: int = EQUIPMENT_MIN_PRODUCTS) -> list[dict]:
    """Equipment types with enough real serviceable machines to earn a page."""
    out = []
    for t in EQUIPMENT_TYPES:
        products = await _collect_equipment_by_type(t)
        if len(products) >= min_products:
            brands = sorted({p["manufacturer"] for p in products if p.get("manufacturer")})
            out.append({
                "slug": t["slug"], "name": t["name"], "plural": t["plural"],
                "term": t["term"], "product_count": len(products), "brands": brands,
            })
    out.sort(key=lambda x: -x["product_count"])
    return out


async def get_equipment_detail(slug: str, *, limit: int = 24) -> Optional[dict]:
    t = _equipment_type(slug)
    if not t:
        return None
    products = await _collect_equipment_by_type(t, limit=limit)
    if len(products) < EQUIPMENT_MIN_PRODUCTS:
        return None
    brands = sorted({p["manufacturer"] for p in products if p.get("manufacturer")})
    return {
        "slug": t["slug"], "name": t["name"], "plural": t["plural"], "term": t["term"],
        "intro": t["intro"], "faults": t["faults"], "tasks": t["tasks"],
        "products": products, "product_count": len(products), "brands": brands,
    }


@router.get("/landing/equipment")
async def list_landing_equipment():
    """Public — equipment-type maintenance pages that have enough content."""
    return {"equipment": await get_landing_equipment()}


@router.get("/landing/equipment/{slug}")
async def equipment_landing_detail(slug: str):
    """Public — one equipment type's real machines + service editorial for
    the /equipment/{slug} landing page."""
    detail = await get_equipment_detail(slug)
    if not detail or len(detail.get("products") or []) == 0:
        raise HTTPException(404, "Equipment landing not found")
    return detail


async def build_sitemap_xml() -> str:
    site = _site()
    nodes: list[str] = [
        _url_node(f"{site}{path}", datetime.now(timezone.utc).date().isoformat(), cf, pr)
        for path, cf, pr in STATIC_PAGES
    ]
    nodes += [
        _url_node(f"{site}/compare/{slug}",
                  datetime.now(timezone.utc).date().isoformat(), "monthly", 0.6)
        for slug in COMPARE_SLUGS
    ]
    today = datetime.now(timezone.utc).date().isoformat()
    # Programmatic solution/use-case landing pages.
    nodes.append(_url_node(f"{site}/solutions", today, "monthly", 0.7))
    nodes += [
        _url_node(f"{site}/solutions/{slug}", today, "monthly", 0.8)
        for slug in SOLUTION_SLUGS
    ]
    # Programmatic manufacturer maintenance landing pages (data-driven —
    # grows automatically as the catalogue ingests more manufacturers).
    nodes.append(_url_node(f"{site}/maintenance", today, "monthly", 0.7))
    for mfr in await get_landing_manufacturers():
        nodes.append(_url_node(f"{site}/maintenance/{mfr['slug']}", today, "monthly", 0.7))
    # Programmatic equipment-type (category) maintenance landing pages.
    nodes.append(_url_node(f"{site}/equipment", today, "monthly", 0.7))
    for eq in await get_landing_equipment():
        nodes.append(_url_node(f"{site}/equipment/{eq['slug']}", today, "monthly", 0.8))
    # Published blog posts — the whole point of making this dynamic.
    cursor = db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "slug": 1, "published_at": 1, "updated_at": 1},
    ).sort("published_at", -1).limit(5000)
    async for art in cursor:
        slug = art.get("slug")
        if not slug:
            continue
        lastmod = _lastmod(art.get("updated_at") or art.get("published_at"))
        nodes.append(_url_node(f"{site}/blog/{slug}", lastmod, "monthly", 0.7))

    body = "\n".join(nodes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml():
    """Live sitemap — static pages + comparison pages + every published
    blog post. Referenced from robots.txt; submit to Search Console."""
    xml = await build_sitemap_xml()
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── Crawler prerender for blog posts ──────────────────────────────

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_LINK = re.compile(r"\[(.+?)\]\((.+?)\)")


def _md_to_basic_html(md: str) -> str:
    """Dependency-free, defensive Markdown → minimal HTML for crawlers.

    Handles headings, bullet lists, bold and links — everything is
    HTML-escaped first so stored content can never inject markup."""
    out: list[str] = []
    in_list = False
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        esc = html.escape(line.strip())
        esc = _MD_BOLD.sub(r"<strong>\1</strong>", esc)
        esc = _MD_LINK.sub(r'<a href="\2">\1</a>', esc)
        m = _MD_HEADING.match(esc)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = min(len(m.group(1)) + 1, 5)  # # → h2 (h1 is the title)
            out.append(f"<h{level}>{m.group(2)}</h{level}>")
        elif line.lstrip().startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:].lstrip('-* ').strip()}</li>")
        else:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _safe_image(article: dict) -> str:
    """og:image must be a real HTTP(S) URL. Hero images stored as base64
    ``data:`` URIs are unusable by social crawlers (and bloat the HTML) —
    fall back to the static brand cover for those."""
    hero = (article.get("hero_image_url") or "").strip()
    if hero.startswith("http"):
        return hero
    return f"{_site()}/brand/og-cover.jpg"


def _json_ld(article: dict, url: str) -> str:
    import json
    site = _site()
    image = _safe_image(article)
    blocks: list[dict] = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": (article.get("title") or "")[:110],
            "description": article.get("meta_description") or article.get("excerpt") or "",
            "image": [image],
            "datePublished": article.get("published_at") or article.get("created_at"),
            "dateModified": article.get("updated_at") or article.get("published_at"),
            "author": {"@type": "Organization", "name": "GymAxis AI", "url": site},
            "publisher": {
                "@type": "Organization", "name": "GymAxis AI",
                "logo": {"@type": "ImageObject",
                         "url": f"{site}/brand/gymaxis-logo.svg"},
            },
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
            "keywords": ", ".join(article.get("tags") or []),
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": site},
                {"@type": "ListItem", "position": 2, "name": "Blog",
                 "item": f"{site}/blog"},
                {"@type": "ListItem", "position": 3,
                 "name": (article.get("title") or "")[:90], "item": url},
            ],
        },
    ]
    qa = article.get("qa_blocks") or []
    faqs = [
        {"@type": "Question", "name": q.get("q") or q.get("question") or "",
         "acceptedAnswer": {"@type": "Answer",
                            "text": q.get("a") or q.get("answer") or ""}}
        for q in qa
        if (q.get("q") or q.get("question")) and (q.get("a") or q.get("answer"))
    ]
    if faqs:
        blocks.append({"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": faqs})
    return "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in blocks
    )


def _render_blog_html(article: dict) -> str:
    site = _site()
    slug = article.get("slug")
    canonical = f"{site}/blog/{slug}"
    title = html.escape((article.get("title") or "GymAxis AI Blog"))
    desc = html.escape((article.get("meta_description") or article.get("excerpt") or "")[:300])
    image = html.escape(_safe_image(article))
    has_real_image = (article.get("hero_image_url") or "").strip().startswith("http")
    tags = html.escape(", ".join(article.get("tags") or []))
    body_html = _md_to_basic_html(article.get("body_md") or "")
    json_ld = _json_ld(article, canonical)
    published = html.escape(str(article.get("published_at") or ""))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} | GymAxis AI</title>
<meta name="description" content="{desc}" />
<meta name="keywords" content="{tags}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<link rel="canonical" href="{canonical}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="GymAxis AI" />
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{desc}" />
<meta property="og:url" content="{canonical}" />
<meta property="og:image" content="{image}" />
<meta property="og:locale" content="en_GB" />
<meta property="article:published_time" content="{published}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title}" />
<meta name="twitter:description" content="{desc}" />
<meta name="twitter:image" content="{image}" />
{json_ld}
<script>
  // Human browsers land on the real SPA route; crawlers (no JS) keep this
  // fully-rendered HTML. Canonical already points at the SPA URL.
  try {{ if (!/bot|crawl|spider|slurp|facebookexternalhit|embedly|quora|whatsapp|slackbot|linkedinbot|twitterbot|telegrambot|discordbot|pinterest|preview/i.test(navigator.userAgent)) {{ window.location.replace({canonical!r}); }} }} catch (e) {{}}
</script>
</head>
<body>
<main>
<article>
<h1>{title}</h1>
{f'<img src="{image}" alt="{title}" />' if has_real_image else ''}
{body_html}
</article>
<p><a href="{canonical}">Read this article on GymAxis AI &rarr;</a></p>
</main>
</body>
</html>
"""


@router.get("/share/blog/{slug}", response_class=HTMLResponse)
async def prerender_blog(slug: str):
    """Crawler-facing, fully server-rendered HTML for a published blog
    post (correct meta + Open Graph + JSON-LD + body). Humans are
    redirected to the SPA route ``/blog/{slug}``."""
    article = await db.seo_articles.find_one(
        {"slug": slug, "status": "published"}, {"_id": 0},
    )
    if not article:
        raise HTTPException(404, "Post not found")
    return HTMLResponse(
        content=_render_blog_html(article),
        headers={"Cache-Control": "public, max-age=1800"},
    )


# ── Manual IndexNow ping (master-admin) ───────────────────────────

def _is_master_admin(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("account_type") == "gymaxis_admin")


@router.post("/indexnow/ping")
async def manual_indexnow_ping(body: dict, user=Depends(get_current_user)):
    """Manually notify IndexNow of one or more URLs (master-admin).
    Body: {urls: [...]} (absolute or site-relative) or {slug: '...'}."""
    if not _is_master_admin(user):
        raise HTTPException(403, "Master admin only")
    site = _site()
    urls = body.get("urls") or []
    if body.get("slug"):
        urls.append(f"/blog/{body['slug']}")
    urls = [u if u.startswith("http") else f"{site}{u if u.startswith('/') else '/' + u}"
            for u in urls]
    return await ping_indexnow(urls)


__all__ = ["router", "build_sitemap_xml", "ping_indexnow"]
