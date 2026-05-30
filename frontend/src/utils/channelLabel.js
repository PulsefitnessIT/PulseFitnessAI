/**
 * channelLabel.js — Iter 220cp
 *
 * Single source of truth for translating raw `intake_channel` / `source`
 * codes into human-friendly labels + colour treatments.
 *
 * Cross-module: used by the Engineer app (`EngineerJobDetailV2`,
 * `EngineerNewJob`) and the Operations Portal / Service Desk drawers
 * so a case logged via "Customer portal" or "Email inbox" reads the
 * same everywhere.
 *
 * Sources we know about today:
 *   manual         — engineer logged it at the counter
 *   phone          — phone call (logged by anyone)
 *   email          — manual email-to-case entry
 *   inbound_email  — auto-parsed from a poll of the support inbox
 *   portal         — customer self-serve portal
 *   embed_widget   — embedded fault widget on a partner site
 *   supplier_card  — supplier-dispatched job-request card
 *   service_desk   — service desk operator logged it
 *   other          — anything else / referral
 */

const CHANNEL_MAP = {
  manual:         { label: 'Walked in / counter', cls: 'bg-slate-100 text-slate-700 border-slate-200' },
  phone:          { label: 'Phone call',          cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  email:          { label: 'Email request',       cls: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  inbound_email:  { label: 'Email inbox',         cls: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  portal:         { label: 'Customer portal',     cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  embed_widget:   { label: 'Embedded widget',     cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  supplier_card:  { label: 'Supplier card',       cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  service_desk:   { label: 'Service desk',        cls: 'bg-violet-50 text-violet-700 border-violet-200' },
  other:          { label: 'Other / referral',    cls: 'bg-slate-100 text-slate-700 border-slate-200' },
};

/**
 * Resolve a channel descriptor from a case-shaped object.
 *
 * Prefers `intake_channel` (engineer-facing field) and falls back to
 * `source` (operations-portal field) so the engineer app keeps working
 * even for historical cases that only carry `source`.
 *
 * Returns `null` when nothing is set, so the caller can skip the chip.
 */
export function resolveChannel(caseLike) {
  if (!caseLike || typeof caseLike !== 'object') return null;
  const code = (caseLike.intake_channel || caseLike.source || '').toString().toLowerCase().trim();
  if (!code) return null;
  return { code, ...(CHANNEL_MAP[code] || { label: code.replace(/_/g, ' '), cls: 'bg-slate-100 text-slate-700 border-slate-200' }) };
}

export const CHANNEL_LABEL = CHANNEL_MAP;
