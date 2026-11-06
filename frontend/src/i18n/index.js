import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Locale JSON lives in public/locales and is fetched at runtime (kept out of the JS bundle).
const PublicLocalesBackend = {
  type: 'backend',
  init() {},
  read(lng, _ns, callback) {
    fetch(`/locales/${lng}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`locale ${lng}: ${r.status}`))))
      .then((data) => callback(null, data))
      .catch((err) => callback(err, false));
  },
};

i18n
  .use(PublicLocalesBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'fr', 'de'],
    // Map region variants (fr-FR, de-AT, en-GB...) to the base language.
    load: 'languageOnly',
    nonExplicitSupportedLngs: true,
    cleanCode: true,
    interpolation: { escapeValue: false },
    react: { useSuspense: true },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;
