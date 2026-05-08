/**
 * useBrand() — Strategy B brand resolver.
 *
 * Iter 215d. The product strategy:
 *   • Marketing surfaces (public homepage, login, pricing, features) are
 *     ALWAYS GymAxis-branded — that's the parent product's identity.
 *   • Authenticated in-app surfaces are Pulse-Fitness-branded for any
 *     operator-facing module (Operations, Memberships, Marketing, CRM,
 *     Service Desk, Gym Floor). Master Admin (GymAxis HQ console) and
 *     MOD Service Portal keep their own identity.
 *
 * Use this hook anywhere you'd previously checked `account_type === 'pulse_pro'`
 * or hand-rolled a brand decision.
 */
import { useMemo } from 'react';

const PULSE = {
  id: 'pulse',
  name: 'Pulse Fitness',
  shortName: 'Pulse',
  accent: '#19CDFF',         // cyan
  accentText: '#0A0C10',     // dark text on cyan
  logoUrl: 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg',
  fontHeading: 'pulse-font-heading',
  fontBody: 'pulse-font-body',
};

const GYMAXIS = {
  id: 'gymaxis',
  name: 'GymAxis AI',
  shortName: 'GymAxis',
  accent: '#0055FF',         // blue
  accentText: '#FFFFFF',
  logoUrl: null,             // wordmark only on marketing
  fontHeading: 'pulse-font-heading',
  fontBody: 'pulse-font-body',
};

/**
 * Resolve the active brand for a given context.
 *
 * @param user      Platform user (or CRM user) — null when unauthenticated.
 * @param surface   'marketing' | 'app' | 'master-admin' | 'mod' — the
 *                  surface the page belongs to. Defaults to 'app'.
 */
export const useBrand = (user, surface = 'app') => {
  return useMemo(() => {
    if (surface === 'marketing') return GYMAXIS;
    if (surface === 'master-admin') return GYMAXIS;
    if (surface === 'mod') return GYMAXIS;
    // Authenticated in-app surfaces → always Pulse for end customers.
    // GymAxis-internal staff (`is_master_admin`) browsing the operator
    // surfaces should still see the customer's brand to match what the
    // customer sees (great for support / training).
    if (user) return PULSE;
    // Unauthenticated → fall back to GymAxis (marketing).
    return GYMAXIS;
  }, [user, surface]);
};

export const BRANDS = { PULSE, GYMAXIS };
