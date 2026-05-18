"""
Iter 216h189 — Server-side `q` filter on `GET /master-admin/organizations`.

Before this iteration the Master Admin Orgs page fetched ALL orgs
(up to 2000) on every load and filtered client-side. With 1000+ orgs
that's ~3-5 MB on every refresh / keystroke. The new `q` query
parameter pushes the text-match into Mongo so the wire payload shrinks
to just the matching rows.

Live integration tests — hit the running server and assert:
  1. No `q` → all orgs (capped at 2000).
  2. `q=pulse` → only orgs whose name / contact fields match.
  3. `q=zzqqxx` → empty list.
  4. `q=a` (single char) → guard skips the filter, full list returned.
  5. `q=PULSE` (uppercase) → case-insensitive match returns the same
     set as `q=pulse`.
  6. `q` does NOT break the older `?brand=` filter (composes cleanly).
"""
import os
import requests


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = 'admin@gymaxisai.com'
ADMIN_PW = 'MasterAdmin123!'


def _token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15,
    )
    r.raise_for_status()
    j = r.json()
    return j.get('token') or j.get('access_token')


def _orgs(token: str, **params) -> list:
    r = requests.get(
        f"{BASE_URL}/api/master-admin/organizations",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get('organizations') or []


def test_baseline_returns_full_list():
    tok = _token()
    orgs = _orgs(tok)
    # We expect more than a handful — every test env has at least the
    # seed orgs + a few Pulse sites.
    assert len(orgs) >= 5, f"baseline returned only {len(orgs)} orgs"


def test_q_pulse_narrows_results():
    tok = _token()
    full = _orgs(tok)
    pulse = _orgs(tok, q="pulse")
    # Strict subset, strictly smaller.
    assert 0 < len(pulse) < len(full), (
        f"q=pulse should be strictly smaller than baseline "
        f"(got {len(pulse)} vs {len(full)})"
    )
    # Every returned org should match the term in one of the searched
    # fields. We don't pin the exact field but at least one of them
    # must contain "pulse" case-insensitively.
    for o in pulse:
        haystack = " ".join([
            str(o.get('name') or ''),
            str(o.get('email') or ''),
            str(o.get('primary_contact_email') or ''),
            str(o.get('primary_contact_name') or ''),
            str(o.get('company_code') or ''),
        ]).lower()
        assert 'pulse' in haystack, f"row {o.get('id')} does not match 'pulse': {o.get('name')}"


def test_q_uppercase_is_case_insensitive():
    tok = _token()
    lower = _orgs(tok, q="pulse")
    upper = _orgs(tok, q="PULSE")
    # Same row count — case shouldn't change the result set.
    assert len(lower) == len(upper), (
        f"case-insensitivity broke: lower={len(lower)} vs upper={len(upper)}"
    )


def test_q_no_match_returns_empty():
    tok = _token()
    rows = _orgs(tok, q="zzqqxxnopossiblematch12345")
    assert rows == [], f"expected empty list, got {len(rows)}"


def test_q_single_char_skips_filter():
    """Soft guard: 1-char queries are explicitly NOT filtered so we
    don't slam Mongo with a near-table-scan regex on every keystroke."""
    tok = _token()
    full = _orgs(tok)
    rows = _orgs(tok, q="a")
    assert len(rows) == len(full), (
        f"1-char query should NOT filter (full={len(full)} vs q=a={len(rows)})"
    )


def test_q_composes_with_brand():
    """`?q=` must compose cleanly with `?brand=` — both are server-side
    filters and should AND together."""
    tok = _token()
    # Pulse brand alone
    pulse_brand = _orgs(tok, brand="pulse")
    # Pulse brand + q=fitness
    pulse_fitness = _orgs(tok, brand="pulse", q="fitness")
    # The combined filter must produce a subset of brand-only.
    assert len(pulse_fitness) <= len(pulse_brand), (
        f"q+brand should be a subset of brand alone "
        f"(got combined={len(pulse_fitness)}, brand-only={len(pulse_brand)})"
    )


def test_enriched_shape_preserved():
    """`q` is purely a filter — the enrichment pipeline
    (user_count, equipment_count, owner_email, etc.) must still run."""
    tok = _token()
    rows = _orgs(tok, q="pulse")
    assert rows, "expected at least one match for q=pulse"
    o = rows[0]
    # Spot-check the enrichment fields the frontend relies on.
    for f in ("user_count", "equipment_count", "issue_count", "open_issues",
              "owner_email", "enabled_modules", "portal_type"):
        assert f in o, f"enrichment field missing from q-filtered row: {f}"
