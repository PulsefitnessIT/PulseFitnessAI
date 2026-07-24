# FR/DE Internationalisation Rollout

User goal (2026-06): add French & German throughout the platform. Decisions:
customer/prospect-facing FIRST; LLM-generated translations; switcher in the
authenticated app too; fix locale drift; text-only (no number/date format work yet).

## Infra (pre-existing)
- react-i18next + i18next-browser-languagedetector. Config: src/i18n/index.js.
- Locale files: src/i18n/locales/{en,fr,de}.json. Detection order localStorage→navigator;
  cache localStorage key `i18nextLng`. fallbackLng=en.
- Components use `t('key', 'English default')` — inline defaults mean missing en keys
  don't break English.

## Phase 1 — DONE (2026-06), verified
1. **Locale drift fixed** — en was missing 424 keys that fr/de had. Script back-filled
   en from inline `t(k,'default')` defaults across the codebase; all three files now
   aligned at **1824 keys** each (sorted). (18 en-only inline-default keys got an English
   fallback in fr/de — see cleanup.)
2. **Reusable LanguageSwitcher** — src/components/shared/LanguageSwitcher.js (globe + EN/FR/DE,
   testids lang-switcher-btn / lang-option-*). Persists choice to /account/profile when signed in.
3. **Switcher in authenticated app** — added to src/components/shared/ModulePageHeader.js
   (shows on every operator module page, next to the date).
4. **Customer portal** — pages/Deliveries/CustomerDeliveriesTab.js fully translated (namespace
   `deliveries.*`) + switcher in its header.
5. **Public pricing page fully localised** — components/pulse/PulseModulePricing.js and
   PulsePricingExtras.js (module cards, billing toggle, ROI calculator, service tiers, FAQ)
   → namespace `pulse_pricing.*`. Brand/product names (Operations, CRM, Marketing, Memberships,
   Pulse Fitness Pro, Service Desk) intentionally kept untranslated. data-testids kept STABLE
   (derived from keys, not translated labels).
   VERIFIED via screenshot in FR: heading/blurbs/CTA/ROI/FAQ all French, no raw-key leak.

Helper: /tmp/merge_i18n.py takes a {en,fr,de:{dotted_key:value}} JSON and merges into the
three locale files (sorted). Reuse for future namespaces.

## Remaining phases (backlog, priority order)
- P1: Spot-audit signup/login + rest of public marketing pages for hardcoded strings (mostly
  already t()-wired) and fill gaps.
- P1: Other portals — add switcher to Dealer, Logistics, Staff portal headers; translate their strings.
- P2: Operator modules (the bulk) — CRM, Inventory & Distribution, Service Desk, Memberships,
  dashboards, Master Admin. Only ~42/836 component files currently use t().
- P2: Backend-sourced strings (module names/descriptions from APIs, emails) — decide per-locale strategy.
- P3: Number/date/currency locale formatting (deferred by user — text only for now).

## Cleanup
- 18 keys added to fr/de as English fallback during the drift fix (en-only inline defaults with
  no fr/de translation). Low impact; translate on the next pass. Find: keys where fr[k]==en[k]
  and value is Latin English.
