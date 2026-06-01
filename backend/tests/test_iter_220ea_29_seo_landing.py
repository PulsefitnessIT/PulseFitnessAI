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
    _looks_like_product,
    _slugify,
    build_sitemap_xml,
    get_landing_manufacturers,
    get_manufacturer_detail,
)


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
