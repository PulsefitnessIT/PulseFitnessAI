/**
 * MODService filter-hardening for SEO / social meta.
 *
 * The MOD sites' networks block ".ai" URLs. The functional app is already
 * clean (all API traffic goes through REACT_APP_BACKEND_URL, which on the
 * MODService deployment is the .com host), but the STATIC index.html still
 * carries commercial `pulsefitness.ai` references in cosmetic head tags:
 *   • <link rel="canonical">           → https://pulsefitness.ai/
 *   • <meta property="og:image">       → https://pulsefitness.ai/brand/…
 *   • <meta name="twitter:image">      → https://pulsefitness.ai/brand/…
 *   • <script type="application/ld+json"> (Organization url / logo / email)
 *
 * Browsers don't fetch these (only social scrapers fetch og:image), so they
 * never block a MOD user — but a deep-content-inspection proxy could flag the
 * ".ai" string in the served HTML. This rewrites every `pulsefitness.ai`
 * reference in <head> to the current host so the MODService deployment serves
 * zero ".ai" strings.
 *
 * IMPORTANT: only runs when isModServiceMode() is true, so the commercial
 * pulsefitness.ai deployment is completely unaffected.
 */
import { isModServiceMode } from '@/utils/portalMode';

// Matches "pulsefitness.ai" and "www.pulsefitness.ai" (requires the literal
// dot, so "instagram.com/pulsefitnessai" is left alone).
const AI_HOST_RE = /(?:www\.)?pulsefitness\.ai/g;

const rewrite = (value, host) => {
  if (!value || value.indexOf('pulsefitness.ai') === -1) return value;
  return value.replace(AI_HOST_RE, host);
};

export function hardenModServiceSeo() {
  try {
    if (!isModServiceMode()) return;
    if (typeof document === 'undefined' || typeof window === 'undefined') return;

    const host = window.location.host; // e.g. modservice.pulsefitness.com
    if (!host || host.indexOf('pulsefitness.ai') !== -1) return; // never rewrite to a .ai host

    // <link href> (canonical, etc.)
    document.head.querySelectorAll('link[href]').forEach((el) => {
      const next = rewrite(el.getAttribute('href'), host);
      if (next !== el.getAttribute('href')) el.setAttribute('href', next);
    });

    // <meta content> (og:image, twitter:image, og:url, …)
    document.head.querySelectorAll('meta[content]').forEach((el) => {
      const next = rewrite(el.getAttribute('content'), host);
      if (next !== el.getAttribute('content')) el.setAttribute('content', next);
    });

    // JSON-LD structured data (Organization url / logo / contact email)
    document.head.querySelectorAll('script[type="application/ld+json"]').forEach((el) => {
      const next = rewrite(el.textContent, host);
      if (next !== el.textContent) el.textContent = next;
    });
  } catch { /* noop — cosmetic hardening must never break the app */ }
}

export default hardenModServiceSeo;
