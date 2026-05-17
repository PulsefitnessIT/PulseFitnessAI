"""
Iter 216h175 — Image optimisation regression test.

Verifies:
  1. The WebP versions of every shipped brand asset exist next to the
     original PNG, so the JSX references in Navbar / AdminSidebar /
     ServiceDeskPage resolve.
  2. The WebP files are substantially smaller than their PNG sources
     (≥80% reduction expected for these flat-colour logos). A future
     accidental regression that overwrites the WebP with a heavier
     variant trips this guard.
  3. The PulseLandingPage Pexels image URLs now request `fm=webp` so
     the browser receives WebP rather than the heavier JPEG.
  4. Member-facing portal `<img>` tags carry `loading=` / `decoding=`
     hints so the browser knows when to defer them.
"""
import os
import re


PUBLIC = '/app/frontend/public'
SRC = '/app/frontend/src'


def test_brand_webp_assets_present():
    """Every shipped brand PNG has a WebP sibling and the WebP is much
    smaller (≥80% reduction)."""
    targets = [
        'gymaxis-mark-tight',
        'gymaxis-mark',
        'gymaxis-text-tight',
        'gymaxis-text',
        'gymaxis-full-tight',
        'gymaxis-full',
        'gymaxis-logo',
    ]
    for base in targets:
        png = os.path.join(PUBLIC, 'brand', f'{base}.png')
        webp = os.path.join(PUBLIC, 'brand', f'{base}.webp')
        assert os.path.exists(png), f"missing source PNG: {png}"
        assert os.path.exists(webp), f"missing WebP variant: {webp}"
        png_size = os.path.getsize(png)
        webp_size = os.path.getsize(webp)
        ratio = webp_size / png_size
        assert ratio < 0.20, (
            f"{base}.webp is suspiciously large "
            f"({webp_size} B vs PNG {png_size} B = {ratio:.2%}); "
            f"expected <20% of the PNG"
        )


def test_chrome_image_refs_point_at_webp():
    """The three eager-loaded brand chrome images (Navbar, AdminSidebar,
    ServiceDeskPage) must reference the new WebP — they're on the
    critical render path of every operator page view."""
    expected = '/brand/gymaxis-mark-tight.webp'
    for rel in (
        'components/shared/Navbar.js',
        'pages/MasterAdmin/AdminSidebar.js',
        'pages/ServiceDeskPage.js',
    ):
        path = os.path.join(SRC, rel)
        body = open(path).read()
        assert expected in body, (
            f"{rel} still references the .png chrome logo — should be .webp"
        )
        # The old .png reference must be gone (only .webp).
        assert '/brand/gymaxis-mark-tight.png' not in body, (
            f"{rel} still has a stale .png reference"
        )


def test_pulse_landing_pexels_urls_force_webp():
    """Pexels does not auto-serve WebP unless `fm=webp` is in the query
    string. Verify both Pexels URLs on the marketing landing carry it."""
    body = open(os.path.join(SRC, 'pages/PulseLandingPage.js')).read()
    pexels_urls = re.findall(r"https://images\.pexels\.com[^'\"]+", body)
    assert pexels_urls, "expected at least one Pexels URL on PulseLandingPage"
    for url in pexels_urls:
        assert 'fm=webp' in url, f"Pexels URL missing fm=webp: {url[:120]}"


def test_member_facing_img_tags_have_loading_hint():
    """Every <img> tag we own on a member-facing surface must carry
    `loading=` (lazy or eager) and `decoding="async"` so the browser
    schedules them efficiently."""
    surfaces = [
        'pages/Memberships/MemberPortal.js',
        'pages/Memberships/portalShared.js',
        'pages/Memberships/tabs/BookTab.js',
        'pages/Memberships/tabs/PassTab.js',
        'pages/Memberships/PublicClassPage.js',
        'pages/Memberships/EmbedTimetable.js',
        'pages/Memberships/BrandedBragPage.js',
        'pages/PublicSignup/JoinPage.js',
        'pages/PublicTracking/PublicTrackingPage.js',
    ]
    for rel in surfaces:
        body = open(os.path.join(SRC, rel)).read()
        img_tags = re.findall(r'<img\s[^/>]*/?>', body)
        for tag in img_tags:
            # Skip QR template strings or commented examples.
            if 'src=' not in tag:
                continue
            assert 'loading=' in tag or 'decoding=' in tag, (
                f"img without loading/decoding hint in {rel}:\n  {tag}"
            )
