/**
 * i18n micro-helper (iter 215c0).
 *
 * Wires the existing /src/i18n/locales/en.json dictionary to a tiny `t()`
 * function that other modules can import without taking the full
 * react-i18next dependency further than it already is. Falls back to the
 * fallback string (or key) if a translation is missing.
 *
 * Usage:
 *   import { t } from '@/utils/i18n';
 *   <h1>{t('nav.dashboard', 'Dashboard')}</h1>
 */
import en from '@/i18n/locales/en.json';

const DICTS = { en };

let currentLang = 'en';

const get = (dict, path) => {
  const parts = (path || '').split('.');
  let cur = dict;
  for (const p of parts) {
    if (cur && typeof cur === 'object' && p in cur) cur = cur[p];
    else return undefined;
  }
  return typeof cur === 'string' ? cur : undefined;
};

export const t = (key, fallback = '') => {
  const fromDict = get(DICTS[currentLang] || en, key);
  if (fromDict != null) return fromDict;
  if (currentLang !== 'en') {
    const fromEn = get(en, key);
    if (fromEn != null) return fromEn;
  }
  return fallback || key;
};

export const setLang = (lang) => {
  currentLang = lang in DICTS ? lang : 'en';
};

export const getLang = () => currentLang;

export const registerLocale = (lang, dict) => { DICTS[lang] = dict; };

export default t;
