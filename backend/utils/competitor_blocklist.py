"""Trial-signup competitor blocklist — Iter 220ca.

Rejects trial signups from known competitor domains so they can't
casually create an account, snoop the dashboard, and copy our IP.

This is intentionally a static list: maintaining it in code (not the
DB) means it ships with the same CI gate as everything else and a
competitor that's reverse-engineering us can't just brute-force the
table.

The list is **not exhaustive** — it's the floor. The other anti-
abuse layers (work-email enforcement, pending-review queue,
audit-trail) sit on top.

Sourced from a mix of (a) names the founder/CEO has called out on
the Pulse Fitness call list as direct competitors, and (b) public market
mapping of the UK + global gym-software / equipment-service space.
"""
from __future__ import annotations

from typing import Optional

# Apex domains only — the matcher strips subdomains. Lower-case.
#
# Two categories — the rationale matters because the rejection
# email differs slightly ("sales has reached out" vs "demo line").
_GYM_SOFTWARE_COMPETITORS = (
    # User-named (call sheet 29 May 2026)
    "orbit4.com", "orbit4.co.uk",
    "servicesport.co.uk", "servicesport.com",
    # SaaS gym management
    "trainerize.com",
    "mindbodyonline.com", "mindbody.io", "mindbodyhq.com",
    "perfectgym.com",
    "glofox.com",
    "abcfitness.com",            # acquired Glofox; same parent
    "xplor.com", "xplortechnologies.com", "xplortechnologies.io",
    "clubright.co.uk",
    "gymmaster.com",
    "wellnessliving.com",
    "mywellness.com", "technogym.com",  # mywellness is Technogym's SaaS arm
)

_EQUIPMENT_SERVICE_COMPETITORS = (
    "fitnessfix.co.uk",
    "fitlock.co.uk",
    "gymequipmentcare.co.uk",
)

# Combined fast-lookup set — `endswith(domain)` against this.
_BLOCKED_DOMAINS = frozenset(
    _GYM_SOFTWARE_COMPETITORS + _EQUIPMENT_SERVICE_COMPETITORS,
)


def _normalise_email(email: str) -> tuple[str, str]:
    """Return (local_part, domain) — lowercased, both stripped of
    whitespace. ``domain`` is ``""`` if the email is malformed."""
    cleaned = (email or "").strip().lower()
    if "@" not in cleaned:
        return cleaned, ""
    local, _, domain = cleaned.rpartition("@")
    return local, domain.strip()


def is_competitor_email(email: str) -> bool:
    """Return ``True`` if the email's domain (or any parent of it)
    is on the competitor blocklist.

    Matching is *suffix-aware*: ``team.uk.orbit4.com`` matches
    ``orbit4.com``. We **do not** match prefixes — ``orbit4-fans.com``
    is fine.
    """
    _local, domain = _normalise_email(email)
    if not domain:
        return False
    # Walk up the domain tree:
    #     "team.uk.orbit4.com" -> ["team.uk.orbit4.com", "uk.orbit4.com",
    #     "orbit4.com", "com"]  -> match on "orbit4.com".
    parts = domain.split(".")
    for i in range(len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in _BLOCKED_DOMAINS:
            return True
    return False


def competitor_block_reason(email: str) -> Optional[str]:
    """Human-readable reason if the email is blocked, else ``None``.

    Used by the register route to drop a friendly explanation into
    the 400 response so a confused real-customer (working for a
    multi-brand parent that happens to own an old gym chain) knows
    who to talk to."""
    if not is_competitor_email(email):
        return None
    return (
        "We can't start a self-serve trial from this email domain — "
        "if you'd like a guided demo, please email "
        "sales@pulsefitness.ai and we'll get back to you within a "
        "business day."
    )


def blocked_domains() -> list[str]:
    """Read-only snapshot for the Master Admin status panel."""
    return sorted(_BLOCKED_DOMAINS)
