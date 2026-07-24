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

## Phase 1b — Browser/region auto-detect + cookie banner (DONE, verified)
- src/i18n/index.js: added supportedLngs=['en','fr','de'], load='languageOnly',
  nonExplicitSupportedLngs=true, cleanCode=true. FIX: a fr-FR/de-DE browser previously fell
  back to English (no region-variant resource); now variants map to the base language, so a
  first-time FR/DE visitor auto-lands in FR/DE. Order kept localStorage→navigator (returning
  visitors keep their saved choice). VERIFIED: navigator=fr-FR + cleared localStorage → pricing in FR.
- components/shared/CookieConsent.js internationalised (namespace cookie.*) — was the one English
  element on the auto-detected French page. VERIFIED in FR.

## Phase 1c — Region/language → currency nudge (DONE, verified)
- components/pulse/PulseModulePricing.js: the displayed currency now follows the UI language so the
  price matches the words. langCcy(lang, detected): FR/DE → 'eur'; EN → IP-detected (gbp/usd) else 'gbp'.
  Applied on load and re-applied when the visitor switches language — UNLESS they manually pick a
  currency (ccyPicked flag), which then wins. VERIFIED: navigator=de-DE + cleared localStorage →
  German text with the € EUR toggle active and €79/€59/€89 prices.

## Phase 2a — Switcher in all sub-portals (DONE, switcher verified)
- LanguageSwitcher added to Dealer (DealerPortalStandalone.js), Logistics (LogisticsPortal.js) and
  Staff (StaffPortal.js) portal headers. LanguageSwitcher.js hardened with CSS-var fallbacks
  (--theme-*, #… defaults) so it renders correctly on the standalone light-themed portals too.
  VERIFIED: logistics portal shows the globe+FR switcher; selecting FR flipped the shared cookie
  banner to French. NOTE: the portals' OWN content strings (e.g. "Upcoming installations",
  "Install pack") are NOT yet translated — that's the P2 per-portal string pass.

## Remaining (large) work
- P2 per-portal strings: Dealer, Logistics, Staff, Customer portal content.
- P2 operator modules (the bulk): CRM, Inventory & Distribution, Service Desk, Memberships,
  dashboards, Master Admin — only ~42/836 components use t(). Multi-pass effort.
- P2 backend-sourced strings & transactional emails.
- P1 spot-audit: signup/login + remaining public marketing pages (mostly t()-wired already).

## Cleanup
- 18 keys added to fr/de as English fallback during the drift fix (en-only inline defaults with
  no fr/de translation). Low impact; translate on the next pass. Find: keys where fr[k]==en[k]
  and value is Latin English.
