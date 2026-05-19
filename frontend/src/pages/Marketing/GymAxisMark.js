/**
 * GymAxis brand assets — wraps the official PNG logos so every surface
 * uses the same source-of-truth artwork.
 *
 *   <GymAxisMark />          – just the GA monogram (round contexts: AXIS centre, favicons, mobile nav).
 *   <GymAxisMark mono />     – same monogram (mono prop kept for API compatibility, the PNG is already
 *                              the brand gradient so we just render it as-is on light/coloured backgrounds).
 *   <GymAxisLockup />        – the full horizontal lockup (GA + GYMAXIS + tagline), used in nav + footer.
 *   <GymAxisWordmark />      – the wordmark + tagline only (no GA), useful where the GA is shown separately.
 */

// PNGs live under /public/brand/ so they're served at /brand/* with cache headers.
// We use the auto-trimmed "tight" versions so display heights translate cleanly.
const ASSETS = {
  mark:     '/brand/gymaxis-mark-tight.png',   // ~861×676  → ratio 1.27 : 1
  text:     '/brand/gymaxis-text-tight.png',   // ~1334×286 → ratio 4.66 : 1
  full:     '/brand/gymaxis-full-tight.png',   // ~1434×255 → ratio 5.62 : 1
};

export default function GymAxisMark({ className = '', ariaLabel = 'GymAxis', mono = false }) {
  return (
    <img
      src={ASSETS.mark}
      alt={ariaLabel}
      className={`select-none object-contain ${mono ? 'gx-mark-on-dark' : ''} ${className}`}
      draggable={false}
    />
  );
}

export function GymAxisLockup({ className = '', ariaLabel = 'GymAxis — Smarter Fitness. Stronger Business.' }) {
  return (
    <img
      src={ASSETS.full}
      alt={ariaLabel}
      className={`select-none object-contain ${className}`}
      draggable={false}
    />
  );
}

export function GymAxisWordmark({ className = '', ariaLabel = 'GymAxis' }) {
  return (
    <img
      src={ASSETS.text}
      alt={ariaLabel}
      className={`select-none object-contain ${className}`}
      draggable={false}
    />
  );
}
