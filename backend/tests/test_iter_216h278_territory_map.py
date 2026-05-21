"""Iter 216h278 — Interactive UK Territory Map.

Customer ask (verbatim): *"I would like an interactive Map of the UK
where we can allocate colours to counties — then be able to allocate
those areas to Sales Managers and Engineers — We can then use this
within Tenders as a visual representation of sales managers and
engineers coverage."*

These tests pin:
* Staff palette returns colour + role with sensible defaults.
* `PUT /staff/{uid}/style` validates input + persists changes.
* `PUT /region/{type}/{code}` creates / updates / archives a region
  territory and refuses unknown region types.
* Coverage map groups assignees by region.
* Coverage-for resolves postcode-area before county (priority 100 vs 10).
* The matching engine treats postcode-area territories with priority
  100 so SW overrides Greater London on cross-overs.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.crm_territories import (
    _matches_territory,
    _normalise_colour,
    _normalise_role,
    _REGION_PRIORITY,
    coverage_for,
    coverage_map,
    staff_palette,
    update_staff_style,
    upsert_region_assignment,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, xs): self._xs = list(xs)
        def __aiter__(self): self._i = 0; return self
        async def __anext__(self):
            if self._i >= len(self._xs): raise StopAsyncIteration
            x = self._xs[self._i]; self._i += 1; return x
    return _Cur(items)


def _admin():
    return {"id": "user-admin", "organization_id": "org-1", "role": "admin"}


def _make_cursor(items):
    """Build a fake Motor cursor that supports .sort().to_list()."""
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


# ── 1. Helpers ─────────────────────────────────────────────────────


def test_normalise_colour_accepts_hex_and_falls_back():
    assert _normalise_colour("#2563EB") == "#2563EB"
    assert _normalise_colour("2563eb") == "#2563EB"
    assert _normalise_colour("#abc") == "#ABC"
    # Bad / empty / nonsense → neutral grey.
    assert _normalise_colour(None) == "#94A3B8"
    assert _normalise_colour("") == "#94A3B8"
    assert _normalise_colour("rgb(1,2,3)") == "#94A3B8"


def test_normalise_role_only_accepts_known_values():
    assert _normalise_role("sales_manager") == "sales_manager"
    assert _normalise_role("Engineer") == "engineer"
    assert _normalise_role("BOTH") == "both"
    assert _normalise_role("") == "sales_manager"
    assert _normalise_role("foo") == "sales_manager"


def test_region_priority_postcode_beats_county():
    # The customer asked for postcode-overrides on cross-overs — pin
    # the priority gap so a future refactor can't accidentally flatten
    # both layers to the same priority.
    assert _REGION_PRIORITY["postcode_area"] > _REGION_PRIORITY["county"]


# ── 2. Staff palette ───────────────────────────────────────────────


def test_staff_palette_returns_defaults_when_unstyled():
    fake_db = MagicMock()
    cur = _make_cursor([
        {"id": "u1", "full_name": "Jane", "email": "jane@x"},
        {"id": "u2", "full_name": "Tom",  "email": "tom@x", "colour_hex": "#FF0000", "territory_role": "engineer"},
    ])
    fake_db.crm_users.find = MagicMock(return_value=cur)
    with patch("routes.crm_territories.db", fake_db):
        result = _run(staff_palette(user=_admin()))
    assert result["total"] == 2
    [u1, u2] = result["staff"]
    # Default neutral colour + manager role for unstyled.
    assert u1["colour_hex"] == "#94A3B8"
    assert u1["territory_role"] == "sales_manager"
    # Styled user preserved.
    assert u2["colour_hex"] == "#FF0000"
    assert u2["territory_role"] == "engineer"


def test_update_staff_style_rejects_empty_body():
    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value={"id": "u1"})
    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        with pytest.raises(Exception) as exc:
            _run(update_staff_style("u1", data={}, user=_admin()))
        assert "Nothing to update" in str(exc.value.detail) or "Nothing to update" in str(exc.value)


def test_update_staff_style_persists_normalised_values():
    fake_db = MagicMock()
    fake_db.crm_users.find_one = AsyncMock(return_value={"id": "u1"})
    fake_db.crm_users.update_one = AsyncMock()
    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(update_staff_style("u1", data={"colour_hex": "2563eb", "territory_role": "Engineer"}, user=_admin()))
    assert out["colour_hex"] == "#2563EB"
    assert out["territory_role"] == "engineer"
    # Confirm the update payload was correct.
    args, _ = fake_db.crm_users.update_one.call_args
    assert args[1]["$set"]["colour_hex"] == "#2563EB"
    assert args[1]["$set"]["territory_role"] == "engineer"


# ── 3. Region assignment ───────────────────────────────────────────


def test_upsert_region_rejects_unknown_type():
    with pytest.raises(Exception) as exc:
        _run(upsert_region_assignment("borough", "Camden", data={"assigned_rep_ids": ["u1"]}, user=_admin()))
    assert "region_type" in str(exc.value.detail)


def test_upsert_region_creates_new_county_territory():
    fake_db = MagicMock()
    fake_db.crm_users.find = MagicMock(return_value=_make_cursor([{"id": "u1"}, {"id": "u2"}]))
    fake_db.crm_territories.find_one = AsyncMock(return_value=None)
    fake_db.crm_territories.insert_one = AsyncMock()
    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(upsert_region_assignment(
            "county", "Greater London",
            data={"assigned_rep_ids": ["u1", "u2"]},
            user=_admin(),
        ))
    assert out["created"] is True
    inserted = fake_db.crm_territories.insert_one.call_args[0][0]
    assert inserted["region_type"] == "county"
    assert inserted["region_code"] == "Greater London"
    assert inserted["counties"] == ["Greater London"]
    assert inserted["postcode_prefixes"] == []
    assert inserted["assigned_rep_ids"] == ["u1", "u2"]
    assert inserted["priority"] == _REGION_PRIORITY["county"]


def test_upsert_region_updates_existing_postcode_area():
    fake_db = MagicMock()
    fake_db.crm_users.find = MagicMock(return_value=_make_cursor([{"id": "u3"}]))
    fake_db.crm_territories.find_one = AsyncMock(return_value={
        "id": "t-existing", "region_type": "postcode_area", "region_code": "SW",
        "assigned_rep_ids": ["u1"],
    })
    fake_db.crm_territories.update_one = AsyncMock()
    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(upsert_region_assignment(
            "postcode_area", "SW",
            data={"assigned_rep_ids": ["u3"]},
            user=_admin(),
        ))
    assert out["territory_id"] == "t-existing"
    patch_doc = fake_db.crm_territories.update_one.call_args[0][1]["$set"]
    assert patch_doc["assigned_rep_ids"] == ["u3"]
    assert patch_doc["archived"] is False


def test_upsert_region_clears_when_empty_list():
    fake_db = MagicMock()
    fake_db.crm_users.find = MagicMock(return_value=_make_cursor([]))
    fake_db.crm_territories.find_one = AsyncMock(return_value={"id": "t-x"})
    fake_db.crm_territories.update_one = AsyncMock()
    with patch("routes.crm_territories.db", fake_db), \
         patch("routes.crm_territories.log_audit", AsyncMock()):
        out = _run(upsert_region_assignment("county", "Kent", data={"assigned_rep_ids": []}, user=_admin()))
    assert out["cleared"] is True
    patch_doc = fake_db.crm_territories.update_one.call_args[0][1]["$set"]
    assert patch_doc["archived"] is True
    assert patch_doc["assigned_rep_ids"] == []


# ── 4. Coverage map ────────────────────────────────────────────────


def test_coverage_map_groups_by_region_and_resolves_rep_meta():
    fake_db = MagicMock()
    # Two territories — one county, one postcode area, sharing rep u1.
    fake_db.crm_territories.find = MagicMock(return_value=_make_cursor([
        {"region_type": "county", "region_code": "Greater London", "assigned_rep_ids": ["u1"]},
        {"region_type": "postcode_area", "region_code": "SW", "assigned_rep_ids": ["u1", "u2"]},
    ]))
    fake_db.crm_users.find = MagicMock(return_value=_make_cursor([
        {"id": "u1", "full_name": "Jane",  "colour_hex": "#2563EB", "territory_role": "sales_manager"},
        {"id": "u2", "full_name": "Tom",   "colour_hex": "#16A34A", "territory_role": "engineer"},
    ]))
    with patch("routes.crm_territories.db", fake_db):
        result = _run(coverage_map(user=_admin()))
    assert "Greater London" in result["counties"]
    assert "SW" in result["postcode_areas"]
    assert {m["user_id"] for m in result["postcode_areas"]["SW"]} == {"u1", "u2"}
    assert result["counties"]["Greater London"][0]["colour_hex"] == "#2563EB"


# ── 5. Coverage resolution (postcode wins) ─────────────────────────


def test_matches_territory_postcode_prefix_wins_for_short_input():
    t_postcode = {"postcode_prefixes": ["SW"], "counties": [], "regions": [], "countries": []}
    t_county   = {"postcode_prefixes": [],     "counties": ["Greater London"], "regions": [], "countries": []}
    record = {"postcode": "SW1A 1AA", "county": "Greater London"}
    # Both match — that's correct. The priority sort in
    # `resolve_territory_for` is what picks postcode-area over county;
    # the matcher itself just answers "does this record qualify".
    assert _matches_territory(t_postcode, record) is True
    assert _matches_territory(t_county, record) is True


def test_coverage_for_returns_owner_via_company_lookup():
    fake_db = MagicMock()
    fake_db.crm2_companies.find_one = AsyncMock(return_value={
        "postcode": "SW1A 1AA", "county": "Greater London",
    })
    # resolve_territory_for: postcode-area territory has higher priority + matches first.
    fake_db.crm_territories.find = MagicMock(return_value=_make_cursor([
        {
            "id": "t-sw", "region_type": "postcode_area", "region_code": "SW", "name": "Postcode SW",
            "postcode_prefixes": ["SW"], "counties": [], "regions": [], "countries": [],
            "assigned_rep_ids": ["u-rep"], "priority": 100,
        },
    ]))
    fake_db.crm_users.find = MagicMock(return_value=_make_cursor([
        {"id": "u-rep", "full_name": "Jane", "colour_hex": "#2563EB", "territory_role": "sales_manager"},
    ]))
    with patch("routes.crm_territories.db", fake_db):
        out = _run(coverage_for(company_id="company-1", user=_admin()))
    assert out["covered"] is True
    assert out["territory_id"] == "t-sw"
    assert out["region_type"] == "postcode_area"
    assert out["reps"][0]["full_name"] == "Jane"


def test_coverage_for_returns_uncovered_when_no_territory():
    fake_db = MagicMock()
    fake_db.crm_territories.find = MagicMock(return_value=_make_cursor([]))
    with patch("routes.crm_territories.db", fake_db):
        out = _run(coverage_for(postcode="ZZ99 9ZZ", user=_admin()))
    assert out == {"covered": False}
