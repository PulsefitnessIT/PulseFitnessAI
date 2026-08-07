"""Unit tests for MOD Code → TL/SOR auto-fill mapping (Jan 2026)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.mod_sor_data import (
    build_seed_rate_card, match_by_mod_code, normalise_mod_code, MOD_CODE_TO_ITEM_NO,
)

RATE_CARD = build_seed_rate_card()


def _item_no(mod_code):
    rc = match_by_mod_code(mod_code, RATE_CARD)
    return rc["item_no"] if rc else None


class TestMODCodeNormalisation:
    def test_normalise_variants(self):
        assert normalise_mod_code("MOD-Spin") == "MOD-SPIN"
        assert normalise_mod_code(" mod ubike ") == "MOD-UBIKE"
        assert normalise_mod_code("MOD UBIKE") == "MOD-UBIKE"
        assert normalise_mod_code("") == ""
        assert normalise_mod_code(None) == ""


class TestMODCodeMappingCoverage:
    """Mapping coverage required by review request."""

    def test_mod_tread_to_2A(self):
        assert _item_no("MOD-Tread") == "2"

    def test_mod_rowing_to_4A(self):
        assert _item_no("MOD-Rowing") == "4"

    def test_mod_spin_to_3A(self):
        assert _item_no("MOD-Spin") == "3"

    def test_mod_bench_to_5A(self):
        assert _item_no("MOD-Bench") == "5"

    def test_mod_strength_to_20A(self):
        assert _item_no("MOD-Strength") == "20"

    def test_mod_multi2_to_23A(self):
        assert _item_no("MOD-Multi2") == "23"

    def test_mod_bike_to_18A(self):
        assert _item_no("MOD-Bike") == "18"

    def test_mod_ubike_spaced_to_18A(self):
        assert _item_no("mod ubike") == "18"

    def test_mod_stepper_to_16A(self):
        assert _item_no("MOD-Stepper") == "16"

    def test_mod_xtp_to_9A(self):
        assert _item_no("MOD-XTP") == "9"

    def test_mod_unknown_returns_none(self):
        assert match_by_mod_code("MOD-Unknown", RATE_CARD) is None


class TestRateCardTLCodes:
    """Verify TL numbers (code_a) resolve correctly for canonical MOD codes."""

    def _tl_a(self, mod_code):
        rc = match_by_mod_code(mod_code, RATE_CARD)
        return rc.get("code_a") if rc else None

    def test_tl_codes(self):
        assert self._tl_a("MOD-Spin") == "3A"
        assert self._tl_a("MOD-Stepper") == "16A"
        assert self._tl_a("MOD-XTP") == "9A"
        assert self._tl_a("MOD-Tread") == "2A"
        assert self._tl_a("MOD-Strength") == "20A"
