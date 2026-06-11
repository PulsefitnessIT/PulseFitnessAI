"""Iter 237 — Production fixes for the Pulse Operations dashboard.

User reports:
1. "The Pulse · today" hero card repeated at the top of EVERY Operations
   tab + a duplicate "Gym Health Score" panel on the Dashboard tab.
   → Card now lives ONLY inside the Dashboard tab (single surface).
2. Light-mode leakage in dark mode (white card / hardcoded text-white).
   → PulseScoreCard + Recent Faults now use --theme-* variables.
3. Pulse Master Admin lost the site switcher (Pulse Fitness HQ /
   iGym Carshalton / iGym Congleton).
   → Frontend gate + backend /api/sites privileged-roles widened.
4. FR/DE language dead once logged in (dashboard fully hardcoded).
   → Tabs / header / KPI labels wired to i18n.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

FRONTEND = "/app/frontend/src"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_pulse_master_admin_sees_all_org_sites():
    """The pulse_master_admin role is privileged on /api/sites — they must
    get every (non-archived) site in their org, ignoring allowed_site_ids."""
    s = _login("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")
    r = s.get(f"{BASE_URL}/api/sites", timeout=30)
    assert r.status_code == 200, r.text
    sites = r.json().get("sites", [])
    assert len(sites) >= 2, (
        f"Pulse Master Admin must see the org's full site list (got {len(sites)}) "
        "— the SiteSwitcher hides itself below 2 sites"
    )


def test_sites_privileged_roles_source_pin():
    src = open("/app/backend/routes/sites.py", encoding="utf-8").read()
    assert '"pulse_master_admin"' in src
    assert 'user.get("is_pulse_admin")' in src


def test_pulse_card_only_on_dashboard_tab():
    """Source pins — the hero card must NOT render above the tab strip in
    LiteDashboardPage; it must render inside LiteOverviewTab, and the old
    duplicate 'Gym Health Score' panel must be gone."""
    page = open(f"{FRONTEND}/pages/LiteDashboardPage.js", encoding="utf-8").read()
    assert "<PulseScoreCard" not in page, (
        "PulseScoreCard must no longer be rendered above the Operations tabs"
    )
    overview = open(f"{FRONTEND}/pages/LiteDashboard/LiteOverviewTab.js", encoding="utf-8").read()
    assert "<PulseScoreCard" in overview, "Hero card must live in the Dashboard tab"
    assert "Gym Health Score</h3>" not in overview, (
        "The duplicate 'Gym Health Score' panel must be removed"
    )


def test_site_switcher_gate_includes_pulse_admin():
    page = open(f"{FRONTEND}/pages/LiteDashboardPage.js", encoding="utf-8").read()
    assert "user?.is_pulse_admin || user?.role === 'pulse_master_admin'" in page, (
        "Pulse Master Admins must pass the SiteSwitcher visibility gate"
    )


def test_pulse_card_dark_mode_theme_vars():
    """No hardcoded light surfaces left in the hero card."""
    card = open(f"{FRONTEND}/components/PulseScoreCard.js", encoding="utf-8").read()
    for leak in ("bg-white", "#E2E8F0", "text-slate-900", "from-[#F0F9FF]"):
        assert leak not in card, f"light-mode leak in PulseScoreCard: {leak}"
    assert "var(--theme-surface)" in card and "var(--theme-border)" in card


def test_dashboard_i18n_wired():
    """Tab labels + welcome line consume i18n; fr/de locales carry the keys."""
    import json
    page = open(f"{FRONTEND}/pages/LiteDashboardPage.js", encoding="utf-8").read()
    assert "t('dashboard.overview'" in page
    assert "t('dashboard.faults'" in page
    assert "t('dashboard.welcome'" in page
    for lang in ("fr", "de"):
        d = json.load(open(f"{FRONTEND}/i18n/locales/{lang}.json"))
        dash = d.get("dashboard", {})
        for key in ("overview", "faults", "equipment", "check_sheets", "welcome",
                    "ai_diagnosis", "gym_floor", "recent_faults", "pulse_desc_tap"):
            assert key in dash, f"{lang}.json missing dashboard.{key}"
