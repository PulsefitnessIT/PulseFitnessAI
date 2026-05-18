/**
 * Shared dropdown option lists for operations forms.
 *
 * Iter 216h193 — Lee's audit:
 *   "wherever possible give the user a dropdown box already populated …
 *    this speeds up the process, stops the user typing in abbreviations
 *    and spelling mistakes and helps keep text tidy and easy to report on."
 *
 * Keeping these in one module so:
 *   1. The same list appears in onboarding, settings, equipment edit,
 *      fault-logging, and reports filters.
 *   2. Reporting can use the same set as the dropdown when it builds
 *      cross-tabs / charts.
 *   3. When we eventually move these to per-org customisation (vNext)
 *      there's a single hook to flip.
 */

// SLA response times offered to operators. The label is what users see;
// the value is what we store. Hours are normalised so reports can compare
// across rows (e.g. "next business day" → 24h, "4 hour response" → 4h).
export const SLA_RESPONSE_TIME_OPTIONS = [
  { value: '2h',  label: '2-hour response',         hours: 2  },
  { value: '4h',  label: '4-hour response',         hours: 4  },
  { value: '8h',  label: 'Same-day (8 hours)',      hours: 8  },
  { value: '24h', label: 'Next business day (24h)', hours: 24 },
  { value: '48h', label: '48-hour response',        hours: 48 },
  { value: '5d',  label: 'Within 5 working days',   hours: 120 },
  { value: '10d', label: 'Within 10 working days',  hours: 240 },
  { value: 'custom', label: 'Custom / per-contract', hours: null },
];

// Common gym floor zones. Operators can still type a custom location;
// the dropdown is suggestion-only.
export const EQUIPMENT_LOCATION_PRESETS = [
  'Cardio Zone',
  'Strength Zone',
  'Free Weights',
  'Functional Area',
  'Stretch / Mobility',
  'Studio 1',
  'Studio 2',
  'Group Cycling',
  'HIIT / Bootcamp Zone',
  'Reception',
  'Changing Rooms',
  'Pool Area',
  'Spa / Wellness',
  'Outdoor / Garden',
  'Storage',
  'Maintenance Bay',
];

// Equipment categories used by the curated supplier catalogue. Kept
// here so the spec-sheet / image-lookup pipeline can validate against
// the same constant the UI shows.
export const EQUIPMENT_CATEGORY_OPTIONS = [
  { value: 'cardio',          label: 'Cardio' },
  { value: 'strength',        label: 'Strength' },
  { value: 'free_weights',    label: 'Free Weights' },
  { value: 'functional',      label: 'Functional' },
  { value: 'indoor_cycling',  label: 'Indoor Cycling' },
  { value: 'rowers',          label: 'Rowers' },
  { value: 'accessories',     label: 'Accessories' },
  { value: 'wellness',        label: 'Wellness / Recovery' },
];

// Fault severity (already used internally; surfaced for dropdown reuse).
export const FAULT_SEVERITY_OPTIONS = [
  { value: 'low',      label: 'Low — cosmetic / non-blocking' },
  { value: 'medium',   label: 'Medium — degraded function' },
  { value: 'high',     label: 'High — out of service' },
  { value: 'critical', label: 'Critical — safety risk' },
];

// Resolution types (matches health-score's self_fix_rate signal).
export const RESOLUTION_TYPE_OPTIONS = [
  { value: 'self_fix',         label: 'Self-fix (in-house)' },
  { value: 'supplier_warranty', label: 'Supplier under warranty' },
  { value: 'supplier_paid',    label: 'Supplier (paid call-out)' },
  { value: 'engineer',         label: 'GymAxis engineer' },
  { value: 'parts_only',       label: 'Parts only' },
  { value: 'replaced',         label: 'Replaced unit' },
];
