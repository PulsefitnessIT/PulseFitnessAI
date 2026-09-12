/**
 * MODService deployment mode.
 *
 * The MOD sites' networks block ".ai" URLs, so the MOD experience is served
 * from a second Emergent deployment on MODService.pulsefitness.com. That
 * deployment runs THIS SAME codebase with REACT_APP_PORTAL_MODE=modservice,
 * which flips the public entry point to the MOD Service Portal sign-in.
 *
 * Detection order:
 *   1. Build/runtime env flag  (set on the MODService deployment only)
 *   2. Host-based             (modservice.* domain)
 *   3. Preview override        ?portal=modservice  (sticky for the session,
 *      so we can verify the MODService experience in the .ai preview before
 *      the real domain is live). ?portal=pulse clears it.
 */
export function isModServiceMode() {
  try {
    if ((process.env.REACT_APP_PORTAL_MODE || '').toLowerCase() === 'modservice') return true;

    const host = (typeof window !== 'undefined' ? window.location.hostname : '').toLowerCase();
    if (host.startsWith('modservice.')) return true;

    if (typeof window !== 'undefined') {
      const q = (new URLSearchParams(window.location.search).get('portal') || '').toLowerCase();
      if (q === 'modservice') { try { sessionStorage.setItem('portal_mode', 'modservice'); } catch { /* noop */ } return true; }
      if (q === 'pulse' || q === 'standard') { try { sessionStorage.removeItem('portal_mode'); } catch { /* noop */ } return false; }
      try { if (sessionStorage.getItem('portal_mode') === 'modservice') return true; } catch { /* noop */ }
    }
  } catch { /* noop */ }
  return false;
}

/** Public URL of the commercial (pulsefitness.ai) experience — used to bounce
 *  commercial/staff users who land on the MODService portal by mistake. */
export const COMMERCIAL_URL = process.env.REACT_APP_COMMERCIAL_URL || 'https://pulsefitness.ai';
