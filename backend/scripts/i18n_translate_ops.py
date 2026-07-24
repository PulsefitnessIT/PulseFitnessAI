#!/usr/bin/env python3
"""
Build-time i18n helper for the Operations Dashboards (LiteDashboard) module.

1. Scans /app/frontend/src/pages/LiteDashboard for t('key','English default') calls
   (namespaces: staffing.*, ops.*, orgchart.*).
2. For any key not already present (with a NON-English-equal value) in fr.json / de.json,
   asks Claude to translate the English default -> FR and DE.
3. Merges results into en.json (default value), fr.json, de.json.

Run: cd /app/backend && python scripts/i18n_translate_ops.py
"""
import os, re, json, asyncio, sys

FE = "/app/frontend/src"
LOCALES = os.path.join(FE, "i18n", "locales")
SCAN_DIR = os.path.join(FE, "pages", "LiteDashboard")
NAMESPACES = ("staffing", "ops", "orgchart")

# ---- 1. Extract t('key','default') pairs ----------------------------------

def read_quoted(s, i):
    """Read a JS string literal starting at s[i] (quote char). Returns (value, next_index) or (None,i)."""
    q = s[i]
    if q not in "'\"`":
        return None, i
    i += 1
    buf = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i+1]
            mp = {"n": "\n", "t": "\t", "'": "'", '"': '"', "`": "`", "\\": "\\"}
            buf.append(mp.get(nxt, nxt))
            i += 2
            continue
        if c == q:
            return "".join(buf), i + 1
        buf.append(c)
        i += 1
    return None, i

def extract_pairs(text):
    pairs = {}
    # find occurrences of t( with a namespace key
    for m in re.finditer(r"\bt\(\s*(['\"])", text):
        start = m.end() - 1  # index of the quote
        key, j = read_quoted(text, start)
        if key is None or not key.startswith(tuple(n + "." for n in NAMESPACES)):
            continue
        # skip whitespace
        while j < len(text) and text[j] in " \t\n\r":
            j += 1
        if j >= len(text) or text[j] != ",":
            continue
        j += 1
        while j < len(text) and text[j] in " \t\n\r":
            j += 1
        if j >= len(text) or text[j] not in "'\"`":
            continue
        default, _ = read_quoted(text, j)
        if default is None:
            continue
        pairs[key] = default
    return pairs

def scan():
    pairs = {}
    for root, _, files in os.walk(SCAN_DIR):
        for fn in files:
            if fn.endswith(".js") or fn.endswith(".jsx"):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    pairs.update(extract_pairs(f.read()))
    return pairs

# ---- json helpers (nested namespace: staffing -> {clock_in: ...}) ---------

def load(name):
    with open(os.path.join(LOCALES, name), encoding="utf-8") as f:
        return json.load(f)

def save(name, data):
    with open(os.path.join(LOCALES, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def get_nested(d, dotted):
    ns, _, key = dotted.partition(".")
    return d.get(ns, {}).get(key)

def set_nested(d, dotted, value):
    ns, _, key = dotted.partition(".")
    d.setdefault(ns, {})[key] = value

# ---- 2. translate via Claude ----------------------------------------------

async def translate_batch(pairs, target_lang_name):
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY") or "sk-emergent-8E60eC543A620FcAaE"
    chat = LlmChat(
        api_key=key,
        session_id=f"i18n-ops-{target_lang_name}",
        system_message=(
            f"You are a professional software UI translator. Translate the given JSON object's "
            f"English UI string VALUES into {target_lang_name}. Keep the JSON keys EXACTLY the same. "
            f"Preserve placeholders, punctuation, leading/trailing spaces, em-dashes, and symbols "
            f"(e.g. '·', '—', '£', '%', ':'). Do NOT translate brand/product names (Pulse, Sage, "
            f"Claude, CSV, PIN, NI Number, AI). Return ONLY a valid JSON object, no prose."
        ),
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    # chunk to keep prompts sane
    items = list(pairs.items())
    out = {}
    CH = 60
    for i in range(0, len(items), CH):
        chunk = dict(items[i:i+CH])
        msg = "Translate the VALUES of this JSON to " + target_lang_name + ":\n" + json.dumps(chunk, ensure_ascii=False)
        resp = await chat.send_message(UserMessage(text=msg))
        raw = resp if isinstance(resp, str) else str(resp)
        s = raw.find("{"); e = raw.rfind("}")
        try:
            parsed = json.loads(raw[s:e+1])
            out.update(parsed)
        except Exception as ex:
            print(f"  ! parse fail chunk {i}: {ex}", file=sys.stderr)
    return out

async def main():
    pairs = scan()
    # Explicit nav labels (StaffingConsole builds keys dynamically via trLabel).
    nav = {
        "staffing.nav_dashboard": "Dashboard", "staffing.nav_people": "People",
        "staffing.nav_hr": "HR", "staffing.nav_staff_onboarding": "Staff Onboarding",
        "staffing.nav_org_chart": "Org Chart", "staffing.nav_team_access": "Team Access",
        "staffing.nav_site_login": "Site Login", "staffing.nav_rota": "Rota",
        "staffing.nav_schedule": "Schedule", "staffing.nav_templates": "Templates",
        "staffing.nav_time_off": "Time Off", "staffing.nav_shift_market": "Shift Market",
        "staffing.nav_live_floor": "Live Floor", "staffing.nav_ai_rota": "AI Rota",
        "staffing.nav_time_clock": "Time Clock", "staffing.nav_team_clock": "Team Clock",
        "staffing.nav_my_clock": "My Clock", "staffing.nav_performance": "Performance",
        "staffing.nav_overview": "Overview", "staffing.nav_ai_insights": "AI Insights",
        "staffing.nav_payroll": "Payroll", "staffing.nav_expenses": "Expenses",
        "staffing.nav_comms": "Comms", "staffing.nav_announcements": "Announcements",
        "staffing.nav_handover_diary": "Handover Diary", "staffing.nav_ops_forms": "Ops · Forms",
        "staffing.nav_rules": "Rules", "staffing.nav_staff": "Staff",
        "staffing.nav_transfers": "Transfers",
    }
    pairs.update(nav)
    # Explicit orgchart dynamic keys (built via template literals in JSX — the
    # scanner only sees static t('key','default') calls, so list them here).
    orgchart_dyn = {
        # NODE_LABELS
        "orgchart.node_staff": "Staff", "orgchart.node_vacancy": "Vacancy",
        "orgchart.node_placeholder": "Placeholder", "orgchart.node_contractor": "Contractor",
        # Settings field toggles
        "orgchart.field_photo": "Avatars", "orgchart.field_department": "Department",
        "orgchart.field_site": "Site", "orgchart.field_email": "Email",
        "orgchart.field_phone": "Phone", "orgchart.field_employment_type": "Employment type",
        "orgchart.field_reports_count": "Direct reports count", "orgchart.field_status": "Status",
        # Table columns (ListView / DocumentImport / AIPanel)
        "orgchart.col_name": "Name", "orgchart.col_job_title": "Job title",
        "orgchart.col_type": "Type", "orgchart.col_department": "Department",
        "orgchart.col_site": "Site", "orgchart.col_manager": "Manager",
        "orgchart.col_reports": "Reports", "orgchart.col_status": "Status",
        "orgchart.col_linked": "Linked", "orgchart.col_reports_to": "Reports to",
        "orgchart.col_title": "Title",
        # Audit trail actions
        "orgchart.action_card_added": "Card added", "orgchart.action_card_edited": "Card edited",
        "orgchart.action_card_removed": "Card removed", "orgchart.action_reporting_changed": "Reporting line changed",
        "orgchart.action_import": "Import", "orgchart.action_template_applied": "Template applied",
        "orgchart.action_version_saved": "Version saved", "orgchart.action_version_restored": "Version restored",
        "orgchart.action_edge_added": "Secondary line added",
        # Sub-tabs
        "orgchart.subtab_chart": "Org Chart", "orgchart.subtab_list": "List View",
        "orgchart.subtab_vacancies": "Vacancies", "orgchart.subtab_ai": "AI Assist",
        "orgchart.subtab_templates": "Templates", "orgchart.subtab_history": "History",
        "orgchart.subtab_import": "Import / Export", "orgchart.subtab_settings": "Settings",
        # CSV mapping field labels
        "orgchart.ie_field_full_name": "Name", "orgchart.ie_field_email": "Email",
        "orgchart.ie_field_phone": "Phone", "orgchart.ie_field_job_title": "Job title",
        "orgchart.ie_field_department": "Department", "orgchart.ie_field_manager_name": "Manager (name)",
        "orgchart.ie_field_employment_type": "Employment type", "orgchart.ie_field_vacancy": "Is vacancy (yes/no)",
    }
    pairs.update(orgchart_dyn)
    print(f"Extracted {len(pairs)} t() keys in namespaces {NAMESPACES} (incl. {len(nav)} nav, {len(orgchart_dyn)} orgchart_dyn)")
    en, fr, de = load("en.json"), load("fr.json"), load("de.json")

    # ensure EN has all defaults
    for k, v in pairs.items():
        if get_nested(en, k) != v:
            set_nested(en, k, v)

    # which keys need FR/DE? missing OR equal to English (untranslated)
    need_fr = {k: v for k, v in pairs.items() if not get_nested(fr, k) or get_nested(fr, k) == v}
    need_de = {k: v for k, v in pairs.items() if not get_nested(de, k) or get_nested(de, k) == v}
    print(f"Need FR: {len(need_fr)} · Need DE: {len(need_de)}")

    if need_fr:
        fr_tr = await translate_batch(need_fr, "French")
        for k, v in fr_tr.items():
            if k in pairs:
                set_nested(fr, k, v)
        print(f"FR translated: {len(fr_tr)}")
    if need_de:
        de_tr = await translate_batch(need_de, "German")
        for k, v in de_tr.items():
            if k in pairs:
                set_nested(de, k, v)
        print(f"DE translated: {len(de_tr)}")

    save("en.json", en)
    save("fr.json", fr)
    save("de.json", de)
    print("Merged en/fr/de.json")

if __name__ == "__main__":
    asyncio.run(main())
