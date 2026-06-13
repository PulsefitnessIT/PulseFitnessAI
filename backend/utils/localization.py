"""Org localization foundation (Iter 220p1 — USA readiness, slice 1).

Single source of truth for an organization's country / currency / timezone
and the tax vocabulary that goes with it. Everything defaults to the United
Kingdom so existing customers see no behavioural change; new markets (USA
first) are unlocked purely by setting an org's ``country_code``.

The org carries three optional localization fields (all independent of the
free-text postal ``country`` address field):
  - ``country_code``  ISO-3166 alpha-2 (e.g. "GB", "US"). Drives the defaults.
  - ``currency``      ISO-4217 (e.g. "GBP", "USD"). Overrides the country default.
  - ``timezone``      IANA tz (e.g. "Europe/London"). Overrides the country default.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_COUNTRY = "GB"

# Curated set of supported markets. USA is the immediate target; the rest are
# common English-speaking / EU markets so the dropdown isn't UK+US only.
COUNTRY_CONFIG: dict[str, dict] = {
    "GB": {
        "name": "United Kingdom", "currency": "GBP", "timezone": "Europe/London",
        "tax_label": "VAT", "default_tax_rate": 20.0, "locale": "en-GB",
        "payment_method": "BACS",
    },
    "US": {
        "name": "United States", "currency": "USD", "timezone": "America/New_York",
        "tax_label": "Sales Tax", "default_tax_rate": 0.0, "locale": "en-US",
        "payment_method": "ACH",
    },
    "IE": {
        "name": "Ireland", "currency": "EUR", "timezone": "Europe/Dublin",
        "tax_label": "VAT", "default_tax_rate": 23.0, "locale": "en-IE",
        "payment_method": "SEPA",
    },
    "CA": {
        "name": "Canada", "currency": "CAD", "timezone": "America/Toronto",
        "tax_label": "Sales Tax", "default_tax_rate": 0.0, "locale": "en-CA",
        "payment_method": "ACH",
    },
    "AU": {
        "name": "Australia", "currency": "AUD", "timezone": "Australia/Sydney",
        "tax_label": "GST", "default_tax_rate": 10.0, "locale": "en-AU",
        "payment_method": "Bank transfer",
    },
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "GBP": "£", "USD": "$", "EUR": "€", "CAD": "C$", "AUD": "A$",
}

# A handful of common IANA zones offered per country so the UI can present a
# sensible picker (US in particular spans several).
COUNTRY_TIMEZONES: dict[str, list[str]] = {
    "GB": ["Europe/London"],
    "US": [
        "America/New_York", "America/Chicago", "America/Denver",
        "America/Phoenix", "America/Los_Angeles", "America/Anchorage",
        "Pacific/Honolulu",
    ],
    "IE": ["Europe/Dublin"],
    "CA": [
        "America/Toronto", "America/Winnipeg", "America/Edmonton",
        "America/Vancouver", "America/Halifax",
    ],
    "AU": [
        "Australia/Sydney", "Australia/Brisbane", "Australia/Adelaide",
        "Australia/Perth",
    ],
}


def country_config(code: Optional[str]) -> dict:
    """Return the config block for a country code, defaulting to GB."""
    return COUNTRY_CONFIG.get((code or "").strip().upper(), COUNTRY_CONFIG[DEFAULT_COUNTRY])


def currency_symbol(currency: Optional[str]) -> str:
    return CURRENCY_SYMBOLS.get((currency or "").strip().upper(), (currency or "").strip().upper() or "£")


def org_localization(org: Optional[dict]) -> dict:
    """Resolve an org's effective localization.

    Reads ``country_code`` (default GB), then layers any explicit ``currency``
    / ``timezone`` overrides on top of the country defaults. Always returns a
    fully-populated dict so callers never need to guard for missing keys.
    """
    org = org or {}
    code = (org.get("country_code") or DEFAULT_COUNTRY).strip().upper()
    cfg = country_config(code)
    currency = (org.get("currency") or cfg["currency"]).strip().upper()
    timezone = (org.get("timezone") or cfg["timezone"]).strip()
    return {
        "country_code": code,
        "country_name": cfg["name"],
        "currency": currency,
        "currency_symbol": currency_symbol(currency),
        "timezone": timezone,
        "tax_label": cfg["tax_label"],
        "default_tax_rate": cfg["default_tax_rate"],
        "locale": cfg["locale"],
        "payment_method": cfg["payment_method"],
    }


async def engineer_localization(user: Optional[dict]) -> dict:
    """Iter 265 — USA readiness for INDEPENDENT engineers.

    Independent partner engineers are created org-less (``organization_id`` is
    ``None``), so the org-based ``org_localization`` always fell back to GB —
    a US engineer's invoices rendered in £ and Stripe/compliance defaulted to
    the UK. This resolver layers a partner-record fallback:

      1. An explicit org ``country_code`` / ``currency`` wins (gym-employed
         engineers, master admins viewing the desk).
      2. Else the engineer's market chosen at signup, stored on
         ``partner_engineers.country_code``.
      3. Else GB (back-compat default).
    """
    user = user or {}
    from utils.database import db
    org = None
    org_id = user.get("organization_id") or user.get("service_org_id")
    if org_id:
        org = await db.organizations.find_one(
            {"id": org_id},
            {"_id": 0, "country_code": 1, "currency": 1, "timezone": 1},
        )
        if org and (org.get("country_code") or org.get("currency")):
            return org_localization(org)
    uid = user.get("id")
    if uid:
        partner = await db.partner_engineers.find_one(
            {"user_id": uid}, {"_id": 0, "country_code": 1},
        )
        if partner and partner.get("country_code"):
            return org_localization({"country_code": partner["country_code"]})
    return org_localization(org)


async def get_org_timezone(organization_id: Optional[str]) -> str:
    """Iter 220p1 — resolve an org's effective IANA timezone (UK default).
    Centralised so scheduling/notifications/reminders all fire on the org's
    local clock instead of a hard-coded Europe/London."""
    if not organization_id:
        return COUNTRY_CONFIG[DEFAULT_COUNTRY]["timezone"]
    from utils.database import db
    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "country_code": 1, "currency": 1, "timezone": 1},
    )
    return org_localization(org)["timezone"]



def format_currency(amount: float, currency: Optional[str]) -> str:
    """Backend money formatter for PDFs / emails. Symbol-prefixed, 2dp."""
    sym = currency_symbol(currency)
    try:
        return f"{sym}{float(amount or 0):,.2f}"
    except (TypeError, ValueError):
        return f"{sym}0.00"


def resolve_org_fields(country_code=None, currency=None, timezone=None) -> dict:
    """Iter 220p1 — normalise a (country_code, currency, timezone) triple into
    the org fields to persist. A country drives currency + timezone defaults;
    explicit currency/timezone override. Defaults to GB. Used at signup and
    master-admin org creation so both paths localize identically."""
    code = (country_code or "").strip().upper()
    if not code or code not in COUNTRY_CONFIG:
        code = DEFAULT_COUNTRY
    cfg = country_config(code)
    cur = (currency or cfg["currency"]).strip().upper()
    if cur not in CURRENCY_SYMBOLS:
        cur = cfg["currency"]
    tz = (timezone or cfg["timezone"]).strip()
    return {"country_code": code, "currency": cur, "timezone": tz}



def supported_countries() -> list[dict]:
    """List for the settings dropdown: code, name, default currency/tz, symbol."""
    out = []
    for code, cfg in COUNTRY_CONFIG.items():
        out.append({
            "code": code,
            "name": cfg["name"],
            "currency": cfg["currency"],
            "currency_symbol": currency_symbol(cfg["currency"]),
            "timezone": cfg["timezone"],
            "timezones": COUNTRY_TIMEZONES.get(code, [cfg["timezone"]]),
            "tax_label": cfg["tax_label"],
            "default_tax_rate": cfg["default_tax_rate"],
        })
    return out
