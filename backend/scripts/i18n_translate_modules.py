#!/usr/bin/env python3
"""
Generalised i18n helper for the Memberships / Marketing / ServiceOps modules.

Scans the configured module dirs for t('ns.key','English default') calls in the
listed namespaces, translates any NEW/untranslated key EN->FR & EN->DE via Claude,
and merges into i18n/locales/{en,fr,de}.json.

Reuses the exact extraction + translation logic from i18n_translate_ops.py.

Run: cd /app/backend && python scripts/i18n_translate_modules.py
     cd /app/backend && python scripts/i18n_translate_modules.py --check   (guard only)
"""
import os, re, json, asyncio, sys

FE = "/app/frontend/src"
LOCALES = os.path.join(FE, "i18n", "locales")

# Module dirs to scan and the namespaces they own. Add more as batches land.
SCAN_DIRS = [
    os.path.join(FE, "pages", "Memberships"),
    os.path.join(FE, "pages", "Marketing"),
    os.path.join(FE, "pages", "ServiceOps"),
    os.path.join(FE, "pages", "ServiceDesk"),
]
NAMESPACES = ("memberships_console", "mkt", "service", "sicon")


def read_quoted(s, i):
    q = s[i]
    if q not in "'\"`":
        return None, i
    i += 1
    buf = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
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
    for m in re.finditer(r"\bt\(\s*(['\"])", text):
        start = m.end() - 1
        key, j = read_quoted(text, start)
        if key is None or not key.startswith(tuple(n + "." for n in NAMESPACES)):
            continue
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
    for d in SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.endswith(".js") or fn.endswith(".jsx"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        pairs.update(extract_pairs(f.read()))
    return pairs


_NS_T_CALL = re.compile(r"\bt\(\s*['\"](?:%s)\." % "|".join(NAMESPACES))


def guard_missing_hook():
    offenders = []
    for d in SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if not (fn.endswith(".js") or fn.endswith(".jsx")):
                    continue
                path = os.path.join(root, fn)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if not _NS_T_CALL.search(text):
                    continue
                if "useTranslation" not in text:
                    offenders.append(os.path.relpath(path, FE))
    return offenders


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


async def translate_batch(pairs, target_lang_name):
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY") or "sk-emergent-8E60eC543A620FcAaE"
    chat = LlmChat(
        api_key=key,
        session_id=f"i18n-modules-{target_lang_name}",
        system_message=(
            f"You are a professional software UI translator. Translate the given JSON object's "
            f"English UI string VALUES into {target_lang_name}. Keep the JSON keys EXACTLY the same. "
            f"Preserve placeholders, punctuation, leading/trailing spaces, em-dashes, and symbols "
            f"(e.g. '·', '—', '£', '%', ':'). Do NOT translate brand/product names (Pulse, Sage, "
            f"Sicon, Claude, CSV, PIN, NI Number, AI, GDPR). Return ONLY a valid JSON object, no prose."
        ),
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    items = list(pairs.items())
    out = {}
    CH = 60
    for i in range(0, len(items), CH):
        chunk = dict(items[i:i + CH])
        msg = "Translate the VALUES of this JSON to " + target_lang_name + ":\n" + json.dumps(chunk, ensure_ascii=False)
        resp = await chat.send_message(UserMessage(text=msg))
        raw = resp if isinstance(resp, str) else str(resp)
        s = raw.find("{"); e = raw.rfind("}")
        try:
            out.update(json.loads(raw[s:e + 1]))
        except Exception as ex:
            print(f"  ! parse fail chunk {i}: {ex}", file=sys.stderr)
    return out


async def main():
    offenders = guard_missing_hook()
    if offenders:
        print("\n\033[1;31m✗ i18n GUARD FAILED\033[0m — files call namespaced t() but never wire useTranslation():")
        for o in offenders:
            print(f"    • {o}")
        if "--check" in sys.argv:
            sys.exit(1)
    else:
        print("✓ i18n guard: every scanned file using namespaced t() wires useTranslation().")
    if "--check" in sys.argv:
        return

    pairs = scan()
    # Explicit nav labels for the Service Desk shell (rendered via template-literal
    # keys t(`service.nav_${id}`, label) which the static scanner can't extract).
    service_nav = {
        "service.nav_dashboard": "Dashboard", "service.nav_cases": "Cases",
        "service.nav_scheduler": "Scheduler", "service.nav_customers": "Customers",
        "service.nav_equipment": "Equipment", "service.nav_maintenance": "Maintenance",
        "service.nav_stores": "Stores", "service.nav_billing": "Billing",
        "service.nav_analytics": "Analytics", "service.nav_expenses": "Expenses",
        "service.nav_safety": "H&S checklist", "service.nav_compliance": "Compliance",
        "service.nav_overview": "Analytics", "service.nav_suppliers": "Supplier health",
        "service.nav_reports": "Reports", "service.nav_imports": "Import data",
        "service.nav_integrations": "Integrations", "service.nav_audit": "Audit log",
        "service.nav_account": "Account settings", "service.nav_engineers": "Engineers",
        "service.nav_brand": "Service Desk", "service.nav_brand_sub": "Field service ops",
        "service.nav_inventory_distribution": "Inventory & Distribution",
        "service.nav_insights_group": "Insights", "service.nav_options": "Options",
    }
    pairs.update(service_nav)
    # Invoice status chips rendered via t(`memberships_console.inv_status_${status}`, status).
    pairs.update({
        "memberships_console.inv_status_draft": "draft",
        "memberships_console.inv_status_sent": "sent",
        "memberships_console.inv_status_paid": "paid",
        "memberships_console.inv_status_void": "void",
    })
    # Events: kind labels + costume statuses (rendered via template-literal keys).
    pairs.update({
        "memberships_console.evt_kind_recital": "Recital",
        "memberships_console.evt_kind_showcase": "Showcase",
        "memberships_console.evt_kind_competition": "Competition",
        "memberships_console.evt_kind_workshop": "Workshop",
        "memberships_console.evt_kind_camp": "Camp",
        "memberships_console.evt_kind_other": "Event",
        "memberships_console.evt_costume_needed": "needed",
        "memberships_console.evt_costume_ordered": "ordered",
        "memberships_console.evt_costume_arrived": "arrived",
        "memberships_console.evt_costume_fitted": "fitted",
        "memberships_console.evt_costume_paid": "paid",
        "memberships_console.evt_costume_refunded": "refunded",
    })
    print(f"Extracted {len(pairs)} t() keys in namespaces {NAMESPACES} (incl. {len(service_nav)} service_nav)")
    en, fr, de = load("en.json"), load("fr.json"), load("de.json")

    for k, v in pairs.items():
        if get_nested(en, k) != v:
            set_nested(en, k, v)

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
