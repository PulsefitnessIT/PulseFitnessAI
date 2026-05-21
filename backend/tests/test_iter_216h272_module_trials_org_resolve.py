"""Iter 216h272 — `/memberships` shows "Organisation not found" (P0 bug).

User report (verbatim): *"Master Admin → Memberships still not
loading on Pulse Fitness or GymAxis"*. Screenshot showed the bare
text "Organisation not found" rendered at the page level on
`/memberships`.

### Root cause

The GymAxis Master Admin home org (`9fa701ef-5cc2-4db6-8795-bbfd2c85179d`)
was missing from the `organizations` collection — likely deleted
by an earlier data-wipe / fixture reset, but the master admin
USER record kept referencing it via `organization_id`.

Every Pulse Fitness staff user (incl. Craig Henshall) is also
parented to the same org, so the entire Pulse + GymAxis user base
lost access to `/memberships`, `/crm`, `/marketing` at once.

The chain:
  /memberships → <ModuleAccessGate module="memberships">
              → GET /api/me/module-trials
              → _resolve_org(user) → org=None → HTTPException(404, "Organisation not found")
              → frontend ModuleAccessGate.js L80 reads `e.response.data.detail`
                and renders it verbatim as the page text (L93-99).

### Fixes (layered)

* **Self-heal in the seeder** (`server.py:_seed_master_admin`):
  when the master admin user already exists but the matching org
  doc has gone missing, re-insert it with full-access modules.
  Idempotent — runs on every boot.
* **Safety net in `_resolve_org`** (`routes/module_trials.py`):
  when the lookup misses for a master admin, synthesise a
  minimal full-access org dict so the UI can still render.
  Belt + braces — survives the seeder failing too.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── 1. _resolve_org no longer 404s for master admin ─────────────


def test_resolve_org_synthesises_for_master_admin_when_doc_missing():
    """The single bug the user reported: org doc deleted, user record
    intact. `_resolve_org` must return a usable stub for masters,
    NOT raise 404 (which renders as the bare page text)."""
    from routes.module_trials import _resolve_org

    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value=None)
    with patch("routes.module_trials.db", fake_db):
        org = _run(_resolve_org({
            "id": "u1",
            "organization_id": "9fa701ef-5cc2-4db6-8795-bbfd2c85179d",
            "is_master_admin": True,
        }))
    assert org["id"] == "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"
    assert org["account_type"] == "full"
    # Full module access so all three operator pages render
    for m in ("memberships", "crm", "marketing"):
        assert org["modules"][m]["enabled"] is True


def test_resolve_org_still_404s_for_non_master_when_org_missing():
    """Non-masters with a broken FK should still see the 404 — the
    safety net is master-only by design (don't paper over real
    tenant data corruption for paying customers)."""
    from fastapi import HTTPException
    import pytest
    from routes.module_trials import _resolve_org

    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value=None)
    with patch("routes.module_trials.db", fake_db):
        with pytest.raises(HTTPException) as exc:
            _run(_resolve_org({
                "id": "u2",
                "organization_id": "missing",
                "is_master_admin": False,
            }))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Organisation not found"


def test_resolve_org_returns_real_doc_when_present():
    """Happy path — the safety net is purely additive, the
    normal lookup is unchanged."""
    from routes.module_trials import _resolve_org

    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "real-org", "name": "Real Co", "account_type": "lite",
    })
    with patch("routes.module_trials.db", fake_db):
        org = _run(_resolve_org({
            "id": "u3", "organization_id": "real-org", "is_master_admin": False,
        }))
    assert org["account_type"] == "lite"
    assert org["name"] == "Real Co"


# ─── 2. Seeder self-heal — org doc re-inserted on boot ───────────


def test_seeder_self_heals_missing_master_admin_org():
    """Verify the boot-time seeder re-creates the org doc when it's
    missing. Pinned via a static check rather than mocking the full
    boot path (which would also touch services like Stripe, MQ, etc.)."""
    src = pathlib.Path("/app/backend/server.py").read_text()
    seeder_block = src.split("async def _seed_master_admin")[1].split("async def _seed_services")[0]
    # Self-heal must:
    #   - read the existing user's organization_id
    #   - look up the org by that id
    #   - insert a fresh org doc if missing
    assert 'existing.get("organization_id")' in seeder_block
    assert "db.organizations.find_one" in seeder_block
    assert "db.organizations.insert_one" in seeder_block
    # Inserted doc must enable the three operator-facing modules,
    # else the UI would gate them out behind the upgrade screen.
    assert '"memberships"' in seeder_block
    assert '"crm"' in seeder_block
    assert '"marketing"' in seeder_block
    # Warning log so ops can see the heal happened
    assert "logger.warning" in seeder_block


# ─── 3. Don't widen the surface — only master admins get the synth ─


def test_resolve_org_safety_net_is_master_admin_only():
    """The synth stub is gated explicitly behind `is_master_admin`.
    A bug that flipped the check (or removed the guard) would mask
    real tenant data corruption for paying customers."""
    src = pathlib.Path("/app/backend/routes/module_trials.py").read_text()
    block = src.split("async def _resolve_org")[1].split("\n\n\n")[0]
    assert 'user.get("is_master_admin")' in block, (
        "safety net must check is_master_admin"
    )
    # The 404 raise must still be reachable for non-masters
    assert 'HTTPException(404, "Organisation not found")' in block
