"""Iter 216h254 — MemberEditDrawer date-field + Country consistency.

Visual audit pass across the Memberships module:
- SellPackAtDeskModal: no date inputs → no changes required.
- ClassActionDrawer: no date inputs → no changes required.
- MemberEditDrawer:
    • DOB was using native `<input type="date">` (DD/MM/YYYY on UK
      locale but YYYY-MM-DD on others). Replaced with the shared
      `DatePicker` so create + edit flows feel identical.
    • Country was a free-text `<input>` with datalist autocomplete.
      Upgraded to a proper `<select>` matching AddMemberModal (with a
      "(custom)" fallback for legacy free-text values).
"""
from __future__ import annotations

import pathlib


def test_member_edit_drawer_uses_shared_datepicker_for_dob():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MemberEditDrawer.js").read_text()
    # Shared DatePicker imported.
    assert "import DatePicker from '@/components/shared/DatePicker';" in src
    # The native date input is gone.
    assert "<Input type=\"date\"" not in src
    # The DatePicker drives DOB now.
    assert '<DatePicker' in src
    assert 'testid="member-drawer-dob"' in src


def test_member_edit_drawer_country_is_select():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MemberEditDrawer.js").read_text()
    # Free-text country gone.
    assert 'placeholder="Country" testid="member-drawer-country"' not in src
    # datalist removed.
    assert 'id="member-drawer-country-list"' not in src
    # Select-driven country present.
    assert 'data-testid="member-drawer-country"' in src
    assert "{COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}" in src


def test_sell_pack_modal_has_no_native_date_inputs():
    """Sanity check — no regressions should reintroduce native date inputs."""
    src = pathlib.Path("/app/frontend/src/pages/Memberships/modals/SellPackAtDeskModal.js").read_text()
    assert 'type="date"' not in src


def test_class_action_drawer_has_no_native_date_inputs():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/ClassActionDrawer.js").read_text()
    assert 'type="date"' not in src
