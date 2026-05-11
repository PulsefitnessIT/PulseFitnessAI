/**
 * Iter 216h17 — Master Admin brand context (P1+P2 of the Master Admin
 * IA redesign, per /app/design_guidelines.json).
 *
 * Single React context that holds the operator's "I'm currently
 * looking at..." choice: All / Pulse Fitness / GymAxis. The value is
 * persisted to localStorage so the choice survives reloads.
 *
 * Components READ from this context to filter data; they MUST NOT
 * duplicate the filter logic across surfaces. This becomes the
 * single switch between the two brands across every Master Admin
 * panel (replaces the ad-hoc `gymaxisOnly` flag scattering).
 */
import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';

const STORAGE_KEY = 'master_admin_brand_filter';
export const BRAND_OPTIONS = [
  { id: 'all', label: 'All Brands', short: 'All', accent: '#0A0A0A' },
  { id: 'pulse', label: 'Pulse Fitness', short: 'Pulse', accent: '#0055FF' },
  { id: 'gymaxis', label: 'GymAxis', short: 'GymAxis', accent: '#10B981' },
];

const BrandContext = createContext({
  brand: 'all',
  setBrand: () => {},
  brandLabel: 'All Brands',
});

export const BrandContextProvider = ({ children }) => {
  const [brand, setBrandState] = useState(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      if (BRAND_OPTIONS.some((o) => o.id === v)) return v;
    } catch { /* SSR or denied */ }
    return 'all';
  });

  const setBrand = useCallback((next) => {
    if (!BRAND_OPTIONS.some((o) => o.id === next)) return;
    setBrandState(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  }, []);

  // Fire a window event so non-React legacy code (some panels still
  // read directly from localStorage) can reactively refresh.
  useEffect(() => {
    try { window.dispatchEvent(new CustomEvent('master-admin-brand-change', { detail: { brand } })); } catch { /* noop */ }
  }, [brand]);

  const value = useMemo(() => ({
    brand,
    setBrand,
    brandLabel: (BRAND_OPTIONS.find((o) => o.id === brand) || BRAND_OPTIONS[0]).label,
    brandShort: (BRAND_OPTIONS.find((o) => o.id === brand) || BRAND_OPTIONS[0]).short,
    brandAccent: (BRAND_OPTIONS.find((o) => o.id === brand) || BRAND_OPTIONS[0]).accent,
  }), [brand, setBrand]);

  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
};

export const useBrandContext = () => useContext(BrandContext);

/** Pure helper — apply the brand filter to an array of records that
 *  have a `brand` field or an inferable shape. Until each panel
 *  adopts its own scoping logic, components can call this to get a
 *  shared default. */
export const filterByBrand = (records, brand) => {
  if (!Array.isArray(records) || !brand || brand === 'all') return records || [];
  return records.filter((r) => {
    const rb = (r?.brand || r?.account_type || '').toLowerCase();
    if (brand === 'pulse') return rb === 'pulse' || rb === 'pulse_fitness' || rb === 'pulse_pro';
    if (brand === 'gymaxis') return rb === 'gymaxis' || rb === 'full' || rb === '';
    return true;
  });
};

export default BrandContext;
