"""Iter 220o — Instagram-attributed apply form.

Auto-detect `?utm_source=instagram` on the Partner Engineer landing
page and swap the hero copy + carry the attribution into the apply
form so master admin can see which channel converted the engineer.

Backend pins:
  * /api/partners/track-source — anonymous counter endpoint. Increments
    `db.partner_attribution_landings` per (source|medium|campaign) key.
    No-UTM payloads are intentionally skipped (organic traffic lives
    elsewhere).
  * /api/partners/public-apply — accepts UTM Form fields and persists
    them on the application doc.
  * /api/partners/attribution-summary — master-admin-only roll-up:
    landings + conversions + conversion-rate per source.

Frontend pins (source-level):
  * useUtmAttribution hook reads URL params on mount, persists to
    sessionStorage with first-touch semantics, fires the track-source
    ping once.
  * PartnerEngineerLanding hero swaps eyebrow/headline/sub-copy when
    the visitor lands via Instagram.
  * PartnerApplyPublic submit appends UTM Form fields from URL OR
    sessionStorage on every application post.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Backend: track-source endpoint ────────────────────────────────


def test_track_source_increments_counter_with_utm_source():
    from routes.partners import track_partner_attribution_source

    captured = {}

    async def fake_update_one(filt, update, upsert=False):
        captured["filt"] = filt
        captured["update"] = update
        captured["upsert"] = upsert
        return MagicMock(upserted_id="x", matched_count=0)

    fake_db = MagicMock()
    fake_db.partner_attribution_landings.update_one = AsyncMock(side_effect=fake_update_one)

    with patch("routes.partners.db", fake_db):
        res = _run(track_partner_attribution_source({
            "utm_source": "instagram",
            "utm_medium": "social",
            "utm_campaign": "partner-launch-may26",
            "utm_content": "feed_01",
            "referrer_url": "https://www.instagram.com/p/xxx",
            "landing_path": "/partners/engineers",
        }))

    assert res["ok"] is True
    assert res["key"] == "instagram|social|partner-launch-may26"
    assert captured["filt"] == {"key": "instagram|social|partner-launch-may26"}
    # $inc on landings, $set on last_*, $setOnInsert on first/source/medium/campaign
    assert captured["update"]["$inc"] == {"landings": 1}
    assert "last_landing_at" in captured["update"]["$set"]
    assert captured["update"]["$setOnInsert"]["utm_source"] == "instagram"
    assert captured["update"]["$setOnInsert"]["utm_medium"] == "social"
    assert captured["update"]["$setOnInsert"]["utm_campaign"] == "partner-launch-may26"
    assert captured["update"]["$setOnInsert"]["utm_content"] == "feed_01"
    assert captured["upsert"] is True


def test_track_source_skips_when_no_utm_source():
    """Organic traffic must NOT pollute the per-channel counters —
    that data lives in web analytics."""
    from routes.partners import track_partner_attribution_source

    fake_db = MagicMock()
    fake_db.partner_attribution_landings.update_one = AsyncMock()

    with patch("routes.partners.db", fake_db):
        res = _run(track_partner_attribution_source({}))

    assert res == {"ok": True, "skipped": "no-utm-source"}
    fake_db.partner_attribution_landings.update_one.assert_not_called()


def test_track_source_normalises_utm_to_lowercase_and_caps_length():
    """`Instagram` and `INSTAGRAM` and `instagram` must all bucket
    to the same channel. Adversarial input (mega-long string) is
    capped to 200 chars at the boundary."""
    from routes.partners import track_partner_attribution_source

    captured = {}

    async def fake_upsert(filt, update, upsert=False):
        captured["update"] = update
        return MagicMock()

    fake_db = MagicMock()
    fake_db.partner_attribution_landings.update_one = AsyncMock(side_effect=fake_upsert)

    with patch("routes.partners.db", fake_db):
        _run(track_partner_attribution_source({
            "utm_source": "INSTAGRAM",
            "utm_medium": "  Paid  ",
            "utm_campaign": "X" * 500,  # adversarial
        }))

    on_insert = captured["update"]["$setOnInsert"]
    assert on_insert["utm_source"] == "instagram", "Must lowercase"
    assert on_insert["utm_medium"] == "paid", "Must trim + lowercase"
    assert len(on_insert["utm_campaign"]) == 200, "Must cap at 200 chars"


def test_attribution_summary_decorates_landings_with_conversion_rate():
    from routes.partners import partner_attribution_summary

    landings_rows = [
        {"key": "instagram|social|launch", "utm_source": "instagram",
         "utm_medium": "social", "utm_campaign": "launch", "landings": 100},
        {"key": "linkedin|social|launch", "utm_source": "linkedin",
         "utm_medium": "social", "utm_campaign": "launch", "landings": 40},
    ]
    convs = [
        {"_id": "instagram", "applications": 8},
        {"_id": "linkedin", "applications": 1},
    ]

    fake_db = MagicMock()
    landings_cursor = MagicMock()
    landings_cursor.sort.return_value = landings_cursor
    landings_cursor.to_list = AsyncMock(return_value=landings_rows)
    fake_db.partner_attribution_landings.find = MagicMock(return_value=landings_cursor)
    agg_cursor = MagicMock()
    agg_cursor.to_list = AsyncMock(return_value=convs)
    fake_db.partner_applications.aggregate = MagicMock(return_value=agg_cursor)

    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._require_master_admin", return_value=None):
        res = _run(partner_attribution_summary(user={"id": "u", "is_master_admin": True}))

    assert res["totals"]["landings"] == 140
    assert res["totals"]["applications_attributed"] == 9
    # Per-row enrichment: applications + conversion_rate_pct
    by_src = {r["utm_source"]: r for r in res["rows"]}
    assert by_src["instagram"]["applications"] == 8
    assert by_src["instagram"]["conversion_rate_pct"] == 8.0  # 8/100
    assert by_src["linkedin"]["applications"] == 1
    assert by_src["linkedin"]["conversion_rate_pct"] == 2.5   # 1/40


# ── Backend: public-apply accepts UTM Form fields ───────────────────


def test_public_apply_signature_accepts_utm_fields():
    """The /partners/public-apply endpoint must accept utm_source,
    utm_medium, utm_campaign, utm_content, utm_term, and referrer_url
    as Form fields so the apply submission can carry attribution."""
    import inspect
    from routes.partners import public_apply_partner
    sig = inspect.signature(public_apply_partner)
    for name in ("utm_source", "utm_medium", "utm_campaign",
                 "utm_content", "utm_term", "referrer_url"):
        assert name in sig.parameters, (
            f"public_apply_partner must accept `{name}` as a Form param"
        )


def test_public_apply_doc_includes_utm_fields_in_source():
    """Source-level pin — the persisted application doc must
    include the utm_* fields so master admin can filter on them."""
    import pathlib
    src = pathlib.Path("/app/backend/routes/partners.py").read_text()
    # The block that builds the application doc must reference each.
    for name in ("utm_source", "utm_medium", "utm_campaign",
                 "utm_content", "utm_term", "referrer_url"):
        assert f'"{name}":' in src, (
            f"application doc must persist `{name}`"
        )


# ── Frontend: hook + UI wiring (source-level pins) ──────────────────


def test_use_utm_attribution_hook_exists_with_first_touch_semantics():
    import pathlib
    src = pathlib.Path("/app/frontend/src/hooks/useUtmAttribution.js").read_text()
    assert "useUtmAttribution" in src
    # First-touch — only overwrite session storage if no existing
    # attribution. Pins the rule against silent regression.
    assert "First-touch" in src or "first-touch" in src or "first touch" in src.lower(), (
        "Hook docstring must explain first-touch semantics"
    )
    # Must call /partners/track-source on first landing.
    assert "/partners/track-source" in src
    # Returns applyHref so CTAs can carry the attribution forward.
    assert "applyHref" in src
    # SessionStorage key must match the apply form's reader.
    assert "gx_utm_attribution" in src


def test_apply_form_reads_session_storage_key():
    """The apply form's submit() must read the same sessionStorage
    key the landing-page hook writes (`gx_utm_attribution`). Pin
    the contract so a rename of the key in one file can't silently
    break attribution end-to-end."""
    import pathlib
    apply_src = pathlib.Path("/app/frontend/src/pages/Marketing/PartnerApplyPublic.js").read_text()
    assert "gx_utm_attribution" in apply_src, (
        "Apply form must read the landing-page's sessionStorage key"
    )
    # And forwards all six attribution fields on the Form payload.
    for field in ("utm_source", "utm_medium", "utm_campaign",
                  "utm_content", "utm_term", "referrer_url"):
        assert field in apply_src, f"Apply form must forward `{field}`"


def test_partner_engineer_landing_swaps_hero_for_instagram():
    """Source-level pin — the hero must branch on `isInstagram` and
    expose `data-attribution-source` on the outer section so an E2E
    can verify the swap fired."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/Marketing/PartnerEngineerLanding.js").read_text()
    assert "useUtmAttribution" in src
    assert "isInstagram" in src
    assert 'data-attribution-source' in src, (
        "Hero must expose data-attribution-source for E2E verification"
    )
    assert "Saw us on Instagram" in src, "Instagram-specific eyebrow must be present"
    assert "Claim your Instagram spot" in src, (
        "Instagram-specific CTA copy must be present"
    )
    # Both CTAs (hero + final) must use applyHref so attribution
    # rides forward regardless of which button the visitor taps.
    assert src.count("applyHref") >= 2, (
        "Both hero + final-CTA must carry attribution via applyHref"
    )
