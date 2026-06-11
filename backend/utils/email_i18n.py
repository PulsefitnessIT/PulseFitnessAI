"""Iter 239 — Email localization helper.

Per-user `language` (set from the Navbar globe, stored on the user doc)
drives which language platform emails are sent in. AI-generated content
(digest headline/narrative) stays in its source language; this module
translates the email *chrome* (subjects, section labels, footers).
"""
from __future__ import annotations

SUPPORTED_LANGS = {"en", "fr", "de"}


def user_lang(user_doc: dict | None) -> str:
    """Resolve a user doc to a supported email language (default en)."""
    lang = ((user_doc or {}).get("language") or "en").lower()[:2]
    return lang if lang in SUPPORTED_LANGS else "en"


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "weekly_brief": "Weekly brief",
        "digest_subject": "GymAxis weekly brief",
        "key_metrics": "Key metrics",
        "recommended_actions": "Recommended actions",
        "top_at_risk": "Top 5 at-risk members",
        "no_at_risk": "No at-risk members flagged this week — nice.",
        "jump_back": "Jump back into the analytics dashboard:",
        "digest_footer": "GymAxis Memberships · Autopilot digest · Full PDF attached",
        "kpi_active_members": "Active members",
        "kpi_net_growth": "Net growth",
        "kpi_churn": "Churn %",
        "kpi_occupancy": "Occupancy",
        "kpi_revenue_week": "Revenue (week)",
    },
    "fr": {
        "weekly_brief": "Synthèse hebdomadaire",
        "digest_subject": "Synthèse hebdomadaire GymAxis",
        "key_metrics": "Indicateurs clés",
        "recommended_actions": "Actions recommandées",
        "top_at_risk": "Top 5 des adhérents à risque",
        "no_at_risk": "Aucun adhérent à risque signalé cette semaine — parfait.",
        "jump_back": "Retournez sur le tableau de bord analytique :",
        "digest_footer": "GymAxis Abonnements · Synthèse Autopilot · PDF complet en pièce jointe",
        "kpi_active_members": "Adhérents actifs",
        "kpi_net_growth": "Croissance nette",
        "kpi_churn": "Attrition %",
        "kpi_occupancy": "Taux d'occupation",
        "kpi_revenue_week": "Revenus (semaine)",
    },
    "de": {
        "weekly_brief": "Wochenbericht",
        "digest_subject": "GymAxis Wochenbericht",
        "key_metrics": "Kennzahlen",
        "recommended_actions": "Empfohlene Maßnahmen",
        "top_at_risk": "Top 5 gefährdete Mitglieder",
        "no_at_risk": "Diese Woche keine gefährdeten Mitglieder — super.",
        "jump_back": "Zurück zum Analyse-Dashboard:",
        "digest_footer": "GymAxis Mitgliedschaften · Autopilot-Bericht · Vollständiges PDF im Anhang",
        "kpi_active_members": "Aktive Mitglieder",
        "kpi_net_growth": "Nettowachstum",
        "kpi_churn": "Abwanderung %",
        "kpi_occupancy": "Auslastung",
        "kpi_revenue_week": "Umsatz (Woche)",
    },
}


def tr(lang: str, key: str) -> str:
    """Translate an email-chrome key; falls back to English, then the key."""
    lang = lang if lang in SUPPORTED_LANGS else "en"
    return _STRINGS[lang].get(key) or _STRINGS["en"].get(key) or key
