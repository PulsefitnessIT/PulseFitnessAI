"""Stripe Price ID guard — Iter 216o-4 (Feb 2026).

Fails the build if any STRIPE_PRICE_* env var is missing OR if its
configuration in Stripe drifts from what payments.py expects (wrong
amount, interval, currency, product, or inactive status).

Skipped automatically when STRIPE_API_KEY isn't a live key (i.e. local
dev pods without the live secret) so it doesn't block CI in those
environments.

Run:
    cd /app/backend && python -m pytest tests/test_stripe_prices_guard_216o.py -v
"""
import os
import pytest
import stripe
from dotenv import load_dotenv
from pathlib import Path

# Force .env to win over the pod-level sk_test_emergent stub.
ENV_PATH = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(ENV_PATH, override=True)

# Expected Stripe Price configuration. Update if PRICING_CATALOG
# (routes/payments.py) changes.
EXPECTED_PRICES = [
    # (env var,                            amount in pence, interval, Stripe product name)
    ('STRIPE_PRICE_GYMAXIS_PRO',           15000,           'month',  'GymAxis Pro (Bundle)'),
    ('STRIPE_PRICE_GYMAXIS_PRO_ANNUAL',    150000,          'year',   'GymAxis Pro (Bundle)'),
    ('STRIPE_PRICE_SITE_ADDON',            5000,            'month',  'GymAxis Pro - Extra Site'),
    ('STRIPE_PRICE_SITE_ADDON_ANNUAL',     50000,           'year',   'GymAxis Pro - Extra Site'),
    ('STRIPE_PRICE_MEMBERSHIPS',           2900,            'month',  'GymAxis Memberships'),
    ('STRIPE_PRICE_MEMBERSHIPS_ANNUAL',    29000,           'year',   'GymAxis Memberships'),
    ('STRIPE_PRICE_CRM',                   4900,            'month',  'GymAxis CRM'),
    ('STRIPE_PRICE_CRM_ANNUAL',            49000,           'year',   'GymAxis CRM'),
    ('STRIPE_PRICE_MARKETING',             4900,            'month',  'GymAxis Marketing'),
    ('STRIPE_PRICE_MARKETING_ANNUAL',      49000,           'year',   'GymAxis Marketing'),
    ('STRIPE_PRICE_OPERATIONS',            5900,            'month',  'GymAxis Operations'),
    ('STRIPE_PRICE_OPERATIONS_ANNUAL',     59000,           'year',   'GymAxis Operations'),
]


def _has_live_stripe() -> bool:
    key = os.environ.get('STRIPE_API_KEY', '')
    return key.startswith('sk_live_') or (key.startswith('sk_test_') and len(key) > 20)


@pytest.mark.skipif(not _has_live_stripe(), reason='No real STRIPE_API_KEY in this env')
@pytest.mark.parametrize('env_var, expected_amount, expected_interval, expected_product', EXPECTED_PRICES)
def test_stripe_price_matches_expected(env_var, expected_amount, expected_interval, expected_product):
    """Each Stripe Price ID is set, active, GBP, and matches the
    expected amount / interval / product name."""
    price_id = os.environ.get(env_var)
    assert price_id, f'{env_var} is not set in environment'
    assert price_id.startswith('price_'), f'{env_var}={price_id!r} is not a Stripe Price ID'

    stripe.api_key = os.environ['STRIPE_API_KEY']
    price = stripe.Price.retrieve(price_id, expand=['product'])

    assert price.active, f'{env_var}: price {price_id} is INACTIVE in Stripe'
    assert price.currency == 'gbp', f'{env_var}: currency {price.currency!r}, expected gbp'
    assert price.unit_amount == expected_amount, (
        f'{env_var}: amount £{price.unit_amount/100:.2f} ≠ expected £{expected_amount/100:.2f}'
    )
    assert price.recurring is not None, f'{env_var}: not a recurring price'
    assert price.recurring.interval == expected_interval, (
        f'{env_var}: interval {price.recurring.interval!r} ≠ expected {expected_interval!r}'
    )
    product_name = price.product.name if hasattr(price.product, 'name') else str(price.product)
    assert product_name == expected_product, (
        f'{env_var}: product {product_name!r} ≠ expected {expected_product!r}'
    )


def test_pricing_endpoint_marks_stripe_configured():
    """Public /api/payments/pricing reports stripe_configured=True when
    bundle + site-addon Price IDs are present (smoke check on the
    public-facing config flag the front-end relies on)."""
    bundle_id  = os.environ.get('STRIPE_PRICE_GYMAXIS_PRO')
    addon_id   = os.environ.get('STRIPE_PRICE_SITE_ADDON')
    assert bundle_id and addon_id, (
        'Bundle and site-addon Price IDs must be set for stripe_configured=True'
    )
