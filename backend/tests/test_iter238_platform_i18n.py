"""Iter 238 — FR/DE translation extended through the Operations module.

Continues the iter-237 i18n work across: ModuleSwitcher, SiteSwitcher,
Equipment tab, Faults tab (incl. filters + severity labels), Documents
tab and the Log-a-Fault wizard (LiteDialogs).
"""

import json

FRONTEND = "/app/frontend/src"

WIRED_FILES = {
    f"{FRONTEND}/components/shared/ModuleSwitcher.js": ["t(`modules.${m.id}`"],
    f"{FRONTEND}/components/shared/SiteSwitcher.js": ["t('sites.all_sites'", "t('sites.switch_site'"],
    f"{FRONTEND}/pages/LiteDashboard/LiteEquipmentTab.js": ["t('equip.search'", "t('equip.add'", "t('equip.under_warranty'"],
    f"{FRONTEND}/pages/LiteDashboard/LiteFaultsTab.js": ["t('faults.reactive'", "t('faults.log_new'", "t('severity.operational_minor'", "t('status.all_statuses'"],
    f"{FRONTEND}/pages/LiteDashboard/LiteDocumentsTab.js": ["t('docs.subtitle'", "t('docs.drop_files'", "docs.cat_"],
    f"{FRONTEND}/pages/LiteDashboard/LiteDialogs.js": ["t('dashboard.log_fault'", "t('dialog.severity'", "t(`severity.${sev.value}`", "t('dialog.submit_fault_report'"],
    f"{FRONTEND}/pages/LiteDashboard/OperationsStartTab.js": ["t('ops_start.title'", "t(`ops_start.${o.k}_title`"],
    f"{FRONTEND}/components/shared/ActivationMilestonesCard.js": ["t('activation.title'", "t(`activation.${m.event_type}`"],
    f"{FRONTEND}/components/shared/Navbar.js": ["t('nav.help_tutorials'", "t('nav.take_tour'"],
}


def test_operations_components_consume_i18n():
    for path, pins in WIRED_FILES.items():
        src = open(path, encoding="utf-8").read()
        for pin in pins:
            assert pin in src, f"{path} lost i18n wiring: {pin}"


def test_severity_label_helper_translates():
    src = open(f"{FRONTEND}/pages/LiteDashboardPage.js", encoding="utf-8").read()
    assert "i18n.t(`severity.${key}`" in src, "getSeverityLabel must resolve via i18n"


def test_locales_carry_all_new_groups():
    required = {
        "modules": ["operations", "memberships", "crm", "marketing"],
        "sites": ["all_sites", "pick_site", "switch_site"],
        "status": ["all_statuses", "open", "in_progress", "resolved", "closed"],
        "severity": ["operational_minor", "out_of_order", "safety_critical",
                     "operational_minor_desc", "safety_critical_desc"],
        "equip": ["search", "add", "under_warranty", "chargeable", "no_equipment"],
        "faults": ["reactive", "ppm", "log_new", "multi_job", "empty_title"],
        "docs": ["subtitle", "drop_files", "cat_manuals", "cat_invoices"],
        "dialog": ["machine_type", "issue_description", "severity",
                   "submit_fault_report", "i_fixed_it", "cancel"],
    }
    for lang in ("en", "fr", "de"):
        d = json.load(open(f"{FRONTEND}/i18n/locales/{lang}.json"))
        for group, keys in required.items():
            assert group in d, f"{lang}.json missing group {group}"
            for k in keys:
                assert k in d[group], f"{lang}.json missing {group}.{k}"


def test_fr_de_values_actually_translated():
    """Guard against copy-paste English into fr/de."""
    fr = json.load(open(f"{FRONTEND}/i18n/locales/fr.json"))
    de = json.load(open(f"{FRONTEND}/i18n/locales/de.json"))
    assert fr["faults"]["log_new"] != "Log New Fault"
    assert fr["severity"]["out_of_order"] == "Hors service"
    assert de["faults"]["log_new"] != "Log New Fault"
    assert de["severity"]["out_of_order"] == "Außer Betrieb"
