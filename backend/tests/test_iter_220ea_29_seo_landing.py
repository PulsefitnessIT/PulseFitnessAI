"""Iter 220ea·29 — programmatic SEO landing pages (solutions + manufacturer
maintenance) and their sitemap inclusion.

Covers the data-driven manufacturer landing logic (quality filtering so
thin/marketing-heavy catalogues don't get a page) and that the new pages
enter the dynamic sitemap.
"""
import uuid
import xml.etree.ElementTree as ET

from tests.shared_loop import run_async
from utils.database import db
from routes.seo_public import (
    MANUFACTURER_MIN_PRODUCTS,
    SOLUTION_SLUGS,
    _collect_products,
    _is_serviceable_machine,
    _looks_like_product,
    _slugify,
    _spec_core_name,
    build_sitemap_xml,
    get_landing_manufacturers,
    get_manufacturer_detail,
)


# ───────────── Serviceable-machine allowlist ──────────────────────

def test_serviceable_machine_accepts_real_machines():
    for t in ["Lat Pulldown", "Incline Chest Press", "Dual Action Leg Press",
              "MotionCage Package 1", "Wattbike Atom", "Impulse RT950 Treadmill",
              "Recumbent Bike", "Elliptical Cross Trainer", "Dual Pulley Functional Trainer",
              "Seated Calf Raise", "Cable Crossover Machine", "Group Cycle"]:
        assert _is_serviceable_machine(t), t


def test_serviceable_machine_rejects_non_serviceable():
    # apparel, free weights, accessories, flooring, benches/racks, no moving parts
    for t in ["Women's Virtus Shorts", "Eleiko Vulcano Dumbbells", "Wellgo E148 pedals",
              "ANT+ dongle", "Universal charger", "Origin 10mm Rubber Interlocking Floor Tile",
              "Olympic Spring Collars", "Commercial Flat/Incline Bench", "Commercial Squat Rack",
              "Olympic Plate Tree", "Atom Arm Pads", "Origin Air Balance Disc",
              "TRX Rip Trainer", "Hyperice Hypervolt 2 Pro", "Studio Barbell",
              "V Handle Cable Attachment", "Wattbike racing saddle", "Pedal Straps - Pair",
              "Iter216e Test Treadmill", "Functional Rig Single Connector"]:
        assert not _is_serviceable_machine(t), t


def test_press_machines_not_dropped_as_press_release():
    # regression: an over-broad press filter once dropped these
    for t in ["Leg Press", "Chest Press", "Shoulder Press"]:
        assert _is_serviceable_machine(t), t


# ───────────────────── Product quality filter ─────────────────────

def test_looks_like_product_accepts_real_products():
    assert _looks_like_product("Lat Pulldown", "https://hoist.com/products/lat-pulldown")
    assert _looks_like_product("Wattbike Atom", "https://wattbike.com/atom")


def test_looks_like_product_rejects_marketing_and_noise():
    # case studies / testimonials / PR
    assert not _looks_like_product("Precor Case Study: Wellfit", "https://precor.com/x/case-study")
    assert not _looks_like_product("Precor Kundenstimmen", "https://precor.com/de/kundenstimmen")
    assert not _looks_like_product("Customer Testimonials", "https://precor.com/testimonials")
    # long marketing sentence
    assert not _looks_like_product(
        "The slat treadmill from Precor offers premium performance for clubs",
        "https://precor.com/treadmill")
    # localised title
    assert not _looks_like_product("Cinta de correr profesional", "https://precor.com/es/cinta")
    # homepage / locale root
    assert not _looks_like_product("Precor", "https://precor.com/")
    assert not _looks_like_product("Precor", "https://precor.com/de")
    # apparel on an equipment-maintenance page
    assert not _looks_like_product("Women's Cycling Jersey", "https://wattbike.com/shop/jersey")


def test_slugify():
    assert _slugify("Hoist Fitness") == "hoist-fitness"
    assert _slugify("Life & Fitness") == "life-and-fitness"


# ───────────── Manufacturer landing (quality gate) ────────────────

def test_manufacturer_landing_quality_gate():
    rich = "ZZTest Rich " + uuid.uuid4().hex[:6]
    thin = "ZZTest Thin " + uuid.uuid4().hex[:6]

    async def scenario():
        # 20+ rows so it passes the distinct-manufacturer floor; 8 are
        # real products, the rest marketing noise.
        rows = []
        for i in range(8):
            rows.append({"manufacturer_display": rich, "domain": "zztest-rich.com",
                         "page_title": f"Leg Press Model {i}", "image_url": "https://x/i.jpg",
                         "page_url": f"https://zztest-rich.com/products/leg-press-{i}"})
        for i in range(14):
            rows.append({"manufacturer_display": rich, "domain": "zztest-rich.com",
                         "page_title": f"Case Study {i}", "image_url": "https://x/c.jpg",
                         "page_url": f"https://zztest-rich.com/stories/{i}"})
        # thin manufacturer: 20 rows but only 2 real products
        for i in range(2):
            rows.append({"manufacturer_display": thin, "domain": "zztest-thin.com",
                         "page_title": f"Rower {i}", "image_url": "https://x/r.jpg",
                         "page_url": f"https://zztest-thin.com/products/rower-{i}"})
        for i in range(18):
            rows.append({"manufacturer_display": thin, "domain": "zztest-thin.com",
                         "page_title": f"Customer Testimonials {i}", "image_url": "https://x/t.jpg",
                         "page_url": f"https://zztest-thin.com/testimonials/{i}"})
        await db.manufacturer_catalogue.insert_many(rows)

        mfrs = await get_landing_manufacturers()
        rich_entry = next((m for m in mfrs if m["name"] == rich), None)
        thin_entry = next((m for m in mfrs if m["name"] == thin), None)
        rich_detail = await get_manufacturer_detail(_slugify(rich))
        thin_detail = await get_manufacturer_detail(_slugify(thin))

        await db.manufacturer_catalogue.delete_many(
            {"manufacturer_display": {"$in": [rich, thin]}})
        return rich_entry, thin_entry, rich_detail, thin_detail

    rich_entry, thin_entry, rich_detail, thin_detail = run_async(scenario())
    # rich qualifies (>= MIN quality products), thin is excluded everywhere
    assert rich_entry and rich_entry["product_count"] >= MANUFACTURER_MIN_PRODUCTS
    assert thin_entry is None
    assert rich_detail and len(rich_detail["products"]) >= MANUFACTURER_MIN_PRODUCTS
    assert thin_detail is None
    # noise is filtered out of the rendered range
    assert all("Case Study" not in p["title"] for p in rich_detail["products"])


# ───────────────────── Sitemap inclusion ─────────────────────────

def test_sitemap_includes_solution_and_manufacturer_pages():
    xml = run_async(build_sitemap_xml())
    ET.fromstring(xml)  # valid XML
    assert "/solutions</loc>" in xml.replace(" ", "")  # index present (loose)
    for slug in SOLUTION_SLUGS:
        assert f"/solutions/{slug}" in xml
    assert "/maintenance<" in xml or "/maintenance</loc>" in xml
    # at least the known-good manufacturers appear
    assert "/maintenance/hoist-fitness" in xml


def test_solution_slugs_are_unique_and_kebab():
    assert len(SOLUTION_SLUGS) == len(set(SOLUTION_SLUGS))
    for s in SOLUTION_SLUGS:
        assert s == _slugify(s)


# ───────── Spec-sheet main pictures (ops-style sourcing) ──────────

def test_spec_core_name_strips_brand_range_and_model_code():
    assert _spec_core_name("Pulse Fitness Classic Strength 446H Seated Row",
                            "Pulse Fitness") == "seated row"
    assert _spec_core_name("Pulse Fitness Club Line / Strength 576H Seated Leg Press",
                            "Pulse Fitness") == "seated leg press"


def test_collect_products_prefers_spec_sheet_image_and_dedups():
    mfr = "ZZSpec " + uuid.uuid4().hex[:6]
    spec_id = "spec-" + uuid.uuid4().hex[:8]

    async def scenario():
        await db.manufacturer_catalogue.insert_many([
            {"manufacturer_display": mfr, "domain": "z.com",
             "page_title": t, "image_url": "https://z.com/i.jpg",
             "page_url": f"https://z.com/products/{t.replace(' ', '-').lower()}"}
            for t in ["Seated Row", "Chest Press", "Lat Pulldown",
                      "Leg Extension", "Shoulder Press", "Leg Curl"]
        ])
        await db.spec_sheets.insert_one({
            "id": spec_id, "manufacturer": mfr,
            "equipment_model": f"{mfr} Classic Strength 446H Seated Row",
            "hero_image_url": "gymaxis-ai/spec-sheets/images/x.jpeg",
        })
        prods = await _collect_products(mfr, limit=30)
        await db.manufacturer_catalogue.delete_many({"manufacturer_display": mfr})
        await db.spec_sheets.delete_one({"id": spec_id})
        return prods

    prods = run_async(scenario())
    titles = [p["title"] for p in prods]
    # spec-sheet machine appears first with its hero image
    assert prods[0]["image_url"] == f"/api/spec-sheets/image/{spec_id}"
    assert "446H Seated Row" in prods[0]["title"]
    # the catalogue "Seated Row" duplicate is removed (spec wins)
    assert "Seated Row" not in titles
    # the other catalogue machines remain
    assert "Chest Press" in titles and "Leg Curl" in titles
