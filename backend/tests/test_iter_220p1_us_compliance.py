"""Iter 220p1 — US engineer compliance (USA readiness, slice 8).

The required compliance doc set follows the engineer's market:
  UK → DBS / RTW / Safeguarding / Public liability
  US → Work authorization (I-9) / Background check / Public liability
and the job-claim gate unlocks on the market's identity docs
(UK: DBS or RTW ; US: work authorization or background check).
"""
from datetime import datetime, timezone, timedelta


def test_required_doc_kinds_per_market():
    from utils.partner_compliance_docs import required_doc_kinds
    gb = required_doc_kinds("GB")
    us = required_doc_kinds("US")
    assert set(gb) == {"dbs", "rtw", "safeguarding", "public_liability"}
    assert set(us) == {"work_authorization", "background_check", "public_liability"}
    # Unknown / missing ⇒ UK default (back-compat).
    assert required_doc_kinds(None) == gb
    assert required_doc_kinds("ZZ") == gb


def test_validate_kind_accepts_us_kinds():
    from utils.partner_compliance_docs import validate_kind
    for k in ("work_authorization", "background_check", "dbs", "rtw"):
        assert validate_kind(k) == k


def test_overall_status_us_counts_only_us_docs():
    from utils.partner_compliance_docs import overall_status
    now = datetime.now(timezone.utc)
    docs = {
        # A US engineer who's uploaded + had verified their 3 US docs.
        "work_authorization": {"file": "x", "verified_at": now},
        "background_check": {"file": "x", "verified_at": now},
        "public_liability": {"file": "x", "verified_at": now},
        # A stray UK doc must NOT count toward the US total.
        "dbs": {"file": "x", "verified_at": now},
    }
    st = overall_status(docs, "US")
    assert st["total"] == 3
    assert st["verified_count"] == 3
    assert st["complete"] is True


def test_overall_status_us_incomplete_with_uk_docs_only():
    from utils.partner_compliance_docs import overall_status
    now = datetime.now(timezone.utc)
    docs = {"dbs": {"file": "x", "verified_at": now}, "rtw": {"file": "x", "verified_at": now}}
    st = overall_status(docs, "US")
    assert st["total"] == 3
    assert st["verified_count"] == 0  # UK docs don't satisfy US requirements
    assert st["complete"] is False


def test_overall_status_expiry_blocks():
    from utils.partner_compliance_docs import overall_status
    past = datetime.now(timezone.utc) - timedelta(days=2)
    docs = {"work_authorization": {"file": "x", "expires_at": past}}
    assert overall_status(docs, "US")["blocked"] is True


def test_claim_required_kinds_per_market():
    from routes.partners import _claim_required_kinds
    assert set(_claim_required_kinds("GB")) == {"dbs", "rtw"}
    assert set(_claim_required_kinds("US")) == {"work_authorization", "background_check"}
    assert set(_claim_required_kinds(None)) == {"dbs", "rtw"}


def test_has_valid_claim_doc_us():
    from routes.partners import _has_valid_claim_doc, _claim_required_kinds
    future = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    partner = {"compliance_docs": {"work_authorization": {"file": "x", "expires_at": future}}}
    assert _has_valid_claim_doc(partner, _claim_required_kinds("US")) is True
    # A UK doc does NOT unlock claiming for a US engineer.
    partner_uk = {"compliance_docs": {"dbs": {"file": "x", "expires_at": future}}}
    assert _has_valid_claim_doc(partner_uk, _claim_required_kinds("US")) is False
