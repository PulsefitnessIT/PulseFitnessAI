"""Iter 240 — Google Search favicon (the "GA" logo next to results).

User report: Google results for gymaxisai.com showed the generic globe.
Root causes: no <link rel="icon"> at all, no favicon files on disk,
apple-touch-icon + manifest icons were data-URIs (not crawlable by
Google), and the Organization schema logo pointed to a file that does
not exist (brand/gymaxis-logo.svg).

Google requirements: a crawlable favicon, multiple of 48x48px, linked
from the homepage <head>.
"""

import os

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()
PUBLIC = "/app/frontend/public"

FAVICON_FILES = [
    "favicon.ico", "favicon-48.png", "favicon-96.png",
    "favicon-192.png", "favicon-512.png", "apple-touch-icon.png",
]


def test_favicon_files_exist_and_are_real_images():
    from PIL import Image
    for name in FAVICON_FILES:
        path = f"{PUBLIC}/{name}"
        assert os.path.exists(path), f"missing {name}"
        if name.endswith(".png"):
            im = Image.open(path)
            assert im.size[0] == im.size[1], f"{name} must be square, got {im.size}"
            if name in ("favicon-48.png", "favicon-96.png", "favicon-192.png"):
                assert im.size[0] % 48 == 0, (
                    f"{name} must be a multiple of 48px for Google, got {im.size}"
                )


def test_favicons_served_over_http():
    for name in FAVICON_FILES:
        r = requests.get(f"{BASE_URL}/{name}", timeout=20)
        assert r.status_code == 200, f"{name} -> {r.status_code}"
        assert r.headers.get("content-type", "").startswith("image/"), (
            f"{name} content-type {r.headers.get('content-type')}"
        )
        assert len(r.content) > 500, f"{name} suspiciously small"


def test_index_html_links_crawlable_icons():
    html = open(f"{PUBLIC}/index.html", encoding="utf-8").read()
    assert '<link rel="icon" href="/favicon.ico" sizes="48x48" />' in html
    assert 'sizes="48x48" href="/favicon-48.png"' in html
    assert 'sizes="96x96" href="/favicon-96.png"' in html
    assert 'sizes="192x192" href="/favicon-192.png"' in html
    # Default apple-touch-icon must be a real file, not a data URI
    # (the /pulse brand swap may still set a data URI at runtime).
    assert 'id="apple-touch-icon" href="/apple-touch-icon.png"' in html
    # Organization schema logo must reference a file that actually exists.
    assert '"logo": "https://gymaxisai.com/favicon-512.png"' in html
    assert "brand/gymaxis-logo.svg" not in html, "schema logo pointed at a non-existent file"


def test_manifest_icons_are_real_files():
    import json
    m = json.load(open(f"{PUBLIC}/manifest.json"))
    for icon in m["icons"]:
        assert icon["src"].startswith("/favicon-"), icon
        assert os.path.exists(f"{PUBLIC}{icon['src']}"), f"{icon['src']} missing on disk"


def test_robots_does_not_block_favicons():
    txt = open(f"{PUBLIC}/robots.txt", encoding="utf-8").read()
    for line in txt.splitlines():
        line = line.strip().lower()
        if line.startswith("disallow:"):
            rule = line.split(":", 1)[1].strip()
            assert rule not in ("/", "/favicon.ico"), f"robots blocks favicons: {line}"
            assert not rule.startswith("/favicon"), f"robots blocks favicons: {line}"
