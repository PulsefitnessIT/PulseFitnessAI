"""Stripe product/price catalog.

Resolves (module, currency, billing_cycle) -> Stripe price_id by reading the
live Stripe account, cached in-process. Lets us sell every module in
GBP/EUR/USD, monthly/annual, without hard-coding 30 price IDs in .env.

Products are matched by their Stripe Product *name* (created in the dashboard).
"""
import time
import logging
import stripe

from utils.database import STRIPE_API_KEY

logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_API_KEY

# Internal module id -> the Stripe Product name the customer created.
MODULE_PRODUCT_NAMES = {
    "operations": "Operations",
    "crm": "CRM",
    "marketing": "Marketing",
    "memberships": "Memberships",
    "site_addon": "Operations Extra Site",
}

SUPPORTED_CURRENCIES = ("gbp", "eur", "usd")
CURRENCY_SYMBOLS = {"gbp": "£", "eur": "€", "usd": "$"}

_CACHE: dict = {"at": 0.0, "data": None}
_TTL = 600  # seconds


def _build() -> dict:
    name_to_module = {v.lower(): k for k, v in MODULE_PRODUCT_NAMES.items()}
    products = {p.id: p for p in stripe.Product.list(active=True, limit=100).auto_paging_iter()}
    catalog: dict = {m: {} for m in MODULE_PRODUCT_NAMES}
    for pr in stripe.Price.list(active=True, limit=100).auto_paging_iter():
        prod = products.get(pr.product)
        if not prod or not pr.recurring:
            continue
        module = name_to_module.get((prod.name or "").lower())
        if not module:
            continue
        ccy = (pr.currency or "").lower()
        interval = pr.recurring.get("interval")  # "month" | "year"
        if ccy not in SUPPORTED_CURRENCIES or interval not in ("month", "year"):
            continue
        catalog[module].setdefault(ccy, {})[interval] = {
            "price_id": pr.id,
            "unit_amount": pr.unit_amount,
            "currency": ccy,
        }
    return catalog


def get_catalog(force: bool = False) -> dict:
    now = time.time()
    if force or not _CACHE["data"] or now - _CACHE["at"] > _TTL:
        try:
            _CACHE["data"] = _build()
            _CACHE["at"] = now
        except Exception:
            logger.exception("[stripe_catalog] build failed")
            if _CACHE["data"] is None:
                _CACHE["data"] = {}
    return _CACHE["data"]


def resolve_price_id(module: str, currency: str = "gbp", billing_cycle: str = "monthly"):
    """Return (price_id, currency) for a module, falling back to GBP / monthly."""
    currency = (currency or "gbp").lower()
    if currency not in SUPPORTED_CURRENCIES:
        currency = "gbp"
    interval = "year" if str(billing_cycle).lower() in ("annual", "year", "yearly") else "month"
    cat = get_catalog().get(module, {})
    for ccy in (currency, "gbp"):
        node = cat.get(ccy, {})
        for itv in (interval, "month"):
            if itv in node:
                return node[itv]["price_id"], node[itv]["currency"]
    return None, None


def pricing_summary() -> dict:
    """Per-module, per-currency monthly/annual amounts for the pricing UI."""
    cat = get_catalog()
    out: dict = {}
    for module, by_ccy in cat.items():
        out[module] = {}
        for ccy, intervals in by_ccy.items():
            out[module][ccy] = {
                "symbol": CURRENCY_SYMBOLS.get(ccy, ""),
                "monthly": (intervals.get("month") or {}).get("unit_amount"),
                "annual": (intervals.get("year") or {}).get("unit_amount"),
            }
    return out
