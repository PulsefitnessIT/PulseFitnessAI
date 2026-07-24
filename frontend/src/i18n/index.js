import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './locales/en.json';
import fr from './locales/fr.json';
import de from './locales/de.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, fr: { translation: fr }, de: { translation: de } },
    fallbackLng: 'en',
    supportedLngs: ['en', 'fr', 'de'],
    // Map region variants (fr-FR, fr-CA, de-AT, de-CH, en-GB...) to the base
    // language so a visitor's browser locale auto-selects FR/DE on first visit.
    load: 'languageOnly',
    nonExplicitSupportedLngs: true,
    cleanCode: true,
    interpolation: { escapeValue: false },
    detection: {
      // Returning visitors keep their saved choice; brand-new visitors are
      // auto-detected from their browser language.
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;
