"""Iter 226 — Pulse data explorer scoping.

Pins the pure scoping logic for the curated Pulse-scoped data explorer
(routes/master_admin_pulse_explorer.py). End-to-end verified live: the
Pulse test admin sees 4 orgs / 6 users / 115 equipment (scoped), not the
789 orgs / 791 users in the full DB.
"""
from routes.master_admin_pulse_explorer import (
    _scope_clause, _merge_scoped, PULSE_COLLECTIONS, _BY_NAME,
)
from utils.brand_filter import PULSE_BRAND_VALUES


def test_org_self_scope():
    assert _scope_clause("org_self", ["a", "b"]) == {"id": {"$in": ["a", "b"]}}


def test_organization_id_scope():
    assert _scope_clause("organization_id", ["a"]) == {"organization_id": {"$in": ["a"]}}


def test_brand_pulse_scope_is_org_independent():
    # Social library is brand-tagged, not org-linked.
    assert _scope_clause("brand_pulse", []) == {"brand": {"$in": PULSE_BRAND_VALUES}}


def test_empty_org_ids_returns_nothing_matchable():
    # No pulse orgs → an $in [] clause that matches zero docs (not everything).
    assert _scope_clause("organization_id", []) == {"organization_id": {"$in": []}}


def test_search_is_anded_inside_scope():
    scope = {"organization_id": {"$in": ["a"]}}
    search = {"$or": [{"name": {"$regex": "x"}}]}
    merged = _merge_scoped(scope, search)
    assert merged == {"$and": [scope, search]}
    # Scope alone when no search.
    assert _merge_scoped(scope, {}) == scope


def test_whitelist_has_no_global_collections():
    # Guard against accidentally adding a GymAxis-global / cross-tenant
    # collection (audit logs, login events, trials, all-org config…).
    names = {c["name"] for c in PULSE_COLLECTIONS}
    forbidden = {"audit_log", "login_events", "trials", "organizations_all",
                 "crm_audit_log", "users_global", "system.users"}
    assert names.isdisjoint(forbidden)
    # Every entry has a valid scope strategy.
    for c in PULSE_COLLECTIONS:
        assert c["scope"] in {"org_self", "organization_id", "brand_pulse"}
    assert len(_BY_NAME) == len(PULSE_COLLECTIONS)
