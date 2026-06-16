/**
 * Pulse Fitness brand assets — wraps the official PNG logos so every surface
 * uses the same source-of-truth artwork.
 *
 *   <PulseFitnessMark />          – just the GA monogram (round contexts: AXIS centre, favicons, mobile nav).
 *   <PulseFitnessMark mono />     – same monogram (mono prop kept for API compatibility, the PNG is already
 *                              the brand gradient so we just render it as-is on light/coloured backgrounds).
 *   <PulseFitnessLockup />        – the full horizontal lockup (GA + GYMAXIS + tagline), used in nav + footer.
 *   <PulseFitnessWordmark />      – the wordmark + tagline only (no GA), useful where the GA is shown separately.
 */

// PNGs live under /public/brand/ so they're served at /brand/* with cache headers.
// We use the auto-trimmed "tight" versions so display heights translate cleanly.
const ASSETS = {
  mark:     '/brand/pulse-mark.svg',        // circular pulse monogram (cyan)
  text:     '/brand/pulse-logo-dark.svg',   // wordmark lockup, dark text for light surfaces
  full:     '/brand/pulse-logo-dark.svg',   // full horizontal lockup (mark + wordmark)
};

export default function PulseFitnessMark({ className = '', ariaLabel = 'Pulse Fitness', mono = false }) {
  return (
    <img
      src={ASSETS.mark}
      alt={ariaLabel}
      className={`select-none object-contain ${mono ? 'gx-mark-on-dark' : ''} ${className}`}
      draggable={false}
    />
  );
}

export function PulseFitnessLockup({ className = '', ariaLabel = 'Pulse Fitness — Smarter Fitness. Stronger Business.' }) {
  return (
    <img
      src={ASSETS.full}
      alt={ariaLabel}
      className={`select-none object-contain ${className}`}
      draggable={false}
    />
  );
}

export function PulseFitnessWordmark({ className = '', ariaLabel = 'Pulse Fitness' }) {
  return (
    <img
      src={ASSETS.text}
      alt={ariaLabel}
      className={`select-none object-contain ${className}`}
      draggable={false}
    />
  );
}
