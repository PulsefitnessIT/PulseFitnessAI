"""Iter 216h270 — Expand Miller Heiman fields on contacts (P3).

The h223 iter shipped multi-tag `influence_types[]` + a per-opp
stakeholder map. This iter adds the **qualitative Strategic
Selling "Blue Sheet" fields** every account exec is taught to
maintain on each contact before a deal review:

  • `buying_influence_level`   — low / medium / high
  • `adoption_sentiment`       — 5-point: strong_anti → strong_supporter
  • `coverage_confidence`      — stranger / acquaintance / trusted_advisor
  • `reports_to_id`            — link to another contact (org chart)
  • `personal_wins`            — free-text motivations

New surfaces:
  GET   /api/crm/stakeholders/miller-heiman-catalogues
  PATCH /api/crm/contacts/{id}/miller-heiman
  GET   /api/crm/v2/contacts/{id}                ← now hydrates `reports_to`
  POST  /api/crm/v2/contacts                     ← accepts the new fields

Frontend adds a "Strategic" tab on the contact detail and surfaces
adoption sentiment + buying influence as header badges.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Catalogues + validators ──────────────────────────────────


def test_catalogues_have_canonical_shape():
    from routes import crm_stakeholders as st

    # Catalogue lists must be non-empty and every row must have at
    # minimum id + label so the UI can render pills.
    for col in (st.BUYING_INFLUENCE_LEVELS, st.ADOPTION_SENTIMENTS, st.COVERAGE_CONFIDENCES):
        assert col, "catalogue is empty"
        for row in col:
            assert row.get("id") and row.get("label")
    # Sentiments must include the canonical 5-point scale
    sentiment_ids = {s["id"] for s in st.ADOPTION_SENTIMENTS}
    assert sentiment_ids == {
        "strong_anti", "anti", "neutral", "supporter", "strong_supporter",
    }
    # Buying influence must be the canonical 3 buckets
    inf_ids = {b["id"] for b in st.BUYING_INFLUENCE_LEVELS}
    assert inf_ids == {"low", "medium", "high"}
    # Coverage confidence — 3 standard tiers
    cov_ids = {c["id"] for c in st.COVERAGE_CONFIDENCES}
    assert cov_ids == {"stranger", "acquaintance", "trusted_advisor"}


def test_validate_miller_heiman_accepts_valid_values():
    from routes.crm_stakeholders import _validate_miller_heiman

    out = _validate_miller_heiman({
        "buying_influence_level": "High",
        "adoption_sentiment": "supporter",
        "coverage_confidence": "trusted_advisor",
        "reports_to_id": "  abc-123  ",
        "personal_wins": "  Wants visibility at C-suite  ",
        "ignored_field": "should not leak",
    })
    assert out["buying_influence_level"] == "high"   # case-insensitive
    assert out["adoption_sentiment"] == "supporter"
    assert out["coverage_confidence"] == "trusted_advisor"
    assert out["reports_to_id"] == "abc-123"          # trimmed
    assert out["personal_wins"] == "Wants visibility at C-suite"
    assert "ignored_field" not in out                  # whitelist enforced


def test_validate_miller_heiman_clears_fields_with_empty_string():
    from routes.crm_stakeholders import _validate_miller_heiman

    out = _validate_miller_heiman({
        "buying_influence_level": "",
        "reports_to_id": "",
    })
    assert out["buying_influence_level"] is None       # explicit clear
    assert out["reports_to_id"] is None


def test_validate_miller_heiman_rejects_unknown_values():
    from routes.crm_stakeholders import _validate_miller_heiman

    with pytest.raises(HTTPException) as exc:
        _validate_miller_heiman({"adoption_sentiment": "indifferent"})
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        _validate_miller_heiman({"buying_influence_level": "extreme"})
    with pytest.raises(HTTPException):
        _validate_miller_heiman({"coverage_confidence": "best_friend"})


def test_validate_miller_heiman_ignores_missing_fields():
    """Partial payload semantics — fields not in the request must
    NOT appear in the validator output (don't overwrite with None)."""
    from routes.crm_stakeholders import _validate_miller_heiman

    out = _validate_miller_heiman({"adoption_sentiment": "neutral"})
    assert out == {"adoption_sentiment": "neutral"}
    assert "buying_influence_level" not in out


# ─── 2. Endpoint registration + behaviour ────────────────────────


def test_endpoints_registered():
    from routes.crm_stakeholders import router
    paths = {r.path for r in router.routes}
    assert "/crm/stakeholders/miller-heiman-catalogues" in paths
    assert "/crm/contacts/{contact_id}/miller-heiman" in paths


def test_catalogues_endpoint_returns_all_three_lists():
    from routes.crm_stakeholders import list_miller_heiman_catalogues

    out = _run(list_miller_heiman_catalogues(user={"organization_id": "o"}))
    assert set(out.keys()) == {
        "buying_influence_levels",
        "adoption_sentiments",
        "coverage_confidences",
    }
    assert len(out["adoption_sentiments"]) == 5


def test_patch_endpoint_updates_contact_and_logs_audit():
    from routes.crm_stakeholders import update_contact_miller_heiman

    fake_db = MagicMock()
    fake_db.crm2_contacts.find_one = AsyncMock(return_value={
        "id": "c1", "organization_id": "o", "first_name": "Jane",
    })
    fake_db.crm2_contacts.update_one = AsyncMock(return_value=MagicMock())

    with patch("routes.crm_stakeholders.db", fake_db), \
         patch("routes.crm_stakeholders.log_audit", new=AsyncMock()) as audit:
        out = _run(update_contact_miller_heiman(
            contact_id="c1",
            data={"adoption_sentiment": "supporter", "buying_influence_level": "high"},
            user={"id": "u", "organization_id": "o", "role": "admin"},
        ))

    assert out["adoption_sentiment"] == "supporter"
    assert out["buying_influence_level"] == "high"
    assert "updated_at" in out
    # Audit was logged with the action key
    assert audit.await_count == 1
    args, _ = audit.call_args
    assert args[3] == "miller_heiman_updated"


def test_patch_endpoint_404s_on_unknown_contact():
    from routes.crm_stakeholders import update_contact_miller_heiman

    fake_db = MagicMock()
    fake_db.crm2_contacts.find_one = AsyncMock(return_value=None)

    with patch("routes.crm_stakeholders.db", fake_db), pytest.raises(HTTPException) as exc:
        _run(update_contact_miller_heiman(
            contact_id="ghost",
            data={"adoption_sentiment": "neutral"},
            user={"id": "u", "organization_id": "o", "role": "admin"},
        ))
    assert exc.value.status_code == 404


def test_patch_endpoint_rejects_self_reports_to():
    from routes.crm_stakeholders import update_contact_miller_heiman

    fake_db = MagicMock()
    fake_db.crm2_contacts.find_one = AsyncMock(return_value={"id": "c1", "organization_id": "o"})

    with patch("routes.crm_stakeholders.db", fake_db), pytest.raises(HTTPException) as exc:
        _run(update_contact_miller_heiman(
            contact_id="c1",
            data={"reports_to_id": "c1"},   # self-reference
            user={"id": "u", "organization_id": "o", "role": "admin"},
        ))
    assert exc.value.status_code == 400
    assert "themselves" in exc.value.detail


def test_patch_endpoint_validates_reports_to_exists_in_same_org():
    from routes.crm_stakeholders import update_contact_miller_heiman

    fake_db = MagicMock()
    # First call (self) returns the contact; second call (boss) returns None
    fake_db.crm2_contacts.find_one = AsyncMock(side_effect=[
        {"id": "c1", "organization_id": "o"},
        None,
    ])

    with patch("routes.crm_stakeholders.db", fake_db), pytest.raises(HTTPException) as exc:
        _run(update_contact_miller_heiman(
            contact_id="c1",
            data={"reports_to_id": "c-outside"},
            user={"id": "u", "organization_id": "o", "role": "admin"},
        ))
    assert exc.value.status_code == 404
    assert "reports_to_id" in exc.value.detail


# ─── 3. Frontend wiring ──────────────────────────────────────────


def test_contacts_strategic_tab_added():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMContacts.js"
    ).read_text())
    # Tab definition present in the tabs array
    assert "'overview', 'strategic'" in src
    assert 'data-testid={`contact-tab-${id}`}' in src
    # Panel component is wired up
    assert "<StrategicSellingPanel" in src
    assert "function StrategicSellingPanel" in src


def test_strategic_panel_calls_catalogue_and_patch_endpoints():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMContacts.js"
    ).read_text())
    assert "/crm/stakeholders/miller-heiman-catalogues" in src
    assert "/crm/contacts/${contact.id}/miller-heiman" in src
    # PATCH method, not PUT
    assert "axios.patch(" in src


def test_strategic_panel_renders_all_five_field_controls():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMContacts.js"
    ).read_text())
    # Pills + select + textarea + save button — every input has a testid
    assert 'data-testid="mh-coverage-row"' in src
    assert 'data-testid="mh-sentiment-row"' in src
    assert 'data-testid="mh-influence-row"' in src
    assert 'data-testid="mh-reports-to-select"' in src
    assert 'data-testid="mh-personal-wins"' in src
    assert 'data-testid="mh-save-btn"' in src


def test_contact_header_shows_strategic_badges():
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMContacts.js"
    ).read_text()
    assert 'data-testid="contact-header-sentiment-badge"' in src
    assert 'data-testid="contact-header-influence-badge"' in src
    # Badges are guarded — only show when set
    assert "contact.adoption_sentiment && (" in src
    assert "contact.buying_influence_level && (" in src


# ─── 4. Backend create_contact + get_contact extensions ──────────


def test_create_contact_accepts_miller_heiman_fields():
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    create_block = src.split('@router.post("/contacts")')[1].split('@router')[0]
    # Each new field is persisted onto the contact doc
    for f in ("buying_influence_level", "adoption_sentiment", "coverage_confidence", "reports_to_id", "personal_wins"):
        assert f in create_block, f"create_contact must persist `{f}`"
    # Uses the shared validator
    assert "_validate_miller_heiman" in create_block


def test_get_contact_hydrates_reports_to_link():
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    get_block = src.split('@router.get("/contacts/{contact_id}")')[1].split('@router')[0]
    assert "reports_to_id" in get_block
    assert '"reports_to"' in get_block
    # Cross-org safety — query joined by `_of(user)`
    assert "**of" in get_block


# ─── 5. Backwards compatibility ──────────────────────────────────


def test_legacy_influence_types_still_work():
    """h223 multi-tag field must stay reachable — h270 only extends,
    doesn't replace."""
    from routes.crm_stakeholders import _validate_types

    out = _validate_types(["champion", "economic_buyer"])
    assert "champion" in out
    assert "economic_buyer" in out


def test_legacy_booleans_still_derived():
    from routes.crm_stakeholders import _derive_legacy_booleans

    flags = _derive_legacy_booleans(["champion", "decision_maker"])
    assert flags == {"is_decision_maker": True, "is_champion": True}
