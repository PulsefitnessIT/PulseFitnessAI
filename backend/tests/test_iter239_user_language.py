"""Iter 239 — Per-user language preference + localized platform emails.

1. PATCH /account/profile accepts `language` (en/fr/de only).
2. /auth/me returns `language` so the frontend applies it on boot
   (preference follows the user across devices).
3. utils/email_i18n provides the chrome translations used by the
   Memberships weekly digest (per-recipient language).
"""

import sys

import requests

sys.path.insert(0, "/app/backend")

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_language_persists_and_survives_relogin():
    s = _login("owner@apexfitness.group", "ApexDemo2026!")
    try:
        r = s.patch(f"{BASE_URL}/api/account/profile", json={"language": "fr"}, timeout=20)
        assert r.status_code == 200, r.text
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=20).json()
        assert me.get("language") == "fr", me
        # Fresh session (new device) — preference must follow the user.
        s2 = _login("owner@apexfitness.group", "ApexDemo2026!")
        me2 = s2.get(f"{BASE_URL}/api/auth/me", timeout=20).json()
        assert me2.get("language") == "fr", me2
    finally:
        s.patch(f"{BASE_URL}/api/account/profile", json={"language": "en"}, timeout=20)


def test_invalid_language_rejected():
    s = _login("owner@apexfitness.group", "ApexDemo2026!")
    r = s.patch(f"{BASE_URL}/api/account/profile", json={"language": "xx"}, timeout=20)
    assert r.status_code == 400, r.text


def test_email_i18n_helper():
    from utils.email_i18n import SUPPORTED_LANGS, tr, user_lang
    assert SUPPORTED_LANGS == {"en", "fr", "de"}
    assert user_lang({"language": "fr"}) == "fr"
    assert user_lang({"language": "fr-FR"}) == "fr"
    assert user_lang({"language": "xx"}) == "en"
    assert user_lang({}) == "en" and user_lang(None) == "en"
    assert tr("fr", "weekly_brief") == "Synthèse hebdomadaire"
    assert tr("de", "digest_subject") == "GymAxis Wochenbericht"
    assert tr("xx", "weekly_brief") == "Weekly brief"  # fallback


def test_digest_html_localized_per_lang():
    from utils.memberships_digest import _build_html
    org = {"name": "Test Gym"}
    for lang, marker in (("fr", "Indicateurs clés"), ("de", "Kennzahlen"), ("en", "Key metrics")):
        html = _build_html(org, {}, {}, [], None, lang=lang)
        assert marker in html, f"{lang} digest missing {marker!r}"
    # Subject strings + per-recipient grouping are wired in the sender.
    src = open("/app/backend/utils/memberships_digest.py", encoding="utf-8").read()
    assert "user_lang(u)" in src and "tr(lang, 'digest_subject')" in src


def test_frontend_applies_and_persists_language():
    app = open("/app/frontend/src/App.js", encoding="utf-8").read()
    assert "i18n.changeLanguage(lang)" in app, "App must apply user.language on hydrate"
    nav = open("/app/frontend/src/components/shared/Navbar.js", encoding="utf-8").read()
    assert "{ language: lang.code }" in nav, "Navbar must persist the language to the profile"
