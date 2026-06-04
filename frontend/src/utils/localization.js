/**
 * Org localization (Iter 220p1 — USA readiness).
 *
 * Resolves the signed-in org's currency / locale / tax vocabulary and exposes
 * a `formatMoney` helper + a `useLocalization` hook. Defaults to UK/GBP so the
 * UI is unchanged for existing customers until an org sets its market.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

export const CURRENCY_SYMBOLS = {
  GBP: '£', USD: '$', EUR: '€', CAD: 'C$', AUD: 'A$',
};

export const DEFAULT_LOCALIZATION = {
  country_code: 'GB',
  country_name: 'United Kingdom',
  currency: 'GBP',
  currency_symbol: '£',
  timezone: 'Europe/London',
  tax_label: 'VAT',
  default_tax_rate: 20.0,
  locale: 'en-GB',
  payment_method: 'BACS',
};

export function currencySymbol(currency) {
  return CURRENCY_SYMBOLS[(currency || '').toUpperCase()] || currency || '£';
}

/** Format an amount with the given currency. Symbol-prefixed, 2dp. */
export function formatMoney(amount, loc = DEFAULT_LOCALIZATION) {
  const currency = (loc && loc.currency) || 'GBP';
  const localeTag = (loc && loc.locale) || 'en-GB';
  try {
    return new Intl.NumberFormat(localeTag, {
      style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    const sym = currencySymbol(currency);
    return `${sym}${Number(amount || 0).toFixed(2)}`;
  }
}

// Simple in-memory cache so multiple components share one fetch per session.
let _cache = null;
let _inflight = null;

export async function fetchLocalization() {
  if (_cache) return _cache;
  if (_inflight) return _inflight;
  const token = (typeof localStorage !== 'undefined' && localStorage.getItem('token')) || '';
  _inflight = axios
    .get(`${API}/org/localization`, { headers: { Authorization: `Bearer ${token}` } })
    .then((r) => {
      _cache = r.data?.localization || DEFAULT_LOCALIZATION;
      return _cache;
    })
    .catch(() => DEFAULT_LOCALIZATION)
    .finally(() => { _inflight = null; });
  return _inflight;
}

/** Clear the cache after a localization change so the next read is fresh. */
export function invalidateLocalization() {
  _cache = null;
}

/** React hook — returns the resolved localization (UK default until loaded). */
export function useLocalization() {
  const [loc, setLoc] = useState(_cache || DEFAULT_LOCALIZATION);
  useEffect(() => {
    let alive = true;
    fetchLocalization().then((l) => { if (alive) setLoc(l); });
    return () => { alive = false; };
  }, []);
  return loc;
}
