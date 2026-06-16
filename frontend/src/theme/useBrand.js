/**
 * useBrand() — Strategy B brand resolver.
 *
 * Iter 215d. The product strategy:
 *   • Marketing surfaces (public homepage, login, pricing, features) are
 *     ALWAYS Pulse Fitness-branded — that's the parent product's identity.
 *   • Authenticated in-app surfaces are Pulse-Fitness-branded for any
 *     operator-facing module (Operations, Memberships, Marketing, CRM,
 *     Service Desk, Gym Floor). Master Admin (Pulse Fitness HQ console) and
 *     MOD Service Portal keep their own identity.
 *
 * Use this hook anywhere you'd previously checked `account_type === 'pulse_pro'`
 * or hand-rolled a brand decision.
 */
import { useMemo } from 'react';

const PULSE = {
  id: 'pulse',
  name: 'Pulse Fitness AI',
  shortName: 'Pulse Fitness',
  accent: '#19CDFF',         // cyan
  accentText: '#0A0C10',     // dark text on cyan
  logoUrl: 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg',
  fontHeading: 'pulse-font-heading',
  fontBody: 'pulse-font-body',
};

// Legacy export kept for back-compat — now mirrors the Pulse Fitness brand so
// every surface is Pulse-branded (full white-label conversion).
const GYMAXIS = { ...PULSE };

/**
 * Resolve the active brand for a given context.
 *
 * @param user      Platform user (or CRM user) — null when unauthenticated.
 * @param surface   'marketing' | 'app' | 'master-admin' | 'mod' — the
 *                  surface the page belongs to. Defaults to 'app'.
 */
export const useBrand = (user, surface = 'app') => {
  return useMemo(() => {
    // Full white-label conversion: every surface is Pulse Fitness AI branded.
    return PULSE;
  }, [user, surface]);
};

export const BRANDS = { PULSE, GYMAXIS };
