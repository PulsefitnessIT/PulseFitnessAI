"""Shared mapping of Stripe Connect errors → structured, actionable HTTP errors.

Stripe rejects ``Account.create(type="express")`` with opaque messages when the
platform isn't fully set up. We translate the two common blockers into stable
``code`` values + a ``help_url`` so the frontend can render a clear banner
("complete your Stripe Connect profile") instead of a raw Stripe string.
"""
from __future__ import annotations

from fastapi import HTTPException

PLATFORM_PROFILE_URL = "https://dashboard.stripe.com/settings/connect/platform-profile"
CONNECT_OVERVIEW_URL = "https://dashboard.stripe.com/connect/overview"


def stripe_connect_http_exception(exc: Exception) -> HTTPException:
    """Return an HTTPException with a structured detail for known Connect blockers."""
    raw = str(exc) or ""
    low = raw.lower()
    user_msg = getattr(exc, "user_message", None) or raw

    # Platform profile / loss-liability responsibilities not completed.
    if (
        "platform-profile" in low
        or "responsibilities of managing losses" in low
        or "review the responsibilities" in low
    ):
        return HTTPException(400, {
            "code": "stripe_connect_profile_incomplete",
            "message": (
                "Your Stripe Connect platform profile isn't finished yet. Complete it "
                "in the Stripe Dashboard — including the loss-liability / "
                "responsibilities section — to start onboarding gyms and engineers."
            ),
            "help_url": PLATFORM_PROFILE_URL,
        })

    # Connect not enabled on the platform at all.
    if "signed up for connect" in low or "enable connect" in low:
        return HTTPException(503, {
            "code": "stripe_connect_not_enabled",
            "message": (
                "Stripe Connect isn't enabled on the platform yet. Enable Connect "
                "in the Stripe Dashboard, then try again."
            ),
            "help_url": CONNECT_OVERVIEW_URL,
        })

    return HTTPException(400, f"Stripe error: {user_msg}")
