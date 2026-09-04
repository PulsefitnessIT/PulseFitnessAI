"""Headless (JS-rendering) page fetch — Iter Jun 2026.

Some prospect sites (e.g. reh-fit.com behind Cloudflare) serve a
JavaScript bot-challenge / "just a moment" interstitial to plain
server-side HTTP fetches, so the regular httpx reader in
`routes/crm_website_recognize.py` gets no real content.

This module renders the page in a real headless Chromium (Playwright)
and returns the fully-rendered HTML, giving the challenge JS time to
resolve. It's used ONLY as a fallback — the fast httpx path handles
the common case, and this heavier renderer only spins up when the
normal read is blocked or yields nothing useful.

Fails safe: any import / launch / navigation error returns None so the
caller falls back to whatever the plain fetch produced.
"""
from __future__ import annotations

import logging
import os

# Playwright resolves its browser binaries from PLAYWRIGHT_BROWSERS_PATH at
# launch time. The container ships Chromium under /pw-browsers; pin it here
# so the fetch works even if the process env didn't inherit the var. Falls
# back gracefully (render returns None) if the browser genuinely isn't there.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/pw-browsers")

from utils.ssrf_guard import assert_safe_external_url, SSRFBlocked
from utils.website_enrichment import _grab, _is_challenge_html

logger = logging.getLogger(__name__)

# A realistic desktop UA — challenge pages fingerprint headless defaults.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MAX_HTML_BYTES = 500_000
NAV_TIMEOUT_MS = 20_000
CHALLENGE_RETRIES = 4          # re-read every 2s while a challenge persists
CHALLENGE_WAIT_MS = 2_000


async def render_html(url: str) -> str | None:
    """Load `url` in headless Chromium and return the rendered HTML.

    Waits for JS bot-challenges to clear (up to ~8s). Returns None on
    any error, SSRF rejection, or if the challenge never clears.
    """
    try:
        assert_safe_external_url(url)
    except SSRFBlocked as exc:
        logger.warning("headless fetch blocked by SSRF guard url=%s reason=%s", url, exc.detail)
        return None
    except Exception:  # noqa: BLE001 — never let the guard crash the fetch
        return None

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001 — playwright not installed
        logger.warning("playwright unavailable, skipping headless fetch: %s", exc)
        return None

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=_UA,
                locale="en-GB",
                viewport={"width": 1366, "height": 900},
            )
            # Mask the automation fingerprint Cloudflare/Turnstile checks for.
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

            html = await page.content()
            title = _grab(r"<title[^>]*>([^<]+)</title>", html) or ""
            # Give a Cloudflare / JS interstitial time to hand off to the
            # real page, re-reading until it clears or we run out of tries.
            tries = 0
            while _is_challenge_html(html, title) and tries < CHALLENGE_RETRIES:
                await page.wait_for_timeout(CHALLENGE_WAIT_MS)
                html = await page.content()
                title = _grab(r"<title[^>]*>([^<]+)</title>", html) or ""
                tries += 1

            await context.close()
            return html[:MAX_HTML_BYTES] if html else None
    except Exception as exc:  # noqa: BLE001 — timeouts, nav errors, crashes
        logger.warning("headless fetch failed url=%s err=%s", url, exc)
        return None
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
