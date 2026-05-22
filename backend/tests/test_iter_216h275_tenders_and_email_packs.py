"""Iter 216h275 — P0 production fixes (3-in-one).

User-reported bugs (production at gymaxisai.com):

1. *"Pulse Fitness have also lost Tender Engine"* — the master
   admin has Tender Engine toggled ON for Pulse Fitness Limited
   but the tab does NOT appear in their CRM nav.
2. *"Can the option name be changed to 'Tenders'"* — rename
   "Tender Engine" → "Tenders" across the platform.
3. *"Marketing — Email packs not available"* — the bolt-on
   packs dialog shows "No packs available right now".

### Root causes

**(1) Tenders tab gated wrong.**
`CRMApp.js:81` had `internalOnly: true` on the Tenders nav item.
That checked `is_pulse_internal` on the user — which was only
true when the user's org name was **literally** "Pulse Fitness"
(strict ==). "Pulse Fitness Limited" (the real customer org!)
failed the check, so Tenders disappeared despite the master
admin toggle saying it was ON. The master admin toggle wasn't
even being read.

Fix:
* Replace `internalOnly: true` with `featureFlag: 'crm_tenders'`
  on both the Tenders and Contracts nav items.
* Add `features` + `modules` to the CRM `/me` + `/login` payloads
  so the frontend can resolve the gate.
* Loosen the "is_pulse_internal" name check from strict `==`
  to `startswith("pulse fitness")` so "Pulse Fitness Limited"
  also matches as a back-compat (existing internal flag still
  acts as a fallback when `features.crm_tenders` is unset on
  legacy orgs).

**(2) Tender Engine → Tenders rename.**
Updated 4 surfaces: `i18n/locales/en.json#crm.tenders`,
`AdminOrganizations.js#L373`, `AdminFeatures.js#L12`,
`FeatureControlPanel.js#L60`.

**(3) Marketing Email packs empty.**
`marketing_addons._seed_catalog_if_empty()` only seeded when
the collection was completely empty (`count > 0 → skip`). If
a master admin had previously deactivated every pack — or a
restore left only inactive rows behind — the auto-seed never
re-populated. Fixed: now re-seeds when no **active** rows exist
(and only inserts default codes that aren't already present,
preserving any custom packs).
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Tender Engine → Tenders rename ───────────────────────────


def test_tenders_label_renamed_in_i18n():
    src = pathlib.Path("/app/frontend/src/i18n/locales/en.json").read_text()
    assert '"tenders": "Tenders"' in src
    # No stale "Tender Engine" label in the canonical locale key
    lines = [ln for ln in src.splitlines() if '"tenders":' in ln]
    assert all("Tender Engine" not in ln for ln in lines)


def test_tenders_label_renamed_in_master_admin_panels():
    for path in (
        "/app/frontend/src/pages/MasterAdmin/AdminOrganizations.js",
        "/app/frontend/src/pages/MasterAdmin/AdminFeatures.js",
        "/app/frontend/src/pages/MasterAdmin/FeatureControlPanel.js",
    ):
        src = pathlib.Path(path).read_text()
        # The crm_tenders entry must read "Tenders" (not "Tender Engine")
        match = re.search(
            r"key:\s*'crm_tenders',\s*label:\s*'([^']+)'", src,
        )
        assert match, f"{path}: crm_tenders entry not found"
        assert match.group(1) == "Tenders", (
            f"{path}: crm_tenders label is '{match.group(1)}', expected 'Tenders'"
        )


# ─── 2. Tender nav gated by feature flag, not is_pulse_internal ──


def test_nav_item_uses_feature_flag_not_internal_only():
    """`internalOnly: true` was the bug — strict equality on org name
    excluded 'Pulse Fitness Limited'. Now the gate is the master
    admin feature toggle."""
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMApp.js"
    ).read_text())
    # Find the Tenders nav entry
    m = re.search(r"id:\s*'tenders',[^}]+", src)
    assert m, "Tenders nav entry not found"
    block = m.group(0)
    assert "featureFlag: 'crm_tenders'" in block, (
        "Tenders nav MUST gate on the feature flag, not internalOnly"
    )
    assert "internalOnly: true" not in block, (
        "Tenders nav must NOT carry internalOnly: true (h275 regression)"
    )


def test_nav_filter_evaluates_feature_flag():
    """Master admin sees all tabs. Other users see a tab when their
    org has the matching feature toggle ON (with `is_pulse_internal`
    as a back-compat fallback for legacy unset flags)."""
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMApp.js"
    ).read_text())
    assert "featureOn(it.featureFlag)" in src, (
        "visibleNavItems filter must consume the featureFlag prop"
    )
    # Master admin short-circuit so a misconfigured org doesn't lock the master out
    assert "user?.is_master_admin) return true" in src


# ─── 3. Backend: features + modules in CRM auth responses ────────


def test_crm_auth_me_returns_features_and_modules():
    """The frontend nav can only gate by feature flag if the
    /api/crm/auth/me payload actually carries `features` + `modules`."""
    src = pathlib.Path("/app/backend/routes/crm_auth.py").read_text()
    me_block = src.split("@router.get(\"/me\")")[1].split("@router")[0]
    assert '"features": features' in me_block
    assert '"modules": modules' in me_block


def test_crm_auth_login_returns_features_and_modules():
    src = pathlib.Path("/app/backend/routes/crm_auth.py").read_text()
    login_block = src.split("@router.post(\"/login\")")[1].split("@router")[0]
    assert '"features": features' in login_block
    assert '"modules": modules' in login_block


def test_resolve_crm_brand_flags_name_check_uses_startswith():
    """Pulse Fitness Limited used to be excluded because the name
    check was strict ==. Now uses startswith so the LTD suffix
    doesn't lock the customer out of their own internal modules."""
    src = pathlib.Path("/app/backend/routes/crm_auth.py").read_text()
    block = src.split("async def _resolve_crm_brand_flags")[1].split("\nasync def")[0]
    assert 'startswith("pulse fitness")' in block, (
        "Name match must be startswith — strict == excluded 'Pulse Fitness Limited'"
    )


def test_resolve_crm_brand_flags_returns_4_tuple():
    """The function signature now returns
    (crm_brand, is_pulse_internal, features, modules). Test by
    inspecting the actual return statement."""
    src = pathlib.Path("/app/backend/routes/crm_auth.py").read_text()
    block = src.split("async def _resolve_crm_brand_flags")[1].split("\nasync def")[0]
    assert "return crm_brand, is_pulse_internal, features, modules" in block


# ─── 4. Marketing email packs auto-seed ──────────────────────────


def test_marketing_addons_reseeds_when_all_inactive():
    """The previous count>0 guard meant a deactivate-then-restore
    flow left the catalog empty forever. Now it re-seeds when no
    ACTIVE rows exist."""
    src = pathlib.Path(
        "/app/backend/routes/marketing_addons.py"
    ).read_text()
    seed_block = src.split("async def _seed_catalog_if_empty")[1].split("\nasync def")[0]
    assert 'count_documents({"active": True})' in seed_block, (
        "h275: seeder must check for active rows specifically, not just any rows"
    )
    # Should still avoid duplicating codes the master admin has already configured
    assert "existing_codes" in seed_block


def test_marketing_addons_seeder_skips_codes_already_present():
    """Custom packs the master admin has added (or default packs
    intentionally deactivated by name) must not be re-inserted."""
    from routes.marketing_addons import _seed_catalog_if_empty, DEFAULT_ADDONS

    fake_db = MagicMock()
    fake_db.marketing_addons.count_documents = AsyncMock(return_value=0)

    # Two of the default codes are already present (master admin
    # disabled them on purpose) — seeder must only re-insert the
    # missing ones.
    present = ["email_boost_25k", "sms_pack_1k"]

    class _Cur:
        def __init__(self, items):
            self._items = list(items)
            self._i = 0

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._items):
                raise StopAsyncIteration
            x = self._items[self._i]
            self._i += 1
            return x

    fake_db.marketing_addons.find = MagicMock(
        return_value=_Cur([{"code": c} for c in present]),
    )
    fake_db.marketing_addons.insert_many = AsyncMock(return_value=MagicMock())

    with patch("routes.marketing_addons.db", fake_db):
        inserted = _run(_seed_catalog_if_empty())

    # 4 default packs - 2 already present = 2 newly inserted
    assert inserted == 2
    fake_db.marketing_addons.insert_many.assert_awaited_once()
    args, _ = fake_db.marketing_addons.insert_many.call_args
    new_codes = {d["code"] for d in args[0]}
    assert new_codes == {a["code"] for a in DEFAULT_ADDONS if a["code"] not in present}
