"""Iter 220dc — Engineer "Nearest of my jobs" endpoint.

Pins ``GET /api/svc/engineer/queue/my-nearest``:

  * With ``lat``+``lon``: sorts the engineer's open jobs by haversine
    distance, returning ``nearest`` + per-job ``distance_km`` +
    ``eta_minutes``.
  * Without origin: falls back to scheduled-time order, ``nearest``
    is the earliest scheduled job.
  * Org-scoped + engineer-scoped (the calling engineer's own jobs).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user():
    return {"id": "eng-1", "organization_id": "org-1"}


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _db_with(rows):
    fdb = MagicMock()
    fdb.svc_cases.find = MagicMock(return_value=_chain(rows))
    return fdb


# ── 1 · Geolocation origin sorts by distance ──────────────────────


def test_my_nearest_sorts_by_distance_when_lat_lon_provided():
    # Two jobs: one in central London, one in Manchester.
    rows = [
        {"id": "job-mcr", "reference": "GA-MCR", "title": "Manchester",
         "site_latitude": 53.4808, "site_longitude": -2.2426,
         "status": "scheduled", "scheduled_at": "2026-05-30T09:00:00Z"},
        {"id": "job-lon", "reference": "GA-LON", "title": "London",
         "site_latitude": 51.5074, "site_longitude": -0.1278,
         "status": "scheduled", "scheduled_at": "2026-05-30T11:00:00Z"},
    ]
    fdb = _db_with(rows)

    async def run():
        with patch("routes.svc.engineer_queue.db", fdb):
            from routes.svc.engineer_queue import my_nearest_jobs
            # Caller in London → London job should be nearest.
            return await my_nearest_jobs(
                lat=51.5, lon=-0.13, postcode=None, limit=5, user=_user(),
            )

    out = _run(run())
    assert out["origin_source"] == "geolocation"
    assert out["nearest"]["id"] == "job-lon"
    assert out["jobs"][0]["id"] == "job-lon"
    assert out["jobs"][0]["distance_km"] is not None
    assert out["jobs"][0]["eta_minutes"] is not None
    # The Manchester job is much further.
    assert out["jobs"][1]["distance_km"] > out["jobs"][0]["distance_km"]


def test_my_nearest_jobs_without_coords_go_last():
    rows = [
        {"id": "job-no-coords", "reference": "GA-NC", "status": "scheduled"},
        {"id": "job-lon", "reference": "GA-LON",
         "site_latitude": 51.5074, "site_longitude": -0.1278,
         "status": "scheduled"},
    ]
    fdb = _db_with(rows)

    async def run():
        with patch("routes.svc.engineer_queue.db", fdb):
            from routes.svc.engineer_queue import my_nearest_jobs
            return await my_nearest_jobs(
                lat=51.5, lon=-0.13, postcode=None, limit=5, user=_user(),
            )

    out = _run(run())
    assert out["nearest"]["id"] == "job-lon"
    # The coord-less job comes after the geocoded one.
    assert out["jobs"][-1]["id"] == "job-no-coords"


# ── 2 · No origin = scheduled order ───────────────────────────────


def test_my_nearest_without_origin_falls_back_to_scheduled():
    rows = [
        {"id": "job-a", "scheduled_at": "2026-05-30T09:00:00Z"},
        {"id": "job-b", "scheduled_at": "2026-05-30T11:00:00Z"},
    ]
    fdb = _db_with(rows)

    async def run():
        with patch("routes.svc.engineer_queue.db", fdb):
            from routes.svc.engineer_queue import my_nearest_jobs
            return await my_nearest_jobs(
                lat=None, lon=None, postcode=None, limit=5, user=_user(),
            )

    out = _run(run())
    assert out["origin_source"] is None
    assert out["sort"] == "scheduled"
    # In the absence of geo sorting, we trust Mongo's scheduled_at sort.
    assert out["nearest"]["id"] == "job-a"


# ── 3 · Query scope ───────────────────────────────────────────────


def test_my_nearest_query_is_org_and_engineer_scoped():
    """Pin the Mongo filter so a future refactor can't widen scope."""
    fdb = _db_with([])

    async def run():
        with patch("routes.svc.engineer_queue.db", fdb):
            from routes.svc.engineer_queue import my_nearest_jobs
            await my_nearest_jobs(
                lat=None, lon=None, postcode=None, limit=5, user=_user(),
            )

    _run(run())
    call_args = fdb.svc_cases.find.call_args
    flt = call_args.args[0]
    assert flt["organization_id"] == "org-1"
    assert flt["assigned_engineer_id"] == "eng-1"
    assert "$in" in flt["status"]


# ── 4 · Empty result ──────────────────────────────────────────────


def test_my_nearest_empty_when_no_jobs():
    fdb = _db_with([])

    async def run():
        with patch("routes.svc.engineer_queue.db", fdb):
            from routes.svc.engineer_queue import my_nearest_jobs
            return await my_nearest_jobs(
                lat=51.5, lon=-0.13, postcode=None, limit=5, user=_user(),
            )

    out = _run(run())
    assert out["nearest"] is None
    assert out["jobs"] == []
    assert out["count"] == 0


# ── 5 · Frontend wiring ───────────────────────────────────────────


def test_frontend_nearest_chip_mounted():
    src = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js").read_text()
    assert "NearestJobChip" in src
    for tid in (
        "nearest-job-chip", "nearest-job-find", "nearest-job-card",
        "nearest-job-open", "nearest-job-navigate",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Hits the right endpoint.
    assert "/svc/engineer/queue/my-nearest" in src
