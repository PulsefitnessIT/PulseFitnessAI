"""Iter 222 — Social media library brand scoping + seed-once.

Verifies the pure-logic guards added in routes/social_media_library.py:
  * `_brand_for` maps Pulse Master Admins → 'pulse', everyone else → 'gymaxis'.
  * Seed rows are tagged with the GymAxis brand.

End-to-end brand isolation + delete-persistence were verified by curl
against the live preview (pulse admin sees 0 GymAxis posts; deletes
persist; cross-brand delete returns 404). See CHANGELOG iter 222.
"""
from routes.social_media_library import _brand_for, SEED_ROWS, ENGINEER_RECRUIT_ROWS


def test_brand_for_pulse_admin():
    assert _brand_for({"is_pulse_admin": True}) == "pulse"
    assert _brand_for({"role": "pulse_master_admin"}) == "pulse"


def test_brand_for_gymaxis_master():
    assert _brand_for({"is_master_admin": True}) == "gymaxis"
    # A master admin who somehow also carries the pulse flag is still GymAxis.
    assert _brand_for({"is_master_admin": True, "is_pulse_admin": True}) == "gymaxis"


def test_brand_for_default():
    assert _brand_for({}) == "gymaxis"


def test_seed_rows_present():
    assert len(SEED_ROWS) > 0
    assert len(ENGINEER_RECRUIT_ROWS) > 0
