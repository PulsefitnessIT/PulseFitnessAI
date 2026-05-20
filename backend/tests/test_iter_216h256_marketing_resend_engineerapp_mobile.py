"""Iter 216h256 — Marketing surface polish + Resend domain fix + Engineer App switch + Service Desk mobile.

User feedback (Feb 20, 2026, production):
1. "Remove the See it in action button - it doesn't give a true
   representation of the platform"
2. "Speak to sales - remove these contact details - they are not real"
3. "Emails - resend emails still not working - resend is verified -
   names.co.uk dns is set up? What else could it be?"  → root cause was
   the mixed-case sender `support@GymAxisAI.com`. Resend stores the
   verified domain in lowercase per RFC 1035, so the API rejected every
   send with "domain is not verified".
4. "Service desk - mobile Optimisation"
5. "Add engineer app button to master for me to demo to potential new
   engineers"
"""
from __future__ import annotations

import pathlib
import re


def _strip_comments(src: str) -> str:
    """Strip JSX `{/* ... */}` and JS `/* ... */` // ... comments."""
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.DOTALL)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//.*", "", src)
    return src


# ─── 1. "See it in action" removed from every marketing surface ─────

def test_see_it_in_action_removed_from_marketing():
    for name in (
        "MarketingHome.js",
        "ContactMarketingPage.js",
        "ModulePage.js",
        "PricingMarketingPage.js",
    ):
        src = _strip_comments(
            pathlib.Path(f"/app/frontend/src/pages/Marketing/{name}").read_text()
        )
        assert "See it in action" not in src, (
            f"{name} still renders 'See it in action' outside comments"
        )


# ─── 2. Fake contact details gone from /contact ─────────────────────

def test_contact_page_no_fake_contact_details():
    src = _strip_comments(
        pathlib.Path(
            "/app/frontend/src/pages/Marketing/ContactMarketingPage.js"
        ).read_text()
    )
    assert "hello@gymaxisai.com" not in src
    assert "+44 20 1234 5678" not in src
    assert "London, United Kingdom" not in src


# ─── 3. Resend domain normalisation ─────────────────────────────────

def test_sender_email_env_is_lowercase():
    env = pathlib.Path("/app/backend/.env").read_text()
    # Specifically check the SENDER_EMAIL line.
    for line in env.splitlines():
        if line.startswith("SENDER_EMAIL="):
            sender = line.split("=", 1)[1].strip()
            assert "@" in sender
            domain = sender.split("@", 1)[1]
            assert domain == domain.lower(), (
                f"SENDER_EMAIL domain must be lowercase to satisfy Resend, got {domain!r}"
            )
            break
    else:
        raise AssertionError("SENDER_EMAIL line missing from backend/.env")


def test_sender_email_runtime_normalised():
    """Even if a future .env edit reintroduces a mixed-case domain, the
    runtime normaliser must keep Resend happy."""
    import importlib
    import os

    os.environ["SENDER_EMAIL"] = "support@GymAxisAI.COM"
    import utils.database as db_mod
    importlib.reload(db_mod)
    assert db_mod.SENDER_EMAIL == "support@gymaxisai.com"

    # And the helper function behaves on edge cases.
    assert db_mod._normalise_sender("") == ""
    assert db_mod._normalise_sender("invalid") == "invalid"
    # Lowercases everything after the first @, including the > suffix of
    # "Name <addr>" style values. Resend sees just the bare email so the
    # lowercase domain still matches the verified record.
    assert db_mod._normalise_sender("Display <X@Y.Z>") == "Display <X@y.z>"
    assert db_mod._normalise_sender("a@B.C") == "a@b.c"


# ─── 4. Service Desk mobile optimisation ────────────────────────────

def test_service_desk_has_mobile_drawer():
    src = pathlib.Path("/app/frontend/src/pages/ServiceDeskPage.js").read_text()
    # Hamburger trigger.
    assert 'data-testid="desk-sidebar-open"' in src
    # Drawer close button.
    assert 'data-testid="desk-sidebar-close"' in src
    # Backdrop.
    assert 'data-testid="desk-sidebar-backdrop"' in src
    # Aside no longer permanently visible — slides in via translate-x.
    assert "-translate-x-full md:translate-x-0" in src
    # Main no longer hard-pads to ml-60 on mobile.
    assert "md:ml-60" in src
    assert "p-4 sm:p-6 md:p-8" in src


# ─── 5. Engineer App switch in Master Admin sidebar ─────────────────

def test_master_admin_has_engineer_app_switch():
    src = pathlib.Path(
        "/app/frontend/src/pages/MasterAdmin/AdminSidebar.js"
    ).read_text()
    assert 'data-testid="portal-switch-engineer-app"' in src
    assert "/svc/engineer" in src
    # Visible label.
    assert "Engineer App" in src
    # HardHat icon imported.
    assert "HardHat" in src
