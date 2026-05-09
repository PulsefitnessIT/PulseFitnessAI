"""Iter 216ay — unit tests for the heuristic rota's max_hours cap.

Tightens the previous LOW issue from iter 216ar: the heuristic could
exceed the cap by ~10% in pathological roster shapes. These tests assert
the cap holds exactly under several adversarial conditions.
"""
from __future__ import annotations

from datetime import date

from routes.staffing_ai_phase6 import _heuristic_rota


def _staff(n: int, role: str = "reception") -> list[dict]:
    return [{"id": f"s{i}", "full_name": f"Staff {i}", "primary_role": role} for i in range(n)]


def _hours_used(rota: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for sh in rota:
        sid = sh["staff_id"]
        # Each shift is fixed at 09:00-17:00 = 8h
        out[sid] = out.get(sid, 0.0) + 8.0
    return out


def test_cap_strictly_respected_with_small_pool_and_high_demand():
    """1 staff, demand for 7 reception shifts/week, cap 40h.
    Should produce exactly 5 shifts (40h) — never 6 or 7."""
    staff = _staff(1)
    demand = {wd: {"reception": 1} for wd in range(7)}
    rota = _heuristic_rota(staff, date(2026, 5, 11), demand, max_hours=40)
    used = _hours_used(rota)
    assert all(h <= 40.0 + 1e-6 for h in used.values()), used
    assert used.get("s0", 0) == 40.0


def test_cap_with_fractional_max_hours():
    """Pathological cap of 39.99h — only 4 shifts (32h) should fit."""
    staff = _staff(1)
    demand = {wd: {"reception": 1} for wd in range(7)}
    rota = _heuristic_rota(staff, date(2026, 5, 11), demand, max_hours=39.99)
    used = _hours_used(rota)
    # 4 shifts × 8h = 32h ≤ 39.99 ✓; 5 shifts = 40h > 39.99 ✗
    assert all(h <= 39.99 + 1e-6 for h in used.values()), used
    assert used.get("s0", 0) == 32.0


def test_cap_with_role_fallback_pool():
    """Ask for 'cleaner' but only 'reception' staff exist — fallback
    pool should still respect each staff's individual hours_used cap."""
    staff = _staff(2)  # both reception
    demand = {wd: {"cleaner": 2} for wd in range(7)}  # 14 cleaner slots
    rota = _heuristic_rota(staff, date(2026, 5, 11), demand, max_hours=40)
    used = _hours_used(rota)
    for sid, h in used.items():
        assert h <= 40.0 + 1e-6, f"{sid} exceeded cap: {h}"
    # 2 staff × 5 shifts = 10 filled; the other 4 slots should be unfilled
    assert len(rota) == 10


def test_cap_zero_hours_yields_empty_rota():
    """Edge: max_hours=0 → no one can be assigned to anything."""
    staff = _staff(3)
    demand = {wd: {"reception": 2} for wd in range(7)}
    rota = _heuristic_rota(staff, date(2026, 5, 11), demand, max_hours=0)
    assert rota == []


def test_cap_round_trip_no_float_drift():
    """Many small assignments accumulate without drifting past the cap."""
    staff = _staff(1)
    # 4 demand slots/day → would push past 40h cap quickly
    demand = {wd: {"reception": 3} for wd in range(7)}
    rota = _heuristic_rota(staff, date(2026, 5, 11), demand, max_hours=48)
    used = _hours_used(rota)
    assert all(h <= 48.0 + 1e-6 for h in used.values()), used
    # 6 shifts × 8h = 48h exactly
    assert used.get("s0", 0) == 48.0
